"""Stage 5: BlockAssembler - ExecutorMixin (execute, _execute_worker_aware, _assemble_blocks)."""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from nl2spl.errors.exceptions import StageError
from nl2spl.ir.block_structure_ir import BlockIR, BlockStructureIR
from nl2spl.ir.field_route_ir import FieldRouteIR
from nl2spl.ir.flow_structure_ir import FlowStructureIR
from nl2spl.ir.span_ir import SpanIR
from nl2spl.ir.worker_plan_ir import (
    ControlComplexityRegionIR,
    WorkerBlockPlanIR,
    WorkerFlowPlanIR,
)
from nl2spl.llm.prompts import load_prompt
from nl2spl.pipeline.stages.stage5_block_assembler.block_postprocess import (
    merge_adjacent_sequential_blocks,
)


class ExecutorMixin:
    """Mixin containing execution logic for BlockAssembler."""

    def execute(
        self,
        input_data: tuple[list[SpanIR], FieldRouteIR, FlowStructureIR]
        | tuple[list[SpanIR], FieldRouteIR, WorkerFlowPlanIR],
    ) -> BlockStructureIR | WorkerBlockPlanIR:
        """Execute block assembly."""
        spans, routes, flow_input = input_data
        if isinstance(flow_input, WorkerFlowPlanIR):
            return self._execute_worker_aware(spans, routes, flow_input)

        self.logger.info(
            "Starting block assembly with %d spans and %d behavior spans",
            len(spans),
            len(routes.behavior),
        )
        block_structure, _, _ = self._assemble_blocks(
            flow_input,
            spans,
            worker_id=None,
            include_delegation_context=True,
            routes=routes,
        )

        total_blocks = len(block_structure.get_all_blocks())
        self.logger.info(
            "Created %d blocks (%d main, %d alternative flows, %d exception flows)",
            total_blocks,
            len(block_structure.main_flow_blocks),
            len(block_structure.alternative_flow_blocks),
            len(block_structure.exception_flow_blocks),
        )

        self.save_checkpoint(asdict(block_structure))
        return block_structure

    def _execute_worker_aware(
        self,
        spans: list[SpanIR],
        routes: FieldRouteIR,
        worker_flow_plan: WorkerFlowPlanIR,
    ) -> WorkerBlockPlanIR:
        """Assemble one BlockStructureIR per worker flow."""
        self.logger.info(
            "Starting worker-aware block assembly for %d workers",
            len(worker_flow_plan.worker_flows),
        )
        worker_blocks: dict[str, BlockStructureIR] = {}
        control_regions: list[ControlComplexityRegionIR] = []
        warnings = list(worker_flow_plan.warnings)

        for worker_id, flow in worker_flow_plan.worker_flows.items():
            block_structure, worker_regions, worker_warnings = self._assemble_blocks(
                flow,
                spans,
                worker_id=worker_id,
                include_delegation_context=False,
                allowed_span_ids=flow.get_all_flow_spans(),
                routes=routes,
            )
            worker_blocks[worker_id] = block_structure
            control_regions.extend(worker_regions)
            warnings.extend(worker_warnings)

        plan = WorkerBlockPlanIR(
            worker_blocks=worker_blocks,
            control_complexity_regions=control_regions,
            warnings=warnings,
        )
        self.save_checkpoint(asdict(plan))
        return plan

    def _assemble_blocks(
        self,
        flow_structure: FlowStructureIR,
        spans: list[SpanIR],
        worker_id: str | None,
        include_delegation_context: bool,
        allowed_span_ids: set[str] | None = None,
        routes: FieldRouteIR | None = None,
    ) -> tuple[BlockStructureIR, list[ControlComplexityRegionIR], list[str]]:
        """Call the LLM and parse a legal BlockStructureIR."""
        flow_json = json.dumps(
            self._flow_with_span_text(
                flow_structure,
                spans,
                include_delegation_context=include_delegation_context,
            ),
            ensure_ascii=False,
            indent=2,
        )

        system_prompt = load_prompt("stage5")
        user_prompt = f"""Assemble block structure from the flow structure.

Flow structure with span text:
---
{flow_json}
---

Use span_id values in output span lists; do not copy span text into span lists.
Return top-level blocks only; do not output nested blocks.
Return JSON only."""

        try:
            result = self.client.call_json(
                stage_name=self.name,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
        except Exception as e:
            self.logger.error("LLM call failed: %s", e)
            raise StageError(
                message=f"LLM call failed in {self.name}: {e}",
                stage=self.name,
            ) from e

        region_counter = 1
        control_regions = self._parse_control_regions(
            result.get("control_complexity_regions", []),
            worker_id,
        )
        if control_regions:
            region_counter += len(control_regions)

        main_flow_blocks, regions = self._parse_block_list(
            result.get("main_flow_blocks", []),
            flow_ref="main",
            worker_id=worker_id,
            region_counter=region_counter,
        )
        control_regions.extend(regions)
        region_counter += len(regions)

        alternative_flow_blocks: dict[str, list[BlockIR]] = {}
        for flow_id, blocks_data in result.get("alternative_flow_blocks", {}).items():
            flow_blocks, regions = self._parse_block_list(
                blocks_data,
                flow_ref=flow_id,
                worker_id=worker_id,
                region_counter=region_counter,
            )
            alternative_flow_blocks[flow_id] = flow_blocks
            control_regions.extend(regions)
            region_counter += len(regions)

        exception_flow_blocks: dict[str, list[BlockIR]] = {}
        for flow_id, blocks_data in result.get("exception_flow_blocks", {}).items():
            flow_blocks, regions = self._parse_block_list(
                blocks_data,
                flow_ref=flow_id,
                worker_id=worker_id,
                region_counter=region_counter,
            )
            exception_flow_blocks[flow_id] = flow_blocks
            control_regions.extend(regions)
            region_counter += len(regions)

        block_structure = BlockStructureIR(
            main_flow_blocks=main_flow_blocks,
            alternative_flow_blocks=alternative_flow_blocks,
            exception_flow_blocks=exception_flow_blocks,
        )

        # D4 guard: strip fabricated handler blocks from condition-only flows
        block_structure, d4_warnings = self._guard_condition_only_exception_blocks(
            block_structure, flow_structure, routes=routes,
        )
        self.stage5_d4_warnings = list(d4_warnings) if d4_warnings else []

        block_structure = merge_adjacent_sequential_blocks(block_structure)

        if allowed_span_ids is not None:
            return self._enforce_worker_span_boundary(
                block_structure,
                control_regions,
                allowed_span_ids,
                worker_id,
            )

        return (block_structure, control_regions, [])

    @staticmethod
    def _guard_condition_only_exception_blocks(
        blocks: BlockStructureIR,
        flow_structure: FlowStructureIR,
        routes: FieldRouteIR | None = None,
    ) -> tuple[BlockStructureIR, list[str]]:
        """D4: strip fabricated handler blocks from condition-only exception flows.

        Derives condition span ids from route annotations
        (``construct_target=EXCEPTION_FLOW, slot_target=condition``) when
        available, falling back to ``exc_adapter_*`` prefix as a weaker
        signal.  A block is stripped only when ALL its spans are condition
        evidence.  Blocks referencing non-condition spans (handler/recovery)
        are preserved.
        """
        warnings: list[str] = []

        # Identify condition spans via route annotations (preferred)
        condition_span_ids: set[str] = set()
        if routes is not None and routes.annotations:
            condition_span_ids = {
                a.span_id
                for a in routes.get_construct_slot_candidates(
                    "EXCEPTION_FLOW", "condition"
                )
                if a.semantic_role == "failure_mode" and a.executable is False
            }

        # Build per-flow condition span sets
        flow_condition_spans: dict[str, set[str]] = {}
        for exc in flow_structure.exception_flows:
            if not exc.flow_id.startswith("exc_adapter_"):
                continue
            if condition_span_ids:
                # Use route-annotated condition spans intersected with flow spans
                flow_condition_spans[exc.flow_id] = set(exc.spans) & condition_span_ids
            else:
                # Fallback: all flow spans are considered condition evidence
                # (only when no route annotations available)
                flow_condition_spans[exc.flow_id] = set(exc.spans)

        cleaned: dict[str, list[BlockIR]] = {}
        for flow_id, flow_blocks in blocks.exception_flow_blocks.items():
            cond_spans = flow_condition_spans.get(flow_id, set())
            if not cond_spans:
                cleaned[flow_id] = list(flow_blocks)
                continue
            kept: list[BlockIR] = []
            for block in flow_blocks:
                block_spans = set(block.spans)
                if block_spans and block_spans.issubset(cond_spans):
                    warnings.append(
                        f"D4 guard: stripped fabricated handler block "
                        f"'{block.block_id}' from condition-only flow "
                        f"'{flow_id}' (spans {sorted(block_spans)} are all "
                        f"condition evidence, not handler actions)"
                    )
                    continue
                kept.append(block)
            cleaned[flow_id] = kept

        # Preserve empty entries for adapter flows not in LLM output
        for exc in flow_structure.exception_flows:
            if exc.flow_id.startswith("exc_adapter_") and exc.flow_id not in cleaned:
                cleaned[exc.flow_id] = []

        return BlockStructureIR(
            main_flow_blocks=list(blocks.main_flow_blocks),
            alternative_flow_blocks=dict(blocks.alternative_flow_blocks),
            exception_flow_blocks=cleaned,
        ), warnings
