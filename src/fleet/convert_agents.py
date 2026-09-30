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

import os
from pathlib import Path
from lib.bootstrap import ensure_virtualenv, prepend_venv_bin, ensure_import_paths
from lib.orchestration_lib import resolve_vault_and_workspace, get_logger

script_dir = Path(__file__).resolve().parent
vault_root = ensure_virtualenv(str(script_dir))
prepend_venv_bin(vault_root)

ensure_import_paths(script_dir, vault_root)

vault_root, workspace_root = resolve_vault_and_workspace(__file__)

logger = get_logger("ConvertAgents")

from os import listdir as osListdir, makedirs as osMakedirs
from os.path import dirname as osPathDirname, abspath as osPathAbspath, join as osPathJoin, isdir as osPathIsdir, exists as osPathExists
from glob import glob as globGlob

# No registry import needed. We output directly to target agent directories.

# -----------------------------------------------------------------------------------------------

def main() -> None:
    # Resolve roots dynamically using the shared vault/workspace helper
    # (script is in vault_root/08-Base-Scripts or vault_root/20-Scripts)
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
                                os.remove(skill_md)
                                os.rmdir(dir_path)
                            except OSError as e:
                                logger.error(f"   ⚠️ Could not purge skill {f}: {e}")
        else:
            for f in osListdir(target):
                if f.endswith(".md"):
                    try:
                        os.remove(osPathJoin(target, f))
                    except OSError as e:
                        logger.error(f"   ⚠️ Could not purge {f}: {e}")

    # Track processed agents to ensure Source of Truth precedence
    processed_agents = set()

    # Process all active source directories in precedence order
    for source_dir in active_source_dirs:
        logger.info(f"📥 Processing roles from: {os.path.basename(os.path.dirname(source_dir))}")
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
                    prompt_files = [f for f in md_files if os.path.basename(f).startswith("Prompt-")]
                    md_file = prompt_files[0] if prompt_files else md_files[0]
                    
                    with open(md_file, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    # Strip existing frontmatter from source content if present
                    from re import sub as reSub, DOTALL as reDotAll
                    content = reSub(r'^---.*?---\s*', '', content, flags=reDotAll)
                    
                    yaml_frontmatter = f"""---
name: {agent_name}
description: The {agent_name} persona from the Bastien-Antigravity squad.
---
"""
                    
                    scan_block = f"""
# 💾 STATE MANAGEMENT RULE (CRITICAL)
Before finishing any major task or concluding a session, you MUST use your available file management tools to append a summary of your actions to the local `AI-Session-State.md` file in the target repository. This acts as our Hard-Stop Context Block to prevent memory loss across sessions.

# 🚨 ATTENTION RESTORATION (SCAN METHOD)
To prevent context degradation, you MUST begin EVERY single response with the following SCAN block:

**[SCAN]** Role: {agent_name} | Source: [Source Verification] | State: [Session Progress]
"""
                    
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
                                f.write(yaml_frontmatter + content + "\n" + scan_block)
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

                    from re import sub as reSub, DOTALL as reDotAll
                    content = reSub(r'^---.*?---\s*', '', content, flags=reDotAll)

                    yaml_frontmatter = f"""---
name: {spec_name}
description: The {spec_name} persona from the Bastien-Antigravity squad.
---
"""
                    scan_block = f"""
# 💾 STATE MANAGEMENT RULE (CRITICAL)
Before finishing any major task or concluding a session, you MUST use your available file management tools to append a summary of your actions to the local `AI-Session-State.md` file in the target repository. This acts as our Hard-Stop Context Block to prevent memory loss across sessions.

# 🚨 ATTENTION RESTORATION (SCAN METHOD)
To prevent context degradation, you MUST begin EVERY single response with the following SCAN block:

**[SCAN]** Role: {spec_name} | Source: [Source Verification] | State: [Session Progress]
"""
                    for name, target in active_targets:
                        if "skills" in target or name == "Antigravity":
                            skill_dir = osPathJoin(target, spec_name)
                            osMakedirs(skill_dir, exist_ok=True)
                            target_file = osPathJoin(skill_dir, "SKILL.md")
                        else:
                            target_file = osPathJoin(target, f"{spec_name}.md")
                        try:
                            with open(target_file, 'w', encoding='utf-8') as f:
                                f.write(yaml_frontmatter + content + "\n" + scan_block)
                            logger.info(f"   [{name}] Created specialist agent: {spec_name}")
                        except OSError as e:
                            logger.error(f"   ⚠️ Could not write specialist agent {spec_name} to {name}: {e}")

                    processed_agents.add(spec_name)

# -----------------------------------------------------------------------------------------------

if __name__ == "__main__":
    main()
