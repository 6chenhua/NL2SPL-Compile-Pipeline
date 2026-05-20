"""Unit tests for Stage 5 adjacent sequential block merge post-processing."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from nl2spl.config import PipelineConfig
from nl2spl.ir.block_structure_ir import BlockIR, BlockStructureIR
from nl2spl.ir.field_route_ir import FieldRouteIR
from nl2spl.ir.flow_structure_ir import FlowStructureIR
from nl2spl.ir.span_ir import SpanIR
from nl2spl.pipeline.stages.stage5_block_assembler import BlockAssembler
from nl2spl.pipeline.stages.stage5_block_assembler.block_postprocess import (
    merge_adjacent_sequential_blocks,
)


def _seq(block_id: str, *span_ids: str) -> BlockIR:
    return BlockIR(block_id=block_id, block_type="SEQUENTIAL", spans=list(span_ids))


def _if_block(block_id: str, condition: str = "cond") -> BlockIR:
    return BlockIR(
        block_id=block_id, block_type="IF",
        condition_text=condition, spans=["s_if"],
    )


class TestMergeAdjacentSequentialBlocks:
    def test_adjacent_seq_merged_in_main_flow(self) -> None:
        blocks = BlockStructureIR(
            main_flow_blocks=[
                _seq("b1", "s1", "s2"),
                _seq("b2", "s3"),
            ]
        )
        result = merge_adjacent_sequential_blocks(blocks)

        assert len(result.main_flow_blocks) == 1
        assert result.main_flow_blocks[0].block_id == "b1"
        assert result.main_flow_blocks[0].spans == ["s1", "s2", "s3"]

    def test_three_adjacent_seq_merged_into_one(self) -> None:
        blocks = BlockStructureIR(
            main_flow_blocks=[
                _seq("b1", "s1"),
                _seq("b2", "s2"),
                _seq("b3", "s3"),
            ]
        )
        result = merge_adjacent_sequential_blocks(blocks)

        assert len(result.main_flow_blocks) == 1
        assert result.main_flow_blocks[0].block_id == "b1"
        assert result.main_flow_blocks[0].spans == ["s1", "s2", "s3"]

    def test_seq_if_seq_not_merged_across_if(self) -> None:
        blocks = BlockStructureIR(
            main_flow_blocks=[
                _seq("b1", "s1"),
                _if_block("b2"),
                _seq("b3", "s2"),
            ]
        )
        result = merge_adjacent_sequential_blocks(blocks)

        assert len(result.main_flow_blocks) == 3
        assert result.main_flow_blocks[0].spans == ["s1"]
        assert result.main_flow_blocks[1].block_type == "IF"
        assert result.main_flow_blocks[2].spans == ["s2"]

    def test_alternative_flow_adjacent_seq_merged(self) -> None:
        blocks = BlockStructureIR(
            main_flow_blocks=[_seq("b1", "s1")],
            alternative_flow_blocks={
                "alt_01": [
                    _seq("b2", "s2"),
                    _seq("b3", "s3"),
                ]
            },
        )
        result = merge_adjacent_sequential_blocks(blocks)

        alt_blocks = result.alternative_flow_blocks["alt_01"]
        assert len(alt_blocks) == 1
        assert alt_blocks[0].block_id == "b2"
        assert alt_blocks[0].spans == ["s2", "s3"]

    def test_exception_flow_adjacent_seq_merged(self) -> None:
        blocks = BlockStructureIR(
            main_flow_blocks=[_seq("b1", "s1")],
            exception_flow_blocks={
                "exc_01": [
                    _seq("b2", "s_e1"),
                    _seq("b3", "s_e2"),
                ]
            },
        )
        result = merge_adjacent_sequential_blocks(blocks)

        exc_blocks = result.exception_flow_blocks["exc_01"]
        assert len(exc_blocks) == 1
        assert exc_blocks[0].block_id == "b2"
        assert exc_blocks[0].spans == ["s_e1", "s_e2"]

    def test_non_seq_blocks_not_merged(self) -> None:
        blocks = BlockStructureIR(
            main_flow_blocks=[
                _if_block("b1"),
                _if_block("b2"),
            ]
        )
        result = merge_adjacent_sequential_blocks(blocks)

        assert len(result.main_flow_blocks) == 2
        assert result.main_flow_blocks[0].block_id == "b1"
        assert result.main_flow_blocks[1].block_id == "b2"

    def test_single_seq_unchanged(self) -> None:
        blocks = BlockStructureIR(
            main_flow_blocks=[_seq("b1", "s1", "s2")],
        )
        result = merge_adjacent_sequential_blocks(blocks)

        assert len(result.main_flow_blocks) == 1
        assert result.main_flow_blocks[0].block_id == "b1"
        assert result.main_flow_blocks[0].spans == ["s1", "s2"]

    def test_empty_blocks_unchanged(self) -> None:
        blocks = BlockStructureIR()
        result = merge_adjacent_sequential_blocks(blocks)

        assert result.main_flow_blocks == []

    def test_input_not_mutated(self) -> None:
        original = BlockStructureIR(
            main_flow_blocks=[
                _seq("b1", "s1"),
                _seq("b2", "s2"),
            ]
        )
        merge_adjacent_sequential_blocks(original)

        assert len(original.main_flow_blocks) == 2
        assert original.main_flow_blocks[0].block_id == "b1"
        assert original.main_flow_blocks[1].block_id == "b2"

    def test_consecutive_span_dedup_at_boundary(self) -> None:
        blocks = BlockStructureIR(
            main_flow_blocks=[
                _seq("b1", "s1", "s2"),
                _seq("b2", "s2", "s3"),
            ]
        )
        result = merge_adjacent_sequential_blocks(blocks)

        assert result.main_flow_blocks[0].spans == ["s1", "s2", "s3"]

    def test_for_while_blocks_not_merged(self) -> None:
        for_loop = BlockIR(
            block_id="b1", block_type="FOR",
            condition_text="each item", spans=["s_loop"],
        )
        while_loop = BlockIR(
            block_id="b2", block_type="WHILE",
            condition_text="retry", spans=["s_retry"],
        )
        blocks = BlockStructureIR(main_flow_blocks=[for_loop, while_loop])
        result = merge_adjacent_sequential_blocks(blocks)

        assert len(result.main_flow_blocks) == 2
        assert result.main_flow_blocks[0].block_type == "FOR"
        assert result.main_flow_blocks[1].block_type == "WHILE"

    def test_seq_with_condition_not_merged(self) -> None:
        seq_with_cond = BlockIR(
            block_id="b1", block_type="SEQUENTIAL",
            condition_text="if user agrees", spans=["s1"],
        )
        blocks = BlockStructureIR(
            main_flow_blocks=[
                seq_with_cond,
                _seq("b2", "s2"),
            ]
        )
        result = merge_adjacent_sequential_blocks(blocks)

        assert len(result.main_flow_blocks) == 2

    @pytest.mark.parametrize(
        "flow_type",
        ["alternative_flow_blocks", "exception_flow_blocks"],
    )
    def test_merge_does_not_cross_flow_ids(self, flow_type: str) -> None:
        """Adjacent SEQ blocks across different flow IDs are not merged."""
        flow_dict = {
            "flow_a": [_seq("b1", "s1")],
            "flow_b": [_seq("b2", "s2")],
        }
        blocks = BlockStructureIR(
            main_flow_blocks=[_seq("b0", "s0")],
            **{flow_type: flow_dict},
        )
        result = merge_adjacent_sequential_blocks(blocks)

        result_flows = (
            result.alternative_flow_blocks
            if flow_type == "alternative_flow_blocks"
            else result.exception_flow_blocks
        )
        assert len(result_flows["flow_a"]) == 1
        assert len(result_flows["flow_b"]) == 1


# =============================================================================
# Integration test — BlockAssembler.execute() with adjacent SEQUENTIAL blocks
# =============================================================================


class TestBlockAssemblerIntegration:
    """Verify that merge_adjacent_sequential_blocks is wired into execute()."""

    @pytest.fixture
    def assembler(self, pipeline_config: PipelineConfig, mock_client: MagicMock) -> BlockAssembler:
        return BlockAssembler(pipeline_config, mock_client)

    def test_adjacent_seq_merged_in_execute(
        self,
        assembler: BlockAssembler,
        mock_client: MagicMock,
    ) -> None:
        """Two adjacent SEQUENTIAL blocks from LLM → merged in execute() output."""
        mock_client.call_json.return_value = {
            "main_flow_blocks": [
                {"block_id": "b1", "block_type": "SEQUENTIAL", "spans": ["s1", "s2"]},
                {"block_id": "b2", "block_type": "SEQUENTIAL", "spans": ["s3"]},
            ],
            "alternative_flow_blocks": {},
            "exception_flow_blocks": {},
        }

        spans = [
            SpanIR("s1", "Normalize request."),
            SpanIR("s2", "Identify vendors."),
            SpanIR("s3", "Solicit quotes."),
        ]
        routes = FieldRouteIR(behavior=["s1", "s2", "s3"])
        flow = FlowStructureIR(main_flow_spans=["s1", "s2", "s3"])

        result = assembler.execute((spans, routes, flow))

        assert len(result.main_flow_blocks) == 1
        assert result.main_flow_blocks[0].block_id == "b1"
        assert result.main_flow_blocks[0].spans == ["s1", "s2", "s3"]

    def test_seq_if_seq_not_merged_in_execute(
        self,
        assembler: BlockAssembler,
        mock_client: MagicMock,
    ) -> None:
        """SEQ + IF + SEQ from LLM → three blocks preserved, no cross-IF merge."""
        mock_client.call_json.return_value = {
            "main_flow_blocks": [
                {"block_id": "b1", "block_type": "SEQUENTIAL", "spans": ["s1"]},
                {
                    "block_id": "b2", "block_type": "IF",
                    "condition_text": "over budget", "spans": ["s2"],
                },
                {"block_id": "b3", "block_type": "SEQUENTIAL", "spans": ["s3"]},
            ],
            "alternative_flow_blocks": {},
            "exception_flow_blocks": {},
        }

        spans = [
            SpanIR("s1", "Review."),
            SpanIR("s2", "Over budget check."),
            SpanIR("s3", "Continue."),
        ]
        routes = FieldRouteIR(behavior=["s1", "s2", "s3"])
        flow = FlowStructureIR(main_flow_spans=["s1", "s2", "s3"])

        result = assembler.execute((spans, routes, flow))

        assert len(result.main_flow_blocks) == 3
        assert result.main_flow_blocks[0].block_type == "SEQUENTIAL"
        assert result.main_flow_blocks[1].block_type == "IF"
        assert result.main_flow_blocks[2].block_type == "SEQUENTIAL"
