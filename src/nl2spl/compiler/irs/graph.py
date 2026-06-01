"""Construct graph types for IRS v6.

Provides ConstructEdge and ConstructGraph for expressing DAG relationships
between SPL constructs, supporting future recursive IRS checking.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

ConstructEdgeType = Literal[
    "contains",
    "produces",
    "consumes",
    "invokes",
    "handoff_to",
    "handles",
    "applies_to",
    "derived_from",
    "promotes_to",
    "blocked_by",
]


@dataclass
class ConstructEdge:
    """Edge representing a relationship between two SPL constructs.

    Attributes:
        from_id: Source construct ID
        to_id: Target construct ID
        edge_type: Type of relationship
        source_span_ids: Source spans supporting this edge
        metadata: Additional edge metadata
    """

    from_id: str
    to_id: str
    edge_type: ConstructEdgeType
    source_span_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ConstructGraph:
    """Graph of SPL constructs and their relationships.

    Attributes:
        nodes: List of construct IDs
        edges: List of construct edges
    """

    nodes: list[str] = field(default_factory=list)
    edges: list[ConstructEdge] = field(default_factory=list)
