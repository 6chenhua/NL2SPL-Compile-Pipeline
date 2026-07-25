"""Repair metadata contracts shared by constructs and SPL Editing.

This module is pure metadata: no IRS runtime, no SPL Editing strategy runtime,
no handlers, no appliers, and no verifier imports.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

SlotActionability = Literal["editable", "non_editable", "optional_enrichment"]

NonEditableDisposition = Literal[
    "review_only",
    "deferred_validation",
    "developer_only",
    "non_repairable",
]

ActionabilityDecisionStatus = Literal["confirmed", "unresolved"]


@dataclass(frozen=True)
class PatchTypeMeta:
    """Presentation metadata for one supported patch type."""

    patch_type: str
    label_key: str
    description_key: str
    verification_lane: str


@dataclass(frozen=True)
class SlotActionabilityDecision:
    """Explicit product decision for a slot that can produce a completion gap.

    This contract records whether the slot is user-actionable. It does not
    declare repair capability; editable slots still require a coherent
    RepairAffordanceSpec and runtime closure.
    """

    actionability: SlotActionability
    non_editable_disposition: NonEditableDisposition | None
    rationale_code: str
    decision_source_ref: str
    decision_status: ActionabilityDecisionStatus = "confirmed"

    def __post_init__(self) -> None:
        if self.actionability not in {
            "editable",
            "non_editable",
            "optional_enrichment",
        }:
            raise ValueError(f"Unknown actionability: {self.actionability}")
        if self.decision_status not in {"confirmed", "unresolved"}:
            raise ValueError(f"Unknown decision_status: {self.decision_status}")
        valid_dispositions = {
            "review_only",
            "deferred_validation",
            "developer_only",
            "non_repairable",
        }
        if (
            self.non_editable_disposition is not None
            and self.non_editable_disposition not in valid_dispositions
        ):
            raise ValueError(
                "Unknown non_editable_disposition: "
                f"{self.non_editable_disposition}"
            )
        if self.actionability == "non_editable":
            if self.non_editable_disposition is None:
                raise ValueError(
                    "non_editable actionability requires a non_editable_disposition"
                )
        elif self.non_editable_disposition is not None:
            raise ValueError(
                f"{self.actionability} actionability forbids non_editable_disposition"
            )
        if not isinstance(self.rationale_code, str) or not self.rationale_code.strip():
            raise ValueError("rationale_code cannot be blank")
        if not isinstance(self.decision_source_ref, str) or not self.decision_source_ref.strip():
            raise ValueError("decision_source_ref cannot be blank")


@dataclass(frozen=True)
class RepairAffordanceSpec:
    """Machine-readable repair capability declared by an IRS slot.

    Pure metadata — no callables, no class references, no LLM integration.
    SPL Editing reads these at runtime to derive the ``RepairCatalog``.

    Attributes:
        affordance_id: Globally unique ID for this repair capability.
            Naming convention: ``{construct_type_lower}.{descriptive_suffix}``
            (e.g. ``exception_flow.add_handler_step``,
            ``worker_promotion.resolve_contract``).
            Used as a stable key in logs, overlays, API payloads, and
            ``RepairCatalogEntry`` derivation — must never be reused
            across different construct+slot combinations.
        description: Human-readable summary of the repair.
        supported_patch_types: Allowed ``patch_type`` values the LLM may
            propose for this slot.
        default_patch_type: Default patch type when the user doesn't choose.
        handler_id: Identifies the ``IssueRepairHandler`` to invoke.
        context_id: Identifies the ``RepairContextBuilder``.
        target_resolver_id: Identifies the ``IssueTargetResolver``.
        default_verification_lane: ``"A"`` (Assembler Replay) or ``"B"``
            (Normalizer Replay).
        editable_artifacts: Stage-level IR artifact class names the patch
            applier may modify.
        required_evidence_kind: Evidence kind required for apply
            (always ``"user_confirmed_repair"`` in MVP).
        user_facing: Whether this affordance is exposed in the Diagnostics
            Console UI.
        notes: Internal design notes — not used by the runtime.
    """

    affordance_id: str
    description: str
    supported_patch_types: tuple[str, ...] = ()
    default_patch_type: str | None = None
    handler_id: str | None = None
    context_id: str | None = None
    target_resolver_id: str | None = None
    default_verification_lane: str = "A"
    editable_artifacts: tuple[str, ...] = ()
    required_evidence_kind: str = "user_confirmed_repair"
    user_facing: bool = True
    materialization_plan_id: str | None = None
    selectable_ref_policy_id: str | None = None
    intent_schema_id: str | None = None
    required_context_facts: tuple[str, ...] = ()
    stage_authority: str | None = None
    notes: str | None = None
    patch_type_metadata: tuple[PatchTypeMeta, ...] = ()
    """Per-patch-type labels, descriptions, and verification lanes.
    When non-empty, the presentation layer derives individual strategy
    options from this tuple instead of combining ``supported_patch_types``
    into a single composite label."""
    repair_strategy_id: str | None = None
