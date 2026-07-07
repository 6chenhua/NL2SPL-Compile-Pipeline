from __future__ import annotations

import inspect
from dataclasses import asdict, dataclass

from nl2spl.compiler.spl_editing.drafting.providers.worker_delegation import (
    WorkerDelegationInferenceProvider,
)
from nl2spl.compiler.spl_editing.drafting.views import (
    OutputDemandItemView,
    PlacementDraftingView,
    PlacementStepView,
    ProducerDraftingView,
    PromotionCandidateDraftView,
    SelectableRefsDraftingView,
    SelectableRefView,
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


def test_selectable_refs_view_returns_dtos_and_stable_ids_only() -> None:
    view = SelectableRefsDraftingView(_refset())

    refs = view.refs_by_role("selectable_input")

    assert refs == view.refs_for_role("selectable_input")
    assert all(isinstance(ref, SelectableRefView) for ref in refs)
    assert view.stable_ref_ids_for_role("selectable_input") == ("ref:input:user_request",)
    assert view.get_ref("ref:input:user_request").canonical_name == "user_request"
    assert view.has_ref("user_request") is False
    asdict(refs[0])


def test_placement_view_returns_typed_steps_without_raw_step_authority() -> None:
    view = PlacementDraftingView(SelectableRefsDraftingView(_refset()))

    steps = view.placement_steps()

    assert steps == (
        PlacementStepView(
            "ref:placement:step_1",
            "step_1",
            "Collect user request",
            "worker_main",
        ),
    )
    assert view.placement_anchor_ids() == ("ref:placement:step_1",)
    assert view.validate(mode="before", ref_id="ref:placement:step_1") is True
    assert view.validate(mode="before", ref_id="step_1") is False


def test_producer_view_distinguishes_output_demands_from_binding_targets() -> None:
    view = ProducerDraftingView("final_report", SelectableRefsDraftingView(_refset()))

    demands = view.output_demands()

    assert demands == (
        OutputDemandItemView(
            "ref:target:final_report",
            "final_report",
            "final_report",
            "required_output",
            worker_id="worker_main",
        ),
    )
    assert view.unresolved_required_outputs() == demands
    assert view.binding_target_ref_ids() == ("ref:binding:result",)
    assert view.is_target_output_ref("ref:target:final_report") is True


def test_worker_delegation_view_exposes_promotion_candidate_dto() -> None:
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

    candidate = view.promotion_candidate()

    assert candidate == PromotionCandidateDraftView(
        "cand_1",
        "worker_promotion:cand_1",
        "worker_main",
        "Gather source evidence",
        ("span_1",),
    )
    asdict(candidate)


def test_worker_delegation_provider_does_not_use_raw_ref_bypass_helpers() -> None:
    source = inspect.getsource(WorkerDelegationInferenceProvider)

    assert "getattr(" not in source
    assert "__dict__" not in source
    assert "vars(" not in source
