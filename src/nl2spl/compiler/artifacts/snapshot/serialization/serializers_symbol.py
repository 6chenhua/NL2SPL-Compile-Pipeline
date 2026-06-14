"""Serializers for SymbolTable and VariableSymbol.

SymbolTable is the only non-dataclass artifact.  Its composite key
``(scope_kind, scope_id, name)`` is serialized as a pipe-delimited
string ``"scope_kind|scope_id|name"`` with ``None`` encoded as
``"__none__"``.
"""

from __future__ import annotations

from typing import Any

from nl2spl.compiler.artifacts.snapshot.serialization.protocol import (
    ArtifactSerializer,
)
from nl2spl.compiler.artifacts.snapshot.serialization.registry import (
    SerializerRegistry,
)
from nl2spl.ir.symbol_table import SymbolTable, VariableSymbol

# ---------------------------------------------------------------------------
# Composite-key encoding
# ---------------------------------------------------------------------------

_NONE_SENTINEL = "__none__"
_SEPARATOR = "|"


def _encode_composite_key(key: tuple[str, str | None, str]) -> str:
    scope_kind, scope_id, name = key
    sid = _NONE_SENTINEL if scope_id is None else scope_id
    return _SEPARATOR.join([scope_kind, sid, name])


def _decode_composite_key(encoded: str) -> tuple[str, str | None, str]:
    parts = encoded.split(_SEPARATOR, 2)
    if len(parts) != 3:
        raise ValueError(f"Invalid composite key: {encoded!r}")
    scope_kind, sid, name = parts
    scope_id = None if sid == _NONE_SENTINEL else sid
    return (scope_kind, scope_id, name)


# ---------------------------------------------------------------------------
# Serializers
# ---------------------------------------------------------------------------


class VariableSymbolSerializer(ArtifactSerializer):
    type_id = "VariableSymbol"

    def to_canonical(self, obj: Any) -> dict[str, Any]:
        v: VariableSymbol = obj
        return {
            "$type": self.type_id,
            "name": v.name,
            "data_type": v.data_type,
            "source": v.source,
            "description": v.description,
            "scope_kind": v.scope_kind,
            "scope_id": v.scope_id,
            "flow_ref": v.flow_ref,
            "block_ref": v.block_ref,
            "producer_step": v.producer_step,
            "consumer_steps": v.consumer_steps,
            "declared": v.declared,
        }

    def from_canonical(self, data: dict[str, Any]) -> Any:
        return VariableSymbol(
            name=data["name"],
            data_type=data["data_type"],
            source=data["source"],
            description=data["description"],
            scope_kind=data.get("scope_kind", "global"),
            scope_id=data.get("scope_id"),
            flow_ref=data.get("flow_ref", "main"),
            block_ref=data.get("block_ref"),
            producer_step=data.get("producer_step"),
            consumer_steps=data.get("consumer_steps", []),
            declared=data.get("declared", True),
        )


class SymbolTableSerializer(ArtifactSerializer):
    type_id = "SymbolTable"

    def to_canonical(self, obj: Any) -> dict[str, Any]:
        st: SymbolTable = obj
        var_ser = VariableSymbolSerializer()
        variables: dict[str, dict[str, Any]] = {}
        for key, var in st._variables.items():
            encoded = _encode_composite_key(key)
            variables[encoded] = var_ser.to_canonical(var)
        return {
            "$type": self.type_id,
            "variables": variables,
        }

    def from_canonical(self, data: dict[str, Any]) -> Any:
        st = SymbolTable()
        var_ser = VariableSymbolSerializer()
        raw_vars: dict[str, dict[str, Any]] = data.get("variables", {})
        for encoded, var_data in raw_vars.items():
            key = _decode_composite_key(encoded)
            var = var_ser.from_canonical(var_data)
            st._variables[key] = var
            # Populate legacy flat dict for global scope
            scope_kind, _scope_id, name = key
            if scope_kind == "global":
                st.variables[name] = var
        return st


def register_all(registry: SerializerRegistry) -> None:
    s1 = VariableSymbolSerializer()
    s2 = SymbolTableSerializer()
    registry.register(s1)
    registry.register(s2)
    registry.register_for_class(VariableSymbol, s1)
    registry.register_for_class(SymbolTable, s2)
