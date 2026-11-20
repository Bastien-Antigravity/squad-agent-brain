#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Orchestrator agent daemon responsible for decomposing user goals, delegating tasks to
specific agents, and preserving cross-brain task_context across @developer and @qa handoffs.

DATA FLOW:
1. Inherits BaseAgent initialization with role-specific prompt and event bus.
2. Registers specialized tools and handles incoming chat events (including bounded cross-brain handoffs).
3. Propagates task_context (target_brain_id, target_workspace_path, bdd_spec_path, fleet_mode) during delegation.

KEY PARAMETERS:
- config: Application configuration singleton.
- logger: UniLog logging handle.
- pg_pool: Shared database connection pool.
- event_bus: SquadEventBus pub/sub provider.
"""

from asyncio import get_running_loop as asyncioGetRunningLoop
from typing import Any as typeAny, Dict as typeDict, Optional as typeOptional

from src.interfaces import SquadEventBus
from src.agents.base_agent import BaseAgent
from src.agents.oracle import record_strategic_milestone
from src.lib.task_decomposer import TaskDecomposer

# -----------------------------------------------------------------------------------------------


def evaluate_and_split_task(request_text: str) -> str:
    """
    Evaluates the complexity of a user coding or architecture request across file count,
    architectural layers, and polyglot scope, returning an atomic micro-step execution plan
    and mandatory ecosystem guardrails when the request exceeds single-turn complexity.

    Args:
        request_text: Raw user request or mission description.
    """
    return ""


# -----------------------------------------------------------------------------------------------


class OrchestratorAgent(BaseAgent):
    """
    Orchestrator agent daemon responsible for decomposing user goals,
    delegating tasks to specific agents, and reporting progress.
    """

    def __init__(
        self,
        *,
        config: typeAny,
        logger: typeAny,
        pg_pool: typeAny,
        event_bus: SquadEventBus,
        target_brain_id: typeOptional[str] = None,
    ):
        super().__init__(
            role_name="orchestrator",
            prompt_file="01-Orchestrator/Prompt-Orchestrator.md",
            config=config,
            logger=logger,
            pg_pool=pg_pool,
            event_bus=event_bus,
            target_brain_id=target_brain_id,
        )
        self.decomposer = TaskDecomposer(max_files_per_turn=2, split_threshold=4)
        self.tools = self.tools + [record_strategic_milestone, evaluate_and_split_task]

    # -----------------------------------------------------------------------------------------------

    def _compile_active_instruction(self) -> str:
        """Extends active system instruction with explicit cross-brain delegation directives."""
        compiled = super()._compile_active_instruction()
        ctx = self.current_task_context
        if not ctx:
            return compiled
        target_brain = ctx.get("target_brain_id", "obsidian-brain")
        target_ws = ctx.get("target_workspace_path", "")
        bdd_spec = ctx.get("bdd_spec_path", "")
        fleet_mode = ctx.get("fleet_mode", "local")
        return (
            f"{compiled}\n\n"
            f"## Cross-Brain Orchestration Directive\n"
            f"When delegating to `@developer` and `@qa`, explicitly reference:\n"
            f"- target_brain_id: `{target_brain}`\n"
            f"- target_workspace_path: `{target_ws}`\n"
            f"- bdd_spec_path: `{bdd_spec}`\n"
            f"- fleet_mode: `{fleet_mode}`\n"
            f"The event bus preserves `task_context` automatically across `@developer` and `@qa` mentions."
        )

    # -----------------------------------------------------------------------------------------------

    async def execute_tool(self, name: str, args: typeDict[str, typeAny]) -> str:
        """Dynamic tool execution handler for Orchestrator."""
        if name == "evaluate_and_split_task":
            req = str(args.get("request_text", ""))
            return self.decomposer.format_execution_plan(req)
        if name == "record_strategic_milestone":
            session_id = args.get("session_id", "default_session")
            milestone = args.get("milestone", "general")
            action = args.get("action", "")
            outcome = args.get("outcome", "completed")
            return await self._record_strategic_milestone_impl(
                session_id=session_id,
                milestone=milestone,
                action=action,
                outcome=outcome,
            )
        return await super().execute_tool(name, args)

    # -----------------------------------------------------------------------------------------------

    async def _record_strategic_milestone_impl(
        self,
        *,
        session_id: str,
        milestone: str,
        action: str,
        outcome: str,
    ) -> str:
        """Records an epic/mission milestone in PostgreSQL and broadcasts over NATS."""
        if self.pool:
            loop = asyncioGetRunningLoop()

            def db_insert():
                conn = self.pool.getconn()
                try:
                    with conn.cursor() as cursor:
                        cursor.execute('SET search_path TO "01-Strategic-Nexus", public')
                        cursor.execute(
                            "INSERT INTO strategic_logs (session_id, milestone, action_taken, outcome) VALUES (%s, %s, %s, %s)",
                            (session_id, milestone, action, outcome),
                        )
                    conn.commit()
                except Exception as e:
                    self.logger.error(f"{self.Name} : Failed to log milestone to DB: {e}")
                finally:
                    self.pool.putconn(conn)

            await loop.run_in_executor(None, db_insert)

        try:
            milestone_payload = {
                "source": "orchestrator",
                "session_id": session_id,
                "milestone": milestone,
                "action": action,
                "outcome": outcome,
            }
            await self.event_bus.publish("bastien-antigravity.strategic.milestone", milestone_payload)
            self.logger.info(f"{self.Name} : Published strategic milestone '{milestone}' to NATS.")
        except Exception as e:
            self.logger.warning(f"{self.Name} : Failed to publish milestone to NATS: {e}")

        return f"Orchestrator milestone '{milestone}' successfully recorded and broadcast."
