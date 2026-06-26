"""Custom exception classes for ConstructRepairIntent operations."""

from __future__ import annotations


class IntentError(Exception):
    """Base exception for intent operations."""


class IntentParseError(IntentError):
    """Raised when an intent payload cannot be parsed."""


class IntentValidationError(IntentError):
    """Raised when an intent fails validation rules."""
