"""Unit tests for Stage 2: FieldRouter."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from nl2spl.errors.exceptions import StageError
from nl2spl.ir.field_route_ir import FieldRouteIR
from nl2spl.ir.span_ir import AmbiguityInfo, SpanIR
from nl2spl.pipeline.stages.stage2_field_router import FieldRouter


class TestFieldRouter:
    """Tests for FieldRouter stage."""

    def test_identity_routing(self, pipeline_config: MagicMock, mock_client: MagicMock) -> None:
        """Test identity field routing."""
        # Arrange
        mock_client.call_json.return_value = {
            "routes": {
                "identity": ["s1"],
                "audience": [],
                "rules": [],
                "domain": [],
                "integrations": [],
                "behavior": [],
            },
            "ambiguity_updates": [],
        }
        router = FieldRouter(pipeline_config, mock_client)
        spans = [SpanIR("s1", "Internal communications specialist")]

        # Act
        routes, ambiguity_updates = router.execute(spans)

        # Assert
        assert "s1" in routes.identity
        assert len(ambiguity_updates) == 0

    def test_behavior_routing(self, pipeline_config: MagicMock, mock_client: MagicMock) -> None:
        """Test behavior field routing."""
        # Arrange
        mock_client.call_json.return_value = {
            "routes": {
                "identity": [],
                "audience": [],
                "rules": [],
                "domain": [],
                "integrations": [],
                "behavior": ["s1"],
            },
            "ambiguity_updates": [],
        }
        router = FieldRouter(pipeline_config, mock_client)
        spans = [SpanIR("s1", "Determine communication type")]

        # Act
        routes, ambiguity_updates = router.execute(spans)

        # Assert
        assert "s1" in routes.behavior

    def test_rules_routing(self, pipeline_config: MagicMock, mock_client: MagicMock) -> None:
        """Test rules field routing."""
        # Arrange
        mock_client.call_json.return_value = {
            "routes": {
                "identity": [],
                "audience": [],
                "rules": ["s1"],
                "domain": [],
                "integrations": [],
                "behavior": [],
            },
            "ambiguity_updates": [],
        }
        router = FieldRouter(pipeline_config, mock_client)
        spans = [SpanIR("s1", "Do not invent facts")]

        # Act
        routes, ambiguity_updates = router.execute(spans)

        # Assert
        assert "s1" in routes.rules

    def test_no_overlap(self, pipeline_config: MagicMock, mock_client: MagicMock) -> None:
        """Test that no span appears in multiple fields."""
        # Arrange
        mock_client.call_json.return_value = {
            "routes": {
                "identity": ["s1"],
                "audience": [],
                "rules": ["s2"],
                "domain": [],
                "integrations": [],
                "behavior": [],
            },
            "ambiguity_updates": [],
        }
        router = FieldRouter(pipeline_config, mock_client)
        spans = [
            SpanIR("s1", "Specialist role"),
            SpanIR("s2", "Do not invent"),
        ]

        # Act
        routes, _ = router.execute(spans)

        # Assert
        assert len(routes.validate_no_overlap()) == 0

    def test_ambiguity_detection(self, pipeline_config: MagicMock, mock_client: MagicMock) -> None:
        """Test detection of ambiguous spans."""
        # Arrange
        mock_client.call_json.return_value = {
            "routes": {
                "identity": [],
                "audience": [],
                "rules": [],
                "domain": [],
                "integrations": [],
                "behavior": ["s1"],
            },
            "ambiguity_updates": [
                {
                    "span_id": "s1",
                    "is_ambiguous": True,
                    "reasons": ["mixed_action_and_policy"],
                    "needs_split": True,
                }
            ],
        }
        router = FieldRouter(pipeline_config, mock_client)
        spans = [SpanIR("s1", "Determine type, but do not invent")]

        # Act
        routes, ambiguity_updates = router.execute(spans)

        # Assert
        assert len(ambiguity_updates) == 1
        assert ambiguity_updates[0]["span_id"] == "s1"
        assert spans[0].ambiguity.is_ambiguous is True
        assert spans[0].ambiguity.needs_split is True

    def test_multiple_fields(self, pipeline_config: MagicMock, mock_client: MagicMock) -> None:
        """Test routing to multiple fields."""
        # Arrange
        mock_client.call_json.return_value = {
            "routes": {
                "identity": ["s1"],
                "audience": [],
                "rules": ["s2"],
                "domain": [],
                "integrations": ["s3"],
                "behavior": ["s4", "s5"],
            },
            "ambiguity_updates": [],
        }
        router = FieldRouter(pipeline_config, mock_client)
        spans = [
            SpanIR("s1", "Specialist role"),
            SpanIR("s2", "Do not invent"),
            SpanIR("s3", "Use email API"),
            SpanIR("s4", "Determine type"),
            SpanIR("s5", "Identify fields"),
        ]

        # Act
        routes, _ = router.execute(spans)

        # Assert
        assert len(routes.identity) == 1
        assert len(routes.rules) == 1
        assert len(routes.integrations) == 1
        assert len(routes.behavior) == 2

    def test_empty_spans(self, pipeline_config: MagicMock, mock_client: MagicMock) -> None:
        """Test routing with empty spans list."""
        # Arrange
        mock_client.call_json.return_value = {
            "routes": {
                "identity": [],
                "audience": [],
                "rules": [],
                "domain": [],
                "integrations": [],
                "behavior": [],
            },
            "ambiguity_updates": [],
        }
        router = FieldRouter(pipeline_config, mock_client)

        # Act
        routes, ambiguity_updates = router.execute([])

        # Assert
        assert len(routes.get_all_span_ids()) == 0
        assert len(ambiguity_updates) == 0

    def test_llm_error(self, pipeline_config: MagicMock, mock_client: MagicMock) -> None:
        """Test LLM error handling."""
        # Arrange
        mock_client.call_json.side_effect = Exception("API error")
        router = FieldRouter(pipeline_config, mock_client)
        spans = [SpanIR("s1", "test")]

        # Act & Assert
        with pytest.raises(StageError, match="LLM call failed"):
            router.execute(spans)

    def test_missing_routes_field(self, pipeline_config: MagicMock, mock_client: MagicMock) -> None:
        """Test handling of missing routes field in LLM response."""
        # Arrange
        mock_client.call_json.return_value = {
            "ambiguity_updates": [],
        }
        router = FieldRouter(pipeline_config, mock_client)
        spans = [SpanIR("s1", "test")]

        # Act
        routes, _ = router.execute(spans)

        # Assert
        assert len(routes.get_all_span_ids()) == 0

    def test_span_not_in_any_field(self, pipeline_config: MagicMock, mock_client: MagicMock) -> None:
        """Test span that is not routed to any field."""
        # Arrange
        mock_client.call_json.return_value = {
            "routes": {
                "identity": [],
                "audience": [],
                "rules": [],
                "domain": [],
                "integrations": [],
                "behavior": [],
            },
            "ambiguity_updates": [],
        }
        router = FieldRouter(pipeline_config, mock_client)
        spans = [SpanIR("s1", "test")]

        # Act
        routes, _ = router.execute(spans)

        # Assert
        assert routes.get_field_for_span("s1") is None

    def test_get_field_for_span(self, pipeline_config: MagicMock, mock_client: MagicMock) -> None:
        """Test get_field_for_span method."""
        # Arrange
        mock_client.call_json.return_value = {
            "routes": {
                "identity": ["s1"],
                "audience": [],
                "rules": ["s2"],
                "domain": [],
                "integrations": [],
                "behavior": [],
            },
            "ambiguity_updates": [],
        }
        router = FieldRouter(pipeline_config, mock_client)
        spans = [
            SpanIR("s1", "Specialist role"),
            SpanIR("s2", "Do not invent"),
        ]

        # Act
        routes, _ = router.execute(spans)

        # Assert
        assert routes.get_field_for_span("s1") == "identity"
        assert routes.get_field_for_span("s2") == "rules"

    def test_checkpoint_content(self, pipeline_config: MagicMock, mock_client: MagicMock) -> None:
        """Test that checkpoint contains correct content."""
        # Arrange
        pipeline_config.save_intermediate = True
        mock_client.call_json.return_value = {
            "routes": {
                "identity": ["s1"],
                "audience": [],
                "rules": ["s2"],
                "domain": [],
                "integrations": [],
                "behavior": [],
            },
            "ambiguity_updates": [],
        }
        router = FieldRouter(pipeline_config, mock_client)
        spans = [
            SpanIR("s1", "Specialist role"),
            SpanIR("s2", "Do not invent"),
        ]

        # Act
        with patch.object(router, 'save_checkpoint') as mock_save:
            router.execute(spans)

            # Assert
            mock_save.assert_called_once()
            checkpoint_data = mock_save.call_args[0][0]
            assert "routes" in checkpoint_data
            assert "ambiguity_updates" in checkpoint_data
            assert "overlaps" in checkpoint_data
            assert checkpoint_data["routes"]["identity"] == ["s1"]
            assert checkpoint_data["routes"]["rules"] == ["s2"]
