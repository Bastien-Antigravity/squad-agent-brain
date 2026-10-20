#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Unit tests validating agent articulation between 08-Squad-Agent and 01-Strategic-Nexus:
- Anti-Backlog query verification.
- Strategic decisions retrieval from obsidiandb.
- Strategic milestone recording and NATS streaming.

DATA FLOW:
1. Mocks PostgreSQL cursor and SquadEventBus.
2. Invokes OracleAgent and OrchestratorAgent strategic tools.
3. Asserts SQL queries and NATS publish events are accurately routed.

KEY PARAMETERS:
- pg_pool: Mock database connection pool.
- event_bus: Mock SquadEventBus instance.
"""

import unittest
from unittest.mock import MagicMock, AsyncMock
import sys
from pathlib import Path
import asyncio

# Resolve paths so we can import src.*
_self_dir = Path(__file__).resolve().parent.parent
if str(_self_dir) not in sys.path:
    sys.path.insert(0, str(_self_dir))

import src.bootstrap as bootstrap
from src.agents.oracle import OracleAgent, query_strategic_decisions, check_anti_backlog, record_strategic_milestone
from src.agents.orchestrator import OrchestratorAgent


class TestStrategicNexusArticulation(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.mock_config = MagicMock()
        self.mock_config.data = {}
        self.mock_logger = MagicMock()
        self.mock_event_bus = MagicMock()
        self.mock_event_bus.publish = AsyncMock()

        # Setup mock postgres pool and cursor
        self.mock_cursor = MagicMock()
        self.mock_conn = MagicMock()
        self.mock_conn.cursor.return_value.__enter__.return_value = self.mock_cursor
        self.mock_pool = MagicMock()
        self.mock_pool.getconn.return_value = self.mock_conn

    def test_oracle_agent_has_strategic_tools(self):
        oracle = OracleAgent(
            config=self.mock_config,
            logger=self.mock_logger,
            pg_pool=self.mock_pool,
            event_bus=self.mock_event_bus
        )
        tool_names = [t.__name__ for t in oracle.tools]
        self.assertIn("query_strategic_decisions", tool_names)
        self.assertIn("check_anti_backlog", tool_names)
        self.assertIn("record_strategic_milestone", tool_names)

    def test_orchestrator_agent_has_milestone_tool(self):
        orchestrator = OrchestratorAgent(
            config=self.mock_config,
            logger=self.mock_logger,
            pg_pool=self.mock_pool,
            event_bus=self.mock_event_bus
        )
        tool_names = [t.__name__ for t in orchestrator.tools]
        self.assertIn("record_strategic_milestone", tool_names)

    async def test_oracle_check_anti_backlog_hit(self):
        oracle = OracleAgent(
            config=self.mock_config,
            logger=self.mock_logger,
            pg_pool=self.mock_pool,
            event_bus=self.mock_event_bus
        )
        # Mock cursor returning a match for rejected idea
        self.mock_cursor.fetchall.return_value = [
            ("ANTI-042", "Reject In-Memory Bus For Production", "In-memory buses drop inter-process messages.")
        ]

        result = await oracle.execute_tool("check_anti_backlog", {"topic": "in-memory bus"})
        self.assertIn("REJECTED IN ANTI-BACKLOG", result)
        self.assertIn("ANTI-042", result)
        self.mock_cursor.execute.assert_any_call('SET search_path TO "01-Strategic-Nexus", public')

    async def test_oracle_check_anti_backlog_clean(self):
        oracle = OracleAgent(
            config=self.mock_config,
            logger=self.mock_logger,
            pg_pool=self.mock_pool,
            event_bus=self.mock_event_bus
        )
        self.mock_cursor.fetchall.return_value = []

        result = await oracle.execute_tool("check_anti_backlog", {"topic": "clean-feature"})
        self.assertIn("not in the Anti-Backlog", result)

    async def test_oracle_record_strategic_milestone(self):
        oracle = OracleAgent(
            config=self.mock_config,
            logger=self.mock_logger,
            pg_pool=self.mock_pool,
            event_bus=self.mock_event_bus
        )

        res = await oracle.execute_tool("record_strategic_milestone", {
            "session_id": "sess-oracle-01",
            "milestone": "FEAT-100 Ready",
            "action": "Audited anti-backlog and aligned patterns",
            "outcome": "Milestone validated"
        })
        self.assertIn("successfully recorded and broadcast", res)
        # Check DB insert was called
        self.mock_conn.commit.assert_called()
        # Check NATS broadcast
        self.mock_event_bus.publish.assert_called_once_with(
            "bastien-antigravity.strategic.milestone",
            {
                "source": "oracle",
                "session_id": "sess-oracle-01",
                "milestone": "FEAT-100 Ready",
                "action": "Audited anti-backlog and aligned patterns",
                "outcome": "Milestone validated"
            }
        )

    async def test_orchestrator_record_strategic_milestone(self):
        orchestrator = OrchestratorAgent(
            config=self.mock_config,
            logger=self.mock_logger,
            pg_pool=self.mock_pool,
            event_bus=self.mock_event_bus
        )

        res = await orchestrator.execute_tool("record_strategic_milestone", {
            "session_id": "sess-orch-01",
            "milestone": "Epic Complete",
            "action": "Coordinated developer and qa verification",
            "outcome": "100% tests green"
        })
        self.assertIn("successfully recorded and broadcast", res)
        self.mock_conn.commit.assert_called()
        self.mock_event_bus.publish.assert_called_once_with(
            "bastien-antigravity.strategic.milestone",
            {
                "source": "orchestrator",
                "session_id": "sess-orch-01",
                "milestone": "Epic Complete",
                "action": "Coordinated developer and qa verification",
                "outcome": "100% tests green"
            }
        )


if __name__ == "__main__":
    unittest.main()
