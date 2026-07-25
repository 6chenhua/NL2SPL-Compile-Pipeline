"""Candidate symbol view for Stage 6.5 condition reference extraction."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from nl2spl.ir.resource_registry_ir import ResourceRegistryIR, TypeSpec
from nl2spl.ir.symbol_table import SymbolTable, VariableSymbol


@dataclass(frozen=True)
class CandidateSymbol:
    """A symbol candidate visible to one condition owner."""

    name: str
    data_type: str
    scope_kind: str
    scope_id: str | None
    description: str
    source: str
    source_span_ids: tuple[str, ...] = ()
    fields: tuple[str, ...] = ()

    def to_prompt_payload(self) -> dict[str, object]:
        return {
            "name": self.name,
            "data_type": self.data_type,
            "scope_kind": self.scope_kind,
            "scope_id": self.scope_id,
            "description": self.description,
            "source": self.source,
            "source_span_ids": list(self.source_span_ids),
            "fields": list(self.fields),
        }


def build_candidate_symbol_view(
    symbol_table: SymbolTable,
    resource_registry: ResourceRegistryIR,
    worker_id: str | None,
) -> tuple[CandidateSymbol, ...]:
    """Build a deterministic worker/global visible candidate-symbol view."""
    variables = (
        symbol_table.get_variables_for_worker(worker_id)
        if worker_id
        else {name: var for name, var in symbol_table.variables.items()}
    )
    candidates = [
        _candidate_from_variable(var, resource_registry)
        for var in variables.values()
    ]
    return tuple(
        sorted(
            candidates,
            key=lambda candidate: (
                0 if candidate.scope_kind == "worker" else 1,
                candidate.name,
                candidate.scope_id or "",
            ),
        )
    )


def candidate_symbol_names(candidates: tuple[CandidateSymbol, ...]) -> set[str]:
    return {candidate.name for candidate in candidates}


def candidate_by_name(
    candidates: tuple[CandidateSymbol, ...],
    name: str,
) -> CandidateSymbol | None:
    return next((candidate for candidate in candidates if candidate.name == name), None)


def candidate_payloads(candidates: tuple[CandidateSymbol, ...]) -> list[dict[str, object]]:
    return [candidate.to_prompt_payload() for candidate in candidates]


def _candidate_from_variable(
    variable: VariableSymbol,
    resource_registry: ResourceRegistryIR,
) -> CandidateSymbol:
    return CandidateSymbol(
        name=variable.name,
        data_type=variable.data_type,
        scope_kind=variable.scope_kind,
        scope_id=variable.scope_id,
        description=variable.description,
        source=variable.source,
        # VariableSymbol currently does not carry source spans. Preserve an empty
        # tuple so the prompt schema is stable and future evidence can fill it.
        source_span_ids=(),
        fields=tuple(sorted(_fields_for_type(resource_registry, variable.data_type))),
    )


def _fields_for_type(resource_registry: ResourceRegistryIR, type_name: str) -> set[str]:
    spec = next((item for item in resource_registry.types if item.type_name == type_name), None)
    if spec is None:
        return set()
    return _field_names_from_type_spec(spec)


def _field_names_from_type_spec(spec: TypeSpec) -> set[str]:
    definition = spec.definition or ""
    return set(re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*:", definition))


def symbol_view_to_prompt_json(
    candidates: tuple[CandidateSymbol, ...],
) -> list[dict[str, Any]]:
    return [dict(candidate.to_prompt_payload()) for candidate in candidates]
