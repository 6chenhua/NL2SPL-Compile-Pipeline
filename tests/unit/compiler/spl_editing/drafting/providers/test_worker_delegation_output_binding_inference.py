from __future__ import annotations

from dataclasses import dataclass

from nl2spl.compiler.spl_editing.drafting.model import UserRepairFieldValue, UserRepairInput
from nl2spl.compiler.spl_editing.drafting.providers.worker_delegation import (
    WorkerDelegationInferenceProvider,
)
from nl2spl.compiler.spl_editing.drafting.values import (
    NewOutputDraftValue,
    ResultBindingValue,
)
from nl2spl.compiler.spl_editing.selectable_refs.model import SelectableRef, SelectableRefSet


@dataclass(frozen=True)
class _Issue:
    issue_id: str = "issue_1"


@dataclass(frozen=True)
class _Target:
    target_ref: str = "worker_promotion:cand_source_gathering"
    worker_id: str = "worker_main"
    canonical_name: str = "cand_source_gathering"


@dataclass(frozen=True)
class _Entry:
    affordance_id: str = "worker_promotion.resolve_contract"


@dataclass(frozen=True)
class _Option:
    strategy_id: str = "worker_delegation.complete_closure.v2"
    option_id: str = "define_child_worker"


@dataclass(frozen=True)
class _Context:
    metadata: dict


def _ref(ref_id: str, role: str, canonical_name: str, *, kind: str = "variable") -> SelectableRef:
    return SelectableRef(
        ref_id,
        kind,
        role,
        canonical_name,
        canonical_name,
        worker_id="worker_main",
        type_hint="text",
    )


def _draft(
    *,
    refs: tuple[SelectableRef, ...],
    metadata: dict | None = None,
    user_input: UserRepairInput | None = None,
):
    provider = WorkerDelegationInferenceProvider()
    context = provider.build_context(
        issue=_Issue(),
        target=_Target(),
        catalog_entry=_Entry(),
        option=_Option(),
        snapshot=object(),
        repair_context=_Context(
            metadata=metadata or {"candidate_source_span_ids": ("s31",)}
        ),
        refset=SelectableRefSet(
            "set_1",
            "issue_1",
            "snapshot_1",
            "worker_main",
            refs,
            "worker_delegation",
        ),
        subject=None,
    )
    return provider.infer(
        context=context,
        user_input=user_input
        or UserRepairInput(
            input_mode="free_text",
            free_text="Gather approved source evidence",
        ),
    )


def _output_and_binding(draft):
    output = next(field for field in draft.fields if field.field_id == "output_draft")
    binding = next(field for field in draft.fields if field.field_id == "result_binding")
    return output, binding


def test_required_output_gap_binds_matching_required_output_target() -> None:
    draft = _draft(
        refs=(
            _ref("ref:input:user_request", "selectable_input", "user_request"),
            _ref(
                "ref:target:source_evidence",
                "target_output",
                "source_evidence",
                kind="required_output",
            ),
            _ref("ref:binding:source_evidence", "binding_target", "source_evidence"),
        )
    )
    output, binding = _output_and_binding(draft)

    assert isinstance(output.value, NewOutputDraftValue)
    assert output.value.local_id == "source_evidence"
    assert output.evidence_refs == ("ref:target:source_evidence",)
    assert isinstance(binding.value, ResultBindingValue)
    assert binding.value.parent_ref_id == "ref:binding:source_evidence"
    assert binding.value.create_parent_local_temporary is False


def test_required_output_without_binding_target_is_blocked_not_temporary() -> None:
    draft = _draft(
        refs=(
            _ref("ref:input:user_request", "selectable_input", "user_request"),
            _ref(
                "ref:target:source_evidence",
                "target_output",
                "source_evidence",
                kind="required_output",
            ),
        )
    )
    _output, binding = _output_and_binding(draft)

    assert binding.value is None
    assert binding.confidence == "blocked"
    assert draft.clarification_questions


def test_single_consumer_visible_binding_target_is_used() -> None:
    draft = _draft(
        refs=(
            _ref("ref:input:user_request", "selectable_input", "user_request"),
            _ref("ref:binding:assumptions_log", "binding_target", "assumptions_log"),
        )
    )
    output, binding = _output_and_binding(draft)

    assert output.value.local_id == "assumptions_log"
    assert isinstance(binding.value, ResultBindingValue)
    assert binding.value.parent_ref_id == "ref:binding:assumptions_log"


def test_parent_local_temporary_only_when_no_required_output_or_consumer() -> None:
    draft = _draft(
        refs=(_ref("ref:input:user_request", "selectable_input", "user_request"),)
    )
    output, binding = _output_and_binding(draft)
    trace = next(record for record in draft.trace if record.field_id == "result_binding")

    assert isinstance(output.value, NewOutputDraftValue)
    assert output.value.local_id == "source_evidence_result"
    assert output.value.display_name == "source evidence result"
    assert isinstance(binding.value, ResultBindingValue)
    assert binding.value.create_parent_local_temporary is True
    assert binding.evidence_refs == (
        "policy_ref:worker_delegation.output.parent_local_temporary",
    )
    assert trace.evidence_refs == binding.evidence_refs


def test_ambiguous_required_outputs_return_clarification() -> None:
    draft = _draft(
        refs=(
            _ref("ref:input:user_request", "selectable_input", "user_request"),
            _ref("ref:target:a", "target_output", "a", kind="required_output"),
            _ref("ref:target:b", "target_output", "b", kind="required_output"),
        )
    )
    _output, binding = _output_and_binding(draft)

    assert binding.value is None
    assert binding.confidence == "blocked"
    assert any(question.field_id == "result_binding" for question in draft.clarification_questions)


def test_free_text_does_not_directly_create_binding_target() -> None:
    draft = _draft(
        refs=(_ref("ref:input:user_request", "selectable_input", "user_request"),),
        metadata={"candidate_source_span_ids": ("s31",)},
    )
    _output, binding = _output_and_binding(draft)

    assert isinstance(binding.value, ResultBindingValue)
    assert binding.value.parent_ref_id is None
    assert binding.value.create_parent_local_temporary is True


def test_user_output_name_override_creates_user_named_result() -> None:
    draft = _draft(
        refs=(_ref("ref:input:user_request", "selectable_input", "user_request"),),
        user_input=UserRepairInput(
            input_mode="mixed",
            free_text="Gather approved source evidence",
            field_values=(
                UserRepairFieldValue(
                    "output_display_name",
                    "approved source evidence",
                    "user",
                ),
            ),
        ),
    )
    output, binding = _output_and_binding(draft)
    trace = next(record for record in draft.trace if record.field_id == "result_binding")

    assert isinstance(output.value, NewOutputDraftValue)
    assert output.value.local_id == "approved_source_evidence"
    assert output.value.display_name == "approved source evidence"
    assert output.evidence_refs == ("user_input:output_display_name",)
    assert isinstance(binding.value, ResultBindingValue)
    assert binding.value.create_parent_local_temporary is True
    assert trace.source == "user_input.field_values.output_display_name"
