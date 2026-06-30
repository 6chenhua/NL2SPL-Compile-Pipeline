"""Stage 6 API declaration materialization for source-backed capability demands."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from nl2spl.compiler.capability_intent.name_resolver import CapabilityNameResolverV1
from nl2spl.compiler.construct_plan import APIDeclarationDemand, ConstructPlan
from nl2spl.ir.resource_registry_ir import APISpec, ResourceRegistryIR
from nl2spl.ir.structured_text_ir import StructuredTextIR


@dataclass(frozen=True)
class APICallBindingIR:
    """Binding between a declaration demand and its materialized APISpec."""

    api_binding_id: str
    declaration_demand_id: str
    api_id: str
    api_name: str
    call_demand_ids: list[str] = field(default_factory=list)
    binding_status: str = "bound"
    source_span_ids: list[str] = field(default_factory=list)

    def to_payload(self) -> dict[str, Any]:
        return {
            "api_binding_id": self.api_binding_id,
            "declaration_demand_id": self.declaration_demand_id,
            "api_id": self.api_id,
            "api_name": self.api_name,
            "call_demand_ids": list(self.call_demand_ids),
            "binding_status": self.binding_status,
            "source_span_ids": list(self.source_span_ids),
        }


@dataclass(frozen=True)
class APIMaterializationRecordIR:
    """Demand-level API declaration materialization and renderability record."""

    declaration_demand_id: str
    capability_intent_id: str | None = None
    api_id: str | None = None
    api_name: str | None = None
    materialization_status: str = "unsupported"
    renderability_status: str = "blocked"
    name_status: str = "missing"
    auth_status: str = "defaulted_none"
    schema_status: str = "unknown_placeholder"
    functions_status: str = "unknown_placeholder"
    reasons: list[str] = field(default_factory=list)
    source_span_ids: list[str] = field(default_factory=list)

    def to_payload(self) -> dict[str, Any]:
        return {
            "declaration_demand_id": self.declaration_demand_id,
            "capability_intent_id": self.capability_intent_id,
            "api_id": self.api_id,
            "api_name": self.api_name,
            "materialization_status": self.materialization_status,
            "renderability_status": self.renderability_status,
            "name_status": self.name_status,
            "auth_status": self.auth_status,
            "schema_status": self.schema_status,
            "functions_status": self.functions_status,
            "reasons": list(self.reasons),
            "source_span_ids": list(self.source_span_ids),
        }


@dataclass(frozen=True)
class APIMaterializationPlanIR:
    """Stage 6 API materialization plan.

    The plan records partial declaration skeletons and call bindings. It is not
    render authority; post-normalize API_DECLARATION reports own that later.
    """

    plan_id: str = "api_materialization_plan_00"
    api_specs: list[APISpec] = field(default_factory=list)
    bindings: list[APICallBindingIR] = field(default_factory=list)
    records: list[APIMaterializationRecordIR] = field(default_factory=list)
    unsupported_declaration_demand_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "api_specs": [_api_spec_payload(api) for api in self.api_specs],
            "bindings": [binding.to_payload() for binding in self.bindings],
            "records": [record.to_payload() for record in self.records],
            "unsupported_declaration_demand_ids": list(self.unsupported_declaration_demand_ids),
            "metadata": dict(sorted(self.metadata.items())),
        }


def materialize_api_declaration_skeletons(
    resources: ResourceRegistryIR,
    construct_plan: ConstructPlan,
) -> APIMaterializationPlanIR:
    """Create partial APISpec skeletons for source-backed declarations."""
    specs: list[APISpec] = []
    bindings: list[APICallBindingIR] = []
    records: list[APIMaterializationRecordIR] = []
    unsupported: list[str] = []
    name_resolver = CapabilityNameResolverV1()
    identity_diagnostics = _canonicalize_existing_apis(resources)
    existing_apis_by_id = {api.api_id: api for api in resources.apis}
    existing_apis_by_name = {api.api_name: api for api in resources.apis if api.api_name}
    existing_names = {api.api_name for api in resources.apis if api.api_name}
    calls_by_declaration: dict[str, list[str]] = {}
    for call in construct_plan.api_call_demands():
        if call.declaration_demand_id:
            calls_by_declaration.setdefault(
                call.declaration_demand_id,
                [],
            ).append(call.demand_id)

    for declaration in construct_plan.api_declaration_demands():
        resolved_name = _api_name_for_declaration(
            declaration,
            existing_names=existing_names,
            name_resolver=name_resolver,
        )
        if resolved_name is None:
            unsupported.append(declaration.demand_id)
            records.append(
                _record(
                    declaration,
                    materialization_status="unsupported",
                    renderability_status="blocked",
                    reasons=["api_name_not_source_backed_or_not_resolvable"],
                )
            )
            continue

        api_name, name_status = resolved_name
        if not _is_valid_api_name(api_name):
            unsupported.append(declaration.demand_id)
            records.append(
                _record(
                    declaration,
                    api_name=api_name,
                    materialization_status="unsupported",
                    renderability_status="blocked",
                    name_status="invalid",
                    reasons=["api_name_not_grammar_safe"],
                )
            )
            continue

        api_id = _canonical_api_id(api_name)
        api = existing_apis_by_id.get(api_id) or existing_apis_by_name.get(api_name)
        materialization_status = "already_declared"
        if api is None:
            api = _partial_api_spec(api_name, api_id, declaration, name_status)
            resources.apis.append(api)
            specs.append(api)
            existing_apis_by_id[api_id] = api
            existing_apis_by_name[api_name] = api
            existing_names.add(api_name)
            materialization_status = "materialized_grammar_minimal_partial"
        else:
            api.api_id = api_id
            _attach_declaration_provenance(api, declaration)

        bindings.append(
            APICallBindingIR(
                api_binding_id=f"api_binding:{declaration.demand_id}",
                declaration_demand_id=declaration.demand_id,
                api_id=api_id,
                api_name=api_name,
                call_demand_ids=calls_by_declaration.get(declaration.demand_id, []),
                source_span_ids=list(declaration.source_span_ids),
            )
        )
        records.append(
            _record(
                declaration,
                api_id=api_id,
                api_name=api_name,
                materialization_status=materialization_status,
                renderability_status="requires_post_normalize_gate",
                name_status=name_status,
                reasons=_partial_reasons_for_api(api),
                api=api,
            )
        )

    return APIMaterializationPlanIR(
        api_specs=specs,
        bindings=bindings,
        records=records,
        unsupported_declaration_demand_ids=unsupported,
        metadata={
            "stage": "stage6_resource_extractor",
            "authority": "api_declaration_materializer",
            "name_resolver": CapabilityNameResolverV1.version,
            "identity_diagnostics": identity_diagnostics,
        },
    )


def _partial_api_spec(
    api_name: str,
    api_id: str,
    declaration: APIDeclarationDemand,
    name_status: str,
) -> APISpec:
    return APISpec(
        api_name=api_name,
        api_id=api_id,
        auth="none",
        description=f"Partial API declaration skeleton for {api_name}.",
        functions=[],
        openapi_schema=StructuredTextIR("empty_placeholder", "{}"),
        source_span_ids=list(declaration.source_span_ids),
        source_annotation_ids=list(declaration.declaration_annotation_ids),
        declaration_demand_ids=[declaration.demand_id],
        origin="source_backed",
        declaration_status="grammar_minimal_partial",
        name_status=name_status,  # type: ignore[arg-type]
        auth_status="compiler_default_none",
        schema_status="unknown_placeholder",
        functions_status="unknown_placeholder",
        partial_reasons=[
            "openapi_schema_unknown",
            "functions_unknown",
        ],
    )


def _api_name_for_declaration(
    declaration: APIDeclarationDemand,
    *,
    existing_names: set[str],
    name_resolver: CapabilityNameResolverV1,
) -> tuple[str, str] | None:
    if declaration.integration_admission != "confirmed":
        return None
    explicit_name = _explicit_api_name(declaration)
    if explicit_name:
        return explicit_name, "explicit_source_name"
    if not declaration.inferred_name_allowed:
        return None
    if declaration.mechanism_status != "concrete_unnamed":
        return None
    capability_surface = declaration.capability_surface or ""
    if not capability_surface.strip():
        return None
    operation_text = str(declaration.metadata.get("operation_text") or capability_surface)
    capability_intent_id = declaration.capability_intent_id or declaration.demand_id
    return (
        name_resolver.resolve(
            capability_intent_id=capability_intent_id,
            capability_surface=capability_surface,
            operation_text=operation_text,
            existing_names=existing_names,
        ),
        "inferred_from_source",
    )


def _explicit_api_name(declaration: APIDeclarationDemand) -> str | None:
    if declaration.mechanism_status != "explicit":
        return None
    for candidate in declaration.explicit_name_candidates:
        if candidate:
            return candidate
    return None


def _record(
    declaration: APIDeclarationDemand,
    *,
    api_id: str | None = None,
    api_name: str | None = None,
    materialization_status: str,
    renderability_status: str,
    name_status: str = "missing",
    reasons: list[str] | None = None,
    api: APISpec | None = None,
) -> APIMaterializationRecordIR:
    return APIMaterializationRecordIR(
        declaration_demand_id=declaration.demand_id,
        capability_intent_id=declaration.capability_intent_id,
        api_id=api_id,
        api_name=api_name,
        materialization_status=materialization_status,
        renderability_status=renderability_status,
        name_status=name_status,
        auth_status=_record_auth_status(api),
        schema_status=api.schema_status if api else "unknown_placeholder",
        functions_status=api.functions_status if api else "unknown_placeholder",
        reasons=list(reasons or []),
        source_span_ids=list(declaration.source_span_ids),
    )


def _canonical_api_id(api_name: str) -> str:
    return f"api:{api_name}"


def _canonicalize_existing_apis(resources: ResourceRegistryIR) -> list[str]:
    """Normalize API identity and merge duplicate names without inventing contracts."""
    diagnostics: list[str] = []
    by_name: dict[str, APISpec] = {}
    canonical: list[APISpec] = []
    for api in resources.apis:
        if not api.api_name:
            canonical.append(api)
            continue
        canonical_id = _canonical_api_id(api.api_name)
        if api.api_id != canonical_id:
            diagnostics.append(f"normalized_api_id:{api.api_id or '<empty>'}->{canonical_id}")
            api.api_id = canonical_id
        existing = by_name.get(api.api_name)
        if existing is None:
            by_name[api.api_name] = api
            canonical.append(api)
            continue
        _merge_api_provenance(existing, api)
        diagnostics.append(f"merged_duplicate_api_name:{api.api_name}")
        if _api_contract_signature(existing) != _api_contract_signature(api):
            diagnostics.append(f"conflicting_duplicate_api_contract:{api.api_name}")
    resources.apis[:] = canonical
    return diagnostics


def _attach_declaration_provenance(
    api: APISpec,
    declaration: APIDeclarationDemand,
) -> None:
    api.source_span_ids = list(dict.fromkeys([*api.source_span_ids, *declaration.source_span_ids]))
    api.source_annotation_ids = list(
        dict.fromkeys([*api.source_annotation_ids, *declaration.declaration_annotation_ids])
    )
    api.declaration_demand_ids = list(
        dict.fromkeys([*api.declaration_demand_ids, declaration.demand_id])
    )


def _merge_api_provenance(target: APISpec, duplicate: APISpec) -> None:
    target.source_span_ids = list(
        dict.fromkeys([*target.source_span_ids, *duplicate.source_span_ids])
    )
    target.source_annotation_ids = list(
        dict.fromkeys([*target.source_annotation_ids, *duplicate.source_annotation_ids])
    )
    target.declaration_demand_ids = list(
        dict.fromkeys([*target.declaration_demand_ids, *duplicate.declaration_demand_ids])
    )
    target.auth_source_span_ids = list(
        dict.fromkeys([*target.auth_source_span_ids, *duplicate.auth_source_span_ids])
    )


def _api_contract_signature(api: APISpec) -> tuple[object, ...]:
    return (
        api.auth,
        api.auth_status,
        api.openapi_schema.format,
        api.openapi_schema.canonical_text,
        api.schema_status,
        api.functions_status,
        tuple(function.name for function in api.functions),
    )


def _record_auth_status(api: APISpec | None) -> str:
    if api is None or api.auth_status == "compiler_default_none":
        return "defaulted_none"
    if api.auth_status == "unresolved":
        return "unresolved"
    return "explicit"


def _partial_reasons_for_api(api: APISpec) -> list[str]:
    reasons: list[str] = []
    if api.auth_status == "unresolved":
        reasons.append("authentication_unresolved")
    if api.schema_status == "unknown_placeholder":
        reasons.append("openapi_schema_unknown")
    if api.functions_status == "unknown_placeholder":
        reasons.append("functions_unknown")
    if api.declaration_status == "partial_blocked":
        reasons.append("placeholder_rendering_not_approved")
    return reasons


def _is_valid_api_name(api_name: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", api_name))


def _api_spec_payload(api: APISpec) -> dict[str, Any]:
    return {
        "api_id": api.api_id,
        "api_name": api.api_name,
        "auth": api.auth,
        "description": api.description,
        "functions": [],
        "source_span_ids": list(api.source_span_ids),
        "source_annotation_ids": list(api.source_annotation_ids),
        "declaration_demand_ids": list(api.declaration_demand_ids),
        "origin": api.origin,
        "declaration_status": api.declaration_status,
        "name_status": api.name_status,
        "auth_status": api.auth_status,
        "auth_evidence_authority": api.auth_evidence_authority,
        "auth_source_span_ids": list(api.auth_source_span_ids),
        "schema_status": api.schema_status,
        "functions_status": api.functions_status,
        "partial_reasons": list(api.partial_reasons),
        "openapi_schema": {
            "format": api.openapi_schema.format,
            "canonical_text": api.openapi_schema.canonical_text,
            "parsed_value": api.openapi_schema.parsed_value,
        },
    }
