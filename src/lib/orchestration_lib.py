#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Provides shared orchestration utility functions for path resolution, mode retrieval,
dynamic inventory querying, and structured logging.

DATA FLOW:
1. Locates parent folders to resolve vault and workspace directories.
2. Reads MODE-MANUAL.md to fetch the active protocol.
3. Parses inventory.json to load registered fleet repositories.
4. Generates a standard Logger or hooks into unilog.facade.UniLog if available.

KEY PARAMETERS:
None
"""
import os
import sys
import json
from pathlib import Path
from typing import Tuple, List, Dict, Any

# -----------------------------------------------------------------------------
# TERMINAL COLORS
# -----------------------------------------------------------------------------
C_RESET = "\033[0m"
C_CYAN = "\033[96m"
C_GREEN = "\033[92m"
C_YELLOW = "\033[93m"
C_RED = "\033[91m"
C_DIM = "\033[2m"
C_BOLD = "\033[1m"

# -----------------------------------------------------------------------------
# SETUP FUNCTIONS
# -----------------------------------------------------------------------------
def setup_terminal() -> None:
    """Standardizes stdout terminal output encoding to UTF-8 on Windows and POSIX systems."""
    if sys.stdout.encoding != 'utf-8':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except (AttributeError, Exception):
            pass

# -----------------------------------------------------------------------------
# CONFIGURATION & LOGGING SETUP
# -----------------------------------------------------------------------------
def get_config() -> Any:
    """
    Returns the centralized ecosystem configuration singleton from bootstrap.
    """
    import src.bootstrap as bootstrap
    return bootstrap.config

# -----------------------------------------------------------------------------
def get_logger(name: str = "SquadLogger") -> Any:
    """
    Returns the centralized UniLog logging engine singleton from bootstrap.
    """
    import src.bootstrap as bootstrap
    return bootstrap.logger

# -----------------------------------------------------------------------------
# PATH & ECOSYSTEM RESOLUTION
# -----------------------------------------------------------------------------
def resolve_vault_and_workspace(script_file: str) -> Tuple[Path, Path]:
    """
    Dynamically resolves the vault root (obsidian-brain or custom brain) and workspace root (parent of vault).
    """
    current = Path(script_file).resolve().parent
    vault_root = None
    for parent in [current] + list(current.parents):
        if (parent / "08-Base-Scripts").is_dir() and (parent / "00-AI-Orchestration").is_dir():
            vault_root = parent
            break
        if parent.name == "obsidian-brain" or parent.name.endswith("-brain"):
            vault_root = parent
            break
            
    if not vault_root:
        # Fallback to parent of script dir if run directly from 08-Base-Scripts
        for parent in [current] + list(current.parents):
            if parent.name == "08-Base-Scripts" or parent.name == "Scripts":
                vault_root = parent.parent
                break
        if not vault_root:
            vault_root = current
            
    workspace_root = vault_root.parent
    return vault_root, workspace_root

# -----------------------------------------------------------------------------
# GOVERNANCE & STATE OPERATIONS
# -----------------------------------------------------------------------------
def get_active_mode(vault_root: Path) -> str:
    """
    Retrieves the currently selected active squad mode protocol from environment
    or fallback MODE-MANUAL.md.
    """
    mode = os.environ.get("SQUAD_ACTIVE_MODE")
    if mode:
        return mode
        
    mode_file = vault_root / "00-AI-Orchestration" / "Config" / "MODE-MANUAL.md"
    if mode_file.exists():
        try:
            with open(mode_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.startswith("active_mode:"):
                        return line.split(":")[1].strip()
        except Exception:
            pass
    return "4"  # Default fallback mode

def get_fleet_repositories(vault_root: Path) -> List[Dict[str, Any]]:
    """
    Loads and returns the list of all registered repositories from inventory.json.
    """
    inventory_path = vault_root / "05-Fleet-Operation" / "00-Repo-Control" / "inventory.json"
    if not inventory_path.exists():
        return []
        
    try:
        with open(inventory_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get("repositories", [])
    except Exception as e:
        sys.stderr.write(f"⚠️ Failed to load inventory.json: {e}\n")
        return []

def resolve_active_workspaces(workspace_root: Path) -> set:
    """
    Resolves the set of active workspace repository folder names.
    1. Environment variables: ACTIVE_WORKSPACES or WORKSPACE_PATHS.
    2. *.code-workspace JSON files in workspace_root.
    3. Fallback: Sibling directories containing .git.
    """
    active = set()
    workspace_root = Path(workspace_root).resolve()

    # 1. Check environment variable
    env_var = os.environ.get("ACTIVE_WORKSPACES") or os.environ.get("WORKSPACE_PATHS")
    if env_var:
        for item in env_var.split(","):
            if item.strip():
                active.add(Path(item.strip()).name)
        if active:
            return active

    # 2. Check *.code-workspace JSON files
    for ws_file in workspace_root.glob("*.code-workspace"):
        try:
            with open(ws_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                for folder in data.get("folders", []):
                    p = folder.get("path")
                    if p:
                        active.add(Path(p).name)
        except Exception:
            pass

    if active:
        return active

    # 3. Fallback: Sibling directories containing .git
    try:
        for item in workspace_root.iterdir():
            if item.is_dir() and (item / ".git").exists():
                active.add(item.name)
    except Exception:
        pass

    return active
