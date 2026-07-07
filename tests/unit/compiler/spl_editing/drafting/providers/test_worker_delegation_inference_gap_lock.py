from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from nl2spl.compiler.spl_editing.drafting.model import UserRepairInput
from nl2spl.compiler.spl_editing.drafting.providers.worker_delegation import (
    WorkerDelegationInferenceProvider,
)
from nl2spl.compiler.spl_editing.drafting.values import (
    PlacementIntentValue,
    ResultBindingValue,
    SelectedInputRefsValue,
)
from nl2spl.compiler.spl_editing.selectable_refs.model import SelectableRef, SelectableRefSet

RD7_FREEZE = Path("artifacts/reviews/repair_drafting/RD7_freeze")


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


def _refset(*, include_user_request: bool = True) -> SelectableRefSet:
    refs = []
    if include_user_request:
        refs.append(
            SelectableRef(
                "ref:input:user_request",
                "variable",
                "selectable_input",
                "user_request",
                "user_request",
                type_hint="text",
            )
        )
    refs.extend(
        (
            SelectableRef(
                "ref:input:source_notes",
                "variable",
                "selectable_input",
                "source_notes",
                "source_notes",
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
        )
    )
    return SelectableRefSet(
        "set_1",
        "issue_1",
        "snapshot_1",
        "worker_main",
        tuple(refs),
        "worker_delegation",
    )


def _draft(*, metadata: dict | None = None, include_user_request: bool = True):
    provider = WorkerDelegationInferenceProvider()
    context = provider.build_context(
        issue=_Issue(),
        target=_Target(),
        catalog_entry=_Entry(),
        option=_Option(),
        snapshot=object(),
        repair_context=_Context(
            metadata=metadata
            or {
                "candidate_task_summary": "Gather source evidence",
                "candidate_possible_inputs": ("user_request",),
                "candidate_source_span_ids": ("span_1", "api:span_2"),
            }
        ),
        refset=_refset(include_user_request=include_user_request),
        subject=None,
    )
    return provider.infer(
        context=context,
        user_input=UserRepairInput(
            input_mode="free_text",
            free_text="Gather approved source evidence",
        ),
    )


def test_wdi0_release1_freeze_prerequisites_are_replayable() -> None:
    manifest = json.loads((RD7_FREEZE / "manifest.json").read_text(encoding="utf-8"))
    bundle = RD7_FREEZE / "worker_delegation_draft_flow"

    assert manifest["status"] == "pass"
    assert manifest["verdict"] == "approved"
    assert "Worker Delegation v2 E2E: PASS" in manifest["checks"]["demo_e2e"]
    for name in (
        "user_input.json",
        "inferred_draft.json",
        "draft_preview.txt",
        "materialized_preview.json",
        "verification_result.json",
        "rendered_spl_after.txt",
        "diagnostic_diff.json",
    ):
        assert (bundle / name).exists()


def test_wdi0_current_draft_first_happy_path_has_field_evidence_and_trace() -> None:
    draft = _draft()
    fields = {field.field_id: field for field in draft.fields}
    trace = {record.field_id: record for record in draft.trace}

    assert draft.clarification_questions == ()
    assert fields.keys() == trace.keys()
    assert all(field.evidence_refs for field in fields.values())
    assert all(record.evidence_refs for record in trace.values())
    assert fields["responsibility"].evidence_refs == ("user_input:free_text",)
    assert trace["responsibility"].evidence_refs == ("user_input:free_text",)


def test_wdi0_current_input_output_placement_and_binding_behavior_is_locked() -> None:
    draft = _draft()
    fields = {field.field_id: field for field in draft.fields}
    report = Path(
        "artifacts/reviews/worker_delegation_inference/WDI0/review_report.md"
    ).read_text(encoding="utf-8")

    assert isinstance(fields["input_refs"].value, SelectedInputRefsValue)
    assert fields["input_refs"].value.ref_ids == ("ref:input:user_request",)
    assert isinstance(fields["placement"].value, PlacementIntentValue)
    assert fields["placement"].value.mode == "append"
    assert isinstance(fields["result_binding"].value, ResultBindingValue)
    assert fields["result_binding"].value.parent_ref_id == "ref:binding:source_evidence"
    assert fields["result_binding"].value.create_parent_local_temporary is False
    assert "Current draft preview exposes internal selectable ref ids" in report
    assert "Current output draft derives local id from candidate id" in report


def test_wdi0_current_low_confidence_path_requires_clarification() -> None:
    provider = WorkerDelegationInferenceProvider()
    context = provider.build_context(
        issue=_Issue(),
        target=_Target(),
        catalog_entry=_Entry(),
        option=_Option(),
        snapshot=object(),
        repair_context=_Context(metadata={"candidate_source_span_ids": ()}),
        refset=_refset(),
        subject=None,
    )

    draft = provider.infer(
        context=context,
        user_input=UserRepairInput(input_mode="none"),
    )

    assert any(question.field_id == "responsibility" for question in draft.clarification_questions)
    assert any(
        field.field_id == "responsibility" and field.confidence == "blocked"
        for field in draft.fields
    )


def test_wdi0_report_records_required_output_gap_baseline() -> None:
    report = Path(
        "artifacts/reviews/worker_delegation_inference/WDI0/review_report.md"
    ).read_text(encoding="utf-8")

    assert "required-output gap protection is not yet modeled" in report
