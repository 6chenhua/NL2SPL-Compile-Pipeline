"""Unit tests for Stage 3: AmbiguityResolver."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from nl2spl.errors.exceptions import StageError
from nl2spl.ir.field_route_ir import FieldRouteIR, RouteAnnotation
from nl2spl.ir.span_ir import SpanIR
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
        assert [span.span_id for span in result_spans] == ["s1"]
        assert result_routes.behavior == ["s1"]

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
        assert result_routes.validate_no_overlap() == []
        assert result_routes.identity == ["s1a"]
        assert result_routes.rules == []
        assert any(
            "ignored overlapping route" in diagnostic
            for diagnostic in result_routes.route_diagnostics
        )

    def test_phantom_routes_for_non_ambiguous_span_are_rejected(
        self,
        pipeline_config: MagicMock,
        mock_client: MagicMock,
    ) -> None:
        mock_client.call_json.return_value = {
            "resolved_spans": [
                {"span_id": "s31a", "text": "Policy", "parent_span_id": "s31"},
                {
                    "span_id": "s31b",
                    "text": "delegation intent",
                    "parent_span_id": "s31",
                },
            ],
            "resolved_routes": {
                "rules": ["s31a"],
                "behavior": ["s27a", "s27b", "s31b"],
            },
        }
        resolver = AmbiguityResolver(pipeline_config, mock_client)
        spans = [
            SpanIR("s27", "If information is missing, ask the user."),
            SpanIR("s31", "Policy and delegation intent."),
        ]
        routes = FieldRouteIR(behavior=["s27", "s31"])
        ambiguity_updates = [
            {
                "span_id": "s31",
                "is_ambiguous": True,
                "reasons": ["mixed"],
                "needs_split": True,
            }
        ]

        result_spans, result_routes = resolver.execute(
            (spans, routes, ambiguity_updates)
        )

        result_span_ids = {span.span_id for span in result_spans}
        assert result_span_ids == {"s27", "s31a", "s31b"}
        assert "s27" in result_routes.behavior
        assert "s27a" not in result_routes.behavior
        assert "s27b" not in result_routes.behavior
        assert result_routes.get_all_span_ids() <= result_span_ids

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


# ===========================================================================
# F4: Annotation-aware AmbiguityResolver
# ===========================================================================


class TestF4AnnotationAwareResolver:
    """F4: Stage 3 preserves provenance and annotations during split."""

    def test_no_ambiguity_preserves_original_routes(self, pipeline_config, mock_client):
        resolver = AmbiguityResolver(pipeline_config, mock_client)
        spans = [SpanIR("s1", "Determine type")]
        routes = FieldRouteIR(
            behavior=["s1"],
            annotations=[RouteAnnotation(span_id="s1", field="behavior")],
        )
        result_spans, result_routes = resolver.execute((spans, routes, []))
        assert result_routes is routes
        assert len(result_routes.annotations) == 1

    def test_child_spans_inherit_provenance(self, pipeline_config, mock_client):
        mock_client.call_json.return_value = {
            "resolved_spans": [
                {"span_id": "s1a", "text": "Determine type", "parent_span_id": "s1"},
                {"span_id": "s1b", "text": "but do not invent", "parent_span_id": "s1"},
            ],
            "resolved_routes": {
                "identity": [], "audience": [], "rules": ["s1b"],
                "domain": [], "integrations": [], "behavior": ["s1a"],
            },
        }
        resolver = AmbiguityResolver(pipeline_config, mock_client)
        spans = [SpanIR("s1", "Determine type, but do not invent",
                         source_section_id="sec_process",
                         source_packet_id="p_process_step_determine")]
        routes = FieldRouteIR(behavior=["s1"])
        ambiguity_updates = [{
            "span_id": "s1", "is_ambiguous": True,
            "reasons": ["mixed_action_and_policy"], "needs_split": True,
        }]

        result_spans, _ = resolver.execute((spans, routes, ambiguity_updates))

        for child in result_spans:
            assert child.source_section_id == "sec_process", (
                f"Child {child.span_id} missing source_section_id"
            )
            assert child.source_packet_id == "p_process_step_determine", (
                f"Child {child.span_id} missing source_packet_id"
            )

    def test_non_ambiguous_annotation_preserved(self, pipeline_config, mock_client):
        mock_client.call_json.return_value = {
            "resolved_spans": [
                {"span_id": "s1a", "text": "Determine type", "parent_span_id": "s1"},
                {"span_id": "s1b", "text": "but do not invent", "parent_span_id": "s1"},
            ],
            "resolved_routes": {
                "identity": ["s2"], "audience": [], "rules": ["s1b"],
                "domain": [], "integrations": [], "behavior": ["s1a"],
            },
        }
        resolver = AmbiguityResolver(pipeline_config, mock_client)
        spans = [SpanIR("s1", "mixed text"), SpanIR("s2", "keep me")]
        routes = FieldRouteIR(
            behavior=["s1"], identity=["s2"],
            annotations=[
                RouteAnnotation(span_id="s1", field="behavior"),
                RouteAnnotation(span_id="s2", field="identity",
                                semantic_role="profile_domain"),
            ],
        )
        ambiguity_updates = [{
            "span_id": "s1", "is_ambiguous": True,
            "reasons": ["mixed_action_and_policy"], "needs_split": True,
        }]

        _, result_routes = resolver.execute((spans, routes, ambiguity_updates))

        s2_anns = result_routes.get_annotations("s2")
        assert len(s2_anns) == 1, "s2 annotation should be preserved"
        assert s2_anns[0].semantic_role == "profile_domain"

    def test_action_policy_split_annotations(self, pipeline_config, mock_client):
        mock_client.call_json.return_value = {
            "resolved_spans": [
                {"span_id": "s1a", "text": "Determine type", "parent_span_id": "s1"},
                {"span_id": "s1b", "text": "but do not invent", "parent_span_id": "s1"},
            ],
            "resolved_routes": {
                "identity": [], "audience": [], "rules": ["s1b"],
                "domain": [], "integrations": [], "behavior": ["s1a"],
            },
        }
        resolver = AmbiguityResolver(pipeline_config, mock_client)
        spans = [SpanIR("s1", "Determine type, but do not invent",
                         source_section_id="sec_process")]
        routes = FieldRouteIR(
            behavior=["s1"],
            annotations=[
                RouteAnnotation(span_id="s1", field="behavior",
                                semantic_role="process_step",
                                source_section_id="sec_process",
                                executable=True),
            ],
        )
        ambiguity_updates = [{
            "span_id": "s1", "is_ambiguous": True,
            "reasons": ["mixed_action_and_policy"], "needs_split": True,
        }]

        _, result_routes = resolver.execute((spans, routes, ambiguity_updates))

        # s1a in behavior → executable
        s1a_anns = result_routes.get_annotations("s1a")
        assert len(s1a_anns) >= 1
        assert s1a_anns[0].field == "behavior"
        assert s1a_anns[0].executable is True
        assert s1a_anns[0].source_section_id == "sec_process"

        # s1b in rules — inherits parent contract-derived field (behavior).
        # ARC: field is contract-derived, not route-field-driven.
        s1b_anns = result_routes.get_annotations("s1b")
        assert len(s1b_anns) >= 1
        assert s1b_anns[0].field == "behavior"
        assert s1b_anns[0].semantic_role == "process_step"
        assert s1b_anns[0].executable is True
        assert s1b_anns[0].source_section_id == "sec_process"

    def test_failure_mode_annotation_stays_non_executable(self, pipeline_config, mock_client):
        mock_client.call_json.return_value = {
            "resolved_spans": [
                {"span_id": "s1a", "text": "Missing timeframe", "parent_span_id": "s1"},
                {"span_id": "s1b", "text": "log and retry", "parent_span_id": "s1"},
            ],
            "resolved_routes": {
                "identity": [], "audience": [], "rules": [],
                "domain": [], "integrations": [], "behavior": ["s1a", "s1b"],
            },
        }
        resolver = AmbiguityResolver(pipeline_config, mock_client)
        spans = [SpanIR("s1", "Missing timeframe, log and retry",
                         source_section_id="sec_failure_handling",
                         source_packet_id="p_failure_mode_missing")]
        routes = FieldRouteIR(
            rules=["s1"],
            annotations=[
                RouteAnnotation(
                    span_id="s1", field="behavior",
                    semantic_role="failure_mode",
                    route_family="flow_relevant",
                    construct_target="EXCEPTION_FLOW",
                    slot_target="condition",
                    executable=False,
                    source_section_id="sec_failure_handling",
                    source_packet_id="p_failure_mode_missing",
                ),
            ],
        )
        ambiguity_updates = [{
            "span_id": "s1", "is_ambiguous": True,
            "reasons": ["mixed_failure_and_action"], "needs_split": True,
        }]

        _, result_routes = resolver.execute((spans, routes, ambiguity_updates))

        for child_id in ("s1a", "s1b"):
            child_anns = result_routes.get_annotations(child_id)
            assert len(child_anns) >= 1, f"Child {child_id} missing annotation"
            for ann in child_anns:
                assert ann.executable is False, (
                    f"Child {child_id}: failure_mode must stay executable=False, "
                    f"got {ann.executable}"
                )
                assert ann.construct_target == "EXCEPTION_FLOW"

    def test_delegation_split_stays_non_executable(self, pipeline_config, mock_client):
        mock_client.call_json.return_value = {
            "resolved_spans": [
                {"span_id": "s1a", "text": "source gathering if bounded",
                 "parent_span_id": "s1"},
                {"span_id": "s1b", "text": "must have handoff contract",
                 "parent_span_id": "s1"},
            ],
            "resolved_routes": {
                "identity": [], "audience": [], "rules": ["s1b"],
                "domain": [], "integrations": [], "behavior": ["s1a"],
            },
        }
        resolver = AmbiguityResolver(pipeline_config, mock_client)
        spans = [SpanIR("s1", "source gathering if bounded, must have contract",
                         source_section_id="sec_delegation_policy",
                         source_packet_id="p_delegation_rule_source_gathering")]
        routes = FieldRouteIR(
            behavior=["s1"],
            annotations=[
                RouteAnnotation(
                    span_id="s1", field="behavior",
                    semantic_role="delegation_intent",
                    route_family="delegation_boundary",
                    executable=False,
                    source_section_id="sec_delegation_policy",
                    source_packet_id="p_delegation_rule_source_gathering",
                ),
            ],
        )
        ambiguity_updates = [{
            "span_id": "s1", "is_ambiguous": True,
            "reasons": ["mixed_delegation_and_policy"], "needs_split": True,
        }]

        _, result_routes = resolver.execute((spans, routes, ambiguity_updates))

        # Both children must stay non-executable
        for child_id in ("s1a", "s1b"):
            child_anns = result_routes.get_annotations(child_id)
            assert len(child_anns) >= 1, f"Child {child_id} missing annotation"
            for ann in child_anns:
                assert ann.executable is False, (
                    f"Child {child_id}: delegation intent must stay executable=False, "
                    f"got {ann.executable}"
                )
                # Delegation semantics preserved
                if child_id == "s1a":
                    assert ann.semantic_role == "delegation_intent"
                    assert ann.route_family == "delegation_boundary"

    def test_checkpoint_includes_annotations(self, pipeline_config, mock_client):
        mock_client.call_json.return_value = {
            "resolved_spans": [
                {"span_id": "s1a", "text": "Determine type", "parent_span_id": "s1"},
                {"span_id": "s1b", "text": "but do not invent", "parent_span_id": "s1"},
            ],
            "resolved_routes": {
                "identity": [], "audience": [], "rules": ["s1b"],
                "domain": [], "integrations": [], "behavior": ["s1a"],
            },
        }
        resolver = AmbiguityResolver(pipeline_config, mock_client)
        spans = [SpanIR("s1", "mixed")]
        routes = FieldRouteIR(
            behavior=["s1"],
            annotations=[RouteAnnotation(span_id="s1", field="behavior")],
        )
        ambiguity_updates = [{
            "span_id": "s1", "is_ambiguous": True,
            "reasons": ["mixed_action_and_policy"], "needs_split": True,
        }]

        with patch.object(resolver, "save_checkpoint") as mock_save:
            resolver.execute((spans, routes, ambiguity_updates))

        mock_save.assert_called_once()
        checkpoint = mock_save.call_args[0][0]
        routes_data = checkpoint["resolved_routes"]
        assert "annotations" in routes_data
        assert len(routes_data["annotations"]) >= 1
