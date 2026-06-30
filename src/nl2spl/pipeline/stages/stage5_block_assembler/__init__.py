"""Stage 5: BlockAssembler - Organize spans into top-level blocks."""

from nl2spl.pipeline.stages.stage5_block_assembler.assembler import BlockAssembler
from nl2spl.pipeline.stages.stage5_block_assembler.api_call_placement import (
    project_api_call_placements,
)

__all__ = ["BlockAssembler", "project_api_call_placements"]
