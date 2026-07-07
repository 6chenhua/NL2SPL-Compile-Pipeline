"""Deterministic policy helpers for Worker Delegation drafting."""

from __future__ import annotations

from dataclasses import dataclass

from nl2spl.compiler.spl_editing.drafting.model import (
    InferenceAlternative,
    RepairClarificationQuestion,
    UserRepairInput,
)
from nl2spl.compiler.spl_editing.drafting.views.worker_delegation import (
    WorkerDelegationDraftingView,
)

USER_FREE_TEXT_EVIDENCE_REF = "user_input:free_text"
USER_INPUT_REFS_EVIDENCE_REF = "user_input:input_refs"
USER_OUTPUT_NAME_EVIDENCE_REF = "user_input:output_display_name"
WORKER_PROMOTION_SUBJECT_EVIDENCE_REF = "worker_promotion:subject"


@dataclass(frozen=True)
class ResponsibilityDecision:
    text: str | None
    source: str
    confidence: str
    evidence_refs: tuple[str, ...]
    clarification: RepairClarificationQuestion | None = None
    decision: str = "selected business responsibility"

    @property
    def is_blocked(self) -> bool:
        return self.text is None


@dataclass(frozen=True)
class InputRefDecision:
    ref_ids: tuple[str, ...]
    source: str
    confidence: str
    evidence_refs: tuple[str, ...]
    clarification: RepairClarificationQuestion | None = None
    explicit_none_reason: str | None = None
    decision: str = "selected input refs"

    @property
    def is_blocked(self) -> bool:
        return not self.ref_ids and self.clarification is not None

    @property
    def is_explicit_none(self) -> bool:
        return not self.ref_ids and self.explicit_none_reason is not None


@dataclass(frozen=True)
class OutputBindingDecision:
    output_local_id: str
    display_name: str
    semantic_description: str
    data_type_hint: str
    output_evidence_refs: tuple[str, ...]
    binding_source: str
    binding_confidence: str
    binding_evidence_refs: tuple[str, ...]
    binding_decision: str
    parent_ref_id: str | None = None
    create_parent_local_temporary: bool = False
    clarification: RepairClarificationQuestion | None = None

    @property
    def is_blocked(self) -> bool:
        return self.parent_ref_id is None and not self.create_parent_local_temporary


@dataclass(frozen=True)
class PlacementDecision:
    mode: str | None
    ref_id: str | None
    source: str
    confidence: str
    evidence_refs: tuple[str, ...]
    decision: str
    preview_text: str
    clarification: RepairClarificationQuestion | None = None

    @property
    def is_blocked(self) -> bool:
        return self.mode is None


def infer_responsibility(
    *,
    view: WorkerDelegationDraftingView,
    user_input: UserRepairInput | None,
    source_evidence_refs: tuple[str, ...],
) -> ResponsibilityDecision:
    child_task = _field_text(user_input, "child_task")
    if child_task is not None:
        return ResponsibilityDecision(
            child_task,
            "user_input.field_values.child_task",
            "high",
            ("user_input:child_task",),
            decision="selected user-confirmed child task",
        )
    free_text = _trimmed(user_input.free_text if user_input is not None else None)
    if free_text is not None:
        return ResponsibilityDecision(
            free_text,
            "user_input.free_text",
            "high",
            (USER_FREE_TEXT_EVIDENCE_REF,),
            decision="selected explicit user responsibility intent",
        )

    candidates = _candidate_tasks(view)
    if len(candidates) == 1:
        return ResponsibilityDecision(
            candidates[0],
            "worker_promotion.source_candidate",
            "medium",
            source_evidence_refs or (WORKER_PROMOTION_SUBJECT_EVIDENCE_REF,),
            decision="selected single source-backed responsibility candidate",
        )
    if len(candidates) > 1:
        return _blocked_with_clarification(
            "worker_promotion.multiple_candidates",
            "Which task should the child worker perform?",
            candidates,
            "multiple responsibility candidates require user choice",
        )

    summary = _trimmed(view.candidate_task_summary)
    if summary is not None and _looks_ambiguous(summary):
        alternatives = _responsibility_alternatives(summary)
        return _blocked_with_clarification(
            "worker_promotion.ambiguous_subject",
            "Which task should the child worker perform?",
            alternatives,
            "ambiguous responsibility candidate requires user choice",
        )
    if summary is not None:
        return ResponsibilityDecision(
            summary,
            "worker_promotion.subject",
            "medium",
            source_evidence_refs or (WORKER_PROMOTION_SUBJECT_EVIDENCE_REF,),
            decision="selected source-backed responsibility summary",
        )

    return _blocked_with_clarification(
        "worker_promotion.missing_subject",
        "What should the child worker do?",
        (),
        "responsibility is missing",
    )


def infer_placement(
    *,
    view: WorkerDelegationDraftingView,
    selected_input_ref_ids: tuple[str, ...],
) -> PlacementDecision:
    first_consumer = _placement_step_by_ref(
        view.placement.placement_steps(),
        view.first_consumer_ref_id,
    )
    if first_consumer is not None:
        blocked = _placement_blocking_reason(
            view=view,
            anchor_ref_id=first_consumer.ref_id,
            selected_input_ref_ids=selected_input_ref_ids,
        )
        if blocked is not None:
            return PlacementDecision(
                None,
                None,
                "PlacementDraftingView.precondition",
                "blocked",
                (first_consumer.ref_id,),
                blocked,
                "Insert: placement needs system review",
            )
        return PlacementDecision(
            "before",
            first_consumer.ref_id,
            "PlacementDraftingView.first_consumer",
            "high",
            (first_consumer.ref_id,),
            "selected placement before first consumer",
            "Insert: before first consumer",
        )

    return PlacementDecision(
        "append",
        None,
        "PlacementDraftingView.no_consumer_fallback",
        "medium",
        ("policy_ref:worker_delegation.placement.append_fallback",),
        "selected append fallback because no first consumer is available",
        "Insert: append to main flow",
    )


def infer_output_binding(
    *,
    view: WorkerDelegationDraftingView,
    responsibility_text: str | None,
    source_evidence_refs: tuple[str, ...],
    user_input: UserRepairInput | None = None,
) -> OutputBindingDecision:
    required_outputs = view.producer.unresolved_required_outputs()
    binding_targets = view.producer.binding_target_refs()
    output_override = (
        _field_text(user_input, "child_output")
        or _field_text(user_input, "output_display_name")
    )
    if output_override is not None:
        matched_binding = _binding_for_name(binding_targets, output_override)
        return OutputBindingDecision(
            _safe_local_id(output_override),
            output_override,
            _output_description(responsibility_text, output_override),
            "text",
            (
                "user_input:child_output"
                if _field_text(user_input, "child_output") is not None
                else USER_OUTPUT_NAME_EVIDENCE_REF,
            ),
            (
                "user_input.field_values.child_output"
                if _field_text(user_input, "child_output") is not None
                else "user_input.field_values.output_display_name"
            ),
            "high",
            (
                matched_binding.ref_id
                if matched_binding is not None
                else (
                    "user_input:child_output"
                    if _field_text(user_input, "child_output") is not None
                    else USER_OUTPUT_NAME_EVIDENCE_REF
                ),
            ),
            (
                "bound child result to user-selected parent-visible result"
                if matched_binding is not None
                else "created user-named child result for parent workflow review"
            ),
            parent_ref_id=matched_binding.ref_id if matched_binding is not None else None,
            create_parent_local_temporary=matched_binding is None,
        )
    possible_outputs = tuple(
        item
        for item in (_trimmed(value) for value in view.candidate_possible_outputs)
        if item is not None
    )

    if len(required_outputs) > 1:
        return _blocked_output_binding(
            "multiple required outputs require user choice",
            tuple(output.display_label for output in required_outputs),
            source_evidence_refs,
        )
    if len(required_outputs) == 1:
        required = required_outputs[0]
        matched_binding = _binding_for_name(binding_targets, required.canonical_name)
        if matched_binding is None:
            return _blocked_output_binding(
                "required output has no legal binding target",
                (required.display_label,),
                (required.ref_id,),
                output_name=required.canonical_name,
            )
        return OutputBindingDecision(
            _safe_local_id(required.canonical_name),
            required.display_label,
            _output_description(responsibility_text, required.display_label),
            required.type_hint or "text",
            (required.ref_id,),
            "ProducerDraftingView.required_output",
            "high",
            (matched_binding.ref_id,),
            "bound child result to required output binding target",
            parent_ref_id=matched_binding.ref_id,
        )

    if possible_outputs:
        matched = tuple(
            ref
            for ref in binding_targets
            if _normalized(ref.canonical_name) in {_normalized(item) for item in possible_outputs}
        )
        if len(matched) == 1:
            return OutputBindingDecision(
                _safe_local_id(matched[0].canonical_name),
                matched[0].display_label,
                _output_description(responsibility_text, matched[0].display_label),
                matched[0].type_hint or "text",
                (matched[0].ref_id,),
                "ProducerDraftingView.candidate_possible_outputs",
                "high",
                (matched[0].ref_id,),
                "bound child result to candidate possible output",
                parent_ref_id=matched[0].ref_id,
            )
        if len(matched) > 1:
            return _blocked_output_binding(
                "multiple output bindings match candidate possible outputs",
                tuple(ref.display_label for ref in matched),
                tuple(ref.ref_id for ref in matched),
            )

    if len(binding_targets) == 1:
        return OutputBindingDecision(
            _safe_local_id(binding_targets[0].canonical_name),
            binding_targets[0].display_label,
            _output_description(responsibility_text, binding_targets[0].display_label),
            binding_targets[0].type_hint or "text",
            source_evidence_refs or (binding_targets[0].ref_id,),
            "ProducerDraftingView.single_binding_target",
            "medium",
            (binding_targets[0].ref_id,),
            "bound child result to single consumer-visible binding target",
            parent_ref_id=binding_targets[0].ref_id,
        )

    fallback_name = (
        _output_name_from_responsibility(responsibility_text)
        or view.candidate_id
        or "delegated_result"
    )
    return OutputBindingDecision(
        _safe_local_id(fallback_name),
        _safe_local_id(fallback_name).replace("_", " "),
        _output_description(responsibility_text, "delegated result"),
        "text",
        source_evidence_refs or ("policy_ref:worker_delegation.output.parent_local",),
        "ProducerDraftingView.parent_local_temporary_policy",
        "medium",
        ("policy_ref:worker_delegation.output.parent_local_temporary",),
        "created parent-local temporary because no required output or consumer binding exists",
        create_parent_local_temporary=True,
    )


def infer_input_refs(
    *,
    view: WorkerDelegationDraftingView,
    user_input: UserRepairInput | None = None,
) -> InputRefDecision:
    candidates = _dedupe_refs(
        tuple(
            ref
            for ref in view.producer.candidate_input_refs()
            if ref.worker_id in {None, view.parent_worker_id}
        )
    )
    input_override = _field_tuple(user_input, "child_inputs")
    input_source = "user_input.field_values.child_inputs"
    input_evidence_ref = "user_input:child_inputs"
    if input_override is None:
        input_override = _field_tuple(user_input, "input_refs")
        input_source = "user_input.field_values.input_refs"
        input_evidence_ref = USER_INPUT_REFS_EVIDENCE_REF
    if input_override is not None:
        candidate_ids = {ref.ref_id for ref in candidates}
        if not input_override:
            return InputRefDecision(
                (),
                input_source,
                "high",
                (input_evidence_ref,),
                explicit_none_reason="User selected no input variables",
                decision="selected user-confirmed no-input semantics",
            )
        if all(ref_id in candidate_ids for ref_id in input_override):
            return InputRefDecision(
                input_override,
                input_source,
                "high",
                (input_evidence_ref, *input_override),
                decision="selected user-confirmed input refs",
            )
        return _blocked_input_choice(
            tuple(ref.display_label for ref in candidates),
            "user-selected input refs are not selectable parent-scope inputs",
        )

    possible_inputs = tuple(
        item
        for item in (_trimmed(value) for value in view.candidate_possible_inputs)
        if item is not None
    )

    if possible_inputs:
        matched = tuple(
            ref
            for ref in candidates
            if _normalized(ref.canonical_name) in {_normalized(item) for item in possible_inputs}
        )
        if len(matched) == 1:
            return InputRefDecision(
                (matched[0].ref_id,),
                "SelectableRefSet.candidate_possible_inputs",
                "high",
                (matched[0].ref_id,),
                decision="selected candidate possible input ref",
            )
        if len(matched) > 1:
            return _blocked_input_choice(
                tuple(ref.display_label for ref in matched),
                "multiple selectable refs match candidate possible inputs",
            )
        return _blocked_input_choice(
            possible_inputs,
            "candidate possible inputs have no selectable ref match",
        )

    parent_request_refs = tuple(
        ref
        for ref in candidates
        if ref.ref_kind == "worker_input" and _normalized(ref.canonical_name) == "userrequest"
    )
    source_repository_refs = tuple(
        ref
        for ref in candidates
        if (
            "connector" in _normalized(ref.canonical_name)
            or "sourcerepositor" in _normalized(ref.canonical_name)
        )
    )
    if source_repository_refs and _responsibility_needs_sources(user_input):
        selected = tuple(ref.ref_id for ref in source_repository_refs)
        return InputRefDecision(
            selected,
            "SelectableRefSet.source_repository_input",
            "medium",
            selected,
            decision="selected source repository input from responsibility text",
        )
    if len(parent_request_refs) == 1:
        return InputRefDecision(
            (parent_request_refs[0].ref_id,),
            "SelectableRefSet.parent_request_input",
            "medium",
            (parent_request_refs[0].ref_id,),
            decision="selected parent user request input as request anchor",
        )

    if len(candidates) == 1:
        return InputRefDecision(
            (candidates[0].ref_id,),
            "SelectableRefSet.single_parent_input",
            "medium",
            (candidates[0].ref_id,),
            decision="selected only parent-scope input ref",
        )
    if len(candidates) > 1:
        return _blocked_input_choice(
            tuple(ref.display_label for ref in candidates),
            "multiple input refs require user choice",
        )

    return InputRefDecision(
        (),
        "SelectableRefSet.no_inputs",
        "medium",
        ("policy_ref:worker_delegation.input.explicit_none",),
        explicit_none_reason="No parent-scope inputs are required or available",
        decision="selected explicit no-input semantics",
    )


def _candidate_tasks(view: WorkerDelegationDraftingView) -> tuple[str, ...]:
    return tuple(
        task
        for task in (_trimmed(candidate) for candidate in view.candidate_task_candidates)
        if task is not None
    )


def _blocked_with_clarification(
    source: str,
    prompt: str,
    candidates: tuple[str, ...],
    decision: str,
) -> ResponsibilityDecision:
    options = tuple(
        InferenceAlternative(candidate, candidate, "medium")
        for candidate in candidates
    )
    return ResponsibilityDecision(
        None,
        source,
        "blocked",
        (),
        RepairClarificationQuestion(
            "clarify_responsibility",
            "child_task",
            prompt,
            options=options,
            required=True,
        ),
        decision=decision,
    )


def _blocked_input_choice(
    candidates: tuple[str, ...],
    decision: str,
) -> InputRefDecision:
    options = tuple(
        InferenceAlternative(candidate, candidate, "medium")
        for candidate in candidates
    )
    return InputRefDecision(
        (),
        "SelectableRefSet.ambiguous_inputs",
        "blocked",
        (),
        RepairClarificationQuestion(
            "clarify_input_refs",
            "child_inputs",
            "Which existing input should the child worker use?",
            options=options,
            required=True,
        ),
        decision=decision,
    )


def _placement_step_by_ref(steps, ref_id: str | None):
    if ref_id is None:
        return None
    for step in steps:
        if step.ref_id == ref_id:
            return step
    return None


def _placement_blocking_reason(
    *,
    view: WorkerDelegationDraftingView,
    anchor_ref_id: str,
    selected_input_ref_ids: tuple[str, ...],
) -> str | None:
    if anchor_ref_id in view.invalid_placement_anchor_ids:
        return "placement anchor crosses an invalid flow or block boundary"
    if anchor_ref_id in view.api_owned_placement_anchor_ids:
        return "placement anchor is API-owned and cannot receive child-worker invoke"
    unavailable_inputs = set(view.input_unavailable_before_ref_ids)
    if any(ref_id in unavailable_inputs for ref_id in selected_input_ref_ids):
        return "selected input is unavailable before placement anchor"
    return None


def _blocked_output_binding(
    decision: str,
    candidates: tuple[str, ...],
    evidence_refs: tuple[str, ...],
    *,
    output_name: str = "delegated_result",
) -> OutputBindingDecision:
    options = tuple(
        InferenceAlternative(candidate, candidate, "medium")
        for candidate in candidates
    )
    return OutputBindingDecision(
        _safe_local_id(output_name),
        output_name.replace("_", " "),
        _output_description(None, output_name),
        "text",
        evidence_refs,
        "ProducerDraftingView.output_binding_blocked",
        "blocked",
        (),
        decision,
        clarification=RepairClarificationQuestion(
            "clarify_result_binding",
            "child_output",
            "Which parent-visible result should receive the child worker output?",
            options=options,
            required=True,
        ),
    )


def _binding_for_name(binding_targets, name: str):
    normalized_name = _normalized(name)
    for ref in binding_targets:
        if _normalized(ref.canonical_name) == normalized_name:
            return ref
    return None


def _output_description(responsibility_text: str | None, display_name: str) -> str:
    return (
        f"Result returned by child worker for {responsibility_text}"
        if responsibility_text
        else f"Result returned by child worker for {display_name}"
    )


def _output_name_from_responsibility(responsibility_text: str | None) -> str | None:
    normalized = _trimmed(responsibility_text)
    if normalized is None:
        return None
    key = _normalized(normalized)
    if "source" in key and "evidence" in key:
        return "source_evidence_result"
    if "source" in key:
        return "source_gathering_result"
    words = _normalized_words(normalized)[:4]
    if not words:
        return None
    return "_".join((*words, "result"))


def _looks_ambiguous(summary: str) -> bool:
    return " or " in summary.lower()


def _responsibility_alternatives(summary: str) -> tuple[str, ...]:
    lower = summary.lower()
    known = []
    for phrase in ("source gathering", "template matching"):
        if phrase in lower:
            known.append(phrase)
    if known:
        return tuple(known)
    return tuple(part.strip() for part in summary.split(" or ") if part.strip())


def _normalized(value: str) -> str:
    return "".join(char.lower() for char in value if char.isalnum())


def _safe_local_id(seed: str) -> str:
    value = "_".join(_normalized_words(seed))
    if not value:
        return "delegated_result"
    if value.startswith("cand_"):
        value = value.removeprefix("cand_")
    if not value[0].isalpha():
        value = f"result_{value}"
    return value[:48]


def _normalized_words(value: str) -> tuple[str, ...]:
    words: list[str] = []
    current = []
    for char in value:
        if char.isalnum():
            current.append(char.lower())
        elif current:
            words.append("".join(current))
            current = []
    if current:
        words.append("".join(current))
    return tuple(words)


def _trimmed(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _field_value(user_input: UserRepairInput | None, field_id: str):
    if user_input is None:
        return None
    for item in user_input.field_values:
        if item.field_id == field_id:
            return item.value
    return None


def _field_text(user_input: UserRepairInput | None, field_id: str) -> str | None:
    value = _field_value(user_input, field_id)
    return _trimmed(value) if isinstance(value, str) else None


def _field_tuple(user_input: UserRepairInput | None, field_id: str) -> tuple[str, ...] | None:
    value = _field_value(user_input, field_id)
    if value is None:
        return None
    if isinstance(value, str):
        return (value,)
    if isinstance(value, tuple) and all(isinstance(item, str) for item in value):
        return value
    return None


def _responsibility_needs_sources(user_input: UserRepairInput | None) -> bool:
    if user_input is None or user_input.free_text is None:
        return False
    text = _normalized(user_input.free_text)
    return "connector" in text or "source" in text or "repository" in text


def _dedupe_refs(refs):
    result = []
    seen = set()
    for ref in refs:
        key = ref.canonical_name
        if key in seen:
            continue
        seen.add(key)
        result.append(ref)
    return tuple(result)
