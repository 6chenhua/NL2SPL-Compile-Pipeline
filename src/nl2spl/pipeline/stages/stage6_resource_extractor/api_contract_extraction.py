"""Source-backed API contract projection owned by Stage 6 extraction."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from nl2spl.ir.resource_registry_ir import APIFunction, APISpec

AUTH_EVIDENCE_AUTHORITY = "stage6_api_contract_extractor"
LANGUAGE_DEFAULT_AUTHORITY = "spl_language_default"


def api_spec_from_extracted_contract(
    api_data: Mapping[str, Any],
    *,
    valid_source_span_ids: Iterable[str] = (),
) -> APISpec:
    """Project Stage 6 structured output without defaulting unresolved auth."""
    valid_ids = set(valid_source_span_ids)
    source_span_ids = [
        span_id
        for span_id in api_data.get("source_span_ids", [])
        if isinstance(span_id, str) and span_id in valid_ids
    ]
    auth_source_span_ids = [
        span_id
        for span_id in api_data.get("authentication_source_span_ids", [])
        if isinstance(span_id, str) and span_id in valid_ids
    ]
    auth, auth_status, auth_authority = _authentication(
        api_data,
        auth_source_span_ids=auth_source_span_ids,
    )
    functions = [
        APIFunction(
            name=function_data["name"],
            description=function_data.get("description", ""),
            parameters=function_data.get("parameters", []),
            return_type=function_data.get("return_type", "text"),
        )
        for function_data in api_data.get("functions", [])
    ]
    return APISpec(
        api_name=api_data["api_name"],
        auth=auth,
        description=api_data.get("description", ""),
        functions=functions,
        source_span_ids=list(dict.fromkeys([*source_span_ids, *auth_source_span_ids])),
        auth_status=auth_status,  # type: ignore[arg-type]
        auth_evidence_authority=auth_authority,
        auth_source_span_ids=list(dict.fromkeys(auth_source_span_ids)),
        functions_status="known_present" if functions else "unknown_placeholder",
        declaration_status="partial_blocked",
    )


def _authentication(
    api_data: Mapping[str, Any],
    *,
    auth_source_span_ids: list[str],
) -> tuple[str, str, str]:
    status = api_data.get("authentication_status", "unmentioned")
    auth = api_data.get("auth", "none")
    if status == "unresolved":
        return "unresolved", "unresolved", AUTH_EVIDENCE_AUTHORITY
    if status == "explicit":
        if not auth_source_span_ids or auth not in {"none", "apikey", "oauth"}:
            return "unresolved", "unresolved", AUTH_EVIDENCE_AUTHORITY
        return str(auth), "source_backed", AUTH_EVIDENCE_AUTHORITY
    # A missing authentication mention is the only case that receives the
    # language default. The extractor must never map an explicit unknown
    # requirement to this branch.
    return "none", "compiler_default_none", LANGUAGE_DEFAULT_AUTHORITY
