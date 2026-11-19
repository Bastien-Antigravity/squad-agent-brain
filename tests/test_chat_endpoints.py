#!/usr/bin/env python
# coding:utf-8

import unittest
from unittest.mock import MagicMock, AsyncMock
import sys
from pathlib import Path
import asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Resolve paths so we can import src.*
_self_dir = Path(__file__).resolve().parent.parent
if str(_self_dir) not in sys.path:
    sys.path.insert(0, str(_self_dir))

import src.bootstrap as bootstrap
from src.rest.rest_handler import SquadRESTHandler
from src.core.controller import CommandController


class TestSquadChatRESTEndpoints(unittest.TestCase):
    def setUp(self):
        self.mock_controller = MagicMock()
        self.mock_logger = MagicMock()
        self.rest_handler = SquadRESTHandler(self.mock_controller, self.mock_logger)
        
        self.app = FastAPI()
        self.rest_handler.register_routes(self.app)
        self.client = TestClient(self.app)

    def tearDown(self):
        self.client.close()

    def test_route_order_stream_does_not_hit_history(self):
        # Configure mock get_chat_history return
        self.mock_controller.get_chat_history = AsyncMock(return_value=[{"sender": "system", "content": "history"}])
        
        response = self.client.get("/api/v1/squad/chat/stream/test_session_123?once=true")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/event-stream", response.headers.get("content-type", ""))
        self.assertIn("connected", response.text)
        self.mock_controller.get_chat_history.assert_not_called()

    def test_get_chat_history_endpoint(self):
        self.mock_controller.get_chat_history = AsyncMock(return_value=[{"sender": "user", "content": "hello"}])
        
        response = self.client.get("/api/v1/squad/chat/test_session_123")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get("success"))
        self.assertEqual(len(data.get("history", [])), 1)
        self.mock_controller.get_chat_history.assert_called_once_with("test_session_123")

    def test_post_chat_message_endpoint(self):
        import os
        old_token = os.environ.get("GITHUB_TOKEN")
        try:
            os.environ["GITHUB_TOKEN"] = "ghp_test_token"
            self.mock_controller.publish_user_message = AsyncMock()
            
            response = self.client.post("/api/v1/squad/chat/test_session_123", json={"message": "Audit code"})
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertTrue(data.get("success"))
            self.mock_controller.publish_user_message.assert_called_once_with("test_session_123", "Audit code")
        finally:
            if old_token is not None:
                os.environ["GITHUB_TOKEN"] = old_token
            else:
                os.environ.pop("GITHUB_TOKEN", None)

    def test_status_endpoint_github_configured_flag(self):
        import os
        old_token = os.environ.get("GITHUB_TOKEN")
        self.mock_controller.get_status = AsyncMock(return_value={"healthy": True, "status": "running", "version": "1.0.0"})
        try:
            # Case 1: Token present
            os.environ["GITHUB_TOKEN"] = "ghp_test_12345"
            resp = self.client.get("/api/v1/status")
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertTrue(data.get("github_configured"))
            self.assertTrue(data.get("healthy"))
            self.assertEqual(data.get("status"), "running")

            # Case 2: Token missing
            os.environ["GITHUB_TOKEN"] = ""
            resp = self.client.get("/api/v1/status")
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertFalse(data.get("github_configured"))
            self.assertFalse(data.get("healthy"))
            self.assertEqual(data.get("status"), "disabled")
        finally:
            if old_token is not None:
                os.environ["GITHUB_TOKEN"] = old_token
            else:
                os.environ.pop("GITHUB_TOKEN", None)

    def test_squad_endpoints_blocked_when_github_token_missing(self):
        import os
        old_token = os.environ.get("GITHUB_TOKEN")
        try:
            os.environ["GITHUB_TOKEN"] = ""
            # Command execution stream
            resp_run = self.client.get("/api/v1/squad/run/preflight-check")
            self.assertEqual(resp_run.status_code, 403)
            self.assertIn("Squad Agent is disabled", resp_run.json().get("detail", ""))

            # Mode switcher
            resp_mode = self.client.post("/api/v1/squad/active-mode", json={"mode": "1"})
            self.assertEqual(resp_mode.status_code, 403)
            self.assertIn("Squad Agent is disabled", resp_mode.json().get("detail", ""))

            # Chat posting
            resp_chat = self.client.post("/api/v1/squad/chat/test_session", json={"message": "hello"})
            self.assertEqual(resp_chat.status_code, 403)
            self.assertIn("Squad Agent is disabled", resp_chat.json().get("detail", ""))
        finally:
            if old_token is not None:
                os.environ["GITHUB_TOKEN"] = old_token
            else:
                os.environ.pop("GITHUB_TOKEN", None)


class TestCommandControllerChatFallback(unittest.IsolatedAsyncioTestCase):
    async def test_publish_and_get_history_without_postgres(self):
        # Create controller with pool=None
        mock_config = MagicMock()
        mock_config.data = {}
        mock_logger = MagicMock()
        controller = CommandController(config=mock_config, logger=mock_logger)
        controller.pool = None
        
        # Publish user message
        await controller.publish_user_message("session_fallback", "Test fallback message")
        
        # Retrieve history
        history = await controller.get_chat_history("session_fallback")
        self.assertGreaterEqual(len(history), 1)
        self.assertEqual(history[-1]["content"], "Test fallback message")
        self.assertEqual(history[-1]["sender"], "user")

    async def test_agent_supervision_and_readiness_tracking(self):
        mock_config = MagicMock()
        mock_config.data = {}
        mock_logger = MagicMock()
        controller = CommandController(config=mock_config, logger=mock_logger)
        controller.pool = None

        ok_agent = MagicMock()
        ok_agent.role_name = "orchestrator"
        ok_agent.running = False
        async def _ok_start():
            ok_agent.running = True
        ok_agent.start = _ok_start

        bad_agent = MagicMock()
        bad_agent.role_name = "developer"
        async def _bad_start():
            raise RuntimeError("NATS subscription failure")
        bad_agent.start = _bad_start

        ready_count = await controller.start_and_supervise_agents([ok_agent, bad_agent])
        self.assertEqual(ready_count, 1)
        self.assertEqual(controller.agent_states["orchestrator"], "ready")
        self.assertEqual(controller.agent_states["developer"], "failed")
        status = await controller.get_status()
        self.assertFalse(status["healthy"])
        self.assertEqual(status["status"], "Degraded")


class TestFleetCommanderAndMCPSafety(unittest.TestCase):
    def test_fleet_commander_dry_run_does_not_mutate_git(self):
        from src.fleet.fleet_commander import FleetCommander
        with unittest.mock.patch.object(FleetCommander, "_load_inventory", return_value=["repo-a"]):
            cmdr = FleetCommander("/tmp/fake_workspace", dry_run=True, target_repo="repo-a")
            recorded_cmds = []

            def fake_run(cmd, cwd):
                cmd_list = cmd if isinstance(cmd, list) else cmd.split()
                recorded_cmds.append(cmd_list)
                if "rev-parse" in cmd_list or "--show-current" in cmd_list:
                    return "develop", None
                if "status" in cmd_list:
                    return " M README.md", None
                if "rev-list" in cmd_list:
                    return "0 2", None
                return "git version 2.40.0", None

            cmdr._run_command = fake_run
            cmdr.audit_docs = lambda p, n: True
            cmdr.validate_architecture = lambda p, n: True
            cmdr.audit_isolation_zone = lambda p, n: True

            with unittest.mock.patch("pathlib.Path.exists", return_value=True):
                cmdr.execute_fleet_push()
                cmdr.execute_fleet_sync()

            flat_verbs = [c[1] for c in recorded_cmds if len(c) > 1 and c[0] == "git"]
            self.assertNotIn("add", flat_verbs)
            self.assertNotIn("commit", flat_verbs)
            self.assertNotIn("push", flat_verbs)
            self.assertNotIn("pull", flat_verbs)

    def test_fleet_commander_worktree_safety_blocks_secrets(self):
        import tempfile
        from src.fleet.fleet_commander import FleetCommander
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            with unittest.mock.patch.object(FleetCommander, "_load_inventory", return_value=[]):
                cmdr = FleetCommander(tmp, dry_run=True)
                self.assertFalse(cmdr._audit_worktree_safety(tmp_path, "repo-a", "?? .env\n"))
                self.assertFalse(cmdr._audit_worktree_safety(tmp_path, "repo-a", " M server.key\n"))
                self.assertTrue(cmdr._audit_worktree_safety(tmp_path, "repo-a", " M README.md\n"))


if __name__ == "__main__":
    unittest.main()
