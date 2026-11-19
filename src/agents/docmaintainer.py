#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
DocMaintainer agent daemon specialized in verifying documentation alignment, detecting document drift, and suggesting corrections.

DATA FLOW:
1. Inherits BaseAgent initialization with role-specific prompt and event bus.
2. Registers specialized tools and handles incoming chat events.

KEY PARAMETERS:
- config: Application configuration singleton.
- logger: UniLog logging handle.
- pg_pool: Shared database connection pool.
- event_bus: SquadEventBus pub/sub provider.
"""

# -----------------------------------------------------------------------------

from asyncio import to_thread as asyncioToThread
from json import dumps as jsonDumps, loads as jsonLoads
from typing import Any as typeAny, Dict as typeDict
from urllib.parse import urlencode as urllibUrlencode
from urllib.request import Request as urllibRequest, urlopen as urllibUrlopen

from src.agents.base_agent import BaseAgent
from src.interfaces import SquadEventBus

# -----------------------------------------------------------------------------

def check_documentation_drift(workspace: str = "") -> str:
    """
    Queries the central RAG Engine alignment registry to detect drifted code-to-documentation
    links (@obsidian [[...]]) where source code changed without updating linked notes.

    Args:
        workspace: Optional repository/workspace name filter.
    """
    return ""

def sync_code_documentation(workspace: str = "", file_path: str = "") -> str:
    """
    Triggers CodeDocSynchronizer on the RAG Engine to refresh 11-Code-Doc mirrors
    and re-verify @obsidian alignment tags.

    Args:
        workspace: Optional target workspace name.
        file_path: Optional specific relative file path to synchronize.
    """
    return ""

# -----------------------------------------------------------------------------

class DocMaintainerAgent(BaseAgent):
    """
    DocMaintainer agent daemon. Specialised in verifying documentation alignment,
    detecting document drift, and suggesting manual corrections.
    """
    def __init__(self, *, config: typeAny, logger: typeAny, pg_pool: typeAny, event_bus: SquadEventBus):
        super().__init__(
            role_name="docmaintainer",
            prompt_file="06-DocMaintainer/Prompt-DocMaintainer.md",
            config=config,
            logger=logger,
            pg_pool=pg_pool,
            event_bus=event_bus
        )
        self.tools = self.tools + [check_documentation_drift, sync_code_documentation]

    # -----------------------------------------------------------------------------

    def _resolve_rag_rest_url(self) -> str:
        """Resolves RAG Engine REST address dynamically from AppConfig (Zero Silent Fallback)."""
        addr = self.config.get_rest_addr("rag_engine")
        if not addr:
            raise ValueError("Capability 'rag_engine' REST address unresolvable from configuration")
        return f"http://{addr}"

    # -----------------------------------------------------------------------------

    async def execute_tool(self, name: str, args: typeDict[str, typeAny]) -> str:
        """Dispatches DocMaintainer specialized RAG alignment and doc-sync tools."""
        if name == "check_documentation_drift":
            workspace = str(args.get("workspace") or "").strip()
            base_url = self._resolve_rag_rest_url()
            qs = f"?{urllibUrlencode({'workspace': workspace})}" if workspace else ""
            url = f"{base_url}/api/v1/drift{qs}"

            def _fetch():
                req = urllibRequest(url, method="GET")
                with urllibUrlopen(req, timeout=5.0) as resp:
                    return jsonLoads(resp.read().decode("utf-8"))

            try:
                data = await asyncioToThread(_fetch)
                drifted = data.get("drifted", [])
                if not drifted:
                    return "Zero documentation drift detected across registered @obsidian links."
                return f"Detected {len(drifted)} drifted documentation link(s): {jsonDumps(drifted)}"
            except Exception as exc:
                return f"Error checking documentation drift via RAG Engine: {exc}"

        if name == "sync_code_documentation":
            workspace = str(args.get("workspace") or "").strip() or None
            file_path = str(args.get("file_path") or "").strip() or None
            base_url = self._resolve_rag_rest_url()
            url = f"{base_url}/api/v1/docs/sync"
            payload = jsonDumps({"workspace": workspace, "file_path": file_path, "cleanup": False}).encode("utf-8")

            def _post():
                req = urllibRequest(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
                with urllibUrlopen(req, timeout=10.0) as resp:
                    return jsonLoads(resp.read().decode("utf-8"))

            try:
                data = await asyncioToThread(_post)
                if data.get("success"):
                    return f"Code-Doc synchronization completed: {jsonDumps(data.get('report', {}))}"
                return f"Code-Doc synchronization failed: {data.get('error', 'unknown error')}"
            except Exception as exc:
                return f"Error synchronizing documentation via RAG Engine: {exc}"

        return await super().execute_tool(name, args)
