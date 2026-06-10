"""Tests for InputAdapter MVP pipeline integration."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from nl2spl.adapters import GenericNLAdapter, StructuralNLAdapter
from nl2spl.compiler.construct_registry import SPLConstructRegistry
from nl2spl.compiler.feedback_report_renderer import render_feedback_report
from nl2spl.compiler.irs.checkers.worker_delegation import WorkerDelegationIRSChecker
from nl2spl.compiler.irs.context import IRSCheckContext
from nl2spl.compiler.irs.projector import DiagnosticProjector
from nl2spl.compiler.irs.registry import IRSCheckerRegistry
from nl2spl.compiler.irs.runner import IRSRunner
from nl2spl.errors.exceptions import StageError
from nl2spl.ir.block_structure_ir import BlockIR, BlockStructureIR
from nl2spl.ir.field_route_ir import FieldRouteIR, RouteAnnotation
from nl2spl.ir.flow_structure_ir import FlowStructureIR
from nl2spl.ir.resource_registry_ir import ResourceRegistryIR
from nl2spl.ir.span_ir import SpanIR
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.ir.worker_plan_ir import WorkerPlanIR
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
    canonical = StructuralNLAdapter(None).adapt(STRUCTURAL_TEXT)
    mock_client.reset_mock()
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


def test_stage6_seeds_hard_fact_variables_and_keeps_output_producer_empty(
    pipeline_config: MagicMock,
    mock_client: MagicMock,
) -> None:
    canonical = StructuralNLAdapter(
        mock_client, enable_hard_facts=True,
    ).adapt(STRUCTURAL_TEXT)
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
    from nl2spl.ir.resource_registry_ir import WorkerScopedResourceIR
    from nl2spl.ir.worker_plan_ir import (
        WorkerBlockPlanIR,
        WorkerFlowPlanIR,
        WorkerPlanIR,
        WorkerSpecIR,
        WorkerStepPlanIR,
    )

    orchestrator = PipelineOrchestrator(pipeline_config)
    worker_plan = WorkerPlanIR(
        main_worker_id="worker_main",
        workers=[
            WorkerSpecIR(
                "worker_main", "Main", "main", "Main worker",
                [], [], [], [], [], "main_worker", [], "",
            )
        ],
        candidates=[],
        decisions=[],
        handoffs=[],
    )
    worker_flow_plan = WorkerFlowPlanIR(worker_flows={"worker_main": FlowStructureIR()})
    worker_block_plan = WorkerBlockPlanIR(worker_blocks={"worker_main": BlockStructureIR()})
    worker_step_plan = WorkerStepPlanIR(main_worker_id="worker_main", worker_steps={"worker_main": []})
    worker = MagicMock()
    worker.steps = []
    worker.child_workers = []
    worker.scoped_steps = False

    setattr(orchestrator, "_run_stage1", MagicMock(return_value=[]))
    setattr(orchestrator, "_run_stage2", MagicMock(return_value=(FieldRouteIR(), [])))
    setattr(orchestrator, "_run_stage3", MagicMock(return_value=([], FieldRouteIR())))
    setattr(orchestrator, "_run_stage3_5", MagicMock(return_value=worker_plan))
    setattr(orchestrator, "_run_stage4", MagicMock(return_value=worker_flow_plan))
    setattr(orchestrator, "_run_stage5", MagicMock(return_value=worker_block_plan))
    setattr(
        orchestrator,
        "_run_stage6_worker_scoped",
        MagicMock(return_value=(WorkerScopedResourceIR(global_resources=ResourceRegistryIR()), MagicMock(), [])),
    )
    setattr(orchestrator, "_run_stage7_worker_scoped", MagicMock(return_value=(worker_step_plan, MagicMock(), [])))
    setattr(orchestrator, "_run_stage8", MagicMock(return_value=MagicMock()))
    setattr(orchestrator, "_run_stage9", MagicMock(return_value=[]))
    setattr(
        orchestrator,
        "_run_normalization_worker_scoped",
        MagicMock(
            return_value=(worker_flow_plan, worker_block_plan, worker_step_plan, MagicMock(), [], [])
        ),
    )
    setattr(orchestrator, "_run_stage10_worker_scoped", MagicMock(return_value=worker))
    setattr(orchestrator, "_run_stage11", MagicMock(return_value=("SPL", [], [])))

    result = orchestrator.run(STRUCTURAL_TEXT)

    assert "canonical_input" in result.intermediate_results
    assert result.intermediate_results["canonical_input"].source_schema == "structural_nl"
    assert "adapter_detection" in result.intermediate_results


def test_orchestrator_stage2_adapter_llm_failure_fails_fast(
    pipeline_config: MagicMock,
) -> None:
    """Structural NL must not continue when Stage 2 adapter LLM is unavailable."""
    orchestrator = PipelineOrchestrator(pipeline_config)
    orchestrator.client = MagicMock()
    orchestrator.client.call_json.side_effect = RuntimeError("stage2 unavailable")
    setattr(orchestrator, "_run_stage3", MagicMock())

    with pytest.raises(StageError) as exc_info:
        orchestrator.run(STRUCTURAL_TEXT)

    err = exc_info.value
    assert err.stage == "stage2_field_router"
    assert "stage2_adapter_guided" in str(err)
    assert "stage2 unavailable" in str(err)
    assert err.details["fallback_allowed"] is False
    orchestrator._run_stage3.assert_not_called()


# ===========================================================================
# F0 Baseline: uncovered section provenance
# ===========================================================================


def test_stage1_uncovered_section_spans_preserve_section_provenance(
    pipeline_config: MagicMock,
    mock_client: MagicMock,
) -> None:
    """F0 Baseline: sections not covered by semantic_packets still carry source_section_id."""
    from nl2spl.canonical import CanonicalCompileInput, RawSection, SemanticPacket

    canonical = CanonicalCompileInput(
        source_schema="structural_nl",
        schema_version="1.0",
        raw_text="Task family:\nExample.\n\nExtra section:\nExtra text.",
        raw_sections=[
            RawSection("sec_task_family", "task_family", "Task family", "Example.", 1),
            RawSection("sec_extra", "failure_handling", "Failure handling", "Extra text.", 2),
        ],
        semantic_packets=[
            SemanticPacket(
                "p1", "sec_task_family", "task_family", "Example.", "hint"
            ),
        ],
    )
    slicer = SpanSlicer(pipeline_config, mock_client)

    spans = slicer.execute(canonical)

    uncovered_spans = [s for s in spans if s.source_packet_id is None]
    assert len(uncovered_spans) >= 1, "Expected at least one uncovered section span"
    for span in uncovered_spans:
        assert span.source_section_id, (
            f"Uncovered span {span.span_id} missing source_section_id"
        )
    mock_client.call_json.assert_not_called()


# ===========================================================================
# F0 Baseline: per-packet-type FieldRouter routing
# ===========================================================================


F0_STRUCTURAL_TEXT = """Task family:
Internal newsletters and announcements.

Inputs for each run:
A user request, optional known topics, optional timeframe.

Required outputs:
A draft communication artifact, a source/evidence set, a short assumptions log, and a completion status.

Reusable process:
First determine what kind of communication is requested.
If sources are needed and available, retrieve them using approved source recipes.

Policies:
Do not invent links or unseen facts. Require evidence for sourced claims.

Failure handling:
Missing timeframe, conflicting instructions, evidence shortage, and provenance failure.

Delegation policy:
Optional delegated subtasks such as source gathering or template matching may be used if bounded.
"""


# ===========================================================================
# F3 Baseline: Hint-Aware FieldRouter emits RouteAnnotations
# ===========================================================================


def _adapt_slice_route(text: str, pipeline_config, mock_client):
    """Helper: adapter → slicer → router for structural NL."""
    canonical = StructuralNLAdapter(mock_client).adapt(text)
    spans = SpanSlicer(pipeline_config, mock_client).execute(canonical)
    mock_client.call_json.return_value = _route_annotations_for_spans(spans)
    router = FieldRouter(pipeline_config, mock_client)
    return router.execute((spans, canonical))


def _route_annotations_for_spans(spans: list[SpanIR]) -> dict:
    annotations = []
    role_by_section = {
        "sec_task_family": ("domain", "profile_domain", False, "profile"),
        "sec_inputs_for_each_run": (
            "resources", "input_contract", False, "resource_contract",
        ),
        "sec_required_outputs": (
            "resources", "output_contract", False, "resource_contract",
        ),
        "sec_reusable_process": (
            "behavior", "process_step", True, "flow_relevant",
        ),
        "sec_policies": ("rules", "constraint", False, "rule"),
        "sec_failure_handling": (
            "behavior", "failure_mode", False, "flow_relevant",
        ),
        "sec_delegation_policy": (
            "behavior", "delegation_intent", False, "delegation_boundary",
        ),
    }
    for span in spans:
        section_id = span.source_section_id
        if section_id not in role_by_section:
            continue
        field, role, executable, route_family = role_by_section[section_id]
        ann = {
            "span_id": span.span_id,
            "field": field,
            "semantic_role": role,
            "route_family": route_family,
            "executable": executable,
            "source_section_id": section_id,
        }
        if span.source_packet_id:
            ann["source_packet_id"] = span.source_packet_id
        if role == "failure_mode":
            ann["construct_target"] = "EXCEPTION_FLOW"
            ann["slot_target"] = "condition"
        annotations.append(ann)
    return {"annotations": annotations}


class TestF3StructuralAnnotations:
    """F3: FieldRouter canonical path emits RouteAnnotations."""

    def test_canonical_emits_annotations(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        routes, ambiguity_updates = _adapt_slice_route(
            F0_STRUCTURAL_TEXT, pipeline_config, mock_client
        )

        assert len(routes.annotations) >= 1, "Expected at least one annotation"
        assert ambiguity_updates == []
        assert any(
            call.kwargs.get("stage_name") == "stage2_adapter_guided"
            for call in mock_client.call_json.call_args_list
        )

        packets_by_pid = {}  # We don't have canonical here, but check provenance
        for ann in routes.annotations:
            assert ann.span_id
            if ann.source_packet_id:
                assert ann.source_section_id, (
                    f"Annotation {ann.span_id} has packet_id but no section_id"
                )

    def test_failure_mode_annotation(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        routes, _ = _adapt_slice_route(
            F0_STRUCTURAL_TEXT, pipeline_config, mock_client
        )

        failure_anns = [
            a for a in routes.annotations
            if a.semantic_role in ("failure_mode", "failure_condition")
        ]
        assert len(failure_anns) >= 1, "Expected at least one failure annotation"

        for ann in failure_anns:
            assert ann.span_id not in routes.behavior
            assert ann.span_id not in routes.rules
            assert ann.field == "behavior"
            assert ann.semantic_role in ("failure_mode", "failure_condition")
            assert ann.construct_target == "EXCEPTION_FLOW"
            assert ann.slot_target == "condition"
            assert ann.executable is False
            assert ann.source_section_id
            assert ann.source_packet_id

    def test_resource_contract_annotations_not_routed(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        routes, _ = _adapt_slice_route(
            F0_STRUCTURAL_TEXT, pipeline_config, mock_client
        )

        all_route_ids = routes.get_all_span_ids()
        input_anns = routes.get_annotations_by_role("input_contract")
        output_anns = routes.get_annotations_by_role("output_contract")

        assert len(input_anns) >= 1, "Expected at least one input_contract annotation"
        assert len(output_anns) >= 1, "Expected at least one output_contract annotation"

        for ann in input_anns + output_anns:
            assert ann.span_id not in all_route_ids, (
                f"Resource contract span {ann.span_id} must not be in old route lists"
            )
            assert ann.route_family == "resource_contract"
            assert ann.executable is False
            assert ann.source_section_id
            assert ann.source_packet_id

    def test_delegation_non_executable_boundary(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        routes, _ = _adapt_slice_route(
            F0_STRUCTURAL_TEXT, pipeline_config, mock_client
        )

        delegation_anns = routes.get_annotations_by_role("delegation_intent")
        assert len(delegation_anns) >= 1, "Expected at least one delegation annotation"

        for ann in delegation_anns:
            assert ann.span_id not in routes.behavior, (
                f"Delegation boundary span {ann.span_id} must not pollute routes.behavior"
            )
            assert ann.semantic_role == "delegation_intent"
            assert ann.route_family == "delegation_boundary"
            assert ann.executable is False

    def test_process_step_remains_executable(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        routes, _ = _adapt_slice_route(
            F0_STRUCTURAL_TEXT, pipeline_config, mock_client
        )

        process_anns = routes.get_annotations_by_role("process_step")
        assert len(process_anns) >= 1, "Expected at least one process_step annotation"

        for ann in process_anns:
            assert ann.span_id in routes.behavior
            assert ann.semantic_role == "process_step"
            assert ann.route_family == "flow_relevant"
            assert ann.executable is True

        # Verify get_executable_behavior_span_ids includes process_step spans
        executable_ids = routes.get_executable_behavior_span_ids()
        for ann in process_anns:
            assert ann.span_id in executable_ids, (
                f"Process step {ann.span_id} must appear in executable behavior"
            )

    def test_generic_nl_path_has_empty_annotations(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """F3: generic NL (LLM) path still produces annotations == []."""
        mock_client.call_json.return_value = {
            "routes": {
                "identity": ["s1"],
                "audience": [],
                "rules": [],
                "domain": [],
                "integrations": [],
                "behavior": [],
            },
            "ambiguity_updates": [],
        }
        router = FieldRouter(pipeline_config, mock_client)
        spans = [SpanIR("s1", "test")]

        routes, _ = router.execute(spans)
        assert routes.annotations == []

    def test_checkpoint_includes_annotations(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """F3: Stage 2 checkpoint serializes annotations for canonical input."""
        from unittest.mock import patch

        canonical = StructuralNLAdapter(None).adapt(F0_STRUCTURAL_TEXT)
        spans = SpanSlicer(pipeline_config, mock_client).execute(canonical)
        mock_client.call_json.return_value = _route_annotations_for_spans(spans)
        router = FieldRouter(pipeline_config, mock_client)

        with patch.object(router, "save_checkpoint") as mock_save:
            router.execute((spans, canonical))

        mock_save.assert_called_once()
        checkpoint = mock_save.call_args[0][0]
        routes_data = checkpoint["routes"]
        assert "annotations" in routes_data, "Checkpoint routes missing annotations"
        assert len(routes_data["annotations"]) >= 1

    def test_llm_annotation_not_overridden_by_conflicting_hint(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """F3: conflicting hint does not override final LLM annotation."""
        from nl2spl.canonical import (
            CanonicalCompileInput,
            CompileHint,
            CompileHints,
            EvidenceRef,
            RawSection,
            SemanticPacket,
        )

        section = RawSection(
            "sec_failure_handling", "failure_handling",
            "Failure handling", "Missing timeframe.", 1,
        )
        packet = SemanticPacket(
            "p_failure_mode_missing_timeframe", "sec_failure_handling",
            "failure_mode", "Missing timeframe.", "hard_fact",
            compile_targets=["flow.exception.condition"],
        )
        hint = CompileHint(
            source_section_id="sec_failure_handling",
            text="Missing timeframe.",
            target="EXCEPTION_FLOW",
            suggested_flow="exception",
            suggested_condition="Missing timeframe.",
            evidence=[
                EvidenceRef(
                    source_section_id="sec_failure_handling",
                    source_packet_id="p_failure_mode_missing_timeframe",
                )
            ],
            metadata={
                "route_family": "flow_relevant",
                "slot_target": "handler",  # CONFLICT: packet says "condition"
                "semantic_role": "failure_mode",
                "executable": True,  # CONFLICT: packet says False
            },
        )
        compile_hints = CompileHints(flow_hints=[hint])
        canonical = CanonicalCompileInput(
            source_schema="structural_nl", schema_version="1.0",
            raw_text="Failure handling:\nMissing timeframe.",
            raw_sections=[section],
            semantic_packets=[packet],
            compile_hints=compile_hints,
        )
        spans = SpanSlicer(pipeline_config, mock_client).execute(canonical)
        mock_client.call_json.return_value = _route_annotations_for_spans(spans)
        router = FieldRouter(pipeline_config, mock_client)
        routes, _ = router.execute((spans, canonical))

        failure_anns = routes.get_annotations_by_role("failure_mode")
        assert len(failure_anns) == 1
        ann = failure_anns[0]

        assert ann.slot_target == "condition", (
            f"Hint slot_target should not override packet-derived 'condition': {ann.slot_target}"
        )
        assert ann.executable is False, (
            f"Hint executable should not override packet-derived False: {ann.executable}"
        )
        assert ann.construct_target == "EXCEPTION_FLOW"

    def test_section_only_hints_populate_source_hint_ids(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """F3: LLM RoutePriors reach neutral packet annotations."""
        canonical = StructuralNLAdapter(mock_client).adapt(F0_STRUCTURAL_TEXT)
        spans = SpanSlicer(pipeline_config, mock_client).execute(canonical)
        mock_client.call_json.return_value = _route_annotations_for_spans(spans)
        router = FieldRouter(pipeline_config, mock_client)
        routes, _ = router.execute((spans, canonical))

        process_anns = routes.get_annotations_by_role("process_step")
        assert len(process_anns) >= 1
        assert all(a.source_packet_id for a in process_anns)

        domain_anns = routes.get_annotations_by_role("profile_domain")
        assert len(domain_anns) >= 1
        assert all(a.source_section_id for a in domain_anns)


# ===========================================================================
# D5: Resource, Profile, Constraint annotation consumption
# ===========================================================================


def test_d5_stage6_failure_variable_rejected_legitimate_kept(
    pipeline_config: MagicMock,
    mock_client: MagicMock,
) -> None:
    """D5: failure-derived variable rejected; legitimate variable kept."""
    canonical = StructuralNLAdapter(mock_client).adapt(F0_STRUCTURAL_TEXT)
    spans = [
        SpanIR("s1", "Determine communication type."),
        SpanIR("s2", "Missing timeframe."),
    ]
    routes = FieldRouteIR(
        behavior=["s1", "s2"],
        annotations=[
            RouteAnnotation(span_id="s1", field="behavior",
                            semantic_role="process_step", executable=True),
            RouteAnnotation(span_id="s2", field="behavior",
                            semantic_role="failure_mode",
                            construct_target="EXCEPTION_FLOW",
                            slot_target="condition",
                            executable=False),
        ],
    )
    # LLM returns failure-derived variable + legitimate variable
    mock_client.call_json.return_value = {
        "variables": [
            {"name": "missing_timeframe", "data_type": "text", "required": False,
             "description": "Missing timeframe condition", "source": "step"},
            {"name": "communication_type", "data_type": "text", "required": False,
             "description": "Communication type", "source": "step"},
        ],
        "files": [], "apis": [], "types": [],
    }
    extractor = ResourceExtractor(pipeline_config, mock_client)
    resources, _ = extractor.execute(
        (spans, routes, FlowStructureIR(), BlockStructureIR(), canonical)
    )

    names = {v.name for v in resources.variables}
    assert "communication_type" in names, "Legitimate variable must survive"
    assert "missing_timeframe" not in names, (
        "Failure-derived variable must be rejected"
    )
    warnings = getattr(extractor, "resource_filter_warnings", [])
    assert any("missing_timeframe" in w or "failure" in w.lower()
               for w in warnings), f"Expected D5 failure filter warning: {warnings}"


def test_d5_stage9_excludes_failure_from_prompt_and_rejects_output(
    pipeline_config: MagicMock,
    mock_client: MagicMock,
) -> None:
    """D5: failure_mode excluded from prompt AND parse-rejected."""
    from nl2spl.pipeline.stages.stage9_constraint_extractor import ConstraintExtractor

    spans = [
        SpanIR("s_policy", "Do not invent facts."),
        SpanIR("s_failure", "Missing timeframe."),
    ]
    routes = FieldRouteIR(
        rules=["s_policy", "s_failure"],
        annotations=[
            RouteAnnotation(span_id="s_policy", field="rules",
                            semantic_role="constraint", executable=False),
            RouteAnnotation(span_id="s_failure", field="behavior",
                            semantic_role="failure_mode",
                            construct_target="EXCEPTION_FLOW",
                            slot_target="condition", executable=False),
        ],
    )
    flow = FlowStructureIR()
    blocks = BlockStructureIR()
    symbols = SymbolTable()
    steps: list = []

    mock_client.call_json.return_value = {
        "constraints": [
            {"constraint_id": "c_bad", "text": "Handle missing timeframe",
             "kind": "prohibition", "targets": ["global"],
             "source_span_ids": ["s_failure"]},
        ],
    }
    extractor = ConstraintExtractor(pipeline_config, mock_client)
    result = extractor.execute((spans, routes, flow, blocks, symbols, steps))

    # Prompt: policy span present, failure excluded
    prompt = mock_client.call_json.call_args.kwargs["user_prompt"]
    assert "Do not invent facts" in prompt
    assert "Missing timeframe" not in prompt
    # Output: failure-sourced constraint rejected
    assert len(result) == 0, "Failure-sourced constraint must be rejected"


def test_d5_stage9_pure_delegation_intent_excluded(
    pipeline_config: MagicMock,
    mock_client: MagicMock,
) -> None:
    """D5: pure delegation_intent excluded from constraint prompt+output."""
    from nl2spl.pipeline.stages.stage9_constraint_extractor import ConstraintExtractor

    spans = [SpanIR("s_del", "delegate research")]
    routes = FieldRouteIR(
        rules=["s_del"],
        annotations=[
            RouteAnnotation(span_id="s_del", field="behavior",
                            semantic_role="delegation_intent",
                            route_family="delegation_boundary",
                            executable=False),
        ],
    )
    flow = FlowStructureIR()
    blocks = BlockStructureIR()
    symbols = SymbolTable()
    steps: list = []

    mock_client.call_json.return_value = {
        "constraints": [
            {"constraint_id": "c_del", "text": "delegate research",
             "kind": "obligation", "targets": ["delegation"],
             "source_span_ids": ["s_del"]},
        ],
    }
    extractor = ConstraintExtractor(pipeline_config, mock_client)
    result = extractor.execute((spans, routes, flow, blocks, symbols, steps))

    prompt = mock_client.call_json.call_args.kwargs["user_prompt"]
    assert "delegate research" not in prompt, "Pure delegation intent excluded from prompt"
    assert len(result) == 0, "Pure delegation intent constraint rejected at parse"


def test_d5_stage9_delegation_boundary_rule_survives(
    pipeline_config: MagicMock,
    mock_client: MagicMock,
) -> None:
    """D5: delegation boundary rule ('Only delegate...when...') survives."""
    from nl2spl.pipeline.stages.stage9_constraint_extractor import ConstraintExtractor

    spans = [
        SpanIR("s_rule", "Only delegate source collection when external sources are required."),
    ]
    routes = FieldRouteIR(
        rules=["s_rule"],
        annotations=[
            RouteAnnotation(span_id="s_rule", field="behavior",
                            semantic_role="delegation_intent",
                            route_family="delegation_boundary",
                            executable=False),
        ],
    )
    flow = FlowStructureIR()
    blocks = BlockStructureIR()
    symbols = SymbolTable()
    steps: list = []

    mock_client.call_json.return_value = {
        "constraints": [
            {"constraint_id": "c_ok", "text": "Only delegate when external needed",
             "kind": "obligation", "targets": ["delegation"],
             "source_span_ids": ["s_rule"]},
        ],
    }
    extractor = ConstraintExtractor(pipeline_config, mock_client)
    result = extractor.execute((spans, routes, flow, blocks, symbols, steps))

    # Prompt includes boundary rule span
    prompt = mock_client.call_json.call_args.kwargs["user_prompt"]
    assert "Only delegate" in prompt, "Boundary rule must appear in rules context"
    # Constraint survives
    assert len(result) == 1, "Boundary rule constraint must survive"
    assert result[0].constraint_id == "c_ok"


# ===========================================================================
# Route-driven delegation IRS diagnostics
# ===========================================================================


def _run_delegation_irs(
    routes: FieldRouteIR,
    worker_plan: WorkerPlanIR | None = None,
):
    registry = IRSCheckerRegistry()
    registry.register(WorkerDelegationIRSChecker())
    runner = IRSRunner(
        registry=registry,
        construct_registry=SPLConstructRegistry.default(),
        projector=DiagnosticProjector(),
    )
    return runner.run_stage(
        "stage3_5",
        IRSCheckContext(
            stage_name="stage3_5",
            routes=routes,
            worker_plan=worker_plan or WorkerPlanIR(main_worker_id="worker_main"),
        ),
    )


def test_irs_route_driven_delegation_diagnostic_from_annotation(
    pipeline_config: MagicMock,
    mock_client: MagicMock,
) -> None:
    """Route delegation intent annotation emits IRS diagnostic."""

    canonical = StructuralNLAdapter(mock_client).adapt(F0_STRUCTURAL_TEXT)
    spans = SpanSlicer(pipeline_config, mock_client).execute(canonical)
    mock_client.call_json.return_value = _route_annotations_for_spans(spans)
    routes, _ = FieldRouter(pipeline_config, mock_client).execute((spans, canonical))

    # Verify delegation annotations exist
    del_anns = routes.get_annotations_by_role("delegation_intent")
    assert len(del_anns) >= 1, "F0_STRUCTURAL_TEXT must have delegation annotation"

    result = _run_delegation_irs(routes)
    diags = [
        d for d in result.diagnostics
        if (d.target_ref or "").startswith("delegation_intent:")
    ]
    assert len(diags) >= 1
    for d in diags:
        assert d.diagnostic_id.startswith("irs_")
        assert d.kind == "type_or_contract_ambiguity"
        assert d.source_span_ids
        assert d.missing_slot is not None
        assert d.missing_slot.slot_name == "handoff_contract"


def test_irs_no_delegation_annotation_emits_no_bridge_diagnostic(
    pipeline_config: MagicMock,
    mock_client: MagicMock,
) -> None:
    """Hard-fact-only delegation no longer triggers delegation IRS diagnostic."""
    from nl2spl.canonical import (
        CanonicalCompileInput, DelegationIntentFact, EvidenceRef, HardFacts, RawSection,
    )

    section = RawSection(
        "sec_delegation_policy", "delegation_policy",
        "Delegation policy", "source gathering", 1,
    )
    canonical = CanonicalCompileInput(
        source_schema="structural_nl", schema_version="1.0",
        raw_text="Delegation policy:\nsource gathering",
        raw_sections=[section],
        hard_facts=HardFacts(
            delegation_intents=[
                DelegationIntentFact(
                    name="source_gathering", text="Source gathering",
                    evidence=[EvidenceRef(source_section_id="sec_delegation_policy")],
                ),
            ],
        ),
    )
    spans = SpanSlicer(pipeline_config, mock_client).execute(canonical)
    routes, _ = FieldRouter(pipeline_config, mock_client).execute((spans, canonical))

    assert routes.get_annotations_by_role("delegation_intent") == []

    result = _run_delegation_irs(routes)
    assert [
        d for d in result.diagnostics
        if (d.target_ref or "").startswith("delegation_intent:")
    ] == []


def test_orchestrator_promotes_delegation_irs_diagnostics(
    pipeline_config: MagicMock,
    mock_client: MagicMock,
) -> None:
    """Promoted IRS helper uses final RouteAnnotation diagnostics only."""
    from nl2spl.compiler.irs.result_store import IRSResultStore, IRSStageResult

    text = (
        "Task family: Test.\n\nInputs for each run:\nA request.\n\n"
        "Required outputs:\nA result.\n\nReusable process:\nDetermine type.\n\n"
        "Policies:\nDo not invent.\n\nFailure handling:\nMissing timeframe.\n\n"
        "Delegation policy:\nOptional source gathering if bounded.\n"
    )
    canonical = StructuralNLAdapter(mock_client).adapt(text)
    spans = SpanSlicer(pipeline_config, mock_client).execute(canonical)
    mock_client.call_json.return_value = _route_annotations_for_spans(spans)
    routes, _ = FieldRouter(pipeline_config, mock_client).execute((spans, canonical))

    result = _run_delegation_irs(routes)
    store = IRSResultStore()
    store.put_stage_result(IRSStageResult(
        stage_name="stage3_5",
        diagnostics=tuple(result.diagnostics),
    ))
    diags = PipelineOrchestrator._promoted_irs_diagnostics(store)
    # Route delegation annotation exists → route-driven diagnostics present
    del_anns = routes.get_annotations_by_role("delegation_intent")
    assert len(del_anns) >= 1
    assert len(diags) >= 1
    assert all(d.diagnostic_id.startswith("irs_") for d in diags)
    assert all(d.kind == "type_or_contract_ambiguity" for d in diags)


def test_only_route_annotations_drive_delegation_irs_diagnostics(
    pipeline_config: MagicMock,
    mock_client: MagicMock,
) -> None:
    """Unrelated hard facts in the same section do not create diagnostics."""
    from nl2spl.canonical import (
        CanonicalCompileInput, DelegationIntentFact, EvidenceRef, HardFacts,
        RawSection,
    )

    section = RawSection(
        "sec_delegation_policy", "delegation_policy",
        "Delegation policy",
        "Source gathering may be used if bounded. "
        "Template matching may be used if available.", 1,
    )
    canonical = CanonicalCompileInput(
        source_schema="structural_nl", schema_version="1.0",
        raw_text="Delegation policy:\nSource gathering. Template matching.",
        raw_sections=[section],
        hard_facts=HardFacts(
            delegation_intents=[
                DelegationIntentFact(
                    name="source_gathering", text="Source gathering",
                    evidence=[EvidenceRef(
                        source_section_id="sec_delegation_policy",
                        source_packet_id="p_delegation_source",
                    )],
                ),
                DelegationIntentFact(
                    name="template_matching", text="Template matching",
                    evidence=[EvidenceRef(
                        source_section_id="sec_delegation_policy",
                    )],
                ),
            ],
        ),
    )
    spans = SpanSlicer(pipeline_config, mock_client).execute(canonical)
    routes, _ = FieldRouter(pipeline_config, mock_client).execute((spans, canonical))

    from nl2spl.ir.field_route_ir import RouteAnnotation
    routes.annotations = [
        RouteAnnotation(
            span_id=spans[0].span_id if spans else "s_src",
            field="behavior",
            semantic_role="delegation_intent",
            route_family="delegation_boundary",
            executable=False,
            source_section_id="sec_delegation_policy",
            source_packet_id="p_delegation_source",
        ),
    ]
    # Force behavior list so the annotation span is accessible
    routes.behavior = [a.span_id for a in routes.annotations]

    result = _run_delegation_irs(routes)
    diags = [
        d for d in result.diagnostics
        if (d.target_ref or "").startswith("delegation_intent:")
    ]
    refs = {d.target_ref for d in diags}
    assert len(diags) == 1, f"Got {len(diags)} with refs {refs}"
    assert refs == {f"delegation_intent:{routes.annotations[0].span_id}"}

def test_d5_stage8_profile_annotation_only_no_old_list(
    pipeline_config: MagicMock,
    mock_client: MagicMock,
) -> None:
    """D5: annotation-only profile span used when old domain list is empty."""
    from nl2spl.pipeline.stages.stage8_profile_extractor import ProfileExtractor

    spans = [
        SpanIR("s_task", "Internal newsletters and announcements."),
        SpanIR("s_failure", "Missing timeframe."),
    ]
    # domain=[] — only annotation provides profile evidence
    routes = FieldRouteIR(
        domain=[], identity=[], audience=[],
        annotations=[
            RouteAnnotation(span_id="s_task", field="domain",
                            semantic_role="profile_domain", executable=False),
            RouteAnnotation(span_id="s_failure", field="behavior",
                            semantic_role="failure_mode",
                            construct_target="EXCEPTION_FLOW",
                            slot_target="condition", executable=False),
        ],
    )
    symbols = SymbolTable()

    mock_client.call_json.return_value = {
        "persona": {"role": "Assistant"}, "aspects": [], "concepts": [],
    }
    extractor = ProfileExtractor(pipeline_config, mock_client)
    extractor.execute((spans, routes, symbols))

    prompt = mock_client.call_json.call_args.kwargs["user_prompt"]
    # Profile annotation span appears in identity/domain evidence
    assert "Internal newsletters" in prompt
    # Failure span NOT in strong profile sections (identity/domain/audience)
    id_start = prompt.index("identity spans")
    domain_start = prompt.index("domain spans")
    audience_start = prompt.index("audience spans") if "audience spans" in prompt else len(prompt)
    profile_sections = prompt[id_start:max(domain_start, audience_start) + 1000]
    assert "Missing timeframe" not in profile_sections, (
        "Failure span must not appear in strong profile evidence sections"
    )


def test_d5_worker_scoped_stage6_child_failure_guard(
    pipeline_config: MagicMock,
    mock_client: MagicMock,
) -> None:
    """D5: child-owned failure span does not become child variable."""
    from nl2spl.ir.resource_registry_ir import WorkerScopedResourceIR
    from nl2spl.ir.worker_plan_ir import (
        WorkerBlockPlanIR, WorkerFlowPlanIR, WorkerHandoffIR,
        WorkerPlanIR, WorkerSpecIR, InputBindingIR,
        InvokeLocationHintIR, OutputBindingIR,
    )

    main_flow = FlowStructureIR(main_flow_spans=["s_main"])
    child_flow = FlowStructureIR(main_flow_spans=["s_fail"])
    main_blocks = BlockStructureIR(
        main_flow_blocks=[BlockIR("b_main", "SEQUENTIAL", None, ["s_main"])]
    )
    child_blocks = BlockStructureIR(
        main_flow_blocks=[BlockIR("b_child", "SEQUENTIAL", None, ["s_fail"])]
    )
    wf = WorkerFlowPlanIR(worker_flows={
        "worker_main": main_flow, "worker_child": child_flow,
    })
    wb = WorkerBlockPlanIR(worker_blocks={
        "worker_main": main_blocks, "worker_child": child_blocks,
    })
    handoff = WorkerHandoffIR(
        handoff_id="h_main_child", from_worker="worker_main",
        to_worker="worker_child", api_ref=None, mode="invoke",
        condition_text=None, ordering="after",
        input_bindings=[InputBindingIR("in", "child_in", True)],
        output_bindings=[OutputBindingIR("child_out", "out", True, "set")],
        invoke_location_hint=InvokeLocationHintIR(
            flow_kind="main", flow_id=None,
            after_span_id="s_main", before_span_id=None,
            block_hint="unknown",
        ),
    )
    wp = WorkerPlanIR(
        main_worker_id="worker_main",
        workers=[
            WorkerSpecIR(worker_id="worker_main", worker_name="Main",
                         kind="main", purpose="Main",
                         owned_span_ids=["s_main"],
                         input_contract=[], output_contract=[],
                         boundary_kind="main_worker"),
            WorkerSpecIR(worker_id="worker_child", worker_name="Child",
                         kind="child", purpose="Child worker",
                         owned_span_ids=["s_fail"],
                         input_contract=[], output_contract=[],
                         boundary_kind="bounded_subtask"),
        ],
        handoffs=[handoff],
    )

    routes = FieldRouteIR(
        behavior=["s_main", "s_fail"],
        annotations=[
            RouteAnnotation(span_id="s_main", field="behavior",
                            semantic_role="process_step", executable=True),
            RouteAnnotation(span_id="s_fail", field="behavior",
                            semantic_role="failure_mode",
                            construct_target="EXCEPTION_FLOW",
                            slot_target="condition",
                            executable=False),
        ],
    )
    spans = [SpanIR("s_main", "Main work."), SpanIR("s_fail", "Missing timeframe.")]

    # Main + child LLM responses
    mock_client.call_json.side_effect = [
        {"variables": [{"name": "main_var", "data_type": "text",
                         "required": False, "description": "Main var",
                         "source": "step"}],
         "files": [], "apis": [], "types": []},
        {"variables": [{"name": "missing_timeframe", "data_type": "text",
                         "required": False, "description": "Failure var",
                         "source": "step"},
                        {"name": "child_var", "data_type": "text",
                         "required": False, "description": "Child var",
                         "source": "step"}],
         "files": [], "apis": [], "types": []},
    ]

    result, _ = ResourceExtractor(pipeline_config, mock_client).execute_worker_scoped(
        spans, routes, wf, wb, wp,
    )
    assert isinstance(result, WorkerScopedResourceIR)
    # Child scope: failure variable should be rejected
    if "worker_child" in result.worker_resources:
        child_vars = {v.name for v in result.worker_resources["worker_child"].variables}
        assert "missing_timeframe" not in child_vars, (
            "Child failure-derived variable must be rejected"
        )
        assert "child_var" in child_vars, "Legitimate child variable must survive"


def test_stage2_route_diagnostics_stay_internal(
    pipeline_config: MagicMock,
    mock_client: MagicMock,
) -> None:
    """Stage 2 route diagnostics stay in route IR and do not enter feedback."""

    canonical = StructuralNLAdapter(mock_client).adapt(STRUCTURAL_TEXT)
    spans = SpanSlicer(pipeline_config, mock_client).execute(canonical)

    # LLM returns valid annotations + one route diagnostic
    failure_span = next((s for s in spans if "Evidence shortage" in s.text), None)
    assert failure_span is not None

    mock_client.call_json.return_value = {
        "annotations": [
            {"span_id": failure_span.span_id, "field": "behavior",
             "semantic_role": "failure_mode",
             "construct_target": "EXCEPTION_FLOW",
             "slot_target": "condition", "executable": False},
        ],
        "split_recommendations": [],
        "diagnostics": [
            {"span_id": failure_span.span_id,
             "kind": "mixed_failure_semantics",
             "message": "Failure condition may need handler text."},
        ],
    }

    from nl2spl.pipeline.orchestrator import PipelineOrchestrator
    orchestrator = PipelineOrchestrator(pipeline_config)
    orchestrator.client = mock_client

    # Mock all other stages on the worker-aware path.
    from unittest.mock import MagicMock as M
    from nl2spl.ir.worker_ir import WorkerIR
    from nl2spl.ir.resource_registry_ir import WorkerScopedResourceIR
    from nl2spl.ir.worker_plan_ir import (
        WorkerBlockPlanIR,
        WorkerFlowPlanIR,
        WorkerPlanIR,
        WorkerSpecIR,
        WorkerStepPlanIR,
    )

    routes = FieldRouteIR(behavior=[span.span_id for span in spans])
    worker_plan = WorkerPlanIR(
        main_worker_id="worker_main",
        workers=[
            WorkerSpecIR(
                "worker_main", "Main", "main", "Main worker",
                [span.span_id for span in spans], [], [], [], [],
                "main_worker", [], "",
            )
        ],
        candidates=[],
        decisions=[],
        handoffs=[],
    )
    worker_flow_plan = WorkerFlowPlanIR(
        worker_flows={
            "worker_main": FlowStructureIR(main_flow_spans=[span.span_id for span in spans])
        }
    )
    worker_block_plan = WorkerBlockPlanIR(
        worker_blocks={"worker_main": BlockStructureIR()}
    )
    worker_step_plan = WorkerStepPlanIR(
        main_worker_id="worker_main",
        worker_steps={"worker_main": []},
    )
    worker = WorkerIR(worker_name="Main", description="Main", steps=[])

    setattr(orchestrator, "_run_stage3", M(return_value=(spans, routes)))
    setattr(orchestrator, "_run_stage3_5", M(return_value=worker_plan))
    setattr(orchestrator, "_run_stage4", M(return_value=worker_flow_plan))
    setattr(orchestrator, "_run_stage5", M(return_value=worker_block_plan))
    setattr(
        orchestrator,
        "_run_stage6_worker_scoped",
        M(return_value=(WorkerScopedResourceIR(global_resources=ResourceRegistryIR()), SymbolTable(), [])),
    )
    setattr(orchestrator, "_run_stage7_worker_scoped", M(return_value=(worker_step_plan, SymbolTable(), [])))
    setattr(orchestrator, "_run_stage8", M(return_value=M()))
    setattr(orchestrator, "_run_stage9", M(return_value=[]))
    setattr(
        orchestrator,
        "_run_normalization_worker_scoped",
        M(return_value=(worker_flow_plan, worker_block_plan, worker_step_plan, SymbolTable(), [], [])),
    )
    setattr(orchestrator, "_run_stage10_worker_scoped", M(return_value=worker))
    setattr(orchestrator, "_run_stage11", M(return_value=("SPL", [], [])))

    result = orchestrator.run(STRUCTURAL_TEXT)

    # Stage 2 route diagnostics remain available for debugging.
    stage2_routes = result.intermediate_results["stage2_routes"]
    route_diags = stage2_routes.structured_route_diagnostics
    assert any(
        d["kind"].startswith("route_refinement_")
        for d in route_diags
    ), f"Expected route refinement diagnostics in stage2_routes, got {route_diags}"
    assert any(
        "Failure condition may need handler text" in d["message"]
        for d in route_diags
    ), f"Expected LLM diagnostic message in stage2 route diagnostics: {route_diags}"

    # They must not become final user-facing requirement diagnostics.
    assert not any(
        d.kind.startswith("route_refinement_")
        for d in result.compile_diagnostics
    ), f"route_refinement_* leaked into compile_diagnostics: {result.compile_diagnostics}"

    feedback = render_feedback_report(
        spl_text=result.spl_text,
        completeness=result.completeness,
        diagnostics=result.compile_diagnostics,
        assumptions=result.assumptions,
        traces=result.traces,
        adapter_warnings=result.adapter_warnings,
        validation_errors=result.validation_errors,
        validation_warnings=result.validation_warnings,
    )
    assert "route_refinement_" not in feedback
    assert "Failure condition may need handler text" not in feedback
    assert result.readable_report == ""
