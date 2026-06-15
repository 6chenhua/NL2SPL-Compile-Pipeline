"""Extension facts schema validation utilities (Phase L1)."""

from __future__ import annotations

from typing import Any, Mapping

from nl2spl.compiler.spl_editing.llm_context.errors import SchemaValidationError


def validate_facts(
    *,
    facts: Mapping[str, Any],
    required_keys: tuple[str, ...],
    optional_keys: tuple[str, ...],
    facts_schema_id: str,
    allow_unknown: bool = False,
) -> list[str]:
    """Validate extension facts against a minimal key-presence schema.

    Returns a list of missing required keys.
    Raises ``SchemaValidationError`` for unknown keys when ``allow_unknown``
    is False.
    """
    missing = [k for k in required_keys if k not in facts or not facts[k]]
    if not allow_unknown:
        known = set(required_keys) | set(optional_keys)
        for key in facts:
            if key not in known:
                raise SchemaValidationError(
                    f"Unknown fact key '{key}' in schema "
                    f"'{facts_schema_id}' (allowed: {sorted(known)})"
                )
    return missing


def check_renderer_compatibility(
    *,
    facts_schema_id: str,
    facts_schema_version: str,
    renderer_schema_ids: tuple[str, ...],
    renderer_supported_versions: tuple[str, ...] = ("1.0",),
) -> bool:
    """Check whether a renderer is compatible with the given facts schema."""
    if facts_schema_id not in renderer_schema_ids:
        return False
    if facts_schema_version not in renderer_supported_versions:
        return False
    return True
