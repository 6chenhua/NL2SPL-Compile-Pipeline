"""Phase B1 behavioral tests — tri-state requiredness in action."""

from __future__ import annotations

import pytest

from nl2spl.ir.worker_ir import WorkerInput, WorkerOutput
from nl2spl.ir.resource_contract_ir import (
    ResourceContractDemandIR,
    ResourceContractFieldIR,
)
from nl2spl.ir.worker_plan_ir import ContractFieldIR
from nl2spl.pipeline.stages.stage11_spl_renderer.renderer import _required_keyword
from nl2spl.pipeline.stages.stage6_resource_extractor.context_builder import (
    _requiredness_label,
)


# =============================================================================
# Renderer _required_keyword tri-state
# =============================================================================


def test_required_keyword_true_returns_REQUIRED() -> None:
    assert _required_keyword(True) == "REQUIRED"


def test_required_keyword_false_returns_OPTIONAL() -> None:
    assert _required_keyword(False) == "OPTIONAL"


def test_required_keyword_none_returns_empty() -> None:
    assert _required_keyword(None) == ""


# =============================================================================
# Context builder _requiredness_label tri-state
# =============================================================================


def test_requiredness_label_true() -> None:
    assert _requiredness_label(True) == "required"


def test_requiredness_label_false() -> None:
    assert _requiredness_label(False) == "optional"


def test_requiredness_label_none() -> None:
    assert _requiredness_label(None) == "unspecified"


# =============================================================================
# ResourceContractDemandIR __post_init__ hydration
# =============================================================================


def test_demand_legacy_bool_required_true_hydrates_requiredness() -> None:
    d = ResourceContractDemandIR(
        demand_id="rcd_output_s1",
        direction="output",
        required=True,
        evidence_text="Some text",
    )
    assert d.required is True
    assert d.requiredness == "required"


def test_demand_legacy_bool_required_false_hydrates_requiredness() -> None:
    d = ResourceContractDemandIR(
        demand_id="rcd_input_s2",
        direction="input",
        required=False,
        evidence_text="Some text",
    )
    assert d.required is False
    assert d.requiredness == "optional"


def test_demand_explicit_requiredness_takes_priority() -> None:
    """When required=None and requiredness is explicitly set, the explicit value wins."""
    d = ResourceContractDemandIR(
        demand_id="rcd_output_s3",
        direction="output",
        required=None,
        evidence_text="Text",
        requiredness="optional",
    )
    assert d.required is None
    assert d.requiredness == "optional"


def test_demand_compat_required_true_no_hydration_when_requiredness_set() -> None:
    """When old code passes required=True + requiredness, requiredness wins only if
    requiredness was explicitly not 'unspecified'.  Passing required=True + no
    requiredness => hydration.  Passing required=True + requiredness='required'
    => explicit, no conflict.  Passing required=True + requiredness='unspecified'
    is considered a legacy pass-through and hydration applies (this is the
    __post_init__ behaviour — unspecified default means 'not set')."""
    d = ResourceContractDemandIR(
        demand_id="rcd_output_s4",
        direction="output",
        required=True,
        evidence_text="Text",
        requiredness="required",
    )
    assert d.requiredness == "required"  # explicit, matches


def test_demand_required_none_no_hydration() -> None:
    d = ResourceContractDemandIR(
        demand_id="rcd_input_s4",
        direction="input",
        required=None,
        evidence_text="Text",
    )
    assert d.required is None
    assert d.requiredness == "unspecified"


# =============================================================================
# ResourceContractFieldIR __post_init__ hydration
# =============================================================================


def test_field_legacy_bool_required_true_hydrates_requiredness() -> None:
    f = ResourceContractFieldIR(
        demand_id="rcd_output_s1",
        name="draft",
        resource_kind="variable",
        direction="output",
        data_type="text",
        required=True,
        description="Finished draft",
    )
    assert f.required is True
    assert f.requiredness == "required"


def test_field_legacy_bool_required_false_hydrates_requiredness() -> None:
    f = ResourceContractFieldIR(
        demand_id="rcd_input_s2",
        name="topic",
        resource_kind="variable",
        direction="input",
        data_type="text",
        required=False,
        description="Topic summary",
    )
    assert f.required is False
    assert f.requiredness == "optional"


# =============================================================================
# ContractFieldIR: required can be None
# =============================================================================


def test_contract_field_accepts_required_none() -> None:
    f = ContractFieldIR(
        name="x",
        data_type="text",
        required=None,
        description="Unspecified field",
        source="output",
    )
    assert f.required is None
    assert f.requiredness == "unspecified"


def test_contract_field_requiredness_explicit() -> None:
    f = ContractFieldIR(
        name="x",
        data_type="text",
        required=True,
        description="Required field",
        source="input",
        requiredness="required",
    )
    assert f.required is True
    assert f.requiredness == "required"


# =============================================================================
# WorkerInput/WorkerOutput: required can be None, requiredness available
# =============================================================================


def test_worker_input_required_none() -> None:
    inp = WorkerInput(name="x", required=None)
    assert inp.required is None
    assert inp.requiredness == "unspecified"


def test_worker_output_required_none() -> None:
    out = WorkerOutput(name="y", required=None)
    assert out.required is None
    assert out.requiredness == "unspecified"


def test_worker_input_required_true() -> None:
    inp = WorkerInput(name="x", required=True)
    assert inp.required is True
    assert inp.requiredness == "unspecified"  # not auto-hydrated (no __post_init__)


def test_worker_output_required_false() -> None:
    out = WorkerOutput(name="y", required=False)
    assert out.required is False
    assert out.requiredness == "unspecified"


# =============================================================================
# to_payload includes requiredness
# =============================================================================


def test_demand_payload_contains_requiredness() -> None:
    d = ResourceContractDemandIR(
        demand_id="rcd_output_s1",
        direction="output",
        required=True,
        evidence_text="Text",
    )
    p = d.to_payload()
    assert "requiredness" in p
    assert p["requiredness"] == "required"
    assert p["required"] is True


def test_demand_payload_required_none() -> None:
    d = ResourceContractDemandIR(
        demand_id="rcd_input_s2",
        direction="input",
        required=None,
        evidence_text="Text",
    )
    p = d.to_payload()
    assert p["requiredness"] == "unspecified"
    assert p["required"] is None
