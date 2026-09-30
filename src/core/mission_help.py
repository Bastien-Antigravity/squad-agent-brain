#!/usr/bin/env python
# coding:utf-8
"""
ESSENTIAL PROCESS: Mission Help - Displays a cheat sheet of missions, personas, and keywords.
DATA FLOW: Prints static help content to the terminal to assist the user in AI squad delegation.
KEY PARAMETERS: None
"""
import os
import sys
from pathlib import Path
from lib.bootstrap import ensure_virtualenv, prepend_venv_bin, ensure_import_paths

script_dir = Path(__file__).resolve().parent
vault_root = ensure_virtualenv(str(script_dir))
prepend_venv_bin(vault_root)

ensure_import_paths(script_dir, vault_root)

from lib.orchestration_lib import setup_terminal
setup_terminal()

from typing import Optional

# ### COMPONENT CLASS ###

class MissionHelper:
    Name: str = "MissionHelper"

    def __init__(self, config: Optional[object] = None, logger: Optional[object] = None) -> None:
        self.config = config
        self.logger = logger

    # -----------------------------------------------------------------------------------------------

    def print_cheat_sheet(self) -> None:
        """Prints the formatted help content to stdout."""
        print("\n--- 💡 Bastien-Antigravity Squad Cheat Sheet ---")
        
        print("\n👥 The Squad (Available for Delegation)")
        print("   - Orchestrator  : Mission planning & coordination.")
        print("   - Architect     : System design & ADR enforcement.")
        print("   - Developer     : Feature implementation & bug fixing.")
        print("   - QA            : Testing, BDD specs, & auditing.")
        print("   - Sentinel      : Governance, sovereignty, & health audits.")
        print("   - Oracle        : Strategic nexus & trajectory analysis.")
        print("   - FleetArchitect: Cross-repo standards & CI/CD logic.")
        print("   - FleetCommander: Multi-repo sync & git orchestration.")
        print("   - DocMaintainer : Link integrity, MOCs, & knowledge mapping.")
        print("   - Purger        : Technical debt & redundant file removal.")

        print("\n🛡️ Mode 1: Spec-First")
        print("   > Ask QA to audit @06-Microservices against specs in @02-Business-BDD.")
        
        print("\n🧪 Mode 2: Free-Labs")
        print("   > Ask Developer to build a prototype in @04-Rapid-Prototyping.")
        
        print("\n🛰️ Mode 3: Fleet-Commander")
        print("   > Ask Fleet Commander to sync the ecosystem to the develop branch.")
        
        print("\n🔄 Protocols & Maintenance")
        print("   > Ask Sentinel to switch to Mode 2 and update the manual.")
        print("   > Ask DocMaintainer to repair links in the vault and update the MOC.")
        
        print("\n🏁 Session Persistence")
        print("   > \"Restore session state\" (Load context at start)")
        print("   > \"Update AI-Session-State.md with progress\" (Save context at end)")
        
        print("\n🛠️ CLI Utility Commands")
        print("   - /mcp list    : Verify tool availability.")
        print("   - /agents list : See all available squad members.")
        
        print("\n🔑 Keywords & Symbols")
        print("   - [SCAN]   : Mandatory header for every AI response.")
        print("   - @<file> : Mention a file for context (e.g. @README.md).")
        print("   - !<cmd>  : Execute terminal commands (e.g. !ls).")
        print("\n-------------------------------------------------\n")

# ### MAIN EXECUTION ###

def main():
    helper = MissionHelper()
    helper.print_cheat_sheet()


if __name__ == "__main__":
    main()
