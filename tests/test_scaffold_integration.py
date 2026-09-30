#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Integration tests for the complete microservice scaffolding lifecycle in 08-Base-Scripts.

DATA FLOW:
1. Input: Temporary directory targets, mock service specifications.
2. Logic: Executes end-to-end scaffolding for Go and Python microservices,
   validating AST syntax, YAML structure, symlink resolution, and mandatory file sets.
3. Output: Assertions verifying that scaffolded repositories are structurally and syntactically sound.
"""

import ast
import io
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
import yaml

BASE_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(BASE_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_SCRIPTS_DIR))

from src.lifecycle.scaffold_microservice import (
    generate_go_scaffold,
    generate_python_scaffold,
    generate_common_files,
    generate_bdd_spec,
)


class TestScaffoldIntegration(unittest.TestCase):
    def setUp(self):
        self.workspace_tmp = Path(tempfile.mkdtemp(prefix="scaffold_integ_ws_"))
        self.brain_tmp = self.workspace_tmp / "obsidian-brain"
        self.brain_tmp.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.workspace_tmp, ignore_errors=True)

    def test_full_go_microservice_scaffolding(self):
        """End-to-end test of Go microservice scaffolding."""
        svc_name = "market-scanner"
        svc_dir = self.workspace_tmp / svc_name
        port = 8096
        desc = "Real-time market scanning and anomaly detection engine"

        # Execute generators
        generate_go_scaffold(svc_dir, svc_name, port, desc, dry_run=False)
        generate_common_files(svc_dir, svc_name, "go", port, desc, dry_run=False)
        generate_bdd_spec(self.brain_tmp, svc_name, desc, dry_run=False)

        # 1. Mandatory Root Files Verification
        expected_files = [
            svc_dir / "Dockerfile",
            svc_dir / "docker-compose.yml",
            svc_dir / "AGENTS.md",
            svc_dir / "AI-Session-State.md",
            svc_dir / "README.md",
            svc_dir / "VERSION.txt",
            svc_dir / "Makefile",
            svc_dir / ".gitignore",
            svc_dir / "go.mod",
            svc_dir / ".golangci.yml",
            svc_dir / f"cmd/{svc_name}/main.go",
            svc_dir / "src/core/controller.go",
            svc_dir / "src/interfaces/interfaces.go",
            svc_dir / "src/models/models.go",
            svc_dir / "quick-overview/Architecture-Overview.md",
            svc_dir / "quick-overview/Features-Behavior.md",
            svc_dir / "quick-overview/Testing-Playbook.md",
            svc_dir / "quick-overview/General-Misc.md",
            svc_dir / ".github/workflows/ci.yml",
            svc_dir / ".github/dependabot.yml",
        ]
        for f in expected_files:
            self.assertTrue(f.exists(), f"Mandatory file missing: {f}")

        # 2. Symlink verification
        symlink = svc_dir / "standalone.yaml"
        self.assertTrue(symlink.is_symlink(), "standalone.yaml must be a symlink")
        self.assertEqual(os.readlink(symlink), "../docker-deployment/modes/local/config/native.yaml")

        # 3. YAML Validation (docker-compose.yml, .golangci.yml)
        compose_content = (svc_dir / "docker-compose.yml").read_text(encoding="utf-8")
        compose_data = yaml.safe_load(compose_content)
        self.assertIn(svc_name, compose_data["services"])
        self.assertIn("teleremote-network", compose_data["networks"])
        self.assertEqual(compose_data["networks"]["teleremote-network"]["name"], "teleremote-network")
        self.assertTrue(compose_data["networks"]["teleremote-network"]["external"])

        # 4. Dockerfile validation (Multi-stage Go)
        dockerfile = (svc_dir / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("FROM golang:1.25-alpine AS builder", dockerfile)
        self.assertIn("FROM alpine:3.20", dockerfile)
        self.assertIn("microservice-toolbox.git", dockerfile)

        # 5. BDD Feature Note validation
        bdd_file = self.brain_tmp / "02-Business-BDD" / "02-Behavior-Specs" / svc_name / "FEAT-001-Initialization.md"
        self.assertTrue(bdd_file.exists(), "BDD FEAT-001 note must exist")
        bdd_content = bdd_file.read_text(encoding="utf-8")
        self.assertIn(f"microservice: {svc_name}", bdd_content)
        self.assertIn("Scenario 1: Clean Startup with Valid Configuration", bdd_content)

    def test_full_python_microservice_scaffolding(self):
        """End-to-end test of Python microservice scaffolding."""
        svc_name = "signal-analyzer"
        svc_dir = self.workspace_tmp / svc_name
        port = 8097
        desc = "Deep learning time-series signal analysis worker"

        # Execute generators
        generate_python_scaffold(svc_dir, svc_name, port, desc, dry_run=False)
        generate_common_files(svc_dir, svc_name, "python", port, desc, dry_run=False)
        generate_bdd_spec(self.brain_tmp, svc_name, desc, dry_run=False)

        # 1. Mandatory Files
        expected_files = [
            svc_dir / "Dockerfile",
            svc_dir / "docker-compose.yml",
            svc_dir / "AGENTS.md",
            svc_dir / "AI-Session-State.md",
            svc_dir / "README.md",
            svc_dir / "VERSION.txt",
            svc_dir / ".gitignore",
            svc_dir / "main.py",
            svc_dir / "requirements.txt",
            svc_dir / "src/core/controller.py",
            svc_dir / "src/interfaces/service.py",
            svc_dir / "src/models/status.py",
            svc_dir / "tests/test_basic.py",
        ]
        for f in expected_files:
            self.assertTrue(f.exists(), f"Mandatory Python file missing: {f}")

        # Pure Python should NOT have a Makefile
        self.assertFalse((svc_dir / "Makefile").exists())

        # 2. Python Syntax AST Validation
        py_files = list(svc_dir.rglob("*.py"))
        self.assertGreaterEqual(len(py_files), 5, "Should have generated at least 5 Python files")
        for py_path in py_files:
            code = py_path.read_text(encoding="utf-8")
            try:
                tree = ast.parse(code, filename=str(py_path))
                self.assertIsNotNone(tree)
            except SyntaxError as e:
                self.fail(f"Syntax error in scaffolded Python file {py_path}: {e}")

        # 3. Dockerfile Multi-Stage & Internal Toolbox Installation Validation
        dockerfile = (svc_dir / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("FROM golang:1.25-alpine AS go-builder", dockerfile)
        self.assertIn("FROM python:3.12-alpine", dockerfile)
        self.assertIn("libunilog.so", dockerfile)
        self.assertIn("git clone --depth 1 -b develop https://github.com/Bastien-Antigravity/microservice-toolbox.git", dockerfile)
        self.assertIn("pip install --no-cache-dir /tmp/microservice-toolbox/python", dockerfile)

        # 4. YAML Validation
        compose_content = (svc_dir / "docker-compose.yml").read_text(encoding="utf-8")
        compose_data = yaml.safe_load(compose_content)
        self.assertEqual(compose_data["services"][svc_name]["ports"], [f"${{HOST_IP:-127.0.0.1}}:{port}:{port}"])
        self.assertEqual(compose_data["networks"]["teleremote-network"]["name"], "teleremote-network")


if __name__ == "__main__":
    unittest.main()
