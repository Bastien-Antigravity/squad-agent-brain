#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Resets and initializes a new AI Brain environment by updating project 
variables, clearing the task inbox, and resetting session state.

DATA FLOW:
1. Inputs a new ecosystem name and optional target vault path via CLI.
2. Updates Project-Variables.md / AI-Project-DNA.md with the new name.
3. Deletes all .md files in the Inbox folder (excluding templates).
4. Reinitializes AI-Session-State.md with canonical YAML frontmatter.

KEY PARAMETERS:
- ecosystem_name: The name of the new project being initialized.
- target_vault: Optional target brain vault directory path.
"""

import sys
from pathlib import Path

try:
    from microservice_toolbox.utils.bootstrap import bootstrap_microservice
except ImportError:
    for parent in Path(__file__).resolve().parents:
        toolbox_py = parent / "microservice-toolbox" / "python"
        if toolbox_py.exists():
            sys.path.insert(0, str(toolbox_py))
            break
    from microservice_toolbox.utils.bootstrap import bootstrap_microservice

bootstrap_microservice(__file__, app_name="squad_agent_init_brain")

from argparse import ArgumentParser as argparseArgumentParser
from pathlib import Path as pathPath
from re import sub as reSub
from sys import exit as sysExit
from typing import Optional as typeOptional

from src.lib.orchestration_lib import resolve_vault_and_workspace, get_logger

vault_root, workspace_root = resolve_vault_and_workspace(__file__)
logger = get_logger("InitNewBrain")

# -----------------------------------------------------------------------------------------------

def init_brain(ecosystem_name: str, target_vault: typeOptional[pathPath] = None) -> None:
    """
    Performs the initialization sequence for a fresh brain ecosystem.
    Resiliently updates Project DNA, purges inbox tasks if present, and resets session state.
    """
    active_vault = pathPath(target_vault).resolve() if target_vault is not None else pathPath(vault_root).resolve()
    logger.info("InitNewBrain : Initializing new AI Brain for '{0}' at {1}".format(ecosystem_name, active_vault))
    
    # 1. Update Project DNA / Variables if readable
    dna_candidates = [
        active_vault / "00-AI-Orchestration" / "AI-Project-DNA.md",
        active_vault / "00-AI-Orchestration" / "Project-Variables.md",
        active_vault / "AI-Project-DNA.md"
    ]
    updated_dna = False
    for dna_path in dna_candidates:
        try:
            content = dna_path.read_text(encoding="utf-8")
        except (FileNotFoundError, OSError):
            continue
        new_content = reSub(r'ecosystem_name:\s*".*?"', f'ecosystem_name: "{ecosystem_name}"', content)
        if new_content != content:
            try:
                dna_path.write_text(new_content, encoding="utf-8")
                logger.info("InitNewBrain : Updated ecosystem_name in {0}".format(dna_path.name))
                updated_dna = True
            except OSError as e:
                logger.error("InitNewBrain : Error updating {0}: {1}".format(dna_path.name, e))
    if not updated_dna:
        logger.info("InitNewBrain : Project variables checked; ready.")

    # 2. Clear Inbox directories if present
    inbox_candidates = [
        active_vault / "04-Rapid-Prototyping" / "Inbox",
        active_vault / "10-State-and-Tasks" / "Inbox",
        active_vault / "Inbox"
    ]
    for inbox_dir in inbox_candidates:
        try:
            md_files = list(inbox_dir.glob("*.md"))
        except OSError:
            continue
        for md_file in md_files:
            if not md_file.name.lower().startswith("template"):
                try:
                    md_file.unlink()
                    logger.info("InitNewBrain : Deleted old task {0}".format(md_file.name))
                except OSError as e:
                    logger.error("InitNewBrain : Error clearing Inbox task {0}: {1}".format(md_file.name, e))

    # 3. Reset Session State preserving canonical YAML frontmatter
    session_candidates = [
        active_vault / "00-AI-Orchestration" / "AI-Session-State.md",
        active_vault / "AI-Session-State.md"
    ]
    fresh_state = (
        "---\n"
        f"microservice: {ecosystem_name}\n"
        "type: state\n"
        "status: active\n"
        'active-protocol: "🛡️ Mode 1: Spec-First"\n'
        "tags:\n"
        f"- '#service/{ecosystem_name}'\n"
        "- '#type/state'\n"
        "- '#state/active'\n"
        "- '#zone/0-orchestration'\n"
        "---\n"
        f"# Central AI Session State: {ecosystem_name}\n\n"
        f"*Brain Initialized for {ecosystem_name}. Ready for tasks.*\n"
    )
    for session_path in session_candidates:
        try:
            session_path.read_text(encoding="utf-8")
        except (FileNotFoundError, OSError):
            continue
        try:
            session_path.write_text(fresh_state, encoding="utf-8")
            logger.info("InitNewBrain : Reset {0}".format(session_path.name))
        except OSError as e:
            logger.error("InitNewBrain : Error resetting {0}: {1}".format(session_path.name, e))
        
    logger.info("InitNewBrain : Brain '{0}' successfully initialized!".format(ecosystem_name))

# -----------------------------------------------------------------------------------------------

def main() -> None:
    parser = argparseArgumentParser(description="Reset and initialize an AI Brain environment.")
    parser.add_argument("ecosystem_name", nargs="?", help="New ecosystem/brain name")
    parser.add_argument("--dest", "-d", type=str, default="", help="Optional target brain vault path")
    args = parser.parse_args()

    if not args.ecosystem_name:
        logger.error("InitNewBrain : Usage: python3 main.py init-new-brain <New-Ecosystem-Name> [--dest <path>]")
        sysExit(1)

    target_vault = pathPath(args.dest).resolve() if args.dest else None
    init_brain(args.ecosystem_name, target_vault=target_vault)

# -----------------------------------------------------------------------------------------------

if __name__ == "__main__":
    main()
