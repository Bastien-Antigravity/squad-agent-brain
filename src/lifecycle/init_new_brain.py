#!/usr/bin/env python
# coding:utf-8
"""
ESSENTIAL PROCESS:
Resets and initializes a new AI Brain environment by updating project 
variables, clearing the task inbox, and resetting session state.

DATA FLOW:
1. Inputs a new ecosystem name via CLI.
2. Updates Project-Variables.md with the new name.
3. Deletes all .md files in the Inbox folder (excluding templates).
4. Reinitializes AI-Session-State.md with a fresh header.

KEY PARAMETERS:
- ecosystem_name: The name of the new project being initialized.
"""
import os
import sys
import re
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

from sys import argv as sysArgv, exit as sysExit

# -----------------------------------------------------------------------------------------------

from lib.orchestration_lib import resolve_vault_and_workspace, get_logger

vault_root, workspace_root = resolve_vault_and_workspace(__file__)
logger = get_logger("InitNewBrain")

# -----------------------------------------------------------------------------------------------

def init_brain(ecosystem_name: str) -> None:
    """
    Performs the initialization sequence for a fresh brain ecosystem.
    Resiliently updates Project DNA, purges inbox tasks if present, and resets session state.
    """
    logger.info("Initializing new AI Brain for: {0}".format(ecosystem_name))
    
    # 1. Update Project DNA / Variables if exists
    dna_candidates = [
        Path(vault_root) / "00-AI-Orchestration" / "AI-Project-DNA.md",
        Path(vault_root) / "00-AI-Orchestration" / "Project-Variables.md",
        Path(vault_root) / "AI-Project-DNA.md"
    ]
    updated_dna = False
    for dna_path in dna_candidates:
        if dna_path.exists():
            try:
                content = dna_path.read_text(encoding="utf-8")
                new_content = re.sub(r'ecosystem_name:\s*".*?"', f'ecosystem_name: "{ecosystem_name}"', content)
                if new_content != content:
                    dna_path.write_text(new_content, encoding="utf-8")
                    logger.info(f"Updated ecosystem_name in {dna_path.name}")
                    updated_dna = True
            except Exception as e:
                logger.error(f"Error updating {dna_path.name}: {e}")
    if not updated_dna:
        logger.info("Project variables file checked; ready.")

    # 2. Clear Inbox directories if they exist
    inbox_candidates = [
        Path(vault_root) / "04-Rapid-Prototyping" / "Inbox",
        Path(vault_root) / "10-State-and-Tasks" / "Inbox",
        Path(vault_root) / "Inbox"
    ]
    for inbox_dir in inbox_candidates:
        if inbox_dir.exists():
            try:
                for file in inbox_dir.glob("*.md"):
                    if not file.name.lower().startswith("template"):
                        file.unlink()
                        logger.info(f"Deleted old task: {file.name}")
            except Exception as e:
                logger.error(f"Error clearing Inbox in {inbox_dir}: {e}")

    # 3. Clear Session State
    session_candidates = [
        Path(vault_root) / "00-AI-Orchestration" / "AI-Session-State.md",
        Path(vault_root) / "AI-Session-State.md"
    ]
    for session_path in session_candidates:
        if session_path.exists():
            try:
                fresh_state = (
                    f"# Central AI Session State\n\n"
                    f"*Brain Initialized for {ecosystem_name}. Ready for tasks.*\n"
                )
                session_path.write_text(fresh_state, encoding="utf-8")
                logger.info(f"Reset {session_path.name}")
            except Exception as e:
                logger.error(f"Error resetting {session_path.name}: {e}")
        
    logger.info("Brain successfully initialized! You can now write your Idea Pitch.")

# -----------------------------------------------------------------------------------------------

def main():
    if len(sysArgv) < 2:
        sys.stderr.write("Usage: python Init-New-Brain.py <New-Ecosystem-Name>\n")
        sysExit(1)
    init_brain(sysArgv[1])


if __name__ == "__main__":
    main()
