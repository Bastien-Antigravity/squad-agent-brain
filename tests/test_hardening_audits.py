#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Unit tests for P0 & P1 ecosystem hardening audits across validate_compliance,
audit_ports, fleet_version, and fleet_commander.

DATA FLOW:
1. Synthesizes isolated temporary source files, YAML port configs, and Git repos.
2. Executes ComplianceAuditor, audit_ports, fleet_version, and FleetCommander checks.
3. Asserts exact violation rules, collision/drift detection, and fail-fast guards.

KEY PARAMETERS:
- SQUAD_AGENT_DIR: Root path to 08-Squad-Agent.
"""

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

SQUAD_AGENT_DIR = Path(__file__).resolve().parent.parent
if str(SQUAD_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(SQUAD_AGENT_DIR))

from src.auditing.audit_ports import audit_ports
from src.auditing.validate_compliance import ComplianceAuditor
from src.fleet.fleet_commander import FleetCommander
from src.fleet.fleet_version import get_repo_git_tag, inspect_repo_version

# -----------------------------------------------------------------------------------------------


class TestHardeningAudits(unittest.TestCase):
    """Test suite for P0/P1 ecosystem hardening rules and guards."""

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="test_hardening_"))
        self.auditor = ComplianceAuditor(workspace_root=SQUAD_AGENT_DIR.parent)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    # -------------------------------------------------------------------------------------------

    def test_dockerenv_prohibited_flags_code_and_ignores_comments_and_env_var(self):
        """Rule A: flags /.dockerenv in code, allows comments/docstrings and DOCKER_ENV == 'true'."""
        bad_py = self.test_dir / "bad_dockerenv.py"
        bad_py.write_text(
            '#!/usr/bin/env python\n'
            '# coding:utf-8\n\n'
            '"""\nESSENTIAL PROCESS:\nCheck container.\n\nDATA FLOW:\n1. Check.\n\nKEY PARAMETERS:\n- None.\n"""\n\n'
            'from os.path import exists as osPathExists\n\n'
            '# -----------------------------------------------------------------------------------------------\n\n'
            'def in_docker() -> bool:\n'
            '    return osPathExists("/.dockerenv")\n',
            encoding="utf-8",
        )
        violations = self.auditor.audit_file(bad_py)
        rules = [v["rule"] for v in violations]
        self.assertIn("DOCKERENV_PROHIBITED", rules)

        bad_go = self.test_dir / "bad_dockerenv.go"
        bad_go.write_text(
            '// ESSENTIAL PROCESS: Check.\n// DATA FLOW: 1. Check.\n// KEY PARAMETERS: None.\n\n'
            'package main\n\nimport "os"\n\n'
            '// -----------------------------------------------------------------------------\n\n'
            'func inDocker() bool {\n'
            '    _, err := os.Stat("/.dockerenv")\n'
            '    return err == nil\n'
            '}\n',
            encoding="utf-8",
        )
        go_rules = [v["rule"] for v in self.auditor.audit_file(bad_go)]
        self.assertIn("DOCKERENV_PROHIBITED", go_rules)

        bad_sh = self.test_dir / "entrypoint.sh"
        bad_sh.write_text("#!/bin/sh\nif [ -f /.dockerenv ]; then echo yes; fi\n", encoding="utf-8")
        sh_rules = [v["rule"] for v in self.auditor.audit_file(bad_sh)]
        self.assertIn("DOCKERENV_PROHIBITED", sh_rules)

        clean_py = self.test_dir / "clean_dockerenv.py"
        clean_py.write_text(
            '#!/usr/bin/env python\n'
            '# coding:utf-8\n\n'
            '"""\nESSENTIAL PROCESS:\nNever probe /.dockerenv in docstrings.\n\n'
            'DATA FLOW:\n1. Check DOCKER_ENV.\n\nKEY PARAMETERS:\n- None.\n"""\n\n'
            'from os import getenv as osGetenv\n\n'
            '# -----------------------------------------------------------------------------------------------\n\n'
            'def in_docker() -> bool:\n'
            '    # Do not check /.dockerenv; use DOCKER_ENV instead.\n'
            '    return osGetenv("DOCKER_ENV") == "true"\n',
            encoding="utf-8",
        )
        clean_violations = self.auditor.audit_file(clean_py, strict_imports=True)
        self.assertEqual(clean_violations, [])

    # -------------------------------------------------------------------------------------------

    def test_cross_os_top_level_import_flags_unconditional_and_allows_lazy(self):
        """Rule B: flags top-level platform-exclusive imports, allows guarded/lazy imports."""
        bad_py = self.test_dir / "bad_os_import.py"
        bad_py.write_text(
            '#!/usr/bin/env python\n'
            '# coding:utf-8\n\n'
            '"""\nESSENTIAL PROCESS:\nPlatform import.\n\nDATA FLOW:\n1. Open.\n\nKEY PARAMETERS:\n- None.\n"""\n\n'
            'import winreg\n'
            'from os import startfile as osStartfile\n\n'
            '# -----------------------------------------------------------------------------------------------\n\n'
            'def launch():\n'
            '    return winreg, osStartfile\n',
            encoding="utf-8",
        )
        violations = self.auditor.audit_file(bad_py)
        cross_os = [v for v in violations if v["rule"] == "CROSS_OS_TOP_LEVEL_IMPORT"]
        self.assertEqual(len(cross_os), 2)

        good_py = self.test_dir / "good_os_import.py"
        good_py.write_text(
            '#!/usr/bin/env python\n'
            '# coding:utf-8\n\n'
            '"""\nESSENTIAL PROCESS:\nGuarded platform import.\n\nDATA FLOW:\n1. Open.\n\nKEY PARAMETERS:\n- None.\n"""\n\n'
            'from sys import platform as sysPlatform\n\n'
            'if sysPlatform == "win32":\n'
            '    import winreg\n\n'
            '# -----------------------------------------------------------------------------------------------\n\n'
            'def open_file(path: str) -> None:\n'
            '    if sysPlatform == "win32":\n'
            '        from os import startfile as osStartfile\n'
            '        osStartfile(path)\n',
            encoding="utf-8",
        )
        clean_violations = self.auditor.audit_file(good_py, strict_imports=True)
        self.assertEqual(clean_violations, [])

    # -------------------------------------------------------------------------------------------

    def _build_port_fixture(self) -> tuple[Path, Path]:
        ws = self.test_dir / "workspace"
        vault = ws / "obsidian-brain"
        (ws / "docker-deployment" / "modes" / "local" / "config").mkdir(parents=True)
        (ws / "docker-deployment" / "modes" / "docker" / "config" / "services").mkdir(parents=True)
        (ws / "docker-deployment" / "modes" / "production" / "config" / "services").mkdir(parents=True)
        (vault / "05-Fleet-Operation" / "00-Repo-Control").mkdir(parents=True)

        native_yaml = (
            "capabilities:\n"
            "  config_server:\n    port: \"${CF_PORT:3306}\"\n    grpc_port: \"${CF_GRPC_PORT:3307}\"\n    rest_port: \"${CF_REST_PORT:3308}\"\n"
            "  log_server:\n    port: \"${LS_PORT:9020}\"\n    grpc_port: \"${LS_GRPC_PORT:9021}\"\n"
            "  notif_server:\n    port: \"${NT_PORT:1026}\"\n    grpc_port: \"${NT_GRPC_PORT:1027}\"\n    rest_port: \"${NT_REST_PORT:1029}\"\n"
            "  tele_remote:\n    port: \"${TR_PORT:1863}\"\n"
            "  web_interface:\n    port: \"${WB_PORT:5000}\"\n    grpc_port: \"${WB_GRPC_PORT:8001}\"\n"
            "  watchdog_agent:\n    port: \"${WD_PORT:9090}\"\n    rest_port: \"${WD_REST_PORT:9095}\"\n"
            "  nats:\n    port: \"${NATS_PORT:4222}\"\n"
            "  timescale_db:\n    port: \"${TS_PORT:5432}\"\n"
            "  rag_engine:\n    port: ${RG_PORT:8090}\n    grpc_port: ${RG_GRPC_PORT:8091}\n    rest_port: ${RG_REST_PORT:8093}\n"
            "    mcp:\n      port: ${RG_MCP_PORT:8090}\n    dashboard:\n      port: ${DASHBOARD_PORT:8082}\n"
        )
        (ws / "docker-deployment" / "modes" / "local" / "config" / "native.yaml").write_text(native_yaml, encoding="utf-8")
        (ws / "docker-deployment" / "modes" / "docker" / "config" / "host-bridge.yaml").write_text(native_yaml, encoding="utf-8")

        compose_yaml = (
            "services:\n"
            "  config-server:\n    ports: [\"127.0.0.2:3306:3306\"]\n"
            "  log-server:\n    ports: [\"127.0.0.2:9020:9020\"]\n"
            "  notif-server:\n    ports: [\"127.0.0.2:1026:1026\"]\n"
            "  tele-remote:\n    ports: [\"127.0.0.2:1863:1863\"]\n"
            "  web-interface:\n    ports: [\"127.0.0.2:5000:5000\"]\n"
            "  nats-server:\n    ports: [\"127.0.0.2:4222:4222\"]\n"
            "  timescale-db:\n    ports: [\"127.0.0.2:5432:5432\"]\n"
            "  rag-engine:\n    ports: [\"127.0.0.2:8090:8090\"]\n"
        )
        (ws / "docker-deployment" / "docker-compose.yaml").write_text(compose_yaml, encoding="utf-8")
        (ws / "docker-deployment" / "modes" / "docker" / "docker-compose.yaml").write_text(compose_yaml, encoding="utf-8")

        registry = {
            "services": {
                "infrastructure": [
                    {"name": "timescale-db", "default_port": 5432},
                    {"name": "nats-server", "default_port": 4222},
                ],
                "application": [
                    {"name": "config-server", "default_port": 3306, "grpc_port": 3307, "rest_port": 3308},
                    {"name": "log-server", "default_port": 9020, "grpc_port": 9021},
                    {"name": "notif-server", "default_port": 1026, "grpc_port": 1027, "rest_port": 1029},
                    {"name": "tele-remote", "default_port": 1863},
                    {"name": "watchdog-agent", "default_port": 9095, "rest_port": 9095},
                    {"name": "rag-engine", "default_port": 8090, "grpc_port": 8091, "rest_port": 8093},
                    {"name": "web-interface", "default_port": 5000, "grpc_port": 8001},
                ],
            }
        }
        (vault / "05-Fleet-Operation" / "00-Repo-Control" / "service-registry.json").write_text(
            json.dumps(registry, indent=2), encoding="utf-8"
        )
        return ws, vault

    def test_audit_ports_catches_intra_service_collision_and_multi_mode_drift(self):
        """audit_ports detects intra-service duplicate ports and multi-mode YAML/compose drift."""
        ws, vault = self._build_port_fixture()
        status, msgs = audit_ports(auto_sync=False, workspace_root=ws, vault_root=vault)
        self.assertEqual(status, "GREEN", f"Expected GREEN, got {status}: {msgs}")

        # 1. Inject intra-service collision in docker service slice (port: 1863 + grpc_port: 1863)
        tele_slice = ws / "docker-deployment" / "modes" / "docker" / "config" / "services" / "tele-remote.yaml"
        tele_slice.write_text(
            "capabilities:\n  tele_remote:\n    port: \"${TR_PORT:-1863}\"\n    grpc_port: \"${TR_GRPC_PORT:-1863}\"\n",
            encoding="utf-8",
        )
        status, msgs = audit_ports(auto_sync=False, workspace_root=ws, vault_root=vault)
        self.assertEqual(status, "RED")
        self.assertTrue(any("COLLISION:" in m and "tele_remote" in m and "1863" in m for m in msgs), msgs)

        # 2. Fix collision, inject cross-file drift in production service slice
        tele_slice.write_text("capabilities:\n  tele_remote:\n    port: \"${TR_PORT:-1863}\"\n", encoding="utf-8")
        prod_slice = ws / "docker-deployment" / "modes" / "production" / "config" / "services" / "notif-server.yaml"
        prod_slice.write_text(
            "capabilities:\n  notif_server:\n    port: \"${NT_PORT:-1999}\"\n    grpc_port: \"${NT_GRPC_PORT:-1027}\"\n",
            encoding="utf-8",
        )
        status, msgs = audit_ports(auto_sync=False, workspace_root=ws, vault_root=vault)
        self.assertEqual(status, "RED")
        self.assertTrue(any("DRIFT:" in m and "production/config/services/notif-server.yaml" in m for m in msgs), msgs)

    # -------------------------------------------------------------------------------------------

    def test_fleet_version_ignores_restore_tags_and_flags_tag_drift(self):
        """fleet_version ignores restore/* tags via --match 'v*' and reports TAG_DRIFT."""
        repo = self.test_dir / "sample-repo"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "ci@test.local"], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "CI"], cwd=repo, check=True, capture_output=True)

        (repo / "VERSION.txt").write_text("0.0.1\n", encoding="utf-8")
        subprocess.run(["git", "add", "VERSION.txt"], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "tag", "-a", "v0.0.1", "-m", "Release v0.0.1"], cwd=repo, check=True, capture_output=True)

        # Create a newer restore/* tag that previously shadowed v0.0.1
        (repo / "README.md").write_text("hello\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "docs"], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "tag", "restore/pre-hardening-2026-11-20"], cwd=repo, check=True, capture_output=True)

        self.assertEqual(get_repo_git_tag(repo), "v0.0.1")
        info = inspect_repo_version(repo)
        self.assertEqual(info["status"], "OK")
        self.assertEqual(info["git_tag"], "v0.0.1")

        # Now add a phantom semver tag v1.9.922 while VERSION.txt stays 0.0.1
        subprocess.run(["git", "tag", "-a", "v1.9.922", "-m", "Phantom"], cwd=repo, check=True, capture_output=True)
        drifted = inspect_repo_version(repo)
        self.assertEqual(drifted["git_tag"], "v1.9.922")
        self.assertEqual(drifted["status"], "TAG_DRIFT")
        self.assertIn("TAG_DRIFT", drifted["warning"] or "")

    # -------------------------------------------------------------------------------------------

    def test_fleet_commander_rejects_mismatched_tag_against_version_txt(self):
        """FleetCommander.execute_fleet_push fails fast when --tag != v<VERSION.txt>."""
        ws = self.test_dir / "fleet_ws"
        repo_a = ws / "repo-a"
        repo_a.mkdir(parents=True)
        (repo_a / "VERSION.txt").write_text("0.0.1\n", encoding="utf-8")

        with unittest.mock.patch.object(FleetCommander, "_load_inventory", return_value=["repo-a"]):
            cmdr = FleetCommander(str(ws), dry_run=True, target_repo="repo-a", tag="v1.9.922")
            recorded = []
            cmdr._run_command = lambda cmd, cwd: (recorded.append(cmd) or "", None)

            with self.assertRaises(ValueError) as ctx:
                cmdr.execute_fleet_push()
            self.assertIn("v1.9.922", str(ctx.exception))
            self.assertIn("v0.0.1", str(ctx.exception))
            self.assertEqual(recorded, [])

            # Matching tag succeeds in dry_run
            cmdr_ok = FleetCommander(str(ws), dry_run=True, target_repo="repo-a", tag="v0.0.1")
            cmdr_ok._run_command = lambda cmd, cwd: ("develop", None)
            cmdr_ok.audit_docs = lambda p, n: True
            cmdr_ok.validate_architecture = lambda p, n: True
            cmdr_ok.audit_isolation_zone = lambda p, n: True
            cmdr_ok.execute_fleet_push()

            # Explicit override allows mismatch
            cmdr_override = FleetCommander(
                str(ws), dry_run=True, target_repo="repo-a", tag="v1.9.922", allow_tag_mismatch=True
            )
            cmdr_override._run_command = lambda cmd, cwd: ("develop", None)
            cmdr_override.audit_docs = lambda p, n: True
            cmdr_override.validate_architecture = lambda p, n: True
            cmdr_override.audit_isolation_zone = lambda p, n: True
            cmdr_override.execute_fleet_push()


if __name__ == "__main__":
    unittest.main()
