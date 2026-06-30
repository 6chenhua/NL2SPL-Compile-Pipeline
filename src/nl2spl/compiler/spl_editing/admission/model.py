"""Typed user-declared facts admitted for repair materialization."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NewOutputDeclarationDraft:
    local_id: str
    display_name: str
    semantic_description: str
    data_type_hint: str | None = None


@dataclass(frozen=True)
class AdmittedOutputDeclaration:
    output_id: str
    canonical_name: str
    display_name: str
    semantic_description: str
    data_type: str
    evidence_ref: str


__all__ = ["AdmittedOutputDeclaration", "NewOutputDeclarationDraft"]
