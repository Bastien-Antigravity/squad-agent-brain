#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Audits the Obsidian vault for structural integrity, YAML compliance, and link health.

DATA FLOW:
1. Scans all .md files in the vault.
2. Parses frontmatter and extracts internal [[Links]].
3. Identifies orphans (files with no incoming links) and broken links.
4. Generates a "Coherence Report".

KEY PARAMETERS:
- VAULT_ROOT: The target directory for auditing.
- IGNORE_DIRS: Folders to skip during the scan.
"""

import os
import sys
from pathlib import Path

# Add src root and project root to sys.path to enable loading lib.* and src.* modules
_self_dir = Path(__file__).resolve().parent
_src_dir = _self_dir.parent
_project_dir = _src_dir.parent
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))
if str(_project_dir) not in sys.path:
    sys.path.insert(0, str(_project_dir))

from lib.bootstrap import ensure_virtualenv, prepend_venv_bin, ensure_import_paths

script_dir = _self_dir
vault_root = ensure_virtualenv(str(script_dir))
prepend_venv_bin(vault_root)

ensure_import_paths(script_dir, vault_root)

from sys import exit as sysExit, stdout as sysStdout, path as sysPath
from os import walk as osWalk
from pathlib import Path
from typing import List

# Add the lib directory to sys.path to import sovereignty
script_dir = Path(__file__).resolve().parent
lib_path = script_dir.parent / "lib"
sysPath.append(str(lib_path))

try:
    from sovereignty import Sovereignty
except ImportError:
    print(f"❌ Error: Could not find sovereignty.py in {lib_path}")
    sysExit(1)

# Standardize terminal output encoding for Windows
if sysStdout.encoding != 'utf-8':
    try:
        sysStdout.reconfigure(encoding='utf-8')
    except (AttributeError, Exception):
        pass

from lib.orchestration_lib import resolve_vault_and_workspace, get_logger

VAULT_ROOT, WORKSPACE_ROOT = resolve_vault_and_workspace(__file__)
logger = get_logger("BrainSentinel")

IGNORE_DIRS = {
    ".git", ".obsidian", ".gemini", ".claude", ".codex", ".mistral", ".deepseek", ".venv", "venv", "node_modules",
    "experiments", "deployments", "plans", "Templates", "04-Templates",
    "09-RAG-Engine"
}

# -----------------------------------------------------------------------------------------------

from src.interfaces import Auditor

class BrainSentinel(Auditor):
    Name = "BrainSentinel"

    def __init__(self, root: Path) -> None:
        self.root = root
        self.files: List[Path] = []
        taxonomy_path = root / "07-Core-KMS" / "tag_taxonomy.md"
        self.engine = Sovereignty(taxonomy_path, WORKSPACE_ROOT)

    # -----------------------------------------------------------------------------------------------

    def scan(self) -> None:
        """
        Discovers all files and builds the relationship graph.
        """
        for root, dirs, files in osWalk(self.root):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in IGNORE_DIRS]
            for file in files:
                path = Path(root) / file
                rel_path = path.relative_to(self.root).as_posix()
                
                if file.endswith(".md"):
                    self.files.append(path)

    # -----------------------------------------------------------------------------------------------

    def audit(self, *args, **kwargs) -> bool:
        """
        Runs the validation rules using the Sovereignty engine.
        """
        for file_path in self.files:
            self.engine.audit_file(file_path)
        return self.engine.get_report()["success"]


    # -----------------------------------------------------------------------------------------------

    def auto_fix(self) -> None:
        """
        Runs the auto-fix logic using the Sovereignty engine.
        """
        for file_path in self.files:
            self.engine.auto_fix_file(file_path)

    # -----------------------------------------------------------------------------------------------

    def report(self) -> None:
        """
        Outputs the audit summary to the terminal.
        """
        report = self.engine.get_report()
        errors = report["errors"]
        warnings = report["warnings"]

        logger.info("="*60)
        logger.info("🧠 BASTIEN BRAIN SENTINEL: HEALTH REPORT")
        logger.info("="*60)
        
        logger.info(f"📊 STATISTICS:")
        logger.info(f"  - Total Markdown Files: {len(self.files)}")
        logger.info(f"  - Total Errors: {len(errors)}")
        logger.info(f"  - Total Warnings: {len(warnings)}")

        if errors:
            logger.warning(f"🚨 CRITICAL VIOLATIONS ({len(errors)}):")
            for err in errors[:15]:
                logger.warning(f"  [!] {err}")
            if len(errors) > 15:
                logger.warning(f"  ... and {len(errors) - 15} more.")

        if warnings:
            logger.info(f"⚠️ HYGIENE WARNINGS ({len(warnings)}):")
            for warn in warnings[:10]:
                logger.info(f"  [~] {warn}")
            if len(warnings) > 10:
                logger.info(f"  ... and {len(warnings) - 10} more.")
            
        logger.info("="*60)
        logger.info("📈 SYNTHESIS VERDICT:")
        
        if report["success"]:
            logger.info("  - Accuracy:     High (0 Errors)")
            logger.info("✨ OVERALL RESULT: BRAIN IS IN PERFECT COHERENCE")
        else:
            logger.info(f"  - Accuracy:     Low ({len(errors)} Errors)")
            logger.warning("⚠️ OVERALL RESULT: DRIFT DETECTED. PLEASE RESOLVE THE ABOVE ISSUES.")
        logger.info("="*60)

# -----------------------------------------------------------------------------------------------

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Bastien Brain Sentinel: Health Audit")
    parser.add_argument("--path", type=str, help="Subdirectory to audit (relative to VAULT_ROOT)")
    args = parser.parse_args()

    target_root = VAULT_ROOT
    if args.path:
        target_root = VAULT_ROOT / args.path

    sentinel = BrainSentinel(target_root)
    sentinel.scan()
    sentinel.auto_fix()
    sentinel.audit()
    sentinel.report()


if __name__ == "__main__":
    main()
