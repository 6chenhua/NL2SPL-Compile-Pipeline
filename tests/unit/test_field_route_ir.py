"""Unit tests for RouteAnnotation and FieldRouteIR helpers (F2)."""

from __future__ import annotations

from nl2spl.ir.field_route_ir import FieldRouteIR, RouteAnnotation


class TestBackwardCompatibility:
    """F2: old FieldRouteIR patterns remain compatible."""

    def test_old_construction_still_works(self) -> None:
        routes = FieldRouteIR(behavior=["s1"])
        assert routes.behavior == ["s1"]
        assert routes.annotations == []

    def test_executable_fallback_to_behavior_list(self) -> None:
        routes = FieldRouteIR(behavior=["s1", "s2"])
        assert routes.get_executable_behavior_span_ids() == ["s1", "s2"]

    def test_non_executable_returns_empty_without_annotations(self) -> None:
        routes = FieldRouteIR(behavior=["s1"])
        assert routes.get_non_executable_behavior_span_ids() == []

    def test_primary_field_falls_back_to_get_field_for_span(self) -> None:
        routes = FieldRouteIR(behavior=["s1"], rules=["s2"])
        assert routes.get_primary_field("s1") == "behavior"
        assert routes.get_primary_field("s2") == "rules"
        assert routes.get_primary_field("s_nonexistent") is None


class TestAnnotationLookup:
    """F2: annotation query helpers."""

    @staticmethod
    def _sample_routes() -> FieldRouteIR:
        return FieldRouteIR(
            behavior=["s1", "s2"],
            annotations=[
                RouteAnnotation(
                    span_id="s1",
                    field="behavior",
                    semantic_role="failure_mode",
                    route_family="flow_relevant",
                    construct_target="EXCEPTION_FLOW",
                    slot_target="condition",
                    executable=False,
                ),
                RouteAnnotation(
                    span_id="s2",
                    field="behavior",
                    semantic_role="action",
                    route_family="flow_relevant",
                    executable=True,
                ),
            ],
        )

    def test_get_annotations_returns_matches(self) -> None:
        routes = self._sample_routes()
        anns = routes.get_annotations("s1")
        assert len(anns) == 1
        assert anns[0].semantic_role == "failure_mode"

    def test_get_annotations_empty_for_unknown(self) -> None:
        routes = self._sample_routes()
        assert routes.get_annotations("s_nonexistent") == []

    def test_get_annotations_by_role(self) -> None:
        routes = self._sample_routes()
        failure = routes.get_annotations_by_role("failure_mode")
        assert len(failure) == 1
        assert failure[0].span_id == "s1"

    def test_get_construct_slot_candidates(self) -> None:
        routes = self._sample_routes()
        candidates = routes.get_construct_slot_candidates("EXCEPTION_FLOW", "condition")
        assert len(candidates) == 1
        assert candidates[0].span_id == "s1"

    def test_construct_slot_candidates_empty_for_wrong_target(self) -> None:
        routes = self._sample_routes()
        assert routes.get_construct_slot_candidates("MAIN_FLOW", "condition") == []


class TestExecutableBehaviorFiltering:
    """F2: executable / non-executable span filtering."""

    @staticmethod
    def _sample_routes() -> FieldRouteIR:
        return FieldRouteIR(
            behavior=["s1", "s2"],
            annotations=[
                RouteAnnotation(
                    span_id="s1",
                    field="behavior",
                    semantic_role="failure_mode",
                    executable=False,
                ),
                RouteAnnotation(
                    span_id="s2",
                    field="behavior",
                    semantic_role="action",
                    executable=True,
                ),
            ],
        )

    def test_executable_returns_only_executable_spans(self) -> None:
        routes = self._sample_routes()
        assert routes.get_executable_behavior_span_ids() == ["s2"]

    def test_non_executable_returns_only_failure_spans(self) -> None:
        routes = self._sample_routes()
        assert routes.get_non_executable_behavior_span_ids() == ["s1"]


class TestPrimaryFieldFallback:
    """F2: primary annotation wins, old list fallback otherwise."""

    @staticmethod
    def _sample_routes() -> FieldRouteIR:
        return FieldRouteIR(
            behavior=["s1"],
            annotations=[
                RouteAnnotation(
                    span_id="s1",
                    field="behavior",
                    semantic_role="action",
                    primary=True,
                ),
            ],
        )

    def test_primary_annotation_wins_when_present(self) -> None:
        routes = self._sample_routes()
        assert routes.get_primary_field("s1") == "behavior"

    def test_old_list_fallback_without_annotations(self) -> None:
        routes = FieldRouteIR(rules=["s2"])
        assert routes.get_primary_field("s2") == "rules"


class TestMultiLabelNotOverlap:
    """F2: annotation multi-label does not count as old-list overlap."""

    @staticmethod
    def _sample_routes() -> FieldRouteIR:
        return FieldRouteIR(
            behavior=["s1"],
            annotations=[
                RouteAnnotation(
                    span_id="s1",
                    field="behavior",
                    semantic_role="failure_mode",
                    executable=False,
                ),
                RouteAnnotation(
                    span_id="s1",
                    field="behavior",
                    semantic_role="action",
                    executable=True,
                ),
            ],
        )

    def test_both_annotations_returned(self) -> None:
        routes = self._sample_routes()
        anns = routes.get_annotations("s1")
        assert len(anns) == 2
        roles = {a.semantic_role for a in anns}
        assert roles == {"failure_mode", "action"}

    def test_validate_no_overlap_does_not_report_multi_label(self) -> None:
        routes = self._sample_routes()
        overlaps = routes.validate_no_overlap()
        assert overlaps == [], (
            f"Multi-label annotations should not trigger old-list overlap: {overlaps}"
        )

    def test_validate_no_overlap_still_catches_old_list_overlap(self) -> None:
        routes = FieldRouteIR(behavior=["s1"], rules=["s1"])
        overlaps = routes.validate_no_overlap()
        assert overlaps == ["s1"]


class TestBehaviorSpanOrdering:
    """F2: executable/non-executable helpers preserve behavior list order."""

    @staticmethod
    def _sample_routes() -> FieldRouteIR:
        return FieldRouteIR(
            behavior=["s2", "s10", "s1"],
            annotations=[
                RouteAnnotation(
                    span_id="s2", field="behavior", executable=True,
                ),
                RouteAnnotation(
                    span_id="s10", field="behavior", executable=False,
                    semantic_role="failure_mode",
                ),
                RouteAnnotation(
                    span_id="s1", field="behavior", executable=True,
                ),
            ],
        )

    def test_executable_preserves_behavior_list_order(self) -> None:
        routes = self._sample_routes()
        executable = routes.get_executable_behavior_span_ids()
        assert executable == ["s2", "s1"], (
            f"Expected ['s2', 's1'] preserving behavior order, got {executable}"
        )

    def test_non_executable_preserves_behavior_list_order(self) -> None:
        routes = self._sample_routes()
        non_exec = routes.get_non_executable_behavior_span_ids()
        assert non_exec == ["s10"], (
            f"Expected ['s10'] preserving behavior order, got {non_exec}"
        )

    def test_annotation_only_span_appended_in_annotation_order(self) -> None:
        routes = FieldRouteIR(
            behavior=["s1"],
            annotations=[
                RouteAnnotation(
                    span_id="s1", field="behavior", executable=True,
                ),
                RouteAnnotation(
                    span_id="s_extra", field="behavior", executable=True,
                ),
                RouteAnnotation(
                    span_id="s_later", field="behavior", executable=True,
                ),
            ],
        )
        executable = routes.get_executable_behavior_span_ids()
        assert executable == ["s1", "s_extra", "s_later"], (
            f"Expected annotation-only spans appended in order, got {executable}"
        )
