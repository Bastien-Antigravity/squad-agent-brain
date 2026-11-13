#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Real-Time Fleet Incident Subscriber & Capability-Aware Tiered Auto-Repair Coordinator.
Listens on brain-partitioned NATS subjects emitted by watchdog-agent, enriches incidents
with correlated TimescaleDB history & source snippets, classifies severity Tiers 1-4 per
Prompt-Fleet-AutoRepair.md, and gates mutations behind isolated /tmp git worktree tests
and 3-strike circuit breakers.

DATA FLOW:
1. Subscribes to '<prefix>[.<brain_id>].fleet.incident' on SquadEventBus.
2. Enforces RestartCircuitBreaker (<=3 strikes / 120s) and EventDeduplicator.
3. Queries watchdog_agent.fleet_error_logs + read-only source context around target file.
4. Performs Gemini/deterministic Tier 1-4 triage; verifies patches inside /tmp git worktrees
   when writable host & toolchains exist, else creates proposal for 1-click Telegram/REST approval.
5. Persists incident records into watchdog_agent.fleet_incidents and dispatches alerts.

KEY PARAMETERS:
- event_bus: SquadEventBus NATS/Local pub-sub handle.
- pg_pool: PostgreSQL pool targeting obsidiandb schema watchdog_agent.
- notif_client: NotificationClient for real-time operator alerts.
"""

import asyncio
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time
from typing import Any, Callable, Dict, List, Optional, Tuple
import urllib.error
import urllib.request

from google import genai
from google.genai import types

from microservice_toolbox.logger import ensure_safe_logger
from src.interfaces import SquadEventBus
from src.lib.orchestration_lib import resolve_vault_and_workspace
from src.lib.pg_pool import (
    ensure_fleet_error_schema,
    list_fleet_incidents,
    query_recent_fleet_errors,
    upsert_fleet_incident,
)

# -----------------------------------------------------------------------------

_MAX_MEMORY_INCIDENTS = 200
_MAX_PATCH_LINES = 250
_OPEN_INCIDENT_STATUSES = frozenset({
    "AWAITING_APPROVAL",
    "PROPOSAL_ONLY",
    "FROZEN",
    "UPSTREAM_BLOCKED",
    "VERIFICATION_FAILED",
    "DIRTY_WORKTREE_BLOCKED",
})
_BLOCKED_PATCH_FILES = frozenset({"version.txt", ".env", "docker-compose.yaml", "docker-compose.yml"})
_TIER_NAMES = {
    1: "Tier 1: Port / Lock Contention",
    2: "Tier 2: Configuration / Symlink Drift",
    3: "Tier 3: Upstream Dependency Outage",
    4: "Tier 4: Code Defect / Runtime Panic",
}


def _get_cap_section(config: Any, section: str) -> Dict[str, Any]:
    """Merges global config-server capabilities[section] with local service slice config.data[section]."""
    if config is None:
        return {}
    data = getattr(config, "data", None) or {}
    merged: Dict[str, Any] = {}
    global_cap = (data.get("capabilities") or {}).get(section)
    if global_cap:
        merged.update(global_cap)
    local_cap = data.get(section)
    if local_cap:
        merged.update(local_cap)
    return merged


def _parse_bool_flag(raw: Any, *, field_name: str) -> bool:
    """Parses YAML boolean or env-expanded string ('true'/'false'), failing fast if malformed."""
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        norm = raw.strip().lower()
        if norm in ("true", "1", "yes"):
            return True
        if norm in ("false", "0", "no"):
            return False
    raise ValueError(f"AutoRepair : Invalid boolean value for '{field_name}': {raw!r}")


def _resolve_autorepair_enabled(squad_cap: Dict[str, Any]) -> bool:
    """Validates and extracts mandatory startup autorepair.enabled flag from AppConfig."""
    autorepair_cap = squad_cap.get("autorepair")
    if not isinstance(autorepair_cap, dict) or "enabled" not in autorepair_cap:
        raise ValueError(
            "AutoRepair : Missing required 'squad_agent.autorepair.enabled' in configuration file"
        )
    return _parse_bool_flag(autorepair_cap["enabled"], field_name="squad_agent.autorepair.enabled")


def resolve_incident_subject(subject_prefix: str, brain_id: str) -> str:
    """Matches watchdog-agent's ResolveIncidentSubject NATS partitioning convention."""
    prefix = subject_prefix.strip() if subject_prefix and subject_prefix.strip() else "bastien-antigravity"
    clean_brain = brain_id.strip() if brain_id else ""
    if not clean_brain or clean_brain in ("obsidian-brain", "root", "main"):
        return f"{prefix}.fleet.incident"
    return f"{prefix}.{clean_brain}.fleet.incident"


# -----------------------------------------------------------------------------


def classify_incident_tier(payload: Dict[str, Any]) -> int:
    """Classifies an incident payload into Operational Tiers 1-4."""
    haystack = " ".join([
        str(payload.get("message", "")),
        str(payload.get("stack_trace", "")),
    ]).lower()

    if any(k in haystack for k in (
        "address already in use",
        "bind: address already in use",
        "failed to acquire file lock",
        "watchdog-agent.lock",
    )):
        return 1

    if any(k in haystack for k in (
        "standalone.yaml",
        "missing config section",
        "unexpanded env",
        "config load error",
        "symlink",
    )):
        return 2

    if any(k in haystack for k in (
        "connection refused",
        "connection timed out",
        "failed to connect to nats",
        "failed to ping postgresql",
        "failed to resolve",
        "config_server",
        "timescale_db",
    )):
        return 3

    return 4


def _incident_signature(brain_id: str, service_name: str, payload: Dict[str, Any]) -> Tuple[str, str, str, str, str]:
    return (
        brain_id,
        service_name,
        str(payload.get("filename", "")),
        str(payload.get("line_number", "")),
        str(payload.get("level_str", "ERROR")),
    )


def validate_proposed_diff(diff_text: str, git_root: Path, service_dir: Path) -> Tuple[bool, str, List[str]]:
    """Validates unified diff syntax, size limits, and target path containment inside service_dir."""
    if not diff_text or not diff_text.strip():
        return False, "Empty diff payload.", []
    lines = diff_text.splitlines()
    if len(lines) > _MAX_PATCH_LINES:
        return False, f"Patch exceeds safety bound ({len(lines)} > {_MAX_PATCH_LINES} lines).", []
    if not any(line.startswith("@@ ") for line in lines):
        return False, "Patch lacks unified diff hunk header (@@).", []

    raw_paths: List[str] = []
    for line in lines:
        if line.startswith("--- ") or line.startswith("+++ "):
            token = line[4:].split("\t", 1)[0].strip()
            if token == "/dev/null":
                continue
            if token.startswith("a/") or token.startswith("b/"):
                token = token[2:]
            if token.startswith(f"{git_root.name}/"):
                token = token[len(git_root.name) + 1:]
            raw_paths.append(token)

    if not raw_paths:
        return False, "Patch contains no target file headers.", []

    resolved_service = service_dir.resolve()
    resolved_git = git_root.resolve()
    clean_paths: List[str] = []
    for rel_str in raw_paths:
        rel_path = Path(rel_str)
        if not rel_str or rel_path.is_absolute() or ".." in rel_path.parts:
            return False, f"Unsafe patch path '{rel_str}'.", []
        name_lower = rel_path.name.lower()
        if (
            ".git" in rel_path.parts
            or name_lower in _BLOCKED_PATCH_FILES
            or name_lower.endswith((".pem", ".key", ".sql"))
            or name_lower.startswith(".env")
        ):
            return False, f"Protected file '{rel_str}' cannot be auto-patched.", []
        try:
            abs_target = (resolved_git / rel_path).resolve()
            abs_target.relative_to(resolved_service)
        except ValueError:
            return False, f"Patch target '{rel_str}' escapes service directory '{resolved_service.name}'.", []
        if rel_str not in clean_paths:
            clean_paths.append(rel_str)

    return True, "ok", clean_paths


# -----------------------------------------------------------------------------


@dataclass
class RuntimeCapabilities:
    """Detects whether this Squad Agent instance can mutate files / run tests or must stay proposal-only."""

    workspace_writable: bool
    git_available: bool
    toolchains: Dict[str, str]
    watchdog_rest_url: str
    auto_apply: bool

    @classmethod
    def detect(cls, workspace_root: Path, config: Any, *, auto_apply: bool = False) -> "RuntimeCapabilities":
        writable = False
        probe_path = workspace_root / f".squad_write_probe_{os.getpid()}"
        try:
            probe_path.write_text("", encoding="utf-8")
            probe_path.unlink()
            writable = True
        except OSError:
            writable = False

        toolchains = {}
        for tool in ("go", "cargo", "pytest", "python3"):
            resolved = shutil.which(tool)
            if resolved:
                toolchains[tool] = resolved

        watchdog_url = ""
        wd_cap = _get_cap_section(config, "watchdog_agent")
        if config is not None and wd_cap.get("rest_port"):
            addr = config.get_rest_addr("watchdog_agent")
            if addr and ":" in addr and not addr.startswith(":"):
                watchdog_url = f"http://{addr}"

        return cls(
            workspace_writable=writable,
            git_available=shutil.which("git") is not None,
            toolchains=toolchains,
            watchdog_rest_url=watchdog_url,
            auto_apply=auto_apply,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "workspace_writable": self.workspace_writable,
            "git_available": self.git_available,
            "toolchains": sorted(self.toolchains.keys()),
            "watchdog_rest_configured": bool(self.watchdog_rest_url),
            "auto_apply": self.auto_apply,
            "execution_mode": "verified_worktree" if (self.workspace_writable and self.git_available) else "proposal_only",
        }


# -----------------------------------------------------------------------------


class RestartCircuitBreaker:
    """Enforces the 3-strike sliding window circuit breaker per (brain_id, service_name)."""

    def __init__(self, *, max_strikes: int = 3, window_sec: float = 120.0):
        self.max_strikes = max_strikes
        self.window_sec = window_sec
        self._strikes: Dict[Tuple[str, str], List[float]] = {}
        self._frozen: Dict[Tuple[str, str], float] = {}

    def _prune(self, key: Tuple[str, str], now: float) -> List[float]:
        cutoff = now - self.window_sec
        active = [ts for ts in self._strikes.get(key, []) if ts >= cutoff]
        self._strikes[key] = active
        return active

    def is_frozen(self, brain_id: str, service_name: str, now: Optional[float] = None) -> bool:
        t = now if now is not None else time.monotonic()
        key = (brain_id, service_name)
        frozen_at = self._frozen.get(key)
        if frozen_at is None:
            return False
        if t - frozen_at > self.window_sec:
            del self._frozen[key]
            self._strikes[key] = []
            return False
        return True

    def record_strike(self, brain_id: str, service_name: str, now: Optional[float] = None) -> Tuple[bool, int]:
        """Records a repair/restart strike; returns (is_now_frozen, count_in_window)."""
        t = now if now is not None else time.monotonic()
        key = (brain_id, service_name)
        if self.is_frozen(brain_id, service_name, t):
            return True, len(self._strikes.get(key, []))
        active = self._prune(key, t)
        active.append(t)
        if len(active) > self.max_strikes:
            self._frozen[key] = t
            return True, len(active)
        return False, len(active)

    def status_snapshot(self) -> Dict[str, Any]:
        now = time.monotonic()
        frozen_services = [
            f"{brain}:{svc}"
            for (brain, svc) in list(self._frozen.keys())
            if self.is_frozen(brain, svc, now)
        ]
        return {
            "max_strikes": self.max_strikes,
            "window_sec": self.window_sec,
            "frozen_services": frozen_services,
        }

    def unfreeze(self, brain_id: str, service_name: str) -> bool:
        """Clears frozen circuit breaker state and strike history for a service."""
        key = (brain_id, service_name)
        was_frozen = key in self._frozen
        self._frozen.pop(key, None)
        self._strikes.pop(key, None)
        return was_frozen


# -----------------------------------------------------------------------------


class AutoRepairCoordinator:
    """Real-time Watchdog incident consumer and capability-aware Tiered Auto-Repair coordinator."""

    def __init__(
        self,
        *,
        config: Any,
        logger: Any,
        pg_pool: Any,
        event_bus: Optional[SquadEventBus],
        notif_client: Optional[Any] = None,
        on_incident_change: Optional[Callable[[], None]] = None,
    ):
        self.config = config
        self.logger = ensure_safe_logger(logger)
        self.pool = pg_pool
        self.event_bus = event_bus
        self.notif_client = notif_client
        self.on_incident_change = on_incident_change

        vault_root, workspace_root = resolve_vault_and_workspace(__file__)
        self.vault_root = vault_root
        self.workspace_root = workspace_root

        if self.config is None:
            raise ValueError("AutoRepair : Validated AppConfig is required at startup")

        self._squad_cap = _get_cap_section(self.config, "squad_agent")
        self._nats_cap = _get_cap_section(self.config, "nats")
        self.enabled = _resolve_autorepair_enabled(self._squad_cap)
        self._last_cfg_enabled = self.enabled

        # auto_apply always starts disabled (False) and requires authenticated runtime toggle
        self.capabilities = RuntimeCapabilities.detect(
            self.workspace_root,
            self.config,
            auto_apply=False,
        )
        self.circuit_breaker = RestartCircuitBreaker(max_strikes=3, window_sec=120.0)

        self.brain_id = self._resolve_brain_id()
        self.subject_prefix = self._resolve_subject_prefix()
        self.incident_topic = resolve_incident_subject(self.subject_prefix, self.brain_id)
        self.system_prompt = self._load_autorepair_prompt()
        self.genai_client = self._resolve_genai_client()
        self.model_name = self._resolve_model_name()

        self._recent_order: deque = deque(maxlen=_MAX_MEMORY_INCIDENTS)
        self._incidents: Dict[str, Dict[str, Any]] = {}
        self._open_by_signature: Dict[Tuple[str, str, str, str, str], str] = {}
        self._seen_order: deque = deque(maxlen=1000)
        self._seen_hashes: set = set()
        self._nats_subs: List[Any] = []
        self._incident_cb: Optional[Callable[[Dict[str, Any]], Any]] = None
        self._worktree_seq: int = 0

        self.paused_reason: str = "" if self.enabled else "Disabled via configuration (squad_agent.autorepair.enabled=false)"
        self.updated_at: str = datetime.now(timezone.utc).isoformat()
        self._metrics: Dict[str, int] = {
            "processed": 0,
            "coalesced": 0,
            "skipped_while_disabled": 0,
            "repaired": 0,
        }

        if hasattr(self.config, "on_live_conf_update"):
            self.config.on_live_conf_update(self._on_live_conf_update)

    def _on_live_conf_update(self, _updated: Any) -> None:
        """Applies live AppConfig changes to autorepair.enabled without overriding operator toggles."""
        squad_cap = _get_cap_section(self.config, "squad_agent")
        if "autorepair" not in squad_cap:
            return
        try:
            cfg_enabled = _resolve_autorepair_enabled(squad_cap)
        except ValueError as err:
            self.logger.error(f"AutoRepair : Ignoring malformed live config update ({err})")
            return
        if cfg_enabled == self._last_cfg_enabled:
            return
        self._squad_cap = squad_cap
        self._last_cfg_enabled = cfg_enabled
        reason = "" if cfg_enabled else "Disabled via live configuration update"
        self.set_enabled(cfg_enabled, reason=reason)

    def set_enabled(self, enabled: bool, reason: str = "", auto_apply: Optional[bool] = None) -> Dict[str, Any]:
        """Enables or disables autonomous AutoRepair incident triage dynamically on the fly."""
        self.enabled = bool(enabled)
        if auto_apply is not None:
            self.capabilities.auto_apply = bool(auto_apply)
        self.paused_reason = "" if self.enabled else (reason.strip() or "Paused on the fly by operator")
        self.updated_at = datetime.now(timezone.utc).isoformat()
        self.logger.info(
            f"AutoRepair : Runtime state updated -> enabled={self.enabled}, auto_apply={self.capabilities.auto_apply}"
            + (f" ({self.paused_reason})" if self.paused_reason else "")
        )
        if self.on_incident_change:
            self.on_incident_change()
        return self.get_autorepair_status()

    def get_autorepair_status(self) -> Dict[str, Any]:
        """Returns current runtime toggle, capabilities, open incident count, and circuit breaker snapshot."""
        open_count = sum(
            1 for inc in self._incidents.values() if inc.get("status") in _OPEN_INCIDENT_STATUSES
        )
        cap_dict = self.capabilities.to_dict()
        return {
            "enabled": self.enabled,
            "paused_reason": self.paused_reason,
            "updated_at": self.updated_at,
            "incident_topic": self.incident_topic,
            "brain_id": self.brain_id,
            "open_incidents": open_count,
            "metrics": dict(self._metrics),
            "circuit_breaker": self.circuit_breaker.status_snapshot(),
            **cap_dict,
        }

    def unfreeze_service(self, service_name: str, brain_id: Optional[str] = None) -> Dict[str, Any]:
        """Resets 3-strike circuit breaker freeze for a service and closes stale FROZEN signature locks."""
        target_brain = brain_id or self.brain_id
        was_frozen = self.circuit_breaker.unfreeze(target_brain, service_name)
        for sig, inc_id in list(self._open_by_signature.items()):
            if sig[0] == target_brain and sig[1] == service_name:
                rec = self._incidents.get(inc_id)
                if rec and rec.get("status") == "FROZEN":
                    self._open_by_signature.pop(sig, None)
        if self.on_incident_change:
            self.on_incident_change()
        return {
            "service_name": service_name,
            "brain_id": target_brain,
            "was_frozen": was_frozen,
            "circuit_breaker": self.circuit_breaker.status_snapshot(),
        }

    def _resolve_brain_id(self) -> str:
        raw = self._squad_cap.get("target_brain_id") or os.environ.get("TARGET_BRAIN_ID") or "obsidian-brain"
        return str(raw).strip() or "obsidian-brain"

    def _resolve_subject_prefix(self) -> str:
        raw = self._nats_cap.get("subject_prefix") or "bastien-antigravity"
        return str(raw).strip() or "bastien-antigravity"

    def _resolve_model_name(self) -> str:
        raw = self._squad_cap.get("gemini_model") or os.environ.get("GEMINI_MODEL") or "gemini-2.5-flash"
        return str(raw).strip() or "gemini-2.5-flash"

    def _resolve_genai_client(self) -> Optional[Any]:
        data = getattr(self.config, "data", None)
        if isinstance(data, dict) and data.get("genai_client"):
            return data["genai_client"]
        raw_key = str(self._squad_cap.get("gemini_api_key") or os.environ.get("GEMINI_API_KEY") or "").strip()
        if raw_key.startswith("${"):
            raw_key = ""
        if raw_key.startswith("ENC(") and raw_key.endswith(")"):
            try:
                raw_key = self.config.decrypt_secret(raw_key)
            except Exception as err:
                self.logger.error(f"AutoRepair : Failed to decrypt squad_agent.gemini_api_key ({err}).")
                return None
        if not raw_key:
            return None
        try:
            return genai.Client(api_key=raw_key)
        except Exception as e:
            self.logger.warning(f"AutoRepair : Could not initialize Gemini client ({e}); deterministic triage active.")
            return None

    def _load_autorepair_prompt(self) -> str:
        prompt_path = self.vault_root / "07-Core-KMS" / "Role-Prompts" / "15-AutoRepair" / "Prompt-Fleet-AutoRepair.md"
        try:
            return prompt_path.read_text(encoding="utf-8")
        except OSError:
            return "You are the Fleet Healer & Auto-Repair Sentinel. Produce concise root_cause and minimal unified diff."

    # -------------------------------------------------------------------------

    async def start(self) -> None:
        """Verifies schema readiness, hydrates open incidents, and subscribes to NATS incident alerts."""
        loop = asyncio.get_running_loop()
        if self.pool:
            await loop.run_in_executor(None, ensure_fleet_error_schema, self.pool, self.logger)
            existing = await loop.run_in_executor(
                None, lambda: list_fleet_incidents(self.pool, self.logger, brain_id=self.brain_id, limit=100)
            )
            for item in reversed(existing):
                self._index_incident_memory(item)

        if not self.event_bus:
            self.logger.warning("AutoRepair : EventBus not configured; running without live NATS incident subscription.")
            return

        async def _incident_cb(payload: Dict[str, Any]) -> None:
            try:
                await self.handle_incident(payload)
            except Exception as err:
                self.logger.error(f"AutoRepair : Unhandled incident processing failure: {err}")

        self._incident_cb = _incident_cb
        subs = await self.event_bus.subscribe(self.incident_topic, callback=_incident_cb)
        if subs:
            self._nats_subs = subs
        self.logger.info(
            f"AutoRepair : Listening on '{self.incident_topic}' (enabled={self.enabled}, mode={self.capabilities.to_dict()['execution_mode']})"
        )

    async def stop(self) -> None:
        if self.event_bus and (self._nats_subs or self._incident_cb is not None):
            await self.event_bus.unsubscribe(self.incident_topic, self._incident_cb, self._nats_subs)
            self._nats_subs = []
            self._incident_cb = None

    # -------------------------------------------------------------------------

    def _index_incident_memory(self, record: Dict[str, Any]) -> None:
        inc_id = record["incident_id"]
        if inc_id not in self._incidents and len(self._recent_order) == self._recent_order.maxlen:
            evicted = self._recent_order[0]
            self._incidents.pop(evicted, None)
        if inc_id not in self._incidents:
            self._recent_order.append(inc_id)
        self._incidents[inc_id] = record

        sig = _incident_signature(
            str(record.get("brain_id") or self.brain_id),
            str(record.get("service_name", "")),
            record,
        )
        if record.get("status") in _OPEN_INCIDENT_STATUSES:
            self._open_by_signature[sig] = inc_id
        elif self._open_by_signature.get(sig) == inc_id:
            self._open_by_signature.pop(sig, None)

    def _remember_incident(self, record: Dict[str, Any]) -> None:
        self._index_incident_memory(record)
        if self.pool:
            upsert_fleet_incident(self.pool, self.logger, record)

    def _resolve_service_repo(self, service_name: str) -> Optional[Path]:
        if not service_name:
            return None
        direct = (self.workspace_root / service_name).resolve()
        if direct.is_dir():
            return direct
        dashed = (self.workspace_root / service_name.replace("_", "-")).resolve()
        if dashed.is_dir():
            return dashed
        if service_name in ("squad_agent", "squad-agent", "08-Squad-Agent"):
            cand = self.vault_root / "08-Squad-Agent"
            if cand.is_dir():
                return cand
        if service_name in ("rag_engine", "rag-engine", "09-RAG-Engine"):
            cand = self.vault_root / "09-RAG-Engine"
            if cand.is_dir():
                return cand
        return None

    def _read_source_context(self, service_name: str, filename: str, line_number: str) -> Tuple[str, str]:
        """Reads a bounded 30-line source excerpt without leaving workspace_root."""
        if not filename:
            return "", ""
        repo_dir = self._resolve_service_repo(service_name)
        search_root = repo_dir or self.workspace_root

        target: Optional[Path] = None
        rel_candidate = Path(filename)
        if not rel_candidate.is_absolute():
            direct = (search_root / rel_candidate).resolve()
            try:
                direct.relative_to(self.workspace_root)
                if direct.is_file():
                    target = direct
            except ValueError:
                return "", ""

        if target is None:
            basename = Path(filename).name
            for found in search_root.rglob(basename):
                if any(part in (".git", "target", "node_modules", ".venv", "vendor") for part in found.parts):
                    continue
                try:
                    resolved = found.resolve()
                    resolved.relative_to(self.workspace_root)
                    if resolved.is_file():
                        target = resolved
                        break
                except ValueError:
                    continue

        if target is None:
            return "", ""

        try:
            lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
            relpath = str(target.relative_to(self.workspace_root))
        except (OSError, ValueError):
            return "", ""

        try:
            ln = max(1, int(line_number))
        except (ValueError, TypeError):
            ln = 1
        start = max(0, ln - 15)
        end = min(len(lines), ln + 15)
        excerpt = "\n".join(f"{idx + 1}: {lines[idx]}" for idx in range(start, end))
        return relpath, excerpt

    # -------------------------------------------------------------------------

    async def _run_rca(
        self,
        payload: Dict[str, Any],
        tier: int,
        recent_errors: List[Dict[str, Any]],
        relpath: str,
        excerpt: str,
    ) -> Dict[str, str]:
        tier_label = _TIER_NAMES.get(tier, _TIER_NAMES[4])
        default_rca = {
            "root_cause": f"{tier_label} detected in {payload.get('service_name', 'unknown')}: {payload.get('message', '')}",
            "target_relpath": relpath,
            "proposed_diff": "",
            "action_hint": payload.get("suggested_action") or f"Inspect {relpath or payload.get('filename', 'service logs')} around line {payload.get('line_number', '?')}",
        }
        if not self.genai_client:
            return default_rca

        prompt_body = json.dumps(
            {
                "incident": payload,
                "classified_tier": tier,
                "target_relpath": relpath,
                "source_excerpt": excerpt[:4000],
                "recent_db_errors": recent_errors[:5],
                "capabilities": self.capabilities.to_dict(),
                "instruction": (
                    "Respond strictly with JSON object keys: "
                    "root_cause (string), target_relpath (string), proposed_diff (minimal unified diff or empty string), action_hint (string)."
                ),
            },
            indent=2,
        )
        try:
            resp = await asyncio.to_thread(
                self.genai_client.models.generate_content,
                model=self.model_name,
                contents=[types.Content(role="user", parts=[types.Part.from_text(text=prompt_body)])],
                config=types.GenerateContentConfig(
                    system_instruction=self.system_prompt,
                    response_mime_type="application/json",
                ),
            )
            parsed = json.loads(resp.text or "{}")
            return {
                "root_cause": str(parsed.get("root_cause") or default_rca["root_cause"]),
                "target_relpath": str(parsed.get("target_relpath") or relpath),
                "proposed_diff": str(parsed.get("proposed_diff") or ""),
                "action_hint": str(parsed.get("action_hint") or default_rca["action_hint"]),
            }
        except Exception as e:
            self.logger.warning(f"AutoRepair : Gemini RCA fallback ({e}); returning deterministic triage.")
            return default_rca

    # -------------------------------------------------------------------------

    def _resolve_git_root(self, repo_dir: Path) -> Tuple[Optional[Path], Path]:
        """Resolves the enclosing git repository root inside workspace_root and its relative service subdir."""
        res = subprocess.run(
            ["git", "-C", str(repo_dir), "rev-parse", "--show-toplevel"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=10,
        )
        if res.returncode != 0 or not res.stdout.strip():
            return None, Path(".")
        git_root = Path(res.stdout.strip()).resolve()
        try:
            git_root.relative_to(self.workspace_root.resolve())
            rel_subdir = repo_dir.resolve().relative_to(git_root)
        except ValueError:
            return None, Path(".")
        return git_root, rel_subdir

    def _apply_patch_in_dir(self, git_root: Path, diff_text: str) -> subprocess.CompletedProcess:
        """Applies a unified diff at git_root, handling workspace-prefixed paths (-p2) cleanly."""
        cmd = ["git", "apply", "--whitespace=nowarn", "-"]
        if f"--- a/{git_root.name}/" in diff_text and f"+++ b/{git_root.name}/" in diff_text:
            cmd = ["git", "apply", "-p2", "--whitespace=nowarn", "-"]
        return subprocess.run(
            cmd,
            cwd=str(git_root),
            input=diff_text,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=20,
        )

    def _verify_patch_in_worktree(self, service_name: str, target_relpath: str, diff_text: str, incident_id: str) -> Tuple[bool, str]:
        """Verifies a candidate unified diff inside an isolated temporary git worktree without mutating HEAD."""
        if not diff_text.strip() or not self.capabilities.workspace_writable or not self.capabilities.git_available:
            return False, "Skipped isolated verification: writable workspace or git unavailable."

        repo_dir = self._resolve_service_repo(service_name)
        if repo_dir is None:
            return False, f"No repository directory found for service '{service_name}'."
        git_root, rel_subdir = self._resolve_git_root(repo_dir)
        if git_root is None:
            return False, f"No independent git repository found for service '{service_name}'."

        diff_ok, diff_reason, _ = validate_proposed_diff(diff_text, git_root, repo_dir)
        if not diff_ok:
            return False, f"Patch safety gate rejected candidate diff: {diff_reason}"

        self._worktree_seq += 1
        tmp_base = Path(tempfile.gettempdir()) / f"squad-autorepair-{incident_id}-{os.getpid()}-{self._worktree_seq}"
        worktree_added = False
        try:
            add_res = subprocess.run(
                ["git", "worktree", "add", "--detach", str(tmp_base), "HEAD"],
                cwd=str(git_root),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=30,
            )
            if add_res.returncode != 0:
                return False, f"git worktree add failed: {add_res.stdout.strip()}"
            worktree_added = True

            apply_res = self._apply_patch_in_dir(tmp_base, diff_text)
            if apply_res.returncode != 0:
                return False, f"Candidate diff rejected by git apply: {apply_res.stdout.strip()}"

            target_test_dir = tmp_base / rel_subdir if str(rel_subdir) != "." else tmp_base
            test_cmd = self._select_verification_command(target_test_dir)
            if not test_cmd:
                return False, "No test toolchain available for isolated verification."

            test_res = subprocess.run(
                test_cmd,
                cwd=str(target_test_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=120,
            )
            output = test_res.stdout.strip()[-2000:]
            return test_res.returncode == 0, output
        except Exception as e:
            return False, f"Isolated worktree verification error: {e}"
        finally:
            if worktree_added:
                subprocess.run(
                    ["git", "worktree", "remove", "--force", str(tmp_base)],
                    cwd=str(git_root),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            shutil.rmtree(tmp_base, ignore_errors=True)
            subprocess.run(
                ["git", "worktree", "prune"],
                cwd=str(git_root),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

    def _select_verification_command(self, repo_dir: Path) -> Optional[List[str]]:
        if (repo_dir / "go.mod").is_file() and "go" in self.capabilities.toolchains:
            return [self.capabilities.toolchains["go"], "test", "-count=1", "./..."]
        if (repo_dir / "Cargo.toml").is_file() and "cargo" in self.capabilities.toolchains:
            return [self.capabilities.toolchains["cargo"], "test"]
        if "pytest" in self.capabilities.toolchains and (repo_dir / "tests").is_dir():
            return [self.capabilities.toolchains["pytest"], "-q"]
        if "python3" in self.capabilities.toolchains and (repo_dir / "tests").is_dir():
            return [self.capabilities.toolchains["python3"], "-m", "unittest", "discover", "-s", "tests"]
        return None

    # -------------------------------------------------------------------------

    def _check_upstream_dependencies(self) -> Tuple[bool, str]:
        """Checks configured upstream dependency listeners cleanly before restarting a Tier 3 service."""
        if not self.config:
            return True, "No AppConfig attached"
        for dep in ("timescale_db", "nats", "config_server"):
            try:
                addr = self.config.get_listen_addr(dep)
                host, port_str = addr.rsplit(":", 1)
                with socket.create_connection((host, int(port_str)), timeout=1.5):
                    pass
            except Exception as e:
                return False, f"Upstream dependency '{dep}' unreachable ({e})"
        return True, "All upstream dependencies reachable"

    def _trigger_watchdog_restart(self, service_name: str) -> Tuple[bool, str]:
        if not self.capabilities.watchdog_rest_url:
            return False, "Watchdog REST URL unavailable in current runtime configuration."
        url = f"{self.capabilities.watchdog_rest_url}/api/v1/watchdog/restart"
        body = json.dumps({"name": service_name}).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                resp_body = resp.read().decode("utf-8", errors="replace")
                return resp.status < 300, resp_body
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            return False, f"Watchdog restart call failed: {e}"

    def _append_audit_log(self, record: Dict[str, Any]) -> None:
        if not self.capabilities.workspace_writable:
            return
        log_path = self.vault_root / "05-Fleet-Operation" / "02-Deployment-Logs" / "AutoRepair-Log.md"
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        entry = (
            f"\n### [{ts}] Incident {record['incident_id']}: {record['service_name']}\n"
            f"- **Error**: {record.get('filename', '')}:{record.get('line_number', '')} - {record['message']}\n"
            f"- **Root Cause**: Tier {record['tier']} - {record.get('root_cause', '')}\n"
            f"- **Remedial Action**: {record.get('action_taken', record['status'])}\n"
            f"- **Verification**: {record.get('verification_output', 'N/A')[:240]}\n"
        )
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(entry)
        except OSError as e:
            self.logger.warning(f"AutoRepair : Could not append AutoRepair-Log.md ({e}).")

    # -------------------------------------------------------------------------

    def _seen_event(self, dedupe_key: str) -> bool:
        if not dedupe_key:
            return False
        if dedupe_key in self._seen_hashes:
            return True
        if len(self._seen_order) == self._seen_order.maxlen:
            evicted = self._seen_order[0]
            self._seen_hashes.discard(evicted)
        self._seen_order.append(dedupe_key)
        self._seen_hashes.add(dedupe_key)
        return False

    async def handle_incident(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Processes an incoming IncidentEvent cleanly with toggle gating, coalescing, and bounded side effects."""
        incident_id = str(payload.get("incident_id") or "").strip()
        service_name = str(payload.get("service_name") or "").strip()
        if not incident_id or not service_name:
            return {}

        if not self.enabled:
            self._metrics["skipped_while_disabled"] += 1
            return {
                "incident_id": incident_id,
                "service_name": service_name,
                "status": "DISABLED",
                "enabled": False,
                "reason": self.paused_reason,
            }

        dedupe_key = str(payload.get("event_hash") or incident_id)
        if self._seen_event(dedupe_key):
            return self._incidents.get(incident_id, {})

        brain_id = str(payload.get("brain_id") or self.brain_id)
        sig = _incident_signature(brain_id, service_name, payload)
        existing_id = self._open_by_signature.get(sig)
        if existing_id and existing_id in self._incidents:
            existing = self._incidents[existing_id]
            if existing.get("status") in _OPEN_INCIDENT_STATUSES:
                existing["occurrence_count"] = int(existing.get("occurrence_count", 1)) + int(payload.get("occurrence_count", 1))
                self._metrics["coalesced"] += 1
                self._remember_incident(existing)
                if self.on_incident_change:
                    self.on_incident_change()
                return existing

        self._metrics["processed"] += 1
        tier = classify_incident_tier(payload)
        loop = asyncio.get_running_loop()

        if self.circuit_breaker.is_frozen(brain_id, service_name):
            record = {
                "incident_id": incident_id,
                "brain_id": brain_id,
                "event_hash": str(payload.get("event_hash", "")),
                "service_name": service_name,
                "hostname": str(payload.get("hostname", "")),
                "level_str": str(payload.get("level_str", "ERROR")),
                "tier": tier,
                "status": "FROZEN",
                "filename": str(payload.get("filename", "")),
                "line_number": str(payload.get("line_number", "")),
                "message": str(payload.get("message", "")),
                "root_cause": "3-strike circuit breaker already tripped (>3 incidents in 120s).",
                "proposed_patch": "",
                "target_relpath": "",
                "verification_output": "",
                "action_taken": "Frozen: manual review required.",
                "occurrence_count": int(payload.get("occurrence_count", 1)),
            }
            self._remember_incident(record)
            await self._notify_operator("CRITICAL", record)
            return record

        recent_errors: List[Dict[str, Any]] = []
        if self.pool:
            recent_errors = await loop.run_in_executor(
                None,
                lambda: query_recent_fleet_errors(self.pool, self.logger, brain_id=brain_id, service_name=service_name, limit=10),
            )

        relpath, excerpt = self._read_source_context(
            service_name, str(payload.get("filename", "")), str(payload.get("line_number", ""))
        )
        rca = await self._run_rca(payload, tier, recent_errors, relpath, excerpt)

        verified = False
        verify_out = "Proposal-only mode: runtime lacks writable workspace or isolated test verification."
        if rca["proposed_diff"] and self.capabilities.workspace_writable and self.capabilities.git_available:
            verified, verify_out = await loop.run_in_executor(
                None,
                self._verify_patch_in_worktree,
                service_name,
                rca["target_relpath"],
                rca["proposed_diff"],
                incident_id,
            )

        record = {
            "incident_id": incident_id,
            "brain_id": brain_id,
            "event_hash": str(payload.get("event_hash", "")),
            "service_name": service_name,
            "hostname": str(payload.get("hostname", "")),
            "level_str": str(payload.get("level_str", "ERROR")),
            "tier": tier,
            "status": "AWAITING_APPROVAL",
            "filename": str(payload.get("filename", "")),
            "line_number": str(payload.get("line_number", "")),
            "message": str(payload.get("message", "")),
            "root_cause": rca["root_cause"],
            "proposed_patch": rca["proposed_diff"],
            "target_relpath": rca["target_relpath"],
            "verification_output": verify_out,
            "action_taken": rca["action_hint"],
            "occurrence_count": int(payload.get("occurrence_count", 1)),
        }

        self._remember_incident(record)

        can_auto_execute = self.capabilities.auto_apply and (tier in (1, 2, 3) or verified)
        if can_auto_execute:
            _, record = await self.approve_incident(incident_id)
        else:
            await self._notify_operator("ERROR", record)

        if self.on_incident_change:
            self.on_incident_change()
        return record

    # -------------------------------------------------------------------------

    async def approve_incident(self, incident_id: str) -> Tuple[bool, Dict[str, Any]]:
        """Applies a verified patch (when applicable) and restarts the affected service via Watchdog REST."""
        record = self.get_incident(incident_id)
        if not record:
            return False, {"error": f"Incident '{incident_id}' not found"}

        brain_id = record.get("brain_id", self.brain_id)
        service_name = record["service_name"]
        tier = int(record.get("tier", 4))

        frozen, strikes = self.circuit_breaker.record_strike(brain_id, service_name)
        if frozen:
            record["status"] = "FROZEN"
            record["action_taken"] = f"Circuit breaker tripped ({strikes} strikes/120s); restart aborted."
            self._remember_incident(record)
            await self._notify_operator("CRITICAL", record)
            return False, record

        loop = asyncio.get_running_loop()
        if tier == 3:
            deps_ok, dep_msg = await loop.run_in_executor(None, self._check_upstream_dependencies)
            if not deps_ok:
                record["status"] = "UPSTREAM_BLOCKED"
                record["action_taken"] = f"Deferred restart per Tier 3 invariant: {dep_msg}"
                self._remember_incident(record)
                return False, record

        has_patch = bool(record.get("proposed_patch"))
        if has_patch:
            if not self.capabilities.workspace_writable or not self.capabilities.git_available:
                record["status"] = "PROPOSAL_ONLY"
                record["action_taken"] = "Cannot apply diff in read-only or git-less environment."
                self._remember_incident(record)
                return False, record

            repo_dir = self._resolve_service_repo(service_name)
            git_root, _ = self._resolve_git_root(repo_dir) if repo_dir is not None else (None, Path("."))
            if repo_dir is None or git_root is None:
                return False, {"error": f"Git repository for '{service_name}' not found"}

            diff_ok, diff_reason, target_files = validate_proposed_diff(record["proposed_patch"], git_root, repo_dir)
            if not diff_ok:
                record["status"] = "VERIFICATION_FAILED"
                record["action_taken"] = f"Patch safety gate rejected diff: {diff_reason}"
                self._remember_incident(record)
                return False, record

            dirty_check = await loop.run_in_executor(
                None,
                lambda: subprocess.run(
                    ["git", "status", "--porcelain", "--", *target_files],
                    cwd=str(git_root),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                ),
            )
            if dirty_check.stdout.strip():
                record["status"] = "DIRTY_WORKTREE_BLOCKED"
                record["action_taken"] = f"Aborted apply: uncommitted local changes detected in {', '.join(target_files)}"
                self._remember_incident(record)
                return False, record

            verified, verify_out = await loop.run_in_executor(
                None,
                self._verify_patch_in_worktree,
                service_name,
                record.get("target_relpath", ""),
                record["proposed_patch"],
                incident_id,
            )
            record["verification_output"] = verify_out
            if not verified:
                record["status"] = "VERIFICATION_FAILED"
                record["action_taken"] = "Patch aborted: isolated worktree verification failed."
                self._remember_incident(record)
                return False, record

            ts_tag = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
            await loop.run_in_executor(
                None,
                lambda: subprocess.run(
                    ["git", "tag", f"restore-point/autorepair-{service_name}-{ts_tag}"],
                    cwd=str(git_root),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                ),
            )
            apply_res = await loop.run_in_executor(
                None,
                lambda: self._apply_patch_in_dir(git_root, record["proposed_patch"]),
            )
            if apply_res.returncode != 0:
                record["status"] = "APPLY_FAILED"
                record["action_taken"] = f"git apply failed: {apply_res.stdout.strip()}"
                self._remember_incident(record)
                return False, record

        restarted, restart_msg = await loop.run_in_executor(None, self._trigger_watchdog_restart, service_name)
        if restarted:
            record["status"] = "REPAIRED"
            self._metrics["repaired"] += 1
        elif has_patch:
            record["status"] = "PATCH_APPLIED_RESTART_PENDING"
        else:
            record["status"] = "RESTART_PENDING"
        record["action_taken"] = f"Watchdog restart ({'ok' if restarted else 'deferred'}): {restart_msg}"
        self._remember_incident(record)
        self._append_audit_log(record)

        if self.on_incident_change:
            self.on_incident_change()
        return True, record

    async def reject_incident(self, incident_id: str, reason: str = "") -> Tuple[bool, Dict[str, Any]]:
        record = self.get_incident(incident_id)
        if not record:
            return False, {"error": f"Incident '{incident_id}' not found"}
        record["status"] = "REJECTED"
        record["action_taken"] = reason or "Rejected by operator."
        self._remember_incident(record)
        if self.on_incident_change:
            self.on_incident_change()
        return True, record

    async def resolve_incident(self, incident_id: str, note: str = "") -> Tuple[bool, Dict[str, Any]]:
        """Marks an active incident manually resolved without applying automated restarts."""
        record = self.get_incident(incident_id)
        if not record:
            return False, {"error": f"Incident '{incident_id}' not found"}
        record["status"] = "RESOLVED"
        record["action_taken"] = note or "Marked resolved by operator."
        self._remember_incident(record)
        if self.on_incident_change:
            self.on_incident_change()
        return True, record

    def list_incidents(self, limit: int = 50) -> List[Dict[str, Any]]:
        if self.pool:
            rows = list_fleet_incidents(self.pool, self.logger, brain_id=self.brain_id, limit=limit)
            if rows:
                return rows
        ordered = [self._incidents[inc_id] for inc_id in reversed(self._recent_order) if inc_id in self._incidents]
        return ordered[:limit]

    def get_incident(self, incident_id: str) -> Optional[Dict[str, Any]]:
        if incident_id in self._incidents:
            return self._incidents[incident_id]
        if self.pool:
            for item in list_fleet_incidents(self.pool, self.logger, limit=200):
                if item.get("incident_id") == incident_id:
                    self._incidents[incident_id] = item
                    return item
        return None

    async def _notify_operator(self, level: str, record: Dict[str, Any]) -> None:
        if not self.notif_client:
            return
        msg = (
            f"[AutoRepair:{record['status']}] {record['incident_id']} | "
            f"{record['service_name']} (Tier {record['tier']})\n"
            f"Cause: {record.get('root_cause', '')[:220]}\n"
            f"Action: {record.get('action_taken', '')[:220]}"
        )
        try:
            await self.notif_client.send_alert(level, msg, "autorepair", record["service_name"])
        except Exception as e:
            self.logger.warning(f"AutoRepair : Notification alert dispatch failed ({e}).")
