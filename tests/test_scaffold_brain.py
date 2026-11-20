#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Unit and integration tests for scaffold_new_brain.py.
Validates brain vault scaffolding, folder hierarchy, mandatory ecosystem files,
YAML frontmatter compliance, standalone.yaml symlink, and agent skills compilation.

DATA FLOW:
1. Input: Temporary directory paths, mock brain vault parameters.
2. Logic: Executes scaffold_brain in dry-run and live modes.
3. Output: Assertions validating structural completeness, frontmatter tags, and symlink targets.
"""

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
import yaml

# Add 08-Squad-Agent to sys.path
SQUAD_AGENT_DIR = Path(__file__).resolve().parent.parent
if str(SQUAD_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(SQUAD_AGENT_DIR))

from src.lifecycle.scaffold_new_brain import scaffold_brain, create_file, create_symlink
from src.lib.orchestration_lib import resolve_vault_and_workspace


class TestScaffoldBrain(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="test_brain_scaffold_"))
        self.vault_root, _ = resolve_vault_and_workspace(__file__)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_create_file_dry_run(self):
        """Verify create_file respects dry_run mode."""
        target = self.test_dir / "sample.md"
        create_file(target, "content", dry_run=True)
        self.assertFalse(target.exists(), "Dry run must not create file on disk")

        create_file(target, "content", dry_run=False)
        self.assertTrue(target.exists(), "Live run must create file on disk")
        self.assertEqual(target.read_text(encoding="utf-8"), "content")

    def test_create_symlink_dry_run(self):
        """Verify create_symlink respects dry_run mode."""
        target = self.test_dir / "link.yaml"
        create_symlink(target, "../some/target.yaml", dry_run=True)
        self.assertFalse(target.exists(), "Dry run must not create symlink")

        create_symlink(target, "../some/target.yaml", dry_run=False)
        self.assertTrue(target.is_symlink(), "Live run must create symlink")
        self.assertEqual(os.readlink(target), "../some/target.yaml")

    def test_scaffold_brain_dry_run(self):
        """Verify scaffolding with dry_run=True produces no disk side effects."""
        target_path = self.test_dir / "dry-brain"
        scaffold_brain("dry-brain", target_path, self.vault_root, dry_run=True)
        self.assertFalse(target_path.exists(), "Dry run must not create destination directory")

    def test_full_brain_scaffolding(self):
        """End-to-end verification of complete brain vault scaffolding."""
        target_name = "test-domain-brain"
        target_path = self.test_dir / target_name

        scaffold_brain(target_name, target_path, self.vault_root, dry_run=False)

        # 1. Standard Double-Digit Folders
        expected_folders = [
            "00-AI-Orchestration",
            "01-Strategic-Nexus",
            "02-Business-BDD",
            "03-Tech-Stack",
            "04-Rapid-Prototyping",
            "05-Fleet-Operation",
            "06-Microservices",
            "07-Core-KMS",
            "07-Core-KMS/Role-Prompts",
            "08-Squad-Agent",
            "11-Code-Doc",
            "99-Humans",
            "quick-overview",
        ]
        for folder in expected_folders:
            folder_path = target_path / folder
            self.assertTrue(folder_path.is_dir(), f"Expected directory missing: {folder}")

        # 2. Mandatory Root Ecosystem Files
        expected_files = [
            target_path / "AGENTS.md",
            target_path / "README.md",
            target_path / "VERSION.txt",
            target_path / ".gitignore",
            target_path / "docker-compose.yaml",
            target_path / "Makefile",
            target_path / "Ecosystem-Map-MOC.md",
            target_path / "00-AI-Orchestration/AI-Project-DNA.md",
            target_path / "00-AI-Orchestration/AI-Session-State.md",
            target_path / "00-AI-Orchestration/AI-Init.md",
            target_path / "00-AI-Orchestration/Config/MODE-MANUAL.md",
            target_path / "quick-overview/00-Overview.md",
        ]
        for f in expected_files:
            self.assertTrue(f.exists(), f"Mandatory ecosystem file missing: {f}")

        # Ensure no non-compliant .env files were generated
        self.assertFalse((target_path / ".env").exists(), "Ecosystem rules prohibit .env files; configuration must source from standalone.yaml")

        # 3. Symlink Verification (non-dangling resolved relative path to native.yaml)
        symlink = target_path / "standalone.yaml"
        self.assertTrue(symlink.is_symlink(), "standalone.yaml must be a symlink")
        self.assertTrue(symlink.exists(), "standalone.yaml symlink must resolve cleanly (never dangling)")
        self.assertTrue(
            os.readlink(symlink).endswith("docker-deployment/modes/local/config/native.yaml"),
            f"Unexpected standalone.yaml symlink target: {os.readlink(symlink)}"
        )

        # Ensure stale runtime artifacts were NOT copied into 08-Squad-Agent
        copied_squad = target_path / "08-Squad-Agent"
        for excluded_name in ("data", ".DS_Store", ".shipper_offsets.json"):
            self.assertFalse((copied_squad / excluded_name).exists(), f"Excluded artifact leaked into copy: {excluded_name}")

        # Verify stale non-convert-agents logs from source vault are never copied into a new brain
        src_logs = self.vault_root / "08-Squad-Agent" / "logs"
        if src_logs.is_dir():
            src_log_names = {
                p.name for p in src_logs.iterdir()
                if p.is_file() and p.name != "squad_agent_convert_agents.log"
            }
            dst_logs = copied_squad / "logs"
            if dst_logs.is_dir():
                dst_log_names = {p.name for p in dst_logs.iterdir() if p.is_file()}
                leaked = src_log_names & dst_log_names
                self.assertFalse(leaked, f"Stale log files leaked from template vault: {leaked}")

        # 4. Frontmatter Integrity across generated Markdown files
        md_files_to_check = [
            target_path / "AGENTS.md",
            target_path / "Ecosystem-Map-MOC.md",
            target_path / "00-AI-Orchestration/AI-Project-DNA.md",
            target_path / "00-AI-Orchestration/AI-Session-State.md",
            target_path / "00-AI-Orchestration/AI-Init.md",
            target_path / "quick-overview/00-Overview.md",
        ]
        for md_file in md_files_to_check:
            content = md_file.read_text(encoding="utf-8")
            self.assertTrue(content.startswith("---"), f"{md_file.name} must start with YAML frontmatter marker '---'")
            parts = content.split("---", 2)
            self.assertGreaterEqual(len(parts), 3, f"{md_file.name} frontmatter not closed with '---'")
            frontmatter_raw = parts[1]
            data = yaml.safe_load(frontmatter_raw)
            self.assertIsInstance(data, dict, f"{md_file.name} frontmatter must parse to a dict")
            self.assertIn("microservice", data, f"{md_file.name} missing 'microservice' key")
            self.assertIn("type", data, f"{md_file.name} missing 'type' key")
            self.assertIn("status", data, f"{md_file.name} missing 'status' key")
            self.assertIn("tags", data, f"{md_file.name} missing 'tags' key")
            self.assertIsInstance(data["tags"], list, f"{md_file.name} 'tags' must be a list")

        # 5. Docker Orchestration Files Content Verification
        compose_text = (target_path / "docker-compose.yaml").read_text(encoding="utf-8")
        self.assertIn("teleremote-network", compose_text)
        self.assertIn("ghcr.io/bastien-antigravity/squad-agent:${TAG:-develop}", compose_text)
        self.assertIn(f"squad-agent-${{BRAIN_ID:-{target_name}}}", compose_text)
        self.assertIn("127.0.0.2", compose_text)
        self.assertIn("SA_PORT", compose_text)
        self.assertIn("RG_REST_PORT=8093", compose_text)
        self.assertIn("standalone.yaml:/app/standalone.yaml:ro", compose_text)
        self.assertIn("standalone.yaml:/app/brain/standalone.yaml:ro", compose_text)

        # Verify 08-Squad-Agent/standalone.yaml is present and readable even in an isolated temp folder
        inner_cfg = target_path / "08-Squad-Agent" / "standalone.yaml"
        self.assertTrue(inner_cfg.exists(), "08-Squad-Agent/standalone.yaml must be resolvable")

        makefile_text = (target_path / "Makefile").read_text(encoding="utf-8")
        self.assertIn("docker compose up -d", makefile_text)
        self.assertIn("scaffold-service:", makefile_text)
        self.assertIn("destroy-sandbox:", makefile_text)

        # 6. Agent Skills Compilation Verification
        skills_dir = target_path / ".agents" / "skills"
        self.assertTrue(skills_dir.is_dir(), ".agents/skills must be generated")
        key_agents = ["architect", "developer", "qa", "sentinel"]
        for agent in key_agents:
            agent_skill_file = skills_dir / agent / "SKILL.md"
            self.assertTrue(agent_skill_file.exists(), f"Agent skill missing: {agent}/SKILL.md")

    def test_sandbox_brain_isolation_and_teardown(self):
        """Verifies --sandbox creates a self-contained standalone.yaml, isolated inventory, and safe teardown."""
        import json
        from src.lifecycle.scaffold_new_brain import destroy_sandbox_brain

        target_name = "alpha-sandbox-brain"
        target_path = self.test_dir / target_name

        scaffold_brain(
            target_name,
            target_path,
            self.vault_root,
            dry_run=False,
            sa_port=8195,
            sa_grpc_port=8197,
            sandbox=True
        )

        # 1. standalone.yaml must be a regular self-contained file (not a symlink to live native.yaml)
        standalone_file = target_path / "standalone.yaml"
        self.assertTrue(standalone_file.is_file(), "Sandbox standalone.yaml must exist")
        self.assertFalse(standalone_file.is_symlink(), "Sandbox standalone.yaml must not be a symlink to live native.yaml")
        inner_link = target_path / "08-Squad-Agent" / "standalone.yaml"
        self.assertTrue(inner_link.is_symlink(), "08-Squad-Agent/standalone.yaml must symlink to ../standalone.yaml in sandbox mode")
        self.assertEqual(os.readlink(inner_link), "../standalone.yaml")
        yaml_text = standalone_file.read_text(encoding="utf-8")
        self.assertIn(f"target_brain_id: ${{TARGET_BRAIN_ID:{target_name}}}", yaml_text)
        self.assertIn('port: "${SA_PORT:8195}"', yaml_text)
        self.assertIn('grpc_port: "${SA_GRPC_PORT:8197}"', yaml_text)

        # 2. Isolated inventory.json must only contain the sandbox brain
        inv_file = target_path / "05-Fleet-Operation" / "00-Repo-Control" / "inventory.json"
        inv_data = json.loads(inv_file.read_text(encoding="utf-8"))
        self.assertTrue(inv_data.get("isolated_sandbox"))
        self.assertEqual(len(inv_data["repositories"]), 1)
        self.assertEqual(inv_data["repositories"][0]["name"], target_name)

        # 3. Safety guard must refuse to destroy 'obsidian-brain' or primary vault_root
        self.assertFalse(destroy_sandbox_brain("obsidian-brain", self.vault_root, self.vault_root, dry_run=False))
        self.assertTrue(self.vault_root.is_dir(), "Primary vault_root must remain untouched")

        # 4. Teardown must cleanly remove the sandbox brain directory
        self.assertTrue(destroy_sandbox_brain(target_name, target_path, self.vault_root, dry_run=False))
        self.assertFalse(target_path.exists(), "Sandbox directory must be deleted after destroy_sandbox_brain")

    def test_dynamic_ecosystem_port_allocation(self):
        """Verifies that ports are resolved dynamically from active capabilities without hardcoding."""
        from src.lifecycle.scaffold_new_brain import get_allocated_ecosystem_ports, resolve_available_ports
        import src.bootstrap as bootstrap

        allocated = get_allocated_ecosystem_ports(bootstrap.config)
        self.assertIsInstance(allocated, set)
        self.assertGreaterEqual(len(allocated), 10, "Should dynamically discover ports from native.yaml capabilities")
        # Ensure canonical ports from native.yaml are present
        self.assertIn(5000, allocated)  # web_interface
        self.assertIn(9020, allocated)  # log_server
        self.assertIn(4222, allocated)  # nats

        # Verify resolve_available_ports allocates a port beyond the discovered set
        target_path = self.test_dir / "dyn-brain"
        http_port, grpc_port = resolve_available_ports(target_path, bootstrap.config)
        self.assertNotIn(http_port, allocated, f"Allocated port {http_port} should not collide with ecosystem capabilities")
        self.assertNotIn(grpc_port, allocated, f"Allocated gRPC port {grpc_port} should not collide with ecosystem capabilities")
        self.assertGreaterEqual(http_port, 8185, "Should start from or above satellite base port")

    def test_generate_sandbox_standalone_yaml_complete_capabilities(self):
        """Verifies fallback standalone.yaml synthesis includes all mandatory ecosystem capabilities."""
        from src.lifecycle.scaffold_new_brain import generate_sandbox_standalone_yaml

        empty_vault = self.test_dir / "empty-vault"
        empty_vault.mkdir(parents=True, exist_ok=True)
        generated = generate_sandbox_standalone_yaml(empty_vault, "quant-brain", 8195, 8197)
        parsed = yaml.safe_load(generated)
        caps = parsed.get("capabilities", {})

        for mandatory_cap in (
            "config_server",
            "log_server",
            "nats",
            "timescale_db",
            "web_interface",
            "notif_server",
            "tele_remote",
            "watchdog_agent",
            "rag_engine",
            "squad_agent",
        ):
            self.assertIn(mandatory_cap, caps, f"Missing mandatory capability: {mandatory_cap}")

        self.assertIn("rest_port", caps["rag_engine"])
        self.assertIn("dashboard", caps["rag_engine"])
        self.assertEqual(caps["squad_agent"]["target_brain_id"], "${TARGET_BRAIN_ID:quant-brain}")
        self.assertIn("8195", str(caps["squad_agent"]["port"]))
        self.assertIn("8197", str(caps["squad_agent"]["grpc_port"]))
        self.assertIn("autorepair", caps["squad_agent"])
        self.assertEqual(caps["squad_agent"]["autorepair"]["enabled"], "${AUTO_REPAIR_ENABLED:-true}")

    def test_launch_satellite_docker_missing_cli_safe(self):
        """Verifies launch_satellite_docker returns False cleanly if docker CLI is missing."""
        from unittest.mock import patch
        from src.lifecycle.scaffold_new_brain import launch_satellite_docker

        with patch("src.lifecycle.scaffold_new_brain.shutilWhich", return_value=None):
            result = launch_satellite_docker(self.test_dir, "no-docker-brain", 8195)
        self.assertFalse(result)

    def test_destroy_sandbox_brain_uses_rest_port_and_psycopg2_placeholders(self):
        """Verifies destroy_sandbox_brain hits RAG rest_port (8093) and uses %s SQL placeholders."""
        from unittest.mock import MagicMock, patch
        from src.lifecycle.scaffold_new_brain import destroy_sandbox_brain

        target_name = "purge-check-brain"
        target_path = self.test_dir / target_name
        target_path.mkdir(parents=True, exist_ok=True)
        (target_path / "docker-compose.yaml").write_text("services: {}\n", encoding="utf-8")

        captured_urls = []
        captured_sql = []

        class _FakeResp:
            status = 200
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False

        def _fake_urlopen(req, timeout=2.5):
            captured_urls.append((req.full_url, req.get_method()))
            return _FakeResp()

        fake_cursor = MagicMock()
        fake_cursor.fetchone.return_value = ("conversation_turns",)
        fake_cursor.__enter__ = lambda s: fake_cursor
        fake_cursor.__exit__ = lambda s, *a: False

        def _record_execute(sql, params=None):
            captured_sql.append((sql, params))

        fake_cursor.execute.side_effect = _record_execute

        fake_conn = MagicMock()
        fake_conn.cursor.return_value = fake_cursor
        fake_pool = MagicMock()
        fake_pool.getconn.return_value = fake_conn

        with patch("src.lifecycle.scaffold_new_brain.shutilWhich", return_value=None), \
             patch("src.lifecycle.scaffold_new_brain.urllibUrlopen", side_effect=_fake_urlopen), \
             patch("src.lifecycle.scaffold_new_brain.get_pg_pool", return_value=fake_pool):
            ok = destroy_sandbox_brain(target_name, target_path, self.vault_root, dry_run=False)

        self.assertTrue(ok)
        self.assertFalse(target_path.exists())
        self.assertEqual(len(captured_urls), 2)
        self.assertTrue(captured_urls[0][0].endswith(":8093/api/v1/vault/purge"))
        self.assertEqual(captured_urls[0][1], "POST")
        self.assertTrue(captured_urls[1][0].endswith(f":8093/api/v1/workspaces/{target_name}"))
        self.assertEqual(captured_urls[1][1], "DELETE")

        delete_stmts = [sql for sql, _ in captured_sql if "DELETE FROM" in sql]
        self.assertGreaterEqual(len(delete_stmts), 1)
        for sql in delete_stmts:
            self.assertIn("%s", sql)
            self.assertNotIn("$1", sql)

    def test_multi_brain_mfe_registration_unique_tags(self):
        """Verifies primary and satellite brains register distinct MFE tags and names."""
        from unittest.mock import MagicMock, patch
        from src.web.server import register_mfe_with_web_interface

        cfg = MagicMock()
        cfg.data = {"capabilities": {"squad_agent": {"target_brain_id": "obsidian-brain"}}}
        logger = MagicMock()

        published = []

        def _capture_publish(config, log, capability, **kwargs):
            published.append((capability, kwargs))

        with patch("src.web.server.toolboxPublishServiceSpec", side_effect=_capture_publish):
            with patch.dict(os.environ, {"BRAIN_ID": "obsidian-brain", "TARGET_BRAIN_ID": "obsidian-brain"}, clear=False):
                register_mfe_with_web_interface(cfg, logger, "127.0.0.1", 8085)
            with patch.dict(os.environ, {"BRAIN_ID": "trading-brain", "TARGET_BRAIN_ID": "trading-brain"}, clear=False):
                register_mfe_with_web_interface(cfg, logger, "0.0.0.0", 8195)

        self.assertEqual(len(published), 2)
        _, root_kwargs = published[0]
        _, sat_kwargs = published[1]

        self.assertEqual(root_kwargs["name"], "squad_agent")
        self.assertEqual(root_kwargs["tag"], "squad-agent-mfe")
        self.assertEqual(root_kwargs["nav_title"], "🤖 Squad Command")

        self.assertEqual(sat_kwargs["name"], "squad_agent_trading_brain")
        self.assertEqual(sat_kwargs["tag"], "squad-agent-trading-brain-mfe")
        self.assertEqual(sat_kwargs["nav_title"], "🤖 Squad (trading-brain)")
        self.assertIn("?tag=squad-agent-trading-brain-mfe", sat_kwargs["url"])

    def test_clean_copy_excludes_stale_runtime_artifacts(self):
        """Verifies scaffold_brain excludes logs, data, standalone.yaml, .DS_Store, *.log, and .shipper_offsets.json."""
        mock_vault = self.test_dir / "mock-vault"
        mock_squad = mock_vault / "08-Squad-Agent"
        (mock_squad / "logs").mkdir(parents=True, exist_ok=True)
        (mock_squad / "data").mkdir(parents=True, exist_ok=True)
        (mock_squad / "logs" / "stale.log").write_text("old log\n", encoding="utf-8")
        (mock_squad / "data" / "state.json").write_text("{}\n", encoding="utf-8")
        (mock_squad / ".DS_Store").write_text("junk\n", encoding="utf-8")
        (mock_squad / ".shipper_offsets.json").write_text("{}\n", encoding="utf-8")
        (mock_squad / "extra.log").write_text("old\n", encoding="utf-8")
        (mock_squad / "standalone.yaml").write_text("stale: true\n", encoding="utf-8")
        (mock_squad / "src").mkdir(parents=True, exist_ok=True)
        (mock_squad / "src" / "keep.py").write_text("# keep\n", encoding="utf-8")

        target_path = self.test_dir / "clean-dest-brain"
        scaffold_brain("clean-dest-brain", target_path, mock_vault, dry_run=False, sa_port=8195, sa_grpc_port=8197, sandbox=True)

        copied_squad = target_path / "08-Squad-Agent"
        self.assertTrue((copied_squad / "src" / "keep.py").is_file())
        self.assertFalse((copied_squad / "logs" / "stale.log").exists())
        self.assertFalse((copied_squad / "data").exists())
        self.assertFalse((copied_squad / ".DS_Store").exists())
        self.assertFalse((copied_squad / ".shipper_offsets.json").exists())
        self.assertFalse((copied_squad / "extra.log").exists())
        self.assertTrue((copied_squad / "standalone.yaml").is_symlink())

    def test_scaffold_brain_fleet_mode_docker(self):
        """Verifies --fleet-mode docker links/bases standalone.yaml on host-bridge.yaml (127.0.0.2)."""
        std_name = "docker-bridge-brain"
        std_path = self.test_dir / std_name
        scaffold_brain(
            std_name,
            std_path,
            self.vault_root,
            dry_run=False,
            sa_port=8215,
            sa_grpc_port=8217,
            sandbox=False,
            fleet_mode="docker",
        )
        std_link = std_path / "standalone.yaml"
        self.assertTrue(std_link.is_symlink())
        self.assertTrue(std_link.exists(), "host-bridge.yaml symlink must resolve cleanly")
        self.assertTrue(
            os.readlink(std_link).endswith("docker-deployment/modes/docker/config/host-bridge.yaml"),
            f"Unexpected docker fleet_mode symlink: {os.readlink(std_link)}",
        )
        self.assertIn("127.0.0.2", std_link.read_text(encoding="utf-8"))

        sb_name = "docker-sandbox-brain"
        sb_path = self.test_dir / sb_name
        scaffold_brain(
            sb_name,
            sb_path,
            self.vault_root,
            dry_run=False,
            sa_port=8225,
            sa_grpc_port=8227,
            sandbox=True,
            fleet_mode="docker",
        )
        sb_yaml = (sb_path / "standalone.yaml").read_text(encoding="utf-8")
        self.assertIn("127.0.0.2", sb_yaml)
        self.assertIn(f"target_brain_id: ${{TARGET_BRAIN_ID:{sb_name}}}", sb_yaml)

    def test_register_workspace_with_rag_posts_and_stays_non_fatal(self):
        """Verifies _register_workspace_with_rag posts workspace payload and never fails when offline."""
        import json
        from unittest.mock import MagicMock, patch
        from src.lifecycle.scaffold_new_brain import _register_workspace_with_rag

        captured = []

        class _FakeResp:
            status = 200
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False

        def _fake_urlopen(req, timeout=2.5):
            captured.append((req.full_url, req.get_method(), json.loads(req.data.decode("utf-8"))))
            return _FakeResp()

        target_path = self.test_dir / "reg-brain"
        mock_logger = MagicMock()
        with patch("src.lifecycle.scaffold_new_brain.urllibUrlopen", side_effect=_fake_urlopen):
            _register_workspace_with_rag("reg-brain", target_path, mock_logger)

        self.assertEqual(len(captured), 1)
        url, method, body = captured[0]
        self.assertTrue(url.endswith(":8093/api/v1/workspaces/register"))
        self.assertEqual(method, "POST")
        self.assertEqual(body["brain_id"], "reg-brain")
        self.assertEqual(body["workspace_path"], str(target_path.parent))
        self.assertEqual(body["vault_path"], str(target_path))
        mock_logger.info.assert_called()

        # Offline RAG Engine must log warning and NOT raise
        mock_logger_offline = MagicMock()
        with patch("src.lifecycle.scaffold_new_brain.urllibUrlopen", side_effect=OSError("Connection refused")):
            _register_workspace_with_rag("reg-brain", target_path, mock_logger_offline)
        mock_logger_offline.warning.assert_called()

    def test_workspace_mode_zero_mixing_and_merged_skills(self):
        """Verifies --workspace creates a clean external domain container with zero 08-Squad-Agent or squad-agent duplication."""
        import json
        import subprocess
        from unittest.mock import patch
        from src.lifecycle.scaffold_new_brain import destroy_sandbox_brain, main as scaffold_brain_main

        target_name = "trading-brain"
        ws_dest = self.test_dir / "My-Trading-Workspace"
        vault_dest = ws_dest / target_name

        # Invoke via CLI main() to verify auto-activation when --dest is outside Bastien-Antigravity and --sandbox is False
        with patch.object(
            sys,
            "argv",
            [
                "scaffold_new_brain.py",
                "--name",
                target_name,
                "--dest",
                str(ws_dest),
                "--fleet-mode",
                "local",
            ],
        ), patch("src.lifecycle.scaffold_new_brain._register_workspace_with_rag"):
            scaffold_brain_main()

        # 1. Root workspace files exist and contain zero cross-workspace symlinks
        for root_file in ("AGENTS.md", "AI-CONTEXT.md", "standalone.yaml", "Makefile", "docker-compose.yaml", "VERSION.txt"):
            p = ws_dest / root_file
            self.assertTrue(p.is_file(), f"Workspace root file missing: {root_file}")
            self.assertFalse(p.is_symlink(), f"Workspace root file must not be a symlink: {root_file}")

        self.assertEqual((ws_dest / "VERSION.txt").read_text(encoding="utf-8").strip(), "0.0.1")

        agents_md = (ws_dest / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("VERSION.txt", agents_md)
        self.assertIn("microservice-toolbox", agents_md)
        self.assertIn("ZERO Mixing", agents_md)

        ai_ctx = (ws_dest / "AI-CONTEXT.md").read_text(encoding="utf-8")
        self.assertIn("@obsidian-brain:orchestrator", ai_ctx)
        self.assertIn("02-Business-BDD/02-Behavior-Specs", ai_ctx)

        # 2. Concrete standalone.yaml seeded with target_brain_id and local 127.0.0.1
        standalone_text = (ws_dest / "standalone.yaml").read_text(encoding="utf-8")
        self.assertIn(f"target_brain_id: ${{TARGET_BRAIN_ID:{target_name}}}", standalone_text)
        self.assertIn(f"brain_id: ${{TARGET_BRAIN_ID:{target_name}}}", standalone_text)
        self.assertIn("127.0.0.1", standalone_text)

        # 3. docker-compose.yaml has ZERO squad-agent and ZERO base L1/L2 containers
        compose_data = yaml.safe_load((ws_dest / "docker-compose.yaml").read_text(encoding="utf-8"))
        self.assertEqual(compose_data.get("services"), {})
        self.assertIn("teleremote-network", compose_data.get("networks", {}))
        self.assertTrue(compose_data["networks"]["teleremote-network"]["external"])

        # 4. Makefile has switch-local / switch-docker / docker-up / docker-down / status and toggles standalone.yaml
        makefile_text = (ws_dest / "Makefile").read_text(encoding="utf-8")
        for target in ("switch-local:", "switch-docker:", "docker-up:", "docker-down:", "status:"):
            self.assertIn(target, makefile_text)

        if shutil.which("make"):
            subprocess.run(["make", "switch-docker"], cwd=str(ws_dest), check=True, capture_output=True)
            self.assertIn("127.0.0.2", (ws_dest / "standalone.yaml").read_text(encoding="utf-8"))
            subprocess.run(["make", "switch-local"], cwd=str(ws_dest), check=True, capture_output=True)
            self.assertIn("127.0.0.1", (ws_dest / "standalone.yaml").read_text(encoding="utf-8"))

        # 5. Pure domain vault: ZERO 08-Squad-Agent, ZERO central Role-Prompts/Tech-Stack copies
        self.assertFalse((ws_dest / "08-Squad-Agent").exists())
        self.assertFalse((vault_dest / "08-Squad-Agent").exists())
        self.assertFalse((vault_dest / "07-Core-KMS" / "Role-Prompts" / "02-Architect").exists())
        self.assertEqual(list((vault_dest / "03-Tech-Stack").iterdir()), [])

        for rel_dir in (
            "00-AI-Orchestration/Config",
            "01-Strategic-Nexus",
            "02-Business-BDD/02-Behavior-Specs",
            "03-Tech-Stack",
            "04-Rapid-Prototyping/Inbox",
            "05-Fleet-Operation/00-Repo-Control",
            "06-Microservices",
            "11-Code-Doc",
        ):
            self.assertTrue((vault_dest / rel_dir).is_dir(), f"Missing domain vault folder: {rel_dir}")

        domain_prompt = vault_dest / "07-Core-KMS/Role-Prompts/20-DomainSpecialist/Prompt-DomainSpecialist.md"
        self.assertTrue(domain_prompt.is_file())
        self.assertIn("@obsidian-brain:orchestrator", domain_prompt.read_text(encoding="utf-8"))

        inv_data = json.loads((vault_dest / "05-Fleet-Operation/00-Repo-Control/inventory.json").read_text(encoding="utf-8"))
        self.assertTrue(inv_data.get("domain_workspace"))
        self.assertEqual(inv_data.get("repositories"), [])
        reg_data = json.loads((vault_dest / "05-Fleet-Operation/00-Repo-Control/service-registry.json").read_text(encoding="utf-8"))
        self.assertEqual(reg_data.get("services"), [])

        # 6. Merged .agents/skills/ contains BOTH central engineering skills and domain skills
        skills_dir = ws_dest / ".agents" / "skills"
        self.assertTrue((skills_dir / "domainspecialist" / "SKILL.md").is_file())
        for core_skill in ("architect", "developer", "orchestrator", "qa", "pythonspecialist", "gospecialist"):
            self.assertTrue((skills_dir / core_skill / "SKILL.md").is_file(), f"Missing merged core skill: {core_skill}")

        # 7. Clean teardown removes workspace container safely without touching Bastien-Antigravity
        self.assertFalse(destroy_sandbox_brain("Bastien-Antigravity", self.vault_root.parent, self.vault_root, dry_run=False))
        self.assertTrue(destroy_sandbox_brain(target_name, ws_dest, self.vault_root, dry_run=False))
        self.assertFalse(ws_dest.exists())

    def test_convert_agents_external_brain_merge_and_protection(self):
        """Verifies convert_agents supports arbitrary domain personas, --merge-core, --out, and core protection."""
        from src.fleet.convert_agents import compile_skills

        ext_ws = self.test_dir / "Ext-Domain-WS"
        ext_brain = ext_ws / "quant-brain"
        custom_prompt_dir = ext_brain / "07-Core-KMS" / "Role-Prompts" / "20-TradingStrategist"
        custom_prompt_dir.mkdir(parents=True, exist_ok=True)
        (custom_prompt_dir / "Prompt-TradingStrategist.md").write_text(
            "# Trading Strategist\nDesign alpha strategies.\n",
            encoding="utf-8",
        )

        out_skills = ext_ws / ".agents" / "skills"
        written = compile_skills(
            brain_dir=str(ext_brain),
            merge_core=True,
            out_dir=str(out_skills),
            skip_workspace_link=True,
        )
        self.assertIn("tradingstrategist", written)
        self.assertIn("architect", written)
        self.assertTrue((out_skills / "tradingstrategist" / "SKILL.md").is_file())
        self.assertIn("Design alpha strategies.", (out_skills / "tradingstrategist" / "SKILL.md").read_text(encoding="utf-8"))

        # Safety guard: refusing to overwrite core Bastien-Antigravity/.agents/skills when external --brain is passed
        core_ws_skills = self.vault_root.parent / ".agents" / "skills"
        with self.assertRaises(ValueError):
            compile_skills(
                brain_dir=str(ext_brain),
                merge_core=True,
                out_dir=str(core_ws_skills),
                skip_workspace_link=True,
            )


if __name__ == "__main__":
    unittest.main()
