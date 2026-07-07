"""Deterministic draft-first provider for Worker Delegation define-child repair."""

from __future__ import annotations

import hashlib
from dataclasses import replace

from nl2spl.compiler.spl_editing.drafting.constants import WORKER_DELEGATION_PROVIDER_ID
from nl2spl.compiler.spl_editing.drafting.context import RepairDraftingContext
from nl2spl.compiler.spl_editing.drafting.model import (
    DraftPreview,
    FieldInference,
    InferenceAlternative,
    InferenceTraceRecord,
    InferredRepairDraft,
    UserRepairInput,
)
from nl2spl.compiler.spl_editing.drafting.providers.worker_delegation_policy import (
    infer_input_refs,
    infer_output_binding,
    infer_placement,
    infer_responsibility,
)
from nl2spl.compiler.spl_editing.drafting.values import (
    BusinessLogicValue,
    ExplicitNoneValue,
    NewOutputDraftValue,
    PlacementIntentValue,
    ResponsibilityValue,
    ResultBindingValue,
    SelectedInputRefsValue,
)
from nl2spl.compiler.spl_editing.drafting.views.worker_delegation import (
    WorkerDelegationDraftingView,
)


class WorkerDelegationInferenceProvider:
    provider_id = WORKER_DELEGATION_PROVIDER_ID
    supported_affordance_ids = frozenset({"worker_promotion.resolve_contract"})
    supported_strategy_ids = frozenset({"worker_delegation.complete_closure.v2"})
    supported_option_ids = frozenset({"define_child_worker"})
    supported_patch_types = frozenset({"DefineChildWorkerClosure"})

    def build_context(
        self,
        *,
        issue,
        target,
        catalog_entry,
        option,
        snapshot,
        repair_context=None,
        refset=None,
        subject=None,
    ) -> RepairDraftingContext:
        view = WorkerDelegationDraftingView.from_parts(
            target=target,
            context=repair_context,
            refset=refset,
        )
        subject_summary = subject.summary if subject is not None else None
        if view.candidate_task_summary is None and isinstance(subject_summary, str):
            view = replace(view, candidate_task_summary=subject_summary)
        return RepairDraftingContext(
            issue=issue,
            target=target,
            catalog_entry=catalog_entry,
            option=option,
            snapshot=snapshot,
            views={"worker_delegation": view, "subject": subject},
        )

    def infer(
        self,
        *,
        context: RepairDraftingContext,
        user_input: UserRepairInput | None,
    ) -> InferredRepairDraft:
        view = context.views["worker_delegation"]
        evidence_refs = self._evidence_refs(view)
        responsibility = infer_responsibility(
            view=view,
            user_input=user_input,
            source_evidence_refs=evidence_refs,
        )
        fields: list[FieldInference] = []
        trace: list[InferenceTraceRecord] = []
        questions = []

        if responsibility.text:
            fields.append(
                FieldInference(
                    "child_task",
                    ResponsibilityValue(self.provider_id, responsibility.text),
                    responsibility.confidence,
                    responsibility.evidence_refs,
                )
            )
            trace.append(
                InferenceTraceRecord(
                    "child_task",
                    responsibility.source,
                    responsibility.evidence_refs,
                    responsibility.decision,
                    responsibility.confidence,
                )
            )
        else:
            if responsibility.clarification is not None:
                questions.append(responsibility.clarification)
            fields.append(
                FieldInference(
                    "child_task",
                    None,
                    "blocked",
                    (),
                    blocking_reason=responsibility.decision,
                )
            )

        input_alternatives = _input_alternatives(view)
        input_refs = infer_input_refs(view=view, user_input=user_input)
        if input_refs.ref_ids:
            fields.append(
                FieldInference(
                    "child_inputs",
                    SelectedInputRefsValue(self.provider_id, input_refs.ref_ids),
                    input_refs.confidence,
                    input_refs.evidence_refs,
                    input_alternatives,
                )
            )
            trace.append(
                InferenceTraceRecord(
                    "child_inputs",
                    input_refs.source,
                    input_refs.evidence_refs,
                    input_refs.decision,
                    input_refs.confidence,
                )
            )
        elif input_refs.is_explicit_none:
            fields.append(
                FieldInference(
                    "child_inputs",
                    ExplicitNoneValue(self.provider_id, input_refs.explicit_none_reason or ""),
                    input_refs.confidence,
                    input_refs.evidence_refs,
                )
            )
            trace.append(
                InferenceTraceRecord(
                    "child_inputs",
                    input_refs.source,
                    input_refs.evidence_refs,
                    input_refs.decision,
                    input_refs.confidence,
                )
            )
        else:
            if input_refs.clarification is not None:
                questions.append(input_refs.clarification)
            fields.append(
                FieldInference(
                    "child_inputs",
                    None,
                    "blocked",
                    (),
                    blocking_reason=input_refs.decision,
                )
            )

        output_binding = infer_output_binding(
            view=view,
            responsibility_text=responsibility.text,
            source_evidence_refs=evidence_refs,
            user_input=user_input,
        )
        local_id = output_binding.output_local_id
        output = NewOutputDraftValue(
            self.provider_id,
            local_id,
            output_binding.display_name,
            output_binding.semantic_description,
            output_binding.data_type_hint,
        )
        fields.append(
            FieldInference(
                "child_output",
                output,
                "medium",
                output_binding.output_evidence_refs,
            )
        )
        trace.append(
            InferenceTraceRecord(
                "child_output",
                "worker_promotion.target",
                output_binding.output_evidence_refs,
                "created one child output draft",
                "medium",
            )
        )

        input_summary = _input_summary(view, input_refs.ref_ids)
        business_logic = _business_logic_text(
            user_input=user_input,
            responsibility_text=responsibility.text,
            input_summary=input_summary,
            output_name=output_binding.display_name,
        )
        if business_logic:
            business_logic_evidence = _business_logic_evidence(
                user_input=user_input,
                fallback=evidence_refs or output_binding.output_evidence_refs,
            )
            business_logic_confidence = (
                "high" if _field_text(user_input, "child_business_logic") else "medium"
            )
            fields.append(
                FieldInference(
                    "child_business_logic",
                    BusinessLogicValue(self.provider_id, business_logic),
                    business_logic_confidence,
                    business_logic_evidence,
                )
            )
            trace.append(
                InferenceTraceRecord(
                    "child_business_logic",
                    (
                        "user_input.field_values.child_business_logic"
                        if _field_text(user_input, "child_business_logic")
                        else "worker_delegation.semantic_projection"
                    ),
                    business_logic_evidence,
                    "selected child worker business logic",
                    business_logic_confidence,
                )
            )
        else:
            fields.append(
                FieldInference(
                    "child_business_logic",
                    None,
                    "blocked",
                    (),
                    blocking_reason="child worker business logic is missing",
                )
            )

        placement = infer_placement(
            view=view,
            selected_input_ref_ids=input_refs.ref_ids,
        )
        if placement.mode is not None:
            placement_value = PlacementIntentValue(
                self.provider_id,
                placement.mode,
                placement.ref_id,
            )
            fields.append(
                FieldInference(
                    "placement",
                    placement_value,
                    placement.confidence,
                    placement.evidence_refs,
                )
            )
            trace.append(
                InferenceTraceRecord(
                    "placement",
                    placement.source,
                    placement.evidence_refs,
                    placement.decision,
                    placement.confidence,
                )
            )
        else:
            fields.append(
                FieldInference(
                    "placement",
                    None,
                    "blocked",
                    (),
                    blocking_reason=placement.decision,
                )
            )

        if output_binding.parent_ref_id is not None:
            binding = ResultBindingValue(
                self.provider_id,
                local_id,
                parent_ref_id=output_binding.parent_ref_id,
            )
            fields.append(
                FieldInference(
                    "result_binding",
                    binding,
                    output_binding.binding_confidence,
                    output_binding.binding_evidence_refs,
                )
            )
            trace.append(
                InferenceTraceRecord(
                    "result_binding",
                    output_binding.binding_source,
                    output_binding.binding_evidence_refs,
                    output_binding.binding_decision,
                    output_binding.binding_confidence,
                )
            )
        elif output_binding.create_parent_local_temporary:
            binding = ResultBindingValue(
                self.provider_id,
                local_id,
                create_parent_local_temporary=True,
            )
            fields.append(
                FieldInference(
                    "result_binding",
                    binding,
                    output_binding.binding_confidence,
                    output_binding.binding_evidence_refs,
                )
            )
            trace.append(
                InferenceTraceRecord(
                    "result_binding",
                    output_binding.binding_source,
                    output_binding.binding_evidence_refs,
                    output_binding.binding_decision,
                    output_binding.binding_confidence,
                )
            )
        else:
            if output_binding.clarification is not None:
                questions.append(output_binding.clarification)
            fields.append(
                FieldInference(
                    "result_binding",
                    None,
                    "blocked",
                    (),
                    blocking_reason=output_binding.binding_decision,
                )
            )

        binding_summary = _binding_summary(view, output_binding.parent_ref_id)
        draft_id = _draft_id(context.issue.issue_id, responsibility.text or "", local_id)
        fields, trace = _with_legacy_aliases(fields, trace)
        questions = _with_legacy_question_aliases(questions)
        preview = DraftPreview(
            "Create child worker",
            responsibility.text or "Needs clarification before creating a child worker.",
            (
                f"Input variables: {input_summary}",
                f"Returned result: {output_binding.display_name}",
                f"Business logic: {business_logic or 'needs confirmation'}",
                placement.preview_text,
                f"Result handling: {binding_summary}",
            ),
            ("Clarification required before materialized preview.",) if questions else (),
        )
        return InferredRepairDraft(
            draft_id,
            context.issue.issue_id,
            context.catalog_entry.affordance_id,
            context.option.strategy_id,
            context.option.option_id,
            tuple(fields),
            tuple(questions),
            tuple(trace),
            preview,
        )

    @staticmethod
    def _evidence_refs(view: WorkerDelegationDraftingView) -> tuple[str, ...]:
        return tuple(
            span_id
            for span_id in view.candidate_source_span_ids
            if not span_id.startswith("api:")
        )


def _draft_id(issue_id: str, responsibility: str, local_id: str) -> str:
    digest = hashlib.sha256(f"{issue_id}|{responsibility}|{local_id}".encode()).hexdigest()[:16]
    return f"draft_{digest}"


def _input_summary(
    view: WorkerDelegationDraftingView,
    ref_ids: tuple[str, ...],
) -> str:
    if not ref_ids:
        return "none"
    labels = []
    for ref_id in ref_ids:
        ref = view.selectable_refs.get_ref(ref_id)
        labels.append(ref.display_label if ref is not None else "selected input")
    return ", ".join(labels)


def _binding_summary(
    view: WorkerDelegationDraftingView,
    parent_ref_id: str | None,
) -> str:
    if parent_ref_id is None:
        return "make the result available in the main workflow"
    ref = view.selectable_refs.get_ref(parent_ref_id)
    if ref is None:
        return "store the result in a parent-visible variable"
    return f"store it in {ref.display_label}"


def _input_alternatives(view: WorkerDelegationDraftingView) -> tuple[InferenceAlternative, ...]:
    refs = []
    seen = set()
    for ref in view.producer.candidate_input_refs():
        if ref.worker_id not in {None, view.parent_worker_id}:
            continue
        key = ref.canonical_name
        if key in seen:
            continue
        seen.add(key)
        refs.append(ref)
    return tuple(
        InferenceAlternative(ref.display_label, ref.ref_id, "medium")
        for ref in refs
    )


def _with_legacy_aliases(
    fields: list[FieldInference],
    trace: list[InferenceTraceRecord],
) -> tuple[list[FieldInference], list[InferenceTraceRecord]]:
    alias_map = {
        "child_task": "responsibility",
        "child_inputs": "input_refs",
        "child_output": "output_draft",
    }
    existing_fields = {field.field_id for field in fields}
    existing_trace = {record.field_id for record in trace}
    for semantic_id, legacy_id in alias_map.items():
        if semantic_id in existing_fields and legacy_id not in existing_fields:
            source = next(field for field in fields if field.field_id == semantic_id)
            fields.append(
                FieldInference(
                    legacy_id,
                    source.value,
                    source.confidence,
                    source.evidence_refs,
                    source.alternatives,
                    source.blocking_reason,
                )
            )
            existing_fields.add(legacy_id)
        if semantic_id in existing_trace and legacy_id not in existing_trace:
            source_trace = next(record for record in trace if record.field_id == semantic_id)
            trace.append(
                InferenceTraceRecord(
                    legacy_id,
                    source_trace.source,
                    source_trace.evidence_refs,
                    source_trace.decision,
                    source_trace.confidence,
                    source_trace.alternatives,
                )
            )
            existing_trace.add(legacy_id)
    child_inputs = next(
        (field for field in fields if field.field_id == "child_inputs"),
        None,
    )
    if (
        child_inputs is not None
        and isinstance(child_inputs.value, ExplicitNoneValue)
        and "input_empty_semantics" not in existing_fields
    ):
        fields.append(
            FieldInference(
                "input_empty_semantics",
                child_inputs.value,
                child_inputs.confidence,
                child_inputs.evidence_refs,
                child_inputs.alternatives,
                child_inputs.blocking_reason,
            )
        )
        existing_fields.add("input_empty_semantics")
    child_inputs_trace = next(
        (record for record in trace if record.field_id == "child_inputs"),
        None,
    )
    if (
        child_inputs_trace is not None
        and child_inputs is not None
        and isinstance(child_inputs.value, ExplicitNoneValue)
        and "input_empty_semantics" not in existing_trace
    ):
        trace.append(
            InferenceTraceRecord(
                "input_empty_semantics",
                child_inputs_trace.source,
                child_inputs_trace.evidence_refs,
                child_inputs_trace.decision,
                child_inputs_trace.confidence,
                child_inputs_trace.alternatives,
            )
        )
        existing_trace.add("input_empty_semantics")
    return fields, trace


def _with_legacy_question_aliases(questions):
    result = list(questions)
    field_ids = {question.field_id for question in result}
    aliases = {
        "child_task": "responsibility",
        "child_inputs": "input_refs",
        "child_output": "result_binding",
    }
    for semantic_id, legacy_id in aliases.items():
        if semantic_id in field_ids and legacy_id not in field_ids:
            source = next(question for question in result if question.field_id == semantic_id)
            result.append(replace(source, field_id=legacy_id))
            field_ids.add(legacy_id)
    return result


def _business_logic_text(
    *,
    user_input: UserRepairInput | None,
    responsibility_text: str | None,
    input_summary: str,
    output_name: str,
) -> str | None:
    override = _field_text(user_input, "child_business_logic")
    if override is not None:
        return override
    responsibility = (responsibility_text or "").strip()
    if not responsibility:
        return None
    if input_summary == "none":
        return f"{responsibility}; return {output_name}."
    return f"{responsibility} using {input_summary}; return {output_name}."


def _business_logic_evidence(
    *,
    user_input: UserRepairInput | None,
    fallback: tuple[str, ...],
) -> tuple[str, ...]:
    if _field_text(user_input, "child_business_logic") is not None:
        return ("user_input:child_business_logic",)
    return fallback or ("policy_ref:worker_delegation.business_logic.semantic_projection",)


def _field_text(user_input: UserRepairInput | None, field_id: str) -> str | None:
    if user_input is None:
        return None
    for item in user_input.field_values:
        if item.field_id != field_id:
            continue
        if isinstance(item.value, str) and item.value.strip():
            return item.value.strip()
    return None
