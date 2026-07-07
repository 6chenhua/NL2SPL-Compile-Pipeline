"""Unit tests for Stage 5 Block Assembler guarded_action condition text consumption."""

from __future__ import annotations

from unittest.mock import MagicMock

from nl2spl.ir.field_route_ir import FieldRouteIR
from nl2spl.ir.flow_structure_ir import FlowStructureIR
from nl2spl.ir.span_ir import SpanIR
from nl2spl.pipeline.stages.stage5_block_assembler import BlockAssembler


def test_stage5_consumes_stage1_guard_text_exact() -> None:
    # 1. Setup spans, one with the guard_text_exact dynamic attribute
    s1 = SpanIR(
        span_id="s16",
        text="When enough required information is available produce a draft.",
        source_section_id="reusable_process",
    )
    s1.guard_text_exact = "enough required information is available"
    s1.segmentation_kind = "guarded_action"

    spans = [s1]

    # 2. Setup routes and flow structure input
    routes = FieldRouteIR(
        identity=[],
        audience=[],
        rules=[],
        domain=[],
        integrations=[],
        behavior=["s16"],
    )
    # Mock RouteAnnotation as well to bypass Stage 2/4 checks
    routes.annotations = []

    flow_input = FlowStructureIR(
        main_flow_spans=["s16"],
        alternative_flows=[],
        exception_flows=[],
        delegation_candidates=[],
    )

    # 3. Setup mock LLM client to return an IF block containing s16
    mock_client = MagicMock()
    mock_client.call_json.return_value = {
        "main_flow_blocks": [
            {
                "block_id": "b_16",
                "block_type": "IF",
                "condition_text": "redundant condition text from LLM",  # Should be overridden!
                "spans": ["s16"],
            }
        ]
    }

    # 4. Run block assembler
    config = MagicMock()
    assembler = BlockAssembler(config, mock_client)

    block_structure = assembler.execute((spans, routes, flow_input))

    # 5. Verify condition_text is overridden by s1's guard_text_exact
    assert len(block_structure.main_flow_blocks) == 1
    block = block_structure.main_flow_blocks[0]
    assert block.block_type == "IF"
    assert block.condition_text == "enough required information is available"


def test_stage5_splits_sequential_block_for_guarded_action() -> None:
    spans = [
        SpanIR(span_id="s15", text="Maintain provenance."),
        SpanIR(
            span_id="s16",
            text="When enough required information is available produce a draft.",
            guard_text_exact="enough required information is available",
            action_text_exact="produce a draft",
            segmentation_kind="guarded_action",
        ),
        SpanIR(span_id="s17", text="Record assumptions."),
    ]
    routes = FieldRouteIR(
        identity=[],
        audience=[],
        rules=[],
        domain=[],
        integrations=[],
        behavior=["s15", "s16", "s17"],
    )
    flow_input = FlowStructureIR(main_flow_spans=["s15", "s16", "s17"])
    mock_client = MagicMock()
    mock_client.call_json.return_value = {
        "main_flow_blocks": [
            {
                "block_id": "b_main",
                "block_type": "SEQUENTIAL",
                "spans": ["s15", "s16", "s17"],
            }
        ]
    }

    assembler = BlockAssembler(MagicMock(), mock_client)
    block_structure = assembler.execute((spans, routes, flow_input))

    assert [
        (block.block_type, block.spans, block.condition_text)
        for block in block_structure.main_flow_blocks
    ] == [
        ("SEQUENTIAL", ["s15"], None),
        ("IF", ["s16"], "enough required information is available"),
        ("SEQUENTIAL", ["s17"], None),
    ]
