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
  11. Platform Schema SSoT Invariant (logger.capnp & notifier.capnp exclusively in microservice-toolbox; no legacy local schema imports)
  12. Polyglot Local-First Workspace Resolution (Zero local filesystem path overrides in go.mod, Cargo.toml, pyproject.toml, requirements*.txt, or CMakeLists.txt)

DATA FLOW:
1. Receives file path or directory path (or reads git staged files).
2. Identifies file language (Go, Python, Rust, C++) or manifest (go.mod, Cargo.toml, pyproject.toml, requirements*.txt, CMakeLists.txt).
3. Evaluates compliance checks based on file type and production vs test status.
4. Generates structured violation reports with line numbers and corrective guidance.
5. Returns exit status (0 = COMPLIANT, 1 = VIOLATIONS_DETECTED) and diagnostic report.

KEY PARAMETERS:
- target_path: Path to a file or directory in the workspace.
- strict_headers: If True, requires all 3 header sections in all non-test source files.
"""

from ast import (
    AsyncFunctionDef as astAsyncFunctionDef,
    ClassDef as astClassDef,
    Constant as astConstant,
    Expr as astExpr,
    FunctionDef as astFunctionDef,
    Import as astImport,
    ImportFrom as astImportFrom,
    Module as astModule,
    parse as astParse,
    walk as astWalk,
)
from json import dumps as jsonDumps
from os import walk as osWalk
from pathlib import Path
from re import (
    IGNORECASE as reIgnoreCase,
    compile as reCompile,
    match as reMatch,
    search as reSearch,
    split as reSplit,
    sub as reSub,
)
from subprocess import run as subprocessRun
from sys import exit as sysExit
from typing import (
    Any as typeAny,
    Dict as typeDict,
    List as typeList,
    Optional as typeOptional,
)

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

PLATFORM_EXCLUSIVE_MODULES = {
    "winreg", "msvcrt", "winsound",
    "fcntl", "termios", "pwd", "grp", "resource", "pty", "syslog",
}

PLATFORM_EXCLUSIVE_OS_SYMBOLS = {
    "startfile", "fork", "getuid", "geteuid", "setuid", "killpg", "mkfifo", "waitpid",
}

# -----------------------------------------------------------------------------

class ComplianceAuditor:
    """Mechanical compliance scanner for code files."""

    def __init__(self, workspace_root: typeOptional[Path] = None):
        if workspace_root:
            self.workspace_root = workspace_root
        else:
            self.workspace_root = Path(__file__).resolve().parent.parent.parent.parent

    # -----------------------------------------------------------------------------------------------

    def audit_python_imports(self, file_path: Path, content: typeOptional[str] = None) -> typeList[typeDict[str, typeAny]]:
        """
        Audits a Python source file for strict adherence to the Bastien Granular Functional Import
        and camelCase Aliasing rules:
          1. No whole-module `import <pkg>` outside the top bootstrap block.
          2. All stdlib/external `from <pkg> import <sym>` must be aliased in camelCase (`as <pkgSym>`).
          3. All imports from the same module must be combined onto a single line.
          4. Local/internal project imports must NOT be aliased.
          5. Wildcard imports (`from <pkg> import *`) are strictly prohibited.
        """
        violations: typeList[typeDict[str, typeAny]] = []
        if file_path.suffix.lower() != ".py":
            return violations

        if content is None:
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                return violations

        try:
            tree = astParse(content, filename=str(file_path))
        except SyntaxError:
            return violations

        from src.lib.improved_transformer import CodeTransformer

        # Identify line where bootstrap_microservice / ensure_virtualenv finishes (if entrypoint)
        lines = content.splitlines()
        bootstrap_end_line = 0
        for idx, l in enumerate(lines, 1):
            if any(k in l for k in ("bootstrap_microservice(", "ensure_import_paths(", "import src.bootstrap as bootstrap")):
                bootstrap_end_line = idx

        seen_from_modules: typeDict[str, int] = {}

        for node in tree.body:
            if isinstance(node, astImport):
                # Allow `import os`, `import sys` inside entrypoint bootstrap block or `import src.bootstrap as bootstrap`
                if node.lineno <= bootstrap_end_line:
                    continue
                for alias in node.names:
                    if alias.name == "src.bootstrap" and alias.asname == "bootstrap":
                        continue
                    suggested_prefix = CodeTransformer.make_camel_alias(alias.name, "func")
                    violations.append({
                        "file": str(file_path),
                        "line": node.lineno,
                        "rule": "PYTHON_WHOLE_MODULE_IMPORT",
                        "message": (
                            f"Whole-module 'import {alias.name}' is prohibited outside bootstrap. "
                            f"Use granular functional import with camelCase alias (e.g., 'from {alias.name} import func as {suggested_prefix}')."
                        ),
                    })
            elif isinstance(node, astImportFrom):
                if node.lineno <= bootstrap_end_line:
                    continue
                mod_name = node.module or ""
                level = node.level or 0
                is_internal = CodeTransformer.is_internal_module(mod_name, level)

                full_mod_key = ("." * level) + mod_name
                if full_mod_key in seen_from_modules:
                    violations.append({
                        "file": str(file_path),
                        "line": node.lineno,
                        "rule": "PYTHON_SEPARATE_MODULE_IMPORTS",
                        "message": (
                            f"Multiple 'from {full_mod_key} import ...' lines detected (previous on line {seen_from_modules[full_mod_key]}). "
                            f"Combine all symbols from '{full_mod_key}' onto a single line."
                        ),
                    })
                else:
                    seen_from_modules[full_mod_key] = node.lineno

                for alias in node.names:
                    if alias.name == "*":
                        violations.append({
                            "file": str(file_path),
                            "line": node.lineno,
                            "rule": "PYTHON_WILDCARD_IMPORT",
                            "message": f"Wildcard import 'from {full_mod_key} import *' is prohibited.",
                        })
                        continue

                    if is_internal:
                        if alias.asname is not None:
                            violations.append({
                                "file": str(file_path),
                                "line": node.lineno,
                                "rule": "PYTHON_LOCAL_IMPORT_ALIASED",
                                "message": (
                                    f"Internal import 'from {full_mod_key} import {alias.name} as {alias.asname}' must NOT be aliased. "
                                    f"The camelCase aliasing rule applies strictly to external and standard libraries."
                                ),
                            })
                    else:
                        # Allow bootstrap helpers unaliased
                        if alias.name in ("bootstrap_microservice", "init_microservice", "ensure_virtualenv", "prepend_venv_bin", "ensure_import_paths", "get_venv_python"):
                            continue
                        expected_alias = CodeTransformer.make_camel_alias(mod_name, alias.name)
                        if not alias.asname:
                            violations.append({
                                "file": str(file_path),
                                "line": node.lineno,
                                "rule": "PYTHON_UNALIASED_IMPORT",
                                "message": (
                                    f"Unaliased import '{alias.name}' from '{mod_name}'. "
                                    f"Use Bastien camelCase aliasing: 'from {mod_name} import {alias.name} as {expected_alias}'."
                                ),
                            })

        return violations

    # -----------------------------------------------------------------------------

    def _audit_dockerenv_prohibited(
        self,
        *,
        file_path: Path,
        ext: str,
        content: str,
        lines: typeList[str],
    ) -> typeList[typeDict[str, typeAny]]:
        """Flags literal '/.dockerenv' references outside comments and docstrings."""
        violations: typeList[typeDict[str, typeAny]] = []
        target_literal = "/." + "dockerenv"
        rule_msg = (
            "Literal reference to '/.dockerenv' is prohibited. "
            "Check environment variable DOCKER_ENV == \"true\" instead."
        )

        if target_literal not in content:
            return violations

        if ext == ".py":
            try:
                tree = astParse(content, filename=str(file_path))
                docstring_node_ids = set()
                for parent in astWalk(tree):
                    if isinstance(parent, (astModule, astClassDef, astFunctionDef, astAsyncFunctionDef)):
                        if parent.body and isinstance(parent.body[0], astExpr):
                            val = parent.body[0].value
                            if isinstance(val, astConstant) and isinstance(val.value, str):
                                docstring_node_ids.add(id(val))

                for node in astWalk(tree):
                    if (
                        isinstance(node, astConstant)
                        and isinstance(node.value, str)
                        and id(node) not in docstring_node_ids
                        and target_literal in node.value
                    ):
                        violations.append({
                            "file": str(file_path),
                            "line": node.lineno,
                            "rule": "DOCKERENV_PROHIBITED",
                            "message": rule_msg,
                        })
                return violations
            except SyntaxError:
                pass

        in_block_comment = False
        for idx, line in enumerate(lines, 1):
            stripped = line.strip()
            if ext in (".py", ".sh"):
                if stripped.startswith("#"):
                    continue
                code_part = reSplit(r"(?:^|\s)#", line, maxsplit=1)[0]
                if target_literal in code_part:
                    violations.append({
                        "file": str(file_path),
                        "line": idx,
                        "rule": "DOCKERENV_PROHIBITED",
                        "message": rule_msg,
                    })
                continue

            # C-family / Go / Rust comment stripping
            work = line
            if in_block_comment:
                if "*/" in work:
                    work = work.split("*/", 1)[1]
                    in_block_comment = False
                else:
                    continue
            work = reSub(r"/\*.*?\*/", "", work)
            if "/*" in work:
                work = work.split("/*", 1)[0]
                in_block_comment = True
            work = reSub(r"(?<!:)//.*$", "", work)
            if target_literal in work:
                violations.append({
                    "file": str(file_path),
                    "line": idx,
                    "rule": "DOCKERENV_PROHIBITED",
                    "message": rule_msg,
                })

        return violations

    # -----------------------------------------------------------------------------------------------

    def _audit_cross_os_top_level_imports(
        self,
        *,
        file_path: Path,
        content: str,
    ) -> typeList[typeDict[str, typeAny]]:
        """Bans platform-exclusive stdlib imports at module top-level (tree.body)."""
        violations: typeList[typeDict[str, typeAny]] = []
        try:
            tree = astParse(content, filename=str(file_path))
        except SyntaxError:
            return violations

        for node in tree.body:
            if isinstance(node, astImport):
                for alias in node.names:
                    parts = alias.name.split(".")
                    root_mod = parts[0]
                    is_banned_mod = root_mod in PLATFORM_EXCLUSIVE_MODULES
                    is_banned_os = root_mod == "os" and len(parts) > 1 and parts[1] in PLATFORM_EXCLUSIVE_OS_SYMBOLS
                    if is_banned_mod or is_banned_os:
                        violations.append({
                            "file": str(file_path),
                            "line": node.lineno,
                            "rule": "CROSS_OS_TOP_LEVEL_IMPORT",
                            "message": (
                                f"Platform-exclusive top-level import '{alias.name}' breaks cross-OS compatibility. "
                                f"Defer import inside a platform guard (e.g., if sysPlatform == 'win32':) or function scope."
                            ),
                        })
            elif isinstance(node, astImportFrom):
                if (node.level or 0) > 0:
                    continue
                mod_name = node.module or ""
                root_mod = mod_name.split(".")[0]
                if root_mod in PLATFORM_EXCLUSIVE_MODULES:
                    violations.append({
                        "file": str(file_path),
                        "line": node.lineno,
                        "rule": "CROSS_OS_TOP_LEVEL_IMPORT",
                        "message": (
                            f"Platform-exclusive top-level import from '{mod_name}' breaks cross-OS compatibility. "
                            f"Defer import inside a platform guard (e.g., if sysPlatform == 'win32':) or function scope."
                        ),
                    })
                elif mod_name == "os":
                    for alias in node.names:
                        if alias.name in PLATFORM_EXCLUSIVE_OS_SYMBOLS:
                            violations.append({
                                "file": str(file_path),
                                "line": node.lineno,
                                "rule": "CROSS_OS_TOP_LEVEL_IMPORT",
                                "message": (
                                    f"Platform-exclusive top-level import 'from os import {alias.name}' breaks cross-OS compatibility. "
                                    f"Defer import inside a platform guard (e.g., if sysPlatform == 'win32':) or function scope."
                                ),
                            })

        return violations

    # -----------------------------------------------------------------------------

    def _audit_go_mod(
        self,
        *,
        file_path: Path,
        content: str,
        lines: typeList[str],
    ) -> typeList[typeDict[str, typeAny]]:
        """
        Audits a go.mod file for local filesystem replace directives.
        In Go multi-repo architectures, local sibling dependencies must be resolved via
        workspace root go.work, never committed as relative replace directives which break
        standalone CI, Docker builds, and external consumer packages.
        """
        violations: typeList[typeDict[str, typeAny]] = []
        in_replace_block = False

        for idx, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("//"):
                continue
            if stripped.startswith("replace ("):
                in_replace_block = True
                continue
            if in_replace_block:
                if stripped == ")":
                    in_replace_block = False
                    continue
                if "=>" in stripped:
                    parts = stripped.split("=>", 1)
                    target = parts[0].strip()
                    dest = parts[1].strip()
                    if dest.startswith(".") or dest.startswith("/") or "\\" in dest:
                        violations.append({
                            "file": str(file_path),
                            "line": idx,
                            "rule": "GO_LOCAL_REPLACE_POLLUTION",
                            "message": (
                                f"Local filesystem replace directive detected in go.mod ('{target} => {dest}'). "
                                f"Pushing this to GitHub breaks standalone CI/Docker builds. "
                                f"Rely on root go.work for local resolution instead of committing replace directives."
                            ),
                        })
                continue

            if stripped.startswith("replace ") and "=>" in stripped:
                parts = stripped.split("=>", 1)
                target = parts[0].replace("replace", "").strip()
                dest = parts[1].strip()
                if dest.startswith(".") or dest.startswith("/") or "\\" in dest:
                    violations.append({
                        "file": str(file_path),
                        "line": idx,
                        "rule": "GO_LOCAL_REPLACE_POLLUTION",
                        "message": (
                            f"Local filesystem replace directive detected in go.mod ('{target} => {dest}'). "
                            f"Pushing this to GitHub breaks standalone CI/Docker builds. "
                            f"Rely on root go.work for local resolution instead of committing replace directives."
                        ),
                    })

        return violations

    # -----------------------------------------------------------------------------------------------

    @staticmethod
    def _is_external_local_path(dep_path: str) -> bool:
        """Returns True if a manifest path escapes the repository root or uses an absolute/Windows path."""
        cleaned = dep_path.strip()
        return (
            cleaned.startswith("..")
            or cleaned.startswith("/")
            or cleaned.startswith("~")
            or "\\" in cleaned
            or "/../" in cleaned
            or cleaned.startswith("./..")
        )

    # -----------------------------------------------------------------------------------------------

    def audit_cargo_toml(self, file_path: Path) -> typeList[typeDict[str, typeAny]]:
        """
        Audits a Cargo.toml file for local filesystem path dependencies in dependency or [patch] sections.
        Ignores non-dependency sections such as [[bin]], [[example]], [lib], and [package].
        """
        violations: typeList[typeDict[str, typeAny]] = []
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return violations

        current_section = ""
        in_dep_section = False

        for idx, line in enumerate(content.splitlines(), 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue

            section_match = reMatch(r"^(\[\[?)\s*(.+?)\s*(\]\]?)\s*(?:#.*)?$", stripped)
            if section_match:
                brackets = section_match.group(1)
                current_section = section_match.group(2).strip()
                sec_lower = current_section.lower()
                if brackets == "[[":
                    in_dep_section = False
                else:
                    in_dep_section = (
                        sec_lower in ("dependencies", "dev-dependencies", "build-dependencies", "workspace.dependencies", "patch")
                        or sec_lower.startswith(("patch.", "dependencies.", "dev-dependencies.", "build-dependencies.", "workspace.dependencies."))
                        or sec_lower.endswith((".dependencies", ".dev-dependencies", ".build-dependencies"))
                        or any(tok in sec_lower for tok in (".dependencies.", ".dev-dependencies.", ".build-dependencies."))
                    )
                continue

            if not in_dep_section:
                continue

            path_match = reSearch(r"""(?<![a-zA-Z0-9_])path\s*=\s*(["'])([^"']+)\1""", stripped)
            if path_match:
                dep_path = path_match.group(2).strip()
                if self._is_external_local_path(dep_path):
                    violations.append({
                        "file": str(file_path),
                        "line": idx,
                        "rule": "RUST_LOCAL_PATH_POLLUTION",
                        "message": (
                            f"Local filesystem path dependency detected in Cargo.toml ('{dep_path}' in [{current_section}]). "
                            f"Pushing this to GitHub breaks standalone CI/Docker builds. "
                            f"Use canonical git = 'https://github.com/Bastien-Antigravity/...' in Cargo.toml and rely on workspace root .cargo/config.toml paths override for local resolution."
                        ),
                    })

        return violations

    # -----------------------------------------------------------------------------------------------

    def audit_python_manifest(self, file_path: Path) -> typeList[typeDict[str, typeAny]]:
        """
        Audits pyproject.toml and requirements*.txt manifests for local filesystem dependency paths
        that would break standalone CI or Docker builds.
        """
        violations: typeList[typeDict[str, typeAny]] = []
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return violations

        filename = file_path.name
        is_requirements = filename.startswith("requirements") and filename.endswith(".txt")
        is_pyproject = filename == "pyproject.toml"
        if not (is_requirements or is_pyproject):
            return violations

        current_section = ""
        for idx, line in enumerate(content.splitlines(), 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue

            if is_requirements:
                code_part = reSplit(r"(?:^|\s)#", stripped, maxsplit=1)[0].strip()
                if not code_part:
                    continue
                has_local_editable = bool(reSearch(r"(?:^|\s)(?:-e|--editable)(?:\s*=|\s+)(?:\.\.(?:[/\\]|$)|[/~]|file://)", code_part))
                has_file_uri = "file://" in code_part
                has_local_at_ref = bool(reSearch(r"@\s*(?:\.\.(?:[/\\]|$)|[/~]|file://)", code_part))
                starts_with_local_path = code_part.startswith(("../", "..\\", "/Users/", "/", "~/", "~\\"))
                if has_local_editable or has_file_uri or has_local_at_ref or starts_with_local_path:
                    violations.append({
                        "file": str(file_path),
                        "line": idx,
                        "rule": "PYTHON_LOCAL_PATH_POLLUTION",
                        "message": (
                            f"Local filesystem dependency path detected in Python manifest ('{code_part}'). "
                            f"Pushing this to GitHub breaks standalone CI/Docker builds. "
                            f"Use canonical 'git+https://github.com/Bastien-Antigravity/...' URLs and rely on bootstrap_microservice / _bastien_workspace.pth for local workspace resolution."
                        ),
                    })
                continue

            # pyproject.toml checks
            section_match = reMatch(r"^(\[\[?)\s*(.+?)\s*(\]\]?)\s*(?:#.*)?$", stripped)
            if section_match:
                current_section = section_match.group(2).strip().lower()
                continue

            has_file_uri = "file://" in stripped
            has_local_at_ref = bool(reSearch(r"@\s*(?:\.\.(?:[/\\]|$)|[/~])", stripped))
            path_match = reSearch(r"""(?<![a-zA-Z0-9_])path\s*=\s*(["'])([^"']+)\1""", stripped)
            has_external_path = bool(path_match and self._is_external_local_path(path_match.group(2)))
            if has_file_uri or has_local_at_ref or has_external_path:
                detail = path_match.group(2).strip() if has_external_path else stripped
                section_note = f" in [{current_section}]" if current_section else ""
                violations.append({
                    "file": str(file_path),
                    "line": idx,
                    "rule": "PYTHON_LOCAL_PATH_POLLUTION",
                    "message": (
                        f"Local filesystem dependency path detected in Python manifest ('{detail}'{section_note}). "
                        f"Pushing this to GitHub breaks standalone CI/Docker builds. "
                        f"Use canonical 'git+https://github.com/Bastien-Antigravity/...' URLs and rely on bootstrap_microservice / _bastien_workspace.pth for local workspace resolution."
                    ),
                })

        return violations

    # -----------------------------------------------------------------------------------------------

    def audit_cmake_lists(self, file_path: Path) -> typeList[typeDict[str, typeAny]]:
        """
        Audits a service CMakeLists.txt for local path pollution that breaks standalone CI/Docker builds.
        Exempts microservice-toolbox/cpp/CMakeLists.txt itself where relative library hints are fallbacks.
        """
        violations: typeList[typeDict[str, typeAny]] = []
        parts = file_path.parts
        if len(parts) >= 3 and parts[-3:] == ("microservice-toolbox", "cpp", "CMakeLists.txt"):
            return violations

        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return violations

        has_fetchcontent = "FetchContent_Declare" in content and "GIT_REPOSITORY" in content
        if_depth = 0

        for idx, line in enumerate(content.splitlines(), 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue

            code_part = reSplit(r"(?:^|\s)#", line, maxsplit=1)[0].strip()
            if not code_part:
                continue

            if reMatch(r"^\s*if\s*\(", code_part, flags=reIgnoreCase):
                if_depth += 1
                continue
            if reMatch(r"^\s*endif\s*\(", code_part, flags=reIgnoreCase):
                if_depth = max(0, if_depth - 1)
                continue

            has_local_subdir = bool(reSearch(r"\badd_subdirectory\s*\(\s*[\"']?(?:\.\.[/\\]|/)", code_part, flags=reIgnoreCase))
            if has_local_subdir and (if_depth == 0 or not has_fetchcontent):
                violations.append({
                    "file": str(file_path),
                    "line": idx,
                    "rule": "CPP_LOCAL_PATH_POLLUTION",
                    "message": (
                        f"Unconditional local add_subdirectory detected in CMakeLists.txt ('{code_part}'). "
                        f"Pushing this to GitHub breaks standalone CI/Docker builds. "
                        f"Use local-first FETCHCONTENT_SOURCE_DIR_* discovery with FetchContent_Declare GitHub fallback."
                    ),
                })
                continue

            if "/Users/" in code_part:
                violations.append({
                    "file": str(file_path),
                    "line": idx,
                    "rule": "CPP_LOCAL_PATH_POLLUTION",
                    "message": (
                        f"Hardcoded machine-specific '/Users/' path detected in CMakeLists.txt ('{code_part}'). "
                        f"Use local-first FETCHCONTENT_SOURCE_DIR_* discovery and HINTS with FetchContent_Declare GitHub fallback."
                    ),
                })

        return violations

    # -----------------------------------------------------------------------------------------------

    def fix_go_mod(self, file_path: Path) -> bool:
        """
        Safely strips local filesystem replace directives from go.mod.
        Preserves module version replaces (e.g., replace pkg => pkg v1.2.0).
        Returns True if modifications were made.
        """
        try:
            content = file_path.read_text(encoding="utf-8")
        except Exception:
            return False

        lines = content.splitlines()
        new_lines: typeList[str] = []
        modified = False
        in_replace_block = False
        replace_block_lines: typeList[str] = []

        for line in lines:
            stripped = line.strip()
            if stripped.startswith("replace ("):
                in_replace_block = True
                replace_block_lines = []
                continue

            if in_replace_block:
                if stripped == ")":
                    in_replace_block = False
                    kept = []
                    for r_line in replace_block_lines:
                        r_stripped = r_line.strip()
                        if "=>" in r_stripped and not r_stripped.startswith("//"):
                            parts = r_stripped.split("=>", 1)
                            dest = parts[1].strip()
                            if dest.startswith(".") or dest.startswith("/") or "\\" in dest:
                                modified = True
                                continue
                        kept.append(r_line)
                    if kept:
                        new_lines.append("replace (")
                        new_lines.extend(kept)
                        new_lines.append(")")
                    else:
                        modified = True
                        if new_lines and new_lines[-1] == "":
                            new_lines.pop()
                    continue
                else:
                    replace_block_lines.append(line)
                    continue

            if stripped.startswith("replace ") and "=>" in stripped and not stripped.startswith("//"):
                parts = stripped.split("=>", 1)
                dest = parts[1].strip()
                if dest.startswith(".") or dest.startswith("/") or "\\" in dest:
                    modified = True
                    continue

            new_lines.append(line)

        if modified:
            result = "\n".join(new_lines).rstrip() + "\n"
            file_path.write_text(result, encoding="utf-8")
        return modified

    # -----------------------------------------------------------------------------

    def audit_file(self, file_path: Path, strict_imports: bool = False, strict_lean: bool = False) -> typeList[typeDict[str, typeAny]]:
        """Audits a single source file and returns a list of detected violations."""
        violations = []
        if not file_path.is_file():
            return violations

        ext = file_path.suffix.lower()
        filename = file_path.name
        is_python_manifest = filename == "pyproject.toml" or (filename.startswith("requirements") and filename.endswith(".txt"))
        if (
            ext not in (".go", ".py", ".rs", ".cpp", ".c", ".h", ".hpp", ".sh", ".capnp")
            and filename != "go.mod"
            and not filename.endswith(".mod")
            and filename != "Cargo.toml"
            and filename != "CMakeLists.txt"
            and not is_python_manifest
        ):
            return violations

        # Rule PlatformSchemaSSoT: logger.capnp and notifier.capnp must live exclusively in microservice-toolbox
        if ext == ".capnp":
            if filename in ("logger.capnp", "notifier.capnp") and "microservice-toolbox" not in file_path.parts:
                violations.append({
                    "file": str(file_path),
                    "line": 1,
                    "rule": "DUPLICATE_PLATFORM_SCHEMA",
                    "message": (
                        f"Duplicate platform schema '{filename}' detected outside microservice-toolbox. "
                        f"Platform schemas (logger.capnp, notifier.capnp) must reside exclusively in "
                        f"microservice-toolbox (go/pkg/schemas/{{logger,notifier}} and schemas/platform/)."
                    ),
                })
            return violations

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

        # Rule GoMod: Check for local replace directives in go.mod files
        if filename == "go.mod" or filename.endswith(".mod"):
            return self._audit_go_mod(file_path=file_path, content=content, lines=lines)

        # Rule CargoToml: Check for local path dependencies in Cargo.toml files
        if filename == "Cargo.toml":
            return self.audit_cargo_toml(file_path)

        # Rule PythonManifest: Check for local path dependencies in pyproject.toml / requirements*.txt
        if is_python_manifest:
            return self.audit_python_manifest(file_path)

        # Rule CMakeLists: Check for local path pollution in service CMakeLists.txt
        if filename == "CMakeLists.txt":
            return self.audit_cmake_lists(file_path)

        # Rule A: /.dockerenv is strictly prohibited in non-test source files
        if not is_test_file:
            violations.extend(
                self._audit_dockerenv_prohibited(
                    file_path=file_path,
                    ext=ext,
                    content=content,
                    lines=lines,
                )
            )

        if ext == ".sh":
            return violations

        # Rule B: Platform-exclusive stdlib imports banned at module top-level in Python
        if ext == ".py" and not is_test_file:
            violations.extend(
                self._audit_cross_os_top_level_imports(
                    file_path=file_path,
                    content=content,
                )
            )

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
            divider_pattern = reCompile(r'(//|#)\s*-{25,}')
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

            # 2b. Platform Schema SSoT Invariant: Ban legacy local schema imports/embeds in non-test code
            if not is_test_file and ext in (".go", ".rs", ".py"):
                if ext == ".py":
                    code_part = reSplit(r"(?:^|\s)#", line, maxsplit=1)[0]
                else:
                    code_part = reSub(r"(?<!:)//.*$", "", line)
                legacy_schema_patterns = (
                    "github.com/Bastien-Antigravity/flexible-logger/src/schemas/capnp",
                    "github.com/Bastien-Antigravity/notif-server/src/schemas/capnp",
                    'include_str!("../schema/capnp/logger.capnp")',
                    'include_str!("../schema/capnp/notifier.capnp")',
                )
                if any(pat in code_part for pat in legacy_schema_patterns):
                    violations.append({
                        "file": str(file_path),
                        "line": idx,
                        "rule": "LEGACY_LOCAL_SCHEMA_IMPORT",
                        "message": (
                            "Legacy local platform schema import/embed detected. "
                            "Import the canonical SSoT from microservice-toolbox/go/pkg/schemas/{logger,notifier} "
                            "or microservice_toolbox::contracts::{LOGGER_CAPNP_SCHEMA, NOTIFIER_CAPNP_SCHEMA}."
                        ),
                    })

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
                    "improved_transformer.py", "debloat_audit.py"
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
                        if reSearch(r'(?<![a-zA-Z0-9_])print\s*\(', stripped):
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
                            "message": "Ad-hoc directory traversal searching for VERSION.txt detected. Call appConfig.GetVersion() / app_config.get_version() instead."
                        })

        # 9. Python Granular Functional Import & camelCase Aliasing Check
        if ext == ".py" and not is_test_file and (strict_imports or "# strict:imports" in content[:500]):
            violations.extend(self.audit_python_imports(file_path, content=content))

        # 10. Anti-Defensive & Safe-By-Design Lean Code Check (Debloat Sentinel Integration)
        if not is_test_file and (strict_lean or "# strict:lean" in content[:500] or "// strict:lean" in content[:500]):
            try:
                from src.auditing.debloat_audit import audit_single_file_bloat
                bloat_findings = audit_single_file_bloat(file_path)
                category_to_rule = {
                    "Over-Defensive Config Paranoia": "DEBLOAT_CONFIG_PARANOIA",
                    "Multi-Fallback Config Chain": "DEBLOAT_MULTI_FALLBACK_CHAIN",
                    "Silent Exception Swallowing": "DEBLOAT_SILENT_EXCEPT_PASS",
                    "Defensive TOCTOU": "DEBLOAT_DEFENSIVE_TOCTOU",
                    "Concurrency Bloat": "DEBLOAT_CONCURRENCY_BLOAT",
                    "Architectural Duplication": "DEBLOAT_ARCHITECTURAL_DUPLICATION",
                    "Redundant Retry Loop": "DEBLOAT_REDUNDANT_RETRY_LOOP",
                    "Fail-Fast Violation": "DEBLOAT_FAIL_FAST_VIOLATION",
                }
                for bf in bloat_findings:
                    rule_code = category_to_rule.get(bf.get("category", ""), "DEBLOAT_VIOLATION")
                    violations.append({
                        "file": str(file_path),
                        "line": bf.get("line", 1),
                        "rule": rule_code,
                        "message": f"{bf.get('title', '')} — {bf.get('recommendation', '')}",
                    })
            except Exception:
                pass

        return violations

    # -----------------------------------------------------------------------------

    def audit_path(self, target_path: Path, strict_imports: bool = False, strict_lean: bool = False) -> typeList[typeDict[str, typeAny]]:
        """Audits a path (file or recursive directory)."""
        all_violations = []
        if target_path.is_file():
            return self.audit_file(target_path, strict_imports=strict_imports, strict_lean=strict_lean)

        for root, dirs, files in osWalk(target_path):
            dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS and not d.startswith(".")]
            for f in sorted(files):
                file_path = Path(root) / f
                all_violations.extend(self.audit_file(file_path, strict_imports=strict_imports, strict_lean=strict_lean))

        return all_violations

    # -----------------------------------------------------------------------------------------------

    def format_report(self, violations: typeList[typeDict[str, typeAny]]) -> str:
        """Formats violations list into human and agent readable report."""
        if not violations:
            return "✅ Code Compliance Audit: ALL CLEAR (100% compliant with ecosystem standards)."

        output = [
            f"❌ Code Compliance Audit: {len(violations)} violation(s) detected across target files:\n"
        ]
        # Group by file
        by_file: typeDict[str, typeList[typeDict[str, typeAny]]] = {}
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
        output.append("  9. Resolve dynamic version via the dedicated AppConfig method (appConfig.GetVersion() / app_config.get_version()).")
        output.append("  10. Use polyglot local-first workspace resolution instead of committing local path overrides: Go (root go.work, never replace => ../ in go.mod), Rust (root .cargo/config.toml paths, never path = '../' in Cargo.toml), Python (bootstrap_microservice / _bastien_workspace.pth, never -e ../ or file:// in manifests), C/C++ (FETCHCONTENT_SOURCE_DIR_* + GitHub FetchContent fallback, never unconditional add_subdirectory(../) or /Users/).")
        output.append("  11. Centralize platform Cap'n Proto schemas (logger.capnp, notifier.capnp) in microservice-toolbox (go/pkg/schemas/{logger,notifier} & schemas/platform/); never duplicate locally or import legacy local schema paths.")
        return "\n".join(output)

    # -----------------------------------------------------------------------------------------------

    def audit_staged(self) -> typeList[typeDict[str, typeAny]]:
        """Audits git staged files in the current repository / workspace."""
        all_violations = []
        try:
            res = subprocessRun(
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

# -----------------------------------------------------------------------------------------------

def main():
    """CLI runner for standalone audit execution."""
    from argparse import ArgumentParser as argparseArgumentParser
    parser = argparseArgumentParser(description="Mechanical Code Compliance Auditor")
    parser.add_argument("path", nargs="?", default=".", help="Target file or directory path to audit (defaults to current dir)")
    parser.add_argument("--staged", action="store_true", help="Audit only Git staged files (pre-commit mode)")
    parser.add_argument("--strict-imports", action="store_true", help="Enforce strict Python granular imports and camelCase aliasing")
    parser.add_argument("--strict-lean", action="store_true", help="Enforce anti-defensive & Safe-by-Design lean code rules")
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

        # Also auto-repair local relative replace directives in go.mod files
        fixed_go_mods = 0
        if target.is_file() and target.name == "go.mod":
            if auditor.fix_go_mod(target):
                fixed_go_mods += 1
        elif target.is_dir():
            for gm in target.glob("**/go.mod"):
                if any(p in gm.parts for p in EXCLUDED_DIRS):
                    continue
                if auditor.fix_go_mod(gm):
                    fixed_go_mods += 1
        if fixed_go_mods > 0:
            print(f"🔧 Cleaned local replace directives from {fixed_go_mods} go.mod file(s).\n")

    if args.staged:
        violations = auditor.audit_staged()
    else:
        target = Path(args.path).resolve()
        violations = auditor.audit_path(target, strict_imports=args.strict_imports, strict_lean=args.strict_lean)

    if args.json:
        print(jsonDumps(violations, indent=2))
    else:
        print(auditor.format_report(violations))

    sysExit(0 if len(violations) == 0 else 1)

if __name__ == "__main__":
    main()
