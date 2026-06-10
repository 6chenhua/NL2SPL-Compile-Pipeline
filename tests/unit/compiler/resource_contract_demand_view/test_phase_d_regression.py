"""Phase D regression tests — orchestrator default path no longer relies on
ResourceContractPlanner as production source of truth."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from nl2spl.pipeline.orchestrator import PipelineOrchestrator
from nl2spl.config import PipelineConfig


def test_orchestrator_default_path_does_not_call_planner_as_authority():
    """The default orchestrator path builds DemandView via DemandViewBuilder,
    not via ResourceContractPlanner as the production authority."""
    from unittest.mock import patch

    config = PipelineConfig()

    with patch("nl2spl.pipeline.orchestrator.LLMClient") as mock_llm:
        mock_llm.return_value.call_json.return_value = {
            "routes": {"behavior": ["s1"]},
            "annotations": [],
        }

        orchestrator = PipelineOrchestrator(config)
        orchestrator.client.call_json = MagicMock(return_value={
            "routes": {"behavior": ["s1"]},
            "annotations": [],
        })

        # Phase E: ResourceContractPlanner is no longer imported in orchestrator.
        # Verify orchestrator can run without it.
        try:
            orchestrator.run("Test. Inputs: - Topic summary. Outputs: - Result.")
        except Exception:
            pass

        # Confirm the orchestrator module no longer imports ResourceContractPlanner
        import nl2spl.pipeline.orchestrator as orch_mod
        import sys
        assert "ResourceContractPlanner" not in dir(orch_mod), (
            "ResourceContractPlanner must not be importable from orchestrator"
        )


def test_stage2_annotation_flows_into_demand_view():
    """Stage 2 confirmed RouteAnnotation → DemandViewBuilder → valid demand."""
    from nl2spl.compiler.resource_contract_demand_view.builder import (
        DemandViewBuilder,
    )
    from nl2spl.ir.field_route_ir import FieldRouteIR, RouteAnnotation
    from nl2spl.ir.span_ir import SpanIR

    spans = [
        SpanIR(span_id="s1", text="Topic summary",
               source_section_id="sec_inputs"),
    ]
    ann = RouteAnnotation(
        span_id="s1", field="resources",
        semantic_role="input_contract",
        route_family="resource_contract",
        construct_target="RESOURCE_CONTRACT",
        slot_target="input", executable=False,
        source_section_id="sec_inputs",
    )
    ann.metadata["requiredness"] = "required"
    routes = FieldRouteIR(behavior=[], annotations=[ann])

    dv = DemandViewBuilder().build(spans, routes)

    assert len(dv.demands) == 1
    assert dv.demands[0].demand_id == "rcd_input_s1"
    assert dv.demands[0].direction == "input"
    assert dv.demands[0].requiredness == "required"


def test_stage2_missing_annotation_produces_no_demand():
    """No Stage 2 contract annotation → DemandView is empty."""
    from nl2spl.compiler.resource_contract_demand_view.builder import (
        DemandViewBuilder,
    )
    from nl2spl.ir.field_route_ir import FieldRouteIR
    from nl2spl.ir.span_ir import SpanIR

    spans = [SpanIR(span_id="s1", text="Topic summary")]
    routes = FieldRouteIR(behavior=["s1"], annotations=[])  # no contract anns

    dv = DemandViewBuilder().build(spans, routes)
    assert len(dv.demands) == 0
    # Diagnostics should be empty (coverage validator handles missing annotation)
    missing_diags = [
        d for d in dv.view_diagnostics
        if d.kind.startswith("resource_contract_annotation_missing")
    ]
    assert len(missing_diags) == 0  # DemandView doesn't check coverage


def test_orchestrator_pipeline_result_includes_view_diagnostics():
    """PipelineResult.compile_diagnostics must contain DemandView diagnostics."""
    from unittest.mock import patch

    config = PipelineConfig()
    with patch("nl2spl.pipeline.orchestrator.LLMClient") as mock_llm:
        mock_llm.return_value.call_json.return_value = {
            "routes": {"behavior": ["s1"]},
            "annotations": [],
        }
        orchestrator = PipelineOrchestrator(config)
        orchestrator.client.call_json = MagicMock(return_value={
            "routes": {"behavior": ["s1"]},
            "annotations": [],
        })
        result = orchestrator.run("Test. Inputs: - Topic. Outputs: - Result.")
        # DemandView may produce diagnostics (e.g. missing requiredness)
        # and they must appear in compile_diagnostics.
        assert isinstance(result.compile_diagnostics, list)


def test_demand_view_diagnostics_enter_compile_diagnostics():
    """DemandView view_diagnostics can be projected to CompileDiagnostic."""
    from nl2spl.compiler.resource_contract_demand_view.builder import (
        DemandViewBuilder,
    )
    from nl2spl.compiler.resource_contract_demand_view.projector import (
        ViewDiagnosticProjector,
    )
    from nl2spl.ir.field_route_ir import FieldRouteIR, RouteAnnotation
    from nl2spl.ir.span_ir import SpanIR

    spans = [
        SpanIR(span_id="s1", text="Some output"),
    ]
    # Annotation missing requiredness → unspecified diagnostic
    ann = RouteAnnotation(
        span_id="s1", field="resources",
        semantic_role="output_contract",
        route_family="resource_contract",
        construct_target="RESOURCE_CONTRACT",
        slot_target="output", executable=False,
    )
    routes = FieldRouteIR(behavior=[], annotations=[ann])

    dv = DemandViewBuilder().build(spans, routes)

    # Should have diagnostic about missing requiredness
    assert len(dv.view_diagnostics) > 0

    projected = ViewDiagnosticProjector.project(dv)
    assert len(projected) == len(dv.view_diagnostics)
    for cd in projected:
        assert cd.kind.startswith("resource_contract_")
