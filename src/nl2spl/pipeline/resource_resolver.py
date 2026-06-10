"""ResourceResolver — unified variable/file resource lookup.

Bridges ``ResourceRegistryIR`` and ``ResourceContractBindingIR`` so
downstream stages (assembler, IRS, ProducerIndex, feedback) can resolve
a resource name to its kind, data type, scope, and demand binding.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from nl2spl.ir.resource_contract_ir import (
    ResourceContractBindingIR,
    ResourceKind,
    ResourceScopeKind,
)
from nl2spl.ir.resource_registry_ir import ResourceRegistryIR


@dataclass(frozen=True)
class ResolvedResourceRef:
    """Result of a successful resource lookup.

    Attributes:
        name: Resource name as declared in the registry.
        resource_kind: ``variable``, ``file``, ``api``, or ``type``.
        data_type: Data type from the registry.
        scope_kind: The scope this resource lives in.
        scope_id: Worker/handoff ID when scoped.
        binding: The demand binding that backs this resource, if any.
    """

    name: str
    resource_kind: ResourceKind
    data_type: str
    scope_kind: ResourceScopeKind
    scope_id: str | None = None
    binding: ResourceContractBindingIR | None = None


def resolve_resource_ref(
    name: str,
    resources: ResourceRegistryIR,
    bindings: Sequence[ResourceContractBindingIR] = (),
    scope_kind: ResourceScopeKind = "global",
    scope_id: str | None = None,
) -> ResolvedResourceRef | None:
    """Resolve a resource name to its kind and provenance.

    Priority:
    1. Binding matching ``name`` and the requested scope.
    2. Global binding matching ``name``.
    3. File spec with matching name.
    4. Variable spec with matching name.

    Bindings are attached when the resolved resource has a matching demand.

    Args:
        name: Resource name to resolve.
        resources: The resource registry to search.
        bindings: Optional contract bindings for demand provenance.
        scope_kind: Hint for which scope this lookup originates from.
        scope_id: Worker/handoff ID when scoped.

    Returns:
        ``ResolvedResourceRef`` or ``None`` if not found.
    """
    binding = _find_binding(name, bindings, scope_kind, scope_id)

    for fs in resources.files:
        if fs.name == name:
            return ResolvedResourceRef(
                name=name,
                resource_kind="file",
                data_type=fs.data_type,
                scope_kind=scope_kind,
                scope_id=scope_id,
                binding=binding,
            )

    for vs in resources.variables:
        if vs.name == name:
            return ResolvedResourceRef(
                name=name,
                resource_kind="variable",
                data_type=vs.data_type,
                scope_kind=scope_kind,
                scope_id=scope_id,
                binding=binding,
            )

    return None


def _find_binding(
    name: str,
    bindings: Sequence[ResourceContractBindingIR],
    scope_kind: ResourceScopeKind,
    scope_id: str | None,
) -> ResourceContractBindingIR | None:
    exact: list[ResourceContractBindingIR] = []
    global_matches: list[ResourceContractBindingIR] = []
    name_matches: list[ResourceContractBindingIR] = []
    for binding in bindings:
        if binding.resource_name != name:
            continue
        name_matches.append(binding)
        if binding.scope_kind == scope_kind and binding.scope_id == scope_id:
            exact.append(binding)
        elif binding.scope_kind == "global" and binding.scope_id is None:
            global_matches.append(binding)
    if exact:
        return exact[0]
    if global_matches:
        return global_matches[0]
    if len(name_matches) == 1:
        return name_matches[0]
    return None
