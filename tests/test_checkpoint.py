#!/usr/bin/env python
# coding:utf-8

"""
===============================================================================================
ESSENTIAL PROCESS:
Unit tests for Squad Checkpoint Manager (Deterministic Git Restore Point Protocol).

DATA FLOW:
1. Validates 'checkpoint create' establishes tag and state file.
2. Validates 'checkpoint status' outputs active checkpoint.
3. Validates 'checkpoint rollback' reverts and cleans state.
4. Validates 'checkpoint release' finalizes changes and prunes tag.

KEY PARAMETERS:
- tmp_path: Pytest temporary directory fixture providing isolated git repositories.
===============================================================================================
"""

import json
from subprocess import run as subprocessRun
from unittest.mock import patch, MagicMock

import pytest

from src.fleet.checkpoint import (
    cmd_create,
    cmd_status,
    cmd_rollback,
    cmd_release,
    CHECKPOINT_FILENAME,
)


@pytest.fixture
def mock_git_repo(tmp_path):
    repo = tmp_path / "test-repo"
    repo.mkdir()
    subprocessRun(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocessRun(["git", "config", "user.name", "Test Agent"], cwd=repo, check=True, capture_output=True)
    subprocessRun(["git", "config", "user.email", "agent@antigravity.test"], cwd=repo, check=True, capture_output=True)

    dummy_file = repo / "README.md"
    dummy_file.write_text("# Initial Repo\n", encoding="utf-8")
    subprocessRun(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocessRun(["git", "commit", "-m", "chore: initial commit"], cwd=repo, check=True, capture_output=True)

    return repo, tmp_path


def test_checkpoint_lifecycle(mock_git_repo):
    repo, workspace = mock_git_repo
    vault_root = repo
    workspace_root = workspace

    # 1. Test create
    args_create = MagicMock()
    args_create.topic = "unit-test-feature"
    args_create.repo = str(repo)
    args_create.fleet = False
    args_create.force = False

    code = cmd_create(args_create, vault_root, workspace_root)
    assert code == 0

    ckpt_file = workspace_root / CHECKPOINT_FILENAME
    assert ckpt_file.exists()
    data = json.loads(ckpt_file.read_text(encoding="utf-8"))
    assert data["topic"] == "unit-test-feature"
    assert len(data["repos"]) == 1
    tag = data["tag"]

    # Verify git tag exists in repo
    res = subprocessRun(["git", "tag", "-l", tag], cwd=repo, capture_output=True, text=True, check=True)
    assert tag in res.stdout

    # 2. Test status
    args_status = MagicMock()
    code_status = cmd_status(args_status, vault_root, workspace_root)
    assert code_status == 0

    # 3. Modify repository
    new_file = repo / "feature.py"
    new_file.write_text("print('test')\n", encoding="utf-8")

    # 4. Test rollback
    args_rollback = MagicMock()
    args_rollback.keep_untracked = False
    args_rollback.force = True

    code_rb = cmd_rollback(args_rollback, vault_root, workspace_root)
    assert code_rb == 0
    assert not ckpt_file.exists()
    assert not new_file.exists()

    # Verify tag was pruned on rollback
    res_tag = subprocessRun(["git", "tag", "-l", tag], cwd=repo, capture_output=True, text=True, check=True)
    assert tag not in res_tag.stdout


def test_checkpoint_release(mock_git_repo):
    repo, workspace = mock_git_repo
    vault_root = repo
    workspace_root = workspace

    args_create = MagicMock()
    args_create.topic = "release-test"
    args_create.repo = str(repo)
    args_create.fleet = False
    args_create.force = False

    assert cmd_create(args_create, vault_root, workspace_root) == 0

    ckpt_file = workspace_root / CHECKPOINT_FILENAME
    data = json.loads(ckpt_file.read_text(encoding="utf-8"))
    tag = data["tag"]

    # Make verified changes
    (repo / "new_module.py").write_text("# new code\n", encoding="utf-8")

    # Release
    args_release = MagicMock()
    args_release.commit_msg = "feat: add new module"
    args_release.message = None
    args_release.keep_tag = False

    code_rel = cmd_release(args_release, vault_root, workspace_root)
    assert code_rel == 0
    assert not ckpt_file.exists()

    # Commit exists in git log
    log_res = subprocessRun(["git", "log", "-1", "--oneline"], cwd=repo, capture_output=True, text=True, check=True)
    assert "feat: add new module" in log_res.stdout

    # Temporary tag was pruned
    res_tag = subprocessRun(["git", "tag", "-l", tag], cwd=repo, capture_output=True, text=True, check=True)
    assert tag not in res_tag.stdout

