"""Custom exception classes for SelectableRef operations."""

from __future__ import annotations


class SelectableRefError(Exception):
    """Base exception for selectable ref operations."""


class SelectableRefNotFoundError(SelectableRefError):
    """Raised when a SelectableRef with a given ref_id cannot be found."""


class SelectableRefRoleMismatchError(SelectableRefError):
    """Raised when a SelectableRef has a role that mismatches the requested role."""


class SelectableRefPolicyViolationError(SelectableRefError):
    """Raised when policy validation fails for selectable refs."""


class SelectableRefCollisionError(SelectableRefError):
    """Raised when a builder detects a collision between generated ref_ids."""
