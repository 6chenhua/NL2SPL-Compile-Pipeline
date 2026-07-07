"""Qualified SPL reference parsing helpers."""

from __future__ import annotations

import re

_REF_TAG_RE = re.compile(r"^<REF>\s*(\*?)([^<]+?)\s*</REF>$")
_SIMPLE_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def unwrap_ref_tag(ref_text: str) -> tuple[str, bool] | None:
    """Return the inner reference text and value-reference flag."""
    text = ref_text.strip()
    match = _REF_TAG_RE.match(text)
    if not match:
        return None
    return match.group(2).strip(), bool(match.group(1))


def parse_ref_name(ref_text: str) -> tuple[str, tuple[str, ...]] | None:
    """Parse a simple or qualified reference name.

    Returns ``(top_name, field_path)`` for syntactically valid simple and
    qualified references. Returns ``None`` for invalid syntax.
    """
    text = ref_text.strip()
    unwrapped = unwrap_ref_tag(text)
    if unwrapped is not None:
        text = unwrapped[0]
    if text.startswith("*"):
        text = text[1:].strip()
    parts = tuple(part.strip() for part in text.split("."))
    if not parts or any(not _SIMPLE_NAME_RE.match(part) for part in parts):
        return None
    return parts[0], parts[1:]


def parse_qualified_ref(ref_text: str) -> tuple[str, tuple[str, ...]] | None:
    """Return ``(top_name, field_path)`` only for qualified references."""
    parsed = parse_ref_name(ref_text)
    if parsed is None:
        return None
    top_name, field_path = parsed
    if not field_path:
        return None
    return top_name, field_path


def is_qualified_ref(ref_text: str) -> bool:
    """Return True when *ref_text* is a syntactically valid qualified ref."""
    return parse_qualified_ref(ref_text) is not None
