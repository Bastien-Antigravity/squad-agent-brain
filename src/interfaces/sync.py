#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
SyncService Interface defining the abstract contract for file, agent, and git synchronization tools.

DATA FLOW:
None (Abstract Base Interface).

KEY PARAMETERS:
None (Abstract Base Interface).
"""

from abc import ABC, abstractmethod

# -----------------------------------------------------------------------------

class SyncService(ABC):
    """
    Abstract base class representing a synchronization service.
    """

    # -----------------------------------------------------------------------------

    @abstractmethod
    def sync(self, *args, **kwargs) -> None:
        """
        Runs the synchronization routine.
        """
        pass
