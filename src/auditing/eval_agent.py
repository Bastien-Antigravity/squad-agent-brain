#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Isolated single-agent evaluation and coherency harness for 08-Squad-Agent personas.
Instantiates a requested squad or specialist persona over an in-memory SquadEventBus,
enforces strict read-only tool guardrails, executes a repository audit prompt without
requiring NATS or PostgreSQL, and compares agent telemetry against deterministic
ecosystem compliance and debloat ground-truth scanners.

DATA FLOW:
1. Resolves requested role slug to its concrete BaseAgent subclass or Role-Prompt file.
2. Locks the agent instance into read-only mode (list_workspace_files, read_workspace_file, RAG).
3. Dispatches an @role audit prompt over the in-memory SquadEventBus and captures tool calls + reply.
4. Runs ComplianceAuditor and run_debloat_audit ground-truth checks on the target repository.
5. Emits a structured Markdown or JSON coherency and accuracy scorecard.

KEY PARAMETERS:
- role: Persona identifier (e.g. 'patternsentinel', 'debloatsentinel', 'gospecialist', 'architect').
- repo: Relative or absolute path to the target repository under evaluation.
- task: Optional custom evaluation instruction overriding the default audit prompt.
- readonly: Enforces zero-mutation tool restrictions (default True; Fail-Fast on mutating calls).
"""

from argparse import ArgumentParser as argparseArgumentParser
from asyncio import run as asyncioRun
from importlib import import_module as importlibImportModule
from json import dumps as jsonDumps
from pathlib import Path as pathPath
from sys import exit as sysExit, stdout as sysStdout
from time import monotonic as timeMonotonic
from typing import Any as typeAny, Callable as typeCallable, Dict as typeDict, List as typeList, Optional as typeOptional

from src.agents.base_agent import BaseAgent, _MUTATING_TOOL_NAMES, slugify_role_name
from src.auditing.debloat_audit import run_debloat_audit
from src.auditing.validate_compliance import ComplianceAuditor
from src.core.agent_dispatcher import ROLE_MAP, get_role_prompt_path
from src.interfaces import SquadEventBus
from src.lib.orchestration_lib import get_config, get_logger, resolve_vault_and_workspace

# -----------------------------------------------------------------------------------------------

_AGENT_CLASS_SPECS: typeDict[str, tuple[str, str]] = {
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

# -----------------------------------------------------------------------------------------------


class SquadAgentEvaluator(SquadEventBus):
    """
    In-memory SquadEventBus and isolated single-agent evaluation runner.
    Executes one persona independently against a target repository in read-only mode
    and grades protocol coherency, tool hygiene, and mechanical ground-truth alignment.
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
        task: str = "",
        model: str = "",
        read_only: bool = True,
        include_ground_truth: bool = True,
    ) -> typeDict[str, typeAny]:
        """Executes a single-turn multi-tool evaluation of one persona and returns its scorecard."""
        self._callbacks.clear()
        self.published_events.clear()

        target_path = self.resolve_target_repo(repo)
        rel_repo = str(target_path.relative_to(self.workspace_root)) if target_path != self.workspace_root else "."
        agent = self.instantiate_agent(role=role, read_only=read_only)
        if model.strip():
            agent.model_name = model.strip()
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

        session_id = f"eval-{agent.role_name}"
        user_payload: typeDict[str, typeAny] = {
            "sender": "user",
            "session_id": session_id,
            "content": addressed_prompt,
            "task_context": {
                "target_brain_id": agent.target_brain_id,
                "target_workspace_path": str(self.workspace_root),
            },
        }

        if model.strip():
            # Keep custom model override across _refresh_llm_config inside think_and_respond
            self.config.data.setdefault("capabilities", {}).setdefault("squad_agent", {})["gemini_model"] = model.strip()

        start_ts = timeMonotonic()
        for cb in list(self._callbacks):
            await cb(user_payload)
        elapsed_sec = round(timeMonotonic() - start_ts, 3)
        await agent.stop()

        agent_reply = ""
        tool_calls: typeList[typeDict[str, typeAny]] = []
        if self.published_events:
            last_payload = self.published_events[-1]["payload"]
            agent_reply = str(last_payload.get("content", ""))
            raw_calls = last_payload.get("tool_calls")
            if isinstance(raw_calls, list):
                tool_calls = raw_calls

        exposed_tool_names = [getattr(t, "__name__", str(t)) for t in agent._get_effective_tools()]
        mutating_exposed = [t for t in exposed_tool_names if t in _MUTATING_TOOL_NAMES]
        mutating_attempted = [c["name"] for c in tool_calls if c.get("name") in _MUTATING_TOOL_NAMES]
        read_errors = [
            c for c in tool_calls
            if str(c.get("result", "")).startswith("Error reading file")
        ]

        scorecard: typeDict[str, typeAny] = {
            "role": agent.role_name,
            "target_repo": rel_repo,
            "target_abs_path": str(target_path),
            "model_name": agent.model_name,
            "live_llm_client": agent.client is not None,
            "read_only": agent.read_only,
            "elapsed_seconds": elapsed_sec,
            "exposed_tools": exposed_tool_names,
            "coherency_checks": {
                "read_only_tools_clean": (len(mutating_exposed) == 0) if read_only else True,
                "zero_mutations_executed": len(mutating_attempted) == 0,
                "scan_header_present": "[SCAN]" in agent_reply,
                "used_file_listing": any(c.get("name") == "list_workspace_files" for c in tool_calls),
                "blind_read_error_count": len(read_errors),
            },
            "tool_calls_count": len(tool_calls),
            "tool_calls": tool_calls,
            "agent_response": agent_reply,
        }

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
            f"{self.Name} : Completed eval for role='{agent.role_name}' repo='{rel_repo}' "
            f"(tools={len(tool_calls)}, scan={scorecard['coherency_checks']['scan_header_present']}, "
            f"elapsed={elapsed_sec}s)"
        )
        return scorecard


# -----------------------------------------------------------------------------------------------


def format_eval_markdown(scorecard: typeDict[str, typeAny]) -> str:
    """Formats an evaluation scorecard dictionary into a human-readable Markdown report."""
    checks = scorecard["coherency_checks"]
    mode_str = "LIVE GEMINI SDK" if scorecard["live_llm_client"] else "OFFLINE MOCK (GEMINI_API_KEY unset)"
    lines: typeList[str] = [
        f"# 🧪 Squad Agent Evaluation Scorecard: `{scorecard['role']}`",
        "",
        f"- **Target Repo**: `{scorecard['target_repo']}` (`{scorecard['target_abs_path']}`)",
        f"- **Execution Mode**: `{mode_str}` | **Model**: `{scorecard['model_name']}` | **Read-Only**: `{scorecard['read_only']}`",
        f"- **Elapsed**: `{scorecard['elapsed_seconds']}s` | **Exposed Tools**: `{', '.join(scorecard['exposed_tools'])}`",
        "",
        "## 1. Coherency & Safety Gate Checks",
        f"- **Read-Only Tool Isolation**: `{'PASS' if checks['read_only_tools_clean'] else 'FAIL'}`",
        f"- **Zero Mutating Calls**: `{'PASS' if checks['zero_mutations_executed'] else 'FAIL'}`",
        f"- **`[SCAN]` Telemetry Header**: `{'PASS' if checks['scan_header_present'] else 'MISSING'}`",
        f"- **Used `list_workspace_files`**: `{checks['used_file_listing']}`",
        f"- **Tool Calls Executed**: `{scorecard['tool_calls_count']}` (Blind Read Errors: `{checks['blind_read_error_count']}`)",
    ]

    gt = scorecard.get("ground_truth")
    if isinstance(gt, dict):
        lines.extend([
            "",
            "## 2. Deterministic Ground-Truth Baseline",
            f"- **`validate-compliance` (`--strict-imports --strict-lean`)**: `{gt['compliance_violation_count']}` violation(s)",
            f"- **`debloat-audit`**: `{gt['debloat_finding_count']}` bloat finding(s) | `{gt['debloat_safe_invariant_count']}` Safe-by-Design invariant(s)",
        ])

    lines.extend([
        "",
        "## 3. Agent Output",
        "",
        scorecard["agent_response"] or "_(No response emitted)_",
        "",
    ])
    return "\n".join(lines)


# -----------------------------------------------------------------------------------------------


def main() -> None:
    """CLI entrypoint for `python3 08-Squad-Agent/main.py eval-agent`."""
    parser = argparseArgumentParser(
        description="Run a single 08-Squad-Agent persona independently in read-only mode with ground-truth grading."
    )
    parser.add_argument("--role", "-r", required=True, help="Squad persona slug (e.g. patternsentinel, debloatsentinel, gospecialist)")
    parser.add_argument("--repo", "-p", default=".", help="Target repository path relative to workspace root (default: .)")
    parser.add_argument("--task", "-t", default="", help="Optional custom evaluation prompt")
    parser.add_argument("--model", "-m", default="", help="Optional Gemini model override for A/B testing")
    parser.add_argument("--readonly", action="store_true", default=True, help="Enforce strict read-only tool lock (default: True)")
    parser.add_argument("--skip-ground-truth", action="store_true", help="Skip running ComplianceAuditor and debloat-audit")
    parser.add_argument("--json", action="store_true", help="Emit JSON scorecard to stdout")
    parser.add_argument("--output", "-o", default="", help="Optional file path to save the report")
    args = parser.parse_args()

    logger = get_logger("EvalAgent")
    config = get_config()
    evaluator = SquadAgentEvaluator(config=config, logger=logger)

    try:
        scorecard = asyncioRun(
            evaluator.evaluate(
                role=args.role,
                repo=args.repo,
                task=args.task,
                model=args.model,
                read_only=True,
                include_ground_truth=not args.skip_ground_truth,
            )
        )
    except (ValueError, FileNotFoundError) as err:
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
    if not checks["read_only_tools_clean"] or not checks["zero_mutations_executed"]:
        sysExit(1)
    sysExit(0)


if __name__ == "__main__":
    main()
