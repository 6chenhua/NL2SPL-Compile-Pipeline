"""Phase B3 tests — Stage 3.5 DemandView consumption."""

from __future__ import annotations

from nl2spl.compiler.resource_contract_demand_view.model import DemandViewDemand
from nl2spl.pipeline.stages.stage3_5_worker_boundary_planner.executor import ExecutorMixin


def _demand(did, direction, requiredness, evidence, span_id):
    return DemandViewDemand(
        demand_id=did,
        direction=direction,
        requiredness=requiredness,
        required=True if requiredness == "required" else (
            False if requiredness == "optional" else None
        ),
        evidence_text=evidence,
        source_span_ids=(span_id,),
        source_section_id="sec_test",
        evidence_source="stage2_annotation",
        view_status="valid",
    )


def test_demand_view_input_contract():
    inps, outs = ExecutorMixin._demand_view_contracts([
        _demand("rcd_input_s1", "input", "required", "Topic summary", "s1"),
    ])
    assert len(inps) == 1 and len(outs) == 0
    f = inps[0]
    assert f.contract_demand_id == "rcd_input_s1"
    assert f.source == "input"
    assert f.requiredness == "required"
    assert f.required is True


def test_demand_view_output_contract():
    inps, outs = ExecutorMixin._demand_view_contracts([
        _demand("rcd_output_s2", "output", "optional", "Optional report", "s2"),
    ])
    assert len(inps) == 0 and len(outs) == 1
    f = outs[0]
    assert f.contract_demand_id == "rcd_output_s2"
    assert f.source == "output"
    assert f.requiredness == "optional"
    assert f.required is False


def test_demand_view_unspecified_requiredness():
    inps, _outs = ExecutorMixin._demand_view_contracts([
        _demand("rcd_input_s3", "input", "unspecified", "Mystery input", "s3"),
    ])
    assert len(inps) == 1
    f = inps[0]
    assert f.requiredness == "unspecified"
    assert f.required is None


def test_demand_view_mixed_directions():
    inps, outs = ExecutorMixin._demand_view_contracts([
        _demand("rcd_input_s1", "input", "required", "A", "s1"),
        _demand("rcd_output_s2", "output", "required", "B", "s2"),
        _demand("rcd_input_s3", "input", "optional", "C", "s3"),
    ])
    assert len(inps) == 2 and len(outs) == 1
    assert inps[0].contract_demand_id == "rcd_input_s1"
    assert inps[1].contract_demand_id == "rcd_input_s3"
    assert outs[0].contract_demand_id == "rcd_output_s2"


def test_demand_view_empty():
    inps, outs = ExecutorMixin._demand_view_contracts([])
    assert inps == [] and outs == []


def test_invalid_demand_excluded():
    """Demands with view_status != 'valid' are silently excluded."""
    valid = _demand("rcd_input_s1", "input", "required", "A", "s1")
    invalid = DemandViewDemand(
        demand_id="rcd_input_s2",
        direction="input",  # type: ignore[arg-type]
        requiredness="unspecified",  # type: ignore[arg-type]
        required=None,
        evidence_text="Conflicting requiredness",
        source_span_ids=("s2",),
        source_section_id="sec_test",
        evidence_source="stage2_annotation",
        view_status="invalid_requiredness",
    )
    inps, outs = ExecutorMixin._demand_view_contracts([valid, invalid])
    assert len(inps) == 1  # only valid
    assert inps[0].contract_demand_id == "rcd_input_s1"
