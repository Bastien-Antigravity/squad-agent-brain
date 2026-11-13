#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Unit tests for 08-Squad-Agent authoritative Exchange Contracts builder and GET /api/v1/contracts.
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

SQUAD_DIR = Path(__file__).resolve().parent.parent
if str(SQUAD_DIR) not in sys.path:
    sys.path.insert(0, str(SQUAD_DIR))

from src.rest.contracts import build_squad_agent_contracts
from src.rest.rest_handler import SquadRESTHandler


class TestSquadContractsAPI(unittest.TestCase):
    def test_build_squad_agent_contracts(self):
        app = FastAPI()

        @app.get("/api/v1/squad/probe")
        def probe():
            return {"ok": True}

        config = MagicMock()
        config.data = {
            "capabilities": {
                "squad_agent": {"target_brain_id": "test-brain"},
                "nats": {"ip": "127.0.0.1", "port": "4222", "subject_prefix": "bastien-antigravity"},
                "timescale_db": {"ip": "127.0.0.1", "port": "5432"},
            }
        }
        config.get_version.return_value = "2.1.0"
        config.get_listen_addr.return_value = "127.0.0.1:8085"
        config.get_rest_addr.return_value = "127.0.0.1:8085"
        config.get_grpc_listen_addr.return_value = "127.0.0.1:50065"

        envelope = build_squad_agent_contracts(app=app, config=config)
        self.assertEqual(envelope["service"], "agent_squad")
        self.assertEqual(envelope["version"], "2.1.0")
        self.assertTrue(envelope["reliable"])
        self.assertTrue(envelope["exhaustive"])

        by_id = {c["id"]: c for c in envelope["contracts"]}
        self.assertTrue({"rest-sse", "grpc", "nats-event-bus", "postgres-memory"}.issubset(by_id.keys()))
        rest_targets = {op["target"] for op in by_id["rest-sse"]["operations"]}
        self.assertIn("/api/v1/squad/probe", rest_targets)
        self.assertIn("SquadControlService", by_id["grpc"]["schema"])
        nats_targets = {op["target"] for op in by_id["nats-event-bus"]["operations"]}
        self.assertIn("bastien-antigravity.test-brain.fleet.incident", nats_targets)
        pg_targets = {op["target"] for op in by_id["postgres-memory"]["operations"]}
        self.assertIn("watchdog_agent.fleet_error_logs", pg_targets)
        self.assertIn("watchdog_agent.fleet_incidents", pg_targets)

    def test_rest_handler_contracts_endpoint(self):
        mock_controller = MagicMock()
        mock_controller.config = None
        mock_controller.facade = MagicMock()
        mock_controller.facade.config = None
        mock_controller.get_status = AsyncMock(return_value={"healthy": True, "version": "0.0.1"})

        app = FastAPI()
        handler = SquadRESTHandler(mock_controller, MagicMock())
        handler.register_routes(app)

        with TestClient(app) as client:
            resp = client.get("/api/v1/contracts")
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertEqual(data["service"], "agent_squad")
            self.assertTrue(data["reliable"])
            self.assertGreaterEqual(len(data["contracts"]), 4)
            by_id = {c["id"]: c for c in data["contracts"]}
            rest_targets = {op["target"] for op in by_id["rest-sse"]["operations"]}
            self.assertIn("/api/v1/squad/incidents", rest_targets)
            self.assertIn("/api/v1/squad/incidents/{incident_id}/approve", rest_targets)
            self.assertIn("/api/v1/squad/autorepair/status", rest_targets)
            self.assertIn("/api/v1/squad/autorepair/toggle", rest_targets)


if __name__ == "__main__":
    unittest.main()

