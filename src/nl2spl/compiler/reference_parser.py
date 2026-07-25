"""Grammar-level parser for SPL ``<REF>...</REF>`` tokens.

This module only parses explicit grammar tokens and offsets.  It deliberately
does not perform symbol lookup, semantic matching, rewriting, or LLM fallback.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_REF_PATTERN = re.compile(r"<REF>(.*?)</REF>")
_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class ReferenceParseDiagnostic:
    """Diagnostic emitted by the grammar-level reference parser."""

    kind: str
    message: str
    start_offset: int
    end_offset: int
    raw_text: str


@dataclass(frozen=True)
class ReferenceToken:
    """A parsed explicit SPL reference token."""

    raw_text: str
    name: str
    is_by_value: bool
    top_level_name: str
    qualified_path: tuple[str, ...]
    start_offset: int
    end_offset: int


@dataclass(frozen=True)
class ReferenceParseResult:
    """Reference parse result with non-fatal parser diagnostics."""

    tokens: tuple[ReferenceToken, ...]
    diagnostics: tuple[ReferenceParseDiagnostic, ...] = ()


def parse_description_reference_result(text: str) -> ReferenceParseResult:
    """Parse explicit ``<REF>...</REF>`` tokens from description text."""
    tokens: list[ReferenceToken] = []
    diagnostics: list[ReferenceParseDiagnostic] = []

    for match in _REF_PATTERN.finditer(text):
        raw_text = match.group(0)
        raw_inner = match.group(1)
        inner = raw_inner.strip()
        if not inner:
            diagnostics.append(
                ReferenceParseDiagnostic(
                    kind="invalid_empty_ref",
                    message="Empty <REF> token is not a valid SPL reference.",
                    start_offset=match.start(),
                    end_offset=match.end(),
                    raw_text=raw_text,
                )
            )
            continue

        is_by_value = inner.startswith("*")
        name = inner[1:].strip() if is_by_value else inner
        parts = tuple(part.strip() for part in name.split("."))
        if (
            not name
            or any(not part for part in parts)
            or any(_NAME_PATTERN.match(part) is None for part in parts)
        ):
            diagnostics.append(
                ReferenceParseDiagnostic(
                    kind="invalid_ref_name",
                    message=f"Invalid <REF> token name: {inner!r}.",
                    start_offset=match.start(),
                    end_offset=match.end(),
                    raw_text=raw_text,
                )
            )
            continue

        tokens.append(
            ReferenceToken(
                raw_text=raw_text,
                name=".".join(parts),
                is_by_value=is_by_value,
                top_level_name=parts[0],
                qualified_path=parts,
                start_offset=match.start(),
                end_offset=match.end(),
            )
        )

    return ReferenceParseResult(
        tokens=tuple(sorted(tokens, key=lambda token: token.start_offset)),
        diagnostics=tuple(diagnostics),
    )


def parse_description_references(text: str) -> tuple[ReferenceToken, ...]:
    """Return parsed reference tokens, raising on malformed explicit tokens."""
    result = parse_description_reference_result(text)
    if result.diagnostics:
        first = result.diagnostics[0]
        raise ValueError(first.message)
    return result.tokens
