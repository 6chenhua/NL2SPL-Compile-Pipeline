"""Projection helper for RepairStrategySpec to catalog metadata.

Does not import catalog.py to prevent circular imports.
"""

from __future__ import annotations

from typing import Any


def project_strategy_metadata(
    repair_strategy_id: str | None,
    strategy_registry: Any,
) -> dict[str, Any]:
    """Look up a strategy and project its display_label, closure_summary, and preview_required."""
    if not repair_strategy_id or not strategy_registry:
        return {
            "repair_strategy_id": None,
            "strategy_display_label": None,
            "closure_summary": None,
            "preview_required": False,
        }
    has_method = getattr(strategy_registry, "has", None)
    if has_method is not None:
        if not has_method(repair_strategy_id):
            return {
                "repair_strategy_id": None,
                "strategy_display_label": None,
                "closure_summary": None,
                "preview_required": False,
            }
    try:
        spec = strategy_registry.get(repair_strategy_id)
        return {
            "repair_strategy_id": spec.strategy_id,
            "strategy_display_label": getattr(spec, "display_label", None),
            "closure_summary": getattr(spec, "closure_summary", None),
            "preview_required": getattr(spec, "preview_required", False),
        }
    except Exception as e:
        if type(e).__name__ not in ("StrategyNotFoundError", "KeyError"):
            raise
        return {
            "repair_strategy_id": None,
            "strategy_display_label": None,
            "closure_summary": None,
            "preview_required": False,
        }
