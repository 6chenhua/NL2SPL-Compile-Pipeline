"""Materialize EXCEPTION_FLOW skeletons from ConstructPlan demands."""

from __future__ import annotations

import re

from nl2spl.compiler.construct_plan.model import ConstructPlan
from nl2spl.ir.block_structure_ir import BlockIR, BlockStructureIR
from nl2spl.ir.flow_structure_ir import ExceptionFlow, FlowStructureIR
from nl2spl.ir.span_ir import SpanIR
from nl2spl.ir.worker_plan_ir import WorkerPlanIR


def normalize_condition_text(text: str) -> str:
    """Normalize condition text for stable dedupe."""
    return re.sub(r"[^\w\s]", "", text.strip().lower())


def is_empty_condition_marker(text: str) -> bool:
    """Return True for explicit empty condition markers."""
    candidate = text.strip()
    candidate = re.sub(r"^\s*[-*+]\s+", "", candidate)
    candidate = re.sub(r"^\s*\d+\.\s+", "", candidate)
    if ":" in candidate or "\uff1a" in candidate:
        _label, candidate = re.split(r"[:\uff1a]", candidate, maxsplit=1)
    candidate = candidate.replace("**", "").replace("__", "")
    normalized = re.sub(r"[^\w\s]", "", candidate.lower()).strip()
    return normalized in {"none", "na", "not applicable", "nil", "empty"}


def materialize_exception_flows_from_construct_plan(
    flow: FlowStructureIR,
    construct_plan: ConstructPlan,
    spans: list[SpanIR],
) -> FlowStructureIR:
    """从 ConstructPlan 创建 condition 驱动的 ExceptionFlow 骨架。

    只创建骨架（condition span），handler span 由后续的
    materialize_handler_blocks_from_construct_plan 负责补充。
    """
    span_by_id = {span.span_id: span for span in spans}
    # 已存在的 condition 文本（归一化后），用于去重
    existing_conditions = {
        normalize_condition_text(exc.condition_text)
        for exc in flow.exception_flows
    }
    new_flows: list[ExceptionFlow] = []
    idx = len(flow.exception_flows)

    for demand in construct_plan.exception_flow_demands():
        # 只处理有 source-backed condition span 的 demand
        if not demand.condition_span_ids:
            continue
        condition_span_id = demand.condition_span_ids[0]
        condition_span = span_by_id.get(condition_span_id)
        if condition_span is None or condition_span.is_placeholder:
            continue
        condition_text = condition_span.text
        # 过滤 "None" / "N/A" 等空标记，防止 adapter 输出的无效文本被当成 condition
        if is_empty_condition_marker(condition_text):
            continue
        # 文本去重：如果已有同义 condition，不再重复创建
        normalized = normalize_condition_text(condition_text)
        if normalized in existing_conditions:
            continue
        existing_conditions.add(normalized)
        new_flows.append(
            ExceptionFlow(
                flow_id=f"exc_adapter_{idx:02d}",
                condition_text=condition_text,
                spans=[condition_span_id],
            )
        )
        idx += 1

    if not new_flows:
        return flow

    return FlowStructureIR(
        main_flow_spans=list(flow.main_flow_spans),
        alternative_flows=list(flow.alternative_flows),
        exception_flows=list(flow.exception_flows) + new_flows,
        delegation_candidates=list(flow.delegation_candidates),
    )


def materialize_worker_exception_flows_from_construct_plan(
    worker_flows: dict[str, FlowStructureIR],
    construct_plan: ConstructPlan,
    spans: list[SpanIR],
    worker_plan: WorkerPlanIR,
    warnings: list[str],
) -> None:
    """将 ExceptionFlow 骨架分配到各 worker 的 FlowStructureIR 中。

    核心规则：condition span 属于哪个 worker，ExceptionFlow 就物化到哪个 worker。
    orphan handler（无 condition）直接跳过，不凭空创建 ExceptionFlow。
    直接修改 worker_flows 和 warnings，无返回值。
    """
    span_by_id = {span.span_id: span for span in spans}
    # 构建反向索引：span_id → 拥有该 span 的 worker_id 列表
    owners_by_span: dict[str, list[str]] = {}
    for worker in worker_plan.workers:
        for span_id in worker.owned_span_ids:
            owners_by_span.setdefault(span_id, []).append(worker.worker_id)

    for demand in construct_plan.exception_flow_demands():
        if not demand.condition_span_ids:
            continue
        condition_span_id = demand.condition_span_ids[0]
        condition_span = span_by_id.get(condition_span_id)
        if condition_span is None or condition_span.is_placeholder:
            continue
        if is_empty_condition_marker(condition_span.text):
            continue

        # 按 condition span 的所有权决定目标 worker
        owners = owners_by_span.get(condition_span_id, [])
        if len(owners) == 1:
            target_worker_id = owners[0]
        else:
            # 无主或多主时降级到 main_worker，记录 warning，不抛异常
            target_worker_id = worker_plan.main_worker_id
            reason = "unowned" if not owners else "ambiguous ownership"
            warnings.append(
                f"ConstructPlan: condition span {condition_span_id} for "
                f"{demand.demand_id} has {reason}; attached to main worker "
                f"{target_worker_id}."
            )

        worker_flows.setdefault(target_worker_id, FlowStructureIR())
        # 将单个 demand 包装成单元素 ConstructPlan，复用单 flow 版的物化逻辑
        worker_flows[target_worker_id] = materialize_exception_flows_from_construct_plan(
            worker_flows[target_worker_id],
            ConstructPlan(
                plan_id=construct_plan.plan_id,
                demands=[demand],
            ),
            spans,
        )


def materialize_handler_blocks_from_construct_plan(
    blocks: BlockStructureIR,
    flow: FlowStructureIR,
    construct_plan: ConstructPlan,
) -> BlockStructureIR:
    """从 ConstructPlan 创建 handler block 骨架。

    不发明 handler 行为——只在 ConstructPlan 已有 handler slot 证据
    且能匹配到已存在的 ExceptionFlow 时，创建一个 block 包装器。
    """
    # 构建反向索引：condition span_id → ExceptionFlow.flow_id
    condition_to_flow_id: dict[str, str] = {}
    for exc in flow.exception_flows:
        for span_id in exc.spans:
            condition_to_flow_id.setdefault(span_id, exc.flow_id)

    exception_flow_blocks = {
        flow_id: list(flow_blocks)
        for flow_id, flow_blocks in blocks.exception_flow_blocks.items()
    }
    changed = False
    counter = sum(
        len(flow_blocks)
        for flow_blocks in exception_flow_blocks.values()
    )

    for demand in construct_plan.exception_flow_demands():
        # 必须同时有 condition 和 handler 才能物化 block
        if not demand.condition_span_ids or not demand.handler_span_ids:
            continue
        # 通过 condition span 反查对应的 flow_id
        flow_id = next(
            (
                condition_to_flow_id[condition_span_id]
                for condition_span_id in demand.condition_span_ids
                if condition_span_id in condition_to_flow_id
            ),
            None,
        )
        if flow_id is None:
            continue

        flow_blocks = exception_flow_blocks.setdefault(flow_id, [])
        existing_span_sets = {tuple(block.spans) for block in flow_blocks}
        for handler_span_id in demand.handler_span_ids:
            # 去重：同一个 handler span 不重复创建 block
            key = (handler_span_id,)
            if key in existing_span_sets:
                continue
            counter += 1
            flow_blocks.append(
                BlockIR(
                    block_id=f"b_exc_handler_{counter:02d}",
                    block_type="SEQUENTIAL",
                    spans=[handler_span_id],
                )
            )
            existing_span_sets.add(key)
            changed = True

    if not changed:
        return blocks
    return BlockStructureIR(
        main_flow_blocks=list(blocks.main_flow_blocks),
        alternative_flow_blocks={
            flow_id: list(flow_blocks)
            for flow_id, flow_blocks in blocks.alternative_flow_blocks.items()
        },
        exception_flow_blocks=exception_flow_blocks,
    )
