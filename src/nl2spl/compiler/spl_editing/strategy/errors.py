"""Exception types for SPL Editing Repair Strategy."""

from __future__ import annotations

from nl2spl.compiler.spl_editing.core.errors import SPLEditingError


class StrategyRegistryError(SPLEditingError):
    """Base exception for strategy registry operations."""


class DuplicateStrategyError(StrategyRegistryError):
    """Raised when a strategy is registered more than once."""


class StrategyNotFoundError(StrategyRegistryError):
    """Raised when a strategy is not found in the registry."""
