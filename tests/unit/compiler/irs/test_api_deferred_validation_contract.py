"""AP0/AP1 API deferred validation diagnostic and projection contract."""

from __future__ import annotations

from nl2spl.compiler.completeness import compute_completeness
from nl2spl.compiler.construct_registry import SPLConstructRegistry
from nl2spl.compiler.irs.checkers.api_declaration import APIDeclarationIRSChecker
from nl2spl.compiler.irs.context import IRSCheckContext
from nl2spl.compiler.irs.projector import DiagnosticProjector
from nl2spl.ir.resource_registry_ir import APISpec, ResourceRegistryIR
from nl2spl.ir.structured_text_ir import StructuredTextIR


def _placeholder_api() -> APISpec:
    return APISpec(
        api_name="SearchAPI",
        auth="none",
        description="Search service",
        source_span_ids=["s1"],
        declaration_status="grammar_minimal_partial",
        schema_status="unknown_placeholder",
        functions_status="unknown_placeholder",
        openapi_schema=StructuredTextIR(
            format="empty_placeholder",
            canonical_text="{}",
        ),
        functions=[],
    )


def test_placeholder_report_and_diagnostics_use_deferred_contract() -> None:
    checker = APIDeclarationIRSChecker()
    irs = SPLConstructRegistry.default().get("API_DECLARATION")
    assert irs is not None
    context = IRSCheckContext(
        stage_name="post_normalize",
        resources=ResourceRegistryIR(apis=[_placeholder_api()]),
    )

    report = checker.check_instance(checker.extract_instances(context)[0], irs, context)
    slots = {slot.slot_name: slot for slot in report.slots}

    assert report.completeness == "partial"
    assert report.renderable is True
    assert report.metadata["nl2spl_renderable"] is True
    assert report.metadata["api_contract_validation_status"] == "pending"
    assert report.metadata["validation_authority"] == "downstream_spl_compiler"
    assert report.metadata["repairability"] == "review_only"
    assert report.metadata["presentation_disposition"] == "deferred_validation"
    assert report.metadata["placeholder_fields"] == ["openapi_schema", "functions"]
    assert report.metadata["issue_group_id"].startswith("api_contract_deferred:")

    for slot_name in ("openapi_schema", "functions"):
        slot = slots[slot_name]
        assert slot.status == "missing"
        assert slot.diagnostic_kind == "deferred_api_contract_validation"
        assert slot.diagnostic_required_for == "downstream_api_validation"
        assert slot.diagnostic_blocks_rendering is False

    projected = DiagnosticProjector().project([report], context).diagnostics
    assert len(projected) == 2
    assert {diagnostic.missing_slot.slot_name for diagnostic in projected} == {
        "openapi_schema",
        "functions",
    }
    assert {diagnostic.kind for diagnostic in projected} == {
        "deferred_api_contract_validation"
    }
    assert all(diagnostic.severity == "info" for diagnostic in projected)
    assert all(diagnostic.blocks_rendering is False for diagnostic in projected)
    assert all(diagnostic.blocks_completion is False for diagnostic in projected)
    assert all(
        diagnostic.missing_slot.required_for == "downstream_api_validation"
        for diagnostic in projected
    )
    assert all(
        diagnostic.metadata["validation_authority"] == "downstream_spl_compiler"
        for diagnostic in projected
    )
    assert compute_completeness(diagnostics=projected) == "complete"


def test_malformed_api_remains_structural_and_blocking() -> None:
    api = _placeholder_api()
    api.openapi_schema = "malformed"  # type: ignore[assignment]
    checker = APIDeclarationIRSChecker()
    irs = SPLConstructRegistry.default().get("API_DECLARATION")
    assert irs is not None
    context = IRSCheckContext(
        stage_name="post_normalize",
        resources=ResourceRegistryIR(apis=[api]),
    )

    report = checker.check_instance(checker.extract_instances(context)[0], irs, context)
    projected = DiagnosticProjector().project([report], context).diagnostics
    schema_diagnostic = next(
        diagnostic
        for diagnostic in projected
        if diagnostic.missing_slot
        and diagnostic.missing_slot.slot_name == "openapi_schema"
    )

    assert report.renderable is False
    assert report.completeness == "blocked"
    assert schema_diagnostic.kind == "type_or_contract_ambiguity"
    assert schema_diagnostic.blocks_rendering is True
    assert schema_diagnostic.blocks_completion is True
    assert "presentation_disposition" not in schema_diagnostic.metadata


def test_projector_report_metadata_is_explicitly_whitelisted() -> None:
    checker = APIDeclarationIRSChecker()
    irs = SPLConstructRegistry.default().get("API_DECLARATION")
    assert irs is not None
    context = IRSCheckContext(
        stage_name="post_normalize",
        resources=ResourceRegistryIR(apis=[_placeholder_api()]),
    )
    report = checker.check_instance(checker.extract_instances(context)[0], irs, context)
    report.metadata["must_not_leak"] = {"secret": True}

    projected = DiagnosticProjector().project([report], context).diagnostics
    assert projected
    assert all("must_not_leak" not in diagnostic.metadata for diagnostic in projected)


def test_api_completion_slots_remain_non_editable_without_affordances() -> None:
    irs = SPLConstructRegistry.default().get("API_DECLARATION")
    assert irs is not None
    for slot_name in ("openapi_schema", "functions"):
        slot = irs.get_slot(slot_name)
        assert slot is not None
        assert slot.repair_affordances == ()
        assert slot.actionability_decision is not None
        assert slot.actionability_decision.actionability == "non_editable"
        assert (
            slot.actionability_decision.non_editable_disposition
            == "deferred_validation"
        )
