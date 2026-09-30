#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Knowledge Compressor and Context Distiller for the Bastien-Antigravity ecosystem.
Automates distillation of active session state logs into fresh architectural decision patterns,
ensuring AI session context remains compact and actionable.

DATA FLOW:
1. Bootstraps environment and resolves vault root.
2. Reads recent sessions from 00-AI-Orchestration/AI-Session-State.md.
3. Distills log items into structured pattern candidate blocks.
4. Writes distillation reports to 00-AI-Orchestration/logs/distillations/.

KEY PARAMETERS:
- vault_root: Root directory of the obsidian-brain vault.
- count: Number of recent sessions to extract and distill.
"""

import os
import re
import sys
import argparse
from datetime import datetime
from pathlib import Path

# Standard ecosystem bootstrap
import src.bootstrap as bootstrap
from lib.orchestration_lib import setup_terminal, resolve_vault_and_workspace

logger = bootstrap.logger

# -----------------------------------------------------------------------------

class KnowledgeCompressor:
    def __init__(self, vault_root: Path):
        self.vault_root = vault_root
        canonical_state = vault_root / "00-AI-Orchestration" / "AI-Session-State.md"
        legacy_state = vault_root / "AI-Session-State.md"
        self.session_state_file = canonical_state if canonical_state.exists() else legacy_state
        self.strategy_file = vault_root / "00-AI-Orchestration" / "Knowledge-Strategy.md"
        self.output_dir = vault_root / "00-AI-Orchestration" / "logs" / "distillations"
        os.makedirs(self.output_dir, exist_ok=True)

    # -----------------------------------------------------------------------------

    def extract_recent_sessions(self, count: int = 3) -> list:
        """Extracts the last N sessions from AI-Session-State.md."""
        if not self.session_state_file.exists():
            logger.error("KnowledgeCompressor : {0} not found.".format(self.session_state_file))
            return []

        try:
            with open(self.session_state_file, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            logger.error("KnowledgeCompressor : Error reading session state: {0}".format(e))
            return []

        # Split by H2 headers (Sessions)
        sessions = re.split(r'^##\s+', content, flags=re.MULTILINE)
        if not sessions:
            return []
            
        return [s.strip() for s in sessions[1:count+1]]

    # -----------------------------------------------------------------------------

    def distill_to_pattern(self, session_text: str) -> str:
        """
        Formats a session log into a Decision Pattern candidate.
        """
        lines = session_text.split('\n')
        title_line = lines[0] if lines else "Unknown Session"
        
        # Try to extract a meaningful title from the first bullet or the header
        pattern_title = title_line.replace("📡 ", "").split("(")[0].strip()
        
        # Simple extraction of 'Decision' and 'Impact' from bullets
        actions = []
        for line in lines[1:]:
            clean = line.strip()
            if clean.startswith("- "):
                actions.append(clean[2:])

        distillation = [
            f"### [Candidate Pattern] {pattern_title}",
            f"**Distilled from**: {title_line}",
            f"**Context**: Derived from recent session orchestration.",
            f"**Decision**: ",
        ]
        
        for action in actions:
            distillation.append(f"- {action}")
            
        distillation.append(f"**Impact**: Improved fleet synchronization and governance alignment.")
        distillation.append("")
        
        return "\n".join(distillation)

    # -----------------------------------------------------------------------------

    def run(self, count: int = 1) -> None:
        logger.info("KnowledgeCompressor : Scanning {0} for recent wisdom...".format(self.session_state_file.name))
        sessions = self.extract_recent_sessions(count)
        
        if not sessions:
            logger.info("KnowledgeCompressor : No sessions found to distill.")
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = self.output_dir / f"distillation_{timestamp}.md"
        
        candidates = []
        for s in sessions:
            candidates.append(self.distill_to_pattern(s))
            
        report_content = [
            f"# 🧠 Knowledge Distillation Report",
            f"*Generated: {datetime.now().isoformat()}*",
            f"",
            "> [!TIP]",
            "> Review these candidates and append the verified ones to `00-AI-Orchestration/Knowledge-Strategy.md` Section 5.",
            "",
            "## 💎 Pattern Candidates",
            "",
            "\n".join(candidates)
        ]
        
        try:
            with open(report_file, 'w', encoding='utf-8') as f:
                f.write("\n".join(report_content))
            logger.info("KnowledgeCompressor : Distillation complete! Review candidates in: {0}".format(report_file))
        except Exception as e:
            logger.error("KnowledgeCompressor : Error writing distillation report: {0}".format(e))

# -----------------------------------------------------------------------------

def main():
    setup_terminal()
    vault_root, _ = resolve_vault_and_workspace(__file__)
    parser = argparse.ArgumentParser(description="Knowledge Compressor - Session Log Distiller")
    parser.add_argument("--count", "-c", type=int, default=1, help="Number of recent sessions to distill")
    args = parser.parse_args()

    compressor = KnowledgeCompressor(vault_root)
    compressor.run(count=args.count)

# -----------------------------------------------------------------------------

if __name__ == "__main__":
    main()
