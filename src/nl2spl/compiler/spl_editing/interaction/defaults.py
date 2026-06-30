from nl2spl.compiler.spl_editing.interaction.model import RepairInteractionContractSpec
from nl2spl.compiler.spl_editing.interaction.providers.worker_delegation import (
    WorkerDelegationInteractionProvider,
)
from nl2spl.compiler.spl_editing.interaction.registry import RepairInteractionContractRegistry


def build_default_interaction_registry() -> RepairInteractionContractRegistry:
    registry = RepairInteractionContractRegistry()
    provider = WorkerDelegationInteractionProvider()
    registry.register_provider(provider.provider_id, provider)
    for contract_id in (
        "worker_delegation.define_child_worker.v1",
        "worker_delegation.keep_in_main_flow.v1",
    ):
        registry.register_contract(
            RepairInteractionContractSpec(
                contract_id=contract_id,
                contract_version="1",
                interaction_kind="dynamic",
                field_ids=(),
                additional_instruction_policy="preference_only",
                provider_id=provider.provider_id,
                normalizer_id="worker_delegation.normalizer.v1",
            )
        )
    return registry
