#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Orchestrator agent daemon responsible for decomposing user goals, delegating tasks to specific agents, and reporting progress.

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
from typing import Any, Dict
from src.interfaces import SquadEventBus
from src.agents.base_agent import BaseAgent
from src.agents.oracle import record_strategic_milestone

# -----------------------------------------------------------------------------

class OrchestratorAgent(BaseAgent):
    """
    Orchestrator agent daemon responsible for decomposing user goals,
    delegating tasks to specific agents, and reporting progress.
    """

    # -----------------------------------------------------------------------------

    def __init__(self, *, config: Any, logger: Any, pg_pool: Any, event_bus: SquadEventBus):
        super().__init__(
            role_name="orchestrator",
            prompt_file="01-Orchestrator/Prompt-Orchestrator.md",
            config=config,
            logger=logger,
            pg_pool=pg_pool,
            event_bus=event_bus
        )
        self.tools = self.tools + [record_strategic_milestone]

    # -----------------------------------------------------------------------------

    async def execute_tool(self, name: str, args: Dict[str, Any]) -> str:
        """Dynamic tool execution handler for Orchestrator."""
        if name == "record_strategic_milestone":
            session_id = args.get("session_id", "default_session")
            milestone = args.get("milestone", "general")
            action = args.get("action", "")
            outcome = args.get("outcome", "completed")
            return await self._record_strategic_milestone_impl(session_id, milestone, action, outcome)
        return await super().execute_tool(name, args)

    # -----------------------------------------------------------------------------

    async def _record_strategic_milestone_impl(self, session_id: str, milestone: str, action: str, outcome: str) -> str:
        """Records an epic/mission milestone in PostgreSQL and broadcasts over NATS."""
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
                    self.logger.error(f"OrchestratorAgent: Failed to log milestone to DB: {e}")
                finally:
                    self.pool.putconn(conn)
            await loop.run_in_executor(None, db_insert)

        # 2. Broadcast milestone over NATS to bastien-antigravity.strategic.milestone
        try:
            milestone_payload = {
                "source": "orchestrator",
                "session_id": session_id,
                "milestone": milestone,
                "action": action,
                "outcome": outcome
            }
            await self.event_bus.publish("bastien-antigravity.strategic.milestone", milestone_payload)
            self.logger.info(f"OrchestratorAgent: Published strategic milestone '{milestone}' to NATS.")
        except Exception as e:
            self.logger.warning(f"OrchestratorAgent: Failed to publish milestone to NATS: {e}")

        return f"Orchestrator milestone '{milestone}' successfully recorded and broadcast."
