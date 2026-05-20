"""Block utility methods for Stage 10 WorkerAssembler."""

from __future__ import annotations

from nl2spl.ir.block_structure_ir import BlockIR, BlockStructureIR
from nl2spl.ir.step_ir import StepIR


class BlockUtilsMixin:
    """Mixin class containing block utility methods for WorkerAssembler."""

    def _ensure_renderable_blocks(
        self,
        blocks: list[BlockIR],
        steps: list[StepIR],
        fallback_block_id: str,
        coverage_blocks: list[BlockIR] | None = None,
    ) -> list[BlockIR]:
        """Ensure all steps can be selected by renderer block matching."""
        if not steps:
            return blocks

        rendered_blocks = coverage_blocks if coverage_blocks is not None else blocks
        block_ids = {block.block_id for block in rendered_blocks}
        block_spans = {span_id for block in rendered_blocks for span_id in block.spans}
        unrendered_steps: list[StepIR] = []

        for step in steps:
            if step.flow_ref and step.flow_ref != "main":
                continue
            if step.block_ref and step.block_ref in block_ids:
                continue
            if any(span_id in block_spans for span_id in step.source_span_ids):
                continue
            unrendered_steps.append(step)

        if not blocks:
            unrendered_steps = [
                step for step in steps
                if not step.flow_ref or step.flow_ref == "main"
            ]

        if not unrendered_steps:
            return blocks

        insert_at = self._fallback_insert_index(blocks, unrendered_steps)
        fallback_block = self._fallback_block_for_steps(
            fallback_block_id,
            unrendered_steps,
        )
        return [*blocks[:insert_at], fallback_block, *blocks[insert_at:]]

    def _all_blocks(self, blocks: BlockStructureIR | None) -> list[BlockIR]:
        if blocks is None:
            return []
        return blocks.get_all_blocks()

    def _fallback_block_for_steps(
        self,
        block_id: str,
        steps: list[StepIR],
    ) -> BlockIR:
        """Build a fallback block using source spans while setting block_ref."""
        span_ids: list[str] = []
        seen: set[str] = set()
        for step in steps:
            if not step.block_ref or step.block_ref.startswith("before:"):
                step.block_ref = block_id
            for span_id in step.source_span_ids:
                if span_id not in seen:
                    span_ids.append(span_id)
                    seen.add(span_id)

        return BlockIR(
            block_id=block_id,
            block_type="SEQUENTIAL",
            spans=span_ids,
        )

    @staticmethod
    def _fallback_insert_index(blocks: list[BlockIR], steps: list[StepIR]) -> int:
        for step in steps:
            if not step.block_ref.startswith("before:"):
                continue
            target_span_id = step.block_ref.removeprefix("before:")
            for index, block in enumerate(blocks):
                if target_span_id in block.spans:
                    return index
        return len(blocks)
