"""IRS v6 Construct Instance — representation of a construct for IRS checking.

ConstructInstance captures the identity, state, and provenance of a construct
that needs IRS evaluation, whether it's already materialized in IR or only
exists as a candidate/demand signal.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from nl2spl.compiler.constructs.graph import ConstructEdge


@dataclass
class ConstructInstance:
    """A construct instance for IRS checking.

    Attributes:
        construct_id: Unique identifier for this construct
        construct_type: SPL construct type (e.g., "GENERAL_COMMAND", "WORKER")
        ir_ref: Reference to the actual IR object (if materialized)
        materialized: True if construct exists in IR, False if candidate/demand only
        source_demanded: True if source evidence requires considering this construct
        candidate_only: True if this is a promotion candidate, not a renderable construct
        primary_parent_id: Main containment parent construct ID
        child_construct_ids: Direct child construct IDs
        related_edges: Non-tree relationships (produces, invokes, etc.)
        construct_path: Hierarchical path for reporting
        source_span_ids: Source spans supporting this construct
        source_section_id: Source section ID
        source_packet_id: Source packet ID
        metadata: Additional construct metadata

    State semantics:
        materialized=True, source_demanded=True, candidate_only=False:
            Normal materialized construct with source evidence

        materialized=False, source_demanded=True, candidate_only=True:
            Candidate for promotion (e.g., WORKER_CANDIDATE, WORKER_PROMOTION)
            Source demands it but it's not yet a renderable construct

        materialized=True, source_demanded=False, candidate_only=False:
            Compiler-generated scaffolding without explicit source demand

    Design notes:
        - Instance is mutable to allow checker-local state updates during extraction
        - Checkers must not modify ir_ref or context IRs
        - candidate_only=True typically implies materialized=False
        - Future R4 will use this for Worker/Delegation promotion analysis
    """

    construct_id: str
    construct_type: str
    ir_ref: Any | None = None
    materialized: bool = True
    source_demanded: bool = True
    candidate_only: bool = False
    primary_parent_id: str | None = None
    child_construct_ids: list[str] = field(default_factory=list)
    related_edges: list[ConstructEdge] = field(default_factory=list)
    construct_path: tuple[str, ...] = ()
    source_span_ids: list[str] = field(default_factory=list)
    source_section_id: str | None = None
    source_packet_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
