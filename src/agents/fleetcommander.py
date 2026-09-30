#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
FleetCommander agent daemon specialized in command dispatch, system monitoring, and triggering cross-language microservice routines.

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

class FleetCommanderAgent(BaseAgent):
    """
    FleetCommander agent daemon. Specialised in command dispatch, system monitoring,
    and triggering cross-language microservice routines.
    """
    def __init__(self, *, config: Any, logger: Any, pg_pool: Any, event_bus: SquadEventBus):
        super().__init__(
            role_name="fleetcommander",
            prompt_file="07-FleetCommander/Prompt-FleetCommander.md",
            config=config,
            logger=logger,
            pg_pool=pg_pool,
            event_bus=event_bus
        )
