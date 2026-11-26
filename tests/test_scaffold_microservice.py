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
from unittest.mock import patch

# Add src to sys.path
SQUAD_AGENT_DIR = Path(__file__).resolve().parent.parent
import sys
if str(SQUAD_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(SQUAD_AGENT_DIR))

from src.lifecycle.scaffold_microservice import (
    generate_go_scaffold,
    generate_python_scaffold,
    generate_rust_scaffold,
    generate_cpp_scaffold,
    generate_common_files,
    generate_bdd_spec,
    create_file,
    create_symlink,
    resolve_workspace_root,
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

        contracts_go = self.test_dir / "src/rest/contracts.go"
        rest_handler_go = self.test_dir / "src/rest/rest_handler.go"
        rest_test_go = self.test_dir / "src/rest/rest_handler_test.go"
        mfe_js = self.test_dir / "src/rest/mfe.js"
        self.assertTrue(contracts_go.exists(), "src/rest/contracts.go must exist")
        self.assertTrue(rest_handler_go.exists(), "src/rest/rest_handler.go must exist")
        self.assertTrue(rest_test_go.exists(), "src/rest/rest_handler_test.go must exist")
        self.assertTrue(mfe_js.exists(), "src/rest/mfe.js must exist")
        mfe_js_text = mfe_js.read_text(encoding="utf-8")
        self.assertIn("BastienMFEContracts", mfe_js_text)
        self.assertIn("openmfe-tabs-bar", mfe_js_text)
        self.assertNotIn("<style>", mfe_js_text)
        self.assertIn("/api/v1/contracts", rest_handler_go.read_text(encoding="utf-8"))

    def test_generate_rust_scaffold(self):
        """Verify Rust scaffolding creates Cargo.toml, main.rs, contracts.rs, core/mod.rs, and tests."""
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

        contracts_rs = self.test_dir / "src/contracts.rs"
        self.assertTrue(contracts_rs.exists(), "src/contracts.rs must exist")
        self.assertIn("ExchangeContract", contracts_rs.read_text(encoding="utf-8"))

        core_rs = self.test_dir / "src/core/mod.rs"
        self.assertTrue(core_rs.exists(), "src/core/mod.rs must exist")

        test_rs = self.test_dir / "tests/test_basic.rs"
        self.assertTrue(test_rs.exists(), "tests/test_basic.rs must exist")

    def test_generate_python_scaffold(self):
        """Verify Python scaffolding creates main.py, controller, rest contracts, mfe.js, and valid syntax."""
        name = "test-py-service"
        port = 9999
        desc = "Test Python Service Description"

        generate_python_scaffold(self.test_dir, name, port, desc, dry_run=False)

        main_py = self.test_dir / "main.py"
        self.assertTrue(main_py.exists(), "main.py must exist")
        main_content = main_py.read_text(encoding="utf-8")
        self.assertIn("microservice_toolbox.config.loader", main_content)
        self.assertIn(f'unilogUniLog(app_name="{name}"', main_content)
        self.assertIn("build_service_contracts", main_content)

        contracts_py = self.test_dir / "src/rest/contracts.py"
        rest_py = self.test_dir / "src/rest/rest_handler.py"
        mfe_js = self.test_dir / "src/rest/mfe.js"
        self.assertTrue(contracts_py.exists(), "src/rest/contracts.py must exist")
        self.assertTrue(rest_py.exists(), "src/rest/rest_handler.py must exist")
        self.assertTrue(mfe_js.exists(), "src/rest/mfe.js must exist")
        self.assertIn("/api/v1/contracts", rest_py.read_text(encoding="utf-8"))

        # Validate python syntax of all generated .py files
        for py_file in self.test_dir.rglob("*.py"):
            code = py_file.read_text(encoding="utf-8")
            try:
                ast.parse(code)
            except SyntaxError as e:
                self.fail(f"Generated file {py_file} has invalid Python syntax: {e}")

        reqs = self.test_dir / "requirements.txt"
        self.assertTrue(reqs.exists(), "requirements.txt must exist")
        reqs_text = reqs.read_text(encoding="utf-8")
        self.assertIn(
            "microservice-toolbox @ git+https://github.com/Bastien-Antigravity/microservice-toolbox.git@develop#subdirectory=python",
            reqs_text,
        )
        self.assertIn(
            "unilog @ git+https://github.com/Bastien-Antigravity/universal-logger.git@develop#subdirectory=unilog/python",
            reqs_text,
        )

    def test_generate_cpp_scaffold_and_common_files(self):
        """Verify C++ scaffolding creates main.cpp, controller.hpp, contracts.hpp, tests, Makefile, and Dockerfile."""
        name = "test-cpp-service"
        port = 9055
        desc = "Low latency C++ feed handler"

        generate_cpp_scaffold(self.test_dir, name, port, desc, dry_run=False)
        generate_common_files(self.test_dir, name, lang="cpp", port=port, desc=desc, dry_run=False)

        self.assertTrue((self.test_dir / "src/main.cpp").exists())
        self.assertTrue((self.test_dir / "src/contracts/contracts.hpp").exists())
        self.assertTrue((self.test_dir / "src/core/controller.hpp").exists())
        self.assertTrue((self.test_dir / "tests/test_basic.cpp").exists())

        contracts_hpp = (self.test_dir / "src/contracts/contracts.hpp").read_text(encoding="utf-8")
        self.assertIn("microservice_toolbox/spec/contracts.hpp", contracts_hpp)
        self.assertIn("ExchangeContract", contracts_hpp)

        main_cpp = (self.test_dir / "src/main.cpp").read_text(encoding="utf-8")
        self.assertIn("SpecPublisher::PublishWithLifecycle", main_cpp)

        makefile = (self.test_dir / "Makefile").read_text(encoding="utf-8")
        self.assertIn("-std=c++17", makefile)
        dockerfile = (self.test_dir / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("FROM alpine:3.20 AS cpp-builder", dockerfile)

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
        self.assertTrue(standalone.exists(), "standalone.yaml symlink must not be dangling")
        self.assertTrue(
            os.readlink(standalone).endswith("docker-deployment/modes/local/config/native.yaml"),
            f"Unexpected standalone.yaml symlink target: {os.readlink(standalone)}",
        )

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
        self.assertIn("FROM rust:1.91-alpine AS builder", dockerfile)
        self.assertIn("FROM alpine:3.20", dockerfile)

        makefile = (self.test_dir / "Makefile").read_text(encoding="utf-8")
        self.assertIn("cargo build --release", makefile)
        self.assertIn("cargo test", makefile)

    def test_all_scaffolded_languages_pass_strict_compliance_auditor(self):
        """Golden Scaffolder Gate: every scaffolded language must pass ComplianceAuditor strict checks with 0 violations."""
        from src.auditing.validate_compliance import ComplianceAuditor

        auditor = ComplianceAuditor(workspace_root=self.test_dir)
        generators = {
            "go": generate_go_scaffold,
            "rust": generate_rust_scaffold,
            "python": generate_python_scaffold,
            "cpp": generate_cpp_scaffold,
        }
        for idx, (lang, gen_fn) in enumerate(generators.items()):
            svc_name = f"golden-{lang}-svc"
            svc_dir = self.test_dir / svc_name
            port = 18200 + idx
            gen_fn(svc_dir, svc_name, port, f"Golden {lang} service", dry_run=False)
            generate_common_files(svc_dir, svc_name, lang=lang, port=port, desc=f"Golden {lang} service", dry_run=False)
            violations = auditor.audit_path(svc_dir, strict_imports=True, strict_lean=True)
            self.assertEqual(
                violations,
                [],
                f"Golden {lang} scaffold failed strict compliance audit:\n{auditor.format_report(violations)}",
            )

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

    def test_runtime_stage_oci_source_label_all_languages(self):
        """Verify final runtime stage in all 4 Dockerfiles includes OCI source label."""
        for lang in ("go", "rust", "python", "cpp"):
            svc_name = f"oci-{lang}-svc"
            svc_dir = self.test_dir / lang
            generate_common_files(svc_dir, svc_name, lang=lang, port=8120, desc="OCI label test", dry_run=False)
            dockerfile = (svc_dir / "Dockerfile").read_text(encoding="utf-8")
            stages = dockerfile.split("\nFROM ")
            self.assertGreaterEqual(len(stages), 2, f"{lang} Dockerfile must be multi-stage")
            runtime_stage = stages[-1]
            self.assertIn(
                f'LABEL org.opencontainers.image.source="https://github.com/Bastien-Antigravity/{svc_name}"',
                runtime_stage,
                f"{lang} Dockerfile final runtime stage missing OCI source label",
            )

    def test_generate_common_files_fleet_mode_docker(self):
        """Verify --fleet-mode docker symlinks standalone.yaml to host-bridge.yaml (127.0.0.2)."""
        name = "test-docker-bridge-svc"
        generate_common_files(
            self.test_dir,
            name,
            lang="go",
            port=8125,
            desc="Docker host-bridge test",
            dry_run=False,
            fleet_mode="docker",
        )
        standalone = self.test_dir / "standalone.yaml"
        self.assertTrue(standalone.is_symlink())
        self.assertTrue(standalone.exists(), "host-bridge standalone.yaml symlink must not be dangling")
        self.assertTrue(
            os.readlink(standalone).endswith("docker-deployment/modes/docker/config/host-bridge.yaml"),
            f"Unexpected docker fleet-mode symlink target: {os.readlink(standalone)}",
        )

    def test_bastien_core_root_resolution_and_python_bootstrap(self):
        """Verify BASTIEN_CORE_ROOT overrides workspace root resolution and Python main.py bootstrap."""
        mock_core = self.test_dir / "mock-core"
        (mock_core / "docker-deployment" / "modes" / "local" / "config").mkdir(parents=True, exist_ok=True)
        (mock_core / "docker-deployment" / "modes" / "local" / "config" / "native.yaml").write_text(
            "common:\n  name: common\n", encoding="utf-8"
        )
        (mock_core / "microservice-toolbox" / "python").mkdir(parents=True, exist_ok=True)

        with patch.dict(os.environ, {"BASTIEN_CORE_ROOT": str(mock_core)}, clear=False):
            resolved = resolve_workspace_root()
        self.assertEqual(resolved, mock_core.resolve())

        py_dir = self.test_dir / "external-py-svc"
        generate_python_scaffold(py_dir, "external-py-svc", 8126, "External L4 Python service", dry_run=False, layer="L4")
        generate_common_files(py_dir, "external-py-svc", lang="python", port=8126, desc="External L4 Python service", dry_run=False, layer="L4")
        main_py = (py_dir / "main.py").read_text(encoding="utf-8")
        self.assertIn("BASTIEN_CORE_ROOT", main_py)
        self.assertIn("microservice-toolbox", main_py)
        self.assertIn("bootstrap_microservice", main_py)
        ast.parse(main_py)
        self.assertEqual((py_dir / "VERSION.txt").read_text(encoding="utf-8").strip(), "0.0.1")

    def test_external_vs_core_go_github_imports_and_makefile(self):
        """Verify external Go scaffolds omit local replace directives and use v0.0.1 + GOPRIVATE."""
        # 1. External domain directory (outside workspace_root)
        ext_go_dir = self.test_dir / "external-domain" / "ext-go-svc"
        generate_go_scaffold(ext_go_dir, "ext-go-svc", 8301, "External Go service", dry_run=False, layer="L4")
        generate_common_files(ext_go_dir, "ext-go-svc", lang="go", port=8301, desc="External Go service", dry_run=False, layer="L4")

        ext_go_mod = (ext_go_dir / "go.mod").read_text(encoding="utf-8")
        self.assertNotIn("replace (", ext_go_mod)
        self.assertNotIn("=>", ext_go_mod)
        self.assertIn("github.com/Bastien-Antigravity/microservice-toolbox v0.0.1", ext_go_mod)
        self.assertIn("github.com/Bastien-Antigravity/universal-logger v0.0.1", ext_go_mod)
        self.assertNotIn("v0.0.0", ext_go_mod)

        ext_makefile = (ext_go_dir / "Makefile").read_text(encoding="utf-8")
        self.assertIn("GOPRIVATE=github.com/Bastien-Antigravity/*", ext_makefile)
        self.assertEqual((ext_go_dir / "VERSION.txt").read_text(encoding="utf-8").strip(), "0.0.1")

        # 2. Core workspace directory (inside mocked workspace_root)
        mock_core = self.test_dir / "mock-core-ws"
        (mock_core / "docker-deployment" / "modes" / "local" / "config").mkdir(parents=True, exist_ok=True)
        (mock_core / "docker-deployment" / "modes" / "local" / "config" / "native.yaml").write_text(
            "common:\n  name: common\n", encoding="utf-8"
        )
        (mock_core / "microservice-toolbox" / "python").mkdir(parents=True, exist_ok=True)
        (mock_core / "go.work").write_text("go 1.25\n\nuse (\n\t./config-server\n)\n", encoding="utf-8")

        core_go_dir = mock_core / "core-go-svc"
        with patch.dict(os.environ, {"BASTIEN_CORE_ROOT": str(mock_core)}, clear=False):
            generate_go_scaffold(core_go_dir, "core-go-svc", 8302, "Core Go service", dry_run=False)
            generate_common_files(core_go_dir, "core-go-svc", lang="go", port=8302, desc="Core Go service", dry_run=False)

        core_go_mod = (core_go_dir / "go.mod").read_text(encoding="utf-8")
        self.assertNotIn("replace (", core_go_mod)
        self.assertNotIn("=>", core_go_mod)
        self.assertIn("github.com/Bastien-Antigravity/microservice-toolbox v0.0.1", core_go_mod)
        self.assertNotIn("v0.0.0", core_go_mod)

        # Verify registration in go.work
        go_work_content = (mock_core / "go.work").read_text(encoding="utf-8")
        self.assertIn("./core-go-svc", go_work_content)

    def test_rust_github_cargo_toml_and_version(self):
        """Verify Rust scaffold Cargo.toml pins v0.0.1 and GitHub develop branch for microservice-toolbox."""
        rs_dir = self.test_dir / "ext-rust-svc"
        generate_rust_scaffold(rs_dir, "ext-rust-svc", 8303, "External Rust service", dry_run=False, layer="L4")
        generate_common_files(rs_dir, "ext-rust-svc", lang="rust", port=8303, desc="External Rust service", dry_run=False, layer="L4")

        cargo_toml = (rs_dir / "Cargo.toml").read_text(encoding="utf-8")
        self.assertIn('version = "0.0.1"', cargo_toml)
        self.assertIn(
            'microservice-toolbox = { git = "https://github.com/Bastien-Antigravity/microservice-toolbox.git", branch = "develop" }',
            cargo_toml,
        )
        self.assertEqual((rs_dir / "VERSION.txt").read_text(encoding="utf-8").strip(), "0.0.1")

    def test_cpp_cmakelists_fetchcontent_and_external_makefile(self):
        """Verify C++ scaffold generates CMakeLists.txt with FetchContent and clean external Makefile."""
        ext_cpp_dir = self.test_dir / "external-domain" / "ext-cpp-svc"
        generate_cpp_scaffold(ext_cpp_dir, "ext-cpp-svc", 8304, "External C++ service", dry_run=False, layer="L4")
        generate_common_files(ext_cpp_dir, "ext-cpp-svc", lang="cpp", port=8304, desc="External C++ service", dry_run=False, layer="L4")

        cmake_path = ext_cpp_dir / "CMakeLists.txt"
        self.assertTrue(cmake_path.exists(), "CMakeLists.txt must be generated for C++ scaffolds")
        cmake_text = cmake_path.read_text(encoding="utf-8")
        self.assertIn("FetchContent_Declare(", cmake_text)
        self.assertIn("https://github.com/Bastien-Antigravity/microservice-toolbox.git", cmake_text)
        self.assertIn("GIT_TAG        develop", cmake_text)
        self.assertIn("SOURCE_SUBDIR  cpp", cmake_text)
        self.assertIn("microservice_toolbox::toolbox", cmake_text)
        self.assertIn("LIBDISTCONF_PATH", cmake_text)
        self.assertIn("$ENV{HOME}/.bastien/lib", cmake_text)
        self.assertIn("/usr/local/lib", cmake_text)
        self.assertNotIn("../microservice-toolbox", cmake_text)

        ext_makefile = (ext_cpp_dir / "Makefile").read_text(encoding="utf-8")
        self.assertNotIn("../microservice-toolbox", ext_makefile)
        self.assertNotIn("../distributed-config", ext_makefile)
        self.assertIn("cmake", ext_makefile)
        self.assertIn("-std=c++17", ext_makefile)
        self.assertEqual((ext_cpp_dir / "VERSION.txt").read_text(encoding="utf-8").strip(), "0.0.1")

    def test_external_domain_workspace_sibling_placement_symlink_and_doclink(self):
        """Verify scaffolding against an external domain workspace uses sibling layout, ../standalone.yaml, and concrete DocLink."""
        import json
        from src.lifecycle.scaffold_microservice import main as scaffold_ms_main

        ext_ws = self.test_dir / "My-Trading-Workspace"
        brain_name = "trading-brain"
        ext_brain = ext_ws / brain_name
        (ext_brain / "02-Business-BDD" / "02-Behavior-Specs").mkdir(parents=True, exist_ok=True)
        (ext_brain / "06-Microservices").mkdir(parents=True, exist_ok=True)
        repo_ctrl = ext_brain / "05-Fleet-Operation" / "00-Repo-Control"
        repo_ctrl.mkdir(parents=True, exist_ok=True)

        (ext_ws / "standalone.yaml").write_text(
            "common:\n    name: common\n\ncapabilities:\n    squad_agent:\n        target_brain_id: trading-brain\n",
            encoding="utf-8",
        )
        (repo_ctrl / "inventory.json").write_text(
            json.dumps({"domain_workspace": True, "brain_id": brain_name, "repositories": []}, indent=2),
            encoding="utf-8",
        )
        (repo_ctrl / "service-registry.json").write_text(
            json.dumps({"brain_id": brain_name, "services": []}, indent=2),
            encoding="utf-8",
        )

        # Scaffold L3 Go service via CLI main() targeting ext_brain (no --dest)
        svc_name = "order-router"
        with patch.object(
            sys,
            "argv",
            [
                "scaffold_microservice.py",
                "--name",
                svc_name,
                "--lang",
                "go",
                "--port",
                "8350",
                "--layer",
                "L3",
                "--brain",
                str(ext_brain),
            ],
        ):
            scaffold_ms_main()

        # 1. Sibling placement: <ext_ws>/<svc_name> (NOT nested inside <ext_brain>/06-Microservices/)
        sibling_dir = ext_ws / svc_name
        self.assertTrue(sibling_dir.is_dir(), "Service must be placed as sibling of domain brain")
        self.assertFalse((ext_brain / "06-Microservices" / svc_name).exists(), "Service code must NOT nest in 06-Microservices/")

        # 2. Internal symlink: standalone.yaml -> ../standalone.yaml
        symlink = sibling_dir / "standalone.yaml"
        self.assertTrue(symlink.is_symlink())
        self.assertEqual(os.readlink(symlink), "../standalone.yaml")
        self.assertTrue(symlink.exists())

        # 3. Concrete DocLink in Go template
        main_go = (sibling_dir / "cmd" / svc_name / "main.go").read_text(encoding="utf-8")
        self.assertIn(f'DocLink:     "{brain_name}/06-Microservices/{svc_name}.md"', main_go)

        # 4. Registered into <ext_ws>/standalone.yaml AND <ext_brain>/05-Fleet-Operation/00-Repo-Control/{inventory,service-registry}.json
        ws_yaml = (ext_ws / "standalone.yaml").read_text(encoding="utf-8")
        self.assertIn("order_router:", ws_yaml)
        self.assertIn("ORDER_ROUTER_PORT:8350", ws_yaml)

        inv_data = json.loads((repo_ctrl / "inventory.json").read_text(encoding="utf-8"))
        self.assertTrue(any(r.get("name") == svc_name and r.get("path") == f"../{svc_name}" for r in inv_data["repositories"]))

        reg_data = json.loads((repo_ctrl / "service-registry.json").read_text(encoding="utf-8"))
        self.assertTrue(any(s.get("name") == svc_name and s.get("default_port") == 8350 for s in reg_data["services"]))

        # 5. Concrete DocLink across Python, Rust, and C++ templates too
        py_dir = ext_ws / "alpha-py-svc"
        generate_python_scaffold(py_dir, "alpha-py-svc", 8351, "Py svc", dry_run=False, brain_name=brain_name)
        self.assertIn(f'doc_link="{brain_name}/06-Microservices/alpha-py-svc.md"', (py_dir / "main.py").read_text(encoding="utf-8"))

        rs_dir = ext_ws / "alpha-rs-svc"
        generate_rust_scaffold(rs_dir, "alpha-rs-svc", 8352, "Rust svc", dry_run=False, brain_name=brain_name)
        self.assertIn(f'doc_link: "{brain_name}/06-Microservices/alpha-rs-svc.md".to_string()', (rs_dir / "src/main.rs").read_text(encoding="utf-8"))

        cpp_dir = ext_ws / "alpha-cpp-svc"
        generate_cpp_scaffold(cpp_dir, "alpha-cpp-svc", 8353, "C++ svc", dry_run=False, brain_name=brain_name)
        self.assertIn(f'spec.docLink = "{brain_name}/06-Microservices/alpha-cpp-svc.md";', (cpp_dir / "src/main.cpp").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
