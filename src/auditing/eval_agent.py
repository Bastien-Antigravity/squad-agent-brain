#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Isolated single-agent evaluation, coherency, and ephemeral worktree sandbox harness
for 08-Squad-Agent personas. Supports two execution modes:
- 'readonly' (default): Zero-mutation audit over an in-memory SquadEventBus.
- 'worktree': Detached HEAD git worktree inside /tmp with sanitized environment
  (secrets stripped, HOME/TMPDIR/GOCACHE/CARGO_TARGET_DIR/CONFIG_PATH jailed,
  LOGGER_PROFILE='minimal', GOWORK='off'), Complexity-Gate file cap, post-edit
  compliance + test verification, optional .patch export, unconditional teardown,
  and pre/post host Git fingerprint assertion proving zero host pollution.

DATA FLOW:
1. Resolves requested role slug to its concrete BaseAgent subclass or Role-Prompt file.
2. Configures either strict read-only mode or an ephemeral /tmp detached git worktree.
3. Dispatches an @role task prompt over the in-memory SquadEventBus and records tool calls.
4. Grades post-run compliance, debloat invariants, worktree diffs/tests, and host fingerprint.
5. Tears down temporary worktrees unconditionally and emits a Markdown or JSON scorecard.

KEY PARAMETERS:
- role: Persona identifier (e.g. 'patternsentinel', 'debloatsentinel', 'gospecialist', 'developer').
- repo: Relative or absolute path to the target repository under evaluation.
- mode: Execution isolation mode ('readonly' or 'worktree'; default 'readonly').
- max_files: Maximum files an agent may mutate in 'worktree' mode (default 2 per Complexity Gate).
- patch_out: Optional path to export the verified unified diff before worktree deletion.
"""

from argparse import ArgumentParser as argparseArgumentParser
from asyncio import run as asyncioRun
from importlib import import_module as importlibImportModule
from json import dumps as jsonDumps
from os import environ as osEnviron
from pathlib import Path as pathPath
from shutil import rmtree as shutilRmtree, which as shutilWhich
from subprocess import TimeoutExpired as subprocessTimeoutExpired, run as subprocessRun
from sys import exit as sysExit, stdout as sysStdout
from tempfile import mkdtemp as tempfileMkdtemp
from time import monotonic as timeMonotonic
from typing import Any as typeAny, Callable as typeCallable, Dict as typeDict, List as typeList, Optional as typeOptional, Tuple as typeTuple

from src.agents.base_agent import _BLOCKED_IN_WORKTREE_TOOLS, _MUTATING_TOOL_NAMES, BaseAgent, slugify_role_name
from src.auditing.debloat_audit import run_debloat_audit
from src.auditing.validate_compliance import ComplianceAuditor
from src.core.agent_dispatcher import ROLE_MAP, get_role_prompt_path
from src.interfaces import SquadEventBus
from src.lib.orchestration_lib import get_config, get_logger, resolve_vault_and_workspace

# -----------------------------------------------------------------------------------------------

_AGENT_CLASS_SPECS: typeDict[str, typeTuple[str, str]] = {
    "oracle": ("src.agents.oracle", "OracleAgent"),
    "orchestrator": ("src.agents.orchestrator", "OrchestratorAgent"),
    "architect": ("src.agents.architect", "ArchitectAgent"),
    "developer": ("src.agents.developer", "DeveloperAgent"),
    "qa": ("src.agents.qa", "QAAgent"),
    "fleetarchitect": ("src.agents.fleetarchitect", "FleetArchitectAgent"),
    "docmaintainer": ("src.agents.docmaintainer", "DocMaintainerAgent"),
    "fleetcommander": ("src.agents.fleetcommander", "FleetCommanderAgent"),
    "purger": ("src.agents.purger", "PurgerAgent"),
    "sentinel": ("src.agents.sentinel", "SentinelAgent"),
    "docindexer": ("src.agents.docindexer", "DocIndexerAgent"),
    "codeindexer": ("src.agents.codeindexer", "CodeIndexerAgent"),
    "patternsentinel": ("src.agents.patternsentinel", "PatternSentinelAgent"),
    "prototyper": ("src.agents.prototyper", "PrototyperAgent"),
    "debloatsentinel": ("src.agents.debloatsentinel", "DebloatSentinelAgent"),
}

_SAFE_PASSTHROUGH_ENV_KEYS = ("PATH", "LANG", "LC_ALL", "SYSTEMROOT", "TERM")

_ISOLATED_DUMMY_CONFIG_YAML = (
    "capabilities:\n"
    "  config_server:\n"
    "    ip: \"127.0.0.1\"\n"
    "    port: \"13306\"\n"
    "  log_server:\n"
    "    ip: \"127.0.0.1\"\n"
    "    port: \"19020\"\n"
    "  notif_server:\n"
    "    ip: \"127.0.0.1\"\n"
    "    port: \"11026\"\n"
    "    grpc_port: \"11027\"\n"
    "    rest_port: \"11029\"\n"
)

# -----------------------------------------------------------------------------------------------


def _run_git(args: typeList[str], *, cwd: pathPath, timeout_sec: int = 30) -> typeTuple[int, str, str]:
    """Executes a deterministic git subprocess with shell=False and returns (rc, stdout, stderr)."""
    proc = subprocessRun(
        ["git"] + args,
        cwd=str(cwd),
        shell=False,
        capture_output=True,
        text=True,
        timeout=timeout_sec,
    )
    return proc.returncode, proc.stdout, proc.stderr


# -----------------------------------------------------------------------------------------------


def _capture_git_fingerprint(git_root: pathPath) -> typeDict[str, str]:
    """Captures HEAD SHA, porcelain status, refs, and worktree list to prove zero host mutation."""
    _, head_out, _ = _run_git(["rev-parse", "HEAD"], cwd=git_root)
    _, status_out, _ = _run_git(["status", "--porcelain"], cwd=git_root)
    _, refs_out, _ = _run_git(["show-ref"], cwd=git_root)
    _, wt_out, _ = _run_git(["worktree", "list", "--porcelain"], cwd=git_root)
    return {
        "head": head_out.strip(),
        "status": status_out,
        "refs": refs_out,
        "worktrees": wt_out.strip(),
    }


# -----------------------------------------------------------------------------------------------


def _resolve_git_root(target_path: pathPath) -> pathPath:
    """Resolves the enclosing Git repository root for target_path, failing fast if not a Git repo."""
    probe_dir = target_path if target_path.is_dir() else target_path.parent
    rc, out, err = _run_git(["rev-parse", "--show-toplevel"], cwd=probe_dir)
    if rc != 0 or not out.strip():
        raise ValueError(
            f"SquadAgentEvaluator : Target '{target_path}' is not inside a Git repository ({err.strip()})."
        )
    return pathPath(out.strip()).resolve()


# -----------------------------------------------------------------------------------------------


def _build_isolated_sandbox_env(*, sandbox_base: pathPath) -> typeDict[str, str]:
    """
    Constructs a hermetically isolated child environment inside sandbox_base:
    - Strips host secrets (GEMINI_API_KEY, GITHUB_TOKEN, DATABASE_URL, etc.).
    - Redirects HOME, TMPDIR, GOCACHE, CARGO_TARGET_DIR, and CONFIG_PATH into /tmp sandbox.
    - Forces LOGGER_PROFILE='minimal', GOWORK='off', and PYTHONDONTWRITEBYTECODE='1'.
    """
    home_dir = sandbox_base / ".home"
    tmp_dir = sandbox_base / ".tmp"
    gocache_dir = sandbox_base / ".gocache"
    cargo_dir = sandbox_base / ".cargo-target"
    for d in (home_dir, tmp_dir, gocache_dir, cargo_dir):
        d.mkdir(parents=True, exist_ok=True)

    cfg_path = sandbox_base / "isolated_config.yaml"
    cfg_path.write_text(_ISOLATED_DUMMY_CONFIG_YAML, encoding="utf-8")

    env: typeDict[str, str] = {}
    for key in _SAFE_PASSTHROUGH_ENV_KEYS:
        val = osEnviron.get(key)
        if val:
            env[key] = val

    env.update({
        "HOME": str(home_dir),
        "TMPDIR": str(tmp_dir),
        "GOCACHE": str(gocache_dir),
        "CARGO_TARGET_DIR": str(cargo_dir),
        "GOWORK": "off",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
        "LOGGER_PROFILE": "minimal",
        "APP_LOGGER_PROFILE": "minimal",
        "CONFIG_PATH": str(cfg_path),
    })
    return env


# -----------------------------------------------------------------------------------------------


def _collect_worktree_diff(sandbox_git_dir: pathPath) -> typeTuple[typeList[str], str]:
    """Collects changed/untracked relative paths and unified diff without mutating Git's index."""
    _, status_out, _ = _run_git(["status", "--porcelain"], cwd=sandbox_git_dir)
    changed_files: typeList[str] = []
    untracked_files: typeList[str] = []
    for raw_line in status_out.splitlines():
        if len(raw_line) < 4:
            continue
        code = raw_line[:2]
        rel_file = raw_line[3:].strip()
        if rel_file not in changed_files:
            changed_files.append(rel_file)
        if code == "??":
            untracked_files.append(rel_file)

    _, tracked_diff, _ = _run_git(["diff", "HEAD"], cwd=sandbox_git_dir)
    diff_chunks: typeList[str] = []
    if tracked_diff.strip():
        diff_chunks.append(tracked_diff.rstrip("\n"))

    for untracked_rel in untracked_files:
        candidate = (sandbox_git_dir / untracked_rel).resolve()
        if candidate.is_file():
            _, new_diff, _ = _run_git(
                ["diff", "--no-index", "--", "/dev/null", untracked_rel],
                cwd=sandbox_git_dir,
            )
            if new_diff.strip():
                diff_chunks.append(new_diff.rstrip("\n"))

    combined_diff = ("\n".join(diff_chunks) + "\n") if diff_chunks else ""
    return changed_files, combined_diff


# -----------------------------------------------------------------------------------------------


def _run_worktree_verification_tests(
    *,
    sandbox_target_dir: pathPath,
    sandbox_env: typeDict[str, str],
) -> typeDict[str, typeAny]:
    """Runs repository unit tests inside the isolated worktree with sandbox_env."""
    cmd: typeOptional[typeList[str]] = None
    go_bin = shutilWhich("go", path=sandbox_env.get("PATH"))
    cargo_bin = shutilWhich("cargo", path=sandbox_env.get("PATH"))
    pytest_bin = shutilWhich("pytest", path=sandbox_env.get("PATH"))
    py_bin = shutilWhich("python3", path=sandbox_env.get("PATH"))

    if (sandbox_target_dir / "go.mod").is_file() and go_bin:
        cmd = [go_bin, "test", "-count=1", "./..."]
    elif (sandbox_target_dir / "Cargo.toml").is_file() and cargo_bin:
        cmd = [cargo_bin, "test"]
    elif (sandbox_target_dir / "tests").is_dir() and pytest_bin:
        cmd = [pytest_bin, "-q"]
    elif (sandbox_target_dir / "tests").is_dir() and py_bin:
        cmd = [py_bin, "-m", "unittest", "discover", "-s", "tests"]

    if cmd is None:
        return {"executed": False, "passed": None, "command": "", "output": "No matching test suite/toolchain detected."}

    try:
        proc = subprocessRun(
            cmd,
            cwd=str(sandbox_target_dir),
            env=sandbox_env,
            shell=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
        combined = (proc.stdout + "\n" + proc.stderr).strip()[-3000:]
        return {
            "executed": True,
            "passed": proc.returncode == 0,
            "exit_code": proc.returncode,
            "command": " ".join(cmd),
            "output": combined,
        }
    except subprocessTimeoutExpired:
        return {
            "executed": True,
            "passed": False,
            "exit_code": -1,
            "command": " ".join(cmd),
            "output": "Test verification timed out after 120 seconds.",
        }


# -----------------------------------------------------------------------------------------------


class SquadAgentEvaluator(SquadEventBus):
    """
    In-memory SquadEventBus and isolated single-agent evaluation runner supporting
    both 'readonly' (zero-mutation) and 'worktree' (detached /tmp sandbox) modes.
    """

    Name = "SquadAgentEvaluator"

    def __init__(
        self,
        *,
        config: typeAny,
        logger: typeAny,
        workspace_root: typeOptional[pathPath] = None,
        vault_root: typeOptional[pathPath] = None,
    ) -> None:
        resolved_vault, resolved_ws = resolve_vault_and_workspace(__file__)
        self.config = config
        self.logger = logger
        self.vault_root: pathPath = (vault_root or resolved_vault).resolve()
        self.workspace_root: pathPath = (workspace_root or resolved_ws).resolve()
        self._callbacks: typeList[typeCallable[[typeDict[str, typeAny]], typeAny]] = []
        self.published_events: typeList[typeDict[str, typeAny]] = []

    # -------------------------------------------------------------------------------------------

    async def connect(self) -> None:
        """No-op connection hook for in-memory evaluation bus."""
        return None

    # -------------------------------------------------------------------------------------------

    async def close(self) -> None:
        """Clears registered in-memory callbacks."""
        self._callbacks.clear()

    # -------------------------------------------------------------------------------------------

    async def subscribe(
        self,
        topic: str,
        callback: typeCallable[[typeDict[str, typeAny]], typeAny],
        role: typeOptional[str] = None,
    ) -> None:
        """Registers the single evaluated agent callback on the in-memory bus."""
        _ = (topic, role)
        self._callbacks.append(callback)

    # -------------------------------------------------------------------------------------------

    async def publish(self, topic: str, payload: typeDict[str, typeAny]) -> None:
        """Records outgoing agent payloads published during evaluation."""
        self.published_events.append({"topic": topic, "payload": dict(payload)})

    # -------------------------------------------------------------------------------------------

    def instantiate_agent(self, *, role: str, read_only: bool = True) -> BaseAgent:
        """Resolves and instantiates a daemon subclass or specialist BaseAgent persona."""
        role_slug = slugify_role_name(role)
        if not role_slug:
            raise ValueError("SquadAgentEvaluator : A non-empty '--role' identifier is required.")

        spec = _AGENT_CLASS_SPECS.get(role_slug)
        if spec is not None:
            mod_name, cls_name = spec
            mod = importlibImportModule(mod_name)
            agent_cls = getattr(mod, cls_name)
            agent: BaseAgent = agent_cls(
                config=self.config,
                logger=self.logger,
                pg_pool=None,
                event_bus=self,
            )
        else:
            rel_prompt = ROLE_MAP.get(role_slug)
            prompt_path = rel_prompt or get_role_prompt_path(role_slug, vault_root=self.vault_root)
            if not prompt_path:
                available = sorted(set(ROLE_MAP.keys()) | set(_AGENT_CLASS_SPECS.keys()))
                raise ValueError(
                    f"SquadAgentEvaluator : Unknown squad role '{role}'. Available roles: {', '.join(available)}"
                )
            agent = BaseAgent(
                role_name=role_slug,
                prompt_file=prompt_path,
                config=self.config,
                logger=self.logger,
                pg_pool=None,
                event_bus=self,
                read_only=read_only,
            )

        if read_only:
            agent.enable_readonly_mode()
        return agent

    # -------------------------------------------------------------------------------------------

    def resolve_target_repo(self, repo_arg: str) -> pathPath:
        """Resolves and validates that the target repository resides inside workspace_root."""
        raw = pathPath(repo_arg)
        candidate = raw.resolve() if raw.is_absolute() else (self.workspace_root / raw).resolve()
        try:
            candidate.relative_to(self.workspace_root)
        except ValueError as exc:
            raise ValueError(
                f"SquadAgentEvaluator : Target path '{repo_arg}' is outside workspace '{self.workspace_root}'."
            ) from exc
        if not candidate.exists():
            raise FileNotFoundError(f"SquadAgentEvaluator : Target path '{candidate}' does not exist.")
        return candidate

    # -------------------------------------------------------------------------------------------

    async def evaluate(
        self,
        *,
        role: str,
        repo: str = ".",
        mode: str = "readonly",
        task: str = "",
        model: str = "",
        read_only: bool = True,
        max_files: int = 2,
        patch_out: str = "",
        run_tests: bool = True,
        include_ground_truth: bool = True,
    ) -> typeDict[str, typeAny]:
        """Executes a single-agent evaluation in 'readonly' or isolated 'worktree' mode."""
        norm_mode = (mode or "readonly").strip().lower()
        if norm_mode not in ("readonly", "worktree"):
            raise ValueError(f"SquadAgentEvaluator : Unsupported mode '{mode}'. Use 'readonly' or 'worktree'.")
        if norm_mode == "worktree":
            return await self._evaluate_in_worktree(
                role=role,
                repo=repo,
                task=task,
                model=model,
                max_files=max_files,
                patch_out=patch_out,
                run_tests=run_tests,
                include_ground_truth=include_ground_truth,
            )
        return await self._evaluate_readonly(
            role=role,
            repo=repo,
            task=task,
            model=model,
            read_only=True if norm_mode == "readonly" else read_only,
            include_ground_truth=include_ground_truth,
        )

    # -------------------------------------------------------------------------------------------

    async def _evaluate_readonly(
        self,
        *,
        role: str,
        repo: str,
        task: str,
        model: str,
        read_only: bool,
        include_ground_truth: bool,
    ) -> typeDict[str, typeAny]:
        """Executes strict zero-mutation read-only evaluation directly against workspace_root."""
        self._callbacks.clear()
        self.published_events.clear()

        target_path = self.resolve_target_repo(repo)
        rel_repo = str(target_path.relative_to(self.workspace_root)) if target_path != self.workspace_root else "."
        agent = self.instantiate_agent(role=role, read_only=read_only)
        if model.strip():
            agent.model_name = model.strip()
            self.config.data.setdefault("capabilities", {}).setdefault("squad_agent", {})["gemini_model"] = model.strip()
        await agent.start()

        prompt_body = task.strip() if task.strip() else (
            f"Perform an independent read-only {agent.role_name} audit of repository '{rel_repo}'. "
            f"First call list_workspace_files(path='{rel_repo}') to inspect exact files without guessing paths, "
            f"then read key source/config files and report concrete rule or architecture findings with exact "
            f"file paths and line numbers. Do NOT attempt to modify files or AI-Session-State.md."
        )
        addressed_prompt = (
            prompt_body
            if f"@{agent.role_name}" in prompt_body.lower()
            else f"@{agent.role_name} {prompt_body}"
        )

        user_payload: typeDict[str, typeAny] = {
            "sender": "user",
            "session_id": f"eval-{agent.role_name}",
            "content": addressed_prompt,
            "task_context": {
                "target_brain_id": agent.target_brain_id,
                "target_workspace_path": str(self.workspace_root),
            },
        }

        start_ts = timeMonotonic()
        for cb in list(self._callbacks):
            await cb(user_payload)
        elapsed_sec = round(timeMonotonic() - start_ts, 3)
        await agent.stop()

        return self._build_scorecard(
            agent=agent,
            mode="readonly",
            rel_repo=rel_repo,
            target_path=target_path,
            elapsed_sec=elapsed_sec,
            include_ground_truth=include_ground_truth,
            worktree_report=None,
        )

    # -------------------------------------------------------------------------------------------

    async def _evaluate_in_worktree(
        self,
        *,
        role: str,
        repo: str,
        task: str,
        model: str,
        max_files: int,
        patch_out: str,
        run_tests: bool,
        include_ground_truth: bool,
    ) -> typeDict[str, typeAny]:
        """
        Executes a write-capable agent inside a detached /tmp git worktree with a sanitized
        environment, post-edit compliance & test verification, unconditional teardown,
        and mathematical pre/post host Git fingerprint verification.
        """
        self._callbacks.clear()
        self.published_events.clear()

        target_path = self.resolve_target_repo(repo)
        rel_repo = str(target_path.relative_to(self.workspace_root)) if target_path != self.workspace_root else "."
        git_root = _resolve_git_root(target_path)
        try:
            rel_git_from_ws = git_root.relative_to(self.workspace_root)
        except ValueError:
            rel_git_from_ws = pathPath(git_root.name)
        rel_target_in_git = target_path.relative_to(git_root)

        pre_fingerprint = _capture_git_fingerprint(git_root)
        role_slug = slugify_role_name(role) or "agent"
        sandbox_base = pathPath(tempfileMkdtemp(prefix=f"squad_eval_{role_slug}_")).resolve()
        sandbox_ws = sandbox_base / "ws"
        sandbox_git_dir = (sandbox_ws / rel_git_from_ws).resolve()
        sandbox_git_dir.parent.mkdir(parents=True, exist_ok=True)
        worktree_added = False

        worktree_report: typeDict[str, typeAny] = {
            "git_root": str(git_root),
            "max_files_limit": max(1, int(max_files)),
            "changed_files": [],
            "diff_line_count": 0,
            "patch_saved_to": "",
            "post_edit_compliance_violations": [],
            "test_verification": {"executed": False, "passed": None, "command": "", "output": ""},
            "sandbox_cleaned_up": False,
            "host_workspace_untouched": False,
        }

        try:
            rc_add, out_add, err_add = _run_git(
                ["worktree", "add", "--detach", str(sandbox_git_dir), "HEAD"],
                cwd=git_root,
            )
            if rc_add != 0:
                raise RuntimeError(f"git worktree add failed: {(out_add + ' ' + err_add).strip()}")
            worktree_added = True

            sandbox_env = _build_isolated_sandbox_env(sandbox_base=sandbox_base)
            agent = self.instantiate_agent(role=role, read_only=False)
            agent.enable_worktree_sandbox_mode(
                sandbox_root=sandbox_ws,
                max_files=max_files,
                sandbox_env=sandbox_env,
            )
            if model.strip():
                agent.model_name = model.strip()
                self.config.data.setdefault("capabilities", {}).setdefault("squad_agent", {})["gemini_model"] = model.strip()
            await agent.start()

            sandbox_rel_target = (
                str((sandbox_git_dir / rel_target_in_git).relative_to(sandbox_ws))
                if (sandbox_git_dir / rel_target_in_git) != sandbox_ws
                else "."
            )
            prompt_body = task.strip() if task.strip() else (
                f"Perform an isolated hardening pass on '{sandbox_rel_target}' inside this sandboxed worktree "
                f"(Complexity Gate: modify at most {max(1, int(max_files))} file(s)). "
                f"Use list_workspace_files and read_workspace_file first, apply surgical changes via "
                f"edit_workspace_file, verify tests via execute_shell_command, and do NOT touch VERSION.txt "
                f"or standalone.yaml."
            )
            addressed_prompt = (
                prompt_body
                if f"@{agent.role_name}" in prompt_body.lower()
                else f"@{agent.role_name} {prompt_body}"
            )

            user_payload: typeDict[str, typeAny] = {
                "sender": "user",
                "session_id": f"eval-wt-{agent.role_name}",
                "content": addressed_prompt,
                "task_context": {
                    "target_brain_id": agent.target_brain_id,
                    "target_workspace_path": str(sandbox_ws),
                },
            }

            start_ts = timeMonotonic()
            for cb in list(self._callbacks):
                await cb(user_payload)
            elapsed_sec = round(timeMonotonic() - start_ts, 3)
            await agent.stop()

            changed_files, unified_diff = _collect_worktree_diff(sandbox_git_dir)
            worktree_report["changed_files"] = changed_files
            worktree_report["diff_line_count"] = len(unified_diff.splitlines()) if unified_diff else 0
            worktree_report["unified_diff"] = unified_diff

            comp_auditor = ComplianceAuditor(workspace_root=self.workspace_root)
            post_violations: typeList[typeDict[str, typeAny]] = []
            for rel_changed in changed_files:
                cand_file = (sandbox_git_dir / rel_changed).resolve()
                if cand_file.is_file():
                    post_violations.extend(
                        comp_auditor.audit_file(cand_file, strict_imports=True, strict_lean=True)
                    )
            worktree_report["post_edit_compliance_violations"] = post_violations

            if run_tests and changed_files:
                sandbox_target_dir = (sandbox_git_dir / rel_target_in_git).resolve()
                worktree_report["test_verification"] = _run_worktree_verification_tests(
                    sandbox_target_dir=sandbox_target_dir,
                    sandbox_env=sandbox_env,
                )

            if patch_out.strip() and unified_diff:
                patch_path = pathPath(patch_out).resolve()
                patch_path.parent.mkdir(parents=True, exist_ok=True)
                tmp_patch = patch_path.parent / f".{patch_path.name}.tmp"
                tmp_patch.write_text(unified_diff, encoding="utf-8")
                tmp_patch.replace(patch_path)
                worktree_report["patch_saved_to"] = str(patch_path)

        finally:
            if worktree_added:
                _run_git(["worktree", "remove", "--force", str(sandbox_git_dir)], cwd=git_root)
            shutilRmtree(sandbox_base, ignore_errors=True)
            _run_git(["worktree", "prune"], cwd=git_root)

        post_fingerprint = _capture_git_fingerprint(git_root)
        worktree_report["sandbox_cleaned_up"] = not sandbox_base.exists()
        worktree_report["host_workspace_untouched"] = (
            pre_fingerprint == post_fingerprint and worktree_report["sandbox_cleaned_up"]
        )

        return self._build_scorecard(
            agent=agent,
            mode="worktree",
            rel_repo=rel_repo,
            target_path=target_path,
            elapsed_sec=elapsed_sec,
            include_ground_truth=include_ground_truth,
            worktree_report=worktree_report,
        )

    # -------------------------------------------------------------------------------------------

    def _build_scorecard(
        self,
        *,
        agent: BaseAgent,
        mode: str,
        rel_repo: str,
        target_path: pathPath,
        elapsed_sec: float,
        include_ground_truth: bool,
        worktree_report: typeOptional[typeDict[str, typeAny]],
    ) -> typeDict[str, typeAny]:
        """Assembles the unified evaluation scorecard across readonly and worktree modes."""
        agent_reply = ""
        tool_calls: typeList[typeDict[str, typeAny]] = []
        if self.published_events:
            last_payload = self.published_events[-1]["payload"]
            agent_reply = str(last_payload.get("content", ""))
            raw_calls = last_payload.get("tool_calls")
            if isinstance(raw_calls, list):
                tool_calls = raw_calls

        exposed_tool_names = [getattr(t, "__name__", str(t)) for t in agent._get_effective_tools()]
        is_ro = mode == "readonly"
        mutating_exposed = [t for t in exposed_tool_names if t in _MUTATING_TOOL_NAMES]
        blocked_wt_exposed = [t for t in exposed_tool_names if t in _BLOCKED_IN_WORKTREE_TOOLS]
        mutating_attempted = [c["name"] for c in tool_calls if c.get("name") in _MUTATING_TOOL_NAMES]
        read_errors = [
            c for c in tool_calls
            if str(c.get("result", "")).startswith("Error reading file")
        ]

        coherency: typeDict[str, typeAny] = {
            "read_only_tools_clean": (len(mutating_exposed) == 0) if is_ro else (len(blocked_wt_exposed) == 0),
            "zero_mutations_executed": (len(mutating_attempted) == 0) if is_ro else True,
            "host_workspace_untouched": True if is_ro else bool(worktree_report and worktree_report["host_workspace_untouched"]),
            "scan_header_present": "[SCAN]" in agent_reply,
            "used_file_listing": any(c.get("name") == "list_workspace_files" for c in tool_calls),
            "blind_read_error_count": len(read_errors),
        }
        if worktree_report is not None:
            coherency["complexity_gate_respected"] = (
                len(worktree_report["changed_files"]) <= worktree_report["max_files_limit"]
            )
            coherency["post_edit_compliance_clean"] = (
                len(worktree_report["post_edit_compliance_violations"]) == 0
            )

        scorecard: typeDict[str, typeAny] = {
            "role": agent.role_name,
            "mode": mode,
            "target_repo": rel_repo,
            "target_abs_path": str(target_path),
            "model_name": agent.model_name,
            "live_llm_client": agent.client is not None,
            "read_only": agent.read_only,
            "elapsed_seconds": elapsed_sec,
            "exposed_tools": exposed_tool_names,
            "coherency_checks": coherency,
            "tool_calls_count": len(tool_calls),
            "tool_calls": tool_calls,
            "agent_response": agent_reply,
        }
        if worktree_report is not None:
            scorecard["worktree_sandbox"] = worktree_report

        if include_ground_truth:
            comp_auditor = ComplianceAuditor(workspace_root=self.workspace_root)
            comp_violations = comp_auditor.audit_path(
                target_path,
                strict_imports=True,
                strict_lean=True,
            )
            debloat_res = run_debloat_audit(str(target_path))
            scorecard["ground_truth"] = {
                "compliance_violation_count": len(comp_violations),
                "compliance_violations": comp_violations,
                "debloat_finding_count": int(debloat_res.get("total_findings", 0)),
                "debloat_safe_invariant_count": int(debloat_res.get("total_safe_invariants", 0)),
                "debloat_findings": debloat_res.get("findings", []),
            }

        self.logger.info(
            f"{self.Name} : Completed eval mode='{mode}' role='{agent.role_name}' repo='{rel_repo}' "
            f"(tools={len(tool_calls)}, host_untouched={coherency['host_workspace_untouched']}, elapsed={elapsed_sec}s)"
        )
        return scorecard


# -----------------------------------------------------------------------------------------------


def format_eval_markdown(scorecard: typeDict[str, typeAny]) -> str:
    """Formats an evaluation scorecard dictionary into a human-readable Markdown report."""
    checks = scorecard["coherency_checks"]
    llm_str = "LIVE GEMINI SDK" if scorecard["live_llm_client"] else "OFFLINE MOCK (GEMINI_API_KEY unset)"
    lines: typeList[str] = [
        f"# 🧪 Squad Agent Evaluation Scorecard: `{scorecard['role']}` (`{scorecard.get('mode', 'readonly')}`)",
        "",
        f"- **Target Repo**: `{scorecard['target_repo']}` (`{scorecard['target_abs_path']}`)",
        f"- **Execution Mode**: `{llm_str}` | **Sandbox**: `{scorecard.get('mode', 'readonly')}` | **Model**: `{scorecard['model_name']}`",
        f"- **Elapsed**: `{scorecard['elapsed_seconds']}s` | **Exposed Tools**: `{', '.join(scorecard['exposed_tools'])}`",
        "",
        "## 1. Coherency & Isolation Safety Gate Checks",
        f"- **Tool Isolation Policy**: `{'PASS' if checks['read_only_tools_clean'] else 'FAIL'}`",
        f"- **Host Workspace Untouched**: `{'PASS' if checks.get('host_workspace_untouched', True) else 'FAIL'}`",
        f"- **`[SCAN]` Telemetry Header**: `{'PASS' if checks['scan_header_present'] else 'MISSING'}`",
        f"- **Used `list_workspace_files`**: `{checks['used_file_listing']}`",
        f"- **Tool Calls Executed**: `{scorecard['tool_calls_count']}` (Blind Read Errors: `{checks['blind_read_error_count']}`)",
    ]

    wt = scorecard.get("worktree_sandbox")
    if isinstance(wt, dict):
        tv = wt.get("test_verification", {})
        test_label = "SKIPPED" if not tv.get("executed") else ("PASS" if tv.get("passed") else "FAIL")
        post_v_count = len(wt["post_edit_compliance_violations"])
        comp_label = "PASS (0 violations)" if post_v_count == 0 else f"FAIL ({post_v_count} violations)"
        lines.extend([
            "",
            "## 2. Isolated `/tmp` Git Worktree Verification",
            f"- **Sandbox Cleaned Up**: `{wt['sandbox_cleaned_up']}` | **Host Git Fingerprint Unchanged**: `{wt['host_workspace_untouched']}`",
            f"- **Changed Files (`{len(wt['changed_files'])}/{wt['max_files_limit']}`)**: `{', '.join(wt['changed_files']) or '(none)'}`",
            f"- **Post-Edit Strict Compliance**: `{comp_label}`",
            f"- **Isolated Unit Test Run**: `{test_label}` (`{tv.get('command') or 'n/a'}`)",
        ])
        if wt.get("patch_saved_to"):
            lines.append(f"- **Exported Candidate Patch**: `{wt['patch_saved_to']}`")

    gt = scorecard.get("ground_truth")
    if isinstance(gt, dict):
        lines.extend([
            "",
            "## 3. Host Repository Ground-Truth Baseline",
            f"- **`validate-compliance` (`--strict-imports --strict-lean`)**: `{gt['compliance_violation_count']}` violation(s)",
            f"- **`debloat-audit`**: `{gt['debloat_finding_count']}` bloat finding(s) | `{gt['debloat_safe_invariant_count']}` Safe-by-Design invariant(s)",
        ])

    lines.extend([
        "",
        "## 4. Agent Output",
        "",
        scorecard["agent_response"] or "_(No response emitted)_",
        "",
    ])
    return "\n".join(lines)


# -----------------------------------------------------------------------------------------------


def main() -> None:
    """CLI entrypoint for `python3 08-Squad-Agent/main.py eval-agent`."""
    parser = argparseArgumentParser(
        description="Run a single 08-Squad-Agent persona independently in 'readonly' or isolated '/tmp' 'worktree' mode."
    )
    parser.add_argument("--role", "-r", required=True, help="Squad persona slug (e.g. patternsentinel, debloatsentinel, gospecialist, developer)")
    parser.add_argument("--repo", "-p", default=".", help="Target repository path relative to workspace root (default: .)")
    parser.add_argument("--mode", choices=("readonly", "worktree"), default="readonly", help="Isolation mode: 'readonly' (default) or detached '/tmp' 'worktree'")
    parser.add_argument("--readonly", action="store_true", help="Explicit alias for --mode readonly")
    parser.add_argument("--task", "-t", default="", help="Optional custom evaluation or hardening prompt")
    parser.add_argument("--model", "-m", default="", help="Optional Gemini model override for A/B testing")
    parser.add_argument("--max-files", type=int, default=2, help="Complexity Gate max mutated files in worktree mode (default: 2)")
    parser.add_argument("--patch-out", default="", help="Optional file path to export unified .patch from worktree mode")
    parser.add_argument("--skip-tests", action="store_true", help="Skip automatic unit test verification inside worktree mode")
    parser.add_argument("--skip-ground-truth", action="store_true", help="Skip running ComplianceAuditor and debloat-audit on host repo")
    parser.add_argument("--json", action="store_true", help="Emit JSON scorecard to stdout")
    parser.add_argument("--output", "-o", default="", help="Optional file path to save the report")
    args = parser.parse_args()

    effective_mode = "readonly" if args.readonly else args.mode
    logger = get_logger("EvalAgent")
    config = get_config()
    evaluator = SquadAgentEvaluator(config=config, logger=logger)

    try:
        scorecard = asyncioRun(
            evaluator.evaluate(
                role=args.role,
                repo=args.repo,
                mode=effective_mode,
                task=args.task,
                model=args.model,
                read_only=(effective_mode == "readonly"),
                max_files=args.max_files,
                patch_out=args.patch_out,
                run_tests=not args.skip_tests,
                include_ground_truth=not args.skip_ground_truth,
            )
        )
    except (ValueError, FileNotFoundError, RuntimeError) as err:
        logger.error(f"SquadAgentEvaluator : {err}")
        sysExit(1)

    rendered = jsonDumps(scorecard, indent=2) if args.json else format_eval_markdown(scorecard)
    if args.output:
        out_path = pathPath(args.output).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(rendered, encoding="utf-8")
        logger.info(f"SquadAgentEvaluator : Saved evaluation report to {out_path}")

    sysStdout.write(rendered + "\n")
    checks = scorecard["coherency_checks"]
    if not checks["read_only_tools_clean"] or not checks.get("host_workspace_untouched", False):
        sysExit(1)
    if effective_mode == "readonly" and not checks["zero_mutations_executed"]:
        sysExit(1)
    sysExit(0)


if __name__ == "__main__":
    main()
