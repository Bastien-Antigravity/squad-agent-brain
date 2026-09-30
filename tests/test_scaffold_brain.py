#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Unit and integration tests for scaffold_new_brain.py.
Validates brain vault scaffolding, folder hierarchy, mandatory ecosystem files,
YAML frontmatter compliance, standalone.yaml symlink, and agent skills compilation.

DATA FLOW:
1. Input: Temporary directory paths, mock brain vault parameters.
2. Logic: Executes scaffold_brain in dry-run and live modes.
3. Output: Assertions validating structural completeness, frontmatter tags, and symlink targets.
"""

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
import yaml

# Add 08-Base-Scripts to sys.path
BASE_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(BASE_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_SCRIPTS_DIR))

from src.lifecycle.scaffold_new_brain import scaffold_brain, create_file, create_symlink
from src.lib.orchestration_lib import resolve_vault_and_workspace


class TestScaffoldBrain(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="test_brain_scaffold_"))
        self.vault_root, _ = resolve_vault_and_workspace(__file__)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_create_file_dry_run(self):
        """Verify create_file respects dry_run mode."""
        target = self.test_dir / "sample.md"
        create_file(target, "content", dry_run=True)
        self.assertFalse(target.exists(), "Dry run must not create file on disk")

        create_file(target, "content", dry_run=False)
        self.assertTrue(target.exists(), "Live run must create file on disk")
        self.assertEqual(target.read_text(encoding="utf-8"), "content")

    def test_create_symlink_dry_run(self):
        """Verify create_symlink respects dry_run mode."""
        target = self.test_dir / "link.yaml"
        create_symlink(target, "../some/target.yaml", dry_run=True)
        self.assertFalse(target.exists(), "Dry run must not create symlink")

        create_symlink(target, "../some/target.yaml", dry_run=False)
        self.assertTrue(target.is_symlink(), "Live run must create symlink")
        self.assertEqual(os.readlink(target), "../some/target.yaml")

    def test_scaffold_brain_dry_run(self):
        """Verify scaffolding with dry_run=True produces no disk side effects."""
        target_path = self.test_dir / "dry-brain"
        scaffold_brain("dry-brain", target_path, self.vault_root, dry_run=True)
        self.assertFalse(target_path.exists(), "Dry run must not create destination directory")

    def test_full_brain_scaffolding(self):
        """End-to-end verification of complete brain vault scaffolding."""
        target_name = "test-domain-brain"
        target_path = self.test_dir / target_name

        scaffold_brain(target_name, target_path, self.vault_root, dry_run=False)

        # 1. Standard Double-Digit Folders
        expected_folders = [
            "00-AI-Orchestration",
            "01-Strategic-Nexus",
            "02-Business-BDD",
            "03-Tech-Stack",
            "04-Rapid-Prototyping",
            "05-Fleet-Operation",
            "06-Microservices",
            "07-Core-KMS",
            "07-Core-KMS/Role-Prompts",
            "08-Base-Scripts",
            "99-Humans",
            "quick-overview",
        ]
        for folder in expected_folders:
            folder_path = target_path / folder
            self.assertTrue(folder_path.is_dir(), f"Expected directory missing: {folder}")

        # 2. Mandatory Root Ecosystem Files
        expected_files = [
            target_path / "AGENTS.md",
            target_path / "README.md",
            target_path / "VERSION.txt",
            target_path / ".gitignore",
            target_path / "Ecosystem-Map-MOC.md",
            target_path / "00-AI-Orchestration/AI-Project-DNA.md",
            target_path / "00-AI-Orchestration/AI-Session-State.md",
            target_path / "00-AI-Orchestration/AI-Init.md",
            target_path / "00-AI-Orchestration/MODE-MANUAL.md",
            target_path / "quick-overview/00-Overview.md",
        ]
        for f in expected_files:
            self.assertTrue(f.exists(), f"Mandatory ecosystem file missing: {f}")

        # 3. Symlink Verification
        symlink = target_path / "standalone.yaml"
        self.assertTrue(symlink.is_symlink(), "standalone.yaml must be a symlink")
        self.assertEqual(os.readlink(symlink), "../docker-deployment/modes/local/config/native.yaml")

        # 4. Frontmatter Integrity across generated Markdown files
        md_files_to_check = [
            target_path / "AGENTS.md",
            target_path / "Ecosystem-Map-MOC.md",
            target_path / "00-AI-Orchestration/AI-Project-DNA.md",
            target_path / "00-AI-Orchestration/AI-Session-State.md",
            target_path / "00-AI-Orchestration/AI-Init.md",
            target_path / "quick-overview/00-Overview.md",
        ]
        for md_file in md_files_to_check:
            content = md_file.read_text(encoding="utf-8")
            self.assertTrue(content.startswith("---"), f"{md_file.name} must start with YAML frontmatter marker '---'")
            parts = content.split("---", 2)
            self.assertGreaterEqual(len(parts), 3, f"{md_file.name} frontmatter not closed with '---'")
            frontmatter_raw = parts[1]
            data = yaml.safe_load(frontmatter_raw)
            self.assertIsInstance(data, dict, f"{md_file.name} frontmatter must parse to a dict")
            self.assertIn("microservice", data, f"{md_file.name} missing 'microservice' key")
            self.assertIn("type", data, f"{md_file.name} missing 'type' key")
            self.assertIn("status", data, f"{md_file.name} missing 'status' key")
            self.assertIn("tags", data, f"{md_file.name} missing 'tags' key")
            self.assertIsInstance(data["tags"], list, f"{md_file.name} 'tags' must be a list")

        # 5. Agent Skills Compilation Verification
        skills_dir = target_path / ".agents" / "skills"
        self.assertTrue(skills_dir.is_dir(), ".agents/skills must be generated")
        key_agents = ["architect", "developer", "qa", "sentinel"]
        for agent in key_agents:
            agent_skill_file = skills_dir / agent / "SKILL.md"
            self.assertTrue(agent_skill_file.exists(), f"Agent skill missing: {agent}/SKILL.md")


if __name__ == "__main__":
    unittest.main()
