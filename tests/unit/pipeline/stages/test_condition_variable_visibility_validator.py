from __future__ import annotations

from nl2spl.ir.block_structure_ir import BlockIR, BlockStructureIR
from nl2spl.ir.composite_output_plan_ir import (
    CompositeOutputPlan,
    ReferenceRewrite,
)
from nl2spl.ir.condition_variable_reference_ir import (
    ConditionVariableReferenceIR,
    ConditionVariableReferencePlan,
)
from nl2spl.ir.flow_structure_ir import FlowStructureIR
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.step_variable_relation_ir import (
    StepVariableRelation,
    StepVariableRelationPlan,
)
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.ir.worker_plan_ir import WorkerBlockPlanIR, WorkerFlowPlanIR, WorkerStepPlanIR
from nl2spl.pipeline.stages.stage9_5_normalizer.condition_variable_validator import (
    ConditionVariableVisibilityValidator,
)


def test_validator_rewrites_condition_text_from_composite_output_plan() -> None:
    symbols = SymbolTable()
    symbols.declare_scoped(
        name="a_b",
        data_type="A_B",
        source="step",
        description="composite",
        scope_kind="worker",
        scope_id="worker_main",
    )
    flow_plan = WorkerFlowPlanIR(worker_flows={"worker_main": FlowStructureIR()})
    block = BlockIR(
        block_id="b1",
        block_type="IF",
        condition_text="<REF>a</REF> is ready",
        spans=["s1"],
    )
    block_plan = WorkerBlockPlanIR(
        worker_blocks={
            "worker_main": BlockStructureIR(main_flow_blocks=[block]),
        }
    )
    reference = ConditionVariableReferenceIR(
        reference_id="cond_ref_owner_0",
        owner_kind="block_condition",
        owner_ref="condition:block:worker_main:main:b1",
        condition_text=block.condition_text or "",
        ref_text="<REF>a</REF>",
        canonical_ref="a",
        top_level_name="a",
        qualified_path=("a",),
        status="resolved",
        source_span_ids=("s1",),
        worker_id="worker_main",
        flow_ref="main",
        block_ref="b1",
    )
    worker_step_plan = WorkerStepPlanIR(
        main_worker_id="worker_main",
        worker_steps={"worker_main": []},
        composite_output_plans=(
            _composite_plan(
                ReferenceRewrite(
                    original_ref="a",
                    rewritten_ref="a_b.a",
                    top_name="a_b",
                    field_path=("a",),
                )
            ),
        ),
    )

    plan = ConditionVariableVisibilityValidator().validate_and_rewrite(
        plan=ConditionVariableReferencePlan(references=(reference,)),
        worker_flow_plan=flow_plan,
        worker_block_plan=block_plan,
        worker_step_plan=worker_step_plan,
        symbol_table=symbols,
    )

    assert block.condition_text == "<REF>a_b.a</REF> is ready"
    assert plan.text_rewrites[0].source_reference_ids == ("cond_ref_owner_0",)
    assert plan.references[0].canonical_ref == "a_b.a"


def test_validator_distinguishes_visibility_and_execution_availability() -> None:
    symbols = SymbolTable()
    symbols.declare_scoped(
        name="late_value",
        data_type="text",
        source="step",
        description="late",
        scope_kind="worker",
        scope_id="worker_main",
    )
    symbols.add_producer("late_value", "st_late")
    block = BlockIR(
        block_id="b1",
        block_type="IF",
        condition_text="<REF>late_value</REF> is present",
        spans=["s1"],
    )
    reference = ConditionVariableReferenceIR(
        reference_id="cond_ref_owner_0",
        owner_kind="block_condition",
        owner_ref="condition:block:worker_main:main:b1",
        condition_text=block.condition_text or "",
        ref_text="<REF>late_value</REF>",
        canonical_ref="late_value",
        top_level_name="late_value",
        qualified_path=("late_value",),
        status="resolved",
        source_span_ids=("s1",),
        worker_id="worker_main",
        flow_ref="main",
        block_ref="b1",
    )
    plan = ConditionVariableVisibilityValidator().validate_and_rewrite(
        plan=ConditionVariableReferencePlan(references=(reference,)),
        worker_flow_plan=WorkerFlowPlanIR(
            worker_flows={"worker_main": FlowStructureIR()}
        ),
        worker_block_plan=WorkerBlockPlanIR(
            worker_blocks={
                "worker_main": BlockStructureIR(main_flow_blocks=[block]),
            }
        ),
        worker_step_plan=WorkerStepPlanIR(
            main_worker_id="worker_main",
            worker_steps={
                "worker_main": [
                    StepIR(
                        step_id="st_late",
                        text="Produce late value",
                        source_span_ids=["s1"],
                        command_type="GENERAL_COMMAND",
                        outputs=["late_value"],
                        block_ref="b1",
                    )
                ]
            },
        ),
        symbol_table=symbols,
    )

    assert {
        diagnostic.kind for diagnostic in plan.diagnostics
    } == {"condition_variable_not_available_before_decision"}


def test_validator_accepts_any_typed_producer_available_before_decision() -> None:
    symbols = SymbolTable()
    symbols.declare_scoped(
        name="draft",
        data_type="text",
        source="step",
        description="draft",
        scope_kind="worker",
        scope_id="worker_main",
    )
    symbols.add_producer("draft", "st_late")
    before = BlockIR(
        block_id="b0",
        block_type="SEQUENTIAL",
        spans=["s0"],
    )
    decision = BlockIR(
        block_id="b1",
        block_type="IF",
        condition_text="<REF>draft</REF> needs revision",
        spans=["s1"],
    )
    reference = ConditionVariableReferenceIR(
        reference_id="cond_ref_owner_0",
        owner_kind="block_condition",
        owner_ref="condition:block:worker_main:main:b1",
        condition_text=decision.condition_text or "",
        ref_text="<REF>draft</REF>",
        canonical_ref="draft",
        top_level_name="draft",
        qualified_path=("draft",),
        status="resolved",
        source_span_ids=("s1",),
        worker_id="worker_main",
        flow_ref="main",
        block_ref="b1",
    )
    steps = [
        StepIR(
            step_id="st_early",
            text="Produce draft",
            source_span_ids=["s0"],
            command_type="GENERAL_COMMAND",
            outputs=["draft"],
            block_ref="b0",
            flow_ref="main",
        ),
        StepIR(
            step_id="st_late",
            text="Revise draft",
            source_span_ids=["s1"],
            command_type="GENERAL_COMMAND",
            outputs=["draft"],
            block_ref="b1",
            flow_ref="main",
        ),
    ]
    relation_plan = StepVariableRelationPlan(
        relations=(
            _produces("st_early", "draft", "s0"),
            _produces("st_late", "draft", "s1"),
        )
    )

    plan = ConditionVariableVisibilityValidator().validate_and_rewrite(
        plan=ConditionVariableReferencePlan(references=(reference,)),
        worker_flow_plan=WorkerFlowPlanIR(
            worker_flows={"worker_main": FlowStructureIR()}
        ),
        worker_block_plan=WorkerBlockPlanIR(
            worker_blocks={
                "worker_main": BlockStructureIR(
                    main_flow_blocks=[before, decision]
                ),
            }
        ),
        worker_step_plan=WorkerStepPlanIR(
            main_worker_id="worker_main",
            worker_steps={"worker_main": steps},
            step_variable_relation_plan=relation_plan,
        ),
        symbol_table=symbols,
    )

    assert not {
        diagnostic.kind
        for diagnostic in plan.diagnostics
        if diagnostic.kind == "condition_variable_not_available_before_decision"
    }


def test_validator_materializes_llm_semantic_condition_reference() -> None:
    symbols = SymbolTable()
    symbols.declare_scoped(
        name="evidence",
        data_type="text",
        source="input",
        description="Collected evidence",
        scope_kind="worker",
        scope_id="worker_main",
    )
    block = BlockIR(
        block_id="b1",
        block_type="IF",
        condition_text="when enough evidence has been collected",
        spans=["s1"],
    )
    reference = ConditionVariableReferenceIR(
        reference_id="cond_ref_owner_llm_0",
        owner_kind="block_condition",
        owner_ref="condition:block:worker_main:main:b1",
        condition_text=block.condition_text or "",
        ref_text=None,
        canonical_ref="evidence",
        top_level_name="evidence",
        qualified_path=("evidence",),
        status="resolved",
        source_span_ids=("s1",),
        worker_id="worker_main",
        flow_ref="main",
        block_ref="b1",
        evidence_kind="llm_condition_semantic_match",
        evidence_text="enough evidence has been collected",
        selected_symbol="evidence",
        confidence="medium",
    )

    plan = ConditionVariableVisibilityValidator().validate_and_rewrite(
        plan=ConditionVariableReferencePlan(references=(reference,)),
        worker_flow_plan=WorkerFlowPlanIR(
            worker_flows={"worker_main": FlowStructureIR()}
        ),
        worker_block_plan=WorkerBlockPlanIR(
            worker_blocks={
                "worker_main": BlockStructureIR(main_flow_blocks=[block]),
            }
        ),
        worker_step_plan=WorkerStepPlanIR(
            main_worker_id="worker_main",
            worker_steps={"worker_main": []},
        ),
        symbol_table=symbols,
    )

    assert block.condition_text == "when <REF>evidence</REF>"
    assert plan.text_rewrites[0].rewrite_reason == "llm_semantic_ref_materialization"


def test_materializer_replaces_only_variable_substring() -> None:
    symbols = SymbolTable()
    symbols.declare_scoped(
        name="timeframe",
        data_type="text",
        source="input",
        description="timeframe context",
        scope_kind="worker",
        scope_id="worker_main",
    )
    block = BlockIR(
        block_id="b1",
        block_type="IF",
        condition_text="Missing timeframe",
        spans=["s1"],
    )
    reference = ConditionVariableReferenceIR(
        reference_id="cond_ref_owner_llm_0",
        owner_kind="block_condition",
        owner_ref="condition:block:worker_main:main:b1",
        condition_text=block.condition_text or "",
        ref_text=None,
        canonical_ref="timeframe",
        top_level_name="timeframe",
        qualified_path=("timeframe",),
        status="resolved",
        source_span_ids=("s1",),
        worker_id="worker_main",
        flow_ref="main",
        block_ref="b1",
        evidence_kind="llm_condition_semantic_match",
        evidence_text="timeframe",
        selected_symbol="timeframe",
        confidence="high",
    )

    plan = ConditionVariableVisibilityValidator().validate_and_rewrite(
        plan=ConditionVariableReferencePlan(references=(reference,)),
        worker_flow_plan=WorkerFlowPlanIR(
            worker_flows={"worker_main": FlowStructureIR()}
        ),
        worker_block_plan=WorkerBlockPlanIR(
            worker_blocks={
                "worker_main": BlockStructureIR(main_flow_blocks=[block]),
            }
        ),
        worker_step_plan=WorkerStepPlanIR(
            main_worker_id="worker_main",
            worker_steps={"worker_main": []},
        ),
        symbol_table=symbols,
    )

    assert block.condition_text == "Missing <REF>timeframe</REF>"
    assert plan.text_rewrites[0].rewrite_reason == "llm_semantic_ref_materialization"


def test_materializer_does_not_rewrite_full_condition_overmatch() -> None:
    symbols = SymbolTable()
    symbols.declare_scoped(
        name="user_request",
        data_type="text",
        source="input",
        description="user request context",
        scope_kind="worker",
        scope_id="worker_main",
    )
    block = BlockIR(
        block_id="b1",
        block_type="IF",
        condition_text="user refusal to answer",
        spans=["s1"],
    )
    # Simulator for a rejected reference (due to full overmatch / direct anchor missing)
    # The resolver will set it to rejected and filter it out of the plan.
    # If a reference is rejected, it does not get rewritten.
    reference = ConditionVariableReferenceIR(
        reference_id="cond_ref_owner_llm_0",
        owner_kind="block_condition",
        owner_ref="condition:block:worker_main:main:b1",
        condition_text=block.condition_text or "",
        ref_text=None,
        canonical_ref=None,
        top_level_name=None,
        qualified_path=(),
        status="rejected",
        source_span_ids=("s1",),
        worker_id="worker_main",
        flow_ref="main",
        block_ref="b1",
        evidence_kind="llm_condition_semantic_match",
        evidence_text="user refusal to answer",
        selected_symbol="user_request",
        confidence="low",
        reason="full_condition_overmatch",
    )

    plan = ConditionVariableVisibilityValidator().validate_and_rewrite(
        plan=ConditionVariableReferencePlan(references=(reference,)),
        worker_flow_plan=WorkerFlowPlanIR(
            worker_flows={"worker_main": FlowStructureIR()}
        ),
        worker_block_plan=WorkerBlockPlanIR(
            worker_blocks={
                "worker_main": BlockStructureIR(main_flow_blocks=[block]),
            }
        ),
        worker_step_plan=WorkerStepPlanIR(
            main_worker_id="worker_main",
            worker_steps={"worker_main": []},
        ),
        symbol_table=symbols,
    )

    # Condition text remains raw text and unchanged
    assert block.condition_text == "user refusal to answer"
    assert len(plan.text_rewrites) == 0


def test_validator_keeps_llm_unresolved_concept_as_audit_only() -> None:
    reference = ConditionVariableReferenceIR(
        reference_id="cond_ref_owner_unresolved_0",
        owner_kind="block_condition",
        owner_ref="condition:block:worker_main:main:b1",
        condition_text="facts are available",
        ref_text=None,
        canonical_ref=None,
        top_level_name=None,
        qualified_path=(),
        status="unresolved",
        source_span_ids=("s1",),
        worker_id="worker_main",
        flow_ref="main",
        block_ref="b1",
        evidence_kind="llm_unresolved_condition_symbol",
        evidence_text="facts",
        proposed_symbol_text="facts",
    )

    plan = ConditionVariableVisibilityValidator().validate_and_rewrite(
        plan=ConditionVariableReferencePlan(references=(reference,)),
        worker_flow_plan=WorkerFlowPlanIR(
            worker_flows={"worker_main": FlowStructureIR()}
        ),
        worker_block_plan=WorkerBlockPlanIR(
            worker_blocks={
                "worker_main": BlockStructureIR(
                    main_flow_blocks=[
                        BlockIR(
                            block_id="b1",
                            block_type="IF",
                            condition_text="facts are available",
                            spans=["s1"],
                        )
                    ]
                )
            }
        ),
        worker_step_plan=WorkerStepPlanIR(
            main_worker_id="worker_main",
            worker_steps={"worker_main": []},
        ),
        symbol_table=SymbolTable(),
    )

    assert plan.references == (reference,)
    assert not plan.diagnostics


def _produces(
    step_id: str,
    variable_name: str,
    source_span_id: str,
) -> StepVariableRelation:
    return StepVariableRelation(
        step_id=step_id,
        variable_name=variable_name,
        relation="produces",
        source_span_ids=(source_span_id,),
        evidence_kind="source_text",
    )


def _composite_plan(rewrite: ReferenceRewrite) -> CompositeOutputPlan:
    return CompositeOutputPlan(
        plan_id="cop_1",
        worker_id="worker_main",
        step_id="st_1",
        command_type="GENERAL_COMMAND",
        original_output_intents=(),
        composite_variable_name="a_b",
        composite_type_name="A_B",
        field_mappings=(),
        declaration_rewrites=(),
        reference_rewrites=(rewrite,),
        worker_output_rewrite=None,
        projection_relations=(),
        naming_authority="test",
        source_span_ids=("s1",),
    )
