#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Propagates the standardized AI-Init.md file across all repositories 
defined in the fleet inventory.

DATA FLOW:
1. Reads the global repository list from inventory.json.
2. For each repository, generates an AI-Init.md file from a template.
3. Overwrites the existing AI-Init.md in each target repository root.

KEY PARAMETERS:
- INVENTORY_PATH: Path to the fleet registry (JSON).
- TEMPLATE: The markdown content for the initialization prompt.
"""

import os
import sys
from pathlib import Path
from lib.bootstrap import ensure_virtualenv, prepend_venv_bin, ensure_import_paths

script_dir = Path(__file__).resolve().parent
vault_root = ensure_virtualenv(str(script_dir))
prepend_venv_bin(vault_root)

ensure_import_paths(script_dir, vault_root)

from json import load as jsonLoad
from pathlib import Path
from sys import stdout as sysStdout

# Standardize terminal output encoding for Windows
if sysStdout.encoding != 'utf-8':
    try:
        sysStdout.reconfigure(encoding='utf-8')
    except (AttributeError, Exception):
        pass

# ### CONFIGURATIONS ###

from lib.orchestration_lib import resolve_vault_and_workspace

vault_root, workspace_root = resolve_vault_and_workspace(__file__)

# Path to the inventory
INVENTORY_PATH = vault_root / "05-Fleet-Operation" / "00-Repo-Control" / "inventory.json"
if not INVENTORY_PATH.exists():
    INVENTORY_PATH = workspace_root / "fleet-operation-brain" / "00-Repo-Control" / "inventory.json"

TEMPLATE = """---
microservice: {repo_name}
type: governance
status: active
---

# ⚡ AI Initialization: {repo_name}

> [!IMPORTANT] MANDATORY INITIALIZATION
> Copy and paste this prompt when starting a new session in this repository:
> 
> "1. Read the ecosystem map in **[[Ecosystem-Map-MOC]]**."
> "2. Load project constraints from **[[AI-Project-DNA]]**."
> "3. Restore session state from **[[AI-Session-State]]**."
> "4. **Sentinel Audit**: Run `python3 08-Base-Scripts/main.py preflight-check` and resolve any drift."
> "5. **Squad Protocol**: You are now the **Lead Developer**. Identify and hire the required **Specialists** from `07-Core-KMS/Role-Prompts/03-Developer/Squad/`."
"""

# -----------------------------------------------------------------------------------------------

def update_fleet() -> None:
    """
    Scans the inventory and updates the AI-Init.md file for every registered repository.
    """
    if not INVENTORY_PATH.exists():
        print("FleetUpdate: Inventory not found at {0}".format(INVENTORY_PATH))
        return

    with open(INVENTORY_PATH, 'r', encoding='utf-8') as f:
        data = jsonLoad(f)

    repos = data.get("repositories", [])
    print("🚀 Starting Fleet-Wide AI-Init Update for {0} repositories...".format(len(repos)))

    for repo in repos:
        name = repo.get("name")
        path_str = repo.get("path")
        
        if not path_str:
            continue
        
        # Resolve relative paths against workspace root
        path = Path(path_str)
        if not path.is_absolute():
            path = (workspace_root / path_str).resolve()
        
        if not path.exists():
            print("  [!] Skipping {0}: Path does not exist ({1})".format(name, path))
            continue

        init_file = path / "AI-Init.md"
        content = TEMPLATE.format(repo_name=name)
        
        try:
            with open(init_file, 'w', encoding='utf-8') as f:
                f.write(content)
            print("  [+] Updated: {0}".format(name))
        except Exception as e:
            print("  [X] Failed {0}: {1}".format(name, str(e)))

    print("\n✅ Fleet Update Complete.")

# -----------------------------------------------------------------------------------------------

def main():
    update_fleet()


if __name__ == "__main__":
    main()
