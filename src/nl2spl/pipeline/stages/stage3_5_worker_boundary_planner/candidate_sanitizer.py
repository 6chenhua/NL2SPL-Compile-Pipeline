"""Candidate sanitizer for API-owned source spans before Stage 3.5b."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any, Literal

from nl2spl.ir.worker_plan_ir import CandidateTaskUnitIR, WorkerBoundaryDecisionIR
from nl2spl.pipeline.stages.stage3_5_worker_boundary_planner.api_exclusion import (
    WorkerBoundaryExclusionView,
)

SanitizedCandidateResultKind = Literal[
    "unchanged",
    "api_only_auto_decision",
    "mixed_trimmed_candidate",
    "mixed_residual_keep_in_main_worker",
    "rejected_invalid",
]


@dataclass(frozen=True)
class SanitizedCandidateResult:
    """Structured sanitizer result projected into Stage 3.5 artifacts."""

    original_candidate_id: str
    result_kind: SanitizedCandidateResultKind
    residual_candidate_id: str | None
    residual_source_span_ids: tuple[str, ...]
    removed_api_span_ids: tuple[str, ...]
    auto_decision: WorkerBoundaryDecisionIR | None
    residual_policy_reason: str | None
    requires_residual_re_evaluation: bool
    audit: Mapping[str, Any]

    def to_payload(self) -> dict[str, Any]:
        return {
            "original_candidate_id": self.original_candidate_id,
            "result_kind": self.result_kind,
            "residual_candidate_id": self.residual_candidate_id,
            "residual_source_span_ids": list(self.residual_source_span_ids),
            "removed_api_span_ids": list(self.removed_api_span_ids),
            "auto_decision": (
                None
                if self.auto_decision is None
                else {
                    "candidate_id": self.auto_decision.candidate_id,
                    "decision": self.auto_decision.decision,
                    "boundary_strength": self.auto_decision.boundary_strength,
                    "boundary_kind": self.auto_decision.boundary_kind,
                    "rejection_reason": self.auto_decision.rejection_reason,
                    "reason": self.auto_decision.reason,
                    "evidence": list(self.auto_decision.evidence),
                }
            ),
            "residual_policy_reason": self.residual_policy_reason,
            "requires_residual_re_evaluation": self.requires_residual_re_evaluation,
            "audit": _jsonable(self.audit),
        }


@dataclass(frozen=True)
class SanitizedCandidateBatch:
    candidates: tuple[CandidateTaskUnitIR, ...]
    auto_decisions: tuple[WorkerBoundaryDecisionIR, ...]
    results: tuple[SanitizedCandidateResult, ...]


def sanitize_candidates_for_api_exclusion(
    candidates: list[CandidateTaskUnitIR],
    exclusion_view: WorkerBoundaryExclusionView,
) -> SanitizedCandidateBatch:
    """Remove confirmed API-owned spans from worker-boundary candidates."""
    sanitized: list[CandidateTaskUnitIR] = []
    auto_decisions: list[WorkerBoundaryDecisionIR] = []
    results: list[SanitizedCandidateResult] = []

    for candidate in candidates:
        candidate_span_ids = tuple(candidate.source_span_ids)
        api_spans = tuple(
            span_id
            for span_id in candidate_span_ids
            if span_id in exclusion_view.api_consumed_span_ids
        )
        residual_spans = tuple(
            span_id
            for span_id in candidate_span_ids
            if span_id not in exclusion_view.api_consumed_span_ids
        )

        if not api_spans:
            sanitized.append(candidate)
            results.append(
                SanitizedCandidateResult(
                    original_candidate_id=candidate.candidate_id,
                    result_kind="unchanged",
                    residual_candidate_id=candidate.candidate_id,
                    residual_source_span_ids=candidate_span_ids,
                    removed_api_span_ids=(),
                    auto_decision=None,
                    residual_policy_reason=None,
                    requires_residual_re_evaluation=False,
                    audit=_audit(candidate, exclusion_view, api_spans, residual_spans),
                )
            )
            continue

        if not residual_spans:
            decision = WorkerBoundaryDecisionIR(
                candidate_id=candidate.candidate_id,
                decision="compile_as_call_api",
                boundary_strength="weak",
                boundary_kind="call_api",
                rejection_reason="single_api_call",
                reason=(
                    "Candidate source spans are already consumed by confirmed "
                    "API invocation authority."
                ),
                evidence=[],
            )
            sanitized.append(candidate)
            auto_decisions.append(decision)
            results.append(
                SanitizedCandidateResult(
                    original_candidate_id=candidate.candidate_id,
                    result_kind="api_only_auto_decision",
                    residual_candidate_id=None,
                    residual_source_span_ids=(),
                    removed_api_span_ids=api_spans,
                    auto_decision=decision,
                    residual_policy_reason="api_only_confirmed_invocation",
                    requires_residual_re_evaluation=False,
                    audit=_audit(candidate, exclusion_view, api_spans, residual_spans),
                )
            )
            continue

        residual_candidate = replace(
            candidate,
            source_span_ids=list(residual_spans),
            risks=_append_unique(
                candidate.risks,
                "insufficient_semantic_boundary",
            ),
        )
        decision = WorkerBoundaryDecisionIR(
            candidate_id=residual_candidate.candidate_id,
            decision="keep_in_main_worker",
            boundary_strength="weak",
            boundary_kind="not_a_worker",
            rejection_reason="insufficient_semantic_boundary",
            reason=(
                "API-owned spans were removed; residual spans require independent "
                "worker-boundary re-evaluation and are kept in main worker by "
                "default."
            ),
            evidence=[],
        )
        sanitized.append(residual_candidate)
        auto_decisions.append(decision)
        results.append(
            SanitizedCandidateResult(
                original_candidate_id=candidate.candidate_id,
                result_kind="mixed_residual_keep_in_main_worker",
                residual_candidate_id=residual_candidate.candidate_id,
                residual_source_span_ids=residual_spans,
                removed_api_span_ids=api_spans,
                auto_decision=decision,
                residual_policy_reason="residual_after_api_exclusion_insufficient",
                requires_residual_re_evaluation=True,
                audit=_audit(candidate, exclusion_view, api_spans, residual_spans),
            )
        )

    return SanitizedCandidateBatch(
        candidates=tuple(sanitized),
        auto_decisions=tuple(auto_decisions),
        results=tuple(results),
    )


def _append_unique(values: list[Any], item: Any) -> list[Any]:
    result = list(values)
    if item not in result:
        result.append(item)
    return result


def _audit(
    candidate: CandidateTaskUnitIR,
    exclusion_view: WorkerBoundaryExclusionView,
    api_spans: tuple[str, ...],
    residual_spans: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "candidate_source_span_ids": list(candidate.source_span_ids),
        "api_call_demand_ids": {
            span_id: list(exclusion_view.api_call_demand_ids_by_span.get(span_id, ()))
            for span_id in api_spans
        },
        "exclusion_authority": exclusion_view.exclusion_authority,
        "removed_api_span_ids": list(api_spans),
        "residual_source_span_ids": list(residual_spans),
    }


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in sorted(value.items())}
    if isinstance(value, tuple | list | set | frozenset):
        return [_jsonable(item) for item in value]
    return value


__all__ = [
    "SanitizedCandidateBatch",
    "SanitizedCandidateResult",
    "sanitize_candidates_for_api_exclusion",
]
