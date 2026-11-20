#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Monitors the Obsidian Vault recursively for pending tasks
and automates the handover to specific AI Agent personas (central and domain-vault).

DATA FLOW:
1. Scans the obsidian-brain recursively for markdown files with '#state/pending' or 'status: pending'.
2. Discovers custom domain personas dynamically via discover_vault_roles(vault_root).
3. Routes tasks semantically across central ROLE_MAP and discovered domain personas.
4. Transitions matched tasks to '#state/active' and publishes handovers to SquadEventBus.

KEY PARAMETERS:
- ROLE_MAP: Dictionary mapping core agent roles to their prompt files.
"""

import os
import sys
from pathlib import Path

try:
    from microservice_toolbox.utils.bootstrap import bootstrap_microservice
except ImportError:
    for parent in Path(__file__).resolve().parents:
        toolbox_py = parent / "microservice-toolbox" / "python"
        if toolbox_py.exists():
            sys.path.insert(0, str(toolbox_py))
            break
    from microservice_toolbox.utils.bootstrap import bootstrap_microservice

bootstrap_microservice(__file__, app_name="squad_agent_dispatcher")

from glob import glob as globGlob
from os.path import basename as osPathBasename, exists as osPathExists, join as osPathJoin
from pathlib import Path as pathPath
from re import findall as reFindall
from typing import Any as typeAny, Dict as typeDict, List as typeList, Optional as typeOptional

from src.agents.base_agent import discover_registered_domain_workspaces, slugify_role_name
from src.lib.orchestration_lib import get_logger, resolve_vault_and_workspace

# -----------------------------------------------------------------------------------------------

vault_root, workspace_root = resolve_vault_and_workspace(__file__)
WORKSPACE_ROOT = str(workspace_root)
OBSIDIAN_DIR = str(vault_root)

logger = get_logger("AgentDispatcher")

# Source of Truth Precedence
ROLE_PROMPT_SOURCES = [
    osPathJoin(OBSIDIAN_DIR, "07-Core-KMS", "Role-Prompts")
]

# Role to Prompt Filename Mapping (21 Ecosystem Squad Personas)
ROLE_MAP = {
    "oracle": "00-Oracle/Prompt-Chronos-Oracle.md",
    "orchestrator": "01-Orchestrator/Prompt-Orchestrator.md",
    "architect": "02-Architect/Prompt-Architect.md",
    "developer": "03-Developer/Prompt-Lead-Developer.md",
    "qa": "04-QA/Prompt-QA.md",
    "fleetarchitect": "05-FleetArchitect/Prompt-Fleet-Architect.md",
    "docmaintainer": "06-DocMaintainer/Prompt-DocMaintainer.md",
    "fleetcommander": "07-FleetCommander/Prompt-FleetCommander.md",
    "purger": "08-Purger/Mister-Straight-to-Goal.md",
    "sentinel": "09-Sentinel/Prompt-Sentinel.md",
    "docindexer": "10-DocIndexer/Prompt-DocIndexer.md",
    "codeindexer": "11-CodeIndexer/Prompt-CodeIndexer.md",
    "patternsentinel": "12-PatternSentinel/Prompt-Pattern-Sentinel.md",
    "prototyper": "13-Prototyper/Prompt-Prototyper.md",
    "debloatsentinel": "14-DebloatSentinel/Prompt-Debloat-Sentinel.md",
    # Developer Squad Specialists
    "pythonspecialist": "03-Developer/Squad/Python-Integration-Specialist.md",
    "gospecialist": "03-Developer/Squad/Go-Systems-Specialist.md",
    "rustspecialist": "03-Developer/Squad/Rust-Safety-Specialist.md",
    "cppspecialist": "03-Developer/Squad/CPP-Low-Latency-Specialist.md",
    "webuispecialist": "03-Developer/Squad/Web-UI-Specialist.md",
    "timescalespecialist": "03-Developer/Squad/Timescale-Data-Specialist.md",
    "vbaspecialist": "03-Developer/Squad/Excel-VBA-Specialist.md",
}

# Semantic Keywords for Fallback Scoring
SEMANTIC_KEYWORDS = {
    "developer": ["code", "implement", "fix", "feature", "refactor", "bug", "compile", "script", "import", "logic"],
    "qa": ["test", "verification", "assert", "acceptance criteria", "scenario", "audit", "coverage", "check", "run_test", "mock", "validation"],
    "architect": ["design", "specification", "adr", "diagram", "blueprint", "pattern", "uml", "hierarchy", "relationship", "concept"],
    "docmaintainer": ["documentation", "markdown", "readme", "links", "glossary", "moc", "write-up", "frontmatter", "wiki", "text"],
    "purger": ["delete", "remove", "clean", "purge", "orphan", "deprecated", "prune", "sweep", "dark matter"],
    "sentinel": ["security", "sandbox", "permissions", "access control", "compliance", "policy", "firewall", "authorization", "matrix"],
    "fleetcommander": ["deploy", "ci/cd", "fleet", "docker", "release", "orchestrate", "git hook", "bootstrap", "submodule"],
    "oracle": ["strategy", "nexus", "oracle", "future", "forecast", "insight", "strategic", "vision", "goal"],
    "orchestrator": ["coordinate", "delegation", "dispatcher", "dispatch", "assign", "workflow", "orchestrator", "schedule"],
    "docindexer": ["docindex", "documentation indexing", "rag vault indexing", "markdown indexing"],
    "codeindexer": ["codeindex", "ast indexing", "symbol table", "code search index"],
    "patternsentinel": ["pattern audit", "architectural pattern", "convention compliance", "rule alignment"],
    "prototyper": ["prototype", "mockup", "poc", "scratchpad", "experimentation"],
    "gospecialist": ["golang", "go", "goroutine", "safe-socket", "gopls", "channel", "cgo"],
    "pythonspecialist": ["python", "pytest", "fastapi", "pydantic", "pip", "venv"],
    "rustspecialist": ["rust", "cargo", "tokio", "log-server", "async rust", "borrow checker"],
    "cppspecialist": ["cpp", "c++", "cmake", "low-latency", "cgo bridge"],
    "webuispecialist": ["frontend", "web-interface", "openmfe", "css", "html", "javascript", "browser subagent"],
    "timescalespecialist": ["timescale", "sql", "postgres", "hypertables", "database migration", "pgvector"],
    "vbaspecialist": ["vba", "excel", "macro", "spreadsheet", "workbook"],
}

# -----------------------------------------------------------------------------------------------


def discover_vault_roles(vault_root: typeAny) -> typeDict[str, str]:
    """
    Discovers custom persona prompt definitions under <vault_root>/07-Core-KMS/Role-Prompts/
    and returns a mapping of slugified role_name -> relative prompt path.
    """
    prompts_dir = pathPath(vault_root).resolve() / "07-Core-KMS" / "Role-Prompts"
    if not prompts_dir.is_dir():
        return {}

    discovered: typeDict[str, str] = {}
    prompt_files: typeList[pathPath] = []
    try:
        prompt_files.extend(sorted(prompts_dir.glob("*/Prompt-*.md"), key=lambda p: str(p)))
        prompt_files.extend(sorted(prompts_dir.glob("Prompt-*.md"), key=lambda p: str(p)))
    except OSError as exc:
        logger.warning(f"AgentDispatcher : Failed scanning '{prompts_dir}': {exc}")
        return {}

    for prompt_path in prompt_files:
        if not prompt_path.is_file():
            continue
        role_slug = slugify_role_name(prompt_path.stem)
        if not role_slug or role_slug in discovered:
            continue
        discovered[role_slug] = str(prompt_path.relative_to(prompts_dir))
    return discovered


# -----------------------------------------------------------------------------------------------


def _role_keywords_from_prompt(*, role_slug: str, rel_prompt: str) -> typeList[str]:
    """Derives semantic matching keywords from a discovered domain role prompt filename."""
    stem = pathPath(rel_prompt).stem
    if stem.lower().startswith("prompt-"):
        stem = stem[7:]
    words = [w.lower() for w in reFindall(r"[A-Z]+(?=[A-Z][a-z]|\b)|[A-Z]?[a-z]+|[0-9]+", stem) if w]
    keywords = [f"@{role_slug}", f":{role_slug}", role_slug]
    if len(words) >= 2:
        keywords.append(" ".join(words))
    return list(dict.fromkeys(keywords))


# -----------------------------------------------------------------------------------------------


def get_role_prompt_path(role_key: str, *, vault_root: typeOptional[typeAny] = None) -> typeOptional[str]:
    """
    Finds the absolute path to a role prompt following Source of Truth precedence
    plus dynamic discovery in the target vault.
    """
    normalized_key = slugify_role_name(role_key)
    filename = ROLE_MAP.get(role_key) or ROLE_MAP.get(normalized_key)
    if filename:
        for source_dir in ROLE_PROMPT_SOURCES:
            full_path = osPathJoin(source_dir, filename)
            if osPathExists(full_path):
                return full_path

    candidate_vaults: typeList[pathPath] = []
    if vault_root is not None:
        candidate_vaults.append(pathPath(vault_root).resolve())
    candidate_vaults.append(pathPath(OBSIDIAN_DIR).resolve())
    for v_root in candidate_vaults:
        discovered = discover_vault_roles(v_root)
        rel_path = discovered.get(role_key) or discovered.get(normalized_key)
        if rel_path:
            full_path = v_root / "07-Core-KMS" / "Role-Prompts" / rel_path
            if full_path.is_file():
                return str(full_path)
    return None


# -----------------------------------------------------------------------------------------------


def parse_frontmatter(file_path: str) -> typeOptional[typeDict[str, typeAny]]:
    """Parses YAML frontmatter from a markdown file using a late import."""
    from yaml import safe_load as yamlSafeLoad

    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            try:
                frontmatter = yamlSafeLoad(parts[1])
                return frontmatter
            except Exception as e:
                logger.error(f"AgentDispatcher : Error parsing YAML in {file_path}: {e}")
    return None


# -----------------------------------------------------------------------------------------------


def route_task_semantically(
    task_content: str,
    default_role: typeOptional[str],
    *,
    vault_root: typeOptional[typeAny] = None,
) -> str:
    """
    Determines the best matching agent role by analyzing keywords and dynamically
    discovered custom domain personas in the active/registered vaults.
    """
    target_vault = pathPath(vault_root).resolve() if vault_root is not None else pathPath(OBSIDIAN_DIR).resolve()
    discovered_roles = discover_vault_roles(target_vault)

    if vault_root is None:
        for entry in discover_registered_domain_workspaces(
            central_vault_root=pathPath(OBSIDIAN_DIR).resolve(),
            central_workspace_root=pathPath(WORKSPACE_ROOT).resolve(),
            logger=logger,
        ):
            for role_slug, rel_prompt in discover_vault_roles(entry["vault_path"]).items():
                discovered_roles.setdefault(role_slug, rel_prompt)

    known_roles: typeDict[str, str] = {**ROLE_MAP, **discovered_roles}

    keyword_table: typeDict[str, typeList[str]] = {
        role: list(words) for role, words in SEMANTIC_KEYWORDS.items()
    }
    for role_slug, rel_prompt in discovered_roles.items():
        if role_slug not in ROLE_MAP:
            extra_kws = _role_keywords_from_prompt(role_slug=role_slug, rel_prompt=rel_prompt)
            keyword_table[role_slug] = list(dict.fromkeys(keyword_table.get(role_slug, []) + extra_kws))

    lower_content = task_content.lower()

    # Preserve explicitly declared custom domain role unless another role is explicitly @mentioned
    if default_role:
        default_slug = default_role if default_role in known_roles else slugify_role_name(default_role)
        if default_slug in discovered_roles and default_slug not in ROLE_MAP:
            explicit_other = [
                r for r in known_roles
                if r != default_slug and (f"@{r}" in lower_content or f":{r}" in lower_content)
            ]
            if not explicit_other:
                return default_slug

    scores = {role: 0 for role in keyword_table}

    for role, keywords in keyword_table.items():
        for keyword in keywords:
            scores[role] += lower_content.count(keyword)

    max_score = -1
    best_role = None
    for role, score in scores.items():
        if score > max_score:
            max_score = score
            best_role = role

    logger.info("AgentDispatcher : Semantic Routing Scores:")
    for role, score in sorted(scores.items(), key=lambda x: x[1], reverse=True)[:3]:
        logger.info(f"  - {role}: {score}")

    if best_role and max_score > 0:
        return best_role

    if default_role:
        if default_role in known_roles:
            return default_role
        default_slug = slugify_role_name(default_role)
        if default_slug in known_roles:
            return default_slug

    return "developer"


# -----------------------------------------------------------------------------------------------


def is_ignored_by_firewall(path_str: str, root_str: str) -> bool:
    """
    Checks if a path is ignored by looking for .aiignore, .geminiignore, or .mcpignore
    in the directory or any of its parents up to root_str.
    Also checks if the file itself has '#ai/ignore' in its first 1000 characters.
    """
    try:
        path = pathPath(path_str).resolve()
        root = pathPath(root_str).resolve()

        check_dir = path if path.is_dir() else path.parent
        while True:
            for ignore_name in [".aiignore", ".geminiignore", ".mcpignore"]:
                if (check_dir / ignore_name).exists():
                    return True
            if check_dir == root or check_dir.parent == check_dir:
                break
            check_dir = check_dir.parent
    except OSError as exc:
        logger.debug(f"AgentDispatcher : Firewall directory scan warning for '{path_str}': {exc}")

    try:
        if path_str.endswith(".md"):
            with open(path_str, "r", encoding="utf-8", errors="ignore") as f:
                head = f.read(1000)
                if "#ai/ignore" in head:
                    return True
    except OSError as exc:
        logger.debug(f"AgentDispatcher : Firewall file read warning for '{path_str}': {exc}")

    return False


# -----------------------------------------------------------------------------------------------


def process_vault_tasks() -> None:
    """
    Scans the entire vault for files with '#state/pending' tag and handles handover.
    """
    all_files = globGlob(osPathJoin(OBSIDIAN_DIR, "**", "*.md"), recursive=True)
    logger.info(f"AgentDispatcher : Scanning {len(all_files)} files for pending tasks...")

    for task_file in all_files:
        if ".git" in task_file or ".obsidian" in task_file:
            continue

        if is_ignored_by_firewall(task_file, OBSIDIAN_DIR):
            continue

        try:
            with open(task_file, "r", encoding="utf-8") as f:
                head = f.read(1000)
        except OSError as exc:
            logger.debug(f"AgentDispatcher : Skipping unreadable task file '{task_file}': {exc}")
            continue

        if "#state/pending" in head or "status: pending" in head:
            frontmatter = parse_frontmatter(task_file)
            if not frontmatter:
                continue

            try:
                with open(task_file, "r", encoding="utf-8") as f:
                    full_content = f.read()
            except OSError as exc:
                logger.debug(f"AgentDispatcher : Partial read fallback for '{task_file}': {exc}")
                full_content = head

            default_role = frontmatter.get("role")
            logger.info(f"AgentDispatcher : Pending task found: {osPathBasename(task_file)} (Declared Role: {default_role})")

            assigned_role = route_task_semantically(full_content, default_role)
            prompt_ref = get_role_prompt_path(assigned_role) or ROLE_MAP.get(assigned_role)
            logger.info(f"AgentDispatcher : Assigned Role: {assigned_role} (Prompt: {prompt_ref})")

            try:
                new_content = full_content.replace("status: pending", "status: active")
                new_content = new_content.replace("#state/pending", "#state/active")

                if assigned_role != default_role and default_role:
                    new_content = new_content.replace(f"role: {default_role}", f"role: {assigned_role}")
                elif "role:" not in new_content and "role :" not in new_content:
                    if new_content.startswith("---"):
                        parts = new_content.split("---", 2)
                        if len(parts) >= 3:
                            fm_lines = parts[1].splitlines()
                            fm_lines.append(f"role: {assigned_role}")
                            new_content = "---\n" + "\n".join(fm_lines) + f"\n---{parts[2]}"

                with open(task_file, "w", encoding="utf-8") as f:
                    f.write(new_content)
                try:
                    from src.interfaces import LocalEventBus
                    rel_task = pathPath(task_file).relative_to(OBSIDIAN_DIR)
                    dispatch_payload = {
                        "sender": "user",
                        "session_id": f"vault_task_{pathPath(task_file).stem}",
                        "content": f"@{assigned_role} Execute pending vault task `{rel_task}`:\n\n{full_content[:2000]}",
                        "source_brain_id": "obsidian-brain",
                        "reply_topic": "bastien-antigravity.squad.chat",
                    }
                    LocalEventBus.publish("bastien-antigravity.squad.chat", dispatch_payload)
                except Exception as pub_err:
                    logger.warning(f"AgentDispatcher : Event bus dispatch warning for {task_file}: {pub_err}")
                logger.info("AgentDispatcher : Handover complete. Transitioned to #state/active and dispatched to SquadEventBus.")
            except Exception as e:
                logger.error(f"AgentDispatcher : Error updating task: {e}")


# -----------------------------------------------------------------------------------------------


def main():
    logger.info("AgentDispatcher : Starting Agent Dispatcher (Semantic Mode)...")
    process_vault_tasks()
    logger.info("AgentDispatcher : Run complete.")


if __name__ == "__main__":
    main()
