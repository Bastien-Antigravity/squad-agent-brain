#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Architect agent daemon specializing in codebase layout design, design patterns,
and referencing architectural specifications (ADRs).

DATA FLOW:
1. Inherits BaseAgent initialization with role-specific prompt and event bus.
2. Binds query_rag_engine tool for architectural RAG lookups.

KEY PARAMETERS:
- config: Application configuration singleton.
- logger: UniLog logging handle.
- pg_pool: Shared database connection pool.
- event_bus: SquadEventBus pub/sub provider.
"""

from typing import Any
from src.interfaces import SquadEventBus
from src.agents.base_agent import BaseAgent, query_rag_engine

# -----------------------------------------------------------------------------

class ArchitectAgent(BaseAgent):
    """
    Architect agent daemon. Specialised in codebase layout design,
    design patterns, and referencing architectural specifications (ADRs).
    """

    # -----------------------------------------------------------------------------

    def __init__(self, *, config: Any, logger: Any, pg_pool: Any, event_bus: SquadEventBus):
        super().__init__(
            role_name="architect",
            prompt_file="02-Architect/Prompt-Architect.md",
            config=config,
            logger=logger,
            pg_pool=pg_pool,
            event_bus=event_bus
        )
        self.tools = [query_rag_engine]
