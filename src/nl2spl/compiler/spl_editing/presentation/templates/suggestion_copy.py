"""Suggestion presentation copy."""

from __future__ import annotations


def expected_effects(patch_type: str) -> tuple[str, ...]:
    if patch_type == "AddExceptionHandlerStep":
        return (
            "The exception flow will no longer be empty.",
            "The new step will be marked as user-confirmed repair evidence.",
        )
    if patch_type in {"InsertProducerStep", "BindExistingProducerStep"}:
        return (
            "The required output will have a renderable producer.",
            "Producer verification will run through the compiler authority.",
        )
    if patch_type == "CreateWorkerHandoffContract":
        return (
            "The worker delegation will have an explicit handoff contract.",
            "Lane B verification will replay the handoff path.",
        )
    if patch_type.startswith("ConvertDelegation"):
        return (
            "The worker promotion ambiguity will be resolved by conversion.",
            "The created step will be marked as user-confirmed repair evidence.",
        )
    return ("The selected repair patch will be applied after confirmation.",)


__all__ = ["expected_effects"]
