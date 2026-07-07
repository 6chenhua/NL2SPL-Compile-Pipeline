"""Typed read-only views for repair drafting providers."""

from nl2spl.compiler.spl_editing.drafting.views.base import DraftingViewSource
from nl2spl.compiler.spl_editing.drafting.views.exception_flow import ExceptionFlowDraftingView
from nl2spl.compiler.spl_editing.drafting.views.placement import PlacementDraftingView
from nl2spl.compiler.spl_editing.drafting.views.producer import ProducerDraftingView
from nl2spl.compiler.spl_editing.drafting.views.request_input import RequestInputDraftingView
from nl2spl.compiler.spl_editing.drafting.views.selectable_refs import SelectableRefsDraftingView
from nl2spl.compiler.spl_editing.drafting.views.types import (
    OutputDemandItemView,
    PlacementStepView,
    PromotionCandidateDraftView,
    SelectableRefView,
)
from nl2spl.compiler.spl_editing.drafting.views.worker_delegation import (
    WorkerDelegationDraftingView,
)

__all__ = [
    "DraftingViewSource",
    "ExceptionFlowDraftingView",
    "PlacementDraftingView",
    "ProducerDraftingView",
    "RequestInputDraftingView",
    "SelectableRefsDraftingView",
    "SelectableRefView",
    "PlacementStepView",
    "OutputDemandItemView",
    "PromotionCandidateDraftView",
    "WorkerDelegationDraftingView",
]
