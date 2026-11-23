#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Unit tests for polyglot local-first workspace manifest compliance rules
(RUST_LOCAL_PATH_POLLUTION on Cargo.toml, PYTHON_LOCAL_PATH_POLLUTION on
pyproject.toml / requirements*.txt, and CPP_LOCAL_PATH_POLLUTION on CMakeLists.txt)
in ComplianceAuditor.

DATA FLOW:
1. Synthesizes isolated temporary Cargo.toml, pyproject.toml, requirements*.txt, and CMakeLists.txt files.
2. Runs ComplianceAuditor.audit_file and ComplianceAuditor.audit_path against valid and polluted manifests.
3. Asserts exact violation detection, line attribution, and exemption of non-dependency sections.

KEY PARAMETERS:
- SQUAD_AGENT_DIR: Root path to 08-Squad-Agent.
"""

from pathlib import Path
from shutil import rmtree as shutilRmtree
from sys import path as sysPath
from tempfile import mkdtemp as tempfileMkdtemp
from unittest import TestCase as unittestTestCase, main as unittestMain

SQUAD_AGENT_DIR = Path(__file__).resolve().parent.parent
if str(SQUAD_AGENT_DIR) not in sysPath:
    sysPath.insert(0, str(SQUAD_AGENT_DIR))

from src.auditing.validate_compliance import ComplianceAuditor

# -----------------------------------------------------------------------------------------------


class TestManifestWorkspaceCompliance(unittestTestCase):
    """Test suite for Cargo.toml and Python manifest local-path pollution checks."""

    def setUp(self) -> None:
        self.test_dir = Path(tempfileMkdtemp(prefix="test_manifest_compliance_"))
        self.auditor = ComplianceAuditor(workspace_root=SQUAD_AGENT_DIR.parent)

    def tearDown(self) -> None:
        shutilRmtree(self.test_dir, ignore_errors=True)

    # -------------------------------------------------------------------------------------------

    def test_cargo_toml_catches_local_path_pollution_and_allows_bin_and_git(self) -> None:
        """RUST_LOCAL_PATH_POLLUTION catches dependency/[patch] local paths and allows [[bin]] and git URLs."""
        bad_cargo = self.test_dir / "bad_crate" / "Cargo.toml"
        bad_cargo.parent.mkdir(parents=True, exist_ok=True)
        bad_cargo.write_text(
            '[package]\n'
            'name = "log-server"\n'
            'version = "0.0.1"\n'
            'edition = "2021"\n\n'
            '[dependencies]\n'
            'tokio = "1.0"\n'
            'microservice-toolbox = { path = "../microservice-toolbox/rust" }\n\n'
            '[patch.crates-io]\n'
            'unilog-rs = { path = "../universal-logger/unilog/rust" }\n\n'
            '[dev-dependencies.safe-socket]\n'
            'path = "/Users/imac/Desktop/Bastien-Antigravity/safe-socket/safesock/rust"\n',
            encoding="utf-8",
        )

        violations = self.auditor.audit_file(bad_cargo)
        rust_violations = [v for v in violations if v["rule"] == "RUST_LOCAL_PATH_POLLUTION"]
        self.assertEqual(len(rust_violations), 3, violations)
        self.assertEqual([v["line"] for v in rust_violations], [8, 11, 14])
        self.assertIn(".cargo/config.toml", rust_violations[0]["message"])

        # Directory scan via audit_path must also detect Cargo.toml
        dir_violations = self.auditor.audit_path(bad_cargo.parent)
        self.assertEqual(len([v for v in dir_violations if v["rule"] == "RUST_LOCAL_PATH_POLLUTION"]), 3)

        good_cargo = self.test_dir / "good_crate" / "Cargo.toml"
        good_cargo.parent.mkdir(parents=True, exist_ok=True)
        good_cargo.write_text(
            '[package]\n'
            'name = "microservice-toolbox"\n'
            'version = "0.0.1"\n'
            'edition = "2024"\n\n'
            '[dependencies]\n'
            'unilog-rs = { git = "https://github.com/Bastien-Antigravity/universal-logger", branch = "develop" }\n'
            'internal-subcrate = { path = "crates/internal-subcrate" }\n\n'
            '[[bin]]\n'
            'name = "integration_gen"\n'
            'path = "../integration/rust_gen.rs"\n\n'
            '[[example]]\n'
            'name = "demo"\n'
            'path = "../examples/demo.rs"\n',
            encoding="utf-8",
        )
        self.assertEqual(self.auditor.audit_file(good_cargo), [])

    # -------------------------------------------------------------------------------------------

    def test_python_manifest_catches_local_path_pollution_and_allows_git_urls(self) -> None:
        """PYTHON_LOCAL_PATH_POLLUTION catches local paths in requirements*.txt and pyproject.toml while allowing git+https."""
        bad_reqs = self.test_dir / "bad_py_svc" / "requirements.txt"
        bad_reqs.parent.mkdir(parents=True, exist_ok=True)
        bad_reqs.write_text(
            "# Ecosystem dependencies\n"
            "fastapi==0.136.3\n"
            "-e ../microservice-toolbox/python\n"
            "unilog @ file:///Users/imac/Desktop/Bastien-Antigravity/universal-logger/unilog/python\n"
            "../distributed-config/distconf/python\n"
            "/Users/imac/Desktop/Bastien-Antigravity/safe-socket/safesock/python\n"
            "-e /opt/custom-pkg\n",
            encoding="utf-8",
        )
        req_violations = self.auditor.audit_file(bad_reqs)
        req_rules = [v["rule"] for v in req_violations]
        self.assertEqual(req_rules, ["PYTHON_LOCAL_PATH_POLLUTION"] * 5, req_violations)
        self.assertIn("_bastien_workspace.pth", req_violations[0]["message"])

        bad_pyproject = self.test_dir / "bad_py_svc" / "pyproject.toml"
        bad_pyproject.write_text(
            '[project]\n'
            'name = "bad-service"\n'
            'dependencies = [\n'
            '    "unilog @ file:///Users/imac/Desktop/Bastien-Antigravity/universal-logger/unilog/python",\n'
            '    "distconf @ ../distributed-config/distconf/python",\n'
            '    "safesock @ /opt/safe-socket",\n'
            ']\n\n'
            '[tool.uv.sources]\n'
            'microservice-toolbox = { path = "../microservice-toolbox/python", editable = true }\n',
            encoding="utf-8",
        )
        pyp_violations = self.auditor.audit_file(bad_pyproject)
        self.assertEqual(len([v for v in pyp_violations if v["rule"] == "PYTHON_LOCAL_PATH_POLLUTION"]), 4, pyp_violations)

        # Directory scan via audit_path must detect both manifests
        dir_violations = self.auditor.audit_path(bad_reqs.parent)
        self.assertEqual(len([v for v in dir_violations if v["rule"] == "PYTHON_LOCAL_PATH_POLLUTION"]), 9)

        good_dir = self.test_dir / "good_py_svc"
        good_dir.mkdir(parents=True, exist_ok=True)
        good_reqs = good_dir / "requirements-dev.txt"
        good_reqs.write_text(
            "# Canonical git URLs\n"
            "microservice-toolbox @ git+https://github.com/Bastien-Antigravity/microservice-toolbox.git#subdirectory=python\n"
            "-e .\n"
            "pytest==8.3.0\n",
            encoding="utf-8",
        )
        good_pyproject = good_dir / "pyproject.toml"
        good_pyproject.write_text(
            '[project]\n'
            'name = "good-service"\n'
            'dependencies = [\n'
            '    "microservice-toolbox @ git+https://github.com/Bastien-Antigravity/microservice-toolbox.git#subdirectory=python",\n'
            ']\n',
            encoding="utf-8",
        )
        self.assertEqual(self.auditor.audit_file(good_reqs), [])
        self.assertEqual(self.auditor.audit_file(good_pyproject), [])

    # -------------------------------------------------------------------------------------------

    def test_cmake_lists_catches_local_path_pollution_and_allows_fetchcontent(self) -> None:
        """CPP_LOCAL_PATH_POLLUTION catches unconditional add_subdirectory/hardcoded /Users/ paths and allows FetchContent local-first fallback."""
        bad_cmake = self.test_dir / "bad_cpp_svc" / "CMakeLists.txt"
        bad_cmake.parent.mkdir(parents=True, exist_ok=True)
        bad_cmake.write_text(
            'cmake_minimum_required(VERSION 3.20)\n'
            'project(bad_cpp_svc LANGUAGES CXX)\n'
            'add_subdirectory(../microservice-toolbox/cpp)\n'
            'add_subdirectory("/opt/bastien/universal-logger")\n'
            'include_directories(/Users/imac/Desktop/Bastien-Antigravity/distributed-config/distconf/libdistconf)\n',
            encoding="utf-8",
        )

        violations = self.auditor.audit_file(bad_cmake)
        cpp_violations = [v for v in violations if v["rule"] == "CPP_LOCAL_PATH_POLLUTION"]
        self.assertEqual(len(cpp_violations), 3, violations)
        self.assertEqual([v["line"] for v in cpp_violations], [3, 4, 5])
        self.assertIn("FetchContent", cpp_violations[0]["message"])

        dir_violations = self.auditor.audit_path(bad_cmake.parent)
        self.assertEqual(len([v for v in dir_violations if v["rule"] == "CPP_LOCAL_PATH_POLLUTION"]), 3)

        good_cmake = self.test_dir / "good_cpp_svc" / "CMakeLists.txt"
        good_cmake.parent.mkdir(parents=True, exist_ok=True)
        good_cmake.write_text(
            'cmake_minimum_required(VERSION 3.20)\n'
            'project(good_cpp_svc LANGUAGES CXX)\n'
            'set(_CANDIDATE_TOOLBOX_CPP "${CMAKE_CURRENT_SOURCE_DIR}/../microservice-toolbox/cpp")\n'
            'if(EXISTS "${_CANDIDATE_TOOLBOX_CPP}/CMakeLists.txt")\n'
            '    set(FETCHCONTENT_SOURCE_DIR_MICROSERVICE_TOOLBOX "${_CANDIDATE_TOOLBOX_CPP}" CACHE PATH "Local override" FORCE)\n'
            'endif()\n'
            'include(FetchContent)\n'
            'FetchContent_Declare(\n'
            '    microservice_toolbox\n'
            '    GIT_REPOSITORY https://github.com/Bastien-Antigravity/microservice-toolbox.git\n'
            '    GIT_TAG develop\n'
            '    SOURCE_SUBDIR cpp\n'
            ')\n'
            'FetchContent_MakeAvailable(microservice_toolbox)\n',
            encoding="utf-8",
        )
        self.assertEqual(self.auditor.audit_file(good_cmake), [])

        toolbox_cmake = self.test_dir / "microservice-toolbox" / "cpp" / "CMakeLists.txt"
        toolbox_cmake.parent.mkdir(parents=True, exist_ok=True)
        toolbox_cmake.write_text(
            'cmake_minimum_required(VERSION 3.16)\n'
            'set(_DISTCONF_SEARCH_PATHS "${CMAKE_CURRENT_SOURCE_DIR}/../../distributed-config/distconf/libdistconf")\n',
            encoding="utf-8",
        )
        self.assertEqual(self.auditor.audit_file(toolbox_cmake), [])


if __name__ == "__main__":
    unittestMain()
