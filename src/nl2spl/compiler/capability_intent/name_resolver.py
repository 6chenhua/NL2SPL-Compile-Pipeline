"""Deterministic SPL-safe names for described unnamed capabilities."""

from __future__ import annotations

import hashlib
import re
import unicodedata


class CapabilityNameResolverV1:
    """Resolve names from final-intent-derived structured fields only."""

    version = "CapabilityNameResolverV1"

    def resolve(
        self,
        *,
        capability_intent_id: str,
        capability_surface: str,
        operation_text: str,
        existing_names: set[str],
    ) -> str:
        words = _ascii_words(capability_surface)
        if not words:
            words = _ascii_words(operation_text)
        base = "".join(word[:1].upper() + word[1:] for word in words[:5])
        if not base:
            base = "ExternalCapability"
        if base[0].isdigit():
            base = f"Capability{base}"
        if not base.endswith("API"):
            base = f"{base}API"
        if base not in existing_names:
            return base
        suffix = hashlib.sha256(capability_intent_id.encode("utf-8")).hexdigest()[:8]
        return f"{base}_{suffix}"


def _ascii_words(value: str) -> list[str]:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    return [
        token
        for token in re.findall(r"[A-Za-z0-9]+", ascii_value)
        if token.casefold() not in {"the", "a", "an", "to", "via", "using"}
    ]
