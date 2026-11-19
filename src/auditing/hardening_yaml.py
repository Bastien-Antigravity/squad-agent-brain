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
import src.bootstrap as bootstrap
from os import walk as osWalk
from re import search as reSearch

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
    "00-AI-Orchestration": {"type": "governance", "status": "active", "zone": "#zone/0-orchestration"},
    "01-Strategic-Nexus": {"type": "strategy", "status": "active", "zone": "#zone/1-nexus"},
    "02-Business-BDD": {"type": "spec", "status": "frozen", "zone": "#zone/2-bdd"},
    "03-Tech-Stack": {"type": "architecture", "status": "active", "zone": "#zone/3-fleet"},
    "04-Rapid-Prototyping": {"type": "experiment", "status": "fluid", "zone": "#zone/4-lab"},
    "05-Fleet-Operation": {"type": "fleet-op", "status": "active", "zone": "#zone/3-fleet"},
    "06-Microservices": {"type": "hub", "status": "active", "zone": "#zone/3-fleet"},
    "07-Core-KMS": {"type": "kms", "status": "active", "zone": "#zone/0-core"},
    "08-Squad-Agent": {"type": "automation", "status": "active", "zone": "#zone/0-core"},
    "09-RAG-Engine": {"type": "automation", "status": "active", "zone": "#zone/0-core"},
}

EXCLUDED_DIRS = {
    ".git", ".obsidian", ".venv", "venv", "node_modules", "__pycache__",
    ".agents", ".gemini", "11-Code-Doc", "99-Humans", "Templates", "04-Templates",
}

# -----------------------------------------------------------------------------------------------

def apply_hardening(file_path: Path) -> bool:
    """
    Reads a markdown file and ensures it has valid, canonical YAML frontmatter
    (microservice, type, status, tags) for its zone without corrupting 11-Code-Doc mirrors.
    """
    import yaml

    try:
        relative_path = file_path.relative_to(VAULT_ROOT)
    except ValueError:
        return False

    parts = relative_path.parts
    if any(p in EXCLUDED_DIRS for p in parts):
        return False

    try:
        content = file_path.read_text(encoding="utf-8")
    except OSError:
        return False

    zone = parts[0] if len(parts) > 1 else ""
    defaults = ZONE_MAP.get(zone, {"type": "note", "status": "active", "zone": "#zone/0-core"})

    microservice = "obsidian-brain"
    if zone == "06-Microservices" and len(parts) > 1:
        hub_match = reSearch(r"([\w-]+)-Hub", parts[-1])
        if hub_match:
            microservice = hub_match.group(1).lower()

    yaml_block = {}
    body = content
    modified = False

    if content.startswith("---"):
        fm_parts = content.split("---", 2)
        if len(fm_parts) >= 3:
            try:
                loaded = yaml.safe_load(fm_parts[1])
                if isinstance(loaded, dict):
                    yaml_block = loaded
                    body = fm_parts[2]
                else:
                    return False
            except Exception:
                return False
        else:
            return False
    else:
        modified = True
        body = "\n" + content.lstrip("\n")

    if not yaml_block.get("microservice"):
        yaml_block["microservice"] = microservice
        modified = True
    if not yaml_block.get("type"):
        yaml_block["type"] = defaults["type"]
        modified = True
    if not yaml_block.get("status"):
        yaml_block["status"] = defaults["status"]
        modified = True

    tags = yaml_block.get("tags")
    if not isinstance(tags, list):
        tags = [tags] if tags else []
        modified = True

    required_tags = [
        f"#service/{yaml_block['microservice']}",
        f"#type/{yaml_block['type']}",
        f"#state/{yaml_block['status']}",
        defaults["zone"],
    ]
    existing_lower = {str(t).strip().lower() for t in tags if t}
    for req in required_tags:
        if req.lower() not in existing_lower:
            tags.append(req)
            existing_lower.add(req.lower())
            modified = True
    yaml_block["tags"] = tags

    if modified:
        new_yaml_str = yaml.safe_dump(yaml_block, default_flow_style=False, sort_keys=False).strip()
        new_content = f"---\n{new_yaml_str}\n---{body}"
        file_path.write_text(new_content, encoding="utf-8")
        return True
    return False

# -----------------------------------------------------------------------------------------------

def main() -> None:
    """
    Orchestrates the batch YAML hardening process across the vault (excluding 11-Code-Doc).
    """
    if not VAULT_ROOT.exists():
        print("HardeningYAML: Vault root not found at {0}".format(VAULT_ROOT))
        return

    print("[*] Starting batch YAML hardening...")
    count = 0
    for root, dirs, files in osWalk(VAULT_ROOT):
        dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS and not d.startswith(".")]
        for file in files:
            if file.endswith(".md"):
                path = Path(root) / file
                if apply_hardening(path):
                    count += 1
    print("[*] Hardened {0} files.".format(count))

# -----------------------------------------------------------------------------------------------

if __name__ == "__main__":
    main()
