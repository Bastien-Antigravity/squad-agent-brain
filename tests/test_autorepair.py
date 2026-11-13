#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Unit tests for 08-Squad-Agent real-time AutoRepair coordinator, circuit breaker,
isolated /tmp git worktree patch verification, and incident REST endpoints.
"""

import asyncio
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

SQUAD_DIR = Path(__file__).resolve().parent.parent
TOOLBOX_PY_DIR = SQUAD_DIR.parent.parent / "microservice-toolbox" / "python"
for candidate in (str(TOOLBOX_PY_DIR), str(SQUAD_DIR)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from src.agents.autorepair import (
    AutoRepairCoordinator,
    RestartCircuitBreaker,
    RuntimeCapabilities,
    classify_incident_tier,
    resolve_incident_subject,
    validate_proposed_diff,
)
from src.rest.rest_handler import SquadRESTHandler


def _make_config(
    brain_id: str = "obsidian-brain",
    prefix: str = "bastien-antigravity",
    autorepair_enabled: bool = True,
) -> MagicMock:
    cfg = MagicMock()
    cfg.data = {
        "capabilities": {
            "squad_agent": {
                "target_brain_id": brain_id,
                "autorepair": {
                    "enabled": autorepair_enabled,
                },
            },
            "nats": {"subject_prefix": prefix},
        }
    }
    cfg.get_rest_addr.side_effect = KeyError("not configured")
    return cfg


class TestAutoRepairHelpers(unittest.TestCase):
    def test_resolve_incident_subject_partitioning(self):
        self.assertEqual(resolve_incident_subject("bastien-antigravity", "obsidian-brain"), "bastien-antigravity.fleet.incident")
        self.assertEqual(resolve_incident_subject("bastien-antigravity", "root"), "bastien-antigravity.fleet.incident")
        self.assertEqual(resolve_incident_subject("bastien-antigravity", ""), "bastien-antigravity.fleet.incident")
        self.assertEqual(resolve_incident_subject("bastien-antigravity", "alpha-brain"), "bastien-antigravity.alpha-brain.fleet.incident")

    def test_classify_incident_tier(self):
        self.assertEqual(classify_incident_tier({"message": "listen tcp :8085: bind: address already in use"}), 1)
        self.assertEqual(classify_incident_tier({"message": "Config load error in standalone.yaml"}), 2)
        self.assertEqual(classify_incident_tier({"message": "Failed to ping postgresql on timescale_db: connection refused"}), 3)
        self.assertEqual(classify_incident_tier({"message": "panic: runtime error: invalid memory address"}), 4)

    def test_circuit_breaker_freezes_after_three_strikes_and_recovers(self):
        cb = RestartCircuitBreaker(max_strikes=3, window_sec=120.0)
        for idx, t in enumerate((10.0, 20.0, 30.0), start=1):
            frozen, count = cb.record_strike("obsidian-brain", "log_server", now=t)
            self.assertFalse(frozen)
            self.assertEqual(count, idx)

        frozen, count = cb.record_strike("obsidian-brain", "log_server", now=40.0)
        self.assertTrue(frozen)
        self.assertEqual(count, 4)
        self.assertTrue(cb.is_frozen("obsidian-brain", "log_server", now=100.0))

        # After cooldown window (>120s), service automatically unfreezes
        self.assertFalse(cb.is_frozen("obsidian-brain", "log_server", now=170.0))

    def test_validate_proposed_diff_blocks_unsafe_paths_and_accepts_scoped_diff(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            git_root = Path(tmpdir)
            svc_dir = git_root / "my-svc"
            svc_dir.mkdir()

            traversal = "--- a/../../etc/passwd\n+++ b/../../etc/passwd\n@@ -1 +1 @@\n-a\n+b\n"
            ok, reason, _ = validate_proposed_diff(traversal, git_root, svc_dir)
            self.assertFalse(ok)
            self.assertIn("Unsafe patch path", reason)

            secret_diff = "--- a/my-svc/.env\n+++ b/my-svc/.env\n@@ -1 +1 @@\n-A=1\n+A=2\n"
            ok, reason, _ = validate_proposed_diff(secret_diff, git_root, svc_dir)
            self.assertFalse(ok)
            self.assertIn("Protected file", reason)

            valid = "--- a/my-svc/app.py\n+++ b/my-svc/app.py\n@@ -1 +1 @@\n-x=1\n+x=2\n"
            ok, reason, paths = validate_proposed_diff(valid, git_root, svc_dir)
            self.assertTrue(ok, reason)
            self.assertEqual(paths, ["my-svc/app.py"])


class TestAutoRepairCoordinator(unittest.IsolatedAsyncioTestCase):
    async def test_handle_incident_proposal_only_dedupe_and_menu_callback(self):
        cfg = _make_config(brain_id="beta-brain")
        logger = MagicMock()
        notif = MagicMock()
        notif.send_alert = AsyncMock()
        on_change = MagicMock()
        event_bus = MagicMock()
        event_bus.subscribe = AsyncMock(return_value=["sub-1"])
        event_bus.unsubscribe = AsyncMock()

        coord = AutoRepairCoordinator(
            config=cfg,
            logger=logger,
            pg_pool=None,
            event_bus=event_bus,
            notif_client=notif,
            on_incident_change=on_change,
        )
        coord.capabilities = RuntimeCapabilities(
            workspace_writable=False,
            git_available=False,
            toolchains={},
            watchdog_rest_url="",
            auto_apply=False,
        )

        self.assertEqual(coord.incident_topic, "bastien-antigravity.beta-brain.fleet.incident")

        await coord.start()
        event_bus.subscribe.assert_awaited_once()
        self.assertIsNotNone(coord._incident_cb)

        payload = {
            "incident_id": "inc-proposal-001",
            "brain_id": "beta-brain",
            "event_hash": "hash-unique-prop-001",
            "service_name": "nonexistent_service",
            "hostname": "docker-node",
            "level_str": "ERROR",
            "filename": "handler.go",
            "line_number": "42",
            "message": "bind: address already in use",
        }
        record = await coord.handle_incident(payload)
        self.assertEqual(record["tier"], 1)
        self.assertEqual(record["status"], "AWAITING_APPROVAL")
        notif.send_alert.assert_awaited()
        on_change.assert_called()

        # Duplicate event_hash should return cached record without extra alert
        prev_calls = notif.send_alert.await_count
        dup_record = await coord.handle_incident(payload)
        self.assertEqual(dup_record["incident_id"], "inc-proposal-001")
        self.assertEqual(notif.send_alert.await_count, prev_calls)

        # Tier-1 auto_apply (distinct signature) cleanly transitions to RESTART_PENDING when Watchdog REST is absent
        coord.capabilities.auto_apply = True
        auto_payload = dict(payload, incident_id="inc-auto-002", event_hash="hash-unique-auto-002", line_number="99")
        auto_record = await coord.handle_incident(auto_payload)
        self.assertEqual(auto_record["status"], "RESTART_PENDING")

        # Reject incident works cleanly
        ok, rejected = await coord.reject_incident("inc-proposal-001", reason="Duplicate in test")
        self.assertTrue(ok)
        self.assertEqual(rejected["status"], "REJECTED")

        saved_cb = coord._incident_cb
        self.assertIsNotNone(saved_cb)
        await coord.stop()
        event_bus.unsubscribe.assert_awaited_once_with(
            "bastien-antigravity.beta-brain.fleet.incident",
            saved_cb,
            ["sub-1"],
        )
        self.assertIsNone(coord._incident_cb)

    async def test_isolated_worktree_verification_gates_apply_and_tags_restore_point(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ws = Path(tmpdir).resolve()
            repo = ws / "demo-service"
            (repo / "app").mkdir(parents=True)
            (repo / "tests").mkdir(parents=True)

            target_file = repo / "app" / "calc.py"
            target_file.write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
            (repo / "tests" / "test_calc.py").write_text(
                "import unittest\n"
                "from app.calc import add\n\n"
                "class TestCalc(unittest.TestCase):\n"
                "    def test_add(self):\n"
                "        self.assertEqual(add(2, 3), 5)\n\n"
                "if __name__ == '__main__':\n"
                "    unittest.main()\n",
                encoding="utf-8",
            )

            subprocess.run(["git", "init"], cwd=str(repo), check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(repo), check=True)
            subprocess.run(["git", "config", "user.name", "TestBot"], cwd=str(repo), check=True)
            subprocess.run(["git", "add", "."], cwd=str(repo), check=True)
            subprocess.run(["git", "commit", "-m", "init buggy calc"], cwd=str(repo), check=True, stdout=subprocess.DEVNULL)

            good_diff = (
                "--- a/app/calc.py\n"
                "+++ b/app/calc.py\n"
                "@@ -1,2 +1,2 @@\n"
                " def add(a, b):\n"
                "-    return a - b\n"
                "+    return a + b\n"
            )
            bad_diff = (
                "--- a/app/calc.py\n"
                "+++ b/app/calc.py\n"
                "@@ -1,2 +1,2 @@\n"
                " def add(a, b):\n"
                "-    return a - b\n"
                "+    return a * b\n"
            )

            coord = AutoRepairCoordinator(
                config=_make_config(),
                logger=MagicMock(),
                pg_pool=None,
                event_bus=None,
                notif_client=None,
            )
            coord.workspace_root = ws
            coord.vault_root = ws / "obsidian-brain"
            coord.capabilities = RuntimeCapabilities(
                workspace_writable=True,
                git_available=True,
                toolchains={"python3": sys.executable},
                watchdog_rest_url="",
                auto_apply=False,
            )

            # 1. Failing patch must fail isolated worktree verification and leave repo untouched
            bad_inc = {
                "incident_id": "inc-bad-patch",
                "brain_id": "obsidian-brain",
                "service_name": "demo_service",
                "tier": 4,
                "status": "AWAITING_APPROVAL",
                "filename": "app/calc.py",
                "line_number": "2",
                "message": "add(2, 3) returned -1",
                "root_cause": "Wrong arithmetic operator",
                "proposed_patch": bad_diff,
                "target_relpath": "demo-service/app/calc.py",
            }
            coord._remember_incident(bad_inc)
            ok_bad, res_bad = await coord.approve_incident("inc-bad-patch")
            self.assertFalse(ok_bad)
            self.assertEqual(res_bad["status"], "VERIFICATION_FAILED")
            self.assertIn("return a - b", target_file.read_text(encoding="utf-8"))

            # 2. Valid patch passes isolated worktree unittest, creates restore-point tag, and applies cleanly
            good_inc = dict(bad_inc, incident_id="inc-good-patch", proposed_patch=good_diff)
            coord._remember_incident(good_inc)
            ok_good, res_good = await coord.approve_incident("inc-good-patch")
            self.assertTrue(ok_good)
            self.assertEqual(res_good["status"], "PATCH_APPLIED_RESTART_PENDING")
            self.assertIn("return a + b", target_file.read_text(encoding="utf-8"))

            tags = subprocess.check_output(["git", "tag"], cwd=str(repo), text=True)
            self.assertIn("restore-point/autorepair-demo_service-", tags)
            log_md = (coord.vault_root / "05-Fleet-Operation" / "02-Deployment-Logs" / "AutoRepair-Log.md").read_text(encoding="utf-8")
            self.assertIn("inc-good-patch", log_md)

            # 3. Uncommitted local edits must block live git apply (DIRTY_WORKTREE_BLOCKED)
            target_file.write_text("# uncommitted manual work\ndef add(a, b):\n    return a - b\n", encoding="utf-8")
            dirty_inc = dict(bad_inc, incident_id="inc-dirty-tree", proposed_patch=good_diff)
            coord._remember_incident(dirty_inc)
            ok_dirty, res_dirty = await coord.approve_incident("inc-dirty-tree")
            self.assertFalse(ok_dirty)
            self.assertEqual(res_dirty["status"], "DIRTY_WORKTREE_BLOCKED")
            self.assertIn("# uncommitted manual work", target_file.read_text(encoding="utf-8"))

    async def test_circuit_breaker_blocks_fourth_approval(self):
        coord = AutoRepairCoordinator(
            config=_make_config(),
            logger=MagicMock(),
            pg_pool=None,
            event_bus=None,
            notif_client=None,
        )
        coord.capabilities = RuntimeCapabilities(
            workspace_writable=False,
            git_available=False,
            toolchains={},
            watchdog_rest_url="",
            auto_apply=False,
        )
        for idx in range(1, 5):
            inc_id = f"inc-cb-{idx}"
            coord._remember_incident({
                "incident_id": inc_id,
                "brain_id": "obsidian-brain",
                "service_name": "flaky_svc",
                "tier": 1,
                "status": "AWAITING_APPROVAL",
                "message": "bind: address already in use",
                "proposed_patch": "",
            })
            ok, rec = await coord.approve_incident(inc_id)
            if idx <= 3:
                self.assertTrue(ok)
            else:
                self.assertFalse(ok)
                self.assertEqual(rec["status"], "FROZEN")

    async def test_on_the_fly_toggle_and_signature_coalescing(self):
        cfg = _make_config()
        notif = MagicMock()
        notif.send_alert = AsyncMock()
        on_change = MagicMock()

        coord = AutoRepairCoordinator(
            config=cfg,
            logger=MagicMock(),
            pg_pool=None,
            event_bus=None,
            notif_client=notif,
            on_incident_change=on_change,
        )
        coord.capabilities = RuntimeCapabilities(
            workspace_writable=False,
            git_available=False,
            toolchains={},
            watchdog_rest_url="",
            auto_apply=False,
        )

        # Pause AutoRepair on the fly -> skips processing cleanly
        status_off = coord.set_enabled(False, reason="Maintenance window")
        self.assertFalse(status_off["enabled"])
        self.assertEqual(status_off["paused_reason"], "Maintenance window")
        skipped = await coord.handle_incident({
            "incident_id": "inc-paused-1",
            "event_hash": "hash-paused-1",
            "service_name": "config_server",
            "message": "transient",
        })
        self.assertEqual(skipped["status"], "DISABLED")
        self.assertEqual(coord.get_autorepair_status()["metrics"]["skipped_while_disabled"], 1)
        notif.send_alert.assert_not_awaited()

        # Re-enable on the fly -> processes & coalesces matching open signatures
        status_on = coord.set_enabled(True)
        self.assertTrue(status_on["enabled"])
        first = await coord.handle_incident({
            "incident_id": "inc-sig-1",
            "event_hash": "hash-sig-1",
            "service_name": "config_server",
            "filename": "main.go",
            "line_number": "12",
            "level_str": "ERROR",
            "message": "bind: address already in use",
            "occurrence_count": 2,
        })
        self.assertEqual(first["status"], "AWAITING_APPROVAL")
        self.assertEqual(notif.send_alert.await_count, 1)

        second = await coord.handle_incident({
            "incident_id": "inc-sig-2",
            "event_hash": "hash-sig-2",
            "service_name": "config_server",
            "filename": "main.go",
            "line_number": "12",
            "level_str": "ERROR",
            "message": "bind: address already in use",
            "occurrence_count": 5,
        })
        self.assertEqual(second["incident_id"], "inc-sig-1")
        self.assertEqual(second["occurrence_count"], 7)
        self.assertEqual(notif.send_alert.await_count, 1)


class TestAutoRepairConfigLifecycle(unittest.TestCase):
    def test_startup_respects_config_disabled_and_defaults_auto_apply_false(self):
        cfg = _make_config(autorepair_enabled=False)
        coord = AutoRepairCoordinator(
            config=cfg,
            logger=MagicMock(),
            pg_pool=None,
            event_bus=MagicMock(),
            notif_client=AsyncMock(),
        )
        status = coord.get_autorepair_status()
        self.assertFalse(status["enabled"])
        self.assertFalse(status["auto_apply"])
        self.assertIn("config", status["paused_reason"].lower())

    def test_missing_autorepair_config_fails_fast(self):
        cfg = _make_config()
        del cfg.data["capabilities"]["squad_agent"]["autorepair"]
        with self.assertRaises(ValueError):
            AutoRepairCoordinator(
                config=cfg,
                logger=MagicMock(),
                pg_pool=None,
                event_bus=MagicMock(),
                notif_client=AsyncMock(),
            )

    def test_docker_slice_merge_top_level_and_live_reload(self):
        cfg = MagicMock()
        cfg.data = {
            "capabilities": {
                "squad_agent": {"target_brain_id": "obsidian-brain"},
                "nats": {"subject_prefix": "bastien-antigravity"},
            },
            "squad_agent": {
                "autorepair": {"enabled": True},
            },
        }
        coord = AutoRepairCoordinator(
            config=cfg,
            logger=MagicMock(),
            pg_pool=None,
            event_bus=MagicMock(),
            notif_client=AsyncMock(),
        )
        self.assertTrue(coord.enabled)
        self.assertFalse(coord.get_autorepair_status()["auto_apply"])

        # Manual runtime pause should NOT be clobbered by unchanged live config refresh
        coord.set_enabled(False, reason="Operator pause")
        cb = cfg.on_live_conf_update.call_args[0][0]
        cb(cfg.data)
        self.assertFalse(coord.enabled)
        self.assertEqual(coord.get_autorepair_status()["paused_reason"], "Operator pause")

        # Explicit change in live config should take effect
        coord.set_enabled(True, reason="Resume")
        cfg.data["squad_agent"]["autorepair"]["enabled"] = False
        cb(cfg.data)
        self.assertFalse(coord.enabled)

        cfg.data["squad_agent"]["autorepair"]["enabled"] = True
        cb(cfg.data)
        self.assertTrue(coord.enabled)


class TestIncidentRESTRoutes(unittest.TestCase):
    def test_incident_rest_endpoints(self):
        sample = {
            "incident_id": "inc-rest-001",
            "brain_id": "obsidian-brain",
            "service_name": "log_server",
            "tier": 3,
            "status": "AWAITING_APPROVAL",
            "root_cause": "timescale_db offline",
        }
        mock_controller = MagicMock()
        mock_controller.config = None
        mock_controller.list_incidents.return_value = [sample]
        mock_controller.get_incident.side_effect = lambda inc_id: sample if inc_id == "inc-rest-001" else None
        mock_controller.approve_incident = AsyncMock(return_value=(True, dict(sample, status="REPAIRED")))
        mock_controller.reject_incident = AsyncMock(return_value=(True, dict(sample, status="REJECTED")))
        mock_controller.resolve_incident = AsyncMock(return_value=(True, dict(sample, status="RESOLVED")))
        mock_controller.get_autorepair_status.return_value = {"enabled": True, "auto_apply": False, "initialized": True}
        mock_controller.set_autorepair_enabled.return_value = {"enabled": False, "paused_reason": "Maintenance", "initialized": True}
        mock_controller.unfreeze_autorepair_service.return_value = {"service_name": "log_server", "was_frozen": True}

        app = FastAPI()
        handler = SquadRESTHandler(mock_controller, MagicMock())
        handler.register_routes(app)

        with TestClient(app) as client:
            res_list = client.get("/api/v1/squad/incidents")
            self.assertEqual(res_list.status_code, 200)
            self.assertEqual(res_list.json()["count"], 1)

            res_one = client.get("/api/v1/squad/incidents/inc-rest-001")
            self.assertEqual(res_one.status_code, 200)
            self.assertEqual(res_one.json()["incident"]["service_name"], "log_server")

            res_404 = client.get("/api/v1/squad/incidents/missing")
            self.assertEqual(res_404.status_code, 404)

            res_status = client.get("/api/v1/squad/autorepair/status")
            self.assertEqual(res_status.status_code, 200)
            self.assertTrue(res_status.json()["enabled"])

            with patch.dict(os.environ, {"GITHUB_TOKEN": ""}, clear=False):
                res_403 = client.post("/api/v1/squad/incidents/inc-rest-001/approve")
                self.assertEqual(res_403.status_code, 403)
                res_toggle_403 = client.post("/api/v1/squad/autorepair/toggle", json={"enabled": False})
                self.assertEqual(res_toggle_403.status_code, 403)

            with patch.dict(os.environ, {"GITHUB_TOKEN": "ghp_test_token"}, clear=False):
                res_approve = client.post("/api/v1/squad/incidents/inc-rest-001/approve")
                self.assertEqual(res_approve.status_code, 200)
                self.assertTrue(res_approve.json()["success"])
                self.assertEqual(res_approve.json()["incident"]["status"], "REPAIRED")

                res_reject = client.post("/api/v1/squad/incidents/inc-rest-001/reject", json={"reason": "No needed"})
                self.assertEqual(res_reject.status_code, 200)
                self.assertEqual(res_reject.json()["incident"]["status"], "REJECTED")

                res_resolve = client.post("/api/v1/squad/incidents/inc-rest-001/resolve", json={"note": "Fixed manually"})
                self.assertEqual(res_resolve.status_code, 200)
                self.assertEqual(res_resolve.json()["incident"]["status"], "RESOLVED")

                res_toggle = client.post("/api/v1/squad/autorepair/toggle", json={"enabled": False, "reason": "Maintenance"})
                self.assertEqual(res_toggle.status_code, 200)
                self.assertFalse(res_toggle.json()["enabled"])

                res_unfreeze = client.post("/api/v1/squad/autorepair/unfreeze", json={"service_name": "log_server"})
                self.assertEqual(res_unfreeze.status_code, 200)
                self.assertTrue(res_unfreeze.json()["was_frozen"])


if __name__ == "__main__":
    unittest.main()
