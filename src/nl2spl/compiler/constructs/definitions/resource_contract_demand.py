"""Default ConstructIRS definitions for resource contract demand."""

from __future__ import annotations

from nl2spl.compiler.constructs.registry import SPLConstructRegistry
from nl2spl.compiler.constructs.spec import ConstructIRS, SlotSpec


def register(registry: SPLConstructRegistry) -> None:

# -- RESOURCE_CONTRACT_DEMAND -----------------------------------------
    registry.register(ConstructIRS(
        construct_type="RESOURCE_CONTRACT_DEMAND",
        existence_policy="source_signal_required",
        source_signals=["input_contract", "output_contract", "resource_contract"],
        partial_rendering_allowed=True,
        description=(
            "A source-demanded resource contract (input or output). "
            "The demand itself is satisfied when a Stage 6 resource_contracts "
            "entry materializes it with a matching demand_id."
        ),
        slots=[
            SlotSpec(
                slot_name="materialization",
                syntax_required=True,
                required_for_partial=True,
                required_for_complete=True,
                evidence_kinds=["resource_contract_binding"],
                missing_diagnostic="missing_resource_contract",
                notes=(
                    "The demand must have at least one "
                    "ResourceContractBindingIR with a matching demand_id."
                ),
            ),
            SlotSpec(
                slot_name="resource_registry",
                syntax_required=False,
                required_for_partial=False,
                required_for_complete=True,
                evidence_kinds=["resource_contract_field"],
                missing_diagnostic="resource_kind_mismatch",
                notes=(
                    "Every ResourceContractBindingIR must point to a "
                    "materialized resource in the matching registry "
                    "collection (variables/files/apis/types)."
                ),
            ),
            SlotSpec(
                slot_name="producer",
                syntax_required=False,
                required_for_partial=False,
                required_for_complete=True,
                evidence_kinds=["producer_index"],
                missing_diagnostic="missing_output_producer",
                notes=(
                    "Required output demands need a renderable producer "
                    "of the same resource name and resource kind. "
                    "Declarations alone do not count as producers."
                ),
            ),
        ],
    ))
