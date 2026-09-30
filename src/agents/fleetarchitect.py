#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
FleetArchitect agent daemon specialized in cross-service coordination, shared configuration management, and microservice layout structures.

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

class FleetArchitectAgent(BaseAgent):
    """
    FleetArchitect agent daemon. Specialised in cross-service coordination,
    shared configuration management, and microservice layout structures.
    """
    def __init__(self, *, config: Any, logger: Any, pg_pool: Any, event_bus: SquadEventBus):
        super().__init__(
            role_name="fleetarchitect",
            prompt_file="05-FleetArchitect/Prompt-Fleet-Architect.md",
            config=config,
            logger=logger,
            pg_pool=pg_pool,
            event_bus=event_bus
        )
