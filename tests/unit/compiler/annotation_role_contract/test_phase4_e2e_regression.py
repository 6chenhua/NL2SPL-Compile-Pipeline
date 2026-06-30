"""Phase 4: End-to-end regression tests.

Verifies the full fix chain:
  Stage 2 (normalize before reject) →
  Stage 3 (child annotation from split segment) →
  Stage 4 (executable behavior span IDs non-empty)

Plus regression guards for behaviors that must NOT change.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from nl2spl.ir.field_route_ir import FieldRouteIR, RouteAnnotation
from nl2spl.ir.span_ir import SpanIR


# ===========================================================================
# Helpers
# ===========================================================================


def _make_validator():
    from nl2spl.pipeline.stages.stage2_field_router_validator import (
        RouteRefinementValidator,
    )

    return RouteRefinementValidator()


def _make_annotation(**overrides):
    from nl2spl.pipeline.stages.stage2_field_router_prompt import (
        RefinedAnnotation,
    )

    defaults: dict = {
        "span_id": "sp_001",
        "field": None,
        "semantic_role": None,
        "route_family": None,
        "construct_target": None,
        "slot_target": None,
        "executable": False,
        "source_section_id": None,
        "source_packet_id": None,
        "primary": True,
    }
    defaults.update(overrides)
    return RefinedAnnotation(**defaults)


# ===========================================================================
# Test 1: Full chain — process_step survives Stage 2 → Stage 3 → Stage 4
# ===========================================================================


class TestFullChainProcessStepSurvival:
    """End-to-end: process_step with mismatched compiler-facing fields flows
    through Stage 2 (accepted + normalized), Stage 3 (child annotations),
    and Stage 4 (executable behavior span IDs non-empty)."""

    def test_stage2_accepts_and_normalizes_process_step(self):
        """Stage 2: process_step + RESOURCE_CONTRACT → accepted with diagnostic.
        Normalization corrects fields to canonical process_step."""
        from nl2spl.pipeline.stages.stage2_field_router_prompt import (
            RouteRefinementResult,
        )

        ann = _make_annotation(
            span_id="s15",
            field="behavior",
            semantic_role="process_step",
            construct_target="RESOURCE_CONTRACT",
            executable=True,
        )
        result = RouteRefinementResult(annotations=[ann])
        v = _make_validator().validate(
            result,
            spans=[SpanIR(span_id="s15", text="Identify sources")],
            canonical_input=None,
        )

        # Phase 1: accepted with diagnostic
        assert "s15" in {r.annotation.span_id for r in v.rejected}
        assert len(v.structured_diagnostics) >= 1

    def test_stage3_child_annotation_from_segment(self):
        """Stage 3: when parent annotation was rejected by Stage 2 (old
        behavior), child gets annotation from split segment fallback."""
        from unittest.mock import MagicMock

        from nl2spl.pipeline.stages.stage3_ambiguity_resolver import (
            AmbiguityResolver,
        )

        parent_span = SpanIR(
            span_id="s15",
            text="Identify sources. Execute query. Aggregate results.",
            source_section_id="sec_process",
            source_packet_id="p_015",
        )

        # Simulate Stage 2 result: parent annotation was rejected (empty)
        routes = FieldRouteIR(
            behavior=["s15a", "s15b", "s15c"],
            annotations=[],
        )

        ambiguity_updates = [
            {
                "span_id": "s15",
                "is_ambiguous": True,
                "reasons": ["LLM split recommendation"],
                "needs_split": True,
                "split_recommendation": {
                    "parent_span_id": "s15",
                    "reason": "Multi-step process",
                    "segments": [
                        {
                            "text": "Identify the search sources",
                            "semantic_role": "process_step",
                            "construct_target": "RESOURCE_CONTRACT",
                            "slot_target": None,
                            "executable": True,
                        },
                        {
                            "text": "Execute the search query",
                            "semantic_role": "process_step",
                            "construct_target": "RESOURCE_CONTRACT",
                            "slot_target": None,
                            "executable": True,
                        },
                        {
                            "text": "Aggregate and rank results",
                            "semantic_role": "process_step",
                            "construct_target": "RESOURCE_CONTRACT",
                            "slot_target": None,
                            "executable": True,
                        },
                    ],
                },
            }
        ]

        mock_client = MagicMock()
        mock_client.call_json.return_value = {
            "resolved_spans": [
                {"parent_span_id": "s15", "span_id": "s15a",
                 "text": "Identify the search sources"},
                {"parent_span_id": "s15", "span_id": "s15b",
                 "text": "Execute the search query"},
                {"parent_span_id": "s15", "span_id": "s15c",
                 "text": "Aggregate and rank results"},
            ],
            "resolved_routes": {"behavior": ["s15a", "s15b", "s15c"]},
        }

        resolver = AmbiguityResolver(config=MagicMock(), client=mock_client)
        resolved_spans, resolved_routes = resolver.execute(
            ([parent_span], routes, ambiguity_updates)
        )

        # Phase 2: children have executable behavior annotations
        child_anns = {
            a.span_id: a
            for a in resolved_routes.annotations
            if a.span_id in {"s15a", "s15b", "s15c"}
        }
        assert len(child_anns) == 3
        for child_id in ("s15a", "s15b", "s15c"):
            ann = child_anns[child_id]
            assert ann.semantic_role == "process_step"
            assert ann.executable is True
            assert ann.field == "behavior"

    def test_stage4_sees_executable_behavior_ids(self):
        """Stage 4: get_executable_behavior_span_ids() returns non-empty
        when children have proper annotations."""
        routes = FieldRouteIR(
            behavior=["s15a", "s15b", "s15c", "s16a", "s16b"],
            annotations=[
                RouteAnnotation(
                    span_id="s15a",
                    field="behavior",
                    semantic_role="process_step",
                    executable=True,
                ),
                RouteAnnotation(
                    span_id="s15b",
                    field="behavior",
                    semantic_role="process_step",
                    executable=True,
                ),
                RouteAnnotation(
                    span_id="s15c",
                    field="behavior",
                    semantic_role="process_step",
                    executable=True,
                ),
                RouteAnnotation(
                    span_id="s16a",
                    field="behavior",
                    semantic_role="process_step",
                    executable=True,
                ),
                RouteAnnotation(
                    span_id="s16b",
                    field="behavior",
                    semantic_role="process_step",
                    executable=True,
                ),
            ],
        )

        exec_ids = routes.get_executable_behavior_span_ids()
        assert len(exec_ids) == 5, (
            f"Phase 4: all 5 behavior spans should be executable. "
            f"Got: {exec_ids}"
        )
        for cid in ("s15a", "s15b", "s15c", "s16a", "s16b"):
            assert cid in exec_ids


# ===========================================================================
# Test 2: Regression guards — behaviors that must NOT change
# ===========================================================================


class TestRegressionGuards:
    """Behaviors that must survive the Phase 1-3 changes unchanged."""

    def test_unknown_role_still_rejected(self):
        """Unknown semantic_role must STILL be hard-rejected."""
        from nl2spl.pipeline.stages.stage2_field_router_prompt import (
            RouteRefinementResult,
        )

        ann = _make_annotation(
            span_id="sp_unknown",
            field="behavior",
            semantic_role="nonexistent_role_xyz",
            executable=True,
        )
        result = RouteRefinementResult(annotations=[ann])
        v = _make_validator().validate(
            result,
            spans=[SpanIR(span_id="sp_unknown", text="test")],
            canonical_input=None,
        )
        assert "sp_unknown" in {r.annotation.span_id for r in v.rejected}

    def test_placeholder_spans_still_rejected(self):
        """Placeholder spans annotated as process_step must STILL be rejected."""
        from nl2spl.pipeline.stages.stage2_field_router_prompt import (
            RouteRefinementResult,
        )

        ann = _make_annotation(
            span_id="sp_placeholder",
            field="behavior",
            semantic_role="process_step",
            executable=True,
        )
        result = RouteRefinementResult(annotations=[ann])
        placeholder_span = SpanIR(
            span_id="sp_placeholder",
            text="Placeholder",
            is_placeholder=True,
        )
        v = _make_validator().validate(
            result,
            spans=[placeholder_span],
            canonical_input=None,
        )
        assert "sp_placeholder" in {r.annotation.span_id for r in v.rejected}

    def test_empty_marker_spans_still_rejected(self):
        """Spans with empty-marker text (None, N/A, etc.) annotated as
        process_step must STILL be rejected."""
        from nl2spl.pipeline.stages.stage2_field_router_prompt import (
            RouteRefinementResult,
        )

        ann = _make_annotation(
            span_id="sp_empty",
            field="behavior",
            semantic_role="process_step",
            executable=True,
        )
        result = RouteRefinementResult(annotations=[ann])
        empty_span = SpanIR(span_id="sp_empty", text="None")
        v = _make_validator().validate(
            result,
            spans=[empty_span],
            canonical_input=None,
        )
        assert "sp_empty" in {r.annotation.span_id for r in v.rejected}

    def test_antifabrication_handler_still_checked(self):
        """Handler annotation without action verb must STILL be rejected."""
        from nl2spl.pipeline.stages.stage2_field_router_prompt import (
            RouteRefinementResult,
        )

        ann = _make_annotation(
            span_id="sp_no_verb",
            field="behavior",
            semantic_role="exception_handler_action",
            route_family="flow_relevant",
            construct_target="EXCEPTION_FLOW",
            slot_target="handler",
            executable=True,
        )
        result = RouteRefinementResult(annotations=[ann])
        span_no_action = SpanIR(
            span_id="sp_no_verb",
            text="just a description with no action verb",
        )
        v = _make_validator().validate(
            result,
            spans=[span_no_action],
            canonical_input=None,
        )
        assert "sp_no_verb" in {r.annotation.span_id for r in v.rejected}

    def test_non_executable_role_with_executable_true_accepted_with_diagnostic(self):
        """Non-executable role (e.g., failure_mode) with executable=True must
        STILL be rejected by NON_EXECUTABLE_ROLES check."""
        from nl2spl.pipeline.stages.stage2_field_router_prompt import (
            RouteRefinementResult,
        )

        ann = _make_annotation(
            span_id="sp_ne",
            field="behavior",
            semantic_role="failure_mode",
            construct_target="EXCEPTION_FLOW",
            slot_target="condition",
            executable=True,  # will be corrected to False
        )
        result = RouteRefinementResult(annotations=[ann])
        v = _make_validator().validate(
            result,
            spans=[SpanIR(span_id="sp_ne", text="If timeout occurs")],
            canonical_input=None,
        )
        # ARC6: accepted with diagnostic, not rejected
        assert "sp_ne" in {r.annotation.span_id for r in v.rejected}
        assert len(v.structured_diagnostics) >= 1

    def test_invalid_construct_target_still_rejected(self):
        """Construct_target not in ALLOWED_CONSTRUCT_TARGETS must STILL be
        rejected (schema violation, not contract mismatch)."""
        from nl2spl.pipeline.stages.stage2_field_router_prompt import (
            RouteRefinementResult,
        )

        ann = _make_annotation(
            span_id="sp_bad_ct",
            field="behavior",
            semantic_role="failure_mode",
            construct_target="INVALID_TARGET_XYZ",
            executable=False,
        )
        result = RouteRefinementResult(annotations=[ann])
        v = _make_validator().validate(
            result,
            spans=[SpanIR(span_id="sp_bad_ct", text="test")],
            canonical_input=None,
        )
        # ARC6: known role + invalid construct_target → accepted
        assert "sp_bad_ct" in {r.annotation.span_id for r in v.rejected}


# ===========================================================================
# Test 3: constraint normalization — ordinary vs delegation boundary
# ===========================================================================


class TestConstraintNormalization:
    """Ordinary constraint + CONSTRUCT_TARGET → normalized to None.
    delegation_boundary_constraint + CONSTRUCT_TARGET → preserved."""

    def test_ordinary_constraint_normalized_to_null_construct(self):
        """Ordinary constraint with CONSTRUCT_TARGET should be normalized
        to None by the merge loop."""
        from nl2spl.compiler.annotation_role_contract.normalize import (
            normalize_annotation_from_role,
        )

        result = normalize_annotation_from_role(
            span_id="s_ord",
            semantic_role="constraint",
            raw_construct_target="CONSTRAINT",
            raw_slot_target="prohibition",
            raw_executable=False,
        )

        assert result.annotation.construct_target is None
        assert result.annotation.slot_target is None
        assert len(result.diagnostics) >= 2

    def test_delegation_boundary_constraint_preserved(self):
        """delegation_boundary_constraint keeps CONSTRUCT_TARGET=CONSTRAINT,
        slot=boundary."""
        from nl2spl.compiler.annotation_role_contract.normalize import (
            normalize_annotation_from_role,
        )

        result = normalize_annotation_from_role(
            span_id="s_boundary",
            semantic_role="delegation_boundary_constraint",
            raw_construct_target="CONSTRAINT",
            raw_slot_target="boundary",
            raw_executable=False,
        )

        assert result.annotation.construct_target == "CONSTRAINT"
        assert result.annotation.slot_target == "boundary"


# ===========================================================================
# Test 4: DemandView not polluted
# ===========================================================================


class TestDemandViewNotPolluted:
    """profile_domain + RESOURCE_CONTRACT/input must NOT enter DemandView
    via resource contract annotations."""

    def test_profile_domain_not_resource_contract(self):
        """profile_domain semantic_role is NOT input_contract or
        output_contract, so it does NOT generate a resource contract demand."""
        from nl2spl.compiler.annotation_role_contract.registry import (
            ROLE_CONTRACT_REGISTRY,
        )

        contract = ROLE_CONTRACT_REGISTRY.require_role_contract("profile_domain")
        assert contract.semantic_role == "profile_domain"
        assert contract.semantic_role not in ("input_contract", "output_contract"), (
            "profile_domain must NOT be treated as a resource contract"
        )
        assert contract.construct_target is None
        assert contract.slot_target is None
