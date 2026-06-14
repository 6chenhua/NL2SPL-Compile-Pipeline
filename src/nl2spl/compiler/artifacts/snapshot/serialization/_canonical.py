"""Canonical conversion helpers — leaf-level type normalization.

Every helper here handles a single leaf-level type conversion:
    - Enum  <-> str (value)
    - datetime <-> ISO 8601 string
    - Path   -> POSIX string
    - tuple  <-> list (shallow)
    - set    -> sorted list

These helpers do NOT handle nested dataclasses — that is the serializer's
responsibility via recursive registry dispatch.  They also MUST NOT perform
any implicit conversions (no ``str(obj)``, no ``asdict()``).
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

# ===================================================================
# .to_canonical direction: typed object -> JSON-native
# ===================================================================


def enum_to_str(val: Enum) -> str:
    """Convert an enum member to its ``.value`` string."""
    if not isinstance(val, Enum):
        raise TypeError(f"Expected Enum, got {type(val).__name__}")
    return val.value


def datetime_to_iso(val: datetime) -> str:
    """Convert a ``datetime`` to an ISO 8601 string (UTC, 'Z' suffix)."""
    if not isinstance(val, datetime):
        raise TypeError(f"Expected datetime, got {type(val).__name__}")
    if val.tzinfo is None:
        val = val.replace(tzinfo=UTC)
    return val.isoformat()


def path_to_posix(val: Path) -> str:
    """Convert a ``Path`` to a POSIX-style string."""
    if not isinstance(val, Path):
        raise TypeError(f"Expected Path, got {type(val).__name__}")
    return val.as_posix()


def tuple_to_list(val: tuple[Any, ...]) -> list[Any]:
    """Convert a tuple to a JSON-safe list (shallow — elements must be
    already canonicalised)."""
    if not isinstance(val, tuple):
        raise TypeError(f"Expected tuple, got {type(val).__name__}")
    return list(val)


def set_to_sorted_list(val: set[Any]) -> list[Any]:
    """Convert a set to a sorted list (elements must be sortable and
    already canonicalised)."""
    if not isinstance(val, set):
        raise TypeError(f"Expected set, got {type(val).__name__}")
    return sorted(val, key=str)


# ===================================================================
# .from_canonical direction: JSON-native -> typed object
# ===================================================================


def str_to_enum(cls: type[Enum], val: str) -> Enum:
    """Look up an enum member by its ``.value`` string."""
    if not isinstance(val, str):
        raise TypeError(f"Expected str for enum value, got {type(val).__name__}")
    # Try by value first, then by name as fallback
    for member in cls:
        if member.value == val:
            return member
    raise ValueError(f"No {cls.__name__} member with value {val!r}")


def iso_to_datetime(val: str) -> datetime:
    """Parse an ISO 8601 string to a ``datetime``."""
    if not isinstance(val, str):
        raise TypeError(f"Expected str, got {type(val).__name__}")
    # Handle 'Z' suffix
    normalized = val.replace("Z", "+00:00")
    dt = datetime.fromisoformat(normalized)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def posix_to_path(val: str) -> Path:
    """Convert a POSIX-style string back to a ``Path``."""
    if not isinstance(val, str):
        raise TypeError(f"Expected str, got {type(val).__name__}")
    return Path(val)


def list_to_tuple(val: list[Any]) -> tuple[Any, ...]:
    """Convert a JSON list back to a tuple (shallow)."""
    if not isinstance(val, list):
        raise TypeError(f"Expected list, got {type(val).__name__}")
    return tuple(val)
