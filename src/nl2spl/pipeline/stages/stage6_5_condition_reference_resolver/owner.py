"""Condition owner collection for Stage 6.5."""

from __future__ import annotations

from dataclasses import dataclass

from nl2spl.ir.condition_variable_reference_ir import ConditionOwnerKind
from nl2spl.ir.worker_plan_ir import WorkerBlockPlanIR, WorkerFlowPlanIR


@dataclass(frozen=True)
class ConditionOwner:
    owner_kind: ConditionOwnerKind
    owner_ref: str
    worker_id: str | None
    flow_ref: str | None
    block_ref: str | None
    condition_text: str
    source_span_ids: tuple[str, ...]


def collect_condition_owners(
    worker_flow_plan: WorkerFlowPlanIR,
    worker_block_plan: WorkerBlockPlanIR,
) -> tuple[ConditionOwner, ...]:
    """Collect flow-level and block-level condition owners."""
    owners: list[ConditionOwner] = []

    for worker_id, flow in worker_flow_plan.worker_flows.items():
        for alt in flow.alternative_flows:
            owners.append(
                ConditionOwner(
                    owner_kind="alternative_flow_condition",
                    owner_ref=_flow_owner_ref(worker_id, "alternative", alt.flow_id),
                    worker_id=worker_id,
                    flow_ref=alt.flow_id,
                    block_ref=None,
                    condition_text=alt.condition_text,
                    source_span_ids=tuple(alt.spans),
                )
            )
        for exc in flow.exception_flows:
            owners.append(
                ConditionOwner(
                    owner_kind="exception_flow_condition",
                    owner_ref=_flow_owner_ref(worker_id, "exception", exc.flow_id),
                    worker_id=worker_id,
                    flow_ref=exc.flow_id,
                    block_ref=None,
                    condition_text=exc.condition_text,
                    source_span_ids=tuple(exc.spans),
                )
            )

    for worker_id, blocks in worker_block_plan.worker_blocks.items():
        for block in blocks.main_flow_blocks:
            if block.condition_text:
                owners.append(
                    ConditionOwner(
                        owner_kind="block_condition",
                        owner_ref=_block_owner_ref(worker_id, "main", block.block_id),
                        worker_id=worker_id,
                        flow_ref="main",
                        block_ref=block.block_id,
                        condition_text=block.condition_text,
                        source_span_ids=tuple(block.spans),
                    )
                )
        for flow_id, flow_blocks in blocks.alternative_flow_blocks.items():
            for block in flow_blocks:
                if block.condition_text:
                    owners.append(
                        ConditionOwner(
                            owner_kind="block_condition",
                            owner_ref=_block_owner_ref(worker_id, flow_id, block.block_id),
                            worker_id=worker_id,
                            flow_ref=flow_id,
                            block_ref=block.block_id,
                            condition_text=block.condition_text,
                            source_span_ids=tuple(block.spans),
                        )
                    )
        for flow_id, flow_blocks in blocks.exception_flow_blocks.items():
            for block in flow_blocks:
                if block.condition_text:
                    owners.append(
                        ConditionOwner(
                            owner_kind="block_condition",
                            owner_ref=_block_owner_ref(worker_id, flow_id, block.block_id),
                            worker_id=worker_id,
                            flow_ref=flow_id,
                            block_ref=block.block_id,
                            condition_text=block.condition_text,
                            source_span_ids=tuple(block.spans),
                        )
                    )

    return tuple(_dedupe_owners(owners))


def _flow_owner_ref(worker_id: str, flow_kind: str, flow_id: str) -> str:
    return f"condition:flow:{worker_id}:{flow_kind}:{flow_id}"


def _block_owner_ref(worker_id: str, flow_ref: str, block_id: str) -> str:
    return f"condition:block:{worker_id}:{flow_ref}:{block_id}"


def _dedupe_owners(owners: list[ConditionOwner]) -> list[ConditionOwner]:
    """Remove mirrored owners, preferring block-level owners over flow mirrors."""
    result_by_key: dict[tuple[str | None, str, tuple[str, ...]], ConditionOwner] = {}
    order: list[tuple[str | None, str, tuple[str, ...]]] = []
    for owner in owners:
        key = (
            owner.worker_id,
            " ".join(owner.condition_text.split()),
            owner.source_span_ids,
        )
        existing = result_by_key.get(key)
        if existing is None:
            result_by_key[key] = owner
            order.append(key)
            continue
        if existing.owner_kind != "block_condition" and owner.owner_kind == "block_condition":
            result_by_key[key] = owner
    return [result_by_key[key] for key in order]


def build_block_condition_owner_ref(
    worker_id: str,
    flow_ref: str,
    block_id: str,
) -> str:
    return _block_owner_ref(worker_id, flow_ref, block_id)


def build_flow_condition_owner_ref(
    worker_id: str,
    flow_kind: str,
    flow_id: str,
) -> str:
    return _flow_owner_ref(worker_id, flow_kind, flow_id)
