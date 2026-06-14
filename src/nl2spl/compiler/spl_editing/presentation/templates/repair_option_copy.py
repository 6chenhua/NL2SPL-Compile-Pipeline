"""Repair option display copy.

This module does not define repair capability.  It only labels options that
RepairCatalog/runtime registry have already made available.
"""

from __future__ import annotations

_PATCH_LABELS = {
    "AddExceptionHandlerStep": "Add handler step",
    "InsertProducerStep": "Insert producer step",
    "BindExistingProducerStep": "Bind existing producer step",
    "CreateWorkerHandoffContract": "Create worker handoff contract",
    "ConvertDelegationIntentToMainFlowStep": "Convert to main-flow step",
    "ConvertDelegationIntentToRequestInput": "Ask user for missing information",
}

_PATCH_DESCRIPTIONS = {
    "AddExceptionHandlerStep": (
        "Use this to add an explicit action inside the exception flow."
    ),
    "InsertProducerStep": (
        "Use this to create a new step that produces the required output."
    ),
    "BindExistingProducerStep": (
        "Use this to mark an existing renderable step as the output producer."
    ),
    "CreateWorkerHandoffContract": (
        "Use this if the task should become a separate worker handoff."
    ),
    "ConvertDelegationIntentToMainFlowStep": (
        "Use this if the action should stay inside the main worker."
    ),
    "ConvertDelegationIntentToRequestInput": (
        "Use this if missing contract details should be requested at runtime."
    ),
}


def patch_label(patch_type: str) -> str:
    return _PATCH_LABELS.get(patch_type, patch_type or "Repair option")


def patch_description(patch_type: str) -> str:
    return _PATCH_DESCRIPTIONS.get(
        patch_type, "Use this repair option if it matches the intended edit."
    )


def option_label(patch_types: tuple[str, ...]) -> str:
    labels = [patch_label(pt) for pt in patch_types]
    return " / ".join(labels) if labels else "No repair option available"


__all__ = ["option_label", "patch_description", "patch_label"]
