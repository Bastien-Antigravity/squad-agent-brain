#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Public package facade re-exporting language-specific microservice generators and shared
workspace/BDD scaffolding utilities.

DATA FLOW:
1. Re-exports Go, Rust, Python, C++, and common scaffolding entrypoints.

KEY PARAMETERS:
- generate_go_scaffold / generate_rust_scaffold / generate_python_scaffold / generate_cpp_scaffold.
"""

from src.lifecycle.scaffolder.common import (
    _is_external_domain_workspace,
    create_file,
    create_symlink,
    generate_bdd_spec,
    generate_common_files,
    generate_openmfe_component_js,
    register_sandbox_service,
    resolve_workspace_root,
)
from src.lifecycle.scaffolder.cpp_generator import generate_cpp_scaffold
from src.lifecycle.scaffolder.go_generator import generate_go_scaffold
from src.lifecycle.scaffolder.python_generator import generate_python_scaffold
from src.lifecycle.scaffolder.rust_generator import generate_rust_scaffold

__all__ = [
    "_is_external_domain_workspace",
    "create_file",
    "create_symlink",
    "generate_bdd_spec",
    "generate_common_files",
    "generate_cpp_scaffold",
    "generate_go_scaffold",
    "generate_openmfe_component_js",
    "generate_python_scaffold",
    "generate_rust_scaffold",
    "register_sandbox_service",
    "resolve_workspace_root",
]
