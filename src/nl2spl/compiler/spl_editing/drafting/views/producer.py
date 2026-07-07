"""Producer facts exposed to drafting providers."""

from __future__ import annotations

from dataclasses import dataclass

from nl2spl.compiler.spl_editing.drafting.views.selectable_refs import (
    SelectableRefsDraftingView,
)
from nl2spl.compiler.spl_editing.drafting.views.types import (
    OutputDemandItemView,
    SelectableRefView,
)


@dataclass(frozen=True)
class ProducerDraftingView:
    target_output_name: str | None
    selectable_refs: SelectableRefsDraftingView

    def candidate_input_ref_ids(self) -> tuple[str, ...]:
        return self.selectable_refs.stable_ref_ids_for_role("selectable_input")

    def candidate_input_refs(self) -> tuple[SelectableRefView, ...]:
        return self.selectable_refs.refs_by_role("selectable_input")

    def binding_target_ref_ids(self) -> tuple[str, ...]:
        return self.selectable_refs.stable_ref_ids_for_role("binding_target")

    def binding_target_refs(self) -> tuple[SelectableRefView, ...]:
        return self.selectable_refs.refs_by_role("binding_target")

    def output_demands(self) -> tuple[OutputDemandItemView, ...]:
        return tuple(
            OutputDemandItemView.from_ref_view(ref)
            for ref in self.selectable_refs.refs_by_role("target_output")
        )

    def unresolved_required_outputs(self) -> tuple[OutputDemandItemView, ...]:
        return tuple(
            demand
            for demand in self.output_demands()
            if demand.demand_kind == "required_output"
        )

    def is_target_output_ref(self, ref_id: str) -> bool:
        ref = self.selectable_refs.get_ref(ref_id)
        return ref is not None and ref.ref_role == "target_output"
