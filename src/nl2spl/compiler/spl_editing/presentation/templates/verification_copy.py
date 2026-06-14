"""Verification presentation copy."""

from __future__ import annotations


def authority_summary(*, accepted: bool, lane: str) -> tuple[str, ...]:
    if accepted:
        return (
            f"Lane {lane}: replay completed.",
            "Compiler authorities accepted the patched snapshot.",
            "Renderer produced updated SPL.",
        )
    return (
        f"Lane {lane}: replay or verifier rejected the patch.",
        "Review failure reasons before applying another repair.",
    )


__all__ = ["authority_summary"]
