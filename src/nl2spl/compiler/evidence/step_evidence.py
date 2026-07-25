"""Unified step evidence classification.

This module provides a compiler-owned, SPL-Editing‑neutral evidence model
that Gate, ProducerIndex, and IRS can share or align with.

Design rules (per implementation plan):
    * Does NOT import ``nl2spl.compiler.spl_editing``.
    * Does NOT import langchain / handlers / renderer.
    * Does NOT read report / stage debug JSON.
    * Only reads ``StepIR.source_span_ids``, ``StepIR.handoff_id``,
      and ``StepIR.metadata``.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from enum import StrEnum

from nl2spl.ir.step_ir import StepIR


class StepEvidenceKind(StrEnum):
    """Semantic classification of where a step's authority comes from."""

    SOURCE_SPAN = "source_span"
    VALID_HANDOFF = "valid_handoff"
    COMPILER_UNPACK = "compiler_unpack"
    USER_CONFIRMED_REPAIR = "user_confirmed_repair"
    MISSING = "missing"


@dataclass(frozen=True)
class StepEvidence:
    """Multi‑dimensional evidence facts about a single ``StepIR``.

    A single ``primary_kind`` field is NOT the sole truth source.
    The boolean flags allow authorities to make layered decisions
    (e.g. "this step is user-confirmed, but ALSO has a handoff — treat
    as handoff-first").
    """

    primary_kind: StepEvidenceKind
    satisfied: bool

    has_source_span: bool = False
    has_user_confirmed_repair: bool = False
    has_compiler_unpack: bool = False
    has_handoff_id: bool = False
    valid_handoff: bool = False

    source_span_ids: tuple[str, ...] = ()
    repair_patch_id: str | None = None
    related_diagnostic_id: str | None = None
    user_text: str | None = None
    relation: str | None = None
    explanation: str | None = None

    # ------------------------------------------------------------------
    # Semantic accessors (shared vocabulary for IRS / Gate / ProducerIndex)
    # ------------------------------------------------------------------

    def satisfies_source_evidence_slot(self) -> bool:
        """True when the step has ANY valid authority source.

        Matches what ``_source_evidence_slot()`` currently considers
        satisfied: source spans, valid handoff, compiler unpack, or
        user-confirmed repair.
        """
        return self.satisfied

    def requires_handoff_authority(self) -> bool:
        """True when the step carries a ``handoff_id``.

        Gate uses this to preserve handoff‑first routing: even if the step
        is also user‑confirmed, the handoff contract must still be validated.
        """
        return self.has_handoff_id

    def is_user_confirmed(self) -> bool:
        """True when the primary evidence is user confirmation."""
        return self.primary_kind == StepEvidenceKind.USER_CONFIRMED_REPAIR

    def repair_metadata_complete(self) -> bool:
        """True when user‑confirmed repair carries the required audit fields."""
        return (
            self.is_user_confirmed()
            and self.repair_patch_id is not None
            and self.related_diagnostic_id is not None
        )


def classify_step_evidence(
    step: StepIR,
    *,
    valid_handoff_ids: Collection[str] = (),
    allow_unknown_handoff_when_no_index: bool = False,
) -> StepEvidence:
    """Classify the evidence source of a single ``StepIR``.

    Priority order (first match wins):
        1. ``source_span_ids`` non‑empty → ``SOURCE_SPAN``
        2. ``handoff_id`` present AND in ``valid_handoff_ids`` → ``VALID_HANDOFF``
        3. ``handoff_id`` present, index is empty,
           and ``allow_unknown_handoff_when_no_index`` → ``VALID_HANDOFF``
           (compat preservation — see implementation plan §7.7)
        4. ``metadata["origin"] == "compiler_unpack"`` → ``COMPILER_UNPACK``
        5. ``metadata["origin"] == "user_confirmed_repair"`` → ``USER_CONFIRMED_REPAIR``
        6. Otherwise → ``MISSING``

    Args:
        step: The step to classify.
        valid_handoff_ids: Known handoff IDs from the enclosing ``WorkerPlanIR``.
        allow_unknown_handoff_when_no_index: Preserve the existing semantics
            where a step with a handoff_id but no index is still treated as
            ``source_evidence=satisfied``.

    Returns:
        A frozen ``StepEvidence`` fact record.
    """
    # ------------------------------------------------------------------
    # Collect ALL dimensional facts FIRST (per §5.1 multi-dimensional contract).
    # The primary_kind is a classification, not a filter — no fact may be lost.
    # ------------------------------------------------------------------
    has_source_span = bool(step.source_span_ids)
    has_handoff_id = step.handoff_id is not None

    # valid_handoff_ids=None means "no handoff index available at all" (compat).
    # valid_handoff_ids is a collection (possibly empty) means "index explicitly
    # present" — empty means no valid handoffs exist.
    handoff_index_available = valid_handoff_ids is not None
    if handoff_index_available:
        valid_handoff = has_handoff_id and step.handoff_id in valid_handoff_ids
    else:
        valid_handoff = False

    has_compiler_unpack = step.metadata.get("origin") == "compiler_unpack"
    has_user_confirmed_repair = step.metadata.get("origin") == "user_confirmed_repair"

    repair_patch_id = step.metadata.get("repair_patch_id") if has_user_confirmed_repair else None
    related_diagnostic_id = (
        step.metadata.get("related_diagnostic_id") if has_user_confirmed_repair else None
    )
    user_text = step.metadata.get("user_text") if has_user_confirmed_repair else None

    # Determine primary kind by priority
    if has_source_span:
        primary_kind = StepEvidenceKind.SOURCE_SPAN
        satisfied = True
        relation = "direct"
        explanation = None
    elif valid_handoff:
        primary_kind = StepEvidenceKind.VALID_HANDOFF
        satisfied = True
        relation = "handoff"
        explanation = None
    elif has_handoff_id and not handoff_index_available and allow_unknown_handoff_when_no_index:
        primary_kind = StepEvidenceKind.VALID_HANDOFF
        satisfied = True
        relation = "handoff"
        explanation = None
    elif has_compiler_unpack:
        primary_kind = StepEvidenceKind.COMPILER_UNPACK
        satisfied = True
        relation = "generated"
        explanation = "Step generated by compiler deterministic unpack."
    elif has_user_confirmed_repair:
        primary_kind = StepEvidenceKind.USER_CONFIRMED_REPAIR
        satisfied = True
        relation = "inferred"
        explanation = "Step evidence provided by user-confirmed repair."
    else:
        primary_kind = StepEvidenceKind.MISSING
        satisfied = False
        relation = None
        explanation = (
            f"Step '{step.step_id}' has no source-span, handoff, "
            "compiler-unpack, or user-confirmed-repair evidence."
        )

    return StepEvidence(
        primary_kind=primary_kind,
        satisfied=satisfied,
        has_source_span=has_source_span,
        has_user_confirmed_repair=has_user_confirmed_repair,
        has_compiler_unpack=has_compiler_unpack,
        has_handoff_id=has_handoff_id,
        valid_handoff=valid_handoff,
        source_span_ids=tuple(step.source_span_ids),
        repair_patch_id=repair_patch_id,
        related_diagnostic_id=related_diagnostic_id,
        user_text=user_text,
        relation=relation,
        explanation=explanation,
    )
