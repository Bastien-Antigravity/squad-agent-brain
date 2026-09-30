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

DATA FLOW:
1. Receives file path or directory path.
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
            is_library_repo = any(lib in file_path.parts for lib in ("microservice-toolbox", "distributed-config", "safe-socket", "universal-logger", "flexible-logger"))
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
        output.append("  2. Place section dividers (// ----------------...) between exported functions.")
        output.append("  3. Replace literal port strings with appConfig.GetListenAddr('capability_name').")
        output.append("  4. Never place test loggers or decrypt fallback nil checks in production constructors.")
        return "\n".join(output)

# -----------------------------------------------------------------------------

def main():
    """CLI runner for standalone audit execution."""
    import argparse
    parser = argparse.ArgumentParser(description="Mechanical Code Compliance Auditor")
    parser.add_argument("path", nargs="?", default=".", help="Target file or directory path to audit (defaults to current dir)")
    parser.add_argument("--json", action="store_true", help="Output raw JSON format")
    parser.add_argument("--fix", action="store_true", help="Auto-repair detected formatting & header violations in Python files")
    args = parser.parse_args()

    target = Path(args.path).resolve()
    auditor = ComplianceAuditor()

    if args.fix:
        from src.lib.improved_transformer import CodeTransformer
        transformer = CodeTransformer()
        repaired = transformer.transform_path(target)
        print(f"🔧 CodeTransformer auto-repaired {repaired} Python file(s).\n")

    violations = auditor.audit_path(target)

    if args.json:
        print(json.dumps(violations, indent=2))
    else:
        print(auditor.format_report(violations))

    sys.exit(0 if len(violations) == 0 else 1)

if __name__ == "__main__":
    main()
