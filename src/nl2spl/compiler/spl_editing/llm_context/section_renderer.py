"""LLMRepairContextSectionRenderer protocol + registry (Phase L0).

Section renderers convert one ``LLMRepairContextExtension`` into a
prompt text block.  Each renderer is bound to one or more
``facts_schema_ids`` — it must NOT branch on construct_type or
patch_type with a giant if-else.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

# =============================================================================
# Section Renderer Protocol
# =============================================================================


@runtime_checkable
class LLMRepairContextSectionRenderer(Protocol):
    """Protocol for a schema-bound section renderer.

    Attributes are class-level declarations consumed by the registry.
    ``render(...)`` is the single instance method.
    """

    renderer_id: str
    facts_schema_ids: tuple[str, ...]

    def render(
        self,
        *,
        extension: Any,  # LLMRepairContextExtension
    ) -> str:
        """Render an extension into a prompt section.

        MUST only read facts keys declared in the matching schema.
        MUST NOT branch on construct_type / patch_type with a giant
        if-else — use the schema to discover fields.
        """
        ...


# =============================================================================
# Section Renderer Registry
# =============================================================================


class SectionRendererRegistry:
    """Registry of section renderers, keyed by renderer_id + facts_schema_id.

    Does NOT import handler / patch / LLM client.
    Does NOT decide repair availability.
    """

    def __init__(self) -> None:
        self._renderers: dict[str, Any] = {}

    def register(self, renderer: Any) -> None:
        """Register a section renderer.

        One renderer may serve multiple facts_schema_ids.  The renderer's
        ``facts_schema_ids`` tuple is iterated and each (renderer_id,
        schema_id) pair is registered independently.
        """
        rid = getattr(renderer, "renderer_id", None)
        if not rid:
            raise ValueError("Section renderer must have a non-empty renderer_id")
        schema_ids = getattr(renderer, "facts_schema_ids", ())
        if not schema_ids:
            raise ValueError(f"Section renderer '{rid}' must declare at least one facts_schema_id")
        for schema_id in schema_ids:
            key = _renderer_key(rid, schema_id)
            if key in self._renderers:
                raise KeyError(f"Duplicate section renderer key: {key}")
            self._renderers[key] = renderer

    def get(
        self,
        *,
        renderer_id: str,
        facts_schema_id: str,
        facts_schema_version: str,  # reserved for future version matching
    ) -> Any | None:
        """Look up a section renderer."""
        _ = facts_schema_version  # reserved
        key = _renderer_key(renderer_id, facts_schema_id)
        return self._renderers.get(key)

    def has(self, renderer_id: str, facts_schema_id: str) -> bool:
        key = _renderer_key(renderer_id, facts_schema_id)
        return key in self._renderers

    def __len__(self) -> int:
        return len(self._renderers)


def _renderer_key(renderer_id: str, facts_schema_id: str) -> str:
    return f"{renderer_id}::{facts_schema_id}"
