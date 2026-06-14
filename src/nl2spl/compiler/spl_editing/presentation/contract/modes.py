"""Presentation display modes."""

from __future__ import annotations

from enum import StrEnum


class PresentationMode(StrEnum):
    USER = "user"
    DEVELOPER = "developer"


__all__ = ["PresentationMode"]
