"""S1 symbol serializer tests — SymbolTable composite key round-trip."""

from __future__ import annotations

import pytest

from nl2spl.compiler.artifacts.snapshot.serialization.registry import (
    build_default_registry,
)
from nl2spl.compiler.artifacts.snapshot.serialization.serializers_symbol import (
    _decode_composite_key,
    _encode_composite_key,
)
from nl2spl.ir.symbol_table import SymbolTable, VariableSymbol


def _rt(registry, obj):
    data = registry.serialize(obj)
    restored = registry.deserialize(data)
    return data, restored


class TestCompositeKeyEncoding:
    def test_encode_decode_global(self) -> None:
        key = ("global", None, "draft")
        encoded = _encode_composite_key(key)
        assert encoded == "global|__none__|draft"
        decoded = _decode_composite_key(encoded)
        assert decoded == key

    def test_encode_decode_worker_scoped(self) -> None:
        key = ("worker", "MainWorker", "result")
        encoded = _encode_composite_key(key)
        assert encoded == "worker|MainWorker|result"
        decoded = _decode_composite_key(encoded)
        assert decoded == key

    def test_encode_decode_handoff(self) -> None:
        key = ("handoff", "h_001", "payload")
        encoded = _encode_composite_key(key)
        assert "handoff" in encoded
        decoded = _decode_composite_key(encoded)
        assert decoded == key

    def test_decode_malformed_key_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid composite key"):
            _decode_composite_key("only_one_part")

    def test_decode_empty_string_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid composite key"):
            _decode_composite_key("")

    def test_decode_too_many_parts_works(self) -> None:
        """Extra separators are consumed by the name part only."""
        result = _decode_composite_key("global|__none__|name|with|pipes")
        assert result == ("global", None, "name|with|pipes")

    def test_none_roundtrip_in_scope_id(self) -> None:
        """None scope_id must be faithfully restored, not become '__none__'."""
        key = ("handoff", None, "var")
        encoded = _encode_composite_key(key)
        decoded = _decode_composite_key(encoded)
        assert decoded[1] is None


class TestVariableSymbolRoundTrip:
    def test_full_roundtrip(self) -> None:
        reg = build_default_registry()
        var = VariableSymbol(
            name="draft",
            data_type="text",
            source="input",
            description="The draft content",
            scope_kind="global",
            scope_id=None,
            flow_ref="main",
            producer_step="st_extract",
            consumer_steps=["st_format", "st_send"],
            declared=True,
        )
        data, restored = _rt(reg, var)
        assert data["$type"] == "VariableSymbol"
        assert restored.name == "draft"
        assert restored.scope_kind == "global"
        assert restored.scope_id is None
        assert restored.consumer_steps == ["st_format", "st_send"]

    def test_worker_scoped_variable(self) -> None:
        reg = build_default_registry()
        var = VariableSymbol(
            name="result",
            data_type="json",
            source="api",
            description="API result",
            scope_kind="worker",
            scope_id="MainWorker",
        )
        _data, restored = _rt(reg, var)
        assert restored.scope_kind == "worker"
        assert restored.scope_id == "MainWorker"


class TestSymbolTableRoundTrip:
    def test_empty_table(self) -> None:
        reg = build_default_registry()
        st = SymbolTable()
        data, restored = _rt(reg, st)
        assert data["$type"] == "SymbolTable"
        assert restored._variables == {}

    def test_with_global_variables(self) -> None:
        reg = build_default_registry()
        st = SymbolTable()
        st.declare("draft", "text", "input", "Draft content")
        st.declare("result", "json", "output", "Result content")
        data, restored = _rt(reg, st)
        assert len(restored._variables) == 2
        # Legacy flat dict also populated for global scope
        assert "draft" in restored.variables

    def test_with_scoped_variables(self) -> None:
        reg = build_default_registry()
        st = SymbolTable()
        st.declare("draft", "text", "input", "Draft")
        # Add a worker-scoped variable via _variables directly
        worker_var = VariableSymbol(
            name="local_result",
            data_type="json",
            source="api",
            description="Worker-local",
            scope_kind="worker",
            scope_id="SubWorker",
        )
        st._variables[("worker", "SubWorker", "local_result")] = worker_var
        data, restored = _rt(reg, st)
        # Both variables preserved
        assert len(restored._variables) == 2
        # Worker-scoped variable has correct key
        found = False
        for key, _val in restored._variables.items():
            if key[0] == "worker":
                assert key[1] == "SubWorker"
                assert key[2] == "local_result"
                found = True
        assert found, "Worker-scoped variable not found after round-trip"

    def test_symbol_table_is_not_dataclass(self) -> None:
        """SymbolTable is a regular class, not a dataclass. Serializer must handle it."""
        import dataclasses

        st = SymbolTable()
        assert not dataclasses.is_dataclass(st)

    def test_no_python_repr_in_payload(self) -> None:
        reg = build_default_registry()
        st = SymbolTable()
        st.declare("x", "int", "input", "Integer x")
        data = reg.serialize(st)
        payload_str = str(data)
        assert "SymbolTable object" not in payload_str
