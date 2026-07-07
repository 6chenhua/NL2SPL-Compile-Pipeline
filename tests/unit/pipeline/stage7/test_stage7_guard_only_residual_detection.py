"""Unit tests for Stage 7 guard-only residual step detection and rejection."""

from __future__ import annotations

from unittest.mock import MagicMock

from nl2spl.ir.block_structure_ir import BlockStructureIR
from nl2spl.ir.field_route_ir import FieldRouteIR
from nl2spl.ir.flow_structure_ir import FlowStructureIR
from nl2spl.ir.span_ir import SpanIR
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.pipeline.stages.stage7_step_extractor.extractor import StepExtractor


def _run_extractor(mock_steps):
    config = MagicMock()
    client = MagicMock()
    client.call_json.return_value = {
        "steps": mock_steps,
        "new_variables": [],
    }

    extractor = StepExtractor(config, client)

    # Minimal valid inputs for extractor
    spans = [SpanIR(span_id="s1", text="some text")]
    routes = FieldRouteIR(
        identity=[], audience=[], rules=[], domain=[], integrations=[], behavior=["s1"]
    )
    flow_structure = FlowStructureIR(main_flow_spans=["s1"])
    block_structure = BlockStructureIR()
    symbol_table = SymbolTable()

    steps, symbol_table = extractor.execute(
        (spans, routes, flow_structure, block_structure, symbol_table)
    )
    return extractor, steps, symbol_table


def test_stage7_rejects_guard_only_residual_step() -> None:
    mock_steps = [
        {
            "step_id": "st_1",
            "text": "When enough required information is available",
            "source_span_ids": ["s1"],
            "command_type": "GENERAL_COMMAND",
        }
    ]
    extractor, steps, symbol_table = _run_extractor(mock_steps)
    assert len(steps) == 0
    assert len(symbol_table.variables) == 0
    assert "stage7_guard_residual_not_materialized" in {
        diag.kind for diag in extractor.stage7_diagnostics
    }


def test_stage7_accepts_valid_step_starting_with_guard_word_and_comma() -> None:
    # A step starting with "If" but contains a comma separating the condition and action
    mock_steps = [
        {
            "step_id": "st_1",
            "text": "If the user asks for revision, revise the draft.",
            "source_span_ids": ["s1"],
            "command_type": "GENERAL_COMMAND",
        }
    ]

    extractor, steps, symbol_table = _run_extractor(mock_steps)
    assert len(steps) == 1
    assert steps[0].step_id == "st_1"
    assert steps[0].text == "If the user asks for revision, revise the draft."
    assert extractor.stage7_diagnostics == []
