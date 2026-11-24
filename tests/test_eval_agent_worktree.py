#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Self-contained Zone-1 unit and adversarial tests for Phase 2 `--mode worktree`
isolation in BaseAgent and SquadAgentEvaluator (`eval-agent`).

DATA FLOW:
1. Initializes temporary standalone Git repositories with tracked files, unit tests,
   VERSION.txt, and external symlinks (`standalone.yaml`) without touching sibling repos.
2. Runs DeveloperAgent inside `--mode worktree`, verifying surgical `edit_workspace_file`,
   secret-stripped child `sandbox_env`, unit test execution, `.patch` export, and 100%
   unchanged host Git fingerprint (`HEAD`, `status`, `refs`, `worktrees`).
3. Exercises adversarial escape vectors: symlink writes, VERSION.txt/.git mutations,
   Complexity Gate >max_files limit, shell chaining/redirection/git/rm commands, and
   unconditional cleanup upon agent exception.

KEY PARAMETERS:
- SQUAD_DIR: Root directory of 08-Squad-Agent.
"""

from os import environ as osEnviron, symlink as osSymlink
from pathlib import Path as pathPath
from subprocess import run as subprocessRun
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
from src.agents.developer import DeveloperAgent
from src.agents.qa import QAAgent
from src.auditing.eval_agent import SquadAgentEvaluator, _capture_git_fingerprint, format_eval_markdown

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


def _init_temp_git_repo(repo_dir: pathPath, external_secret_cfg: pathPath) -> None:
    """Creates a realistic self-contained Git repository fixture with tests, VERSION.txt, and symlink."""
    (repo_dir / "src").mkdir(parents=True)
    (repo_dir / "tests").mkdir(parents=True)
    (repo_dir / "VERSION.txt").write_text("1.2.3\n", encoding="utf-8")

    compliant_calc = (
        "#!/usr/bin/env python\n"
        "# coding:utf-8\n\n"
        '"""\n'
        "ESSENTIAL PROCESS:\nDeterministic signal multiplier.\n\n"
        "DATA FLOW:\n1. Multiplies input value by factor.\n\n"
        "KEY PARAMETERS:\n- val: Numeric value.\n"
        '"""\n\n'
        "# -----------------------------------------------------------------------------------------------\n\n\n"
        "def scale_value(val: int) -> int:\n"
        '    """Scales val by 2."""\n'
        "    return val * 2\n"
    )
    (repo_dir / "src" / "calc.py").write_text(compliant_calc, encoding="utf-8")

    # Unit test ALSO asserts that host secrets are stripped and LOGGER_PROFILE is 'minimal' inside sandbox!
    unit_test = (
        "import os\n"
        "import sys\n"
        "import unittest\n"
        "from pathlib import Path\n\n"
        "sys.path.insert(0, str(Path(__file__).resolve().parent.parent))\n"
        "from src.calc import scale_value\n\n\n"
        "class TestCalc(unittest.TestCase):\n"
        "    def test_scale_and_hermetic_env(self):\n"
        "        self.assertEqual(scale_value(5), 15)\n"
        "        self.assertIsNone(os.environ.get('GITHUB_TOKEN'))\n"
        "        self.assertIsNone(os.environ.get('GEMINI_API_KEY'))\n"
        "        self.assertEqual(os.environ.get('LOGGER_PROFILE'), 'minimal')\n"
        "        self.assertEqual(os.environ.get('GOWORK'), 'off')\n\n\n"
        "if __name__ == '__main__':\n"
        "    unittest.main()\n"
    )
    (repo_dir / "tests" / "test_calc.py").write_text(unit_test, encoding="utf-8")
    osSymlink(str(external_secret_cfg), str(repo_dir / "standalone.yaml"))

    for git_args in (
        ["init"],
        ["config", "user.email", "test@bastien.local"],
        ["config", "user.name", "SquadEvalTest"],
        ["add", "."],
        ["commit", "-m", "initial fixture"],
    ):
        proc = subprocessRun(["git"] + git_args, cwd=str(repo_dir), capture_output=True, text=True, check=True)
        _ = proc


# -----------------------------------------------------------------------------------------------


class TestEvalAgentWorktreeSandbox(unittestIsolatedAsyncioTestCase):
    """End-to-end and adversarial tests proving `--mode worktree` isolation."""

    async def test_worktree_mode_edits_runs_hermetic_tests_exports_patch_and_leaves_host_untouched(self) -> None:
        """Agent fixes a bug in /tmp worktree, passes tests & compliance, exports .patch, and touches 0 host bytes."""
        with tempfileTemporaryDirectory() as tmpdir:
            ws = pathPath(tmpdir).resolve()
            external_cfg = ws / "host_native_secret.yaml"
            external_cfg.write_text("secret_token: DO_NOT_TOUCH\n", encoding="utf-8")

            repo_dir = ws / "demo-svc"
            _init_temp_git_repo(repo_dir, external_cfg)
            orig_calc = (repo_dir / "src" / "calc.py").read_text(encoding="utf-8")
            pre_fp = _capture_git_fingerprint(repo_dir)
            patch_file = ws / "exported" / "fix_scale.patch"

            old_gh = osEnviron.get("GITHUB_TOKEN")
            old_gm = osEnviron.get("GEMINI_API_KEY")
            osEnviron["GITHUB_TOKEN"] = "ghp_super_secret_host_token"
            osEnviron["GEMINI_API_KEY"] = "AIza_super_secret_host_key"
            try:
                turn1 = typesSimpleNamespace(
                    text="",
                    candidates=[
                        typesSimpleNamespace(
                            content=typesSimpleNamespace(
                                parts=[
                                    typesSimpleNamespace(
                                        function_call=typesSimpleNamespace(
                                            name="edit_workspace_file",
                                            args={
                                                "path": "demo-svc/src/calc.py",
                                                "target": '    """Scales val by 2."""\n    return val * 2',
                                                "replacement": '    """Scales val by 3."""\n    return val * 3',
                                            },
                                        ),
                                        thought_signature=b"s1",
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
                                            name="execute_shell_command",
                                            args={"command": "python3 -m unittest discover -s demo-svc/tests"},
                                        ),
                                        thought_signature=b"s2",
                                    )
                                ]
                            )
                        )
                    ],
                )
                turn3 = typesSimpleNamespace(
                    text="[SCAN] Role: developer | Source: demo-svc/src/calc.py | State: Verified\nFixed multiplier to 3.",
                    candidates=[typesSimpleNamespace(content=typesSimpleNamespace(parts=[]))],
                )

                fake_genai = mockMagicMock()
                fake_genai.models.generate_content.side_effect = [turn1, turn2, turn3]
                cfg = _make_test_config()
                cfg.data["genai_client"] = fake_genai
                logger = mockMagicMock()

                evaluator = SquadAgentEvaluator(config=cfg, logger=logger, workspace_root=ws)
                scorecard = await evaluator.evaluate(
                    role="developer",
                    repo="demo-svc",
                    mode="worktree",
                    max_files=2,
                    patch_out=str(patch_file),
                    run_tests=True,
                    include_ground_truth=False,
                )
            finally:
                if old_gh is None:
                    osEnviron.pop("GITHUB_TOKEN", None)
                else:
                    osEnviron["GITHUB_TOKEN"] = old_gh
                if old_gm is None:
                    osEnviron.pop("GEMINI_API_KEY", None)
                else:
                    osEnviron["GEMINI_API_KEY"] = old_gm

            # 1. Host repository & external symlink target are 100% untouched byte-for-byte
            self.assertEqual((repo_dir / "src" / "calc.py").read_text(encoding="utf-8"), orig_calc)
            self.assertEqual(external_cfg.read_text(encoding="utf-8"), "secret_token: DO_NOT_TOUCH\n")
            self.assertEqual(_capture_git_fingerprint(repo_dir), pre_fp)

            # 2. Scorecard confirms clean sandbox teardown, compliance, and test pass
            wt = scorecard["worktree_sandbox"]
            self.assertTrue(wt["sandbox_cleaned_up"])
            self.assertTrue(wt["host_workspace_untouched"])
            self.assertEqual(wt["changed_files"], ["src/calc.py"])
            self.assertEqual(wt["post_edit_compliance_violations"], [])
            self.assertTrue(wt["test_verification"]["executed"])
            self.assertTrue(wt["test_verification"]["passed"], wt["test_verification"])
            self.assertTrue(scorecard["coherency_checks"]["complexity_gate_respected"])
            self.assertTrue(scorecard["coherency_checks"]["post_edit_compliance_clean"])

            # 3.Sandboxed shell command inside turn 2 also passed with stripped env
            shell_call = scorecard["tool_calls"][1]
            self.assertIn("Exit Code: 0", shell_call["result"])

            # 4. Exported .patch is valid and cleanly applicable to the untouched host repo
            self.assertTrue(patch_file.is_file())
            apply_check = subprocessRun(
                ["git", "apply", "--check", str(patch_file)],
                cwd=str(repo_dir),
                capture_output=True,
                text=True,
            )
            self.assertEqual(apply_check.returncode, 0, apply_check.stderr)

            md = format_eval_markdown(scorecard)
            self.assertIn("Isolated `/tmp` Git Worktree Verification", md)

    # -------------------------------------------------------------------------------------------

    async def test_adversarial_escape_vectors_blocked_in_worktree_jail(self) -> None:
        """Blocks symlink writes, VERSION.txt/.git edits, >max_files edits, and shell/git escapes."""
        with tempfileTemporaryDirectory() as tmpdir:
            root = pathPath(tmpdir).resolve()
            outside_secret = root / "outside_native.yaml"
            outside_secret.write_text("live: untouched\n", encoding="utf-8")

            sandbox_ws = root / "sandbox_ws"
            svc_dir = sandbox_ws / "svc"
            (svc_dir / ".git").mkdir(parents=True)
            (svc_dir / ".git" / "config").write_text("[core]\n", encoding="utf-8")
            (svc_dir / "VERSION.txt").write_text("0.0.1\n", encoding="utf-8")
            (svc_dir / "a.txt").write_text("alpha\n", encoding="utf-8")
            (svc_dir / "b.txt").write_text("beta\n", encoding="utf-8")
            (svc_dir / "c.txt").write_text("gamma\n", encoding="utf-8")
            osSymlink(str(outside_secret), str(svc_dir / "standalone.yaml"))

            cfg = _make_test_config()
            logger = mockMagicMock()
            bus = SquadAgentEvaluator(config=cfg, logger=logger, workspace_root=sandbox_ws)
            dev = DeveloperAgent(config=cfg, logger=logger, pg_pool=None, event_bus=bus)
            qa = QAAgent(config=cfg, logger=logger, pg_pool=None, event_bus=bus)
            dev.enable_worktree_sandbox_mode(sandbox_root=sandbox_ws, max_files=2)
            qa.enable_worktree_sandbox_mode(sandbox_root=sandbox_ws, max_files=2)

            # 1. Symlink escape blocked
            res_sym = await dev.execute_tool(
                "write_workspace_file",
                {"path": "svc/standalone.yaml", "content": "hacked: true\n"},
            )
            self.assertIn("Refusing to modify symlink", res_sym)
            self.assertEqual(outside_secret.read_text(encoding="utf-8"), "live: untouched\n")

            # 2. Protected files & .git metadata blocked
            res_ver = await dev.execute_tool("write_workspace_file", {"path": "svc/VERSION.txt", "content": "9.9.9\n"})
            self.assertIn("protected", res_ver)
            self.assertEqual((svc_dir / "VERSION.txt").read_text(encoding="utf-8"), "0.0.1\n")

            res_git = await dev.execute_tool("write_workspace_file", {"path": "svc/.git/config", "content": "bad\n"})
            self.assertIn("Git metadata", res_git)

            # 3. Path traversal blocked
            res_trav = await dev.execute_tool("write_workspace_file", {"path": "../outside_native.yaml", "content": "x"})
            self.assertIn("Access denied", res_trav)

            # 4. External side-effect tools blocked in worktree mode
            res_scaf = await dev.execute_tool("scaffold_microservice", {"name": "evil-svc"})
            self.assertIn("disabled in isolated worktree sandbox mode", res_scaf)
            res_probe = await qa.execute_tool("probe_service_health", {"url": "http://127.0.0.1:8085/api/v1/status"})
            self.assertIn("disabled in isolated worktree sandbox mode", res_probe)

            # 5. Shell chaining, git mutations, python -c, and absolute paths blocked
            for forbidden_cmd in (
                "git commit -am 'pollute'",
                "git checkout -b leaked-branch",
                "rm -rf svc",
                "pytest && echo pwned",
                "pytest; ls",
                "pytest /etc/passwd",
                "pytest ../outside",
                "python3 -c 'import os; os.system(\"id\")'",
                "go install example.com/pkg@latest",
            ):
                cmd_out = await dev.execute_tool("execute_shell_command", {"command": forbidden_cmd})
                self.assertTrue(
                    cmd_out.startswith("Error:"),
                    f"Command should have been blocked in worktree jail: {forbidden_cmd} -> {cmd_out}",
                )

            # 6. Complexity Gate allows 2 distinct files and blocks the 3rd file
            ok1 = await dev.execute_tool(
                "edit_workspace_file",
                {"path": "svc/a.txt", "target": "alpha", "replacement": "alpha_v2"},
            )
            ok2 = await dev.execute_tool(
                "edit_workspace_file",
                {"path": "svc/b.txt", "target": "beta", "replacement": "beta_v2"},
            )
            ok2_repeat = await dev.execute_tool(
                "edit_workspace_file",
                {"path": "svc/b.txt", "target": "beta_v2", "replacement": "beta_v3"},
            )
            blocked3 = await dev.execute_tool(
                "edit_workspace_file",
                {"path": "svc/c.txt", "target": "gamma", "replacement": "gamma_v2"},
            )
            self.assertIn("Success editing", ok1)
            self.assertIn("Success editing", ok2)
            self.assertIn("Success editing", ok2_repeat)
            self.assertIn("Complexity Gate exceeded", blocked3)
            self.assertEqual((svc_dir / "c.txt").read_text(encoding="utf-8"), "gamma\n")

    # -------------------------------------------------------------------------------------------

    async def test_worktree_cleaned_up_even_when_agent_raises_exception(self) -> None:
        """Guaranteed try/finally cleanup prunes /tmp worktree even if execution crashes mid-run."""
        with tempfileTemporaryDirectory() as tmpdir:
            ws = pathPath(tmpdir).resolve()
            ext_cfg = ws / "ext.yaml"
            ext_cfg.write_text("k: v\n", encoding="utf-8")
            repo_dir = ws / "crash-svc"
            _init_temp_git_repo(repo_dir, ext_cfg)
            pre_fp = _capture_git_fingerprint(repo_dir)

            cfg = _make_test_config()
            logger = mockMagicMock()
            evaluator = SquadAgentEvaluator(config=cfg, logger=logger, workspace_root=ws)

            async def _boom() -> None:
                raise RuntimeError("simulated fatal crash during worktree teardown")

            orig_inst = evaluator.instantiate_agent

            def _crashing_agent(**kwargs):
                ag = orig_inst(**kwargs)
                ag.stop = _boom  # type: ignore[method-assign]
                return ag

            evaluator.instantiate_agent = _crashing_agent  # type: ignore[method-assign]
            with self.assertRaises(RuntimeError):
                await evaluator.evaluate(
                    role="developer",
                    repo="crash-svc",
                    mode="worktree",
                    run_tests=False,
                    include_ground_truth=False,
                )
            self.assertEqual(_capture_git_fingerprint(repo_dir), pre_fp)


if __name__ == "__main__":
    unittestMain()
