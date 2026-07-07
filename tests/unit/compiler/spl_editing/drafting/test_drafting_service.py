from __future__ import annotations

from dataclasses import dataclass

from nl2spl.compiler.spl_editing.drafting.context import RepairDraftingContext
from nl2spl.compiler.spl_editing.drafting.model import (
    DraftPreview,
    InferredRepairDraft,
    UserRepairInput,
)
from nl2spl.compiler.spl_editing.drafting.registry import RepairInferenceProviderRegistry
from nl2spl.compiler.spl_editing.drafting.service import RepairDraftingService
from nl2spl.compiler.spl_editing.drafting.store import RepairDraftStore


@dataclass(frozen=True)
class _CatalogEntry:
    affordance_id: str = "worker_promotion.resolve_contract"


@dataclass(frozen=True)
class _Option:
    strategy_id: str = "worker_delegation.complete_closure.v2"
    option_id: str = "define_child_worker"
    execution_patch_types: tuple[str, ...] = ("DefineChildWorkerClosure",)


@dataclass(frozen=True)
class _Snapshot:
    snapshot_id: str = "snapshot_1"
    overlay_version: int = 0


class _Provider:
    provider_id = "worker_provider"
    supported_affordance_ids = frozenset({"worker_promotion.resolve_contract"})
    supported_strategy_ids = frozenset({"worker_delegation.complete_closure.v2"})
    supported_option_ids = frozenset({"define_child_worker"})
    supported_patch_types = frozenset({"DefineChildWorkerClosure"})

    def __init__(self) -> None:
        self.infer_calls = 0

    def build_context(self, **kwargs):
        kwargs.pop("repair_context", None)
        kwargs.pop("refset", None)
        kwargs.pop("subject", None)
        return RepairDraftingContext(**kwargs)

    def infer(self, *, context, user_input):
        self.infer_calls += 1
        assert isinstance(user_input, UserRepairInput)
        return InferredRepairDraft(
            "draft_1",
            "issue_1",
            "worker_promotion.resolve_contract",
            "worker_delegation.complete_closure.v2",
            "define_child_worker",
            (),
            (),
            (),
            DraftPreview("Create child worker", "Gather evidence."),
        )


def test_service_creates_and_stores_draft_without_admission() -> None:
    registry = RepairInferenceProviderRegistry()
    provider = _Provider()
    registry.register(provider)
    store = RepairDraftStore()
    service = RepairDraftingService(registry=registry, store=store)

    result = service.create_draft(
        session_id="session_1",
        issue=object(),
        target=object(),
        catalog_entry=_CatalogEntry(),
        option=_Option(),
        snapshot=_Snapshot(),
        user_input=UserRepairInput(input_mode="free_text", free_text="Gather evidence"),
    )

    assert result.status == "draft_created"
    assert result.stored_draft is not None
    assert result.stored_draft.session_id == "session_1"
    assert provider.infer_calls == 1


def test_service_no_provider_returns_unavailable_without_calling_model() -> None:
    service = RepairDraftingService(
        registry=RepairInferenceProviderRegistry(),
        store=RepairDraftStore(),
    )

    result = service.create_draft(
        session_id="session_1",
        issue=object(),
        target=object(),
        catalog_entry=_CatalogEntry(),
        option=_Option(),
        snapshot=_Snapshot(),
        user_input=None,
    )

    assert result.status == "drafting_unavailable"
    assert result.draft is None
    assert result.stored_draft is None
    assert result.reasons == ("no provider",)
