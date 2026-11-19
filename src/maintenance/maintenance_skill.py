#!/usr/bin/env python
# coding:utf-8
"""
ESSENTIAL PROCESS:
Performs routine maintenance tasks across the ecosystem, specifically 
compacting stale AI-Session-State.md files in-place to prevent context bloat
without deleting mandatory repository governance files.

DATA FLOW:
1. Scans all directories in the workspace root for AI-Session-State.md.
2. Checks the last modification time and session section count of each file.
3. Compacts files older than 30 days or with >10 sessions to keep the header and latest 5 sessions.

KEY PARAMETERS:
- WORKSPACE_DIR: The root directory containing all brain repositories.
- max_sessions: Maximum number of recent session blocks retained during compaction.
"""
import os
import re
import sys
from pathlib import Path
import src.bootstrap as bootstrap

from time import time as timeTime
from sys import argv as sysArgv

# ### CONFIGURATIONS ###

from src.lib.orchestration_lib import resolve_vault_and_workspace, get_logger

vault_root, workspace_root = resolve_vault_and_workspace(__file__)
WORKSPACE_DIR = workspace_root
logger = get_logger("MaintenanceSkill")

# -----------------------------------------------------------------------------------------------

def compact_session_state_file(state_file: Path, max_sessions: int = 5) -> bool:
    """
    Compacts an AI-Session-State.md file in-place by retaining its YAML frontmatter,
    preamble, and the most recent `max_sessions` H2 session sections.
    Never deletes the file itself so FleetCommander mandatory doc checks remain valid.
    """
    try:
        content = state_file.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("Could not read state file {0}: {1}".format(state_file, exc))
        return False

    parts = re.split(r"(?m)^##\s+", content)
    if len(parts) <= max_sessions + 1:
        return False

    preamble = parts[0]
    recent_sections = parts[1 : max_sessions + 1]
    compacted = preamble + "".join(f"## {sec}" for sec in recent_sections)
    try:
        state_file.write_text(compacted, encoding="utf-8")
        return True
    except OSError as exc:
        logger.warning("Could not write compacted state file {0}: {1}".format(state_file, exc))
        return False

# -----------------------------------------------------------------------------------------------

def purge_stale_state(max_sessions: int = 5) -> None:
    """
    Identifies and compacts AI-Session-State.md files that are older than 30 days
    or have accumulated excessive session history, preserving the file for FleetCommander compliance.
    """
    logger.info("Checking for bloated or stale AI-Session-State.md files to compact...")
    now = timeTime()
    count = 0
    for state_file in WORKSPACE_DIR.rglob("AI-Session-State.md"):
        if ".git" in state_file.parts or ".venv" in state_file.parts:
            continue
        try:
            is_old = state_file.stat().st_mtime < now - 30 * 86400
        except OSError:
            continue
        if is_old or state_file.stat().st_size > 8192:
            if compact_session_state_file(state_file, max_sessions=max_sessions):
                logger.info("Compacted session state in-place: {0}".format(state_file))
                count += 1
    if count == 0:
        logger.info("No bloated or stale state files required compaction.")

# -----------------------------------------------------------------------------------------------

def main() -> None:
    """
    Orchestrates the maintenance operations. Requires explicit 'purge' argument.
    """
    if len(sysArgv) < 2 or "purge" not in sysArgv:
        logger.info("Maintenance Skill: No action taken. Use 'python3 08-Squad-Agent/main.py maintenance-skill purge' to run.")
        return
    logger.info("Starting Maintenance Skill (Purger Mode)...")
    purge_stale_state()
    logger.info("Maintenance complete.")

# -----------------------------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sysArgv) > 1 and sysArgv[1] == "purge":
        main()
    else:
        sys.stderr.write("Usage: python Maintenance-Skill.py purge\n")
