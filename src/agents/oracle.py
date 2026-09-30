#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Oracle agent daemon specialized in long-term chronological log auditing, historical analysis, and querying temporal knowledge vaults.

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

class OracleAgent(BaseAgent):
    """
    Oracle agent daemon. Specialised in long-term chronological log auditing,
    historical analysis, and querying temporal knowledge vaults.
    """
    def __init__(self, *, config: Any, logger: Any, pg_pool: Any, event_bus: SquadEventBus):
        super().__init__(
            role_name="oracle",
            prompt_file="00-Oracle/Prompt-Chronos-Oracle.md",
            config=config,
            logger=logger,
            pg_pool=pg_pool,
            event_bus=event_bus
        )
