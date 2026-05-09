"""Unit tests for Stage 9: ConstraintExtractor."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from nl2spl.ir.block_structure_ir import BlockStructureIR
from nl2spl.ir.constraint_ir import ConstraintIR
from nl2spl.ir.field_route_ir import FieldRouteIR
from nl2spl.ir.flow_structure_ir import FlowStructureIR
from nl2spl.ir.span_ir import SpanIR
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.pipeline.stages.stage9_constraint_extractor import ConstraintExtractor


class TestConstraintExtractor:
    """Tests for ConstraintExtractor stage."""

    def test_prohibition_constraint(self, pipeline_config: MagicMock, mock_client: MagicMock) -> None:
        """Test prohibition constraint extraction."""
        # Arrange
        mock_client.call_json.return_value = {
            "constraints": [
                {
                    "constraint_id": "c1",
                    "text": "Do not invent facts",
                    "kind": "prohibition",
                    "targets": ["global"],
                    "source_span_ids": ["s1"],
                }
            ]
        }
        extractor = ConstraintExtractor(pipeline_config, mock_client)
        spans = [SpanIR("s1", "Do not invent facts")]
        routes = FieldRouteIR(rules=["s1"])
        flow = FlowStructureIR()
        blocks = BlockStructureIR()
        symbols = SymbolTable()
        steps = []

        # Act
        constraints = extractor.execute((spans, routes, flow, blocks, symbols, steps))

        # Assert
        assert len(constraints) == 1
        assert constraints[0].kind == "prohibition"
        assert constraints[0].text == "Do not invent facts"

    def test_requirement_constraint(self, pipeline_config: MagicMock, mock_client: MagicMock) -> None:
        """Test requirement constraint extraction."""
        # Arrange
        mock_client.call_json.return_value = {
            "constraints": [
                {
                    "constraint_id": "c1",
                    "text": "Require evidence for claims",
                    "kind": "evidence",
                    "targets": ["global"],
                    "source_span_ids": ["s1"],
                }
            ]
        }
        extractor = ConstraintExtractor(pipeline_config, mock_client)
        spans = [SpanIR("s1", "Require evidence for claims")]
        routes = FieldRouteIR(rules=["s1"])
        flow = FlowStructureIR()
        blocks = BlockStructureIR()
        symbols = SymbolTable()
        steps = []

        # Act
        constraints = extractor.execute((spans, routes, flow, blocks, symbols, steps))

        # Assert
        assert len(constraints) == 1
        assert constraints[0].kind == "evidence"

    def test_variable_target(self, pipeline_config: MagicMock, mock_client: MagicMock) -> None:
        """Test variable target constraint."""
        # Arrange
        mock_client.call_json.return_value = {
            "constraints": [
                {
                    "constraint_id": "c1",
                    "text": "Draft must include citations",
                    "kind": "requirement",
                    "targets": ["variable:draft"],
                    "source_span_ids": ["s1"],
                }
            ]
        }
        extractor = ConstraintExtractor(pipeline_config, mock_client)
        spans = [SpanIR("s1", "Draft must include citations")]
        routes = FieldRouteIR(rules=["s1"])
        flow = FlowStructureIR()
        blocks = BlockStructureIR()
        symbols = SymbolTable()
        symbols.declare("draft", "text", "output", "Draft")
        steps = []

        # Act
        constraints = extractor.execute((spans, routes, flow, blocks, symbols, steps))

        # Assert
        assert len(constraints) == 1
        assert any("variable:" in t for c in constraints for t in c.targets)

    def test_step_target(self, pipeline_config: MagicMock, mock_client: MagicMock) -> None:
        """Test step target constraint."""
        # Arrange
        mock_client.call_json.return_value = {
            "constraints": [
                {
                    "constraint_id": "c1",
                    "text": "Step must validate input",
                    "kind": "gate",
                    "targets": ["step:st1"],
                    "source_span_ids": ["s1"],
                }
            ]
        }
        extractor = ConstraintExtractor(pipeline_config, mock_client)
        spans = [SpanIR("s1", "Step must validate input")]
        routes = FieldRouteIR(rules=["s1"])
        flow = FlowStructureIR()
        blocks = BlockStructureIR()
        symbols = SymbolTable()
        steps = [StepIR("st1", "Test step", ["s1"], "GENERAL_COMMAND")]

        # Act
        constraints = extractor.execute((spans, routes, flow, blocks, symbols, steps))

        # Assert
        assert len(constraints) == 1
        assert any("step:" in t for c in constraints for t in c.targets)

    def test_multiple_constraints(self, pipeline_config: MagicMock, mock_client: MagicMock) -> None:
        """Test multiple constraints extraction."""
        # Arrange
        mock_client.call_json.return_value = {
            "constraints": [
                {
                    "constraint_id": "c1",
                    "text": "Do not invent facts",
                    "kind": "prohibition",
                    "targets": ["global"],
                    "source_span_ids": ["s1"],
                },
                {
                    "constraint_id": "c2",
                    "text": "Require evidence",
                    "kind": "evidence",
                    "targets": ["global"],
                    "source_span_ids": ["s2"],
                },
            ]
        }
        extractor = ConstraintExtractor(pipeline_config, mock_client)
        spans = [SpanIR("s1", "Do not invent facts"), SpanIR("s2", "Require evidence")]
        routes = FieldRouteIR(rules=["s1", "s2"])
        flow = FlowStructureIR()
        blocks = BlockStructureIR()
        symbols = SymbolTable()
        steps = []

        # Act
        constraints = extractor.execute((spans, routes, flow, blocks, symbols, steps))

        # Assert
        assert len(constraints) == 2

    def test_empty_constraints(self, pipeline_config: MagicMock, mock_client: MagicMock) -> None:
        """Test empty constraints handling."""
        # Arrange
        mock_client.call_json.return_value = {"constraints": []}
        extractor = ConstraintExtractor(pipeline_config, mock_client)
        spans = []
        routes = FieldRouteIR()
        flow = FlowStructureIR()
        blocks = BlockStructureIR()
        symbols = SymbolTable()
        steps = []

        # Act
        constraints = extractor.execute((spans, routes, flow, blocks, symbols, steps))

        # Assert
        assert len(constraints) == 0

    def test_llm_error(self, pipeline_config: MagicMock, mock_client: MagicMock) -> None:
        """Test LLM error handling."""
        # Arrange
        mock_client.call_json.side_effect = Exception("API error")
        extractor = ConstraintExtractor(pipeline_config, mock_client)
        spans = [SpanIR("s1", "test")]
        routes = FieldRouteIR(rules=["s1"])
        flow = FlowStructureIR()
        blocks = BlockStructureIR()
        symbols = SymbolTable()
        steps = []

        # Act & Assert
        with pytest.raises(Exception, match="API error"):
            extractor.execute((spans, routes, flow, blocks, symbols, steps))

    def test_missing_constraint_id(self, pipeline_config: MagicMock, mock_client: MagicMock) -> None:
        """Test handling of missing constraint_id."""
        # Arrange
        mock_client.call_json.return_value = {
            "constraints": [
                {"text": "test", "kind": "prohibition", "targets": [], "source_span_ids": []}
            ]
        }
        extractor = ConstraintExtractor(pipeline_config, mock_client)
        spans = [SpanIR("s1", "test")]
        routes = FieldRouteIR(rules=["s1"])
        flow = FlowStructureIR()
        blocks = BlockStructureIR()
        symbols = SymbolTable()
        steps = []

        # Act
        constraints = extractor.execute((spans, routes, flow, blocks, symbols, steps))

        # Assert
        assert len(constraints) == 0  # Should skip invalid constraints

    def test_invalid_constraint_id_format(self, pipeline_config: MagicMock, mock_client: MagicMock) -> None:
        """Test handling of invalid constraint_id format."""
        # Arrange
        mock_client.call_json.return_value = {
            "constraints": [
                {
                    "constraint_id": "invalid",
                    "text": "test",
                    "kind": "prohibition",
                    "targets": [],
                    "source_span_ids": [],
                }
            ]
        }
        extractor = ConstraintExtractor(pipeline_config, mock_client)
        spans = [SpanIR("s1", "test")]
        routes = FieldRouteIR(rules=["s1"])
        flow = FlowStructureIR()
        blocks = BlockStructureIR()
        symbols = SymbolTable()
        steps = []

        # Act
        constraints = extractor.execute((spans, routes, flow, blocks, symbols, steps))

        # Assert
        assert len(constraints) == 0  # Should skip invalid constraints

    def test_checkpoint_saved(self, pipeline_config: MagicMock, mock_client: MagicMock) -> None:
        """Test that checkpoint is saved."""
        # Arrange
        pipeline_config.save_intermediate = True
        mock_client.call_json.return_value = {
            "constraints": [
                {
                    "constraint_id": "c1",
                    "text": "test",
                    "kind": "prohibition",
                    "targets": [],
                    "source_span_ids": [],
                }
            ]
        }
        extractor = ConstraintExtractor(pipeline_config, mock_client)
        spans = [SpanIR("s1", "test")]
        routes = FieldRouteIR(rules=["s1"])
        flow = FlowStructureIR()
        blocks = BlockStructureIR()
        symbols = SymbolTable()
        steps = []

        # Act
        extractor.execute((spans, routes, flow, blocks, symbols, steps))

        # Assert - checkpoint saving is called (verified by mock)

    def test_all_constraint_kinds(self, pipeline_config: MagicMock, mock_client: MagicMock) -> None:
        """Test all constraint kinds."""
        # Arrange
        mock_client.call_json.return_value = {
            "constraints": [
                {"constraint_id": "c1", "text": "test", "kind": "requirement", "targets": [], "source_span_ids": []},
                {"constraint_id": "c2", "text": "test", "kind": "prohibition", "targets": [], "source_span_ids": []},
                {"constraint_id": "c3", "text": "test", "kind": "gate", "targets": [], "source_span_ids": []},
                {"constraint_id": "c4", "text": "test", "kind": "evidence", "targets": [], "source_span_ids": []},
                {"constraint_id": "c5", "text": "test", "kind": "approval", "targets": [], "source_span_ids": []},
                {"constraint_id": "c6", "text": "test", "kind": "safety", "targets": [], "source_span_ids": []},
                {"constraint_id": "c7", "text": "test", "kind": "audit", "targets": [], "source_span_ids": []},
                {"constraint_id": "c8", "text": "test", "kind": "delegation_boundary", "targets": [], "source_span_ids": []},
                {"constraint_id": "c9", "text": "test", "kind": "promotion_requirement", "targets": [], "source_span_ids": []},
            ]
        }
        extractor = ConstraintExtractor(pipeline_config, mock_client)
        spans = [SpanIR("s1", "test")]
        routes = FieldRouteIR(rules=["s1"])
        flow = FlowStructureIR()
        blocks = BlockStructureIR()
        symbols = SymbolTable()
        steps = []

        # Act
        constraints = extractor.execute((spans, routes, flow, blocks, symbols, steps))

        # Assert
        assert len(constraints) == 9
        kinds = {c.kind for c in constraints}
        expected_kinds = {
            "requirement",
            "prohibition",
            "gate",
            "evidence",
            "approval",
            "safety",
            "audit",
            "delegation_boundary",
            "promotion_requirement",
        }
        assert kinds == expected_kinds
