#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Oracle agent daemon specialized in long-term chronological log auditing, historical analysis, and querying temporal knowledge vaults.

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

import asyncio
from typing import Any, Dict, List
from src.agents.base_agent import BaseAgent
from src.interfaces import SquadEventBus

# -----------------------------------------------------------------------------

def query_strategic_decisions(category: str = "") -> str:
    """
    Queries the Strategic Nexus decision registry for architectural patterns,
    anti-backlog entries, or strategic audit decisions.
    
    Args:
        category: Optional category filter ('anti-backlog', 'pattern', 'audit').
    """
    return ""

def check_anti_backlog(topic: str) -> str:
    """
    Checks whether a proposed feature, library, or design decision was previously
    rejected and recorded in the Anti-Backlog to prevent recurring debates.
    
    Args:
        topic: The feature or architecture concept to verify (e.g. 'redis', 'local bus').
    """
    return ""

def record_strategic_milestone(session_id: str, milestone: str, action: str, outcome: str) -> str:
    """
    Records an architectural milestone or significant strategic progress
    into the 01-Strategic-Nexus database and broadcasts it over NATS.
    
    Args:
        session_id: The active session identifier.
        milestone: Short title of the milestone (e.g. 'FEAT-001 Complete').
        action: Action taken by the squad.
        outcome: Result or impact of the action.
    """
    return ""

# -----------------------------------------------------------------------------

class OracleAgent(BaseAgent):
    """
    Oracle agent daemon (Chronos-Oracle). Specialized in long-term chronological log auditing,
    historical analysis, Anti-Backlog drift detection, and Strategic Nexus synchronization.
    """

    # -----------------------------------------------------------------------------

    def __init__(self, *, config: Any, logger: Any, pg_pool: Any, event_bus: SquadEventBus):
        super().__init__(
            role_name="oracle",
            prompt_file="00-Oracle/Prompt-Chronos-Oracle.md",
            config=config,
            logger=logger,
            pg_pool=pg_pool,
            event_bus=event_bus
        )
        # Augment base tools with Strategic Nexus integration tools
        self.tools = self.tools + [query_strategic_decisions, check_anti_backlog, record_strategic_milestone]

    # -----------------------------------------------------------------------------

    async def execute_tool(self, name: str, args: Dict[str, Any]) -> str:
        """Dynamic tool execution handler for Oracle strategic capabilities."""
        if name == "query_strategic_decisions":
            category = args.get("category", "")
            return await self._query_strategic_decisions_impl(category)
        elif name == "check_anti_backlog":
            topic = args.get("topic", "")
            return await self._check_anti_backlog_impl(topic)
        elif name == "record_strategic_milestone":
            session_id = args.get("session_id", "default_session")
            milestone = args.get("milestone", "general")
            action = args.get("action", "")
            outcome = args.get("outcome", "completed")
            return await self._record_strategic_milestone_impl(session_id, milestone, action, outcome)
        return await super().execute_tool(name, args)

    # -----------------------------------------------------------------------------

    async def _query_strategic_decisions_impl(self, category: str) -> str:
        """Queries 01-Strategic-Nexus.strategic_decisions in PostgreSQL."""
        if not self.pool:
            return "PostgreSQL connection pool is not available."
        loop = asyncio.get_running_loop()
        def db_query():
            conn = self.pool.getconn()
            try:
                with conn.cursor() as cursor:
                    cursor.execute('SET search_path TO "01-Strategic-Nexus", public')
                    if category:
                        cursor.execute(
                            "SELECT decision_id, title, category, content FROM strategic_decisions WHERE category = %s AND status = 'active' ORDER BY updated_at DESC LIMIT 10",
                            (category,)
                        )
                    else:
                        cursor.execute(
                            "SELECT decision_id, title, category, content FROM strategic_decisions WHERE status = 'active' ORDER BY updated_at DESC LIMIT 10"
                        )
                    rows = cursor.fetchall()
                    if not rows:
                        return f"No active strategic decisions found in category '{category}'." if category else "No active strategic decisions found."
                    results = []
                    for r in rows:
                        results.append(f"[{r[0]}] ({r[2]}) {r[1]}:\n{r[3]}")
                    return "\n\n---\n\n".join(results)
            except Exception as e:
                self.logger.error(f"OracleAgent: Failed to query strategic_decisions: {e}")
                return f"Error querying strategic decisions: {e}"
            finally:
                self.pool.putconn(conn)
        return await loop.run_in_executor(None, db_query)

    # -----------------------------------------------------------------------------

    async def _check_anti_backlog_impl(self, topic: str) -> str:
        """Searches the Anti-Backlog for previously settled/rejected architectural topics."""
        if not self.pool:
            return "PostgreSQL connection pool is not available."
        loop = asyncio.get_running_loop()
        def db_query():
            conn = self.pool.getconn()
            try:
                with conn.cursor() as cursor:
                    cursor.execute('SET search_path TO "01-Strategic-Nexus", public')
                    cursor.execute(
                        "SELECT decision_id, title, content FROM strategic_decisions WHERE category = 'anti-backlog' AND (title ILIKE %s OR content ILIKE %s)",
                        (f"%{topic}%", f"%{topic}%")
                    )
                    rows = cursor.fetchall()
                    if not rows:
                        return f"✅ Topic '{topic}' is not in the Anti-Backlog. No historical rejection found."
                    results = [f"⚠️ REJECTED IN ANTI-BACKLOG: Topic '{topic}' matches historical decisions:"]
                    for r in rows:
                        results.append(f"• [{r[0]}] {r[1]}: {r[2]}")
                    return "\n".join(results)
            except Exception as e:
                self.logger.error(f"OracleAgent: Failed to check anti-backlog: {e}")
                return f"Error checking anti-backlog: {e}"
            finally:
                self.pool.putconn(conn)
        return await loop.run_in_executor(None, db_query)

    # -----------------------------------------------------------------------------

    async def _record_strategic_milestone_impl(self, session_id: str, milestone: str, action: str, outcome: str) -> str:
        """Records a strategic milestone into PostgreSQL and broadcasts over NATS."""
        # 1. Insert into PostgreSQL "01-Strategic-Nexus".strategic_logs
        if self.pool:
            loop = asyncio.get_running_loop()
            def db_insert():
                conn = self.pool.getconn()
                try:
                    with conn.cursor() as cursor:
                        cursor.execute('SET search_path TO "01-Strategic-Nexus", public')
                        cursor.execute(
                            "INSERT INTO strategic_logs (session_id, milestone, action_taken, outcome) VALUES (%s, %s, %s, %s)",
                            (session_id, milestone, action, outcome)
                        )
                    conn.commit()
                except Exception as e:
                    self.logger.error(f"OracleAgent: Failed to log strategic milestone to DB: {e}")
                finally:
                    self.pool.putconn(conn)
            await loop.run_in_executor(None, db_insert)

        # 2. Broadcast milestone over NATS to bastien-antigravity.strategic.milestone
        try:
            milestone_payload = {
                "source": "oracle",
                "session_id": session_id,
                "milestone": milestone,
                "action": action,
                "outcome": outcome
            }
            await self.event_bus.publish("bastien-antigravity.strategic.milestone", milestone_payload)
            self.logger.info(f"OracleAgent: Published strategic milestone '{milestone}' to NATS.")
        except Exception as e:
            self.logger.warning(f"OracleAgent: Failed to publish milestone to NATS: {e}")

        return f"Strategic milestone '{milestone}' successfully recorded and broadcast."
