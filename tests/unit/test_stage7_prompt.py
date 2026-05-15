"""Prompt isolation tests for Stage 7: StepExtractor.

Tests the LLM prompt for step extraction independently from the full pipeline,
using mock LLM responses loaded from shared fixtures.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from nl2spl.ir.block_structure_ir import BlockStructureIR
from nl2spl.ir.diagnostics import CompileDiagnostic
from nl2spl.ir.field_route_ir import FieldRouteIR
from nl2spl.ir.flow_structure_ir import FlowStructureIR
from nl2spl.ir.span_ir import SpanIR
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.llm.prompts import load_prompt
from nl2spl.pipeline.stages.stage7_step_extractor import StepExtractor
from tests.fixtures.stage_prompt_fixtures import (
    STAGE1_EXPECTED_SPANS,
    STAGE2_EXPECTED_ROUTES,
    STAGE4_EXPECTED_FLOW,
    STAGE5_EXPECTED_BLOCKS,
    STAGE6_EXPECTED_SYMBOL_TABLE,
    STAGE7_EXPECTED_STEPS,
    STAGE7_MOCK_LLM_RESPONSE,
    compare_steps,
    generate_test_report,
    load_mock_response,
)


# =============================================================================
# Pytest Markers
# =============================================================================

pytestmark = [pytest.mark.prompt_test, pytest.mark.stage7]


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def input_spans() -> list[SpanIR]:
    """Spans produced by Stage 1 (input for Stage 7)."""
    return STAGE1_EXPECTED_SPANS


@pytest.fixture
def input_routes() -> FieldRouteIR:
    """Field routes produced by Stage 2 (input for Stage 7)."""
    return STAGE2_EXPECTED_ROUTES


@pytest.fixture
def input_flow() -> FlowStructureIR:
    """Flow structure produced by Stage 4 (input for Stage 7)."""
    return STAGE4_EXPECTED_FLOW


@pytest.fixture
def input_blocks() -> BlockStructureIR:
    """Block structure produced by Stage 5 (input for Stage 7)."""
    return STAGE5_EXPECTED_BLOCKS


@pytest.fixture
def input_symbol_table() -> SymbolTable:
    """Symbol table produced by Stage 6 (input for Stage 7)."""
    return STAGE6_EXPECTED_SYMBOL_TABLE


@pytest.fixture
def mock_llm_response() -> dict:
    """Mock LLM JSON response for Stage 7."""
    return STAGE7_MOCK_LLM_RESPONSE


@pytest.fixture
def expected_steps() -> list[StepIR]:
    """Expected step output for Stage 7."""
    return STAGE7_EXPECTED_STEPS


@pytest.fixture
def extractor(pipeline_config: MagicMock, mock_client: MagicMock) -> StepExtractor:
    """Create StepExtractor instance with mock client."""
    return StepExtractor(pipeline_config, mock_client)


# =============================================================================
# Tests
# =============================================================================


class TestStage7Prompt:
    """Test Stage 7 StepExtractor prompt in isolation."""

    def test_prompt_produces_expected_steps(
        self,
        extractor: StepExtractor,
        mock_client: MagicMock,
        mock_llm_response: dict,
        input_spans: list[SpanIR],
        input_routes: FieldRouteIR,
        input_flow: FlowStructureIR,
        input_blocks: BlockStructureIR,
        input_symbol_table: SymbolTable,
        expected_steps: list[StepIR],
    ) -> None:
        """Verify that with a mock LLM response, execute() produces expected steps."""
        mock_client.call_json.return_value = mock_llm_response

        steps, updated_symbol_table = extractor.execute(
            (input_spans, input_routes, input_flow, input_blocks, input_symbol_table)
        )

        # Assert - structure
        assert isinstance(steps, list), "First output must be a list"
        assert all(isinstance(s, StepIR) for s in steps), "All items must be StepIR"
        assert isinstance(updated_symbol_table, SymbolTable), "Second output must be SymbolTable"

        # Assert - key fields
        mismatches = compare_steps(steps, expected_steps)
        report = generate_test_report(7, "StepExtractor", mismatches)
        assert not mismatches, f"Stage 7 prompt test failed:\n{report}"

    def test_prompt_calls_llm_with_correct_stage_name(
        self,
        extractor: StepExtractor,
        mock_client: MagicMock,
        mock_llm_response: dict,
        input_spans: list[SpanIR],
        input_routes: FieldRouteIR,
        input_flow: FlowStructureIR,
        input_blocks: BlockStructureIR,
        input_symbol_table: SymbolTable,
    ) -> None:
        """Verify the LLM is called with the correct stage_name."""
        mock_client.call_json.return_value = mock_llm_response
        extractor.execute(
            (input_spans, input_routes, input_flow, input_blocks, input_symbol_table)
        )

        mock_client.call_json.assert_called_once()
        call_kwargs = mock_client.call_json.call_args[1]
        assert call_kwargs["stage_name"] == "stage7_step_extractor"

    def test_prompt_step_ids_valid(
        self,
        extractor: StepExtractor,
        mock_client: MagicMock,
        mock_llm_response: dict,
        input_spans: list[SpanIR],
        input_routes: FieldRouteIR,
        input_flow: FlowStructureIR,
        input_blocks: BlockStructureIR,
        input_symbol_table: SymbolTable,
    ) -> None:
        """Verify all step IDs have valid format (st{N})."""
        mock_client.call_json.return_value = mock_llm_response
        steps, _ = extractor.execute(
            (input_spans, input_routes, input_flow, input_blocks, input_symbol_table)
        )

        for step in steps:
            assert step.step_id.startswith("st"), f"step_id {step.step_id} must start with 'st'"

    def test_prompt_command_types_valid(
        self,
        extractor: StepExtractor,
        mock_client: MagicMock,
        mock_llm_response: dict,
        input_spans: list[SpanIR],
        input_routes: FieldRouteIR,
        input_flow: FlowStructureIR,
        input_blocks: BlockStructureIR,
        input_symbol_table: SymbolTable,
    ) -> None:
        """Verify all command types are valid."""
        mock_client.call_json.return_value = mock_llm_response
        steps, _ = extractor.execute(
            (input_spans, input_routes, input_flow, input_blocks, input_symbol_table)
        )

        valid_types = {"GENERAL_COMMAND", "CALL_API", "INVOKE_WORKER", "REQUEST_INPUT", "DISPLAY_MESSAGE"}
        for step in steps:
            assert step.command_type in valid_types, (
                f"command_type {step.command_type} must be one of {valid_types}"
            )

    def test_prompt_steps_have_io_variables(
        self,
        extractor: StepExtractor,
        mock_client: MagicMock,
        mock_llm_response: dict,
        input_spans: list[SpanIR],
        input_routes: FieldRouteIR,
        input_flow: FlowStructureIR,
        input_blocks: BlockStructureIR,
        input_symbol_table: SymbolTable,
    ) -> None:
        """Verify steps have input/output variable references."""
        mock_client.call_json.return_value = mock_llm_response
        steps, _ = extractor.execute(
            (input_spans, input_routes, input_flow, input_blocks, input_symbol_table)
        )

        for step in steps:
            assert isinstance(step.inputs, list), f"Step {step.step_id} inputs must be a list"
            assert isinstance(step.outputs, list), f"Step {step.step_id} outputs must be a list"

    def test_prompt_steps_reference_correct_flow(
        self,
        extractor: StepExtractor,
        mock_client: MagicMock,
        mock_llm_response: dict,
        input_spans: list[SpanIR],
        input_routes: FieldRouteIR,
        input_flow: FlowStructureIR,
        input_blocks: BlockStructureIR,
        input_symbol_table: SymbolTable,
    ) -> None:
        """Verify steps reference the correct flow."""
        mock_client.call_json.return_value = mock_llm_response
        steps, _ = extractor.execute(
            (input_spans, input_routes, input_flow, input_blocks, input_symbol_table)
        )

        for step in steps:
            assert step.flow_ref in ("main", "alt_1", "exc_1"), (
                f"Step {step.step_id} has unexpected flow_ref: {step.flow_ref}"
            )

    def test_prompt_symbol_table_updated(
        self,
        extractor: StepExtractor,
        mock_client: MagicMock,
        mock_llm_response: dict,
        input_spans: list[SpanIR],
        input_routes: FieldRouteIR,
        input_flow: FlowStructureIR,
        input_blocks: BlockStructureIR,
        input_symbol_table: SymbolTable,
    ) -> None:
        """Verify symbol table is updated with producer/consumer info."""
        mock_client.call_json.return_value = mock_llm_response
        _, updated_table = extractor.execute(
            (input_spans, input_routes, input_flow, input_blocks, input_symbol_table)
        )

        # At least some variables should have producer/consumer info
        has_producer = any(v.producer_step for v in updated_table.variables.values())
        assert has_producer, "Symbol table should have at least one variable with a producer step"

    def test_prompt_fixture_loader(self) -> None:
        """Verify load_mock_response() returns the same fixture data."""
        loaded = load_mock_response(7)
        assert loaded == STAGE7_MOCK_LLM_RESPONSE

    # =========================================================================
    # TODO 2: Anti-fabrication — unmapped span diagnostics
    # =========================================================================

    def test_unmapped_spans_produce_diagnostics(
        self,
        extractor: StepExtractor,
        mock_client: MagicMock,
        input_spans: list[SpanIR],
        input_routes: FieldRouteIR,
        input_flow: FlowStructureIR,
        input_blocks: BlockStructureIR,
        input_symbol_table: SymbolTable,
    ) -> None:
        """LLM-reported unmapped_spans become CompileDiagnostic records."""
        # Simulate LLM intentionally leaving "Missing timeframe" unmapped
        behavior_span = SpanIR("s_unmapped", "Missing timeframe.")
        spans = list(input_spans) + [behavior_span]
        routes = FieldRouteIR(
            behavior=input_routes.behavior + ["s_unmapped"],
            identity=input_routes.identity,
            audience=input_routes.audience,
            rules=input_routes.rules,
            domain=input_routes.domain,
            integrations=input_routes.integrations,
        )
        flow = FlowStructureIR(
            main_flow_spans=input_flow.main_flow_spans + ["s_unmapped"]
        )

        mock_client.call_json.return_value = {
            "steps": [],
            "new_variables": [],
            "unmapped_spans": [
                {
                    "span_id": "s_unmapped",
                    "reason": "Non-executable failure condition without handler",
                }
            ],
        }

        extractor.execute((spans, routes, flow, input_blocks, input_symbol_table))

        diags = getattr(extractor, "stage7_diagnostics", [])
        unmapped = [d for d in diags if d.kind == "unmapped_behavior_span"]
        assert len(unmapped) >= 1
        assert any("s_unmapped" in d.target_ref for d in unmapped)
        assert any("Missing timeframe" in d.message for d in unmapped)
        assert all(not d.blocks_rendering for d in unmapped)
        assert all(d.blocks_completion for d in unmapped)
        assert all(d.severity == "warning" for d in unmapped)

    def test_uncovered_spans_detected_even_without_llm_report(
        self,
        extractor: StepExtractor,
        mock_client: MagicMock,
        input_spans: list[SpanIR],
        input_routes: FieldRouteIR,
        input_flow: FlowStructureIR,
        input_blocks: BlockStructureIR,
        input_symbol_table: SymbolTable,
    ) -> None:
        """Behavior spans not covered by any step are auto-detected."""
        behavior_span = SpanIR("s_vague", "Handle failures properly.")
        spans = list(input_spans) + [behavior_span]
        routes = FieldRouteIR(
            behavior=input_routes.behavior + ["s_vague"],
            identity=input_routes.identity,
            audience=input_routes.audience,
            rules=input_routes.rules,
            domain=input_routes.domain,
            integrations=input_routes.integrations,
        )
        flow = FlowStructureIR(
            main_flow_spans=input_flow.main_flow_spans + ["s_vague"]
        )

        # LLM returns steps that do NOT cover "s_vague" — and no unmapped_spans
        mock_client.call_json.return_value = {
            "steps": [
                {
                    "step_id": "st_1",
                    "text": "Produce a draft",
                    "source_span_ids": ["s1"],
                    "command_type": "GENERAL_COMMAND",
                    "inputs": [],
                    "outputs": [],
                    "integration_ref": None,
                    "flow_ref": "main",
                    "block_ref": "b1",
                    "kind": "normal",
                }
            ],
            "new_variables": [],
        }

        extractor.execute((spans, routes, flow, input_blocks, input_symbol_table))

        diags = getattr(extractor, "stage7_diagnostics", [])
        unmapped = [d for d in diags if d.kind == "unmapped_behavior_span"]
        assert any("s_vague" in d.target_ref for d in unmapped), (
            f"Expected unmapped diagnostic for s_vague, got: {[d.target_ref for d in unmapped]}"
        )

    def test_prompt_no_longer_forces_every_span_to_step(self) -> None:
        """The Stage 7 prompt must not say every behavior span must map to a step."""
        prompt = load_prompt("stage7")
        assert "Every behavior span must map to at least one step" not in prompt, (
            "Prompt must not force every span into a step"
        )
        assert "source-backed EXECUTABLE behaviors" in prompt, (
            "Prompt should guide LLM to only map executable behaviors"
        )

    def test_prompt_request_input_requires_explicit_source(self) -> None:
        """REQUEST_INPUT must only be used when source explicitly requests user input."""
        prompt = load_prompt("stage7")
        # The prompt must contain guidance that REQUEST_INPUT requires explicit
        # source evidence. Check for key fragments since encoding may vary.
        assert "REQUEST_INPUT" in prompt
        assert "explicitly" in prompt
        assert "receive input" in prompt.lower() or "receive input back" in prompt.lower()

    def test_prompt_output_format_includes_unmapped_spans(self) -> None:
        """Prompt output format should document the unmapped_spans field."""
        prompt = load_prompt("stage7")
        assert '"unmapped_spans"' in prompt, (
            "Prompt output format must include unmapped_spans"
        )
        assert "unmapped_spans is optional" in prompt, (
            "Prompt must note that unmapped_spans is optional"
        )
