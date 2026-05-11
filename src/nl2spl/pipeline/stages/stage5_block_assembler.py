"""Stage 5: BlockAssembler - Organize spans into top-level blocks."""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any, Literal

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
from nl2spl.pipeline.stages.base import PipelineStage


class BlockAssembler(
    PipelineStage[
        tuple[list[SpanIR], FieldRouteIR, FlowStructureIR]
        | tuple[list[SpanIR], FieldRouteIR, WorkerFlowPlanIR],
        BlockStructureIR | WorkerBlockPlanIR,
    ]
):
    """Organize behavior spans into legal top-level blocks.

    Legacy calls return one global BlockStructureIR. Worker-aware calls consume
    WorkerFlowPlanIR and return WorkerBlockPlanIR.
    """

    @property
    def name(self) -> str:
        """Stage name for logging and checkpointing."""
        return "stage5_block_assembler"

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

        if allowed_span_ids is not None:
            return self._enforce_worker_span_boundary(
                block_structure,
                control_regions,
                allowed_span_ids,
                worker_id,
            )

        return (block_structure, control_regions, [])

    def _parse_block_list(
        self,
        blocks_data: list[dict[str, Any]],
        flow_ref: str,
        worker_id: str | None,
        region_counter: int,
    ) -> tuple[list[BlockIR], list[ControlComplexityRegionIR]]:
        """Parse blocks and repair nested model output into top-level blocks."""
        blocks: list[BlockIR] = []
        regions: list[ControlComplexityRegionIR] = []

        for item in blocks_data:
            try:
                parsed_blocks, parsed_regions = self._parse_block_item(
                    item,
                    flow_ref=flow_ref,
                    worker_id=worker_id,
                    region_id=f"ccr_{region_counter + len(regions)}",
                )
            except (KeyError, TypeError, ValueError) as e:
                self.logger.warning("Skipping invalid block in %s: %s", flow_ref, e)
                continue

            blocks.extend(parsed_blocks)
            regions.extend(parsed_regions)

        return blocks, regions

    def _parse_block_item(
        self,
        item: dict[str, Any],
        flow_ref: str,
        worker_id: str | None,
        region_id: str,
    ) -> tuple[list[BlockIR], list[ControlComplexityRegionIR]]:
        """Parse one block, flattening or reporting nested control intent."""
        nested_items = self._nested_block_items(item)
        block = self._block_from_item(item)

        if not nested_items:
            return [block], []

        nested_blocks: list[BlockIR] = []
        for nested_item in nested_items:
            nested_blocks.append(self._block_from_item(nested_item))

        region = self._region_from_nested_blocks(
            region_id=region_id,
            outer_block=block,
            nested_blocks=nested_blocks,
            flow_ref=flow_ref,
            worker_id=worker_id,
        )

        if block.block_type == "SEQUENTIAL":
            # Repair order step 1: split surrounding sequential blocks.
            flattened = []
            if block.spans:
                flattened.append(block)
            flattened.extend(nested_blocks)
            return flattened, [region]

        # If merging the condition is lossless, keep the nested action as a
        # top-level block with the merged condition instead of nesting blocks.
        if region.can_merge_condition and nested_blocks:
            merged = [
                self._merge_conditions(block, nested)
                for nested in nested_blocks
            ]
            return merged, [region]

        # Guard lifting and command compression are later normalization steps.
        # Preserve a single top-level control block covering the affected spans.
        return [self._outer_block_covering_nested(block, nested_blocks)], [region]

    def _block_from_item(self, item: dict[str, Any]) -> BlockIR:
        """Create a BlockIR from a model block object, ignoring nested fields."""
        return BlockIR(
            block_id=item["block_id"],
            block_type=item["block_type"],
            condition_text=item.get("condition_text"),
            spans=self._span_ids(item.get("spans", [])),
        )

    def _nested_block_items(self, item: dict[str, Any]) -> list[dict[str, Any]]:
        """Return nested block objects from known model-output keys."""
        nested: list[dict[str, Any]] = []
        for key in ("blocks", "nested_blocks", "child_blocks", "body_blocks"):
            value = item.get(key, [])
            if isinstance(value, list):
                nested.extend(v for v in value if isinstance(v, dict))
        for branch_key in ("then_blocks", "else_blocks", "elseif_blocks"):
            value = item.get(branch_key, [])
            if isinstance(value, list):
                nested.extend(v for v in value if isinstance(v, dict))
        return nested

    def _region_from_nested_blocks(
        self,
        region_id: str,
        outer_block: BlockIR,
        nested_blocks: list[BlockIR],
        flow_ref: str,
        worker_id: str | None,
    ) -> ControlComplexityRegionIR:
        """Create a confirmed control-complexity finding from nested output."""
        inner_controls = {
            block.block_type
            for block in nested_blocks
            if block.block_type in {"IF", "FOR", "WHILE"}
        }
        if len(inner_controls) == 1:
            inner_control = next(iter(inner_controls))
        elif len(inner_controls) > 1:
            inner_control = "multiple"
        else:
            inner_control = "unknown"

        can_flatten = outer_block.block_type == "SEQUENTIAL"
        can_merge_condition = (
            outer_block.block_type == "IF"
            and len(nested_blocks) == 1
            and nested_blocks[0].block_type == "IF"
        )
        can_lift_guard = outer_block.block_type in {"IF", "FOR", "WHILE"}
        severity: Literal["info", "warning", "error"]
        if can_flatten or can_merge_condition:
            severity = "info"
        elif can_lift_guard:
            severity = "warning"
        else:
            severity = "error"

        if can_flatten:
            suggested_repairs = ["split_blocks"]
        elif can_merge_condition:
            suggested_repairs = ["merge_condition"]
        elif can_lift_guard:
            suggested_repairs = [
                "guard_variable",
                "compress_to_command",
                "raise_validation_error",
            ]
        else:
            suggested_repairs = ["compress_to_command", "raise_validation_error"]

        source_span_ids = list(outer_block.spans)
        for nested_block in nested_blocks:
            source_span_ids.extend(nested_block.spans)

        scope = f"worker {worker_id}, {flow_ref}" if worker_id else flow_ref
        return ControlComplexityRegionIR(
            region_id=region_id,
            source_span_ids=self._dedupe(source_span_ids),
            outer_control=outer_block.block_type,
            inner_control=inner_control,  # type: ignore[arg-type]
            description=(
                f"Nested block intent detected in {scope}; final BlockStructureIR "
                "keeps blocks top-level because SPL block grammar does not nest."
            ),
            discovery_phase="confirmed",
            severity=severity,
            can_flatten=can_flatten,
            can_merge_condition=can_merge_condition,
            can_lift_guard=can_lift_guard,
            suggested_repairs=suggested_repairs,  # type: ignore[arg-type]
        )

    def _merge_conditions(self, outer: BlockIR, inner: BlockIR) -> BlockIR:
        """Merge nested IF conditions into one top-level IF block."""
        outer_condition = outer.condition_text or ""
        inner_condition = inner.condition_text or ""
        condition = " and ".join(
            part for part in [outer_condition, inner_condition] if part
        )
        return BlockIR(
            block_id=inner.block_id,
            block_type=inner.block_type,
            condition_text=condition or inner.condition_text,
            spans=self._dedupe([*outer.spans, *inner.spans]),
        )

    def _outer_block_covering_nested(
        self,
        outer: BlockIR,
        nested_blocks: list[BlockIR],
    ) -> BlockIR:
        """Return one top-level block covering a non-flattened nested region."""
        span_ids = list(outer.spans)
        for nested_block in nested_blocks:
            span_ids.extend(nested_block.spans)
        return BlockIR(
            block_id=outer.block_id,
            block_type=outer.block_type,
            condition_text=outer.condition_text,
            spans=self._dedupe(span_ids),
        )

    def _parse_control_regions(
        self,
        regions_data: list[dict[str, Any]],
        worker_id: str | None,
    ) -> list[ControlComplexityRegionIR]:
        """Parse optional model-reported control complexity regions."""
        regions: list[ControlComplexityRegionIR] = []
        for index, item in enumerate(regions_data, start=1):
            try:
                suggested_repairs = [
                    repair
                    for repair in item.get("suggested_repairs", [])
                    if repair != "extract_child_worker"
                ]
                regions.append(
                    ControlComplexityRegionIR(
                        region_id=item.get(
                            "region_id",
                            f"ccr_{worker_id}_{index}" if worker_id else f"ccr_{index}",
                        ),
                        source_span_ids=item["source_span_ids"],
                        outer_control=self._valid_outer_control(
                            item.get("outer_control", "unknown")
                        ),
                        inner_control=self._valid_inner_control(
                            item.get("inner_control", "unknown")
                        ),
                        description=item.get("description", "Nested control intent."),
                        discovery_phase="confirmed",
                        severity=self._valid_severity(item.get("severity", "warning")),
                        can_flatten=item.get("can_flatten", False),
                        can_merge_condition=item.get("can_merge_condition", False),
                        can_lift_guard=item.get("can_lift_guard", False),
                        suggested_repairs=suggested_repairs,
                    )
                )
            except (KeyError, TypeError, ValueError) as e:
                self.logger.warning("Skipping invalid control complexity region: %s", e)
        return regions

    def _enforce_worker_span_boundary(
        self,
        block_structure: BlockStructureIR,
        control_regions: list[ControlComplexityRegionIR],
        allowed_span_ids: set[str],
        worker_id: str | None,
    ) -> tuple[BlockStructureIR, list[ControlComplexityRegionIR], list[str]]:
        """Drop spans outside the worker-local flow and report each repair."""
        filtered_main, warnings = self._filter_blocks_to_allowed_spans(
            block_structure.main_flow_blocks,
            flow_ref="main",
            allowed_span_ids=allowed_span_ids,
            worker_id=worker_id,
        )

        filtered_alternative: dict[str, list[BlockIR]] = {}
        for flow_id, blocks in block_structure.alternative_flow_blocks.items():
            filtered_blocks, flow_warnings = self._filter_blocks_to_allowed_spans(
                blocks,
                flow_ref=flow_id,
                allowed_span_ids=allowed_span_ids,
                worker_id=worker_id,
            )
            filtered_alternative[flow_id] = filtered_blocks
            warnings.extend(flow_warnings)

        filtered_exception: dict[str, list[BlockIR]] = {}
        for flow_id, blocks in block_structure.exception_flow_blocks.items():
            filtered_blocks, flow_warnings = self._filter_blocks_to_allowed_spans(
                blocks,
                flow_ref=flow_id,
                allowed_span_ids=allowed_span_ids,
                worker_id=worker_id,
            )
            filtered_exception[flow_id] = filtered_blocks
            warnings.extend(flow_warnings)

        filtered_regions: list[ControlComplexityRegionIR] = []
        for region in control_regions:
            invalid_span_ids = [
                span_id
                for span_id in region.source_span_ids
                if span_id not in allowed_span_ids
            ]
            if invalid_span_ids:
                warnings.append(
                    self._boundary_warning(
                        worker_id,
                        f"control region {region.region_id}",
                        invalid_span_ids,
                    )
                )
            region.source_span_ids = [
                span_id
                for span_id in region.source_span_ids
                if span_id in allowed_span_ids
            ]
            if region.source_span_ids:
                filtered_regions.append(region)

        return (
            BlockStructureIR(
                main_flow_blocks=filtered_main,
                alternative_flow_blocks=filtered_alternative,
                exception_flow_blocks=filtered_exception,
            ),
            filtered_regions,
            warnings,
        )

    def _filter_blocks_to_allowed_spans(
        self,
        blocks: list[BlockIR],
        flow_ref: str,
        allowed_span_ids: set[str],
        worker_id: str | None,
    ) -> tuple[list[BlockIR], list[str]]:
        """Return blocks with only worker-local spans, dropping empty blocks."""
        filtered_blocks: list[BlockIR] = []
        warnings: list[str] = []

        for block in blocks:
            invalid_span_ids = [
                span_id for span_id in block.spans if span_id not in allowed_span_ids
            ]
            kept_span_ids = [
                span_id for span_id in block.spans if span_id in allowed_span_ids
            ]
            if invalid_span_ids:
                warnings.append(
                    self._boundary_warning(
                        worker_id,
                        f"{flow_ref} block {block.block_id}",
                        invalid_span_ids,
                    )
                )
            if not kept_span_ids:
                if block.spans:
                    warnings.append(
                        self._drop_block_warning(worker_id, flow_ref, block.block_id)
                    )
                continue
            filtered_blocks.append(
                BlockIR(
                    block_id=block.block_id,
                    block_type=block.block_type,
                    condition_text=block.condition_text,
                    spans=kept_span_ids,
                )
            )

        return filtered_blocks, warnings

    def _boundary_warning(
        self,
        worker_id: str | None,
        target: str,
        invalid_span_ids: list[str],
    ) -> str:
        """Format a worker-boundary span warning."""
        worker_label = worker_id or "legacy"
        invalid_spans = ", ".join(invalid_span_ids)
        return (
            f"Worker {worker_label} {target} referenced span(s) outside "
            f"its worker-local flow and they were discarded: {invalid_spans}."
        )

    def _drop_block_warning(
        self,
        worker_id: str | None,
        flow_ref: str,
        block_id: str,
    ) -> str:
        """Format a warning for blocks emptied by worker-boundary filtering."""
        worker_label = worker_id or "legacy"
        return (
            f"Worker {worker_label} {flow_ref} block {block_id} was dropped "
            "because no spans remained inside the worker-local flow."
        )

    def _flow_with_span_text(
        self,
        flow: FlowStructureIR,
        spans: list[SpanIR],
        include_delegation_context: bool,
    ) -> dict[str, object]:
        """Return flow JSON with span IDs paired with source text."""
        span_text_by_id = {span.span_id: span.text for span in spans}
        flow_json: dict[str, object] = {
            "main_flow_spans": self._span_refs(flow.main_flow_spans, span_text_by_id),
            "alternative_flows": [
                {
                    "flow_id": alt_flow.flow_id,
                    "condition_text": alt_flow.condition_text,
                    "spans": self._span_refs(alt_flow.spans, span_text_by_id),
                }
                for alt_flow in flow.alternative_flows
            ],
            "exception_flows": [
                {
                    "flow_id": exc_flow.flow_id,
                    "condition_text": exc_flow.condition_text,
                    "spans": self._span_refs(exc_flow.spans, span_text_by_id),
                }
                for exc_flow in flow.exception_flows
            ],
        }
        if include_delegation_context:
            flow_json["delegation_candidates"] = [
                {
                    "candidate_id": candidate.candidate_id,
                    "spans": self._span_refs(candidate.spans, span_text_by_id),
                    "reason": candidate.reason,
                    "suggested_type": candidate.suggested_type,
                    "input_variables": candidate.input_variables,
                    "output_variables": candidate.output_variables,
                }
                for candidate in flow.delegation_candidates
            ]
        return flow_json

    def _span_refs(
        self,
        span_ids: list[str],
        span_text_by_id: dict[str, str],
    ) -> list[dict[str, str]]:
        """Pair span ids with text while preserving IDs for output references."""
        return [
            {
                "span_id": span_id,
                "text": span_text_by_id.get(span_id, ""),
            }
            for span_id in span_ids
        ]

    def _span_ids(self, spans: list[Any]) -> list[str]:
        """Normalize model span refs to span_id strings."""
        span_ids: list[str] = []
        for span in spans:
            if isinstance(span, str):
                span_ids.append(span)
            elif isinstance(span, dict) and isinstance(span.get("span_id"), str):
                span_ids.append(span["span_id"])
        return span_ids

    def _valid_outer_control(
        self,
        value: Any,
    ) -> Literal["SEQUENTIAL", "IF", "FOR", "WHILE", "unknown"]:
        """Clamp outer_control to the ControlComplexityRegionIR enum."""
        if value in {"SEQUENTIAL", "IF", "FOR", "WHILE", "unknown"}:
            return value
        return "unknown"

    def _valid_inner_control(
        self,
        value: Any,
    ) -> Literal["IF", "FOR", "WHILE", "multiple", "unknown"]:
        """Clamp inner_control to the ControlComplexityRegionIR enum."""
        if value in {"IF", "FOR", "WHILE", "multiple", "unknown"}:
            return value
        return "unknown"

    def _valid_severity(self, value: Any) -> Literal["info", "warning", "error"]:
        """Clamp severity to the ControlComplexityRegionIR enum."""
        if value in {"info", "warning", "error"}:
            return value
        return "warning"

    def _dedupe(self, values: list[str]) -> list[str]:
        """Deduplicate strings while preserving order."""
        seen: set[str] = set()
        deduped: list[str] = []
        for value in values:
            if value not in seen:
                seen.add(value)
                deduped.append(value)
        return deduped
