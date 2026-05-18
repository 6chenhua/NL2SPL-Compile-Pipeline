"""Resource name filter -- reject schema/IR-looking variable names.

Phase 7: deterministic rejection of reserved names and IR field patterns
at the Stage 6 parse boundary, before they become business variables.
"""

from __future__ import annotations

import re

# Canonical reserved names -- exact match.
RESERVED_RESOURCE_NAMES: set[str] = {
    "span_id",
    "source_span_id",
    "source_span_ids",
    "source_section_id",
    "source_packet_id",
    "main_flow_spans",
    "exception_flows",
    "block_id",
    "flow_id",
    "step_id",
    "worker_id",
    "target_ref",
    "diagnostic_id",
}

# Prefixes / stems that indicate an IR/schema field when paired with
# a trailing separator.
_IR_STEMS: set[str] = {
    "span", "source", "block", "flow", "step", "worker",
    "target", "diagnostic", "exception",
}

_IR_SUFFIXES: set[str] = {
    "id", "ids", "ref", "span", "spans", "flow", "flows",
    "section_id", "packet_id",
}


def _normalize(name: str) -> str:
    """Normalise *name* for case- and separator-insensitive comparison."""
    return re.sub(r"[_\-]", "", name).lower()


def looks_like_ir_field(name: str) -> bool:
    """Return True when *name* resembles an IR/schema field.

    Heuristic: normalised form starts with an IR stem and ends with an
    IR suffix (e.g. ``span_id``, ``source-section-id``, ``StepID``).
    """
    norm = _normalize(name)
    for stem in _IR_STEMS:
        for suffix in _IR_SUFFIXES:
            if norm.startswith(stem) and norm.endswith(suffix):
                return True
    return False


def is_allowed_resource_variable(name: str) -> tuple[bool, str | None]:
    """Return ``(allowed, reason)``.

    *reason* is None when allowed, otherwise a short explanation for
    the rejection.
    """
    norm = _normalize(name)

    # Direct reserved-name match.
    if norm in {_normalize(r) for r in RESERVED_RESOURCE_NAMES}:
        return False, f"reserved IR/schema name: {name}"

    # Heuristic field-like pattern match.
    if looks_like_ir_field(name):
        return False, f"name resembles IR/schema field: {name}"

    return True, None
