"""Apply confirmation copy."""

from __future__ import annotations


def will_do(patch_type: str, lane: str) -> tuple[str, ...]:
    base = [f"Apply typed patch {patch_type}."]
    base.append("Mark the repair as user-confirmed evidence.")
    base.append(f"Re-run compiler verification through Lane {lane}.")
    return tuple(base)


def will_not_do() -> tuple[str, ...]:
    return (
        "Modify final SPL text directly.",
        "Bypass IRS, Gate, ProducerIndex, or Renderer.",
        "Apply unconfirmed AI content.",
    )


__all__ = ["will_do", "will_not_do"]
