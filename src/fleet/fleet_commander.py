#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Fleet Commander - Unified Fleet Git, Synchronization, and Architectural Compliance.
Native first-class Engine Room orchestrator in 08-Base-Scripts.

DATA FLOW:
1. Loads registered repositories from inventory.json (SSoT).
2. Audits architecture, documentation, and isolation zone compliance via Sovereignty engine.
3. Coordinates multi-repo status audits, atomic sync, vault submodule synchronization, and pushes.

KEY PARAMETERS:
- action: 'status', 'sync', 'vault-sync', or 'push'. Defaults to 'status'.
- repo: Target a specific repository or active workspaces.
- is_fleet: Explicitly target all repositories.
- message: Standardized commit message.
- tag: Optional Git release tag.
- dry_run: Simulate operations without modifying repositories.
"""

import os
import sys
import argparse
import subprocess
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Any
from json import load as jsonLoad

from lib.orchestration_lib import setup_terminal, get_logger, resolve_vault_and_workspace, resolve_active_workspaces

setup_terminal()

# --- Sovereignty Engine Integration ---
try:
    from lib.sovereignty import Sovereignty
except ImportError:
    try:
        from sovereignty import Sovereignty
    except ImportError:
        Sovereignty = None


# -----------------------------------------------------------------------------------------------

class FleetCommander:
    Name: str = "FleetCommander"

    def __init__(
        self,
        base_path: str,
        config: Optional[object] = None,
        logger: Optional[object] = None,
        dry_run: bool = False,
        target_repo: Optional[str] = None,
        is_fleet: bool = False,
        commit_msg: Optional[str] = None,
        tag: Optional[str] = None,
    ) -> None:
        self.config = config
        self.logger = logger or get_logger(self.Name)
        self.base_path: str = base_path
        self.dry_run: bool = dry_run
        self.engine = Sovereignty(workspace_root=Path(self.base_path)) if Sovereignty else None
        self.excluded_repos = set()

        vault_root, workspace_root = resolve_vault_and_workspace(__file__)
        self.vault_root = vault_root
        self.workspace_root = workspace_root

        self.inventory_path = self.vault_root / "05-Fleet-Operation" / "00-Repo-Control" / "inventory.json"
        self.repo_name_to_path: Dict[str, str] = {}
        all_repos = self._load_inventory()

        if target_repo:
            if target_repo.lower() in ["active", "active-workspaces", "workspaces"]:
                active_names = self._resolve_active_workspaces()
                self.repos = [
                    p for name, p in self.repo_name_to_path.items()
                    if name in active_names or Path(p).name in active_names
                ]
                self.single_mode = False
            else:
                resolved_path = self.repo_name_to_path.get(target_repo, target_repo)
                self.repos = [resolved_path]
                self.single_mode = True
        elif is_fleet:
            self.repos = all_repos
            self.single_mode = False
        else:
            # Default to active workspaces when neither --fleet nor --repo is explicitly passed
            active_names = self._resolve_active_workspaces()
            matched = [
                p for name, p in self.repo_name_to_path.items()
                if name in active_names or Path(p).name in active_names
            ]
            self.repos = matched if matched else all_repos
            self.single_mode = False

        self.commit_msg: str = commit_msg or "chore(fleet): standardized fleet operation"
        self.tag: Optional[str] = tag

    # -----------------------------------------------------------------------------------------------

    def _load_inventory(self) -> List[str]:
        """Loads repository paths from inventory.json and populates compliance exclusions."""
        if not self.inventory_path.exists():
            self._log(f"Inventory not found at {self.inventory_path}", "error")
            return []

        try:
            with open(self.inventory_path, "r", encoding="utf-8") as f:
                data = jsonLoad(f)
                repos = []
                for repo in data.get("repositories", []):
                    repo_path = repo.get("path", "")
                    if repo_path.startswith("./"):
                        repo_path = repo_path[2:]
                    repos.append(repo_path)

                    repo_name = repo.get("name", "")
                    if repo_name:
                        self.repo_name_to_path[repo_name] = repo_path

                    if repo.get("exclude_from_compliance", False):
                        self.excluded_repos.add(repo_path)
                        self.excluded_repos.add(repo_name)
                return repos
        except Exception as e:
            self._log(f"Failed to load inventory: {e}", "error")
            return []

    # -----------------------------------------------------------------------------------------------

    def _resolve_active_workspaces(self) -> set:
        return resolve_active_workspaces(Path(self.workspace_root))

    # -----------------------------------------------------------------------------------------------

    def _log(self, message: str, level: str = "info") -> None:
        if hasattr(self.logger, level):
            getattr(self.logger, level)(message)
        else:
            self.logger.info(message)

    def _step(self, repo: str, action: str) -> None:
        print(f"    {repo.ljust(35)} | {action}...")

    def _run_command(self, cmd: str, cwd: str) -> Tuple[str, Optional[str]]:
        try:
            cmd_list = cmd.split() if isinstance(cmd, str) else cmd
            result = subprocess.run(
                cmd_list, cwd=cwd, shell=False,
                capture_output=True, text=True, check=True
            )
            return result.stdout.strip(), None
        except subprocess.CalledProcessError as e:
            return e.stdout.strip() or "No stdout", e.stderr.strip() or "No stderr"

    # -----------------------------------------------------------------------------------------------
    # COMPLIANCE AUDITS
    # -----------------------------------------------------------------------------------------------

    def audit_docs(self, repo_path: Path, repo_name: str) -> bool:
        if not self.engine:
            return True
        self._step(repo_name, "Auditing documentation")
        mandatory_files = ["AI-Init.md", "AI-Project-DNA.md", "AI-Session-State.md", "TODO.md", "README.md"]
        success = True

        for filename in mandatory_files:
            file_path = repo_path / filename
            if not file_path.exists():
                self._log(f"[{repo_name}] Missing mandatory file: {filename}", "error")
                success = False
            else:
                self.engine.audit_file(file_path)

        report = self.engine.get_report()
        if report.get("errors"):
            for err in report["errors"]:
                self._log(f"[{repo_name}] {err}", "error")
            success = False

        return success

    def audit_isolation_zone(self, repo_path: Path, repo_name: str) -> bool:
        if not self.engine:
            return True
        self._step(repo_name, "Auditing isolation zone compliance")
        return self.engine.validate_isolation_zone(repo_path, repo_name)

    def validate_architecture(self, repo_path: Path, repo_name: str) -> bool:
        self._step(repo_name, "Validating fleet architecture rules")
        workflow_dir = repo_path / ".github" / "workflows"
        if not workflow_dir.exists():
            self._log(f"[{repo_name}] No GitHub workflows found.", "warning")
            return True

        for wf in workflow_dir.glob("*.yml"):
            try:
                with open(wf, "r", encoding="utf-8") as f:
                    content = f.read()
                    if "[FLEET-ARCHITECT]" not in content:
                        self._log(f"[{repo_name}] Workflow {wf.name} missing [FLEET-ARCHITECT] header.", "error")
                        return False
                    if "Sync-ID:" not in content:
                        self._log(f"[{repo_name}] Workflow {wf.name} missing Sync-ID.", "error")
                        return False
            except Exception:
                pass
        return True

    # -----------------------------------------------------------------------------------------------
    # COMMAND 1: STATUS
    # -----------------------------------------------------------------------------------------------

    def execute_fleet_status(self) -> None:
        """Audits git status, active branch, and working tree purity across repos."""
        print("\n" + "=" * 80)
        print(f"  {'Repository':<30} | {'Branch':<15} | {'Status':<10} | {'Clean':<6}")
        print("=" * 80)

        for repo in self.repos:
            repo_path_str = os.path.join(self.base_path, repo)
            repo_path = Path(repo_path_str)
            repo_name = repo_path.name

            if not repo_path.exists():
                print(f"  {repo_name:<30} | {'N/A':<15} | {'MISSING':<10} | ❌")
                continue

            if not (repo_path / ".git").exists():
                print(f"  {repo_name:<30} | {'N/A':<15} | {'NO GIT':<10} | ❌")
                continue

            # Detect branch
            branch, err = self._run_command("git branch --show-current", repo_path_str)
            if not branch or err:
                branch, _ = self._run_command("git rev-parse --abbrev-ref HEAD", repo_path_str)

            # Detect dirty state
            status_out, _ = self._run_command("git status --porcelain", repo_path_str)
            is_clean = not bool(status_out.strip())
            clean_str = "✅" if is_clean else "❌"
            status_str = "OK" if branch == "develop" else "DRIFT"

            print(f"  {repo_name:<30} | {branch:<15} | {status_str:<10} | {clean_str}")

        print("=" * 80 + "\n")

    # -----------------------------------------------------------------------------------------------
    # COMMAND 2: SYNC
    # -----------------------------------------------------------------------------------------------

    def execute_fleet_sync(self) -> None:
        """Pulls latest changes on develop branch and pushes if ahead, strictly skipping dirty repos."""
        self._log("🚀 Starting Fleet Synchronization...", "info")
        results = []

        for repo in self.repos:
            repo_path_str = os.path.join(self.base_path, repo)
            repo_path = Path(repo_path_str)
            name = repo_path.name

            if not repo_path.exists() or not (repo_path / ".git").exists():
                results.append(f"{name}: [SKIP] Not a local git repository")
                continue

            status_out, _ = self._run_command("git status --porcelain", repo_path_str)
            if status_out.strip():
                self._log(f"[{name}] Has uncommitted changes. Skipping sync to protect work.", "warning")
                results.append(f"{name}: [DIRTY] Skipped (work preserved)")
                continue

            # Pull latest develop
            self._step(name, "Pulling origin develop")
            out, err = self._run_command("git pull --rebase origin develop", repo_path_str)
            if err and "error" in err.lower():
                self._log(f"[{name}] Pull failed: {err}", "error")
                results.append(f"{name}: [ERROR] Pull failed")
                continue

            # Check if ahead of remote
            ahead_out, _ = self._run_command("git rev-list --left-right --count origin/develop...HEAD", repo_path_str)
            parts = ahead_out.split()
            ahead = int(parts[1]) if len(parts) == 2 else 0

            if ahead > 0 and not self.dry_run:
                self._step(name, f"Pushing {ahead} commit(s)")
                out, push_err = self._run_command("git push origin develop", repo_path_str)
                if push_err and "error" in push_err.lower():
                    results.append(f"{name}: [ERROR] Push failed")
                else:
                    results.append(f"{name}: [SYNCED] Pushed {ahead} commit(s)")
            else:
                results.append(f"{name}: [UP-TO-DATE]")

        print("\n" + "=" * 80)
        self._log("FLEET SYNC SUMMARY", "info")
        print("=" * 80)
        for r in results:
            print(f"  {r}")
        print("=" * 80 + "\n")

    # -----------------------------------------------------------------------------------------------
    # COMMAND 3: VAULT-SYNC
    # -----------------------------------------------------------------------------------------------

    def execute_vault_sync(self, commit_msg: Optional[str] = None) -> None:
        """Performs atomic synchronization across all obsidian-brain submodules and parent pointer."""
        msg = commit_msg or self.commit_msg or "chore(vault): atomic sync via Fleet Commander"
        obsidian_dir = self.workspace_root / "obsidian-brain"

        if not obsidian_dir.exists():
            self._log(f"obsidian-brain not found at {obsidian_dir}", "error")
            return

        self._log("🚀 Starting Atomic Vault Sync across submodules...", "info")

        submodules = [d for d in obsidian_dir.iterdir() if d.is_dir() and (d / ".git").exists()]
        for sub in submodules:
            name = sub.name
            sub_path = str(sub)

            status_out, _ = self._run_command("git status --porcelain", sub_path)
            if status_out.strip() and not self.dry_run:
                self._log(f"[{name}] Committing local submodule changes...", "info")
                self._run_command("git add .", sub_path)
                self._run_command(f'git commit -m "{msg}"', sub_path)

            self._log(f"[{name}] Pulling latest develop...", "info")
            self._run_command("git pull --rebase origin develop", sub_path)

            # Check if ahead
            ab_out, _ = self._run_command("git rev-list --left-right --count origin/develop...HEAD", sub_path)
            parts = ab_out.split()
            ahead = int(parts[1]) if len(parts) == 2 else 0

            if ahead > 0 and not self.dry_run:
                self._log(f"[{name}] Pushing {ahead} commit(s) to origin develop...", "info")
                _, err = self._run_command("git push origin develop", sub_path)
                if err and "error" in err.lower():
                    self._log(f"[{name}] PUSH FAILED: {err}", "error")
                else:
                    self._log(f"[{name}] SYNCED.", "info")
            else:
                self._log(f"[{name}] UP-TO-DATE.", "info")

        # Update parent pointer
        obsidian_path = str(obsidian_dir)
        self._log("[ obsidian-brain ] Updating submodule pointers...", "info")
        if not self.dry_run:
            self._run_command("git add .", obsidian_path)
            status, _ = self._run_command("git status --porcelain", obsidian_path)
            if status.strip():
                self._run_command('git commit -m "chore(fleet): update submodule pointers"', obsidian_path)

            ab_out, _ = self._run_command("git rev-list --left-right --count origin/develop...HEAD", obsidian_path)
            parts = ab_out.split()
            ahead = int(parts[1]) if len(parts) == 2 else 0

            if ahead > 0:
                self._log(f"[ obsidian-brain ] Pushing {ahead} commit(s) to origin...", "info")
                _, err = self._run_command("git push origin develop", obsidian_path)
                if err and "error" in err.lower():
                    self._log(f"❌ Vault push failed: {err}", "error")
                else:
                    self._log("✨ Atomic Vault Sync Complete!", "info")
            else:
                self._log("✨ Vault is already up-to-date.", "info")

    # -----------------------------------------------------------------------------------------------
    # COMMAND 4: PUSH (With Full Compliance Audits)
    # -----------------------------------------------------------------------------------------------

    def execute_fleet_push(self) -> None:
        """Main execution loop for mass git operations with Sovereignty compliance audits."""
        mode_str = " (DRY RUN MODE)" if self.dry_run else ""
        scope_str = "Single Repo" if self.single_mode else "Mass Push"
        self._log(f"Starting {scope_str} Operation{mode_str} ---", "info")

        # Automatically trigger housekeeping
        try:
            log_archiver = self.vault_root / "05-Fleet-Operation" / "02-Deployment-Logs" / "archive.py"
            if log_archiver.exists():
                self._run_command(f"python3 {log_archiver}", self.base_path)

            plan_archiver = self.vault_root / "05-Fleet-Operation" / "01-Fleet-Action-Plans" / "archive.py"
            if plan_archiver.exists():
                self._run_command(f"python3 {plan_archiver}", self.base_path)
        except Exception:
            pass

        git_ver, err = self._run_command("git --version", self.base_path)
        if err:
            self._log(f"Git not found! {err}", "error")
            return

        results: List[str] = []

        for repo in self.repos:
            repo_path_str = os.path.join(self.base_path, repo)
            repo_path = Path(repo_path_str)
            name = repo_path.name
            self._log(f"Processing repository: {repo}", "info")

            if not repo_path.exists():
                results.append(f"{name}: [SKIP] Path does not exist")
                continue

            if not (repo_path / ".git").exists():
                results.append(f"{name}: [SKIP] Not a git repository")
                continue

            # Branch check
            self._step(name, "Detecting branch")
            branch, err = self._run_command("git rev-parse --abbrev-ref HEAD", repo_path_str)
            if err or branch == "HEAD":
                branch, err = self._run_command("git branch --show-current", repo_path_str)
                if not branch or branch == "HEAD":
                    self._log(f"[{name}] Detached HEAD. Push blocked.", "error")
                    results.append(f"{name}: [ERROR] Detached HEAD")
                    continue

            self._step(name, f"Active branch: {branch}")
            if branch != "develop":
                self._log(f"[{name}] Not on 'develop' branch. Push blocked.", "error")
                results.append(f"{name}: [ERROR] Not on develop branch")
                continue

            # Compliance Audits
            is_excluded = repo in self.excluded_repos or name in self.excluded_repos
            if is_excluded:
                self._log(f"[{name}] Skipping compliance audits (Knowledge-Base).", "info")
            else:
                docs_ok = self.audit_docs(repo_path, name)
                arch_ok = self.validate_architecture(repo_path, name)
                iso_ok = self.audit_isolation_zone(repo_path, name)

                if not (docs_ok and arch_ok and iso_ok):
                    self._log(f"[{name}] Failed compliance audits. Skipping push.", "error")
                    results.append(f"{name}: [ERROR] Compliance failed (QUARANTINED)")
                    continue

            # Stage changes
            self._step(name, "Staging changes")
            self._run_command("git add .", repo_path_str)

            # Check status
            status, _ = self._run_command("git status --porcelain", repo_path_str)
            has_changes = bool(status.strip())

            commit_ok = True
            if has_changes and not self.dry_run:
                self._step(name, f"Committing changes: {self.commit_msg[:30]}...")
                _, commit_err = self._run_command(f'git commit -m "{self.commit_msg}"', repo_path_str)
                if commit_err and "error" in commit_err.lower():
                    self._log(f"[{name}] Commit failed: {commit_err}", "error")
                    results.append(f"{name}: [ERROR] Commit failed")
                    commit_ok = False

                if commit_ok:
                    self._step(name, f"Pushing to origin {branch}")
                    _, push_err = self._run_command(f"git push origin {branch}", repo_path_str)
                    if push_err and "error" in push_err.lower():
                        self._log(f"[{name}] Push failed: {push_err}", "error")
                        results.append(f"{name}: [ERROR] Push failed")
                        commit_ok = False
            elif has_changes and self.dry_run:
                self._step(name, "[DRY RUN] Would commit and push changes")

            if commit_ok:
                if self.tag and not self.dry_run:
                    self._step(name, f"Tagging with {self.tag}")
                    self._run_command(f'git tag -a {self.tag} -m "Release version {self.tag}"', repo_path_str)
                    self._run_command(f"git push origin {self.tag}", repo_path_str)
                    results.append(f"{name}: [SUCCESS] Pushed changes & tag {self.tag}")
                else:
                    if has_changes:
                        results.append(f"{name}: [SUCCESS] Pushed to {branch}")
                    else:
                        results.append(f"{name}: [OK] No changes")

        print("\n" + "=" * 80)
        self._log("FINAL FLEET SUMMARY", "info")
        print("=" * 80)
        for res in results:
            print(f"  {res}")
        print("=" * 80 + "\n")


# -----------------------------------------------------------------------------------------------
# CLI DISPATCHER
# -----------------------------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="FleetCommander - Unified Fleet Git & Compliance Operations")
    parser.add_argument(
        "action",
        nargs="?",
        default="status",
        choices=["status", "sync", "vault-sync", "push"],
        help="Action to perform: status, sync, vault-sync, push (default: status)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Simulate operations without making changes")
    parser.add_argument("--repo", "-r", type=str, help="Target a specific repository (or 'active' for workspace repos)")
    parser.add_argument("--fleet", action="store_true", help="Explicitly target the entire fleet")
    parser.add_argument("--message", "-m", type=str, help="Commit message")
    parser.add_argument("--tag", "-t", type=str, help="Attach a Git tag to the commit and push it")

    args = parser.parse_args()

    vault_root, workspace_root = resolve_vault_and_workspace(__file__)
    base_dir = str(workspace_root)

    commander = FleetCommander(
        base_dir,
        dry_run=args.dry_run,
        target_repo=args.repo,
        is_fleet=args.fleet,
        commit_msg=args.message,
        tag=args.tag,
    )

    if args.action == "status":
        commander.execute_fleet_status()
    elif args.action == "sync":
        commander.execute_fleet_sync()
    elif args.action == "vault-sync":
        commander.execute_vault_sync(commit_msg=args.message)
    elif args.action == "push":
        commander.execute_fleet_push()


if __name__ == "__main__":
    main()
