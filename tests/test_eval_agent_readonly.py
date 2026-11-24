#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Self-contained Zone-1 unit and adversarial tests for BaseAgent read-only guardrails,
list_workspace_files containment, folded-body write corruption protection, SCAN header
deduplication, and the isolated SquadAgentEvaluator (`eval-agent`) harness.

DATA FLOW:
1. Creates isolated temporary workspace/repository fixtures with zero external repo dependencies.
2. Verifies role-scoped read-only defaults, adversarial mutating-tool rejection, and path traversal blocks.
3. Simulates multi-turn Gemini tool calls (`list_workspace_files` -> `read_workspace_file` -> `[SCAN]`)
   through SquadAgentEvaluator with `pg_pool=None` and verifies the generated scorecard.

KEY PARAMETERS:
- SQUAD_DIR: Root directory of 08-Squad-Agent.
"""

from pathlib import Path as pathPath
from sys import path as sysPath
from tempfile import TemporaryDirectory as tempfileTemporaryDirectory
from types import SimpleNamespace as typesSimpleNamespace
from unittest import IsolatedAsyncioTestCase as unittestIsolatedAsyncioTestCase, main as unittestMain
from unittest.mock import MagicMock as mockMagicMock

SQUAD_DIR = pathPath(__file__).resolve().parent.parent
TOOLBOX_PY_DIR = SQUAD_DIR.parent.parent / "microservice-toolbox" / "python"
for _candidate in (str(TOOLBOX_PY_DIR), str(SQUAD_DIR)):
    if _candidate not in sysPath:
        sysPath.insert(0, _candidate)

import src.bootstrap as _bootstrap  # noqa: F401
from src.agents.architect import ArchitectAgent
from src.agents.debloatsentinel import DebloatSentinelAgent
from src.agents.developer import DeveloperAgent
from src.agents.patternsentinel import PatternSentinelAgent
from src.agents.qa import QAAgent
from src.auditing.check_coherence import strip_frontmatter, strip_sandbox_headers
from src.auditing.eval_agent import SquadAgentEvaluator, format_eval_markdown
from src.fleet.convert_agents import build_skill_markdown

# -----------------------------------------------------------------------------------------------


def _make_test_config() -> mockMagicMock:
    cfg = mockMagicMock()
    cfg.data = {
        "capabilities": {
            "squad_agent": {
                "target_brain_id": "obsidian-brain",
                "gemini_model": "gemini-3.8-flash",
            },
        },
    }
    cfg.get_capability.return_value = cfg.data["capabilities"]["squad_agent"]
    cfg.get_version.return_value = "0.0.1"
    return cfg


# -----------------------------------------------------------------------------------------------


class TestEvalAgentAndReadOnlyGuardrails(unittestIsolatedAsyncioTestCase):
    """Zone-1 tests for read-only agent guardrails and SquadAgentEvaluator."""

    def test_scan_header_deduplicated_when_prompt_already_defines_scan(self) -> None:
        """Prompts that already define [SCAN] must not receive a duplicate trailing [SCAN] block."""
        prompt_with_scan = (
            "---\nmicroservice: core-kms\ntype: governance\n---\n"
            "# Role 12: Pattern Sentinel\n"
            "`[SCAN] Role: PatternSentinel | Insights: [New] | Governance: [Rules]`\n"
            "Audit repository patterns."
        )
        compiled_dedup = build_skill_markdown("patternsentinel", prompt_with_scan)
        self.assertEqual(compiled_dedup.count("[SCAN]"), 1)
        self.assertNotIn("ATTENTION RESTORATION", compiled_dedup)
        self.assertEqual(
            strip_sandbox_headers(strip_frontmatter(compiled_dedup)),
            strip_sandbox_headers(strip_frontmatter(prompt_with_scan)),
        )

        prompt_without_scan = (
            "---\nmicroservice: core-kms\ntype: governance\n---\n"
            "# Squad Role: Go Systems Specialist\n"
            "Write concurrent Go services."
        )
        compiled_added = build_skill_markdown("gospecialist", prompt_without_scan)
        self.assertEqual(compiled_added.count("[SCAN]"), 1)
        self.assertIn("ATTENTION RESTORATION", compiled_added)
        self.assertEqual(
            strip_sandbox_headers(strip_frontmatter(compiled_added)),
            strip_sandbox_headers(strip_frontmatter(prompt_without_scan)),
        )

    # -------------------------------------------------------------------------------------------

    async def test_role_scoped_read_only_permissions_and_adversarial_rejection(self) -> None:
        """Auditor personas default to read-only while Developer/QA keep write tools until locked."""
        cfg = _make_test_config()
        logger = mockMagicMock()
        bus = SquadAgentEvaluator(config=cfg, logger=logger)

        pat_agent = PatternSentinelAgent(config=cfg, logger=logger, pg_pool=None, event_bus=bus)
        deb_agent = DebloatSentinelAgent(config=cfg, logger=logger, pg_pool=None, event_bus=bus)
        arch_agent = ArchitectAgent(config=cfg, logger=logger, pg_pool=None, event_bus=bus)
        dev_agent = DeveloperAgent(config=cfg, logger=logger, pg_pool=None, event_bus=bus)
        qa_agent = QAAgent(config=cfg, logger=logger, pg_pool=None, event_bus=bus)

        for ro_agent in (pat_agent, deb_agent, arch_agent):
            self.assertTrue(ro_agent.read_only)
            tool_names = [t.__name__ for t in ro_agent._get_effective_tools()]
            self.assertIn("list_workspace_files", tool_names)
            self.assertIn("read_workspace_file", tool_names)
            self.assertNotIn("write_workspace_file", tool_names)
            self.assertNotIn("execute_shell_command", tool_names)
            self.assertNotIn("generate_safe_by_design_spec", tool_names)

        # Adversarial calls to mutating tools on read-only agents must fail fast without side effects
        with tempfileTemporaryDirectory() as tmpdir:
            ws = pathPath(tmpdir).resolve()
            pat_agent.domain_workspace_root = ws
            deb_agent.domain_workspace_root = ws

            res_w = await pat_agent.execute_tool("write_workspace_file", {"path": "hack.py", "content": "x = 1\n"})
            self.assertIn("disabled in read-only mode", res_w)
            self.assertFalse((ws / "hack.py").exists())

            res_sh = await pat_agent.execute_tool("execute_shell_command", {"command": "echo hi"})
            self.assertIn("disabled in read-only mode", res_sh)

            res_spec = await deb_agent.execute_tool("generate_safe_by_design_spec", {"path": "."})
            self.assertIn("disabled in read-only mode", res_spec)

        # Developer and QA start writable in normal mode, then lock cleanly via enable_readonly_mode()
        self.assertFalse(dev_agent.read_only)
        self.assertFalse(qa_agent.read_only)
        self.assertIn("write_workspace_file", [t.__name__ for t in qa_agent._get_effective_tools()])

        dev_agent.enable_readonly_mode()
        self.assertTrue(dev_agent.read_only)
        dev_ro_tools = [t.__name__ for t in dev_agent._get_effective_tools()]
        self.assertNotIn("write_workspace_file", dev_ro_tools)
        self.assertNotIn("execute_shell_command", dev_ro_tools)
        self.assertNotIn("scaffold_microservice", dev_ro_tools)
        res_scaf = await dev_agent.execute_tool("scaffold_microservice", {"name": "demo-svc"})
        self.assertIn("disabled in read-only mode", res_scaf)

    # -------------------------------------------------------------------------------------------

    async def test_list_workspace_files_and_folded_body_write_protection(self) -> None:
        """Verifies list_workspace_files containment, full-body default reads, and folded-body write rejection."""
        with tempfileTemporaryDirectory() as tmpdir:
            ws = pathPath(tmpdir).resolve()
            svc_dir = ws / "demo-svc" / "src"
            svc_dir.mkdir(parents=True)
            (ws / "demo-svc" / ".git").mkdir()
            (ws / "demo-svc" / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")

            multi_line_py = (
                "def compute_total(items):\n"
                "    acc = 0\n"
                "    for item in items:\n"
                "        acc += item\n"
                "    if acc < 0:\n"
                "        return 0\n"
                "    return acc\n"
            )
            target_py = svc_dir / "calc.py"
            target_py.write_text(multi_line_py, encoding="utf-8")

            cfg = _make_test_config()
            logger = mockMagicMock()
            bus = SquadAgentEvaluator(config=cfg, logger=logger, workspace_root=ws)
            dev = DeveloperAgent(config=cfg, logger=logger, pg_pool=None, event_bus=bus)
            dev.domain_workspace_root = ws

            # 1. list_workspace_files lists source files and excludes .git
            listed = await dev.execute_tool("list_workspace_files", {"path": "demo-svc"})
            self.assertEqual(listed.strip(), "demo-svc/src/calc.py")

            # 2. Path traversal outside workspace is denied
            escaped = await dev.execute_tool("list_workspace_files", {"path": "../../etc"})
            self.assertIn("Access denied", escaped)

            # 3. Default read_workspace_file keeps full body (fold_bodies=False default)
            full_read = await dev.execute_tool("read_workspace_file", {"path": "demo-svc/src/calc.py"})
            self.assertEqual(full_read, multi_line_py)
            self.assertNotIn("# ... folded ...", full_read)

            # 4. Explicit fold_bodies=True folds body, and write_workspace_file blocks writing it back
            folded_read = await dev.execute_tool(
                "read_workspace_file",
                {"path": "demo-svc/src/calc.py", "fold_bodies": True},
            )
            self.assertIn("# ... folded ...", folded_read)

            blocked_write = await dev.execute_tool(
                "write_workspace_file",
                {"path": "demo-svc/src/calc.py", "content": folded_read},
            )
            self.assertIn("Refusing to write", blocked_write)
            self.assertEqual(target_py.read_text(encoding="utf-8"), multi_line_py)

    # -------------------------------------------------------------------------------------------

    async def test_evaluator_runs_multi_turn_readonly_session_without_postgres(self) -> None:
        """SquadAgentEvaluator runs tool-calling turns with pg_pool=None and builds an accurate scorecard."""
        with tempfileTemporaryDirectory() as tmpdir:
            ws = pathPath(tmpdir).resolve()
            repo_dir = ws / "sample-repo"
            repo_dir.mkdir(parents=True)
            sample_file = repo_dir / "bad_client.py"
            sample_file.write_text("import os\nPORT = 1027\n", encoding="utf-8")

            # Simulate 3-turn Gemini SDK tool sequence: list_workspace_files -> read_workspace_file -> final report
            turn1 = typesSimpleNamespace(
                text="",
                candidates=[
                    typesSimpleNamespace(
                        content=typesSimpleNamespace(
                            parts=[
                                typesSimpleNamespace(
                                    function_call=typesSimpleNamespace(
                                        name="list_workspace_files",
                                        args={"path": "sample-repo"},
                                    ),
                                    thought_signature=b"sig1",
                                )
                            ]
                        )
                    )
                ],
            )
            turn2 = typesSimpleNamespace(
                text="",
                candidates=[
                    typesSimpleNamespace(
                        content=typesSimpleNamespace(
                            parts=[
                                typesSimpleNamespace(
                                    function_call=typesSimpleNamespace(
                                        name="read_workspace_file",
                                        args={"path": "sample-repo/bad_client.py"},
                                    ),
                                    thought_signature=b"sig2",
                                )
                            ]
                        )
                    )
                ],
            )
            turn3 = typesSimpleNamespace(
                text=(
                    "[SCAN] Role: PatternSentinel | Insights: 2 violations | Governance: None\n"
                    "Found whole-module `import os` and hardcoded port `1027` in `sample-repo/bad_client.py`."
                ),
                candidates=[typesSimpleNamespace(content=typesSimpleNamespace(parts=[]))],
            )

            fake_genai = mockMagicMock()
            fake_genai.models.generate_content.side_effect = [turn1, turn2, turn3]

            cfg = _make_test_config()
            cfg.data["genai_client"] = fake_genai
            logger = mockMagicMock()

            evaluator = SquadAgentEvaluator(config=cfg, logger=logger, workspace_root=ws)
            scorecard = await evaluator.evaluate(
                role="patternsentinel",
                repo="sample-repo",
                read_only=True,
                include_ground_truth=True,
            )

            self.assertEqual(scorecard["role"], "patternsentinel")
            self.assertTrue(scorecard["read_only"])
            self.assertEqual(scorecard["tool_calls_count"], 2)
            self.assertTrue(scorecard["coherency_checks"]["read_only_tools_clean"])
            self.assertTrue(scorecard["coherency_checks"]["zero_mutations_executed"])
            self.assertTrue(scorecard["coherency_checks"]["scan_header_present"])
            self.assertTrue(scorecard["coherency_checks"]["used_file_listing"])
            self.assertEqual(scorecard["coherency_checks"]["blind_read_error_count"], 0)
            self.assertGreaterEqual(scorecard["ground_truth"]["compliance_violation_count"], 2)

            md = format_eval_markdown(scorecard)
            self.assertIn("Squad Agent Evaluation Scorecard: `patternsentinel`", md)
            self.assertIn("`PASS`", md)

            # Specialist role instantiation (gospecialist) also resolves and locks read-only cleanly
            go_agent = evaluator.instantiate_agent(role="gospecialist", read_only=True)
            self.assertEqual(go_agent.role_name, "gospecialist")
            self.assertTrue(go_agent.read_only)
            self.assertNotIn("write_workspace_file", [t.__name__ for t in go_agent._get_effective_tools()])


if __name__ == "__main__":
    unittestMain()
