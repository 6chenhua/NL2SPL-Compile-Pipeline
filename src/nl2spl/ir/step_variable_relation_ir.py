"""Step-to-variable relation IR for ProducerIndex v2."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

StepVariableRelationKind = Literal[
    "produces",
    "consumes",
    "records_metadata",
    "refines",
    "validates",
    "declares",
    "no_relation",
    "unknown",
    "ambiguous",
]
StepVariableEvidenceSource = Literal[
    "source_text",
    "api_contract",
    "user_confirmed_repair",
    "inferred_unconfirmed",
    "stage7_structured_output_source_match",
    "stage7_structured_output_without_source_match",
    "stage7_provenance_maintenance_no_output",
    "worker_handoff",
    "command_type_contract",
]
RequiredOutputFulfillmentStatus = Literal["produced", "deferred", "missing"]


@dataclass(frozen=True)
class StepVariableRelation:
    """A typed relation between a StepIR and a symbolic variable."""

    step_id: str
    variable_name: str
    relation: StepVariableRelationKind
    source_span_ids: tuple[str, ...]
    evidence_kind: str
    reason: str | None = None
    evidence_source: StepVariableEvidenceSource | None = None
    evidence_text: str | None = None
    confidence: Literal["high", "medium", "low", "unknown"] = "unknown"

    def to_payload(self) -> dict[str, object]:
        return {
            "step_id": self.step_id,
            "variable_name": self.variable_name,
            "relation": self.relation,
            "source_span_ids": list(self.source_span_ids),
            "evidence_kind": self.evidence_kind,
            "reason": self.reason,
            "evidence_source": self.evidence_source or self.evidence_kind,
            "evidence_text": self.evidence_text,
            "confidence": self.confidence,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> StepVariableRelation:
        return cls(
            step_id=str(payload.get("step_id", "")),
            variable_name=str(payload.get("variable_name", "")),
            relation=str(payload.get("relation", "unknown")),  # type: ignore[arg-type]
            source_span_ids=tuple(str(v) for v in payload.get("source_span_ids", ())),
            evidence_kind=str(
                payload.get(
                    "evidence_kind",
                    payload.get("evidence_source", "inferred_unconfirmed"),
                )
            ),
            reason=str(payload["reason"]) if payload.get("reason") is not None else None,
            evidence_source=(
                str(payload["evidence_source"])  # type: ignore[arg-type]
                if payload.get("evidence_source") is not None
                else None
            ),
            evidence_text=(
                str(payload["evidence_text"]) if payload.get("evidence_text") is not None else None
            ),
            confidence=str(payload.get("confidence", "unknown")),  # type: ignore[arg-type]
        )


@dataclass(frozen=True)
class StepVariableRelationPlan:
    """Read-only plan consumed by ProducerIndex v2."""

    relations: tuple[StepVariableRelation, ...] = ()
    diagnostics: tuple[str, ...] = ()

    def producing_relations(self) -> tuple[StepVariableRelation, ...]:
        return tuple(relation for relation in self.relations if relation.relation == "produces")

    def to_payload(self) -> dict[str, object]:
        return {
            "relations": [relation.to_payload() for relation in self.relations],
            "diagnostics": list(self.diagnostics),
        }

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> StepVariableRelationPlan:
        return cls(
            relations=tuple(
                StepVariableRelation.from_payload(item)
                for item in payload.get("relations", ())
                if isinstance(item, dict)
            ),
            diagnostics=tuple(str(v) for v in payload.get("diagnostics", ())),
        )


@dataclass(frozen=True)
class RequiredOutputFulfillmentState:
    """ProducerIndex-owned required output fulfillment truth."""

    output_name: str
    status: RequiredOutputFulfillmentStatus
    producer_step_ids: tuple[str, ...] = ()
    deferred_refs: tuple[str, ...] = ()
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.status == "produced" and not self.producer_step_ids:
            raise ValueError("produced required output must list producer_step_ids")
        if self.status == "deferred" and not self.deferred_refs:
            raise ValueError("deferred required output must list deferred_refs")
        if self.status == "missing" and (
            self.producer_step_ids or self.deferred_refs
        ):
            raise ValueError(
                "missing required output must not list producer_step_ids or deferred_refs"
            )

    def to_payload(self) -> dict[str, object]:
        return {
            "output_name": self.output_name,
            "status": self.status,
            "producer_step_ids": list(self.producer_step_ids),
            "deferred_refs": list(self.deferred_refs),
            "reason": self.reason,
        }

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, object],
    ) -> RequiredOutputFulfillmentState:
        return cls(
            output_name=str(payload.get("output_name", "")),
            status=str(payload.get("status", "missing")),  # type: ignore[arg-type]
            producer_step_ids=tuple(str(v) for v in payload.get("producer_step_ids", ())),
            deferred_refs=tuple(str(v) for v in payload.get("deferred_refs", ())),
            reason=str(payload["reason"]) if payload.get("reason") is not None else None,
        )
