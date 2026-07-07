"""Shared types for drafting context views."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DraftingViewSource:
    source_id: str
    authority: str
    evidence_refs: tuple[str, ...] = ()

