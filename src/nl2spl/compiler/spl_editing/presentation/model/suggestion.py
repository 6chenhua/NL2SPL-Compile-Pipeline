"""Suggestion presentation DTO."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SuggestionPresentationView:
    suggestion_id: str
    title: str
    explanation: str
    expected_effect: tuple[str, ...] = ()
    risks: tuple[str, ...] = ()
    preview: str | None = None
    patch_type: str = ""


__all__ = ["SuggestionPresentationView"]
