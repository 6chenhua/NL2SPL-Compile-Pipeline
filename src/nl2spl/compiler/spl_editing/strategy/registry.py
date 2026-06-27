"""Registry for SPL Editing Repair Strategy Spec."""

from __future__ import annotations

import threading

from nl2spl.compiler.spl_editing.strategy.errors import (
    DuplicateStrategyError,
    StrategyNotFoundError,
)
from nl2spl.compiler.spl_editing.strategy.model import RepairStrategySpec


class RepairStrategyRegistry:
    """Thread-safe in-memory registry of RepairStrategySpec definitions."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._strategies: dict[str, RepairStrategySpec] = {}

    def register(self, spec: RepairStrategySpec) -> None:
        """Register a new strategy spec. Raises DuplicateStrategyError if strategy_id already exists."""
        with self._lock:
            if spec.strategy_id in self._strategies:
                raise DuplicateStrategyError(
                    f"Strategy '{spec.strategy_id}' is already registered."
                )
            self._strategies[spec.strategy_id] = spec

    def get(self, strategy_id: str) -> RepairStrategySpec:
        """Retrieve a registered spec. Raises StrategyNotFoundError if strategy_id does not exist."""
        with self._lock:
            if strategy_id not in self._strategies:
                raise StrategyNotFoundError(
                    f"Strategy '{strategy_id}' not found in registry."
                )
            return self._strategies[strategy_id]

    def has(self, strategy_id: str) -> bool:
        """Check if a strategy spec is registered."""
        with self._lock:
            return strategy_id in self._strategies

    def list_strategies(self) -> list[str]:
        """Return a sorted list of registered strategy IDs."""
        with self._lock:
            return sorted(self._strategies.keys())

    def clear(self) -> None:
        """Clear all registered strategies."""
        with self._lock:
            self._strategies.clear()
