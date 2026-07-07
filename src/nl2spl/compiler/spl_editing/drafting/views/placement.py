"""Placement facts exposed to drafting providers."""

from __future__ import annotations

from dataclasses import dataclass

from nl2spl.compiler.spl_editing.drafting.views.selectable_refs import (
    SelectableRefsDraftingView,
)
from nl2spl.compiler.spl_editing.drafting.views.types import PlacementStepView


@dataclass(frozen=True)
class PlacementDraftingView:
    selectable_refs: SelectableRefsDraftingView

    def placement_steps(self) -> tuple[PlacementStepView, ...]:
        return tuple(
            PlacementStepView.from_ref_view(ref)
            for ref in self.selectable_refs.refs_by_role("placement_anchor")
        )

    def placement_anchor_ids(self) -> tuple[str, ...]:
        return tuple(step.ref_id for step in self.placement_steps())

    def default_mode(self) -> str:
        return "append"

    def validate(self, *, mode: str, ref_id: str | None = None) -> bool:
        if mode == "append":
            return ref_id is None
        if mode in {"before", "after"}:
            return ref_id is not None and self.selectable_refs.has_ref(
                ref_id,
                role="placement_anchor",
            )
        return False
