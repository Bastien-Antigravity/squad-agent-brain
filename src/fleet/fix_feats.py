#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS: Fix Feats - Standardizes FEAT markdown files across the obsidian-brain.

DATA FLOW:
1. Scans specified directories.
2. Parses frontmatter.
3. Applies domain tags and backlinks.
4. Updates files.

KEY PARAMETERS:
None (Auditing and fixing utility).
"""

from sys import exit as sysExit
from pathlib import Path
from os import walk as osWalk, listdir as osListdir, rename as osRename, makedirs as osMakedirs
from os.path import join as osPathJoin, exists as osPathExists, basename as osPathBasename
import re
from typing import Dict, List, Optional, Any
from lib.bootstrap import ensure_virtualenv, prepend_venv_bin, ensure_import_paths
from lib.orchestration_lib import setup_terminal, resolve_vault_and_workspace, get_logger, get_config

# -----------------------------------------------------------------------------------------------

# Setup paths and environment
_self_dir = Path(__file__).resolve().parent
_vault_root = ensure_virtualenv(str(_self_dir))
prepend_venv_bin(_vault_root)
ensure_import_paths(_self_dir, _vault_root)

setup_terminal()
VAULT_ROOT, WORKSPACE_ROOT = resolve_vault_and_workspace(__file__)

# -----------------------------------------------------------------------------------------------

class FeatFixer:
    Name: str = "FeatFixer"

    def __init__(self, *, config: Any, logger: Any):
        self.config = config
        self.logger = logger
        self.vault_root: str = str(VAULT_ROOT)
        self.root_dir: str = osPathJoin(self.vault_root, "02-Business-BDD", "02-Behavior-Specs")
        self.hubs_dir: str = osPathJoin(self.vault_root, "06-Microservices")
        self.domain_map: Dict[str, str] = {
            "config-server": "#domain/networking",
            "data-ingestor": "#domain/analysis",
            "distributed-config": "#domain/networking",
            "enhanced-backtesting": "#domain/analysis",
            "flexible-logger": "#domain/observability",
            "fundamental-analysis": "#domain/analysis",
            "log-server": "#domain/observability",
            "market-observer": "#domain/analysis",
            "microservice-toolbox": "#domain/architecture",
            "notif-server": "#domain/interface",
            "ontime-scheduler": "#domain/architecture",
            "orderbook-aggregator": "#domain/analysis",
            "safe-socket": "#domain/networking",
            "sandbox-testing": "#domain/architecture",
            "tele-remote": "#domain/interface",
            "universal-logger": "#domain/observability",
            "web-interface": "#domain/interface",
            "technical-analysis": "#domain/analysis"
        }

    # -----------------------------------------------------------------------------------------------

    def _get_hub_link(self, *, ms: str) -> Optional[str]:
        """Try to find the hub file for a given microservice."""
        if not osPathExists(self.hubs_dir):
            return None
            
        for file in osListdir(self.hubs_dir):
            if ms.lower() in file.lower() and file.endswith("-Hub.md"):
                return f"[[06-Microservices/{file.replace('.md', '')}|🌐 {ms.capitalize()} Hub]]"
        return None

    # -----------------------------------------------------------------------------------------------

    def _move_root_feats(self) -> None:
        """Move root FEAT files to ontime-scheduler if appropriate."""
        if not osPathExists(self.root_dir):
            return

        root_feats: List[str] = [f for f in osListdir(self.root_dir) if f.startswith("FEAT-") and f.endswith(".md")]
        if root_feats:
            target_dir: str = osPathJoin(self.root_dir, "ontime-scheduler")
            if not osPathExists(target_dir):
                osMakedirs(target_dir, exist_ok=True)
            for f in root_feats:
                osRename(osPathJoin(self.root_dir, f), osPathJoin(target_dir, f))

    # -----------------------------------------------------------------------------------------------

    def process_feats(self) -> None:
        """Iterates through all FEAT files and applies standardization rules."""
        self.logger.info(f"{self.Name} : Starting FEAT file standardization...")
        self._move_root_feats()

        for root, dirs, files in osWalk(self.root_dir):
            ms_from_folder: str = osPathBasename(root)
            if ms_from_folder not in self.domain_map:
                continue
            
            domain_tag: str = self.domain_map[ms_from_folder]
            hub_link: Optional[str] = self._get_hub_link(ms=ms_from_folder)
            
            for file in files:
                if file.startswith("FEAT-") and file.endswith(".md"):
                    self._process_single_file(
                        file_path=osPathJoin(root, file),
                        ms_from_folder=ms_from_folder,
                        domain_tag=domain_tag,
                        hub_link=hub_link
                    )
        
        self.logger.info(f"{self.Name} : FEAT file standardization complete.")

    # -----------------------------------------------------------------------------------------------

    def _process_single_file(self, *, file_path: str, ms_from_folder: str, domain_tag: str, hub_link: Optional[str]) -> None:
        """Processes a single FEAT file to update frontmatter and backlinks."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines: List[str] = f.readlines()
            
            new_lines: List[str] = []
            in_frontmatter: bool = False
            frontmatter_end: int = -1
            
            for i, line in enumerate(lines):
                if line.strip() == "---":
                    if not in_frontmatter:
                        in_frontmatter = True
                    else:
                        in_frontmatter = False
                        frontmatter_end = i
                
                if in_frontmatter:
                    if line.startswith("microservice:"):
                        new_lines.append(f"microservice: {ms_from_folder}\n")
                    elif line.startswith("type:"):
                        new_lines.append(f"type: behavior-spec\n")
                    elif line.startswith("tags:"):
                        new_lines.append(line)
                    elif line.strip() == "- null":
                        pass
                    elif line.strip().startswith("- '#"):
                        new_lines.append(line)
                    else:
                        new_lines.append(line)
                else:
                    new_lines.append(line)
            
            # Insert domain tag if not present
            found_tags: bool = False
            for i, line in enumerate(new_lines):
                if line.startswith("tags:"):
                    new_lines.insert(i+1, f"- {domain_tag}\n")
                    found_tags = True
                    break
            
            # Add backlink after frontmatter if not present
            if hub_link:
                link_line: str = f"\n*Back-link: {hub_link}*\n"
                if link_line not in "".join(new_lines):
                    new_lines.insert(frontmatter_end + 1, link_line)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.writelines(new_lines)
        except Exception as e:
            self.logger.error(f"{self.Name} : Error processing {file_path}: {e}")

# -----------------------------------------------------------------------------------------------

def main():
    config = get_config()
    logger = get_logger("FeatFixer")
    fixer = FeatFixer(config=config, logger=logger)
    fixer.process_feats()

if __name__ == "__main__":
    main()
