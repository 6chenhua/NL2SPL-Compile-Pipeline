"""Construct satisfaction report data structures."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from nl2spl.compiler.constructs.graph import ConstructEdge

FrontierStatus = Literal[
    "continue",
    "leaf",
    "cutline_partial",
    "cutline_blocked",
]

CutlineReason = Literal[
    "missing_required_for_complete",
    "no_source_demand",
    "promotion_blocked",
    "non_renderable_candidate",
    "blocked_by_gate",
    "missing_api_identity_or_evidence",
    "incomplete_api_declaration_contract",
]


SlotStatus = Literal["satisfied", "missing", "inferred", "assumed", "not_applicable"]

ConstructCompleteness = Literal["complete", "partial", "blocked"]


@dataclass
class SlotSatisfaction:
    """Evidence-backed assessment of a single slot."""

    slot_name: str
    status: SlotStatus
    source_span_ids: list[str] = field(default_factory=list)
    source_section_id: str | None = None
    source_packet_id: str | None = None
    relation: Literal["direct", "normalized", "inferred", "assumed"] | None = None
    diagnostic_kind: str | None = None
    explanation: str | None = None
    diagnostic_target_ref: str | None = None
    diagnostic_required_for: str | None = None
    diagnostic_blocks_rendering: bool | None = None
    suggested_resolution: str | None = None


@dataclass
class ConstructSatisfactionReport:
    """Slot-level satisfaction report for one materialised construct.

    IRS v6 extensions:
        primary_parent_id: Main containment parent construct ID
        child_construct_ids: Direct child construct IDs
        related_edges: Non-tree relationships (produces, invokes, etc.)
        construct_path: Hierarchical path for reporting
        source_span_ids: Source spans supporting this construct
        source_section_id: Source section ID
        source_packet_id: Source packet ID
        cutline_reason: Why recursive checking stopped
        frontier_status: Traversal control for future recursive checking
        metadata: Additional construct metadata
    """

    construct_id: str
    construct_type: str
    slots: list[SlotSatisfaction]
    completeness: ConstructCompleteness
    renderable: bool
    diagnostics: list = field(default_factory=list)
    # IRS v6 extensions - all have defaults for backward compatibility
    primary_parent_id: str | None = None
    child_construct_ids: list[str] = field(default_factory=list)
    related_edges: list[ConstructEdge] = field(default_factory=list)
    construct_path: tuple[str, ...] = ()
    source_span_ids: list[str] = field(default_factory=list)
    source_section_id: str | None = None
    source_packet_id: str | None = None
    cutline_reason: CutlineReason | None = None
    frontier_status: FrontierStatus = "leaf"
    metadata: dict[str, Any] = field(default_factory=dict)
