"""Presentation template keys."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IssueTemplateKey:
    category: str
    construct_type: str = ""
    slot_name: str = ""
    diagnostic_kind: str = ""
    affordance_id: str = ""


__all__ = ["IssueTemplateKey"]
