#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Unit tests for ecosystem compliance, AST verification, and anti-pattern detection rules.
Validates that ComplianceAuditor enforces mandatory ecosystem tooling and detects anti-patterns.

DATA FLOW:
1. Audits live ecosystem directories (08-Squad-Agent/src, 04-Rapid-Prototyping/src, 05-Fleet-Operation).
2. Synthesizes violation fixtures (bare prints, legacy path climbing, unbootstrapped entrypoints).
3. Asserts that ComplianceAuditor accurately flags violations and passes compliant code.

KEY PARAMETERS:
- SQUAD_AGENT_DIR: Root path to 08-Squad-Agent.
"""

import sys
import shutil
import tempfile
import unittest
from pathlib import Path

# Add squad root to sys.path
SQUAD_AGENT_DIR = Path(__file__).resolve().parent.parent
if str(SQUAD_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(SQUAD_AGENT_DIR))

from src.auditing.validate_compliance import ComplianceAuditor

# -----------------------------------------------------------------------------

class TestEcosystemCompliance(unittest.TestCase):
    """Test suite for mechanical compliance rules and ecosystem tooling enforcement."""

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="test_compliance_"))
        self.auditor = ComplianceAuditor(workspace_root=SQUAD_AGENT_DIR.parent)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    # -----------------------------------------------------------------------------

    def test_squad_agent_src_is_100_percent_compliant(self):
        """Verifies that 08-Squad-Agent/src has 0 compliance violations."""
        src_path = SQUAD_AGENT_DIR / "src"
        violations = self.auditor.audit_path(src_path)
        self.assertEqual(
            violations, [],
            f"08-Squad-Agent/src must be 100% compliant. Found {len(violations)} violation(s): {violations}"
        )

    def test_rapid_prototyping_src_is_100_percent_compliant(self):
        """Verifies that 04-Rapid-Prototyping/src has 0 compliance violations."""
        l04_src = SQUAD_AGENT_DIR.parent / "04-Rapid-Prototyping" / "src"
        if l04_src.exists():
            violations = self.auditor.audit_path(l04_src)
            self.assertEqual(
                violations, [],
                f"04-Rapid-Prototyping/src must be 100% compliant. Found {len(violations)} violation(s): {violations}"
            )

    def test_fleet_operation_repo_control_is_100_percent_compliant(self):
        """Verifies that 05-Fleet-Operation/00-Repo-Control has 0 compliance violations."""
        l05_control = SQUAD_AGENT_DIR.parent / "05-Fleet-Operation" / "00-Repo-Control"
        if l05_control.exists():
            violations = self.auditor.audit_path(l05_control)
            self.assertEqual(
                violations, [],
                f"05-Fleet-Operation must be 100% compliant. Found {len(violations)} violation(s): {violations}"
            )

    # -----------------------------------------------------------------------------

    def test_catches_bare_print_in_python_production(self):
        """Verifies that bare print() in non-test Python files is flagged."""
        bad_file = self.test_dir / "worker.py"
        bad_file.write_text("""#!/usr/bin/env python
# coding:utf-8

\"\"\"
ESSENTIAL PROCESS:
Worker process.

DATA FLOW:
1. Runs worker.

KEY PARAMETERS:
- param: Test param.
\"\"\"

# -----------------------------------------------------------------------------

def do_work():
    print("starting work...")
""")
        violations = self.auditor.audit_file(bad_file)
        rules = [v["rule"] for v in violations]
        self.assertIn("BARE_PRINT_PRODUCTION", rules)

    def test_allows_print_with_cli_allow_print_marker(self):
        """Verifies that # cli:allow-print permits terminal output."""
        cli_file = self.test_dir / "reporter.py"
        cli_file.write_text("""#!/usr/bin/env python
# coding:utf-8
# cli:allow-print

\"\"\"
ESSENTIAL PROCESS:
CLI reporter.

DATA FLOW:
1. Renders table.

KEY PARAMETERS:
- param: Test param.
\"\"\"

# -----------------------------------------------------------------------------

def render_table():
    print("+-------+-------+")
""")
        violations = self.auditor.audit_file(cli_file)
        rules = [v["rule"] for v in violations]
        self.assertNotIn("BARE_PRINT_PRODUCTION", rules)

    def test_catches_bare_print_in_go_and_rust(self):
        """Verifies that bare fmt.Println in Go and println! in Rust are flagged."""
        bad_go = self.test_dir / "service.go"
        bad_go.write_text("""package main

import "fmt"

func run() {
    fmt.Println("starting go service...")
}
""")
        go_violations = self.auditor.audit_file(bad_go)
        go_rules = [v["rule"] for v in go_violations]
        self.assertIn("BARE_PRINT_PRODUCTION", go_rules)

        bad_rust = self.test_dir / "service.rs"
        bad_rust.write_text("""fn run() {
    println!("starting rust daemon...");
}
""")
        rs_violations = self.auditor.audit_file(bad_rust)
        rs_rules = [v["rule"] for v in rs_violations]
        self.assertIn("BARE_PRINT_PRODUCTION", rs_rules)

    def test_catches_unbootstrapped_entrypoint(self):
        """Verifies that unbootstrapped main.go and main.py are flagged."""
        bad_main_go = self.test_dir / "main.go"
        bad_main_go.write_text("""package main

func main() {
    // Missing toolbox_bootstrap.BootstrapService
}
""")
        violations = self.auditor.audit_file(bad_main_go)
        rules = [v["rule"] for v in violations]
        self.assertIn("UNBOOTSTRAPPED_ENTRYPOINT", rules)

        bad_main_py = self.test_dir / "main.py"
        bad_main_py.write_text("""#!/usr/bin/env python
# coding:utf-8

\"\"\"
ESSENTIAL PROCESS:
Main entry.

DATA FLOW:
1. Run.

KEY PARAMETERS:
- None.
\"\"\"

def main():
    pass

if __name__ == "__main__":
    main()
""")
        violations_py = self.auditor.audit_file(bad_main_py)
        rules_py = [v["rule"] for v in violations_py]
        self.assertIn("UNBOOTSTRAPPED_ENTRYPOINT", rules_py)

    def test_catches_legacy_path_climbing(self):
        """Verifies that manual sys.path climbing is flagged."""
        bad_file = self.test_dir / "legacy_script.py"
        bad_file.write_text("""#!/usr/bin/env python
# coding:utf-8

\"\"\"
ESSENTIAL PROCESS:
Legacy script.

DATA FLOW:
1. Climb.

KEY PARAMETERS:
- None.
\"\"\"

# -----------------------------------------------------------------------------

import sys
from pathlib import Path
_self_dir = Path(__file__).resolve().parent
_src_dir = _self_dir.parent
sys.path.insert(0, str(_src_dir))
""")
        violations = self.auditor.audit_file(bad_file)
        rules = [v["rule"] for v in violations]
        self.assertIn("LEGACY_PATH_CLIMBING", rules)

    def test_catches_hardcoded_ports_and_direct_yaml(self):
        """Verifies that literal ports and direct YAML parsing are caught."""
        bad_file = self.test_dir / "connector.py"
        bad_file.write_text("""#!/usr/bin/env python
# coding:utf-8

\"\"\"
ESSENTIAL PROCESS:
Connector.

DATA FLOW:
1. Connect.

KEY PARAMETERS:
- None.
\"\"\"

# -----------------------------------------------------------------------------

import yaml

def connect():
    cfg = yaml.safe_load(open("standalone.yaml"))
    target = "http://127.0.0.1:3306"
    return cfg, target
""")
        violations = self.auditor.audit_file(bad_file)
        rules = [v["rule"] for v in violations]
        self.assertIn("DIRECT_YAML_PARSE", rules)
        self.assertIn("HARDCODED_PORT", rules)

    def test_catches_python_granular_import_and_alias_violations(self):
        """Verifies that whole-module imports and unaliased stdlib imports are flagged in strict mode."""
        bad_py = self.test_dir / "unaliased_worker.py"
        bad_py.write_text("""#!/usr/bin/env python
# coding:utf-8

\"\"\"
ESSENTIAL PROCESS:
Worker with non-compliant imports.

DATA FLOW:
1. Serializes payload.

KEY PARAMETERS:
- payload: Input dictionary.
\"\"\"

import json
from os.path import join
from .storage import Storage as aliasedStorage

# -----------------------------------------------------------------------------------------------

def serialize(payload):
    return json.dumps(payload), join("a", "b"), aliasedStorage
""")
        violations = self.auditor.audit_file(bad_py, strict_imports=True)
        rules = [v["rule"] for v in violations]
        self.assertIn("PYTHON_WHOLE_MODULE_IMPORT", rules)
        self.assertIn("PYTHON_UNALIASED_IMPORT", rules)
        self.assertIn("PYTHON_LOCAL_IMPORT_ALIASED", rules)

        compliant_py = self.test_dir / "compliant_worker.py"
        compliant_py.write_text("""#!/usr/bin/env python
# coding:utf-8

\"\"\"
ESSENTIAL PROCESS:
Worker with compliant Bastien granular camelCase aliased imports.

DATA FLOW:
1. Serializes payload.

KEY PARAMETERS:
- payload: Input dictionary.
\"\"\"

from json import dumps as jsonDumps
from os.path import join as osPathJoin, exists as osPathExists
from typing import Any as typeAny, Dict as typeDict

from .storage import Storage

# -----------------------------------------------------------------------------------------------

def serialize(payload: typeDict[str, typeAny]) -> str:
    if osPathExists(osPathJoin("a", "b")):
        return jsonDumps(payload)
    return str(Storage)
""")
        clean_violations = self.auditor.audit_file(compliant_py, strict_imports=True)
        self.assertEqual(clean_violations, [])

    def test_catches_strict_lean_anti_defensive_violations(self):
        """Verifies that strict_lean flags config paranoia, multi-fallback chains, silent except: pass, and TOCTOU."""
        bloated_py = self.test_dir / "bloated_service.py"
        bloated_py.write_text("""#!/usr/bin/env python
# coding:utf-8

\"\"\"
ESSENTIAL PROCESS:
Bloated worker with over-defensive anti-patterns.

DATA FLOW:
1. Checks config redundantly.

KEY PARAMETERS:
- config: AppConfig.
\"\"\"

import os

# -----------------------------------------------------------------------------------------------

class BloatedWorker:
    def run(self):
        if hasattr(self.config, "data") and isinstance(self.config.data, dict):
            pass
        brain = self.config.get("target_brain_id") or os.getenv("TARGET_BRAIN_ID") or os.getenv("BRAIN_ID")
        if os.path.exists("data.txt"):
            with open("data.txt", "r") as f:
                _ = f.read()
        try:
            _ = int(brain or "1")
        except Exception:
            pass
""")
        violations = self.auditor.audit_file(bloated_py, strict_lean=True)
        rules = [v["rule"] for v in violations]
        self.assertIn("DEBLOAT_CONFIG_PARANOIA", rules)
        self.assertIn("DEBLOAT_MULTI_FALLBACK_CHAIN", rules)
        self.assertIn("DEBLOAT_DEFENSIVE_TOCTOU", rules)
        self.assertIn("DEBLOAT_SILENT_EXCEPT_PASS", rules)

    def test_task_decomposer_complexity_gate_and_splitting(self):
        """Verifies TaskDecomposer classifies atomic vs multi-step requests and injects toolbox guardrails."""
        from src.lib.task_decomposer import TaskDecomposer
        decomposer = TaskDecomposer(max_files_per_turn=2, split_threshold=4)

        # 1. Simple atomic request (1 file, 1 layer)
        simple = decomposer.decompose_request("Fix typo in controller.py")
        self.assertFalse(simple["requires_split"])
        self.assertEqual(simple["classification"], "ATOMIC")
        self.assertEqual(len(simple["subtasks"]), 1)

        # 2. Complex multi-file, multi-layer, polyglot request
        complex_req = (
            "Refactor standalone.yaml, controller.py, memory.py, rest_handler.py, and service.go "
            "to add PostgreSQL schema migration, gRPC endpoint, FastAPI route, and pytest unit tests."
        )
        split_res = decomposer.decompose_request(complex_req)
        self.assertTrue(split_res["requires_split"])
        self.assertEqual(split_res["classification"], "MULTI_STEP_REQUIRED")
        self.assertGreaterEqual(len(split_res["subtasks"]), 3)
        for st in split_res["subtasks"]:
            self.assertLessEqual(len(st["target_files"]), 2)

        formatted = decomposer.format_execution_plan(complex_req)
        self.assertIn("MULTI_STEP_REQUIRED", formatted)
        self.assertIn("config.get_version()", formatted)

    def test_maintenance_skill_compacts_without_deleting_mandatory_file(self):
        """Scenario: compact_session_state_file trims old sessions in-place without deleting AI-Session-State.md."""
        from src.maintenance.maintenance_skill import compact_session_state_file
        state_path = self.test_dir / "AI-Session-State.md"
        sections = [f"## Session {i}\n- Action {i}\n\n" for i in range(1, 8)]
        state_path.write_text(
            "---\nmicroservice: test-svc\ntype: state\nstatus: active\n---\n# Session State\n\n"
            + "".join(sections),
            encoding="utf-8",
        )
        compacted = compact_session_state_file(state_path, max_sessions=3)
        self.assertTrue(compacted)
        self.assertTrue(state_path.exists(), "AI-Session-State.md must NEVER be deleted")
        new_text = state_path.read_text(encoding="utf-8")
        self.assertIn("microservice: test-svc", new_text)
        self.assertEqual(new_text.count("## Session "), 3)
        self.assertIn("## Session 1", new_text)
        self.assertNotIn("## Session 7", new_text)

    def test_hardening_yaml_valid_frontmatter_and_11_code_doc_protection(self):
        """Scenario: apply_hardening injects canonical YAML frontmatter and refuses to mutate 11-Code-Doc mirrors."""
        import unittest.mock
        import src.auditing.hardening_yaml as hy

        fake_vault = self.test_dir / "obsidian-brain"
        arch_dir = fake_vault / "03-Tech-Stack"
        codedoc_dir = fake_vault / "11-Code-Doc" / "config-server"
        arch_dir.mkdir(parents=True, exist_ok=True)
        codedoc_dir.mkdir(parents=True, exist_ok=True)

        arch_note = arch_dir / "Sample-Blueprint.md"
        arch_note.write_text("# Sample Blueprint\nContent here.\n", encoding="utf-8")

        mirror_note = codedoc_dir / "main.go.md"
        orig_mirror = "---\nsource: main.go\nworkspace: config-server\ntype: code-mirror\nstatus: auto-generated\n---\n# Mirror\n"
        mirror_note.write_text(orig_mirror, encoding="utf-8")

        with unittest.mock.patch.object(hy, "VAULT_ROOT", fake_vault):
            self.assertTrue(hy.apply_hardening(arch_note))
            updated_arch = arch_note.read_text(encoding="utf-8")
            self.assertTrue(updated_arch.startswith("---\n"))
            self.assertNotIn("--- \n", updated_arch)
            self.assertIn("type: architecture", updated_arch)
            self.assertIn("#zone/3-fleet", updated_arch)

            # 11-Code-Doc mirror must be untouched
            self.assertFalse(hy.apply_hardening(mirror_note))
            self.assertEqual(mirror_note.read_text(encoding="utf-8"), orig_mirror)

    def test_skill_template_coherence_round_trip(self):
        """Scenario: build_skill_markdown output is 100% coherent with check_coherence stripping rules."""
        from src.fleet.convert_agents import build_skill_markdown
        from src.auditing.check_coherence import strip_frontmatter, strip_sandbox_headers

        raw_prompt = "---\nmicroservice: core-kms\ntype: governance\n---\n# Role: Developer\nFollow clean code rules."
        compiled = build_skill_markdown("developer", raw_prompt)
        self.assertIn("COMPLEXITY GATE & CANONICAL TOOLBOX CONTRACT", compiled)

        skill_clean = strip_sandbox_headers(strip_frontmatter(compiled)).strip()
        prompt_clean = strip_sandbox_headers(strip_frontmatter(raw_prompt)).strip()
        self.assertEqual(skill_clean, prompt_clean)


if __name__ == "__main__":
    unittest.main()
