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
from pathlib import Path
from lib.bootstrap import ensure_virtualenv, prepend_venv_bin, ensure_import_paths

script_dir = Path(__file__).resolve().parent
vault_root = ensure_virtualenv(str(script_dir))
prepend_venv_bin(vault_root)

ensure_import_paths(script_dir, vault_root)

from os import remove as osRemove
from os.path import dirname as osPathDirname, abspath as osPathAbspath, join as osPathJoin, basename as osPathBasename, exists as osPathExists
from glob import glob as globGlob
from sys import argv as sysArgv, exit as sysExit

# -----------------------------------------------------------------------------------------------

from lib.orchestration_lib import resolve_vault_and_workspace, get_logger

vault_root, workspace_root = resolve_vault_and_workspace(__file__)
logger = get_logger("InitNewBrain")

def init_brain(ecosystem_name: str) -> None:
    """
    Performs the initialization sequence for a fresh brain ecosystem.
    """
    logger.info("Initializing new AI Brain for: {0}".format(ecosystem_name))
    
    # Corrected paths for the actual Bastien-Antigravity structure
    project_vars_path = osPathJoin(str(vault_root), "00-AI-Orchestration", "Project-Variables.md")
    inbox_dir = osPathJoin(str(vault_root), "10-State-and-Tasks", "Inbox")
    session_state_path = osPathJoin(str(vault_root), "00-AI-Orchestration", "AI-Session-State.md")
    
    # 1. Update Project Variables
    try:
        with open(project_vars_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        with open(project_vars_path, 'w', encoding='utf-8') as f:
            for line in lines:
                if line.startswith('ecosystem_name:'):
                    f.write('ecosystem_name: "{0}"\n'.format(ecosystem_name))
                else:
                    f.write(line)
        logger.info("Updated Project-Variables.md")
    except Exception as e:
        logger.error("Error updating Project-Variables: {0}".format(e))

    # 2. Clear Inbox
    try:
        for file in globGlob(osPathJoin(inbox_dir, "*.md")):
            osRemove(file)
            logger.info("Deleted old task: {0}".format(osPathBasename(file)))
    except Exception as e:
        logger.error("Error clearing Inbox: {0}".format(e))

    # 3. Clear Session State
    try:
        with open(session_state_path, 'w', encoding='utf-8') as f:
            f.write("# Central AI Session State\n\n*Brain Initialized. Ready for tasks.*")
        logger.info("Cleared AI-Session-State.md")
    except Exception as e:
        logger.error("Error clearing Session State: {0}".format(e))
        
    logger.info("Brain successfully initialized! You can now write your Idea Pitch.")

# -----------------------------------------------------------------------------------------------

def main():
    if len(sysArgv) < 2:
        sys.stderr.write("Usage: python Init-New-Brain.py <New-Ecosystem-Name>\n")
        sysExit(1)
    init_brain(sysArgv[1])


if __name__ == "__main__":
    main()
