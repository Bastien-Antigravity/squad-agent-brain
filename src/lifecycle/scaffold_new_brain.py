#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Scaffolds a new Bastien-Antigravity ecosystem directory by creating the 
standard folder structure, mandatory governance files, standalone.yaml symlink,
and baking the AI Squad DNA into .agents/skills.

DATA FLOW:
1. Inputs project name and destination path via CLI arguments or user prompts.
2. Creates the 2-Digit standard directory hierarchy (00-99).
3. Copies Role-Prompts and Squad-Agent from the parent brain vault root.
4. Generates AGENTS.md, README.md, VERSION.txt, .gitignore, standalone.yaml symlink.
5. Injects compliant YAML frontmatter into AI-Project-DNA, AI-Session-State, AI-Init, and Ecosystem-Map-MOC.
6. Invokes convert_agents.py to initialize subagents and skills in the new target.

KEY PARAMETERS:
- target_name: Name of the new brain (e.g. trading-brain).
- target_path: The filesystem path where the new brain will be built.
- dry_run: If True, previews creation without writing to disk.
"""

import argparse
import os
import socket
import sys
from pathlib import Path
from shutil import copytree as shutilCopytree, copy as shutilCopy, ignore_patterns as shutilIgnorePatterns
from subprocess import run as subprocessRun
from sys import executable as sysExecutable
from typing import Optional, Tuple, Any, Set

# Standard ecosystem bootstrap
import src.bootstrap as bootstrap
from lib.orchestration_lib import setup_terminal, resolve_vault_and_workspace

logger = bootstrap.logger

# -----------------------------------------------------------------------------

def is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    """Checks whether a port is currently open and accepting connections."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.3)
            return s.connect_ex((host, port)) == 0
    except OSError:
        return False

# -----------------------------------------------------------------------------

def get_allocated_ecosystem_ports(app_config: Any = None) -> Set[int]:
    """
    Dynamically extracts all ports declared across ecosystem capabilities
    directly from the active configuration profile (single source of truth).
    """
    allocated: Set[int] = set()
    active_cfg = app_config if app_config is not None else bootstrap.config
    config_data = getattr(active_cfg, "data", {}) if active_cfg else {}
    caps = config_data.get("capabilities", {})
    for _, c_val in caps.items():
        if isinstance(c_val, dict):
            for k, v in c_val.items():
                if "port" in k and str(v).isdigit():
                    allocated.add(int(v))
                elif isinstance(v, dict):
                    for sub_k, sub_v in v.items():
                        if "port" in sub_k and str(sub_v).isdigit():
                            allocated.add(int(sub_v))
    return allocated

# -----------------------------------------------------------------------------

def resolve_available_ports(target_path: Path, app_config: Any = None) -> Tuple[int, int]:
    """
    Finds the next free non-colliding (HTTP, gRPC) port pair for the satellite brain.
    Extracts allocated ports dynamically from the ecosystem configuration and verifies
    local socket availability without any hardcoded port constants or .env files.
    """
    active_cfg = app_config if app_config is not None else bootstrap.config
    used_ports = get_allocated_ecosystem_ports(active_cfg)

    squad_cap = (getattr(active_cfg, "data", {})
                 .get("capabilities", {})
                 .get("squad_agent", {}))
    base_port_val = squad_cap.get("satellite_base_port", 8185)
    base_grpc_val = squad_cap.get("satellite_base_grpc_port", 8187)
    base_port = int(base_port_val) if str(base_port_val).isdigit() else 8185
    base_grpc_port = int(base_grpc_val) if str(base_grpc_val).isdigit() else 8187
    port_gap = base_grpc_port - base_port if base_grpc_port > base_port else 2

    # Dynamically scan sibling directories for existing satellite docker-compose.yaml files
    parent = target_path.parent
    if parent.exists():
        for sibling in parent.iterdir():
            compose_file = sibling / "docker-compose.yaml"
            if sibling.is_dir() and compose_file.exists():
                try:
                    for line in compose_file.read_text(encoding="utf-8").splitlines():
                        if "SA_PORT" in line or "SA_GRPC_PORT" in line:
                            for token in line.replace(":", " ").replace("-", " ").replace("}", " ").replace('"', ' ').replace("'", ' ').split():
                                if token.isdigit():
                                    used_ports.add(int(token))
                except Exception:
                    pass

    port = base_port
    while True:
        grpc_port = port + port_gap
        if port not in used_ports and grpc_port not in used_ports:
            if not is_port_in_use(port) and not is_port_in_use(grpc_port):
                return port, grpc_port
        port += 10

# -----------------------------------------------------------------------------

def launch_satellite_docker(target_path: Path, brain_name: str, sa_port: int) -> bool:
    """Launches the newly scaffolded satellite brain squad-agent in Docker."""
    logger.info(f"ScaffoldNewBrain : Launching satellite squad-agent for '{brain_name}' in Docker...")
    try:
        res = subprocessRun(["docker", "info"], capture_output=True, text=True)
        if res.returncode != 0:
            logger.warning("ScaffoldNewBrain : Docker daemon is not active. Skipping container launch.")
            return False

        net_check = subprocessRun(["docker", "network", "inspect", "teleremote-network"], capture_output=True, text=True)
        if net_check.returncode != 0:
            logger.info("ScaffoldNewBrain : Creating Docker bridge network 'teleremote-network'...")
            subprocessRun(["docker", "network", "create", "teleremote-network"], check=True)

        run_res = subprocessRun(["docker", "compose", "up", "-d"], cwd=str(target_path), capture_output=True, text=True)
        if run_res.returncode == 0:
            logger.info(f"   🐳 Successfully launched 'squad-agent-{brain_name}' in Docker on port {sa_port}!")
            return True
        else:
            logger.warning(f"ScaffoldNewBrain : docker compose failed: {run_res.stderr.strip()}")
            return False
    except Exception as e:
        logger.warning(f"ScaffoldNewBrain : Could not launch Docker container: {e}")
        return False


# -----------------------------------------------------------------------------

def create_file(path: Path, content: str, dry_run: bool = False) -> None:
    """Creates a file with parent directory creation, respecting dry-run mode."""
    if dry_run:
        logger.info(f"   [DRY-RUN] Would create: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    logger.info(f"   ✅ Created: {path.name}")

# -----------------------------------------------------------------------------

def create_symlink(target_path: Path, link_target: str, dry_run: bool = False) -> None:
    """Creates a symbolic link, respecting dry-run mode."""
    if dry_run:
        logger.info(f"   [DRY-RUN] Would symlink: {target_path} -> {link_target}")
        return
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if target_path.is_symlink() or target_path.exists():
        target_path.unlink()
    os.symlink(link_target, target_path)
    logger.info(f"   🔗 Symlinked: {target_path.name} -> {link_target}")

# -----------------------------------------------------------------------------

def scaffold_brain(
    target_name: str,
    target_path: Path,
    vault_root: Path,
    dry_run: bool = False,
    launch_docker: bool = False,
    sa_port: Optional[int] = None,
    sa_grpc_port: Optional[int] = None
) -> None:
    """
    Executes complete scaffolding of a new Bastien-Antigravity brain vault.
    """
    logger.info(f"ScaffoldNewBrain : Fabricating '{target_name}' at {target_path}...")

    # 0. Resolve non-colliding host ports for the satellite squad agent
    if sa_port is None or sa_grpc_port is None:
        auto_port, auto_grpc = resolve_available_ports(target_path)
        sa_port = sa_port or auto_port
        sa_grpc_port = sa_grpc_port or auto_grpc
    logger.info(f"ScaffoldNewBrain : Allocated ports -> HTTP: {sa_port}, gRPC: {sa_grpc_port}")

    # 1. Create Double-Digit Folder Hierarchy
    folders = [
        "00-AI-Orchestration",
        "01-Strategic-Nexus",
        "02-Business-BDD",
        "03-Tech-Stack",
        "04-Rapid-Prototyping",
        "05-Fleet-Operation",
        "06-Microservices",
        "07-Core-KMS/Role-Prompts",
        "08-Squad-Agent",
        "99-Humans",
        "quick-overview",
    ]
    
    for folder in folders:
        d = target_path / folder
        if dry_run:
            logger.info(f"   [DRY-RUN] Would create directory: {d}")
        else:
            d.mkdir(parents=True, exist_ok=True)

    # 2. Copy "DNA" (Role Prompts, Squad-Agent, Governance Config, Repo Control & Tech Stack)
    logger.info("ScaffoldNewBrain : Copying AI Squad DNA...")
    role_prompts_src = vault_root / "07-Core-KMS" / "Role-Prompts"
    if role_prompts_src.exists():
        dest_prompts = target_path / "07-Core-KMS" / "Role-Prompts"
        if dry_run:
            logger.info(f"   [DRY-RUN] Would copy {role_prompts_src} -> {dest_prompts}")
        else:
            shutilCopytree(role_prompts_src, dest_prompts, dirs_exist_ok=True)
    
    squad_agent_src = vault_root / "08-Squad-Agent"
    if squad_agent_src.exists():
        dest_scripts = target_path / "08-Squad-Agent"
        if dry_run:
            logger.info(f"   [DRY-RUN] Would copy {squad_agent_src} -> {dest_scripts}")
        else:
            shutilCopytree(
                squad_agent_src,
                dest_scripts,
                dirs_exist_ok=True,
                ignore=shutilIgnorePatterns(".venv*", "__pycache__", "*.pyc", ".pytest_cache*", ".git*")
            )

    config_src = vault_root / "00-AI-Orchestration" / "Config"
    if config_src.exists():
        dest_config = target_path / "00-AI-Orchestration" / "Config"
        if dry_run:
            logger.info(f"   [DRY-RUN] Would copy {config_src} -> {dest_config}")
        else:
            shutilCopytree(config_src, dest_config, dirs_exist_ok=True)

    repo_control_src = vault_root / "05-Fleet-Operation" / "00-Repo-Control"
    if repo_control_src.exists():
        dest_repo_control = target_path / "05-Fleet-Operation" / "00-Repo-Control"
        if dry_run:
            logger.info(f"   [DRY-RUN] Would copy {repo_control_src} -> {dest_repo_control}")
        else:
            shutilCopytree(repo_control_src, dest_repo_control, dirs_exist_ok=True)

    tech_stack_src = vault_root / "03-Tech-Stack"
    if tech_stack_src.exists():
        dest_tech_stack = target_path / "03-Tech-Stack"
        if dry_run:
            logger.info(f"   [DRY-RUN] Would copy {tech_stack_src} -> {dest_tech_stack}")
        else:
            shutilCopytree(tech_stack_src, dest_tech_stack, dirs_exist_ok=True)

    # 3. Create Root Ecosystem Files
    logger.info("ScaffoldNewBrain : Creating root ecosystem files...")
    
    # standalone.yaml symlink
    create_symlink(target_path / "standalone.yaml", "../docker-deployment/modes/local/config/native.yaml", dry_run)

    # VERSION.txt
    create_file(target_path / "VERSION.txt", "0.0.1\n", dry_run)

    # .gitignore
    gitignore_content = """# Environments
.venv/
env/
venv/
ENV/

# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.pytest_cache/

# IDE & OS
.DS_Store
.idea/
.vscode/
*.swp
*.swo

# Runtime Data
fs_data/
fs_temp/
*.log
"""
    create_file(target_path / ".gitignore", gitignore_content, dry_run)

    # AGENTS.md
    agents_md = f"""---
microservice: {target_name}
type: rules
status: active
tags:
- '#service/{target_name}'
- '#domain/knowledge'
- '#type/rules'
- '#state/active'
- '#zone/0-core'
- '#ai/ignore'
---

# AGENTS.md: {target_name}

## Repository Mission & Architecture Role
`{target_name}` is an autonomous knowledge vault, domain intelligence engine, and pluggable satellite squad for the Bastien-Antigravity ecosystem.

- **Primary Structure**:
  - `00-AI-Orchestration`: Agent personas, coordination protocols, squad directives
  - `02-Business-BDD`: Domain glossary, BDD behavior specifications, acceptance criteria
  - `03-Tech-Stack`: Technical standards, networking protocols, domain blueprints
  - `06-Microservices`: Service specification sheets, endpoint registries, capability maps
  - `07-Core-KMS`: Operational prompts, key management references
  - `08-Squad-Agent`: AI squad operational engine room, CLI utilities (`main.py`)
- **Configuration Link**: `standalone.yaml -> ../docker-deployment/modes/local/config/native.yaml`

## Key Commands & Verification
```bash
# Start in Docker (Recommended - connects to fleet teleremote-network)
make up
# or
docker compose up -d

# Check status & logs
make status
make logs

# Stop container
make down

# Run locally in native Python
python3 08-Squad-Agent/main.py preflight-check
python3 08-Squad-Agent/main.py squad-agent
```

## AI Development & Integration Guidelines
1. **Never Contradict Architecture Blueprints**: Refer to `03-Tech-Stack/` before making cross-service design changes.
2. **Markdown Frontmatter Standard**: Every markdown file in this vault MUST begin with canonical YAML frontmatter (`microservice`, `type`, `status`, `tags`).
3. **Triple-Block Header in Code**: Any code script must adhere to the Triple-Block header (`ESSENTIAL PROCESS`, `DATA FLOW`, `KEY PARAMETERS`).
4. **Encrypted Credentials**: Never commit plaintext secrets to markdown notes or config files. Use `ENC(...)` tokens.
5. **No Broken Links**: Always use relative links or verified obsidian wikilinks.
"""
    create_file(target_path / "AGENTS.md", agents_md, dry_run)

    # README.md
    readme_content = f"""# 🧠 {target_name.replace('-', ' ').title()}

Bastien-Antigravity Ecosystem Knowledge Vault and Domain Orchestration Hub.

## 🚀 Quick Start
### Option A: Docker (Zero-Config, Plugs into Fleet)
```bash
make up       # Starts squad-agent on port {sa_port} connected to central teleremote-network
make logs     # Follow agent logs
make down     # Stop agent
```

### Option B: Native Python
```bash
python3 08-Squad-Agent/main.py preflight-check
python3 08-Squad-Agent/main.py squad-agent
```

## 📁 Vault Structure
- `00-AI-Orchestration`: AI squad coordination and session state
- `01-Strategic-Nexus`: Strategic objectives and anti-backlog
- `02-Business-BDD`: Domain specifications and Gherkin scenarios
- `03-Tech-Stack`: Architecture standards and protocols
- `06-Microservices`: Microservice hubs and registries
- `07-Core-KMS`: Security policies and squad role prompts
- `08-Squad-Agent`: Fleet management and scaffolding automation
"""
    create_file(target_path / "README.md", readme_content, dry_run)

    # docker-compose.yaml
    docker_compose_content = f"""# =============================================================================
# Satellite Brain Squad Agent Compose: {target_name}
# Pluggable autonomous agent workshop connecting to central teleremote-network.
# Configuration is sourced strictly from standalone.yaml (ecosystem standard).
# =============================================================================
services:
  squad-agent:
    build:
      context: ./08-Squad-Agent
      dockerfile: Dockerfile
    image: ghcr.io/bastien-antigravity/squad-agent-{target_name}:${{TAG:-latest}}
    container_name: squad-agent-${{BRAIN_ID:-{target_name}}}
    restart: unless-stopped
    ports:
      - "${{HOST_IP:-127.0.0.1}}:${{SA_PORT:-{sa_port}}}:${{SA_PORT:-{sa_port}}}"
      - "${{HOST_IP:-127.0.0.1}}:${{SA_GRPC_PORT:-{sa_grpc_port}}}:${{SA_GRPC_PORT:-{sa_grpc_port}}}"
    environment:
      - DOCKER_ENV=true
      - BRAIN_ID=${{BRAIN_ID:-{target_name}}}
      - TARGET_BRAIN_ID=${{BRAIN_ID:-{target_name}}}
      - SA_PORT=${{SA_PORT:-{sa_port}}}
      - SA_GRPC_PORT=${{SA_GRPC_PORT:-{sa_grpc_port}}}
      - BASTIEN_PRIVATE_KEY_PATH=/etc/bastien/private.pem
    volumes:
      - ./:/app/brain:rw
      - ./standalone.yaml:/app/standalone.yaml:ro
      - ${{BASTIEN_PRIVATE_KEY_PATH:-/etc/bastien/private.pem}}:/etc/bastien/private.pem:ro
    networks:
      - teleremote-network
    labels:
      - com.centurylinklabs.watchtower.enable=false
      - ecosystem.antigravity.role=satellite-brain
      - ecosystem.antigravity.brain=${{BRAIN_ID:-{target_name}}}

networks:
  teleremote-network:
    name: teleremote-network
    external: true
"""
    create_file(target_path / "docker-compose.yaml", docker_compose_content, dry_run)

    # Makefile
    makefile_content = f"""# Satellite Brain Squad Agent Controller: {target_name}
.PHONY: up down logs status restart build

up:
\tdocker compose up -d

down:
\tdocker compose down

logs:
\tdocker compose logs -f squad-agent

status:
\tdocker compose ps

restart:
\tdocker compose restart

build:
\tdocker compose build
"""
    create_file(target_path / "Makefile", makefile_content, dry_run)

    # 4. Generate Core Governance & Navigation Files
    logger.info("ScaffoldNewBrain : Generating Project Compass...")

    # 🧬 AI-Project-DNA.md
    dna_content = f"""---
microservice: {target_name}
type: governance
status: active
tags:
- '#service/{target_name}'
- '#type/governance'
- '#state/active'
- '#zone/0-orchestration'
---
# 🧬 AI Project DNA: {target_name}

## 🎯 High-Level Vision
Dedicated knowledge base, behavioral specifications, and domain orchestration hub for `{target_name}`.

## 🛡️ Core Constraints
1. **The [SCAN] Protocol**: Every response must start with a [SCAN] block.
2. **Double-Digit Hierarchy**: Maintain the 00-99 folder structure.
3. **Isolation Zones**: Keep human dashboards in `quick-overview/` and `99-Humans/` with `#ai/ignore`.
4. **Transversal Tags**: Every file must be classified via `#tech/`, `#tier/`, and `#zone/`.
"""
    create_file(target_path / "00-AI-Orchestration/AI-Project-DNA.md", dna_content, dry_run)

    # 🧠 AI-Session-State.md
    session_content = f"""---
microservice: {target_name}
type: state
status: active
active-protocol: "🛡️ Mode 1: Spec-First"
tags:
- '#service/{target_name}'
- '#type/state'
- '#state/active'
- '#zone/0-orchestration'
---
# 🧠 AI Session State: {target_name}

## 🚀 Active Missions
- [ ] Initialize domain specifications and microservice hubs.
"""
    create_file(target_path / "00-AI-Orchestration/AI-Session-State.md", session_content, dry_run)

    # ⚡ AI-Init.md
    init_content = f"""---
microservice: {target_name}
type: governance
status: active
tags:
- '#service/{target_name}'
- '#type/governance'
- '#state/active'
- '#zone/0-orchestration'
---
# ⚡ AI Initialization: {target_name}

> [!IMPORTANT] MANDATORY INITIALIZATION
> Copy and paste this prompt when starting a new session:
> 
> "1. Read the ecosystem map in **[[Ecosystem-Map-MOC]]**."
> "2. Load project constraints from **[[AI-Project-DNA]]**."
> "3. Restore session state from **[[AI-Session-State]]**."
"""
    create_file(target_path / "00-AI-Orchestration/AI-Init.md", init_content, dry_run)

    # 🗺️ Ecosystem-Map-MOC.md
    moc_content = f"""---
microservice: ecosystem-core
type: moc
status: active
tags:
- '#service/{target_name}'
- '#type/moc'
- '#state/active'
- '#zone/0-orchestration'
---
# 🌌 {target_name}: Master Knowledge Hub (MOC)

## 🤖 00 - AI Orchestration
- [[00-AI-Orchestration/AI-Project-DNA|🧬 AI Project DNA]]
- [[00-AI-Orchestration/AI-Init|⚡ AI Initialization]]
- [[00-AI-Orchestration/AI-Session-State|🧠 AI Session State]]
"""
    create_file(target_path / "Ecosystem-Map-MOC.md", moc_content, dry_run)

    # 00-AI-Orchestration/MODE-MANUAL.md
    mode_content = "active_mode: 1\n\n# Mode Manual\n1: Spec-First\n2: Free-Labs\n3: Fleet-Commander\n"
    create_file(target_path / "00-AI-Orchestration/MODE-MANUAL.md", mode_content, dry_run)

    # quick-overview/00-Overview.md
    overview_content = f"""---
microservice: {target_name}
type: documentation
status: active
tags:
- '#service/{target_name}'
- '#type/documentation'
- '#state/active'
- '#ai/ignore'
---
# 📖 Overview: {target_name.replace('-', ' ').title()}

Human-readable overview and quick-start reference for this domain vault.
"""
    create_file(target_path / "quick-overview/00-Overview.md", overview_content, dry_run)

    # 5. Bake the AI Squad into the new ecosystem
    logger.info("ScaffoldNewBrain : Baking the AI Squad into the new ecosystem...")
    if not dry_run:
        env = os.environ.copy()
        toolbox_py = vault_root.parent / "microservice-toolbox" / "python"
        if not toolbox_py.exists():
            for p in [vault_root] + list(vault_root.parents):
                candidate = p / "microservice-toolbox" / "python"
                if candidate.exists():
                    toolbox_py = candidate
                    break
        scripts_dir = target_path / "08-Squad-Agent"
        pythonpath_entries = [str(scripts_dir), str(scripts_dir / "src")]
        if toolbox_py.exists():
            pythonpath_entries.append(str(toolbox_py))
        if "PYTHONPATH" in env:
            pythonpath_entries.append(env["PYTHONPATH"])
        env["PYTHONPATH"] = ":".join(pythonpath_entries)

        convert_script = scripts_dir / "main.py"
        if convert_script.exists():
            subprocessRun([sysExecutable, str(convert_script), "convert-agents"], cwd=target_path, env=env)
        else:
            fallback_convert = scripts_dir / "src" / "fleet" / "convert_agents.py"
            if fallback_convert.exists():
                subprocessRun([sysExecutable, str(fallback_convert)], cwd=target_path, env=env)

    # 6. Optional: Launch in Docker
    if launch_docker and not dry_run:
        launch_satellite_docker(target_path, target_name, sa_port)

    logger.info(f"ScaffoldNewBrain : SUCCESS! Your new Command Center is ready at: {target_path}")

# -----------------------------------------------------------------------------

def main() -> None:
    setup_terminal()
    vault_root, _ = resolve_vault_and_workspace(__file__)

    parser = argparse.ArgumentParser(description="Bastien-Antigravity Ecosystem Scaffolder")
    parser.add_argument("--name", "-n", type=str, default="", help="New project name (e.g. trading-brain)")
    parser.add_argument("--dest", "-d", type=str, default="", help="Destination path (defaults to ../<name>)")
    parser.add_argument("--dry-run", action="store_true", help="Preview file fabrication without writing to disk")
    parser.add_argument("--docker", action="store_true", help="Automatically launch the newly scaffolded brain in Docker")
    parser.add_argument("--port", "-p", type=int, default=None, help="Explicit host HTTP port for squad-agent (defaults to auto-allocating 8185+)")
    parser.add_argument("--grpc-port", type=int, default=None, help="Explicit host gRPC port for squad-agent (defaults to port + 2)")
    args = parser.parse_args()

    target_name = args.name.strip()
    if not target_name:
        try:
            target_name = input("Enter new project name (e.g. trading-brain): ").strip()
        except EOFError:
            target_name = ""

    if not target_name:
        logger.error("ScaffoldNewBrain : Project name is required.")
        return

    dest_input = args.dest.strip()
    if not dest_input:
        try:
            dest_input = input(f"Enter destination path [default: ../{target_name}]: ").strip() or f"../{target_name}"
        except EOFError:
            dest_input = f"../{target_name}"
            
    target_path = Path(dest_input).resolve()
    
    if target_path.exists() and not args.dry_run:
        logger.error(f"ScaffoldNewBrain : Path {target_path} already exists.")
        return

    scaffold_brain(
        target_name,
        target_path,
        vault_root,
        dry_run=args.dry_run,
        launch_docker=args.docker,
        sa_port=args.port,
        sa_grpc_port=args.grpc_port
    )

# -----------------------------------------------------------------------------

if __name__ == "__main__":
    main()

