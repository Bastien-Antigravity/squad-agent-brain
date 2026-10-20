#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS: Memory Stores
  Provides memory storage implementations for the agent squad. Includes volatile,
  persistent PostgreSQL, semantic RAG, and combined dual-layer memory layers.

DATA FLOW:
  1. Input:   Raw dict message turns, session ID, query, and limit overrides.
  2. Logic:   Saves turns to Postgres schema or in-memory lists; retrieves via
              recent conversation timelines or semantic vector similarity.
  3. Output:  Chronologically ordered list of message turns.

KEY PARAMETERS:
  - max_size: Maximum number of conversation turns retained in memory.
  - pg_pool:  Connection pool for Postgres schema-isolated queries.
  - tenant:   Workspace tenant context.
"""

import os
import time
import urllib.request
from typing import Dict, List, Any, Optional
from json import dumps as jsonDumps, loads as jsonLoads

from microservice_toolbox.logger import ensure_safe_logger
from microservice_toolbox.conn_manager.manager import NetworkManager
from interfaces import MemoryStore

# -----------------------------------------------------------------------------------------------

class ShortTermMemory(MemoryStore):
    """
    Volatile in-memory conversation buffer fallback.
    """

    Name = "ShortTermMemory"

    def __init__(self, *, config: Any, logger: Any, max_size: int = 50, name: Optional[str] = None):
        self.config = config
        self.logger = ensure_safe_logger(logger)
        self.max_size = max_size
        self.Name = name or self.__class__.__name__
        self._buffer: List[Dict[str, Any]] = []

    # -----------------------------------------------------------------------------------------------

    def add(self, message: Dict[str, Any], session_id: Optional[str] = None) -> None:
        """Appends a new turn to the in-memory buffer, capping size."""
        self._buffer.append(message)
        if len(self._buffer) > self.max_size:
            self._buffer.pop(0)

    # -----------------------------------------------------------------------------------------------

    def retrieve(self, query: str, session_id: Optional[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
        """Retrieves active conversation history buffer."""
        return self._buffer[-limit:]

    # -----------------------------------------------------------------------------------------------

    def clear(self, session_id: Optional[str] = None) -> None:
        """Clears the buffer."""
        self._buffer.clear()


# -----------------------------------------------------------------------------------------------

class PostgresMemoryStore(MemoryStore):
    """
    Persistent short-term memory store.
    Saves conversation history to the tenant's schema in obsidiandb with brain_id partition isolation.
    """

    def __init__(self, *, config: Any, logger: Any, pg_pool: Any, schema: str, brain_id: Optional[str] = None, name: Optional[str] = None):
        self.config = config
        self.logger = ensure_safe_logger(logger)
        self.pool = pg_pool
        self.schema = schema
        raw_brain_id = (
            brain_id or 
            os.environ.get("TARGET_BRAIN_ID") or 
            os.environ.get("BRAIN_ID")
        )
        if not raw_brain_id and hasattr(self.config, "get_capability"):
            cap = self.config.get_capability("squad_agent")
            if isinstance(cap, dict):
                raw_brain_id = cap.get("target_brain_id")
        self.brain_id = raw_brain_id if isinstance(raw_brain_id, str) and raw_brain_id.strip() else None
        self.Name = name or self.__class__.__name__
        self._init_db()

    # -----------------------------------------------------------------------------------------------

    def _init_db(self) -> None:
        """Declares and builds the conversation_turns table if not already present."""
        conn = self.pool.getconn()
        try:
            with conn.cursor() as cursor:
                cursor.execute('CREATE SCHEMA IF NOT EXISTS "{0}"'.format(self.schema))
                cursor.execute('SET search_path TO "{0}", public'.format(self.schema))
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS conversation_turns (
                        id SERIAL PRIMARY KEY,
                        session_id VARCHAR(255) NOT NULL,
                        role VARCHAR(50) NOT NULL,
                        content TEXT NOT NULL,
                        metadata JSONB,
                        brain_id VARCHAR(100),
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                cursor.execute("ALTER TABLE conversation_turns ADD COLUMN IF NOT EXISTS brain_id VARCHAR(100)")
                cursor.execute("CREATE INDEX IF NOT EXISTS conv_turns_brain_idx ON conversation_turns (brain_id)")
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS squad_chat_logs (
                        id SERIAL PRIMARY KEY,
                        session_id VARCHAR(255) NOT NULL,
                        sender VARCHAR(100) NOT NULL,
                        content TEXT NOT NULL,
                        tool_calls JSONB,
                        brain_id VARCHAR(100),
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                cursor.execute("ALTER TABLE squad_chat_logs ADD COLUMN IF NOT EXISTS brain_id VARCHAR(100)")
            conn.commit()
            self.logger.info("{0} : Initialised database schema '{1}' (brain_id: {2})".format(self.Name, self.schema, self.brain_id))
        except Exception as e:
            self.logger.error("{0} : Error initialising database table: {1}".format(self.Name, e))
            raise
        finally:
            self.pool.putconn(conn)

    # -----------------------------------------------------------------------------------------------

    def add(self, message: Dict[str, Any], session_id: Optional[str] = None) -> None:
        """Persists a new message turn to the database."""
        session_id = session_id or "default_session"
        conn = self.pool.getconn()
        try:
            with conn.cursor() as cursor:
                cursor.execute('SET search_path TO "{0}", public'.format(self.schema))
                cursor.execute(
                    "INSERT INTO conversation_turns (session_id, role, content, metadata, brain_id) VALUES (%s, %s, %s, %s, %s)",
                    (session_id, message["role"], message["content"], jsonDumps(message.get("metadata", {})), self.brain_id)
                )
            conn.commit()
            self.logger.info("{0} : Added message turn for session '{1}' (brain: {2})".format(self.Name, session_id, self.brain_id))
        except Exception as e:
            self.logger.error("{0} : Error writing turn to postgres: {1}".format(self.Name, e))
        finally:
            self.pool.putconn(conn)

    # -----------------------------------------------------------------------------------------------

    def retrieve(self, query: str, session_id: Optional[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
        """Retrieves and returns the last limit conversation turns from the database."""
        session_id = session_id or "default_session"
        conn = self.pool.getconn()
        try:
            with conn.cursor() as cursor:
                cursor.execute('SET search_path TO "{0}", public'.format(self.schema))
                if self.brain_id:
                    cursor.execute(
                        "SELECT role, content, metadata FROM conversation_turns WHERE session_id = %s AND (brain_id = %s OR brain_id IS NULL) ORDER BY created_at DESC LIMIT %s",
                        (session_id, self.brain_id, limit)
                    )
                else:
                    cursor.execute(
                        "SELECT role, content, metadata FROM conversation_turns WHERE session_id = %s ORDER BY created_at DESC LIMIT %s",
                        (session_id, limit)
                    )
                rows = cursor.fetchall()
                # Return in chronological order
                turns = []
                for r in reversed(rows):
                    meta = r[2] if isinstance(r[2], dict) else (jsonLoads(r[2]) if r[2] else {})
                    turns.append({"role": r[0], "content": r[1], "metadata": meta})
                return turns
        except Exception as e:
            self.logger.error("{0} : Error retrieving memory from postgres: {1}".format(self.Name, e))
            return []
        finally:
            self.pool.putconn(conn)

    # -----------------------------------------------------------------------------------------------

    def delete_by_brain(self, brain_id: str) -> int:
        """Purges conversation turns and chat logs for a brain partition, ensuring zero state pollution."""
        if not brain_id:
            return 0
        conn = self.pool.getconn()
        try:
            with conn.cursor() as cursor:
                cursor.execute('SET search_path TO "{0}", public'.format(self.schema))
                cursor.execute("DELETE FROM conversation_turns WHERE brain_id = %s", (brain_id,))
                count_turns = cursor.rowcount
                cursor.execute("DELETE FROM squad_chat_logs WHERE brain_id = %s", (brain_id,))
                count_logs = cursor.rowcount
            conn.commit()
            total = count_turns + count_logs
            self.logger.info(f"{self.Name} : Cleanly purged {total} conversational records for brain '{brain_id}'")
            return total
        except Exception as e:
            self.logger.error(f"{self.Name} : Error purging conversation records for brain '{brain_id}': {e}")
            return 0
        finally:
            self.pool.putconn(conn)

    # -----------------------------------------------------------------------------------------------

    def clear(self, session_id: Optional[str] = None) -> None:
        """Purges conversation history for the specified session from the database."""
        session_id = session_id or "default_session"
        conn = self.pool.getconn()
        try:
            with conn.cursor() as cursor:
                cursor.execute('SET search_path TO "{0}", public'.format(self.schema))
                cursor.execute("DELETE FROM conversation_turns WHERE session_id = %s", (session_id,))
            conn.commit()
            self.logger.info("{0} : Cleared memory session '{1}'".format(self.Name, session_id))
        except Exception as e:
            self.logger.error("{0} : Error clearing memory from postgres: {1}".format(self.Name, e))
        finally:
            self.pool.putconn(conn)


# -----------------------------------------------------------------------------------------------

class RAGMemoryStore(MemoryStore):
    """
    Long-term semantic memory store.
    Integrates directly with the multi-tenant RAG database schemas to query vector similarity.
    """

    def __init__(self, *, config: Any, logger: Any, tenant: Optional[str] = None, client: Optional[Any] = None, name: Optional[str] = None):
        self.config = config
        self.logger = ensure_safe_logger(logger)
        raw_tenant = (
            tenant or 
            os.environ.get("TARGET_BRAIN_ID") or 
            os.environ.get("BRAIN_ID")
        )
        if not raw_tenant and hasattr(self.config, "get_capability"):
            cap = self.config.get_capability("squad_agent")
            if isinstance(cap, dict):
                raw_tenant = cap.get("target_brain_id")
        self.tenant = raw_tenant if isinstance(raw_tenant, str) and raw_tenant.strip() else ""
        if not self.tenant:
            raise ValueError("Tenant/brain_id must be specified to prevent multi-tenant cross-brain pollution")
        self.client = client
        self.Name = name or self.__class__.__name__

    # -----------------------------------------------------------------------------------------------

    def add(self, message: Dict[str, Any], session_id: Optional[str] = None) -> None:
        """No-op. Chunks are indexed via RAG pipelines."""
        pass

    # -----------------------------------------------------------------------------------------------

    def retrieve(self, query: str, session_id: Optional[str] = None, limit: int = 5) -> List[Dict[str, Any]]:
        """Queries the RAG Engine for relevant context matching the query."""
        if not query:
            return []

        self.logger.info("{0} : Querying long-term semantic context for '{1}' (brain: {2})".format(self.Name, query, self.tenant))

        # 1. Attempt using REST API via canonical get_rest_addr (Zero Silent Fallback)
        try:
            if not hasattr(self.config, "get_rest_addr"):
                raise ValueError("Config loader must implement get_rest_addr() per ecosystem standards")
            rag_addr = self.config.get_rest_addr("rag_engine")
            if not rag_addr:
                raise ValueError("Capability 'rag_engine' REST address unresolvable from configuration")

            url = f"http://{rag_addr}/api/v1/query"
            payload = jsonDumps({
                "query": query,
                "limit": limit,
                "brain_id": self.tenant
            }).encode("utf-8")
            
            nm = NetworkManager(max_retries=3, base_delay_ms=200, max_delay_ms=2000, backoff=2.0, jitter=0.1, logger=self.logger)
            req = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json"}
            )
            for attempt in range(nm.max_retries):
                try:
                    with urllib.request.urlopen(req, timeout=3.0) as resp:
                        if resp.status == 200:
                            data = jsonLoads(resp.read().decode("utf-8"))
                            if data.get("success") and "results" in data:
                                return self._format_results(data["results"])
                            return []
                except Exception as net_err:
                    if attempt < nm.max_retries - 1:
                        delay = nm.get_next_delay(attempt)
                        self.logger.debug(f"{self.Name} : REST query attempt {attempt+1} failed ({net_err}); retrying in {delay:.2f}s...")
                        time.sleep(delay)
                    else:
                        self.logger.debug(f"{self.Name} : REST query to RAG Engine unavailable ({net_err}) after {nm.max_retries} attempts.")
        except Exception as net_err:
            self.logger.debug(f"{self.Name} : REST query to RAG Engine unavailable ({net_err}), falling back...")

        # 2. Attempt using injected client
        if self.client and hasattr(self.client, "query_brain"):
            try:
                results = self.client.query_brain(query=query, workspace=self.tenant, limit=limit)
                return self._format_results(results)
            except Exception as e:
                self.logger.error("{0} : Error querying via RAG client: {1}".format(self.Name, e))

        return []

    # -----------------------------------------------------------------------------------------------

    def _format_results(self, results: Any) -> List[Dict[str, Any]]:
        """Formats RAG results into system prompt turns."""
        turns = []
        if not results:
            return turns

        documents = []
        if isinstance(results, dict):
            documents = results.get("documents", [])
        elif isinstance(results, list):
            documents = results

        for doc in documents:
            source = doc.get("source_path") or doc.get("metadata", {}).get("source_path", "unknown")
            content = doc.get("content") or doc.get("text", "")
            if content:
                turns.append({
                    "role": "system",
                    "content": "[Semantic Context from {0}]: {1}".format(source, content.strip())
                })
        return turns

    # -----------------------------------------------------------------------------------------------

    def clear(self, session_id: Optional[str] = None) -> None:
        """No-op."""
        pass


# -----------------------------------------------------------------------------------------------

class DualLayerMemoryStore(MemoryStore):
    """
    Hybrid memory store combining short-term conversation context with
    long-term semantic RAG indexing.
    """

    Name = "DualLayerMemoryStore"

    def __init__(self, *, config: Any, logger: Any, short_term: MemoryStore, long_term: Optional[MemoryStore] = None, name: Optional[str] = None):
        self.config = config
        self.logger = ensure_safe_logger(logger)
        self.short_term = short_term
        self.long_term = long_term
        self.Name = name or self.__class__.__name__

    # -----------------------------------------------------------------------------------------------

    def add(self, message: Dict[str, Any], session_id: Optional[str] = None) -> None:
        """Persists a conversation turn in the short-term storage layer."""
        self.short_term.add(message, session_id)

    # -----------------------------------------------------------------------------------------------

    def retrieve(self, query: str, session_id: Optional[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
        """Retrieves and consolidates short-term turns and long-term semantic context turns."""
        turns = self.short_term.retrieve(query, session_id, limit=limit)
        if self.long_term:
            long_term_turns = self.long_term.retrieve(query, session_id, limit=5)
            # Prepend long-term context so it sits as passive context background information
            return long_term_turns + turns
        return turns

    # -----------------------------------------------------------------------------------------------

    def clear(self, session_id: Optional[str] = None) -> None:
        """Purges history inside all integrated memory layers."""
        self.short_term.clear(session_id)
        if self.long_term:
            self.long_term.clear(session_id)

    # -----------------------------------------------------------------------------------------------

    def delete_by_brain(self, brain_id: str) -> int:
        """Purges conversation records for a specific brain partition across storage layers."""
        total = 0
        if hasattr(self.short_term, "delete_by_brain"):
            total += self.short_term.delete_by_brain(brain_id)
        if hasattr(self.long_term, "delete_by_brain"):
            total += self.long_term.delete_by_brain(brain_id)
        return total
