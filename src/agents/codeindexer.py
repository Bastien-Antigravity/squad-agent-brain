#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
CodeIndexer agent daemon specialized in code symbol parsing, cross-referencing, and semantic dependency indexing.

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

def search_code_symbols(symbol_query: str, workspace: str = "") -> str:
    """
    Searches AST symbols (functions, classes, structs, interfaces) indexed in the
    RAG Engine's relational codebase graph.

    Args:
        symbol_query: Function, class, or symbol name substring to search for.
        workspace: Optional microservice/repository workspace filter.
    """
    return ""

def get_file_dependency_graph(file_path: str) -> str:
    """
    Retrieves inbound callers/consumers and outbound dependencies for a source file
    from the RAG Engine's codebase relational graph.

    Args:
        file_path: Workspace-relative path to the source file (e.g. 'config-server/main.go').
    """
    return ""

# -----------------------------------------------------------------------------

class CodeIndexerAgent(BaseAgent):
    """
    CodeIndexer agent daemon. Specialised in code symbol parsing, cross-referencing,
    and semantic dependency indexing.
    """
    def __init__(self, *, config: typeAny, logger: typeAny, pg_pool: typeAny, event_bus: SquadEventBus):
        super().__init__(
            role_name="codeindexer",
            prompt_file="11-CodeIndexer/Prompt-CodeIndexer.md",
            config=config,
            logger=logger,
            pg_pool=pg_pool,
            event_bus=event_bus
        )
        self.tools = self.tools + [search_code_symbols, get_file_dependency_graph]

    # -----------------------------------------------------------------------------

    def _resolve_rag_rest_url(self) -> str:
        """Resolves RAG Engine REST address dynamically from AppConfig (Zero Silent Fallback)."""
        addr = self.config.get_rest_addr("rag_engine")
        if not addr:
            raise ValueError("Capability 'rag_engine' REST address unresolvable from configuration")
        return f"http://{addr}"

    # -----------------------------------------------------------------------------

    async def execute_tool(self, name: str, args: typeDict[str, typeAny]) -> str:
        """Dispatches CodeIndexer AST symbol search and dependency graph tools via RAG REST API."""
        if name == "search_code_symbols":
            query = str(args.get("symbol_query") or "").strip()
            workspace = str(args.get("workspace") or "").strip()
            base_url = self._resolve_rag_rest_url()
            params = {"query": query}
            if workspace:
                params["workspace"] = workspace
            url = f"{base_url}/api/v1/code/symbols?{urllibUrlencode(params)}"

            def _fetch():
                req = urllibRequest(url, method="GET")
                with urllibUrlopen(req, timeout=5.0) as resp:
                    return jsonLoads(resp.read().decode("utf-8"))

            try:
                data = await asyncioToThread(_fetch)
                symbols = data.get("symbols", [])
                if not symbols:
                    return f"No AST symbols found matching '{query}'."
                return f"Found {len(symbols)} AST symbol(s): {jsonDumps(symbols)}"
            except Exception as exc:
                return f"Error searching code symbols via RAG Engine: {exc}"

        if name == "get_file_dependency_graph":
            file_path = str(args.get("file_path") or "").strip()
            if not file_path:
                return "Error: Missing required 'file_path' parameter."
            base_url = self._resolve_rag_rest_url()
            url = f"{base_url}/api/v1/code/dependencies?{urllibUrlencode({'file_path': file_path})}"

            def _fetch():
                req = urllibRequest(url, method="GET")
                with urllibUrlopen(req, timeout=5.0) as resp:
                    return jsonLoads(resp.read().decode("utf-8"))

            try:
                data = await asyncioToThread(_fetch)
                return (
                    f"Dependency graph for '{file_path}': "
                    f"outbound={jsonDumps(data.get('outbound', []))}, "
                    f"inbound={jsonDumps(data.get('inbound', []))}"
                )
            except Exception as exc:
                return f"Error querying file dependency graph via RAG Engine: {exc}"

        return await super().execute_tool(name, args)
