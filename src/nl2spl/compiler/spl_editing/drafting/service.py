"""Service shell for repair draft inference."""

from __future__ import annotations

from dataclasses import dataclass

from nl2spl.compiler.spl_editing.drafting.model import (
    InferredRepairDraft,
    StoredRepairDraft,
    UserRepairInput,
)
from nl2spl.compiler.spl_editing.drafting.registry import (
    RepairInferenceProviderRegistry,
)
from nl2spl.compiler.spl_editing.drafting.store import RepairDraftStore


@dataclass(frozen=True)
class RepairDraftingServiceResult:
    status: str
    draft: InferredRepairDraft | None = None
    stored_draft: StoredRepairDraft | None = None
    reasons: tuple[str, ...] = ()


class RepairDraftingService:
    """Resolve provider, infer draft, and store ephemeral draft state."""

    def __init__(
        self,
        *,
        registry: RepairInferenceProviderRegistry,
        store: RepairDraftStore,
    ) -> None:
        self._registry = registry
        self._store = store

    def create_draft(
        self,
        *,
        session_id: str,
        issue,
        target,
        catalog_entry,
        option,
        snapshot,
        user_input: UserRepairInput | None,
        repair_context=None,
        refset=None,
        subject=None,
    ) -> RepairDraftingServiceResult:
        patch_type = _single_patch_type(option)
        resolution = self._registry.resolve(
            affordance_id=catalog_entry.affordance_id,
            strategy_id=option.strategy_id,
            option_id=option.option_id,
            patch_type=patch_type,
        )
        if not resolution.available or resolution.provider is None:
            return RepairDraftingServiceResult(
                status="drafting_unavailable",
                reasons=resolution.reasons,
            )
        provider = resolution.provider
        context = provider.build_context(
            issue=issue,
            target=target,
            catalog_entry=catalog_entry,
            option=option,
            snapshot=snapshot,
            repair_context=repair_context,
            refset=refset,
            subject=subject,
        )
        draft = provider.infer(context=context, user_input=user_input)
        stored = self._store.put(
            draft,
            session_id=session_id,
            artifact_snapshot_id=snapshot.snapshot_id,
            overlay_version=snapshot.overlay_version,
        )
        return RepairDraftingServiceResult("draft_created", draft, stored, ())


def _single_patch_type(option) -> str | None:
    patch_types = tuple(getattr(option, "execution_patch_types", ()) or ())
    if len(patch_types) == 1:
        return patch_types[0]
    return None
