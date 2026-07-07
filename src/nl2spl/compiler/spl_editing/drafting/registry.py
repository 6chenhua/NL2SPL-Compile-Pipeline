"""Registry for repair inference providers."""

from __future__ import annotations

from dataclasses import dataclass

from nl2spl.compiler.spl_editing.drafting.errors import RepairDraftingError
from nl2spl.compiler.spl_editing.drafting.provider import (
    RepairInferenceProvider,
    RepairInferenceProviderIdentity,
)


@dataclass(frozen=True)
class ProviderResolution:
    provider: RepairInferenceProvider | None
    status: str
    reasons: tuple[str, ...] = ()

    @property
    def available(self) -> bool:
        return self.provider is not None and self.status == "available"


class DuplicateRepairInferenceProviderError(RepairDraftingError):
    """Raised when two providers claim the same semantic identity."""


class RepairInferenceProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[RepairInferenceProviderIdentity, RepairInferenceProvider] = {}

    def register(self, provider: RepairInferenceProvider) -> None:
        for identity in self._identities(provider):
            if identity in self._providers:
                existing = self._providers[identity]
                raise DuplicateRepairInferenceProviderError(
                    f"Provider identity {identity} already registered by {existing.provider_id}"
                )
            self._providers[identity] = provider

    def resolve(
        self,
        *,
        affordance_id: str,
        strategy_id: str,
        option_id: str,
        patch_type: str | None = None,
    ) -> ProviderResolution:
        identity = RepairInferenceProviderIdentity(affordance_id, strategy_id, option_id)
        provider = self._providers.get(identity)
        if provider is None:
            return ProviderResolution(None, "drafting_unavailable", ("no provider",))
        if patch_type is not None and patch_type not in provider.supported_patch_types:
            return ProviderResolution(
                None,
                "drafting_unavailable",
                (f"incompatible patch_type: {patch_type}",),
            )
        return ProviderResolution(provider, "available", ())

    def list_identities(self) -> tuple[RepairInferenceProviderIdentity, ...]:
        return tuple(sorted(self._providers, key=str))

    @staticmethod
    def _identities(
        provider: RepairInferenceProvider,
    ) -> tuple[RepairInferenceProviderIdentity, ...]:
        identities = []
        for affordance_id in provider.supported_affordance_ids:
            for strategy_id in provider.supported_strategy_ids:
                for option_id in provider.supported_option_ids:
                    identities.append(
                        RepairInferenceProviderIdentity(
                            affordance_id=affordance_id,
                            strategy_id=strategy_id,
                            option_id=option_id,
                        )
                    )
        if not identities:
            raise ValueError("Provider must declare at least one semantic identity")
        return tuple(identities)

