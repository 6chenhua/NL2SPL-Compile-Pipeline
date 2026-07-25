"""Compatibility shim for construct graph schema.

New code should import from ``nl2spl.compiler.constructs.graph``.
"""

from nl2spl.compiler.constructs.graph import (
    ConstructEdge,
    ConstructEdgeType,
    ConstructGraph,
)

__all__ = ["ConstructEdge", "ConstructEdgeType", "ConstructGraph"]
