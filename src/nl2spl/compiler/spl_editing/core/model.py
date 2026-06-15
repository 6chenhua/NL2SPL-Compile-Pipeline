"""SPL Editing core data model.

All types are frozen dataclasses.  No type uses raw ``dict[str, Any]``
as a primary field — structured payloads have dedicated types.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any, Literal, overload

from nl2spl.ir.diagnostics import CompileDiagnostic, DiagnosticIRSRef

# ---------------------------------------------------------------------------
# EditableIssue — one user-facing repair candidate
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EditableIssue:
    """A single user-actionable issue extracted from compile diagnostics.

    Attributes:
        issue_id: Stable identifier for this issue within a run.
        primary_diagnostic_id: The primary diagnostic that drives repair.
        related_diagnostic_ids: All diagnostic IDs in this issue group.
        issue_group_id: Shared group key (from R4/R5 grouping metadata).
        kind: Diagnostic kind (e.g. ``missing_handler``).
        target_ref: Human-readable target reference.
        irs_ref: Structured IRS source reference.
        missing_slot: Slot name that triggered the diagnostic.
        source_span_ids: Related source spans.
        message: Human-readable summary.
        suggested_resolution: Optional compiler-suggested resolution hint.
        blocks_rendering: Whether the gap blocks SPL rendering.
        blocks_completion: Whether the gap blocks compile completion.
        authority: Source authority string.
        affordance_ids: Allowed affordance IDs for this issue.
        default_affordance_id: Default affordance (first in list).
        repairable: Whether this issue can enter Fix-with-AI.
        repairability: ``editable`` / ``review_only`` / ``non_repairable``.
    """

    issue_id: str
    primary_diagnostic_id: str
    related_diagnostic_ids: tuple[str, ...]
    issue_group_id: str | None
    kind: str
    target_ref: str
    irs_ref: DiagnosticIRSRef
    missing_slot: str | None
    source_span_ids: tuple[str, ...]
    message: str
    suggested_resolution: str | None = None
    blocks_rendering: bool = False
    blocks_completion: bool = True
    authority: str = "post_normalize_irs"
    affordance_ids: tuple[str, ...] = ()
    default_affordance_id: str | None = None
    repairable: bool = True
    repairability: Literal["editable", "review_only", "non_repairable"] = "editable"


# ---------------------------------------------------------------------------
# EditingSession
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EditingSession:
    """A single user editing session tied to one issue.

    Created when the user selects an issue for repair.  Holds the base
    snapshot identity so we can detect stale revisions.
    """

    session_id: str
    compile_run_id: str
    artifact_snapshot_id: str
    overlay_version: int
    issue: EditableIssue
    created_at: str


# ---------------------------------------------------------------------------
# RepairTarget — resolved editable artifact target
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RepairTarget:
    """The stage-level artifact target for a repair patch.

    Resolved from an ``EditableIssue`` by an ``IssueTargetResolver``.
    """

    target_ref: str
    target_kind: str
    irs_ref: DiagnosticIRSRef
    affordance_id: str
    construct_path: tuple[str, ...]
    worker_id: str | None = None
    editable_artifacts: tuple[str, ...] = ()
    subtype: str | None = None


# ---------------------------------------------------------------------------
# RepairContext — issue-specific data gathered for the LLM handler
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RepairContext:
    """Issue-specific context gathered for the repair handler.

    Must be bounded — not the entire ``intermediate`` dict.
    """

    issue: EditableIssue
    target: RepairTarget
    related_diagnostics: tuple[CompileDiagnostic, ...] = ()
    source_spans: tuple[Any, ...] = ()
    worker_scope: str | None = None
    related_steps: tuple[Any, ...] = ()
    related_outputs: tuple[str, ...] = ()
    related_worker_plan_refs: tuple[str, ...] = ()
    user_instruction: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# RepairEvidence — user-confirmed repair provenance
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RepairEvidence:
    """Evidence that the user confirmed this repair.

    Stored alongside the patched artifact to distinguish user-confirmed
    repairs from AI suggestions.
    """

    evidence_kind: Literal["user_confirmed_repair"] = "user_confirmed_repair"
    user_text: str = ""
    related_source_span_ids: tuple[str, ...] = ()
    related_diagnostic_id: str = ""


# ---------------------------------------------------------------------------
# RepairPatch — typed repair payload + metadata
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PatchPrecondition:
    """A named precondition checked before apply."""

    precondition_id: str
    description: str
    satisfied: bool = True


@dataclass(frozen=True)
class RepairPatch:
    """A typed repair patch with preconditions and evidence.

    This is what the backend applies (after user confirmation), NOT
    the LLM-generated suggestion.
    """

    patch_id: str
    affordance_id: str
    patch_type: str
    target_ref: str
    irs_ref: DiagnosticIRSRef
    base_compile_run_id: str
    artifact_snapshot_id: str
    overlay_version: int
    payload: Any  # typed per patch family (e.g. AddExceptionHandlerStepPayload)
    preconditions: tuple[PatchPrecondition, ...] = ()
    evidence: RepairEvidence = field(default_factory=RepairEvidence)
    verification_lane: str = "A"


# ---------------------------------------------------------------------------
# RepairSuggestion — LLM candidate + preview (NOT apply authority)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RepairSuggestion:
    """A single repair candidate generated by the LLM handler.

    The ``spl_preview`` is display-only.  The ``patch`` is the
    structured authority — only it carries the payload that the
    applier acts on after user confirmation.
    """

    suggestion_id: str
    session_id: str
    affordance_id: str
    title: str
    explanation: str
    patch: RepairPatch
    spl_preview: str | None = None
    expected_effect: tuple[str, ...] = ()
    risks: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# VerificationResult
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SuggestionGenerationResult:
    """Structured result of suggestion generation.

    Carries readiness status and suggestions (if any).  Blocked/unavailable
    states carry empty suggestions and reasons — never squashed to ``()``.
    """

    status: str
    """ready | ready_low_confidence | generation_blocked | repair_unavailable."""
    suggestions: tuple[Any, ...] = ()  # RepairSuggestion instances
    reasons: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def __bool__(self) -> bool:
        return bool(self.suggestions)

    def __len__(self) -> int:
        return len(self.suggestions)

    def __iter__(self) -> Iterator[Any]:
        return iter(self.suggestions)

    @overload
    def __getitem__(self, index: int) -> Any: ...

    @overload
    def __getitem__(self, index: slice) -> tuple[Any, ...]: ...

    def __getitem__(self, index: int | slice) -> Any | tuple[Any, ...]:
        return self.suggestions[index]


@dataclass(frozen=True)
class VerificationResult:
    """Outcome of running verification after patch apply."""

    session_id: str
    patch_id: str
    accepted: bool
    lane: str
    resolved_diagnostic_ids: tuple[str, ...] = ()
    new_blocking_diagnostic_ids: tuple[str, ...] = ()
    diagnostic_diff_summary: str = ""
    failure_reasons: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# PatchApplyResult — structured return from patch applier (U3.5)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RepairEvidenceRef:
    """Evidence reference for a changed artifact.

    Ties a changed artifact back to the repair patch and diagnostic
    that motivated the change.  Used by ``GenericEvidenceVerifier``
    to confirm every changed artifact carries the required evidence.
    """

    artifact_ref: str
    """Stable reference like ``step:{worker_id}:{step_id}`` or ``handoff:{handoff_id}``."""

    evidence_kind: Literal["user_confirmed_repair"] = "user_confirmed_repair"
    repair_patch_id: str = ""
    related_diagnostic_id: str = ""
    user_text: str = ""


@dataclass(frozen=True)
class PatchApplyResult:
    """Structured result returned by a patch applier.

    In addition to the patched snapshot and overlay event, exposes
    ``changed_refs`` and ``evidence_refs`` so that verification and
    provenance can generically audit repair evidence without needing
    patch-specific knowledge.
    """

    patched_snapshot: Any  # ArtifactSnapshot (forward-ref to avoid circular import)
    overlay_event: Any  # OverlayEvent
    changed_refs: tuple[str, ...] = ()
    """Stable refs for changed artifacts, e.g. ``step:{wid}:{step_id}``."""

    changed_step_ids: tuple[str, ...] = ()
    """Step IDs created or modified by this patch."""

    changed_handoff_ids: tuple[str, ...] = ()
    """Handoff IDs created or modified by this patch."""

    evidence_refs: tuple[RepairEvidenceRef, ...] = ()
    """Per-artifact evidence references for GenericEvidenceVerifier."""


@dataclass(frozen=True)
class PatchTypeContract:
    """Declarative contract for a patch bundle type.

    Registered at bundle creation time so that the registry, audit
    tests, and GenericEvidenceVerifier can check evidence obligations
    without patch-specific knowledge.
    """

    patch_type: str
    produces_step_ir: bool = False
    produces_handoff_ir: bool = False
    requires_user_confirmed_evidence: bool = True
    evidence_targets: tuple[str, ...] = ()
    """Expected kinds of evidence targets (e.g. ``("step",)``, ``("handoff",)``)."""
