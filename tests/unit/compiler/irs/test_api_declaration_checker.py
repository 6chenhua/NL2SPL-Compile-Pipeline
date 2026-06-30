"""Unit tests for APIDeclarationIRSChecker."""

from __future__ import annotations

import copy

from nl2spl.compiler.artifacts.snapshot.serialization.serializers_resource import APISpecSerializer
from nl2spl.compiler.construct_registry import SPLConstructRegistry
from nl2spl.compiler.irs.checkers.api_declaration import APIDeclarationIRSChecker
from nl2spl.compiler.irs.context import IRSCheckContext
from nl2spl.compiler.irs.factory import build_irs_runner
from nl2spl.ir.resource_registry_ir import APIFunction, APISpec, ResourceRegistryIR
from nl2spl.ir.structured_text_ir import StructuredTextIR


class TestAPIDeclarationChecker:
    """Unit tests for APIDeclarationIRSChecker extraction, satisfaction, and immutability checks."""

    def test_expected_correct_extract_instances_returns_empty_when_no_resources(self) -> None:
        """Verify extract_instances returns empty list when resources is None or empty."""
        checker = APIDeclarationIRSChecker()
        ctx = IRSCheckContext(stage_name="stage6", resources=None)

        instances = checker.extract_instances(ctx)
        assert instances == []

        ctx_empty = IRSCheckContext(stage_name="stage6", resources=ResourceRegistryIR())
        instances_empty = checker.extract_instances(ctx_empty)
        assert instances_empty == []

    def test_expected_correct_extract_instances_from_resource_registry(self) -> None:
        """Verify extract_instances extracts API_DECLARATION instances from resources.apis."""
        checker = APIDeclarationIRSChecker()
        api1 = APISpec(api_name="SearchAPI", auth="none", description="Search service")
        resources = ResourceRegistryIR(apis=[api1])
        ctx = IRSCheckContext(stage_name="stage6", resources=resources)

        instances = checker.extract_instances(ctx)
        assert len(instances) == 1
        assert instances[0].construct_id == "api_declaration:api:SearchAPI"
        assert instances[0].construct_type == "API_DECLARATION"
        assert instances[0].materialized is True
        assert instances[0].construct_path == ("resources", "apis", "api:SearchAPI")

    def test_expected_correct_missing_name_or_source_is_not_renderable(self) -> None:
        """Missing API identity or source evidence blocks the declaration."""
        checker = APIDeclarationIRSChecker()
        registry = SPLConstructRegistry.default()
        irs = registry.get("API_DECLARATION")
        assert irs is not None

        # API spec missing source spans / origin evidence
        api_no_source = APISpec(
            api_name="NoSourceAPI",
            auth="none",
            description="API without source spans",
            source_span_ids=[],
        )
        ctx = IRSCheckContext(
            stage_name="stage6", resources=ResourceRegistryIR(apis=[api_no_source])
        )
        instances = checker.extract_instances(ctx)

        report = checker.check_instance(instances[0], irs, ctx)
        assert report.renderable is False, "Missing source evidence must prevent rendering"
        assert report.completeness == "blocked"
        assert report.frontier_status == "cutline_blocked"
        assert report.cutline_reason == "missing_api_identity_or_evidence"
        assert report.construct_path == ("resources", "apis", "api:NoSourceAPI")

        slot_map = {s.slot_name: s for s in report.slots}
        assert slot_map["source_evidence"].status == "missing"

    def test_expected_correct_unapproved_partial_api_spec_is_blocked(self) -> None:
        """Unknown placeholders cannot render without D-CAP-0 approval."""
        checker = APIDeclarationIRSChecker()
        registry = SPLConstructRegistry.default()
        irs = registry.get("API_DECLARATION")
        assert irs is not None

        api = APISpec(
            api_name="WeatherAPI",
            auth="apikey",
            description="Weather info",
            functions=[
                APIFunction(name="get_weather", description="Get weather", return_type="text")
            ],
            source_span_ids=["span_1"],
        )
        ctx = IRSCheckContext(stage_name="stage6", resources=ResourceRegistryIR(apis=[api]))
        instances = checker.extract_instances(ctx)

        report = checker.check_instance(instances[0], irs, ctx)
        assert report.construct_id == "api_declaration:api:WeatherAPI"
        assert report.renderable is False
        assert report.completeness == "blocked"
        assert report.frontier_status == "cutline_blocked"
        assert report.cutline_reason == "api_declaration_grammar_blocked"

    def test_expected_correct_legacy_payload_with_complete_status_fails_closed(self) -> None:
        """A legacy complete payload with placeholder slots fails closed."""
        legacy_payload = {
            "$type": "APISpec",
            "api_name": "LegacyAPI",
            "auth": "apikey",
            "description": "Legacy service",
            "source_span_ids": ["span_1"],
            "functions": [{"$type": "APIFunction", "name": "fn1", "description": "fn"}],
            "declaration_status": "complete",
        }
        serializer = APISpecSerializer()
        api: APISpec = serializer.from_canonical(legacy_payload)

        assert api.auth_status == "configured"
        assert api.schema_status == "unknown_placeholder"
        assert api.functions_status == "known_present"

        checker = APIDeclarationIRSChecker()
        registry = SPLConstructRegistry.default()
        irs = registry.get("API_DECLARATION")
        assert irs is not None

        ctx = IRSCheckContext(stage_name="stage6", resources=ResourceRegistryIR(apis=[api]))
        instances = checker.extract_instances(ctx)
        report = checker.check_instance(instances[0], irs, ctx)

        assert report.renderable is False
        assert report.completeness == "blocked"
        assert report.frontier_status == "cutline_blocked"
        assert report.cutline_reason == "api_declaration_grammar_blocked"

    def test_expected_correct_contradictory_complete_status_is_rejected(self) -> None:
        """A complete status cannot override unknown placeholder slots."""
        checker = APIDeclarationIRSChecker()
        registry = SPLConstructRegistry.default()
        irs = registry.get("API_DECLARATION")
        assert irs is not None

        # Force complete while schema and functions remain unknown placeholders.
        api = APISpec(
            api_name="FakeCompleteAPI",
            auth="none",
            description="Fake complete",
            source_span_ids=["span_1"],
            declaration_status="complete",
            schema_status="unknown_placeholder",
            functions_status="unknown_placeholder",
        )
        ctx = IRSCheckContext(stage_name="stage6", resources=ResourceRegistryIR(apis=[api]))
        instances = checker.extract_instances(ctx)

        report = checker.check_instance(instances[0], irs, ctx)
        assert report.completeness == "blocked", (
            "Must fail closed when required slots are placeholders"
        )
        assert report.frontier_status == "cutline_blocked"

    def test_expected_correct_invalid_name_auth_and_schema_are_grammar_blocked(self) -> None:
        checker = APIDeclarationIRSChecker()
        irs = SPLConstructRegistry.default().get("API_DECLARATION")
        assert irs is not None
        api = APISpec(
            api_name="bad name",
            auth="bogus",
            description="invalid",
            source_span_ids=["s1"],
            declaration_status="complete",
            auth_status="configured",
            schema_status="known_present",
            functions_status="known_empty",
            openapi_schema="not structured",  # type: ignore[arg-type]
        )

        report = checker.check_instance(
            checker.extract_instances(
                IRSCheckContext(
                    stage_name="post_normalize", resources=ResourceRegistryIR(apis=[api])
                )
            )[0],
            irs,
            IRSCheckContext(stage_name="post_normalize", resources=ResourceRegistryIR(apis=[api])),
        )

        assert report.renderable is False
        assert report.completeness == "blocked"
        assert report.metadata["grammar_validation_status"] == "partial_blocked"
        assert set(report.metadata["grammar_validation_reasons"]) >= {
            "api_name_not_grammar_safe",
            "authentication_not_grammar_safe",
            "openapi_schema_not_structured_text",
        }

    def test_expected_correct_full_complete_api_spec(self) -> None:
        """A grammar-valid declaration with all required slots is complete."""
        checker = APIDeclarationIRSChecker()
        registry = SPLConstructRegistry.default()
        irs = registry.get("API_DECLARATION")
        assert irs is not None

        api = APISpec(
            api_name="FullAPI",
            auth="apikey",
            description="Full complete API",
            source_span_ids=["span_1"],
            declaration_status="complete",
            auth_status="configured",
            schema_status="known_present",
            functions_status="known_present",
            openapi_schema=StructuredTextIR(
                format="json_object", canonical_text='{"openapi":"3.0"}'
            ),
            functions=[APIFunction(name="query", description="Query function")],
        )
        ctx = IRSCheckContext(stage_name="stage6", resources=ResourceRegistryIR(apis=[api]))
        instances = checker.extract_instances(ctx)

        report = checker.check_instance(instances[0], irs, ctx)
        assert report.completeness == "complete"
        assert report.renderable is True
        assert report.frontier_status == "leaf"
        assert report.cutline_reason is None

    def test_expected_correct_input_immutability(self) -> None:
        """Verify check_instance does not modify the input APISpec or IRSCheckContext."""
        checker = APIDeclarationIRSChecker()
        registry = SPLConstructRegistry.default()
        irs = registry.get("API_DECLARATION")
        assert irs is not None

        api = APISpec(api_name="TestAPI", auth="none", description="Test", source_span_ids=["s1"])
        api_copy = copy.deepcopy(api)
        ctx = IRSCheckContext(stage_name="stage6", resources=ResourceRegistryIR(apis=[api]))
        ctx_copy = copy.deepcopy(ctx)

        instances = checker.extract_instances(ctx)
        checker.check_instance(instances[0], irs, ctx)

        assert api == api_copy, "APISpec input must remain untouched"
        assert ctx.resources == ctx_copy.resources, (
            "IRSCheckContext resources must remain untouched"
        )

    def test_expected_correct_runner_with_api_declaration_checker_empty_demands(self) -> None:
        """The IRS runner handles an empty API declaration set."""
        runner = build_irs_runner(enable_api_declaration=True)
        ctx = IRSCheckContext(stage_name="stage6", resources=ResourceRegistryIR())

        result = runner.run_stage("stage6", ctx)
        assert result is not None
        assert result.reports == []
        assert result.diagnostics == []

    def test_expected_correct_api_checker_cases_a_to_e(self) -> None:
        """AP-1 Baseline: Verify Case A to Case E status matrix predictions in IRS checker."""
        checker = APIDeclarationIRSChecker()
        irs = SPLConstructRegistry.default().get("API_DECLARATION")
        assert irs is not None

        # Case A: Valid placeholders (approved minimal partial skeleton)
        api_a = APISpec(
            api_name="SearchAPI",
            auth="none",
            description="Search service",
            source_span_ids=["s1"],
            declaration_status="grammar_minimal_partial",
            schema_status="unknown_placeholder",
            functions_status="unknown_placeholder",
            openapi_schema=StructuredTextIR(format="empty_placeholder", canonical_text="{}"),
            functions=[],
        )
        ctx_a = IRSCheckContext(stage_name="stage6", resources=ResourceRegistryIR(apis=[api_a]))
        inst_a = checker.extract_instances(ctx_a)[0]
        rep_a = checker.check_instance(inst_a, irs, ctx_a)
        assert rep_a.completeness == "partial"
        assert rep_a.renderable is True
        assert rep_a.frontier_status == "cutline_partial"

        # Case B: Malformed openapi_schema (known present but not StructuredTextIR type)
        api_b = APISpec(
            api_name="SearchAPI",
            auth="none",
            description="Search service",
            source_span_ids=["s1"],
            declaration_status="grammar_minimal_partial",
            schema_status="known_present",
            functions_status="unknown_placeholder",
            openapi_schema="invalid_schema_type",  # type: ignore[arg-type]
            functions=[],
        )
        ctx_b = IRSCheckContext(stage_name="stage6", resources=ResourceRegistryIR(apis=[api_b]))
        inst_b = checker.extract_instances(ctx_b)[0]
        rep_b = checker.check_instance(inst_b, irs, ctx_b)
        assert rep_b.completeness == "blocked"
        assert rep_b.renderable is False
        assert rep_b.frontier_status == "cutline_blocked"

        # Case C: Malformed functions (known present but not APIFunction instances list)
        api_c = APISpec(
            api_name="SearchAPI",
            auth="none",
            description="Search service",
            source_span_ids=["s1"],
            declaration_status="grammar_minimal_partial",
            schema_status="unknown_placeholder",
            functions_status="known_present",
            openapi_schema=StructuredTextIR(format="empty_placeholder", canonical_text="{}"),
            functions="invalid_functions_list",  # type: ignore[arg-type]
        )
        ctx_c = IRSCheckContext(stage_name="stage6", resources=ResourceRegistryIR(apis=[api_c]))
        inst_c = checker.extract_instances(ctx_c)[0]
        rep_c = checker.check_instance(inst_c, irs, ctx_c)
        assert rep_c.completeness == "blocked"
        assert rep_c.renderable is False
        assert rep_c.frontier_status == "cutline_blocked"

        # Case D: Missing API name
        api_d = APISpec(
            api_name="",
            auth="none",
            description="Search service",
            source_span_ids=["s1"],
            declaration_status="grammar_minimal_partial",
            schema_status="unknown_placeholder",
            functions_status="unknown_placeholder",
            openapi_schema=StructuredTextIR(format="empty_placeholder", canonical_text="{}"),
            functions=[],
        )
        ctx_d = IRSCheckContext(stage_name="stage6", resources=ResourceRegistryIR(apis=[api_d]))
        inst_d = checker.extract_instances(ctx_d)[0]
        rep_d = checker.check_instance(inst_d, irs, ctx_d)
        assert rep_d.completeness == "blocked"
        assert rep_d.renderable is False
        assert rep_d.frontier_status == "cutline_blocked"

        # Case E: Missing evidence
        api_e = APISpec(
            api_name="SearchAPI",
            auth="none",
            description="Search service",
            source_span_ids=[],
            declaration_status="grammar_minimal_partial",
            schema_status="unknown_placeholder",
            functions_status="unknown_placeholder",
            openapi_schema=StructuredTextIR(format="empty_placeholder", canonical_text="{}"),
            functions=[],
        )
        ctx_e = IRSCheckContext(stage_name="stage6", resources=ResourceRegistryIR(apis=[api_e]))
        inst_e = checker.extract_instances(ctx_e)[0]
        rep_e = checker.check_instance(inst_e, irs, ctx_e)
        assert rep_e.completeness == "blocked"
        assert rep_e.renderable is False
        assert rep_e.frontier_status == "cutline_blocked"
