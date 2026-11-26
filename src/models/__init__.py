#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Exports domain models for 08-Squad-Agent cross-brain orchestration and build contracts.

DATA FLOW:
1. Re-exports MicroserviceBuildSpec and port allocation helpers.

KEY PARAMETERS:
- MicroserviceBuildSpec: Validated cross-brain microservice build contract.
"""

from src.models.build_spec import (
    MicroserviceBuildSpec,
    allocate_domain_port,
    collect_reserved_ports,
)

__all__ = [
    "MicroserviceBuildSpec",
    "allocate_domain_port",
    "collect_reserved_ports",
]
