from nl2spl.compiler.construct_registry import SPLConstructRegistry
from nl2spl.compiler.irs.checkers.worker_delegation import WorkerDelegationIRSChecker
from nl2spl.compiler.irs.context import IRSCheckContext
from nl2spl.ir.worker_plan_ir import (
    CandidateTaskUnitIR,
    InvokeLocationHintIR,
    WorkerBoundaryDecisionIR,
    WorkerHandoffIR,
    WorkerPlanIR,
    WorkerSpecIR,
)


def _slot_statuses(report):
    return {slot.slot_name: slot.status for slot in report.slots}


def _check_report(plan: WorkerPlanIR, construct_type: str):
    checker = WorkerDelegationIRSChecker()
    context = IRSCheckContext(stage_name="stage3_5", worker_plan=plan)
    instance = next(
        inst
        for inst in checker.extract_instances(context)
        if inst.construct_type == construct_type
    )
    return checker.check_instance(
        instance,
        SPLConstructRegistry.default().get(construct_type),
        context,
    )


def test_child_worker_responsibility_only_is_partial_renderable():
    child = WorkerSpecIR(
        worker_id="worker_child",
        worker_name="Child",
        kind="child",
        purpose="Extracted child responsibility",
        owned_span_ids=["s2"],
        input_contract=[],
        output_contract=[],
        boundary_kind="child_worker",
        partial_reason="partial_contract_unknown",
    )
    plan = WorkerPlanIR(main_worker_id="main", workers=[child])

    report = _check_report(plan, "CHILD_WORKER")

    assert report.completeness == "partial"
    assert report.frontier_status == "leaf"
    assert report.renderable is True
    slots = _slot_statuses(report)
    assert slots["responsibility"] == "satisfied"
    assert slots["input_contract"] == "missing"
    assert slots["output_contract"] == "missing"


def test_child_worker_known_empty_contract_is_satisfied():
    child = WorkerSpecIR(
        worker_id="worker_child",
        worker_name="Child",
        kind="child",
        purpose="Extracted child responsibility",
        owned_span_ids=["s2"],
        input_contract=[],
        output_contract=[],
        input_contract_status="known_empty",
        output_contract_status="known_empty",
        input_contract_status_source="user_confirmed_empty_contract",
        output_contract_status_source="user_confirmed_empty_contract",
        boundary_kind="child_worker",
    )
    plan = WorkerPlanIR(main_worker_id="main", workers=[child])

    report = _check_report(plan, "CHILD_WORKER")

    slots = _slot_statuses(report)
    assert slots["input_contract"] == "satisfied"
    assert slots["output_contract"] == "satisfied"
    assert report.completeness == "partial"
    assert report.renderable is True


def test_worker_handoff_known_empty_bindings_are_satisfied():
    main = WorkerSpecIR(
        worker_id="main",
        worker_name="Main",
        kind="main",
        purpose="Main worker",
    )
    child = WorkerSpecIR(
        worker_id="worker_child",
        worker_name="Child",
        kind="child",
        purpose="Child worker",
        owned_span_ids=["s2"],
    )
    handoff = WorkerHandoffIR(
        handoff_id="handoff_1",
        from_worker="main",
        to_worker="worker_child",
        api_ref=None,
        mode="invoke",
        condition_text=None,
        ordering="after",
        input_bindings=[],
        output_bindings=[],
        invoke_location_hint=InvokeLocationHintIR(
            flow_kind="main",
            flow_id=None,
            after_span_id="s2",
            before_span_id=None,
            block_hint="sequential",
        ),
        input_binding_status="known_empty",
        output_binding_status="known_empty",
        input_binding_status_source="user_confirmed_empty_contract",
        output_binding_status_source="user_confirmed_empty_contract",
        materialization_status="confirmed_empty_contract",
    )
    plan = WorkerPlanIR(
        main_worker_id="main",
        workers=[main, child],
        handoffs=[handoff],
    )

    report = _check_report(plan, "WORKER_HANDOFF")

    assert report.completeness == "complete"
    slots = _slot_statuses(report)
    assert slots["input_bindings"] == "satisfied"
    assert slots["output_bindings"] == "satisfied"


def test_worker_promotion_known_empty_contract_and_result_handoff_satisfy_slots():
    candidate = CandidateTaskUnitIR(
        candidate_id="c1",
        source_span_ids=["s2"],
        task_text="Run child worker",
        purpose="Run child worker",
        candidate_kind="explicit_delegation",
        possible_inputs=[],
        possible_outputs=[],
        input_contract_status="known_empty",
        output_contract_status="known_empty",
        input_contract_status_source="user_confirmed_empty_contract",
        output_contract_status_source="user_confirmed_empty_contract",
    )
    main = WorkerSpecIR(
        worker_id="main",
        worker_name="Main",
        kind="main",
        purpose="Main worker",
    )
    child = WorkerSpecIR(
        worker_id="worker_child",
        worker_name="Child",
        kind="child",
        purpose="Child worker",
        owned_span_ids=["s2"],
    )
    handoff = WorkerHandoffIR(
        handoff_id="handoff_1",
        from_worker="main",
        to_worker="worker_child",
        api_ref=None,
        mode="invoke",
        condition_text=None,
        ordering="after",
        input_bindings=[],
        output_bindings=[],
        invoke_location_hint=InvokeLocationHintIR(
            flow_kind="main",
            flow_id=None,
            after_span_id="s2",
            before_span_id=None,
            block_hint="sequential",
        ),
        input_binding_status="known_empty",
        output_binding_status="known_empty",
        input_binding_status_source="user_confirmed_empty_contract",
        output_binding_status_source="user_confirmed_empty_contract",
        materialization_status="confirmed_empty_contract",
    )
    decision = WorkerBoundaryDecisionIR(
        candidate_id="c1",
        decision="extract_child_worker",
        boundary_strength="strong",
        boundary_kind="explicit_delegation",
        rejection_reason=None,
        reason="Confirmed child worker",
    )
    plan = WorkerPlanIR(
        main_worker_id="main",
        workers=[main, child],
        candidates=[candidate],
        decisions=[decision],
        handoffs=[handoff],
    )

    report = _check_report(plan, "WORKER_PROMOTION")

    assert report.completeness == "complete"
    assert report.metadata["promotion_status"] == "ready"
    slots = _slot_statuses(report)
    assert slots["promotion_input_contract"] == "satisfied"
    assert slots["promotion_output_contract"] == "satisfied"
    assert slots["promotion_result_handoff"] == "satisfied"
