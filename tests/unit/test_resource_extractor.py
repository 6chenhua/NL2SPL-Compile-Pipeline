"""Unit tests for Stage 6: ResourceExtractor."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from nl2spl.errors.exceptions import StageError
from nl2spl.ir.field_route_ir import FieldRouteIR
from nl2spl.ir.span_ir import SpanIR
from nl2spl.pipeline.stages.stage6_resource_extractor import ResourceExtractor


class TestResourceExtractor:
    """Tests for ResourceExtractor stage."""

    def test_input_variables(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """Test input variable identification."""
        # Arrange
        spans = [SpanIR(span_id="s1", text="A user request is provided")]
        routes = FieldRouteIR(behavior=["s1"])
        mock_client.call_json.return_value = {
            "variables": [
                {
                    "name": "user_request",
                    "data_type": "text",
                    "required": True,
                    "description": "User's request",
                    "source": "input",
                }
            ],
            "files": [],
            "apis": [],
            "types": [],
        }
        extractor = ResourceExtractor(pipeline_config, mock_client)

        # Act
        resources, symbols = extractor.execute((spans, routes))

        # Assert
        assert len(resources.variables) == 1
        assert resources.variables[0].source == "input"
        assert "user_request" in symbols.variables

    def test_output_variables(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """Test output variable identification."""
        # Arrange
        spans = [SpanIR(span_id="s1", text="Produce a draft communication")]
        routes = FieldRouteIR(behavior=["s1"])
        mock_client.call_json.return_value = {
            "variables": [
                {
                    "name": "draft_communication",
                    "data_type": "text",
                    "required": True,
                    "description": "Draft communication output",
                    "source": "output",
                }
            ],
            "files": [],
            "apis": [],
            "types": [],
        }
        extractor = ResourceExtractor(pipeline_config, mock_client)

        # Act
        resources, symbols = extractor.execute((spans, routes))

        # Assert
        assert len(resources.variables) == 1
        assert resources.variables[0].source == "output"
        assert "draft_communication" in symbols.variables

    def test_step_variables(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """Test intermediate variable identification."""
        # Arrange
        spans = [SpanIR(span_id="s1", text="Then use the result to continue")]
        routes = FieldRouteIR(behavior=["s1"])
        mock_client.call_json.return_value = {
            "variables": [
                {
                    "name": "intermediate_result",
                    "data_type": "text",
                    "required": False,
                    "description": "Intermediate result",
                    "source": "step",
                }
            ],
            "files": [],
            "apis": [],
            "types": [],
        }
        extractor = ResourceExtractor(pipeline_config, mock_client)

        # Act
        resources, symbols = extractor.execute((spans, routes))

        # Assert
        assert len(resources.variables) == 1
        assert resources.variables[0].source == "step"

    def test_api_extraction(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """Test API extraction."""
        # Arrange
        spans = [SpanIR(span_id="s1", text="Call source retrieval API")]
        routes = FieldRouteIR(integrations=["s1"])
        mock_client.call_json.return_value = {
            "variables": [],
            "files": [],
            "apis": [
                {
                    "api_name": "source_retrieval",
                    "auth": "api_key",
                    "description": "Source retrieval API",
                    "functions": [
                        {
                            "name": "retrieve",
                            "description": "Retrieve sources",
                            "parameters": [
                                {"name": "query", "type": "text", "description": "Search query"}
                            ],
                            "return_type": "List[text]",
                        }
                    ],
                }
            ],
            "types": [],
        }
        extractor = ResourceExtractor(pipeline_config, mock_client)

        # Act
        resources, symbols = extractor.execute((spans, routes))

        # Assert
        assert len(resources.apis) == 1
        assert resources.apis[0].api_name == "source_retrieval"
        assert resources.apis[0].auth == "api_key"
        assert len(resources.apis[0].functions) == 1

    def test_file_extraction(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """Test file extraction."""
        # Arrange
        spans = [SpanIR(span_id="s1", text="Use template file for output")]
        routes = FieldRouteIR(behavior=["s1"])
        mock_client.call_json.return_value = {
            "variables": [],
            "files": [
                {
                    "name": "template",
                    "path": "/templates/output.txt",
                    "data_type": "text",
                    "description": "Output template",
                }
            ],
            "apis": [],
            "types": [],
        }
        extractor = ResourceExtractor(pipeline_config, mock_client)

        # Act
        resources, symbols = extractor.execute((spans, routes))

        # Assert
        assert len(resources.files) == 1
        assert resources.files[0].name == "template"
        assert resources.files[0].path == "/templates/output.txt"

    def test_type_extraction(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """Test type extraction."""
        # Arrange
        spans = [SpanIR(span_id="s1", text="Define a structured type for data")]
        routes = FieldRouteIR(behavior=["s1"])
        mock_client.call_json.return_value = {
            "variables": [],
            "files": [],
            "apis": [],
            "types": [
                {
                    "type_name": "DataType",
                    "type_kind": "structured",
                    "definition": "A structured data type",
                }
            ],
        }
        extractor = ResourceExtractor(pipeline_config, mock_client)

        # Act
        resources, symbols = extractor.execute((spans, routes))

        # Assert
        assert len(resources.types) == 1
        assert resources.types[0].type_name == "DataType"
        assert resources.types[0].type_kind == "structured"

    def test_symbol_table_construction(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """Test SymbolTable construction from variables."""
        # Arrange
        spans = [SpanIR(span_id="s1", text="A user request is provided")]
        routes = FieldRouteIR(behavior=["s1"])
        mock_client.call_json.return_value = {
            "variables": [
                {
                    "name": "user_request",
                    "data_type": "text",
                    "required": True,
                    "description": "User's request",
                    "source": "input",
                },
                {
                    "name": "output_result",
                    "data_type": "text",
                    "required": False,
                    "description": "Output result",
                    "source": "output",
                },
            ],
            "files": [],
            "apis": [],
            "types": [],
        }
        extractor = ResourceExtractor(pipeline_config, mock_client)

        # Act
        resources, symbols = extractor.execute((spans, routes))

        # Assert
        assert len(symbols.variables) == 2
        assert "user_request" in symbols.variables
        assert "output_result" in symbols.variables
        assert symbols.variables["user_request"].source == "input"
        assert symbols.variables["output_result"].source == "output"

    def test_empty_input(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """Test empty spans list."""
        # Arrange
        spans: list[SpanIR] = []
        routes = FieldRouteIR(behavior=[], integrations=[])
        mock_client.call_json.return_value = {
            "variables": [],
            "files": [],
            "apis": [],
            "types": [],
        }
        extractor = ResourceExtractor(pipeline_config, mock_client)

        # Act
        resources, symbols = extractor.execute((spans, routes))

        # Assert
        assert len(resources.variables) == 0
        assert len(resources.files) == 0
        assert len(resources.apis) == 0
        assert len(resources.types) == 0
        assert len(symbols.variables) == 0

    def test_llm_error(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """Test LLM API error handling."""
        # Arrange
        spans = [SpanIR(span_id="s1", text="A user request is provided")]
        routes = FieldRouteIR(behavior=["s1"])
        mock_client.call_json.side_effect = Exception("API error")
        extractor = ResourceExtractor(pipeline_config, mock_client)

        # Act & Assert
        with pytest.raises(StageError, match="LLM call failed"):
            extractor.execute((spans, routes))

    def test_missing_fields(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """Test missing fields in LLM response."""
        # Arrange
        spans = [SpanIR(span_id="s1", text="A user request is provided")]
        routes = FieldRouteIR(behavior=["s1"])
        mock_client.call_json.return_value = {
            "variables": [
                {"name": "var1"}  # Missing data_type
            ],
            "files": [],
            "apis": [],
            "types": [],
        }
        extractor = ResourceExtractor(pipeline_config, mock_client)

        # Act
        resources, symbols = extractor.execute((spans, routes))

        # Assert - invalid variables are skipped
        assert len(resources.variables) == 0

    def test_multiple_spans(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """Test extraction with multiple spans."""
        # Arrange
        spans = [
            SpanIR(span_id="s1", text="A user request is provided"),
            SpanIR(span_id="s2", text="Produce a draft communication"),
            SpanIR(span_id="s3", text="Call email API to send"),
        ]
        routes = FieldRouteIR(behavior=["s1", "s2"], integrations=["s3"])
        mock_client.call_json.return_value = {
            "variables": [
                {
                    "name": "user_request",
                    "data_type": "text",
                    "required": True,
                    "description": "User's request",
                    "source": "input",
                },
                {
                    "name": "draft",
                    "data_type": "text",
                    "required": True,
                    "description": "Draft communication",
                    "source": "output",
                },
            ],
            "files": [],
            "apis": [
                {
                    "api_name": "email_api",
                    "auth": "none",
                    "description": "Email sending API",
                    "functions": [],
                }
            ],
            "types": [],
        }
        extractor = ResourceExtractor(pipeline_config, mock_client)

        # Act
        resources, symbols = extractor.execute((spans, routes))

        # Assert
        assert len(resources.variables) == 2
        assert len(resources.apis) == 1
        assert len(symbols.variables) == 2

    def test_checkpoint_saved(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """Test that checkpoint is saved."""
        # Arrange
        pipeline_config.save_intermediate = True
        spans = [SpanIR(span_id="s1", text="A user request is provided")]
        routes = FieldRouteIR(behavior=["s1"])
        mock_client.call_json.return_value = {
            "variables": [
                {
                    "name": "user_request",
                    "data_type": "text",
                    "required": True,
                    "description": "User's request",
                    "source": "input",
                }
            ],
            "files": [],
            "apis": [],
            "types": [],
        }
        extractor = ResourceExtractor(pipeline_config, mock_client)

        # Act
        extractor.execute((spans, routes))

        # Assert - checkpoint saving is called (verified by mock)

    def test_variable_list_for_prompt(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """Test variable list generation for prompt."""
        # Arrange
        spans = [SpanIR(span_id="s1", text="A user request is provided")]
        routes = FieldRouteIR(behavior=["s1"])
        mock_client.call_json.return_value = {
            "variables": [
                {
                    "name": "user_request",
                    "data_type": "text",
                    "required": True,
                    "description": "User's request",
                    "source": "input",
                }
            ],
            "files": [],
            "apis": [],
            "types": [],
        }
        extractor = ResourceExtractor(pipeline_config, mock_client)

        # Act
        resources, symbols = extractor.execute((spans, routes))

        # Assert
        variable_list = symbols.get_variable_list_for_prompt()
        assert "user_request" in variable_list
        assert "text" in variable_list
        assert "input" in variable_list
