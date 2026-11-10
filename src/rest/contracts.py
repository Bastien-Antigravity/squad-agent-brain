#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Builds authoritative, runtime-introspected Exchange Contracts for squad-agent
across FastAPI REST & SSE endpoints, gRPC SquadControlService, NATS Event Bus
chat/incident topics, and PostgreSQL conversation memory tables.

DATA FLOW:
1. Introspects live FastAPI app.routes, reads src/grpc_control/squad_control.proto,
   inspects runtime brain_id & NATS capability config.
2. Produces ContractsEnvelope JSON for GET /api/v1/contracts and ServiceSpec registration.

KEY PARAMETERS:
- app: FastAPI application serving Squad control REST/SSE endpoints.
- config: Ecosystem AppConfig resolving gRPC, REST, NATS, and Postgres settings.
"""

from datetime import datetime as dtDatetime, timezone as dtTimezone
import os as osMod
from pathlib import Path as pathPath
import re as reMod
from typing import Any as typeAny, Dict as typeDict, List as typeList, Optional as typeOptional

try:
    from microservice_toolbox.contracts import (
        ContractOperation,
        ContractPeer,
        ExchangeContract,
        build_contracts_envelope,
        display_address,
        extract_fastapi_operations,
        extract_proto_operations,
        read_schema_file,
        resolve_contract_port,
    )
except ImportError:
    from dataclasses import dataclass as _dc, field as _field

    @_dc
    class ContractPeer:
        service: str
        role: str
        description: str = ""

        def to_dict(self) -> typeDict[str, typeAny]:
            d = {"service": self.service, "role": self.role}
            if self.description:
                d["description"] = self.description
            return d

    @_dc
    class ContractOperation:
        name: str
        kind: str
        target: str
        input: str = ""
        output: str = ""
        description: str = ""

        def to_dict(self) -> typeDict[str, typeAny]:
            d = {"name": self.name, "kind": self.kind, "target": self.target}
            if self.input:
                d["input"] = self.input
            if self.output:
                d["output"] = self.output
            if self.description:
                d["description"] = self.description
            return d

    @_dc
    class ExchangeContract:
        id: str
        type: str
        tab_label: str = ""
        icon: str = "fa-exchange"
        direction: str = "inbound"
        transport: str = ""
        address: str = ""
        port: int = 0
        framing: str = ""
        auth: str = ""
        summary: str = ""
        source: str = ""
        peers: typeList[ContractPeer] = _field(default_factory=list)
        operations: typeList[ContractOperation] = _field(default_factory=list)
        schema_format: str = ""
        schema: str = ""

        def to_dict(self) -> typeDict[str, typeAny]:
            d: typeDict[str, typeAny] = {"id": self.id, "type": self.type}
            for attr, key in (
                ("tab_label", "tabLabel"),
                ("icon", "icon"),
                ("direction", "direction"),
                ("transport", "transport"),
                ("address", "address"),
                ("framing", "framing"),
                ("auth", "auth"),
                ("summary", "summary"),
                ("source", "source"),
                ("schema_format", "schemaFormat"),
                ("schema", "schema"),
            ):
                val = getattr(self, attr)
                if val:
                    d[key] = val
            if self.port:
                d["port"] = int(self.port)
            if self.peers:
                d["peers"] = [p.to_dict() for p in self.peers]
            if self.operations:
                d["operations"] = [o.to_dict() for o in self.operations]
            return d

    def display_address(addr: str) -> str:
        clean = (addr or "").strip()
        if not clean:
            return "dynamic"
        if clean.startswith(":"):
            return f"127.0.0.1{clean}"
        if clean.startswith("0.0.0.0:"):
            return "127.0.0.1:" + clean[len("0.0.0.0:"):]
        return clean

    def resolve_contract_port(addr: str) -> int:
        if not addr or ":" not in addr:
            return 0
        try:
            return int(addr.rsplit(":", 1)[-1])
        except ValueError:
            return 0

    def read_schema_file(file_path: typeAny) -> str:
        p = pathPath(file_path)
        return p.read_text(encoding="utf-8") if p.is_file() else ""

    def extract_fastapi_operations(app: typeAny, include_prefixes=None, exclude_paths=None) -> typeList[ContractOperation]:
        ops: typeList[ContractOperation] = []
        if app is None:
            return ops
        seen = set()
        for route in getattr(app, "routes", []):
            path = getattr(route, "path", "")
            if not path or path in ("/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"):
                continue
            methods = sorted(m for m in (getattr(route, "methods", None) or []) if m not in ("HEAD", "OPTIONS"))
            for method in methods:
                if (method, path) not in seen:
                    seen.add((method, path))
                    ops.append(ContractOperation(name=getattr(route, "name", "") or path, kind=method, target=path, description=f"FastAPI handler {getattr(route, 'name', path)}"))
        ops.sort(key=lambda o: (o.target, o.kind))
        return ops

    def extract_proto_operations(proto_text: str) -> typeList[ContractOperation]:
        ops: typeList[ContractOperation] = []
        pkg_match = reMod.search(r"^\s*package\s+([A-Za-z0-9_.]+)\s*;", proto_text, reMod.MULTILINE)
        pkg_prefix = f"{pkg_match.group(1)}." if pkg_match else ""
        rpc_re = reMod.compile(r"rpc\s+([A-Za-z0-9_]+)\s*\(\s*(stream\s+)?([A-Za-z0-9_.]+)\s*\)\s+returns\s*\(\s*(stream\s+)?([A-Za-z0-9_.]+)\s*\)")
        for blk in reMod.finditer(r"service\s+([A-Za-z0-9_]+)\s*\{([^}]*)\}", proto_text, reMod.DOTALL):
            svc_name, body = blk.group(1), blk.group(2)
            for m in rpc_re.finditer(body):
                rpc_name, rs, rt, ss, st = m.groups()
                kind = "RPC" if not (rs or ss) else "STREAM"
                ops.append(ContractOperation(name=rpc_name, kind=kind, target=f"{pkg_prefix}{svc_name}/{rpc_name}", input=rt, output=st, description=f"{svc_name}.{rpc_name}"))
        return ops

    def build_contracts_envelope(service: str, version: str, source: str, contracts: typeList[ExchangeContract]) -> typeDict[str, typeAny]:
        return {
            "service": service,
            "version": version or "0.0.1",
            "reliable": True,
            "exhaustive": True,
            "generatedAt": dtDatetime.now(dtTimezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "source": source,
            "contracts": [c.to_dict() for c in contracts],
        }


# -----------------------------------------------------------------------------------------------

_SQUAD_ROOT = pathPath(__file__).resolve().parent.parent.parent
_SQUAD_PROTO_PATH = _SQUAD_ROOT / "src" / "grpc_control" / "squad_control.proto"

_SQUAD_SQL_DDL = """CREATE TABLE IF NOT EXISTS conversation_turns (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(255) NOT NULL,
    role VARCHAR(50) NOT NULL,
    content TEXT NOT NULL,
    metadata JSONB,
    brain_id VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS squad_chat_logs (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(255) NOT NULL,
    sender VARCHAR(100) NOT NULL,
    content TEXT NOT NULL,
    tool_calls JSONB,
    brain_id VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);"""


def build_squad_agent_contracts(
    app: typeAny = None,
    config: typeAny = None,
    version: str = "",
) -> typeDict[str, typeAny]:
    data = getattr(config, "data", {}) or {}
    caps = data.get("capabilities", {}) or {}
    squad_cap = caps.get("squad_agent", {}) or {}
    nats_cap = caps.get("nats", {}) or {}
    pg_cap = caps.get("timescale_db", {}) or {}

    brain_id = (
        osMod.getenv("TARGET_BRAIN_ID")
        or osMod.getenv("BRAIN_ID")
        or squad_cap.get("target_brain_id")
        or "obsidian-brain"
    )
    prefix = nats_cap.get("subject_prefix") or "bastien-antigravity"
    chat_topic = f"{prefix}.{brain_id}.squad.chat" if brain_id not in ("obsidian-brain", "root", "main", "") else f"{prefix}.squad.chat"
    incident_topic = "bastien-antigravity.fleet.incident"

    rest_addr = ""
    grpc_addr = ""
    if config is not None:
        for attr, target in (("get_listen_addr", "rest"), ("get_rest_addr", "rest"), ("get_grpc_listen_addr", "grpc")):
            fn = getattr(config, attr, None)
            if callable(fn):
                try:
                    val = fn("squad_agent") or ""
                    if target == "rest" and val:
                        rest_addr = val
                    elif target == "grpc" and val:
                        grpc_addr = val
                except Exception:
                    pass

    ver = version or (config.get_version() if hasattr(config, "get_version") else "0.0.1")
    rest_ops = extract_fastapi_operations(app)
    if not rest_ops:
        rest_ops = [
            ContractOperation(name="get_status", kind="GET", target="/api/v1/status", output="{ healthy, status, version, github_configured, brain_id }", description="Squad status & GitHub credential health"),
            ContractOperation(name="get_commands", kind="GET", target="/api/v1/squad/commands", output="{ success, commands[] }", description="List orchestrator subcommands"),
            ContractOperation(name="get_active_mode", kind="GET", target="/api/v1/squad/active-mode", output="{ success, mode, name, description }", description="Query active execution mode"),
            ContractOperation(name="switch_mode", kind="POST", target="/api/v1/squad/active-mode", input="{ mode }", output="{ success, message }", description="Switch execution mode (1..4)"),
            ContractOperation(name="run_command_stream", kind="SSE", target="/api/v1/squad/run/{cmd_name}", output="text/event-stream", description="Stream subcommand execution stdout"),
            ContractOperation(name="stream_chat_messages", kind="SSE", target="/api/v1/squad/chat/stream/{session_id}", output="text/event-stream", description="Stream collaborative squad NATS chat turns via SSE"),
            ContractOperation(name="post_chat_message", kind="POST", target="/api/v1/squad/chat/{session_id}", input="{ message, brain_id }", output="{ success, message }", description="Publish operator chat prompt to NATS bus"),
            ContractOperation(name="get_contracts", kind="GET", target="/api/v1/contracts", output="ContractsEnvelope JSON", description="Self-describing microservice exchange contracts"),
        ]

    proto_text = read_schema_file(_SQUAD_PROTO_PATH)
    grpc_ops = extract_proto_operations(proto_text)

    nats_addr = ""
    pg_addr = ""
    if config is not None and callable(getattr(config, "get_listen_addr", None)):
        try:
            nats_addr = config.get_listen_addr("nats") or ""
        except Exception:
            nats_addr = ""
        try:
            pg_addr = config.get_listen_addr("timescale_db") or ""
        except Exception:
            pg_addr = ""
    if not nats_addr and nats_cap.get("port"):
        nats_addr = f"{nats_cap.get('ip', '')}:{nats_cap.get('port')}"
    if not pg_addr and pg_cap.get("port"):
        pg_addr = f"{pg_cap.get('ip', '')}:{pg_cap.get('port')}"

    contracts = [
        ExchangeContract(
            id="rest-sse",
            type="HTTP/REST & SSE API",
            tab_label="HTTP/REST & SSE",
            icon="fa-globe",
            direction="inbound",
            transport="HTTP/1.1 + FastAPI + Server-Sent Events",
            address=display_address(rest_addr),
            port=resolve_contract_port(rest_addr),
            framing="JSON REST endpoints & text/event-stream subcommand/chat streaming",
            auth="Requires session auth in OpenMFE + GITHUB_TOKEN for mutations",
            summary="Control & collaborative streaming REST API consumed by <squad-agent-mfe>.",
            source="obsidian-brain/08-Squad-Agent/src/rest/rest_handler.py (live FastAPI route introspection)",
            peers=[
                ContractPeer(service="web_interface", role="consumer", description="Hosts <squad-agent-mfe> control panel & SSE chat viewer"),
                ContractPeer(service="rag_engine", role="dependency", description="Queried by agents for codebase/documentation retrieval"),
            ],
            operations=rest_ops,
            schema_format="http",
            schema="\n".join(f"{o.kind:<6} {o.target}" for o in rest_ops),
        ),
        ExchangeContract(
            id="grpc",
            type="gRPC / Protobuf (SquadControlService)",
            tab_label="gRPC Control",
            icon="fa-code",
            direction="inbound",
            transport="HTTP/2 + grpc.aio + Protobuf",
            address=display_address(grpc_addr),
            port=resolve_contract_port(grpc_addr),
            framing="gRPC async HTTP/2 frames defined in squad_control.proto",
            auth="Internal insecure gRPC listener",
            summary="Remote RPC control plane for querying status, executing subcommands, and toggling active isolation mode.",
            source="obsidian-brain/08-Squad-Agent/src/grpc_control/squad_control.proto",
            operations=grpc_ops,
            schema_format="proto3",
            schema=proto_text,
        ),
        ExchangeContract(
            id="nats-event-bus",
            type="NATS Pub/Sub Event Bus",
            tab_label="NATS Event Bus",
            icon="fa-paper-plane",
            direction="bidirectional",
            transport="NATS Core TCP Pub/Sub (SquadEventBus)",
            address=display_address(nats_addr),
            port=resolve_contract_port(nats_addr),
            framing="JSON turn & incident payloads partitioned per brain_id",
            auth="AppConfig nats capability",
            summary="Distributes real-time collaborative squad chat messages and consumes watchdog fleet incident alerts for triage.",
            source="obsidian-brain/08-Squad-Agent/src/interfaces/interfaces.py + rest_handler.py",
            peers=[
                ContractPeer(service="nats", role="broker", description="Central pub/sub event bus"),
                ContractPeer(service="watchdog_agent", role="producer", description="Publishes fleet incidents to bastien-antigravity.fleet.incident"),
            ],
            operations=[
                ContractOperation(name="SquadChat", kind="PUB/SUB", target=chat_topic, input="{ session_id, sender, message, brain_id }", description="Multi-agent collaborative chat stream topic"),
                ContractOperation(name="FleetIncidentSub", kind="SUB", target=incident_topic, input="IncidentEvent JSON", description="Automated incident triage feed from watchdog-agent"),
            ],
            schema_format="json",
            schema=f'{{\n  "chat_topic": "{chat_topic}",\n  "incident_topic": "{incident_topic}",\n  "brain_partition": "{brain_id}"\n}}',
        ),
        ExchangeContract(
            id="postgres-memory",
            type="PostgreSQL Conversation Memory",
            tab_label="PostgreSQL Memory",
            icon="fa-database",
            direction="outbound",
            transport="PostgreSQL Wire Protocol v3",
            address=display_address(pg_addr),
            port=resolve_contract_port(pg_addr),
            framing="Per-brain schema persistent turn & squad chat log storage",
            auth="AppConfig timescale_db credentials",
            summary="Persists multi-turn agent conversation memory and squad chat audit trails.",
            source="obsidian-brain/08-Squad-Agent/src/lib/memory.py",
            peers=[
                ContractPeer(service="timescale_db", role="server", description="Hosts conversation_turns and squad_chat_logs tables"),
            ],
            operations=[
                ContractOperation(name="conversation_turns", kind="TABLE", target="conversation_turns", input="id, session_id, role, content, metadata, brain_id, created_at", description="Persistent turn memory per session"),
                ContractOperation(name="squad_chat_logs", kind="TABLE", target="squad_chat_logs", input="id, session_id, sender, content, tool_calls, brain_id, created_at", description="Multi-agent tool & chat audit trail"),
            ],
            schema_format="sql",
            schema=_SQUAD_SQL_DDL,
        ),
    ]

    return build_contracts_envelope(
        "agent_squad",
        ver,
        "08-Squad-Agent (live FastAPI routes + squad_control.proto + NATS + PG DDL)",
        contracts,
    )

