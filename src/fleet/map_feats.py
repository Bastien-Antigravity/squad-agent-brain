#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS: Map Feats - Generates a mapping of microservices to their behavior specs (FEAT files).

DATA FLOW:
1. Scans the BDD Behavior Specs directory.
2. Parses 'microservice' frontmatter.
3. Aggregates and prints the mapping.

KEY PARAMETERS:
None (Read-only mapping utility).
"""

from sys import exit as sysExit
from pathlib import Path
from os import walk as osWalk
from os.path import join as osPathJoin, exists as osPathExists
import re
try:
    from microservice_toolbox.utils.bootstrap import bootstrap_microservice
except ImportError:
    for parent in Path(__file__).resolve().parents:
        toolbox_py = parent / "microservice-toolbox" / "python"
        if toolbox_py.exists():
            sys.path.insert(0, str(toolbox_py))
            break
    from microservice_toolbox.utils.bootstrap import bootstrap_microservice

bootstrap_microservice(__file__, app_name="squad_agent_map_feats")

from lib.orchestration_lib import setup_terminal, resolve_vault_and_workspace, get_logger

setup_terminal()
VAULT_ROOT, WORKSPACE_ROOT = resolve_vault_and_workspace(__file__)
logger = get_logger("MapFeats")

# -----------------------------------------------------------------------------------------------

def extract_microservice(file_path: str) -> str:
    """Parses the YAML frontmatter to find the microservice name."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                frontmatter = parts[1]
                match = re.search(r'^microservice:\s*(.*)', frontmatter, re.MULTILINE)
                if match:
                    return match.group(1).strip().strip("'\"")
    except Exception as e:
        logger.error(f"Error reading {file_path}: {e}")
    return None

# -----------------------------------------------------------------------------------------------

from src.interfaces import Command

class MapFeatsCommand(Command):
    """
    Command implementation for mapping microservices to behavior specs.
    """
    def execute(self, *args, **kwargs) -> None:
        # Scans the specs and builds the microservice-to-feat mapping.
        root_dir = osPathJoin(str(VAULT_ROOT), "02-Business-BDD", "02-Behavior-Specs")
        
        mapping = {}
        
        if not osPathExists(root_dir):
            logger.error(f"Error: Directory not found: {root_dir}")
            sysExit(1)

        for root, dirs, files in osWalk(root_dir):
            for file in files:
                if file.startswith("FEAT-") and file.endswith(".md"):
                    file_path = osPathJoin(root, file)
                    ms = extract_microservice(file_path)
                    if ms:
                        if ms not in mapping:
                            mapping[ms] = []
                        mapping[ms].append(file.replace(".md", ""))
                    else:
                        logger.warning(f"File {file} has no microservice frontmatter defined.")
        
        # Print report
        logger.info("📋 Microservice to Behavior Spec mapping:")
        for ms, feats in sorted(mapping.items()):
            logger.info(f"[{ms}]")
            for feat in feats:
                logger.info(f"  - {feat}")

def main() -> None:
    cmd = MapFeatsCommand()
    cmd.execute()

if __name__ == "__main__":
    main()

