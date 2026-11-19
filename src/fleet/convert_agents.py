#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Converts the human-readable Role-Prompts from the core-kms-brain into 
compatible Gemini CLI agent definitions in the obsidian-brain vault.

DATA FLOW:
1. Scans core-kms-brain/Role-Prompts for markdown files.
2. Extracts agent names from folder prefixes.
3. Injects mandatory YAML frontmatter and the [SCAN] restoration block.
4. Writes the final agent markdown to obsidian-brain/ :
    gemini      : .agents/skills/ 

KEY PARAMETERS:
- source_dir: Path to the raw role prompts.
- target_dir: Path to the generated Antigravity/Gemini agent definitions.
"""

from argparse import ArgumentParser as argparseArgumentParser
from glob import glob as globGlob
from os import listdir as osListdir, makedirs as osMakedirs, readlink as osReadlink, remove as osRemove, rmdir as osRmdir
from os.path import basename as osPathBasename, dirname as osPathDirname, exists as osPathExists, isdir as osPathIsdir, join as osPathJoin, relpath as osPathRelpath
from pathlib import Path as pathPath
from re import DOTALL as reDotAll, sub as reSub
import src.bootstrap as bootstrap
from src.lib.orchestration_lib import resolve_vault_and_workspace, get_logger

vault_root, workspace_root = resolve_vault_and_workspace(__file__)

logger = get_logger("ConvertAgents")

# No registry import needed. We output directly to target agent directories.

# -----------------------------------------------------------------------------------------------

def build_skill_markdown(role_name: str, raw_prompt_content: str) -> str:
    """
    Canonical builder for Antigravity IDE SKILL.md files from source Role-Prompts.
    Shared by convert_agents.py and check_coherence.py to guarantee zero template drift.
    """
    clean_body = reSub(r'^---.*?---\s*', '', raw_prompt_content, flags=reDotAll)
    yaml_frontmatter = f"""---
name: {role_name}
description: The {role_name} persona from the Bastien-Antigravity squad.
---
"""
    scan_block = f"""
# 🧭 COMPLEXITY GATE & CANONICAL TOOLBOX CONTRACT (IDE <-> SQUAD LINK)
1. **Complexity Gate (Max 2 Files / Step)**: Before writing code, evaluate whether the request touches >2 files, >2 architectural layers, or multiple languages. If so, decompose it via `TaskDecomposer` (`08-Squad-Agent/src/lib/task_decomposer.py`) into sequential atomic micro-steps.
2. **Canonical `microservice-toolbox` APIs ONLY**:
   - Version: `config.get_version()` / `appConfig.GetVersion()` (never scan directories for `VERSION.txt`).
   - Networking: `config.get_listen_addr(cap)`, `config.get_grpc_listen_addr(cap)`, `config.get_rest_addr(cap)` (never hardcode `127.0.0.1` or ports).
   - Config: Read from `config.get_capability('<service>')` (never chain `os.getenv()` fallbacks in service code; `standalone.yaml` expands `${{VAR:default}}` at boot).
3. **Zero Over-Defensive Bloat (`15-Safe-By-Design-Invariants.md`)**:
   - Never write `hasattr(self.config, ...)` or `isinstance(self.config.data, dict)` on pre-validated `AppConfig`.
   - Never use `asyncio.Lock` without an inner `await`, never wrap Go `atomic.*` in `sync.Mutex`, and never check `os.path.exists()` before `open()` (TOCTOU).
   - Always verify modified files with: `python3 08-Squad-Agent/main.py validate-compliance <path> --strict-imports --strict-lean`.

# 💾 STATE MANAGEMENT RULE (CRITICAL)
Before finishing any major task or concluding a session, you MUST use your available file management tools to append a summary of your actions to the local `AI-Session-State.md` file in the target repository. This acts as our Hard-Stop Context Block to prevent memory loss across sessions.

# 🚨 ATTENTION RESTORATION (SCAN METHOD)
To prevent context degradation, you MUST begin EVERY single response with the following SCAN block:

**[SCAN]** Role: {role_name} | Source: [Source Verification] | State: [Session Progress]
"""
    return yaml_frontmatter + clean_body + "\n" + scan_block

# -----------------------------------------------------------------------------------------------

def main() -> None:
    parser = argparseArgumentParser(description="Compile squad role prompts into Antigravity skills.")
    parser.add_argument(
        "--skip-workspace-link",
        action="store_true",
        help="Skip updating workspace root .agents/skills symlink (enforced automatically for non-obsidian-brain vaults).",
    )
    args, _ = parser.parse_known_args()

    # Resolve roots dynamically using the shared vault/workspace helper
    # (script is in vault_root/08-Squad-Agent)
    # vault_root and workspace_root are already resolved at import time.

    # Precedence:
    # 1. 01-Strategic-Nexus (Source of Truth for Strategic Identities)
    # 2. 07-Core-KMS (Central Repository for Operational Personas)
    
    source_dirs = [
        osPathJoin(vault_root, "01-Strategic-Nexus", "Role-Prompts"),
        osPathJoin(vault_root, "02-Business-BDD", "Role-Prompts"),
        osPathJoin(vault_root, "03-Tech-Stack", "Role-Prompts"),
        osPathJoin(vault_root, "07-Core-KMS", "Role-Prompts"),
        # Standalone clones support
        osPathJoin(workspace_root, "core-kms-brain", "Role-Prompts"),
        osPathJoin(workspace_root, "nexus-strategic-brain", "Role-Prompts"),
    ]
    
    # Filter only existing directories
    active_source_dirs = [d for d in source_dirs if osPathIsdir(d)]

    # Output directly to the unified .agents/skills directory used by the squad agents
    active_targets = []
    target = osPathJoin(vault_root, ".agents", "skills")
    try:
        osMakedirs(target, exist_ok=True)
        active_targets.append(("Antigravity", target))
    except OSError as e:
        logger.error(f"   ⚠️ Could not prepare Antigravity agents at {target}: {e}")

    if not active_targets:
        logger.warning("⚠️ No active AI adapters found.")
        return

    # Cleanup: Remove orphaned agents in all active targets
    for name, target in active_targets:
        logger.info(f"🧹 Purging old {name} agents in {target}...")
        if "skills" in target or name == "Antigravity":
            if osPathExists(target):
                for f in osListdir(target):
                    dir_path = osPathJoin(target, f)
                    if osPathIsdir(dir_path):
                        skill_md = osPathJoin(dir_path, "SKILL.md")
                        if osPathExists(skill_md):
                            try:
                                osRemove(skill_md)
                                osRmdir(dir_path)
                            except OSError as e:
                                logger.error(f"   ⚠️ Could not purge skill {f}: {e}")
        else:
            for f in osListdir(target):
                if f.endswith(".md"):
                    try:
                        osRemove(osPathJoin(target, f))
                    except OSError as e:
                        logger.error(f"   ⚠️ Could not purge {f}: {e}")

    # Track processed agents to ensure Source of Truth precedence
    processed_agents = set()

    # Process all active source directories in precedence order
    for source_dir in active_source_dirs:
        logger.info(f"📥 Processing roles from: {osPathBasename(osPathDirname(source_dir))}")
        for folder in osListdir(source_dir):
            folder_path = osPathJoin(source_dir, folder)
            if osPathIsdir(folder_path):
                # e.g. "04-QA" -> "qa"
                agent_name = folder.split("-", 1)[1].lower() if "-" in folder else folder.lower()
                
                # Precedence check: if we already processed this agent from a higher-priority source, skip
                if agent_name in processed_agents:
                    continue

                md_files = globGlob(osPathJoin(folder_path, "*.md"))
                if md_files:
                    # Prioritize files starting with "Prompt-"
                    prompt_files = [f for f in md_files if osPathBasename(f).startswith("Prompt-")]
                    md_file = prompt_files[0] if prompt_files else md_files[0]
                    
                    with open(md_file, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    compiled_skill = build_skill_markdown(agent_name, content)
                    
                    # Sync to all active targets
                    for name, target in active_targets:
                        if "skills" in target or name == "Antigravity":
                            skill_dir = osPathJoin(target, agent_name)
                            osMakedirs(skill_dir, exist_ok=True)
                            target_file = osPathJoin(skill_dir, "SKILL.md")
                        else:
                            target_file = osPathJoin(target, f"{agent_name}.md")
                        try:
                            with open(target_file, 'w', encoding='utf-8') as f:
                                f.write(compiled_skill)
                            logger.info(f"   [{name}] Created agent: {agent_name}")
                        except OSError as e:
                            logger.error(f"   ⚠️ Could not write agent {agent_name} to {name}: {e}")
                    
                    processed_agents.add(agent_name)

        # Process developer squad language & domain specialists
        squad_path = osPathJoin(source_dir, "03-Developer", "Squad")
        if osPathIsdir(squad_path):
            specialist_map = {
                "pythonspecialist": "Python-Integration-Specialist.md",
                "gospecialist": "Go-Systems-Specialist.md",
                "rustspecialist": "Rust-Safety-Specialist.md",
                "cppspecialist": "CPP-Low-Latency-Specialist.md",
                "webuispecialist": "Web-UI-Specialist.md",
                "timescalespecialist": "Timescale-Data-Specialist.md",
                "vbaspecialist": "Excel-VBA-Specialist.md",
            }
            for spec_name, spec_filename in specialist_map.items():
                if spec_name in processed_agents:
                    continue
                spec_file = osPathJoin(squad_path, spec_filename)
                if osPathExists(spec_file):
                    with open(spec_file, 'r', encoding='utf-8') as f:
                        content = f.read()

                    compiled_spec = build_skill_markdown(spec_name, content)

                    for name, target in active_targets:
                        if "skills" in target or name == "Antigravity":
                            skill_dir = osPathJoin(target, spec_name)
                            osMakedirs(skill_dir, exist_ok=True)
                            target_file = osPathJoin(skill_dir, "SKILL.md")
                        else:
                            target_file = osPathJoin(target, f"{spec_name}.md")
                        try:
                            with open(target_file, 'w', encoding='utf-8') as f:
                                f.write(compiled_spec)
                            logger.info(f"   [{name}] Created specialist agent: {spec_name}")
                        except OSError as e:
                            logger.error(f"   ⚠️ Could not write specialist agent {spec_name} to {name}: {e}")

                    processed_agents.add(spec_name)

    # Ensure workspace root .agents/skills symlink points to obsidian-brain/.agents/skills
    # so Antigravity AI IDE sessions opened at workspace root discover all 22 Squad skills.
    # Never overwrite the workspace root symlink when scaffolding or running inside a satellite/sandbox brain.
    if not args.skip_workspace_link and pathPath(vault_root).name == "obsidian-brain":
        try:
            ws_agents_dir = pathPath(workspace_root) / ".agents"
            ws_skills_link = ws_agents_dir / "skills"
            vault_skills_dir = pathPath(vault_root) / ".agents" / "skills"
            if vault_skills_dir.exists() and pathPath(workspace_root).resolve() != pathPath(vault_root).resolve():
                ws_agents_dir.mkdir(parents=True, exist_ok=True)
                rel_target = osPathRelpath(vault_skills_dir, ws_agents_dir)
                if ws_skills_link.is_symlink():
                    if osReadlink(ws_skills_link) != rel_target:
                        ws_skills_link.unlink()
                        ws_skills_link.symlink_to(rel_target)
                elif not ws_skills_link.exists():
                    ws_skills_link.symlink_to(rel_target)
                logger.info(f"🔗 Linked workspace skills: {ws_skills_link} -> {rel_target}")
        except OSError as e:
            logger.warning(f"⚠️ Could not link workspace .agents/skills: {e}")

# -----------------------------------------------------------------------------------------------

if __name__ == "__main__":
    main()
