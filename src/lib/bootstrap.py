#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Legacy bootstrap wrapper delegating bootstrapping capabilities to microservice-toolbox utils/bootstrap.
Ensures zero-code-change backwards compatibility for legacy base scripts.

DATA FLOW:
1. Resolves workspace root containing microservice-toolbox.
2. Injects microservice-toolbox/python into sys.path.
3. Exports bootstrap functions (ensure_virtualenv, prepend_venv_bin, ensure_import_paths).

KEY PARAMETERS:
None (Facade module).
"""

import sys
from pathlib import Path

# -----------------------------------------------------------------------------

# Add microservice-toolbox/python to sys.path so we can import it
_self_dir = Path(__file__).resolve().parent
_workspace_root = None
for parent in [_self_dir] + list(_self_dir.parents):
    if (parent / "microservice-toolbox").exists():
        _workspace_root = parent
        break
if not _workspace_root:
    _workspace_root = _self_dir.parent.parent.parent.parent
_toolbox_path = _workspace_root / "microservice-toolbox" / "python"
if _toolbox_path.exists() and str(_toolbox_path) not in sys.path:
    sys.path.append(str(_toolbox_path))

# -----------------------------------------------------------------------------

# Delegate exports
from microservice_toolbox.utils.bootstrap import (
    find_vault_root as find_vault_root,
    get_venv_python as get_venv_python,
    ensure_virtualenv as ensure_virtualenv,
    prepend_venv_bin as prepend_venv_bin,
    ensure_import_paths as ensure_import_paths,
    redirect_working_directory as redirect_working_directory
)
