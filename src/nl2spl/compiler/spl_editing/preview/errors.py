"""Exception types for Preview lifecycle."""

from __future__ import annotations

from nl2spl.compiler.spl_editing.core.errors import SPLEditingError


class PreviewError(SPLEditingError):
    """Exception related to preview lifecycle operations."""


class PreviewStaleError(PreviewError):
    """Raised when a stored preview no longer matches an apply candidate."""
