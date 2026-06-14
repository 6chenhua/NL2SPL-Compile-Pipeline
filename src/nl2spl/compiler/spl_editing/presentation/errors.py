"""Presentation projection errors."""

from __future__ import annotations


class PresentationError(Exception):
    """Base error for presentation projection failures."""


class IssuePresentationNotFoundError(PresentationError, KeyError):
    """Raised when a requested issue presentation does not exist."""


__all__ = ["IssuePresentationNotFoundError", "PresentationError"]
