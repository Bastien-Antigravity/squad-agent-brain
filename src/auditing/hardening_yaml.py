#!/usr/bin/env python
# coding:utf-8
"""
ESSENTIAL PROCESS:
Enforces mandatory YAML frontmatter (microservice, type, status) across 
all markdown files in the Obsidian vault based on their directory location.

DATA FLOW:
1. Crawls the obsidian-brain directory for .md files.
2. Identifies the "Zone" (folder prefix) to determine default metadata.
3. Injects or updates the YAML frontmatter in each file.
4. Saves the hardened content back to disk.

KEY PARAMETERS:
- ZONE_MAP: Mapping of folder names to their architectural type and status.
- VAULT_ROOT: The target directory for hardening.
"""
import os
import sys
from pathlib import Path
from lib.bootstrap import ensure_virtualenv, prepend_venv_bin, ensure_import_paths

script_dir = Path(__file__).resolve().parent
vault_root = ensure_virtualenv(str(script_dir))
prepend_venv_bin(vault_root)

ensure_import_paths(script_dir, vault_root)

from os import walk as osWalk
from re import search as reSearch
from pathlib import Path

# ### CONFIGURATIONS ###

def _find_workspace_root() -> Path:
    """
    Walk up from this script's location until we find the workspace root.
    """
    current = Path(__file__).resolve().parent
    for parent in [current] + list(current.parents):
        if list(parent.glob("*.code-workspace")):
            return parent
        if (parent / "obsidian-brain").is_dir() and (parent / "fleet-operation-brain").is_dir():
            return parent
    return Path(__file__).resolve().parents[1]

WORKSPACE_ROOT = _find_workspace_root()
VAULT_ROOT = WORKSPACE_ROOT / "obsidian-brain"

# Mapping of folder prefixes to metadata
ZONE_MAP = {
    "00-AI-Orchestration": {"type": "governance", "status": "active"},
    "01-Strategic-Nexus": {"type": "strategy", "status": "active"},
    "02-Business-BDD": {"type": "spec", "status": "frozen"},
    "03-Tech-Stack": {"type": "architecture", "status": "active"},
    "04-Rapid-Prototyping": {"type": "experiment", "status": "fluid"},
    "05-Fleet-Operation": {"type": "fleet-op", "status": "active"},
    "06-Microservices": {"type": "hub", "status": "active"},
    "07-Core-KMS": {"type": "kms", "status": "active"},
    "08-Base-Scripts": {"type": "automation", "status": "active"},
}

# -----------------------------------------------------------------------------------------------

def apply_hardening(file_path: Path) -> None:
    """
    Reads a file and ensures it has the correct YAML frontmatter for its zone.
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    try:
        relative_path = file_path.relative_to(VAULT_ROOT)
    except ValueError:
        # File is not within VAULT_ROOT
        return
        
    parts = relative_path.parts
    
    # Determine zone-based defaults
    zone = parts[0] if parts else ""
    defaults = ZONE_MAP.get(zone, {"type": "note", "status": "active"})
    
    # Determine microservice
    microservice = "obsidian-brain"
    if zone == "06-Microservices" and len(parts) > 1:
        # Try to extract microservice name from Hub file
        hub_match = reSearch(r"([\w-]+)-Hub", parts[-1])
        if hub_match:
            microservice = hub_match.group(1).lower()

    new_frontmatter = {
        "microservice": microservice,
        "type": defaults["type"],
        "status": defaults["status"]
    }

    if content.startswith("---"):
        # Update existing frontmatter
        fm_parts = content.split("---", 2)
        if len(fm_parts) >= 3:
            fm_content = fm_parts[1]
            body = fm_parts[2]
            
            for key, val in new_frontmatter.items():
                if "{0}:".format(key) not in fm_content:
                    fm_content = "{0}: {1}\n".format(key, val) + fm_content
            
            new_content = "--- \n{0}\n---{1}".format(fm_content.strip(), body)
        else:
            # Malformed, treat as no frontmatter for safety
            fm_header = "\n".join(["{0}: {1}".format(k, v) for k, v in new_frontmatter.items()])
            new_content = "---\n{0}\n---\n\n{1}".format(fm_header, content)
    else:
        # Create new frontmatter
        fm_header = "\n".join(["{0}: {1}".format(k, v) for k, v in new_frontmatter.items()])
        new_content = "---\n{0}\n---\n\n{1}".format(fm_header, content)

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(new_content)

# -----------------------------------------------------------------------------------------------

def main() -> None:
    """
    Orchestrates the batch hardening process across the entire vault.
    """
    if not VAULT_ROOT.exists():
        print("HardeningYAML: Vault root not found at {0}".format(VAULT_ROOT))
        return

    print("[*] Starting batch YAML hardening...")
    count = 0
    for root, dirs, files in osWalk(VAULT_ROOT):
        if ".git" in root or ".obsidian" in root:
            continue
        for file in files:
            if file.endswith(".md"):
                path = Path(root) / file
                apply_hardening(path)
                count += 1
    print("[*] Hardened {0} files.".format(count))

# -----------------------------------------------------------------------------------------------

if __name__ == "__main__":
    main()
