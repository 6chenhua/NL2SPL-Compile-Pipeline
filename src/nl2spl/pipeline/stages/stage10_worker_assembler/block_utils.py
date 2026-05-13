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
            if step.block_ref and step.block_ref in block_ids:
                continue
            if any(span_id in block_spans for span_id in step.source_span_ids):
                continue
            unrendered_steps.append(step)

        if not blocks:
            unrendered_steps = list(steps)

        if not unrendered_steps:
            return blocks

        return [*blocks, self._fallback_block_for_steps(fallback_block_id, unrendered_steps)]

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
            if not step.block_ref:
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
