from __future__ import annotations

from dataclasses import dataclass

from nl2spl.compiler.spl_editing.drafting.model import UserRepairInput
from nl2spl.compiler.spl_editing.drafting.providers.worker_delegation import (
    WorkerDelegationInferenceProvider,
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


def _refset() -> SelectableRefSet:
    return SelectableRefSet(
        "set_1",
        "issue_1",
        "snapshot_1",
        "worker_main",
        (
            SelectableRef(
                "ref:input:user_request",
                "variable",
                "selectable_input",
                "user_request",
                "user_request",
                type_hint="text",
            ),
            SelectableRef(
                "ref:binding:source_evidence",
                "variable",
                "binding_target",
                "source_evidence",
                "source_evidence",
                type_hint="text",
            ),
        ),
        "worker_delegation",
    )


def _context(refset=None, metadata=None):
    provider = WorkerDelegationInferenceProvider()
    return provider.build_context(
        issue=_Issue(),
        target=_Target(),
        catalog_entry=_Entry(),
        option=_Option(),
        snapshot=object(),
        repair_context=_Context(
            metadata=metadata
            or {
                "candidate_task_summary": "Gather source evidence",
                "candidate_source_span_ids": ("span_1", "api:span_2"),
            }
        ),
        refset=refset if refset is not None else _refset(),
        subject=None,
    )


def test_provider_supports_only_define_child_worker_identity() -> None:
    provider = WorkerDelegationInferenceProvider()
    assert provider.supported_affordance_ids == {"worker_promotion.resolve_contract"}
    assert provider.supported_strategy_ids == {"worker_delegation.complete_closure.v2"}
    assert provider.supported_option_ids == {"define_child_worker"}
    assert provider.supported_patch_types == {"DefineChildWorkerClosure"}


def test_provider_infers_fields_with_confidence_evidence_and_trace() -> None:
    provider = WorkerDelegationInferenceProvider()
    draft = provider.infer(
        context=_context(),
        user_input=UserRepairInput(
            input_mode="free_text",
            free_text="Gather approved source evidence",
        ),
    )

    assert draft.clarification_questions == ()
    assert {field.field_id for field in draft.fields}.issuperset(
        {
            "child_task",
            "child_inputs",
            "child_output",
            "child_business_logic",
            "placement",
            "result_binding",
            "responsibility",
            "input_refs",
            "output_draft",
        }
    )
    assert all(field.confidence in {"high", "medium"} for field in draft.fields)
    assert all(field.evidence_refs for field in draft.fields)
    assert all(record.evidence_refs for record in draft.trace)
    assert {record.field_id for record in draft.trace} == {
        field.field_id for field in draft.fields
    }
    responsibility = next(field for field in draft.fields if field.field_id == "responsibility")
    responsibility_trace = next(
        record for record in draft.trace if record.field_id == "responsibility"
    )
    assert responsibility.evidence_refs == ("user_input:free_text",)
    assert responsibility_trace.evidence_refs == ("user_input:free_text",)
    assert "api:span_2" not in {
        evidence for record in draft.trace for evidence in record.evidence_refs
    }


def test_low_confidence_responsibility_returns_clarification() -> None:
    provider = WorkerDelegationInferenceProvider()
    draft = provider.infer(
        context=_context(metadata={"candidate_source_span_ids": ()}),
        user_input=UserRepairInput(input_mode="none"),
    )

    assert draft.clarification_questions
    assert any(field.confidence == "blocked" for field in draft.fields)


def test_provider_does_not_construct_ir_or_patch_payload() -> None:
    provider = WorkerDelegationInferenceProvider()
    draft = provider.infer(
        context=_context(),
        user_input=UserRepairInput(input_mode="free_text", free_text="Gather evidence"),
    )

    assert all("WorkerIR" not in type(field.value).__name__ for field in draft.fields)
    assert all("payload" not in field.field_id for field in draft.fields)
