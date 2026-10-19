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


if __name__ == "__main__":
    unittest.main()
