from __future__ import annotations

from nl2spl.ir.block_structure_ir import BlockIR, BlockStructureIR
from nl2spl.ir.span_ir import SpanIR
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.ir.worker_plan_ir import WorkerStepPlanIR
from nl2spl.pipeline.stages.stage7_step_extractor.worker_scoped import (
    _add_source_backed_provenance_maintenance_steps,
    _build_step_variable_relation_plan,
    _remove_redundant_same_source_output_steps,
)


def test_provenance_step_drops_inputs_not_mentioned_by_source_text() -> None:
    step = StepIR(
        step_id="st_provenance",
        text="Maintain provenance for externally sourced facts.",
        source_span_ids=["s19"],
        command_type="GENERAL_COMMAND",
        inputs=[
            "available_connectors_or_source_repositories",
            "source_evidence_set",
        ],
    )
    worker_steps = WorkerStepPlanIR(
        main_worker_id="worker_main",
        worker_steps={"worker_main": [step]},
    )

    _build_step_variable_relation_plan(worker_steps, SymbolTable())

    assert step.inputs == []


def test_provenance_maintenance_does_not_produce_variable_without_record_action() -> None:
    step = StepIR(
        step_id="st_provenance",
        text="Maintain provenance for externally sourced facts.",
        source_span_ids=["s19"],
        command_type="GENERAL_COMMAND",
        outputs=["provenance"],
    )
    worker_steps = WorkerStepPlanIR(
        main_worker_id="worker_main",
        worker_steps={"worker_main": [step]},
    )

    plan = _build_step_variable_relation_plan(worker_steps, SymbolTable())

    assert step.outputs == []
    assert plan.diagnostics == (
        "step_variable_relation_ambiguous:st_provenance:provenance",
    )


def test_rephrased_provenance_maintenance_does_not_produce_source_evidence() -> None:
    step = StepIR(
        step_id="st_provenance",
        text="Record source evidence with provenance.",
        source_span_ids=["s19"],
        command_type="GENERAL_COMMAND",
        outputs=["source_evidence_set"],
    )
    worker_steps = WorkerStepPlanIR(
        main_worker_id="worker_main",
        worker_steps={"worker_main": [step]},
    )
    symbols = SymbolTable()
    symbols.declare(
        "source_evidence_set",
        "List[text]",
        "output",
        "Collected source and evidence items.",
    )

    plan = _build_step_variable_relation_plan(
        worker_steps,
        symbols,
        span_by_id={
            "s19": SpanIR(
                span_id="s19",
                text="Maintain provenance for externally sourced facts.",
            )
        },
    )

    assert step.outputs == []
    assert plan.diagnostics == (
        "step_variable_relation_ambiguous:st_provenance:source_evidence_set",
    )


def test_display_message_never_owns_output_relation() -> None:
    step = StepIR(
        step_id="st_display",
        text="Display the draft communication artifact.",
        source_span_ids=["s1"],
        command_type="DISPLAY_MESSAGE",
        outputs=["draft_communication_artifact"],
    )
    worker_steps = WorkerStepPlanIR(
        main_worker_id="worker_main",
        worker_steps={"worker_main": [step]},
    )

    plan = _build_step_variable_relation_plan(
        worker_steps,
        SymbolTable(),
        span_by_id={
            "s1": SpanIR(
                span_id="s1",
                text="Output the draft communication artifact.",
            )
        },
    )

    assert step.outputs == []
    assert step.command_type == "DISPLAY_MESSAGE"
    assert step.text.startswith("Output the draft communication artifact")
    assert plan.producing_relations() == ()
    assert plan.diagnostics == (
        "step_variable_relation_ambiguous:st_display:draft_communication_artifact",
    )


def test_output_statement_does_not_produce_listed_variables() -> None:
    step = StepIR(
        step_id="st_output",
        text="Produce the draft, unresolved items, and completion status.",
        source_span_ids=["s1"],
        command_type="GENERAL_COMMAND",
        outputs=[
            "draft_communication_artifact",
            "record_of_unresolved_items",
            "completion_status",
        ],
    )
    worker_steps = WorkerStepPlanIR(
        main_worker_id="worker_main",
        worker_steps={"worker_main": [step]},
    )

    plan = _build_step_variable_relation_plan(
        worker_steps,
        SymbolTable(),
        span_by_id={
            "s1": SpanIR(
                span_id="s1",
                text=(
                    "Output the draft communication artifact, record of "
                    "unresolved items, and completion status."
                ),
            )
        },
    )

    assert step.outputs == []
    assert step.command_type == "DISPLAY_MESSAGE"
    assert step.text.startswith("Output the draft communication artifact")
    assert plan.producing_relations() == ()
    assert len(plan.diagnostics) == 3


def test_description_overlap_does_not_create_output_relation() -> None:
    step = StepIR(
        step_id="st_analyze",
        text="Analyze the request and produce a draft.",
        source_span_ids=["s1"],
        command_type="GENERAL_COMMAND",
        outputs=["draft_communication_artifact"],
    )
    worker_steps = WorkerStepPlanIR(
        main_worker_id="worker_main",
        worker_steps={"worker_main": [step]},
    )
    symbols = SymbolTable()
    symbols.declare(
        "draft_communication_artifact",
        "text",
        "output",
        "Draft communication artifact produced for the user.",
    )

    plan = _build_step_variable_relation_plan(
        worker_steps,
        symbols,
        span_by_id={
            "s1": SpanIR(
                span_id="s1",
                text=(
                    "Analyze the user request to clarify the type of "
                    "communication material."
                ),
            )
        },
    )

    assert step.outputs == []
    assert plan.producing_relations() == ()


def test_delegation_verification_does_not_produce_unresolved_items() -> None:
    step = StepIR(
        step_id="st_verify",
        text="Verify delegated results and produce unresolved items.",
        source_span_ids=["s1"],
        command_type="GENERAL_COMMAND",
        outputs=["unresolved_items"],
    )
    worker_steps = WorkerStepPlanIR(
        main_worker_id="worker_main",
        worker_steps={"worker_main": [step]},
    )

    plan = _build_step_variable_relation_plan(
        worker_steps,
        SymbolTable(),
        span_by_id={
            "s1": SpanIR(
                span_id="s1",
                text=(
                    "The main process shall verify that delegated results "
                    "comply with task scope and user requirements."
                ),
            )
        },
    )

    assert step.outputs == []
    assert plan.producing_relations() == ()


def test_control_condition_inputs_are_not_action_inputs() -> None:
    step = StepIR(
        step_id="st_draft",
        text="Produce the draft communication artifact.",
        source_span_ids=["s20"],
        command_type="GENERAL_COMMAND",
        inputs=[
            "enough_required_information",
            "user_request",
        ],
        outputs=["draft_communication_artifact"],
    )
    worker_steps = WorkerStepPlanIR(
        main_worker_id="worker_main",
        worker_steps={"worker_main": [step]},
    )

    _build_step_variable_relation_plan(worker_steps, SymbolTable())

    assert step.inputs == ["user_request"]


def test_control_condition_input_name_variants_are_not_action_inputs() -> None:
    step = StepIR(
        step_id="st_draft",
        text="Produce the draft communication artifact.",
        source_span_ids=["s20"],
        command_type="GENERAL_COMMAND",
        inputs=[
            "enough_required_information_available",
            "user_request",
        ],
        outputs=["draft_communication_artifact"],
    )
    worker_steps = WorkerStepPlanIR(
        main_worker_id="worker_main",
        worker_steps={"worker_main": [step]},
    )

    _build_step_variable_relation_plan(worker_steps, SymbolTable())

    assert step.inputs == ["user_request"]


def test_relation_planner_does_not_add_llm_omitted_completion_status() -> None:
    step = StepIR(
        step_id="st_finalize",
        text="Record unresolved assumptions.",
        source_span_ids=["s24"],
        command_type="GENERAL_COMMAND",
        outputs=["assumptions_log"],
    )
    worker_steps = WorkerStepPlanIR(
        main_worker_id="worker_main",
        worker_steps={"worker_main": [step]},
    )
    symbols = SymbolTable()
    symbols.declare(
        "assumptions_log",
        "text",
        "output",
        "Short log of assumptions for unresolved items.",
    )
    symbols.declare(
        "completion_status",
        "text",
        "output",
        "Final completion status for the run.",
    )

    plan = _build_step_variable_relation_plan(
        worker_steps,
        symbols,
        span_by_id={
            "s24": SpanIR(
                span_id="s24",
                text=(
                    "At the end, record a short assumptions log for any "
                    "unresolved items and set a completion status for the run."
                ),
            )
        },
    )

    assert step.outputs == ["assumptions_log"]
    assert "set completion status" not in step.text
    assert {
        (relation.step_id, relation.variable_name, relation.relation)
        for relation in plan.relations
    } == {
        ("st_finalize", "assumptions_log", "produces"),
    }


def test_unbacked_output_contract_variable_is_not_kept_as_step_input() -> None:
    step = StepIR(
        step_id="st_draft",
        text=(
            "Produce the draft communication artifact based on "
            "source_evidence_set and user_request."
        ),
        source_span_ids=["s20"],
        command_type="GENERAL_COMMAND",
        inputs=["source_evidence_set", "user_request"],
        outputs=["draft_communication_artifact"],
    )
    worker_steps = WorkerStepPlanIR(
        main_worker_id="worker_main",
        worker_steps={"worker_main": [step]},
    )
    symbols = SymbolTable()
    symbols.declare(
        "source_evidence_set",
        "List[text]",
        "output",
        "Collected source or evidence items supporting the draft.",
    )
    symbols.declare(
        "user_request",
        "text",
        "input",
        "Requested communication from the user.",
    )
    symbols.declare(
        "draft_communication_artifact",
        "text",
        "output",
        "Draft communication artifact produced for the user.",
    )

    _build_step_variable_relation_plan(
        worker_steps,
        symbols,
        span_by_id={
            "s20": SpanIR(
                span_id="s20",
                text="When enough required information is available, produce a draft.",
            )
        },
    )

    assert step.inputs == ["user_request"]


def test_source_backed_provenance_maintenance_fallback_is_no_output_command() -> None:
    steps: list[StepIR] = []
    span = SpanIR(
        span_id="s19",
        text="Maintain provenance for externally sourced facts.",
        source_section_id="sec_reusable_process",
        segmentation_kind="atomic_action_candidate",
    )
    blocks = BlockStructureIR(
        main_flow_blocks=[
            BlockIR(
                block_id="b_provenance",
                block_type="SEQUENTIAL",
                spans=["s19"],
            )
        ]
    )

    _add_source_backed_provenance_maintenance_steps(steps, [span], blocks)

    assert len(steps) == 1
    assert steps[0].text == "Maintain provenance for externally sourced facts"
    assert steps[0].outputs == []
    assert steps[0].block_ref == "b_provenance"


def test_redundant_same_source_output_step_is_removed() -> None:
    worker_steps = WorkerStepPlanIR(
        main_worker_id="worker_main",
        worker_steps={
            "worker_main": [
                StepIR(
                    step_id="st_finalize",
                    text="Record assumptions and set completion status.",
                    source_span_ids=["s23"],
                    command_type="GENERAL_COMMAND",
                    outputs=["assumptions_log", "completion_status"],
                ),
                StepIR(
                    step_id="st_status",
                    text="Set completion status.",
                    source_span_ids=["s23"],
                    command_type="GENERAL_COMMAND",
                    outputs=["completion_status"],
                ),
            ]
        },
    )

    changed = _remove_redundant_same_source_output_steps(worker_steps)

    assert changed is True
    assert [step.step_id for step in worker_steps.worker_steps["worker_main"]] == [
        "st_finalize"
    ]


def test_revision_step_refines_existing_output_instead_of_producing_duplicate() -> None:
    worker_steps = WorkerStepPlanIR(
        main_worker_id="worker_main",
        worker_steps={
            "worker_main": [
                StepIR(
                    step_id="st_draft",
                    text="Produce the draft communication artifact.",
                    source_span_ids=["s20"],
                    command_type="GENERAL_COMMAND",
                    outputs=["draft_communication_artifact"],
                ),
                StepIR(
                    step_id="st_revise",
                    text="Revise the draft communication artifact.",
                    source_span_ids=["s21"],
                    command_type="GENERAL_COMMAND",
                    outputs=["draft_communication_artifact"],
                ),
            ]
        },
    )
    symbols = SymbolTable()
    symbols.declare(
        "draft_communication_artifact",
        "text",
        "output",
        "Draft communication artifact produced by the process.",
    )

    plan = _build_step_variable_relation_plan(
        worker_steps,
        symbols,
        span_by_id={
            "s20": SpanIR(
                span_id="s20",
                text="Produce the draft communication artifact.",
            ),
            "s21": SpanIR(
                span_id="s21",
                text="Revise the draft communication artifact.",
            ),
        },
    )

    relations = {
        (item.step_id, item.variable_name): item.relation
        for item in plan.relations
    }
    assert relations[("st_draft", "draft_communication_artifact")] == "produces"
    assert relations[("st_revise", "draft_communication_artifact")] == "refines"
    assert {
        item.step_id for item in plan.producing_relations()
    } == {"st_draft"}
    assert worker_steps.worker_steps["worker_main"][0].outputs == [
        "draft_communication_artifact"
    ]
    assert worker_steps.worker_steps["worker_main"][1].outputs == []
