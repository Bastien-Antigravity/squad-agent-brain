#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
DocMaintainer agent daemon specialized in verifying documentation alignment, detecting document drift, and suggesting corrections.

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

class DocMaintainerAgent(BaseAgent):
    """
    DocMaintainer agent daemon. Specialised in verifying documentation alignment,
    detecting document drift, and suggesting manual corrections.
    """
    def __init__(self, *, config: Any, logger: Any, pg_pool: Any, event_bus: SquadEventBus):
        super().__init__(
            role_name="docmaintainer",
            prompt_file="06-DocMaintainer/Prompt-DocMaintainer.md",
            config=config,
            logger=logger,
            pg_pool=pg_pool,
            event_bus=event_bus
        )
