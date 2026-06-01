"""IRS v6 framework types and interfaces.

This package provides the foundational types for IRS v6 extensible architecture.
"""

from nl2spl.compiler.irs.frontier import CutlineReason, FrontierStatus
from nl2spl.compiler.irs.graph import ConstructEdge, ConstructEdgeType, ConstructGraph

__all__ = [
    "ConstructEdge",
    "ConstructEdgeType",
    "ConstructGraph",
    "FrontierStatus",
    "CutlineReason",
]
