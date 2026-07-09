"""Declaration authority resolution for Stage 6 resource extraction.

Provides the integration layer between ``DeclarationAuthoritySidecar`` /
``DeclarationAuthorityRegistry`` and the Stage 6 extractor so that
``_merge_contract_variables()`` and the SymbolTable write path can
query authority metadata.

S6V2.5: MVP sidecar approach.  No IR dataclass churn.
"""

from __future__ import annotations

from nl2spl.ir.variable_declaration_authority_ir import (
    DeclarationAuthority,
    DeclarationAuthorityRegistry,
    DeclarationAuthoritySidecar,
    is_admissible_by_default,
    is_conditionally_admissible,
    is_inadmissible,
    sidecar_from_candidate_io,
    sidecar_from_worker_contract_field,
)


def build_authority_registry_from_worker_spec(
    worker_spec: object,  # WorkerSpecIR — avoid circular import
) -> DeclarationAuthorityRegistry:
    """Build a ``DeclarationAuthorityRegistry`` from a ``WorkerSpecIR``.

    Registers sidecars for every field in ``input_contract`` and
    ``output_contract``.  Fields without evidence (empty source_span_ids,
    no contract_demand_id) default to ``llm_candidate_io`` / inadmissible.
    """
    registry = DeclarationAuthorityRegistry()
    input_contract: list[object] = getattr(worker_spec, "input_contract", []) or []
    output_contract: list[object] = getattr(worker_spec, "output_contract", []) or []
    registry.register_from_contract_fields(list(input_contract) + list(output_contract))
    return registry


def filter_admissible_fields(
    fields: list[object],  # list[ContractFieldIR]
    registry: DeclarationAuthorityRegistry | None = None,
) -> list[object]:
    """Filter a list of ContractFieldIR-like objects, keeping only those
    whose declaration authority is admissible.

    If *registry* is None, builds one on the fly from the fields themselves.
    """
    if registry is None:
        registry = DeclarationAuthorityRegistry()
        registry.register_from_contract_fields(fields)

    return [f for f in fields if registry.is_admissible(getattr(f, "name", ""))]


__all__ = [
    "DeclarationAuthority",
    "DeclarationAuthorityRegistry",
    "DeclarationAuthoritySidecar",
    "build_authority_registry_from_worker_spec",
    "filter_admissible_fields",
    "is_admissible_by_default",
    "is_conditionally_admissible",
    "is_inadmissible",
    "sidecar_from_candidate_io",
    "sidecar_from_worker_contract_field",
]
