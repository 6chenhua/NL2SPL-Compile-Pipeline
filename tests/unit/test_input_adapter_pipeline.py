"""Tests for InputAdapter MVP pipeline integration."""

from __future__ import annotations

from unittest.mock import MagicMock

from nl2spl.adapters import GenericNLAdapter, StructuralNLAdapter
from nl2spl.ir.block_structure_ir import BlockStructureIR
from nl2spl.ir.field_route_ir import FieldRouteIR
from nl2spl.ir.flow_structure_ir import FlowStructureIR
from nl2spl.ir.span_ir import SpanIR
from nl2spl.pipeline.orchestrator import PipelineOrchestrator
from nl2spl.pipeline.stages.stage1_span_slicer import SpanSlicer
from nl2spl.pipeline.stages.stage2_field_router import FieldRouter
from nl2spl.pipeline.stages.stage6_resource_extractor import ResourceExtractor


STRUCTURAL_TEXT = """Task family:
Internal newsletters and announcements.

Inputs for each run:
A user request, optional known topics.

Required outputs:
A draft communication artifact, a source/evidence set,
a short assumptions log for any unresolved items, and a completion status.

Reusable process:
First determine what kind of communication is requested.

Policies:
Do not invent links or unseen facts.

Failure handling:
Evidence shortage.

Delegation policy:
Optional delegated subtasks such as source gathering may be used if bounded.
"""


def test_stage1_adapter_path_preserves_packet_provenance(
    pipeline_config: MagicMock,
    mock_client: MagicMock,
) -> None:
    canonical = StructuralNLAdapter().adapt(STRUCTURAL_TEXT)
    slicer = SpanSlicer(pipeline_config, mock_client)

    spans = slicer.execute(canonical)

    assert spans
    assert all(span.source_section_id for span in spans)
    assert any(span.source_packet_id for span in spans)
    mock_client.call_json.assert_not_called()


def test_stage1_generic_path_uses_legacy_llm(
    pipeline_config: MagicMock,
    mock_client: MagicMock,
) -> None:
    canonical = GenericNLAdapter().adapt("Draft a short update.")
    mock_client.call_json.return_value = {
        "spans": [{"span_id": "s1", "text": "Draft a short update."}]
    }
    slicer = SpanSlicer(pipeline_config, mock_client)

    spans = slicer.execute(canonical)

    assert spans[0].source_section_id is None
    mock_client.call_json.assert_called_once()


def test_stage2_adapter_routing_excludes_hard_fact_spans(
    pipeline_config: MagicMock,
    mock_client: MagicMock,
) -> None:
    canonical = StructuralNLAdapter().adapt(STRUCTURAL_TEXT)
    spans = SpanSlicer(pipeline_config, mock_client).execute(canonical)
    router = FieldRouter(pipeline_config, mock_client)

    routes, ambiguity_updates = router.execute((spans, canonical))

    packets = {packet.packet_id: packet for packet in canonical.semantic_packets}
    hard_fact_span_ids = {
        span.span_id
        for span in spans
        if span.source_packet_id
        and packets[span.source_packet_id].packet_type in {"runtime_input", "required_output"}
    }
    assert not hard_fact_span_ids.intersection(routes.behavior)
    assert ambiguity_updates == []
    assert routes.rules
    assert routes.behavior


def test_stage6_seeds_hard_fact_variables_and_keeps_output_producer_empty(
    pipeline_config: MagicMock,
    mock_client: MagicMock,
) -> None:
    canonical = StructuralNLAdapter().adapt(STRUCTURAL_TEXT)
    mock_client.call_json.return_value = {
        "variables": [
            {
                "name": "user_request",
                "data_type": "boolean",
                "required": False,
                "description": "Wrong type",
                "source": "step",
            },
            {
                "name": "draft_communication_artifact",
                "data_type": "text",
                "required": False,
                "description": "LLM duplicate",
                "source": "step",
            },
        ],
        "files": [],
        "apis": [],
        "types": [],
    }
    extractor = ResourceExtractor(pipeline_config, mock_client)

    resources, symbols = extractor.execute(
        (
            [SpanIR("s1", "First determine what kind of communication is requested.")],
            FieldRouteIR(behavior=["s1"]),
            FlowStructureIR(),
            BlockStructureIR(),
            canonical,
        )
    )

    variables = {variable.name: variable for variable in resources.variables}
    assert variables["user_request"].source == "input"
    assert variables["user_request"].data_type == "text"
    assert variables["user_request"].required is True
    assert variables["draft_communication_artifact"].source == "output"
    assert variables["source_evidence_set"].required is True
    assert symbols.variables["draft_communication_artifact"].producer_step is None


def test_orchestrator_records_adapter_intermediate_results(
    pipeline_config: MagicMock,
) -> None:
    orchestrator = PipelineOrchestrator(pipeline_config)

    setattr(orchestrator, "_run_stage1", MagicMock(return_value=[]))
    setattr(orchestrator, "_run_stage2", MagicMock(return_value=(FieldRouteIR(), [])))
    setattr(orchestrator, "_run_stage3", MagicMock(return_value=([], FieldRouteIR())))
    setattr(orchestrator, "_run_stage4", MagicMock(return_value=FlowStructureIR()))
    setattr(orchestrator, "_run_stage5", MagicMock(return_value=BlockStructureIR()))
    setattr(
        orchestrator,
        "_run_stage6",
        MagicMock(return_value=(MagicMock(variables=[]), MagicMock(), [])),
    )
    setattr(orchestrator, "_run_stage7", MagicMock(return_value=([], MagicMock(), [])))
    setattr(orchestrator, "_run_stage8", MagicMock(return_value=MagicMock()))
    setattr(orchestrator, "_run_stage9", MagicMock(return_value=[]))
    setattr(
        orchestrator,
        "_run_normalization",
        MagicMock(
            return_value=(FlowStructureIR(), BlockStructureIR(), [], [], MagicMock(), [], [])
        ),
    )
    setattr(orchestrator, "_run_stage10", MagicMock(return_value=MagicMock()))
    setattr(orchestrator, "_run_stage11", MagicMock(return_value=("SPL", [], [])))

    result = orchestrator.run(STRUCTURAL_TEXT)

    assert "canonical_input" in result.intermediate_results
    assert result.intermediate_results["canonical_input"].source_schema == "structural_nl"
    assert "adapter_detection" in result.intermediate_results


def test_orchestrator_adapter_llm_engine_populates_canonical_facts(
    pipeline_config: MagicMock,
) -> None:
    pipeline_config.adapter_llm_engine = "generic_only"
    orchestrator = PipelineOrchestrator(pipeline_config)
    orchestrator.client = MagicMock()
    orchestrator.client.call_json.return_value = {
        "outputs": [
            {
                "name": "summary",
                "description": "A summary.",
                "data_type": "text",
                "required": True,
                "source_section_id": "sec_freeform_input",
                "source_packet_id": "p_freeform_000",
            }
        ]
    }

    setattr(orchestrator, "_run_stage1", MagicMock(return_value=[]))
    setattr(orchestrator, "_run_stage2", MagicMock(return_value=(FieldRouteIR(), [])))
    setattr(orchestrator, "_run_stage3", MagicMock(return_value=([], FieldRouteIR())))
    setattr(orchestrator, "_run_stage4", MagicMock(return_value=FlowStructureIR()))
    setattr(orchestrator, "_run_stage5", MagicMock(return_value=BlockStructureIR()))
    setattr(
        orchestrator,
        "_run_stage6",
        MagicMock(return_value=(MagicMock(variables=[]), MagicMock(), [])),
    )
    setattr(orchestrator, "_run_stage7", MagicMock(return_value=([], MagicMock(), [])))
    setattr(orchestrator, "_run_stage8", MagicMock(return_value=MagicMock()))
    setattr(orchestrator, "_run_stage9", MagicMock(return_value=[]))
    setattr(
        orchestrator,
        "_run_normalization",
        MagicMock(
            return_value=(FlowStructureIR(), BlockStructureIR(), [], [], MagicMock(), [], [])
        ),
    )
    setattr(orchestrator, "_run_stage10", MagicMock(return_value=MagicMock()))
    setattr(orchestrator, "_run_stage11", MagicMock(return_value=("SPL", [], [])))

    result = orchestrator.run("Summarize the request.")

    canonical = result.intermediate_results["canonical_input"]
    assert canonical.source_schema == "generic_nl"
    assert canonical.hard_facts.outputs[0].name == "summary"
    assert canonical.raw_sections[0].section_id == "sec_freeform_input"
