from __future__ import annotations

from dataclasses import dataclass

from nl2spl.compiler.spl_editing.drafting.views import (
    ExceptionFlowDraftingView,
    PlacementDraftingView,
    ProducerDraftingView,
    RequestInputDraftingView,
    SelectableRefsDraftingView,
    WorkerDelegationDraftingView,
)
from nl2spl.compiler.spl_editing.selectable_refs.model import SelectableRef, SelectableRefSet


@dataclass(frozen=True)
class _Target:
    target_ref: str = "worker_promotion:cand_1"
    worker_id: str = "worker_main"
    canonical_name: str = "cand_1"


@dataclass(frozen=True)
class _Context:
    metadata: dict


def _refset() -> SelectableRefSet:
    return SelectableRefSet(
        set_id="set_1",
        issue_id="issue_1",
        snapshot_id="snap_1",
        worker_scope="worker_main",
        policy_id="worker_delegation",
        refs=(
            SelectableRef(
                "ref:input:user_request",
                "variable",
                "selectable_input",
                "user_request",
                "user_request",
                worker_id="worker_main",
            ),
            SelectableRef(
                "ref:placement:step_1",
                "existing_step",
                "placement_anchor",
                "step_1",
                "Collect user request",
                worker_id="worker_main",
            ),
            SelectableRef(
                "ref:binding:result",
                "variable",
                "binding_target",
                "result",
                "result",
                worker_id="worker_main",
            ),
            SelectableRef(
                "ref:target:final_report",
                "required_output",
                "target_output",
                "final_report",
                "final_report",
                worker_id="worker_main",
            ),
        ),
    )


def test_selectable_refs_view_returns_stable_ref_ids_only() -> None:
    view = SelectableRefsDraftingView(_refset())
    assert view.stable_ref_ids_for_role("selectable_input") == ("ref:input:user_request",)
    assert view.has_ref("user_request") is False


def test_placement_view_uses_ref_roles_not_raw_step_text() -> None:
    view = PlacementDraftingView(SelectableRefsDraftingView(_refset()))
    assert view.placement_anchor_ids() == ("ref:placement:step_1",)
    assert view.validate(mode="before", ref_id="ref:placement:step_1") is True
    assert view.validate(mode="before", ref_id="Collect user request") is False


def test_exception_flow_view_reads_structured_context_fact() -> None:
    view = ExceptionFlowDraftingView.from_target_and_context(
        _Target(target_ref="worker:main.exception_flow:exc_1", canonical_name="exc_1"),
        _Context(metadata={"condition_text": "API result is missing"}),
    )
    assert view.flow_id == "exc_1"
    assert view.condition_text == "API result is missing"


def test_producer_view_distinguishes_target_output_from_input_refs() -> None:
    view = ProducerDraftingView("final_report", SelectableRefsDraftingView(_refset()))
    assert view.candidate_input_ref_ids() == ("ref:input:user_request",)
    assert view.binding_target_ref_ids() == ("ref:binding:result",)
    assert view.is_target_output_ref("ref:target:final_report") is True


def test_worker_delegation_view_does_not_recompute_authority() -> None:
    view = WorkerDelegationDraftingView.from_parts(
        target=_Target(),
        context=_Context(
            metadata={
                "parent_worker_id": "worker_main",
                "candidate_task_summary": "Gather source evidence",
                "candidate_source_span_ids": ("span_1",),
            }
        ),
        refset=_refset(),
    )
    assert view.candidate_id == "cand_1"
    assert view.candidate_task_summary == "Gather source evidence"
    assert view.selectable_input_ref_ids() == ("ref:input:user_request",)
    assert not hasattr(view, "api_authority_decision")


def test_request_input_view_locates_value_target_gap() -> None:
    view = RequestInputDraftingView.from_target(
        _Target(target_ref="request_input:req_1", canonical_name="approval_window")
    )
    assert view.value_target_gap == "approval_window"
