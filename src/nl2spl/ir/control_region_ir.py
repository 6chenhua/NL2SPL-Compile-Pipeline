"""Control-region planning IR consumed by Stage 5 block materialization."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ControlRegionKind = Literal[
    "local_if",
    "top_level_alternative",
    "exception_flow",
    "loop",
    "unresolved",
]
ControlRegionStatus = Literal["validated", "rejected", "ambiguous"]
ControlRegionSource = Literal[
    "stage1_guarded_action",
    "stage4_llm_classified",
    "construct_plan",
    "route_derived",
    "deterministic_evidence",
    "stage1_cross_packet_guard_repair",
]
ControlRegionRelation = Literal["direct", "derived", "ambiguous"]
ControlRegionConfidence = Literal["high", "medium", "low", "unknown"]


@dataclass(frozen=True)
class ControlRegion:
    """Validated control region with source-backed condition and action spans."""

    region_id: str
    region_kind: ControlRegionKind
    condition_text: str
    action_span_ids: tuple[str, ...]
    condition_source_span_ids: tuple[str, ...]
    worker_id: str
    source: ControlRegionSource
    status: ControlRegionStatus = "validated"
    reason: str | None = None
    relation: ControlRegionRelation = "direct"
    classification_source: ControlRegionSource | None = None
    confidence: ControlRegionConfidence = "unknown"
    notes: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, object]:
        return {
            "region_id": self.region_id,
            "region_kind": self.region_kind,
            "condition_text": self.condition_text,
            "action_span_ids": list(self.action_span_ids),
            "condition_source_span_ids": list(self.condition_source_span_ids),
            "worker_id": self.worker_id,
            "source": self.source,
            "status": self.status,
            "reason": self.reason,
            "relation": self.relation,
            "classification_source": self.classification_source or self.source,
            "confidence": self.confidence,
            "notes": list(self.notes),
        }

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> ControlRegion:
        return cls(
            region_id=str(payload.get("region_id", "")),
            region_kind=str(payload.get("region_kind", "unresolved")),  # type: ignore[arg-type]
            condition_text=str(payload.get("condition_text", "")),
            action_span_ids=tuple(str(v) for v in payload.get("action_span_ids", ())),
            condition_source_span_ids=tuple(
                str(v) for v in payload.get("condition_source_span_ids", ())
            ),
            worker_id=str(payload.get("worker_id", "")),
            source=str(payload.get("source", "deterministic_evidence")),  # type: ignore[arg-type]
            status=str(payload.get("status", "ambiguous")),  # type: ignore[arg-type]
            reason=str(payload["reason"]) if payload.get("reason") is not None else None,
            relation=str(payload.get("relation", "direct")),  # type: ignore[arg-type]
            classification_source=(
                str(payload["classification_source"])  # type: ignore[arg-type]
                if payload.get("classification_source") is not None
                else None
            ),
            confidence=str(payload.get("confidence", "unknown")),  # type: ignore[arg-type]
            notes=tuple(str(v) for v in payload.get("notes", ())),
        )


@dataclass(frozen=True)
class ControlRegionPlan:
    """Read-only Stage 4/5 control materialization plan."""

    regions: tuple[ControlRegion, ...] = ()
    diagnostics: tuple[str, ...] = ()

    def regions_for_worker(self, worker_id: str) -> tuple[ControlRegion, ...]:
        return tuple(
            region
            for region in self.regions
            if region.worker_id == worker_id and region.status == "validated"
        )

    def to_payload(self) -> dict[str, object]:
        return {
            "regions": [region.to_payload() for region in self.regions],
            "diagnostics": list(self.diagnostics),
        }

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> ControlRegionPlan:
        return cls(
            regions=tuple(
                ControlRegion.from_payload(item)
                for item in payload.get("regions", ())
                if isinstance(item, dict)
            ),
            diagnostics=tuple(str(v) for v in payload.get("diagnostics", ())),
        )
