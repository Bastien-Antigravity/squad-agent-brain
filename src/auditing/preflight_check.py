#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Cross-platform Preflight Check that runs before every squad startup.
Detects and auto-repairs common drift issues across the brain ecosystem.

DATA FLOW:
1. Resolves the workspace root from the script location.
2. Checks submodule initialization status in obsidian-brain.
3. Validates mode consistency between AI-Session-State and MODE-MANUAL.
4. Warns about non-portable paths in inventory.json.
5. Returns a status report (GREEN / YELLOW / RED).

KEY PARAMETERS:
- WORKSPACE_ROOT: Automatically detected from the script's location.
- VAULT_DIR: The obsidian-brain directory.
"""

import os
import sys
from pathlib import Path

# Add src root and project root to sys.path to enable loading lib.* and src.* modules
_self_dir = Path(__file__).resolve().parent
_src_dir = _self_dir.parent
_project_dir = _src_dir.parent
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))
if str(_project_dir) not in sys.path:
    sys.path.insert(0, str(_project_dir))

from lib.bootstrap import ensure_virtualenv, prepend_venv_bin, ensure_import_paths

script_dir = _self_dir
vault_root = ensure_virtualenv(str(script_dir))
prepend_venv_bin(vault_root)

ensure_import_paths(script_dir, vault_root)

from sys import stdout as sysStdout, executable as sysExecutable
from os import name as osName
from os.path import exists as osPathExists, isdir as osPathIsdir, join as osPathJoin
from subprocess import run as subprocessRun, DEVNULL
from pathlib import Path
from re import search as reSearch
from typing import List, Tuple

from lib.orchestration_lib import setup_terminal, resolve_vault_and_workspace
setup_terminal()

VAULT_DIR, WORKSPACE_ROOT = resolve_vault_and_workspace(__file__)

# Submodule mapping: folder name inside vault -> sibling repo name
SUBMODULE_MAP = {
    "01-Strategic-Nexus": "nexus-strategic-brain",
    "02-Business-BDD": "business-bdd-brain",
    "03-Tech-Stack": "tech-stack-brain",
    "04-Rapid-Prototyping": "rapid-prototyping-brain",
    "05-Fleet-Operation": "fleet-operation-brain",
    "07-Core-KMS": "core-kms-brain",
    "09-RAG-Engine": "obsidian-rag-mcp",
    "10-Agent-Factory": "oop-agent-factory",
}

# -----------------------------------------------------------------------------------------------

def _check_submodules() -> Tuple[str, List[str]]:
    """
    Checks if obsidian-brain submodules are initialized.
    Auto-repairs by running 'git submodule update --init' if needed.
    Returns: (status, list_of_messages)
    """
    messages = []
    
    if not VAULT_DIR.exists():
        return "RED", ["obsidian-brain directory not found at {0}".format(VAULT_DIR)]
    
    gitmodules_path = VAULT_DIR / ".gitmodules"
    if not gitmodules_path.exists():
        return "GREEN", ["No .gitmodules found — skipping submodule check."]
    
    empty_submodules = []
    for folder_name, repo_name in SUBMODULE_MAP.items():
        submodule_path = VAULT_DIR / folder_name
        if submodule_path.exists() and osPathIsdir(str(submodule_path)):
            # Check if directory is empty (no files beyond .git)
            contents = list(submodule_path.iterdir())
            if len(contents) == 0:
                empty_submodules.append(folder_name)
            elif len(contents) == 1 and contents[0].name == ".git":
                empty_submodules.append(folder_name)
        elif not submodule_path.exists():
            empty_submodules.append(folder_name)
    
    if not empty_submodules:
        messages.append("All {0} submodules are initialized.".format(len(SUBMODULE_MAP)))
        return "GREEN", messages
    
    # Auto-repair: run git submodule update --init --recursive
    messages.append("{0} empty submodule(s) detected: {1}".format(
        len(empty_submodules), ", ".join(empty_submodules)))
    messages.append("Auto-repairing: running 'git submodule update --init --recursive'...")
    
    try:
        result = subprocessRun(
            ["git", "-C", str(VAULT_DIR), "submodule", "update", "--init", "--recursive"],
            capture_output=True, text=True, timeout=120
        )
        if result.returncode == 0:
            messages.append("Submodules initialized successfully.")
            return "YELLOW", messages
        else:
            messages.append("Submodule init failed: {0}".format(result.stderr.strip()))
            messages.append("TIP: You may need to run 'git -C obsidian-brain submodule sync' first if repo URLs changed.")
            return "RED", messages
    except Exception as e:
        messages.append("Submodule init error: {0}".format(e))
        return "RED", messages

# -----------------------------------------------------------------------------------------------

def _check_mode_consistency() -> Tuple[str, List[str]]:
    """
    Validates that AI-Session-State.md and MODE-MANUAL.md agree on the active mode.
    """
    messages = []
    
    session_state_path = VAULT_DIR / "00-AI-Orchestration" / "AI-Session-State.md"
    mode_manual_path = VAULT_DIR / "00-AI-Orchestration" / "Config" / "MODE-MANUAL.md"
    
    if not session_state_path.exists() or not mode_manual_path.exists():
        messages.append("Mode files not found — skipping consistency check.")
        return "YELLOW", messages
    
    # Read MODE-MANUAL active_mode
    manual_mode = None
    with open(mode_manual_path, "r", encoding="utf-8") as f:
        for line in f:
            match = reSearch(r"active_mode:\s*(\d+)", line)
            if match:
                manual_mode = match.group(1)
                break
    
    # Read AI-Session-State active-protocol
    session_mode = None
    with open(session_state_path, "r", encoding="utf-8") as f:
        for line in f:
            match = reSearch(r"active-protocol:\s*.*Mode[- ]?(\d+)", line)
            if match:
                session_mode = match.group(1)
                break
    
    if manual_mode is None:
        messages.append("Could not read active_mode from MODE-MANUAL.md")
        return "YELLOW", messages
    
    if session_mode is None:
        messages.append("Could not read active-protocol from AI-Session-State.md")
        return "YELLOW", messages
    
    if manual_mode == session_mode:
        messages.append("Mode consistent: Mode {0} in both files.".format(manual_mode))
        return "GREEN", messages
    else:
        messages.append("MODE MISMATCH: MODE-MANUAL says Mode {0}, Session-State says Mode {1}.".format(
            manual_mode, session_mode))
        messages.append("The AI-Session-State should be updated to match.")
        return "YELLOW", messages

# -----------------------------------------------------------------------------------------------

def _check_inventory_portability() -> Tuple[str, List[str]]:
    """
    Checks that inventory.json uses portable (relative) paths.
    """
    messages = []
    
    # Updated path to match submodule structure
    inventory_path = VAULT_DIR / "05-Fleet-Operation" / "00-Repo-Control" / "inventory.json"
    if not inventory_path.exists():
        messages.append("inventory.json not found — skipping portability check.")
        return "YELLOW", messages
    
    import json
    with open(inventory_path, "r", encoding="utf-8") as f:
        try:
            inventory = json.load(f)
        except Exception:
            messages.append("inventory.json is malformed.")
            return "RED", messages
    
    absolute_paths = []
    for repo in inventory.get("repositories", []):
        path = repo.get("path", "")
        if Path(path).is_absolute():
            absolute_paths.append(repo.get("name", "unknown"))
    
    if absolute_paths:
        messages.append("{0} repo(s) use absolute paths (not portable): {1}".format(
            len(absolute_paths), ", ".join(absolute_paths[:5])))
        messages.append("TIP: Run 'python fleet-manager.py discover' to regenerate with relative paths.")
        return "YELLOW", messages
    
    # Verify that docker-deployment modes link to this SSoT
    mode_links = ["local", "docker", "production"]
    broken_mode_links = []
    for mode in mode_links:
        ml_path = WORKSPACE_ROOT / "docker-deployment" / "modes" / mode / "inventory.json"
        if not ml_path.exists():
            broken_mode_links.append(f"modes/{mode}/inventory.json")
    if broken_mode_links:
        messages.append(f"Missing SSoT symlinks in docker-deployment: {', '.join(broken_mode_links)}")
        return "YELLOW", messages

    messages.append("All {0} inventory paths are portable (relative) and mode symlinks verified.".format(
        len(inventory.get("repositories", []))))
    return "GREEN", messages

# -----------------------------------------------------------------------------------------------

def _check_essential_files() -> Tuple[str, List[str]]:
    """
    Verifies that critical ecosystem files exist.
    """
    messages = []
    essential = [
        ("AI-Init.md", VAULT_DIR / "00-AI-Orchestration" / "AI-Init.md"),
        ("AI-Session-State.md", VAULT_DIR / "00-AI-Orchestration" / "AI-Session-State.md"),
        ("MODE-MANUAL.md", VAULT_DIR / "00-AI-Orchestration" / "Config" / "MODE-MANUAL.md"),
        ("Ecosystem-Map-MOC.md", VAULT_DIR / "Ecosystem-Map-MOC.md"),
        ("inventory.json", VAULT_DIR / "05-Fleet-Operation" / "00-Repo-Control" / "inventory.json"),
    ]
    
    missing = []
    for name, path in essential:
        if not path.exists():
            missing.append(name)
    
    if missing:
        messages.append("Missing essential files: {0}".format(", ".join(missing)))
        messages.append("Attempted vault path: {0}".format(VAULT_DIR))
        return "RED", messages
    
    messages.append("All {0} essential files present.".format(len(essential)))
    return "GREEN", messages

# -----------------------------------------------------------------------------------------------

def _check_spec_parity() -> Tuple[str, List[str]]:
    """
    Validates that BDD features specify repositories that actually exist in the workspace.
    """
    messages = []
    behavior_specs_dir = VAULT_DIR / "02-Business-BDD" / "02-Behavior-Specs"
    if not behavior_specs_dir.exists():
        messages.append("Behavior specs folder not found — skipping spec parity check.")
        return "YELLOW", messages
        
    missing_repos = set()
    total_checked = 0
    
    # Load core repositories from inventory.json to know what is expected in local workspace
    core_repos = set()
    inventory_path = VAULT_DIR / "05-Fleet-Operation" / "00-Repo-Control" / "inventory.json"
    if inventory_path.exists():
        import json
        try:
            with open(inventory_path, "r", encoding="utf-8") as f:
                inv_data = json.load(f)
                for r in inv_data.get("repositories", []):
                    if r.get("is_core"):
                        core_repos.add(r.get("name"))
        except Exception:
            pass

    for root, _, files in os.walk(str(behavior_specs_dir)):
        for file in files:
            if file.endswith(".md") and file != "TEMPLATE.md":
                filepath = osPathJoin(root, file)
                total_checked += 1
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        content = f.read()
                    if content.startswith("---"):
                        parts = content.split("---", 2)
                        if len(parts) >= 3:
                            frontmatter = parts[1]
                            repo_name = None
                            for line in frontmatter.splitlines():
                                if line.strip().startswith("repo:"):
                                    repo_name = line.split(":", 1)[1].strip()
                                    # Strip quotes if present
                                    repo_name = repo_name.strip("'\"")
                                    break
                            
                            if repo_name:
                                # Domain/external repos (is_core: false) are not required in base local clone
                                if core_repos and repo_name not in core_repos:
                                    continue
                                repo_dir = WORKSPACE_ROOT / repo_name
                                if not repo_dir.exists():
                                    missing_repos.add((file, repo_name))
                except Exception:
                    pass
                    
    if missing_repos:
        messages.append("Spec-Code drift: {0} specifications reference missing repositories:".format(len(missing_repos)))
        for spec_file, repo_name in sorted(list(missing_repos))[:5]:
            messages.append("  - '{0}' references missing repo '{1}'".format(spec_file, repo_name))
        if len(missing_repos) > 5:
            messages.append("  - ... and {0} more.".format(len(missing_repos) - 5))
        return "YELLOW", messages
        
    messages.append("All {0} feature specifications have matching workspace repositories.".format(total_checked))
    return "GREEN", messages

def _check_manifest_elements() -> Tuple[str, List[str]]:
    """
    Loads process-manifest.json and verifies that all registered associated files exist.
    """
    messages = []
    manifest_path = VAULT_DIR / "00-AI-Orchestration" / "Config" / "process-manifest.json"
    if not manifest_path.exists():
        messages.append("process-manifest.json not found.")
        return "RED", messages

    import json
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    except Exception as e:
        messages.append("Failed to load process-manifest.json: {0}".format(e))
        return "RED", messages

    missing_files = []
    total_checked = 0

    for category in ["processes", "agents", "concepts"]:
        elements = manifest.get(category, [])
        for element in elements:
            name = element.get("name")
            assoc_file = element.get("associated_file")
            if assoc_file:
                total_checked += 1
                full_path = VAULT_DIR / assoc_file
                if not full_path.exists():
                    missing_files.append("{0} ({1}): missing {2}".format(name, category, assoc_file))

    if missing_files:
        messages.append("Ecosystem drift: {0} manifest elements have missing files:".format(len(missing_files)))
        for err in missing_files:
            messages.append("  - {0}".format(err))
        return "RED", messages

    messages.append("All {0} manifest-registered files are present and verified.".format(total_checked))
    return "GREEN", messages

def _check_ports_and_capabilities() -> Tuple[str, List[str]]:
    """
    Checks that ports across native.yaml (SSoT), docker-compose.yaml, and service-registry.json
    are in 100% mechanical parity without drift.
    """
    try:
        from auditing.audit_ports import audit_ports
        return audit_ports(auto_sync=False)
    except Exception as e:
        return "RED", ["Port audit execution failed: {0}".format(e)]

# ### MAIN ###

def run_preflight(quiet: bool = False) -> bool:
    """
    Runs all preflight checks and prints a status report.
    Returns True if all checks passed (GREEN), False otherwise.
    """
    checks = [
        ("Essential Files", _check_essential_files),
        ("Submodule Status", _check_submodules),
        ("Mode Consistency", _check_mode_consistency),
        ("Inventory Portability", _check_inventory_portability),
        ("Spec-Code Parity", _check_spec_parity),
        ("Process Manifest Check", _check_manifest_elements),
        ("4-Layer Port Drift Check", _check_ports_and_capabilities),
    ]
    
    overall = "GREEN"
    results = []
    
    for check_name, check_fn in checks:
        status, messages = check_fn()
        results.append((check_name, status, messages))
        if status == "RED":
            overall = "RED"
        elif status == "YELLOW" and overall != "RED":
            overall = "YELLOW"
    
    # Print report
    if not quiet:
        status_icons = {"GREEN": "✅", "YELLOW": "⚠️", "RED": "❌"}
        
        print("\n" + "=" * 60)
        print("🛫 PREFLIGHT CHECK REPORT")
        print("=" * 60)
        
        for check_name, status, messages in results:
            icon = status_icons.get(status, "?")
            print("\n{0} {1}: {2}".format(icon, check_name, status))
            for msg in messages:
                print("    {0}".format(msg))
        
        print("\n" + "=" * 60)
        icon = status_icons.get(overall, "?")
        if overall == "GREEN":
            print("{0} PREFLIGHT: ALL CLEAR. Ready to launch.".format(icon))
        elif overall == "YELLOW":
            print("{0} PREFLIGHT: WARNINGS DETECTED. Review above.".format(icon))
        else:
            print("{0} PREFLIGHT: CRITICAL ISSUES. Fix before proceeding.".format(icon))
        print("=" * 60 + "\n")
    
    return overall == "GREEN"

# -----------------------------------------------------------------------------------------------

def main():
    run_preflight(quiet=False)


if __name__ == "__main__":
    main()
