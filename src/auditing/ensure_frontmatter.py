#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Enforces YAML front-matter standards and tag taxonomy across Obsidian Brain RAG human documentation.
Designed to run as a git pre-commit hook or standalone validator.

DATA FLOW:
1. Locates human documentation markdown files (under quick-overview/ or 06-Microservices/).
2. Parses existing YAML blocks or initializes them using directory context defaults.
3. Automatically inserts or updates key-value pairs (microservice, type, status).
4. Synchronizes Obsidian tags taxonomy (e.g. #service/<name>, #type/<type>, #state/<status>, #ai/ignore).
5. Writes changes back to files, and exits with non-zero if checking/hook constraints fail.

KEY PARAMETERS:
- check_only: If True, only verifies compliance without modifying files.
- workspace_root: Root workspace path to scan.
"""

import os
import sys
import re
import yaml
from pathlib import Path
import subprocess

# -----------------------------------------------------------------------------

# Patterns
FRONT_MATTER_PATTERN = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

# -----------------------------------------------------------------------------

def is_documentation_file(file_path):
    """Determines whether a markdown file is human documentation subject to frontmatter checks."""
    path = Path(file_path)
    if path.suffix != ".md":
        return False
    parts = path.parts
    # Exclude machine-generated AST mirrors, virtualenvs, git, node_modules
    if any(p in parts for p in ("11-Code-Doc", ".venv", "node_modules", ".git", ".agents")):
        return False
    # Include quick-overview human documentation
    if "quick-overview" in parts:
        return True
    # Include 06-Microservices service specs
    if "06-Microservices" in parts and path.name != "Hubs-MOC.md":
        return True
    # Include repo-level AGENTS.md rules
    if path.name == "AGENTS.md":
        return True
    return False

# -----------------------------------------------------------------------------

def get_modified_files():
    """Retrieves list of modified and cached markdown files using git."""
    try:
        res = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
            capture_output=True, text=True, check=True
        )
        files = []
        for line in res.stdout.splitlines():
            if is_documentation_file(line):
                files.append(line)
        return files
    except Exception:
        return []

# -----------------------------------------------------------------------------

def get_all_documentation_files(workspace_root):
    """Scans for all human documentation markdown files in quick-overview and 06-Microservices."""
    docs = []
    root_path = Path(workspace_root)
    
    # 1. Scan quick-overview folders across the workspace
    for p in root_path.glob("**/quick-overview/*.md"):
        if ".venv" not in p.parts and "node_modules" not in p.parts:
            docs.append(p)
            
    # 2. Scan 06-Microservices/
    microservices_dir = root_path / "obsidian-brain" / "06-Microservices"
    if microservices_dir.exists():
        for p in microservices_dir.glob("*.md"):
            if p.name != "Hubs-MOC.md":
                docs.append(p)
                
    return docs

# -----------------------------------------------------------------------------

def normalize_frontmatter(file_path, check_only=False):
    """
    Parses and ensures frontmatter conforms to specifications.
    Returns (modified_bool, error_msg).
    """
    path = Path(file_path)
    if not path.exists():
        return False, f"File {file_path} does not exist."
        
    try:
        content = path.read_text(encoding='utf-8')
    except Exception as e:
        return False, f"Failed reading file: {e}"

    # Determine default microservice name from directory structure
    parts = path.parts
    microservice_name = "common"
    for i, part in enumerate(parts):
        if part == "quick-overview" and i > 0:
            microservice_name = parts[i - 1]
            break
    if "06-Microservices" in parts:
        microservice_name = path.stem.lower().replace("-hub", "").replace("-", "_")

    match = FRONT_MATTER_PATTERN.match(content)
    yaml_block = {}
    remaining_content = content
    has_frontmatter = False

    if match:
        has_frontmatter = True
        yaml_str = match.group(1)
        remaining_content = content[match.end():]
        try:
            yaml_block = yaml.safe_load(yaml_str) or {}
        except Exception as e:
            return False, f"Invalid YAML frontmatter: {e}"

    # Verify and complete key fields
    modified = False
    
    # Ensure microservice
    orig_service = yaml_block.get("microservice") or yaml_block.get("service")
    if not orig_service:
        yaml_block["microservice"] = microservice_name
        modified = True
    elif "service" in yaml_block:
        # standardise to 'microservice'
        yaml_block["microservice"] = yaml_block.pop("service")
        modified = True
        
    # Ensure type
    if "type" not in yaml_block:
        yaml_block["type"] = "overview"
        modified = True
        
    # Ensure status
    if "status" not in yaml_block:
        yaml_block["status"] = "active"
        modified = True

    # Normalize tags
    tags = yaml_block.get("tags", [])
    if not isinstance(tags, list):
        tags = [tags] if tags else []
    
    svc_tag = f"#service/{yaml_block['microservice']}"
    type_tag = f"#type/{yaml_block['type']}"
    state_tag = f"#state/{yaml_block['status']}"
    ai_ignore_tag = "#ai/ignore"

    required_tags = [svc_tag, type_tag, state_tag, ai_ignore_tag]
    
    # Remove duplicates or slightly malformed representations
    cleaned_tags = []
    for tag in tags:
        if isinstance(tag, str):
            cleaned_tag = tag.strip().lower()
            if cleaned_tag not in cleaned_tags:
                cleaned_tags.append(cleaned_tag)
                
    # Insert required tags if missing
    for req in required_tags:
        if req.lower() not in cleaned_tags:
            cleaned_tags.append(req)
            modified = True

    yaml_block["tags"] = cleaned_tags

    if modified:
        if check_only:
            return True, "Frontmatter or tags missing required standard values."
        
        # Serialize back to file
        try:
            new_yaml_str = yaml.safe_dump(yaml_block, default_flow_style=False, sort_keys=False)
            new_content = f"---\n{new_yaml_str}---\n{remaining_content}"
            path.write_text(new_content, encoding='utf-8')
            return True, "Updated successfully."
        except Exception as e:
            return False, f"Failed writing updates to file: {e}"
            
    return False, "Conforming."

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Enforce frontmatter standards on human documentation.")
    parser.add_argument("--check-all", action="store_true", help="Validate all docs in workspace.")
    parser.add_argument("--check", action="store_true", help="Checking only, do not write changes.")
    args = parser.parse_args()

    try:
        from src.lib.orchestration_lib import resolve_vault_and_workspace
        vault_root, workspace_root = resolve_vault_and_workspace(__file__)
    except Exception:
        script_dir = Path(__file__).resolve().parent
        vault_root = script_dir.parent.parent.parent
        workspace_root = vault_root.parent

    if args.check_all:
        files = get_all_documentation_files(workspace_root)
    else:
        # Default: check git cached files (git diff paths are relative to vault_root)
        cached_files = get_modified_files()
        if cached_files:
            files = [vault_root / f for f in cached_files]
        elif args.check:
            # In pre-commit check hook, if no documentation files are staged, nothing to validate
            files = []
        else:
            # In standalone manual run without arguments, check all documentation files
            files = get_all_documentation_files(workspace_root)

    print(f"🔍 Enforcing frontmatter checks on {len(files)} files...")
    
    violations = 0
    for file in files:
        try:
            rel_path = Path(file).relative_to(vault_root)
        except ValueError:
            rel_path = Path(file).relative_to(workspace_root)
        modified, msg = normalize_frontmatter(file, check_only=args.check)
        if modified:
            if args.check:
                print(f"❌ Violation in {rel_path}: {msg}")
                violations += 1
            else:
                print(f"⚙️ Fixed frontmatter metadata in {rel_path}")
        else:
            if "Failed" in msg:
                print(f"❌ Error in {rel_path}: {msg}")
                violations += 1

    if violations > 0:
        print(f"❌ Verification failed: {violations} file(s) require metadata fixes.")
        sys.exit(1)
        
    print("✅ All check specifications conform successfully.")
    sys.exit(0)

if __name__ == "__main__":
    main()
