from __future__ import annotations

from dataclasses import dataclass

from nl2spl.compiler.spl_editing.drafting.model import UserRepairFieldValue, UserRepairInput
from nl2spl.compiler.spl_editing.drafting.providers.worker_delegation import (
    WorkerDelegationInferenceProvider,
)
from nl2spl.compiler.spl_editing.drafting.serialization import to_json_text
from nl2spl.compiler.spl_editing.drafting.values import (
    ExplicitNoneValue,
    SelectedInputRefsValue,
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


def _selectable_ref(
    ref_id: str,
    role: str,
    canonical_name: str,
    *,
    worker_id: str | None = "worker_main",
    ref_kind: str = "variable",
) -> SelectableRef:
    return SelectableRef(
        ref_id,
        ref_kind,
        role,
        canonical_name,
        canonical_name,
        worker_id=worker_id,
        type_hint="text",
    )


def _draft(*, refs: tuple[SelectableRef, ...], metadata: dict):
    provider = WorkerDelegationInferenceProvider()
    context = provider.build_context(
        issue=_Issue(),
        target=_Target(),
        catalog_entry=_Entry(),
        option=_Option(),
        snapshot=object(),
        repair_context=_Context(metadata=metadata),
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
        user_input=UserRepairInput(
            input_mode="free_text",
            free_text="Gather approved source evidence",
        ),
    )


def _draft_with_input(*, refs: tuple[SelectableRef, ...], metadata: dict, user_input):
    provider = WorkerDelegationInferenceProvider()
    context = provider.build_context(
        issue=_Issue(),
        target=_Target(),
        catalog_entry=_Entry(),
        option=_Option(),
        snapshot=object(),
        repair_context=_Context(metadata=metadata),
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
    return provider.infer(context=context, user_input=user_input)


def test_possible_input_match_selects_non_user_request_ref() -> None:
    draft = _draft(
        refs=(
            _selectable_ref("ref:input:user_request", "selectable_input", "user_request"),
            _selectable_ref("ref:input:source_notes", "selectable_input", "source_notes"),
            _selectable_ref("ref:binding:source_evidence", "binding_target", "source_evidence"),
        ),
        metadata={
            "candidate_possible_inputs": ("source notes",),
            "candidate_source_span_ids": ("s31",),
        },
    )
    field = next(field for field in draft.fields if field.field_id == "input_refs")
    trace = next(record for record in draft.trace if record.field_id == "input_refs")

    assert isinstance(field.value, SelectedInputRefsValue)
    assert field.value.ref_ids == ("ref:input:source_notes",)
    assert field.evidence_refs == ("ref:input:source_notes",)
    assert trace.source == "SelectableRefSet.candidate_possible_inputs"


def test_out_of_scope_ref_is_not_selected() -> None:
    draft = _draft(
        refs=(
            _selectable_ref(
                "ref:input:external_notes",
                "selectable_input",
                "external_notes",
                worker_id="other_worker",
            ),
            _selectable_ref("ref:binding:source_evidence", "binding_target", "source_evidence"),
        ),
        metadata={
            "candidate_possible_inputs": ("external_notes",),
            "candidate_source_span_ids": ("s31",),
        },
    )
    field = next(field for field in draft.fields if field.field_id == "input_refs")

    assert field.value is None
    assert field.confidence == "blocked"
    assert draft.clarification_questions


def test_target_output_ref_is_not_treated_as_input() -> None:
    draft = _draft(
        refs=(
            _selectable_ref(
                "ref:target:source_notes",
                "target_output",
                "source_notes",
                ref_kind="required_output",
            ),
            _selectable_ref("ref:binding:source_evidence", "binding_target", "source_evidence"),
        ),
        metadata={
            "candidate_possible_inputs": ("source_notes",),
            "candidate_source_span_ids": ("s31",),
        },
    )
    field = next(field for field in draft.fields if field.field_id == "input_refs")

    assert field.value is None
    assert "ref:target:source_notes" not in field.evidence_refs
    assert "ref:target:source_notes" not in to_json_text(field)


def test_no_input_uses_explicit_none_with_policy_evidence() -> None:
    draft = _draft(
        refs=(
            _selectable_ref("ref:binding:source_evidence", "binding_target", "source_evidence"),
        ),
        metadata={"candidate_source_span_ids": ("s31",)},
    )
    field = next(field for field in draft.fields if field.field_id == "input_empty_semantics")
    trace = next(
        record for record in draft.trace if record.field_id == "input_empty_semantics"
    )

    assert isinstance(field.value, ExplicitNoneValue)
    assert field.evidence_refs == ("policy_ref:worker_delegation.input.explicit_none",)
    assert trace.evidence_refs == ("policy_ref:worker_delegation.input.explicit_none",)


def test_ambiguous_inputs_return_clarification() -> None:
    draft = _draft(
        refs=(
            _selectable_ref("ref:input:user_request", "selectable_input", "user_request"),
            _selectable_ref("ref:input:source_notes", "selectable_input", "source_notes"),
            _selectable_ref("ref:binding:source_evidence", "binding_target", "source_evidence"),
        ),
        metadata={"candidate_source_span_ids": ("s31",)},
    )
    field = next(field for field in draft.fields if field.field_id == "input_refs")

    assert field.value is None
    assert field.confidence == "blocked"
    assert any(question.field_id == "input_refs" for question in draft.clarification_questions)


def test_user_selected_input_refs_override_system_inference() -> None:
    draft = _draft_with_input(
        refs=(
            _selectable_ref("ref:input:user_request", "selectable_input", "user_request"),
            _selectable_ref(
                "ref:input:connectors",
                "selectable_input",
                "connectors_or_source_repositories",
            ),
            _selectable_ref("ref:binding:source_evidence", "binding_target", "source_evidence"),
        ),
        metadata={"candidate_source_span_ids": ("s31",)},
        user_input=UserRepairInput(
            input_mode="mixed",
            free_text="Gather approved source evidence",
            field_values=(
                UserRepairFieldValue(
                    "input_refs",
                    ("ref:input:connectors",),
                    "ui_selection",
                ),
            ),
        ),
    )
    field = next(field for field in draft.fields if field.field_id == "input_refs")
    trace = next(record for record in draft.trace if record.field_id == "input_refs")

    assert isinstance(field.value, SelectedInputRefsValue)
    assert field.value.ref_ids == ("ref:input:connectors",)
    assert field.evidence_refs == ("user_input:input_refs", "ref:input:connectors")
    assert trace.source == "user_input.field_values.input_refs"


def test_source_connector_responsibility_prefers_connector_input() -> None:
    draft = _draft(
        refs=(
            _selectable_ref("ref:input:user_request", "selectable_input", "user_request"),
            _selectable_ref(
                "ref:input:connectors",
                "selectable_input",
                "connectors_or_source_repositories",
            ),
            _selectable_ref("ref:binding:source_evidence", "binding_target", "source_evidence"),
        ),
        metadata={"candidate_source_span_ids": ("s31",)},
    )
    field = next(field for field in draft.fields if field.field_id == "input_refs")

    assert isinstance(field.value, SelectedInputRefsValue)
    assert field.value.ref_ids == ("ref:input:connectors",)


def test_duplicate_selectable_inputs_are_deduplicated_by_variable_name() -> None:
    draft = _draft(
        refs=(
            _selectable_ref(
                "ref:input:connectors",
                "selectable_input",
                "connectors_or_source_repositories",
            ),
            _selectable_ref(
                "ref:symbol:connectors",
                "selectable_input",
                "connectors_or_source_repositories",
            ),
            _selectable_ref("ref:binding:source_evidence", "binding_target", "source_evidence"),
        ),
        metadata={"candidate_source_span_ids": ("s31",)},
    )
    field = next(field for field in draft.fields if field.field_id == "input_refs")

    assert isinstance(field.value, SelectedInputRefsValue)
    assert field.value.ref_ids == ("ref:input:connectors",)
    assert [
        alternative.label
        for alternative in field.alternatives
        if alternative.label == "connectors_or_source_repositories"
    ] == ["connectors_or_source_repositories"]
