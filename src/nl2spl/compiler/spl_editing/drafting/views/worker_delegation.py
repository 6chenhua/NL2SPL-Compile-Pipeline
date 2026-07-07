"""Worker-delegation facts exposed to drafting providers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from nl2spl.compiler.spl_editing.drafting.views.placement import PlacementDraftingView
from nl2spl.compiler.spl_editing.drafting.views.producer import ProducerDraftingView
from nl2spl.compiler.spl_editing.drafting.views.selectable_refs import (
    SelectableRefsDraftingView,
)
from nl2spl.compiler.spl_editing.drafting.views.types import PromotionCandidateDraftView
from nl2spl.compiler.spl_editing.selectable_refs.model import SelectableRefSet


class WorkerDelegationTargetViewSource(Protocol):
    target_ref: str
    worker_id: str
    canonical_name: str


class WorkerDelegationContextViewSource(Protocol):
    metadata: dict


@dataclass(frozen=True)
class WorkerDelegationDraftingView:
    target_ref: str
    candidate_id: str | None
    parent_worker_id: str | None
    candidate_task_summary: str | None
    candidate_task_candidates: tuple[str, ...]
    candidate_possible_inputs: tuple[str, ...]
    candidate_possible_outputs: tuple[str, ...]
    candidate_source_span_ids: tuple[str, ...]
    first_consumer_ref_id: str | None
    input_unavailable_before_ref_ids: tuple[str, ...]
    invalid_placement_anchor_ids: tuple[str, ...]
    api_owned_placement_anchor_ids: tuple[str, ...]
    selectable_refs: SelectableRefsDraftingView
    placement: PlacementDraftingView
    producer: ProducerDraftingView

    @classmethod
    def from_parts(
        cls,
        *,
        target: WorkerDelegationTargetViewSource,
        context: WorkerDelegationContextViewSource | None,
        refset: SelectableRefSet | None,
    ) -> WorkerDelegationDraftingView:
        metadata = context.metadata if context is not None else {}
        refs = SelectableRefsDraftingView(refset)
        return cls(
            target_ref=target.target_ref,
            candidate_id=target.canonical_name,
            parent_worker_id=metadata.get("parent_worker_id") or target.worker_id,
            candidate_task_summary=metadata.get("candidate_task_summary"),
            candidate_task_candidates=_metadata_string_tuple(
                metadata,
                "candidate_task_candidates",
            ),
            candidate_possible_inputs=_metadata_string_tuple(
                metadata,
                "candidate_possible_inputs",
            ),
            candidate_possible_outputs=_metadata_string_tuple(
                metadata,
                "candidate_possible_outputs",
            ),
            candidate_source_span_ids=_metadata_string_tuple(
                metadata,
                "candidate_source_span_ids",
            ),
            first_consumer_ref_id=_metadata_string(metadata, "first_consumer_ref_id"),
            input_unavailable_before_ref_ids=_metadata_string_tuple(
                metadata,
                "input_unavailable_before_ref_ids",
            ),
            invalid_placement_anchor_ids=_metadata_string_tuple(
                metadata,
                "invalid_placement_anchor_ids",
            ),
            api_owned_placement_anchor_ids=_metadata_string_tuple(
                metadata,
                "api_owned_placement_anchor_ids",
            ),
            selectable_refs=refs,
            placement=PlacementDraftingView(refs),
            producer=ProducerDraftingView(target.canonical_name, refs),
        )

    def promotion_candidate(self) -> PromotionCandidateDraftView:
        return PromotionCandidateDraftView(
            candidate_id=self.candidate_id,
            target_ref=self.target_ref,
            parent_worker_id=self.parent_worker_id,
            task_text=self.candidate_task_summary,
            source_span_ids=self.candidate_source_span_ids,
            task_candidates=self.candidate_task_candidates,
            possible_inputs=self.candidate_possible_inputs,
            possible_outputs=self.candidate_possible_outputs,
        )

    def selectable_input_ref_ids(self) -> tuple[str, ...]:
        return self.selectable_refs.stable_ref_ids_for_role("selectable_input")

    def binding_target_ref_ids(self) -> tuple[str, ...]:
        return self.selectable_refs.stable_ref_ids_for_role("binding_target")


def _metadata_string_tuple(metadata: dict, key: str) -> tuple[str, ...]:
    value = metadata.get(key)
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, tuple) and all(isinstance(item, str) for item in value):
        return value
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return tuple(value)
    return ()


def _metadata_string(metadata: dict, key: str) -> str | None:
    value = metadata.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None
