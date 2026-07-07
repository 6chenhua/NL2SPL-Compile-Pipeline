"""Stable DTOs exposed by drafting read-only views."""

from __future__ import annotations

from dataclasses import dataclass

from nl2spl.compiler.spl_editing.selectable_refs.model import SelectableRef


@dataclass(frozen=True)
class SelectableRefView:
    ref_id: str
    ref_kind: str
    ref_role: str
    canonical_name: str
    display_label: str
    worker_id: str | None = None
    type_hint: str | None = None
    scope: str | None = None
    source_artifact_ref: str | None = None
    scope_path: tuple[str, ...] = ()
    selectable_for: tuple[str, ...] = ()

    @classmethod
    def from_ref(cls, ref: SelectableRef) -> SelectableRefView:
        return cls(
            ref_id=ref.ref_id,
            ref_kind=ref.ref_kind,
            ref_role=ref.ref_role,
            canonical_name=ref.canonical_name,
            display_label=ref.display_label,
            worker_id=ref.worker_id,
            type_hint=ref.type_hint,
            scope=ref.scope,
            source_artifact_ref=ref.source_artifact_ref,
            scope_path=tuple(ref.scope_path),
            selectable_for=tuple(ref.selectable_for),
        )


@dataclass(frozen=True)
class PlacementStepView:
    ref_id: str
    canonical_name: str
    display_label: str
    worker_id: str | None
    source_artifact_ref: str | None = None
    scope_path: tuple[str, ...] = ()

    @classmethod
    def from_ref_view(cls, ref: SelectableRefView) -> PlacementStepView:
        return cls(
            ref_id=ref.ref_id,
            canonical_name=ref.canonical_name,
            display_label=ref.display_label,
            worker_id=ref.worker_id,
            source_artifact_ref=ref.source_artifact_ref,
            scope_path=ref.scope_path,
        )


@dataclass(frozen=True)
class OutputDemandItemView:
    ref_id: str
    canonical_name: str
    display_label: str
    demand_kind: str
    worker_id: str | None = None
    type_hint: str | None = None
    source_artifact_ref: str | None = None

    @classmethod
    def from_ref_view(cls, ref: SelectableRefView) -> OutputDemandItemView:
        return cls(
            ref_id=ref.ref_id,
            canonical_name=ref.canonical_name,
            display_label=ref.display_label,
            demand_kind=ref.ref_kind,
            worker_id=ref.worker_id,
            type_hint=ref.type_hint,
            source_artifact_ref=ref.source_artifact_ref,
        )


@dataclass(frozen=True)
class PromotionCandidateDraftView:
    candidate_id: str | None
    target_ref: str
    parent_worker_id: str | None
    task_text: str | None
    source_span_ids: tuple[str, ...]
    task_candidates: tuple[str, ...] = ()
    possible_inputs: tuple[str, ...] = ()
    possible_outputs: tuple[str, ...] = ()
