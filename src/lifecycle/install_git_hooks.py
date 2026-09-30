#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Installs background post-commit and post-merge git hooks inside the vault's .git/ directory.
This automates the synchronization of RAG indexing and AI coding personas on Git events.

DATA FLOW:
1. Bootstraps the virtual environment.
2. Identifies the vault's .git/hooks directory.
3. Generates hook scripts targeting python virtualenvs for RAG Engine and Persona Extractor.
4. Marks the hook files as executable (chmod +x).

KEY PARAMETERS:
- hooks: List of git hooks to deploy (post-commit, post-merge).
"""

import os
import sys
import stat
from pathlib import Path
from lib.bootstrap import ensure_virtualenv, prepend_venv_bin, ensure_import_paths
from lib.orchestration_lib import resolve_vault_and_workspace

# -----------------------------------------------------------------------------

def install_hooks(vault_root, git_hooks_dir):
    hook_content = """#!/bin/sh

cd "$(dirname "$0")/../.."

if [ -f "./09-RAG-Engine/.venv/bin/python3" ]; then
    PYTHONPATH="./09-RAG-Engine" ./09-RAG-Engine/.venv/bin/python3 ./09-RAG-Engine/main.py index > /dev/null 2>&1 &
elif [ -f "./09-RAG-Engine/.venv/Scripts/python.exe" ]; then
    PYTHONPATH="./09-RAG-Engine" ./09-RAG-Engine/.venv/Scripts/python.exe ./09-RAG-Engine/main.py index > /dev/null 2>&1 &
elif [ -f "./.venv/bin/python3" ]; then
    PYTHONPATH="./09-RAG-Engine" ./.venv/bin/python3 ./09-RAG-Engine/main.py index > /dev/null 2>&1 &
elif [ -f "./.venv/Scripts/python.exe" ]; then
    PYTHONPATH="./09-RAG-Engine" ./.venv/Scripts/python.exe ./09-RAG-Engine/main.py index > /dev/null 2>&1 &
else
    PYTHONPATH="./09-RAG-Engine" python3 ./09-RAG-Engine/main.py index > /dev/null 2>&1 &
fi

if [ -f "./.venv/bin/python3" ]; then
    ./.venv/bin/python3 ./08-Base-Scripts/main.py persona-extractor --daemon > /dev/null 2>&1 &
elif [ -f "./.venv/Scripts/python.exe" ]; then
    ./.venv/Scripts/python.exe ./08-Base-Scripts/main.py persona-extractor --daemon > /dev/null 2>&1 &
else
    python3 ./08-Base-Scripts/main.py persona-extractor --daemon > /dev/null 2>&1 &
fi
"""

    pre_commit_content = """#!/bin/sh

cd "$(dirname "$0")/../.."

if [ -f "./09-RAG-Engine/.venv/bin/python3" ]; then
    ./09-RAG-Engine/.venv/bin/python3 ./08-Base-Scripts/main.py ensure-frontmatter --check
elif [ -f "./09-RAG-Engine/.venv/Scripts/python.exe" ]; then
    ./09-RAG-Engine/.venv/Scripts/python.exe ./08-Base-Scripts/main.py ensure-frontmatter --check
elif [ -f "./.venv/bin/python3" ]; then
    ./.venv/bin/python3 ./08-Base-Scripts/main.py ensure-frontmatter --check
elif [ -f "./.venv/Scripts/python.exe" ]; then
    ./.venv/Scripts/python.exe ./08-Base-Scripts/main.py ensure-frontmatter --check
else
    python3 ./08-Base-Scripts/main.py ensure-frontmatter --check
fi
"""

    hooks_config = {
        "pre-commit": pre_commit_content,
        "post-commit": hook_content,
        "post-merge": hook_content
    }

    for hook, content in hooks_config.items():
        hook_path = os.path.join(git_hooks_dir, hook)
        try:
            with open(hook_path, 'w', encoding='utf-8') as f:
                f.write(content)
        
            st = os.stat(hook_path)
            os.chmod(hook_path, st.st_mode | stat.S_IEXEC)
            print(f"✅ Successfully installed {hook} hook at {hook_path}")
        except Exception as e:
            print(f"❌ Failed to install {hook} hook: {e}")

# -----------------------------------------------------------------------------

def main():
    script_dir = Path(__file__).resolve().parent
    vault_root_path = ensure_virtualenv(str(script_dir))
    prepend_venv_bin(vault_root_path)
    ensure_import_paths(script_dir, vault_root_path)

    vault_root, _ = resolve_vault_and_workspace(__file__)
    git_hooks_dir = os.path.join(str(vault_root), ".git", "hooks")

    if not os.path.exists(git_hooks_dir):
        print(f"❌ Error: Git hooks directory not found at {git_hooks_dir}. Make sure you are inside a Git repository.")
        sys.exit(1)

    install_hooks(str(vault_root), git_hooks_dir)

if __name__ == '__main__':
    main()
