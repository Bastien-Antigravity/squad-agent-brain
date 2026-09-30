#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Scans the workspace and reliably generates inventory.json for the Fleet Manager.
Native first-class Engine Room implementation in 08-Base-Scripts.

DATA FLOW:
1. Resolves vault & workspace roots via orchestration_lib.
2. Hard-aborts if the tool is invoked from a FORBIDDEN branch (e.g. 'main').
3. Walks every directory looking for .git repos.
4. For each repo, auto-detects compliance exclusions and flags forbidden branches.
5. Merges with existing inventory.json to preserve manual overrides.
6. Writes a clean, sorted inventory.json to 05-Fleet-Operation/00-Repo-Control/inventory.json.

KEY PARAMETERS:
- fleet_name: Written into the "fleet_name" key.
- master_branch: Default and only authorised branch ('develop').
- forbidden_branches: Set of branch names that are strictly prohibited ('main').
"""

import os
import sys
import argparse
import subprocess
from pathlib import Path
from json import load as jsonLoad, dump as jsonDump
from typing import Dict, List, Any, Optional

from lib.orchestration_lib import setup_terminal, get_logger, get_config, resolve_vault_and_workspace

setup_terminal()

# -----------------------------------------------------------------------------------------------

class MInventoryBuilder:
    """
    Core class responsible for discovering repositories and managing the fleet inventory.
    """

    def __init__(self, *, config: Any = None, logger: Any = None, name: Optional[str] = None):
        self.config = config or get_config()
        self.logger = logger or get_logger("MInventoryBuilder")
        self.Name = name or self.__class__.__name__
        self.FleetName = "Bastien-Antigravity"
        self.MasterBranch = "develop"
        self.ForbiddenBranches = frozenset({"main"})
        self.CodeExtensions = {".go", ".rs", ".cpp", ".c", ".java", ".ts", ".js"}
        self.PlainMarkers = [
            "go.mod", "Cargo.toml", "package.json",
            "requirements.txt", "setup.py", "pyproject.toml",
            "CMakeLists.txt", "Makefile",
        ]
        self.vault_root, self.workspace_root = resolve_vault_and_workspace(__file__)
        self.inventory_path = self.vault_root / "05-Fleet-Operation" / "00-Repo-Control" / "inventory.json"

    # -----------------------------------------------------------------------------------------------

    def build(self, *, dry_run: bool = False) -> None:
        """
        Executes the full inventory building process.
        """
        # Step 0: Branch Guard
        self._abort_if_self_on_forbidden_branch(script_path=Path(__file__).resolve())

        self.logger.info(f"{self.Name} : 🔍 Workspace root : {self.workspace_root}")
        self.logger.info(f"{self.Name} : 📄 Inventory path : {self.inventory_path}")
        self.logger.info(f"{self.Name} : 🔒 Master branch  : {self.MasterBranch}")

        # Step 1: Load existing data
        existing = self._load_existing_inventory(inventory_path=self.inventory_path)
        manual_overrides = self._build_manual_overrides(existing=existing)
        if manual_overrides:
            self.logger.info(f"{self.Name} : 🔒 Preserving {len(manual_overrides)} manual override(s)")

        # Step 2: Discover repos
        self.logger.info(f"{self.Name} : 🔎 Scanning for repositories...")
        discovered = self._discover_repos(workspace_root=self.workspace_root)
        self.logger.info(f"{self.Name} :    Found {len(discovered)} repositories.")

        # Step 3: Build final repo list
        repositories = []
        for repo in discovered:
            name = repo["name"]
            raw_path = repo.pop("raw_path")

            if name in manual_overrides:
                over = manual_overrides[name]
                exclude = over.get("exclude_from_compliance", False)
                source = "manual"
            else:
                exclude = self._is_knowledge_base(repo_path=raw_path, workspace_root=self.workspace_root)
                source = "auto"

            repo_type = self._detect_repo_type(repo_name=name, is_excluded=exclude)
            entry: Dict[str, Any] = {
                "name": name,
                "path": repo["path"],
                "remote": repo["remote"],
                "master_branch": repo["master_branch"],
                "repo_type": repo_type,
            }

            if exclude:
                entry["exclude_from_compliance"] = True

            # Preserve manual override keys
            if name in manual_overrides:
                for k, v in manual_overrides[name].items():
                    entry[k] = v

            repositories.append(entry)

            status = "⛔ EXCLUDED " if exclude else "✅ COMPLIANT"
            self.logger.info(f"{self.Name} :    {name:<30} {status} [{repo_type}] [{source}]")

        # Step 4: Output
        payload = {
            "fleet_name": self.FleetName,
            "master_branch": self.MasterBranch,
            "repositories": repositories,
        }

        if dry_run:
            self.logger.info(f"{self.Name} : 🧪 DRY RUN — Would write {len(repositories)} repos.")
            return

        self.inventory_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(self.inventory_path, "w", encoding="utf-8") as f:
                jsonDump(payload, f, indent=2)
            self.logger.info(f"{self.Name} : ✨ Inventory written to: {self.inventory_path}")
            self.logger.info(f"{self.Name} : 🚀 Registered {len(repositories)} repositories.")
        except Exception as e:
            self.logger.critical(f"{self.Name} : Failed to save inventory: {e}")
            sys.exit(1)

    # -----------------------------------------------------------------------------------------------

    def _abort_if_self_on_forbidden_branch(self, *, script_path: Path) -> None:
        try:
            res = subprocess.run(
                ["git", "-C", str(script_path.parent), "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if res.returncode == 0:
                branch = res.stdout.strip()
                if branch in self.ForbiddenBranches:
                    self.logger.critical(
                        f"{self.Name} : [FORBIDDEN BRANCH] build-inventory cannot be run on branch '{branch}'. Aborting."
                    )
                    sys.exit(1)
        except Exception:
            pass

    # -----------------------------------------------------------------------------------------------

    def _detect_repo_type(self, *, repo_name: str, is_excluded: bool) -> str:
        if is_excluded:
            return "orchestration"
        if repo_name in {"docker-deployment", "sandbox-testing"}:
            return "orchestration"
        if any(repo_name.endswith(s) for s in ("-logger", "-config", "-toolbox", "-socket")):
            return "library"
        if repo_name in {"config-server", "log-server", "notif-server", "tele-remote", "rag-engine", "web-interface"}:
            return "level1-microservice"
        return "level2-microservice"

    # -----------------------------------------------------------------------------------------------

    def _is_knowledge_base(self, *, repo_path: Path, workspace_root: Path) -> bool:
        if repo_path == workspace_root / "obsidian-brain":
            return True
        obsidian_dir = workspace_root / "obsidian-brain"
        try:
            repo_path.relative_to(obsidian_dir)
            return True
        except ValueError:
            pass
        return False

    # -----------------------------------------------------------------------------------------------

    def _get_git_remote_and_branch(self, *, repo_path: Path) -> tuple:
        remote = ""
        branch = self.MasterBranch
        try:
            r = subprocess.run(
                ["git", "-C", str(repo_path), "remote", "get-url", "origin"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if r.returncode == 0:
                remote = r.stdout.strip()
        except Exception:
            pass

        try:
            r = subprocess.run(
                ["git", "-C", str(repo_path), "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if r.returncode == 0:
                branch = r.stdout.strip()
                if branch in self.ForbiddenBranches:
                    self.logger.warning(
                        f"{self.Name} : [FORBIDDEN BRANCH] {repo_path.name} is on '{branch}'!"
                    )
        except Exception:
            pass

        return remote, branch

    # -----------------------------------------------------------------------------------------------

    def _discover_repos(self, *, workspace_root: Path) -> List[Dict[str, Any]]:
        found = []
        for root, dirs, _ in os.walk(str(workspace_root)):
            p_root = Path(root)
            if p_root.name in {".git", ".venv", "venv", "node_modules", "target", "bin", "dist"}:
                dirs.clear()
                continue

            if (p_root / ".git").exists():
                path = p_root.resolve()
                remote, branch = self._get_git_remote_and_branch(repo_path=path)

                try:
                    rel_path = f"./{path.relative_to(workspace_root).as_posix()}"
                except ValueError:
                    rel_path = str(path)

                found.append({
                    "name": path.name,
                    "path": rel_path,
                    "raw_path": path,
                    "remote": remote,
                    "master_branch": branch,
                })
                dirs[:] = [d for d in dirs if d != ".git"]

        found.sort(key=lambda x: x["name"])
        return found

    # -----------------------------------------------------------------------------------------------

    def _load_existing_inventory(self, *, inventory_path: Path) -> Dict[str, Any]:
        if not inventory_path.exists():
            return {"fleet_name": self.FleetName, "master_branch": self.MasterBranch, "repositories": []}
        try:
            with open(inventory_path, "r", encoding="utf-8") as f:
                return jsonLoad(f)
        except Exception as e:
            self.logger.warning(f"{self.Name} : Could not read existing inventory: {e}")
            return {"fleet_name": self.FleetName, "master_branch": self.MasterBranch, "repositories": []}

    # -----------------------------------------------------------------------------------------------

    def _build_manual_overrides(self, *, existing: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        overrides: Dict[str, Dict[str, Any]] = {}
        for repo in existing.get("repositories", []):
            name = repo.get("name")
            if name:
                overrides[name] = {
                    k: repo[k] for k in ("exclude_from_compliance", "is_core", "modes") if k in repo
                }
        return overrides


# -----------------------------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Build or rebuild inventory.json.")
    parser.add_argument("--dry-run", "-n", action="store_true", help="Scan without writing.")
    args = parser.parse_args()

    builder = MInventoryBuilder()
    builder.build(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
