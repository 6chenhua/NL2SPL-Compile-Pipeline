"""S1 canonical helper tests: enum, datetime, Path, tuple, set round-trips."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from pathlib import Path

import pytest

from nl2spl.compiler.artifacts.snapshot.serialization._canonical import (
    datetime_to_iso,
    enum_to_str,
    iso_to_datetime,
    list_to_tuple,
    path_to_posix,
    posix_to_path,
    set_to_sorted_list,
    str_to_enum,
    tuple_to_list,
)


class _TestEnum(str, Enum):  # noqa: UP042
    ALPHA = "alpha_value"
    BETA = "beta_value"


class TestEnumHelpers:
    def test_enum_to_str_roundtrip(self) -> None:
        val = enum_to_str(_TestEnum.ALPHA)
        assert val == "alpha_value"
        restored = str_to_enum(_TestEnum, val)
        assert restored is _TestEnum.ALPHA

    def test_enum_to_str_rejects_non_enum(self) -> None:
        with pytest.raises(TypeError, match="Expected Enum"):
            enum_to_str("not_an_enum")  # type: ignore[arg-type]

    def test_str_to_enum_rejects_unknown_value(self) -> None:
        with pytest.raises(ValueError, match="No _TestEnum"):
            str_to_enum(_TestEnum, "nonexistent")

    def test_str_to_enum_rejects_non_str(self) -> None:
        with pytest.raises(TypeError, match="Expected str"):
            str_to_enum(_TestEnum, 123)  # type: ignore[arg-type]

    def test_str_to_enum_by_value_not_name(self) -> None:
        """Must look up by .value, not .name."""
        val = str_to_enum(_TestEnum, "alpha_value")
        assert val is _TestEnum.ALPHA


class TestDatetimeHelpers:
    def test_datetime_roundtrip(self) -> None:
        dt = datetime(2025, 6, 15, 14, 30, 0, tzinfo=UTC)
        iso = datetime_to_iso(dt)
        restored = iso_to_datetime(iso)
        assert restored == dt

    def test_datetime_naive_becomes_utc(self) -> None:
        dt = datetime(2025, 6, 15, 14, 30, 0)
        iso = datetime_to_iso(dt)
        assert "+00:00" in iso or "Z" in iso

    def test_datetime_to_iso_rejects_non_datetime(self) -> None:
        with pytest.raises(TypeError, match="Expected datetime"):
            datetime_to_iso("2025-01-01")  # type: ignore[arg-type]

    def test_iso_to_datetime_rejects_non_str(self) -> None:
        with pytest.raises(TypeError, match="Expected str"):
            iso_to_datetime(12345)  # type: ignore[arg-type]


class TestPathHelpers:
    def test_path_roundtrip(self) -> None:
        p = Path("/some/output/dir")
        s = path_to_posix(p)
        assert s == "/some/output/dir"
        restored = posix_to_path(s)
        assert restored == p

    def test_path_to_posix_rejects_non_path(self) -> None:
        with pytest.raises(TypeError, match="Expected Path"):
            path_to_posix("not_a_path")  # type: ignore[arg-type]

    def test_posix_to_path_rejects_non_str(self) -> None:
        with pytest.raises(TypeError, match="Expected str"):
            posix_to_path(123)  # type: ignore[arg-type]


class TestTupleListHelpers:
    def test_tuple_to_list(self) -> None:
        assert tuple_to_list(("a", "b", "c")) == ["a", "b", "c"]

    def test_list_to_tuple(self) -> None:
        assert list_to_tuple([1, 2, 3]) == (1, 2, 3)

    def test_empty_tuple_roundtrip(self) -> None:
        assert list_to_tuple(tuple_to_list(())) == ()

    def test_tuple_to_list_rejects_non_tuple(self) -> None:
        with pytest.raises(TypeError, match="Expected tuple"):
            tuple_to_list([1, 2])  # type: ignore[arg-type]

    def test_list_to_tuple_rejects_non_list(self) -> None:
        with pytest.raises(TypeError, match="Expected list"):
            list_to_tuple((1, 2))  # type: ignore[arg-type]

    def test_nested_tuples_not_handled_shallow(self) -> None:
        """tuple_to_list is shallow — nested tuples stay as tuples."""
        nested = (1, (2, 3))
        result = tuple_to_list(nested)
        assert result == [1, (2, 3)]  # inner tuple preserved


class TestSetHelpers:
    def test_set_to_sorted_list(self) -> None:
        result = set_to_sorted_list({"c", "a", "b"})
        assert result == ["a", "b", "c"]

    def test_set_to_sorted_list_empty(self) -> None:
        assert set_to_sorted_list(set()) == []

    def test_set_to_sorted_list_stable(self) -> None:
        """Same input must produce same output every time."""
        s = {"z", "a", "m"}
        out1 = set_to_sorted_list(s)
        out2 = set_to_sorted_list(s)
        assert out1 == out2

    def test_set_to_sorted_list_rejects_non_set(self) -> None:
        with pytest.raises(TypeError, match="Expected set"):
            set_to_sorted_list(["a", "b"])  # type: ignore[arg-type]
