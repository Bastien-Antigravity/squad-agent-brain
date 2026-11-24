#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Autonomous Agent Base Class and Tool Execution Engine for the AI Squad.
Provides unified LLM prompt compilation, tool calling, memory history retrieval,
cross-brain task_context handoffs, and reactive event bus message processing.

DATA FLOW:
1. Loads tiered role instructions (domain vault override -> central vault + central/domain AGENTS.md).
2. Listens for incoming chat messages via SquadEventBus (NATS or Local).
3. Compiles active prompt with session context, RAG augmentations, and conversation history.
4. Invokes LLM via Gemini SDK and executes workspace-scoped autonomous agent tool calls.
5. Publishes synthesized thoughts and responses with bounded task_context handoffs.

KEY PARAMETERS:
- role_name: Persona identifier matching Role-Prompts folder.
- prompt_file: Path to Markdown role prompt specification.
- event_bus: SquadEventBus instance for pub/sub message transit.
- pg_pool: Shared database connection pool for memory persistence.
- domain_vault_root: Optional external domain Obsidian vault root.
- domain_workspace_root: Optional external domain workspace directory root.
"""

from ast import AsyncFunctionDef as astAsyncFunctionDef, FunctionDef as astFunctionDef, parse as astParse, walk as astWalk
from asyncio import get_running_loop as asyncioGetRunningLoop, sleep as asyncioSleep, to_thread as asyncioToThread
from json import dumps as jsonDumps
from os import environ as osEnviron, getenv as osGetenv, walk as osWalk
from pathlib import Path as pathPath
from re import findall as reFindall, search as reSearch, split as reSplit, sub as reSub
from subprocess import TimeoutExpired as subprocessTimeoutExpired, run as subprocessRun
from typing import Any as typeAny, Dict as typeDict, List as typeList, Optional as typeOptional
from google import genai as googleGenai
from google.genai import errors as googleGenaiErrors, types as googleGenaiTypes
from yaml import safe_load as yamlSafeLoad

from src.interfaces import SquadEventBus
from src.lib.memory import RAGMemoryStore
from src.lib.orchestration_lib import resolve_vault_and_workspace

# -----------------------------------------------------------------------------------------------

_BLOCKED_WORKSPACE_ROOTS = frozenset({
    pathPath("/"),
    pathPath("/etc"),
    pathPath("/private/etc"),
    pathPath("/var"),
    pathPath("/private/var"),
    pathPath("/usr"),
    pathPath("/bin"),
    pathPath("/sbin"),
    pathPath("/System"),
    pathPath("/Library"),
    pathPath("/dev"),
    pathPath("/proc"),
    pathPath("/sys"),
    pathPath("/root"),
})

_RESERVED_PRIMARY_BRAINS = frozenset({"obsidian-brain", "root", "main"})

_READ_ONLY_ROLES = frozenset({
    "orchestrator",
    "architect",
    "patternsentinel",
    "debloatsentinel",
    "sentinel",
    "oracle",
    "codeindexer",
    "docindexer",
})

_MUTATING_TOOL_NAMES = frozenset({
    "write_workspace_file",
    "execute_shell_command",
    "scaffold_microservice",
    "generate_safe_by_design_spec",
    "sync_code_documentation",
    "index_brain_document",
    "purge_brain_index",
    "record_strategic_milestone",
})

_LIST_EXCLUDED_DIRS = frozenset({
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "target",
    "bin",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
})

_MAX_LISTED_FILES = 500

# -----------------------------------------------------------------------------------------------


def query_rag_engine(query: str, brain_id: str = "") -> str:
    """
    Queries the central RAG engine to retrieve architectural guidelines,
    codebase design patterns, or strategic decision history.

    Args:
        query: The semantic search query (e.g. 'REST API design standard').
        brain_id: Optional target brain namespace filter (e.g. 'obsidian-brain', 'trading-brain').
    """
    return ""


# -----------------------------------------------------------------------------------------------


def list_workspace_files(path: str = ".") -> str:
    """
    Lists relative file paths inside a directory of the active workspace so the agent
    can discover exact filenames without guessing paths.

    Args:
        path: Relative directory path from workspace root (e.g. '.' or 'notif-server').
    """
    return ""


# -----------------------------------------------------------------------------------------------


def read_workspace_file(path: str, fold_bodies: bool = False) -> str:
    """
    Reads the contents of a file in the active workspace directory.

    Args:
        path: Relative path to the file from workspace root (e.g. 'src/core/controller.py').
        fold_bodies: Whether to collapse large function and class bodies to save tokens (default False).
    """
    return ""


# -----------------------------------------------------------------------------------------------


def write_workspace_file(path: str, content: str) -> str:
    """
    Writes or edits the contents of a file in the active workspace directory.

    Args:
        path: Relative path to the file from workspace root.
        content: Complete contents to write to the file.
    """
    return ""


# -----------------------------------------------------------------------------------------------


def execute_shell_command(command: str) -> str:
    """
    Executes a shell command in the active workspace directory (e.g. compiling or linting).

    Args:
        command: The command line string to run.
    """
    return ""


# -----------------------------------------------------------------------------------------------


def slugify_role_name(raw_name: str) -> str:
    """Normalizes a prompt stem or role label into a canonical lowercase slug."""
    cleaned = reSub(r"^prompt[-_]+", "", str(raw_name).strip(), flags=0)
    if cleaned.lower().startswith("prompt"):
        cleaned = reSub(r"^prompt[-_]*", "", cleaned, flags=0)
    lowered = cleaned.lower()
    if lowered.startswith("prompt"):
        lowered = lowered[6:]
    return reSub(r"[^a-z0-9]", "", lowered)


# -----------------------------------------------------------------------------------------------


def _infer_domain_vault_path(*, workspace_path: pathPath, brain_id: str) -> pathPath:
    """Infers the Obsidian vault root inside a registered domain workspace."""
    if (workspace_path / "00-AI-Orchestration").is_dir() or (workspace_path / "07-Core-KMS" / "Role-Prompts").is_dir():
        return workspace_path
    named_child = (workspace_path / brain_id).resolve()
    if (named_child / "00-AI-Orchestration").is_dir() or (named_child / "07-Core-KMS" / "Role-Prompts").is_dir():
        return named_child
    try:
        for child in sorted(workspace_path.iterdir(), key=lambda p: p.name):
            if child.is_dir() and not child.name.startswith("."):
                if (child / "00-AI-Orchestration").is_dir() or (child / "07-Core-KMS" / "Role-Prompts").is_dir():
                    return child.resolve()
    except OSError:
        return workspace_path
    if named_child.is_dir():
        return named_child
    return workspace_path


# -----------------------------------------------------------------------------------------------


def _parse_extra_workspaces_env(raw_extra: str) -> typeList[str]:
    """Splits EXTRA_WORKSPACES supporting both comma and colon entry delimiters."""
    entries: typeList[str] = []
    for comma_part in raw_extra.split(","):
        chunk = comma_part.strip()
        if not chunk:
            continue
        for colon_part in reSplit(r":(?![\\/])", chunk):
            cleaned = colon_part.strip()
            if cleaned:
                entries.append(cleaned)
    return entries


# -----------------------------------------------------------------------------------------------


def discover_registered_domain_workspaces(
    *,
    central_vault_root: pathPath,
    central_workspace_root: typeOptional[pathPath] = None,
    logger: typeOptional[typeAny] = None,
) -> typeList[typeDict[str, typeAny]]:
    """
    Discovers external registered domain vaults/workspaces from:
    1. EXTRA_WORKSPACES_DIR (e.g. /workspaces in Docker)
    2. EXTRA_WORKSPACES (supporting both ',' and ':' delimiters)
    3. <central_vault_root>/09-RAG-Engine/workspaces.yaml (or EXTRA_WORKSPACES_CONFIG)
    """
    central_vault_resolved = pathPath(central_vault_root).resolve()
    discovered: typeDict[str, typeDict[str, typeAny]] = {}

    def _register(*, bid: str, ws_path: pathPath, v_path: pathPath) -> None:
        clean_bid = bid.strip()
        if not clean_bid or clean_bid in _RESERVED_PRIMARY_BRAINS:
            return
        ws_resolved = ws_path.resolve()
        v_resolved = v_path.resolve()
        if v_resolved == central_vault_resolved:
            return
        if not ws_resolved.is_dir() or not v_resolved.is_dir():
            return
        discovered[clean_bid] = {
            "brain_id": clean_bid,
            "workspace_path": ws_resolved,
            "vault_path": v_resolved,
        }

    # 1. Scan EXTRA_WORKSPACES_DIR
    raw_dir = osGetenv("EXTRA_WORKSPACES_DIR", "").strip()
    if raw_dir:
        base_dir = pathPath(raw_dir).resolve()
        if base_dir.is_dir():
            try:
                for domain in sorted(base_dir.iterdir(), key=lambda p: p.name):
                    if not domain.is_dir() or domain.name.startswith("."):
                        continue
                    domain_resolved = domain.resolve()
                    if (domain_resolved / "00-AI-Orchestration").is_dir() or (domain_resolved / "07-Core-KMS" / "Role-Prompts").is_dir():
                        _register(bid=domain_resolved.name, ws_path=domain_resolved, v_path=domain_resolved)
                        continue
                    for child in sorted(domain_resolved.iterdir(), key=lambda p: p.name):
                        if child.is_dir() and not child.name.startswith("."):
                            if (child / "00-AI-Orchestration").is_dir() or (child / "07-Core-KMS" / "Role-Prompts").is_dir():
                                _register(bid=child.name, ws_path=domain_resolved, v_path=child.resolve())
            except OSError as exc:
                if logger is not None:
                    logger.warning(f"DomainWorkspaceDiscovery : Failed scanning EXTRA_WORKSPACES_DIR '{raw_dir}': {exc}")

    # 2. Parse EXTRA_WORKSPACES (',' and ':' separated)
    raw_extra = osGetenv("EXTRA_WORKSPACES", "").strip()
    if raw_extra:
        for entry in _parse_extra_workspaces_env(raw_extra):
            if "=" in entry:
                bid_raw, path_raw = entry.split("=", 1)
                bid = bid_raw.strip()
                target = pathPath(path_raw.strip()).resolve()
            else:
                target = pathPath(entry).resolve()
                bid = target.name
            if bid and target.is_dir():
                v_path = _infer_domain_vault_path(workspace_path=target, brain_id=bid)
                _register(bid=bid, ws_path=target, v_path=v_path)

    # 3. Load <central_vault_root>/09-RAG-Engine/workspaces.yaml (and optional EXTRA_WORKSPACES_CONFIG)
    cfg_candidates: typeList[pathPath] = [
        (central_vault_resolved / "09-RAG-Engine" / "workspaces.yaml").resolve()
    ]
    cfg_env = osGetenv("EXTRA_WORKSPACES_CONFIG", "").strip()
    if cfg_env:
        env_cfg_path = pathPath(cfg_env).resolve()
        if env_cfg_path not in cfg_candidates:
            cfg_candidates.append(env_cfg_path)

    for cfg_path in cfg_candidates:
        try:
            raw_text = cfg_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            continue
        except OSError as exc:
            if logger is not None:
                logger.warning(f"DomainWorkspaceDiscovery : Failed reading '{cfg_path}': {exc}")
            continue

        try:
            data = yamlSafeLoad(raw_text) or {}
        except Exception as exc:
            if logger is not None:
                logger.warning(f"DomainWorkspaceDiscovery : Invalid YAML in '{cfg_path}': {exc}")
            continue

        entries = data.get("workspaces", []) if type(data) is dict else []
        if type(entries) is dict:
            entries = [{"brain_id": bid, **info} for bid, info in entries.items() if type(info) is dict]
        if type(entries) is not list:
            continue

        for item in entries:
            if type(item) is not dict:
                continue
            bid = str(item.get("brain_id", "")).strip()
            ws_str = str(item.get("workspace_path", "")).strip()
            v_str = str(item.get("vault_path", "")).strip() if item.get("vault_path") else ""
            if not bid or not ws_str:
                continue
            ws_path = pathPath(ws_str).resolve()
            if not ws_path.is_dir():
                continue
            v_path = pathPath(v_str).resolve() if v_str else _infer_domain_vault_path(workspace_path=ws_path, brain_id=bid)
            _register(bid=bid, ws_path=ws_path, v_path=v_path)

    return list(discovered.values())


# -----------------------------------------------------------------------------------------------


def _fold_python_code(content: str) -> str:
    """Folds python function/class bodies to show only signatures and docstrings."""
    try:
        tree = astParse(content)
        lines = content.splitlines()
        folded_intervals = []

        for node in astWalk(tree):
            if isinstance(node, (astFunctionDef, astAsyncFunctionDef)):
                start = node.lineno
                end = node.end_lineno
                if end and end - start > 5:
                    sig_line = lines[start - 1]
                    indent = len(sig_line) - len(sig_line.lstrip())
                    folded_intervals.append((start + 1, end, indent + 4))

        folded_intervals.sort(key=lambda x: x[0], reverse=True)
        for f_start, f_end, f_indent in folded_intervals:
            indent_str = " " * f_indent
            lines[f_start - 1 : f_end] = [f"{indent_str}# ... folded ..."]

        return "\n".join(lines)
    except Exception:
        return content


# -----------------------------------------------------------------------------------------------


def _fold_generic_code(content: str) -> str:
    """Folds braced language function bodies (JS/TS/Go/Rust/C++)."""
    lines = content.splitlines()
    folded_lines = []
    brace_count = 0
    in_fold = False
    fold_start_indent = 0

    for line in lines:
        stripped = line.strip()
        if in_fold:
            brace_count += stripped.count("{")
            brace_count -= stripped.count("}")
            if brace_count <= 0:
                in_fold = False
                indent = " " * fold_start_indent
                folded_lines.append(f"{indent}}} // ... folded ...")
            continue

        if "{" in line and any(keyword in line for keyword in ("function", "class", "impl", "fn", "struct", "interface", "public", "private")):
            brace_count = line.count("{") - line.count("}")
            if brace_count > 0:
                in_fold = True
                fold_start_indent = len(line) - len(line.lstrip())
                folded_lines.append(line.split("{")[0] + "{")
                folded_lines.append(" " * (fold_start_indent + 4) + "// ... folded ...")
                continue

        folded_lines.append(line)

    return "\n".join(folded_lines)


# -----------------------------------------------------------------------------------------------


class BaseAgent:
    """
    Base squad agent client handling SquadEventBus routing, PostgreSQL log indexing,
    tiered cross-brain prompt inheritance, and Google GenAI SDK model generation.
    """

    def __init__(
        self,
        *,
        role_name: str,
        prompt_file: str,
        config: typeAny,
        logger: typeAny,
        pg_pool: typeAny,
        event_bus: SquadEventBus,
        extra_prompt_files: typeOptional[typeList[str]] = None,
        target_brain_id: typeOptional[str] = None,
        domain_vault_root: typeOptional[pathPath] = None,
        domain_workspace_root: typeOptional[pathPath] = None,
        read_only: typeOptional[bool] = None,
    ):
        self.Name = self.__class__.__name__
        self.role_name = role_name
        self.prompt_file = prompt_file
        self.extra_prompt_files = extra_prompt_files or []
        self.config = config
        self.logger = logger
        self.pool = pg_pool
        self.event_bus = event_bus
        self.loop = None
        self.running = False
        self.domain_vault_root: typeOptional[pathPath] = (
            pathPath(domain_vault_root).resolve() if domain_vault_root else None
        )
        self.domain_workspace_root: typeOptional[pathPath] = (
            pathPath(domain_workspace_root).resolve() if domain_workspace_root else None
        )
        self.current_source_brain: typeOptional[str] = None
        self.current_task_context: typeOptional[typeDict[str, typeAny]] = None

        # Resolve target_brain_id (explicit kwarg > AppConfig > env > obsidian-brain)
        if isinstance(target_brain_id, str) and target_brain_id.strip():
            self.target_brain_id = target_brain_id.strip()
        else:
            squad_cap = self._get_squad_capability()
            cfg_brain = squad_cap.get("target_brain_id")
            if isinstance(cfg_brain, str) and cfg_brain.strip():
                self.target_brain_id = cfg_brain.strip()
            else:
                env_brain = osGetenv("TARGET_BRAIN_ID") or osGetenv("BRAIN_ID") or "obsidian-brain"
                self.target_brain_id = env_brain.strip() if env_brain.strip() else "obsidian-brain"

        self.brain_id = self.target_brain_id
        self.squad_chat_topic = (
            f"bastien-antigravity.{self.target_brain_id}.squad.chat"
            if self.target_brain_id != "obsidian-brain"
            else "bastien-antigravity.squad.chat"
        )

        # Initialise LLM configuration and client with live hot-reload support
        self.api_key = None
        self.model_name = None
        self.thinking_level = None
        self.thinking_budget = None
        self.client = None
        self._refresh_llm_config()
        if not self.client:
            self._init_genai_client()

        # Register dynamic config reload listener if supported by AppConfig
        on_update = getattr(self.config, "on_live_conf_update", None)
        if callable(on_update):
            try:
                on_update(lambda _: self._refresh_llm_config())
            except Exception as ex:
                self.logger.debug(f"{self.Name} : Could not bind on_live_conf_update for {self.role_name}: {ex}")

        # Load tiered system instruction
        self.system_instruction = self._load_system_prompt()

        # Role-scoped read-only boundary (auditors/indexers default to read-only)
        self.read_only: bool = (
            bool(read_only)
            if read_only is not None
            else (self.role_name in _READ_ONLY_ROLES)
        )
        if self.read_only:
            self.tools = [query_rag_engine, list_workspace_files, read_workspace_file]
        else:
            self.tools = [
                query_rag_engine,
                list_workspace_files,
                read_workspace_file,
                write_workspace_file,
                execute_shell_command,
            ]

    # -----------------------------------------------------------------------------------------------

    def enable_readonly_mode(self) -> None:
        """Enforces strict read-only tool permissions on this agent instance."""
        self.read_only = True
        self.tools = self._get_effective_tools()

    # -----------------------------------------------------------------------------------------------

    def _get_effective_tools(self) -> typeList[typeAny]:
        """Returns active LLM tools, stripping mutating tools whenever read_only is enabled."""
        if not self.read_only:
            return list(self.tools)
        return [
            t for t in self.tools if getattr(t, "__name__", "") not in _MUTATING_TOOL_NAMES
        ]

    # -----------------------------------------------------------------------------------------------

    def _get_squad_capability(self) -> typeDict[str, typeAny]:
        """Reads squad_agent capability settings from AppConfig data or accessor."""
        if self.config is None:
            return {}
        raw_data = getattr(self.config, "data", None)
        if type(raw_data) is dict:
            cap_slice = (raw_data.get("capabilities") or {}).get("squad_agent") or raw_data.get("squad_agent")
            if type(cap_slice) is dict:
                return cap_slice
        get_cap = getattr(self.config, "get_capability", None)
        if callable(get_cap):
            cap = get_cap("squad_agent")
            if type(cap) is dict:
                return cap
        return {}

    # -----------------------------------------------------------------------------------------------

    def _read_optional_text(self, file_path: pathPath) -> typeOptional[str]:
        """Directly reads an optional text file without a TOCTOU pre-check."""
        try:
            return file_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        except OSError as exc:
            self.logger.warning(f"{self.Name} : Failed reading '{file_path}': {exc}")
            return None

    # -----------------------------------------------------------------------------------------------

    def _load_system_prompt(self) -> str:
        """
        Compiles the agent role's complete system instruction via tiered inheritance:
        1. Domain prompt (if domain_vault_root has prompt_file, or absolute prompt_file) else central Role-Prompts.
        2. Central Workspace Root AGENTS.md (Non-Negotiable Engineering & Language Invariants).
        3. External Domain Workspace AGENTS.md (from domain_workspace_root or active task_context).
        4. Active Session Rituals (00-AI-Orchestration/Workflows/ACTIVE-RITUALS.md).
        5. Optional specialist appendices (e.g. Squad/*.md for DeveloperAgent).
        """
        vault_root, workspace_root = resolve_vault_and_workspace(__file__)
        sections: typeList[str] = []

        # 1. Tiered role prompt lookup (domain vault override -> central vault)
        prompt_text: typeOptional[str] = None
        prompt_candidate = pathPath(self.prompt_file)
        if prompt_candidate.is_absolute():
            prompt_text = self._read_optional_text(prompt_candidate)
        if prompt_text is None and self.domain_vault_root is not None:
            domain_prompt_path = self.domain_vault_root / "07-Core-KMS" / "Role-Prompts" / self.prompt_file
            prompt_text = self._read_optional_text(domain_prompt_path)
        if prompt_text is None:
            central_prompt_path = vault_root / "07-Core-KMS" / "Role-Prompts" / self.prompt_file
            prompt_text = self._read_optional_text(central_prompt_path)
        if prompt_text is not None:
            sections.append(prompt_text)
        else:
            sections.append(f"You are the {self.role_name} AI squad agent.")

        # 2. Central Bastien-Antigravity AGENTS.md (always included)
        central_agents_text = self._read_optional_text(workspace_root / "AGENTS.md")
        if central_agents_text is not None:
            sections.append(central_agents_text)

        # 3. Domain Workspace AGENTS.md (from active task_context or domain_workspace_root)
        ctx = self.current_task_context or {}
        active_ws_raw = ctx.get("target_workspace_path")
        domain_ws_candidates: typeList[pathPath] = []
        if isinstance(active_ws_raw, str) and active_ws_raw.strip():
            domain_ws_candidates.append(pathPath(active_ws_raw.strip()).resolve())
        if self.domain_workspace_root is not None:
            resolved_domain_ws = self.domain_workspace_root.resolve()
            if resolved_domain_ws not in domain_ws_candidates:
                domain_ws_candidates.append(resolved_domain_ws)

        central_ws_resolved = workspace_root.resolve()
        for domain_ws in domain_ws_candidates:
            if domain_ws == central_ws_resolved:
                continue
            domain_agents_text = self._read_optional_text(domain_ws / "AGENTS.md")
            if domain_agents_text is not None:
                sections.append(f"# Domain Workspace Rules ({domain_ws.name}/AGENTS.md)\n\n{domain_agents_text}")
                break

        # 4. Active Session Rituals (domain vault or central vault)
        active_rituals_text: typeOptional[str] = None
        if self.domain_vault_root is not None:
            active_rituals_text = self._read_optional_text(
                self.domain_vault_root / "00-AI-Orchestration" / "Workflows" / "ACTIVE-RITUALS.md"
            )
        if active_rituals_text is None:
            active_rituals_text = self._read_optional_text(
                vault_root / "00-AI-Orchestration" / "Workflows" / "ACTIVE-RITUALS.md"
            )
        if active_rituals_text is not None:
            sections.append(active_rituals_text)

        # 5. Specialist appendices
        for extra_rel in getattr(self, "extra_prompt_files", []):
            extra_text = None
            if self.domain_vault_root is not None:
                extra_text = self._read_optional_text(
                    self.domain_vault_root / "07-Core-KMS" / "Role-Prompts" / extra_rel
                )
            if extra_text is None:
                extra_text = self._read_optional_text(
                    vault_root / "07-Core-KMS" / "Role-Prompts" / extra_rel
                )
            if extra_text is not None:
                sections.append(extra_text)

        try:
            from src.lib.task_decomposer import CANONICAL_TOOLBOX_REMINDERS
            guardrails_block = (
                "# 🛡️ CANONICAL ECOSYSTEM & ANTI-BLOAT GUARDRAILS (MANDATORY)\n"
                "1. **Complexity Gate**: Never modify more than 2 files in a single turn. If a request spans >2 files or >2 architectural layers, split it into sequential atomic steps.\n"
                + "\n".join(f"- {r}" for r in CANONICAL_TOOLBOX_REMINDERS)
            )
            sections.append(guardrails_block)
        except Exception as exc:
            self.logger.debug(f"{self.Name} : Could not load CANONICAL_TOOLBOX_REMINDERS: {exc}")

        return "\n\n---\n\n".join(sections)

    # -----------------------------------------------------------------------------------------------

    def _refresh_llm_config(self) -> None:
        """Dynamically re-reads LLM configuration from config capability or environment for live hot-reload."""
        cap = self._get_squad_capability()

        # 1. Hot-reload model name (exact name, default: gemini-3.8-flash)
        env_model = osGetenv("GEMINI_MODEL")
        if env_model:
            new_model = env_model
        elif cap.get("gemini_model"):
            new_model = cap["gemini_model"]
        else:
            new_model = getattr(self, "model_name", None) or "gemini-3.8-flash"

        new_model_str = str(new_model).strip()
        if getattr(self, "model_name", None) and self.model_name != new_model_str:
            self.logger.info(
                f"{self.Name} : Hot-reloaded model from '{self.model_name}' to '{new_model_str}' without restarting process."
            )
        self.model_name = new_model_str

        # 2. Hot-reload thinking configuration
        env_tl = osGetenv("GEMINI_THINKING_LEVEL")
        self.thinking_level = env_tl if env_tl else (cap.get("thinking_level") or getattr(self, "thinking_level", None))

        env_tb = osGetenv("GEMINI_THINKING_BUDGET")
        self.thinking_budget = env_tb if env_tb else (cap.get("thinking_budget") or getattr(self, "thinking_budget", None))

        # 3. Hot-reload API key and client if updated dynamically
        target_key = osGetenv("GEMINI_API_KEY")
        if not target_key and cap.get("gemini_api_key"):
            raw_key = cap.get("gemini_api_key")
            decrypt_fn = getattr(self.config, "decrypt_secret", None)
            try:
                target_key = decrypt_fn(raw_key) if callable(decrypt_fn) else raw_key
            except Exception as e:
                self.logger.error(f"{self.Name} : Failed to decrypt updated gemini_api_key for {self.role_name}: {e}")

        if target_key and target_key != getattr(self, "api_key", None):
            self.api_key = target_key
            self._init_genai_client()
        elif not hasattr(self, "api_key"):
            self.api_key = target_key

    # -----------------------------------------------------------------------------------------------

    def _init_genai_client(self) -> None:
        """Initialises or updates the Google GenAI Client with active credentials."""
        raw_data = getattr(self.config, "data", None)
        if type(raw_data) is dict and raw_data.get("genai_client"):
            self.client = raw_data["genai_client"]
            self.logger.info(f"{self.Name} : Re-using shared Google AI Studio Client from config for {self.role_name}.")
        elif self.api_key:
            try:
                self.client = googleGenai.Client(api_key=self.api_key)
                self.logger.info(f"{self.Name} : Initialised Google AI Studio Client using GEMINI_API_KEY for {self.role_name}.")
                if type(raw_data) is dict:
                    raw_data["genai_client"] = self.client
            except Exception as e:
                self.logger.error(f"{self.Name} : Failed to initialise Google AI Studio Client for {self.role_name}: {e}")
        else:
            self.client = None

    # -----------------------------------------------------------------------------------------------

    async def start(self) -> None:
        """Registers the agent message consumer loop."""
        self.running = True
        self.loop = asyncioGetRunningLoop()

        async def msg_cb(payload):
            try:
                await self.on_chat_message(payload)
            except Exception as e:
                self.logger.error(f"{self.Name} : Agent {self.role_name} failed to handle incoming message: {e}")

        await self.event_bus.subscribe(self.squad_chat_topic, callback=msg_cb, role=self.role_name)
        self.logger.info(
            f"{self.Name} : Agent {self.role_name} listening on event_bus topic '{self.squad_chat_topic}' for role '{self.role_name}'"
        )

    # -----------------------------------------------------------------------------------------------

    async def stop(self) -> None:
        """Clean shut down."""
        self.running = False

    # -----------------------------------------------------------------------------------------------

    async def on_chat_message(self, payload: typeDict[str, typeAny]) -> None:
        """Callback invoked when a new message arrives in the room."""
        sender = payload.get("sender")
        session_id = payload.get("session_id")
        content = payload.get("content")

        if not session_id or not content or sender == self.role_name:
            return

        raw_task_context = payload.get("task_context")
        task_context = dict(raw_task_context) if type(raw_task_context) is dict else None

        is_orchestrator = self.role_name == "orchestrator"
        lower_content = content.lower()
        is_addressed = f"@{self.role_name}" in lower_content or f":{self.role_name}" in lower_content

        # Safeguard: Orchestrator coordinates on user input, or on bounded task_context handoffs (hops < 3)
        if is_orchestrator and sender != "user":
            if not task_context:
                return
            try:
                hops = int(task_context.get("handoff_hops", 0))
            except (TypeError, ValueError):
                return
            if hops >= 3:
                return
            if "@" in lower_content and not is_addressed:
                return

        if not is_orchestrator and not is_addressed:
            return

        reply_topic = payload.get("reply_topic") or payload.get("source_topic") or self.squad_chat_topic
        source_brain = (
            payload.get("source_brain_id")
            or (task_context.get("target_brain_id") if task_context else None)
            or self.target_brain_id
        )
        self.logger.info(
            f"{self.Name} : Agent {self.role_name} processing message from {sender} in session {session_id} (reply_topic: {reply_topic})"
        )
        await self.think_and_respond(
            session_id,
            reply_topic=reply_topic,
            source_brain=source_brain,
            task_context=task_context,
            fallback_message=content,
            fallback_sender=sender or "user",
        )

    # -----------------------------------------------------------------------------------------------

    def _compile_active_instruction(self) -> str:
        """Compiles system instruction with dynamic task_context details when active."""
        if not self.current_task_context:
            return self.system_instruction
        base_instruction = self._load_system_prompt()
        ctx_json = jsonDumps(self.current_task_context, indent=2, default=str)
        return (
            f"{base_instruction}\n\n---\n\n"
            f"# ACTIVE CROSS-BRAIN TASK CONTEXT\n"
            f"Use this exact context for target brain RAG lookups, workspace reads/writes, scaffolding, and handoffs:\n"
            f"```json\n{ctx_json}\n```"
        )

    # -----------------------------------------------------------------------------------------------

    async def _publish_agent_response(
        self,
        *,
        session_id: str,
        answer_text: str,
        tool_calls_data: typeList[typeDict[str, typeAny]],
        publish_topic: str,
        source_brain: typeOptional[str] = None,
    ) -> None:
        """Publishes response to reply_topic and any cross-brain @brain:role targets with incremented handoff_hops."""
        payload_data: typeDict[str, typeAny] = {
            "sender": self.role_name,
            "session_id": session_id,
            "content": answer_text,
            "tool_calls": tool_calls_data,
            "source_brain_id": source_brain or self.target_brain_id or "obsidian-brain",
            "reply_topic": publish_topic,
        }
        if self.current_task_context is not None:
            outgoing_ctx = dict(self.current_task_context)
            if "@" in answer_text:
                try:
                    current_hops = int(outgoing_ctx.get("handoff_hops", 0))
                except (TypeError, ValueError):
                    current_hops = 0
                outgoing_ctx["handoff_hops"] = current_hops + 1
            payload_data["task_context"] = outgoing_ctx

        await self.event_bus.publish(publish_topic, payload_data)

        # Cross-brain @brain:role handoff routing (e.g., @obsidian-brain:orchestrator)
        cross_mentions = reFindall(r"@([a-zA-Z0-9_-]+):([a-zA-Z0-9_-]+)", answer_text)
        forwarded_topics = {publish_topic}
        for target_brain, _target_role in cross_mentions:
            clean_brain = target_brain.strip().lower()
            cross_topic = (
                "bastien-antigravity.squad.chat"
                if clean_brain in _RESERVED_PRIMARY_BRAINS
                else f"bastien-antigravity.{clean_brain}.squad.chat"
            )
            if cross_topic not in forwarded_topics:
                forwarded_topics.add(cross_topic)
                cross_payload = dict(payload_data)
                cross_payload["reply_topic"] = cross_topic
                await self.event_bus.publish(cross_topic, cross_payload)

    # -----------------------------------------------------------------------------------------------

    async def think_and_respond(
        self,
        session_id: str,
        reply_topic: typeOptional[str] = None,
        source_brain: typeOptional[str] = None,
        task_context: typeOptional[typeDict[str, typeAny]] = None,
        fallback_message: typeOptional[str] = None,
        fallback_sender: str = "user",
    ) -> None:
        """Queries Gemini using conversation logs database history and broadcasts response."""
        self._refresh_llm_config()
        self.current_source_brain = source_brain
        self.current_task_context = dict(task_context) if type(task_context) is dict else None
        publish_topic = reply_topic or self.squad_chat_topic

        try:
            if not self.client:
                self.logger.info(f"{self.Name} : Agent {self.role_name} using mock offline response (Gemini API key is missing).")
                await self._run_mock_think_and_respond(
                    session_id,
                    reply_topic=publish_topic,
                    source_brain=source_brain,
                    task_context=self.current_task_context,
                    fallback_message=fallback_message,
                )
                return

            # 1. Fetch chat history from postgres (or in-memory fallback when pg_pool is None)
            history = await self._fetch_history(session_id)
            if not history and fallback_message:
                history = [{"sender": fallback_sender, "content": fallback_message, "tool_calls": []}]

            # 2. Convert to Gemini Content types
            contents = []
            for log in history:
                role = "user" if log["sender"] == "user" else "model"
                content_text = log["content"]
                if role == "model":
                    content_text = f"[{log['sender']}]: {log['content']}"
                contents.append(
                    googleGenaiTypes.Content(role=role, parts=[googleGenaiTypes.Part.from_text(text=content_text)])
                )

            # 3. Call generation
            try:
                self.logger.info(f"{self.Name} : Agent {self.role_name} invoking model generate_content...")

                config_params: typeDict[str, typeAny] = {
                    "system_instruction": self._compile_active_instruction(),
                }
                effective_tools = self._get_effective_tools()
                if effective_tools:
                    config_params["tools"] = effective_tools

                # Support Gemini Thinking models (e.g. Flash Thinking Level: HIGH)
                if getattr(self, "thinking_level", None):
                    tl = getattr(googleGenaiTypes.ThinkingLevel, str(self.thinking_level).upper(), None)
                    if tl:
                        config_params["thinking_config"] = googleGenaiTypes.ThinkingConfig(thinking_level=tl)
                elif getattr(self, "thinking_budget", None):
                    try:
                        tb = int(self.thinking_budget)
                        config_params["thinking_config"] = googleGenaiTypes.ThinkingConfig(thinking_budget=tb)
                    except (ValueError, TypeError) as tb_err:
                        self.logger.warning(f"{self.Name} : Invalid thinking_budget '{self.thinking_budget}': {tb_err}")

                response = await asyncioToThread(
                    self.client.models.generate_content,
                    model=self.model_name,
                    contents=contents,
                    config=googleGenaiTypes.GenerateContentConfig(**config_params),
                )

                answer_text = response.text or ""
                tool_calls_data: typeList[typeDict[str, typeAny]] = []

                # Turn budget loop for parallel tool calls and multi-turn execution
                loop_turn = 0
                MAX_TOOL_TURNS = 10
                current_response = response

                while loop_turn < MAX_TOOL_TURNS:
                    function_calls = []
                    if current_response.candidates and current_response.candidates[0].content.parts:
                        for part in current_response.candidates[0].content.parts:
                            if part.function_call:
                                function_calls.append(part)

                    if not function_calls:
                        break

                    loop_turn += 1
                    self.logger.info(
                        f"{self.Name} : Agent {self.role_name} processing {len(function_calls)} parallel tool calls (turn {loop_turn}/{MAX_TOOL_TURNS})"
                    )
                    user_parts = []
                    for part in function_calls:
                        call = part.function_call
                        self.logger.info(f"{self.Name} : Agent {self.role_name} executing tool call: {call.name}")
                        tool_result = await self.execute_tool(call.name, dict(call.args))

                        tool_calls_data.append({
                            "name": call.name,
                            "args": dict(call.args),
                            "result": tool_result,
                        })

                        user_parts.append(googleGenaiTypes.Part(
                            function_response=googleGenaiTypes.FunctionResponse(
                                name=call.name,
                                response={"result": tool_result},
                            ),
                            thought_signature=part.thought_signature,
                        ))

                    contents.append(current_response.candidates[0].content)
                    contents.append(googleGenaiTypes.Content(role="user", parts=user_parts))

                    current_response = await asyncioToThread(
                        self.client.models.generate_content,
                        model=self.model_name,
                        contents=contents,
                        config=googleGenaiTypes.GenerateContentConfig(**config_params),
                    )
                    answer_text = current_response.text or ""
                else:
                    self.logger.warning(f"{self.Name} : Agent {self.role_name} exceeded MAX_TOOL_TURNS limit of {MAX_TOOL_TURNS}")
                    answer_text = f"⚠️ [System Alert]: Agent exceeded maximum tool execution turns ({MAX_TOOL_TURNS}). Execution halted."

                if answer_text:
                    await self._save_log(session_id, answer_text, tool_calls_data)
                    await self._publish_agent_response(
                        session_id=session_id,
                        answer_text=answer_text,
                        tool_calls_data=tool_calls_data,
                        publish_topic=publish_topic,
                        source_brain=self.target_brain_id,
                    )
            except googleGenaiErrors.APIError as e:
                err_str = str(e).lower()
                if getattr(e, "code", None) == 404 or "not found" in err_str or "not_found" in err_str:
                    err_msg = f"❌ [Model Error]: Model '{self.model_name}' was not found online on Google AI Studio. Please verify the exact model identifier."
                    self.logger.error(f"{self.Name} : Agent {self.role_name}: {err_msg} (Details: {e})")
                else:
                    err_msg = f"⚠️ [System Alert]: Agent '{self.role_name}' Google GenAI API error: {e}"
                    self.logger.error(f"{self.Name} : Agent {self.role_name} API error: {e}")
                try:
                    await self._publish_agent_response(
                        session_id=session_id,
                        answer_text=err_msg,
                        tool_calls_data=[],
                        publish_topic=publish_topic,
                        source_brain=self.target_brain_id,
                    )
                except Exception as publish_err:
                    self.logger.error(f"{self.Name} : Failed to publish error alert for {self.role_name}: {publish_err}")
            except Exception as e:
                err_str = str(e).lower()
                if "not found" in err_str or "not_found" in err_str or "404" in err_str:
                    err_msg = f"❌ [Model Error]: Model '{self.model_name}' was not found online on Google AI Studio. Please verify the exact model identifier."
                else:
                    err_msg = f"⚠️ [System Alert]: Agent '{self.role_name}' failed during generation loop: {e}"
                self.logger.error(f"{self.Name} : Agent {self.role_name} failed during LLM generation loop: {e}")
                try:
                    await self._publish_agent_response(
                        session_id=session_id,
                        answer_text=err_msg,
                        tool_calls_data=[],
                        publish_topic=publish_topic,
                        source_brain=self.target_brain_id,
                    )
                except Exception as publish_err:
                    self.logger.error(f"{self.Name} : Failed to publish error alert for {self.role_name}: {publish_err}")
        finally:
            self.current_source_brain = None
            self.current_task_context = None

    # -----------------------------------------------------------------------------------------------

    def _is_valid_domain_workspace(
        self,
        *,
        candidate: pathPath,
        central_vault_root: pathPath,
        central_workspace_root: pathPath,
    ) -> bool:
        """Validates that candidate is an existing non-root, non-system domain workspace directory."""
        if candidate in _BLOCKED_WORKSPACE_ROOTS or candidate == candidate.parent:
            return False
        for blocked in (
            pathPath("/etc"),
            pathPath("/private/etc"),
            pathPath("/System"),
            pathPath("/usr"),
            pathPath("/bin"),
            pathPath("/sbin"),
        ):
            if candidate == blocked or blocked in candidate.parents:
                return False
        if not candidate.is_dir():
            return False
        if candidate == central_workspace_root:
            return True
        if self.domain_workspace_root is not None and candidate == self.domain_workspace_root.resolve():
            return True

        registered = discover_registered_domain_workspaces(
            central_vault_root=central_vault_root,
            central_workspace_root=central_workspace_root,
            logger=self.logger,
        )
        if registered:
            for entry in registered:
                ws_p = entry["workspace_path"].resolve()
                v_p = entry["vault_path"].resolve()
                if candidate == ws_p or candidate == v_p:
                    return True
            extra_dir_raw = osGetenv("EXTRA_WORKSPACES_DIR", "").strip()
            if extra_dir_raw:
                extra_dir = pathPath(extra_dir_raw).resolve()
                if extra_dir in candidate.parents and candidate != extra_dir:
                    return True
            return False

        if candidate == pathPath.home().resolve():
            return False
        return True

    # -----------------------------------------------------------------------------------------------

    def _resolve_active_workspace_root(self) -> pathPath:
        """
        Resolves the active workspace root for file/shell operations:
        1. Validated task_context['target_workspace_path'] (never '/')
        2. Agent's domain_workspace_root
        3. Central Bastien-Antigravity workspace_root
        """
        central_vault_root, central_workspace_root = resolve_vault_and_workspace(__file__)
        central_ws_resolved = central_workspace_root.resolve()

        ctx = self.current_task_context or {}
        raw_target_ws = ctx.get("target_workspace_path")
        if isinstance(raw_target_ws, str) and raw_target_ws.strip():
            candidate = pathPath(raw_target_ws.strip()).resolve()
            if self._is_valid_domain_workspace(
                candidate=candidate,
                central_vault_root=central_vault_root.resolve(),
                central_workspace_root=central_ws_resolved,
            ):
                return candidate
            self.logger.warning(
                f"{self.Name} : Rejected invalid or unregistered target_workspace_path '{raw_target_ws}'; falling back."
            )

        if self.domain_workspace_root is not None and self.domain_workspace_root.is_dir():
            return self.domain_workspace_root

        return central_ws_resolved

    # -----------------------------------------------------------------------------------------------

    async def execute_tool(self, name: str, args: typeDict[str, typeAny]) -> str:
        """Dynamic tool execution handler."""
        if self.read_only and name in _MUTATING_TOOL_NAMES:
            return f"Error: Tool '{name}' is disabled in read-only mode for role '{self.role_name}'."

        if name == "query_rag_engine":
            query_arg = args.get("query", "")
            ctx = self.current_task_context or {}
            target_brain = (
                args.get("brain_id")
                or ctx.get("target_brain_id")
                or self.current_source_brain
                or self.target_brain_id
            )
            raw_data = getattr(self.config, "data", None)
            rag_client = raw_data.get("rag_client") if type(raw_data) is dict else None

            rag_store = RAGMemoryStore(
                config=self.config,
                logger=self.logger,
                tenant=target_brain,
                client=rag_client,
            )
            loop = asyncioGetRunningLoop()
            results = await loop.run_in_executor(
                None,
                lambda: rag_store.retrieve(query_arg, limit=5),
            )
            if not results:
                return f"No architectural context found in RAG engine for brain '{target_brain}'."
            formatted = [f"Context turn:\n{doc.get('content', '')}" for doc in results]
            return "\n\n---\n\n".join(formatted)

        elif name == "list_workspace_files":
            path_arg = str(args.get("path", ".") or ".").strip()
            active_workspace_root = self._resolve_active_workspace_root()
            target_path = (active_workspace_root / path_arg).resolve()

            try:
                target_path.relative_to(active_workspace_root)
            except ValueError:
                return f"Error: Access denied. Path {path_arg} is outside the workspace root."

            if target_path.is_file():
                return str(target_path.relative_to(active_workspace_root))
            if not target_path.is_dir():
                return f"Error: Directory {path_arg} does not exist."

            rel_files: typeList[str] = []
            truncated = False
            for root_str, dirs, files in osWalk(str(target_path)):
                dirs[:] = sorted(d for d in dirs if d not in _LIST_EXCLUDED_DIRS)
                root_p = pathPath(root_str)
                for fname in sorted(files):
                    if fname == ".DS_Store" or fname.endswith(".pyc"):
                        continue
                    rel_files.append(str((root_p / fname).relative_to(active_workspace_root)))
                    if len(rel_files) >= _MAX_LISTED_FILES:
                        truncated = True
                        break
                if truncated:
                    break

            if not rel_files:
                return f"No files found in {path_arg}."
            listing = "\n".join(rel_files)
            if truncated:
                return f"{listing}\n... (truncated at {_MAX_LISTED_FILES} files; pass a narrower subdirectory)"
            return listing

        elif name == "read_workspace_file":
            path_arg = args.get("path", "")
            fold_bodies_arg = args.get("fold_bodies", False)
            active_workspace_root = self._resolve_active_workspace_root()
            file_path = (active_workspace_root / path_arg).resolve()

            try:
                file_path.relative_to(active_workspace_root)
            except ValueError:
                return f"Error: Access denied. Path {path_arg} is outside the workspace root."

            try:
                content = file_path.read_text(encoding="utf-8")
                if fold_bodies_arg:
                    ext = file_path.suffix.lower().lstrip(".")
                    if ext == "py":
                        content = _fold_python_code(content)
                    elif ext in ("js", "ts", "go", "rs", "cpp", "h", "hpp", "cc"):
                        content = _fold_generic_code(content)
                return content
            except Exception as e:
                return f"Error reading file {path_arg}: {e}"

        elif name == "write_workspace_file":
            path_arg = args.get("path", "")
            content_arg = args.get("content", "")
            if "# ... folded ..." in content_arg or "// ... folded ..." in content_arg:
                return (
                    f"Error: Refusing to write {path_arg} because content contains folded-body "
                    f"placeholders ('... folded ...'). Re-read the file with fold_bodies=False first."
                )
            active_workspace_root = self._resolve_active_workspace_root()
            _, central_workspace_root = resolve_vault_and_workspace(__file__)
            file_path = (active_workspace_root / path_arg).resolve()

            try:
                file_path.relative_to(active_workspace_root)
            except ValueError:
                return f"Error: Access denied. Path {path_arg} is outside the workspace root."

            try:
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(content_arg, encoding="utf-8")
                if file_path.suffix.lower() in (".py", ".go", ".rs", ".cpp", ".h", ".hpp"):
                    try:
                        from src.auditing.validate_compliance import ComplianceAuditor
                        auditor = ComplianceAuditor(workspace_root=central_workspace_root)
                        violations = auditor.audit_file(file_path, strict_imports=True, strict_lean=True)
                        if violations:
                            v_lines = [f"  - [{v['rule']}] Line {v['line']}: {v['message']}" for v in violations[:8]]
                            return (
                                f"Success writing to file {path_arg}, BUT {len(violations)} ecosystem compliance / lean-code violation(s) "
                                f"were detected and MUST be fixed immediately:\n" + "\n".join(v_lines)
                            )
                    except Exception as audit_err:
                        self.logger.warning(f"{self.Name} : ComplianceAuditor check skipped on '{path_arg}': {audit_err}")
                return f"Success writing to file {path_arg}"
            except Exception as e:
                return f"Error writing file {path_arg}: {e}"

        elif name == "execute_shell_command":
            cmd_arg = args.get("command", "")
            blocked_commands = [
                "rm", "rmdir", "chmod", "chown", "sudo", "su", "curl", "wget",
                "scp", "ssh", "sftp", "ftp", "/etc/", "/var/", "mv", "dd",
                "mkfs", "tftp",
            ]
            cleaned_cmd = cmd_arg.lower().replace("'", "").replace('"', "").replace("\\", "")
            cmd_parts = reSplit(r"[;&|`\n\r]", cleaned_cmd)
            for part in cmd_parts:
                part_strip = part.strip()
                for kw in blocked_commands:
                    if kw.startswith("/"):
                        if kw in part_strip:
                            return f"Error: Command execution blocked for safety. Path '{kw}' is prohibited."
                    else:
                        if reSearch(r"\b" + kw + r"\b", part_strip):
                            return f"Error: Command execution blocked for safety. Command '{kw}' is prohibited."

            active_workspace_root = self._resolve_active_workspace_root()
            try:
                proc = await asyncioToThread(
                    subprocessRun,
                    cmd_arg,
                    shell=True,
                    capture_output=True,
                    text=True,
                    cwd=str(active_workspace_root),
                    timeout=30,
                )
                return f"Stdout:\n{proc.stdout}\nStderr:\n{proc.stderr}\nExit Code: {proc.returncode}"
            except subprocessTimeoutExpired:
                return "Error: Command execution timed out after 30 seconds."
            except Exception as e:
                return f"Error executing command: {e}"

        return f"Tool {name} not implemented."

    # -----------------------------------------------------------------------------------------------

    async def _run_mock_think_and_respond(
        self,
        session_id: str,
        reply_topic: typeOptional[str] = None,
        source_brain: typeOptional[str] = None,
        task_context: typeOptional[typeDict[str, typeAny]] = None,
        fallback_message: typeOptional[str] = None,
    ) -> None:
        """Generates a simulated role-specific mock response for testing offline."""
        self.current_source_brain = source_brain
        if task_context is not None:
            self.current_task_context = dict(task_context)

        history = await self._fetch_history(session_id)
        last_msg = history[-1]["content"] if history else (fallback_message or "")

        answer_text = ""
        tool_calls_data: typeList[typeDict[str, typeAny]] = []
        ctx = self.current_task_context or {}

        if self.role_name == "orchestrator":
            if ctx:
                target_brain = ctx.get("target_brain_id", "obsidian-brain")
                target_ws = ctx.get("target_workspace_path", "")
                bdd_spec = ctx.get("bdd_spec_path", "")
                fleet_mode = ctx.get("fleet_mode", "local")
                answer_text = (
                    f"🤖 **[Orchestrator]** Coordinating cross-brain handoff for brain '{target_brain}' "
                    f"(workspace: '{target_ws}', spec: '{bdd_spec}', fleet_mode: '{fleet_mode}'). "
                    f"@developer Please implement/scaffold and audit compliance. @qa Please verify tests and health endpoints."
                )
            elif "status" in last_msg.lower() or "check" in last_msg.lower():
                answer_text = (
                    "🤖 **[Orchestrator]** Hello! I have initiated a status check across all squad agent services. "
                    "The system is healthy and responsive. Let me loop in the developer and QA agents to verify details. @developer @qa"
                )
            else:
                answer_text = (
                    f"🤖 **[Orchestrator]** Understood. I am coordinating the squad to address your request: '{last_msg}'. "
                    "@developer, please review the workspace files. @qa, prepare the verification tests."
                )
        elif self.role_name == "developer":
            answer_text = (
                "🛠️ **[Developer]** Developer here. I have scanned the repository workspace. "
                "All python and Go codebase files conform to standard architecture layout guidelines. "
                "I stand ready to apply edits as requested."
            )
            tool_calls_data.append({
                "name": "read_workspace_file",
                "args": {"path": "src/agents/developer.py"},
                "result": "Success: Read 107 lines of code.",
            })
        elif self.role_name == "qa":
            answer_text = (
                "🧪 **[QA]** Greetings, this is QA. I have executed the syntax verification suite. "
                "Codebase integrity is verified: all tests pass successfully, and no config drift was detected."
            )
        elif self.role_name == "architect":
            answer_text = (
                "📐 **[Architect]** Hello! Architect here. The current system architecture conforms to our standard "
                "multi-agent decoupled layout. The dual-layer memory persistence and event routing schemes are fully aligned."
            )
        elif self.domain_vault_root is not None:
            answer_text = (
                f"🧠 **[{self.role_name}]** Domain specialist for '{self.target_brain_id}' ready. "
                "Preparing BDD specification handoff for @obsidian-brain:orchestrator."
            )
        else:
            answer_text = (
                f"[SCAN] Role: {self.role_name} | Source: offline-mock | State: Ready\n"
                f"🔍 **[{self.role_name}]** Offline read-only mock response (set GEMINI_API_KEY for live LLM evaluation)."
            )

        if answer_text:
            await asyncioSleep(0.05)
            await self._save_log(session_id, answer_text, tool_calls_data)
            publish_topic = reply_topic or self.squad_chat_topic
            await self._publish_agent_response(
                session_id=session_id,
                answer_text=answer_text,
                tool_calls_data=tool_calls_data,
                publish_topic=publish_topic,
                source_brain=source_brain or self.target_brain_id,
            )

    # -----------------------------------------------------------------------------------------------

    async def _fetch_history(self, session_id: str) -> typeList[typeDict[str, typeAny]]:
        """Queries postgres squad_chat_logs for history turns."""
        if not self.pool:
            return []

        active_brain = self.current_source_brain or self.brain_id
        loop = asyncioGetRunningLoop()

        def db_query():
            conn = self.pool.getconn()
            try:
                with conn.cursor() as cursor:
                    cursor.execute('SET search_path TO "08-Squad-Agent", public')
                    cursor.execute(
                        "SELECT sender, content, tool_calls FROM squad_chat_logs WHERE session_id = %s AND brain_id = %s ORDER BY created_at DESC LIMIT 15",
                        (session_id, active_brain),
                    )
                    rows = cursor.fetchall()
                    return [
                        {"sender": r[0], "content": r[1], "tool_calls": r[2]}
                        for r in reversed(rows)
                    ]
            except Exception as e:
                self.logger.error(f"{self.Name} : Failed to query squad_chat_logs: {e}")
                return []
            finally:
                self.pool.putconn(conn)

        return await loop.run_in_executor(None, db_query)

    # -----------------------------------------------------------------------------------------------

    async def _save_log(
        self,
        session_id: str,
        content: str,
        tool_calls: typeOptional[typeList[typeDict[str, typeAny]]] = None,
    ) -> None:
        """Saves a conversation turn to squad_chat_logs."""
        if not self.pool:
            return

        loop = asyncioGetRunningLoop()
        active_brain = self.current_source_brain or self.target_brain_id or "obsidian-brain"

        def db_insert():
            conn = self.pool.getconn()
            try:
                with conn.cursor() as cursor:
                    cursor.execute('SET search_path TO "08-Squad-Agent", public')
                    cursor.execute(
                        "INSERT INTO squad_chat_logs (session_id, sender, content, tool_calls, brain_id) VALUES (%s, %s, %s, %s, %s)",
                        (session_id, self.role_name, content, jsonDumps(tool_calls or []), active_brain),
                    )
                conn.commit()
            except Exception as e:
                self.logger.error(f"{self.Name} : Failed to insert squad_chat_logs: {e}")
            finally:
                self.pool.putconn(conn)

        await loop.run_in_executor(None, db_insert)
