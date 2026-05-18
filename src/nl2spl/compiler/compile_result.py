"""Compiler result types for the NL2SPL pipeline.

Defines the public result interface: completeness, diagnostics, assumptions,
traces, and the full CompileResult container.  These types are separate from
pipeline-internal IRs and are the stable API surface for callers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from nl2spl.ir.diagnostics import CompileDiagnostic, TraceRecord

DiagnosticKind = Literal[
    "missing_handler",
    "missing_output_producer",
    "type_or_contract_ambiguity",
    "assumed_command_not_renderable",
    "unmapped_behavior_span",
    "missing_provenance",
    "semantic_conflict",
]

Severity = Literal["info", "warning", "error"]
Completeness = Literal["complete", "partial", "blocked"]
TraceRelation = Literal["direct", "normalized", "inferred", "assumed"]


@dataclass
class MissingSlot:
    """A gap in the requirement that blocks a specific SPL element.

    Describes *what* is missing, *why* it matters, and optionally suggests
    a human-facing question the user could answer to fill the gap.
    """

    slot_name: str
    required_for: str
    reason: str
    source_span_ids: list[str] = field(default_factory=list)
    suggested_question: str | None = None


@dataclass
class CompileAssumption:
    """A compiler-created suggestion that was NOT rendered into SPL.

    Assumptions capture behaviour the compiler could infer but that lacks
    explicit source backing.  They appear in the readable report, not in
    executable SPL.
    """

    assumption_id: str
    target_ref: str
    source_span_ids: list[str] = field(default_factory=list)
    text: str = ""
    reason: str = ""
    suggested_resolution: str | None = None
    related_missing_slot: str | None = None
    related_diagnostic_id: str | None = None


@dataclass
class CompileResult:
    """Full compiler output — SPL text plus structured metadata.

    This is the stable public result type.  Internal PipelineResult mirrors
    these fields so existing callers are not broken during the transition.
    """

    spl_text: str
    completeness: Completeness = "complete"
    diagnostics: list[CompileDiagnostic] = field(default_factory=list)
    traces: list[TraceRecord] = field(default_factory=list)
    assumptions: list[CompileAssumption] = field(default_factory=list)
    adapter_warnings: list[str] = field(default_factory=list)
    validation_errors: list[str] = field(default_factory=list)
    validation_warnings: list[str] = field(default_factory=list)
    readable_report: str = ""
