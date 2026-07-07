"""
Unit tests for CompositeOutputPlanApplier.
"""

from __future__ import annotations

from nl2spl.ir import (
    ResourceRegistryIR,
    StepIR,
    StepVariableRelation,
    StepVariableRelationPlan,
    SymbolTable,
    VariableSpec,
    WorkerPlanIR,
    WorkerSpecIR,
)
from nl2spl.ir.composite_output_plan_ir import (
    CompositeFieldMapping,
    CompositeOutputPlan,
    DeclarationRewrite,
    OutputIntent,
    ReferenceRewrite,
    WorkerOutputRewrite,
)
from nl2spl.pipeline.stages.stage9_5_normalizer.composite_output_applier import (
    CompositeOutputPlanApplier,
)


def test_composite_output_applier_executes_all_rewrites() -> None:
    # 1. Setup IR structures
    step = StepIR(
        step_id="st7",
        text="Record assumptions and completion status",
        source_span_ids=["s20"],
        command_type="GENERAL_COMMAND",
        inputs=["request"],
        outputs=["assumptions_log", "completion_status"],
        block_ref="b1",
    )
    consumer = StepIR(
        step_id="st8",
        text="Review assumptions",
        source_span_ids=["s21"],
        command_type="GENERAL_COMMAND",
        inputs=["assumptions_log"],
        outputs=[],
        block_ref="b1",
    )
    steps = [step, consumer]

    symbols = SymbolTable()
    symbols.declare("request", "text", "input", "req")
    symbols.declare("assumptions_log", "text", "output", "assumptions")
    symbols.declare("completion_status", "text", "output", "status")

    resources = ResourceRegistryIR()
    resources.variables.extend(
        [
            VariableSpec(
                name="request", data_type="text", required=True, source="input", description="req"
            ),
            VariableSpec(
                name="assumptions_log",
                data_type="text",
                required=True,
                source="output",
                description="assumptions",
            ),
            VariableSpec(
                name="completion_status",
                data_type="text",
                required=True,
                source="output",
                description="status",
            ),
        ]
    )

    worker_plan = WorkerPlanIR(
        main_worker_id="worker_main",
        workers=[
            WorkerSpecIR(
                worker_id="worker_main",
                worker_name="MainWorker",
                kind="main",
                purpose="Main worker",
                owned_span_ids=["s20", "s21"],
                output_contract=["assumptions_log", "completion_status"],
            )
        ],
    )

    relation_plan = StepVariableRelationPlan(
        relations=(
            StepVariableRelation(
                step_id="st7",
                variable_name="assumptions_log",
                relation="produces",
                source_span_ids=("s20",),
                evidence_kind="source_text",
            ),
            StepVariableRelation(
                step_id="st7",
                variable_name="completion_status",
                relation="produces",
                source_span_ids=("s20",),
                evidence_kind="source_text",
            ),
            StepVariableRelation(
                step_id="st8",
                variable_name="assumptions_log",
                relation="consumes",
                source_span_ids=("s21",),
                evidence_kind="source_text",
            ),
        )
    )

    # 2. Build mock plan
    intent1 = OutputIntent(
        variable_name="assumptions_log", data_type="text", source_span_ids=("s20",)
    )
    intent2 = OutputIntent(
        variable_name="completion_status", data_type="text", source_span_ids=("s20",)
    )
    mapping1 = CompositeFieldMapping(
        original_field_name="assumptions_log",
        original_data_type="text",
        composite_field_name="assumptions_log",
    )
    mapping2 = CompositeFieldMapping(
        original_field_name="completion_status",
        original_data_type="text",
        composite_field_name="completion_status",
    )
    decl1 = DeclarationRewrite(remove_variable_name="assumptions_log")
    decl2 = DeclarationRewrite(remove_variable_name="completion_status")
    ref1 = ReferenceRewrite(
        original_ref="assumptions_log",
        rewritten_ref="run_completion_record.assumptions_log",
        top_name="run_completion_record",
        field_path=("assumptions_log",),
    )
    ref2 = ReferenceRewrite(
        original_ref="completion_status",
        rewritten_ref="run_completion_record.completion_status",
        top_name="run_completion_record",
        field_path=("completion_status",),
    )
    worker_rewrite = WorkerOutputRewrite(
        remove_output_names=("assumptions_log", "completion_status"),
        add_output_name="run_completion_record",
        add_output_type="RunCompletionRecord",
        required=True,
    )

    plan = CompositeOutputPlan(
        plan_id="cop_worker_main_st7",
        worker_id="worker_main",
        step_id="st7",
        command_type="GENERAL_COMMAND",
        original_output_intents=(intent1, intent2),
        composite_variable_name="run_completion_record",
        composite_type_name="RunCompletionRecord",
        field_mappings=(mapping1, mapping2),
        declaration_rewrites=(decl1, decl2),
        reference_rewrites=(ref1, ref2),
        worker_output_rewrite=worker_rewrite,
        projection_relations=(),
        naming_authority="CompositeNamePolicy",
        source_span_ids=("s20",),
    )

    # 3. Apply the plan
    applier = CompositeOutputPlanApplier()
    apply_result = applier.apply(
        plan=plan,
        steps=steps,
        resources=resources,
        symbol_table=symbols,
        worker_plan=worker_plan,
        relation_plan=relation_plan,
    )

    # 4. Verify rewrites
    # Rewrite 1: step outputs
    assert step.outputs == ["run_completion_record"]

    # Rewrite 2: downstream inputs
    assert consumer.inputs == ["run_completion_record.assumptions_log"]

    # Rewrite 3: variables in resource registry
    registered_vars = {v.name for v in resources.variables}
    assert "assumptions_log" not in registered_vars
    assert "completion_status" not in registered_vars
    assert "run_completion_record" in registered_vars

    # Rewrite 4: types in resource registry
    registered_types = {t.type_name for t in resources.types}
    assert "RunCompletionRecord" in registered_types
    type_spec = next(t for t in resources.types if t.type_name == "RunCompletionRecord")
    assert type_spec.definition == {
        "assumptions_log": "text",
        "completion_status": "text",
    }

    # Rewrite 5: symbols in symbol table
    assert "assumptions_log" not in symbols.variables
    assert "completion_status" not in symbols.variables
    assert "run_completion_record" in symbols.variables

    # Rewrite 6: worker outputs contract
    worker = worker_plan.workers[0]
    assert worker.output_contract == ["run_completion_record"]

    # Rewrite 7: step variable relation plan
    assert apply_result.relation_plan is not None
    producing_relations = [
        r for r in apply_result.relation_plan.relations if r.relation == "produces"
    ]
    assert len(producing_relations) == 1
    assert producing_relations[0].variable_name == "run_completion_record"

    consuming_relations = [
        r for r in apply_result.relation_plan.relations if r.relation == "consumes"
    ]
    assert len(consuming_relations) == 1
    assert consuming_relations[0].variable_name == "run_completion_record.assumptions_log"
