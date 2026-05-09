"""Stage 5: BlockAssembler - Organize spans into blocks within flows."""

from __future__ import annotations

import json
from dataclasses import asdict

from nl2spl.errors.exceptions import StageError
from nl2spl.ir.block_structure_ir import BlockIR, BlockStructureIR
from nl2spl.ir.field_route_ir import FieldRouteIR
from nl2spl.ir.flow_structure_ir import FlowStructureIR
from nl2spl.ir.span_ir import SpanIR
from nl2spl.llm.prompts import load_prompt
from nl2spl.pipeline.stages.base import PipelineStage


class BlockAssembler(
    PipelineStage[tuple[list[SpanIR], FieldRouteIR, FlowStructureIR], BlockStructureIR]
):
    """Organize behavior spans into blocks within each flow.

    This stage takes behavior spans, field routes, and flow structure,
    then organizes spans into blocks (SEQUENTIAL/IF/FOR/WHILE) within
    each flow.
    """

    @property
    def name(self) -> str:
        """Stage name for logging and checkpointing."""
        return "stage5_block_assembler"

    def execute(
        self, input_data: tuple[list[SpanIR], FieldRouteIR, FlowStructureIR]
    ) -> BlockStructureIR:
        """Execute block assembly.

        Args:
            input_data: Tuple of (spans, field routes, flow structure)

        Returns:
            BlockStructureIR with blocks organized by flow

        Raises:
            StageError: If block assembly fails
        """
        spans, routes, flow_structure = input_data
        self.logger.info(
            "Starting block assembly with %d spans and %d behavior spans",
            len(spans),
            len(routes.behavior),
        )

        # 1. Build prompts
        behavior_spans = [s for s in spans if s.span_id in routes.behavior]
        behavior_json = json.dumps([asdict(s) for s in behavior_spans], ensure_ascii=False)
        flow_json = json.dumps(asdict(flow_structure), ensure_ascii=False)

        system_prompt = load_prompt("stage5")
        user_prompt = f"""请将以下 span 组织成 Block：

Flow 结构：
---
{flow_json}
---

behavior spans：
---
{behavior_json}
---

输出 JSON："""

        # 2. Call LLM
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

        # 3. Parse result
        main_flow_blocks: list[BlockIR] = []
        for item in result.get("main_flow_blocks", []):
            try:
                main_flow_blocks.append(BlockIR(**item))
            except (KeyError, ValueError, TypeError) as e:
                self.logger.warning("Skipping invalid main flow block: %s", e)
                continue

        alternative_flow_blocks: dict[str, list[BlockIR]] = {}
        for flow_id, blocks_data in result.get("alternative_flow_blocks", {}).items():
            flow_blocks: list[BlockIR] = []
            for item in blocks_data:
                try:
                    flow_blocks.append(BlockIR(**item))
                except (KeyError, ValueError, TypeError) as e:
                    self.logger.warning(
                        "Skipping invalid alternative flow block in %s: %s",
                        flow_id,
                        e,
                    )
                    continue
            alternative_flow_blocks[flow_id] = flow_blocks

        exception_flow_blocks: dict[str, list[BlockIR]] = {}
        for flow_id, blocks_data in result.get("exception_flow_blocks", {}).items():
            exc_blocks: list[BlockIR] = []
            for item in blocks_data:
                try:
                    exc_blocks.append(BlockIR(**item))
                except (KeyError, ValueError, TypeError) as e:
                    self.logger.warning(
                        "Skipping invalid exception flow block in %s: %s",
                        flow_id,
                        e,
                    )
                    continue
            exception_flow_blocks[flow_id] = exc_blocks

        block_structure = BlockStructureIR(
            main_flow_blocks=main_flow_blocks,
            alternative_flow_blocks=alternative_flow_blocks,
            exception_flow_blocks=exception_flow_blocks,
        )

        total_blocks = len(block_structure.get_all_blocks())
        self.logger.info(
            "Created %d blocks (%d main, %d alternative flows, %d exception flows)",
            total_blocks,
            len(main_flow_blocks),
            len(alternative_flow_blocks),
            len(exception_flow_blocks),
        )

        # 4. Save checkpoint
        self.save_checkpoint(asdict(block_structure))

        return block_structure
