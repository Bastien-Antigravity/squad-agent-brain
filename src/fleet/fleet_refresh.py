#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Safely refreshes, synchronizes, or clones repositories across the fleet.
Enforces strict anti-data-loss verification to ensure uncommitted work is NEVER lost.

DATA FLOW:
1. Loads target repositories from inventory.json (SSoT default) or GitHub API.
2. For each repository:
   - If directory does not exist: clones from remote.
   - If directory exists: runs git status to verify working tree purity.
   - If dirty / uncommitted changes: SKIPS operation with warning to protect data.
   - If clean: synchronizes via git fetch or optional clean re-clone.
3. Reports comprehensive status summary across the fleet.

KEY PARAMETERS:
- account: GitHub account/organization (fallback if querying API).
- target: Target base directory for repositories.
- dry_run: Preview operations without touching filesystem.
- use_inventory: Use inventory.json as authoritative list (True by default).
- wipe: Re-clone clean repositories (STRICTLY blocked if repository is dirty).
"""

import sys
import argparse
import subprocess
from os import chmod
from pathlib import Path
from shutil import rmtree
from json import load as jsonLoad, loads as jsonLoads
from typing import List, Dict, Any, Optional, Tuple

from lib.orchestration_lib import setup_terminal, get_logger, get_config, resolve_vault_and_workspace

setup_terminal()

DEFAULT_USER = "Bastien-Antigravity"

# -----------------------------------------------------------------------------------------------

class FleetRefresher:
    """
    Core class for performing safe, non-destructive repository synchronization and cloning.
    """

    def __init__(self, *, config: Any = None, logger: Any = None, name: Optional[str] = None) -> None:
        self.config = config or get_config()
        self.logger = logger or get_logger("FleetRefresher")
        self.Name = name or self.__class__.__name__
        self.vault_root, self.workspace_root = resolve_vault_and_workspace(__file__)

    # -----------------------------------------------------------------------------------------------

    def _is_repo_dirty(self, path: Path) -> Tuple[bool, str]:
        """
        Inspects working tree status to ensure untracked files or uncommitted changes are never wiped.
        Returns (is_dirty, reason).
        """
        git_dir = path / ".git"
        if not git_dir.exists():
            return True, "Not a git repository (foreign folder)"

        try:
            res = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=str(path),
                capture_output=True,
                text=True,
                timeout=15,
            )
            if res.returncode != 0:
                return True, f"git status check failed: {res.stderr.strip()}"
            if res.stdout.strip():
                return True, "Uncommitted or untracked changes present"
            return False, ""
        except Exception as e:
            return True, f"Error running git status: {e}"

    # -----------------------------------------------------------------------------------------------

    def run_refresh(
        self,
        *,
        account: str,
        target: str,
        dry_run: bool,
        use_inventory: bool = True,
        wipe: bool = False,
    ) -> None:
        """
        Executes the safe refresh workflow.
        """
        if not target or target == ".":
            target = str(self.workspace_root)

        repos_to_refresh = []

        if use_inventory:
            inventory_path = self.vault_root / "05-Fleet-Operation" / "00-Repo-Control" / "inventory.json"
            if not inventory_path.exists():
                self.logger.critical(f"{self.Name} : [CRITICAL] inventory.json not found at {inventory_path}")
                sys.exit(1)

            try:
                with open(inventory_path, "r", encoding="utf-8") as f:
                    inventory = jsonLoad(f)
                    for r in inventory.get("repositories", []):
                        repos_to_refresh.append({
                            "name": r["name"],
                            "clone_url": r["remote"]
                        })
                self.logger.info(f"{self.Name} : Loaded {len(repos_to_refresh)} repos from inventory.json (SSoT).")
            except Exception as e:
                self.logger.critical(f"{self.Name} : Failed to load inventory: {e}")
                sys.exit(1)
        else:
            repos_to_refresh = self.get_github_repos(user=account)

        if repos_to_refresh:
            self.refresh_repos(repos=repos_to_refresh, target_base_dir=target, dry_run=dry_run, wipe=wipe)
            self.logger.info(f"{self.Name} : \n--- Fleet Refresh operations finished ---")
        else:
            self.logger.error(f"{self.Name} : [ERROR] No repositories found to refresh.")
            sys.exit(1)

    # -----------------------------------------------------------------------------------------------

    def get_github_repos(self, *, user: str) -> Optional[List[Dict[str, Any]]]:
        """
        Fetches repository list from GitHub API as a fallback when inventory is not used.
        """
        from urllib.request import Request, urlopen

        self.logger.info(f"{self.Name} : Step 1: Fetching repositories for '{user}' from GitHub API...")
        repos = []
        page = 1
        while True:
            api_url = f"https://api.github.com/users/{user}/repos?page={page}&per_page=100"
            try:
                req = Request(api_url)
                req.add_header("User-Agent", "Python-Fleet-Refresher")
                with urlopen(req) as response:
                    page_repos = jsonLoads(response.read().decode("utf-8"))
                    if not page_repos:
                        break
                    repos.extend(page_repos)
                    page += 1
            except Exception as e:
                self.logger.error(f"{self.Name} :   [CRITICAL] API Error on page {page}: {e}")
                return None
        return repos

    # -----------------------------------------------------------------------------------------------

    def refresh_repos(
        self,
        *,
        repos: List[Dict[str, Any]],
        target_base_dir: str = ".",
        dry_run: bool = False,
        wipe: bool = False,
    ) -> None:
        """
        Safe synchronization and cloning logic with data-loss prevention guardrails.
        """
        self.logger.info(f"{self.Name} : Step 2: Processing {len(repos)} repositories in '{target_base_dir}'...")

        if dry_run:
            self.logger.info(f"{self.Name} :   [DRY RUN] Simulation mode active. No filesystem modifications will occur.")

        base_path = Path(target_base_dir).resolve()
        if not base_path.exists() and not dry_run:
            try:
                base_path.mkdir(parents=True, exist_ok=True)
                self.logger.info(f"{self.Name} :   [INFO] Target directory created: {base_path}")
            except Exception as e:
                self.logger.error(f"{self.Name} : Failed to create target directory {base_path}: {e}")
                return

        for repo in repos:
            name = repo["name"]
            clone_url = repo["clone_url"]
            target_path = base_path / name

            if target_path.exists():
                is_dirty, reason = self._is_repo_dirty(target_path)
                if is_dirty:
                    self.logger.warning(
                        f"{self.Name} :   ⚠️ [PROTECT] Skipping '{name}': {reason}. Local changes preserved!"
                    )
                    continue

                if wipe:
                    if dry_run:
                        self.logger.info(f"{self.Name} :   [DRY RUN] Would remove clean folder and re-clone: {target_path}")
                    else:
                        self.logger.info(f"{self.Name} :   [SAFE WIPE] Repository clean. Removing for fresh clone: {name}")
                        try:
                            rmtree(str(target_path), onerror=self._handle_remove_readonly)
                        except Exception as e:
                            self.logger.error(f"{self.Name} :     [ERROR] Deletion failed for {name}: {e}")
                            continue
                else:
                    if dry_run:
                        self.logger.info(f"{self.Name} :   [DRY RUN] Would fetch latest updates for clean repository: {name}")
                    else:
                        self.logger.info(f"{self.Name} :   [SYNC] Clean repository found. Fetching updates: {name}...")
                        res = subprocess.run(["git", "fetch", "--all", "--prune"], cwd=str(target_path), capture_output=True, text=True)
                        if res.returncode == 0:
                            self.logger.info(f"{self.Name} :     [SUCCESS] {name} fetched cleanly.")
                        else:
                            self.logger.error(f"{self.Name} :     [ERROR] Fetch failed for {name}: {res.stderr.strip()}")
                    continue

            if not target_path.exists():
                if dry_run:
                    self.logger.info(f"{self.Name} :   [DRY RUN] Would clone {name} into {target_path}")
                else:
                    self.logger.info(f"{self.Name} :   [CLONE] Fetching fresh copy of {name}...")
                    result = subprocess.run(["git", "clone", clone_url, str(target_path)], capture_output=True, text=True)

                    if result.returncode == 0:
                        self.logger.info(f"{self.Name} :     [SUCCESS] {name} cloned successfully.")
                    else:
                        self.logger.error(f"{self.Name} :     [ERROR] Clone failed for {name}: {result.stderr.strip()}")

    # -----------------------------------------------------------------------------------------------

    def _handle_remove_readonly(self, func: Any, path: str, excinfo: Any) -> None:
        """
        Handles read-only files during authorized deletion.
        """
        try:
            chmod(path, 0o777)
            func(path)
        except Exception:
            pass


# -----------------------------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Fleet Refresh: Non-destructive sync and safe cloning.")
    parser.add_argument("account", nargs="?", default=DEFAULT_USER, help="GitHub account")
    parser.add_argument("--target", "-t", default=".", help="Target directory")
    parser.add_argument("--dry-run", action="store_true", help="Simulate actions without modifying files")
    parser.add_argument("--github-api", action="store_true", help="Fetch repos from GitHub API instead of inventory.json")
    parser.add_argument("--inventory", "-i", action="store_true", default=True, help="Use inventory.json (default)")
    parser.add_argument("--wipe", action="store_true", help="Re-clone clean repositories (blocked if repository has uncommitted changes)")

    args = parser.parse_args()

    use_inv = not args.github_api

    refresher = FleetRefresher()
    refresher.run_refresh(
        account=args.account,
        target=args.target,
        dry_run=args.dry_run,
        use_inventory=use_inv,
        wipe=args.wipe,
    )


if __name__ == "__main__":
    main()
