#!/usr/bin/env python
# coding:utf-8

import asyncio
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

_self_dir = Path(__file__).resolve().parent.parent
if str(_self_dir) not in sys.path:
    sys.path.insert(0, str(_self_dir))

import src.bootstrap  # noqa: F401
from src.agents.developer import DeveloperAgent
from src.auditing.validate_compliance import CANONICAL_PORTS, ComplianceAuditor, load_canonical_ports_from_ssot
from src.interfaces import EventDeduplicator, LocalEventBus
from src.models.build_spec import MicroserviceBuildSpec


class TestEcosystemGovernanceCoherence(unittest.IsolatedAsyncioTestCase):
    """Meta-governance CI suite preventing rule drift, RAG blindness, port collisions, and routing bugs."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.squad_root = _self_dir
        cls.vault_root = cls.squad_root.parent
        cls.workspace_root = cls.vault_root.parent

    def setUp(self) -> None:
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="gov_coherence_"))
        LocalEventBus._subscribers = None
        EventDeduplicator._seen = set()
        EventDeduplicator._seen_list = []

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_zero_misplaced_ai_ignore_tags_in_active_knowledge(self) -> None:
        """Active vault rules, protocols, hubs, and prompts must NEVER carry #ai/ignore."""
        active_targets = [
            self.vault_root / "AGENTS.md",
            self.vault_root / "README.md",
            self.vault_root / "08-Squad-Agent" / "README.md",
            self.vault_root / "00-AI-Orchestration",
            self.vault_root / "02-Business-BDD",
            self.vault_root / "03-Tech-Stack",
            self.vault_root / "06-Microservices",
            self.vault_root / "07-Core-KMS",
        ]
        offenders = []
        for target in active_targets:
            files = [target] if target.is_file() else list(target.rglob("*.md"))
            for md_file in files:
                rel_parts = md_file.relative_to(self.vault_root).parts
                if "quick-overview" in rel_parts or "99-Humans" in rel_parts or "archive" in rel_parts:
                    continue
                head = md_file.read_text(encoding="utf-8", errors="ignore")[:1200]
                if head.startswith("---") and "#ai/ignore" in head.split("---", 2)[1]:
                    offenders.append(str(md_file.relative_to(self.vault_root)))
        self.assertEqual(offenders, [], f"Found #ai/ignore blinding active vault knowledge: {offenders}")

    def test_port_allocation_matrix_ssot_parity(self) -> None:
        """native.yaml, AI-CONTEXT.md, and CANONICAL_PORTS must stay 100% synchronized without phantom 8080."""
        native_yaml = (self.workspace_root / "docker-deployment" / "modes" / "local" / "config" / "native.yaml").read_text(
            encoding="utf-8"
        )
        ai_context = (self.workspace_root / "AI-CONTEXT.md").read_text(encoding="utf-8")

        yaml_ports = set()
        for m in re.findall(r"(?:port|rest_port|grpc_port|http_port)\s*:\s*[\"']?\$\{[A-Z0-9_]+:(\d+)\}", native_yaml):
            yaml_ports.add(m)

        for p in yaml_ports:
            self.assertIn(p, CANONICAL_PORTS, f"Port {p} in native.yaml missing from CANONICAL_PORTS")
        self.assertNotIn("**8080**", ai_context, "Phantom port 8080 must not reappear in AI-CONTEXT.md")
        self.assertIn("**8093**", ai_context)

    def test_all_23_compiled_runtime_skills_coherent(self) -> None:
        """All 23 compiled SKILL.md personas must match 07-Core-KMS Role-Prompts."""
        proc = subprocess.run(
            [sys.executable, str(self.squad_root / "main.py"), "check-coherence"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(proc.returncode, 0, f"check-coherence failed:\n{proc.stdout}\n{proc.stderr}")

    def test_canonical_rule_alignment_across_docs(self) -> None:
        """AGENTS.md, Global-Architecture-Rules.md, and Naming Conventions must agree on zero M/I Hungarian prefixes & Python f-strings."""
        root_agents = (self.workspace_root / "AGENTS.md").read_text(encoding="utf-8")
        global_rules = (
            self.vault_root / "03-Tech-Stack" / "02-Project-Architecture" / "Global-Architecture-Rules.md"
        ).read_text(encoding="utf-8")
        naming_rules = (
            self.vault_root / "03-Tech-Stack" / "03-Project-Coding" / "01-General-Naming-Conventions.md"
        ).read_text(encoding="utf-8")

        self.assertIn('self.logger.info(f"{self.Name} : {msg}")', root_agents)
        self.assertIn("no `M` or `I` prefixes", root_agents)
        self.assertIn("NO `M` or `I` Hungarian prefixes", global_rules)
        self.assertIn("MUST NOT use `I`- or `M`-prefixes", naming_rules)
        self.assertNotIn("ProcessController", global_rules)
        self.assertEqual(load_canonical_ports_from_ssot(self.workspace_root), CANONICAL_PORTS)

    async def test_explicit_role_mention_does_not_double_dispatch_orchestrator(self) -> None:
        """Addressing @developer directly from user must NOT simultaneously wake @orchestrator."""
        dev_msgs = []
        orch_msgs = []

        async def dev_cb(payload):
            dev_msgs.append(payload)

        async def orch_cb(payload):
            orch_msgs.append(payload)

        LocalEventBus.subscribe("bastien-antigravity.squad.chat", dev_cb, role="developer")
        LocalEventBus.subscribe("bastien-antigravity.squad.chat", orch_cb, role="orchestrator")

        LocalEventBus.publish(
            "bastien-antigravity.squad.chat",
            {"event_id": "evt-direct-dev", "sender": "user", "content": "@developer implement order-router"},
        )
        await asyncio.sleep(0.01)

        self.assertEqual(len(dev_msgs), 1)
        self.assertEqual(len(orch_msgs), 0, "Orchestrator must NOT double-fire when user explicitly tags @developer")

    def test_cross_brain_build_spec_and_port_allocator(self) -> None:
        """MicroserviceBuildSpec validates strictly, blocks canonical port collisions, and allocates free domain ports."""
        ext_ws = self.tmp_dir / "Alpha-Antigravity"
        ext_ws.mkdir(parents=True)
        (ext_ws / "standalone.yaml").write_text(
            'capabilities:\n  existing_svc:\n    ip: 127.0.0.1\n    port: "${EXISTING_PORT:18100}"\n',
            encoding="utf-8",
        )

        # Collision with canonical port 5000 must fail fast
        bad_spec = MicroserviceBuildSpec(service_name="alpha-feed", lang="go", layer="L3", port=5000)
        with self.assertRaises(ValueError):
            bad_spec.resolve_port(workspace_root=self.workspace_root)

        # Auto-allocation skips 18100 (already in ext_ws/standalone.yaml) and picks 18101
        spec = MicroserviceBuildSpec.from_dict(
            {
                "service_name": "alpha-feed",
                "lang": "rust",
                "layer": "L3",
                "brain_id": "alpha-brain",
                "workspace_path": str(ext_ws),
                "port": 0,
                "description": "Low-latency market feed normalizer",
            }
        )
        allocated = spec.resolve_port(workspace_root=self.workspace_root)
        self.assertEqual(allocated, 18101)

        # build_spec.py and trace.py must pass strict ComplianceAuditor with 0 violations
        auditor = ComplianceAuditor(workspace_root=self.workspace_root)
        for checked_file in (
            self.squad_root / "src" / "models" / "build_spec.py",
            self.workspace_root / "microservice-toolbox" / "python" / "microservice_toolbox" / "trace.py",
        ):
            violations = auditor.audit_path(
                checked_file,
                strict_imports=True,
                strict_lean=True,
            )
            self.assertEqual(violations, [], auditor.format_report(violations))

    async def test_base_agent_contextvar_isolation_and_fail_fast_guard(self) -> None:
        """Concurrent async sessions on BaseAgent must isolate task_context via ContextVar and block invalid workspaces."""
        mock_cfg = MagicMock()
        mock_cfg.data = {}
        dev = DeveloperAgent(config=mock_cfg, logger=MagicMock(), pg_pool=None, event_bus=MagicMock())

        observed = {}

        async def run_session(label: str, brain: str) -> None:
            dev.current_task_context = {"target_brain_id": brain}
            await asyncio.sleep(0.02)
            observed[label] = dev.current_task_context["target_brain_id"]

        await asyncio.gather(
            run_session("s1", "trading-brain"),
            run_session("s2", "analytics-brain"),
        )
        self.assertEqual(observed, {"s1": "trading-brain", "s2": "analytics-brain"})

        # Invalid unregistered target_workspace_path must fail fast on read_workspace_file too
        dev.current_task_context = {"target_workspace_path": "/nonexistent-unregistered-domain-ws"}
        res = await dev.execute_tool("read_workspace_file", {"path": "AGENTS.md"})
        self.assertIn("Fail-Fast Workspace Guard", res)

    def test_developer_agent_dynamic_language_scoped_specialist_loading(self) -> None:
        """DeveloperAgent scopes specialist prompts to the active mission language instead of dumping all 7 languages."""
        mock_cfg = MagicMock()
        mock_cfg.data = {}
        mock_logger = MagicMock()
        mock_bus = MagicMock()

        dev = DeveloperAgent(config=mock_cfg, logger=mock_logger, pg_pool=None, event_bus=mock_bus)
        dev.current_task_context = {
            "target_brain_id": "alpha-brain",
            "lang": "rust",
            "expose_openmfe": False,
            "use_timescale": False,
        }
        compiled = dev._compile_active_instruction()
        self.assertIn("Rust", compiled)
        self.assertNotIn("Excel-VBA", compiled)


if __name__ == "__main__":
    unittest.main()
