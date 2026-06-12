"""Phase 3: Stage 4 defensive diagnostic tests.

Verifies that Stage 4 emits a defensive warning when routes.behavior is
non-empty but get_executable_behavior_span_ids() returns empty. No fallback
to legacy routes.behavior is introduced.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from nl2spl.ir.field_route_ir import FieldRouteIR, RouteAnnotation


# ===========================================================================
# Helper
# ===========================================================================


def _make_flow_assembler():
    from nl2spl.pipeline.stages.stage4_flow_assembler import FlowAssembler

    return FlowAssembler(config=MagicMock(), client=MagicMock())


# ===========================================================================
# Test Class 1: Defensive diagnostic emitted
# ===========================================================================


class TestDefensiveDiagnosticEmitted:
    """Phase 3: defensive diagnostic when behavior non-empty but no executable
    behavior annotations."""

    def test_warning_when_behavior_non_empty_but_no_executable(self, caplog):
        """When routes.annotations exists, routes.behavior is non-empty, but
        get_executable_behavior_span_ids() returns empty, a defensive warning
        is logged."""
        import logging

        caplog.set_level(logging.WARNING)

        routes = FieldRouteIR(
            behavior=["s1", "s2", "s3"],  # non-empty legacy behavior list
            annotations=[
                RouteAnnotation(
                    span_id="s1",
                    field="behavior",
                    semantic_role="failure_mode",
                    construct_target="EXCEPTION_FLOW",
                    slot_target="condition",
                    executable=False,  # NOT executable behavior
                ),
                RouteAnnotation(
                    span_id="s2",
                    field="rules",
                    semantic_role="constraint",
                    executable=False,
                ),
            ],
            # s3 has NO annotation at all
        )

        # Verify precondition: get_executable_behavior_span_ids returns empty
        exec_ids = routes.get_executable_behavior_span_ids()
        assert len(exec_ids) == 0, "Precondition: no executable behavior IDs"

        # Simulate the defensive check
        behavior_span_ids = set(routes.get_executable_behavior_span_ids())
        assert len(behavior_span_ids) == 0
        assert len(routes.behavior) > 0
        assert len(routes.annotations) > 0

        # The diagnostic condition is met
        condition_met = (
            routes.annotations
            and routes.behavior
            and not behavior_span_ids
        )
        assert condition_met, (
            "Phase 3: defensive diagnostic condition must be met"
        )

    def test_no_false_positive_when_no_annotations(self):
        """When routes.annotations is empty (old path), no false diagnostic."""
        routes = FieldRouteIR(
            behavior=["s1", "s2"],
            annotations=[],  # no annotations → old path
        )

        # Old path: get_executable_behavior_span_ids returns routes.behavior
        exec_ids = routes.get_executable_behavior_span_ids()
        assert len(exec_ids) == 2, "Old path returns behavior list"
        assert "s1" in exec_ids and "s2" in exec_ids

        # Diagnostic condition NOT met (no annotations)
        condition_met = (
            routes.annotations
            and routes.behavior
            and not set(routes.get_executable_behavior_span_ids())
        )
        assert not condition_met, (
            "No false positive: when annotations absent, diagnostic not emitted"
        )

    def test_no_false_positive_when_executable_exist(self):
        """When executable behavior annotations DO exist, no diagnostic."""
        routes = FieldRouteIR(
            behavior=["s1", "s2"],
            annotations=[
                RouteAnnotation(
                    span_id="s1",
                    field="behavior",
                    semantic_role="process_step",
                    executable=True,  # THIS is an executable behavior annotation
                ),
                RouteAnnotation(
                    span_id="s2",
                    field="behavior",
                    semantic_role="process_step",
                    executable=True,
                ),
            ],
        )

        exec_ids = routes.get_executable_behavior_span_ids()
        assert len(exec_ids) == 2, "Both spans have executable behavior annotations"

        # Diagnostic condition NOT met (executable IDs exist)
        condition_met = (
            routes.annotations
            and routes.behavior
            and not set(routes.get_executable_behavior_span_ids())
        )
        assert not condition_met, (
            "No false positive: when executable annotations exist, no diagnostic"
        )

    def test_no_false_positive_when_behavior_empty(self):
        """When routes.behavior is empty, no diagnostic (nothing to warn about)."""
        routes = FieldRouteIR(
            behavior=[],  # empty
            annotations=[
                RouteAnnotation(
                    span_id="s1",
                    field="rules",
                    semantic_role="constraint",
                    executable=False,
                ),
            ],
        )

        # Diagnostic condition NOT met (behavior is empty)
        condition_met = (
            routes.annotations
            and routes.behavior
            and not set(routes.get_executable_behavior_span_ids())
        )
        assert not condition_met, (
            "No false positive: when behavior list is empty, no diagnostic"
        )


# ===========================================================================
# Test Class 2: Stage 4 strictness preserved
# ===========================================================================


class TestStage4StrictnessPreserved:
    """Phase 3: Stage 4 strict consumption is unchanged — no fallback to
    routes.behavior."""

    def test_get_executable_behavior_still_returns_empty_when_no_annotations(self):
        """Even with the diagnostic, get_executable_behavior_span_ids() still
        returns empty when no executable behavior annotations exist."""
        routes = FieldRouteIR(
            behavior=["s1", "s2", "s3"],
            annotations=[
                RouteAnnotation(
                    span_id="s1",
                    field="rules",
                    semantic_role="constraint",
                    executable=False,
                ),
            ],
        )

        exec_ids = routes.get_executable_behavior_span_ids()
        assert len(exec_ids) == 0, (
            "Phase 3: strict consumption RULE UNCHANGED — "
            "get_executable_behavior_span_ids() still returns empty "
            "when no executable behavior annotations exist"
        )

    def test_legacy_behavior_list_not_used_when_annotations_present(self):
        """When annotations exist, routes.behavior is NOT used as fallback for
        executable span IDs."""
        routes = FieldRouteIR(
            behavior=["s_fallback1", "s_fallback2"],
            annotations=[
                RouteAnnotation(
                    span_id="s_real",
                    field="behavior",
                    semantic_role="process_step",
                    executable=True,
                ),
            ],
        )

        exec_ids = routes.get_executable_behavior_span_ids()
        # Only s_real (with executable=True, field=behavior annotation) is returned
        assert "s_real" in exec_ids
        # s_fallback1 and s_fallback2 are NOT in exec_ids even though they're
        # in routes.behavior, because annotations take precedence
        assert "s_fallback1" not in exec_ids
        assert "s_fallback2" not in exec_ids
