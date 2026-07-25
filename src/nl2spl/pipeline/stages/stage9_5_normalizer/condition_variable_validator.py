"""Stage 9.5 validation/rewrite for condition variable references."""

from __future__ import annotations

from dataclasses import replace

from nl2spl.ir.condition_variable_reference_ir import (
    ConditionTextRewrite,
    ConditionVariableReferenceIR,
    ConditionVariableReferencePlan,
)
from nl2spl.ir.diagnostics import CompileDiagnostic
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.ir.worker_plan_ir import (
    WorkerBlockPlanIR,
    WorkerFlowPlanIR,
    WorkerStepPlanIR,
)
from nl2spl.pipeline.stages.stage6_5_condition_reference_resolver.owner import (
    build_block_condition_owner_ref,
    build_flow_condition_owner_ref,
)


class ConditionVariableVisibilityValidator:
    """Final authority for condition-ref visibility, availability, and rewrite."""

    def validate_and_rewrite(
        self,
        *,
        plan: ConditionVariableReferencePlan,
        worker_flow_plan: WorkerFlowPlanIR,
        worker_block_plan: WorkerBlockPlanIR,
        worker_step_plan: WorkerStepPlanIR,
        symbol_table: SymbolTable,
    ) -> ConditionVariableReferencePlan:
        if not plan.references:
            return ConditionVariableReferencePlan(
                references=plan.references,
                text_rewrites=plan.text_rewrites,
                diagnostics=plan.diagnostics,
                metadata={
                    **dict(plan.metadata),
                    "final_authority": "stage9_5_condition_variable_visibility_validator",
                },
            )

        rewritten_refs = [
            self._rewrite_reference(reference, worker_step_plan)
            for reference in plan.references
        ]
        diagnostics = list(plan.diagnostics)
        diagnostics.extend(
            self._build_final_diagnostics(
                rewritten_refs,
                worker_step_plan,
                worker_block_plan,
                symbol_table,
            )
        )
        text_rewrites = self._build_text_rewrites(plan.references, rewritten_refs)
        updated_plan = ConditionVariableReferencePlan(
            references=tuple(rewritten_refs),
            text_rewrites=tuple([*plan.text_rewrites, *text_rewrites]),
            diagnostics=tuple(diagnostics),
            metadata={
                **dict(plan.metadata),
                "final_authority": "stage9_5_condition_variable_visibility_validator",
            },
        )
        self._apply_text_rewrites(
            worker_flow_plan,
            worker_block_plan,
            updated_plan,
        )
        return updated_plan

    def _rewrite_reference(
        self,
        reference: ConditionVariableReferenceIR,
        worker_step_plan: WorkerStepPlanIR,
    ) -> ConditionVariableReferenceIR:
        if reference.canonical_ref is None:
            return reference
        for composite_plan in worker_step_plan.composite_output_plans:
            for rewrite in composite_plan.reference_rewrites:
                if reference.canonical_ref == rewrite.original_ref:
                    rewritten_path = tuple(rewrite.rewritten_ref.split("."))
                    return replace(
                        reference,
                        canonical_ref=rewrite.rewritten_ref,
                        top_level_name=rewritten_path[0],
                        qualified_path=rewritten_path,
                    )
        return reference

    def _build_text_rewrites(
        self,
        original_refs: tuple[ConditionVariableReferenceIR, ...],
        rewritten_refs: list[ConditionVariableReferenceIR],
    ) -> list[ConditionTextRewrite]:
        rewrites: list[ConditionTextRewrite] = []
        grouped: dict[str, list[tuple[ConditionVariableReferenceIR, ConditionVariableReferenceIR]]] = {}
        for original, rewritten in zip(original_refs, rewritten_refs, strict=True):
            if _needs_condition_text_rewrite(original, rewritten):
                grouped.setdefault(original.owner_ref, []).append((original, rewritten))

        for owner_ref, pairs in grouped.items():
            original_text = pairs[0][0].condition_text
            rewritten_text = original_text
            source_ids: list[str] = []
            rewrite_reason = "composite_output_rewrite"
            for original, rewritten in pairs:
                if rewritten.canonical_ref is None:
                    continue
                if original.ref_text is not None:
                    replacement = _ref_text_for(original.ref_text, rewritten.canonical_ref)
                    rewritten_text = rewritten_text.replace(original.ref_text, replacement, 1)
                    rewrite_reason = "composite_output_rewrite"
                elif original.evidence_kind == "llm_condition_semantic_match":
                    materialized = _materialize_semantic_ref(
                        rewritten_text,
                        original.evidence_text,
                        rewritten.canonical_ref,
                    )
                    if materialized == rewritten_text:
                        continue
                    rewritten_text = materialized
                    rewrite_reason = "llm_semantic_ref_materialization"
                source_ids.append(original.reference_id)
            if rewritten_text != original_text:
                rewrites.append(
                    ConditionTextRewrite(
                        owner_ref=owner_ref,
                        original_condition_text=original_text,
                        rewritten_condition_text=rewritten_text,
                        rewrite_reason=rewrite_reason,  # type: ignore[arg-type]
                        source_reference_ids=tuple(source_ids),
                    )
                )
        return rewrites

    def _build_final_diagnostics(
        self,
        references: list[ConditionVariableReferenceIR],
        worker_step_plan: WorkerStepPlanIR,
        worker_block_plan: WorkerBlockPlanIR,
        symbol_table: SymbolTable,
    ) -> list[CompileDiagnostic]:
        diagnostics: list[CompileDiagnostic] = []
        for reference in references:
            if reference.status in {
                "unresolved",
                "ambiguous",
                "invalid_qualified_ref",
                "rejected",
            }:
                # S6V5/Fix3: explicit missing <REF> blocks completion;
                # LLM unresolved/rejected → report/audit only.
                if reference.evidence_kind != "explicit_ref_token":
                    continue
                diagnostics.append(
                    _condition_diagnostic(
                        reference=reference,
                        kind=_final_kind_for_status(reference.status),
                        message=(
                            f"Condition reference "
                            f"{reference.ref_text or reference.evidence_text or reference.proposed_symbol_text} "
                            f"is {reference.status}."
                        ),
                        blocks_completion=True,
                    )
                )
                continue

            if not reference.top_level_name:
                continue
            visible = (
                symbol_table.get_variables_for_worker(reference.worker_id).get(
                    reference.top_level_name
                )
                if reference.worker_id
                else symbol_table.lookup(reference.top_level_name)
            )
            if visible is None:
                diagnostics.append(
                    _condition_diagnostic(
                        reference=reference,
                        kind="condition_variable_not_visible_in_scope",
                        message=(
                            f"Condition reference {_display_ref(reference)} is not "
                            "declared in visible scope."
                        ),
                    )
                )
                continue

            producer_step_ids = _typed_producer_step_ids(
                reference,
                worker_step_plan,
            )
            if not producer_step_ids and visible.producer_step:
                producer_step_ids = (visible.producer_step,)
            if producer_step_ids and all(
                _producer_not_available(
                    reference,
                    producer_step_id,
                    worker_step_plan,
                    worker_block_plan,
                )
                for producer_step_id in producer_step_ids
            ):
                diagnostics.append(
                    _condition_diagnostic(
                        reference=reference,
                        kind="condition_variable_not_available_before_decision",
                        message=(
                            f"Condition reference {_display_ref(reference)} is produced "
                            "after or inside the decision it controls."
                        ),
                    )
                )

        return diagnostics

    def _apply_text_rewrites(
        self,
        worker_flow_plan: WorkerFlowPlanIR,
        worker_block_plan: WorkerBlockPlanIR,
        plan: ConditionVariableReferencePlan,
    ) -> None:
        rewrites = plan.rewrites_by_owner()
        if not rewrites:
            return

        for worker_id, flow in worker_flow_plan.worker_flows.items():
            for alt in flow.alternative_flows:
                owner_ref = build_flow_condition_owner_ref(
                    worker_id,
                    "alternative",
                    alt.flow_id,
                )
                if owner_ref in rewrites:
                    alt.condition_text = rewrites[owner_ref].rewritten_condition_text
            for exc in flow.exception_flows:
                owner_ref = build_flow_condition_owner_ref(
                    worker_id,
                    "exception",
                    exc.flow_id,
                )
                if owner_ref in rewrites:
                    exc.condition_text = rewrites[owner_ref].rewritten_condition_text

        for worker_id, blocks in worker_block_plan.worker_blocks.items():
            for block in blocks.main_flow_blocks:
                owner_ref = build_block_condition_owner_ref(
                    worker_id,
                    "main",
                    block.block_id,
                )
                if owner_ref in rewrites:
                    block.condition_text = rewrites[owner_ref].rewritten_condition_text
            for flow_id, flow_blocks in blocks.alternative_flow_blocks.items():
                for block in flow_blocks:
                    owner_ref = build_block_condition_owner_ref(
                        worker_id,
                        flow_id,
                        block.block_id,
                    )
                    if owner_ref in rewrites:
                        block.condition_text = rewrites[
                            owner_ref
                        ].rewritten_condition_text
            for flow_id, flow_blocks in blocks.exception_flow_blocks.items():
                for block in flow_blocks:
                    owner_ref = build_block_condition_owner_ref(
                        worker_id,
                        flow_id,
                        block.block_id,
                    )
                    if owner_ref in rewrites:
                        block.condition_text = rewrites[
                            owner_ref
                        ].rewritten_condition_text


def _needs_condition_text_rewrite(
    original: ConditionVariableReferenceIR,
    rewritten: ConditionVariableReferenceIR,
) -> bool:
    if original.ref_text is not None:
        return original.canonical_ref != rewritten.canonical_ref
    return (
        rewritten.status == "resolved"
        and rewritten.canonical_ref is not None
        and original.evidence_kind == "llm_condition_semantic_match"
    )


def _materialize_semantic_ref(
    condition_text: str,
    evidence_text: str | None,
    canonical_ref: str,
) -> str:
    if not evidence_text or evidence_text not in condition_text:
        return condition_text
    return condition_text.replace(evidence_text, f"<REF>{canonical_ref}</REF>", 1)


def _ref_text_for(original_ref_text: str, canonical_ref: str) -> str:
    prefix = "<REF>*" if original_ref_text.startswith("<REF>*") else "<REF>"
    return f"{prefix}{canonical_ref}</REF>"


def _condition_diagnostic(
    *,
    reference: ConditionVariableReferenceIR,
    kind: str,
    message: str,
    blocks_completion: bool = True,
) -> CompileDiagnostic:
    """Create a condition diagnostic with source-sensitive blocking policy.

    S6V5/Fix3: blocks_completion defaults to True for structural errors
    (visibility, availability). Callers must pass blocks_completion=False
    for LLM unresolved/rejected matches (report/audit only).
    """
    return CompileDiagnostic(
        diagnostic_id=f"{kind}_{reference.reference_id}",
        kind=kind,
        severity="warning",
        message=message,
        target_ref=reference.owner_ref,
        source_span_ids=list(reference.source_span_ids),
        metadata={
            "stage": "stage9_5",
            "reference_id": reference.reference_id,
            "owner_kind": reference.owner_kind,
            "canonical_ref": reference.canonical_ref,
            "evidence_kind": reference.evidence_kind,
        },
        blocks_rendering=False,
        blocks_completion=blocks_completion,
    )


def _final_kind_for_status(status: str) -> str:
    if status == "unresolved":
        return "condition_variable_ref_unresolved"
    if status == "ambiguous":
        return "condition_variable_ref_ambiguous"
    if status == "invalid_qualified_ref":
        return "condition_variable_invalid_qualified_ref"
    if status == "rejected":
        return "condition_variable_llm_candidate_rejected"
    return f"condition_variable_{status}"


def _display_ref(reference: ConditionVariableReferenceIR) -> str:
    return (
        reference.ref_text
        or reference.evidence_text
        or reference.proposed_symbol_text
        or reference.canonical_ref
        or "<unknown>"
    )


def _producer_not_available(
    reference: ConditionVariableReferenceIR,
    producer_step_id: str,
    worker_step_plan: WorkerStepPlanIR,
    worker_block_plan: WorkerBlockPlanIR,
) -> bool:
    producer_step = _find_step(worker_step_plan, reference.worker_id, producer_step_id)
    if producer_step is None:
        return True
    if reference.owner_kind != "block_condition":
        return producer_step.flow_ref == reference.flow_ref
    if producer_step.block_ref == reference.block_ref:
        return True
    return _producer_block_is_after_decision_block(
        reference,
        producer_step,
        worker_block_plan,
    )


def _typed_producer_step_ids(
    reference: ConditionVariableReferenceIR,
    worker_step_plan: WorkerStepPlanIR,
) -> tuple[str, ...]:
    relation_plan = worker_step_plan.step_variable_relation_plan
    if relation_plan is None or not reference.top_level_name:
        return ()
    return tuple(
        dict.fromkeys(
            relation.step_id
            for relation in relation_plan.producing_relations()
            if relation.variable_name == reference.top_level_name
        )
    )


def _find_step(
    worker_step_plan: WorkerStepPlanIR,
    worker_id: str | None,
    step_id: str,
) -> StepIR | None:
    if worker_id:
        steps = worker_step_plan.worker_steps.get(worker_id, [])
    else:
        steps = worker_step_plan.get_all_steps()
    return next((step for step in steps if step.step_id == step_id), None)


def _producer_block_is_after_decision_block(
    reference: ConditionVariableReferenceIR,
    producer_step: StepIR,
    worker_block_plan: WorkerBlockPlanIR,
) -> bool:
    if not reference.worker_id or not reference.block_ref:
        return False
    blocks = worker_block_plan.worker_blocks.get(reference.worker_id)
    if blocks is None:
        return False
    flow_ref = reference.flow_ref or "main"
    if flow_ref == "main":
        flow_blocks = blocks.main_flow_blocks
    else:
        flow_blocks = (
            blocks.alternative_flow_blocks.get(flow_ref)
            or blocks.exception_flow_blocks.get(flow_ref)
            or []
        )
    index_by_block = {
        block.block_id: index
        for index, block in enumerate(flow_blocks)
    }
    owner_index = index_by_block.get(reference.block_ref)
    producer_index = index_by_block.get(producer_step.block_ref or "")
    if owner_index is None or producer_index is None:
        return False
    return producer_index >= owner_index
