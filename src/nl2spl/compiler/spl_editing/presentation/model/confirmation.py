"""Apply confirmation presentation DTO."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ConfirmationRefItem:
    """A single selected reference displayed in the confirmation view."""

    ref_id: str
    display_label: str
    ref_kind: str
    ref_role: str


@dataclass(frozen=True)
class ApplyConfirmationView:
    suggestion_id: str
    title: str
    will_do: tuple[str, ...] = ()
    will_not_do: tuple[str, ...] = ()
    verification_lane: str = "A"
    requires_user_confirmation: bool = True
    # R6: materialization-aware fields
    target_construct: str = ""
    target_name: str = ""
    selected_refs: tuple[ConfirmationRefItem, ...] = ()
    intent_summary: str = ""
    materialization_plan_id: str = ""


__all__ = ["ApplyConfirmationView", "ConfirmationRefItem"]
