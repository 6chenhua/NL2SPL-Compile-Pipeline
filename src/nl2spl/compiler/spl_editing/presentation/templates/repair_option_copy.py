from __future__ import annotations

from typing import Any

_PATCH_LABELS = {
    "AddExceptionHandlerStep": "Add handler step",
    "InsertProducerStep": "Insert producer step",
    "CreateWorkerHandoffContract": "Create worker handoff contract",
    "ConvertDelegationIntentToMainFlowStep": "Convert to main-flow step",
    "ConvertDelegationIntentToRequestInput": "Ask user for missing information",
}

_PATCH_DESCRIPTIONS = {
    "AddExceptionHandlerStep": ("Use this to add an explicit action inside the exception flow."),
    "InsertProducerStep": ("Use this to create a new step that produces the required output."),
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


_STRATEGY_LABELS = {
    "exception_flow.complete_handler_action.v1": "Complete Exception Handler Action",
    "required_output.materialize_producer.v1": "Materialize Producer for Required Output",
    "worker_delegation.complete_closure.v1": "Complete Worker Delegation Handoff Contract",
}


def strategy_label(strategy_id: str) -> str:
    return _STRATEGY_LABELS.get(strategy_id, strategy_id or "Repair strategy")


def option_label_for_entry(entry: Any) -> str:
    strategy_id = getattr(entry, "repair_strategy_id", None)
    if strategy_id:
        strategy_display_label = getattr(entry, "strategy_display_label", None)
        if strategy_display_label:
            return strategy_display_label
        return strategy_label(strategy_id)
    patch_types = getattr(entry, "supported_" + "patch_types", ())
    return option_label(patch_types)


__all__ = ["option_label", "patch_description", "patch_label", "option_label_for_entry", "strategy_label"]
