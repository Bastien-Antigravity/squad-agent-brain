#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Sovereignty Engine and Centralized Knowledge Validation Library.
Enforces YAML frontmatter schema, Obsidian tag taxonomy, and cross-reference integrity
across the Bastien-Antigravity ecosystem notes.

DATA FLOW:
1. Indexes workspace markdown files and builds link/stem registries.
2. Loads canonical tag taxonomy from 00-AI-Orchestration/Tag-Taxonomy.md.
3. Evaluates document frontmatter against REQUIRED_YAML keys.
4. Validates Obsidian tags and wikilinks against indexed notes.
5. Returns structured error and warning collections.

KEY PARAMETERS:
- taxonomy_path: Optional path to Tag-Taxonomy.md.
- workspace_root: Optional path to workspace parent folder.
"""
import os
import sys
from pathlib import Path
from typing import Dict, Set
import json
import re
from lib.bootstrap import ensure_virtualenv, prepend_venv_bin, ensure_import_paths

script_dir = Path(__file__).resolve().parent
vault_root = ensure_virtualenv(str(script_dir))
prepend_venv_bin(vault_root)

ensure_import_paths(script_dir, vault_root)

try:
    import yaml
except ImportError:
    yaml = None

# -----------------------------------------------------------------------------

class Sovereignty:
    # --- Configuration ---
    REQUIRED_YAML = ["microservice", "type", "status"]
    MANDATORY_TAG_ROOTS = ["#type/", "#state/"]
    TRANSVERSAL_TAG_ROOTS = ["#tech/", "#tier/", "#zone/"]
    
    # -----------------------------------------------------------------------------

    def __init__(self, taxonomy_path: Path = None, workspace_root: Path = None):
        self.errors = []
        self.warnings = []
        self.file_errors = {}
        self.file_warnings = {}
        self.current_file = None
        self.valid_tags = set()
        self.valid_stems = set()
        self.valid_paths = set()
        
        self.vault_root = Path(__file__).resolve().parents[2]
        
        # Determine workspace root (defaults to parent of vault)
        if workspace_root is None:
            self.workspace_root = self.vault_root.parent
        else:
            self.workspace_root = Path(workspace_root)
            
        self._index_workspace()
        
        if taxonomy_path and taxonomy_path.exists():
            self._load_taxonomy(taxonomy_path)

    def _index_workspace(self):
        from os import walk as osWalk
        exclude_dirs = {
            ".git", ".obsidian", ".gemini", ".claude", ".codex", ".deepseek", 
            "experiments", "node_modules", ".venv", "venv",
            "dist-packages", "site-packages", "__pycache__", "target", "build"
        }
        for root, dirs, files in osWalk(self.workspace_root):
            # Prune directories in-place to avoid traversing ignored folders
            dirs[:] = [d for d in dirs if d not in exclude_dirs and not d.startswith(".")]
            
            for file in files:
                path = Path(root) / file
                self.valid_stems.add(path.stem)
                self.valid_paths.add(file)
                try:
                    rel_path = path.relative_to(self.workspace_root).as_posix()
                    self.valid_paths.add(rel_path)
                except ValueError:
                    pass

    def _load_taxonomy(self, path: Path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
                # Find all #tag/ or #tag patterns
                found = re.findall(r'#[\w/-]+', content)
                for t in found:
                    self.valid_tags.add(t)
        except Exception as e:
            self.log_warning(f"Could not load taxonomy from {path}: {e}")

    def log_error(self, message: str):
        self.errors.append(message)
        if self.current_file:
            # Normalize path for reporting
            file_key = str(self.current_file)
            self.file_errors.setdefault(file_key, []).append(message)

    def log_warning(self, message: str):
        self.warnings.append(message)
        if self.current_file:
            # Normalize path for reporting
            file_key = str(self.current_file)
            self.file_warnings.setdefault(file_key, []).append(message)

    # --- Validation Methods ---

    def validate_frontmatter(self, content: str, file_name: str) -> bool:
        """Checks for mandatory YAML frontmatter fields."""
        if not content.startswith("---"):
            self.log_error(f"[{file_name}] Missing YAML frontmatter.")
            return False

        parts = content.split("---", 2)
        if len(parts) < 3:
            self.log_error(f"[{file_name}] Malformed YAML frontmatter.")
            return False

        yaml_block = parts[1]
        missing = [f for f in self.REQUIRED_YAML if f"{f}:" not in yaml_block]
        
        for field in missing:
            self.log_error(f"[{file_name}] Missing mandatory field: '{field}'")
            
        return len(missing) == 0

    def validate_taxonomy(self, content: str, file_name: str):
        """Ensures mandatory and transversal tags are present."""
        # 1. Mandatory Roots
        for tag_root in self.MANDATORY_TAG_ROOTS:
            if tag_root not in content:
                self.log_warning(f"[{file_name}] Missing recommended taxonomy tag: '{tag_root}'")
        
        # 2. Transversal Trinity (Need at least one of these)
        if not any(t in content for t in self.TRANSVERSAL_TAG_ROOTS):
            self.log_error(f"[{file_name}] TRANSVERSAL ERROR: File must have at least one #tech/, #tier/, or #zone/ tag.")

    def validate_isolation_zone(self, repo_path: Path, repo_name: str) -> bool:
        """Checks for the presence and structure of the isolation zone."""
        is_brain = (repo_name == self.vault_root.name)
        zone_name = "99-Humans" if is_brain else "quick-overview"
        zone_dir = repo_path / zone_name
        
        if not zone_dir.exists():
            self.log_error(f"[{repo_name}] Missing mandatory isolation zone: {zone_name}")
            return False
            
        # Define mandatory files for the zone
        if is_brain:
            # Brain only requires the core dashboards
            mandatory = ["Sprint-Dashboard.md", "Domain-Dashboard.md"]
        else:
            # Microservices require the full structural quartet
            mandatory = [
                "Architecture-Overview.md", 
                "Features-Behavior.md", 
                "Testing-Playbook.md", 
                "General-Misc.md"
            ]
            
        success = True
        for filename in mandatory:
            if not (zone_dir / filename).exists():
                self.log_error(f"[{repo_name}] Missing file in {zone_name}: {filename}")
                success = False
        
        return success

    def validate_links(self, content: str, file_name: str):
        """Identifies broken [[Links]], ignoring those inside code blocks."""
        # Strip fenced code blocks (```vba ... ```) and inline code blocks (`code`)
        clean_content = re.sub(r'```.*?```', '', content, flags=re.DOTALL)
        clean_content = re.sub(r'`[^`\n]+`', '', clean_content)
        
        # Extract [[Link]] or [[Link|Alias]]
        links = re.findall(r'\[\[([^|\]]+)(?:\|[^\]]*)?\]\]', clean_content)
        
        for link in links:
            clean_link = link.strip().replace("\\", "/")
            # Strip anchor if present (e.g., filename#anchor -> filename)
            if "#" in clean_link:
                clean_link = clean_link.split("#", 1)[0]
                
            link_stem = Path(clean_link).stem
            
            # Check against stems, full relative paths, or exact filenames
            if clean_link in self.valid_stems or clean_link in self.valid_paths or link_stem in self.valid_stems:
                continue
                
            # If it's a direct file reference with extension
            if any(clean_link.endswith(ext) for ext in [".md", ".json"]):
                # This would need a full file list to be perfect, 
                # for now we flag it if not in paths
                if clean_link not in self.valid_paths:
                    self.log_error(f"[{file_name}] Broken link: [[{link}]]")
            else:
                # Assume .md if no extension
                if f"{clean_link}.md" not in self.valid_paths:
                    self.log_error(f"[{file_name}] Broken link: [[{link}]]")

    def validate_telemetry(self, content: str, file_name: str):
        """Ensures Roles have the [SCAN] block."""
        # Only enforce on core agent definitions or role prompts
        if any(x in file_name.lower() for x in ["role-", "prompt-", "agent-"]):
            if "[SCAN]" not in content:
                self.log_error(f"[{file_name}] Role definition missing mandatory [SCAN] telemetry block.")

    def validate_utc_mandate(self, content: str, file_name: str):
        """Heuristic check for prohibited local time references."""
        # Very basic check for common local time indicators if they aren't followed by 'UTC' or 'Z'
        # This is a warning-only check as it can have false positives
        local_time_patterns = [
            r'\d{1,2}:\d{2} (AM|PM)(?!.*UTC)',
            r'Local Time',
            r'Heure locale'
        ]
        for pattern in local_time_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                self.log_warning(f"[{file_name}] Potential 'Local Time' detected. Ensure UTC mandate is followed.")

    def validate_session_state(self, content: str, file_name: str):
        """Checks for Mission-ID in session states."""
        if "AI-Session-State" in file_name:
            if not re.search(r'Mission-ID:|Trace-ID:|X-Bastien-Mission-ID', content, re.IGNORECASE):
                self.log_error(f"[{file_name}] Session state entry missing Mission/Trace ID.")

    def validate_orphan_tags(self, content: str, file_name: str):
        """Identifies tags not defined in the taxonomy, ignoring hex colors and code blocks."""
        if not self.valid_tags:
            return
            
        # Strip fenced code blocks (```vba ... ```) and inline code blocks (`code`)
        clean_content = re.sub(r'```.*?```', '', content, flags=re.DOTALL)
        clean_content = re.sub(r'`[^`\n]+`', '', clean_content)
        
        # Strip internal markdown links to avoid matching section anchors like [[File#Section]]
        clean_content = re.sub(r'\[\[.*?\]\]', '', clean_content)
        
        tags = re.findall(r'#([\w/-]+)', clean_content)
        for t in tags:
            full_tag = f"#{t}"
            
            # Skip hex colors (3 or 6 hex digits)
            if re.match(r'^[0-9a-fA-F]{3}$|^[0-9a-fA-F]{6}$', t):
                continue
            
            # Check if valid
            is_valid = False
            for v in self.valid_tags:
                if full_tag == v or (v.endswith("/") and full_tag.startswith(v)):
                    is_valid = True
                    break
            
            if not is_valid:
                self.log_warning(f"[{file_name}] Orphan tag detected: {full_tag}")

    def is_ignored_by_firewall(self, path: Path, ignore_ai_tag: bool = False) -> bool:
        """Checks if a path is ignored by context firewalls (.aiignore etc) or carries the #ai/ignore tag."""
        try:
            current = path.resolve()
            root = self.workspace_root.resolve()
            check_dir = current if current.is_dir() else current.parent
            while True:
                for ignore_name in [".aiignore", ".geminiignore", ".mcpignore"]:
                    if (check_dir / ignore_name).exists():
                        return True
                if check_dir == root or check_dir.parent == check_dir:
                    break
                check_dir = check_dir.parent
        except Exception:
            pass

        if ignore_ai_tag:
            return False

        try:
            if path.is_file() and path.suffix == ".md":
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    head = f.read(1000)
                    if '#ai/ignore' in head:
                        return True
        except Exception:
            pass
        return False

    # --- Orchestration ---

    def audit_file(self, path: Path):
        """Runs the full suite against a single file."""
        if not path.suffix == ".md":
            return

        if self.is_ignored_by_firewall(path, ignore_ai_tag=True):
            return

        self.current_file = path
        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            file_name = path.name
            
            self.validate_frontmatter(content, file_name)
            self.validate_taxonomy(content, file_name)
            self.validate_orphan_tags(content, file_name)
            self.validate_links(content, file_name)
            self.validate_telemetry(content, file_name)
            self.validate_utc_mandate(content, file_name)
            self.validate_session_state(content, file_name)
            self.validate_placeholders(content, file_name)
            self.validate_hardcoded_paths(content, file_name)
            
        except Exception as e:
            self.log_error(f"Failed to read {path.name}: {str(e)}")
        finally:
            self.current_file = None

    def validate_placeholders(self, content: str, file_name: str):
        """Ensures that template placeholders like {{microservice}} are resolved."""
        placeholders = re.findall(r'\{\{[\w-]+\}\}', content)
        if placeholders:
            for p in placeholders:
                self.log_error(f"[{file_name}] Unresolved placeholder detected: {p}")

    def validate_hardcoded_paths(self, content: str, file_name: str):
        """Ensures that no hardcoded absolute local paths are used in links."""
        matches = re.findall(r'(\bfile:///Users/[^\s)\]\n\r]+|\b/Users/[^\s)\]\n\r]+|\bfile:///home/[^\s)\]\n\r]+|\b/home/[^\s)\]\n\r]+)', content)
        if matches:
            for m in matches:
                self.log_error(f"[{file_name}] Hardcoded absolute path detected: {m}")

    def auto_fix_file(self, path: Path):
        """Fixes taxonomy issues, enforces YAML frontmatter schema, and automatically converts absolute links to relative ones."""
        if not path.suffix == ".md":
            return
            
        if self.is_ignored_by_firewall(path, ignore_ai_tag=True):
            return
            
        if yaml is None:
            self.log_warning("PyYAML not installed — frontmatter auto-fix skipped. Run: pip install pyyaml")
            return
            
        self.current_file = path
        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
                
            original_content = content
            
            # 1. Enforce YAML Frontmatter Schema
            # Zone metadata defaults mapping (from Hardening-YAML)
            zone_map = {
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
            
            vault_root = self.vault_root
            try:
                rel_path = path.relative_to(vault_root)
            except ValueError:
                try:
                    rel_path = path.relative_to(self.workspace_root)
                    if rel_path.parts and rel_path.parts[0] == self.vault_root.name:
                        rel_path = Path(*rel_path.parts[1:])
                except ValueError:
                    rel_path = path
                    
            parts = rel_path.parts
            zone = parts[0] if parts else ""
            defaults = zone_map.get(zone, {"type": "note", "status": "active"})
            
            # Determine microservice
            microservice = self.vault_root.name
            if zone == "06-Microservices" and len(parts) > 1:
                hub_match = re.search(r"([\w-]+)-Hub", parts[-1])
                if hub_match:
                    microservice = hub_match.group(1).lower()
            elif zone == "02-Business-BDD" and len(parts) > 2 and parts[1] == "02-Behavior-Specs":
                microservice = parts[2]
                
            data = {}
            body = content
            
            has_fm = content.startswith("---")
            if has_fm:
                fm_parts = content.split("---", 2)
                if len(fm_parts) >= 3:
                    yaml_block = fm_parts[1]
                    body = fm_parts[2]
                    
                    # Sanitize list bullet format before loading to be robust
                    sanitized_lines = []
                    for line in yaml_block.splitlines():
                        stripped = line.strip()
                        if stripped.startswith("-"):
                            val = stripped.split("-", 1)[1].strip().strip("'\"")
                            line = f"  - '{val}'"
                        sanitized_lines.append(line)
                    yaml_block = "\n".join(sanitized_lines)
                    
                    try:
                        data = yaml.safe_load(yaml_block) or {}
                    except Exception:
                        data = {}
            
            # Ensure mandatory fields
            if not isinstance(data, dict):
                data = {}
                
            # Inject defaults if missing or empty
            if not data.get("microservice"):
                data["microservice"] = microservice
            if not data.get("type"):
                data["type"] = defaults["type"]
            if not data.get("status"):
                data["status"] = defaults["status"]
                
            # Clean and normalize tags
            tags = data.get("tags", [])
            if not isinstance(tags, list):
                tags = [tags] if tags else []
                
            new_tags = []
            for tag in tags:
                if not tag or str(tag).lower() == 'null':
                    continue
                tag_str = str(tag).strip().replace("\\", "").strip("'\"")
                if not tag_str.startswith("#"):
                    if tag_str.startswith("domain/"):
                        tag_str = "#" + tag_str
                    elif tag_str.startswith("/"):
                        tag_str = "#" + tag_str[1:]
                    else:
                        tag_str = "#" + tag_str
                new_tags.append(tag_str)
                
            # Ensure #service tag is present if microservice is set
            service_tag = f"#service/{data['microservice']}"
            if service_tag not in new_tags:
                new_tags.append(service_tag)
                
            # Ensure type tag is present if type is set
            type_tag = f"#type/{data['type']}"
            if type_tag not in new_tags:
                new_tags.append(type_tag)
                
            # Ensure status tag is present if status is set
            status_tag = f"#state/{data['status']}"
            if status_tag not in new_tags:
                new_tags.append(status_tag)
                
            # Ensure at least one transversal tag (#tech/, #tier/, #zone/) is present
            if not any(t in str(tag) for t in ["#tech/", "#tier/", "#zone/"] for tag in new_tags):
                new_tags.append("#zone/3-fleet")
                
            # Remove duplicate tags while preserving order
            seen = set()
            dedup_tags = []
            for t in new_tags:
                if t not in seen:
                    seen.add(t)
                    dedup_tags.append(t)
            data["tags"] = dedup_tags
            
            # Serialize yaml with a clean structured style
            new_yaml = yaml.dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True)
            content = f"---\n{new_yaml}---{body}"
            
            # 2. Auto-fix absolute links to dynamic relative links
            absolute_links = re.findall(r'\[([^\]]*)\]\((file:///Users/[^\s)\]]+|/Users/[^\s)\]]+|file:///home/[^\s)\]]+|/home/[^\s)\]]+)\)', content)
            for text, target_url in absolute_links:
                clean_path_str = target_url.replace("file://", "")
                target_path = Path(clean_path_str).resolve()
                if target_path.exists():
                    from os.path import relpath as osPathRelPath
                    rel_path = osPathRelPath(target_path, path.parent)
                    rel_path_str = Path(rel_path).as_posix()
                    old_link = f"[{text}]({target_url})"
                    new_link = f"[{text}]({rel_path_str})"
                    content = content.replace(old_link, new_link)
            
            if content != original_content:
                # Handle potential read-only files by temporarily adding write permissions
                is_readonly = not os.access(path, os.W_OK)
                if is_readonly:
                    try:
                        os.chmod(path, 0o644)
                    except Exception:
                        pass
                
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(content)
                    
                if is_readonly:
                    try:
                        os.chmod(path, 0o444)
                    except Exception:
                        pass
                    
        except Exception as e:
            self.log_warning(f"Auto-fix failed for {path.name}: {str(e)}")
        finally:
            self.current_file = None

    def get_report(self) -> Dict:
        return {
            "errors": self.errors,
            "warnings": self.warnings,
            "success": len(self.errors) == 0,
            "file_errors": self.file_errors,
            "file_warnings": self.file_warnings
        }

