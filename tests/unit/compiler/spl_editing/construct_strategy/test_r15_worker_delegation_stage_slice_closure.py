"""R15 worker delegation stage-slice closure tests."""

from __future__ import annotations

from nl2spl.compiler.spl_editing.cli import _build_default_service
from nl2spl.ir.diagnostics import CompileDiagnostic
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.worker_plan_ir import WorkerPlanIR, WorkerSpecIR, WorkerStepPlanIR
from tests.spl_editing_stub_llm import StubSuggestionLLM
from tests.unit.compiler.spl_editing.test_c6_create_worker_handoff_contract import _snap


def test_worker_delegation_apply_materializes_matching_handoff_and_invoke_step() -> None:
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
    session = svc.create_session(run_id, issue)
    suggestion = [
        s
        for s in svc.generate_suggestions(session.session_id)
        if s.patch.patch_type == "CreateWorkerHandoffContract"
    ][0]

    updated = svc.apply_suggestion(session.session_id, suggestion.suggestion_id)
    patched = svc._snapshots.get(run_id, snap.snapshot_id, overlay_version=updated.overlay_version)
    invoke_steps = [
        step
        for step in patched.worker_step_plan.worker_steps["w_main"]
        if step.command_type == "INVOKE_WORKER" and step.metadata.get("origin") == "user_confirmed_repair"
    ]
    handoff_ids = {handoff.handoff_id for handoff in patched.worker_plan.handoffs}

    assert len(invoke_steps) == 1
    assert invoke_steps[0].handoff_id in handoff_ids
    assert svc.verify_session(session.session_id).accepted is True