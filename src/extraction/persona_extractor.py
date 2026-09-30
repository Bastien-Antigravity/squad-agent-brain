#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Scans the fleet repositories for Go, Rust, and Python code, extracting structural patterns
(AST, Regex matching of structs, traits, interfaces) to build persona context for the AI RAG engine.

DATA FLOW:
1. Bootstraps the virtual environment.
2. Acquires a cross-platform process lock (via microservice-toolbox) to prevent concurrent runs.
3. Walks the directory structure to identify Go, Rust, and Python files.
4. Parses files and extracts metrics (imports, unwraps, exceptions, goroutines).
5. Writes Markdown RAG profiles to the Core KMS telemetry store.
6. Prunes old run profiles (keeping the latest 3).

KEY PARAMETERS:
- repo_path: Workspace root to scan.
- output_dir: Destination folder for telemetry reports.
"""

import os
import ast
import re
import collections
import argparse
import datetime
import json
import time
import sys
from pathlib import Path
from lib.bootstrap import ensure_virtualenv, prepend_venv_bin, ensure_import_paths
from microservice_toolbox.utils.process_lock import prevent_double_start

# -----------------------------------------------------------------------------
# Extractor Classes
# -----------------------------------------------------------------------------

class PythonExtractor(ast.NodeVisitor):
    def __init__(self):
        self.imports = collections.Counter()
        self.exceptions_caught = collections.Counter()
        self.logging_calls = collections.Counter()
        self.class_names = []
        self.func_names = []
        self.async_funcs = 0

    def visit_Import(self, node):
        for alias in node.names:
            self.imports[alias.name] += 1
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        if node.module:
            self.imports[node.module] += 1
        self.generic_visit(node)

    def visit_ClassDef(self, node):
        self.class_names.append(node.name)
        self.generic_visit(node)

    def visit_FunctionDef(self, node):
        self.func_names.append(node.name)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node):
        self.async_funcs += 1
        self.func_names.append(node.name)
        self.generic_visit(node)

    def visit_ExceptHandler(self, node):
        if node.type:
            names = self._get_exception_names(node.type)
            for name in names:
                self.exceptions_caught[name] += 1
        self.generic_visit(node)

    def _get_exception_names(self, node):
        if isinstance(node, ast.Name):
            return [node.id]
        elif isinstance(node, ast.Attribute):
            val = getattr(node.value, 'id', '')
            if val:
                return [f"{val}.{node.attr}"]
            return [node.attr]
        elif isinstance(node, ast.Tuple):
            res = []
            for elt in node.elts:
                res.extend(self._get_exception_names(elt))
            return res
        return []

    def visit_Call(self, node):
        if isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name) and node.func.value.id in ('log', 'logger', 'logging'):
                self.logging_calls[node.func.attr] += 1
            elif isinstance(node.func.value, ast.Attribute) and getattr(node.func.value, 'attr', None) in ('logger', 'log'):
                self.logging_calls[node.func.attr] += 1
        self.generic_visit(node)


class GoExtractor:
    def __init__(self):
        self.interfaces = collections.Counter()
        self.structs = collections.Counter()
        self.goroutines = 0
        self.panics = 0
        self.error_checks = 0

    def parse(self, content):
        for match in re.finditer(r'type\s+([A-Z]\w*)\s+interface', content):
            self.interfaces[match.group(1)] += 1
        for match in re.finditer(r'type\s+([A-Z]\w*)\s+struct', content):
            self.structs[match.group(1)] += 1
        self.goroutines += len(re.findall(r'go\s+func', content))
        self.panics += len(re.findall(r'panic\(', content))
        self.error_checks += len(re.findall(r'if\s+err\s*!=\s*nil', content))


class RustExtractor:
    def __init__(self):
        self.traits = collections.Counter()
        self.structs = collections.Counter()
        self.unwraps = 0
        self.matches = 0

    def parse(self, content):
        for match in re.finditer(r'(?:pub(?:\([^)]+\))?\s+)?trait\s+([A-Z]\w*)', content):
            self.traits[match.group(1)] += 1
        for match in re.finditer(r'(?:pub(?:\([^)]+\))?\s+)?struct\s+([A-Z]\w*)', content):
            self.structs[match.group(1)] += 1
        self.unwraps += len(re.findall(r'\.unwrap\(\)', content))
        self.matches += len(re.findall(r'match\s+', content))


def extract_personas(repo_path, output_dir, is_daemon, logger=None):
    os.makedirs(output_dir, exist_ok=True)
    start_time = time.time()
    scanned_files = {"python": 0, "go": 0, "rust": 0}

    py_ext = PythonExtractor()
    go_ext = GoExtractor()
    rs_ext = RustExtractor()

    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ('venv', '.venv', '__pycache__', 'node_modules', 'target', 'dist', 'build', 'vendor')]
        
        for file in files:
            filepath = os.path.join(root, file)
            try:
                if os.path.getsize(filepath) > 1024 * 1024:
                    continue
                if file.endswith('.py'):
                    scanned_files["python"] += 1
                    with open(filepath, 'r', encoding='utf-8') as f:
                        tree = ast.parse(f.read(), filename=filepath)
                        py_ext.visit(tree)
                elif file.endswith('.go'):
                    scanned_files["go"] += 1
                    with open(filepath, 'r', encoding='utf-8') as f:
                        go_ext.parse(f.read())
                elif file.endswith('.rs'):
                    scanned_files["rust"] += 1
                    with open(filepath, 'r', encoding='utf-8') as f:
                        rs_ext.parse(f.read())
            except Exception:
                pass

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    py_content = [
        f"# 🐍 Python Persona RAG Context",
        f"*Generated: {datetime.datetime.now().isoformat()}*",
        f"",
        f"> [!WARNING]",
        f"> This is static telemetry showing current codebase statistics. It does NOT define standard rules.",
        f"> Always prioritize the hard-coded rules in `07-Core-KMS/Role-Prompts/03-Developer/Squad/Python-Integration-Specialist.md`.",
        f"",
        f"## ⚙️ Architecture Trends",
        f"- **Async Adoptions**: {py_ext.async_funcs} asynchronous functions defined.",
        f"## 🔥 Core Dependencies (Top 10)",
        "\n".join([f"- `{imp}` ({c} times)" for imp, c in py_ext.imports.most_common(10)]),
        f"## 🛡️ Error Handling (Top 10)",
        "\n".join([f"- `except {exc}:` ({c} times)" for exc, c in py_ext.exceptions_caught.most_common(10)]),
        f"## 📝 Logging Culture (Top 10)",
        "\n".join([f"- `logger.{meth}()` ({c} times)" for meth, c in py_ext.logging_calls.most_common(10)])
    ]
    with open(os.path.join(output_dir, f"persona_python_{timestamp}.md"), 'w', encoding='utf-8') as f:
        f.write("\n".join(py_content))

    go_content = [
        f"# 🐹 Go Persona RAG Context",
        f"*Generated: {datetime.datetime.now().isoformat()}*",
        f"",
        f"> [!WARNING]",
        f"> This is static telemetry showing current codebase statistics. It does NOT define standard rules.",
        f"> Always prioritize the hard-coded rules in `07-Core-KMS/Role-Prompts/03-Developer/Squad/Go-Systems-Specialist.md`.",
        f"",
        f"## ⚙️ Architecture Trends",
        f"- **Standard Error Checks (`if err != nil`)**: {go_ext.error_checks}",
        f"- **Panics**: {go_ext.panics}",
        f"- **Goroutines (`go func`)**: {go_ext.goroutines}",
        f"## 🧩 Top Interfaces",
        "\n".join([f"- `type {i} interface`" for i, c in go_ext.interfaces.most_common(10)]),
        f"## 🏗️ Top Structs",
        "\n".join([f"- `type {s} struct`" for s, c in go_ext.structs.most_common(10)])
    ]
    with open(os.path.join(output_dir, f"persona_go_{timestamp}.md"), 'w', encoding='utf-8') as f:
        f.write("\n".join(go_content))

    rs_content = [
        f"# 🦀 Rust Persona RAG Context",
        f"*Generated: {datetime.datetime.now().isoformat()}*",
        f"",
        f"> [!WARNING]",
        f"> This is static telemetry showing current codebase statistics. It does NOT define standard rules.",
        f"> Always prioritize the hard-coded rules in `07-Core-KMS/Role-Prompts/03-Developer/Squad/Rust-Safety-Specialist.md`.",
        f"",
        f"## ⚙️ Architecture Trends",
        f"- **Pattern Matching (`match`)**: {rs_ext.matches}",
        f"- **Unwraps (`.unwrap()`)**: {rs_ext.unwraps} (Hint: try to minimize these!)",
        f"## 🧩 Top Traits",
        "\n".join([f"- `pub trait {t}`" for t, c in rs_ext.traits.most_common(10)]),
        f"## 🏗️ Top Structs",
        "\n".join([f"- `struct {s}`" for s, c in rs_ext.structs.most_common(10)])
    ]
    with open(os.path.join(output_dir, f"persona_rust_{timestamp}.md"), 'w', encoding='utf-8') as f:
        f.write("\n".join(rs_content))

    try:
        for lang in ['python', 'go', 'rust']:
            files = [f for f in os.listdir(output_dir) if f.startswith(f"persona_{lang}_") and f.endswith(".md")]
            files.sort(reverse=True)
            for old_file in files[3:]:
                os.remove(os.path.join(output_dir, old_file))
    except Exception:
        pass

    duration_ms = int((time.time() - start_time) * 1000)
    manifest = {
        "timestamp": timestamp,
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "status": "ready",
        "duration_ms": duration_ms,
        "files_scanned": scanned_files,
        "artifacts": {
            "python": f"persona_python_{timestamp}.md",
            "go": f"persona_go_{timestamp}.md",
            "rust": f"persona_rust_{timestamp}.md"
        },
        "metrics_summary": {
            "python": {
                "async_functions": py_ext.async_funcs,
                "total_classes": len(py_ext.class_names),
                "total_functions": len(py_ext.func_names),
                "top_imports": dict(py_ext.imports.most_common(10)),
                "top_exceptions": dict(py_ext.exceptions_caught.most_common(10)),
                "top_logging_calls": dict(py_ext.logging_calls.most_common(10))
            },
            "go": {
                "error_checks": go_ext.error_checks,
                "panics": go_ext.panics,
                "goroutines": go_ext.goroutines,
                "top_interfaces": dict(go_ext.interfaces.most_common(10)),
                "top_structs": dict(go_ext.structs.most_common(10))
            },
            "rust": {
                "matches": rs_ext.matches,
                "unwraps": rs_ext.unwraps,
                "top_traits": dict(rs_ext.traits.most_common(10)),
                "top_structs": dict(rs_ext.structs.most_common(10))
            }
        }
    }

    manifest_path = os.path.join(output_dir, "manifest.json")
    with open(manifest_path, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2)

    flag_path = os.path.join(output_dir, ".persona_ready")
    with open(flag_path, 'w', encoding='utf-8') as f:
        f.write(timestamp)
    
    total_files = sum(scanned_files.values())
    if logger:
        logger.info(f"Persona Extraction complete ({duration_ms}ms, {total_files} files scanned). Manifest saved to {manifest_path}")
    if not is_daemon:
        print(f"✅ Persona Extraction complete ({duration_ms}ms, {total_files} files). Manifest: {manifest_path}")


def main():
    script_dir = Path(__file__).resolve().parent
    vault_root_path = ensure_virtualenv(str(script_dir))
    prepend_venv_bin(vault_root_path)
    ensure_import_paths(script_dir, vault_root_path)

    parser = argparse.ArgumentParser(description="Fleet Persona Extractor")
    parser.add_argument("--daemon", action="store_true", help="Run silently in background")
    args = parser.parse_args()

    prevent_double_start("persona_extractor")

    from lib.orchestration_lib import resolve_vault_and_workspace, get_logger
    logger = get_logger("PersonaExtractor")
    vault_root, workspace_root = resolve_vault_and_workspace(__file__)
    
    output_dir = os.path.join(str(vault_root), "07-Core-KMS", "quick-overview", "ast-patterns")
    output_dir = os.path.abspath(output_dir)

    if logger:
        logger.info(f"Initiating AST persona extraction across {workspace_root}...")
    extract_personas(str(workspace_root), output_dir, args.daemon, logger=logger)


if __name__ == '__main__':
    main()
