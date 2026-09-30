#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Unit tests for scaffold_microservice.py components.

DATA FLOW:
1. Input: Mock parameters for service name, language, port, description.
2. Logic: Exercises individual scaffolding generator functions in isolated temp directory.
3. Output: Assertions verifying generated file contents, structure, and constraints.
"""

import ast
import os
import shutil
import tempfile
import unittest
from pathlib import Path

# Add src to sys.path
BASE_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
import sys
if str(BASE_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_SCRIPTS_DIR))

from src.lifecycle.scaffold_microservice import (
    generate_go_scaffold,
    generate_python_scaffold,
    generate_rust_scaffold,
    generate_common_files,
    generate_bdd_spec,
    create_file,
    create_symlink,
)



class TestScaffoldUnits(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="scaffold_unit_"))
        self.brain_dir = Path(tempfile.mkdtemp(prefix="scaffold_brain_"))

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)
        shutil.rmtree(self.brain_dir, ignore_errors=True)

    def test_create_file_and_dry_run(self):
        """Verify create_file creates files and respects dry_run."""
        target = self.test_dir / "test.txt"
        create_file(target, "content", dry_run=True)
        self.assertFalse(target.exists())

        create_file(target, "content", dry_run=False)
        self.assertTrue(target.exists())
        self.assertEqual(target.read_text(encoding="utf-8"), "content")

    def test_create_symlink_and_dry_run(self):
        """Verify create_symlink establishes links and respects dry_run."""
        target = self.test_dir / "link.yaml"
        create_symlink(target, "../some/target.yaml", dry_run=True)
        self.assertFalse(target.exists())

        create_symlink(target, "../some/target.yaml", dry_run=False)
        self.assertTrue(target.is_symlink())
        self.assertEqual(os.readlink(target), "../some/target.yaml")

    def test_generate_go_scaffold(self):
        """Verify Go scaffolding creates cmd entrypoint, controller, interface, models, tests."""
        name = "test-go-service"
        port = 8888
        desc = "Test Go Service Description"

        generate_go_scaffold(self.test_dir, name, port, desc, dry_run=False)

        main_go = self.test_dir / f"cmd/{name}/main.go"
        self.assertTrue(main_go.exists(), "cmd/<name>/main.go must exist")
        main_content = main_go.read_text(encoding="utf-8")
        self.assertIn(f'BootstrapService("{name}")', main_content)
        self.assertIn(f'GetListenAddr("test_go_service")', main_content)
        self.assertIn("ESSENTIAL PROCESS", main_content)

        controller_go = self.test_dir / "src/core/controller.go"
        self.assertTrue(controller_go.exists(), "src/core/controller.go must exist")

        service_go = self.test_dir / "src/interfaces/interfaces.go"
        self.assertTrue(service_go.exists(), "src/interfaces/interfaces.go must exist")

        status_go = self.test_dir / "src/models/models.go"
        self.assertTrue(status_go.exists(), "src/models/models.go must exist")

        test_go = self.test_dir / "src/core/controller_test.go"
        self.assertTrue(test_go.exists(), "src/core/controller_test.go must exist")
        self.assertIn("TestController_Lifecycle", test_go.read_text(encoding="utf-8"))

        go_mod = self.test_dir / "go.mod"
        self.assertTrue(go_mod.exists(), "go.mod must exist")

        golangci = self.test_dir / ".golangci.yml"
        self.assertTrue(golangci.exists(), ".golangci.yml must exist")

    def test_generate_rust_scaffold(self):
        """Verify Rust scaffolding creates Cargo.toml, main.rs, core/mod.rs, and tests."""
        name = "test-rust-service"
        port = 9030
        desc = "Test Rust Service Description"

        generate_rust_scaffold(self.test_dir, name, port, desc, dry_run=False)

        cargo_toml = self.test_dir / "Cargo.toml"
        self.assertTrue(cargo_toml.exists(), "Cargo.toml must exist")
        self.assertIn(f'name = "{name}"', cargo_toml.read_text(encoding="utf-8"))

        main_rs = self.test_dir / "src/main.rs"
        self.assertTrue(main_rs.exists(), "src/main.rs must exist")
        self.assertIn("tokio::main", main_rs.read_text(encoding="utf-8"))

        core_rs = self.test_dir / "src/core/mod.rs"
        self.assertTrue(core_rs.exists(), "src/core/mod.rs must exist")

        test_rs = self.test_dir / "tests/test_basic.rs"
        self.assertTrue(test_rs.exists(), "tests/test_basic.rs must exist")

    def test_generate_python_scaffold(self):
        """Verify Python scaffolding creates main.py, controller, interface, model, and valid syntax."""
        name = "test-py-service"
        port = 9999
        desc = "Test Python Service Description"

        generate_python_scaffold(self.test_dir, name, port, desc, dry_run=False)

        main_py = self.test_dir / "main.py"
        self.assertTrue(main_py.exists(), "main.py must exist")
        main_content = main_py.read_text(encoding="utf-8")
        self.assertIn("microservice_toolbox.config.loader", main_content)
        self.assertIn(f'UniLog(app_name="{name}"', main_content)

        # Validate python syntax of all generated .py files
        for py_file in self.test_dir.rglob("*.py"):
            code = py_file.read_text(encoding="utf-8")
            try:
                ast.parse(code)
            except SyntaxError as e:
                self.fail(f"Generated file {py_file} has invalid Python syntax: {e}")

        reqs = self.test_dir / "requirements.txt"
        self.assertTrue(reqs.exists(), "requirements.txt must exist")
        self.assertIn("microservice-toolbox", reqs.read_text(encoding="utf-8"))

    def test_generate_common_files_go(self):
        """Verify common files generation for Go includes multi-stage Dockerfile and teleremote-network."""
        name = "test-go-common"
        generate_common_files(self.test_dir, name, lang="go", port=8090, desc="Go Desc", dry_run=False)

        dockerfile = (self.test_dir / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("FROM golang:1.25-alpine AS builder", dockerfile)
        self.assertIn("FROM alpine:3.20", dockerfile)
        self.assertIn("microservice-toolbox", dockerfile)

        compose = (self.test_dir / "docker-compose.yml").read_text(encoding="utf-8")
        self.assertIn("teleremote-network", compose)
        self.assertIn("external: true", compose)

        agents_md = (self.test_dir / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn(f"# AGENTS.md: {name}", agents_md)
        self.assertIn("go test -v ./...", agents_md)

        self.assertTrue((self.test_dir / "AI-Init.md").exists(), "AI-Init.md must exist")
        self.assertTrue((self.test_dir / "AI-Project-DNA.md").exists(), "AI-Project-DNA.md must exist")
        self.assertTrue((self.test_dir / "AI-Session-State.md").exists(), "AI-Session-State.md must exist")
        self.assertTrue((self.test_dir / "TODO.md").exists(), "TODO.md must exist")

        makefile = self.test_dir / "Makefile"
        self.assertTrue(makefile.exists(), "Makefile must exist for compiled languages")

        standalone = self.test_dir / "standalone.yaml"
        self.assertTrue(standalone.is_symlink())
        self.assertEqual(os.readlink(standalone), "../docker-deployment/modes/local/config/native.yaml")

    def test_generate_common_files_python(self):
        """Verify Python Dockerfile includes multi-stage build and microservice-toolbox installation."""
        name = "test-py-common"
        generate_common_files(self.test_dir, name, lang="python", port=8092, desc="Py Desc", dry_run=False)

        dockerfile = (self.test_dir / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("FROM golang:1.25-alpine AS go-builder", dockerfile)
        self.assertIn("FROM python:3.12-alpine", dockerfile)
        self.assertIn("libunilog.so", dockerfile)
        self.assertIn("git clone --depth 1 -b develop https://github.com/Bastien-Antigravity/microservice-toolbox.git", dockerfile)
        self.assertIn("pip install --no-cache-dir /tmp/microservice-toolbox/python", dockerfile)

        # Makefile should NOT be generated for pure Python
        self.assertFalse((self.test_dir / "Makefile").exists())

    def test_generate_common_files_rust(self):
        """Verify Rust common files generation includes multi-stage Dockerfile and cargo Makefile."""
        name = "test-rs-common"
        generate_common_files(self.test_dir, name, lang="rust", port=9030, desc="Rust Desc", dry_run=False)

        dockerfile = (self.test_dir / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("FROM rust:1.80-alpine AS builder", dockerfile)
        self.assertIn("FROM alpine:3.20", dockerfile)

        makefile = (self.test_dir / "Makefile").read_text(encoding="utf-8")
        self.assertIn("cargo build --release", makefile)
        self.assertIn("cargo test", makefile)

    def test_generate_bdd_spec(self):
        """Verify BDD spec note creation with frontmatter and Gherkin scenarios."""
        name = "test-bdd-service"
        generate_bdd_spec(self.brain_dir, name, "BDD Description", dry_run=False)

        feat_file = self.brain_dir / "02-Business-BDD" / "02-Behavior-Specs" / name / "FEAT-001-Initialization.md"
        self.assertTrue(feat_file.exists())
        content = feat_file.read_text(encoding="utf-8")
        self.assertTrue(content.startswith("---"))
        self.assertIn(f"microservice: {name}", content)
        self.assertIn("Scenario 1: Clean Startup with Valid Configuration", content)
        self.assertIn("Scenario 2: Graceful Termination on OS Signal", content)


if __name__ == "__main__":
    unittest.main()
