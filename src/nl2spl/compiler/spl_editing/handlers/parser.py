"""Shared parser for LLM suggestion output.

Two parsing paths:

1. ``parse_suggestion_envelope()`` (R6)
   Parses the outer JSON envelope (patch_type, title, explanation) but does
   NOT validate the inner payload schema.  The handler routes the raw
   payload to either ``parse_raw_intent()`` (InsertProducerStep) or the
   legacy per-patch-type validators.

2. ``parse_suggestion_payload()`` (legacy)
   Full parse including inner payload schema validation via
   ``_validate_*_payload()``.  Used by handlers that have not yet migrated
   to the intent path.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from nl2spl.compiler.spl_editing.core.errors import (
    PatchValidationError,
    UnsupportedPatchTypeError,
)

# ---------------------------------------------------------------------------
# R6: Envelope DTO
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SuggestionEnvelope:
    """Parsed outer JSON envelope from LLM output.

    The inner ``raw_payload`` is NOT schema-validated 閳?the handler
    decides whether to route it to ``parse_raw_intent()`` (intent path)
    or a legacy ``_validate_*_payload()`` validator.
    """

    patch_type: str
    title: str
    explanation: str
    raw_payload: Any  # dict 閳?unvalidated


# ---------------------------------------------------------------------------
# Per-patch-type payload validators
# ---------------------------------------------------------------------------

_VALID_COMMAND_TYPES = frozenset(
    {
        "GENERAL_COMMAND",
        "REQUEST_INPUT",
        "DISPLAY_MESSAGE",
    }
)


def _validate_add_exception_handler_payload(payload: object) -> None:
    if not isinstance(payload, dict):
        raise PatchValidationError("AddExceptionHandlerStep payload must be a JSON object")
    handler_text = payload.get("handler_goal") or payload.get("handler_text")
    if not isinstance(handler_text, str) or not handler_text.strip():
        raise PatchValidationError(
            "AddExceptionHandlerStep payload requires a non-empty "
            "string 'handler_goal' or 'handler_text'"
        )
    command_type = payload.get("command_type")
    if command_type is not None:
        if not isinstance(command_type, str) or command_type not in _VALID_COMMAND_TYPES:
            raise PatchValidationError(
                f"AddExceptionHandlerStep payload 'command_type' must be "
                f"one of {sorted(_VALID_COMMAND_TYPES)}, got "
                f"{command_type!r}"
            )

        # Legacy per-command-type rules. R13+ prompts do not ask the LLM to
        # choose this field; when older tests or adapters provide it, validate it.
        if command_type == "DISPLAY_MESSAGE":
            if payload.get("outputs"):
                raise PatchValidationError("DISPLAY_MESSAGE must not have outputs")
            if payload.get("inputs"):
                raise PatchValidationError("DISPLAY_MESSAGE must not have inputs")
        elif command_type == "REQUEST_INPUT":
            if payload.get("inputs"):
                raise PatchValidationError("REQUEST_INPUT must not have inputs")
            outputs = payload.get("outputs", [])
            if not outputs or not isinstance(outputs, (list, tuple)) or len(outputs) == 0:
                raise PatchValidationError("REQUEST_INPUT must have at least one output")

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


def _validate_insert_producer_payload(payload: object) -> None:
    if not isinstance(payload, dict):
        raise PatchValidationError("InsertProducerStep payload must be a JSON object")
    producer_text = payload.get("producer_text")
    if not isinstance(producer_text, str) or not producer_text.strip():
        raise PatchValidationError(
            "InsertProducerStep payload requires a non-empty string 'producer_text'"
        )
    command_type = payload.get("command_type")
    if not isinstance(command_type, str) or command_type not in _VALID_COMMAND_TYPES:
        raise PatchValidationError(
            f"InsertProducerStep payload 'command_type' must be one of "
            f"{sorted(_VALID_COMMAND_TYPES)}, got {command_type!r}"
        )
    for field in ("inputs", "outputs"):
        val = payload.get(field)
        if val is not None:
            if not isinstance(val, (list, tuple)):
                raise PatchValidationError(
                    f"InsertProducerStep payload '{field}' must be a list of strings"
                )
            for i, item in enumerate(val):
                if not isinstance(item, str) or not item.strip():
                    raise PatchValidationError(
                        f"InsertProducerStep payload '{field}[{i}]' must be a non-empty string"
                    )


def _validate_convert_to_main_flow_payload(payload: object) -> None:
    if not isinstance(payload, dict):
        raise PatchValidationError(
            "ConvertDelegationIntentToMainFlowStep payload must be a JSON object"
        )
    action_text = payload.get("action_text")
    if not isinstance(action_text, str) or not action_text.strip():
        raise PatchValidationError(
            "ConvertDelegationIntentToMainFlowStep payload requires a non-empty "
            "string 'action_text'"
        )


def _validate_convert_to_request_input_payload(payload: object) -> None:
    if not isinstance(payload, dict):
        raise PatchValidationError(
            "ConvertDelegationIntentToRequestInput payload must be a JSON object"
        )
    prompt_text = payload.get("prompt_text")
    if not isinstance(prompt_text, str) or not prompt_text.strip():
        raise PatchValidationError(
            "ConvertDelegationIntentToRequestInput payload requires a non-empty "
            "string 'prompt_text'"
        )
    value_target = payload.get("value_target")
    if not isinstance(value_target, str) or not value_target.strip():
        raise PatchValidationError(
            "ConvertDelegationIntentToRequestInput payload requires a non-empty "
            "string 'value_target'"
        )


def _validate_create_handoff_payload(payload: object) -> None:
    if not isinstance(payload, dict):
        raise PatchValidationError("CreateWorkerHandoffContract payload must be a JSON object")

    def _side_valid(bindings, status, source, side_name):
        if not isinstance(bindings, dict):
            raise PatchValidationError(
                f"CreateWorkerHandoffContract payload '{side_name}_bindings' must be a JSON object"
            )
        if status == "known_empty":
            if not isinstance(source, str) or not source.strip():
                raise PatchValidationError(
                    f"CreateWorkerHandoffContract payload "
                    f"'{side_name}_binding_status'='known_empty' requires "
                    f"non-empty '{side_name}_binding_status_source'"
                )
            if bindings:
                raise PatchValidationError(
                    f"CreateWorkerHandoffContract payload "
                    f"'{side_name}_binding_status'='known_empty' requires "
                    f"empty '{side_name}_bindings'"
                )
            return  # known_empty + source 閳?empty bindings allowed
        if not bindings:
            raise PatchValidationError(
                f"CreateWorkerHandoffContract payload requires a non-empty "
                f"object '{side_name}_bindings'"
            )

    in_status = payload.get("input_binding_status", "known_present")
    out_status = payload.get("output_binding_status", "known_present")
    for side, status in [("input", in_status), ("output", out_status)]:
        if status not in {"known_present", "known_empty"}:
            raise PatchValidationError(
                f"CreateWorkerHandoffContract payload '{side}_binding_status' "
                f"must be 'known_present' or 'known_empty', got '{status}'"
            )
    in_source = payload.get("input_binding_status_source")
    out_source = payload.get("output_binding_status_source")

    _side_valid(payload.get("input_bindings"), in_status, in_source, "input")
    _side_valid(payload.get("output_bindings"), out_status, out_source, "output")
    invocation_point = payload.get("invocation_point")
    if not isinstance(invocation_point, str) or not invocation_point.strip():
        raise PatchValidationError(
            "CreateWorkerHandoffContract payload requires a non-empty string 'invocation_point'"
        )
    if invocation_point not in {"main", "alternative", "exception"}:
        raise PatchValidationError(
            "CreateWorkerHandoffContract payload 'invocation_point' must be one of: "
            "main, alternative, exception"
        )


_PAYLOAD_VALIDATORS: dict[str, Any] = {
    "AddExceptionHandlerStep": _validate_add_exception_handler_payload,
    "InsertProducerStep": _validate_insert_producer_payload,
    "ConvertDelegationIntentToMainFlowStep": _validate_convert_to_main_flow_payload,
    "ConvertDelegationIntentToRequestInput": _validate_convert_to_request_input_payload,
    "CreateWorkerHandoffContract": _validate_create_handoff_payload,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_suggestion_envelope(
    raw: str,
    allowed_patch_types: tuple[str, ...],
) -> SuggestionEnvelope:
    """Parse the outer JSON envelope only 閳?no inner payload validation.

    The caller is responsible for routing ``raw_payload`` to the correct
    validator: ``parse_raw_intent()`` for intent-aware patch types, or a
    legacy ``_validate_*_payload()`` for types that have not migrated yet.

    Args:
        raw: Raw LLM output string (JSON expected).
        allowed_patch_types: Patch types allowed by the catalog entry.

    Returns:
        A ``SuggestionEnvelope`` with unvalidated ``raw_payload``.

    Raises:
        UnsupportedPatchTypeError: If ``patch_type`` is not in
            *allowed_patch_types*.
        PatchValidationError: If JSON is malformed, type mismatches, or
            required keys (patch_type / title / explanation / payload)
            are missing or invalid.
    """
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise PatchValidationError(f"Failed to parse LLM output as JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise PatchValidationError("LLM output must be a JSON object")

    patch_type = data.get("patch_type")
    if not isinstance(patch_type, str):
        raise PatchValidationError("Missing or invalid 'patch_type' in LLM output")

    if patch_type not in allowed_patch_types:
        raise UnsupportedPatchTypeError(
            f"LLM returned patch_type '{patch_type}', which is not in "
            f"the allowed set: {sorted(allowed_patch_types)}"
        )

    for required_key in ("title", "explanation", "payload"):
        if required_key not in data:
            raise PatchValidationError(f"LLM output missing required key '{required_key}'")

    for field in ("title", "explanation"):
        val = data.get(field)
        if not isinstance(val, str) or not val.strip():
            raise PatchValidationError(f"LLM output '{field}' must be a non-empty string")

    raw_payload = data["payload"]
    if not isinstance(raw_payload, dict):
        raise PatchValidationError("LLM output 'payload' must be a JSON object")

    return SuggestionEnvelope(
        patch_type=patch_type,
        title=str(data["title"]).strip(),
        explanation=str(data["explanation"]).strip(),
        raw_payload=raw_payload,
    )


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
        raise PatchValidationError(f"Failed to parse LLM output as JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise PatchValidationError("LLM output must be a JSON object")

    patch_type = data.get("patch_type")
    if not isinstance(patch_type, str):
        raise PatchValidationError("Missing or invalid 'patch_type' in LLM output")

    if patch_type not in allowed_patch_types:
        raise UnsupportedPatchTypeError(
            f"LLM returned patch_type '{patch_type}', which is not in "
            f"the allowed set: {sorted(allowed_patch_types)}"
        )

    for required_key in ("title", "explanation", "payload"):
        if required_key not in data:
            raise PatchValidationError(f"LLM output missing required key '{required_key}'")

    # Validate title / explanation are non-empty strings
    for field in ("title", "explanation"):
        val = data.get(field)
        if not isinstance(val, str) or not val.strip():
            raise PatchValidationError(f"LLM output '{field}' must be a non-empty string")

    # Validate payload schema per patch type
    validator = _PAYLOAD_VALIDATORS.get(patch_type)
    if validator is not None:
        validator(data["payload"])

    return data
