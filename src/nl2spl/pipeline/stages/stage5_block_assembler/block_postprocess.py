"""Stage 5 deterministic post-processing: merge adjacent sequential blocks.

Adjacent SEQUENTIAL blocks in the same flow have no structural difference
from a single merged SEQUENTIAL block.  Rendering them separately only
adds SPL noise.  This module normalizes them after LLM parsing and before
the block structure is returned to the caller.
"""

from __future__ import annotations

from nl2spl.ir.block_structure_ir import BlockIR, BlockStructureIR


def merge_adjacent_sequential_blocks(blocks: BlockStructureIR) -> BlockStructureIR:
    """Normalize away adjacent SEQUENTIAL blocks across all flows.

    Only adjacent ``SEQUENTIAL`` blocks without ``condition_text`` are
    merged.  ``IF``, ``FOR``, ``WHILE``, and conditional blocks are never
    merged.  Merging never crosses flow boundaries (main / alternative /
    exception).

    Returns a new ``BlockStructureIR``; the input is not mutated.
    """
    return BlockStructureIR(
        main_flow_blocks=_merge_block_list(blocks.main_flow_blocks),
        alternative_flow_blocks={
            flow_id: _merge_block_list(flow_blocks)
            for flow_id, flow_blocks in blocks.alternative_flow_blocks.items()
        },
        exception_flow_blocks={
            flow_id: _merge_block_list(flow_blocks)
            for flow_id, flow_blocks in blocks.exception_flow_blocks.items()
        },
    )


def _merge_block_list(blocks: list[BlockIR]) -> list[BlockIR]:
    """Merge adjacent SEQUENTIAL blocks in a flat block list."""
    if len(blocks) <= 1:
        return [BlockIR(b.block_id, b.block_type, b.condition_text, list(b.spans)) for b in blocks]

    merged: list[BlockIR] = []

    for block in blocks:
        if (
            merged
            and block.block_type == "SEQUENTIAL"
            and merged[-1].block_type == "SEQUENTIAL"
            and not block.condition_text
            and not merged[-1].condition_text
        ):
            merged[-1] = BlockIR(
                block_id=merged[-1].block_id,
                block_type="SEQUENTIAL",
                condition_text=None,
                spans=_append_without_boundary_duplicate(merged[-1].spans, block.spans),
            )
        else:
            merged.append(
                BlockIR(
                    block_id=block.block_id,
                    block_type=block.block_type,
                    condition_text=block.condition_text,
                    spans=list(block.spans),
                )
            )

    return merged


def _append_without_boundary_duplicate(existing: list[str], incoming: list[str]) -> list[str]:
    """Append items from *incoming* that are not already at the end of *existing*."""
    result = list(existing)
    for item in incoming:
        if not result or result[-1] != item:
            result.append(item)
    return result
