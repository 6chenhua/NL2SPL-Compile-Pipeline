"""Validated LLM-generated, issue-specific presentation JSON."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any, Protocol

from nl2spl.compiler.spl_editing.presentation.contract.availability import (
    RepairOptionAvailability,
)
from nl2spl.compiler.spl_editing.presentation.model.issue import (
    IssueDetailPresentationView,
)

_SYSTEM_PROMPT = """Explain one compiler issue to a non-expert user.
Return one JSON object only with: headline, problem, impact,
source_interpretation, option_guidance, recommended_option,
recommendation_reason, and questions. option_guidance is an array containing
each supplied option exactly once as {option, when_to_choose, tradeoff}.
Use only supplied facts. Never invent requirements, repair options, workers,
steps, inputs, outputs, or invocation points. recommended_option must be an
available supplied option, or null. Use the requested language and do not
expose internal identifiers.
"""


class IssueExplanationLLM(Protocol):
    def generate_json(self, system_prompt: str, user_prompt: str) -> str: ...


@dataclass(frozen=True)
class RepairOptionExplanation:
    option: int
    label: str
    description: str
    available: bool
    when_to_choose: str
    tradeoff: str


@dataclass(frozen=True)
class IssueExplanation:
    schema_version: str
    issue_id: str
    language: str
    generation_source: str
    headline: str
    problem: str
    impact: str
    source_interpretation: str | None
    missing_information: tuple[str, ...]
    options: tuple[RepairOptionExplanation, ...]
    recommended_option: int | None
    recommendation_reason: str
    questions: tuple[str, ...]
    generation_warning: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class IssueExplanationGenerator:
    def __init__(self, llm: IssueExplanationLLM) -> None:
        self._llm = llm

    def generate(
        self,
        detail: IssueDetailPresentationView,
        *,
        language: str = "zh-CN",
    ) -> IssueExplanation:
        prompt = json.dumps(
            {"requested_language": language, "compiler_facts": _facts(detail)},
            ensure_ascii=False,
        )
        try:
            payload = json.loads(self._llm.generate_json(_SYSTEM_PROMPT, prompt))
            return _validate(detail, language, payload)
        except Exception as exc:
            return _fallback(detail, language, str(exc))


def _facts(detail: IssueDetailPresentationView) -> dict[str, Any]:
    return {
        "issue_id": detail.issue_id,
        "compiler_title": detail.title,
        "diagnostic_kind": detail.advanced.diagnostic_kind,
        "construct_type": detail.advanced.irs_construct_type,
        "missing_information": list(detail.missing_items),
        "source_excerpt": detail.source_context,
        "compiler_suggested_resolution": detail.suggested_resolution,
        "repair_options": [
            {
                "option": index,
                "label": option.label,
                "description": option.description,
                "available": option.availability == RepairOptionAvailability.AVAILABLE,
            }
            for index, option in enumerate(detail.available_repairs, 1)
        ],
    }


def _validate(
    detail: IssueDetailPresentationView,
    language: str,
    payload: object,
) -> IssueExplanation:
    if not isinstance(payload, dict):
        raise TypeError("response must be an object")
    guidance = payload.get("option_guidance")
    if not isinstance(guidance, list):
        raise TypeError("option_guidance must be an array")
    by_number: dict[int, dict[str, Any]] = {}
    for item in guidance:
        if not isinstance(item, dict) or not isinstance(item.get("option"), int):
            raise TypeError("invalid option guidance")
        by_number[item["option"]] = item
    expected = set(range(1, len(detail.available_repairs) + 1))
    if set(by_number) != expected:
        raise ValueError("option guidance does not match compiler options")
    options = tuple(
        RepairOptionExplanation(
            option=index,
            label=option.label,
            description=option.description,
            available=option.availability == RepairOptionAvailability.AVAILABLE,
            when_to_choose=_text(by_number[index], "when_to_choose"),
            tradeoff=_text(by_number[index], "tradeoff"),
        )
        for index, option in enumerate(detail.available_repairs, 1)
    )
    recommended = payload.get("recommended_option")
    if recommended is not None:
        if not isinstance(recommended, int) or recommended not in expected:
            raise ValueError("invalid recommended option")
        if not options[recommended - 1].available:
            raise ValueError("recommended option is unavailable")
    questions = payload.get("questions", [])
    if not isinstance(questions, list) or any(not isinstance(q, str) for q in questions):
        raise TypeError("questions must be strings")
    return IssueExplanation(
        schema_version="issue_explanation.v1",
        issue_id=detail.issue_id,
        language=language,
        generation_source="llm",
        headline=_text(payload, "headline"),
        problem=_text(payload, "problem"),
        impact=_text(payload, "impact"),
        source_interpretation=_optional_text(payload.get("source_interpretation")),
        missing_information=detail.missing_items,
        options=options,
        recommended_option=recommended,
        recommendation_reason=_text(payload, "recommendation_reason"),
        questions=tuple(q.strip()[:1200] for q in questions[:3] if q.strip()),
    )


def _fallback(
    detail: IssueDetailPresentationView,
    language: str,
    warning: str,
) -> IssueExplanation:
    return IssueExplanation(
        schema_version="issue_explanation.v1",
        issue_id=detail.issue_id,
        language=language,
        generation_source="deterministic_fallback",
        headline=detail.title,
        problem=detail.what_was_detected,
        impact=detail.why_it_matters,
        source_interpretation=detail.source_context,
        missing_information=detail.missing_items,
        options=tuple(
            RepairOptionExplanation(
                index,
                option.label,
                option.description,
                option.availability == RepairOptionAvailability.AVAILABLE,
                option.description,
                "Review the generated patch before applying it.",
            )
            for index, option in enumerate(detail.available_repairs, 1)
        ),
        recommended_option=None,
        recommendation_reason="Live explanation unavailable; no option was inferred.",
        questions=(),
        generation_warning=warning[:300],
    )


def _text(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"{key} must be non-empty text")
    return value.strip()[:1200]


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("source_interpretation must be text or null")
    return value.strip()[:1200] or None


__all__ = ["IssueExplanation", "IssueExplanationGenerator", "IssueExplanationLLM"]
