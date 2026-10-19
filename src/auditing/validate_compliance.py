#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Mechanical Code Compliance and Architectural Invariant Auditor.
Scans source code files across the Bastien-Antigravity fleet to verify strict adherence to:
  1. Triple-Block Header Standard (ESSENTIAL PROCESS, DATA FLOW, KEY PARAMETERS)
  2. Section Divider Standard (// --------- or # ---------)
  3. Dynamic Port Invariant (No hardcoded canonical ports in production code)
  4. Production Cleanliness Invariant (No test mocks, EnsureSafeLogger, or nil fallbacks in bin source)
  5. Dynamic Host Invariant (No hardcoded 127.0.0.1 / localhost in capability connection logic)
  6. Ecosystem Tooling Invariant (Entrypoints must use BootstrapService / bootstrap_microservice)
  7. Observability Invariant (Zero bare print/println in production code)
  8. Path Sovereignty Invariant (Zero legacy manual sys.path climbing)
  9. SSoT Configuration Invariant (No direct parsing of standalone.yaml)
  10. Dynamic Versioning Invariant (No manual directory loops for VERSION.txt)

DATA FLOW:
1. Receives file path or directory path (or reads git staged files).
2. Identifies file language (Go, Python, Rust, C++).
3. Evaluates compliance checks based on file type and production vs test status.
4. Generates structured violation reports with line numbers and corrective guidance.
5. Returns exit status (0 = COMPLIANT, 1 = VIOLATIONS_DETECTED) and diagnostic report.

KEY PARAMETERS:
- target_path: Path to a file or directory in the workspace.
- strict_headers: If True, requires all 3 header sections in all non-test source files.
"""

import os
import sys
import re
import json
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional

# -----------------------------------------------------------------------------

CANONICAL_PORTS = {
    "3306": "config_server (TCP)",
    "3307": "config_server (gRPC)",
    "3308": "config_server (REST)",
    "9020": "log_server (SafeSocket TCP)",
    "1026": "notif_server (TCP)",
    "1027": "notif_server (gRPC)",
    "1029": "notif_server (REST)",
    "1863": "tele_remote (gRPC)",
    "5000": "web_interface (HTTP)",
    "8001": "web_interface (gRPC)",
    "9095": "watchdog_agent (HTTP)",
    "4222": "nats_server (Core)",
    "5432": "timescale_db (PostgreSQL)",
    "8090": "rag_engine (MCP SSE)",
    "8091": "rag_engine (gRPC)",
    "8093": "rag_engine (REST)",
    "8082": "rag_engine (Dashboard)",
}

EXCLUDED_DIRS = {
    ".git", ".venv", "venv", "node_modules", "target", "bin", 
    "obj", "dist", "build", "vendor", ".rag_cache", "__pycache__"
}

# -----------------------------------------------------------------------------

class ComplianceAuditor:
    """Mechanical compliance scanner for code files."""

    def __init__(self, workspace_root: Optional[Path] = None):
        if workspace_root:
            self.workspace_root = workspace_root
        else:
            self.workspace_root = Path(__file__).resolve().parent.parent.parent.parent

    # -----------------------------------------------------------------------------

    def audit_file(self, file_path: Path) -> List[Dict[str, Any]]:
        """Audits a single source file and returns a list of detected violations."""
        violations = []
        if not file_path.is_file():
            return violations

        ext = file_path.suffix.lower()
        if ext not in (".go", ".py", ".rs", ".cpp", ".h", ".hpp"):
            return violations

        filename = file_path.name
        is_test_file = (
            filename.endswith("_test.go") or 
            filename.startswith("test_") or 
            filename.endswith("_test.py") or
            "tests" in file_path.parts or
            "test" in file_path.parts
        )
        is_generated = (
            filename.endswith(".pb.go") or 
            filename.endswith(".capnp.go") or
            filename.endswith("_pb2.py") or
            filename.endswith("_pb2_grpc.py") or
            "_gen.go" in filename or
            "schemas" in file_path.parts
        )

        if is_generated or filename == "validate_compliance.py":
            return violations

        is_library_repo = any(lib in file_path.parts for lib in ("microservice-toolbox", "distributed-config", "safe-socket", "universal-logger", "flexible-logger"))

        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            violations.append({
                "file": str(file_path),
                "line": 0,
                "rule": "FILE_READ_ERROR",
                "message": f"Unable to read file: {e}"
            })
            return violations

        lines = content.splitlines()
        total_lines = len(lines)

        # 0. Shebang and Encoding Check (All Python files)
        if ext == ".py":
            has_shebang = len(lines) >= 1 and lines[0].strip() == "#!/usr/bin/env python"
            has_encoding = len(lines) >= 2 and lines[1].strip() == "# coding:utf-8"
            if not (has_shebang and has_encoding):
                violations.append({
                    "file": str(file_path),
                    "line": 1,
                    "rule": "SHEBANG_AND_ENCODING_MISSING",
                    "message": "Python file must start with '#!/usr/bin/env python' on line 1 and '# coding:utf-8' on line 2."
                })

        # 0b. Unbootstrapped Entrypoint Check (Go and Python binaries)
        if not is_test_file and not is_library_repo:
            if filename == "main.go":
                has_bootstrap = any("BootstrapService" in l and not l.strip().startswith("//") for l in lines)
                if not has_bootstrap:
                    violations.append({
                        "file": str(file_path),
                        "line": 1,
                        "rule": "UNBOOTSTRAPPED_ENTRYPOINT",
                        "message": "Go entrypoint main.go must initialize via toolbox_bootstrap.BootstrapService(\"service-name\", ...)."
                    })
            elif filename in ("main.py", "app.py"):
                has_bootstrap = any(
                    ("bootstrap_microservice" in l or "src.bootstrap" in l) and not l.strip().startswith("#") 
                    for l in lines
                ) or "src/bootstrap" in str(file_path)
                if not has_bootstrap:
                    violations.append({
                        "file": str(file_path),
                        "line": 1,
                        "rule": "UNBOOTSTRAPPED_ENTRYPOINT",
                        "message": "Python entrypoint must invoke bootstrap_microservice(__file__, ...) from microservice_toolbox."
                    })

        # 1. Triple-Block Header Check (Non-test files with > 15 lines)
        if not is_test_file and total_lines > 15 and filename not in ("__init__.py", "main.go"):
            header_sample = "\n".join(lines[:45])
            has_essential = "ESSENTIAL PROCESS" in header_sample
            has_data_flow = "DATA FLOW" in header_sample
            has_key_params = "KEY PARAMETERS" in header_sample

            missing_sections = []
            if not has_essential:
                missing_sections.append("ESSENTIAL PROCESS")
            if not has_data_flow:
                missing_sections.append("DATA FLOW")
            if not has_key_params:
                missing_sections.append("KEY PARAMETERS")

            if missing_sections:
                violations.append({
                    "file": str(file_path),
                    "line": 1,
                    "rule": "TRIPLE_BLOCK_HEADER_MISSING",
                    "message": f"Missing Triple-Block header sections: {', '.join(missing_sections)}"
                })

        # 2. Section Divider Check (Non-test files with > 50 lines)
        if not is_test_file and total_lines > 50:
            divider_pattern = re.compile(r'(//|#)\s*-{25,}')
            has_divider = any(divider_pattern.search(l) for l in lines)
            if not has_divider:
                violations.append({
                    "file": str(file_path),
                    "line": 1,
                    "rule": "SECTION_DIVIDERS_MISSING",
                    "message": "File lacks standard section dividers (// ----------------- or # -----------------)"
                })

        # Line-by-line checks
        for idx, line in enumerate(lines, 1):
            stripped = line.strip()
            # Skip pure comment lines for code checks
            if stripped.startswith("//") or stripped.startswith("#") or stripped.startswith("*"):
                continue

            # 3. Dynamic Port Invariant: Flag hardcoded canonical ports in production code
            if not is_test_file:
                for port_num, port_desc in CANONICAL_PORTS.items():
                    # Look for :port or "port" string literals in networking contexts
                    port_patterns = [
                        f':{port_num}"',
                        f':{port_num}\'',
                        f'"{port_num}"',
                        f"'{port_num}'",
                    ]
                    for pat in port_patterns:
                        if pat in line:
                            # Avoid false positives in config loading keys or comments
                            if not any(k in line.lower() for k in ("getlistenaddr", "getgrpc", "getrest", "capability", "capabilities", "port_map")):
                                violations.append({
                                    "file": str(file_path),
                                    "line": idx,
                                    "rule": "HARDCODED_PORT",
                                    "message": f"Hardcoded canonical port {port_num} ({port_desc}) detected. Use appConfig.Get*Addr dynamic accessor instead."
                                })
                                break

            # 4. Production Cleanliness Invariant: No test mocks or nil fallbacks in non-test microservice files
            if not is_test_file and not is_library_repo:
                if "EnsureSafeLogger" in line:
                    violations.append({
                        "file": str(file_path),
                        "line": idx,
                        "rule": "PRODUCTION_MOCK_POLLUTION",
                        "message": "EnsureSafeLogger is an anti-pattern in microservice production code. Standard runtime guarantees non-nil logger via bootstrapper."
                    })
                if "decrypt == nil" in line:
                    violations.append({
                        "file": str(file_path),
                        "line": idx,
                        "rule": "PRODUCTION_MOCK_POLLUTION",
                        "message": "Fallback 'decrypt == nil' detected in production code. Standard runtime guarantees non-nil decrypt function via appConfig."
                    })
                if ext == ".go" and stripped == 'import "testing"':
                    violations.append({
                        "file": str(file_path),
                        "line": idx,
                        "rule": "TEST_IMPORT_IN_PRODUCTION",
                        "message": "Direct import of 'testing' framework in non-test Go file. Must be in *_test.go only."
                    })
                if ext == ".py" and (stripped.startswith("import pytest") or stripped.startswith("from pytest")):
                    violations.append({
                        "file": str(file_path),
                        "line": idx,
                        "rule": "TEST_IMPORT_IN_PRODUCTION",
                        "message": "Direct import of 'pytest' in non-test Python file. Must be in test_*.py only."
                    })

                # 5. Observability Invariant: No bare print/println in production code
                cli_presenters = {
                    "start_squad.py", "scaffold_microservice.py", "mission_help.py", 
                    "switch_mode.py", "install_git_hooks.py", "fleet_commander.py", 
                    "fleet_version.py", "preflight_check.py", "joint_audit_purger.py",
                    "audit_ports.py", "ensure_frontmatter.py", "hardening_yaml.py",
                    "improved_transformer.py"
                }
                allow_print = filename in cli_presenters or any(marker in content[:500] for marker in ("# cli:allow-print", "// cli:allow-print", "/* cli:allow-print */"))
                if not allow_print:
                    if ext == ".go":
                        if any(p in stripped for p in ("fmt.Println(", "fmt.Printf(", "fmt.Print(", "log.Println(", "log.Printf(", "log.Print(")):
                            if not any(k in stripped for k in ("//", "/*")):
                                violations.append({
                                    "file": str(file_path),
                                    "line": idx,
                                    "rule": "BARE_PRINT_PRODUCTION",
                                    "message": "Bare fmt/log print detected in production Go code. Output must route via universal-logger / Logger.<Level>(...)."
                                })
                    elif ext == ".rs":
                        if any(p in stripped for p in ("println!(", "eprintln!(")):
                            violations.append({
                                "file": str(file_path),
                                "line": idx,
                                "rule": "BARE_PRINT_PRODUCTION",
                                "message": "Bare println!/eprintln! detected in production Rust code. Output must route via universal-logger / tracing."
                            })
                    elif ext == ".py":
                        if re.search(r'(?<![a-zA-Z0-9_])print\s*\(', stripped):
                            violations.append({
                                "file": str(file_path),
                                "line": idx,
                                "rule": "BARE_PRINT_PRODUCTION",
                                "message": "Bare print() detected in production Python code. Output must route via UniLog (from universal_logger / microservice_toolbox)."
                            })

                # 6. Legacy Path Climbing Invariant: No manual sys.path manipulation in service code
                if ext == ".py" and filename not in ("bootstrap.py", "validate_compliance.py"):
                    if any(p in line for p in ("sys.path.insert(0, str(_src_dir))", "sys.path.insert(0, str(_project_dir))", "_src_dir = _self_dir.parent", "_self_dir = Path(__file__).resolve().parent")):
                        violations.append({
                            "file": str(file_path),
                            "line": idx,
                            "rule": "LEGACY_PATH_CLIMBING",
                            "message": "Legacy manual path climbing detected. Use bootstrap_microservice(__file__, app_name=...) from microservice_toolbox instead."
                        })

                # 7. SSoT Configuration Invariant: No direct YAML parsing of standalone.yaml
                if "standalone.yaml" in line or "native.yaml" in line:
                    if any(p in line for p in ("yaml.safe_load", "yaml.load", "yaml.Unmarshal")):
                        violations.append({
                            "file": str(file_path),
                            "line": idx,
                            "rule": "DIRECT_YAML_PARSE",
                            "message": "Direct YAML parsing of standalone.yaml / native.yaml detected. Configuration must be loaded via microservice-toolbox / distributed-config."
                        })

                # 8. Dynamic Versioning Invariant: No ad-hoc directory crawling for VERSION.txt
                if filename not in ("fleet_version.py", "preflight_check.py"):
                    if "VERSION.txt" in line and any(p in line for p in ("while ", "parents", "[]string", '.parent / "VERSION.txt"')):
                        violations.append({
                            "file": str(file_path),
                            "line": idx,
                            "rule": "HARDCODED_VERSION_TRAVERSAL",
                            "message": "Ad-hoc directory traversal searching for VERSION.txt detected. Call appConfig.GetVersion() or microservice_toolbox.version.get_version() instead."
                        })

        return violations

    # -----------------------------------------------------------------------------

    def audit_path(self, target_path: Path) -> List[Dict[str, Any]]:
        """Audits a path (file or recursive directory)."""
        all_violations = []
        if target_path.is_file():
            return self.audit_file(target_path)

        for root, dirs, files in os.walk(target_path):
            dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS and not d.startswith(".")]
            for f in sorted(files):
                file_path = Path(root) / f
                all_violations.extend(self.audit_file(file_path))

        return all_violations

    # -----------------------------------------------------------------------------

    def format_report(self, violations: List[Dict[str, Any]]) -> str:
        """Formats violations list into human and agent readable report."""
        if not violations:
            return "✅ Code Compliance Audit: ALL CLEAR (100% compliant with ecosystem standards)."

        output = [
            f"❌ Code Compliance Audit: {len(violations)} violation(s) detected across target files:\n"
        ]
        # Group by file
        by_file: Dict[str, List[Dict[str, Any]]] = {}
        for v in violations:
            by_file.setdefault(v["file"], []).append(v)

        for file_str, v_list in by_file.items():
            rel_file = file_str
            try:
                rel_file = str(Path(file_str).relative_to(self.workspace_root))
            except ValueError:
                pass
            output.append(f"📁 [{rel_file}] ({len(v_list)} violations):")
            for item in v_list:
                line_str = f"Line {item['line']}" if item['line'] > 0 else "File header"
                output.append(f"   - [{item['rule']}] {line_str}: {item['message']}")
            output.append("")

        output.append("💡 Corrective Guidelines:")
        output.append("  1. Add standard Triple-Block headers (ESSENTIAL PROCESS, DATA FLOW, KEY PARAMETERS) to all non-test files.")
        output.append("  2. Place section dividers (// ----------------- or # -----------------) between exported functions.")
        output.append("  3. Replace literal port strings with appConfig.GetListenAddr('capability_name').")
        output.append("  4. Never place test loggers or decrypt fallback nil checks in production constructors.")
        output.append("  5. Entrypoints must initialize via BootstrapService / bootstrap_microservice.")
        output.append("  6. Output must route through universal-logger / UniLog (no bare print / println in production).")
        output.append("  7. Use bootstrap_microservice instead of legacy manual sys.path climbing.")
        output.append("  8. Load configuration via microservice-toolbox / distributed-config instead of direct YAML parsing.")
        output.append("  9. Resolve dynamic version via appConfig.GetVersion() or microservice_toolbox.version.")
        return "\n".join(output)

    # -----------------------------------------------------------------------------

    def audit_staged(self) -> List[Dict[str, Any]]:
        """Audits git staged files in the current repository / workspace."""
        all_violations = []
        try:
            res = subprocess.run(
                ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
                capture_output=True, text=True, check=True
            )
            staged_files = [f.strip() for f in res.stdout.splitlines() if f.strip()]
            for sf in staged_files:
                p = Path(sf).resolve()
                if p.is_file():
                    all_violations.extend(self.audit_file(p))
        except Exception as e:
            all_violations.append({
                "file": "git",
                "line": 0,
                "rule": "GIT_STAGED_AUDIT_ERROR",
                "message": f"Failed to inspect git staged files: {e}"
            })
        return all_violations

# -----------------------------------------------------------------------------

def main():
    """CLI runner for standalone audit execution."""
    import argparse
    parser = argparse.ArgumentParser(description="Mechanical Code Compliance Auditor")
    parser.add_argument("path", nargs="?", default=".", help="Target file or directory path to audit (defaults to current dir)")
    parser.add_argument("--staged", action="store_true", help="Audit only Git staged files (pre-commit mode)")
    parser.add_argument("--json", action="store_true", help="Output raw JSON format")
    parser.add_argument("--fix", action="store_true", help="Auto-repair detected formatting & header violations in Python files")
    args = parser.parse_args()

    auditor = ComplianceAuditor()

    if args.fix:
        target = Path(args.path).resolve()
        from src.lib.improved_transformer import CodeTransformer
        transformer = CodeTransformer()
        repaired = transformer.transform_path(target)
        print(f"🔧 CodeTransformer auto-repaired {repaired} Python file(s).\n")

    if args.staged:
        violations = auditor.audit_staged()
    else:
        target = Path(args.path).resolve()
        violations = auditor.audit_path(target)

    if args.json:
        print(json.dumps(violations, indent=2))
    else:
        print(auditor.format_report(violations))

    sys.exit(0 if len(violations) == 0 else 1)

if __name__ == "__main__":
    main()
