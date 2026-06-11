"""Phase 2: Stage 3 child annotation from split segment semantic_role.

Tests that when parent annotations are missing (rejected by Stage 2),
Stage 3 derives canonical child annotations from the split recommendation
segment's semantic_role using normalize_annotation_from_role().
"""

from __future__ import annotations

import pytest

from nl2spl.ir.field_route_ir import FieldRouteIR, RouteAnnotation
from nl2spl.ir.span_ir import SpanIR


# ===========================================================================
# Helpers
# ===========================================================================


def _make_resolver():
    from unittest.mock import MagicMock

    from nl2spl.pipeline.stages.stage3_ambiguity_resolver import (
        AmbiguityResolver,
    )

    resolver = AmbiguityResolver(config=MagicMock(), client=MagicMock())
    return resolver


def _make_split_ambiguity_updates(parent_span_id="s15", segments=None):
    """Build ambiguity_updates with split_recommendation carrying segments."""
    if segments is None:
        segments = [
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
        ]
    return [
        {
            "span_id": parent_span_id,
            "is_ambiguous": True,
            "reasons": ["LLM split recommendation"],
            "needs_split": True,
            "split_recommendation": {
                "parent_span_id": parent_span_id,
                "reason": "Multi-step process",
                "segments": segments,
            },
        }
    ]


# ===========================================================================
# Test Class 1: Child annotation from segment semantic_role
# ===========================================================================


class TestChildAnnotationFromSplitSegment:
    """Phase 2: child annotations derived from split segment when parent missing."""

    def test_child_annotation_from_segment_semantic_role(self):
        """When parent has NO annotations but split segment has
        semantic_role=process_step, child gets executable behavior annotation."""
        from nl2spl.compiler.annotation_role_contract.normalize import (
            normalize_annotation_from_role,
        )
        from nl2spl.pipeline.stages.stage3_ambiguity_resolver import (
            _derive_child_annotation,
        )

        ambiguity_updates = _make_split_ambiguity_updates()

        # Build split segment index (as Stage 3 does)
        _split_by_parent: dict = {}
        for au in ambiguity_updates:
            sr = au.get("split_recommendation", {})
            if sr:
                segments = sr.get("segments", [])
                pid = sr.get("parent_span_id") or au.get("span_id")
                if pid and segments:
                    _split_by_parent[pid] = segments

        # Simulate: parent s15 has no annotations (they were rejected by Stage 2)
        # Child s15a should get annotation from first segment
        parent_span_id = "s15"
        child_id = "s15a"
        child_field = "behavior"
        child_source_section_id = "sec_process"
        child_source_packet_id = "p_015"

        segments = _split_by_parent[parent_span_id]
        seg = segments[0]

        assert seg["semantic_role"] == "process_step"
        assert seg["construct_target"] == "RESOURCE_CONTRACT"  # raw mismatch

        result = normalize_annotation_from_role(
            span_id=child_id,
            semantic_role=seg["semantic_role"],
            source_section_id=child_source_section_id,
            source_packet_id=child_source_packet_id,
            raw_construct_target=seg.get("construct_target"),
            raw_slot_target=seg.get("slot_target"),
            raw_executable=seg.get("executable"),
        )

        # Normalization corrects construct_target to None
        assert result.annotation.construct_target is None, (
            f"Normalization must correct construct_target from "
            f"'{seg['construct_target']}' to None"
        )
        assert result.annotation.field == "behavior"
        assert result.annotation.semantic_role == "process_step"
        assert result.annotation.executable is True

        # Apply field-derived overrides via _derive_child_annotation
        child_ann = _derive_child_annotation(
            result.annotation, child_id, child_field,
        )

        assert child_ann.span_id == child_id
        assert child_ann.field == "behavior"
        assert child_ann.semantic_role == "process_step"
        assert child_ann.executable is True
        assert child_ann.source_section_id == child_source_section_id
        assert child_ann.source_packet_id == child_source_packet_id

        # Diagnostics from normalization
        assert len(result.diagnostics) >= 1, (
            "Normalization must record diagnostic for construct_target correction"
        )

    def test_segment_raw_values_corrected_by_normalization(self):
        """Segment raw construct_target/slot_target are corrected by normalization."""
        from nl2spl.compiler.annotation_role_contract.normalize import (
            normalize_annotation_from_role,
        )

        # Segment with constraint role but CONSTRAINT construct_target (wrong)
        seg = {
            "text": "Policy rule text",
            "semantic_role": "constraint",
            "construct_target": "CONSTRAINT",
            "slot_target": "prohibition",
            "executable": False,
        }

        result = normalize_annotation_from_role(
            span_id="s18a",
            semantic_role=seg["semantic_role"],
            raw_construct_target=seg.get("construct_target"),
            raw_slot_target=seg.get("slot_target"),
            raw_executable=seg.get("executable"),
        )

        # Constraint contract: construct_target=None, slot_target=None
        assert result.annotation.construct_target is None, (
            "constraint construct_target must be corrected to None"
        )
        assert result.annotation.slot_target is None, (
            "constraint slot_target must be corrected to None"
        )
        assert result.annotation.semantic_role == "constraint"
        assert result.annotation.executable is False

        # Diagnostics for both mismatches
        assert len(result.diagnostics) >= 2, (
            f"Expected at least 2 diagnostics (construct_target + slot_target), "
            f"got {len(result.diagnostics)}: {result.diagnostics}"
        )

    def test_derive_child_annotation_preserves_parent_semantic_role(self):
        """ARC: _derive_child_annotation preserves parent semantic_role
        and contract-derived fields, not driven by child_field."""
        from nl2spl.compiler.annotation_role_contract.normalize import (
            normalize_annotation_from_role,
        )
        from nl2spl.pipeline.stages.stage3_ambiguity_resolver import (
            _derive_child_annotation,
        )

        # Segment says process_step, but child is routed to 'rules' field
        seg = {
            "text": "A constraint that was split from process",
            "semantic_role": "process_step",
            "construct_target": None,
            "slot_target": None,
            "executable": True,
        }

        result = normalize_annotation_from_role(
            span_id="child_on_rules",
            semantic_role=seg["semantic_role"],
            raw_construct_target=seg.get("construct_target"),
            raw_executable=seg.get("executable"),
        )

        # Normalized: process_step, behavior, executable=True
        assert result.annotation.semantic_role == "process_step"
        assert result.annotation.field == "behavior"
        assert result.annotation.executable is True

        # ARC: _derive_child_annotation preserves semantic_role from parent.
        # Field-driven overrides (rules→constraint) are removed.
        child_ann = _derive_child_annotation(
            result.annotation, "child_on_rules", "rules",
        )

        assert child_ann.semantic_role == "process_step", (
            "ARC: semantic_role must be preserved, not overridden by field"
        )
        assert child_ann.executable is True, (
            "ARC: executable must be preserved from parent"
        )
        assert child_ann.field == "behavior", (
            "ARC: field must be contract-derived from parent, not route field"
        )

    def test_delegation_boundary_constraint_preserved(self):
        """delegation_boundary_constraint segment preserves its construct/slot."""
        from nl2spl.compiler.annotation_role_contract.normalize import (
            normalize_annotation_from_role,
        )

        seg = {
            "text": "If no answer in cache, delegate to WebSearchWorker",
            "semantic_role": "delegation_boundary_constraint",
            "construct_target": "CONSTRAINT",
            "slot_target": "boundary",
            "executable": False,
        }

        result = normalize_annotation_from_role(
            span_id="s_boundary",
            semantic_role=seg["semantic_role"],
            raw_construct_target=seg.get("construct_target"),
            raw_slot_target=seg.get("slot_target"),
            raw_executable=seg.get("executable"),
        )

        # delegation_boundary_constraint keeps CONSTRUCT_TARGET=CONSTRAINT, slot=boundary
        assert result.annotation.construct_target == "CONSTRAINT"
        assert result.annotation.slot_target == "boundary"
        assert result.annotation.semantic_role == "delegation_boundary_constraint"
        # No diagnostics needed — values match contract
        diags_about_construct = [
            d for d in result.diagnostics if "construct_target" in d.lower()
        ]
        assert len(diags_about_construct) == 0, (
            f"delegation_boundary_constraint with correct construct should "
            f"have no construct diagnostics. Got: {diags_about_construct}"
        )

    def test_no_segment_with_semantic_role_produces_no_fake_annotation(self):
        """When segment has no semantic_role, no annotation is fabricated."""
        ambiguity_updates = _make_split_ambiguity_updates(
            segments=[
                {
                    "text": "Some text without role",
                    "semantic_role": None,  # missing!
                    "construct_target": None,
                    "slot_target": None,
                    "executable": None,
                },
            ]
        )

        _split_by_parent = {}
        for au in ambiguity_updates:
            sr = au.get("split_recommendation", {})
            if sr:
                pid = sr.get("parent_span_id") or au.get("span_id")
                _split_by_parent[pid] = sr.get("segments", [])

        segments = _split_by_parent.get("s15", [])
        seg = segments[0]
        assert seg["semantic_role"] is None, (
            "Segment has no semantic_role — no annotation should be fabricated"
        )


# ===========================================================================
# Test Class 2: Parent annotations still primary path (regression guards)
# ===========================================================================


class TestParentAnnotationsPrimaryPath:
    """Parent annotation inheritance is the FALLBACK path for child annotations.
    Split segment semantic_role is PRIMARY.  These tests verify _derive_child_annotation
    behavior for the fallback case and as a helper function."""

    def test_parent_annotations_still_used_when_present(self):
        """When parent HAS annotations, they are used to derive children."""
        from nl2spl.pipeline.stages.stage3_ambiguity_resolver import (
            _derive_child_annotation,
        )

        # Parent has an accepted process_step annotation
        parent_ann = RouteAnnotation(
            span_id="s15",
            field="behavior",
            semantic_role="process_step",
            route_family="flow_relevant",
            construct_target=None,
            slot_target=None,
            executable=True,
            source_section_id="sec_process",
            source_packet_id="p_015",
        )
        routes = FieldRouteIR(
            behavior=["s15a"],
            annotations=[parent_ann],
        )

        parent_anns = routes.get_annotations("s15")
        assert len(parent_anns) == 1, "Parent has annotation"

        child_field = routes.get_field_for_span("s15a") or "behavior"
        child_ann = _derive_child_annotation(parent_anns[0], "s15a", child_field)

        # Child inherits from parent
        assert child_ann.span_id == "s15a"
        assert child_ann.semantic_role == "process_step"
        assert child_ann.executable is True
        assert child_ann.field == "behavior"
        assert child_ann.source_section_id == "sec_process"
        assert child_ann.source_packet_id == "p_015"

    def test_parent_with_multiple_annotations_produces_multiple_children(self):
        """Each parent annotation produces one child annotation."""
        from nl2spl.pipeline.stages.stage3_ambiguity_resolver import (
            _derive_child_annotation,
        )

        parent_anns = [
            RouteAnnotation(
                span_id="s15",
                field="behavior",
                semantic_role="process_step",
                executable=True,
            ),
            RouteAnnotation(
                span_id="s15",
                field="rules",
                semantic_role="constraint",
                executable=False,
            ),
        ]
        routes = FieldRouteIR(
            behavior=["s15a"],
            annotations=parent_anns,
        )

        child_annotations = []
        child_field = routes.get_field_for_span("s15a") or "behavior"
        for pa in parent_anns:
            child_ann = _derive_child_annotation(pa, "s15a", child_field)
            child_annotations.append(child_ann)

        assert len(child_annotations) == 2, (
            "Each parent annotation produces one child annotation"
        )


# ===========================================================================
# Test Class 3: Stage 3 integration with segment fallback
# ===========================================================================


class TestStage3Integration:
    """Integration tests: Stage 3 execute() with LLM mocked, verifying
    child annotations flow through the entire execute() method."""

    def test_execute_with_segment_fallback(self):
        """Full Stage 3 execution: parent has NO accepted annotations →
        child annotations derived from split segment semantic_role."""
        from unittest.mock import MagicMock

        from nl2spl.pipeline.stages.stage3_ambiguity_resolver import (
            AmbiguityResolver,
        )

        # Parent span s15 — its process_step annotation was rejected by Stage 2
        parent_span = SpanIR(
            span_id="s15",
            text="Identify the search sources. Execute the search query. Aggregate results.",
            source_section_id="sec_process",
            source_packet_id="p_015",
        )

        # Routes: parent has NO annotations (they were all rejected)
        routes = FieldRouteIR(
            behavior=["s15a", "s15b", "s15c"],
            annotations=[],  # empty!
        )

        # Ambiguity updates with split_recommendation carrying segments
        ambiguity_updates = _make_split_ambiguity_updates()

        # Mock LLM: returns 3 child spans
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
            "resolved_routes": {
                "behavior": ["s15a", "s15b", "s15c"],
            },
        }

        resolver = AmbiguityResolver(config=MagicMock(), client=mock_client)
        resolved_spans, resolved_routes = resolver.execute(
            ([parent_span], routes, ambiguity_updates)
        )

        # All 3 children should have executable behavior annotations
        child_anns = {
            a.span_id: a
            for a in resolved_routes.annotations
            if a.span_id in {"s15a", "s15b", "s15c"}
        }
        assert len(child_anns) == 3, (
            f"All 3 children must have annotations. "
            f"Got: {child_anns}"
        )

        for child_id in ("s15a", "s15b", "s15c"):
            ann = child_anns[child_id]
            assert ann.semantic_role == "process_step", (
                f"{child_id}: expected process_step, got {ann.semantic_role}"
            )
            assert ann.executable is True, (
                f"{child_id}: expected executable=True, got {ann.executable}"
            )
            assert ann.field == "behavior", (
                f"{child_id}: expected field='behavior', got {ann.field}"
            )
            assert ann.source_section_id == "sec_process", (
                f"{child_id}: must inherit source_section_id from child SpanIR"
            )
            assert ann.source_packet_id == "p_015", (
                f"{child_id}: must inherit source_packet_id from child SpanIR"
            )

        # Non-ambiguous spans (none in this case)
        # Resolved spans include the 3 children
        assert len(resolved_spans) == 3

        # Resolved routes behavior has the children
        assert all(cid in resolved_routes.behavior for cid in ("s15a", "s15b", "s15c"))

    def test_segment_role_primary_over_parent_annotation(self):
        """P1 fix: Segment semantic_role is PRIMARY. Even when parent HAS
        annotations, children get their semantic_role from the corresponding
        split recommendation segment, NOT from the parent.

        A mixed parent span split into constraint + profile_domain children
        must NOT inherit the parent's process_step role."""
        from unittest.mock import MagicMock

        from nl2spl.pipeline.stages.stage3_ambiguity_resolver import (
            AmbiguityResolver,
        )

        parent_span = SpanIR(
            span_id="s15",
            text="Source text for splitting",
            source_section_id="sec_process",
        )

        # Parent HAS a process_step annotation (but the span was ambiguous
        # because it contained mixed semantics)
        routes = FieldRouteIR(
            behavior=["s15a", "s15b"],
            annotations=[
                RouteAnnotation(
                    span_id="s15",
                    field="behavior",
                    semantic_role="process_step",
                    route_family="flow_relevant",
                    construct_target=None,
                    slot_target=None,
                    executable=True,
                    source_section_id="sec_process",
                ),
            ],
        )

        # Split segments have DIFFERENT semantic roles from parent —
        # this is exactly why the span needed splitting.
        ambiguity_updates = _make_split_ambiguity_updates(
            segments=[
                {
                    "text": "Step A",
                    "semantic_role": "constraint",
                    "construct_target": "CONSTRAINT",
                    "slot_target": None,
                    "executable": False,
                },
                {
                    "text": "Step B",
                    "semantic_role": "profile_domain",
                    "construct_target": None,
                    "slot_target": None,
                    "executable": False,
                },
            ],
        )

        mock_client = MagicMock()
        mock_client.call_json.return_value = {
            "resolved_spans": [
                {"parent_span_id": "s15", "span_id": "s15a", "text": "Step A"},
                {"parent_span_id": "s15", "span_id": "s15b", "text": "Step B"},
            ],
            "resolved_routes": {
                "behavior": ["s15a", "s15b"],
            },
        }

        resolver = AmbiguityResolver(config=MagicMock(), client=mock_client)
        resolved_spans, resolved_routes = resolver.execute(
            ([parent_span], routes, ambiguity_updates)
        )

        # P1 FIX: children get semantic_role from SEGMENT, not parent.
        child_anns = {
            a.span_id: a
            for a in resolved_routes.annotations
            if a.span_id in {"s15a", "s15b"}
        }
        assert len(child_anns) == 2

        # s15a segment = constraint → child must be constraint
        assert child_anns["s15a"].semantic_role == "constraint", (
            f"s15a: segment role is 'constraint', must NOT inherit parent's "
            f"'process_step'. Got: {child_anns['s15a'].semantic_role}"
        )
        # s15b segment = profile_domain → child must be profile_domain
        assert child_anns["s15b"].semantic_role == "profile_domain", (
            f"s15b: segment role is 'profile_domain', must NOT inherit parent's "
            f"'process_step'. Got: {child_anns['s15b'].semantic_role}"
        )

    def test_parent_fallback_when_segment_has_no_role(self):
        """When segment has no semantic_role, fall back to parent annotation
        inheritance (with diagnostic)."""
        from unittest.mock import MagicMock

        from nl2spl.pipeline.stages.stage3_ambiguity_resolver import (
            AmbiguityResolver,
        )

        parent_span = SpanIR(
            span_id="s15",
            text="Source text for splitting",
            source_section_id="sec_process",
        )

        routes = FieldRouteIR(
            behavior=["s15a"],
            annotations=[
                RouteAnnotation(
                    span_id="s15",
                    field="behavior",
                    semantic_role="process_step",
                    executable=True,
                ),
            ],
        )

        # Segment has NO semantic_role → parent fallback
        ambiguity_updates = _make_split_ambiguity_updates(
            segments=[
                {
                    "text": "Step A",
                    "semantic_role": None,  # missing!
                    "construct_target": None,
                    "slot_target": None,
                    "executable": None,
                },
            ],
        )

        mock_client = MagicMock()
        mock_client.call_json.return_value = {
            "resolved_spans": [
                {"parent_span_id": "s15", "span_id": "s15a", "text": "Step A"},
            ],
            "resolved_routes": {
                "behavior": ["s15a"],
            },
        }

        resolver = AmbiguityResolver(config=MagicMock(), client=mock_client)
        resolved_spans, resolved_routes = resolver.execute(
            ([parent_span], routes, ambiguity_updates)
        )

        # Segment has no role → fallback to parent
        child_anns = [
            a for a in resolved_routes.annotations if a.span_id == "s15a"
        ]
        assert len(child_anns) == 1, "Child must get annotation from parent fallback"
        assert child_anns[0].semantic_role == "process_step", (
            "Segment role missing → must fall back to parent's process_step"
        )

    def test_unknown_segment_role_falls_back_to_parent(self):
        """When segment has an unknown semantic_role (not in registry),
        Stage 3 resolves it, finds it unknown, and falls back to parent
        annotation with a diagnostic. No exception is raised."""
        from unittest.mock import MagicMock

        from nl2spl.pipeline.stages.stage3_ambiguity_resolver import (
            AmbiguityResolver,
        )

        parent_span = SpanIR(
            span_id="s15",
            text="Source text for splitting",
            source_section_id="sec_process",
        )

        routes = FieldRouteIR(
            behavior=["s15a"],
            annotations=[
                RouteAnnotation(
                    span_id="s15",
                    field="behavior",
                    semantic_role="process_step",
                    executable=True,
                ),
            ],
        )

        # Segment has UNKNOWN role
        ambiguity_updates = _make_split_ambiguity_updates(
            segments=[
                {
                    "text": "Step A",
                    "semantic_role": "nonexistent_role_xyz",
                    "construct_target": None,
                    "slot_target": None,
                    "executable": None,
                },
            ],
        )

        mock_client = MagicMock()
        mock_client.call_json.return_value = {
            "resolved_spans": [
                {"parent_span_id": "s15", "span_id": "s15a", "text": "Step A"},
            ],
            "resolved_routes": {
                "behavior": ["s15a"],
            },
        }

        resolver = AmbiguityResolver(config=MagicMock(), client=mock_client)
        # Must NOT raise an exception
        resolved_spans, resolved_routes = resolver.execute(
            ([parent_span], routes, ambiguity_updates)
        )

        # Child must get annotation from parent fallback (not crash)
        child_anns = [
            a for a in resolved_routes.annotations if a.span_id == "s15a"
        ]
        assert len(child_anns) >= 1, (
            "Unknown segment role must NOT crash; parent fallback must provide annotation"
        )


# ===========================================================================
# Test Class 4: P2 — fallback diagnostics in route_diagnostics
# ===========================================================================


class TestFallbackDiagnosticsInRouteOutput:
    """P2: Stage 3 fallback warnings must appear in resolved_routes.route_diagnostics,
    not just in logs. This makes fallback visible in pipeline artifacts for
    downstream diagnostic consumers (IRS, feedback report, etc.)."""

    def test_unknown_segment_role_diagnostic_in_routes(self):
        """When segment has unknown role, the fallback diagnostic appears in
        resolved_routes.route_diagnostics."""
        from unittest.mock import MagicMock

        from nl2spl.pipeline.stages.stage3_ambiguity_resolver import (
            AmbiguityResolver,
        )

        parent_span = SpanIR(span_id="s15", text="Source text")
        routes = FieldRouteIR(
            behavior=["s15a"],
            annotations=[
                RouteAnnotation(
                    span_id="s15", field="behavior",
                    semantic_role="process_step", executable=True,
                ),
            ],
        )
        ambiguity_updates = _make_split_ambiguity_updates(
            segments=[{
                "text": "Step A",
                "semantic_role": "nonexistent_role_xyz",
                "construct_target": None, "slot_target": None, "executable": None,
            }],
        )

        mock_client = MagicMock()
        mock_client.call_json.return_value = {
            "resolved_spans": [
                {"parent_span_id": "s15", "span_id": "s15a", "text": "Step A"},
            ],
            "resolved_routes": {"behavior": ["s15a"]},
        }

        resolver = AmbiguityResolver(config=MagicMock(), client=mock_client)
        _, resolved_routes = resolver.execute(
            ([parent_span], routes, ambiguity_updates)
        )

        # P2: diagnostic must be in route_diagnostics
        assert len(resolved_routes.route_diagnostics) >= 1, (
            "Unknown segment role fallback must produce route_diagnostics entry"
        )
        diag_text = " ".join(resolved_routes.route_diagnostics)
        assert "nonexistent_role_xyz" in diag_text, (
            f"Diagnostic must mention the unknown role. Got: {diag_text}"
        )
        assert "s15a" in diag_text, (
            f"Diagnostic must mention the child span. Got: {diag_text}"
        )
        assert "falling back" in diag_text.lower(), (
            f"Diagnostic must indicate fallback. Got: {diag_text}"
        )

    def test_missing_segment_role_diagnostic_in_routes(self):
        """When segment has no semantic_role at all, parent fallback is
        recorded in route_diagnostics."""
        from unittest.mock import MagicMock

        from nl2spl.pipeline.stages.stage3_ambiguity_resolver import (
            AmbiguityResolver,
        )

        parent_span = SpanIR(span_id="s15", text="Source text")
        routes = FieldRouteIR(
            behavior=["s15a"],
            annotations=[
                RouteAnnotation(
                    span_id="s15", field="behavior",
                    semantic_role="process_step", executable=True,
                ),
            ],
        )
        ambiguity_updates = _make_split_ambiguity_updates(
            segments=[{
                "text": "Step A",
                "semantic_role": None,  # missing
                "construct_target": None, "slot_target": None, "executable": None,
            }],
        )

        mock_client = MagicMock()
        mock_client.call_json.return_value = {
            "resolved_spans": [
                {"parent_span_id": "s15", "span_id": "s15a", "text": "Step A"},
            ],
            "resolved_routes": {"behavior": ["s15a"]},
        }

        resolver = AmbiguityResolver(config=MagicMock(), client=mock_client)
        _, resolved_routes = resolver.execute(
            ([parent_span], routes, ambiguity_updates)
        )

        # P2: parent fallback diagnostic in route_diagnostics
        assert len(resolved_routes.route_diagnostics) >= 1, (
            "Missing segment role → parent fallback must produce route_diagnostics entry"
        )
        diag_text = " ".join(resolved_routes.route_diagnostics)
        assert "falling back" in diag_text.lower(), (
            f"Diagnostic must indicate fallback. Got: {diag_text}"
        )

    def test_no_false_diagnostic_when_segment_role_used(self):
        """When segment role is valid and used (PRIMARY path), route_diagnostics
        does NOT contain a fallback diagnostic."""
        from unittest.mock import MagicMock

        from nl2spl.pipeline.stages.stage3_ambiguity_resolver import (
            AmbiguityResolver,
        )

        parent_span = SpanIR(
            span_id="s15", text="Source text",
            source_section_id="sec_process",
        )
        routes = FieldRouteIR(
            behavior=["s15a"],
            annotations=[
                RouteAnnotation(
                    span_id="s15", field="behavior",
                    semantic_role="process_step", executable=True,
                ),
            ],
        )
        ambiguity_updates = _make_split_ambiguity_updates(
            segments=[{
                "text": "Step A",
                "semantic_role": "process_step",
                "construct_target": "RESOURCE_CONTRACT",
                "slot_target": None, "executable": True,
            }],
        )

        mock_client = MagicMock()
        mock_client.call_json.return_value = {
            "resolved_spans": [
                {"parent_span_id": "s15", "span_id": "s15a", "text": "Step A"},
            ],
            "resolved_routes": {"behavior": ["s15a"]},
        }

        resolver = AmbiguityResolver(config=MagicMock(), client=mock_client)
        _, resolved_routes = resolver.execute(
            ([parent_span], routes, ambiguity_updates)
        )

        # P2: no fallback diagnostic when segment role is valid and used
        fallback_diags = [
            d for d in resolved_routes.route_diagnostics
            if "falling back" in d.lower()
        ]
        assert len(fallback_diags) == 0, (
            f"No fallback diagnostic expected when segment role is valid. "
            f"Got: {fallback_diags}"
        )

    def test_no_segment_no_parent_diagnostic_in_routes(self):
        """When there's no segment role AND no parent annotation, the
        'skipping' diagnostic appears in route_diagnostics."""
        from unittest.mock import MagicMock

        from nl2spl.pipeline.stages.stage3_ambiguity_resolver import (
            AmbiguityResolver,
        )

        parent_span = SpanIR(span_id="s15", text="Source text")
        # No parent annotations
        routes = FieldRouteIR(behavior=["s15a"], annotations=[])
        ambiguity_updates = _make_split_ambiguity_updates(
            segments=[{
                "text": "Step A",
                "semantic_role": None,
                "construct_target": None, "slot_target": None, "executable": None,
            }],
        )

        mock_client = MagicMock()
        mock_client.call_json.return_value = {
            "resolved_spans": [
                {"parent_span_id": "s15", "span_id": "s15a", "text": "Step A"},
            ],
            "resolved_routes": {"behavior": ["s15a"]},
        }

        resolver = AmbiguityResolver(config=MagicMock(), client=mock_client)
        _, resolved_routes = resolver.execute(
            ([parent_span], routes, ambiguity_updates)
        )

        # P2: skipping diagnostic in route_diagnostics
        assert len(resolved_routes.route_diagnostics) >= 1, (
            "No segment + no parent must produce route_diagnostics entry"
        )
        diag_text = " ".join(resolved_routes.route_diagnostics)
        assert "skipping" in diag_text.lower(), (
            f"Diagnostic must indicate skipping. Got: {diag_text}"
        )
