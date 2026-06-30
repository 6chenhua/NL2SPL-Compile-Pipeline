"""API-related snapshot serializer tests."""

from __future__ import annotations

import json

from nl2spl.compiler.artifacts.snapshot.serialization.registry import (
    get_default_registry,
)
from nl2spl.compiler.artifacts.snapshot.serialization.serializers_resource import (
    APIFunctionSerializer,
    APISpecSerializer,
    StructuredTextIRSerializer,
)
from nl2spl.ir.resource_registry_ir import (
    APIFunction,
    APIParameterSpec,
    APIReturnSpec,
    APISpec,
)
from nl2spl.ir.structured_text_ir import StructuredTextIR
from nl2spl.pipeline.stages.stage6_resource_extractor.api_materialization import (
    APICallBindingIR,
    APIMaterializationPlanIR,
)


class TestAPISpecSerializers:
    """Unit tests for resource API snapshot serializers."""

    def test_structured_text_ir_empty_placeholder_roundtrip(self) -> None:
        """Verify StructuredTextIR(empty_placeholder) serializer roundtrip."""
        serializer = StructuredTextIRSerializer()
        st = StructuredTextIR(format="empty_placeholder", canonical_text="{}")

        canonical = serializer.to_canonical(st)
        assert canonical["$type"] == "StructuredTextIR"
        assert canonical["format"] == "empty_placeholder"
        assert canonical["canonical_text"] == "{}"

        restored: StructuredTextIR = serializer.from_canonical(canonical)
        assert restored.format == "empty_placeholder"
        assert restored.canonical_text == "{}"

    def test_structured_text_ir_json_object_roundtrip(self) -> None:
        """Verify StructuredTextIR(json_object) serializer roundtrip."""
        serializer = StructuredTextIRSerializer()
        st = StructuredTextIR(
            format="json_object",
            canonical_text='{"title": "PetStore API"}',
            parsed_value={"title": "PetStore API"},
        )

        canonical = serializer.to_canonical(st)
        assert canonical["format"] == "json_object"
        assert canonical["parsed_value"] == {"title": "PetStore API"}

        restored: StructuredTextIR = serializer.from_canonical(canonical)
        assert restored.format == "json_object"
        assert restored.parsed_value == {"title": "PetStore API"}

    def test_default_registry_roundtrip(self) -> None:
        """Verify default registry roundtrip for API snapshot types."""
        registry = get_default_registry()
        st = StructuredTextIR(
            format="json_object",
            canonical_text='{"k": "v"}',
            parsed_value={"k": "v"},
        )

        canonical_st = registry.serialize(st)
        assert canonical_st["$type"] == "StructuredTextIR"
        restored_st = registry.deserialize(canonical_st)
        assert isinstance(restored_st, StructuredTextIR)
        assert restored_st.parsed_value == {"k": "v"}

        param_spec = APIParameterSpec(
            name="param1",
            data_type="string",
            required=True,
            description="desc",
        )
        canonical_p = registry.serialize(param_spec)
        assert canonical_p["$type"] == "APIParameterSpec"
        restored_p = registry.deserialize(canonical_p)
        assert isinstance(restored_p, APIParameterSpec)
        assert restored_p.name == "param1"

        ret_spec = APIReturnSpec(data_type="json", controlled_output=True, description="ret desc")
        canonical_r = registry.serialize(ret_spec)
        assert canonical_r["$type"] == "APIReturnSpec"
        restored_r = registry.deserialize(canonical_r)
        assert isinstance(restored_r, APIReturnSpec)
        assert restored_r.controlled_output is True

        spec = APISpec(
            api_name="RegAPI",
            auth="apikey",
            description="Registry test API",
            openapi_schema=st,
        )
        canonical_spec = registry.serialize(spec)
        assert canonical_spec["$type"] == "APISpec"
        restored_spec = registry.deserialize(canonical_spec)
        assert isinstance(restored_spec, APISpec)
        assert restored_spec.api_name == "RegAPI"

    def test_api_materialization_plan_roundtrip_preserves_partial_status(self) -> None:
        registry = get_default_registry()
        api = APISpec(
            api_name="SearchAPI",
            auth="none",
            description="Partial API declaration skeleton for SearchAPI.",
            api_id="api:SearchAPI",
            source_span_ids=["s_api"],
            declaration_demand_ids=["api_decl_search"],
            declaration_status="partial_blocked",
            schema_status="unknown_placeholder",
            functions_status="unknown_placeholder",
        )
        plan = APIMaterializationPlanIR(
            api_specs=[api],
            bindings=[
                APICallBindingIR(
                    api_binding_id="api_binding:api_decl_search",
                    declaration_demand_id="api_decl_search",
                    api_id="api:SearchAPI",
                    api_name="SearchAPI",
                    call_demand_ids=["api_call_search"],
                    source_span_ids=["s_api"],
                )
            ],
            metadata={"authority": "api_declaration_materializer"},
        )

        canonical = registry.serialize(plan)
        restored = registry.deserialize(canonical)

        assert isinstance(restored, APIMaterializationPlanIR)
        assert restored.api_specs[0].declaration_status == "partial_blocked"
        assert restored.api_specs[0].schema_status == "unknown_placeholder"
        assert restored.api_specs[0].functions_status == "unknown_placeholder"
        assert restored.bindings[0].api_binding_id == "api_binding:api_decl_search"
        assert restored.bindings[0].call_demand_ids == ["api_call_search"]

    def test_api_materialization_plan_roundtrip_preserves_deferred_placeholder_status(
        self,
    ) -> None:
        registry = get_default_registry()
        api = APISpec(
            api_name="SearchAPI",
            auth="none",
            description="Renderable placeholder API declaration for SearchAPI.",
            api_id="api:SearchAPI",
            source_span_ids=["s_api"],
            declaration_demand_ids=["api_decl_search"],
            declaration_status="grammar_minimal_partial",
            schema_status="unknown_placeholder",
            functions_status="unknown_placeholder",
            openapi_schema=StructuredTextIR(
                format="empty_placeholder",
                canonical_text="{}",
            ),
            functions=[],
        )
        plan = APIMaterializationPlanIR(
            api_specs=[api],
            bindings=[
                APICallBindingIR(
                    api_binding_id="api_binding:api_decl_search",
                    declaration_demand_id="api_decl_search",
                    api_id="api:SearchAPI",
                    api_name="SearchAPI",
                    call_demand_ids=["api_call_search"],
                    source_span_ids=["s_api"],
                )
            ],
            metadata={"authority": "api_declaration_materializer"},
        )

        canonical = registry.serialize(plan)
        restored = registry.deserialize(canonical)

        assert isinstance(restored, APIMaterializationPlanIR)
        restored_api = restored.api_specs[0]
        assert restored_api.declaration_status == "grammar_minimal_partial"
        assert restored_api.schema_status == "unknown_placeholder"
        assert restored_api.functions_status == "unknown_placeholder"
        assert restored_api.openapi_schema.format == "empty_placeholder"
        assert restored_api.openapi_schema.canonical_text == "{}"
        assert restored_api.functions == []

    def test_legacy_api_spec_migration_contract(self) -> None:
        """Verify legacy canonical data deserialization infers status fields."""
        legacy_canonical = {
            "$type": "APISpec",
            "api_name": "LegacySearch",
            "auth": "apikey",
            "description": "Legacy search service",
            "functions": [
                {
                    "$type": "APIFunction",
                    "name": "search",
                    "description": "Search items",
                    "parameters": [],
                    "return_type": "text",
                }
            ],
            "openapi_schema": {"paths": {"/search": {}}},
        }

        serializer = APISpecSerializer()
        restored: APISpec = serializer.from_canonical(legacy_canonical)

        assert restored.api_name == "LegacySearch"
        assert restored.auth == "apikey"
        assert restored.auth_status == "configured", (
            "Legacy non-none auth must be inferred as configured, not source_backed"
        )
        assert restored.functions_status == "known_present", (
            "Legacy non-empty functions must be inferred as known_present"
        )
        assert restored.schema_status == "unknown_placeholder", (
            "Legacy missing schema_status must remain unknown_placeholder"
        )
        assert restored.openapi_schema.format == "json_object"
        assert json.loads(restored.openapi_schema.canonical_text) == {"paths": {"/search": {}}}

    def test_api_function_legacy_and_extended_fields_roundtrip(self) -> None:
        """Verify APIFunction legacy fields roundtrip and extended fields defaults."""
        fn_serializer = APIFunctionSerializer()

        # Legacy construction
        fn_legacy = APIFunction(
            name="get_item",
            description="Get item details",
            parameters=[{"name": "id", "type": "string"}],
            return_type="json",
        )
        assert fn_legacy.url == ""  # Does not pseudofy URL

        canonical_legacy = fn_serializer.to_canonical(fn_legacy)
        restored_legacy: APIFunction = fn_serializer.from_canonical(canonical_legacy)
        assert restored_legacy.name == "get_item"
        assert restored_legacy.description == "Get item details"
        assert restored_legacy.parameters == [{"name": "id", "type": "string"}]
        assert restored_legacy.return_type == "json"
        assert restored_legacy.url == ""

        # Extended construction
        fn_extended = APIFunction(
            name="create_item",
            description="Create item",
            function_id="fn_create",
            url="https://api.example.com/items",
            parameter_specs=[
                APIParameterSpec(
                    name="item_name",
                    data_type="string",
                    required=True,
                )
            ],
            controlled_input=True,
            return_spec=APIReturnSpec(data_type="json", controlled_output=True),
        )
        canonical_ext = fn_serializer.to_canonical(fn_extended)
        restored_ext: APIFunction = fn_serializer.from_canonical(canonical_ext)
        assert restored_ext.function_id == "fn_create"
        assert restored_ext.url == "https://api.example.com/items"
        assert len(restored_ext.parameter_specs) == 1
        assert restored_ext.parameter_specs[0].name == "item_name"
        assert restored_ext.return_spec is not None
        assert restored_ext.return_spec.controlled_output is True
