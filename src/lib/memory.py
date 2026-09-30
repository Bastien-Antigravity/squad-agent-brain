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

from typing import Dict, List, Any, Optional
from json import dumps as jsonDumps, loads as jsonLoads

from microservice_toolbox.logger import ensure_safe_logger
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
    Saves conversation history to the tenant's schema in obsidiandb.
    """

    def __init__(self, *, config: Any, logger: Any, pg_pool: Any, schema: str, name: Optional[str] = None):
        self.config = config
        self.logger = ensure_safe_logger(logger)
        self.pool = pg_pool
        self.schema = schema
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
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS squad_chat_logs (
                        id SERIAL PRIMARY KEY,
                        session_id VARCHAR(255) NOT NULL,
                        sender VARCHAR(100) NOT NULL,
                        content TEXT NOT NULL,
                        tool_calls JSONB,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    )
                """)
            conn.commit()
            self.logger.info("{0} : Initialised database schema '{1}'".format(self.Name, self.schema))
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
                    "INSERT INTO conversation_turns (session_id, role, content, metadata) VALUES (%s, %s, %s, %s)",
                    (session_id, message["role"], message["content"], jsonDumps(message.get("metadata", {})))
                )
            conn.commit()
            self.logger.info("{0} : Added message turn for session '{1}'".format(self.Name, session_id))
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

    def __init__(self, *, config: Any, logger: Any, tenant: str, client: Optional[Any] = None, name: Optional[str] = None):
        self.config = config
        self.logger = ensure_safe_logger(logger)
        self.tenant = tenant
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

        self.logger.info("{0} : Querying long-term semantic context for '{1}'".format(self.Name, query))

        # 1. Attempt using injected client
        if self.client and hasattr(self.client, "query_brain"):
            try:
                results = self.client.query_brain(query=query, workspace=self.tenant, limit=limit)
                return self._format_results(results)
            except Exception as e:
                self.logger.error("{0} : Error querying via RAG client: {1}".format(self.Name, e))

        # 2. Fallback to direct import if running within same directory structure
        try:
            from src.facade import get_rag_facade
            import src.bootstrap as RAGBootstrap
            
            facade = get_rag_facade(RAGBootstrap.config, RAGBootstrap.logger)
            import asyncio
            
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
            results = loop.run_until_complete(facade.query_brain(query=query, workspace=self.tenant, limit=limit))
            return self._format_results(results)
        except Exception as e:
            self.logger.warning("{0} : RAG Facade fallback unavailable: {1}".format(self.Name, e))

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
