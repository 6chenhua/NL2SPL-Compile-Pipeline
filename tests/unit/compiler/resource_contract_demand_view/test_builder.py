"""Phase A tests for DemandViewBuilder.

Covers all 15 test requirements from the implementation plan, Section 4.5,
PLUS builder-triggered scenarios for EVERY Phase A diagnostic kind.
"""

from __future__ import annotations

import pytest

from nl2spl.compiler.resource_contract_demand_view import (
    DemandViewBuilder,
    ViewDiagnostic,
    ViewDiagnosticProjector,
)
from nl2spl.compiler.resource_contract_demand_view.diagnostics import (
    RESOURCE_CONTRACT_AMBIGUOUS_MULTI_DIRECTION_SPAN,
    RESOURCE_CONTRACT_ANNOTATION_CONFLICTING_DIRECTION,
    RESOURCE_CONTRACT_ANNOTATION_CONFLICTING_REQUIREDNESS,
    RESOURCE_CONTRACT_ANNOTATION_MISSING_DIRECTION,
    RESOURCE_CONTRACT_ANNOTATION_MISSING_REQUIREDNESS,
    RESOURCE_CONTRACT_DUPLICATE_DEMAND_ID,
    RESOURCE_CONTRACT_INVALID_ANNOTATION_CONTRACT,
    RESOURCE_CONTRACT_MULTI_ANNOTATION_REQUIRES_SPLIT,
)
from nl2spl.ir.diagnostics import CompileDiagnostic
from nl2spl.ir.field_route_ir import FieldRouteIR, RouteAnnotation
from nl2spl.ir.span_ir import SpanIR

# =============================================================================
# Helpers
# =============================================================================


def _span(
    span_id: str,
    text: str,
    section_id: str | None = None,
    packet_id: str | None = None,
) -> SpanIR:
    return SpanIR(
        span_id=span_id,
        text=text,
        source_section_id=section_id,
        source_packet_id=packet_id,
    )


def _output_contract_annotation(
    span_id: str,
    section_id: str = "sec_required_outputs",
    packet_id: str | None = None,
    requiredness: str | None = None,
) -> RouteAnnotation:
    pid = packet_id or f"p_list_item_{span_id}"
    ann = RouteAnnotation(
        span_id=span_id,
        field="resources",
        semantic_role="output_contract",
        route_family="resource_contract",
        construct_target="RESOURCE_CONTRACT",
        slot_target="output",
        executable=False,
        source_section_id=section_id,
        source_packet_id=pid,
    )
    if requiredness is not None:
        ann.metadata["requiredness"] = requiredness
    return ann


def _input_contract_annotation(
    span_id: str,
    section_id: str = "sec_inputs_for_each_run",
    packet_id: str | None = None,
    requiredness: str | None = None,
) -> RouteAnnotation:
    pid = packet_id or f"p_list_item_{span_id}"
    ann = RouteAnnotation(
        span_id=span_id,
        field="resources",
        semantic_role="input_contract",
        route_family="resource_contract",
        construct_target="RESOURCE_CONTRACT",
        slot_target="input",
        executable=False,
        source_section_id=section_id,
        source_packet_id=pid,
    )
    if requiredness is not None:
        ann.metadata["requiredness"] = requiredness
    return ann


# =============================================================================
# Test 1 & 2: input_contract / output_contract annotation → demand
# =============================================================================


def test_input_contract_annotation_generates_input_demand() -> None:
    """input_contract annotation produces an input demand with correct direction."""
    spans = [_span("s8", "Topic summary", section_id="sec_inputs_for_each_run")]
    routes = FieldRouteIR(
        behavior=[],
        annotations=[_input_contract_annotation("s8", requiredness="required")],
    )

    view = DemandViewBuilder().build(spans, routes)

    assert len(view.demands) == 1
    demand = view.demands[0]
    assert demand.direction == "input"
    assert demand.demand_id == "rcd_input_s8"
    assert demand.requiredness == "required"
    assert demand.required is True
    assert demand.evidence_source == "stage2_annotation"
    assert demand.view_status == "valid"


def test_output_contract_annotation_generates_output_demand() -> None:
    """output_contract annotation produces an output demand with correct direction."""
    spans = [_span("s11", "Finished draft", section_id="sec_required_outputs")]
    routes = FieldRouteIR(
        behavior=[],
        annotations=[_output_contract_annotation("s11", requiredness="required")],
    )

    view = DemandViewBuilder().build(spans, routes)

    assert len(view.demands) == 1
    demand = view.demands[0]
    assert demand.direction == "output"
    assert demand.demand_id == "rcd_output_s11"
    assert demand.requiredness == "required"
    assert demand.required is True


# =============================================================================
# Test 3: stable demand id
# =============================================================================


def test_demand_id_is_stable() -> None:
    """Demand IDs are stable: rcd_{direction}_{span_id}."""
    spans = [
        _span("s1", "Input A", section_id="sec_inputs_for_each_run"),
        _span("s2", "Output B", section_id="sec_required_outputs"),
    ]
    routes = FieldRouteIR(
        behavior=[],
        annotations=[
            _input_contract_annotation("s1", requiredness="required"),
            _output_contract_annotation("s2", requiredness="required"),
        ],
    )

    view = DemandViewBuilder().build(spans, routes)

    demand_ids = {d.demand_id for d in view.demands}
    assert demand_ids == {"rcd_input_s1", "rcd_output_s2"}


def test_demand_id_idempotent() -> None:
    """Building the same view twice produces identical demand IDs."""
    spans = [_span("s1", "Input A", section_id="sec_inputs_for_each_run")]
    routes = FieldRouteIR(
        behavior=[],
        annotations=[_input_contract_annotation("s1", requiredness="required")],
    )

    view1 = DemandViewBuilder().build(spans, routes)
    view2 = DemandViewBuilder().build(spans, routes)

    assert [d.demand_id for d in view1.demands] == [
        d.demand_id for d in view2.demands
    ]


# =============================================================================
# Test 4: provenance preserved
# =============================================================================


def test_provenance_preserved() -> None:
    """DemandView preserves span, section, packet, and hint provenance."""
    spans = [
        _span("s11", "Finished draft (Word or Google Doc...)",
              section_id="sec_required_outputs",
              packet_id="p_list_item_finished_draft"),
    ]
    ann = _output_contract_annotation(
        "s11",
        section_id="sec_required_outputs",
        packet_id="p_list_item_finished_draft",
        requiredness="required",
    )
    ann.source_hint_ids = ["h1", "h2"]

    routes = FieldRouteIR(behavior=[], annotations=[ann])

    view = DemandViewBuilder().build(spans, routes)

    assert len(view.demands) == 1
    demand = view.demands[0]
    assert demand.source_span_ids == ("s11",)
    assert demand.source_section_id == "sec_required_outputs"
    assert demand.source_packet_id == "p_list_item_finished_draft"
    assert "h1" in demand.source_hint_ids
    assert "h2" in demand.source_hint_ids


# =============================================================================
# Test 5: builder does not receive CanonicalCompileInput
# =============================================================================


def test_builder_signature_does_not_accept_canonical_input() -> None:
    """DemandViewBuilder.build() only accepts spans and routes, not CanonicalCompileInput."""
    import inspect

    sig = inspect.signature(DemandViewBuilder.build)
    params = list(sig.parameters.keys())
    non_self_params = [p for p in params if p != "self"]
    assert "resolved_spans" in non_self_params
    assert "resolved_routes" in non_self_params
    assert "canonical_input" not in non_self_params
    assert "raw_text" not in non_self_params
    assert "llm_client" not in non_self_params


# =============================================================================
# Test 6: construct_target=RESOURCE_CONTRACT but direction missing → NO default
# =============================================================================


def test_construct_target_without_direction_produces_no_demand() -> None:
    """RESOURCE_CONTRACT alone must not select a contract annotation."""
    spans = [_span("s5", "Some text")]
    ann = RouteAnnotation(
        span_id="s5",
        field="behavior",
        semantic_role=None,
        route_family="resource_contract",
        construct_target="RESOURCE_CONTRACT",
        slot_target=None,
        executable=False,
        source_section_id="sec_required_outputs",
    )
    routes = FieldRouteIR(behavior=["s5"], annotations=[ann])

    view = DemandViewBuilder().build(spans, routes)

    assert len(view.demands) == 0
    assert len(view.view_diagnostics) >= 1, "ARC5: suspicious resource-contract annotations produce visible diagnostic"


def test_route_family_and_slot_target_without_contract_role_do_not_create_demand() -> None:
    """Only input_contract/output_contract semantic roles authorize demands."""
    spans = [_span("s6", "Profile domain")]
    ann = RouteAnnotation(
        span_id="s6",
        field="resources",
        semantic_role="profile_domain",
        route_family="resource_contract",
        construct_target="RESOURCE_CONTRACT",
        slot_target="input",
        executable=False,
        source_section_id="sec_inputs",
    )
    ann.metadata["requiredness"] = "required"
    routes = FieldRouteIR(behavior=["s6"], annotations=[ann])

    view = DemandViewBuilder().build(spans, routes)

    assert len(view.demands) == 0
    assert len(view.view_diagnostics) >= 1, "ARC5: suspicious resource-contract annotations produce visible diagnostic"


# =============================================================================
# Test 7: direction conflict → no demand
# =============================================================================


def test_empty_annotations_returns_empty_view() -> None:
    """No contract annotations means zero demands, zero diagnostics."""
    spans = [_span("s1", "General text")]
    routes = FieldRouteIR(behavior=["s1"], annotations=[])

    view = DemandViewBuilder().build(spans, routes)

    assert len(view.demands) == 0
    assert len(view.view_diagnostics) == 0


def test_non_contract_annotations_produce_no_demands() -> None:
    """Annotations without resource contract semantics produce no demands."""
    spans = [_span("s1", "Some text")]
    ann = RouteAnnotation(
        span_id="s1",
        field="behavior",
        semantic_role="action",
        executable=True,
    )
    routes = FieldRouteIR(behavior=["s1"], annotations=[ann])

    view = DemandViewBuilder().build(spans, routes)

    assert len(view.demands) == 0


# =============================================================================
# P1 fix: intra-annotation direction conflict
#   semantic_role + slot_target disagree → conflicting_direction, no demand
# =============================================================================


def test_intra_annotation_direction_conflict_yields_no_demand() -> None:
    """Single annotation: semantic_role=input_contract + slot_target=output → conflict."""
    spans = [_span("s3", "Conflicting signals")]
    ann = RouteAnnotation(
        span_id="s3",
        field="behavior",
        semantic_role="input_contract",   # signals input
        route_family="resource_contract",
        slot_target="output",              # signals output — CONFLICT
        executable=False,
        source_section_id="sec_mixed",
    )
    routes = FieldRouteIR(behavior=[], annotations=[ann])

    view = DemandViewBuilder().build(spans, routes)

    assert len(view.demands) == 0, (
        "Intra-annotation direction conflict must not generate a demand"
    )
    conflicting = [
        d for d in view.view_diagnostics
        if d.kind == RESOURCE_CONTRACT_ANNOTATION_CONFLICTING_DIRECTION
    ]
    assert len(conflicting) >= 1
    assert "s3" in conflicting[0].span_ids


def test_annotation_with_role_and_metadata_conflict() -> None:
    """semantic_role=output_contract + metadata.direction=input → conflict."""
    spans = [_span("s7", "Metadata vs role")]
    ann = RouteAnnotation(
        span_id="s7",
        field="behavior",
        semantic_role="output_contract",
        route_family="resource_contract",
        slot_target="output",
        executable=False,
    )
    ann.metadata["direction"] = "input"  # conflicts with semantic_role=output_contract
    routes = FieldRouteIR(behavior=[], annotations=[ann])

    view = DemandViewBuilder().build(spans, routes)

    assert len(view.demands) == 0
    conflicting = [
        d for d in view.view_diagnostics
        if d.kind == RESOURCE_CONTRACT_ANNOTATION_CONFLICTING_DIRECTION
    ]
    assert len(conflicting) >= 1


# =============================================================================
# Test 8: requiredness missing → diagnostic (demand still generated)
# =============================================================================


def test_requiredness_unspecified_emits_diagnostic_but_generates_demand() -> None:
    """When requiredness is unspecified, demand is still created + diagnostic emitted."""
    spans = [_span("s11", "Output item", section_id="sec_required_outputs")]
    routes = FieldRouteIR(
        behavior=[],
        annotations=[_output_contract_annotation("s11")],
    )

    view = DemandViewBuilder().build(spans, routes)

    assert len(view.demands) == 1
    assert view.demands[0].requiredness == "unspecified"
    assert view.demands[0].required is None
    assert view.demands[0].view_status == "valid"

    missing_req = [
        d for d in view.view_diagnostics
        if d.kind == RESOURCE_CONTRACT_ANNOTATION_MISSING_REQUIREDNESS
    ]
    assert len(missing_req) >= 1
    assert view.demands[0].demand_id in missing_req[0].message


def test_requiredness_optional_produces_required_false() -> None:
    """Requiredness=optional → required=False (not None)."""
    spans = [_span("s9", "Optional input",
                   section_id="sec_inputs_for_each_run")]
    routes = FieldRouteIR(
        behavior=[],
        annotations=[_input_contract_annotation("s9", requiredness="optional")],
    )

    view = DemandViewBuilder().build(spans, routes)

    assert len(view.demands) == 1
    assert view.demands[0].requiredness == "optional"
    assert view.demands[0].required is False


# =============================================================================
# P1 fix: requiredness CONFLICT (not missing)
#   Multiple annotations disagree on requiredness → conflicting_requiredness,
#   demand kept but view_status=invalid_requiredness
# =============================================================================


def test_requiredness_conflict_yields_demand_invalid_status() -> None:
    """Two annotations for same demand disagree on requiredness → conflict diag,
    demand generated but view_status=invalid_requiredness."""
    spans = [_span("s10", "Conflicting requiredness")]
    ann_a = _output_contract_annotation(
        "s10", requiredness="required", packet_id="p_same",
    )
    ann_b = _output_contract_annotation(
        "s10", requiredness="optional", packet_id="p_same",
    )
    routes = FieldRouteIR(behavior=[], annotations=[ann_a, ann_b])

    view = DemandViewBuilder().build(spans, routes)

    # Both annotations share span+direction+packet, so they merge into one demand.
    # Requiredness conflict should be detected.
    conflicting = [
        d for d in view.view_diagnostics
        if d.kind == RESOURCE_CONTRACT_ANNOTATION_CONFLICTING_REQUIREDNESS
    ]
    assert len(conflicting) >= 1, (
        "Conflicting requiredness must emit a diagnostic"
    )
    # Demand should exist but be invalid
    assert len(view.demands) == 1
    assert view.demands[0].view_status == "invalid_requiredness"
    assert view.demands[0].requiredness == "unspecified"
    assert view.demands[0].required is None


# =============================================================================
# Test 9: same span input+output → default conflict
# =============================================================================


def test_same_span_input_and_output_triggers_ambiguous_conflict() -> None:
    """When the same span has both input_contract and output_contract (same
    packet), the builder emits AMBIGUOUS_MULTI_DIRECTION diagnostic and no demand."""
    spans = [_span("s4", "Ambiguous data",
                   section_id="sec_required_outputs")]
    routes = FieldRouteIR(
        behavior=[],
        annotations=[
            _input_contract_annotation("s4", packet_id="p_same"),
            _output_contract_annotation("s4", packet_id="p_same"),
        ],
    )

    view = DemandViewBuilder().build(spans, routes)

    assert len(view.demands) == 0
    ambiguous = [
        d for d in view.view_diagnostics
        if d.kind == RESOURCE_CONTRACT_AMBIGUOUS_MULTI_DIRECTION_SPAN
    ]
    assert len(ambiguous) >= 1


# =============================================================================
# Test 10: legitimate multi-demand (distinct packets)
# =============================================================================


def test_different_packet_ids_allows_both_directions() -> None:
    """When input and output annotations have different source_packet_ids,
    both demands are generated (legitimate multi-demand)."""
    spans = [
        _span("s4", "Multi-contract data",
              section_id="sec_required_outputs",
              packet_id="p_input_item"),
    ]
    routes = FieldRouteIR(
        behavior=[],
        annotations=[
            _input_contract_annotation("s4", packet_id="p_input_item",
                                        requiredness="required"),
            _output_contract_annotation("s4", packet_id="p_output_item",
                                         requiredness="required"),
        ],
    )

    view = DemandViewBuilder().build(spans, routes)

    assert len(view.demands) == 2
    directions = {d.direction for d in view.demands}
    assert directions == {"input", "output"}

    split_diags = [
        d for d in view.view_diagnostics
        if d.kind == RESOURCE_CONTRACT_MULTI_ANNOTATION_REQUIRES_SPLIT
    ]
    assert len(split_diags) >= 1


# =============================================================================
# Test 11: header title does NOT generate demand
# =============================================================================


def test_header_title_does_not_generate_demand() -> None:
    """The builder does not use section titles or text to infer demands."""
    spans = [
        _span("s11", "Finished draft",
              section_id="sec_required_outputs"),
    ]
    routes = FieldRouteIR(behavior=["s11"], annotations=[])

    view = DemandViewBuilder().build(spans, routes)

    assert len(view.demands) == 0


def test_section_title_not_used_even_with_packets() -> None:
    """Even if span falls under 'required outputs', builder does not inspect titles."""
    spans = [
        _span("s11", "Some output text",
              section_id="sec_required_outputs",
              packet_id="p_list_item_11"),
    ]
    routes = FieldRouteIR(behavior=["s11"], annotations=[])

    view = DemandViewBuilder().build(spans, routes)

    assert len(view.demands) == 0


# =============================================================================
# Test 12: evidence text does not determine direction or requiredness
# =============================================================================


def test_evidence_text_does_not_override_direction() -> None:
    """Even if evidence text contains 'input', direction comes from annotation."""
    spans = [_span("s1", "This is an output, not input",
                   section_id="sec_required_outputs")]
    routes = FieldRouteIR(
        behavior=[],
        annotations=[_output_contract_annotation("s1", requiredness="required")],
    )

    view = DemandViewBuilder().build(spans, routes)

    assert len(view.demands) == 1
    assert view.demands[0].direction == "output"


def test_evidence_text_does_not_override_requiredness() -> None:
    """Evidence text 'optional' does not change requiredness from annotation."""
    spans = [_span("s1", "Optional data",
                   section_id="sec_required_outputs")]
    ann = _output_contract_annotation("s1", requiredness="required")
    routes = FieldRouteIR(behavior=[], annotations=[ann])

    view = DemandViewBuilder().build(spans, routes)

    assert len(view.demands) == 1
    assert view.demands[0].requiredness == "required"
    assert view.demands[0].required is True


# =============================================================================
# Test 13: payload deterministic
# =============================================================================


def test_to_payload_is_deterministic() -> None:
    """to_payload() produces identical output for identical inputs."""
    spans = [
        _span("s1", "Input A", section_id="sec_inputs_for_each_run"),
        _span("s2", "Output B", section_id="sec_required_outputs"),
    ]
    anns = [
        _input_contract_annotation("s1", requiredness="required"),
        _output_contract_annotation("s2", requiredness="optional"),
    ]

    def build_and_payload() -> dict:
        routes = FieldRouteIR(behavior=[], annotations=anns)
        view = DemandViewBuilder().build(spans, routes)
        return view.to_payload()

    p1 = build_and_payload()
    p2 = build_and_payload()
    assert p1 == p2


def test_payload_contains_requiredness() -> None:
    """Payload includes the requiredness field for each demand."""
    spans = [_span("s1", "Input A", section_id="sec_inputs_for_each_run")]
    routes = FieldRouteIR(
        behavior=[],
        annotations=[_input_contract_annotation("s1", requiredness="required")],
    )

    view = DemandViewBuilder().build(spans, routes)
    payload = view.to_payload()

    assert len(payload["demands"]) == 1
    assert payload["demands"][0]["requiredness"] == "required"
    assert payload["demands"][0]["required"] is True


# =============================================================================
# Test 14: diagnostics deterministic
# =============================================================================


def test_diagnostics_deterministic() -> None:
    """The same conflict produces deterministic diagnostics."""
    spans = [_span("s4", "Conflict data")]
    anns = [
        _input_contract_annotation("s4", packet_id="p_same"),
        _output_contract_annotation("s4", packet_id="p_same"),
    ]

    def build_and_diags() -> list[dict]:
        routes = FieldRouteIR(behavior=[], annotations=anns)
        view = DemandViewBuilder().build(spans, routes)
        return [d.to_payload() for d in view.view_diagnostics]

    d1 = build_and_diags()
    d2 = build_and_diags()
    assert d1 == d2


def test_no_direction_diagnostic_details() -> None:
    """Non-contract RESOURCE_CONTRACT annotations are not DemandView inputs."""
    spans = [_span("s99", "Mystery text")]
    ann = RouteAnnotation(
        span_id="s99",
        field="behavior",
        semantic_role=None,
        route_family="resource_contract",
        construct_target="RESOURCE_CONTRACT",
        slot_target=None,
        executable=False,
    )
    routes = FieldRouteIR(behavior=["s99"], annotations=[ann])

    view = DemandViewBuilder().build(spans, routes)

    assert len(view.demands) == 0
    assert len(view.view_diagnostics) >= 1, "ARC5: suspicious resource-contract annotations produce visible diagnostic"


# =============================================================================
# P2 fix: duplicate demand_id → diagnostic (NOT silent skip)
# =============================================================================


def test_duplicate_demand_id_emits_diagnostic() -> None:
    """Same span + same direction + DIFFERENT packets → duplicate demand_id
    must emit duplicate_demand_id diagnostic."""
    spans = [_span("s5", "Shared span text")]
    ann_a = _output_contract_annotation(
        "s5", packet_id="p_item_a", requiredness="required",
    )
    ann_b = _output_contract_annotation(
        "s5", packet_id="p_item_b", requiredness="required",
    )
    routes = FieldRouteIR(behavior=[], annotations=[ann_a, ann_b])

    view = DemandViewBuilder().build(spans, routes)

    # Both have same span+direction, different packets → duplicate demand_id
    dup_diags = [
        d for d in view.view_diagnostics
        if d.kind == RESOURCE_CONTRACT_DUPLICATE_DEMAND_ID
    ]
    assert len(dup_diags) >= 1, (
        f"Expected duplicate_demand_id diagnostic; got: "
        f"{[d.kind for d in view.view_diagnostics]}"
    )
    assert "rcd_output_s5" in dup_diags[0].message
    # Exactly one demand should exist (first one wins; second is skipped)
    assert len(view.demands) == 1


# =============================================================================
# P3 fix: builder-triggered scenario for EVERY Phase A diagnostic kind
# =============================================================================


def test_conflicting_direction_builder_scenario() -> None:
    """Builder emits CONFLICTING_DIRECTION when intra-annotation signals disagree."""
    spans = [_span("s3", "Conflicting")]
    ann = RouteAnnotation(
        span_id="s3",
        field="behavior",
        semantic_role="input_contract",
        route_family="resource_contract",
        slot_target="output",  # conflict
        executable=False,
    )
    routes = FieldRouteIR(behavior=[], annotations=[ann])

    view = DemandViewBuilder().build(spans, routes)
    kinds = {d.kind for d in view.view_diagnostics}
    assert RESOURCE_CONTRACT_ANNOTATION_CONFLICTING_DIRECTION in kinds


def test_conflicting_requiredness_builder_scenario() -> None:
    """Builder emits CONFLICTING_REQUIREDNESS when two annotations disagree."""
    spans = [_span("s10", "Data")]
    ann_a = _output_contract_annotation("s10", requiredness="required",
                                         packet_id="p_same")
    ann_b = _output_contract_annotation("s10", requiredness="optional",
                                         packet_id="p_same")
    routes = FieldRouteIR(behavior=[], annotations=[ann_a, ann_b])

    view = DemandViewBuilder().build(spans, routes)
    kinds = {d.kind for d in view.view_diagnostics}
    assert RESOURCE_CONTRACT_ANNOTATION_CONFLICTING_REQUIREDNESS in kinds
    assert view.demands[0].view_status == "invalid_requiredness"


def test_duplicate_demand_id_builder_scenario() -> None:
    """Builder emits DUPLICATE_DEMAND_ID for same span+direction+different packets."""
    spans = [_span("s5", "Text")]
    ann_a = _output_contract_annotation("s5", packet_id="p_a", requiredness="required")
    ann_b = _output_contract_annotation("s5", packet_id="p_b", requiredness="required")
    routes = FieldRouteIR(behavior=[], annotations=[ann_a, ann_b])

    view = DemandViewBuilder().build(spans, routes)
    kinds = {d.kind for d in view.view_diagnostics}
    assert RESOURCE_CONTRACT_DUPLICATE_DEMAND_ID in kinds


def test_missing_direction_builder_scenario() -> None:
    """RESOURCE_CONTRACT without a contract role is ignored, not inferred."""
    spans = [_span("s99", "Mystery")]
    ann = RouteAnnotation(
        span_id="s99",
        field="behavior",
        semantic_role=None,
        route_family=None,
        construct_target="RESOURCE_CONTRACT",
        slot_target=None,
        executable=False,
    )
    routes = FieldRouteIR(behavior=[], annotations=[ann])

    view = DemandViewBuilder().build(spans, routes)
    assert len(view.demands) == 0
    assert len(view.view_diagnostics) >= 1, "ARC5: suspicious resource-contract annotations produce visible diagnostic"


def test_missing_requiredness_builder_scenario() -> None:
    """Builder emits MISSING_REQUIREDNESS when annotation has no requiredness metadata."""
    spans = [_span("s11", "Data")]
    routes = FieldRouteIR(
        behavior=[],
        annotations=[_output_contract_annotation("s11")],  # no requiredness
    )

    view = DemandViewBuilder().build(spans, routes)
    kinds = {d.kind for d in view.view_diagnostics}
    assert RESOURCE_CONTRACT_ANNOTATION_MISSING_REQUIREDNESS in kinds


def test_ambiguous_multi_direction_builder_scenario() -> None:
    """Builder emits AMBIGUOUS_MULTI_DIRECTION for same span input+output."""
    spans = [_span("s4", "Data")]
    routes = FieldRouteIR(
        behavior=[],
        annotations=[
            _input_contract_annotation("s4", packet_id="p_same"),
            _output_contract_annotation("s4", packet_id="p_same"),
        ],
    )

    view = DemandViewBuilder().build(spans, routes)
    kinds = {d.kind for d in view.view_diagnostics}
    assert RESOURCE_CONTRACT_AMBIGUOUS_MULTI_DIRECTION_SPAN in kinds


def test_invalid_annotation_contract_builder_scenario() -> None:
    """Builder emits INVALID_ANNOTATION_CONTRACT for output_contract with executable=True."""
    spans = [_span("s7", "Invalid contract")]
    ann = RouteAnnotation(
        span_id="s7",
        field="resources",
        semantic_role="output_contract",
        route_family="resource_contract",
        construct_target="RESOURCE_CONTRACT",
        slot_target="output",
        executable=True,  # ← violates contract: must be False
        source_section_id="sec_required_outputs",
    )
    routes = FieldRouteIR(behavior=[], annotations=[ann])

    view = DemandViewBuilder().build(spans, routes)

    kinds = {d.kind for d in view.view_diagnostics}
    assert RESOURCE_CONTRACT_INVALID_ANNOTATION_CONTRACT in kinds
    assert len(view.demands) == 0, (
        "Invalid contract annotation must not generate a demand"
    )


def test_input_contract_with_executable_true_also_invalid() -> None:
    """input_contract with executable=True is also invalid."""
    spans = [_span("s8", "Invalid input contract")]
    ann = RouteAnnotation(
        span_id="s8",
        field="resources",
        semantic_role="input_contract",
        route_family="resource_contract",
        construct_target="RESOURCE_CONTRACT",
        slot_target="input",
        executable=True,
        source_section_id="sec_inputs_for_each_run",
    )
    routes = FieldRouteIR(behavior=[], annotations=[ann])

    view = DemandViewBuilder().build(spans, routes)

    kinds = {d.kind for d in view.view_diagnostics}
    assert RESOURCE_CONTRACT_INVALID_ANNOTATION_CONTRACT in kinds
    assert len(view.demands) == 0


def test_valid_annotations_unaffected_by_invalid_in_same_route() -> None:
    """A valid contract annotation still produces a demand even when an
    invalid one exists in the same route for a different span."""
    spans = [
        _span("s7", "Invalid contract", section_id="sec_required_outputs"),
        _span("s10", "Valid output", section_id="sec_required_outputs"),
    ]
    routes = FieldRouteIR(
        behavior=[],
        annotations=[
            RouteAnnotation(
                span_id="s7",
                field="resources",
                semantic_role="output_contract",
                route_family="resource_contract",
                construct_target="RESOURCE_CONTRACT",
                slot_target="output",
                executable=True,  # invalid
                source_section_id="sec_required_outputs",
            ),
            _output_contract_annotation("s10", requiredness="required"),
        ],
    )

    view = DemandViewBuilder().build(spans, routes)

    kinds = {d.kind for d in view.view_diagnostics}
    assert RESOURCE_CONTRACT_INVALID_ANNOTATION_CONTRACT in kinds
    # Valid annotation for s10 must still produce a demand
    assert len(view.demands) == 1
    assert view.demands[0].demand_id == "rcd_output_s10"


def test_multi_annotation_requires_split_builder_scenario() -> None:
    """Builder emits MULTI_ANNOTATION_REQUIRES_SPLIT for distinct-packet multi-direction."""
    spans = [_span("s4", "Data")]
    routes = FieldRouteIR(
        behavior=[],
        annotations=[
            _input_contract_annotation("s4", packet_id="p_a", requiredness="required"),
            _output_contract_annotation("s4", packet_id="p_b", requiredness="required"),
        ],
    )

    view = DemandViewBuilder().build(spans, routes)
    kinds = {d.kind for d in view.view_diagnostics}
    assert RESOURCE_CONTRACT_MULTI_ANNOTATION_REQUIRES_SPLIT in kinds


# =============================================================================
# Immutability tests
# =============================================================================


def test_demand_view_is_frozen() -> None:
    """ResourceContractDemandView and DemandViewDemand must be frozen."""
    spans = [_span("s1", "Data")]
    routes = FieldRouteIR(
        behavior=[],
        annotations=[_input_contract_annotation("s1", requiredness="required")],
    )
    view = DemandViewBuilder().build(spans, routes)

    # Attempt to set an attribute on DemandViewDemand
    demand = view.demands[0]
    with pytest.raises(Exception):  # noqa: B017 - FrozenInstanceError or similar
        demand.direction = "output"  # type: ignore[misc]

    # Attempt to set an attribute on ViewDiagnostic
    if view.view_diagnostics:
        diag = view.view_diagnostics[0]
        with pytest.raises(Exception):  # noqa: B017 - FrozenInstanceError or similar
            diag.kind = "fake"  # type: ignore[misc]

    # Attempt to set on ResourceContractDemandView
    with pytest.raises(Exception):  # noqa: B017 - FrozenInstanceError or similar
        view.demands = ()  # type: ignore[misc]


def test_view_contents_unchanged_after_external_modification() -> None:
    """External modification of source data does not affect built view."""
    spans = [_span("s1", "Original text")]
    ann = _input_contract_annotation("s1", requiredness="required")
    routes = FieldRouteIR(behavior=[], annotations=[ann])

    view = DemandViewBuilder().build(spans, routes)

    # Mutate the source objects after building
    spans[0].span_id = "s_mutated"
    ann.semantic_role = "output_contract"

    # View must be unchanged
    assert view.demands[0].demand_id == "rcd_input_s1"
    assert view.demands[0].direction == "input"
    assert view.demands[0].evidence_text == "Original text"


# =============================================================================
# Test 15: ViewDiagnosticProjector → CompileDiagnostic
# =============================================================================


def test_projector_converts_single_diagnostic() -> None:
    """Projector maps ViewDiagnostic to CompileDiagnostic with correct fields."""
    diag = ViewDiagnostic(
        kind=RESOURCE_CONTRACT_ANNOTATION_MISSING_DIRECTION,
        severity="warning",
        message="No direction for span s1",
        span_ids=("s1",),
        demand_id=None,
    )

    result = ViewDiagnosticProjector.project_list([diag])

    assert len(result) == 1
    cd = result[0]
    assert isinstance(cd, CompileDiagnostic)
    assert cd.kind == RESOURCE_CONTRACT_ANNOTATION_MISSING_DIRECTION
    assert cd.severity == "warning"
    assert cd.message == "No direction for span s1"
    assert cd.source_span_ids == ["s1"]
    assert cd.target_ref == "span:s1"
    assert not cd.blocks_rendering
    assert not cd.blocks_completion


def test_projector_converts_diagnostic_with_demand_id() -> None:
    """Projector includes demand_id in target_ref when available."""
    diag = ViewDiagnostic(
        kind=RESOURCE_CONTRACT_ANNOTATION_MISSING_REQUIREDNESS,
        severity="info",
        message="Requiredness unspecified for demand rcd_input_s1",
        span_ids=("s1",),
        demand_id="rcd_input_s1",
    )

    result = ViewDiagnosticProjector.project_list([diag])

    assert len(result) == 1
    cd = result[0]
    assert cd.kind == RESOURCE_CONTRACT_ANNOTATION_MISSING_REQUIREDNESS
    assert cd.target_ref == "rcd_input_s1"
    assert cd.source_span_ids == ["s1"]


def test_projector_projects_from_view() -> None:
    """Projector can take a whole ResourceContractDemandView."""
    spans = [_span("s4", "Conflict data")]
    anns = [
        _input_contract_annotation("s4", packet_id="p_same"),
        _output_contract_annotation("s4", packet_id="p_same"),
    ]
    routes = FieldRouteIR(behavior=[], annotations=anns)
    view = DemandViewBuilder().build(spans, routes)

    assert len(view.view_diagnostics) > 0

    projected = ViewDiagnosticProjector.project(view)

    assert len(projected) == len(view.view_diagnostics)
    for cd in projected:
        assert isinstance(cd, CompileDiagnostic)


def test_projector_handles_empty_diagnostics() -> None:
    """Projector handles empty diagnostic lists gracefully."""
    spans = [_span("s1", "Input A", section_id="sec_inputs_for_each_run")]
    routes = FieldRouteIR(
        behavior=[],
        annotations=[_input_contract_annotation("s1", requiredness="required")],
    )
    view = DemandViewBuilder().build(spans, routes)
    assert len(view.view_diagnostics) == 0

    projected = ViewDiagnosticProjector.project(view)
    assert projected == []


def test_projector_covers_all_phase_a_diagnostic_kinds() -> None:
    """Every Phase A view diagnostic kind can be projected to CompileDiagnostic."""
    phase_a_kinds = [
        RESOURCE_CONTRACT_ANNOTATION_MISSING_DIRECTION,
        RESOURCE_CONTRACT_ANNOTATION_CONFLICTING_DIRECTION,
        RESOURCE_CONTRACT_ANNOTATION_MISSING_REQUIREDNESS,
        RESOURCE_CONTRACT_ANNOTATION_CONFLICTING_REQUIREDNESS,
        RESOURCE_CONTRACT_DUPLICATE_DEMAND_ID,
        RESOURCE_CONTRACT_INVALID_ANNOTATION_CONTRACT,
        RESOURCE_CONTRACT_AMBIGUOUS_MULTI_DIRECTION_SPAN,
        RESOURCE_CONTRACT_MULTI_ANNOTATION_REQUIRES_SPLIT,
    ]

    for kind in phase_a_kinds:
        diag = ViewDiagnostic(
            kind=kind,
            severity="warning",
            message=f"Test diagnostic: {kind}",
            span_ids=("s1",),
            demand_id="rcd_test",
        )
        result = ViewDiagnosticProjector.project_list([diag])
        assert len(result) == 1
        assert result[0].kind == kind


# =============================================================================
# Direction from slot_target / metadata (single source)
# =============================================================================


def test_direction_from_slot_target() -> None:
    """slot_target alone must not authorize a resource contract demand."""

    spans = [_span("s5", "Slot-targeted text")]
    ann = RouteAnnotation(
        span_id="s5",
        field="behavior",
        semantic_role="action",
        route_family="resource_contract",
        construct_target="RESOURCE_CONTRACT",
        slot_target="output",
        executable=False,
    )
    routes = FieldRouteIR(behavior=["s5"], annotations=[ann])

    view = DemandViewBuilder().build(spans, routes)

    assert len(view.demands) == 0
    assert len(view.view_diagnostics) >= 1, "ARC5: suspicious resource-contract annotations produce visible diagnostic"


def test_direction_from_metadata() -> None:
    """metadata.direction alone must not authorize a resource contract demand."""

    spans = [_span("s5", "Metadata-driven text")]
    ann = RouteAnnotation(
        span_id="s5",
        field="behavior",
        route_family="resource_contract",
        construct_target="RESOURCE_CONTRACT",
        executable=False,
    )
    ann.metadata["direction"] = "input"
    routes = FieldRouteIR(behavior=["s5"], annotations=[ann])

    view = DemandViewBuilder().build(spans, routes)

    assert len(view.demands) == 0
    assert len(view.view_diagnostics) >= 1, "ARC5: suspicious resource-contract annotations produce visible diagnostic"


# =============================================================================
# Equivalence: DemandView annotation-derived ↔ old Stage 3.2 annotation-derived
# =============================================================================


def test_equivalence_with_old_planner_annotation_derived_subset() -> None:
    """DemandView must produce the same demand_id, direction, provenance, and
    evidence_text as the old ResourceContractPlanner for annotation-only inputs.

    This equivalence covers: demand_id, direction, source_span_ids,
    source_section_id, source_packet_id, evidence_text.
    It does NOT require requiredness to match.
    """
    from nl2spl.pipeline.stages.stage3_2_resource_contract_planner import (
        ResourceContractPlanner,
    )

    spans = [
        _span("s11", "Finished draft (Word or Google Doc, 200-500 words)",
              section_id="sec_required_outputs",
              packet_id="p_list_item_finished_draft"),
        _span("s8", "Topic summary",
              section_id="sec_inputs_for_each_run",
              packet_id="p_list_item_topic_summary"),
    ]
    routes = FieldRouteIR(
        behavior=[],
        annotations=[
            _output_contract_annotation(
                "s11", section_id="sec_required_outputs",
                packet_id="p_list_item_finished_draft",
            ),
            _input_contract_annotation(
                "s8", section_id="sec_inputs_for_each_run",
                packet_id="p_list_item_topic_summary",
            ),
        ],
    )

    old_plan = ResourceContractPlanner().plan(spans, routes)
    new_view = DemandViewBuilder().build(spans, routes)

    assert len(old_plan.demands) == 2
    assert len(new_view.demands) == 2

    old_by_id = {d.demand_id: d for d in old_plan.demands}
    new_by_id = {d.demand_id: d for d in new_view.demands}

    assert old_by_id.keys() == new_by_id.keys()

    for demand_id in old_by_id:
        old_d = old_by_id[demand_id]
        new_d = new_by_id[demand_id]

        assert new_d.demand_id == old_d.demand_id
        assert new_d.direction == old_d.direction
        assert list(new_d.source_span_ids) == old_d.source_span_ids
        assert new_d.source_section_id == old_d.source_section_id
        assert new_d.source_packet_id == old_d.source_packet_id
        assert new_d.evidence_text == old_d.evidence_text

        assert new_d.evidence_source == "stage2_annotation"
        assert "route_annotation" in old_d.evidence_sources

    for new_d in new_view.demands:
        assert new_d.evidence_source == "stage2_annotation"
