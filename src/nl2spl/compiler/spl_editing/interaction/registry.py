"""Static interaction-contract and dynamic-provider registries."""

from __future__ import annotations

from nl2spl.compiler.spl_editing.interaction.errors import RepairInteractionNotFoundError
from nl2spl.compiler.spl_editing.interaction.model import RepairInteractionContractSpec


class RepairInteractionContractRegistry:
    def __init__(self) -> None:
        self._contracts: dict[str, RepairInteractionContractSpec] = {}
        self._providers: dict[str, object] = {}

    def register_contract(self, spec: RepairInteractionContractSpec) -> None:
        if spec.contract_id in self._contracts:
            raise ValueError(f"Duplicate interaction contract '{spec.contract_id}'")
        self._contracts[spec.contract_id] = spec

    def register_provider(self, provider_id: str, provider: object) -> None:
        if provider_id in self._providers:
            raise ValueError(f"Duplicate interaction provider '{provider_id}'")
        self._providers[provider_id] = provider

    def resolve(self, contract_id: str):
        try:
            spec = self._contracts[contract_id]
            provider = self._providers[spec.provider_id]
        except KeyError as exc:
            raise RepairInteractionNotFoundError(contract_id) from exc
        return spec, provider

    def has(self, contract_id: str) -> bool:
        return contract_id in self._contracts
