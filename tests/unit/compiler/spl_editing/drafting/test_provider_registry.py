from __future__ import annotations

from dataclasses import dataclass

import pytest

from nl2spl.compiler.spl_editing.drafting.context import RepairDraftingContext
from nl2spl.compiler.spl_editing.drafting.model import DraftPreview, InferredRepairDraft
from nl2spl.compiler.spl_editing.drafting.registry import (
    DuplicateRepairInferenceProviderError,
    RepairInferenceProviderRegistry,
)


@dataclass
class _Provider:
    provider_id: str = "worker_provider"
    supported_affordance_ids: frozenset[str] = frozenset(
        {"worker_promotion.resolve_contract"}
    )
    supported_strategy_ids: frozenset[str] = frozenset(
        {"worker_delegation.complete_closure.v2"}
    )
    supported_option_ids: frozenset[str] = frozenset({"define_child_worker"})
    supported_patch_types: frozenset[str] = frozenset({"DefineChildWorkerClosure"})

    def build_context(self, **kwargs):
        return RepairDraftingContext(**kwargs)

    def infer(self, *, context, user_input):
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


def test_duplicate_provider_identity_rejected() -> None:
    registry = RepairInferenceProviderRegistry()
    registry.register(_Provider("first"))
    with pytest.raises(DuplicateRepairInferenceProviderError):
        registry.register(_Provider("second"))


def test_same_provider_can_support_multiple_compatible_patch_types() -> None:
    registry = RepairInferenceProviderRegistry()
    provider = _Provider(
        supported_patch_types=frozenset(
            {"DefineChildWorkerClosure", "CreateWorkerHandoffContract"}
        )
    )
    registry.register(provider)

    result = registry.resolve(
        affordance_id="worker_promotion.resolve_contract",
        strategy_id="worker_delegation.complete_closure.v2",
        option_id="define_child_worker",
        patch_type="CreateWorkerHandoffContract",
    )
    assert result.available is True
    assert result.provider is provider


def test_incompatible_patch_type_returns_unavailable() -> None:
    registry = RepairInferenceProviderRegistry()
    registry.register(_Provider())

    result = registry.resolve(
        affordance_id="worker_promotion.resolve_contract",
        strategy_id="worker_delegation.complete_closure.v2",
        option_id="define_child_worker",
        patch_type="OtherPatch",
    )

    assert result.available is False
    assert "incompatible patch_type: OtherPatch" in result.reasons


def test_no_provider_returns_unavailable_without_fallback() -> None:
    registry = RepairInferenceProviderRegistry()

    result = registry.resolve(
        affordance_id="worker_promotion.resolve_contract",
        strategy_id="worker_delegation.complete_closure.v2",
        option_id="define_child_worker",
        patch_type="DefineChildWorkerClosure",
    )

    assert result.available is False
    assert result.reasons == ("no provider",)


def test_diagnostic_kind_alone_cannot_resolve_provider() -> None:
    registry = RepairInferenceProviderRegistry()
    registry.register(_Provider())

    result = registry.resolve(
        affordance_id="type_or_contract_ambiguity",
        strategy_id="",
        option_id="",
        patch_type=None,
    )

    assert result.available is False

