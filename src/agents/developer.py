#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Lead Developer agent daemon specialized in reading/writing source files, scaffolding
compliant L3/L4/L5 microservices, compiling code, and implementing logic changes across
both the central workspace and registered external domain workspaces.

DATA FLOW:
1. Inherits BaseAgent initialization with role-specific prompt and event bus.
2. Registers standard workspace tools plus scaffold_microservice for domain repo creation.
3. Routes scaffold_microservice invocations cleanly to main.py scaffold-microservice.

KEY PARAMETERS:
- config: Application configuration singleton.
- logger: UniLog logging handle.
- pg_pool: Shared database connection pool.
- event_bus: SquadEventBus pub/sub provider.
"""

from asyncio import to_thread as asyncioToThread
from os import environ as osEnviron
from pathlib import Path as pathPath
from re import match as reMatch
from subprocess import TimeoutExpired as subprocessTimeoutExpired, run as subprocessRun
from sys import executable as sysExecutable
from typing import Any as typeAny, Dict as typeDict, Optional as typeOptional

from src.interfaces import SquadEventBus
from src.agents.base_agent import (
    BaseAgent,
    edit_workspace_file,
    execute_shell_command,
    list_workspace_files,
    query_rag_engine,
    read_workspace_file,
    write_workspace_file,
)
from src.lib.orchestration_lib import resolve_vault_and_workspace

# -----------------------------------------------------------------------------------------------

_ALLOWED_LANGS = frozenset({"go", "python", "rust", "cpp"})
_ALLOWED_LAYERS = frozenset({"L1", "L2", "L3", "L4", "L5"})
_ALLOWED_FLEET_MODES = frozenset({"local", "docker"})

# -----------------------------------------------------------------------------------------------


def scaffold_microservice(
    name: str,
    lang: str = "go",
    port: int = 8190,
    layer: str = "L3",
    brain: str = "",
    dest: str = "",
    fleet_mode: str = "local",
) -> str:
    """
    Scaffolds a standard-compliant Bastien-Antigravity microservice repository into the active
    or external domain workspace using the ecosystem scaffold-microservice generator.

    Args:
        name: Microservice name (e.g. 'alpha-observer').
        lang: Implementation language ('go', 'python', 'rust', 'cpp').
        port: Default capability listen port.
        layer: Architecture layer ('L1', 'L2', 'L3', 'L4', 'L5').
        brain: Optional target knowledge brain directory path.
        dest: Optional destination directory path for the scaffolded microservice.
        fleet_mode: Target fleet mode ('local' or 'docker').
    """
    return ""


# -----------------------------------------------------------------------------------------------


class DeveloperAgent(BaseAgent):
    """
    Lead Developer agent daemon. Specialized in reading/writing source files,
    scaffolding compliant microservices, compiling code, and implementing logic changes.
    """

    SPECIALIST_PROMPTS = [
        "03-Developer/Squad/Python-Integration-Specialist.md",
        "03-Developer/Squad/Go-Systems-Specialist.md",
        "03-Developer/Squad/Rust-Safety-Specialist.md",
        "03-Developer/Squad/CPP-Low-Latency-Specialist.md",
        "03-Developer/Squad/Web-UI-Specialist.md",
        "03-Developer/Squad/Timescale-Data-Specialist.md",
        "03-Developer/Squad/Excel-VBA-Specialist.md",
    ]

    LANG_SPECIALIST_MAP = {
        "go": "03-Developer/Squad/Go-Systems-Specialist.md",
        "python": "03-Developer/Squad/Python-Integration-Specialist.md",
        "rust": "03-Developer/Squad/Rust-Safety-Specialist.md",
        "cpp": "03-Developer/Squad/CPP-Low-Latency-Specialist.md",
    }

    def __init__(
        self,
        *,
        config: typeAny,
        logger: typeAny,
        pg_pool: typeAny,
        event_bus: SquadEventBus,
        target_brain_id: typeOptional[str] = None,
    ):
        super().__init__(
            role_name="developer",
            prompt_file="03-Developer/Prompt-Lead-Developer.md",
            config=config,
            logger=logger,
            pg_pool=pg_pool,
            event_bus=event_bus,
            extra_prompt_files=self.SPECIALIST_PROMPTS,
            target_brain_id=target_brain_id,
        )
        self.tools = [
            query_rag_engine,
            list_workspace_files,
            read_workspace_file,
            edit_workspace_file,
            write_workspace_file,
            execute_shell_command,
            scaffold_microservice,
        ]

    # -----------------------------------------------------------------------------------------------

    def _load_system_prompt(self) -> str:
        """Scopes specialist prompts dynamically when task_context specifies a target language."""
        ctx = getattr(self, "current_task_context", None)
        if type(ctx) is not dict:
            return super()._load_system_prompt()

        build_spec = ctx.get("build_spec") if type(ctx.get("build_spec")) is dict else {}
        lang = str(ctx.get("lang") or build_spec.get("lang") or "").strip().lower()
        primary_spec = self.LANG_SPECIALIST_MAP.get(lang)
        if not primary_spec:
            return super()._load_system_prompt()

        scoped_extras = [primary_spec]
        if ctx.get("expose_openmfe", build_spec.get("expose_openmfe", True)):
            scoped_extras.append("03-Developer/Squad/Web-UI-Specialist.md")
        if ctx.get("use_timescale", build_spec.get("use_timescale", False)):
            scoped_extras.append("03-Developer/Squad/Timescale-Data-Specialist.md")

        prev_extras = self.extra_prompt_files
        self.extra_prompt_files = scoped_extras
        try:
            return super()._load_system_prompt()
        finally:
            self.extra_prompt_files = prev_extras

    # -----------------------------------------------------------------------------------------------

    async def execute_tool(self, name: str, args: typeDict[str, typeAny]) -> str:
        """Executes DeveloperAgent tools, delegating standard workspace/RAG tools to BaseAgent."""
        if self.read_only and name == "scaffold_microservice":
            return f"Error: Tool '{name}' is disabled in read-only mode for role '{self.role_name}'."
        if self.worktree_sandbox_mode and name == "scaffold_microservice":
            return f"Error: Tool '{name}' is disabled in isolated worktree sandbox mode."
        if name != "scaffold_microservice":
            return await super().execute_tool(name, args)

        svc_name = str(args.get("name", "")).strip()
        if not svc_name or not reMatch(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$", svc_name):
            return "Error: Valid alphanumeric/hyphenated service 'name' is required for scaffold_microservice."

        lang = str(args.get("lang", "go")).strip().lower()
        if lang not in _ALLOWED_LANGS:
            return f"Error: Unsupported language '{lang}'. Allowed: {sorted(_ALLOWED_LANGS)}."

        layer = str(args.get("layer", "L3")).strip().upper()
        if layer not in _ALLOWED_LAYERS:
            return f"Error: Unsupported layer '{layer}'. Allowed: {sorted(_ALLOWED_LAYERS)}."

        try:
            port = int(args.get("port", 0))
        except (TypeError, ValueError):
            return "Error: 'port' must be an integer (0 for auto-allocation or 1..65535)."
        if port < 0 or port > 65535:
            return "Error: 'port' must be 0 (auto-allocate) or between 1 and 65535."

        ctx = self.current_task_context or {}
        fleet_mode = str(args.get("fleet_mode") or ctx.get("fleet_mode") or "local").strip().lower()
        if fleet_mode not in _ALLOWED_FLEET_MODES:
            return f"Error: Unsupported fleet_mode '{fleet_mode}'. Allowed: {sorted(_ALLOWED_FLEET_MODES)}."

        brain_arg = str(args.get("brain") or ctx.get("target_vault_path") or "").strip()
        active_ws = self._resolve_active_workspace_root()
        if port == 0:
            from src.models.build_spec import allocate_domain_port
            extra_scan = [active_ws]
            if brain_arg:
                extra_scan.append(pathPath(brain_arg))
            port = allocate_domain_port(workspace_root=self.workspace_root, extra_paths=extra_scan)
        central_vault, central_ws = resolve_vault_and_workspace(__file__)
        central_ws_resolved = central_ws.resolve()

        dest_raw = str(args.get("dest", "")).strip()
        dest_path: typeOptional[pathPath] = None
        if dest_raw:
            dest_path = (active_ws / dest_raw).resolve()
            try:
                dest_path.relative_to(active_ws)
            except ValueError:
                return f"Error: Access denied. Destination '{dest_raw}' is outside active workspace '{active_ws}'."
        elif active_ws != central_ws_resolved:
            dest_path = (active_ws / svc_name).resolve()

        main_py = (central_vault / "08-Squad-Agent" / "main.py").resolve()
        cmd = [
            sysExecutable,
            str(main_py),
            "scaffold-microservice",
            "--name",
            svc_name,
            "--lang",
            lang,
            "--port",
            str(port),
            "--layer",
            layer,
            "--fleet-mode",
            fleet_mode,
        ]
        if brain_arg:
            cmd.extend(["--brain", brain_arg])
        if dest_path is not None:
            cmd.extend(["--dest", str(dest_path)])

        run_env = dict(osEnviron)
        run_env["APP_LOGGER_PROFILE"] = "devel"

        try:
            proc = await asyncioToThread(
                subprocessRun,
                cmd,
                capture_output=True,
                text=True,
                cwd=str(active_ws),
                env=run_env,
                timeout=60,
            )
            return f"Stdout:\n{proc.stdout}\nStderr:\n{proc.stderr}\nExit Code: {proc.returncode}"
        except subprocessTimeoutExpired:
            return "Error: scaffold_microservice timed out after 60 seconds."
        except Exception as exc:
            self.logger.error(f"{self.Name} : scaffold_microservice failed for '{svc_name}': {exc}")
            return f"Error executing scaffold_microservice: {exc}"
