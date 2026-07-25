"""Qualified reference checks for Stage 6.5 condition refs."""

from __future__ import annotations

import re

from nl2spl.ir.resource_registry_ir import ResourceRegistryIR, TypeSpec
from nl2spl.ir.symbol_table import SymbolTable, VariableSymbol


def resolve_visible_variable(
    symbol_table: SymbolTable,
    worker_id: str | None,
    variable_name: str,
) -> VariableSymbol | None:
    """Resolve a variable from global/worker-visible scope."""
    if worker_id:
        return symbol_table.get_variables_for_worker(worker_id).get(variable_name)
    return symbol_table.lookup(variable_name)


def qualified_ref_is_valid(
    variable: VariableSymbol,
    qualified_path: tuple[str, ...],
    resource_registry: ResourceRegistryIR,
) -> bool:
    """Return whether a qualified field path is allowed by known type metadata.

    Unknown schemas are not rejected by Stage 6.5.  If the variable's type has a
    known type definition, every referenced field must appear in that definition.
    """
    if len(qualified_path) <= 1:
        return True

    spec = _find_type_spec(resource_registry, variable.data_type)
    if spec is None:
        return True

    definition = spec.definition or ""
    field_names = _field_names_from_definition(definition)
    return all(part in field_names for part in qualified_path[1:])


def _find_type_spec(
    resource_registry: ResourceRegistryIR,
    type_name: str,
) -> TypeSpec | None:
    return next(
        (spec for spec in resource_registry.types if spec.type_name == type_name),
        None,
    )


def _field_names_from_definition(definition: str) -> set[str]:
    # Supports common source forms such as "{x: A, y: B}" and JSON-ish fields.
    return set(re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*:", definition))
