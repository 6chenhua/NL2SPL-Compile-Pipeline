"""Phase 1 tests for ResourceContractPlanner.

Covers:
1. Annotation evidence → demand
2. Deterministic section/list-item evidence without annotation → demand
3. Dedup when annotation and section evidence point to same span
4. Demand does not contain resource_kind/name/data_type
5. Empty section / empty markers do not generate demands
6. Planner warning when list items have no resolved span
"""

from __future__ import annotations

import pytest

from nl2spl.canonical.compile_input import CanonicalCompileInput, RawSection, SemanticPacket
from nl2spl.ir.field_route_ir import FieldRouteIR, RouteAnnotation
from nl2spl.ir.resource_contract_ir import ResourceContractPlanIR
from nl2spl.ir.span_ir import SpanIR
from nl2spl.pipeline.stages.stage3_2_resource_contract_planner import (
    ResourceContractPlanner,
)


# =============================================================================
# Helpers
# =============================================================================


def _span(
    span_id: str,
    text: str,
    section_id: str = "sec_required_outputs",
    packet_id: str | None = None,
) -> SpanIR:
    return SpanIR(
        span_id=span_id,
        text=text,
        source_section_id=section_id,
        source_packet_id=packet_id,
    )


def _output_contract_annotation(span_id: str) -> RouteAnnotation:
    return RouteAnnotation(
        span_id=span_id,
        field="resources",
        semantic_role="output_contract",
        route_family="resource_contract",
        construct_target="RESOURCE_CONTRACT",
        slot_target="output",
        executable=False,
        source_section_id="sec_required_outputs",
        source_packet_id=f"p_list_item_{span_id}",
    )


def _input_contract_annotation(span_id: str) -> RouteAnnotation:
    return RouteAnnotation(
        span_id=span_id,
        field="resources",
        semantic_role="input_contract",
        route_family="resource_contract",
        construct_target="RESOURCE_CONTRACT",
        slot_target="input",
        executable=False,
        source_section_id="sec_inputs_for_each_run",
        source_packet_id=f"p_list_item_{span_id}",
    )


def _raw_section(section_id: str, canonical_title: str) -> RawSection:
    return RawSection(
        section_id=section_id,
        canonical_title=canonical_title,
        original_title=canonical_title.title(),
        text="",
        order=1,
    )


def _list_item_packet(packet_id: str, section_id: str, text: str) -> SemanticPacket:
    return SemanticPacket(
        packet_id=packet_id,
        source_section_id=section_id,
        packet_type="list_item",
        text=text,
        modality="hint",
    )


# =============================================================================
# Test 1: Annotation evidence → demand
# =============================================================================


def test_annotation_evidence_generates_output_demand() -> None:
    """Rule 1: output_contract RouteAnnotation produces an output demand."""
    spans = [
        _span("s11", "Finished draft (Word or Google Doc, 200-500 words)",
              packet_id="p_list_item_finished_draft"),
    ]
    routes = FieldRouteIR(
        behavior=[],
        annotations=[_output_contract_annotation("s11")],
    )

    plan = ResourceContractPlanner().plan(spans, routes)

    assert len(plan.demands) == 1
    demand = plan.demands[0]
    assert demand.demand_id == "rcd_output_s11"
    assert demand.direction == "output"
    assert demand.required is True
    assert demand.evidence_text == "Finished draft (Word or Google Doc, 200-500 words)"
    assert demand.source_span_ids == ["s11"]
    assert demand.source_section_id == "sec_required_outputs"
    assert "route_annotation" in demand.evidence_sources


def test_annotation_evidence_generates_input_demand() -> None:
    """Rule 1: input_contract RouteAnnotation produces an input demand."""
    spans = [
        _span("s8", "Topic summary",
              section_id="sec_inputs_for_each_run",
              packet_id="p_list_item_topic_summary"),
    ]
    routes = FieldRouteIR(
        behavior=[],
        annotations=[_input_contract_annotation("s8")],
    )

    plan = ResourceContractPlanner().plan(spans, routes)

    assert len(plan.demands) == 1
    demand = plan.demands[0]
    assert demand.demand_id == "rcd_input_s8"
    assert demand.direction == "input"
    # Input requiredness depends on text; non-optional input is required
    assert demand.required is True
    assert "route_annotation" in demand.evidence_sources


def test_annotation_evidence_optional_input_is_not_required() -> None:
    """Optional input (starting with 'optional') is marked required=False."""
    spans = [
        _span("s9", "Optional known topics",
              section_id="sec_inputs_for_each_run",
              packet_id="p_list_item_known_topics"),
    ]
    routes = FieldRouteIR(
        behavior=[],
        annotations=[RouteAnnotation(
            span_id="s9",
            field="resources",
            semantic_role="input_contract",
            route_family="resource_contract",
            construct_target="RESOURCE_CONTRACT",
            slot_target="input",
            executable=False,
            source_section_id="sec_inputs_for_each_run",
            source_packet_id="p_list_item_s9",
        )],
    )

    plan = ResourceContractPlanner().plan(spans, routes)
    assert len(plan.demands) == 1
    assert plan.demands[0].required is False


# =============================================================================
# Test 2: Deterministic evidence without annotation → demand
# =============================================================================


def test_deterministic_evidence_without_annotation() -> None:
    """Rule 2: Required Outputs list item without annotation still produces
    an output demand from deterministic section/list-item evidence."""
    spans = [
        _span("s11", "Finished draft (Word or Google Doc, 200-500 words)",
              packet_id="p_list_item_finished_draft"),
    ]
    routes = FieldRouteIR(behavior=[], annotations=[])  # no contract annotations

    canonical = CanonicalCompileInput(
        source_schema="structural_nl",
        schema_version="1.0",
        raw_text="Required outputs:\n- Finished draft (Word or Google Doc...)",
        raw_sections=[
            _raw_section("sec_required_outputs", "required outputs"),
        ],
        semantic_packets=[
            _list_item_packet(
                "p_list_item_finished_draft",
                "sec_required_outputs",
                "Finished draft (Word or Google Doc, 200-500 words, no approval marks)",
            ),
        ],
    )

    plan = ResourceContractPlanner().plan(spans, routes, canonical)

    assert len(plan.demands) == 1
    demand = plan.demands[0]
    assert demand.demand_id == "rcd_output_s11"
    assert demand.direction == "output"
    assert "section_title" in demand.evidence_sources
    assert "list_item_packet" in demand.evidence_sources
    assert "route_annotation" not in demand.evidence_sources


def test_deterministic_input_evidence_without_annotation() -> None:
    """Rule 2: Inputs for each run list item without annotation produces
    an input demand."""
    spans = [
        _span("s8", "Topic summary",
              section_id="sec_inputs_for_each_run",
              packet_id="p_list_item_topic_summary"),
    ]
    routes = FieldRouteIR(behavior=[], annotations=[])

    canonical = CanonicalCompileInput(
        source_schema="structural_nl",
        schema_version="1.0",
        raw_text="Inputs for each run:\n- Topic summary",
        raw_sections=[
            _raw_section("sec_inputs_for_each_run", "inputs for each run"),
        ],
        semantic_packets=[
            _list_item_packet(
                "p_list_item_topic_summary",
                "sec_inputs_for_each_run",
                "Topic summary",
            ),
        ],
    )

    plan = ResourceContractPlanner().plan(spans, routes, canonical)

    assert len(plan.demands) == 1
    demand = plan.demands[0]
    assert demand.demand_id == "rcd_input_s8"
    assert demand.direction == "input"
    assert "section_title" in demand.evidence_sources


# =============================================================================
# Test 3: Dedup — annotation + section evidence for same span
# =============================================================================


def test_dedup_annotation_and_section_evidence_same_span() -> None:
    """Rule 3: annotation and deterministic evidence for the same span+direction
    are merged into one demand, not two."""
    spans = [
        _span("s11", "Finished draft (Word or Google Doc...)",
              packet_id="p_list_item_finished_draft"),
    ]
    routes = FieldRouteIR(
        behavior=[],
        annotations=[_output_contract_annotation("s11")],
    )

    canonical = CanonicalCompileInput(
        source_schema="structural_nl",
        schema_version="1.0",
        raw_text="Required outputs:\n- Finished draft (Word or Google Doc...)",
        raw_sections=[
            _raw_section("sec_required_outputs", "required outputs"),
        ],
        semantic_packets=[
            _list_item_packet(
                "p_list_item_finished_draft",
                "sec_required_outputs",
                "Finished draft (Word or Google Doc...)",
            ),
        ],
    )

    plan = ResourceContractPlanner().plan(spans, routes, canonical)

    # Must be exactly 1 demand, not 2
    assert len(plan.demands) == 1
    demand = plan.demands[0]
    assert demand.demand_id == "rcd_output_s11"
    # Evidence sources should include both
    assert "route_annotation" in demand.evidence_sources
    assert "section_title" in demand.evidence_sources


# =============================================================================
# Test 4: Demand does not contain resource_kind/name/data_type
# =============================================================================


def test_demand_does_not_contain_resource_kind_name_data_type() -> None:
    """The demand IR must be 'pure' — no resource kind, variable name,
    or data type leaks from the planner."""
    spans = [
        _span("s11", "Finished draft (Word or Google Doc...)",
              packet_id="p_list_item_finished_draft"),
    ]
    routes = FieldRouteIR(
        behavior=[],
        annotations=[_output_contract_annotation("s11")],
    )

    plan = ResourceContractPlanner().plan(spans, routes)

    payload = plan.demands[0].to_payload()
    # These keys must NOT exist
    for forbidden in ("resource_kind", "name", "data_type", "kind"):
        assert forbidden not in payload, (
            f"Demand payload must not contain '{forbidden}': {payload}"
        )


# =============================================================================
# Test 5: Empty section / empty marker → no demand
# =============================================================================


def test_empty_section_generates_no_demand() -> None:
    """Empty Required Outputs section with no spans generates zero demands."""
    spans: list[SpanIR] = []
    routes = FieldRouteIR(behavior=[], annotations=[])

    canonical = CanonicalCompileInput(
        source_schema="structural_nl",
        schema_version="1.0",
        raw_text="Required outputs:\n",
        raw_sections=[
            _raw_section("sec_required_outputs", "required outputs"),
        ],
        semantic_packets=[],  # no packets
    )

    plan = ResourceContractPlanner().plan(spans, routes, canonical)

    assert len(plan.demands) == 0


def test_none_marker_packet_generates_no_demand() -> None:
    """A list item with 'None' text should not produce a demand."""
    spans = [
        _span("s12", "None",
              section_id="sec_required_outputs",
              packet_id="p_list_item_none"),
    ]
    routes = FieldRouteIR(behavior=[], annotations=[])

    canonical = CanonicalCompileInput(
        source_schema="structural_nl",
        schema_version="1.0",
        raw_text="Required outputs:\n- None",
        raw_sections=[
            _raw_section("sec_required_outputs", "required outputs"),
        ],
        semantic_packets=[
            _list_item_packet(
                "p_list_item_none",
                "sec_required_outputs",
                "None",
            ),
        ],
    )

    plan = ResourceContractPlanner().plan(spans, routes, canonical)

    # The "None" marker should not generate a demand (empty marker)
    empty_marker_demands = [
        d for d in plan.demands if "none" in d.evidence_text.lower()
    ]
    assert len(empty_marker_demands) == 0, (
        f"None marker should not generate a demand: {empty_marker_demands}"
    )


# =============================================================================
# Test 6: Warning when list item has no resolved span
# =============================================================================


def test_warning_when_list_item_has_no_resolved_span() -> None:
    """If Required Outputs has a list item packet but no span maps to it,
    the planner must emit a warning."""
    spans: list[SpanIR] = []  # no spans at all
    routes = FieldRouteIR(behavior=[], annotations=[])

    canonical = CanonicalCompileInput(
        source_schema="structural_nl",
        schema_version="1.0",
        raw_text="Required outputs:\n- Finished draft\n- Status flag",
        raw_sections=[
            _raw_section("sec_required_outputs", "required outputs"),
        ],
        semantic_packets=[
            _list_item_packet(
                "p_list_item_finished_draft",
                "sec_required_outputs",
                "Finished draft (Word or Google Doc...)",
            ),
            _list_item_packet(
                "p_list_item_status_flag",
                "sec_required_outputs",
                "Status flag",
            ),
        ],
    )

    plan = ResourceContractPlanner().plan(spans, routes, canonical)

    assert len(plan.demands) == 0
    assert len(plan.warnings) == 2  # one per unmapped packet
    assert any("p_list_item_finished_draft" in w for w in plan.warnings)
    assert any("p_list_item_status_flag" in w for w in plan.warnings)


def test_warning_not_emitted_for_empty_markers() -> None:
    """Empty markers that have no resolved span should not produce warnings."""
    spans: list[SpanIR] = []
    routes = FieldRouteIR(behavior=[], annotations=[])

    canonical = CanonicalCompileInput(
        source_schema="structural_nl",
        schema_version="1.0",
        raw_text="Required outputs:\n- None",
        raw_sections=[
            _raw_section("sec_required_outputs", "required outputs"),
        ],
        semantic_packets=[
            _list_item_packet(
                "p_list_item_none",
                "sec_required_outputs",
                "None",
            ),
        ],
    )

    plan = ResourceContractPlanner().plan(spans, routes, canonical)

    assert len(plan.warnings) == 0


# =============================================================================
# Serialization
# =============================================================================


def test_resource_contract_plan_serializes_to_json() -> None:
    """Phase 1 gate: ResourceContractPlanIR must serialize to JSON."""
    import json

    from nl2spl.ir.resource_contract_ir import ResourceContractDemandIR

    plan = ResourceContractPlanIR(
        demands=[
            ResourceContractDemandIR(
                demand_id="rcd_output_s11",
                direction="output",
                required=True,
                evidence_text="Finished draft (Word or Google Doc...)",
                source_span_ids=["s11"],
                source_section_id="sec_required_outputs",
                source_packet_id="p_list_item_finished_draft",
                evidence_sources=["section_title", "list_item_packet"],
            ),
        ],
        warnings=["test warning"],
    )

    payload = plan.to_payload()
    serialized = json.dumps(payload)
    assert "rcd_output_s11" in serialized
    assert "section_title" in serialized


# =============================================================================
# Integration-style: multi-demand plan from section evidence only
# =============================================================================


def test_multiple_output_demands_from_section_only() -> None:
    """Two Required Outputs list items → two output demands, no annotation."""
    spans = [
        _span("s11", "Finished draft (Word or Google Doc...)",
              packet_id="p_list_item_finished_draft"),
        _span("s12", "Status flag (values: drafting, ready for review, approved)",
              packet_id="p_list_item_status_flag"),
    ]
    routes = FieldRouteIR(behavior=[], annotations=[])

    canonical = CanonicalCompileInput(
        source_schema="structural_nl",
        schema_version="1.0",
        raw_text="Required outputs:\n- Finished draft\n- Status flag",
        raw_sections=[
            _raw_section("sec_required_outputs", "required outputs"),
        ],
        semantic_packets=[
            _list_item_packet(
                "p_list_item_finished_draft",
                "sec_required_outputs",
                "Finished draft (Word or Google Doc...)",
            ),
            _list_item_packet(
                "p_list_item_status_flag",
                "sec_required_outputs",
                "Status flag (values: drafting, ready for review, approved)",
            ),
        ],
    )

    plan = ResourceContractPlanner().plan(spans, routes, canonical)

    assert len(plan.demands) == 2
    output_demands = [d for d in plan.demands if d.direction == "output"]
    assert len(output_demands) == 2
    demand_texts = {d.evidence_text for d in output_demands}
    assert "Finished draft (Word or Google Doc...)" in demand_texts
    assert "Status flag (values: drafting, ready for review, approved)" in demand_texts
