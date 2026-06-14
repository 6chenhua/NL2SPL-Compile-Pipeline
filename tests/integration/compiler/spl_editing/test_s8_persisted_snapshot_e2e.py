"""S8 persisted JSON snapshot end-to-end SPL Editing regressions."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest

from nl2spl.compiler.artifacts.snapshot.capabilities import SnapshotCapability
from nl2spl.compiler.artifacts.snapshot.config import SnapshotPersistenceConfig
from nl2spl.compiler.irs.policy import IRSRuntimeConfig
from nl2spl.compiler.spl_editing.cli import _build_default_service
from nl2spl.config import LLMConfig, PipelineConfig
from nl2spl.ir.agent_profile_ir import AgentProfileIR, PersonaIR
from nl2spl.ir.block_structure_ir import BlockStructureIR
from nl2spl.ir.diagnostics import CompileDiagnostic
from nl2spl.ir.field_route_ir import FieldRouteIR
from nl2spl.ir.flow_structure_ir import FlowStructureIR
from nl2spl.ir.resource_registry_ir import WorkerScopedResourceIR
from nl2spl.ir.span_ir import SpanIR
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.ir.worker_ir import ExceptionFlowRef, WorkerIR
from nl2spl.ir.worker_plan_ir import (
    ContractFieldIR,
    WorkerBlockPlanIR,
    WorkerFlowPlanIR,
    WorkerPlanIR,
    WorkerSpecIR,
    WorkerStepPlanIR,
)
from nl2spl.pipeline.executable_gate import ExecutableElementGate
from nl2spl.pipeline.orchestrator import PipelineOrchestrator
from nl2spl.pipeline.provenance import ProvenanceAggregator
from tests.spl_editing_stub_llm import StubSuggestionLLM


@dataclass(frozen=True)
class _Case:
    run_name: str
    diagnostic: CompileDiagnostic
    worker_plan: WorkerPlanIR
    worker_flow_plan: WorkerFlowPlanIR
    worker_block_plan: WorkerBlockPlanIR
    worker_step_plan: WorkerStepPlanIR
    expected_patch_type: str


def _diag(
    diagnostic_id: str,
    kind: str,
    target_ref: str,
    construct_type: str,
    construct_id: str,
    slot_name: str,
    *,
    authority: str = "post_normalize_irs",
) -> CompileDiagnostic:
    diagnostic = CompileDiagnostic(
        diagnostic_id,
        kind,
        "warning",
        f"{kind} needs repair.",
        target_ref=target_ref,
        blocks_completion=True,
    )
    diagnostic.metadata["irs_ref"] = {
        "construct_type": construct_type,
        "construct_id": construct_id,
        "slot_name": slot_name,
        "construct_path": [],
        "source_authority": authority,
    }
    diagnostic.metadata["authority"] = authority
    diagnostic.metadata["repairability"] = "editable"
    diagnostic.metadata["issue_group_id"] = f"group_{diagnostic_id}"
    diagnostic.metadata["issue_role"] = "primary"
    return diagnostic


def _missing_handler_case() -> _Case:
    return _Case(
        run_name="s8_missing_handler",
        diagnostic=_diag(
            "diag_mh",
            "missing_handler",
            "worker:w_main.exception_flow:exc_1",
            "EXCEPTION_FLOW",
            "exc_1",
            "handler_action",
        ),
        worker_plan=_main_worker_plan(),
        worker_flow_plan=WorkerFlowPlanIR(worker_flows={
            "w_main": FlowStructureIR(
                exception_flows=[
                    ExceptionFlowRef("exc_1", "Template unavailable.", []),
                ],
            ),
        }),
        worker_block_plan=WorkerBlockPlanIR(worker_blocks={
            "w_main": BlockStructureIR(),
        }),
        worker_step_plan=WorkerStepPlanIR("w_main", {"w_main": []}),
        expected_patch_type="AddExceptionHandlerStep",
    )


def _missing_output_case() -> _Case:
    return _Case(
        run_name="s8_missing_output",
        diagnostic=_diag(
            "diag_mop",
            "missing_output_producer",
            "worker:w_main.output:draft",
            "REQUIRED_OUTPUT",
            "required_output:draft",
            "producer",
        ),
        worker_plan=_main_worker_plan(),
        worker_flow_plan=WorkerFlowPlanIR(worker_flows={"w_main": FlowStructureIR()}),
        worker_block_plan=WorkerBlockPlanIR(worker_blocks={
            "w_main": BlockStructureIR(),
        }),
        worker_step_plan=WorkerStepPlanIR("w_main", {"w_main": []}),
        expected_patch_type="InsertProducerStep",
    )


def _worker_promotion_case() -> _Case:
    diagnostic = _diag(
        "diag_wp",
        "type_or_contract_ambiguity",
        "worker_promotion:cand_1",
        "WORKER_PROMOTION",
        "worker_promotion:cand_1",
        "promotion_input_contract",
        authority="selected_promoted_stage_local_irs",
    )
    diagnostic.metadata["original_semantic_role"] = "delegation_intent"
    diagnostic.metadata["promotion_status"] = "blocked"
    return _Case(
        run_name="s8_worker_promotion",
        diagnostic=diagnostic,
        worker_plan=WorkerPlanIR(
            main_worker_id="w_main",
            workers=[
                WorkerSpecIR(
                    "w_main", "MainWorker", "main", "Main worker",
                    boundary_kind="main_worker", owned_span_ids=["s1"],
                ),
                WorkerSpecIR(
                    "w_child", "Child", "child", "Child worker",
                    boundary_kind="bounded_subtask",
                    owned_span_ids=["s1"],
                    input_contract=[
                        ContractFieldIR(
                            "request", "text", True, "Request", "input",
                        ),
                    ],
                    output_contract=[
                        ContractFieldIR(
                            "result", "text", True, "Result", "output",
                        ),
                    ],
                ),
            ],
        ),
        worker_flow_plan=WorkerFlowPlanIR(worker_flows={
            "w_main": FlowStructureIR(),
            "w_child": FlowStructureIR(),
        }),
        worker_block_plan=WorkerBlockPlanIR(worker_blocks={
            "w_main": BlockStructureIR(),
            "w_child": BlockStructureIR(),
        }),
        worker_step_plan=WorkerStepPlanIR("w_main", {
            "w_main": [
                StepIR(
                    "st_inv", "Invoke child", ["s1"], "INVOKE_WORKER",
                    inputs=["request"],
                    outputs=["result"],
                    handoff_id="handoff_repair_cand_1",
                    integration_ref="Child",
                ),
            ],
            "w_child": [
                StepIR(
                    "st_child_result",
                    "Produce result",
                    ["s1"],
                    "GENERAL_COMMAND",
                    outputs=["result"],
                ),
            ],
        }),
        expected_patch_type="CreateWorkerHandoffContract",
    )


def _main_worker_plan() -> WorkerPlanIR:
    return WorkerPlanIR(
        main_worker_id="w_main",
        workers=[
            WorkerSpecIR(
                "w_main", "MainWorker", "main", "Main worker",
                boundary_kind="main_worker", owned_span_ids=["s1"],
            ),
        ],
    )


def _patch_pipeline(monkeypatch: pytest.MonkeyPatch, case: _Case) -> None:
    span = SpanIR("s1", "Do work.")
    symbols = SymbolTable()
    profile = AgentProfileIR(persona=PersonaIR(role="Assistant", aspects=[]))

    monkeypatch.setattr(PipelineOrchestrator, "_run_stage1", lambda s, *a, **k: [span])
    monkeypatch.setattr(
        PipelineOrchestrator,
        "_run_stage2",
        lambda s, *a, **k: (FieldRouteIR(behavior=["s1"]), []),
    )
    monkeypatch.setattr(
        PipelineOrchestrator,
        "_run_stage3",
        lambda s, *a, **k: ([span], FieldRouteIR(behavior=["s1"])),
    )
    monkeypatch.setattr(
        PipelineOrchestrator, "_run_stage3_5",
        lambda s, *a, **k: case.worker_plan,
    )
    monkeypatch.setattr(
        PipelineOrchestrator, "_run_stage4",
        lambda s, *a, **k: case.worker_flow_plan,
    )
    monkeypatch.setattr(
        PipelineOrchestrator, "_run_stage5",
        lambda s, *a, **k: case.worker_block_plan,
    )
    monkeypatch.setattr(
        PipelineOrchestrator,
        "_run_stage6_worker_scoped",
        lambda s, *a, **k: (WorkerScopedResourceIR(), symbols, []),
    )
    monkeypatch.setattr(
        PipelineOrchestrator,
        "_run_stage7_worker_scoped",
        lambda s, *a, **k: (case.worker_step_plan, symbols, []),
    )
    monkeypatch.setattr(PipelineOrchestrator, "_run_stage8", lambda s, *a, **k: profile)
    monkeypatch.setattr(PipelineOrchestrator, "_run_stage9", lambda s, *a, **k: [])
    monkeypatch.setattr(
        PipelineOrchestrator,
        "_run_normalization_worker_scoped",
        lambda s, *a, **k: (
            case.worker_flow_plan, case.worker_block_plan,
            case.worker_step_plan, symbols, [], [],
        ),
    )
    monkeypatch.setattr(
        PipelineOrchestrator,
        "_run_stage10_worker_scoped",
        lambda s, *a, **k: WorkerIR("MainWorker", "Main worker"),
    )
    monkeypatch.setattr(
        PipelineOrchestrator,
        "_run_stage11",
        lambda s, *a, **k: ("[DEFINE_WORKER: MainWorker]", [], []),
    )
    monkeypatch.setattr(
        ExecutableElementGate,
        "apply",
        lambda s, worker, worker_plan=None: (worker, [], []),
    )
    monkeypatch.setattr(
        ProvenanceAggregator,
        "aggregate",
        lambda s, **k: ([], []),
    )
    if case.expected_patch_type == "CreateWorkerHandoffContract":
        from nl2spl.pipeline.worker_plan_validator import (
            WorkerPlanValidationResult,
            WorkerPlanValidator,
        )

        monkeypatch.setattr(
            WorkerPlanValidator,
            "validate",
            lambda s, *a, **k: WorkerPlanValidationResult(is_valid=True),
        )

    from nl2spl.compiler.diagnostic_consolidator import (
        DiagnosticConsolidationResult,
        DiagnosticConsolidator,
    )

    original_consolidate = DiagnosticConsolidator.consolidate

    def _consolidate(self, data):
        if data.irs_store is not None:
            return DiagnosticConsolidationResult(
                final_diagnostics=[case.diagnostic],
            )
        return original_consolidate(self, data)

    monkeypatch.setattr(
        DiagnosticConsolidator,
        "consolidate",
        _consolidate,
    )


def _run_pipeline_case(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case: _Case,
    *,
    required_capabilities: tuple[SnapshotCapability, ...] = (
        SnapshotCapability.ISSUE_EXTRACTION,
        SnapshotCapability.LANE_A_REPLAY,
    ),
) -> Path:
    _patch_pipeline(monkeypatch, case)
    config = PipelineConfig(
        llm=LLMConfig(api_key="sk-fake"),
        output_dir=tmp_path,
        run_name=case.run_name,
        save_intermediate=False,
        irs=IRSRuntimeConfig(enabled=False, stage_local_enabled=False),
        snapshot=SnapshotPersistenceConfig.required(*required_capabilities),
    )
    result = PipelineOrchestrator(config).run("Do work.")
    assert result.spl_editing_snapshot_status == "available", (
        result.spl_editing_snapshot_error
    )
    assert result.spl_editing_snapshot_path is not None
    return result.spl_editing_snapshot_path


@pytest.mark.parametrize(
    "case_factory",
    [_missing_handler_case, _missing_output_case, _worker_promotion_case],
)
def test_persisted_snapshot_full_editing_flow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case_factory: Callable[[], _Case],
) -> None:
    case = case_factory()
    snapshot_path = _run_pipeline_case(
        tmp_path,
        monkeypatch,
        case,
        required_capabilities=(SnapshotCapability.LANE_A_REPLAY,),
    )

    svc = _build_default_service(suggestion_llm=StubSuggestionLLM())
    run_id = svc.register_snapshot_file(snapshot_path)
    issues = svc.list_editable_issues(run_id)
    assert len(issues) == 1

    session = svc.create_session(run_id, issues[0])
    suggestions = svc.generate_suggestions(session.session_id)
    selected = next(
        suggestion for suggestion in suggestions
        if suggestion.patch.patch_type == case.expected_patch_type
    )
    svc.apply_suggestion(session.session_id, selected.suggestion_id)
    result = svc.verify_session(session.session_id)

    assert result.accepted is True
    assert (snapshot_path.parent / "spl_editing_overlays").exists()
    assert list((snapshot_path.parent / "spl_editing_overlays").glob("*.json"))


def test_snapshot_without_irs_ref_is_not_editable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = _missing_handler_case()
    case.diagnostic.kind = "informational_missing_handler"
    case.diagnostic.metadata.pop("irs_ref")
    case.diagnostic.metadata["repairability"] = "non_repairable"
    snapshot_path = _run_pipeline_case(
        tmp_path,
        monkeypatch,
        case,
        required_capabilities=(SnapshotCapability.LANE_A_REPLAY,),
    )

    svc = _build_default_service(suggestion_llm=StubSuggestionLLM())
    run_id = svc.register_snapshot_file(snapshot_path)

    assert svc.list_editable_issues(run_id) == ()


def test_cli_demo_consumes_pipeline_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = _missing_handler_case()
    snapshot_path = _run_pipeline_case(tmp_path, monkeypatch, case)

    from nl2spl.compiler.spl_editing.cli import main

    answers = iter(["1", "1", "y"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    monkeypatch.setattr(
        "nl2spl.compiler.spl_editing.cli.build_suggestion_llm_from_env",
        lambda: StubSuggestionLLM(),
    )
    monkeypatch.setattr(
        "sys.argv",
        ["spl-edit", "demo", "--run", str(snapshot_path.parent)],
    )

    main()

    overlay_dir = snapshot_path.parent / "spl_editing_overlays"
    assert list(overlay_dir.glob("*.json"))


def test_stage_json_alone_cannot_enter_editing_flow(tmp_path: Path) -> None:
    stage_json = tmp_path / "stage1.json"
    stage_json.write_text("{}", encoding="utf-8")

    svc = _build_default_service(suggestion_llm=StubSuggestionLLM())
    with pytest.raises(ValueError, match="Stage JSON"):
        svc.register_snapshot_file(stage_json)


def test_broken_artifact_hash_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = _missing_handler_case()
    snapshot_path = _run_pipeline_case(tmp_path, monkeypatch, case)
    data = snapshot_path.read_text(encoding="utf-8")
    snapshot_path.write_text(data.replace("MainWorker", "TamperedWorker", 1),
                             encoding="utf-8")

    svc = _build_default_service(suggestion_llm=StubSuggestionLLM())
    with pytest.raises(ValueError, match="payload_hash mismatch"):
        svc.register_snapshot_file(snapshot_path)


