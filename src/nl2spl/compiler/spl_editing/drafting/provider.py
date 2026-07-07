"""Provider protocol for strategy-specific repair draft inference."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from nl2spl.compiler.spl_editing.drafting.context import RepairDraftingContext
from nl2spl.compiler.spl_editing.drafting.model import (
    InferredRepairDraft,
    UserRepairInput,
)


@dataclass(frozen=True)
class RepairInferenceProviderIdentity:
    affordance_id: str
    strategy_id: str
    option_id: str


class RepairInferenceProvider(Protocol):
    provider_id: str
    supported_affordance_ids: frozenset[str]
    supported_strategy_ids: frozenset[str]
    supported_option_ids: frozenset[str]
    supported_patch_types: frozenset[str]

    def build_context(
        self,
        *,
        issue,
        target,
        catalog_entry,
        option,
        snapshot,
        repair_context=None,
        refset=None,
        subject=None,
    ) -> RepairDraftingContext:
        ...

    def infer(
        self,
        *,
        context: RepairDraftingContext,
        user_input: UserRepairInput | None,
    ) -> InferredRepairDraft:
        ...
