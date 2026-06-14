"""Verification presentation DTO."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class VerificationPresentationView:
    status: Literal["accepted", "rejected"]
    resolved: tuple[str, ...] = ()
    new_blocking_diagnostics: tuple[str, ...] = ()
    authority_summary: tuple[str, ...] = ()
    new_snapshot_id: str | None = None
    overlay_version: int | None = None
    updated_spl: str | None = None


__all__ = ["VerificationPresentationView"]
