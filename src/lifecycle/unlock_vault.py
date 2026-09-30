#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Restores read/write permissions (chmod 0755/0644) to role prompts in Tech Stack and Core KMS,
enabling AI adapters and templates to be synchronized and edited across the fleet.

DATA FLOW:
1. Bootstraps the virtual environment and resolves vault root.
2. Scans Role-Prompts subdirectories in 03-Tech-Stack and 07-Core-KMS.
3. Recursively updates permissions on directories (0755) and files (0644).
4. Logs completion status.

KEY PARAMETERS:
- folders: List of directories within the vault root to unlock.
"""

import os
import sys
from pathlib import Path

# Standard ecosystem bootstrap
import src.bootstrap as bootstrap
from lib.orchestration_lib import setup_terminal, resolve_vault_and_workspace

logger = bootstrap.logger

# -----------------------------------------------------------------------------

def unlock_role_prompts(vault_root: Path) -> None:
    """Recursively restores permissions to Role-Prompts directories."""
    for folder in ["03-Tech-Stack", "07-Core-KMS"]:
        prompts_dir = vault_root / folder / "Role-Prompts"
        if prompts_dir.exists():
            logger.info("UnlockVault : Unlocking {0}...".format(prompts_dir))
            for root, dirs, files in os.walk(prompts_dir):
                for d in dirs:
                    try:
                        os.chmod(os.path.join(root, d), 0o755)
                    except Exception as e:
                        logger.error("UnlockVault : Error chmod dir {0}: {1}".format(d, e))
                for f in files:
                    try:
                        os.chmod(os.path.join(root, f), 0o644)
                    except Exception as e:
                        logger.error("UnlockVault : Error chmod file {0}: {1}".format(f, e))

    logger.info("UnlockVault : Role prompts unlock complete!")

# -----------------------------------------------------------------------------

def main():
    setup_terminal()
    vault_root, _ = resolve_vault_and_workspace(__file__)
    unlock_role_prompts(vault_root)

# -----------------------------------------------------------------------------

if __name__ == '__main__':
    main()
