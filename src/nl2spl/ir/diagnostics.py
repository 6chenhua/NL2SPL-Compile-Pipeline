"""Compiler diagnostics for requirement fidelity."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from nl2spl.compiler.compile_result import MissingSlot


@dataclass
class CompileDiagnostic:
    """A structured compiler diagnostic about requirement incompleteness.

    Represents issues discovered during compilation: missing information,
    ambiguity, assumptions, and anti-fabrication decisions.  Distinct from
    validation errors which are syntax/reference/structure failures.

    Attributes:
        diagnostic_id: Unique diagnostic identifier
        kind: Diagnostic kind (e.g. missing_output_producer, missing_handler)
        severity: Severity level (info, warning, error)
        message: Human-readable diagnostic message
        target_ref: Reference to the affected SPL element
        source_span_ids: Related source span IDs
        suggested_resolution: Optional hint for resolving the issue
        blocks_rendering: Whether this prevents rendering the affected element
        blocks_completion: Whether this prevents producing a complete SPL
    """

    diagnostic_id: str
    kind: str
    severity: str
    message: str
    target_ref: str | None = None
    source_span_ids: list[str] = field(default_factory=list)
    source_section_id: str | None = None
    source_packet_id: str | None = None
    suggested_resolution: str | None = None
    missing_slot: MissingSlot | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    """Structured payload: e.g. semantic_role, field_name, expected, actual."""
    blocks_rendering: bool = False
    blocks_completion: bool = True


@dataclass
class TraceRecord:
    """A provenance record linking an SPL element to its source evidence.

    Maps a compiler-produced element (step, variable, constraint, worker,
    flow, etc.) back to the source spans that justify its existence, along
    with a relation type describing how the element was derived.

    Attributes:
        target_ref: Reference to the SPL element (e.g. ``step:st1``,
            ``variable:draft``, ``worker:MainWorker``)
        source_span_ids: Source span IDs that evidence this element
        source_section_id: Adapter structural-nl section, when available
        source_packet_id: Adapter packet within a section, when available
        relation: How the element relates to the source —
            ``direct`` (verbatim copy), ``normalized`` (named/typed from
            source wording), ``inferred`` (structural materialization),
            ``assumed`` (compiler-created suggestion)
        explanation: Human-readable description of the provenance
        needs_confirmation: Whether the provenance requires user confirmation
    """

    target_ref: str
    source_span_ids: list[str] = field(default_factory=list)
    source_section_id: str | None = None
    source_packet_id: str | None = None
    relation: str = "direct"
    explanation: str = ""
    needs_confirmation: bool = False


@dataclass
class StepRenderInfo:
    """Renderability side-table entry for a single step.

    Classifies a step by its origin and determines whether it may be
    rendered into executable SPL.  This is checked *before* Stage 11 so
    the renderer only receives verifiably source-backed commands.

    Attributes:
        step_id: Step identifier
        origin: ``source_backed`` | ``handoff_generated`` |
            ``compiler_synthetic`` | ``assumed``
        renderable: Whether this step may be rendered as executable SPL
        render_block_reason: Why the step is blocked, when applicable
    """

    step_id: str
    origin: str
    renderable: bool
    render_block_reason: str | None = None
