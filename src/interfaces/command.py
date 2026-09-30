#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Command Interface defining the abstract contract for all executable CLI commands in base scripts.

DATA FLOW:
None (Abstract Base Interface).

KEY PARAMETERS:
None (Abstract Base Interface).
"""

from abc import ABC, abstractmethod

# -----------------------------------------------------------------------------

class Command(ABC):
    """
    Abstract base class representing an executable CLI command.
    """

    # -----------------------------------------------------------------------------

    @abstractmethod
    def execute(self, *args, **kwargs) -> None:
        """
        Executes the command logic with optional arguments.
        """
        pass
