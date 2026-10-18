#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Unit tests for fleet_version.py dynamic semantic versioning tools.

DATA FLOW:
Test Harness -> Semver Parsing / Bumping / Inspect / Update -> Assertions
"""

import shutil
import tempfile
import unittest
from pathlib import Path

# Add src to sys.path
SQUAD_AGENT_DIR = Path(__file__).resolve().parent.parent
import sys
if str(SQUAD_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(SQUAD_AGENT_DIR))

from src.fleet.fleet_version import (
    parse_semver,
    increment_semver,
    inspect_repo_version,
    update_repo_version,
)


class TestFleetVersion(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="test_version_"))

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_parse_semver_valid(self):
        major, minor, patch, pre = parse_semver("0.0.1")
        self.assertEqual((major, minor, patch, pre), (0, 0, 1, ""))

        major, minor, patch, pre = parse_semver("v1.2.3-rc.1")
        self.assertEqual((major, minor, patch, pre), (1, 2, 3, "rc.1"))

    def test_parse_semver_invalid(self):
        with self.assertRaises(ValueError):
            parse_semver("invalid-version")
        with self.assertRaises(ValueError):
            parse_semver("1.0")

    def test_increment_semver(self):
        self.assertEqual(increment_semver("0.0.1", "patch"), "0.0.2")
        self.assertEqual(increment_semver("0.0.1", "minor"), "0.1.0")
        self.assertEqual(increment_semver("0.0.1", "major"), "1.0.0")
        self.assertEqual(increment_semver("1.2.3", "patch"), "1.2.4")

    def test_inspect_and_update_repo_version(self):
        # 1. Missing VERSION.txt
        info = inspect_repo_version(self.test_dir)
        self.assertEqual(info["status"], "MISSING_VERSION_TXT")

        # 2. Create VERSION.txt and AI-Project-DNA.md
        v_file = self.test_dir / "VERSION.txt"
        v_file.write_text("0.0.1\n", encoding="utf-8")

        dna_file = self.test_dir / "AI-Project-DNA.md"
        dna_file.write_text(
            "# Metadata\n- Version: 0.0.1\n\n- Versioning Strategy: Semantic Versioning (v0.0.1).\n",
            encoding="utf-8",
        )

        info = inspect_repo_version(self.test_dir)
        self.assertEqual(info["status"], "OK")
        self.assertEqual(info["version_txt"], "0.0.1")
        self.assertEqual(info["dna_version"], "0.0.1")

        # 3. Bump version to 0.0.2
        ok = update_repo_version(self.test_dir, "0.0.2", dry_run=False, git_commit=False)
        self.assertTrue(ok)
        self.assertEqual(v_file.read_text(encoding="utf-8").strip(), "0.0.2")
        self.assertIn("- Version: 0.0.2", dna_file.read_text(encoding="utf-8"))
        self.assertIn("Semantic Versioning (v0.0.2)", dna_file.read_text(encoding="utf-8"))

        info_after = inspect_repo_version(self.test_dir)
        self.assertEqual(info_after["status"], "OK")
        self.assertEqual(info_after["version_txt"], "0.0.2")
        self.assertEqual(info_after["dna_version"], "0.0.2")

    def test_detect_dna_drift(self):
        v_file = self.test_dir / "VERSION.txt"
        v_file.write_text("0.0.2\n", encoding="utf-8")

        dna_file = self.test_dir / "AI-Project-DNA.md"
        dna_file.write_text("- Version: 0.0.1\n", encoding="utf-8")

        info = inspect_repo_version(self.test_dir)
        self.assertEqual(info["status"], "DNA_DRIFT")


if __name__ == "__main__":
    unittest.main()
