"""LLMRepairContextProvider protocol (Phase L0).

Providers collect affordance/patch-specific facts from structured
backend state.  They MUST NOT:
  - Decide issue repairability
  - Declare new patch capabilities
  - Call LLM
  - Parse rendered SPL / feedback_report / stage debug JSON
  - Extract business facts from raw diagnostic.message regex
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class LLMRepairContextProvider(Protocol):
    """Protocol for affordance-scoped context providers.

    Attributes are class-level declarations consumed by the registry
    and builder.  ``collect_facts(...)`` is the single instance method.
    """

    # -- Class-level declarations (registry keys) ------------------------

    provider_id: str
    role: str  # "primary" | "auxiliary"

    affordance_id: str | None
    construct_type: str | None
    slot_name: str | None
    diagnostic_kinds: tuple[str, ...]
    supported_patch_types: tuple[str, ...]

    facts_schema_id: str
    facts_schema_version: str
    facts_schema: dict[str, Any]  # JSON-serializable schema

    renderer_id: str
    required_fact_keys: tuple[str, ...]
    optional_fact_keys: tuple[str, ...]

    # -- Instance method ------------------------------------------------

    def collect_facts(
        self,
        *,
        issue: Any,  # EditableIssue (avoid circular import)
        target: Any,  # RepairTarget
        repair_context: Any,  # RepairContext
        artifact_snapshot: Any,  # ArtifactSnapshot
        presentation_view: Any | None,  # IssuePresentationView | None
    ) -> Any:  # LLMRepairContextExtension
        """Collect affordance-specific facts from structured state.

        Returns a schema-validated ``LLMRepairContextExtension``.
        """
        ...
