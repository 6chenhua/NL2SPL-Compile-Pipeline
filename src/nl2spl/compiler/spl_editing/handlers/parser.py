"""Shared parser for LLM suggestion output.

The parser flow is:
    raw LLM output → parse JSON → reject unsupported patch_type
    against allowed_patch_types → validate payload schema → return.
"""

from __future__ import annotations

import json
from typing import Any

from nl2spl.compiler.spl_editing.core.errors import (
    PatchValidationError,
    UnsupportedPatchTypeError,
)

# ---------------------------------------------------------------------------
# Per-patch-type payload validators
# ---------------------------------------------------------------------------

_VALID_COMMAND_TYPES = frozenset({
    "GENERAL_COMMAND", "REQUEST_INPUT", "DISPLAY_MESSAGE",
})


def _validate_add_exception_handler_payload(payload: object) -> None:
    if not isinstance(payload, dict):
        raise PatchValidationError(
            "AddExceptionHandlerStep payload must be a JSON object"
        )
    handler_text = payload.get("handler_text")
    if not isinstance(handler_text, str) or not handler_text.strip():
        raise PatchValidationError(
            "AddExceptionHandlerStep payload requires a non-empty "
            "string 'handler_text'"
        )
    command_type = payload.get("command_type")
    if not isinstance(command_type, str) or command_type not in _VALID_COMMAND_TYPES:
        raise PatchValidationError(
            f"AddExceptionHandlerStep payload 'command_type' must be "
            f"one of {sorted(_VALID_COMMAND_TYPES)}, got "
            f"{command_type!r}"
        )
    for field in ("inputs", "outputs"):
        val = payload.get(field)
        if val is not None:
            if not isinstance(val, (list, tuple)):
                raise PatchValidationError(
                    f"AddExceptionHandlerStep payload '{field}' must be "
                    f"a list of strings when present"
                )
            for i, item in enumerate(val):
                if not isinstance(item, str) or not item.strip():
                    raise PatchValidationError(
                        f"AddExceptionHandlerStep payload '{field}[{i}]' "
                        f"must be a non-empty string, got {item!r}"
                    )


_PAYLOAD_VALIDATORS: dict[str, Any] = {
    "AddExceptionHandlerStep": _validate_add_exception_handler_payload,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_suggestion_payload(
    raw: str,
    allowed_patch_types: tuple[str, ...],
) -> dict[str, Any]:
    """Parse LLM output into a typed suggestion payload dictionary.

    Args:
        raw: Raw LLM output string (JSON expected).
        allowed_patch_types: Patch types allowed by the catalog entry.

    Returns:
        A dict with at least ``patch_type``, ``title``, ``explanation``,
        and ``payload`` keys.

    Raises:
        UnsupportedPatchTypeError: If the parsed ``patch_type`` is not in
            *allowed_patch_types*.
        PatchValidationError: If the payload does not match the schema
            for the declared patch type.
        ValueError: If the JSON is malformed or required keys are missing.
    """
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise PatchValidationError(
            f"Failed to parse LLM output as JSON: {exc}"
        ) from exc

    if not isinstance(data, dict):
        raise PatchValidationError("LLM output must be a JSON object")

    patch_type = data.get("patch_type")
    if not isinstance(patch_type, str):
        raise PatchValidationError(
            "Missing or invalid 'patch_type' in LLM output"
        )

    if patch_type not in allowed_patch_types:
        raise UnsupportedPatchTypeError(
            f"LLM returned patch_type '{patch_type}', which is not in "
            f"the allowed set: {sorted(allowed_patch_types)}"
        )

    for required_key in ("title", "explanation", "payload"):
        if required_key not in data:
            raise PatchValidationError(
                f"LLM output missing required key '{required_key}'"
            )

    # Validate title / explanation are non-empty strings
    for field in ("title", "explanation"):
        val = data.get(field)
        if not isinstance(val, str) or not val.strip():
            raise PatchValidationError(
                f"LLM output '{field}' must be a non-empty string"
            )

    # Validate payload schema per patch type
    validator = _PAYLOAD_VALIDATORS.get(patch_type)
    if validator is not None:
        validator(data["payload"])

    return data
