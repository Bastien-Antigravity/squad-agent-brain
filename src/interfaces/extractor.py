#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Extractor Interface defining the abstract contract for codebase parser and extractor utilities.

DATA FLOW:
None (Abstract Base Interface).

KEY PARAMETERS:
None (Abstract Base Interface).
"""

from abc import ABC, abstractmethod
from typing import Any

# -----------------------------------------------------------------------------

class Extractor(ABC):
    """
    Abstract base class representing a codebase AST or info extractor.
    """

    # -----------------------------------------------------------------------------

    @abstractmethod
    def extract(self, *args, **kwargs) -> Any:
        """
        Runs the extraction process and returns extracted data.
        """
        pass
