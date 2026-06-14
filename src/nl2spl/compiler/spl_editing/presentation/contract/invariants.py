"""Presentation contract invariants."""

from __future__ import annotations

from collections.abc import Iterable

from nl2spl.compiler.spl_editing.presentation.contract.availability import (
    RepairOptionAvailability,
)


def has_available_repair_option(options: Iterable[object]) -> bool:
    """Return True iff at least one option is currently actionable."""
    return any(
        getattr(option, "availability", None)
        == RepairOptionAvailability.AVAILABLE
        for option in options
    )


def expected_can_fix(options: Iterable[object]) -> bool:
    """Contract: can_fix mirrors existence of an available repair option."""
    return has_available_repair_option(options)


def assert_can_fix_invariant(*, can_fix: bool, options: Iterable[object]) -> None:
    expected = expected_can_fix(options)
    if can_fix != expected:
        raise ValueError(
            f"can_fix invariant violated: can_fix={can_fix!r}, "
            f"expected={expected!r}"
        )


__all__ = [
    "assert_can_fix_invariant",
    "expected_can_fix",
    "has_available_repair_option",
]
