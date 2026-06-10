"""Phase C tests — Coverage Validator + diagnostic visibility."""

from __future__ import annotations

import pytest

from nl2spl.canonical.compile_input import (
    CanonicalCompileInput,
    EvidenceRef,
    HardFacts,
    VariableFact,
)
from nl2spl.compiler.resource_contract_demand_view.coverage_validator import (
    ResourceContractAnnotationCoverageValidator,
)
from nl2spl.compiler.resource_contract_demand_view.diagnostics import (
    RESOURCE_CONTRACT_ANNOTATION_COVERAGE_GAP,
    RESOURCE_CONTRACT_ANNOTATION_MISSING,
)
from nl2spl.compiler.resource_contract_demand_view.model import (
    DemandViewDemand,
    ResourceContractDemandView,
)
from nl2spl.compiler.resource_contract_demand_view.projector import (
    ViewDiagnosticProjector,
)
from nl2spl.ir.diagnostics import CompileDiagnostic
from nl2spl.ir.field_route_ir import FieldRouteIR
from nl2spl.ir.span_ir import SpanIR


# =============================================================================
# Helpers
# =============================================================================


def _dvh(did, direction, pkt_id=None, span_id="s1"):
    return DemandViewDemand(
        demand_id=did, direction=direction,
        requiredness="required" if direction == "output" else "optional",
        required=True if direction == "output" else False,
        evidence_text="Test", source_span_ids=(span_id,),
        source_packet_id=pkt_id, evidence_source="stage2_annotation",
        view_status="valid",
    )


def _fact(name, required, pkt_id=None, span_id="s1"):
    return VariableFact(
        name=name, description=name, data_type="text", required=required,
        source_section_id="sec_test",
        evidence=[
            EvidenceRef(
                source_section_id="sec_test",
                source_packet_id=pkt_id,
                source_span_ids=[span_id] if span_id else [],
            ),
        ],
    )


# =============================================================================
# Happy path: fact has matching demand → no diagnostic
# =============================================================================


def test_fact_with_matching_demand_by_packet_id():
    validator = ResourceContractAnnotationCoverageValidator()
    dv = ResourceContractDemandView(demands=(
        _dvh("rcd_out_s1", "output", pkt_id="p_list_draft"),
    ))
    ci = CanonicalCompileInput(
        source_schema="structural_nl", schema_version="1.0", raw_text="",
        hard_facts=HardFacts(
            inputs=[],
            outputs=[_fact("draft", True, pkt_id="p_list_draft")],
        ),
    )
    diags = validator.validate(ci, [], FieldRouteIR(), dv)
    assert diags == []


def test_fact_with_matching_demand_by_span_id():
    validator = ResourceContractAnnotationCoverageValidator()
    dv = ResourceContractDemandView(demands=(
        _dvh("rcd_in_s2", "input", span_id="s2"),
    ))
    ci = CanonicalCompileInput(
        source_schema="structural_nl", schema_version="1.0", raw_text="",
        hard_facts=HardFacts(
            inputs=[_fact("topic", True, span_id="s2")],
            outputs=[],
        ),
    )
    diags = validator.validate(ci, [], FieldRouteIR(), dv)
    assert diags == []


# =============================================================================
# Gap: fact without matching demand → diagnostic
# =============================================================================


def test_unmatched_output_fact_coverage_gap():
    validator = ResourceContractAnnotationCoverageValidator()
    dv = ResourceContractDemandView(demands=())  # empty
    ci = CanonicalCompileInput(
        source_schema="structural_nl", schema_version="1.0", raw_text="",
        hard_facts=HardFacts(
            inputs=[],
            outputs=[_fact("draft", True, pkt_id="p_list_draft")],
        ),
    )
    diags = validator.validate(ci, [], FieldRouteIR(), dv)
    kinds = {d.kind for d in diags}
    assert RESOURCE_CONTRACT_ANNOTATION_MISSING in kinds
    assert RESOURCE_CONTRACT_ANNOTATION_COVERAGE_GAP in kinds
    assert any("draft" in d.message for d in diags)


def test_unmatched_input_fact_coverage_gap():
    validator = ResourceContractAnnotationCoverageValidator()
    dv = ResourceContractDemandView(demands=())
    ci = CanonicalCompileInput(
        source_schema="structural_nl", schema_version="1.0", raw_text="",
        hard_facts=HardFacts(
            inputs=[_fact("topic", True, pkt_id="p_list_topic")],
            outputs=[],
        ),
    )
    diags = validator.validate(ci, [], FieldRouteIR(), dv)
    assert len(diags) > 0


# =============================================================================
# Direction matching: input fact only matches input demand
# =============================================================================


def test_output_fact_not_matched_by_input_demand():
    validator = ResourceContractAnnotationCoverageValidator()
    dv = ResourceContractDemandView(demands=(
        _dvh("rcd_in_s1", "input", pkt_id="p_list_draft"),
    ))
    ci = CanonicalCompileInput(
        source_schema="structural_nl", schema_version="1.0", raw_text="",
        hard_facts=HardFacts(
            inputs=[],
            outputs=[_fact("draft", True, pkt_id="p_list_draft")],
        ),
    )
    diags = validator.validate(ci, [], FieldRouteIR(), dv)
    assert len(diags) > 0  # input demand doesn't cover output fact


# =============================================================================
# Validator is read-only
# =============================================================================


def test_validator_does_not_modify_demand_view():
    validator = ResourceContractAnnotationCoverageValidator()
    dv = ResourceContractDemandView(demands=(
        _dvh("rcd_out_s1", "output", pkt_id="p_known"),
    ))
    original_demands = list(dv.demands)
    ci = CanonicalCompileInput(
        source_schema="structural_nl", schema_version="1.0", raw_text="",
        hard_facts=HardFacts(
            inputs=[],
            outputs=[_fact("unknown", True, pkt_id="p_unknown")],
        ),
    )
    validator.validate(ci, [], FieldRouteIR(), dv)
    assert list(dv.demands) == original_demands


def test_validator_does_not_modify_routes():
    validator = ResourceContractAnnotationCoverageValidator()
    dv = ResourceContractDemandView(demands=())
    routes = FieldRouteIR(behavior=["s1"])
    original_behavior = list(routes.behavior)
    ci = CanonicalCompileInput(
        source_schema="structural_nl", schema_version="1.0", raw_text="",
        hard_facts=HardFacts(
            inputs=[_fact("x", True, pkt_id="p_x")],
            outputs=[],
        ),
    )
    validator.validate(ci, [], routes, dv)
    assert list(routes.behavior) == original_behavior


# =============================================================================
# Projector integration
# =============================================================================


def test_projector_converts_coverage_diagnostics():
    validator = ResourceContractAnnotationCoverageValidator()
    dv = ResourceContractDemandView(demands=())
    ci = CanonicalCompileInput(
        source_schema="structural_nl", schema_version="1.0", raw_text="",
        hard_facts=HardFacts(
            inputs=[],
            outputs=[_fact("draft", True, pkt_id="p_draft")],
        ),
    )
    diags = validator.validate(ci, [], FieldRouteIR(), dv)
    projected = ViewDiagnosticProjector.project_list(list(diags))
    for cd in projected:
        assert isinstance(cd, CompileDiagnostic)
    assert len(projected) == len(diags)


# =============================================================================
# Empty / no hard facts → no diagnostics
# =============================================================================


def test_same_packet_different_span_still_matches():
    """Packet_id match is sufficient, even when span_ids differ."""
    validator = ResourceContractAnnotationCoverageValidator()
    dv = ResourceContractDemandView(demands=(
        _dvh("rcd_out_s1", "output", pkt_id="p_shared", span_id="s1"),
    ))
    ci = CanonicalCompileInput(
        source_schema="structural_nl", schema_version="1.0", raw_text="",
        hard_facts=HardFacts(
            inputs=[],
            outputs=[_fact("draft", True, pkt_id="p_shared", span_id="s99")],
        ),
    )
    diags = validator.validate(ci, [], FieldRouteIR(), dv)
    assert diags == [], f"Same packet should match; got {[d.kind for d in diags]}"


def test_two_packet_only_missing_facts_unique_diagnostic_ids():
    """Two missing facts without span_ids produce distinct diagnostic_ids."""
    validator = ResourceContractAnnotationCoverageValidator()
    dv = ResourceContractDemandView(demands=())
    ci = CanonicalCompileInput(
        source_schema="structural_nl", schema_version="1.0", raw_text="",
        hard_facts=HardFacts(
            inputs=[],
            outputs=[
                _fact("draft", True, pkt_id="p_draft", span_id=""),
                _fact("report", True, pkt_id="p_report", span_id=""),
            ],
        ),
    )
    diags = validator.validate(ci, [], FieldRouteIR(), dv)
    missing_diags = [d for d in diags if d.kind.endswith("_missing")]
    assert len(missing_diags) >= 2
    projected = ViewDiagnosticProjector.project_list(list(missing_diags))
    ids = {cd.diagnostic_id for cd in projected}
    assert len(ids) == len(missing_diags), (
        f"Expected {len(missing_diags)} unique IDs; got {len(ids)}: {ids}"
    )


def test_empty_hard_facts_no_diagnostics():
    validator = ResourceContractAnnotationCoverageValidator()
    dv = ResourceContractDemandView(demands=(_dvh("rcd_out_s1", "output"),))
    ci = CanonicalCompileInput(
        source_schema="structural_nl", schema_version="1.0", raw_text="",
        hard_facts=HardFacts(inputs=[], outputs=[]),
    )
    diags = validator.validate(ci, [], FieldRouteIR(), dv)
    assert diags == []
