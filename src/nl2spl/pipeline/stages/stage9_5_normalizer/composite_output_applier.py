"""
CompositeOutputPlanApplier - Apply a CompositeOutputPlan to rewrite IR structures.
"""

from __future__ import annotations

from dataclasses import dataclass

from nl2spl.ir import (
    ResourceRegistryIR,
    StepIR,
    StepVariableRelation,
    StepVariableRelationPlan,
    SymbolTable,
    TypeSpec,
    VariableSpec,
    WorkerPlanIR,
)
from nl2spl.ir.composite_output_plan_ir import CompositeOutputPlan


@dataclass(frozen=True)
class CompositeOutputApplyResult:
    relation_plan: StepVariableRelationPlan | None


class CompositeOutputPlanApplier:
    """Applier to execute rewrites defined in CompositeOutputPlan."""

    def apply(
        self,
        *,
        plan: CompositeOutputPlan,
        steps: list[StepIR],
        resources: ResourceRegistryIR,
        symbol_table: SymbolTable,
        worker_plan: WorkerPlanIR,
        relation_plan: StepVariableRelationPlan | None,
    ) -> CompositeOutputApplyResult:
        original_outputs = [intent.variable_name for intent in plan.original_output_intents]

        # 1. step.outputs rewrite for target step
        for s in steps:
            if s.step_id == plan.step_id:
                s.outputs = [plan.composite_variable_name]
                # Also remove self-consuming inputs if any
                s.inputs = [inp for inp in s.inputs if inp not in original_outputs]

        # 2. Downstream step inputs rewrite (original_ref -> qualified ref)
        for s in steps:
            rewritten_inputs = []
            for inp in s.inputs:
                rewrite = next((r for r in plan.reference_rewrites if r.original_ref == inp), None)
                if rewrite:
                    rewritten_inputs.append(rewrite.rewritten_ref)
                else:
                    rewritten_inputs.append(inp)
            s.inputs = rewritten_inputs

        # 3. ResourceRegistryIR.variables rewrite
        resources.variables = [
            var for var in resources.variables if var.name not in original_outputs
        ]
        # Add composite variable
        resources.variables.append(
            VariableSpec(
                name=plan.composite_variable_name,
                data_type=plan.composite_type_name,
                required=True,
                description=f"Structured result for step {plan.step_id}.",
                source="output",
            )
        )

        # 4. ResourceRegistryIR.types rewrite
        type_definition = {
            m.composite_field_name: m.original_data_type for m in plan.field_mappings
        }
        # Check if type already exists
        existing_type = next(
            (t for t in resources.types if t.type_name == plan.composite_type_name), None
        )
        if not existing_type:
            resources.types.append(
                TypeSpec(
                    type_name=plan.composite_type_name,
                    type_kind="structured",
                    definition=type_definition,
                )
            )

        # 5. SymbolTable rewrite
        for out in original_outputs:
            symbol_table.variables.pop(out, None)
        symbol_table.declare(
            plan.composite_variable_name,
            plan.composite_type_name,
            "output",
            f"Structured result for step {plan.step_id}.",
        )
        # Add producer relationship
        symbol_table.add_producer(plan.composite_variable_name, plan.step_id)

        # 6. WorkerPlanIR output contract rewrite
        if plan.worker_output_rewrite:
            worker = next((w for w in worker_plan.workers if w.worker_id == plan.worker_id), None)
            if worker:
                updated_contract = []
                replaced = False
                for field in worker.output_contract:
                    field_name = getattr(field, "name", field)
                    if field_name in plan.worker_output_rewrite.remove_output_names:
                        if not replaced:
                            if isinstance(field, str):
                                updated_contract.append(plan.worker_output_rewrite.add_output_name)
                            else:
                                from copy import copy

                                new_field = copy(field)
                                new_field.name = plan.worker_output_rewrite.add_output_name
                                if hasattr(new_field, "data_type"):
                                    new_field.data_type = plan.composite_type_name
                                if hasattr(new_field, "required"):
                                    new_field.required = True
                                updated_contract.append(new_field)
                            replaced = True
                    else:
                        updated_contract.append(field)
                worker.output_contract = updated_contract

        # 7. StepVariableRelationPlan rewrite
        updated_relation_plan = None
        if relation_plan:
            new_relations = []
            for rel in relation_plan.relations:
                if rel.variable_name in original_outputs:
                    if rel.relation == "produces" and rel.step_id == plan.step_id:
                        already = any(
                            r.step_id == rel.step_id
                            and r.variable_name == plan.composite_variable_name
                            and r.relation == "produces"
                            for r in new_relations
                        )
                        if not already:
                            new_relations.append(
                                StepVariableRelation(
                                    step_id=rel.step_id,
                                    variable_name=plan.composite_variable_name,
                                    relation="produces",
                                    source_span_ids=rel.source_span_ids,
                                    evidence_kind=rel.evidence_kind,
                                )
                            )
                    elif rel.relation == "consumes":
                        new_relations.append(
                            StepVariableRelation(
                                step_id=rel.step_id,
                                variable_name=f"{plan.composite_variable_name}.{rel.variable_name}",
                                relation="consumes",
                                source_span_ids=rel.source_span_ids,
                                evidence_kind=rel.evidence_kind,
                            )
                        )
                else:
                    new_relations.append(rel)
            updated_relation_plan = StepVariableRelationPlan(relations=tuple(new_relations))

        # Write struct aggregation to step metadata for debug/audit (non-correctness authority)
        for s in steps:
            if s.step_id == plan.step_id:
                s.metadata["composite_output_debug"] = {
                    "result_name": plan.composite_variable_name,
                    "original_outputs": original_outputs,
                    "type_name": plan.composite_type_name,
                    "schema_version": plan.schema_version,
                }

        return CompositeOutputApplyResult(relation_plan=updated_relation_plan)
