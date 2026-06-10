"""Phase B5 tests — Post-normalize IRS with DemandView + tri-state producer."""

from __future__ import annotations

import pytest

from nl2spl.compiler.irs.checkers.post_normalize import PostNormalizeIRSCheckerV6
from nl2spl.compiler.resource_contract_demand_view.model import (
    DemandViewDemand,
    ResourceContractDemandView,
)
from nl2spl.ir.resource_contract_ir import (
    ResourceContractBindingIR,
    ResourceContractDemandIR,
)
from nl2spl.ir.resource_registry_ir import (
    ResourceRegistryIR,
    VariableSpec,
)


# =============================================================================
# Helpers
# =============================================================================


def _demand_dv(did, direction, requiredness):
    return DemandViewDemand(
        demand_id=did,
        direction=direction,
        requiredness=requiredness,
        required=True if requiredness == "required" else (
            False if requiredness == "optional" else None
        ),
        evidence_text="Test demand",
        source_span_ids=("s1",),
        evidence_source="stage2_annotation",
        view_status="valid",
    )


def _demand_legacy(did, direction, requiredness):
    return ResourceContractDemandIR(
        demand_id=did,
        direction=direction,
        requiredness=requiredness,
        required=True if requiredness == "required" else (
            False if requiredness == "optional" else None
        ),
        evidence_text="Test demand",
        source_span_ids=["s1"],
    )


def _binding(did, name, kind="variable", scope="global"):
    return ResourceContractBindingIR(
        contract_demand_id=did,
        resource_name=name,
        resource_kind=kind,
        direction="output",
        scope_kind=scope,
        scope_id=None,
        source_span_ids=["s1"],
    )


def _var(name, source="output"):
    return VariableSpec(
        name=name, data_type="text", required=True, description="Test", source=source,
    )


# =============================================================================
# Test _demand_attr adapts both types
# =============================================================================


def test_demand_attr_legacy() -> None:
    d = _demand_legacy("rcd_out_s1", "output", "required")
    assert PostNormalizeIRSCheckerV6._demand_attr(d, "demand_id") == "rcd_out_s1"
    assert PostNormalizeIRSCheckerV6._demand_attr(d, "requiredness") == "required"
    assert PostNormalizeIRSCheckerV6._demand_attr(d, "required") is True


def test_demand_attr_demand_view() -> None:
    d = _demand_dv("rcd_in_s2", "input", "unspecified")
    assert PostNormalizeIRSCheckerV6._demand_attr(d, "demand_id") == "rcd_in_s2"
    assert PostNormalizeIRSCheckerV6._demand_attr(d, "requiredness") == "unspecified"
    assert PostNormalizeIRSCheckerV6._demand_attr(d, "required") is None


# =============================================================================
# Test materialization: DemandView demand with no binding → missing
# =============================================================================


def test_demand_view_no_binding_missing_materialization() -> None:
    """DemandView has a demand but no binding → materialization missing."""
    from unittest.mock import MagicMock

    dv = ResourceContractDemandView(demands=(
        _demand_dv("rcd_out_s1", "output", "required"),
    ))
    checker = PostNormalizeIRSCheckerV6()
    instance = MagicMock()
    instance.metadata = {
        "kind": "resource_contract_demand",
        "demand": _demand_dv("rcd_out_s1", "output", "required"),
        "matching_bindings": [],
    }
    irs = MagicMock()
    irs.get_slot.return_value = None
    ctx = MagicMock()
    ctx.worker_plan = None
    ctx.resources = ResourceRegistryIR(variables=[])
    ctx.worker_scoped_resources = None
    checker._merged_resources = lambda c: ResourceRegistryIR(variables=[])
    checker._worker_from_context = lambda c: MagicMock()
    checker._get_bindings = lambda c: []

    report = checker._check_resource_contract_demand(instance, irs, ctx)
    mat_slot = next(s for s in report.slots if s.slot_name == "materialization")
    assert mat_slot.status == "missing"


# =============================================================================
# Test registry mismatch
# =============================================================================


def test_binding_not_in_registry_mismatch() -> None:
    """Binding exists but resource not in registry → registry missing."""
    from unittest.mock import MagicMock

    checker = PostNormalizeIRSCheckerV6()
    instance = MagicMock()
    instance.metadata = {
        "kind": "resource_contract_demand",
        "demand": _demand_dv("rcd_out_s1", "output", "required"),
        "matching_bindings": [_binding("rcd_out_s1", "draft")],
    }
    irs = MagicMock()
    irs.get_slot.return_value = None
    ctx = MagicMock()
    ctx.worker_plan = None
    ctx.resources = ResourceRegistryIR(variables=[])
    ctx.worker_scoped_resources = None
    checker._merged_resources = lambda c: ResourceRegistryIR(variables=[])
    checker._worker_from_context = lambda c: MagicMock()
    checker._get_bindings = lambda c: []

    report = checker._check_resource_contract_demand(instance, irs, ctx)
    reg_slot = next(s for s in report.slots if s.slot_name == "resource_registry")
    assert reg_slot.status == "missing"


# =============================================================================
# Test required output no producer → missing
# =============================================================================


def test_required_output_no_producer_missing() -> None:
    """Required output with binding but no producer → producer missing."""
    from unittest.mock import MagicMock

    checker = PostNormalizeIRSCheckerV6()
    instance = MagicMock()
    instance.metadata = {
        "kind": "resource_contract_demand",
        "demand": _demand_dv("rcd_out_s1", "output", "required"),
        "matching_bindings": [_binding("rcd_out_s1", "draft")],
    }
    irs = MagicMock()
    irs.get_slot.return_value = None
    ctx = MagicMock()
    ctx.worker_plan = None
    ctx.resources = ResourceRegistryIR(variables=[_var("draft")])
    ctx.worker_scoped_resources = None
    checker._merged_resources = lambda c: ResourceRegistryIR(variables=[_var("draft")])
    checker._worker_from_context = lambda c: MagicMock()
    checker._get_bindings = lambda c: [_binding("rcd_out_s1", "draft")]

    report = checker._check_resource_contract_demand(instance, irs, ctx)
    prod_slot = next(s for s in report.slots if s.slot_name == "producer")
    assert prod_slot.status == "missing"


# =============================================================================
# Test optional output no producer → no error
# =============================================================================


def test_optional_output_no_producer_satisfied() -> None:
    """Optional output with no producer → producer slot satisfied (no error)."""
    from unittest.mock import MagicMock

    checker = PostNormalizeIRSCheckerV6()
    instance = MagicMock()
    instance.metadata = {
        "kind": "resource_contract_demand",
        "demand": _demand_dv("rcd_out_s2", "output", "optional"),
        "matching_bindings": [_binding("rcd_out_s2", "report")],
    }
    irs = MagicMock()
    irs.get_slot.return_value = None
    ctx = MagicMock()
    ctx.worker_plan = None
    ctx.resources = ResourceRegistryIR(variables=[_var("report")])
    ctx.worker_scoped_resources = None
    checker._merged_resources = lambda c: ResourceRegistryIR(variables=[_var("report")])
    checker._worker_from_context = lambda c: MagicMock()
    checker._get_bindings = lambda c: [_binding("rcd_out_s2", "report")]

    report = checker._check_resource_contract_demand(instance, irs, ctx)
    prod_slot = next(s for s in report.slots if s.slot_name == "producer")
    assert prod_slot.status == "satisfied", (
        f"Optional output without producer should be satisfied; got {prod_slot.status}"
    )


# =============================================================================
# Test unspecified output no producer → warning
# =============================================================================


def test_unspecified_output_no_producer_warning() -> None:
    """Unspecified output with no producer → warning, not error."""
    from unittest.mock import MagicMock

    checker = PostNormalizeIRSCheckerV6()
    instance = MagicMock()
    instance.metadata = {
        "kind": "resource_contract_demand",
        "demand": _demand_dv("rcd_out_s3", "output", "unspecified"),
        "matching_bindings": [_binding("rcd_out_s3", "mystery_out")],
    }
    irs = MagicMock()
    irs.get_slot.return_value = None
    ctx = MagicMock()
    ctx.worker_plan = None
    ctx.resources = ResourceRegistryIR(variables=[_var("mystery_out")])
    ctx.worker_scoped_resources = None
    checker._merged_resources = lambda c: ResourceRegistryIR(
        variables=[_var("mystery_out")]
    )
    checker._worker_from_context = lambda c: MagicMock()
    checker._get_bindings = lambda c: [_binding("rcd_out_s3", "mystery_out")]

    report = checker._check_resource_contract_demand(instance, irs, ctx)
    prod_slot = next(s for s in report.slots if s.slot_name == "producer")
    assert prod_slot.status == "satisfied", (
        f"Unspecified without producer should be satisfied + diagnostic; "
        f"got {prod_slot.status}"
    )
    assert prod_slot.diagnostic_kind == "unspecified_output_missing_producer"
