#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
MemoryStore Interface defining the abstract contract for short-term and long-term memory storage layers.

DATA FLOW:
None (Abstract Base Interface).

KEY PARAMETERS:
None (Abstract Base Interface).
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional

# -----------------------------------------------------------------------------

class MemoryStore(ABC):
    """
    Abstract base class representing a memory storage layer.
    """

    # -----------------------------------------------------------------------------

    @abstractmethod
    def add(self, message: Dict[str, Any], session_id: Optional[str] = None) -> None:
        """
        AI-CONTEXT: Persists a single conversation turn in the memory store.
        """
        pass

    # -----------------------------------------------------------------------------

    @abstractmethod
    def retrieve(self, query: str, session_id: Optional[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
        """
        AI-CONTEXT: Retrieves conversation history or semantic chunks relevant to the query.
        """
        pass

    # -----------------------------------------------------------------------------

    @abstractmethod
    def clear(self, session_id: Optional[str] = None) -> None:
        """
        AI-CONTEXT: Purges conversation history associated with the session.
        """
        pass
