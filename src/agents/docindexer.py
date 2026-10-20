#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
DocIndexer agent daemon specialized in documentation indexing, formatting, and metadata cataloging.
Provides capabilities to scan local markdown files in any satellite brain and index or purge
them remotely in the central partitioned RAG Engine.

DATA FLOW:
1. Receives indexing tasks via chat event bus or CLI invocation.
2. Scans local documents and sends chunks to the central RAG Engine REST endpoint.
3. Coordinates multi-brain namespace unmerge/purge on request.

KEY PARAMETERS:
- config: Application configuration singleton.
- logger: UniLog logging handle.
- pg_pool: Shared database connection pool.
- event_bus: SquadEventBus pub/sub provider.
"""

import os
import time
import urllib.request
from json import dumps as jsonDumps, loads as jsonLoads
from pathlib import Path
from typing import Any, Dict, Optional

from microservice_toolbox.conn_manager.manager import NetworkManager
from microservice_toolbox.utils.bootstrap import find_vault_root
from src.agents.base_agent import BaseAgent
from src.interfaces import SquadEventBus

# -----------------------------------------------------------------------------
# Tool Declarations for LLM Function Calling
# -----------------------------------------------------------------------------

def index_brain_document(brain_id: str, rel_path: str, content: str, title: str = "") -> str:
    """
    Indexes a markdown document into the specified brain partition in the central RAG Engine.
    
    Args:
        brain_id: Target brain identifier (e.g. 'obsidian-brain', 'finance-brain').
        rel_path: Relative path of the document (e.g. '01-Architecture/specs.md').
        content: Complete markdown content of the document.
        title: Optional title of the document.
    """
    return ""

def purge_brain_index(brain_id: str) -> str:
    """
    Purges and cleanly unmerges an entire brain partition from the central vector store.
    
    Args:
        brain_id: Target brain identifier to purge (e.g. 'satellite-brain').
    """
    return ""

def scan_and_index_local_vault(brain_id: str, local_vault_dir: str = "") -> str:
    """
    Scans a local brain directory on the current host and indexes all markdown files
    into the central RAG Engine under the specified brain_id partition.
    
    Args:
        brain_id: Target brain partition namespace.
        local_vault_dir: Local filesystem directory path to scan (defaults to vault root).
    """
    return ""

# -----------------------------------------------------------------------------

class DocIndexerAgent(BaseAgent):
    """
    DocIndexer agent daemon. Specialised in documentation indexing, formatting,
    and metadata cataloging across partitioned multi-tenant brains.
    """

    def __init__(self, *, config: Any, logger: Any, pg_pool: Any, event_bus: SquadEventBus):
        super().__init__(
            role_name="docindexer",
            prompt_file="10-DocIndexer/Prompt-DocIndexer.md",
            config=config,
            logger=logger,
            pg_pool=pg_pool,
            event_bus=event_bus
        )
        self.tools.extend([index_brain_document, purge_brain_index, scan_and_index_local_vault])
        self.Name = "DocIndexer"
        raw_target = (
            os.environ.get("TARGET_BRAIN_ID") or 
            os.environ.get("BRAIN_ID")
        )
        if not raw_target and hasattr(self.config, "get_capability"):
            cap = self.config.get_capability("squad_agent")
            if isinstance(cap, dict):
                raw_target = cap.get("target_brain_id")
        self.target_brain_id = raw_target if isinstance(raw_target, str) and raw_target.strip() else None

        raw_root = None
        if hasattr(self.config, "common") and isinstance(self.config.common, dict):
            raw_root = self.config.common.get("name")
        elif hasattr(self.config, "data") and isinstance(self.config.data, dict):
            raw_root = self.config.data.get("common", {}).get("name")
        if not raw_root:
            raw_root = os.environ.get("ROOT_BRAIN_ID")
        self.root_brain_id = raw_root if isinstance(raw_root, str) and raw_root.strip() else "obsidian-brain"
        self.net_manager = NetworkManager(max_retries=3, base_delay_ms=200, max_delay_ms=2000, backoff=2.0, jitter=0.1, logger=self.logger)

    # -----------------------------------------------------------------------------

    def _resolve_rag_rest_url(self) -> str:
        """Dynamically resolves RAG Engine REST endpoint from ecosystem configuration."""
        if hasattr(self.config, "get_rest_addr"):
            addr = self.config.get_rest_addr("rag_engine")
            if addr:
                return f"http://{addr}"
        raise ValueError("Capability 'rag_engine' REST address unresolvable from configuration")

    # -----------------------------------------------------------------------------

    async def execute_tool(self, name: str, args: Dict[str, Any]) -> str:
        """Dispatches DocIndexer specific tools with fallback to BaseAgent."""
        if name == "index_brain_document":
            brain_id = args.get("brain_id") or self.target_brain_id
            if not brain_id:
                return "Error: Missing required 'brain_id' parameter. Specify target brain partition."
            rel_path = args.get("rel_path", "")
            content = args.get("content", "")
            title = args.get("title", "")
            return self._index_document_remote(brain_id, rel_path, content, title)

        elif name == "purge_brain_index":
            brain_id = args.get("brain_id")
            if not brain_id:
                return "Error: Missing required 'brain_id' parameter to purge."
            if brain_id == self.root_brain_id:
                return f"Error: Purging the root '{self.root_brain_id}' via remote tool is restricted to prevent ecosystem data loss."
            return self._purge_brain_remote(brain_id)

        elif name == "scan_and_index_local_vault":
            brain_id = args.get("brain_id") or self.target_brain_id
            if not brain_id:
                return "Error: Missing required 'brain_id' parameter. Specify target brain partition."
            local_dir = args.get("local_vault_dir") or str(find_vault_root("."))
            return self._scan_and_index_directory(brain_id, local_dir)

        return await super().execute_tool(name, args)

    # -----------------------------------------------------------------------------

    def _index_document_remote(self, brain_id: str, rel_path: str, content: str, title: str) -> str:
        """Sends document to central RAG REST endpoint for indexing with resilient retry."""
        url = f"{self._resolve_rag_rest_url()}/api/v1/index/document"
        payload = jsonDumps({
            "brain_id": brain_id,
            "rel_path": rel_path,
            "content": content,
            "title": title
        }).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        for attempt in range(self.net_manager.max_retries):
            try:
                with urllib.request.urlopen(req, timeout=10.0) as resp:
                    data = jsonLoads(resp.read().decode("utf-8"))
                    if data.get("success"):
                        return f"Successfully indexed '{rel_path}' into brain '{brain_id}' ({data.get('chunks_indexed', 0)} chunks)"
                    return f"Failed to index document: {data.get('error')}"
            except Exception as e:
                if attempt < self.net_manager.max_retries - 1:
                    delay = self.net_manager.get_next_delay(attempt)
                    self.logger.debug(f"{self.Name} : Index document retry {attempt+1} in {delay:.2f}s ({e})")
                    time.sleep(delay)
                else:
                    return f"Error connecting to RAG Engine REST service at {url}: {e}"
        return f"Error connecting to RAG Engine REST service at {url}: Max retries reached"

    # -----------------------------------------------------------------------------

    def _purge_brain_remote(self, brain_id: str) -> str:
        """Sends purge request to central RAG REST endpoint with resilient retry."""
        url = f"{self._resolve_rag_rest_url()}/api/v1/vault/purge"
        payload = jsonDumps({"brain_id": brain_id}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        for attempt in range(self.net_manager.max_retries):
            try:
                with urllib.request.urlopen(req, timeout=10.0) as resp:
                    data = jsonLoads(resp.read().decode("utf-8"))
                    if data.get("success"):
                        return f"Successfully unmerged/purged brain partition '{brain_id}' ({data.get('deleted_count', 0)} records deleted)"
                    return f"Failed to purge brain: {data.get('error')}"
            except Exception as e:
                if attempt < self.net_manager.max_retries - 1:
                    delay = self.net_manager.get_next_delay(attempt)
                    self.logger.debug(f"{self.Name} : Purge brain retry {attempt+1} in {delay:.2f}s ({e})")
                    time.sleep(delay)
                else:
                    return f"Error connecting to RAG Engine REST service at {url}: {e}"
        return f"Error connecting to RAG Engine REST service at {url}: Max retries reached"

    # -----------------------------------------------------------------------------

    def _scan_and_index_directory(self, brain_id: str, local_dir: str) -> str:
        """Walks local directory and indexes all markdown files."""
        root = Path(local_dir).resolve()
        if not root.is_dir():
            return f"Error: '{local_dir}' is not a valid directory."

        count = 0
        errors = []
        for file_path in root.rglob("*.md"):
            if ".git" in file_path.parts or "node_modules" in file_path.parts:
                continue
            try:
                rel_path = str(file_path.relative_to(root))
                content = file_path.read_text(encoding="utf-8")
                res = self._index_document_remote(brain_id, rel_path, content, file_path.stem)
                if "Successfully" in res:
                    count += 1
                else:
                    errors.append(f"{rel_path}: {res}")
            except Exception as e:
                errors.append(f"{file_path.name}: {e}")

        summary = f"Scanned {local_dir} and indexed {count} markdown file(s) into brain partition '{brain_id}'."
        if errors:
            summary += f"\nEncountered {len(errors)} issues:\n" + "\n".join(errors[:5])
        return summary
