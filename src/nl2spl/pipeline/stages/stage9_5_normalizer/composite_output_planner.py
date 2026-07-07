"""
CompositeOutputPlanner - Analyze steps and generate CompositeOutputPlans.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from nl2spl.ir import StepIR, StepVariableRelationPlan, SymbolTable, WorkerPlanIR
from nl2spl.ir.composite_output_plan_ir import (
    CompositeFieldMapping,
    CompositeOutputPlan,
    DeclarationRewrite,
    OutputIntent,
    ReferenceRewrite,
    WorkerOutputRewrite,
)
from nl2spl.ir.diagnostics import CompileDiagnostic
from nl2spl.pipeline.stages.stage9_5_normalizer.composite_name_policy import (
    CompositeNamePolicy,
)


@dataclass(frozen=True)
class CompositeOutputPlanningResult:
    plans: tuple[CompositeOutputPlan, ...]
    diagnostics: tuple[CompileDiagnostic, ...]


class CompositeOutputPlanner:
    """Planner to build CompositeOutputPlans from worker steps."""

    def build_plans(
        self,
        *,
        steps: list[StepIR],
        symbol_table: SymbolTable,
        relation_plan: StepVariableRelationPlan | None,
        worker_id: str,
        worker_plan: WorkerPlanIR,
    ) -> CompositeOutputPlanningResult:
        plans: list[CompositeOutputPlan] = []
        diagnostics: list[CompileDiagnostic] = []
        policy = CompositeNamePolicy()

        for step in steps:
            non_empty_outputs = [o for o in step.outputs if o]
            if len(non_empty_outputs) <= 1:
                continue

            original_outputs = list(dict.fromkeys(non_empty_outputs))

            # 1. Variable Name Selection. Legacy aggregation metadata is
            # debug/compatibility payload only; it is not a naming authority
            # for new CompositeOutputPlan instances.
            candidate_var_name = None
            joined = "_".join(original_outputs)
            joined_cleaned = re.sub(r"[^A-Za-z0-9_]", "", joined)
            policy_res = policy.validate_variable_name(joined_cleaned)
            if policy_res.accepted:
                candidate_var_name = joined_cleaned

            # If naming policy failed, create diagnostic and fail closed
            if not candidate_var_name:
                diagnostics.append(
                    CompileDiagnostic(
                        diagnostic_id=f"diag_name_policy_{step.step_id}",
                        kind="composite_name_policy_violation",
                        severity="error",
                        message=(
                            f"Composite name policy violation for step '{step.step_id}': "
                            "Could not generate a valid variable name for "
                            f"outputs {original_outputs}"
                        ),
                        target_ref=f"step:{step.step_id}",
                        source_span_ids=list(step.source_span_ids),
                        blocks_rendering=True,
                        blocks_completion=True,
                    )
                )
                continue

            # 2. Type Name Selection
            candidate_type_name = None

            # Generate from variable name (CamelCase).
            camel_case = "".join(
                part.capitalize() for part in candidate_var_name.split("_") if part
            )
            policy_res = policy.validate_type_name(camel_case)
            if policy_res.accepted:
                candidate_type_name = camel_case

            # If type naming policy failed, fail closed
            if not candidate_type_name:
                diagnostics.append(
                    CompileDiagnostic(
                        diagnostic_id=f"diag_name_policy_type_{step.step_id}",
                        kind="composite_name_policy_violation",
                        severity="error",
                        message=(
                            f"Composite name policy violation for step '{step.step_id}': "
                            "Could not generate a valid type name from "
                            f"variable '{candidate_var_name}'"
                        ),
                        target_ref=f"step:{step.step_id}",
                        source_span_ids=list(step.source_span_ids),
                        blocks_rendering=True,
                        blocks_completion=True,
                    )
                )
                continue

            # 3. Create Plan details
            # a. Original Output Intents
            intents = []
            for out in original_outputs:
                # get data type from symbol table
                sym = symbol_table.variables.get(out)
                data_type = sym.data_type if sym else "text"
                # get source span ids from relation plan if available
                span_ids = ()
                if relation_plan:
                    rel = next(
                        (
                            r
                            for r in relation_plan.relations
                            if r.step_id == step.step_id and r.variable_name == out
                        ),
                        None,
                    )
                    if rel:
                        span_ids = tuple(rel.source_span_ids)
                if not span_ids:
                    span_ids = tuple(step.source_span_ids)
                intents.append(
                    OutputIntent(
                        variable_name=out,
                        data_type=data_type,
                        source_span_ids=span_ids,
                    )
                )

            # b. Field Mappings
            mappings = []
            for out in original_outputs:
                sym = symbol_table.variables.get(out)
                data_type = sym.data_type if sym else "text"
                mappings.append(
                    CompositeFieldMapping(
                        original_field_name=out,
                        original_data_type=data_type,
                        composite_field_name=out,
                    )
                )

            # c. Declaration Rewrites
            decl_rewrites = [
                DeclarationRewrite(remove_variable_name=out) for out in original_outputs
            ]

            # d. Reference Rewrites
            ref_rewrites = []
            for out in original_outputs:
                ref_rewrites.append(
                    ReferenceRewrite(
                        original_ref=out,
                        rewritten_ref=f"{candidate_var_name}.{out}",
                        top_name=candidate_var_name,
                        field_path=(out,),
                    )
                )

            # e. Worker Output Rewrite
            worker_rewrite = None
            worker = next((w for w in worker_plan.workers if w.worker_id == worker_id), None)
            if worker:
                removed_contract_fields = tuple(
                    getattr(f, "name", f)
                    for f in worker.output_contract
                    if getattr(f, "name", f) in original_outputs
                )
                if removed_contract_fields:
                    # check if any of the removed outputs were required
                    # (we assume required=True for composite)
                    worker_rewrite = WorkerOutputRewrite(
                        remove_output_names=removed_contract_fields,
                        add_output_name=candidate_var_name,
                        add_output_type=candidate_type_name,
                        required=True,
                    )

            # Build CompositeOutputPlan
            plans.append(
                CompositeOutputPlan(
                    plan_id=f"cop_{worker_id}_{step.step_id}",
                    worker_id=worker_id,
                    step_id=step.step_id,
                    command_type=step.command_type,
                    original_output_intents=tuple(intents),
                    composite_variable_name=candidate_var_name,
                    composite_type_name=candidate_type_name,
                    field_mappings=tuple(mappings),
                    declaration_rewrites=tuple(decl_rewrites),
                    reference_rewrites=tuple(ref_rewrites),
                    worker_output_rewrite=worker_rewrite,
                    projection_relations=(),
                    naming_authority="CompositeNamePolicy",
                    source_span_ids=tuple(step.source_span_ids),
                    schema_version="composite_output_plan.v1",
                )
            )

        return CompositeOutputPlanningResult(
            plans=tuple(plans),
            diagnostics=tuple(diagnostics),
        )
