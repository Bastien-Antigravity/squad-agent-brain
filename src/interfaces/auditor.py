#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Auditor Interface defining the abstract contract for all vault auditing/validation tasks.

DATA FLOW:
None (Abstract Base Interface).

KEY PARAMETERS:
None (Abstract Base Interface).
"""

from abc import ABC, abstractmethod

# -----------------------------------------------------------------------------

class Auditor(ABC):
    """
    Abstract base class representing a workspace auditor.
    """

    # -----------------------------------------------------------------------------

    @abstractmethod
    def audit(self, *args, **kwargs) -> bool:
        """
        Runs the audit check. Returns True if successful (coherent/healthy), False otherwise.
        """
        pass
