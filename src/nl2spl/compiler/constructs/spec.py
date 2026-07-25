"""Construct IRS static specification types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from nl2spl.compiler.repair_contracts import (
    RepairAffordanceSpec,
    SlotActionabilityDecision,
)

ExistencePolicy = Literal[
    "source_signal_required",
    "compiler_default_allowed",
    "grammar_required_if_parent_exists",
]

NoDemandBehavior = Literal[
    "do_not_generate",
    "generate_default",
    "report_ambiguity",
]

@dataclass
class SlotSpec:
    """A single information slot within a SPL construct."""

    slot_name: str
    syntax_required: bool = False
    required_for_partial: bool = False
    required_for_complete: bool = False
    renderable_without: bool = False
    evidence_kinds: list[str] = field(default_factory=list)
    missing_diagnostic: str | None = None
    can_be_inferred: bool = False
    can_be_suggested: bool = True
    notes: str | None = None
    repair_affordances: tuple[RepairAffordanceSpec, ...] = ()
    actionability_decision: SlotActionabilityDecision | None = None
    """Repair capabilities for SPL Editing.  Default empty — slots without
    affordances are non-repairable in the MVP Diagnostics Console."""



    def requires_actionability_decision(self) -> bool:
        """Return whether this slot is in the mandatory audit scope."""
        return bool(
            self.required_for_partial
            or self.required_for_complete
            or self.missing_diagnostic is not None
            or self.repair_affordances
        )

@dataclass
class ConstructIRS:
    """Information Requirements Spec for one SPL construct type."""

    construct_type: str
    existence_policy: ExistencePolicy
    source_signals: list[str]
    slots: list[SlotSpec]
    no_demand_behavior: NoDemandBehavior = "do_not_generate"
    partial_rendering_allowed: bool = False
    description: str | None = None

    # ------------------------------------------------------------------
    # Read-only helpers (no evaluator logic — Phase 1 data model only)
    # ------------------------------------------------------------------

    def get_slot(self, name: str) -> SlotSpec | None:
        """Return the SlotSpec with *name*, or None."""
        for slot in self.slots:
            if slot.slot_name == name:
                return slot
        return None

    def required_slots_for_partial(self) -> list[SlotSpec]:
        """Slots that must be satisfied to produce even a partial construct."""
        return [s for s in self.slots if s.required_for_partial]

    def required_slots_for_complete(self) -> list[SlotSpec]:
        """Slots that must be satisfied to produce a semantically complete construct."""
        return [s for s in self.slots if s.required_for_complete]
