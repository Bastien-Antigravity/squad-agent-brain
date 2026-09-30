#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Monitors the Obsidian Vault recursively for pending tasks
and automates the handover to specific AI Agent personas.

DATA FLOW:
1. Scans the entire obsidian-brain recursively for markdown files.
2. Parses YAML frontmatter to identify tasks with 'status: pending'.
3. Updates the status to 'active' for tasks assigned to known roles.
4. (Simulation) Triggers the appropriate AI persona workflow.

KEY PARAMETERS:
- ROLE_MAP: Dictionary mapping agent roles to their prompt files.
"""

import os
import sys
from pathlib import Path
from lib.bootstrap import ensure_virtualenv, prepend_venv_bin, ensure_import_paths

script_dir = Path(__file__).resolve().parent
vault_root = ensure_virtualenv(str(script_dir))
prepend_venv_bin(vault_root)

ensure_import_paths(script_dir, vault_root)

from os.path import join as osPathJoin, exists as osPathExists
from glob import glob as globGlob
from typing import Optional, Dict, Any
from lib.orchestration_lib import resolve_vault_and_workspace, get_logger

vault_root, workspace_root = resolve_vault_and_workspace(__file__)
WORKSPACE_ROOT = str(workspace_root)
OBSIDIAN_DIR = str(vault_root)

logger = get_logger("AgentDispatcher")

# Source of Truth Precedence
ROLE_PROMPT_SOURCES = [
    osPathJoin(OBSIDIAN_DIR, "07-Core-KMS", "Role-Prompts")
]

# Role to Prompt Filename Mapping
ROLE_MAP = {
    "oracle": "00-Oracle/Prompt-Chronos-Oracle.md",
    "orchestrator": "01-Orchestrator/Prompt-Orchestrator.md",
    "architect": "02-Architect/Prompt-Architect.md",
    "developer": "03-Developer/Prompt-Lead-Developer.md",
    "qa": "04-QA/Prompt-QA.md",
    "fleetarchitect": "05-FleetArchitect/Prompt-Fleet-Architect.md",
    "docmaintainer": "06-DocMaintainer/Prompt-DocMaintainer.md",
    "fleetcommander": "07-FleetCommander/Prompt-FleetCommander.md",
    "purger": "08-Purger/Mister-Straight-to-Goal.md",
    "sentinel": "09-Sentinel/Prompt-Sentinel.md",
}

def get_role_prompt_path(role_key: str) -> Optional[str]:
    """
    Finds the absolute path to a role prompt following the Source of Truth precedence.
    """
    filename = ROLE_MAP.get(role_key)
    if not filename:
        return None
        
    for source_dir in ROLE_PROMPT_SOURCES:
        full_path = osPathJoin(source_dir, filename)
        if osPathExists(full_path):
            return full_path
    return None

# Semantic Keywords for Fallback Scoring
SEMANTIC_KEYWORDS = {
    "developer": ["code", "implement", "fix", "feature", "refactor", "bug", "go", "python", "rust", "compile", "script", "import", "logic"],
    "qa": ["test", "verification", "assert", "acceptance criteria", "scenario", "audit", "coverage", "check", "run_test", "mock", "validation"],
    "architect": ["design", "specification", "adr", "diagram", "blueprint", "pattern", "uml", "hierarchy", "relationship", "concept"],
    "docmaintainer": ["documentation", "markdown", "readme", "links", "glossary", "moc", "write-up", "frontmatter", "wiki", "text"],
    "purger": ["delete", "remove", "clean", "purge", "orphan", "deprecated", "prune", "sweep", "dark matter"],
    "sentinel": ["security", "sandbox", "permissions", "access control", "compliance", "policy", "firewall", "authorization", "matrix"],
    "fleetcommander": ["deploy", "ci/cd", "fleet", "docker", "release", "orchestrate", "git hook", "bootstrap", "submodule"],
    "oracle": ["strategy", "nexus", "oracle", "future", "forecast", "insight", "strategic", "vision", "goal"],
    "orchestrator": ["coordinate", "delegation", "dispatcher", "dispatch", "assign", "workflow", "orchestrator", "schedule"]
}

# -----------------------------------------------------------------------------------------------

def parse_frontmatter(file_path: str) -> Optional[Dict[str, Any]]:
    """
    Parses YAML frontmatter from a markdown file using a late import.
    """
    from yaml import safe_load as yamlSafeLoad

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
        
    if content.startswith('---'):
        parts = content.split('---', 2)
        if len(parts) >= 3:
            try:
                frontmatter = yamlSafeLoad(parts[1])
                return frontmatter
            except Exception as e:
                logger.error(f"Error parsing YAML in {file_path}: {e}")
    return None

def route_task_semantically(task_content: str, default_role: Optional[str]) -> str:
    """
    Determines the best matching agent role by analyzing keywords in task description.
    """
    lower_content = task_content.lower()
    scores = {role: 0 for role in SEMANTIC_KEYWORDS}
    
    for role, keywords in SEMANTIC_KEYWORDS.items():
        for keyword in keywords:
            scores[role] += lower_content.count(keyword)
            
    max_score = -1
    best_role = None
    for role, score in scores.items():
        if score > max_score:
            max_score = score
            best_role = role
            
    logger.info("Semantic Routing Scores:")
    for role, score in sorted(scores.items(), key=lambda x: x[1], reverse=True)[:3]:
        logger.info(f"  - {role}: {score}")
        
    if best_role and max_score > 0:
        return best_role
        
    return default_role if default_role in ROLE_MAP else "developer"

def is_ignored_by_firewall(path_str: str, root_str: str) -> bool:
    """
    Checks if a path is ignored by looking for .aiignore, .geminiignore, or .mcpignore
    in the directory or any of its parents up to root_str.
    Also checks if the file itself has '#ai/ignore' in its first 1000 characters.
    """
    from pathlib import Path
    try:
        path = Path(path_str).resolve()
        root = Path(root_str).resolve()
        
        check_dir = path if path.is_dir() else path.parent
        while True:
            for ignore_name in [".aiignore", ".geminiignore", ".mcpignore"]:
                if (check_dir / ignore_name).exists():
                    return True
            if check_dir == root or check_dir.parent == check_dir:
                break
            check_dir = check_dir.parent
    except Exception:
        pass

    try:
        if path_str.endswith(".md"):
            with open(path_str, 'r', encoding='utf-8', errors='ignore') as f:
                head = f.read(1000)
                if "#ai/ignore" in head:
                    return True
    except Exception:
        pass

    return False

# -----------------------------------------------------------------------------------------------

def process_vault_tasks() -> None:
    """
    Scans the entire vault for files with '#state/pending' tag and handles handover.
    """
    from glob import glob as globGlob
    import os
    
    all_files = globGlob(osPathJoin(OBSIDIAN_DIR, "**", "*.md"), recursive=True)
    logger.info(f"Scanning {len(all_files)} files for pending tasks...")
    
    for task_file in all_files:
        if ".git" in task_file or ".obsidian" in task_file:
            continue
            
        if is_ignored_by_firewall(task_file, OBSIDIAN_DIR):
            continue
            
        try:
            with open(task_file, 'r', encoding='utf-8') as f:
                head = f.read(1000)
        except:
            continue
            
        if "#state/pending" in head or "status: pending" in head:
            frontmatter = parse_frontmatter(task_file)
            if not frontmatter:
                continue
            
            try:
                with open(task_file, 'r', encoding='utf-8') as f:
                    full_content = f.read()
            except:
                full_content = head
                
            default_role = frontmatter.get('role')
            logger.info(f"Pending task found: {os.path.basename(task_file)} (Declared Role: {default_role})")
            
            assigned_role = route_task_semantically(full_content, default_role)
            logger.info(f"Assigned Role: {assigned_role} (Prompt: {ROLE_MAP.get(assigned_role)})")
            
            try:
                new_content = full_content.replace('status: pending', 'status: active')
                new_content = new_content.replace('#state/pending', '#state/active')
                
                if assigned_role != default_role and default_role:
                    new_content = new_content.replace(f"role: {default_role}", f"role: {assigned_role}")
                elif 'role:' not in new_content and 'role :' not in new_content:
                    if new_content.startswith('---'):
                        parts = new_content.split('---', 2)
                        if len(parts) >= 3:
                            fm_lines = parts[1].splitlines()
                            fm_lines.append(f"role: {assigned_role}")
                            new_content = f"---\n" + "\n".join(fm_lines) + f"\n---{parts[2]}"
                
                with open(task_file, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                logger.info("Handover complete. Transitioned to #state/active.")
            except Exception as e:
                logger.error(f"Error updating task: {e}")

# -----------------------------------------------------------------------------------------------

def main():
    logger.info("Starting Agent Dispatcher (Semantic Mode)...")
    process_vault_tasks()
    logger.info("Run complete.")


if __name__ == "__main__":
    main()
