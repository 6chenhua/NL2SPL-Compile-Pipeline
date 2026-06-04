"""Construct graph types for IRS v6.

Provides ConstructEdge and ConstructGraph for expressing DAG relationships
between SPL constructs, supporting future recursive IRS checking.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Literal


def _metadata_sort_key(metadata: dict[str, Any]) -> str:
    """Canonical string for metadata, used in snapshot sorting."""
    return json.dumps(metadata, sort_keys=True, default=str)

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

    def key(self) -> tuple[str, str, str, tuple[str, ...]]:
        """Deterministic dedup key: (edge_type, from_id, to_id, sorted_spans)."""
        return (
            self.edge_type,
            self.from_id,
            self.to_id,
            tuple(sorted(self.source_span_ids)),
        )

    def to_snapshot(self) -> dict[str, Any]:
        """Stable dict representation for serialization and comparison."""
        return {
            "edge_type": self.edge_type,
            "from_id": self.from_id,
            "to_id": self.to_id,
            "source_span_ids": sorted(self.source_span_ids),
            "metadata": dict(sorted(self.metadata.items())),
        }


@dataclass
class ConstructGraph:
    """Graph of SPL constructs and their relationships.

    Attributes:
        nodes: List of construct IDs
        edges: List of construct edges
    """

    nodes: list[str] = field(default_factory=list)
    edges: list[ConstructEdge] = field(default_factory=list)

    def add_node(self, node_id: str) -> None:
        """Add a node if not already present."""
        if node_id not in self.nodes:
            self.nodes.append(node_id)

    def add_edge(self, edge: ConstructEdge) -> None:
        """Add an edge and ensure both endpoints are nodes."""
        self.edges.append(edge)
        self.add_node(edge.from_id)
        self.add_node(edge.to_id)

    def deduped(self) -> ConstructGraph:
        """Return a new graph with duplicate edges removed.

        Two edges are duplicates if they have the same (edge_type, from_id,
        to_id, sorted source_span_ids).  The first occurrence is kept.
        Nodes are reconstructed from edges to ensure virtual nodes are
        included.
        """
        seen: set[tuple[str, str, str, tuple[str, ...]]] = set()
        unique: list[ConstructEdge] = []
        for edge in self.edges:
            k = edge.key()
            if k not in seen:
                seen.add(k)
                unique.append(edge)
        # Preserve explicit nodes, then add edge endpoints
        nodes: list[str] = list(self.nodes)
        seen_nodes: set[str] = set(self.nodes)
        for edge in unique:
            for node_id in (edge.from_id, edge.to_id):
                if node_id not in seen_nodes:
                    seen_nodes.add(node_id)
                    nodes.append(node_id)
        return ConstructGraph(
            nodes=nodes,
            edges=unique,
        )

    def edge_snapshots(self) -> list[dict[str, Any]]:
        """Return stable-sorted list of edge snapshots."""
        snapshots = [e.to_snapshot() for e in self.edges]
        snapshots.sort(
            key=lambda s: (
                s["edge_type"],
                s["from_id"],
                s["to_id"],
                tuple(s["source_span_ids"]),
                _metadata_sort_key(s["metadata"]),
            )
        )
        return snapshots
