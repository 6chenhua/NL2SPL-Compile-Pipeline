"""Typed SelectableRefSet projection for drafting providers."""

from __future__ import annotations

from dataclasses import dataclass

from nl2spl.compiler.spl_editing.drafting.views.types import SelectableRefView
from nl2spl.compiler.spl_editing.selectable_refs.model import SelectableRefSet


@dataclass(frozen=True)
class SelectableRefsDraftingView:
    refset: SelectableRefSet | None

    def refs_by_role(self, role: str) -> tuple[SelectableRefView, ...]:
        refs = self.refset.refs if self.refset is not None else ()
        return tuple(
            SelectableRefView.from_ref(ref)
            for ref in refs
            if ref.ref_role == role
        )

    def refs_for_role(self, role: str) -> tuple[SelectableRefView, ...]:
        return self.refs_by_role(role)

    def all_refs(self) -> tuple[SelectableRefView, ...]:
        refs = self.refset.refs if self.refset is not None else ()
        return tuple(SelectableRefView.from_ref(ref) for ref in refs)

    def refs_by_kind(self, kind: str) -> tuple[SelectableRefView, ...]:
        refs = self.refset.refs if self.refset is not None else ()
        return tuple(
            SelectableRefView.from_ref(ref)
            for ref in refs
            if ref.ref_kind == kind
        )

    def stable_ref_ids_for_role(self, role: str) -> tuple[str, ...]:
        return tuple(ref.ref_id for ref in self.refs_by_role(role))

    def has_ref(self, ref_id: str, *, role: str | None = None) -> bool:
        ref = self.get_ref(ref_id)
        if ref is None:
            return False
        return role is None or ref.ref_role == role

    def get_ref(self, ref_id: str) -> SelectableRefView | None:
        if self.refset is None:
            return None
        ref = self.refset.get_ref(ref_id)
        return SelectableRefView.from_ref(ref) if ref is not None else None
