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

try:
    from microservice_toolbox.utils.bootstrap import bootstrap_microservice
except ImportError:
    for parent in Path(__file__).resolve().parents:
        toolbox_py = parent / "microservice-toolbox" / "python"
        if toolbox_py.exists():
            sys.path.insert(0, str(toolbox_py))
            break
    from microservice_toolbox.utils.bootstrap import bootstrap_microservice

bootstrap_microservice(__file__, app_name="fleet_init_update")

from json import load as jsonLoad
from universal_logger import UniLog
from lib.orchestration_lib import resolve_vault_and_workspace

vault_root, workspace_root = resolve_vault_and_workspace(__file__)
logger = UniLog(app_name="fleet_init_update")

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
> "4. **Sentinel Audit**: Run `python3 08-Squad-Agent/main.py preflight-check` and resolve any drift."
> "5. **Squad Protocol**: You are now the **Lead Developer**. Identify and hire the required **Specialists** from `07-Core-KMS/Role-Prompts/03-Developer/Squad/`."
"""

# -----------------------------------------------------------------------------------------------

def update_fleet() -> None:
    """
    Scans the inventory and updates the AI-Init.md file for every registered repository.
    """
    if not INVENTORY_PATH.exists():
        logger.error(f"FleetUpdate: Inventory not found at {INVENTORY_PATH}")
        return

    with open(INVENTORY_PATH, 'r', encoding='utf-8') as f:
        data = jsonLoad(f)

    repos = data.get("repositories", [])
    logger.info(f"Starting Fleet-Wide AI-Init Update for {len(repos)} repositories...")

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
            logger.warning(f"Skipping {name}: Path does not exist ({path})")
            continue

        init_file = path / "AI-Init.md"
        content = TEMPLATE.format(repo_name=name)
        
        try:
            with open(init_file, 'w', encoding='utf-8') as f:
                f.write(content)
            logger.info(f"Updated: {name}")
        except Exception as e:
            logger.error(f"Failed {name}: {e}")

    logger.info("Fleet Update Complete.")

# -----------------------------------------------------------------------------------------------

def main():
    update_fleet()


if __name__ == "__main__":
    main()
