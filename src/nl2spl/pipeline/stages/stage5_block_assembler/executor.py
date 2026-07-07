"""Stage 5: BlockAssembler - ExecutorMixin (execute, _execute_worker_aware, _assemble_blocks)."""

from __future__ import annotations

import json
from dataclasses import asdict

from nl2spl.compiler.construct_plan import ConstructPlan
from nl2spl.compiler.construct_plan.exception_materializer import (
    materialize_handler_blocks_from_construct_plan,
)
from nl2spl.errors.exceptions import StageError
from nl2spl.ir.block_structure_ir import BlockIR, BlockStructureIR
from nl2spl.ir.control_region_ir import ControlRegion, ControlRegionPlan
from nl2spl.ir.diagnostics import CompileDiagnostic
from nl2spl.ir.field_route_ir import FieldRouteIR
from nl2spl.ir.flow_structure_ir import FlowStructureIR
from nl2spl.ir.span_ir import SpanIR
from nl2spl.ir.worker_plan_ir import (
    ControlComplexityRegionIR,
    WorkerBlockPlanIR,
    WorkerFlowPlanIR,
)
from nl2spl.llm.prompts import load_prompt
from nl2spl.pipeline.control_region_plan import is_terminal_placement_guard
from nl2spl.pipeline.stages.stage5_block_assembler.block_postprocess import (
    merge_adjacent_sequential_blocks,
)


class ExecutorMixin:
    """Mixin containing execution logic for BlockAssembler."""

    def execute(
        self,
        input_data: tuple[list[SpanIR], FieldRouteIR, FlowStructureIR]
        | tuple[list[SpanIR], FieldRouteIR, WorkerFlowPlanIR]
        | tuple[list[SpanIR], FieldRouteIR, WorkerFlowPlanIR, ConstructPlan]
        | tuple[
            list[SpanIR],
            FieldRouteIR,
            WorkerFlowPlanIR,
            ConstructPlan | None,
            ControlRegionPlan,
        ],
    ) -> BlockStructureIR | WorkerBlockPlanIR:
        """Execute block assembly."""
        self.stage5_diagnostics = []
        self.stage5_warnings = []
        construct_plan = input_data[3] if len(input_data) == 4 else None
        control_region_plan = input_data[4] if len(input_data) == 5 else None
        if len(input_data) == 5:
            construct_plan = input_data[3]
        spans, routes, flow_input = input_data[:3]
        if isinstance(flow_input, WorkerFlowPlanIR):
            return self._execute_worker_aware(
                spans, routes, flow_input, construct_plan, control_region_plan,
            )

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
            construct_plan=construct_plan,
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
        construct_plan: ConstructPlan | None = None,
        control_region_plan: ControlRegionPlan | None = None,
    ) -> WorkerBlockPlanIR:
        """Assemble one BlockStructureIR per worker flow."""
        self.stage5_diagnostics = []
        self.stage5_warnings = []
        self.logger.info(
            "Starting worker-aware block assembly for %d workers",
            len(worker_flow_plan.worker_flows),
        )
        worker_blocks: dict[str, BlockStructureIR] = {}
        control_regions: list[ControlComplexityRegionIR] = []
        warnings = list(worker_flow_plan.warnings)

        for worker_id, flow in worker_flow_plan.worker_flows.items():
            allowed_span_ids = set(flow.get_all_flow_spans())
            if control_region_plan is not None:
                for region in control_region_plan.regions_for_worker(worker_id):
                    allowed_span_ids.update(region.action_span_ids)
            block_structure, worker_regions, worker_warnings = self._assemble_blocks(
                flow,
                spans,
                worker_id=worker_id,
                include_delegation_context=False,
                allowed_span_ids=allowed_span_ids,
                routes=routes,
                construct_plan=construct_plan,
                control_region_plan=control_region_plan,
            )
            worker_blocks[worker_id] = block_structure
            control_regions.extend(worker_regions)
            warnings.extend(worker_warnings)

        plan = WorkerBlockPlanIR(
            worker_blocks=worker_blocks,
            control_complexity_regions=control_regions,
            warnings=warnings + getattr(self, "stage5_warnings", []),
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
        construct_plan: ConstructPlan | None = None,
        control_region_plan: ControlRegionPlan | None = None,
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

        # Stage 1 active mode guarded_action consumption (Phase E)
        block_structure = self._process_guarded_and_ambiguous_blocks(block_structure, spans)
        if control_region_plan is not None and worker_id is not None:
            block_structure = _apply_control_region_plan(
                self,
                block_structure,
                control_region_plan,
                worker_id,
            )

        if construct_plan is not None:
            block_structure = materialize_handler_blocks_from_construct_plan(
                block_structure,
                flow_structure,
                construct_plan,
            )

        # D4 guard: strip fabricated handler blocks from condition-only flows
        block_structure, d4_warnings = self._guard_condition_only_exception_blocks(
            block_structure, flow_structure, routes=routes,
            construct_plan=construct_plan,
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
        construct_plan: ConstructPlan | None = None,
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
        if construct_plan is not None:
            condition_span_ids = {
                span_id
                for demand in construct_plan.exception_flow_demands()
                for span_id in demand.condition_span_ids
            }
        elif routes is not None and routes.annotations:
            condition_span_ids = {
                a.span_id
                for a in routes.get_construct_slot_candidates(
                    "EXCEPTION_FLOW", "condition"
                )
                if (
                    a.semantic_role in ("failure_mode", "failure_condition")
                    and a.executable is False
                )
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

    def _process_guarded_and_ambiguous_blocks(
        self,
        block_structure: BlockStructureIR,
        spans: list[SpanIR],
    ) -> BlockStructureIR:
        records = getattr(self, "stage1_segmentation_records", [])

        # Build unified mapping for spans
        span_info = {}
        for s in spans:
            span_info[s.span_id] = {
                "segmentation_kind": getattr(s, "segmentation_kind", None),
                "guard_text_exact": getattr(s, "guard_text_exact", None),
                "action_text_exact": getattr(s, "action_text_exact", None),
            }
        for r in records:
            if hasattr(r, "span_id"):
                span_id = r.span_id
                kind = r.segmentation_kind
                guard = r.guard_text_exact
                action = r.action_text_exact
            elif isinstance(r, dict):
                span_id = r.get("span_id")
                kind = r.get("segmentation_kind")
                guard = r.get("guard_text_exact")
                action = r.get("action_text_exact")
            else:
                continue
            if span_id:
                existing = span_info.get(span_id, {})
                # Resolved SpanIR metadata is the current stage-local authority.
                # Sidecar records are retained for serialization/replay fallback,
                # but may refer to pre-resolution span ids after Stage 3 routing.
                span_info[span_id] = {
                    "segmentation_kind": existing.get("segmentation_kind") or kind,
                    "guard_text_exact": existing.get("guard_text_exact") or guard,
                    "action_text_exact": existing.get("action_text_exact") or action,
                }

        stage5_diagnostics = []
        warnings = []

        def process_blocks(blocks_list: list[BlockIR]) -> list[BlockIR]:
            new_blocks = []
            block_counter = 1
            for block in blocks_list:
                if block.block_type == "SEQUENTIAL":
                    # Check whether this block requires guarded-action splitting.
                    needs_split = any(
                        span_info.get(sid, {}).get("segmentation_kind")
                        in ("guarded_action", "ambiguous_boundary")
                        for sid in block.spans
                    )
                    if not needs_split:
                        # No splitting needed – preserve the original block unchanged
                        new_blocks.append(block)
                        continue

                    current_seq_spans = []
                    for span_id in block.spans:
                        info = span_info.get(span_id, {})
                        kind = info.get("segmentation_kind")
                        guard = info.get("guard_text_exact")

                        if (
                            kind == "guarded_action"
                            and guard
                            and not is_terminal_placement_guard(guard)
                        ):
                            if current_seq_spans:
                                new_blocks.append(BlockIR(
                                    block_id=f"{block.block_id}_seq_{block_counter}",
                                    block_type="SEQUENTIAL",
                                    spans=current_seq_spans,
                                ))
                                block_counter += 1
                                current_seq_spans = []
                            new_blocks.append(BlockIR(
                                block_id=f"b_local_if_{block.block_id}_{block_counter}",
                                block_type="IF",
                                condition_text=guard,
                                spans=[span_id],
                            ))
                            block_counter += 1
                        elif kind == "ambiguous_boundary":
                            # Do not silently place ambiguous boundaries in sequence.
                            msg = (
                                "Ambiguous guard/action boundary detected for span "
                                f"{span_id}."
                            )
                            warnings.append(
                                f"stage1_guard_action_boundary_ambiguous: {msg}"
                            )

                            diag = CompileDiagnostic(
                                diagnostic_id=f"diag_s5_ambiguity_{span_id}",
                                kind="stage1_guard_action_boundary_ambiguous",
                                severity="warning",
                                message=msg,
                                target_ref=f"span:{span_id}",
                                source_span_ids=[span_id],
                                blocks_rendering=False,
                                blocks_completion=True,
                            )
                            stage5_diagnostics.append(diag)
                        else:
                            current_seq_spans.append(span_id)
                    if current_seq_spans:
                        new_blocks.append(BlockIR(
                            block_id=f"{block.block_id}_seq_{block_counter}",
                            block_type="SEQUENTIAL",
                            spans=current_seq_spans,
                        ))
                        block_counter += 1
                elif block.block_type == "IF":
                    for span_id in block.spans:
                        info = span_info.get(span_id, {})
                        kind = info.get("segmentation_kind")
                        guard = info.get("guard_text_exact")
                        if (
                            kind == "guarded_action"
                            and guard
                            and not is_terminal_placement_guard(guard)
                        ):
                            block.condition_text = guard
                            break
                    if not block.condition_text:
                        msg = f"Unable to establish condition text for IF block {block.block_id}."
                        warnings.append(f"stage5_unable_to_build_if: {msg}")
                        diag = CompileDiagnostic(
                            diagnostic_id=f"diag_s5_missing_if_cond_{block.block_id}",
                            kind="stage5_unable_to_build_if",
                            severity="error",
                            message=msg,
                            target_ref=f"block:{block.block_id}",
                            source_span_ids=block.spans,
                            blocks_rendering=True,
                            blocks_completion=True,
                        )
                        stage5_diagnostics.append(diag)
                    new_blocks.append(block)
                else:
                    new_blocks.append(block)
            return new_blocks

        block_structure.main_flow_blocks = process_blocks(block_structure.main_flow_blocks)
        for flow_id, blocks_data in list(block_structure.alternative_flow_blocks.items()):
            block_structure.alternative_flow_blocks[flow_id] = process_blocks(blocks_data)
        for flow_id, blocks_data in list(block_structure.exception_flow_blocks.items()):
            block_structure.exception_flow_blocks[flow_id] = process_blocks(blocks_data)

        self.stage5_diagnostics.extend(stage5_diagnostics)
        self.stage5_warnings.extend(warnings)
        return block_structure


def _remove_spans_from_blocks(
    blocks: list[BlockIR],
    span_ids: set[str],
) -> list[BlockIR]:
    cleaned: list[BlockIR] = []
    for block in blocks:
        chunk: list[str] = []
        chunk_index = 1
        for span_id in block.spans:
            if span_id in span_ids:
                if chunk:
                    cleaned.append(_copy_block_chunk(block, chunk, chunk_index))
                    chunk_index += 1
                    chunk = []
                continue
            chunk.append(span_id)
        if chunk:
            cleaned.append(_copy_block_chunk(block, chunk, chunk_index))
    return cleaned


def _copy_block_chunk(block: BlockIR, spans: list[str], chunk_index: int) -> BlockIR:
    block_id = block.block_id if chunk_index == 1 else f"{block.block_id}_part_{chunk_index}"
    return BlockIR(
        block_id=block_id,
        block_type=block.block_type,
        condition_text=block.condition_text,
        spans=list(spans),
    )


def _block_for_region(region: ControlRegion) -> BlockIR:
    block_id = f"b_{region.region_id}"
    return BlockIR(
        block_id=block_id,
        block_type="IF",
        condition_text=region.condition_text,
        spans=list(region.action_span_ids),
    )


def _block_sort_key(block: BlockIR) -> tuple[int, str]:
    if not block.spans:
        return (10**9, block.block_id)
    return min(_span_sort_key(span_id) for span_id in block.spans), block.block_id


def _span_sort_key(span_id: str) -> int:
    digits = "".join(ch for ch in span_id if ch.isdigit())
    return int(digits) if digits else 10**9

def _apply_control_region_plan(
    self,
    block_structure: BlockStructureIR,
    control_region_plan: ControlRegionPlan,
    worker_id: str,
) -> BlockStructureIR:
    """Apply validated control regions.

    A validated ControlRegionPlan is authoritative for block
    materialization when it conflicts with legacy Stage 4 main/alternative
    output. Legacy flow output remains provenance/debug input only.
    """
    regions = control_region_plan.regions_for_worker(worker_id)
    if not regions:
        return block_structure

    planned_span_ids = {
        span_id
        for region in regions
        for span_id in region.action_span_ids
    }
    main_blocks = _remove_spans_from_blocks(
        block_structure.main_flow_blocks,
        planned_span_ids,
    )
    alternative_blocks = {
        flow_id: _remove_spans_from_blocks(blocks, planned_span_ids)
        for flow_id, blocks in block_structure.alternative_flow_blocks.items()
    }
    exception_blocks = {
        flow_id: _remove_spans_from_blocks(blocks, planned_span_ids)
        for flow_id, blocks in block_structure.exception_flow_blocks.items()
    }

    for region in regions:
        if region.region_kind == "local_if":
            main_blocks.append(_block_for_region(region))
        elif region.region_kind == "top_level_alternative":
            alternative_blocks[region.region_id] = [_block_for_region(region)]
        else:
            self.stage5_warnings.append(
                f"control_region_unresolved:{region.region_id}"
            )

    main_blocks = sorted(main_blocks, key=_block_sort_key)
    return BlockStructureIR(
        main_flow_blocks=main_blocks,
        alternative_flow_blocks={
            flow_id: blocks
            for flow_id, blocks in alternative_blocks.items()
            if blocks
        },
        exception_flow_blocks={
            flow_id: blocks
            for flow_id, blocks in exception_blocks.items()
            if blocks
        },
    )
