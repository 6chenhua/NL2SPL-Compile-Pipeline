"""End-to-end acceptance scenarios — implementation plan Section 15.

These tests exercise the full Resource Contract Demand View chain:
  Stage 2 annotation → DemandView → Stage 3.5 → Stage 6 → IRS → Renderer.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from nl2spl.canonical.compile_input import (
    CanonicalCompileInput,
    EvidenceRef,
    HardFacts,
    VariableFact,
)
from nl2spl.compiler.irs.checkers.post_normalize import PostNormalizeIRSCheckerV6
from nl2spl.compiler.irs.context import IRSCheckContext
from nl2spl.compiler.irs.subsystem import IRSSubsystem
from nl2spl.compiler.producer_index import ProducerIndex
from nl2spl.compiler.resource_contract_demand_view.builder import DemandViewBuilder
from nl2spl.compiler.resource_contract_demand_view.coverage_validator import (
    ResourceContractAnnotationCoverageValidator,
)
from nl2spl.compiler.resource_contract_demand_view.model import (
    DemandViewDemand,
    ResourceContractDemandView,
)
from nl2spl.compiler.resource_contract_demand_view.projector import (
    ViewDiagnosticProjector,
)
from nl2spl.ir.field_route_ir import FieldRouteIR, RouteAnnotation
from nl2spl.ir.resource_contract_ir import (
    ResourceContractBindingIR,
    ResourceContractFieldIR,
)
from nl2spl.ir.resource_registry_ir import (
    ResourceRegistryIR,
    VariableSpec,
    WorkerScopedResourceIR,
)
from nl2spl.ir.span_ir import SpanIR
from nl2spl.ir.worker_ir import WorkerInput, WorkerIR, WorkerOutput
from nl2spl.ir.worker_plan_ir import (
    ContractFieldIR,
    WorkerSpecIR,
)
from nl2spl.pipeline.stages.stage11_spl_renderer.renderer import _required_keyword
from nl2spl.pipeline.stages.stage3_5_worker_boundary_planner.executor import (
    ExecutorMixin,
)
from nl2spl.pipeline.stages.stage6_resource_extractor.context_builder import (
    build_resource_context,
)


# =============================================================================
# Scenario 1: Structured NL Happy Path
# =============================================================================


def test_e2e_happy_path():
    """Stage 2 annotations → DemandView → Stage 3.5 placeholders → IRS satisfied.

    Full chain: annotation → demand → contract placeholder → materialization
    → IRS check → all satisfied.
    """
    # -- Stage 2: confirmed annotations --
    spans = [
        SpanIR("s1", "Topic summary", source_section_id="sec_inputs"),
        SpanIR("s2", "Finished draft", source_section_id="sec_outputs"),
    ]
    ann_in = RouteAnnotation(
        span_id="s1", field="resources",
        semantic_role="input_contract", route_family="resource_contract",
        construct_target="RESOURCE_CONTRACT", slot_target="input",
        executable=False, source_section_id="sec_inputs",
    )
    ann_in.metadata["requiredness"] = "required"
    ann_out = RouteAnnotation(
        span_id="s2", field="resources",
        semantic_role="output_contract", route_family="resource_contract",
        construct_target="RESOURCE_CONTRACT", slot_target="output",
        executable=False, source_section_id="sec_outputs",
    )
    ann_out.metadata["requiredness"] = "required"
    routes = FieldRouteIR(behavior=[], annotations=[ann_in, ann_out])

    # -- DemandView --
    dv = DemandViewBuilder().build(spans, routes)
    assert len(dv.valid_demands()) == 2
    assert {d.direction for d in dv.demands} == {"input", "output"}

    # -- Stage 3.5: contractor placeholder from DemandView --
    dv_demands = list(dv.valid_demands())
    inps, outs = ExecutorMixin._demand_view_contracts(dv_demands)
    assert len(inps) == 1
    assert len(outs) == 1
    assert inps[0].contract_demand_id == "rcd_input_s1"
    assert outs[0].contract_demand_id == "rcd_output_s2"

    # -- Stage 6: materialization --
    # Build a ResourceContractFieldIR (simulating LLM output)
    field = ResourceContractFieldIR(
        demand_id="rcd_output_s2", name="draft", resource_kind="variable",
        direction="output", data_type="text", required=True,
        requiredness="required", description="Finished draft",
    )
    binding = ResourceContractBindingIR(
        contract_demand_id="rcd_output_s2", resource_name="draft",
        resource_kind="variable", direction="output",
        scope_kind="global", scope_id=None,
    )

    # -- IRS: check materialization + producer --
    checker = PostNormalizeIRSCheckerV6()
    instance = MagicMock()
    instance.metadata = {
        "kind": "resource_contract_demand",
        "demand": dv_demands[1],  # output demand
        "matching_bindings": [binding],
    }
    irs = MagicMock()
    irs.get_slot.return_value = None
    ctx = MagicMock()
    ctx.worker_plan = None
    resources = ResourceRegistryIR(variables=[
        VariableSpec("draft", "text", True, "Finished draft", "output"),
    ])
    ctx.resources = resources
    ctx.worker_scoped_resources = None
    worker = MagicMock()
    worker.steps = [
        MagicMock(outputs=["draft"], inputs=[], handoff_id=None, integration_ref=None),
    ]
    checker._merged_resources = lambda c: resources
    checker._worker_from_context = lambda c: worker
    checker._get_bindings = lambda c: [binding]

    report = checker._check_resource_contract_demand(instance, irs, ctx)
    assert all(s.status == "satisfied" for s in report.slots), (
        f"All slots should be satisfied; got {[(s.slot_name, s.status) for s in report.slots]}"
    )


# =============================================================================
# Scenario 2: Stage 2 missing annotation → Coverage validator diagnostic
# =============================================================================


def test_e2e_missing_annotation_coverage_gap():
    """No Stage 2 contract annotation → DemandView empty → coverage gap diagnostic.

    Default path must NOT generate fallback demands from section titles.
    """
    spans = [
        SpanIR("s1", "Topic summary", source_section_id="sec_inputs",
               source_packet_id="p_list_topic"),
    ]
    # No contract annotations
    routes = FieldRouteIR(behavior=["s1"], annotations=[])

    # DemandView is empty
    dv = DemandViewBuilder().build(spans, routes)
    assert len(dv.demands) == 0

    # Coverage validator detects the gap
    ci = CanonicalCompileInput(
        source_schema="structural_nl", schema_version="1.0", raw_text="",
        hard_facts=HardFacts(
            inputs=[VariableFact(
                name="topic_summary", description="Topic summary",
                data_type="text", required=True,
                source_section_id="sec_inputs",
                evidence=[EvidenceRef(
                    source_section_id="sec_inputs",
                    source_packet_id="p_list_topic",
                )],
            )],
            outputs=[],
        ),
    )
    validator = ResourceContractAnnotationCoverageValidator()
    diags = validator.validate(ci, spans, routes, dv)

    kinds = {d.kind for d in diags}
    assert "resource_contract_annotation_missing" in kinds
    assert "resource_contract_annotation_coverage_gap" in kinds

    # Projector converts to CompileDiagnostic
    projected = ViewDiagnosticProjector.project_list(list(diags))
    assert len(projected) >= 2  # gap summary + missing detail

    # Verify no fallback demand was generated
    assert len(dv.demands) == 0


# =============================================================================
# Scenario 3: Direction conflict → no demand
# =============================================================================


def test_e2e_direction_conflict():
    """Same span with input+output contract → no demand, diagnostic visible."""
    spans = [
        SpanIR("s3", "Ambiguous data", source_section_id="sec_mixed"),
    ]
    ann_in = RouteAnnotation(
        span_id="s3", field="resources",
        semantic_role="input_contract", route_family="resource_contract",
        construct_target="RESOURCE_CONTRACT", slot_target="input",
        executable=False, source_packet_id="p_same",
    )
    ann_out = RouteAnnotation(
        span_id="s3", field="resources",
        semantic_role="output_contract", route_family="resource_contract",
        construct_target="RESOURCE_CONTRACT", slot_target="output",
        executable=False, source_packet_id="p_same",
    )
    routes = FieldRouteIR(behavior=[], annotations=[ann_in, ann_out])

    dv = DemandViewBuilder().build(spans, routes)

    # No demand generated
    assert len(dv.demands) == 0

    # Diagnostic emitted
    diag_kinds = {d.kind for d in dv.view_diagnostics}
    assert "resource_contract_ambiguous_multi_direction_span" in diag_kinds

    # Projector converts diagnostic
    projected = ViewDiagnosticProjector.project(dv)
    assert len(projected) >= 1


# =============================================================================
# Scenario 4: Requiredness unspecified — full chain
# =============================================================================


def test_e2e_unspecified_requiredness_full_chain():
    """Requiredness=unspecified: demand kept, required=None, renderer no REQUIRED,
    IRS producer check warning not error."""
    spans = [
        SpanIR("s4", "Mystery output", source_section_id="sec_outputs"),
    ]
    ann = RouteAnnotation(
        span_id="s4", field="resources",
        semantic_role="output_contract", route_family="resource_contract",
        construct_target="RESOURCE_CONTRACT", slot_target="output",
        executable=False,
    )
    # No requiredness metadata → unspecified
    routes = FieldRouteIR(behavior=[], annotations=[ann])

    # -- DemandView: demand kept, required=None --
    dv = DemandViewBuilder().build(spans, routes)
    assert len(dv.demands) == 1
    assert dv.demands[0].requiredness == "unspecified"
    assert dv.demands[0].required is None
    assert dv.demands[0].view_status == "valid"

    # Requiredness unspecified diagnostic
    diags = [d for d in dv.view_diagnostics
             if d.kind == "resource_contract_annotation_missing_requiredness"]
    assert len(diags) >= 1

    # -- Stage 6: pass-through --
    field = ResourceContractFieldIR(
        demand_id="rcd_output_s4", name="mystery", resource_kind="variable",
        direction="output", data_type="text", required=None,
        requiredness="unspecified", description="Mystery output",
    )
    assert field.required is None
    assert field.requiredness == "unspecified"

    # -- Renderer: no REQUIRED keyword --
    inp = WorkerInput(name="mystery", required=None, requiredness="unspecified")
    assert _required_keyword(inp.required) == ""

    # -- IRS: producer check → warning, not error --
    checker = PostNormalizeIRSCheckerV6()
    instance = MagicMock()
    instance.metadata = {
        "kind": "resource_contract_demand",
        "demand": dv.demands[0],
        "matching_bindings": [ResourceContractBindingIR(
            contract_demand_id="rcd_output_s4", resource_name="mystery",
            resource_kind="variable", direction="output",
            scope_kind="global", scope_id=None,
        )],
    }
    irs = MagicMock()
    irs.get_slot.return_value = None
    ctx = MagicMock()
    ctx.worker_plan = None
    resources = ResourceRegistryIR(variables=[
        VariableSpec("mystery", "text", True, "Mystery output", "output"),
    ])
    ctx.resources = resources
    ctx.worker_scoped_resources = None
    checker._merged_resources = lambda c: resources
    checker._worker_from_context = lambda c: MagicMock()
    checker._get_bindings = lambda c: []

    report = checker._check_resource_contract_demand(instance, irs, ctx)
    prod_slot = next(s for s in report.slots if s.slot_name == "producer")
    assert prod_slot.status == "satisfied", (
        f"Unspecified output without producer should get satisfied+diag; "
        f"got {prod_slot.status}"
    )
    assert prod_slot.diagnostic_kind == "unspecified_output_missing_producer"


# =============================================================================
# Scenario 5: Header-only legacy input → no demand in default path
# =============================================================================


def test_e2e_header_only_legacy_input_no_demand():
    """Default path: section titled 'Inputs for each run' without Stage 2
    annotation → DemandView empty (no header fallback)."""

    spans = [
        SpanIR("s5", "Topic summary", source_section_id="sec_inputs"),
    ]
    # No contract annotation at all
    routes = FieldRouteIR(behavior=["s5"], annotations=[])

    dv = DemandViewBuilder().build(spans, routes)

    # Header fallback must NOT generate demand
    assert len(dv.demands) == 0, (
        "Header fallback must not generate demand in default path"
    )


def test_e2e_header_only_required_outputs_no_demand():
    """'Required Outputs' section without annotation → no demand."""
    spans = [
        SpanIR("s6", "Finished draft", source_section_id="sec_required_outputs"),
    ]
    routes = FieldRouteIR(behavior=["s6"], annotations=[])

    dv = DemandViewBuilder().build(spans, routes)
    assert len(dv.demands) == 0
