#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
DocIndexer agent daemon specialized in documentation indexing, formatting, and metadata cataloging.

DATA FLOW:
1. Inherits BaseAgent initialization with role-specific prompt and event bus.
2. Registers specialized tools and handles incoming chat events.

KEY PARAMETERS:
- config: Application configuration singleton.
- logger: UniLog logging handle.
- pg_pool: Shared database connection pool.
- event_bus: SquadEventBus pub/sub provider.
"""

# -----------------------------------------------------------------------------

from typing import Any
from src.agents.base_agent import BaseAgent
from src.interfaces import SquadEventBus

# -----------------------------------------------------------------------------

class DocIndexerAgent(BaseAgent):
    """
    DocIndexer agent daemon. Specialised in documentation indexing, formatting,
    and metadata cataloging.
    """
    def __init__(self, *, config: Any, logger: Any, pg_pool: Any, event_bus: SquadEventBus):
        super().__init__(
            role_name="docindexer",
            prompt_file="10-DocIndexer/Prompt-DocIndexer.md",
            config=config,
            logger=logger,
            pg_pool=pg_pool,
            event_bus=event_bus
        )
