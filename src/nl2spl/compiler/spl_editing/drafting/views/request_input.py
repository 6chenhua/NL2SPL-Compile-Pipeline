"""REQUEST_INPUT value-target facts exposed to future drafting providers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RequestInputDraftingView:
    target_ref: str
    value_target_gap: str | None

    @classmethod
    def from_target(cls, target) -> RequestInputDraftingView:
        return cls(target_ref=target.target_ref, value_target_gap=target.canonical_name)

