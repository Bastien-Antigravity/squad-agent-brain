#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Unit and integration tests for cross-brain domain-specialized agent discovery,
tiered prompt inheritance, bounded task_context BDD handoffs to central Squad-Agent,
workspace-scoped DeveloperAgent tooling with ComplianceAuditor, and SSRF-safe QAAgent probing.
"""

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

SQUAD_DIR = Path(__file__).resolve().parent.parent
TOOLBOX_PY_DIR = SQUAD_DIR.parent.parent / "microservice-toolbox" / "python"
for candidate in (str(TOOLBOX_PY_DIR), str(SQUAD_DIR)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

import os
import src.bootstrap as bootstrap
from src.agents.base_agent import BaseAgent
from src.agents.developer import DeveloperAgent
from src.agents.orchestrator import OrchestratorAgent
from src.agents.qa import QAAgent
from src.core.agent_dispatcher import discover_vault_roles, route_task_semantically
from src.core.controller import CommandController
from src.core.start_squad import discover_domain_agents


def _make_mock_config(brain_id: str = "obsidian-brain") -> MagicMock:
    cfg = MagicMock()
    cfg.data = {
        "capabilities": {
            "squad_agent": {
                "target_brain_id": brain_id,
                "gemini_model": "gemini-3.8-flash",
            },
        }
    }
    cfg.get_capability.return_value = cfg.data["capabilities"]["squad_agent"]
    cfg.get_version.return_value = "0.0.1"
    return cfg


class _FakeSquadBus:
    def __init__(self) -> None:
        self.published = []
        self.subscriptions = []

    async def connect(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def subscribe(self, topic: str, callback, role=None) -> None:
        self.subscriptions.append((topic, role, callback))

    async def publish(self, topic: str, payload: dict) -> None:
        self.published.append((topic, payload))


class TestCrossBrainBDDHandoff(unittest.IsolatedAsyncioTestCase):
    def test_discover_domain_agents_from_extra_workspaces_and_yaml(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            central_vault = root / "central-obsidian-brain"
            central_ws = root
            (central_vault / "09-RAG-Engine").mkdir(parents=True)

            # Domain 1 via EXTRA_WORKSPACES_DIR
            extra_dir = root / "workspaces"
            trading_ws = extra_dir / "trading-brain"
            trading_prompts = trading_ws / "07-Core-KMS" / "Role-Prompts" / "01-TradingStrategist"
            trading_prompts.mkdir(parents=True)
            (trading_prompts / "Prompt-TradingStrategist.md").write_text(
                "You are TradingStrategist for alpha strategy specs.", encoding="utf-8"
            )
            (trading_ws / "00-AI-Orchestration").mkdir(parents=True)

            # Domain 2 via colon-separated EXTRA_WORKSPACES
            macro_ws = root / "macro-brain"
            macro_prompts = macro_ws / "07-Core-KMS" / "Role-Prompts" / "02-MacroEconomyAnalyst"
            macro_prompts.mkdir(parents=True)
            (macro_prompts / "Prompt-MacroEconomyAnalyst.md").write_text(
                "You are MacroEconomyAnalyst.", encoding="utf-8"
            )

            # Domain 3 via central_vault/09-RAG-Engine/workspaces.yaml
            risk_ws = root / "risk-ws"
            risk_vault = risk_ws / "risk-brain"
            risk_prompts = risk_vault / "07-Core-KMS" / "Role-Prompts" / "03-RiskOfficer"
            risk_prompts.mkdir(parents=True)
            (risk_prompts / "Prompt-RiskOfficer.md").write_text(
                "You are RiskOfficer.", encoding="utf-8"
            )
            (risk_vault / "00-AI-Orchestration").mkdir(parents=True)
            (central_vault / "09-RAG-Engine" / "workspaces.yaml").write_text(
                f"workspaces:\n  - brain_id: risk-brain\n    workspace_path: {risk_ws}\n    vault_path: {risk_vault}\n",
                encoding="utf-8",
            )

            bus = _FakeSquadBus()
            logger = MagicMock()
            cfg = _make_mock_config()

            with patch.dict(
                os.environ,
                {
                    "EXTRA_WORKSPACES_DIR": str(extra_dir),
                    "EXTRA_WORKSPACES": f"macro-brain={macro_ws}:",
                },
                clear=False,
            ):
                agents = discover_domain_agents(
                    bus=bus,
                    logger=logger,
                    central_vault_root=central_vault,
                    central_workspace_root=central_ws,
                    config=cfg,
                    pg_pool=None,
                )

            by_role = {a.role_name: a for a in agents}
            self.assertIn("tradingstrategist", by_role)
            self.assertIn("macroeconomyanalyst", by_role)
            self.assertIn("riskofficer", by_role)

            ts_agent = by_role["tradingstrategist"]
            self.assertEqual(ts_agent.target_brain_id, "trading-brain")
            self.assertEqual(ts_agent.domain_vault_root, trading_ws.resolve())
            self.assertEqual(ts_agent.domain_workspace_root, trading_ws.resolve())
            self.assertEqual(ts_agent.squad_chat_topic, "bastien-antigravity.trading-brain.squad.chat")

            # Verify agent_dispatcher dynamic vault role lookup & semantic routing
            vault_roles = discover_vault_roles(trading_ws)
            self.assertIn("tradingstrategist", vault_roles)
            routed_declared = route_task_semantically(
                "Design seasonal BTC allocation strategy",
                "TradingStrategist",
                vault_root=trading_ws,
            )
            self.assertEqual(routed_declared, "tradingstrategist")
            routed_no_keywords = route_task_semantically(
                "Evaluate portfolio rebalance",
                "tradingstrategist",
                vault_root=trading_ws,
            )
            self.assertEqual(routed_no_keywords, "tradingstrategist")
            routed_mentioned = route_task_semantically(
                "Ask @tradingstrategist to review allocation",
                None,
                vault_root=trading_ws,
            )
            self.assertEqual(routed_mentioned, "tradingstrategist")

    def test_tiered_prompt_inheritance_merges_domain_and_central_agents_md(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            domain_ws = Path(tmpdir) / "trading-ws"
            domain_vault = domain_ws / "trading-brain"
            prompt_dir = domain_vault / "07-Core-KMS" / "Role-Prompts" / "01-TradingStrategist"
            prompt_dir.mkdir(parents=True)
            (prompt_dir / "Prompt-TradingStrategist.md").write_text(
                "DOMAIN_PERSONA: TradingStrategist Alpha Spec Writer",
                encoding="utf-8",
            )
            (domain_ws / "AGENTS.md").write_text(
                "DOMAIN_RULE: All alpha strategies require Sharpe >= 1.5.",
                encoding="utf-8",
            )

            agent = BaseAgent(
                role_name="tradingstrategist",
                prompt_file="01-TradingStrategist/Prompt-TradingStrategist.md",
                config=_make_mock_config("trading-brain"),
                logger=MagicMock(),
                pg_pool=None,
                event_bus=_FakeSquadBus(),
                target_brain_id="trading-brain",
                domain_vault_root=domain_vault,
                domain_workspace_root=domain_ws,
            )

            self.assertIn("DOMAIN_PERSONA: TradingStrategist Alpha Spec Writer", agent.system_instruction)
            self.assertIn("Non-Negotiable Engineering Invariants", agent.system_instruction)
            self.assertIn("DOMAIN_RULE: All alpha strategies require Sharpe >= 1.5.", agent.system_instruction)

    async def test_orchestrator_accepts_bounded_task_context_handoff_and_forwards_to_dev_and_qa(self):
        bus = _FakeSquadBus()
        logger = MagicMock()
        cfg = _make_mock_config("obsidian-brain")
        orch = OrchestratorAgent(config=cfg, logger=logger, pg_pool=None, event_bus=bus)
        orch.client = None  # Force deterministic offline delegation path

        with tempfile.TemporaryDirectory() as tmpdir:
            ext_ws = Path(tmpdir) / "trading-ws"
            ext_ws.mkdir(parents=True)

            base_ctx = {
                "target_brain_id": "trading-brain",
                "target_workspace_path": str(ext_ws),
                "target_vault_path": str(ext_ws / "trading-brain"),
                "target_repo_path": str(ext_ws / "alpha-executor"),
                "bdd_spec_path": "02-Business-BDD/02-Behavior-Specs/alpha-executor/FEAT-001.md",
                "fleet_mode": "docker",
                "handoff_hops": 0,
            }

            # 1. Accepted when sender != "user" AND task_context present AND handoff_hops < 3
            await orch.on_chat_message({
                "sender": "tradingstrategist",
                "session_id": "sess-bdd-1",
                "content": "@obsidian-brain:orchestrator Implement FEAT-001 in alpha-executor.",
                "source_brain_id": "trading-brain",
                "reply_topic": "bastien-antigravity.squad.chat",
                "task_context": dict(base_ctx),
            })

            self.assertEqual(len(bus.published), 1)
            pub_topic, pub_payload = bus.published[0]
            self.assertEqual(pub_topic, "bastien-antigravity.squad.chat")
            self.assertIn("@developer", pub_payload["content"])
            self.assertIn("@qa", pub_payload["content"])
            self.assertEqual(pub_payload["task_context"]["target_brain_id"], "trading-brain")
            self.assertEqual(pub_payload["task_context"]["fleet_mode"], "docker")
            self.assertEqual(pub_payload["task_context"]["handoff_hops"], 1)

            # 2. Rejected when handoff_hops >= 3
            bus.published.clear()
            exhausted_ctx = dict(base_ctx, handoff_hops=3)
            await orch.on_chat_message({
                "sender": "tradingstrategist",
                "session_id": "sess-bdd-2",
                "content": "@obsidian-brain:orchestrator Loop check.",
                "task_context": exhausted_ctx,
            })
            self.assertEqual(len(bus.published), 0)

            # 3. Rejected when sender != "user" and task_context is missing
            await orch.on_chat_message({
                "sender": "tradingstrategist",
                "session_id": "sess-bdd-3",
                "content": "@obsidian-brain:orchestrator No context.",
            })
            self.assertEqual(len(bus.published), 0)

            # 4. Controller propagates task_context in process_message & publish_user_message
            ctrl = CommandController(config=cfg, logger=logger)
            ctrl.pool = None
            ctrl.event_bus = bus
            await ctrl.publish_user_message("sess-ctrl", "Start cross-brain job", task_context=base_ctx)
            self.assertEqual(bus.published[-1][1]["task_context"]["bdd_spec_path"], base_ctx["bdd_spec_path"])

    async def test_developer_writes_in_external_workspace_runs_compliance_and_defaults_rag_brain(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ext_ws = Path(tmpdir) / "trading-ws"
            ext_ws.mkdir(parents=True)

            bus = _FakeSquadBus()
            logger = MagicMock()
            cfg = _make_mock_config("obsidian-brain")
            dev = DeveloperAgent(config=cfg, logger=logger, pg_pool=None, event_bus=bus)

            # Verify '/' is rejected by _resolve_active_workspace_root()
            dev.current_task_context = {"target_workspace_path": "/"}
            resolved_root = dev._resolve_active_workspace_root()
            self.assertNotEqual(str(resolved_root), "/")

            # Set valid external domain workspace task_context
            dev.current_task_context = {
                "target_brain_id": "trading-brain",
                "target_workspace_path": str(ext_ws),
                "target_vault_path": str(ext_ws / "trading-brain"),
                "fleet_mode": "docker",
                "handoff_hops": 1,
            }

            # 1. Compliant Python write succeeds in external workspace
            compliant_py = (
                "#!/usr/bin/env python\n"
                "# coding:utf-8\n\n"
                '"""\n'
                "ESSENTIAL PROCESS:\nAlpha strategy signal calculator.\n\n"
                "DATA FLOW:\n1. Computes moving signal.\n\n"
                "KEY PARAMETERS:\n- price: Input price.\n"
                '"""\n\n'
                "from math import sqrt as mathSqrt\n\n"
                "# -----------------------------------------------------------------------------------------------\n\n\n"
                "def calc_signal(price: float) -> float:\n"
                '    """Computes normalized signal."""\n'
                "    return mathSqrt(price)\n"
            )
            res_ok = await dev.execute_tool(
                "write_workspace_file",
                {"path": "alpha-svc/src/signal.py", "content": compliant_py},
            )
            self.assertEqual(res_ok, "Success writing to file alpha-svc/src/signal.py")
            self.assertTrue((ext_ws / "alpha-svc" / "src" / "signal.py").is_file())

            # 2. Non-compliant Python write triggers central ComplianceAuditor
            bad_py = "import os\ndef bad():\n    pass\n"
            res_bad = await dev.execute_tool(
                "write_workspace_file",
                {"path": "alpha-svc/src/bad.py", "content": bad_py},
            )
            self.assertIn("ecosystem compliance / lean-code violation(s)", res_bad)

            # 3. query_rag_engine defaults brain_id to task_context['target_brain_id']
            captured_tenants = []

            class _FakeRAGStore:
                def __init__(self, *, config, logger, tenant, client=None):
                    captured_tenants.append(tenant)

                def retrieve(self, query, limit=5):
                    return [{"content": "Trading strategy convention"}]

            with patch("src.agents.base_agent.RAGMemoryStore", _FakeRAGStore):
                rag_out = await dev.execute_tool("query_rag_engine", {"query": "alpha contracts"})

            self.assertEqual(captured_tenants, ["trading-brain"])
            self.assertIn("Trading strategy convention", rag_out)

            # 4. scaffold_microservice tool invokes main.py scaffold-microservice with APP_LOGGER_PROFILE=devel
            fake_proc = MagicMock(stdout="Scaffolded alpha-svc", stderr="", returncode=0)
            with patch("src.agents.developer.subprocessRun", return_value=fake_proc) as mock_run:
                scaf_out = await dev.execute_tool(
                    "scaffold_microservice",
                    {"name": "alpha-svc", "lang": "go", "port": 8150, "layer": "L4"},
                )

            self.assertIn("Exit Code: 0", scaf_out)
            cmd_used = mock_run.call_args.args[0]
            env_used = mock_run.call_args.kwargs["env"]
            self.assertIn("scaffold-microservice", cmd_used)
            self.assertIn("--fleet-mode", cmd_used)
            self.assertEqual(cmd_used[cmd_used.index("--fleet-mode") + 1], "docker")
            self.assertEqual(cmd_used[cmd_used.index("--dest") + 1], str((ext_ws / "alpha-svc").resolve()))
            self.assertEqual(env_used["APP_LOGGER_PROFILE"], "devel")

    async def test_qa_probe_service_health_ssrf_allowlist(self):
        qa = QAAgent(
            config=_make_mock_config("obsidian-brain"),
            logger=MagicMock(),
            pg_pool=None,
            event_bus=_FakeSquadBus(),
        )

        # 1. 127.0.0.1, 127.0.0.2, and single-label container DNS allowed via urlopen
        fake_resp = MagicMock()
        fake_resp.status = 200
        fake_resp.read.return_value = b'{"status":"healthy","brain_id":"trading-brain"}'
        fake_cm = MagicMock()
        fake_cm.__enter__.return_value = fake_resp
        fake_cm.__exit__.return_value = False

        with patch("src.agents.qa.urllibRequestUrlopen", return_value=fake_cm) as mock_open:
            res_127 = await qa.execute_tool(
                "probe_service_health",
                {"url": "http://127.0.0.1:8150/api/v1/health"},
            )
            res_bridge = await qa.execute_tool(
                "probe_service_health",
                {"url": "http://127.0.0.2:8150/api/v1/contracts"},
            )
            res_dns = await qa.execute_tool(
                "probe_service_health",
                {"url": "http://web-interface:5000/api/v1/services?brain_id=trading-brain"},
            )
        self.assertEqual(mock_open.call_count, 3)
        self.assertIn("HTTP 200", res_127)
        self.assertIn("trading-brain", res_127)
        self.assertIn("HTTP 200", res_bridge)
        self.assertIn("HTTP 200", res_dns)

        # 2. External domains / metadata IPs / non-HTTP schemes rejected
        for blocked_url in (
            "https://evil.com/steal",
            "http://169.254.169.254/latest/meta-data",
            "http://10.0.0.5:8080/api/v1/health",
            "http://2130706433/api/v1/health",
            "file:///etc/passwd",
        ):
            blocked_res = await qa.execute_tool("probe_service_health", {"url": blocked_url})
            self.assertTrue(
                blocked_res.startswith("Error:"),
                f"Expected SSRF rejection for {blocked_url}, got: {blocked_res}",
            )


if __name__ == "__main__":
    unittest.main()
