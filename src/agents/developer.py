#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Lead Developer agent daemon specialized in reading/writing source files, compiling code, and implementing logic changes.

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
from src.interfaces import SquadEventBus
from src.agents.base_agent import BaseAgent, read_workspace_file, write_workspace_file, execute_shell_command

# -----------------------------------------------------------------------------

class DeveloperAgent(BaseAgent):
    """
    Lead Developer agent daemon. Specialized in reading/writing source files,
    compiling code, and implementing logic changes.
    """
    def __init__(self, *, config: Any, logger: Any, pg_pool: Any, event_bus: SquadEventBus):
        super().__init__(
            role_name="developer",
            prompt_file="03-Developer/Prompt-Lead-Developer.md",
            config=config,
            logger=logger,
            pg_pool=pg_pool,
            event_bus=event_bus
        )
        self.tools = [read_workspace_file, write_workspace_file, execute_shell_command]
