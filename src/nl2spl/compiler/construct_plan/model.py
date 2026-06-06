"""ConstructPlan data model.

The model is intentionally construct-generic even though the first
implementation practice is EXCEPTION_FLOW.  It records construct demand and
slot evidence; it does not create SPL IR.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from nl2spl.compiler.irs.graph import ConstructEdge
from nl2spl.ir.diagnostics import CompileDiagnostic
from nl2spl.ir.worker_plan_ir import WorkerPlanIR

SlotEvidenceRelation = Literal["direct", "derived", "ambiguous"]
SlotDemandStatus = Literal["present", "missing", "ambiguous", "orphan", "invalid"]


@dataclass
class ConstructSlotDemand:
    """Slot-specific source evidence for a demanded construct."""

    slot_name: str
    source_span_ids: list[str] = field(default_factory=list)
    semantic_roles: list[str] = field(default_factory=list)
    executable_values: list[bool | None] = field(default_factory=list)
    source_section_id: str | None = None
    source_packet_id: str | None = None
    evidence_relation: SlotEvidenceRelation = "direct"
    status: SlotDemandStatus = "present"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        """Return deterministic JSON-serializable payload."""
        return {
            "slot_name": self.slot_name,
            "source_span_ids": list(self.source_span_ids),
            "semantic_roles": list(self.semantic_roles),
            "executable_values": list(self.executable_values),
            "source_section_id": self.source_section_id,
            "source_packet_id": self.source_packet_id,
            "evidence_relation": self.evidence_relation,
            "status": self.status,
            "metadata": dict(sorted(self.metadata.items())),
        }


@dataclass
class ConstructDemand:
    """Generic construct demand instance."""

    demand_id: str
    construct_type: str
    slots: dict[str, ConstructSlotDemand] = field(default_factory=dict)
    pairing_status: str = "unknown"
    materialization_policy: str = "source_backed_only"
    owner_policy: str = "unspecified"
    owner_worker_id: str | None = None
    reserved_span_ids: set[str] = field(default_factory=set)
    dual_role_span_ids: set[str] = field(default_factory=set)
    source_span_ids: list[str] = field(default_factory=list)
    source_section_id: str | None = None
    source_packet_id: str | None = None
    construct_path: tuple[str, ...] = ()
    related_edges: list[ConstructEdge] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        """Return deterministic JSON-serializable payload."""
        return {
            "demand_id": self.demand_id,
            "construct_type": self.construct_type,
            "slots": {
                name: self.slots[name].to_payload()
                for name in sorted(self.slots)
            },
            "pairing_status": self.pairing_status,
            "materialization_policy": self.materialization_policy,
            "owner_policy": self.owner_policy,
            "owner_worker_id": self.owner_worker_id,
            "reserved_span_ids": sorted(self.reserved_span_ids),
            "dual_role_span_ids": sorted(self.dual_role_span_ids),
            "source_span_ids": list(self.source_span_ids),
            "source_section_id": self.source_section_id,
            "source_packet_id": self.source_packet_id,
            "construct_path": list(self.construct_path),
            "related_edges": [edge.to_snapshot() for edge in self.related_edges],
            "metadata": dict(sorted(self.metadata.items())),
        }


@dataclass
class ExceptionFlowDemand(ConstructDemand):
    """EXCEPTION_FLOW demand with condition and handler slot evidence."""

    construct_type: str = "EXCEPTION_FLOW"
    condition_span_ids: list[str] = field(default_factory=list)
    handler_span_ids: list[str] = field(default_factory=list)
    condition_text: str | None = None
    owner_policy: Literal[
        "condition_owner",
        "same_worker_required",
        "allow_cross_worker_with_diagnostic",
    ] = "condition_owner"

    def to_payload(self) -> dict[str, Any]:
        payload = super().to_payload()
        payload.update(
            {
                "condition_span_ids": list(self.condition_span_ids),
                "handler_span_ids": list(self.handler_span_ids),
                "condition_text": self.condition_text,
            }
        )
        return payload


@dataclass
class ConstructPlan:
    """Construct-level demand plan consumed by downstream stages and IRS."""

    plan_id: str
    source_schema: str | None = None
    demands: list[ConstructDemand] = field(default_factory=list)
    reserved_span_ids: set[str] = field(default_factory=set)
    dual_role_span_ids: set[str] = field(default_factory=set)
    diagnostics: list[CompileDiagnostic] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def exception_flow_demands(self) -> list[ExceptionFlowDemand]:
        """Return EXCEPTION_FLOW demands."""
        return [
            demand
            for demand in self.demands
            if isinstance(demand, ExceptionFlowDemand)
        ]

    def reserved_without_dual_role(self) -> set[str]:
        """Return handler-only spans that should be excluded from main candidates."""
        return set(self.reserved_span_ids) - set(self.dual_role_span_ids)

    def to_payload(self) -> dict[str, Any]:
        """Return deterministic JSON-serializable payload."""
        return {
            "plan_id": self.plan_id,
            "source_schema": self.source_schema,
            "demands": [demand.to_payload() for demand in self.demands],
            "reserved_span_ids": sorted(self.reserved_span_ids),
            "dual_role_span_ids": sorted(self.dual_role_span_ids),
            "diagnostics": [_diagnostic_payload(diag) for diag in self.diagnostics],
            "warnings": list(self.warnings),
            "metadata": dict(sorted(self.metadata.items())),
        }

    def enforce_exception_flow_ownership(
        self,
        worker_plan: WorkerPlanIR,
    ) -> list[str]:
        """Keep condition and handler spans in the condition owner's worker.

        This enforces the first-practice EXCEPTION_FLOW owner policy without
        creating new workers or SPL constructs.
        """
        warnings: list[str] = []
        if not worker_plan.workers:
            return warnings

        for demand in self.exception_flow_demands():
            if not demand.condition_span_ids or not demand.handler_span_ids:
                continue
            condition_owners = _owners_for_span_ids(
                worker_plan, demand.condition_span_ids
            )
            if len(condition_owners) != 1:
                warnings.append(
                    f"ConstructPlan: cannot enforce ownership for {demand.demand_id}; "
                    f"condition spans have owners {sorted(condition_owners)}."
                )
                continue
            owner_id = next(iter(condition_owners))
            demand.owner_worker_id = owner_id
            for span_id in demand.handler_span_ids:
                moved_from = _move_span_to_worker(worker_plan, span_id, owner_id)
                if moved_from:
                    warnings.append(
                        f"ConstructPlan: moved handler span {span_id} for "
                        f"{demand.demand_id} from {sorted(moved_from)} to {owner_id}."
                    )
        self.warnings.extend(warnings)
        worker_plan.warnings.extend(warnings)
        return warnings


def _owners_for_span_ids(worker_plan: WorkerPlanIR, span_ids: list[str]) -> set[str]:
    owners: set[str] = set()
    wanted = set(span_ids)
    for worker in worker_plan.workers:
        if wanted.intersection(worker.owned_span_ids):
            owners.add(worker.worker_id)
    return owners


def _move_span_to_worker(
    worker_plan: WorkerPlanIR,
    span_id: str,
    target_worker_id: str,
) -> set[str]:
    moved_from: set[str] = set()
    target_worker = None
    for worker in worker_plan.workers:
        if worker.worker_id == target_worker_id:
            target_worker = worker
        if worker.worker_id != target_worker_id and span_id in worker.owned_span_ids:
            worker.owned_span_ids = [
                existing for existing in worker.owned_span_ids
                if existing != span_id
            ]
            moved_from.add(worker.worker_id)

    if target_worker is not None and span_id not in target_worker.owned_span_ids:
        target_worker.owned_span_ids.append(span_id)
    return moved_from


def _diagnostic_payload(diagnostic: CompileDiagnostic) -> dict[str, Any]:
    missing_slot = diagnostic.missing_slot
    return {
        "diagnostic_id": diagnostic.diagnostic_id,
        "kind": diagnostic.kind,
        "severity": diagnostic.severity,
        "message": diagnostic.message,
        "target_ref": diagnostic.target_ref,
        "source_span_ids": list(diagnostic.source_span_ids),
        "suggested_resolution": diagnostic.suggested_resolution,
        "missing_slot": (
            None if missing_slot is None else {
                "slot_name": missing_slot.slot_name,
                "required_for": missing_slot.required_for,
                "reason": missing_slot.reason,
                "source_span_ids": list(missing_slot.source_span_ids),
                "suggested_question": missing_slot.suggested_question,
            }
        ),
        "blocks_rendering": diagnostic.blocks_rendering,
        "blocks_completion": diagnostic.blocks_completion,
    }
