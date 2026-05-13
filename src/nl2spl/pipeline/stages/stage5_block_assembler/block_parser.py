"""Stage 5: BlockAssembler - BlockParserMixin (block list/item parsing and nesting repair)."""

from __future__ import annotations

from typing import Any, Literal

from nl2spl.ir.block_structure_ir import BlockIR
from nl2spl.ir.worker_plan_ir import ControlComplexityRegionIR


class BlockParserMixin:
    """Mixin containing block parsing and nesting-repair methods."""

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
