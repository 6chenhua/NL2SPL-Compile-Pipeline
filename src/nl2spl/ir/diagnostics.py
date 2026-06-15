"""Compiler diagnostics for requirement fidelity."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, TYPE_CHECKING

if TYPE_CHECKING:
    from nl2spl.compiler.compile_result import MissingSlot

# ---------------------------------------------------------------------------
# Structured IRS reference stored in CompileDiagnostic.metadata["irs_ref"]
# ---------------------------------------------------------------------------

SourceAuthority = Literal[
    "post_normalize_irs",
    "producer_index",
    "stage_local_irs",
    "selected_promoted_stage_local_irs",
    "gate",
]

METADATA_KEY_IRS_REF = "irs_ref"
METADATA_KEY_AUTHORITY = "authority"

# ---------------------------------------------------------------------------
# R4 Producer issue grouping metadata keys
# ---------------------------------------------------------------------------

Repairability = Literal["editable", "review_only", "non_repairable"]
"""Repairability classification for a diagnostic.

``editable`` — the diagnostic maps to an editable issue that can enter
    the Fix-with-AI flow.
``review_only`` — the diagnostic is displayed but cannot be repaired
    through SPL Editing (e.g. ``unspecified_output_missing_producer``).
``non_repairable`` — the diagnostic is an internal compiler signal,
    not a user-actionable repair target (e.g. ``resource_kind_mismatch``).
"""

IssueRole = Literal["primary", "alias", "context"]
"""Role of a diagnostic within a grouped editable issue.

``primary`` — the main editable diagnostic driving the repair.
``alias`` — a related diagnostic referring to the same issue via a
    different construct or slot.
``context`` — a non-repairable diagnostic in the same group that
    provides additional information but does not control the repair.
"""

# Backward-compatible alias — R4 producer grouping originally used a
# producer-specific name.  All new code should use IssueRole.
ProducerIssueRole = IssueRole

METADATA_KEY_ISSUE_GROUP_ID = "issue_group_id"
METADATA_KEY_PRIMARY_DIAGNOSTIC_ID = "primary_diagnostic_id"
METADATA_KEY_RELATED_DIAGNOSTIC_IDS = "related_diagnostic_ids"
METADATA_KEY_REPAIRABILITY = "repairability"
METADATA_KEY_ISSUE_ROLE = "issue_role"
"""Generic issue role key.  Used by both R4 producer grouping and R5
worker/delegation promotion."""

# Deprecated — use METADATA_KEY_ISSUE_ROLE instead.
METADATA_KEY_PRODUCER_ISSUE_ROLE = METADATA_KEY_ISSUE_ROLE


@dataclass(frozen=True)
class DiagnosticIRSRef:
    """Structured IRS reference stored in ``CompileDiagnostic.metadata["irs_ref"]``.

    Provides a stable machine-readable link from a final diagnostic back to
    the IRS construct type, construct instance, and slot that produced it.
    SPL Editing uses this reference to look up repair affordances and
    determine the right patch handler.

    Attributes:
        construct_type: IRS construct type (e.g. ``EXCEPTION_FLOW``).
        construct_id: Unique construct instance identifier.
        slot_name: Slot that emitted the diagnostic.
        construct_path: Hierarchical path tuple for reporting/discovery.
        source_authority: Which compiler authority produced the diagnostic.
    """

    construct_type: str
    construct_id: str
    slot_name: str
    construct_path: tuple[str, ...] = ()
    source_authority: SourceAuthority = "post_normalize_irs"

    def to_dict(self) -> dict[str, Any]:
        """Serialize to the dict stored in ``CompileDiagnostic.metadata["irs_ref"]``."""
        return {
            "construct_type": self.construct_type,
            "construct_id": self.construct_id,
            "slot_name": self.slot_name,
            "construct_path": list(self.construct_path),
            "source_authority": self.source_authority,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DiagnosticIRSRef:
        """Deserialize from a ``CompileDiagnostic.metadata["irs_ref"]`` dict."""
        return cls(
            construct_type=data["construct_type"],
            construct_id=data["construct_id"],
            slot_name=data["slot_name"],
            construct_path=tuple(data.get("construct_path", [])),
            source_authority=data.get("source_authority", "post_normalize_irs"),
        )


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
        metadata: Extension data for structured evidence details.
            For ``user_confirmed_repair`` steps, carries
            ``repair_patch_id``, ``related_diagnostic_id``, ``user_text``.
    """

    target_ref: str
    source_span_ids: list[str] = field(default_factory=list)
    source_section_id: str | None = None
    source_packet_id: str | None = None
    relation: str = "direct"
    explanation: str = ""
    needs_confirmation: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


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
