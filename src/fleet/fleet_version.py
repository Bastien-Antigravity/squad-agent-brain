#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Fleet-wide dynamic semantic versioning manager for Bastien-Antigravity.
Audits, verifies, increments, and synchronizes VERSION.txt across all 14 workspaces
and ensures strict mechanical parity with AI-Project-DNA.md and Git release tags.

DATA FLOW:
1. Input: CLI action (status, bump, set, check), target repo (--repo or --all), bump type.
2. Logic: Resolves active repositories from inventory.json / workspace root.
   Inspects/updates VERSION.txt and AI-Project-DNA.md atomically.
   Optionally commits and creates annotated Git release tags.
3. Output: Colorized fleet version audit report and synchronization confirmation.

KEY PARAMETERS:
- --action: 'status' (default), 'bump', 'set', 'check'.
- --type: Semver bump type ('patch', 'minor', 'major'). Defaults to 'patch'.
- --set: Explicit semver string (e.g. '0.0.2', '0.0.1').
- --repo: Target a single repository (e.g. 'microservice-toolbox').
- --all: Target all repositories in the workspace inventory (default if --repo omitted).
- --git: Stage files, commit, and create Git tag for release.
- --dry-run: Preview updates without modifying disk or Git refs.
"""

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    from microservice_toolbox.utils.bootstrap import bootstrap_microservice
except ImportError:
    for parent in Path(__file__).resolve().parents:
        toolbox_py = parent / "microservice-toolbox" / "python"
        if toolbox_py.exists():
            sys.path.insert(0, str(toolbox_py))
            break
    from microservice_toolbox.utils.bootstrap import bootstrap_microservice

bootstrap_microservice(__file__, app_name="squad_agent_fleet_version")

from lib.orchestration_lib import (
    C_BOLD,
    C_CYAN,
    C_DIM,
    C_GREEN,
    C_RED,
    C_RESET,
    C_YELLOW,
    get_fleet_repositories,
    resolve_vault_and_workspace,
    setup_terminal,
)

SEMVER_REGEX = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?$")

# -----------------------------------------------------------------------------

def parse_semver(v_str: str) -> Tuple[int, int, int, str]:
    """Parses a semver string into (major, minor, patch, prerelease)."""
    clean_v = v_str.strip().lstrip("v")
    m = SEMVER_REGEX.match(clean_v)
    if not m:
        raise ValueError(f"Invalid semver: '{v_str}'")
    major, minor, patch = int(m.group(1)), int(m.group(2)), int(m.group(3))
    prerelease = m.group(4) or ""
    return major, minor, patch, prerelease

# -----------------------------------------------------------------------------

def increment_semver(current_v: str, bump_type: str = "patch") -> str:
    """Computes the next semver string based on bump type."""
    major, minor, patch, _ = parse_semver(current_v)
    b_type = bump_type.lower()
    if b_type == "major":
        return f"{major + 1}.0.0"
    elif b_type == "minor":
        return f"{major}.{minor + 1}.0"
    elif b_type == "patch":
        return f"{major}.{minor}.{patch + 1}"
    else:
        raise ValueError(f"Unknown bump type '{bump_type}'. Choose major, minor, or patch.")

# -----------------------------------------------------------------------------

def get_repo_git_tag(repo_dir: Path) -> str:
    """Returns the latest Git tag for the repository, or 'none'."""
    try:
        res = subprocess.run(
            ["git", "describe", "--tags", "--abbrev=0"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            check=False,
        )
        tag = res.stdout.strip()
        return tag if tag else "none"
    except Exception:
        return "none"

# -----------------------------------------------------------------------------

def inspect_repo_version(repo_dir: Path) -> Dict[str, Optional[str]]:
    """Inspects VERSION.txt and AI-Project-DNA.md within a repository directory."""
    result: Dict[str, Optional[str]] = {
        "version_txt": None,
        "dna_version": None,
        "git_tag": "none",
        "status": "OK",
    }

    # 1. VERSION.txt
    v_txt = repo_dir / "VERSION.txt"
    if v_txt.exists():
        try:
            val = v_txt.read_text(encoding="utf-8").strip()
            result["version_txt"] = val
        except Exception as e:
            result["status"] = f"ERR_READ_VERSION_TXT ({e})"
    else:
        result["status"] = "MISSING_VERSION_TXT"

    # 2. AI-Project-DNA.md
    dna_file = repo_dir / "AI-Project-DNA.md"
    if dna_file.exists():
        try:
            content = dna_file.read_text(encoding="utf-8")
            m = re.search(r"^-\s*Version:\s*([^\r\n]+)", content, re.MULTILINE)
            if m:
                result["dna_version"] = m.group(1).strip()
        except Exception:
            pass

    # 3. Git tag
    result["git_tag"] = get_repo_git_tag(repo_dir)

    # 4. Status determination
    if result["status"] == "OK":
        if result["version_txt"]:
            try:
                parse_semver(result["version_txt"])
            except ValueError:
                result["status"] = "INVALID_SEMVER"

        if result["dna_version"] and result["version_txt"]:
            if result["dna_version"] != result["version_txt"]:
                result["status"] = "DNA_DRIFT"

    return result

# -----------------------------------------------------------------------------

def update_repo_version(
    repo_dir: Path,
    new_version: str,
    dry_run: bool = False,
    git_commit: bool = False,
) -> bool:
    """Updates VERSION.txt and AI-Project-DNA.md to new_version and optionally commits/tags."""
    v_txt = repo_dir / "VERSION.txt"
    dna_file = repo_dir / "AI-Project-DNA.md"

    if dry_run:
        print(f"  {C_DIM}[DRY-RUN] Would update {v_txt} -> {new_version}{C_RESET}")
        if dna_file.exists():
            print(f"  {C_DIM}[DRY-RUN] Would update {dna_file} -> {new_version}{C_RESET}")
        return True

    # 1. Update VERSION.txt
    v_txt.write_text(f"{new_version}\n", encoding="utf-8")

    # 2. Update AI-Project-DNA.md if present
    if dna_file.exists():
        content = dna_file.read_text(encoding="utf-8")
        # Replace '- Version: ...'
        updated = re.sub(
            r"^(-\s*Version:\s*)([^\r\n]+)",
            rf"\g<1>{new_version}",
            content,
            flags=re.MULTILINE,
        )
        # Replace 'Semantic Versioning (v...)'
        updated = re.sub(
            r"(Semantic Versioning \(v)[^)]+(\))",
            rf"\g<1>{new_version}\g<2>",
            updated,
        )
        dna_file.write_text(updated, encoding="utf-8")

    # 3. Git commit & tag if requested
    if git_commit and (repo_dir / ".git").exists():
        try:
            subprocess.run(["git", "add", "VERSION.txt"], cwd=repo_dir, check=True)
            if dna_file.exists():
                subprocess.run(["git", "add", "AI-Project-DNA.md"], cwd=repo_dir, check=True)
            
            commit_msg = f"chore(release): bump version to v{new_version}"
            subprocess.run(["git", "commit", "-m", commit_msg], cwd=repo_dir, check=False)
            
            tag_name = f"v{new_version}"
            subprocess.run(
                ["git", "tag", "-a", tag_name, "-m", f"Release {tag_name}"],
                cwd=repo_dir,
                check=False,
            )
        except Exception as e:
            print(f"  {C_YELLOW}⚠️ Git commit/tag warning for {repo_dir.name}: {e}{C_RESET}")

    return True

# -----------------------------------------------------------------------------

def resolve_target_repos(vault_root: Path, workspace_root: Path, target_repo: Optional[str]) -> List[Tuple[str, Path]]:
    """Resolves target repositories to operate on."""
    targets: List[Tuple[str, Path]] = []
    
    if target_repo:
        # Single target repo
        p = (workspace_root / target_repo).resolve()
        if p.exists() and p.is_dir():
            targets.append((target_repo, p))
        elif target_repo == vault_root.name or (vault_root / target_repo).exists():
            targets.append((target_repo, vault_root))
        else:
            print(f"{C_RED}❌ Error: Target repository '{target_repo}' not found at {p}.{C_RESET}")
            sys.exit(1)
        return targets

    # All repositories in fleet
    repos = get_fleet_repositories(vault_root)
    seen = set()

    for r in repos:
        name = r.get("name")
        rel_path = r.get("path")
        if name and rel_path:
            abs_p = (workspace_root / rel_path).resolve()
            if abs_p.exists() and abs_p.is_dir() and name not in seen:
                targets.append((name, abs_p))
                seen.add(name)

    # Ensure obsidian-brain is included if not in inventory
    if vault_root.name not in seen and vault_root.exists():
        targets.append((vault_root.name, vault_root))
        seen.add(vault_root.name)

    # Fallback to inspecting all sibling folders with .git or VERSION.txt
    if not targets:
        for item in workspace_root.iterdir():
            if item.is_dir() and ((item / ".git").exists() or (item / "VERSION.txt").exists()):
                targets.append((item.name, item))

    return sorted(targets, key=lambda x: x[0])

# -----------------------------------------------------------------------------

def run_status_or_check(targets: List[Tuple[str, Path]], is_check: bool = False) -> bool:
    """Displays version audit status table. Returns True if all are coherent and valid."""
    setup_terminal()
    print("\n" + "=" * 90)
    print(f"📦 BASTIEN-ANTIGRAVITY: FLEET VERSION INTEGRITY REPORT")
    print("=" * 90)
    print(f"{'Repository':<28} {'VERSION.txt':<14} {'AI-Project-DNA':<16} {'Git Tag':<14} {'Status':<16}")
    print("-" * 90)

    all_ok = True

    for name, p in targets:
        info = inspect_repo_version(p)
        v_txt = info["version_txt"] or "-"
        v_dna = info["dna_version"] or "-"
        tag = info["git_tag"] or "-"
        status = info["status"]

        if status == "OK":
            status_display = f"{C_GREEN}✅ OK{C_RESET}"
        elif status == "DNA_DRIFT":
            status_display = f"{C_YELLOW}⚠️ DNA_DRIFT{C_RESET}"
            all_ok = False
        else:
            status_display = f"{C_RED}❌ {status}{C_RESET}"
            all_ok = False

        print(f"{name:<28} {v_txt:<14} {v_dna:<16} {tag:<14} {status_display}")

    print("=" * 90)
    if all_ok:
        print(f"{C_GREEN}🎉 All {len(targets)} repositories adhere to dynamic semver specifications!{C_RESET}\n")
    else:
        print(f"{C_YELLOW}⚠️ Discrepancies detected. Use 'fleet-version bump' or 'fleet-version set' to resolve.{C_RESET}\n")

    return all_ok

# -----------------------------------------------------------------------------

def main():
    setup_terminal()
    parser = argparse.ArgumentParser(
        description="Bastien-Antigravity Fleet Dynamic Semantic Versioning Engine"
    )
    parser.add_argument(
        "action",
        nargs="?",
        default="status",
        choices=["status", "bump", "set", "check"],
        help="Action to perform: status (report), bump (increment semver), set (explicit semver), check (verify)",
    )
    parser.add_argument(
        "--type",
        "-t",
        default="patch",
        choices=["patch", "minor", "major"],
        help="Semver bump type: patch (0.0.1 -> 0.0.2), minor (0.1.0), major (1.0.0)",
    )
    parser.add_argument(
        "--set",
        "-s",
        dest="set_version",
        help="Explicit semver value to set (e.g. 0.0.2 or 0.0.1)",
    )
    parser.add_argument(
        "--repo",
        "-r",
        help="Target single microservice repository (defaults to all fleet repositories)",
    )
    parser.add_argument(
        "--git",
        "-g",
        action="store_true",
        help="Automatically git commit and create annotated git release tag",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without modifying disk or git tags",
    )

    args = parser.parse_args()

    vault_root, workspace_root = resolve_vault_and_workspace(__file__)
    targets = resolve_target_repos(vault_root, workspace_root, args.repo)

    if args.action in ["status", "check"]:
        ok = run_status_or_check(targets, is_check=(args.action == "check"))
        if args.action == "check" and not ok:
            sys.exit(1)
        return

    # Bump or Set operation
    print("\n" + "=" * 80)
    mode_str = f"Setting explicit version '{args.set_version}'" if args.set_version else f"Bumping '{args.type}' semver"
    print(f"🚀 BASTIEN-ANTIGRAVITY: {mode_str} across {len(targets)} repositories")
    if args.dry_run:
        print(f"   Mode: {C_YELLOW}DRY-RUN (No files will be modified){C_RESET}")
    if args.git:
        print(f"   Git: {C_GREEN}Enabled (Auto-commit and tag){C_RESET}")
    print("=" * 80)

    success_count = 0

    for name, p in targets:
        curr_info = inspect_repo_version(p)
        curr_ver = curr_info["version_txt"] or "0.0.1"

        if args.set_version:
            new_ver = args.set_version.strip().lstrip("v")
            try:
                parse_semver(new_ver)
            except ValueError as e:
                print(f"{C_RED}❌ Invalid target semver: {e}{C_RESET}")
                sys.exit(1)
        else:
            try:
                new_ver = increment_semver(curr_ver, args.type)
            except Exception as e:
                print(f"{C_RED}❌ [{name}] Could not increment version from '{curr_ver}': {e}{C_RESET}")
                continue

        print(f"📦 [{name}] {curr_ver} -> {C_GREEN}{C_BOLD}{new_ver}{C_RESET}")
        ok = update_repo_version(p, new_ver, dry_run=args.dry_run, git_commit=args.git)
        if ok:
            success_count += 1

    print("=" * 80)
    print(f"🎉 Version operation finished: {success_count}/{len(targets)} repositories processed successfully.\n")

if __name__ == "__main__":
    main()
