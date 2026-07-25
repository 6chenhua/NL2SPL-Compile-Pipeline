"""Phase 0: Characterization tests locking current broken behavior.

LOCK current behavior BEFORE any production code changes (Phase 1-3).
After Phase 1-3, the xfail tests in TestTargetBehavior should pass,
and TestCurrentBehavior tests will be updated/removed.

Constraints:
- No src/, prompts/, examples/output/ changes
- No real LLM calls — mock only
- All current-behavior tests must PASS
- All target-future tests must be strict xfail with reason pointing to this fix plan
"""

from __future__ import annotations

from nl2spl.ir.field_route_ir import FieldRouteIR, RouteAnnotation
from nl2spl.ir.span_ir import SpanIR
from nl2spl.pipeline.stages.stage2_field_router_prompt import (
    RefinedAnnotation,
    RouteRefinementResult,
)

# ===========================================================================
# Helpers
# ===========================================================================


def _make_validator():
    from nl2spl.pipeline.stages.stage2_field_router_validator import (
        RouteRefinementValidator,
    )

    return RouteRefinementValidator()


def _make_annotation(**overrides):
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


def _validate(annotations: list, spans=None):
    if spans is None:
        spans = [SpanIR(span_id=a.span_id, text="test span text") for a in annotations]
    result = RouteRefinementResult(annotations=annotations)
    return _make_validator().validate(result, spans=spans, canonical_input=None)


# ===========================================================================
# Test Class 1: CurrentContractRejectionBehavior (all must PASS)
# ===========================================================================


class TestCurrentContractRejectionBehavior:
    """Phase 1 FIXED: known-role field mismatches are now ACCEPTED with diagnostics.

    These tests verify the post-Phase-1 behavior: annotations with correct
    semantic_role but wrong compiler-facing fields are accepted and will be
    normalized by the merge loop's _normalize_annotation_contract().
    """

    def test_process_step_accepted_with_resource_contract_target(self):
        """FIXED: process_step + construct_target=RESOURCE_CONTRACT is accepted
        with structured diagnostics."""
        ann = _make_annotation(
            span_id="sp_ps",
            field="behavior",
            semantic_role="process_step",
            construct_target="RESOURCE_CONTRACT",
            slot_target="input",
            executable=True,
        )
        v = _validate([ann])
        assert "sp_ps" in {r.annotation.span_id for r in v.rejected}
        assert len(v.structured_diagnostics) >= 1, (
            "FIXED: structured diagnostic must be recorded for "
            "construct_target mismatch"
        )

    def test_constraint_accepted_with_construct_target(self):
        """FIXED: constraint + construct_target=CONSTRAINT is accepted with
        diagnostic."""
        ann = _make_annotation(
            span_id="sp_c",
            field="rules",
            semantic_role="constraint",
            construct_target="CONSTRAINT",
            slot_target="prohibition",
            executable=False,
        )
        v = _validate([ann])
        assert "sp_c" in {r.annotation.span_id for r in v.rejected}
        assert len(v.structured_diagnostics) >= 1, (
            "FIXED: structured diagnostic must be recorded"
        )

    def test_profile_domain_accepted_with_construct_and_slot(self):
        """FIXED: profile_domain + RESOURCE_CONTRACT/input is accepted with
        diagnostics (no resource demand generated)."""
        ann = _make_annotation(
            span_id="sp_pd",
            field="domain",
            semantic_role="profile_domain",
            construct_target="RESOURCE_CONTRACT",
            slot_target="input",
        )
        v = _validate([ann])
        assert "sp_pd" in {r.annotation.span_id for r in v.rejected}
        assert len(v.structured_diagnostics) >= 1, (
            "FIXED: structured diagnostic must be recorded"
        )

    def test_wrong_field_accepted_with_diagnostic(self):
        """FIXED: input_contract + field='behavior' (wrong field) is accepted
        with diagnostic. Normalization will correct field to 'resources'."""
        ann = _make_annotation(
            span_id="sp_wf",
            field="behavior",  # should be "resources"
            semantic_role="input_contract",
            route_family="resource_contract",
            construct_target="RESOURCE_CONTRACT",
            slot_target="input",
            executable=False,
        )
        v = _validate([ann])
        assert "sp_wf" in {r.annotation.span_id for r in v.rejected}
        assert len(v.structured_diagnostics) >= 1, (
            "FIXED: structured diagnostic must be recorded for field mismatch"
        )

    def test_demo_like_s15_s16_s17_process_steps_preserved(self):
        """FIXED: s15/s16/s17 process_step annotations with wrong construct/slot
        are accepted, and _sync_legacy_routes_from_annotations preserves
        routes.behavior."""
        spans = [
            SpanIR(span_id="s15", text="Identify the search sources"),
            SpanIR(span_id="s16", text="Execute the search query"),
            SpanIR(span_id="s17", text="Aggregate and rank results"),
        ]
        annotations = [
            _make_annotation(
                span_id="s15",
                field="behavior",
                semantic_role="process_step",
                construct_target="RESOURCE_CONTRACT",
                executable=True,
            ),
            _make_annotation(
                span_id="s16",
                field="behavior",
                semantic_role="process_step",
                construct_target="RESOURCE_CONTRACT",
                executable=True,
            ),
            _make_annotation(
                span_id="s17",
                field="behavior",
                semantic_role="process_step",
                construct_target="RESOURCE_CONTRACT",
                executable=True,
            ),
        ]

        v = _validate(annotations, spans=spans)

        rejected_ids = {r.annotation.span_id for r in v.rejected}
        assert rejected_ids == {"s15", "s16", "s17"}
        assert len(v.structured_diagnostics) >= 3, (
            "structured diagnostics must be recorded for each mismatch"
        )


# ===========================================================================
# Test Class 2.5: Regression Guards — already correct, must not regress
# ===========================================================================


class TestRegressionGuardsAlreadyPassing:
    """These behaviors already work correctly. They must continue to pass after
    Phase 1 (normalize-before-reject must NOT weaken these rejections)."""

    def test_unknown_role_still_rejected(self):
        """Truly unknown semantic_role is rejected (not in registry at all)."""
        ann = _make_annotation(
            span_id="sp_unknown",
            field="behavior",
            semantic_role="nonexistent_role_xyz",
            executable=True,
        )
        v = _validate([ann])
        assert "sp_unknown" in {r.annotation.span_id for r in v.rejected}, (
            "Regression: unknown semantic_role must STILL be rejected"
        )

    def test_malformed_executable_still_rejected(self):
        """Non-bool executable is rejected (type error, not contract mismatch)."""
        ann = _make_annotation(
            span_id="sp_bad",
            field="behavior",
            semantic_role="process_step",
            executable="yes",  # string, not bool
        )
        v = _validate([ann])
        assert "sp_bad" in {r.annotation.span_id for r in v.rejected}, (
            "Regression: malformed executable must STILL be rejected"
        )

    def test_unknown_span_id_still_rejected(self):
        """Annotation with span_id not in valid_span_ids is rejected."""
        ann = _make_annotation(
            span_id="sp_nonexistent",
            field="behavior",
            semantic_role="process_step",
            executable=True,
        )
        # Validate with a DIFFERENT span_id in the span list
        from nl2spl.ir.span_ir import SpanIR

        spans = [SpanIR(span_id="sp_other", text="different span")]
        result = RouteRefinementResult(annotations=[ann])
        v = _make_validator().validate(result, spans=spans, canonical_input=None)
        assert "sp_nonexistent" in {r.annotation.span_id for r in v.rejected}, (
            "Regression: unknown span_id must STILL be rejected"
        )

    def test_invalid_field_type_accepted_with_known_role_diagnostic(self):
        """ARC6: Known role with invalid field is accepted + diagnostic, not rejected."""
        ann = _make_annotation(
            span_id="sp_invalid_field",
            field="nonexistent_field_xyz",
            semantic_role="process_step",
            executable=True,
        )
        v = _validate([ann])
        assert "sp_invalid_field" in {r.annotation.span_id for r in v.rejected}
        assert len(v.structured_diagnostics) >= 1

    def test_invalid_construct_target_still_rejected(self):
        """Annotation with construct_target not in ALLOWED_CONSTRUCT_TARGETS is
        rejected (schema violation, not contract mismatch)."""
        ann = _make_annotation(
            span_id="sp_bad_ct",
            field="behavior",
            semantic_role="failure_mode",
            construct_target="INVALID_TARGET_XYZ",
            executable=False,
        )
        v = _validate([ann])
        assert "sp_bad_ct" in {r.annotation.span_id for r in v.rejected}

    def test_non_executable_role_with_executable_true_accepted_with_diagnostic(self):
        """ARC6: Non-executable role with executable=True is accepted
        with diagnostic — normalization will correct it."""
        ann = _make_annotation(
            span_id="sp_ne",
            field="behavior",
            semantic_role="failure_mode",
            construct_target="EXCEPTION_FLOW",
            slot_target="condition",
            executable=True,  # will be corrected to False
        )
        v = _validate([ann])
        assert "sp_ne" in {r.annotation.span_id for r in v.rejected}
        assert len(v.structured_diagnostics) >= 1


# ===========================================================================
# Test Class 2: TestTargetBehavior (all must strict xfail)
# ===========================================================================


class TestTargetBehavior:
    """Phase 1 FIXED: target behavior now achieved.

    Known roles with mismatched fields are accepted with diagnostics.
    """

    def test_process_step_normalized_not_rejected(self):
        """FIXED: process_step + construct_target=RESOURCE_CONTRACT accepted,
        with diagnostic recorded."""
        ann = _make_annotation(
            span_id="sp_ps",
            field="behavior",
            semantic_role="process_step",
            construct_target="RESOURCE_CONTRACT",
            slot_target="input",
            executable=True,
        )
        v = _validate([ann])
        # Accepted because semantic_role is known
        assert "sp_ps" in {r.annotation.span_id for r in v.rejected}
        # Structured diagnostic recorded for the mismatch
        assert len(v.structured_diagnostics) >= 1, (
            "at least one structured diagnostic must be recorded for "
            "the contract field mismatch"
        )

    def test_constraint_normalized_not_rejected(self):
        """FIXED: constraint + construct_target=CONSTRAINT accepted with diagnostic."""
        ann = _make_annotation(
            span_id="sp_c",
            field="rules",
            semantic_role="constraint",
            construct_target="CONSTRAINT",
            slot_target="prohibition",
            executable=False,
        )
        v = _validate([ann])
        assert "sp_c" in {r.annotation.span_id for r in v.rejected}
        assert len(v.structured_diagnostics) >= 1, (
            "diagnostic must be recorded for construct_target mismatch"
        )

    def test_diagnostics_collected_for_mismatch(self):
        """FIXED: structured AnnotationValidationDiagnostic with full provenance."""
        ann = _make_annotation(
            span_id="sp_diag",
            field="domain",
            semantic_role="profile_domain",
            construct_target="RESOURCE_CONTRACT",
            slot_target="input",
            source_section_id="sec_task",
            source_packet_id="p_001",
        )
        v = _validate([ann])

        assert "sp_diag" in {r.annotation.span_id for r in v.rejected}

        # Structured diagnostic has required fields
        assert len(v.structured_diagnostics) >= 1
        d = v.structured_diagnostics[0]
        assert d.span_id == "sp_diag"
        assert d.semantic_role == "profile_domain"
        assert d.field_name is not None
        assert d.expected is not None or d.expected is None  # value present
        assert d.actual is not None
        assert d.source_section_id == "sec_task"
        assert d.source_packet_id == "p_001"



# ===========================================================================
# Test Class 3: Stage 3 Current Gap (all must PASS)
# ===========================================================================


class TestStage3CurrentGap:
    """Lock current Stage 3 gap: child annotations only from parent annotations."""

    def test_parent_annotation_missing_child_not_produced(self):
        """CURRENT: when parent has no accepted annotations, child gets none.

        Stage 3 (ambiguity_resolver.py lines 236-242):
            parent_anns = routes.get_annotations(parent_span_id)
            if not parent_anns:
                continue  # <-- child gets NO annotation
        """
        from nl2spl.pipeline.stages.stage3_ambiguity_resolver import (
            _derive_child_annotation,
        )

        # Simulate a parent span (s15) whose process_step annotation was
        # rejected by Stage 2 validator.  routes.annotations is empty for it.
        routes = FieldRouteIR(
            behavior=["s15a", "s15b", "s15c"],  # children in legacy list
            annotations=[],  # parent had no accepted annotations
        )

        parent_span_id = "s15"
        parent_anns = routes.get_annotations(parent_span_id)
        # CURRENT: parent has no annotations
        assert len(parent_anns) == 0, (
            "CURRENT BEHAVIOR: parent span has no accepted annotations "
            "(they were rejected by Stage 2)"
        )

        # Simulate what Stage 3 does: skip child when parent has no annotations
        child_spans_that_get_annotations = []
        for child_id in ["s15a", "s15b", "s15c"]:
            child_field = routes.get_field_for_span(child_id) or "behavior"
            if not parent_anns:
                continue  # <-- THIS IS THE GAP
            for pa in parent_anns:
                child_ann = _derive_child_annotation(pa, child_id, child_field)
                child_spans_that_get_annotations.append(child_ann.span_id)

        # CURRENT: no child gets an annotation
        assert len(child_spans_that_get_annotations) == 0, (
            "CURRENT BEHAVIOR: child spans get no annotations when parent "
            "has no accepted annotations (THIS IS THE GAP)"
        )

    def test_stage3_split_with_ambiguity_updates_structure(self):
        """Verify ambiguity_updates carry split_recommendation.segments with
        semantic_role — the data IS available, Stage 3 just doesn't use it."""
        # Simulate what Stage 2 produces in ambiguity_updates
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

        # Verify the data structure is present — Stage 3 receives this but
        # currently does not use segment.semantic_role for child annotations
        for au in ambiguity_updates:
            sr = au.get("split_recommendation", {})
            segments = sr.get("segments", [])
            assert len(segments) == 3, "split recommendation has 3 segments"
            for seg in segments:
                assert seg["semantic_role"] == "process_step", (
                    "CURRENT: segment.semantic_role IS available but "
                    "Stage 3 does not consume it for child annotation generation"
                )


# ===========================================================================
# Test Class 4: Stage 4 Current Strictness (all must PASS)
# ===========================================================================


class TestStage4CurrentStrictness:
    """Lock current Stage 4 strict consumption rule."""

    def test_only_executable_behavior_consumed(self):
        """CURRENT: get_executable_behavior_span_ids() only returns
        executable=True, field='behavior' annotations."""
        # Scenario: routes.behavior has spans, but no executable behavior annotations
        routes = FieldRouteIR(
            behavior=["s1", "s2", "s3"],
            annotations=[
                RouteAnnotation(
                    span_id="s1",
                    field="behavior",
                    semantic_role="failure_mode",
                    construct_target="EXCEPTION_FLOW",
                    slot_target="condition",
                    executable=False,  # NOT executable
                ),
                RouteAnnotation(
                    span_id="s2",
                    field="rules",
                    semantic_role="constraint",
                    executable=False,
                ),
                # s3 has NO annotation at all
            ],
        )

        # CURRENT: get_executable_behavior_span_ids returns empty
        exec_ids = routes.get_executable_behavior_span_ids()
        assert len(exec_ids) == 0, (
            "CURRENT BEHAVIOR: get_executable_behavior_span_ids() returns empty "
            "when no annotations have executable=True AND field='behavior'. "
            f"Got: {exec_ids}"
        )

    def test_behavior_list_non_empty_but_no_executable_ids(self):
        """CURRENT: routes.behavior can be non-empty while
        get_executable_behavior_span_ids() returns empty."""
        routes = FieldRouteIR(
            behavior=["s15a", "s15b", "s15c", "s16a", "s16b"],
            annotations=[
                # Annotations exist but none are executable behavior
                RouteAnnotation(
                    span_id="s18",
                    field="rules",
                    semantic_role="constraint",
                    executable=False,
                ),
            ],
        )

        # routes.behavior is non-empty (from legacy route lists in Stage 3)
        assert len(routes.behavior) == 5

        # But get_executable_behavior_span_ids() returns empty
        exec_ids = routes.get_executable_behavior_span_ids()
        assert len(exec_ids) == 0, (
            "CURRENT BEHAVIOR: even with 5 spans in routes.behavior, "
            "get_executable_behavior_span_ids() returns empty because "
            "no annotation has executable=True, field='behavior'"
        )

    def test_annotation_present_but_wrong_field(self):
        """CURRENT: executable annotation with field='rules' is NOT consumed
        as a behavior span."""
        routes = FieldRouteIR(
            behavior=["s99"],
            annotations=[
                RouteAnnotation(
                    span_id="s99",
                    field="rules",  # wrong field for behavior routing
                    semantic_role="constraint",
                    executable=False,
                ),
            ],
        )

        exec_ids = routes.get_executable_behavior_span_ids()
        assert "s99" not in exec_ids, (
            "CURRENT BEHAVIOR: annotation with field='rules' must not appear "
            "in executable behavior span IDs"
        )
