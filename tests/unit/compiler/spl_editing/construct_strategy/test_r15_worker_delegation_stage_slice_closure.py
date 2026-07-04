"""R15 worker delegation stage-slice closure tests."""

from __future__ import annotations

import inspect

from nl2spl.compiler.spl_editing.cli import _build_default_service
from nl2spl.compiler.spl_editing.stage_slices import (
    build_worker_delegation_stage_slice_registry,
)
from nl2spl.compiler.spl_editing.stage_slices.worker_delegation_v2 import (
    DefineChildWorkerClosureMaterializer,
)
from nl2spl.ir.diagnostics import CompileDiagnostic
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.worker_plan_ir import WorkerPlanIR, WorkerSpecIR, WorkerStepPlanIR
from tests.spl_editing_stub_llm import StubSuggestionLLM
from tests.unit.compiler.spl_editing.test_c6_create_worker_handoff_contract import _snap


def test_worker_delegation_legacy_handoff_option_is_not_exposed() -> None:
    svc = _build_default_service(suggestion_llm=StubSuggestionLLM())
    diag = CompileDiagnostic(
        "diag_promo",
        "type_or_contract_ambiguity",
        "warning",
        "Missing handoff contract.",
        target_ref="worker_promotion:cand_1",
        blocks_completion=True,
    )
    diag.metadata["irs_ref"] = {
        "construct_type": "WORKER_PROMOTION",
        "construct_id": "worker_promotion:cand_1",
        "slot_name": "promotion_input_contract",
        "construct_path": [],
        "source_authority": "selected_promoted_stage_local_irs",
    }
    diag.metadata["authority"] = "selected_promoted_stage_local_irs"
    diag.metadata["repairability"] = "editable"
    diag.metadata["issue_role"] = "primary"
    diag.metadata["issue_group_id"] = "worker_promotion_group:worker_promotion:cand_1"
    diag.metadata["original_semantic_role"] = "delegation_intent"
    diag.metadata["promotion_status"] = "blocked"
    plan = WorkerPlanIR(
        main_worker_id="w_main",
        workers=[
            WorkerSpecIR("w_main", "Main", "main", "Main", boundary_kind="main_worker"),
            WorkerSpecIR("w_child", "Child", "child", "ChildWorker", boundary_kind="child_worker"),
        ],
    )
    snap = _snap(
        worker_plan=plan,
        compile_diagnostics=(diag,),
        worker_step_plan=WorkerStepPlanIR(
            "w_main",
            {
                "w_main": [
                    StepIR(
                        "st_invoke",
                        "Invoke child",
                        ["s1"],
                        "INVOKE_WORKER",
                        inputs=["request"],
                        outputs=["result"],
                        handoff_id="handoff_repair_cand_1",
                        integration_ref="Child",
                    )
                ],
            },
        ),
    )

    run_id = svc.register_compile_result(snap)
    issue = svc.list_editable_issues(run_id)[0]
    from nl2spl.compiler.spl_editing.presentation.service import (
        SPLEditingPresentationService,
    )

    detail = SPLEditingPresentationService(svc).get_issue_detail_presentation(
        run_id, issue.issue_id
    )
    assert [option.option_id for option in detail.available_repairs] == [
        "define_child_worker",
        "keep_in_main_flow",
    ]
    assert all(
        "CreateWorkerHandoffContract" not in option.patch_types
        and "ConvertDelegationIntentToRequestInput" not in option.patch_types
        for option in detail.available_repairs
    )


def test_worker_delegation_v2_registers_independent_single_layer_slices() -> None:
    registry = build_worker_delegation_stage_slice_registry()
    expected = {
        "stage3_5.define_child_worker.v2",
        "stage4.child_worker_flow.v2",
        "stage5.worker_delegation_blocks.v2",
        "stage7.child_worker_command.v2",
        "stage3_5.worker_handoff_contract.v2",
        "stage7.worker_invoke.v2",
        "stage3_5.worker_symbol_bindings.v2",
        "stage3_5.keep_main_boundary.v2",
        "stage4.keep_main_flow_cleanup.v2",
        "stage5.keep_main_placement.v2",
        "stage7.keep_main_command.v2",
    }
    assert set(registry.list_slice_ids()) == expected
    for slice_id in expected:
        stage_slice = registry.get(slice_id)
        assert len(stage_slice.output_artifacts) == 1
        assert len(stage_slice.write_layers) == 1


def test_worker_delegation_v2_orchestrator_has_no_ir_write_implementation() -> None:
    source = inspect.getsource(DefineChildWorkerClosureMaterializer)
    assert "def _stage_results" not in source
    assert "copy.deepcopy" not in source
    assert "WorkerSpecIR" not in source
    assert "WorkerHandoffIR" not in source
    assert "StepIR(" not in source
    assert "BlockIR(" not in source
