"""Pure grammar validation for materialized API declarations."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Literal

from nl2spl.ir.resource_registry_ir import APIFunction, APISpec
from nl2spl.ir.structured_text_ir import StructuredTextIR

API_NAME_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
ALLOWED_AUTH = frozenset({"none", "apikey", "oauth"})

APIGrammarStatus = Literal[
    "grammar_minimal_partial",
    "partial_blocked",
    "complete",
]


@dataclass(frozen=True)
class APIDeclarationGrammarResult:
    """Validation result consumed by IRS and ResourceDeclarationGate."""

    status: APIGrammarStatus
    grammar_valid: bool
    name_valid: bool
    auth_valid: bool
    schema_valid: bool
    functions_valid: bool
    reasons: tuple[str, ...] = ()


def validate_api_declaration(api: APISpec) -> APIDeclarationGrammarResult:
    """Validate grammar shape without repairing or defaulting the APISpec."""
    name_valid = isinstance(api.api_name, str) and bool(API_NAME_PATTERN.fullmatch(api.api_name))
    auth_valid = isinstance(api.auth, str) and api.auth in ALLOWED_AUTH
    schema_valid = _valid_structured_text(api.openapi_schema)
    functions_valid = _valid_functions(api)

    reasons: list[str] = []
    if not name_valid:
        reasons.append("api_name_not_grammar_safe")
    if not auth_valid:
        reasons.append("authentication_not_grammar_safe")
    if getattr(api, "auth_status", None) == "unresolved":
        auth_valid = False
        reasons.append("authentication_unresolved")
    if not schema_valid:
        reasons.append("openapi_schema_not_structured_text")
    if not functions_valid:
        reasons.append("functions_not_grammar_safe")

    grammar_valid = name_valid and auth_valid and schema_valid and functions_valid
    has_unknown_placeholder = (
        api.schema_status == "unknown_placeholder" or api.functions_status == "unknown_placeholder"
    )
    semantic_contract_complete = (
        api.auth_status != "unresolved"
        and api.schema_status in {"known_present", "known_empty"}
        and api.functions_status in {"known_present", "known_empty"}
    )

    if grammar_valid and semantic_contract_complete and api.declaration_status == "complete":
        status: APIGrammarStatus = "complete"
    elif (
        grammar_valid
        and has_unknown_placeholder
        and api.declaration_status == "grammar_minimal_partial"
    ):
        # This state must be assigned only after the external D-CAP-0 policy
        # approves placeholder rendering. The validator never upgrades a
        # partial declaration into this state by itself.
        status = "grammar_minimal_partial"
    else:
        status = "partial_blocked"
        if grammar_valid and has_unknown_placeholder:
            reasons.append("placeholder_rendering_not_approved")
        elif grammar_valid and not semantic_contract_complete:
            reasons.append("api_contract_incomplete")

    return APIDeclarationGrammarResult(
        status=status,
        grammar_valid=grammar_valid,
        name_valid=name_valid,
        auth_valid=auth_valid,
        schema_valid=schema_valid,
        functions_valid=functions_valid,
        reasons=tuple(dict.fromkeys(reasons)),
    )


def _valid_structured_text(value: object) -> bool:
    if not isinstance(value, StructuredTextIR):
        return False
    if value.format not in {"json_object", "structured_text", "empty_placeholder"}:
        return False
    text = value.canonical_text
    if not isinstance(text, str) or not text.strip():
        return False
    if value.format in {"json_object", "empty_placeholder"}:
        try:
            parsed = json.loads(text)
        except (TypeError, ValueError):
            return False
        if not isinstance(parsed, dict):
            return False
        return value.format != "empty_placeholder" or parsed == {}
    stripped = text.strip()
    return stripped.startswith("{") and stripped.endswith("}")


def _valid_functions(api: APISpec) -> bool:
    if not isinstance(api.functions, list):
        return False
    if api.functions_status == "known_empty":
        return not api.functions
    if api.functions_status == "known_present" and not api.functions:
        return False
    if api.functions_status == "unknown_placeholder" and api.functions:
        return False
    if api.functions_status not in {
        "known_empty",
        "known_present",
        "unknown_placeholder",
    }:
        return False
    return all(_valid_function(function) for function in api.functions)


def _valid_function(function: object) -> bool:
    if not isinstance(function, APIFunction):
        return False
    if not isinstance(function.name, str) or not function.name:
        return False
    if not isinstance(function.description, str):
        return False
    if not isinstance(function.parameters, list):
        return False
    if not isinstance(function.return_type, str) or not function.return_type:
        return False
    for parameter in function.parameters:
        if not isinstance(parameter, dict):
            return False
        if not isinstance(parameter.get("name"), str) or not parameter["name"]:
            return False
        parameter_type = parameter.get("type", parameter.get("data_type"))
        if not isinstance(parameter_type, str) or not parameter_type:
            return False
        required = parameter.get("required")
        if required is not None and not isinstance(required, bool):
            return False
    return True
