"""Helpers for resource description normalization."""

from __future__ import annotations


def clean_resource_description(name: str, description: str | None) -> str:
    """Return a concise ASCII description suitable for DEFINE_VARIABLES."""
    text = " ".join((description or "").split())
    if not text or _has_non_ascii(text):
        return _description_from_name(name)
    return text


def _has_non_ascii(text: str) -> bool:
    return any(ord(char) > 127 for char in text)


def _description_from_name(name: str) -> str:
    words = [part for part in name.replace("-", "_").split("_") if part]
    if not words:
        return "Variable"
    return " ".join(words).capitalize()
