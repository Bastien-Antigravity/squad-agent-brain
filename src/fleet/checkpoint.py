#!/usr/bin/env python
# coding:utf-8

"""
===============================================================================================
ESSENTIAL PROCESS:
Squad Checkpoint Manager - Deterministic Git Restore Point Protocol.
Native first-class engine room orchestrator in 08-Squad-Agent.

DATA FLOW:
1. Creates an annotated Git tag and records pre-task state before starting new features or refactors.
2. Tracks active restore points, diffs, and multi-repo state in .squad_checkpoint.json.
3. Provides a reliable one-command rollback facility (or final release/promotion upon test pass).

KEY PARAMETERS:
- action: 'create', 'status', 'rollback', 'release'.
- topic: Identifier for the feature, bugfix, or task.
- repo: Optional target repository (auto-detected if omitted).
- commit_msg: Commit message when releasing/promoting the completed task.
- force: Overwrite active checkpoint or force rollback.
===============================================================================================
"""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from subprocess import run as subprocessRun
from typing import Dict, List, Optional, Tuple, Any

try:
    from src.lib.orchestration_lib import (
        setup_terminal,
        resolve_vault_and_workspace,
        resolve_active_workspaces,
        get_logger,
    )
except ImportError:
    from lib.orchestration_lib import (
        setup_terminal,
        resolve_vault_and_workspace,
        resolve_active_workspaces,
        get_logger,
    )

logger = get_logger("SquadCheckpoint")
setup_terminal()

# ---------------------------------------------------------------------------------------------
# CONSTANTS & METADATA
# ---------------------------------------------------------------------------------------------
CHECKPOINT_FILENAME = ".squad_checkpoint.json"

# ---------------------------------------------------------------------------------------------
# HELPER FUNCTIONS
# ---------------------------------------------------------------------------------------------
def run_git_cmd(args: List[str], cwd: Path) -> Tuple[int, str, str]:
    """Executes a git command in the specified directory and returns (code, stdout, stderr)."""
    try:
        res = subprocessRun(
            ["git"] + args,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=False,
        )
        return res.returncode, res.stdout.strip(), res.stderr.strip()
    except Exception as e:
        return 1, "", str(e)


def is_git_repo(path: Path) -> bool:
    """Verifies whether a directory belongs to a git working tree."""
    if not path.exists() or not path.is_dir():
        return False
    code, _, _ = run_git_cmd(["rev-parse", "--is-inside-work-tree"], path)
    return code == 0


def get_git_root(path: Path) -> Optional[Path]:
    """Finds the root directory of the git repository containing path."""
    code, stdout, _ = run_git_cmd(["rev-parse", "--show-toplevel"], path)
    if code == 0 and stdout:
        return Path(stdout).resolve()
    return None


def get_checkpoint_file(workspace_root: Path, vault_root: Path) -> Path:
    """Returns the primary path for .squad_checkpoint.json."""
    return workspace_root / CHECKPOINT_FILENAME


def load_active_checkpoint(workspace_root: Path, vault_root: Path) -> Optional[Dict[str, Any]]:
    """Loads existing checkpoint metadata if present."""
    ckpt_path = get_checkpoint_file(workspace_root, vault_root)
    if not ckpt_path.exists():
        fallback = vault_root / CHECKPOINT_FILENAME
        if fallback.exists():
            ckpt_path = fallback
        else:
            return None
    try:
        with open(ckpt_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Failed to read existing checkpoint file: {e}")
        return None


def save_checkpoint(workspace_root: Path, vault_root: Path, data: Dict[str, Any]) -> bool:
    """Saves checkpoint metadata to .squad_checkpoint.json."""
    ckpt_path = get_checkpoint_file(workspace_root, vault_root)
    try:
        with open(ckpt_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Failed to write checkpoint file {ckpt_path}: {e}")
        return False


def remove_checkpoint_file(workspace_root: Path, vault_root: Path) -> None:
    """Removes the checkpoint metadata file."""
    for root in (workspace_root, vault_root):
        ckpt_path = root / CHECKPOINT_FILENAME
        if ckpt_path.exists():
            try:
                ckpt_path.unlink()
            except Exception as e:
                logger.warning(f"Could not remove {ckpt_path}: {e}")


def resolve_target_repos(
    vault_root: Path,
    workspace_root: Path,
    requested_repo: Optional[str] = None,
    is_fleet: bool = False,
) -> List[Path]:
    """
    Resolves the set of Git repositories targeted by this checkpoint operation:
    1. If requested_repo is given, matches repository by name or path.
    2. If is_fleet is True, discovers all git repositories inside workspace_root.
    3. If inside a specific git repo (cwd), targets that repo.
    4. Otherwise discovers repositories with uncommitted modifications.
    5. Fallback: vault_root (obsidian-brain).
    """
    workspace_root = workspace_root.resolve()
    vault_root = vault_root.resolve()

    # 1. Explicit target repo requested
    if requested_repo:
        candidate = Path(requested_repo).resolve()
        if is_git_repo(candidate):
            return [candidate]
        sibling = workspace_root / requested_repo
        if is_git_repo(sibling):
            return [sibling]
        in_vault = vault_root / requested_repo
        if is_git_repo(in_vault):
            return [in_vault]
        logger.error(f"Specified repository '{requested_repo}' is not a valid git repository.")
        return []

    # 2. Entire fleet requested
    if is_fleet:
        repos: List[Path] = []
        for item in workspace_root.iterdir():
            if item.is_dir() and is_git_repo(item):
                repos.append(item.resolve())
        if is_git_repo(vault_root) and vault_root not in repos:
            repos.append(vault_root)
        return sorted(repos, key=lambda p: p.name)

    # 3. Check current working directory
    cwd = Path.cwd().resolve()
    cwd_root = get_git_root(cwd)
    if cwd_root and cwd_root != workspace_root:
        return [cwd_root]

    # 4. Check for modified repositories across workspace
    dirty_repos: List[Path] = []
    for item in workspace_root.iterdir():
        if item.is_dir() and is_git_repo(item):
            code, status_out, _ = run_git_cmd(["status", "--porcelain"], item)
            if code == 0 and status_out:
                dirty_repos.append(item.resolve())

    if dirty_repos:
        return sorted(dirty_repos, key=lambda p: p.name)

    # 5. Default fallback to vault_root
    if is_git_repo(vault_root):
        return [vault_root]

    return []

# ---------------------------------------------------------------------------------------------
# COMMAND IMPLEMENTATIONS
# ---------------------------------------------------------------------------------------------
def cmd_create(args: argparse.Namespace, vault_root: Path, workspace_root: Path) -> int:
    """Creates a new pre-task restore point tag and records state."""
    topic = args.topic
    if not topic:
        logger.error("A --topic name is required to create a checkpoint (e.g. --topic 'wiretap-parity').")
        return 1

    clean_topic = re.sub(r"[^a-zA-Z0-9_\-]", "-", topic).strip("-").lower()
    if not clean_topic:
        clean_topic = "task"

    # Check for existing active checkpoint
    existing = load_active_checkpoint(workspace_root, vault_root)
    if existing and not args.force:
        logger.warning(
            f"⚠️ An active checkpoint already exists for topic: '{existing.get('topic')}' "
            f"(tag: {existing.get('tag')}).\n"
            "   Use 'checkpoint status' to inspect, 'checkpoint rollback' to revert, "
            "or 'checkpoint create --force' to overwrite."
        )
        return 1

    target_repos = resolve_target_repos(vault_root, workspace_root, args.repo, args.fleet)
    if not target_repos:
        logger.error("No valid Git repositories found to checkpoint.")
        return 1

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    tag_name = f"restore-point/{clean_topic}-{ts}"

    repo_entries: List[Dict[str, Any]] = []

    logger.info(f"Establishing restore point '{tag_name}' across {len(target_repos)} repo(s)...")

    for repo in target_repos:
        # Check if working tree has uncommitted modifications
        code, status_out, _ = run_git_cmd(["status", "--porcelain"], repo)
        wip_committed = False

        if status_out:
            logger.info(f"   [{repo.name}] Dirty working tree detected — snapshotting WIP commit...")
            run_git_cmd(["add", "."], repo)
            c_code, _, c_err = run_git_cmd(
                ["commit", "-m", f"chore(checkpoint): pre-task WIP snapshot for '{clean_topic}'"],
                repo,
            )
            if c_code == 0:
                wip_committed = True
            else:
                logger.warning(f"   [{repo.name}] Could not create WIP commit: {c_err}")

        # Get HEAD commit hash
        _, head_hash, _ = run_git_cmd(["rev-parse", "HEAD"], repo)

        # Create annotated Git tag
        tag_msg = f"Restore point: {clean_topic} at {ts}"
        t_code, _, t_err = run_git_cmd(["tag", "-a", tag_name, "-m", tag_msg], repo)
        if t_code != 0:
            logger.error(f"   [{repo.name}] Failed to create tag '{tag_name}': {t_err}")
            return 1

        repo_entries.append({
            "repo_name": repo.name,
            "repo_path": str(repo.resolve()),
            "commit": head_hash,
            "wip_committed": wip_committed,
        })
        logger.info(f"   ✅ [{repo.name}] Tagged HEAD ({head_hash[:8]}) -> {tag_name}")

    checkpoint_data: Dict[str, Any] = {
        "topic": clean_topic,
        "tag": tag_name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "repos": repo_entries,
    }

    if not save_checkpoint(workspace_root, vault_root, checkpoint_data):
        return 1

    logger.info("=" * 77)
    logger.info(f"🏁 SQUAD CHECKPOINT ESTABLISHED: {tag_name}")
    logger.info("=" * 77)
    logger.info(f"Topic:        {clean_topic}")
    logger.info(f"Tag:          {tag_name}")
    logger.info(f"Timestamp:    {ts}")
    logger.info("Repositories:")
    for entry in repo_entries:
        wip_note = " (WIP committed)" if entry["wip_committed"] else " (clean)"
        logger.info(f"  • {entry['repo_name']} @ {entry['commit'][:8]}{wip_note}")
    logger.info("-" * 77)
    logger.info("💡 GUIDANCE FOR SQUAD & AI ASSISTANTS:")
    logger.info("  • Inspect diff:      python3 08-Squad-Agent/main.py checkpoint status")
    logger.info("  • Roll back anytime: python3 08-Squad-Agent/main.py checkpoint rollback")
    logger.info("  • Finish & commit:   python3 08-Squad-Agent/main.py checkpoint release -m \"feat(...)\"")
    logger.info("=" * 77)

    return 0


def cmd_status(args: argparse.Namespace, vault_root: Path, workspace_root: Path) -> int:
    """Displays the status and diff of the active restore point."""
    ckpt = load_active_checkpoint(workspace_root, vault_root)
    if not ckpt:
        logger.info("ℹ️ No active squad restore point found.")
        logger.info("   Create one before starting work: python3 08-Squad-Agent/main.py checkpoint create --topic <name>")
        return 0

    tag = ckpt.get("tag", "unknown")
    topic = ckpt.get("topic", "unknown")
    created_at = ckpt.get("created_at", "unknown")
    repos = ckpt.get("repos", [])

    logger.info("=" * 77)
    logger.info(f"🔍 ACTIVE SQUAD CHECKPOINT: {tag}")
    logger.info("=" * 77)
    logger.info(f"Topic:      {topic}")
    logger.info(f"Created At: {created_at}")
    logger.info("-" * 77)

    for entry in repos:
        repo_path = Path(entry["repo_path"])
        repo_name = entry["repo_name"]
        base_commit = entry["commit"]

        logger.info(f"📂 Repository: {repo_name} ({repo_path})")
        logger.info(f"   Restore Point Base: {base_commit[:8]} ({tag})")

        if not repo_path.exists():
            logger.warning("   ⚠️ Path not found on disk.")
            continue

        # Current HEAD
        _, current_head, _ = run_git_cmd(["rev-parse", "HEAD"], repo_path)
        logger.info(f"   Current HEAD:       {current_head[:8]}")

        # Diff against tag
        _, diff_stat, _ = run_git_cmd(["diff", "--stat", f"{tag}..HEAD"], repo_path)
        if diff_stat:
            logger.info("   Committed changes since restore point:")
            for line in diff_stat.splitlines():
                logger.info(f"     {line}")
        else:
            logger.info("   Committed changes since restore point: None (HEAD == tag)")

        # Uncommitted changes
        _, short_status, _ = run_git_cmd(["status", "--short"], repo_path)
        if short_status:
            logger.info("   Uncommitted working tree changes:")
            for line in short_status.splitlines():
                logger.info(f"     {line}")
        else:
            logger.info("   Working tree is clean.")

    logger.info("=" * 77)
    return 0


def cmd_rollback(args: argparse.Namespace, vault_root: Path, workspace_root: Path) -> int:
    """
    Rolls back the workspace to the active restore point tag.
    Note: Rollback is a reliable recovery facility for the AI/developer when a feature
    fails, does not do what was expected, or when starting clean is easier than patching.
    """
    ckpt = load_active_checkpoint(workspace_root, vault_root)
    if not ckpt:
        logger.error("❌ No active squad restore point found to roll back to.")
        return 1

    tag = ckpt.get("tag")
    topic = ckpt.get("topic")
    repos = ckpt.get("repos", [])

    logger.info(f"⏪ Rolling back to restore point '{tag}' for topic '{topic}'...")

    for entry in repos:
        repo_path = Path(entry["repo_path"])
        repo_name = entry["repo_name"]
        wip_committed = entry.get("wip_committed", False)

        if not repo_path.exists():
            logger.warning(f"   [{repo_name}] Repo path {repo_path} does not exist, skipping.")
            continue

        # Verify tag exists in repo
        code, _, _ = run_git_cmd(["rev-parse", "--verify", tag], repo_path)
        if code != 0:
            logger.error(f"   [{repo_name}] Tag '{tag}' not found in repository.")
            continue

        # Hard reset to tag
        r_code, _, r_err = run_git_cmd(["reset", "--hard", tag], repo_path)
        if r_code != 0:
            logger.error(f"   [{repo_name}] Hard reset failed: {r_err}")
            continue

        # Clean untracked files generated during the task
        if not args.keep_untracked:
            run_git_cmd(["clean", "-fd"], repo_path)

        # If we created a WIP commit at create-time, softly restore the dirty working state
        if wip_committed:
            run_git_cmd(["reset", "--mixed", "HEAD~1"], repo_path)
            logger.info(f"   [{repo_name}] Restored pre-task working modifications.")

        # Prune the temporary restore-point tag
        run_git_cmd(["tag", "-d", tag], repo_path)
        logger.info(f"   ✅ [{repo_name}] Successfully rolled back to pre-task state.")

    remove_checkpoint_file(workspace_root, vault_root)
    logger.info("🎉 Rollback completed. Workspace is clean and restored.")
    return 0


def cmd_release(args: argparse.Namespace, vault_root: Path, workspace_root: Path) -> int:
    """Finalizes and commits verified changes, pruning the temporary restore point tag."""
    ckpt = load_active_checkpoint(workspace_root, vault_root)
    if not ckpt:
        logger.error("❌ No active squad restore point found to release.")
        return 1

    commit_msg = args.commit_msg or args.message
    if not commit_msg:
        logger.error("A commit message is required for release (e.g. -m 'feat(wiretap): ...').")
        return 1

    tag = ckpt.get("tag")
    topic = ckpt.get("topic")
    repos = ckpt.get("repos", [])

    logger.info(f"🚀 Releasing topic '{topic}' with commit message: \"{commit_msg}\"...")

    for entry in repos:
        repo_path = Path(entry["repo_path"])
        repo_name = entry["repo_name"]

        if not repo_path.exists():
            continue

        # Stage all changes
        run_git_cmd(["add", "."], repo_path)

        # Check if changes exist to commit
        code, status_out, _ = run_git_cmd(["status", "--porcelain"], repo_path)
        if status_out:
            c_code, _, c_err = run_git_cmd(["commit", "-m", commit_msg], repo_path)
            if c_code == 0:
                logger.info(f"   ✅ [{repo_name}] Changes committed successfully.")
            else:
                logger.warning(f"   [{repo_name}] Git commit returned: {c_err}")
        else:
            logger.info(f"   [{repo_name}] Working tree clean, nothing new to commit.")

        # Prune temporary restore-point tag unless requested to keep
        if not args.keep_tag:
            d_code, _, _ = run_git_cmd(["tag", "-d", tag], repo_path)
            if d_code == 0:
                logger.info(f"   🗑️ [{repo_name}] Pruned temporary restore tag '{tag}'.")

    remove_checkpoint_file(workspace_root, vault_root)
    logger.info(f"🎉 Checkpoint released. Topic '{topic}' finalized successfully.")
    return 0

# ---------------------------------------------------------------------------------------------
# MAIN CLI ENTRYPOINT
# ---------------------------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Squad Checkpoint Manager - Deterministic Git Restore Point Protocol",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="action", help="Checkpoint action to perform")

    # 1. CREATE
    p_create = subparsers.add_parser("create", help="Create a new pre-task restore point tag")
    p_create.add_argument("--topic", "-t", required=True, help="Topic, feature, or bugfix name")
    p_create.add_argument("--repo", "-r", help="Specific repository folder name or path")
    p_create.add_argument("--fleet", action="store_true", help="Tag all fleet repositories in workspace")
    p_create.add_argument("--force", "-f", action="store_true", help="Overwrite existing active checkpoint")

    # 2. STATUS
    p_status = subparsers.add_parser("status", help="Show active restore point status and diff")

    # 3. ROLLBACK
    p_rollback = subparsers.add_parser("rollback", help="Roll back workspace to restore point tag")
    p_rollback.add_argument("--keep-untracked", action="store_true", help="Do not run git clean on untracked files")
    p_rollback.add_argument("--force", "-f", action="store_true", help="Force rollback without prompting")

    # 4. RELEASE
    p_release = subparsers.add_parser("release", help="Commit verified changes and prune restore point tag")
    p_release.add_argument("--commit-msg", "-m", dest="commit_msg", required=True, help="Semantic commit message")
    p_release.add_argument("--keep-tag", action="store_true", help="Keep the restore point tag instead of pruning it")

    args = parser.parse_args()

    if not args.action:
        parser.print_help()
        sys.exit(1)

    vault_root, workspace_root = resolve_vault_and_workspace(Path(__file__))

    if args.action == "create":
        code = cmd_create(args, vault_root, workspace_root)
    elif args.action == "status":
        code = cmd_status(args, vault_root, workspace_root)
    elif args.action == "rollback":
        code = cmd_rollback(args, vault_root, workspace_root)
    elif args.action == "release":
        code = cmd_release(args, vault_root, workspace_root)
    else:
        parser.print_help()
        code = 1

    sys.exit(code)


if __name__ == "__main__":
    main()