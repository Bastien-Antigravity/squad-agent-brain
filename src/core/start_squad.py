#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Initializes the Bastien-Antigravity AI Squad Command Center. Handles MCP binding,
pre-session audits, role synchronization, and launches the selected AI client.

DATA FLOW:
1. Performs Preflight and Sovereignty audits to detect architecture drift.
2. Synchronizes Role-Prompts to agent definitions (convert_agents.py).
3. Invokes the Mode Selector and applies the protocol (switch_mode.py).
4. Configures the MCP server-filesystem based on mode isolation rules.
5. Launches the selected AI client in a re-launchable lifecycle loop.

KEY PARAMETERS:
- vault_root: Resolved path to the Obsidian Brain vault.
- mcp_args: Dynamic arguments for the filesystem MCP server.
"""

import sys
from pathlib import Path

from lib.bootstrap import ensure_virtualenv, prepend_venv_bin, ensure_import_paths, get_venv_python

# Ensure we are running inside the virtual environment
script_dir = Path(__file__).resolve().parent
vault_root_path = ensure_virtualenv(str(script_dir))
prepend_venv_bin(vault_root_path)
ensure_import_paths(script_dir, vault_root_path)
_venv_python = get_venv_python(vault_root_path)
vault_root = str(vault_root_path)

from os import makedirs as osMakedirs, listdir as osListdir, name as osName, getenv as osGetenv, remove as osRemove, \
               environ as osEnviron, chmod as osChmod, walk as osWalk
from json import dump as jsonDump, load as jsonLoad
from subprocess import run as subprocessRun
from os.path import abspath as osPathAbspath, join as osPathJoin, dirname as osPathDirname, exists as osPathExists, \
                    expanduser as osPathExpanduser, isdir as osPathIsdir, basename as osPathBasename, getmtime as osPathGetmtime
from sys import exit as sysExit, executable as sysExecutable, path as sysPath, stdout as sysStdout
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime


try:
    from lib.orchestration_lib import get_logger, get_config
    logger = get_logger("SquadAgent")
    
    from switch_mode import apply_mode_protocol, MODES
    from mission_help import MissionHelper
except ImportError:
    print("❌ Error: Could not find required launcher modules in 08-Squad-Agent/")
    sysExit(1)

# -----------------------------------------------------------------------------------------------

def log_session_event(message: str) -> None:
    """Logs a message with timestamp to the session log file."""
    log_dir = osPathJoin(vault_root, "00-AI-Orchestration", "Logs")
    if not osPathExists(log_dir):
        try:
            osMakedirs(log_dir, exist_ok=True)
        except OSError as e:
            logger.warning(f"Could not create session log directory: {e}")
            return
            
    log_file = osPathJoin(log_dir, f"session-{datetime.now().strftime('%Y-%m-%d')}.log")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {message}\n")
    except OSError as e:
        logger.warning(f"Failed to write to session log: {e}")

def get_vault_python() -> str:
    """Return the vault virtualenv Python when available, otherwise current Python."""
    return _venv_python if osPathExists(_venv_python) else sysExecutable

# -----------------------------------------------------------------------------------------------

def print_process_manifest_summary() -> None:
    """
    Reads process-manifest.json and prints a beautiful status table of all active components.
    """
    C_RESET = "\033[0m"
    C_GREEN = "\033[92m"
    C_RED = "\033[91m"
    C_BOLD = "\033[1m"

    manifest_path = osPathJoin(vault_root, "00-AI-Orchestration", "Config", "process-manifest.json")
    if not osPathExists(manifest_path):
        print(f"{C_RED}⚠️ Process manifest not found at {manifest_path}{C_RESET}")
        return

    try:
        with open(manifest_path, 'r', encoding='utf-8') as f:
            manifest = jsonLoad(f)
    except (OSError, ValueError) as e:
        logger.error(f"⚠️ Error loading process manifest: {e}")
        return

    print("\n" + "═"*75)
    print(f"📊 {C_BOLD}BASTIEN-ANTIGRAVITY: MULTIDIMENSIONAL PROCESS REGISTRY SUMMARY{C_RESET}")
    print("═"*75)
    
    header_format = "{:<20} {:<10} {:<32} {:<10}"
    print(C_BOLD + header_format.format("Component Name", "Type", "Trigger Condition", "Status") + C_RESET)
    print("─"*75)

    all_ok = True
    for category in ["processes", "agents", "concepts"]:
        elements = manifest.get(category, [])
        for el in elements:
            name = el.get("name", "Unknown")
            trigger = el.get("trigger_condition", "N/A")
            assoc_file = el.get("associated_file", "")
            
            if len(trigger) > 30:
                trigger = trigger[:27] + "..."
                
            full_path = osPathJoin(vault_root, assoc_file)
            if osPathExists(full_path):
                status_str = f"{C_GREEN}GREEN [OK]{C_RESET}"
            else:
                status_str = f"{C_RED}RED [DRIFT]{C_RESET}"
                all_ok = False
                
            type_label = category[:-1].upper()
            print(header_format.format(name, type_label, trigger, status_str))

    print("═"*75)
    if all_ok:
        print(f"✨ {C_GREEN}SYSTEM COHERENCE: All active control elements are verified.{C_RESET}")
    else:
        print(f"⚠️  {C_RED}SYSTEM ALERT: Component drift detected! Check missing files.{C_RESET}")
    print("═"*75 + "\n")

# -----------------------------------------------------------------------------------------------

def archive_strat_files() -> None:
    """
    DATA FLOW:
    Finds all STRAT-*.md files in the root of 01-Strategic-Nexus and moves them to 01-Strategic-Nexus/archive/.
    Creates the archive folder if it doesn't exist.
    Updates the links in all Strategy-Nexus markdown files to reflect the new location if needed.
    """
    nexus_dir = osPathJoin(vault_root, "01-Strategic-Nexus")
    if not osPathExists(nexus_dir):
        return
        
    archive_dir = osPathJoin(nexus_dir, "archive")
    
    moved_any = False
    
    try:
        # Scan for STRAT-*.md files in the root of 01-Strategic-Nexus
        for item in osListdir(nexus_dir):
            if item.startswith("STRAT-") and item.endswith(".md"):
                # Create archive folder on demand
                if not osPathExists(archive_dir):
                    try:
                        osMakedirs(archive_dir, exist_ok=True)
                        logger.info("📁 Created archive directory in 01-Strategic-Nexus")
                    except OSError as e:
                        logger.warning(f"⚠️ Warning: Could not create archive directory via python: {e}")
                
                src_path = osPathJoin(nexus_dir, item)
                dst_path = osPathJoin(archive_dir, item)
                
                # Robust move with copy+delete fallback to bypass OS permission/metadata locks
                import shutil
                try:
                    shutil.move(src_path, dst_path)
                    logger.info(f"📦 Archived STRAT audit: {item} -> archive/{item}")
                    moved_any = True
                except OSError as e_move:
                    # Fallback to copy and remove
                    try:
                        with open(src_path, "rb") as f_src:
                            with open(dst_path, "wb") as f_dst:
                                f_dst.write(f_src.read())
                        try:
                            osRemove(src_path)
                        except OSError as e_rm:
                            logger.warning(f"⚠️ Warning: Could not remove source file {item}: {e_rm}")
                        logger.info(f"📦 Archived STRAT audit (fallback): {item} -> archive/{item}")
                        moved_any = True
                    except OSError as e_copy:
                        logger.error(f"⚠️ Error: Could not move {item} to archive: {e_move} (fallback failed: {e_copy})")
                
        # If we moved files, update links in all markdown files in 01-Strategic-Nexus (excluding archive/)
        if moved_any:
            import re
            for file_item in osListdir(nexus_dir):
                if file_item.endswith(".md"):
                    file_path = osPathJoin(nexus_dir, file_item)
                    try:
                        with open(file_path, "r", encoding="utf-8") as f:
                            content = f.read()
                        
                        # Use negative lookahead to prevent double-archiving already updated links
                        updated_content = re.sub(
                            r'\[\[(?!archive/)(STRAT-\d+-[^\]]+)\]\]',
                            r'[[archive/\1]]',
                            content
                        )
                        
                        if updated_content != content:
                            with open(file_path, "w", encoding="utf-8") as f:
                                f.write(updated_content)
                            logger.info(f"📝 Updated links in {file_item} to target the archive folder.")
                    except OSError as e:
                        logger.warning(f"⚠️ Warning: Could not update links in {file_item}: {e}")
    except OSError as e:
        logger.error(f"⚠️ Error scanning STRAT files: {e}")

# -----------------------------------------------------------------------------------------------

def setup_mcp(mode_choice: str) -> None:
    """
    DATA FLOW:
    Resolves vault root and configures the MCP filesystem and RAG servers.
    Registers servers in Gemini configurations dynamically (AI-agnostic).
    Allows root access to fix 'path not allowed' errors for Ecosystem Map and manuals.
    """
    from microservice_toolbox.utils.mcp_ai_config import safe_load_and_repair_json
    vault_root = osPathAbspath(osPathJoin(script_dir, ".."))
    workspace_root = osPathAbspath(osPathJoin(vault_root, ".."))
    
    # 1. Check if RAG Engine option is available
    rag_dir = osPathJoin(vault_root, "09-RAG-Engine")
    rag_main_script = osPathJoin(rag_dir, "main.py")
    rag_core_server = osPathJoin(rag_dir, "src", "core", "server.py")
    has_rag = osPathExists(rag_dir) and (osPathExists(rag_main_script) or osPathExists(rag_core_server))
    obsidian_rag_config = None
    mcp_args = None
    
    if has_rag:
        # Resolve RAG server port dynamically from standalone.yaml or default to 8090
        rag_port = 8090
        try:
            import yaml
            yaml_path = osPathJoin(rag_dir, "standalone.yaml")
            if osPathExists(yaml_path):
                with open(yaml_path, 'r') as f:
                    ydata = yaml.safe_load(f)
                    mcp_conf = ydata.get("capabilities", {}).get("rag_engine", {}).get("mcp", {})
                    if mcp_conf.get("port"):
                        rag_port = int(mcp_conf.get("port"))
        except Exception:
            pass

        # Check if RAG server is running
        is_running = False
        import socket
        try:
            with socket.create_connection(("127.0.0.1", rag_port), timeout=1.0):
                is_running = True
        except Exception:
            is_running = False

        if not is_running:
            print("\n" + "⚠️" * 30)
            print(f"⚠️  RAG ENGINE SERVER IS NOT RUNNING ON PORT {rag_port}!")
            print("=" * 60)
            print("Please start the RAG Engine server in another terminal via:")
            print("  cd 09-RAG-Engine && .venv/bin/python main.py server")
            print("\nFALLBACK ENFORCED: The launcher will use standard filesystem MCP instead.")
            print("=" * 60)
            print("⚠️" * 30 + "\n")
            has_rag = False

    if has_rag:
        # Determine the Python virtual environment path dynamically:
        # Prioritize the RAG Engine's local virtualenv if it exists, otherwise fall back to the unified vault venv.
        rag_venv_python = osPathJoin(rag_dir, ".venv", "Scripts", "python.exe") if osName == "nt" else osPathJoin(rag_dir, ".venv", "bin", "python3")
        local_python = osPathJoin(vault_root, ".venv", "Scripts", "python.exe") if osName == "nt" else osPathJoin(vault_root, ".venv", "bin", "python3")
        rag_server_script = rag_main_script if osPathExists(rag_main_script) else rag_core_server
        
        if osPathExists(rag_venv_python):
            resolved_python = rag_venv_python
            print(f"📡 RAG using local RAG virtual environment: {resolved_python}")
        elif osPathExists(local_python):
            resolved_python = local_python
            print(f"📡 RAG using unified {osPathBasename(vault_root)} virtual environment: {resolved_python}")
        else:
            resolved_python = sysExecutable
            print(f"📡 RAG using system Python fallback: {resolved_python}")
            
        obsidian_rag_config = {
            "command": resolved_python,
            "args": [rag_server_script, "server"],
            "env": {
                "SQUAD_ACTIVE_MODE": str(mode_choice),
                "PYTHONPATH": rag_dir
            }
        }
    else:
        # Fallback to standard basic filesystem MCP server
        # --- Dynamic Context Exclusion Logic (The Firewall) ---
        global_excludes = {
            ".obsidian", ".git", ".gemini", ".codex", ".agents",
            "node_modules", "99-Humans", "quick-overview"
        }
        mode_excludes_map = {
            "1": {"01-Strategic-Nexus", "04-Rapid-Prototyping", "05-Fleet-Operation"},
            "2": {"01-Strategic-Nexus", "02-Business-BDD", "05-Fleet-Operation", "06-Microservices"},
            "3": {"01-Strategic-Nexus", "02-Business-BDD", "04-Rapid-Prototyping"},
            "4": set()
        }
        
        current_excludes = mode_excludes_map.get(mode_choice, set())
        allowed_dirs = [workspace_root, vault_root]
        
        try:
            for item in osListdir(vault_root):
                if item in global_excludes or item in current_excludes:
                    continue
                item_path = osPathJoin(vault_root, item)
                if osPathIsdir(item_path):
                    allowed_dirs.append(item_path)
        except Exception as e:
            print(f"⚠️ Warning: Could not scan vault_root for exclusions: {e}")
                
        mcp_args = ["-y", "@modelcontextprotocol/server-filesystem"] + allowed_dirs
    
    # 2. Update MCP configs (AI-Agnostic: Gemini and Antigravity)
    configs_to_update = [
        # (filepath, label)
        (osPathJoin(osPathExpanduser("~/.gemini"), "settings.json"), "Gemini Settings"),
        (osPathJoin(osPathExpanduser("~/.gemini/antigravity-cli"), "mcp_config.json"), "Antigravity CLI MCP Config"),
        (osPathJoin(osPathExpanduser("~/.gemini/antigravity-cli"), "settings.json"), "Antigravity CLI Settings"),
        (osPathJoin(osPathExpanduser("~/.gemini/antigravity-ide"), "mcp_config.json"), "Antigravity IDE MCP Config"),
        (osPathJoin(osPathExpanduser("~/.gemini/antigravity-ide"), "settings.json"), "Antigravity IDE Settings"),
        (osPathJoin(osPathExpanduser("~/.gemini/config"), "mcp_config.json"), "Shared MCP Config"),
        (osPathJoin(osPathExpanduser("~/.gemini-cli"), "mcp_config.json"), "Gemini CLI MCP Config"),
    ]
        
    for config_file, label in configs_to_update:
        config_dir = osPathDirname(config_file)
        if not osPathExists(config_dir):
            try:
                osMakedirs(config_dir, exist_ok=True)
            except Exception:
                continue # Skip if directory cannot be created
                
        settings = safe_load_and_repair_json(config_file, label)
                
        if "mcpServers" not in settings:
            settings["mcpServers"] = {}
            
        # Clean up old workspace_code_editor name
        settings["mcpServers"].pop("workspace_code_editor", None)
        
        if has_rag:
            # Unified RAG Server: register it, clean up standard filesystem MCP
            settings["mcpServers"]["obsidian_rag"] = obsidian_rag_config
            settings["mcpServers"].pop("obsidian_vault", None)
        else:
            # Fallback standard filesystem server: register it, clean up RAG
            settings["mcpServers"]["obsidian_vault"] = {
                "command": "npx",
                "args": mcp_args
            }
            settings["mcpServers"].pop("obsidian_rag", None)
            
        try:
            with open(config_file, 'w', encoding='utf-8') as f:
                jsonDump(settings, f, indent=2)
            print(f"✅ {label} configured successfully.")
        except Exception as e:
            print(f"⚠️ Warning: Could not write {label}: {e}")

    # 3. Non-destructive config validation and auto-repair check
    #    Mirrors the RAG Engine's startup validation (09-RAG-Engine/main.py).
    #    Ensures all .gemini config files have valid JSON and SSE-mode obsidian_rag entries.
    try:
        # Resolve MCP URL from the already-determined rag_port (defaults to 8090)
        _rag_port = rag_port if 'rag_port' in dir() else 8090
        mcp_url = "http://127.0.0.1:{0}/sse".format(_rag_port)

        paths_to_verify = [
            (osPathJoin(osPathExpanduser("~/.gemini"), "settings.json"), "Gemini Settings"),
            (osPathJoin(osPathExpanduser("~/.gemini/antigravity-cli"), "mcp_config.json"), "Antigravity CLI MCP Config"),
            (osPathJoin(osPathExpanduser("~/.gemini/antigravity-cli"), "settings.json"), "Antigravity CLI Settings"),
            (osPathJoin(osPathExpanduser("~/.gemini/antigravity-ide"), "mcp_config.json"), "Antigravity IDE MCP Config"),
            (osPathJoin(osPathExpanduser("~/.gemini/antigravity-ide"), "settings.json"), "Antigravity IDE Settings"),
            (osPathJoin(osPathExpanduser("~/.gemini/config"), "mcp_config.json"), "Shared MCP Config"),
            (osPathJoin(osPathExpanduser("~/.gemini-cli"), "mcp_config.json"), "Gemini CLI MCP Config"),
        ]
        for path, label in paths_to_verify:
            safe_load_and_repair_json(path, label, mcp_url)
    except Exception as e_verify:
        logger.warning("Could not run config validation check: {0}".format(e_verify))

# -----------------------------------------------------------------------------------------------

def run_preflight() -> bool:
    """
    ESSENTIAL PROCESS:
    Runs the full audit chain to ensure the brain is healthy before session start.
    Returns True when all governance scripts complete successfully.
    """
    workspace_root = osPathAbspath(osPathJoin(script_dir, "..", ".."))
    
    # Define fallback path candidates for each governance check
    governance_scripts = [
        (
            "preflight_check.py",
            [
                osPathJoin(script_dir.parent, "auditing", "preflight_check.py"),
                osPathJoin(script_dir, "Preflight-Check.py"),
                osPathJoin(workspace_root, "core-kms-brain", "Scripts", "Preflight-Check.py")
            ]
        ),
        (
            "brain_health_audit.py",
            [
                osPathJoin(script_dir.parent, "auditing", "brain_health_audit.py"),
                osPathJoin(script_dir, "Brain-Health-Audit.py"),
                osPathJoin(workspace_root, "core-kms-brain", "Scripts", "Brain-Health-Audit.py")
            ]
        )
    ]
    all_clean = True

    for name, paths in governance_scripts:
        target = None
        for path in paths:
            if osPathExists(path):
                target = path
                break
            
        if target:
            print(f"📡 Executing Governance Audit: {osPathBasename(target)}...")
            result = subprocessRun([get_vault_python(), target])
            if result.returncode != 0:
                print(f"❌ Governance audit failed: {osPathBasename(target)} returned {result.returncode}.")
                all_clean = False
        else:
            print(f"⚠️ Governance audit skipped: {name} not found.")

    return all_clean

def _check_single_repo(repo_info, exclusions):
    """Worker function for parallel git status checks."""
    repo_name = repo_info["name"]
    repo_path = repo_info["path"]
    is_vault = repo_info["is_vault"]
    
    try:
        result = subprocessRun(
            ["git", "status", "--porcelain"], 
            cwd=repo_path, capture_output=True, text=True, check=True
        )
        uncommitted = []
        for line in result.stdout.splitlines():
            if not line.strip():
                continue
            status_path = line[3:].strip()
            if " -> " in status_path:
                status_path = status_path.split(" -> ", 1)[1].strip()
            # Apply exclusions for the vault
            if is_vault:
                if status_path.endswith(".md"):
                    if any(x in status_path for x in exclusions):
                        continue
                    uncommitted.append(status_path)
            else:
                # Sibling repos: any uncommitted change matters
                if not any(x in status_path for x in exclusions):
                    uncommitted.append(status_path)
                    
        if uncommitted:
            return (repo_name, len(uncommitted))
    except Exception:
        pass
    return None

def check_session_health(mode_choice: str) -> None:
    """
    Checks if there are uncommitted changes across the entire fleet from a previous session.
    Enforces mode-specific rules for unclosed missions.
    """
    workspace_root = osPathAbspath(osPathJoin(script_dir, "..", ".."))
    vault_root = osPathAbspath(osPathJoin(script_dir, ".."))
    inventory_path = osPathJoin(vault_root, "05-Fleet-Operation", "00-Repo-Control", "inventory.json")
    
    repos_to_check = []
    
    # 1. Load fleet repositories from inventory
    if osPathExists(inventory_path):
        try:
            with open(inventory_path, 'r', encoding='utf-8') as f:
                data = jsonLoad(f)
                repositories = data.get("repositories", [])
                for repo in repositories:
                    repo_path_rel = repo.get("path")
                    repo_abs_path = osPathAbspath(osPathJoin(workspace_root, repo_path_rel))
                    if osPathExists(repo_abs_path) and osPathExists(osPathJoin(repo_abs_path, ".git")):
                        repos_to_check.append({
                            "name": repo.get("name"),
                            "path": repo_abs_path,
                            "is_vault": (repo.get("name") == "obsidian-brain" or repo_abs_path == vault_root)
                        })
        except Exception as e:
            print(f"⚠️ Warning: Failed to load inventory.json: {e}")
            
    # Fallback to checking vault if inventory is missing or empty
    if not repos_to_check:
        repos_to_check.append({
            "name": "obsidian-brain",
            "path": vault_root,
            "is_vault": True
        })
        
    EXCLUSIONS = [".git", ".obsidian", ".gemini", ".codex", ".agents", "Templates", "MODE-MANUAL.md"]
    
    print(f"📡 Auditing Fleet Health ({len(repos_to_check)} repositories)...")
    dirty_repos_info = []
    
    # Parallel execution for git status
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(_check_single_repo, repo, EXCLUSIONS) for repo in repos_to_check]
        for future in as_completed(futures):
            res = future.result()
            if res:
                dirty_repos_info.append(res)
            
    if dirty_repos_info:
        if mode_choice == "3":
            # Mode 3 - Strict Block
            print("\n" + "🛑"*30)
            print("🛑 CRITICAL GOVERNANCE VIOLATION: UNCLOSED MISSION DETECTED")
            print("="*60)
            print("The following repositories have uncommitted changes:")
            for repo_name, count in dirty_repos_info:
                print(f"  - {repo_name} ({count} file(s) dirty)")
            print("\nIn Mode 3 (Fleet-Commander), startup is STRICTLY BLOCKED to prevent multi-repository drift.")
            print(f"Please run 'python3 ./{osPathBasename(vault_root)}/08-Squad-Agent/close_mission.py' to verify and sign-off.")
            print("="*60)
            print("🛑"*30 + "\n")
            sysExit(1)
        
        elif mode_choice == "1":
            # Mode 1 - Strict Checkpoint Mandate (Improved Hardening)
            print("\n" + "⚠️"*30)
            print("⚠️  GOVERNANCE ALERT: UNCLOSED MISSION DETECTED")
            print("="*60)
            print("The following repositories have uncommitted changes:")
            for repo_name, count in dirty_repos_info:
                print(f"  - {repo_name} ({count} file(s) dirty)")
            print("\nMode 1 (Spec-First) REQUIRES a clean state for architectural integrity.")
            print(f"Mandate: Run 'python3 ./{osPathBasename(vault_root)}/08-Squad-Agent/close_mission.py' or stash changes.")
            print("="*60)
            print("⚠️"*30 + "\n")
            
            import sys
            if not sys.stdin.isatty():
                print("📡 Non-interactive environment detected. Skipping interactive block.")
            else:
                confirm = input("Ignore and start session anyway? (NOT RECOMMENDED) [y/N]: ").lower().strip()
                if confirm != 'y':
                    print("👋 Session aborted. Please secure your work before proceeding in Mode 1.")
                    sysExit(0)
                
        elif mode_choice == "2":
            # Mode 2 - Simple warning
            print("\n💡 NOTE: The following repositories have uncommitted changes from a previous session:")
            for repo_name, count in dirty_repos_info:
                print(f"  - {repo_name} ({count} file(s) dirty)")
            print("")

def regenerate_agents() -> None:
    """
    DATA FLOW:
    Triggers the multi-AI agent converter to ensure prompts are synchronized.
    """
    try:
        from src.fleet.convert_agents import main as sync_agents
        print("🔄 Synchronizing AI Squad Roles across adapters...")
        sync_agents()
    except Exception as e:
        print(f"⚠️ Warning: Failed to run agent prompt synchronisation in-process: {e}")

def _strip_frontmatter(text: str) -> str:
    if text.strip().startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            return parts[2].lstrip()
    return text

def generate_active_rituals(mode_choice: str) -> None:
    """
    DATA FLOW:
    Combines global rituals with mode-specific rituals into a single ACTIVE-RITUALS.md file.
    This file acts as the 'Preamble' that all AI roles are instructed to read.
    """
    rituals_dir = osPathJoin(vault_root, "00-AI-Orchestration", "Workflows", "Rituals")
    active_rituals_path = osPathJoin(vault_root, "00-AI-Orchestration", "Workflows", "ACTIVE-RITUALS.md")
    
    global_ritual = osPathJoin(rituals_dir, "Ritual-Global.md")
    mode_ritual = None
    
    if mode_choice == "1":
        mode_ritual = osPathJoin(rituals_dir, "Ritual-SpecFirst.md")
    elif mode_choice == "3":
        mode_ritual = osPathJoin(rituals_dir, "Ritual-Fleet.md")
        
    header = [
        "---",
        "microservice: ecosystem-core",
        "type: ritual",
        "status: active",
        "tags:",
        "- '#zone/0-orchestration'",
        "- '#tier/ritual'",
        "---",
        "# ⚡ ACTIVE SESSION RITUALS",
        f"> **Mode {mode_choice} Active** | Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "\n"
    ]
    
    content = header
    
    # 1. Add Global Ritual
    if osPathExists(global_ritual):
        with open(global_ritual, 'r', encoding='utf-8') as f:
            content.append(_strip_frontmatter(f.read()))
            content.append("\n---\n")
            
    # 2. Add Mode-Specific Ritual
    if mode_ritual and osPathExists(mode_ritual):
        with open(mode_ritual, 'r', encoding='utf-8') as f:
            content.append(_strip_frontmatter(f.read()))
            
    # 3. Add Strategic Memory (Anti-Backlog & Strategic Patterns)
    content.append("\n---\n")
    content.append("# 🧠 STRATEGIC MEMORY (ACTIVE DECISIONS & PATTERNS)\n")
    content.append("> Do NOT re-implement or debate rejected features listed in the Anti-Backlog. Follow standard Strategic Patterns.\n")
    
    anti_backlog_path = osPathJoin(vault_root, "01-Strategic-Nexus", "Anti-Backlog.md")
    if osPathExists(anti_backlog_path):
        try:
            with open(anti_backlog_path, 'r', encoding='utf-8') as f:
                content.append("## ❌ The Anti-Backlog (Rejected Choices)")
                content.append(_strip_frontmatter(f.read()))
                content.append("\n")
        except Exception as e:
            logger.warning(f"Could not read Anti-Backlog: {e}")
            
    patterns_path = osPathJoin(vault_root, "01-Strategic-Nexus", "Strategic", "Strategic-Patterns.md")
    if osPathExists(patterns_path):
        try:
            with open(patterns_path, 'r', encoding='utf-8') as f:
                content.append("## 🛠️ Strategic Patterns (Proven Abstractions)")
                content.append(_strip_frontmatter(f.read()))
                content.append("\n")
        except Exception as e:
            logger.warning(f"Could not read Strategic Patterns: {e}")
            
    try:
        with open(active_rituals_path, 'w', encoding='utf-8') as f:
            f.write("\n".join(content))
        print(f"✨ Generated session preamble: [[00-AI-Orchestration/Workflows/ACTIVE-RITUALS]] (Level: {mode_choice})")
    except Exception as e:
        print(f"⚠️ Warning: Could not generate ACTIVE-RITUALS.md: {e}")

def unlock_core_kms() -> None:
    """
    Restores write permissions to 07-Core-KMS to allow audits and updates.
    Excludes quick-overview (dynamic AST telemetry) and Git files.
    """
    vault_root = osPathAbspath(osPathJoin(script_dir, ".."))
    kms_dir = osPathJoin(vault_root, "07-Core-KMS")
    if not osPathExists(kms_dir):
        return
    print("🔓 Restoring write permissions to 07-Core-KMS for audit phase...")
    for root, dirs, files in osWalk(kms_dir):
        # Exclude quick-overview and git metadata from permission changes
        for exclude_dir in [".git", "quick-overview"]:
            if exclude_dir in dirs:
                dirs.remove(exclude_dir)
        for d in dirs:
            dir_path = osPathJoin(root, d)
            try:
                osChmod(dir_path, 0o755)
            except Exception:
                pass
        for f in files:
            if f.startswith(".git"):
                continue
            file_path = osPathJoin(root, f)
            try:
                osChmod(file_path, 0o644)
            except Exception:
                pass

def protect_core_kms() -> None:
    """
    Sets the 07-Core-KMS directory and files to read-only
    at the OS level to protect them against modifications.
    Excludes quick-overview (dynamic AST telemetry) and Git files.
    """
    vault_root = osPathAbspath(osPathJoin(script_dir, ".."))
    kms_dir = osPathJoin(vault_root, "07-Core-KMS")
    if not osPathExists(kms_dir):
        return
    print("🔒 Enforcing read-only permissions on 07-Core-KMS directory...")
    for root, dirs, files in osWalk(kms_dir):
        # Exclude quick-overview and git metadata from permission changes
        for exclude_dir in [".git", "quick-overview"]:
            if exclude_dir in dirs:
                dirs.remove(exclude_dir)
        for d in dirs:
            dir_path = osPathJoin(root, d)
            try:
                osChmod(dir_path, 0o555)
            except Exception:
                pass
        for f in files:
            if f.startswith(".git"):
                continue
            file_path = osPathJoin(root, f)
            try:
                osChmod(file_path, 0o444)
            except Exception:
                pass

def check_rag_attached() -> bool:
    """Returns True if the 09-RAG-Engine exists and a valid server entrypoint is available."""
    vault_root = osPathAbspath(osPathJoin(script_dir, ".."))
    rag_dir = osPathJoin(vault_root, "09-RAG-Engine")
    rag_main_script = osPathJoin(rag_dir, "main.py")
    rag_core_server = osPathJoin(rag_dir, "src", "core", "server.py")
    return osPathExists(rag_dir) and (osPathExists(rag_main_script) or osPathExists(rag_core_server))

# -----------------------------------------------------------------------------------------------

def check_environment() -> bool:
    """
    Verifies that the required Python environment is healthy and has necessary packages.
    """
    required_packages = ["yaml", "markdown", "dotenv"] # Add more as needed
    missing = []
    
    # We check the active environment (where we are running)
    import importlib.util
    
    for pkg in required_packages:
        if importlib.util.find_spec(pkg) is None:
            # Special case for pyyaml (import name is yaml)
            if pkg == "yaml" and importlib.util.find_spec("yaml") is not None:
                continue
            # Special case for python-dotenv (import name is dotenv)
            if pkg == "dotenv" and importlib.util.find_spec("dotenv") is not None:
                continue
            missing.append(pkg)
            
    if missing:
        print(f"⚠️ Warning: Missing required Python packages: {', '.join(missing)}")
        print(f"📡 Attempting auto-install into {get_vault_python()}...")
        try:
            # Try to auto-repair if possible
            pip_cmd = [get_vault_python(), "-m", "pip", "install"] + missing
            subprocessRun(pip_cmd, check=True)
            print("✅ Environment repaired successfully.")
            return True
        except Exception as e:
            print(f"❌ Error: Could not auto-repair environment: {e}")
            return False
    return True

# -----------------------------------------------------------------------------------------------

def ensure_background_services() -> None:
    """
    Checks if the web-interface (MFE portal) and tele-remote (Telegram gateway)
    services are running, and launches them in the background if they are not.
    Strictly enforces fail-fast dynamic port resolution via ecosystem config.
    """
    import socket
    from subprocess import Popen, DEVNULL
    
    workspace_root_path = Path(vault_root).parent
    config = get_config()
    
    # 1. Resolve & Check Web Interface (MFE Portal) via dynamic config (Fail-Fast)
    web_addr = config.get_listen_addr("web_interface")
    if not web_addr or ":" not in web_addr:
        logger.critical("Fatal: capabilities.web_interface.port is unresolvable from configuration (fail-fast violation).")
        raise RuntimeError("Fail-fast: Unresolvable capabilities.web_interface address in ecosystem config")
    web_host, web_port_str = web_addr.split(":", 1)
    web_port = int(web_port_str)
    
    web_running = False
    try:
        with socket.create_connection((web_host, web_port), timeout=0.5):
            web_running = True
    except Exception:
        web_running = False
        
    if not web_running:
        web_dir = workspace_root_path / "web-interface"
        web_bin = web_dir / "web-interface"
        if web_bin.exists():
            logger.info(f"🚀 Launching Web Interface (MFE Portal) on port {web_port} in background...")
            log_session_event("Launching Web Interface in background.")
            try:
                # Spawn in background, change directory to web_dir
                Popen(
                    [str(web_bin)],
                    cwd=str(web_dir),
                    stdout=DEVNULL,
                    stderr=DEVNULL
                )
            except Exception as e:
                logger.error(f"Failed to launch Web Interface: {e}")
        else:
            logger.warning(f"Web Interface binary not found at {web_bin}")
    else:
        logger.info(f"✅ Web Interface (MFE Portal) is already running on port {web_port}.")

    # 2. Resolve & Check Tele-Remote (Telegram gateway) via dynamic config (Fail-Fast)
    tele_addr = config.get_listen_addr("tele_remote")
    if not tele_addr or ":" not in tele_addr:
        logger.critical("Fatal: capabilities.tele_remote.port is unresolvable from configuration (fail-fast violation).")
        raise RuntimeError("Fail-fast: Unresolvable capabilities.tele_remote address in ecosystem config")
    tele_host, tele_port_str = tele_addr.split(":", 1)
    tele_port = int(tele_port_str)
    
    tele_running = False
    try:
        with socket.create_connection((tele_host, tele_port), timeout=0.5):
            tele_running = True
    except Exception:
        tele_running = False
        
    if not tele_running:
        tele_dir = workspace_root_path / "tele-remote"
        tele_bin = tele_dir / "bin" / "tele-remote"
        if tele_bin.exists():
            logger.info(f"🚀 Launching Tele-Remote (Telegram gateway) on port {tele_port} in background...")
            log_session_event("Launching Tele-Remote in background.")
            try:
                Popen(
                    [str(tele_bin)],
                    cwd=str(tele_dir),
                    stdout=DEVNULL,
                    stderr=DEVNULL
                )
            except Exception as e:
                logger.error(f"Failed to launch Tele-Remote: {e}")
        else:
            logger.warning(f"Tele-Remote binary not found at {tele_bin}")
    else:
        logger.info(f"✅ Tele-Remote is already running on port {tele_port}.")

# -----------------------------------------------------------------------------------------------

def start_engine() -> None:
    """
    FUNCTIONAL ANALYSE:
    Launches the Squad Control Daemon web server, gRPC server, and Telegram manager.
    """
    import asyncio
    import src.bootstrap as bootstrap
    from src.core.controller import CommandController
    from src.grpc_control.service import start_grpc_server
    from src.telegram.manager import SetupTelegram
    from src.web.server import start_async_server
    from microservice_toolbox.utils.process_lock import prevent_double_start

    logger = bootstrap.logger
    config = bootstrap.config

    prevent_double_start("squad_agent_daemon", logger=logger)
    logger.info("Initializing Squad Control Daemon...")

    # Create controller instance
    controller = CommandController(config=config, logger=logger)

    # 1. Resolve host and ports strictly via standard toolbox accessors (zero silent fallback)
    sa_rest_addr = config.get_listen_addr("squad_agent")
    sa_grpc_addr = config.get_grpc_listen_addr("squad_agent")

    host, port_str = sa_rest_addr.split(":")
    port = int(port_str)
    _, grpc_port_str = sa_grpc_addr.split(":")
    grpc_port = int(grpc_port_str)

    # 2. Get/Create Event Loop
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    # --- Pre-Session Audits & Agent Sync (Coherent Integration) ---
    active_mode = loop.run_until_complete(controller.get_active_mode())
    
    unlock_core_kms()
    archive_strat_files()
    
    logger.info("🔄 Synchronizing AI Squad role prompts...")
    regenerate_agents()
    # ---------------------------------------------------------------

    # Initialize global hybrid Event Bus
    from src.interfaces import DualSquadEventBus
    from microservice_toolbox.messaging.config import NatsConfig
    nats_cap = config.data.get("capabilities", {}).get("nats", {})
    nats_servers = nats_cap.get("servers")
    if not nats_servers:
        addr = config.get_listen_addr("nats")
        nats_servers = [f"nats://{addr}"] if addr else []
    client_id = nats_cap.get("client_id", "python_agent_squad")
    subject_prefix = nats_cap.get("subject_prefix", "bastien-antigravity")
    
    nats_cfg = NatsConfig(
        servers=nats_servers,
        client_id=client_id,
        subject_prefix=subject_prefix,
        connect_timeout=0.5,
        reconnect_wait=1.0,
        max_reconnects=1
    )
    event_bus = DualSquadEventBus(nats_cfg=nats_cfg, logger=logger)
    loop.run_until_complete(event_bus.connect())
    
    # Store event_bus reference on controller for REST usage
    controller.event_bus = event_bus

    # 3. Start gRPC Squad Control Server
    loop.create_task(start_grpc_server(controller, host, grpc_port, logger))

    # 4. Start Telegram dynamic menu client
    SetupTelegram(config, controller, logger)

    # 4.5. Start Collaborative Agent Daemons
    try:
        from src.agents.orchestrator import OrchestratorAgent
        from src.agents.developer import DeveloperAgent
        from src.agents.qa import QAAgent
        from src.agents.architect import ArchitectAgent
        from src.agents.codeindexer import CodeIndexerAgent
        from src.agents.docindexer import DocIndexerAgent
        from src.agents.docmaintainer import DocMaintainerAgent
        from src.agents.fleetarchitect import FleetArchitectAgent
        from src.agents.fleetcommander import FleetCommanderAgent
        from src.agents.oracle import OracleAgent
        from src.agents.patternsentinel import PatternSentinelAgent
        from src.agents.prototyper import PrototyperAgent
        from src.agents.purger import PurgerAgent
        from src.agents.sentinel import SentinelAgent
        
        agents = [
            OrchestratorAgent(config=config, logger=logger, pg_pool=controller.pool, event_bus=event_bus),
            DeveloperAgent(config=config, logger=logger, pg_pool=controller.pool, event_bus=event_bus),
            QAAgent(config=config, logger=logger, pg_pool=controller.pool, event_bus=event_bus),
            ArchitectAgent(config=config, logger=logger, pg_pool=controller.pool, event_bus=event_bus),
            CodeIndexerAgent(config=config, logger=logger, pg_pool=controller.pool, event_bus=event_bus),
            DocIndexerAgent(config=config, logger=logger, pg_pool=controller.pool, event_bus=event_bus),
            DocMaintainerAgent(config=config, logger=logger, pg_pool=controller.pool, event_bus=event_bus),
            FleetArchitectAgent(config=config, logger=logger, pg_pool=controller.pool, event_bus=event_bus),
            FleetCommanderAgent(config=config, logger=logger, pg_pool=controller.pool, event_bus=event_bus),
            OracleAgent(config=config, logger=logger, pg_pool=controller.pool, event_bus=event_bus),
            PatternSentinelAgent(config=config, logger=logger, pg_pool=controller.pool, event_bus=event_bus),
            PrototyperAgent(config=config, logger=logger, pg_pool=controller.pool, event_bus=event_bus),
            PurgerAgent(config=config, logger=logger, pg_pool=controller.pool, event_bus=event_bus),
            SentinelAgent(config=config, logger=logger, pg_pool=controller.pool, event_bus=event_bus),
        ]
        
        for agent in agents:
            loop.create_task(agent.start())
            
        logger.info(f"Collaborative AI squad: {len(agents)} agents successfully launched in background.")
    except Exception as e:
        logger.warning(f"Failed to start collaborative agents: {e}")

    # 5. Start FastAPI / Uvicorn Server
    server = start_async_server(controller, config, logger, host, port)
    
    # Run server forever
    loop.run_until_complete(server.serve())



# -----------------------------------------------------------------------------------------------

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Bastien-Antigravity AI Squad Command Center")
    parser.add_argument("--client", "-c", type=str, help="Specify the active client on startup.")
    parser.add_argument("--agent", "-a", type=str, help="Specify the active agent persona on startup.")
    args, unknown = parser.parse_known_args()

    if args.client:
        osEnviron["ACTIVE_CLIENT"] = args.client

    if args.agent:
        osEnviron["ACTIVE_AGENT"] = args.agent

    try:
        start_engine()
    except KeyboardInterrupt:
        import sys
        print("\n\n👋 Daemon terminated. Exiting.")
        sysExit(0)
    except Exception as e:
        logger.critical(f"Squad Agent Daemon fatal exception: {e}")
        try:
            import src.bootstrap as bootstrap
            from src.core.controller import CommandController
            ctrl = CommandController(config=bootstrap.config, logger=bootstrap.logger)
            ctrl.dispatch_alert_sync("CRITICAL", f"Squad Agent Daemon crashed: {e}", "squad", "fatal")
        except Exception:
            pass
        raise



if __name__ == "__main__":
    main()
