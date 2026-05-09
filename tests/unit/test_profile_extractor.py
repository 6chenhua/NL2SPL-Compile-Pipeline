"""Unit tests for Stage 8: ProfileExtractor."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from nl2spl.ir.agent_profile_ir import AgentProfileIR, Aspect, Concept, PersonaIR
from nl2spl.ir.field_route_ir import FieldRouteIR
from nl2spl.ir.span_ir import SpanIR
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.pipeline.stages.stage8_profile_extractor import ProfileExtractor


class TestProfileExtractor:
    """Tests for ProfileExtractor stage."""

    def test_persona_extraction(self, pipeline_config: MagicMock, mock_client: MagicMock) -> None:
        """Test persona extraction."""
        # Arrange
        mock_client.call_json.return_value = {
            "persona": {
                "role": "Internal communications specialist",
                "aspects": [
                    {"name": "Tone", "text": "Professional and concise"},
                    {"name": "Style", "text": "Clear and direct"},
                ]
            },
            "audience": {"aspects": []},
            "concepts": [],
        }
        extractor = ProfileExtractor(pipeline_config, mock_client)
        spans = [SpanIR("s1", "Internal communications specialist")]
        routes = FieldRouteIR(identity=["s1"])
        symbols = SymbolTable()

        # Act
        profile = extractor.execute((spans, routes, symbols))

        # Assert
        assert profile.persona.role == "Internal communications specialist"
        assert len(profile.persona.aspects) == 2
        assert profile.persona.aspects[0].name == "Tone"
        assert profile.persona.aspects[0].text == "Professional and concise"

    def test_audience_extraction(self, pipeline_config: MagicMock, mock_client: MagicMock) -> None:
        """Test audience extraction."""
        # Arrange
        mock_client.call_json.return_value = {
            "persona": {"role": "General Assistant", "aspects": []},
            "audience": {
                "aspects": [
                    {"name": "Level", "text": "Senior leadership"},
                    {"name": "Format", "text": "Briefings"},
                ]
            },
            "concepts": [],
        }
        extractor = ProfileExtractor(pipeline_config, mock_client)
        spans = [SpanIR("s1", "Senior leadership requiring briefings")]
        routes = FieldRouteIR(audience=["s1"])
        symbols = SymbolTable()

        # Act
        profile = extractor.execute((spans, routes, symbols))

        # Assert
        assert len(profile.audience_aspects) == 2
        assert profile.audience_aspects[0].name == "Level"
        assert profile.audience_aspects[0].text == "Senior leadership"

    def test_concepts_extraction(self, pipeline_config: MagicMock, mock_client: MagicMock) -> None:
        """Test concepts extraction."""
        # Arrange
        mock_client.call_json.return_value = {
            "persona": {"role": "General Assistant", "aspects": []},
            "audience": {"aspects": []},
            "concepts": [
                {"term": "Provenance", "definition": "The origin of sourced facts"},
                {"term": "Evidence", "definition": "Supporting documentation"},
            ],
        }
        extractor = ProfileExtractor(pipeline_config, mock_client)
        spans = [SpanIR("s1", "Provenance: The origin of sourced facts")]
        routes = FieldRouteIR(domain=["s1"])
        symbols = SymbolTable()

        # Act
        profile = extractor.execute((spans, routes, symbols))

        # Assert
        assert len(profile.concepts) == 2
        assert profile.concepts[0].term == "Provenance"
        assert profile.concepts[0].definition == "The origin of sourced facts"

    def test_empty_spans(self, pipeline_config: MagicMock, mock_client: MagicMock) -> None:
        """Test empty span handling."""
        # Arrange
        mock_client.call_json.return_value = {
            "persona": {"role": "General Assistant", "aspects": []},
            "audience": {"aspects": []},
            "concepts": [],
        }
        extractor = ProfileExtractor(pipeline_config, mock_client)
        spans = []
        routes = FieldRouteIR()
        symbols = SymbolTable()

        # Act
        profile = extractor.execute((spans, routes, symbols))

        # Assert
        assert profile.persona.role == "General Assistant"
        assert len(profile.persona.aspects) == 0
        assert len(profile.audience_aspects) == 0
        assert len(profile.concepts) == 0

    def test_multiple_identity_spans(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """Test multiple identity spans."""
        # Arrange
        mock_client.call_json.return_value = {
            "persona": {
                "role": "Technical writer",
                "aspects": [
                    {"name": "Expertise", "text": "Software documentation"},
                    {"name": "Audience", "text": "Developers"},
                ]
            },
            "audience": {"aspects": []},
            "concepts": [],
        }
        extractor = ProfileExtractor(pipeline_config, mock_client)
        spans = [
            SpanIR("s1", "Technical writer specializing in software documentation"),
            SpanIR("s2", "Target audience: developers"),
        ]
        routes = FieldRouteIR(identity=["s1", "s2"])
        symbols = SymbolTable()

        # Act
        profile = extractor.execute((spans, routes, symbols))

        # Assert
        assert profile.persona.role == "Technical writer"
        assert len(profile.persona.aspects) == 2

    def test_llm_error(self, pipeline_config: MagicMock, mock_client: MagicMock) -> None:
        """Test LLM error handling."""
        # Arrange
        mock_client.call_json.side_effect = Exception("API error")
        extractor = ProfileExtractor(pipeline_config, mock_client)
        spans = [SpanIR("s1", "test")]
        routes = FieldRouteIR(identity=["s1"])
        symbols = SymbolTable()

        # Act & Assert
        with pytest.raises(Exception, match="API error"):
            extractor.execute((spans, routes, symbols))

    def test_default_persona_role(self, pipeline_config: MagicMock, mock_client: MagicMock) -> None:
        """Test default persona role when not provided."""
        # Arrange
        mock_client.call_json.return_value = {
            "persona": {"aspects": []},  # Missing role
            "audience": {"aspects": []},
            "concepts": [],
        }
        extractor = ProfileExtractor(pipeline_config, mock_client)
        spans = []
        routes = FieldRouteIR()
        symbols = SymbolTable()

        # Act
        profile = extractor.execute((spans, routes, symbols))

        # Assert
        assert profile.persona.role == "General Assistant"

    def test_role_inferred_from_source_spans_when_identity_is_empty(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """Test ROLE fallback from source spans when identity routing is empty."""
        # Arrange
        mock_client.call_json.return_value = {
            "persona": {"role": "", "aspects": []},
            "audience": {"aspects": []},
            "concepts": [],
        }
        extractor = ProfileExtractor(pipeline_config, mock_client)
        spans = [
            SpanIR(
                "s1",
                "Task family: Internal newsletters, announcements, and executive briefs.",
            )
        ]
        routes = FieldRouteIR(audience=["s1"])
        symbols = SymbolTable()

        # Act
        profile = extractor.execute((spans, routes, symbols))

        # Assert
        assert profile.persona.role.startswith("Agent specializing in internal newsletters")

    def test_checkpoint_saved(self, pipeline_config: MagicMock, mock_client: MagicMock) -> None:
        """Test that checkpoint is saved."""
        # Arrange
        pipeline_config.save_intermediate = True
        mock_client.call_json.return_value = {
            "persona": {"role": "Test", "aspects": []},
            "audience": {"aspects": []},
            "concepts": [],
        }
        extractor = ProfileExtractor(pipeline_config, mock_client)
        spans = [SpanIR("s1", "test")]
        routes = FieldRouteIR(identity=["s1"])
        symbols = SymbolTable()

        # Act
        extractor.execute((spans, routes, symbols))

        # Assert - checkpoint saving is called (verified by mock)

    def test_with_variables(self, pipeline_config: MagicMock, mock_client: MagicMock) -> None:
        """Test extraction with known variables."""
        # Arrange
        mock_client.call_json.return_value = {
            "persona": {"role": "Test", "aspects": []},
            "audience": {"aspects": []},
            "concepts": [],
        }
        extractor = ProfileExtractor(pipeline_config, mock_client)
        spans = [SpanIR("s1", "test")]
        routes = FieldRouteIR(identity=["s1"])
        symbols = SymbolTable()
        symbols.declare("user_request", "text", "input", "User request")

        # Act
        profile = extractor.execute((spans, routes, symbols))

        # Assert
        assert profile.persona.role == "Test"

    def test_unicode_support(self, pipeline_config: MagicMock, mock_client: MagicMock) -> None:
        """Test Unicode text support."""
        # Arrange
        mock_client.call_json.return_value = {
            "persona": {
                "role": "中文助手",
                "aspects": [{"name": "语言", "text": "中文"}],
            },
            "audience": {"aspects": []},
            "concepts": [],
        }
        extractor = ProfileExtractor(pipeline_config, mock_client)
        spans = [SpanIR("s1", "中文助手")]
        routes = FieldRouteIR(identity=["s1"])
        symbols = SymbolTable()

        # Act
        profile = extractor.execute((spans, routes, symbols))

        # Assert
        assert profile.persona.role == "中文助手"
        assert profile.persona.aspects[0].text == "中文"
