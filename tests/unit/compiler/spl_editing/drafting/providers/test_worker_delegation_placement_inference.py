from __future__ import annotations

from dataclasses import dataclass

from nl2spl.compiler.spl_editing.drafting.model import UserRepairInput
from nl2spl.compiler.spl_editing.drafting.providers.worker_delegation import (
    WorkerDelegationInferenceProvider,
)
from nl2spl.compiler.spl_editing.drafting.values import PlacementIntentValue
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


def _base_refs() -> tuple[SelectableRef, ...]:
    return (
        _ref("ref:input:user_request", "selectable_input", "user_request", kind="worker_input"),
        _ref("ref:binding:source_evidence", "binding_target", "source_evidence"),
        _ref("ref:placement:consumer", "placement_anchor", "consumer_step", kind="existing_step"),
        _ref("ref:placement:tail", "placement_anchor", "tail_step", kind="existing_step"),
    )


def _draft(*, metadata: dict):
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
            _base_refs(),
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


def _placement_field(draft):
    return next(field for field in draft.fields if field.field_id == "placement")


def test_first_consumer_before_placement_has_trace() -> None:
    draft = _draft(
        metadata={
            "candidate_source_span_ids": ("s31",),
            "first_consumer_ref_id": "ref:placement:consumer",
        }
    )
    field = _placement_field(draft)
    trace = next(record for record in draft.trace if record.field_id == "placement")

    assert isinstance(field.value, PlacementIntentValue)
    assert field.value.mode == "before"
    assert field.value.ref_id == "ref:placement:consumer"
    assert trace.source == "PlacementDraftingView.first_consumer"
    assert trace.evidence_refs == ("ref:placement:consumer",)


def test_input_unavailable_before_anchor_blocks_without_user_anchor_question() -> None:
    draft = _draft(
        metadata={
            "candidate_source_span_ids": ("s31",),
            "first_consumer_ref_id": "ref:placement:consumer",
            "input_unavailable_before_ref_ids": (
                "worker_input:worker_main:worker_main::user_request",
                "ref:input:user_request",
            ),
        }
    )
    field = _placement_field(draft)

    assert field.value is None
    assert field.confidence == "blocked"
    assert not any(question.field_id == "placement" for question in draft.clarification_questions)


def test_no_consumer_uses_append_fallback_with_policy_trace() -> None:
    draft = _draft(metadata={"candidate_source_span_ids": ("s31",)})
    field = _placement_field(draft)
    trace = next(record for record in draft.trace if record.field_id == "placement")

    assert isinstance(field.value, PlacementIntentValue)
    assert field.value.mode == "append"
    assert field.value.ref_id is None
    assert trace.source == "PlacementDraftingView.no_consumer_fallback"


def test_cross_flow_invalid_placement_is_blocked() -> None:
    draft = _draft(
        metadata={
            "candidate_source_span_ids": ("s31",),
            "first_consumer_ref_id": "ref:placement:consumer",
            "invalid_placement_anchor_ids": ("ref:placement:consumer",),
        }
    )

    assert _placement_field(draft).value is None


def test_api_owned_placement_anchor_is_blocked() -> None:
    draft = _draft(
        metadata={
            "candidate_source_span_ids": ("s31",),
            "first_consumer_ref_id": "ref:placement:consumer",
            "api_owned_placement_anchor_ids": ("ref:placement:consumer",),
        }
    )

    assert _placement_field(draft).value is None


def test_draft_preview_does_not_show_final_step_id() -> None:
    draft = _draft(
        metadata={
            "candidate_source_span_ids": ("s31",),
            "first_consumer_ref_id": "ref:placement:consumer",
        }
    )
    rendered = "\n".join(draft.draft_preview.field_summaries)

    assert "before first consumer" in rendered
    assert "ref:placement:consumer" not in rendered
    assert "step_id" not in rendered
