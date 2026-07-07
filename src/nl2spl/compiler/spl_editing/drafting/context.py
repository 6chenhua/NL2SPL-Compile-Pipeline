"""Read-only context envelope passed to repair inference providers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RepairDraftingContext:
    issue: Any
    target: Any
    catalog_entry: Any
    option: Any
    snapshot: Any
    views: dict[str, Any] | None = None

