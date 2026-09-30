#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Unified CLI entry point router for Bastien-Antigravity base ecosystem tools.

DATA FLOW:
1. Imports src.bootstrap to align paths, relaunch in virtualenv, and load configuration.
2. Resolves the requested themed package mapping.
3. Parses the first argument (command) and forwards remaining arguments to the correct module main().

KEY PARAMETERS:
- sys.argv: Command line arguments containing target command and forwarded flags.
"""

import sys
from pathlib import Path

# Add 08-Base-Scripts root to sys.path so we can import src.*
_self_dir = Path(__file__).resolve().parent
if str(_self_dir) not in sys.path:
    sys.path.insert(0, str(_self_dir))

# Enforce environment bootstrap & configuration loading
import src.bootstrap as bootstrap

# -----------------------------------------------------------------------------

# Commands map (CLI alias -> themed python module namespace relative to src)
COMMANDS_MAP = {
    "agent-dispatcher": "core.agent_dispatcher",
    "audit-ports": "auditing.audit_ports",
    "brain-health-audit": "auditing.brain_health_audit",
    "validate-compliance": "auditing.validate_compliance",
    "build-inventory": "fleet.build_inventory",
    "fleet-init-update": "fleet.fleet_init_update",
    "fleet-refresh": "fleet.fleet_refresh",
    "hardening-yaml": "auditing.hardening_yaml",
    "init-new-brain": "lifecycle.init_new_brain",
    "joint-audit-purger": "maintenance.joint_audit_purger",
    "maintenance-skill": "maintenance.maintenance_skill",
    "preflight-check": "auditing.preflight_check",
    "close-mission": "fleet.close_mission",
    "convert-agents": "fleet.convert_agents",
    "ensure-frontmatter": "auditing.ensure_frontmatter",
    "fleet-commander": "fleet.fleet_commander",
    "install-git-hooks": "lifecycle.install_git_hooks",
    "knowledge-compressor": "maintenance.knowledge_compressor",
    "mission-help": "core.mission_help",
    "persona-extractor": "extraction.persona_extractor",
    "scaffold-microservice": "lifecycle.scaffold_microservice",
    "scaffold-new-brain": "lifecycle.scaffold_new_brain",
    "start-squad": "core.start_squad",
    "switch-mode": "core.switch_mode",
    "unlock-vault": "lifecycle.unlock_vault",
    "check-coherence": "auditing.check_coherence",
    "map-feats": "fleet.map_feats",
    "fix-feats": "fleet.fix_feats",
    "controller": "core.controller",
    "discord-client": "clients.discord_client",
    "format-compliance": "lib.improved_transformer"
}

# -----------------------------------------------------------------------------

def print_usage():
    print("Usage: python3 08-Base-Scripts/main.py <command> [args...]")
    print("\nAvailable commands:")
    for cmd in sorted(COMMANDS_MAP.keys()):
        print(f"  - {cmd}")

# -----------------------------------------------------------------------------

def main():
    if len(sys.argv) < 2:
        print_usage()
        sys.exit(1)
        
    cmd_arg = sys.argv[1].lower()
    
    if cmd_arg not in COMMANDS_MAP:
        print(f"❌ Unknown command: {cmd_arg}")
        print_usage()
        sys.exit(1)
        
    module_path = COMMANDS_MAP[cmd_arg]
    
    # Shift arguments to remove "main.py" and the command name
    sys.argv = [sys.argv[0]] + sys.argv[2:]
    
    # Import and run command
    try:
        import importlib
        module = importlib.import_module(f"src.{module_path}")
        module.main()
    except Exception as e:
        import traceback
        print(f"❌ Error running command '{cmd_arg}': {e}")
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()

