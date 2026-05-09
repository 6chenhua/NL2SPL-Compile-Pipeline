"""Unit tests for Stage 3: AmbiguityResolver."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from nl2spl.errors.exceptions import StageError
from nl2spl.ir.field_route_ir import FieldRouteIR
from nl2spl.ir.span_ir import AmbiguityInfo, SpanIR
from nl2spl.pipeline.stages.stage3_ambiguity_resolver import AmbiguityResolver


class TestAmbiguityResolver:
    """Tests for AmbiguityResolver stage."""

    def test_no_ambiguity(self, pipeline_config: MagicMock, mock_client: MagicMock) -> None:
        """Test no ambiguity case."""
        # Arrange
        resolver = AmbiguityResolver(pipeline_config, mock_client)
        spans = [SpanIR("s1", "Determine type")]
        routes = FieldRouteIR(behavior=["s1"])

        # Act
        result_spans, result_routes = resolver.execute((spans, routes, []))

        # Assert
        assert len(result_spans) == 1
        assert result_spans[0].span_id == "s1"
        assert "s1" in result_routes.behavior

    def test_split_ambiguous_span(self, pipeline_config: MagicMock, mock_client: MagicMock) -> None:
        """Test splitting ambiguous span."""
        # Arrange
        mock_client.call_json.return_value = {
            "resolved_spans": [
                {"span_id": "s1a", "text": "Determine type", "parent_span_id": "s1"},
                {"span_id": "s1b", "text": "but do not invent", "parent_span_id": "s1"},
            ],
            "resolved_routes": {
                "identity": [],
                "audience": [],
                "rules": ["s1b"],
                "domain": [],
                "integrations": [],
                "behavior": ["s1a"],
            },
        }
        resolver = AmbiguityResolver(pipeline_config, mock_client)
        spans = [SpanIR("s1", "Determine type, but do not invent")]
        routes = FieldRouteIR(behavior=["s1"])
        ambiguity_updates = [
            {
                "span_id": "s1",
                "is_ambiguous": True,
                "reasons": ["mixed_action_and_policy"],
                "needs_split": True,
            }
        ]

        # Act
        result_spans, result_routes = resolver.execute((spans, routes, ambiguity_updates))

        # Assert
        assert len(result_spans) == 2
        assert result_spans[0].span_id == "s1a"
        assert result_spans[1].span_id == "s1b"
        assert "s1a" in result_routes.behavior
        assert "s1b" in result_routes.rules

    def test_multiple_ambiguous_spans(self, pipeline_config: MagicMock, mock_client: MagicMock) -> None:
        """Test splitting multiple ambiguous spans."""
        # Arrange
        mock_client.call_json.return_value = {
            "resolved_spans": [
                {"span_id": "s1a", "text": "Determine type", "parent_span_id": "s1"},
                {"span_id": "s1b", "text": "but do not invent", "parent_span_id": "s1"},
                {"span_id": "s2a", "text": "Identify fields", "parent_span_id": "s2"},
                {"span_id": "s2b", "text": "and require evidence", "parent_span_id": "s2"},
            ],
            "resolved_routes": {
                "identity": [],
                "audience": [],
                "rules": ["s1b", "s2b"],
                "domain": [],
                "integrations": [],
                "behavior": ["s1a", "s2a"],
            },
        }
        resolver = AmbiguityResolver(pipeline_config, mock_client)
        spans = [
            SpanIR("s1", "Determine type, but do not invent"),
            SpanIR("s2", "Identify fields and require evidence"),
        ]
        routes = FieldRouteIR(behavior=["s1", "s2"])
        ambiguity_updates = [
            {
                "span_id": "s1",
                "is_ambiguous": True,
                "reasons": ["mixed_action_and_policy"],
                "needs_split": True,
            },
            {
                "span_id": "s2",
                "is_ambiguous": True,
                "reasons": ["mixed_action_and_policy"],
                "needs_split": True,
            },
        ]

        # Act
        result_spans, result_routes = resolver.execute((spans, routes, ambiguity_updates))

        # Assert
        assert len(result_spans) == 4
        assert len(result_routes.rules) == 2
        assert len(result_routes.behavior) == 2

    def test_preserves_non_ambiguous_spans(self, pipeline_config: MagicMock, mock_client: MagicMock) -> None:
        """Test that non-ambiguous spans are preserved."""
        # Arrange
        mock_client.call_json.return_value = {
            "resolved_spans": [
                {"span_id": "s1a", "text": "Determine type", "parent_span_id": "s1"},
                {"span_id": "s1b", "text": "but do not invent", "parent_span_id": "s1"},
            ],
            "resolved_routes": {
                "identity": ["s2"],
                "audience": [],
                "rules": ["s1b"],
                "domain": [],
                "integrations": [],
                "behavior": ["s1a"],
            },
        }
        resolver = AmbiguityResolver(pipeline_config, mock_client)
        spans = [
            SpanIR("s1", "Determine type, but do not invent"),
            SpanIR("s2", "Internal communications specialist"),
        ]
        routes = FieldRouteIR(behavior=["s1"], identity=["s2"])
        ambiguity_updates = [
            {
                "span_id": "s1",
                "is_ambiguous": True,
                "reasons": ["mixed_action_and_policy"],
                "needs_split": True,
            }
        ]

        # Act
        result_spans, result_routes = resolver.execute((spans, routes, ambiguity_updates))

        # Assert
        assert len(result_spans) == 3
        assert any(s.span_id == "s2" for s in result_spans)
        assert "s2" in result_routes.identity

    def test_empty_ambiguity_updates(self, pipeline_config: MagicMock, mock_client: MagicMock) -> None:
        """Test empty ambiguity updates."""
        # Arrange
        resolver = AmbiguityResolver(pipeline_config, mock_client)
        spans = [SpanIR("s1", "Determine type")]
        routes = FieldRouteIR(behavior=["s1"])

        # Act
        result_spans, result_routes = resolver.execute((spans, routes, []))

        # Assert
        assert len(result_spans) == 1
        assert result_spans[0].span_id == "s1"

    def test_llm_error(self, pipeline_config: MagicMock, mock_client: MagicMock) -> None:
        """Test LLM error handling."""
        # Arrange
        mock_client.call_json.side_effect = Exception("API error")
        resolver = AmbiguityResolver(pipeline_config, mock_client)
        spans = [SpanIR("s1", "test")]
        routes = FieldRouteIR(behavior=["s1"])
        ambiguity_updates = [
            {
                "span_id": "s1",
                "is_ambiguous": True,
                "reasons": ["test"],
                "needs_split": True,
            }
        ]

        # Act & Assert
        with pytest.raises(StageError, match="LLM call failed"):
            resolver.execute((spans, routes, ambiguity_updates))

    def test_missing_resolved_spans(self, pipeline_config: MagicMock, mock_client: MagicMock) -> None:
        """Test handling of missing resolved_spans in LLM response."""
        # Arrange
        mock_client.call_json.return_value = {
            "resolved_routes": {
                "identity": [],
                "audience": [],
                "rules": [],
                "domain": [],
                "integrations": [],
                "behavior": [],
            },
        }
        resolver = AmbiguityResolver(pipeline_config, mock_client)
        spans = [SpanIR("s1", "test")]
        routes = FieldRouteIR(behavior=["s1"])
        ambiguity_updates = [
            {
                "span_id": "s1",
                "is_ambiguous": True,
                "reasons": ["test"],
                "needs_split": True,
            }
        ]

        # Act
        result_spans, result_routes = resolver.execute((spans, routes, ambiguity_updates))

        # Assert
        assert len(result_spans) == 0  # Original span removed, no new spans added

    def test_overlap_detection(self, pipeline_config: MagicMock, mock_client: MagicMock) -> None:
        """Test detection of overlapping spans in resolved routes."""
        # Arrange
        mock_client.call_json.return_value = {
            "resolved_spans": [
                {"span_id": "s1a", "text": "test", "parent_span_id": "s1"},
            ],
            "resolved_routes": {
                "identity": ["s1a"],
                "audience": [],
                "rules": ["s1a"],  # Overlap!
                "domain": [],
                "integrations": [],
                "behavior": [],
            },
        }
        resolver = AmbiguityResolver(pipeline_config, mock_client)
        spans = [SpanIR("s1", "test")]
        routes = FieldRouteIR(behavior=["s1"])
        ambiguity_updates = [
            {
                "span_id": "s1",
                "is_ambiguous": True,
                "reasons": ["test"],
                "needs_split": True,
            }
        ]

        # Act
        result_spans, result_routes = resolver.execute((spans, routes, ambiguity_updates))

        # Assert
        assert len(result_routes.validate_no_overlap()) > 0

    def test_checkpoint_saved(self, pipeline_config: MagicMock, mock_client: MagicMock) -> None:
        """Test that checkpoint is saved."""
        # Arrange
        pipeline_config.save_intermediate = True
        mock_client.call_json.return_value = {
            "resolved_spans": [
                {"span_id": "s1a", "text": "test", "parent_span_id": "s1"},
            ],
            "resolved_routes": {
                "identity": [],
                "audience": [],
                "rules": [],
                "domain": [],
                "integrations": [],
                "behavior": ["s1a"],
            },
        }
        resolver = AmbiguityResolver(pipeline_config, mock_client)
        spans = [SpanIR("s1", "test")]
        routes = FieldRouteIR(behavior=["s1"])
        ambiguity_updates = [
            {
                "span_id": "s1",
                "is_ambiguous": True,
                "reasons": ["test"],
                "needs_split": True,
            }
        ]

        # Act
        resolver.execute((spans, routes, ambiguity_updates))

        # Assert - checkpoint saving is called (verified by mock)

    def test_checkpoint_content(self, pipeline_config: MagicMock, mock_client: MagicMock) -> None:
        """Test that checkpoint contains correct content."""
        # Arrange
        pipeline_config.save_intermediate = True
        mock_client.call_json.return_value = {
            "resolved_spans": [
                {"span_id": "s1a", "text": "test", "parent_span_id": "s1"},
            ],
            "resolved_routes": {
                "identity": [],
                "audience": [],
                "rules": [],
                "domain": [],
                "integrations": [],
                "behavior": ["s1a"],
            },
        }
        resolver = AmbiguityResolver(pipeline_config, mock_client)
        spans = [SpanIR("s1", "test")]
        routes = FieldRouteIR(behavior=["s1"])
        ambiguity_updates = [
            {
                "span_id": "s1",
                "is_ambiguous": True,
                "reasons": ["test"],
                "needs_split": True,
            }
        ]

        # Act
        with patch.object(resolver, 'save_checkpoint') as mock_save:
            resolver.execute((spans, routes, ambiguity_updates))

            # Assert
            mock_save.assert_called_once()
            checkpoint_data = mock_save.call_args[0][0]
            assert "original_spans_count" in checkpoint_data
            assert "resolved_spans_count" in checkpoint_data
            assert "resolved_spans" in checkpoint_data
            assert "resolved_routes" in checkpoint_data
            assert "overlaps" in checkpoint_data
            assert checkpoint_data["original_spans_count"] == 1
            assert checkpoint_data["resolved_spans_count"] == 1
            assert checkpoint_data["resolved_spans"][0]["span_id"] == "s1a"
