"""Read-only API ownership view for Stage 3.5 worker-boundary planning."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class WorkerBoundaryExclusionView:
    """Minimal API authority projection consumed by worker-boundary logic.

    The view is not an IRS construct, diagnostic, repair target, or
    materialization artifact. It explains which source spans are already owned
    by confirmed API invocation authority and keeps enough audit data to explain
    why those spans must not become child-worker-owned executable work.
    """

    api_consumed_span_ids: frozenset[str]
    api_residual_span_ids: frozenset[str]
    api_call_demand_ids_by_span: Mapping[str, tuple[str, ...]]
    exclusion_authority: Literal["external_capability_intent_plan"] = (
        "external_capability_intent_plan"
    )
    audit_payload: Mapping[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        """Return a stable JSON-serializable payload."""
        return {
            "api_consumed_span_ids": sorted(self.api_consumed_span_ids),
            "api_residual_span_ids": sorted(self.api_residual_span_ids),
            "api_call_demand_ids_by_span": {
                span_id: list(self.api_call_demand_ids_by_span[span_id])
                for span_id in sorted(self.api_call_demand_ids_by_span)
            },
            "exclusion_authority": self.exclusion_authority,
            "audit_payload": _jsonable(self.audit_payload),
        }


def build_worker_boundary_exclusion_view(
    external_capability_intent_plan: object | Mapping[str, Any] | None,
) -> WorkerBoundaryExclusionView:
    """Build a Stage 3.5 API exclusion view from structured resolver output.

    ``external_capability_intent_plan`` may be the typed
    ``ExternalCapabilityIntentPlanIR`` or its persisted ``to_payload`` form.
    Only confirmed, executable, admitted invocations enter
    ``api_consumed_span_ids``.
    """
    payload = _unwrap_result(external_capability_intent_plan)
    intents = _iter_intents(payload)

    consumed: set[str] = set()
    residual: set[str] = set()
    demand_ids_by_span: dict[str, set[str]] = {}
    intent_audit: list[dict[str, Any]] = []

    for intent in intents:
        intent_id = str(_get(intent, "intent_id", ""))
        source_span_ids = tuple(str(item) for item in _get(intent, "source_span_ids", ()))
        status = {
            "boundary_status": _get(intent, "boundary_status", None),
            "invocation_status": _get(intent, "invocation_status", None),
            "capability_admission_status": _get(
                intent, "capability_admission_status", None,
            ),
            "invocation_admission_status": _get(
                intent, "invocation_admission_status", None,
            ),
        }
        is_confirmed_invocation = (
            status["boundary_status"] == "confirmed_external"
            and status["invocation_status"] == "executable"
            and status["capability_admission_status"] == "confirmed_capability"
            and status["invocation_admission_status"] == "confirmed_invocation"
        )
        call_demand_id = (
            _stable_capability_demand_id("api_call", intent_id)
            if is_confirmed_invocation and intent_id
            else None
        )
        if is_confirmed_invocation:
            for span_id in source_span_ids:
                consumed.add(span_id)
                demand_ids_by_span.setdefault(span_id, set()).add(str(call_demand_id))
        elif status["capability_admission_status"] == "confirmed_capability":
            residual.update(source_span_ids)

        intent_audit.append(
            {
                "intent_id": intent_id,
                "source_span_ids": list(source_span_ids),
                "operation_text": _get(intent, "operation_text", None),
                "capability_surface": _get(intent, "capability_surface", None),
                "api_call_demand_id": call_demand_id,
                "consumed_by_api_authority": is_confirmed_invocation,
                **status,
            }
        )

    residual.difference_update(consumed)
    return WorkerBoundaryExclusionView(
        api_consumed_span_ids=frozenset(consumed),
        api_residual_span_ids=frozenset(residual),
        api_call_demand_ids_by_span={
            span_id: tuple(sorted(demand_ids))
            for span_id, demand_ids in sorted(demand_ids_by_span.items())
        },
        audit_payload={
            "authority": "external_capability_intent_plan",
            "intent_count": len(intent_audit),
            "intents": intent_audit,
        },
    )


def _unwrap_result(value: object | Mapping[str, Any] | None) -> object | Mapping[str, Any]:
    if value is None:
        return {}
    if isinstance(value, Mapping) and "result" in value:
        result = value.get("result")
        return result if isinstance(result, Mapping) else {}
    return value


def _iter_intents(value: object | Mapping[str, Any]) -> tuple[object, ...]:
    intents = _get(value, "intents", ())
    if isinstance(intents, tuple):
        return intents
    if isinstance(intents, list):
        return tuple(intents)
    return ()


def _get(value: object | Mapping[str, Any], name: str, default: Any) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _stable_capability_demand_id(prefix: str, stable_source: str) -> str:
    digest = hashlib.sha256(stable_source.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in sorted(value.items())}
    if isinstance(value, tuple | list | set | frozenset):
        return [_jsonable(item) for item in value]
    return value


__all__ = [
    "WorkerBoundaryExclusionView",
    "build_worker_boundary_exclusion_view",
]
