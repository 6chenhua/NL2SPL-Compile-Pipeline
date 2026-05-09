"""BlockStructureIR - Block structure within flows."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

BlockType = Literal["SEQUENTIAL", "IF", "FOR", "WHILE"]


@dataclass
class BlockIR:
    """Block within a flow.

    Attributes:
        block_id: Unique identifier (format: b{N})
        block_type: Block type
        condition_text: Condition text (for IF/FOR/WHILE)
        spans: Span IDs in this block
    """

    block_id: str
    block_type: BlockType
    condition_text: str | None = None
    spans: list[str] = field(default_factory=list)


@dataclass
class BlockStructureIR:
    """Block structure for all flows.

    Attributes:
        main_flow_blocks: Blocks in main flow
        alternative_flow_blocks: Blocks in alternative flows (keyed by flow_id)
        exception_flow_blocks: Blocks in exception flows (keyed by flow_id)
    """

    main_flow_blocks: list[BlockIR] = field(default_factory=list)
    alternative_flow_blocks: dict[str, list[BlockIR]] = field(default_factory=dict)
    exception_flow_blocks: dict[str, list[BlockIR]] = field(default_factory=dict)

    def get_all_blocks(self) -> list[BlockIR]:
        """Get all blocks across all flows."""
        blocks = list(self.main_flow_blocks)
        for flow_blocks in self.alternative_flow_blocks.values():
            blocks.extend(flow_blocks)
        for flow_blocks in self.exception_flow_blocks.values():
            blocks.extend(flow_blocks)
        return blocks

    def get_block_for_span(self, span_id: str) -> BlockIR | None:
        """Find the block containing a span.

        Args:
            span_id: Span ID to look up

        Returns:
            BlockIR or None if not found
        """
        for block in self.get_all_blocks():
            if span_id in block.spans:
                return block
        return None
