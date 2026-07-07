"""Executable action ownership and placement planning IR."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

ExecutableActionSource = Literal[
    "stage1_action_segmentation",
    "stage1_segmentation",
    "construct_plan_executable_demand",
    "construct_plan_demand",
    "route_executable_role",
    "route_annotation",
    "adapter_hard_fact",
]

ExecutableActionStatus = Literal[
    "accepted",
    "rejected_non_executable",
    "ambiguous",
]

PlacementStatus = Literal["placed", "unplaced", "ambiguous"]
MaterializationExclusionTarget = Literal[
    "general_command_extraction",
    "child_worker_candidate_extraction",
    "request_input_extraction",
]
MaterializationAuthority = Literal[
    "api_call",
    "worker_delegation",
    "request_input",
    "construct_repair",
]


@dataclass(frozen=True)
class ExecutableActionCandidate:
    """Source-backed candidate that may be materialized as an executable action."""

    candidate_id: str
    source_span_ids: tuple[str, ...]
    action_text: str
    source: ExecutableActionSource
    status: ExecutableActionStatus
    reason: str
    command_type_hint: str | None = None
    guard_text: str | None = None

    def to_payload(self) -> dict[str, object]:
        return {
            "candidate_id": self.candidate_id,
            "source_span_ids": list(self.source_span_ids),
            "action_text": self.action_text,
            "source": self.source,
            "status": self.status,
            "reason": self.reason,
            "command_type_hint": self.command_type_hint,
            "guard_text": self.guard_text,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> ExecutableActionCandidate:
        return cls(
            candidate_id=str(payload.get("candidate_id", "")),
            source_span_ids=tuple(str(v) for v in payload.get("source_span_ids", ())),
            action_text=str(payload.get("action_text", "")),
            source=str(payload.get("source", "stage1_action_segmentation")),  # type: ignore[arg-type]
            status=str(payload.get("status", "ambiguous")),  # type: ignore[arg-type]
            reason=str(payload.get("reason", "")),
            command_type_hint=(
                str(payload["command_type_hint"])
                if payload.get("command_type_hint") is not None
                else None
            ),
            guard_text=(
                str(payload["guard_text"]) if payload.get("guard_text") is not None else None
            ),
        )


@dataclass(frozen=True)
class ExecutableActionPlacement:
    """Worker/flow/block placement for an accepted executable action candidate."""

    candidate_id: str
    worker_id: str | None
    flow_ref: str | None
    block_ref: str | None
    status: PlacementStatus
    reason: str | None = None

    def to_payload(self) -> dict[str, object]:
        return {
            "candidate_id": self.candidate_id,
            "worker_id": self.worker_id,
            "flow_ref": self.flow_ref,
            "block_ref": self.block_ref,
            "status": self.status,
            "reason": self.reason,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> ExecutableActionPlacement:
        return cls(
            candidate_id=str(payload.get("candidate_id", "")),
            worker_id=(str(payload["worker_id"]) if payload.get("worker_id") is not None else None),
            flow_ref=str(payload["flow_ref"]) if payload.get("flow_ref") is not None else None,
            block_ref=(str(payload["block_ref"]) if payload.get("block_ref") is not None else None),
            status=str(payload.get("status", "ambiguous")),  # type: ignore[arg-type]
            reason=str(payload["reason"]) if payload.get("reason") is not None else None,
        )


@dataclass(frozen=True)
class MaterializationExclusion:
    """A materialization exclusion that preserves placement ownership."""

    span_id: str
    excluded_from: MaterializationExclusionTarget
    owning_authority: MaterializationAuthority
    authority_ref: str
    reason: str

    def to_payload(self) -> dict[str, object]:
        return {
            "span_id": self.span_id,
            "excluded_from": self.excluded_from,
            "owning_authority": self.owning_authority,
            "authority_ref": self.authority_ref,
            "reason": self.reason,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> MaterializationExclusion:
        return cls(
            span_id=str(payload.get("span_id", "")),
            excluded_from=str(payload.get("excluded_from", "general_command_extraction")),  # type: ignore[arg-type]
            owning_authority=str(payload.get("owning_authority", "api_call")),  # type: ignore[arg-type]
            authority_ref=str(payload.get("authority_ref", "")),
            reason=str(payload.get("reason", "")),
        )


@dataclass(frozen=True)
class WorkerExecutableActionSet:
    """Worker-owned executable action spans split by placement vs extraction."""

    worker_id: str
    placement_span_ids: tuple[str, ...] = ()
    generic_step_extraction_span_ids: tuple[str, ...] = ()
    materialization_exclusions: tuple[MaterializationExclusion, ...] = ()

    def to_payload(self) -> dict[str, object]:
        return {
            "worker_id": self.worker_id,
            "placement_span_ids": list(self.placement_span_ids),
            "generic_step_extraction_span_ids": list(self.generic_step_extraction_span_ids),
            "materialization_exclusions": [
                item.to_payload() for item in self.materialization_exclusions
            ],
        }

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> WorkerExecutableActionSet:
        return cls(
            worker_id=str(payload.get("worker_id", "")),
            placement_span_ids=tuple(str(v) for v in payload.get("placement_span_ids", ())),
            generic_step_extraction_span_ids=tuple(
                str(v) for v in payload.get("generic_step_extraction_span_ids", ())
            ),
            materialization_exclusions=tuple(
                MaterializationExclusion.from_payload(item)
                for item in payload.get("materialization_exclusions", ())
                if isinstance(item, dict)
            ),
        )


@dataclass(frozen=True)
class ExecutableActionPlacementPlan:
    """Read-only cross-stage action candidate and placement plan."""

    candidates: tuple[ExecutableActionCandidate, ...] = ()
    placements: tuple[ExecutableActionPlacement, ...] = ()
    worker_actions: tuple[WorkerExecutableActionSet, ...] = ()
    diagnostics: tuple[str, ...] = ()
    audit: dict[str, object] = field(default_factory=dict)

    def accepted_span_ids(self) -> set[str]:
        return {
            span_id
            for candidate in self.candidates
            if candidate.status == "accepted"
            for span_id in candidate.source_span_ids
        } | {
            span_id
            for worker_set in self.worker_actions
            for span_id in worker_set.placement_span_ids
        }

    def generic_step_extraction_span_ids(self, worker_id: str) -> tuple[str, ...]:
        for worker_set in self.worker_actions:
            if worker_set.worker_id == worker_id:
                return worker_set.generic_step_extraction_span_ids
        return ()

    def to_payload(self) -> dict[str, object]:
        return {
            "candidates": [candidate.to_payload() for candidate in self.candidates],
            "placements": [placement.to_payload() for placement in self.placements],
            "worker_actions": [item.to_payload() for item in self.worker_actions],
            "diagnostics": list(self.diagnostics),
            "audit": dict(self.audit),
        }

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> ExecutableActionPlacementPlan:
        return cls(
            candidates=tuple(
                ExecutableActionCandidate.from_payload(item)
                for item in payload.get("candidates", ())
                if isinstance(item, dict)
            ),
            placements=tuple(
                ExecutableActionPlacement.from_payload(item)
                for item in payload.get("placements", ())
                if isinstance(item, dict)
            ),
            worker_actions=tuple(
                WorkerExecutableActionSet.from_payload(item)
                for item in payload.get("worker_actions", ())
                if isinstance(item, dict)
            ),
            diagnostics=tuple(str(v) for v in payload.get("diagnostics", ())),
            audit=dict(payload.get("audit", {})),
        )
