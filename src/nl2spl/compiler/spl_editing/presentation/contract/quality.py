"""Presentation quality contract."""

from __future__ import annotations

from enum import StrEnum


class PresentationQuality(StrEnum):
    COMPLETE = "complete"
    DEGRADED = "degraded"


__all__ = ["PresentationQuality"]
