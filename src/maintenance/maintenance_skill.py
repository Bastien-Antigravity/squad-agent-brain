#!/usr/bin/env python
# coding:utf-8
"""
ESSENTIAL PROCESS:
Performs routine maintenance tasks across the ecosystem, specifically 
purging stale AI-Session-State.md files to prevent context bloat.

DATA FLOW:
1. Scans all directories in the workspace root for AI-Session-State.md.
2. Checks the last modification time of each file.
3. Deletes files older than 30 days (excluding the central obsidian-brain state).

KEY PARAMETERS:
- WORKSPACE_DIR: The root directory containing all brain repositories.
- state_file: Target file name for the purge operation.
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
from time import time as timeTime
from pathlib import Path
from sys import argv as sysArgv

# ### CONFIGURATIONS ###

from lib.orchestration_lib import resolve_vault_and_workspace, get_logger

vault_root, workspace_root = resolve_vault_and_workspace(__file__)
WORKSPACE_DIR = workspace_root
logger = get_logger("MaintenanceSkill")

# -----------------------------------------------------------------------------------------------

def purge_stale_state() -> None:
    """
    Identifies and removes AI-Session-State.md files that haven't been touched in 30 days.
    """
    logger.info("Checking for stale state files (older than 30 days)...")
    now = timeTime()
    count = 0
    for state_file in WORKSPACE_DIR.rglob("AI-Session-State.md"):
        # Don't delete the central one in obsidian-brain
        if "obsidian-brain" in str(state_file): 
            continue
        if state_file.stat().st_mtime < now - 30 * 86400:
            osRemove(state_file)
            logger.info("Deleted stale state: {0}".format(state_file))
            count += 1
    if count == 0:
        logger.info("No stale state files found.")

# -----------------------------------------------------------------------------------------------

def main() -> None:
    """
    Orchestrates the maintenance operations.
    """
    logger.info("Starting Maintenance Skill (Purger Mode)...")
    purge_stale_state()
    logger.info("Maintenance complete.")

# -----------------------------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sysArgv) > 1 and sysArgv[1] == "purge":
        main()
    else:
        sys.stderr.write("Usage: python Maintenance-Skill.py purge\n")
