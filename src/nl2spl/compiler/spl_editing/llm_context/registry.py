"""LLMRepairContextExtensionRegistry (Phase L0).

Registry for primary and auxiliary context providers.
Lookup is by affordance_id + construct_type + slot_name + diagnostic_kind + patch_type.
"""

from __future__ import annotations

from typing import Any


class LLMRepairContextExtensionRegistry:
    """Registry of ``LLMRepairContextProvider`` instances.

    Does NOT import handler / patch / LLM client.
    Does NOT decide repair availability — that is RepairCatalog's job.
    """

    def __init__(self) -> None:
        self._providers: dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Resolution
    # ------------------------------------------------------------------

    def resolve_primary(
        self,
        *,
        affordance_id: str,
        construct_type: str,
        slot_name: str,
        diagnostic_kind: str,
        patch_type: str,
    ) -> Any | None:
        """Resolve the primary provider for a selected affordance + patch type.

        Priority:
        1. Exact affordance_id + patch_type match
        2. Affordance_id fallback (any patch_type match for that affordance)
        3. Construct_type + slot_name + patch_type fallback (if #1 and #2 fail)
        4. Return None if no match
        """
        # Priority 1: exact affordance_id + patch_type
        for diag_kind in (diagnostic_kind, "*"):
            key = _encode_key(affordance_id, construct_type, slot_name, diag_kind, patch_type)
            if key in self._providers:
                return self._providers[key]

        # Priority 2: affordance_id default (any patch_type)
        for diag_kind in (diagnostic_kind, "*"):
            key = _encode_key(affordance_id, construct_type, slot_name, diag_kind, "*")
            if key in self._providers:
                return self._providers[key]

        # Priority 3: construct_type + slot_name + patch_type fallback
        for diag_kind in (diagnostic_kind, "*"):
            key = _encode_key("*", construct_type, slot_name, diag_kind, patch_type)
            if key in self._providers:
                return self._providers[key]

        return None

    def resolve_auxiliary(
        self,
        *,
        primary_extension: Any,  # LLMRepairContextExtension
        issue: Any,
        target: Any,
        repair_context: Any,
    ) -> tuple[Any, ...]:
        """Resolve auxiliary providers for supporting facts.

        Returns a tuple of matching auxiliary providers.
        The base implementation returns all registered providers whose
        role is "auxiliary" and whose diagnostic_kinds / construct_type
        overlap with the primary extension scope.
        """
        auxiliary: list[Any] = []
        for provider in self._providers.values():
            role = getattr(provider, "role", None)
            if role != "auxiliary":
                continue
            # Match on at least one supported diagnostic kind
            diag_kinds = getattr(provider, "diagnostic_kinds", ())
            if diag_kinds:
                if primary_extension.diagnostic_kind not in diag_kinds and "*" not in diag_kinds:
                    continue
            auxiliary.append(provider)
        return tuple(auxiliary)

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def has_provider(self, provider_id: str) -> bool:
        """Check whether a provider with the given id is registered."""
        return any(
            getattr(p, "provider_id", None) == provider_id
            for p in self._providers.values()
        )

    def list_provider_ids(self) -> tuple[str, ...]:
        """Return all registered provider ids."""
        return tuple(
            getattr(p, "provider_id", "")
            for p in self._providers.values()
        )

    def __len__(self) -> int:
        return len(self._providers)

    # ------------------------------------------------------------------
    # Key construction
    # ------------------------------------------------------------------

    def register(self, provider: Any) -> None:
        """Register a provider for ALL its supported diagnostic kinds
        and patch types.  A provider declaring three patch types gets
        three registry entries — one per patch type.
        """
        affordance = provider.affordance_id or "*"
        construct = provider.construct_type or "*"
        slot = provider.slot_name or "*"
        diag_kinds: tuple[str, ...] = getattr(provider, "diagnostic_kinds", ()) or ("*",)
        patch_types: tuple[str, ...] = getattr(provider, "supported_patch_types", ()) or ("*",)

        for diag in diag_kinds:
            for pt in patch_types:
                key = _encode_key(affordance, construct, slot, diag or "*", pt or "*")
                if key in self._providers:
                    # Allow same provider to re-register under different key
                    # but fail if a DIFFERENT provider already claimed this key
                    existing = self._providers[key]
                    if getattr(existing, "provider_id", None) != getattr(provider, "provider_id", None):
                        raise KeyError(
                            f"Duplicate provider key '{key}': "
                            f"'{getattr(existing, 'provider_id', '?')}' vs "
                            f"'{getattr(provider, 'provider_id', '?')}'"
                        )
                self._providers[key] = provider

    # ------------------------------------------------------------------
    # Key construction (removed — using register with loop instead)
    # ------------------------------------------------------------------


def _encode_key(
    affordance_id: str,
    construct_type: str,
    slot_name: str,
    diagnostic_kind: str,
    patch_type: str,
) -> str:
    """Composite registry key encoding."""
    return f"{affordance_id}::{construct_type}::{slot_name}::{diagnostic_kind}::{patch_type}"
