"""Strict response parsing for Stage 6.5 condition-reference LLM output."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

Confidence = Literal["high", "medium", "low"]


@dataclass(frozen=True)
class LLMConditionReferenceCandidate:
    relation: str
    selected_symbol: str
    qualified_ref: str
    evidence_text: str
    confidence: Confidence
    reason: str | None = None


@dataclass(frozen=True)
class LLMUnresolvedConditionCandidate:
    proposed_symbol_text: str
    evidence_text: str
    reason: str | None = None


@dataclass(frozen=True)
class ConditionReferenceLLMResponse:
    owner_ref: str
    references: tuple[LLMConditionReferenceCandidate, ...]
    unresolved_candidates: tuple[LLMUnresolvedConditionCandidate, ...]


class ConditionReferenceResponseError(ValueError):
    """Raised when a Stage 6.5 LLM response violates the strict schema."""


def parse_condition_reference_response(
    payload: dict[str, Any],
    *,
    expected_owner_ref: str,
) -> ConditionReferenceLLMResponse:
    """Parse a condition-reference LLM response, rejecting authority leaks."""
    forbidden_keys = {"severity", "blocks_rendering", "blocks_completion", "repair_action"}
    if forbidden_keys.intersection(payload):
        raise ConditionReferenceResponseError(
            "Stage 6.5 LLM response must not contain diagnostic authority fields."
        )

    owner_ref = str(payload.get("owner_ref", ""))
    if owner_ref != expected_owner_ref:
        raise ConditionReferenceResponseError(
            f"owner_ref mismatch: expected {expected_owner_ref!r}, got {owner_ref!r}"
        )

    references = tuple(_parse_reference(item) for item in payload.get("references", []))
    unresolved = tuple(
        _parse_unresolved(item) for item in payload.get("unresolved_candidates", [])
    )
    return ConditionReferenceLLMResponse(
        owner_ref=owner_ref,
        references=references,
        unresolved_candidates=unresolved,
    )


def _parse_reference(item: Any) -> LLMConditionReferenceCandidate:
    if not isinstance(item, dict):
        raise ConditionReferenceResponseError("references[] entries must be objects.")
    forbidden_keys = {"severity", "blocks_rendering", "blocks_completion", "repair_action"}
    if forbidden_keys.intersection(item):
        raise ConditionReferenceResponseError(
            "references[] entries must not contain diagnostic authority fields."
        )
    relation = str(item.get("relation", ""))
    if relation != "condition_reads":
        raise ConditionReferenceResponseError("reference relation must be condition_reads.")
    confidence = str(item.get("confidence", ""))
    if confidence not in {"high", "medium", "low"}:
        raise ConditionReferenceResponseError("confidence must be high, medium, or low.")
    selected_symbol = str(item.get("selected_symbol", "")).strip()
    qualified_ref = str(item.get("qualified_ref", "")).strip()
    evidence_text = str(item.get("evidence_text", "")).strip()
    if not selected_symbol or not qualified_ref or not evidence_text:
        raise ConditionReferenceResponseError(
            "selected_symbol, qualified_ref, and evidence_text are required."
        )
    return LLMConditionReferenceCandidate(
        relation=relation,
        selected_symbol=selected_symbol,
        qualified_ref=qualified_ref,
        evidence_text=evidence_text,
        confidence=confidence,  # type: ignore[arg-type]
        reason=str(item["reason"]) if item.get("reason") is not None else None,
    )


def _parse_unresolved(item: Any) -> LLMUnresolvedConditionCandidate:
    if not isinstance(item, dict):
        raise ConditionReferenceResponseError(
            "unresolved_candidates[] entries must be objects."
        )
    proposed = str(item.get("proposed_symbol_text", "")).strip()
    evidence = str(item.get("evidence_text", "")).strip()
    if not proposed or not evidence:
        raise ConditionReferenceResponseError(
            "proposed_symbol_text and evidence_text are required."
        )
    return LLMUnresolvedConditionCandidate(
        proposed_symbol_text=proposed,
        evidence_text=evidence,
        reason=str(item["reason"]) if item.get("reason") is not None else None,
    )
