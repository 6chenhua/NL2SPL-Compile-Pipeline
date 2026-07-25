"""Shared render-contract rules for SPL text and structured presentations."""

from __future__ import annotations

from typing import Final

from nl2spl.ir.resource_registry_ir import ResourceRegistryIR
from nl2spl.ir.symbol_table import SymbolTable

SOURCE_BACKED_PROFILE_RELATIONS: Final[frozenset[str]] = frozenset(
    {"direct", "normalized", "derived", "inferred"}
)

COMMAND_RESULT_KEYWORDS: Final[dict[str, str]] = {
    "GENERAL_COMMAND": "RESULT",
    "CALL_API": "RESPONSE",
    "INVOKE_WORKER": "RESPONSE",
    "REQUEST_INPUT": "VALUE",
}

REQUEST_INPUT_DEFAULT_RESULT_NAME: Final = "user_input"
REQUEST_INPUT_DEFAULT_RESULT_TYPE: Final = "text"


def is_renderable_optional_profile_item(item: object) -> bool:
    """Return whether Stage 11 may materialize an optional profile item."""
    source_span_ids = getattr(item, "source_span_ids", ())
    relation = getattr(item, "provenance_relation", "assumed")
    return bool(source_span_ids) and relation in SOURCE_BACKED_PROFILE_RELATIONS


def grammar_aspect_name(value: str) -> str:
    """Return the grammar-safe optional-aspect spelling used by SPL."""
    return "".join(part.capitalize() for part in value.split("_")) or "Requirement"


def command_result_keyword(command_type: str) -> str:
    """Return the SPL result keyword for a command type."""
    return COMMAND_RESULT_KEYWORDS.get(command_type, "RESULT")


def build_result_type_lookup(
    resources: ResourceRegistryIR | None,
    symbol_table: SymbolTable | None,
) -> dict[str, str]:
    """Build Stage 11's variable-name to data-type lookup."""
    lookup: dict[str, str] = {}
    if isinstance(resources, ResourceRegistryIR):
        lookup.update((variable.name, variable.data_type) for variable in resources.variables)
    if isinstance(symbol_table, SymbolTable):
        for variable in symbol_table.get_all_declared_variables().values():
            lookup.setdefault(variable.name, variable.data_type)
    return lookup
