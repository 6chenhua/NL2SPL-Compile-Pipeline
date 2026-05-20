"""Integration tests for v5 IRS pipeline -- scenarios with IRS flags enabled.

Tests mock LLM stages but exercise the full orchestrator path with
Stage 4/7 IRS checks, consolidation, and resource hardening enabled.
"""

import contextlib
from pathlib import Path
from unittest.mock import MagicMock, patch

from nl2spl.config import LLMConfig, PipelineConfig
from nl2spl.ir.block_structure_ir import BlockIR, BlockStructureIR
from nl2spl.ir.field_route_ir import FieldRouteIR
from nl2spl.ir.flow_structure_ir import ExceptionFlow, FlowStructureIR
from nl2spl.ir.resource_registry_ir import (
    ResourceRegistryIR,
    VariableSpec,
    WorkerScopedResourceIR,
)
from nl2spl.ir.span_ir import SpanIR
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.ir.worker_plan_ir import (
    WorkerBlockPlanIR,
    WorkerFlowPlanIR,
    WorkerPlanIR,
    WorkerSpecIR,
    WorkerStepPlanIR,
)
from nl2spl.pipeline.orchestrator import PipelineOrchestrator, PipelineResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _orch(
    tmp_path: Path,
    *,
    stage4_check: bool = True,
    stage7_check: bool = True,
    consolidation: bool = True,
    resource_filter: bool = False,
) -> PipelineOrchestrator:
    return PipelineOrchestrator(PipelineConfig(
        llm=LLMConfig(api_key="test-key"),
        output_dir=tmp_path / "output",
        save_intermediate=False,
        enable_worker_boundary_planner=True,
        enable_irs_stage4_exception_flow_check=stage4_check,
        enable_irs_stage7_step_check=stage7_check,
        enable_irs_diagnostic_consolidation=consolidation,
        enable_resource_name_filter=resource_filter,
        enable_irs_post_normalize_check=False,
    ))


def _run_orch(
    orch: PipelineOrchestrator,
    *,
    spans: list | None = None,
    routes: FieldRouteIR | None = None,
    plan: WorkerPlanIR | None = None,
    flow_plan: WorkerFlowPlanIR | None = None,
    block_plan: WorkerBlockPlanIR | None = None,
    step_plan: WorkerStepPlanIR | None = None,
    resources: ResourceRegistryIR | None = None,
    skip_norm_mock: bool = False,
    **kwargs: object,
) -> "PipelineResult":
    """Mock all LLM stages, run pipeline, return result."""
    s = spans or [SpanIR("s1", "Process.")]
    r = routes or FieldRouteIR(behavior=["s1"])
    p = plan or WorkerPlanIR(
        main_worker_id="worker_main",
        workers=[
            WorkerSpecIR("worker_main", "Main", "main", "Main",
                         ["s1"], [], [], [], [], "main_worker", [], ""),
        ],
        candidates=[], decisions=[], handoffs=[],
    )
    fp = flow_plan or WorkerFlowPlanIR(
        worker_flows={"worker_main": FlowStructureIR(main_flow_spans=["s1"])}
    )
    bp = block_plan or WorkerBlockPlanIR(
        worker_blocks={"worker_main": BlockStructureIR(
            main_flow_blocks=[BlockIR("b1", "SEQUENTIAL", None, ["s1"])]
        )}
    )
    sym = SymbolTable()
    ws_res = resources or ResourceRegistryIR()
    ws_resources = WorkerScopedResourceIR(global_resources=ws_res)
    sp = step_plan or WorkerStepPlanIR(main_worker_id="worker_main", worker_steps={"worker_main": []})
    wm = MagicMock()
    wm.steps = []
    wm.child_workers = []
    wm.scoped_steps = False

    extra_patches = kwargs.pop("extra_patches", [])
    skip_norm = kwargs.pop("skip_norm_mock", False)
    patches = [
        patch.object(orch, "_run_stage1", return_value=s),
        patch.object(orch, "_run_stage2", return_value=(r, [])),
        patch.object(orch, "_run_stage3", return_value=(s, r)),
        patch.object(orch, "_run_stage3_5", return_value=p),
        patch.object(orch, "_run_stage4", return_value=fp),
        patch.object(orch, "_run_stage5", return_value=bp),
        patch.object(orch, "_run_stage6_worker_scoped", return_value=(ws_resources, sym, [])),
        patch.object(orch, "_run_stage7_worker_scoped", return_value=(sp, sym, [])),
        patch.object(orch, "_run_stage8", return_value=MagicMock()),
        patch.object(orch, "_run_stage9", return_value=[]),
        patch.object(orch, "_run_stage10_worker_scoped", return_value=wm),
        patch.object(orch, "_run_stage11", return_value=("SPL", [], [])),
    ]
    if not skip_norm:
        patches.append(patch.object(orch, "_run_normalization_worker_scoped",
                         return_value=(fp, bp, sp, sym, [], [])))
    patches.extend(extra_patches)

    result_container: list = []

    def _run_with_patches():
        with contextlib.ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            result_container.append(orch.run("test"))

    _run_with_patches()
    return result_container[0]


# ---------------------------------------------------------------------------
# Scenario 1: No failure signal -> no EXCEPTION_FLOW, no missing_handler
# ---------------------------------------------------------------------------

class TestNoFailureSignal:
    def test_no_exception_flow_and_no_missing_handler(self, tmp_path: Path):
        orch = _orch(tmp_path)
        result = _run_orch(orch)
        kinds = {d.kind for d in result.compile_diagnostics}
        assert "missing_handler" not in kinds
        # With IRS consolidation on, stage4 check finds 0 exception flows -> 0 diags
        sat = result.intermediate_results.get("construct_satisfaction", {}).get("stage4", [])
        assert len(sat) == 0


# ---------------------------------------------------------------------------
# Scenario 2: Failure condition only -> partial EXCEPTION_FLOW + missing_handler
# ---------------------------------------------------------------------------

class TestFailureConditionOnly:
    def test_failure_condition_stage4_partial_satisfaction(self, tmp_path: Path):
        """Stage 4 IRS: source-backed condition -> partial EXCEPTION_FLOW satisfaction."""
        orch = _orch(tmp_path)
        flow_plan = WorkerFlowPlanIR(worker_flows={
            "worker_main": FlowStructureIR(
                main_flow_spans=["s1"],
                exception_flows=[ExceptionFlow("exc_1", "Over budget", ["s1"])],
            ),
        })
        result = _run_orch(orch, flow_plan=flow_plan)

        sat = result.intermediate_results["construct_satisfaction"]["stage4"]
        assert len(sat) == 1
        assert sat[0].construct_id == "worker:worker_main.exception_flow:exc_1"
        assert sat[0].renderable is True
        assert sat[0].completeness == "partial"

    def test_failure_condition_normalizer_emits_missing_handler(self, tmp_path: Path):
        """PostNormalizeIRSChecker emits missing_handler for exception flow
        without handler.  Uses legacy path."""
        orch = PipelineOrchestrator(PipelineConfig(
            llm=LLMConfig(api_key="test-key"),
            output_dir=tmp_path / "output",
            save_intermediate=False,
            enable_worker_boundary_planner=False,  # legacy
        ))
        s = [SpanIR("s1", "Process.")]
        r = FieldRouteIR(behavior=["s1"])
        sym = SymbolTable()
        import nl2spl.ir.worker_ir as wir
        wm = wir.WorkerIR(
            worker_name="MainWorker", description="Main",
            main_flow=wir.FlowRef(),
            exception_flows=[
                wir.ExceptionFlowRef("exc_1", "If provenance failure is detected, halt."),
            ],
            steps=[],
            child_workers=[],
        )
        flow_s = FlowStructureIR(
            main_flow_spans=["s1"],
            exception_flows=[ExceptionFlow("exc_1", "If provenance failure is detected, halt.", ["s1"])],
        )
        with (
            patch.object(orch, "_run_stage1", return_value=s),
            patch.object(orch, "_run_stage2", return_value=(r, [])),
            patch.object(orch, "_run_stage3", return_value=(s, r)),
            patch.object(orch, "_run_stage4", return_value=flow_s),
            patch.object(orch, "_run_stage5", return_value=BlockStructureIR()),
            patch.object(orch, "_run_stage6", return_value=(ResourceRegistryIR(), sym, [])),
            patch.object(orch, "_run_stage7", return_value=([], sym, [])),
            patch.object(orch, "_run_stage8", return_value=MagicMock()),
            patch.object(orch, "_run_stage9", return_value=[]),
            patch.object(orch, "_run_stage10", return_value=wm),
            patch.object(orch, "_run_stage11", return_value=("SPL", [], [])),
        ):
            result = orch.run("test")

        kinds = {d.kind for d in result.compile_diagnostics}
        assert "missing_handler" in kinds


# ---------------------------------------------------------------------------
# Scenario 3: Vague failure policy -> type_or_contract_ambiguity
# ---------------------------------------------------------------------------

class TestVagueFailurePolicy:
    def test_vague_policy_type_or_contract_ambiguity(self, tmp_path: Path):
        orch = _orch(tmp_path)
        flow_plan = WorkerFlowPlanIR(worker_flows={
            "worker_main": FlowStructureIR(
                main_flow_spans=["s1"],
                exception_flows=[ExceptionFlow("exc_1", "Handle errors", [])],
            ),
        })
        result = _run_orch(orch, flow_plan=flow_plan)

        # Stage 4 IRS: condition assumed (no spans)
        sat = result.intermediate_results["construct_satisfaction"]["stage4"]
        assert len(sat) == 1
        assert sat[0].renderable is False
        cond = _find_slot(sat[0], "condition")
        assert cond.status == "assumed"

        # With consolidation on, the stage4 type_or_contract_ambiguity enters compile_diags
        kinds = {d.kind for d in result.compile_diagnostics}
        assert "type_or_contract_ambiguity" in kinds


# ---------------------------------------------------------------------------
# Scenario 4: REQUEST_INPUT without ask signal
# ---------------------------------------------------------------------------

class TestRequestInputWithoutAskSignal:
    def test_no_executable_request_input(self, tmp_path: Path):
        orch = _orch(tmp_path)
        step_plan = WorkerStepPlanIR(
            main_worker_id="worker_main",
            worker_steps={
                "worker_main": [
                    StepIR("st_1", "Ask user", [], "REQUEST_INPUT", [], [], None, "main", "b_1", None),
                ],
            },
        )
        result = _run_orch(orch, step_plan=step_plan)

        # Stage 7 IRS: REQUEST_INPUT without source_span_ids -> type_or_contract_ambiguity
        sat = result.intermediate_results["construct_satisfaction"]["stage7"]
        req_input = [r for r in sat if r.construct_type == "REQUEST_INPUT"]
        assert len(req_input) == 1
        assert req_input[0].renderable is False

        kinds = {d.kind for d in result.compile_diagnostics}
        assert "type_or_contract_ambiguity" in kinds


# ---------------------------------------------------------------------------
# Scenario 5: CALL_API with context-only mention
# ---------------------------------------------------------------------------

class TestCallAPIContextOnly:
    def test_no_executable_call_api(self, tmp_path: Path):
        orch = _orch(tmp_path)
        step_plan = WorkerStepPlanIR(
            main_worker_id="worker_main",
            worker_steps={
                "worker_main": [
                    StepIR("st_1", "Call API", [], "CALL_API", [], [], None, "main", "b_1", None),
                ],
            },
        )
        result = _run_orch(orch, step_plan=step_plan)

        # Stage 7 IRS: CALL_API without integration_ref -> type_or_contract_ambiguity
        sat = result.intermediate_results["construct_satisfaction"]["stage7"]
        call_api = [r for r in sat if r.construct_type == "CALL_API"]
        assert len(call_api) == 1
        assert call_api[0].renderable is False

        kinds = {d.kind for d in result.compile_diagnostics}
        assert "type_or_contract_ambiguity" in kinds


# ---------------------------------------------------------------------------
# Scenario 6: Incomplete delegation -> no INVOKE_WORKER
# ---------------------------------------------------------------------------

class TestIncompleteDelegation:
    def test_no_executable_invoke_worker(self, tmp_path: Path):
        orch = _orch(tmp_path)
        step_plan = WorkerStepPlanIR(
            main_worker_id="worker_main",
            worker_steps={
                "worker_main": [
                    StepIR("st_1", "Invoke worker", [], "INVOKE_WORKER", [], [], None, "main", "b_1", None),
                ],
            },
        )
        result = _run_orch(orch, step_plan=step_plan)

        # Stage 7 IRS: INVOKE_WORKER without handoff_id -> type_or_contract_ambiguity
        sat = result.intermediate_results["construct_satisfaction"]["stage7"]
        invoke = [r for r in sat if r.construct_type == "INVOKE_WORKER"]
        assert len(invoke) == 1
        assert invoke[0].renderable is False

        kinds = {d.kind for d in result.compile_diagnostics}
        assert "type_or_contract_ambiguity" in kinds


# ---------------------------------------------------------------------------
# Scenario 7: Complete source-backed delegation
# ---------------------------------------------------------------------------

class TestCompleteDelegation:
    def test_complete_delegation_allowed(self, tmp_path: Path):
        orch = _orch(tmp_path)
        step_plan = WorkerStepPlanIR(
            main_worker_id="worker_main",
            worker_steps={
                "worker_main": [
                    StepIR("st_1", "Invoke child", ["s1"], "INVOKE_WORKER", ["req"], ["result"], "ChildWorker", "main", "b_1", handoff_id="handoff_1"),
                ],
            },
        )
        result = _run_orch(orch, step_plan=step_plan)

        # Stage 7 IRS: INVOKE_WORKER with handoff_id + integration_ref -> satisfied
        sat = result.intermediate_results["construct_satisfaction"]["stage7"]
        invoke = [r for r in sat if r.construct_type == "INVOKE_WORKER"]
        assert len(invoke) == 1
        assert invoke[0].renderable is True
        assert invoke[0].completeness == "complete"


# ---------------------------------------------------------------------------
# Scenario 8: Required output without producer
# ---------------------------------------------------------------------------

class TestRequiredOutputWithoutProducer:
    def test_missing_output_producer(self, tmp_path: Path):
        """Use legacy path: _ensure_required_main_outputs checks global output variables."""
        orch = PipelineOrchestrator(PipelineConfig(
            llm=LLMConfig(api_key="test-key"),
            output_dir=tmp_path / "output",
            save_intermediate=False,
            enable_worker_boundary_planner=False,  # legacy path
        ))
        resources = ResourceRegistryIR(
            variables=[
                VariableSpec("draft", "text", True, "Final draft", "output"),
            ],
        )
        s = [SpanIR("s1", "Process.")]
        r = FieldRouteIR(behavior=["s1"])
        sym = SymbolTable()
        wm = MagicMock(); wm.steps = []; wm.child_workers = []; wm.scoped_steps = False

        with (
            patch.object(orch, "_run_stage1", return_value=s),
            patch.object(orch, "_run_stage2", return_value=(r, [])),
            patch.object(orch, "_run_stage3", return_value=(s, r)),
            patch.object(orch, "_run_stage4", return_value=FlowStructureIR()),
            patch.object(orch, "_run_stage5", return_value=BlockStructureIR()),
            patch.object(orch, "_run_stage6", return_value=(resources, sym, [])),
            patch.object(orch, "_run_stage7", return_value=([], sym, [])),
            patch.object(orch, "_run_stage8", return_value=MagicMock()),
            patch.object(orch, "_run_stage9", return_value=[]),
            patch.object(orch, "_run_stage10", return_value=wm),
            patch.object(orch, "_run_stage11", return_value=("SPL", [], [])),
        ):
            result = orch.run("test")

        kinds = {d.kind for d in result.compile_diagnostics}
        assert "missing_output_producer" in kinds


# ---------------------------------------------------------------------------
# Scenario 9: LLMConflictAnalyzer disabled = v4 behavior
# ---------------------------------------------------------------------------

class TestConflictAnalyzerDisabled:
    def test_disabled_analyzer_no_semantic_conflict(self, tmp_path: Path):
        orch = _orch(tmp_path)
        result = _run_orch(orch)
        kinds = {d.kind for d in result.compile_diagnostics}
        assert "semantic_conflict" not in kinds


# ---------------------------------------------------------------------------
# Scenario 10: Resource hardening
# ---------------------------------------------------------------------------

class TestResourceHardening:
    def test_schema_variable_filtered(self, tmp_path: Path):
        """Flag on: Stage 6 filter_warnings reach adapter_warnings.
        Full parse-boundary filter logic is tested in test_resource_extractor_hardening.py."""
        orch = PipelineOrchestrator(PipelineConfig(
            llm=LLMConfig(api_key="test-key"),
            output_dir=tmp_path / "output",
            save_intermediate=False,
            enable_worker_boundary_planner=False,
            enable_resource_name_filter=True,
        ))
        s = [SpanIR("s1", "Process.")]
        r = FieldRouteIR(behavior=["s1"])
        sym = SymbolTable()
        wm = MagicMock(); wm.steps = []; wm.child_workers = []; wm.scoped_steps = False
        fake_warnings = ["Rejected schema-looking variable 'span_id': reserved IR/schema name: span_id"]
        with (
            patch.object(orch, "_run_stage1", return_value=s),
            patch.object(orch, "_run_stage2", return_value=(r, [])),
            patch.object(orch, "_run_stage3", return_value=(s, r)),
            patch.object(orch, "_run_stage4", return_value=FlowStructureIR()),
            patch.object(orch, "_run_stage5", return_value=BlockStructureIR()),
            patch.object(orch, "_run_stage6", return_value=(ResourceRegistryIR(), sym, fake_warnings)),
            patch.object(orch, "_run_stage7", return_value=([], sym, [])),
            patch.object(orch, "_run_stage8", return_value=MagicMock()),
            patch.object(orch, "_run_stage9", return_value=[]),
            patch.object(orch, "_run_stage10", return_value=wm),
            patch.object(orch, "_run_stage11", return_value=("SPL", [], [])),
        ):
            result = orch.run("test")

        assert any("Rejected schema-looking variable" in w for w in result.adapter_warnings)
        assert any("span_id" in w for w in result.adapter_warnings)

    def test_legitimate_variable_preserved(self, tmp_path: Path):
        orch = _orch(tmp_path)
        resources_reg = ResourceRegistryIR(
            variables=[VariableSpec("purchase_request", "text", True, "Purchase request", "input")],
        )
        result = _run_orch(orch, resources=resources_reg)
        ws_res = result.intermediate_results["stage6_worker_scoped_resources"]
        all_vars = ws_res.get_all_variables()
        assert any(v.name == "purchase_request" for v in all_vars)


# ---------------------------------------------------------------------------
# Cross-cutting: intermediate_results side-channel
# ---------------------------------------------------------------------------

class TestSideChannel:
    def test_construct_satisfaction_present(self, tmp_path: Path):
        orch = _orch(tmp_path)
        result = _run_orch(orch)
        assert "construct_satisfaction" in result.intermediate_results
        assert "stage_local_diagnostics" in result.intermediate_results
        assert isinstance(result.intermediate_results["construct_satisfaction"], dict)
        assert isinstance(result.intermediate_results["stage_local_diagnostics"], dict)


# ---------------------------------------------------------------------------
# Post-gate missing_handler (Phase 5)
# ---------------------------------------------------------------------------


class TestPostGateMissingHandler:
    def test_handler_removed_by_gate_emits_missing_handler(self, tmp_path: Path):
        """Gate post-gate check: handler removed → missing_handler from Gate."""
        from nl2spl.ir.worker_ir import (
            ExceptionFlowRef,
            FlowRef,
            WorkerIR,
        )

        orch = _orch(tmp_path)
        exc_flow = ExceptionFlow("exc_1", "Missing timeframe.", ["s1"])
        flow_plan = WorkerFlowPlanIR(
            worker_flows={"worker_main": FlowStructureIR(
                main_flow_spans=["s1"],
                exception_flows=[exc_flow],
            )},
        )
        worker = WorkerIR(
            worker_name="MainWorker",
            description="Main",
            main_flow=FlowRef(),
            exception_flows=[
                ExceptionFlowRef(
                    flow_id="exc_1",
                    condition_text="Missing timeframe.",
                    blocks=[],
                ),
            ],
            steps=[
                StepIR(
                    step_id="st_h", text="Handle missing timeframe.",
                    source_span_ids=[],  # no source → Gate filters
                    command_type="GENERAL_COMMAND",
                    flow_ref="exc_1",
                ),
            ],
            child_workers=[],
        )
        result = _run_orch(
            orch, flow_plan=flow_plan,
            extra_patches=[
                patch.object(orch, "_run_stage10_worker_scoped",
                            return_value=worker),
            ],
        )
        mh = [d for d in result.compile_diagnostics
              if d.kind == "missing_handler"]
        # Gate's _post_gate_missing_handler emits a single diagnostic
        # with worker-scoped target_ref.
        assert len(mh) == 1
        assert "exc_1" in mh[0].target_ref
        assert mh[0].blocks_completion is True
        assert mh[0].blocks_rendering is False

    def test_handler_with_source_survives_gate_no_duplicate_mh(self, tmp_path: Path):
        """Handler step with source_span_ids survives Gate → no missing_handler."""
        from nl2spl.ir.worker_ir import (
            ExceptionFlowRef,
            FlowRef,
            WorkerIR,
        )

        orch = _orch(tmp_path)
        exc_flow = ExceptionFlow("exc_1", "Missing timeframe.", ["s1"])
        flow_plan = WorkerFlowPlanIR(
            worker_flows={"worker_main": FlowStructureIR(
                main_flow_spans=["s1"],
                exception_flows=[exc_flow],
            )},
        )
        worker = WorkerIR(
            worker_name="MainWorker",
            description="Main",
            main_flow=FlowRef(),
            exception_flows=[
                ExceptionFlowRef(
                    flow_id="exc_1",
                    condition_text="Missing timeframe.",
                    blocks=[],
                ),
            ],
            steps=[
                StepIR(
                    step_id="st_h", text="Handle missing timeframe.",
                    source_span_ids=["s1"],
                    command_type="GENERAL_COMMAND",
                    flow_ref="exc_1",
                ),
            ],
            child_workers=[],
        )
        result = _run_orch(
            orch, flow_plan=flow_plan,
            extra_patches=[
                patch.object(orch, "_run_stage10_worker_scoped",
                            return_value=worker),
            ],
        )
        mh = [d for d in result.compile_diagnostics
              if d.kind == "missing_handler"]
        assert len(mh) == 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_slot(report, slot_name: str):
    for s in report.slots:
        if s.slot_name == slot_name:
            return s
    raise KeyError(slot_name)
