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
3. Copies Role-Prompts and Base-Scripts from the parent brain vault root.
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
import sys
from pathlib import Path
from shutil import copytree as shutilCopytree, copy as shutilCopy, ignore_patterns as shutilIgnorePatterns
from subprocess import run as subprocessRun
from sys import executable as sysExecutable

# Standard ecosystem bootstrap
import src.bootstrap as bootstrap
from lib.orchestration_lib import setup_terminal, resolve_vault_and_workspace

logger = bootstrap.logger

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

def scaffold_brain(target_name: str, target_path: Path, vault_root: Path, dry_run: bool = False) -> None:
    """
    Executes complete scaffolding of a new Bastien-Antigravity brain vault.
    """
    logger.info(f"ScaffoldNewBrain : Fabricating '{target_name}' at {target_path}...")

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
        "08-Base-Scripts",
        "99-Humans",
        "quick-overview",
    ]
    
    for folder in folders:
        d = target_path / folder
        if dry_run:
            logger.info(f"   [DRY-RUN] Would create directory: {d}")
        else:
            d.mkdir(parents=True, exist_ok=True)

    # 2. Copy "DNA" (Role Prompts and Base-Scripts) from canonical vault root
    logger.info("ScaffoldNewBrain : Copying AI Squad DNA...")
    role_prompts_src = vault_root / "07-Core-KMS" / "Role-Prompts"
    if role_prompts_src.exists():
        dest_prompts = target_path / "07-Core-KMS" / "Role-Prompts"
        if dry_run:
            logger.info(f"   [DRY-RUN] Would copy {role_prompts_src} -> {dest_prompts}")
        else:
            shutilCopytree(role_prompts_src, dest_prompts, dirs_exist_ok=True)
    
    base_scripts_src = vault_root / "08-Base-Scripts"
    if base_scripts_src.exists():
        dest_scripts = target_path / "08-Base-Scripts"
        if dry_run:
            logger.info(f"   [DRY-RUN] Would copy {base_scripts_src} -> {dest_scripts}")
        else:
            shutilCopytree(
                base_scripts_src,
                dest_scripts,
                dirs_exist_ok=True,
                ignore=shutilIgnorePatterns(".venv*", "__pycache__", "*.pyc", ".pytest_cache*", ".git*")
            )

    # 3. Create Root Ecosystem Files
    logger.info("ScaffoldNewBrain : Creating root ecosystem files...")
    
    # standalone.yaml symlink
    create_symlink(target_path / "standalone.yaml", "../docker-deployment/modes/local/config/native.yaml", dry_run)

    # VERSION.txt
    create_file(target_path / "VERSION.txt", "1.0.0\n", dry_run)

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
`{target_name}` is a centralized knowledge vault, architecture registry, operational runbook, and domain intelligence engine for the Bastien-Antigravity ecosystem.

- **Primary Structure**:
  - `00-AI-Orchestration`: Agent personas, coordination protocols, squad directives
  - `02-Business-BDD`: Domain glossary, BDD behavior specifications, acceptance criteria
  - `03-Tech-Stack`: Technical standards, networking protocols, domain blueprints
  - `06-Microservices`: Service specification sheets, endpoint registries, capability maps
  - `07-Core-KMS`: Operational prompts, key management references
  - `08-Base-Scripts`: AI squad operational engine room, CLI utilities (`main.py`)
- **Configuration Link**: `standalone.yaml -> ../docker-deployment/modes/local/config/native.yaml`

## Key Commands & Verification
```bash
# Run ecosystem preflight check
python3 08-Base-Scripts/main.py preflight-check

# Scaffold a new microservice
python3 08-Base-Scripts/main.py scaffold-microservice --name <name> --lang <go|python|rust>

# Check vault frontmatter & coherence
python3 08-Base-Scripts/main.py ensure-frontmatter
python3 08-Base-Scripts/main.py check-coherence
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

## 📁 Vault Structure
- `00-AI-Orchestration`: AI squad coordination and session state
- `01-Strategic-Nexus`: Strategic objectives and anti-backlog
- `02-Business-BDD`: Domain specifications and Gherkin scenarios
- `03-Tech-Stack`: Architecture standards and protocols
- `06-Microservices`: Microservice hubs and registries
- `07-Core-KMS`: Security policies and squad role prompts
- `08-Base-Scripts`: Fleet management and scaffolding automation
"""
    create_file(target_path / "README.md", readme_content, dry_run)

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
        scripts_dir = target_path / "08-Base-Scripts"
        pythonpath_entries = [str(scripts_dir), str(scripts_dir / "src")]
        if toolbox_py.exists():
            pythonpath_entries.append(str(toolbox_py))
        if "PYTHONPATH" in env:
            pythonpath_entries.append(env["PYTHONPATH"])
        env["PYTHONPATH"] = ":".join(pythonpath_entries)

        convert_script = target_path / "08-Base-Scripts" / "main.py"
        if convert_script.exists():
            subprocessRun([sysExecutable, "08-Base-Scripts/main.py", "convert-agents"], cwd=target_path, env=env)
        else:
            fallback_convert = target_path / "08-Base-Scripts" / "src" / "fleet" / "convert_agents.py"
            if fallback_convert.exists():
                subprocessRun([sysExecutable, str(fallback_convert)], cwd=target_path, env=env)

    logger.info(f"ScaffoldNewBrain : SUCCESS! Your new Command Center is ready at: {target_path}")

# -----------------------------------------------------------------------------

def main() -> None:
    setup_terminal()
    vault_root, _ = resolve_vault_and_workspace(__file__)

    parser = argparse.ArgumentParser(description="Bastien-Antigravity Ecosystem Scaffolder")
    parser.add_argument("--name", "-n", type=str, default="", help="New project name (e.g. trading-brain)")
    parser.add_argument("--dest", "-d", type=str, default="", help="Destination path (defaults to ../<name>)")
    parser.add_argument("--dry-run", action="store_true", help="Preview file fabrication without writing to disk")
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

    scaffold_brain(target_name, target_path, vault_root, dry_run=args.dry_run)

# -----------------------------------------------------------------------------

if __name__ == "__main__":
    main()

