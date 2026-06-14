"""Apply confirmation presentation DTO."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ApplyConfirmationView:
    suggestion_id: str
    title: str
    will_do: tuple[str, ...] = ()
    will_not_do: tuple[str, ...] = ()
    verification_lane: str = "A"
    requires_user_confirmation: bool = True


__all__ = ["ApplyConfirmationView"]
