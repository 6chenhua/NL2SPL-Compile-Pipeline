"""Unit tests for API_DECLARATION and CALL_API ConstructIRS registry rules."""

from __future__ import annotations

import pytest

from nl2spl.compiler.construct_registry import SPLConstructRegistry
from nl2spl.compiler.spl_editing.core.catalog import RepairCatalogBuilder


class TestAPIDeclarationRegistry:
    """Unit tests for API_DECLARATION and CALL_API registry constraints."""

    def test_api_declaration_exists_in_default_registry(self) -> None:
        """Verify API_DECLARATION construct is present in default construct registry."""
        registry = SPLConstructRegistry.default()
        irs = registry.get("API_DECLARATION")

        assert irs is not None
        assert irs.construct_type == "API_DECLARATION"
        assert irs.existence_policy == "source_signal_required"
        assert irs.partial_rendering_allowed is True

    def test_api_declaration_slots_and_properties(self) -> None:
        """Verify slots, requiredness, and diagnostic kinds for API_DECLARATION."""
        registry = SPLConstructRegistry.default()
        irs = registry.get("API_DECLARATION")
        assert irs is not None

        slot_names = [slot.slot_name for slot in irs.slots]
        expected_slots = ["api_name", "source_evidence", "authentication", "openapi_schema", "functions"]
        assert slot_names == expected_slots

        api_name_slot = irs.get_slot("api_name")
        assert api_name_slot is not None
        assert api_name_slot.syntax_required is True
        assert api_name_slot.required_for_complete is True
        assert api_name_slot.renderable_without is False
        assert api_name_slot.missing_diagnostic == "type_or_contract_ambiguity"

        source_ev_slot = irs.get_slot("source_evidence")
        assert source_ev_slot is not None
        assert source_ev_slot.syntax_required is False
        assert source_ev_slot.required_for_complete is True

        auth_slot = irs.get_slot("authentication")
        assert auth_slot is not None
        assert auth_slot.renderable_without is True

    def test_api_declaration_no_repair_affordances(self) -> None:
        """Verify all slots of API_DECLARATION have repair_affordances == ()."""
        registry = SPLConstructRegistry.default()
        irs = registry.get("API_DECLARATION")
        assert irs is not None

        for slot in irs.slots:
            assert slot.repair_affordances == (), f"Slot {slot.slot_name} should have no repair affordances"

    def test_repair_catalog_does_not_generate_api_declaration_entries(self) -> None:
        """Verify RepairCatalog contains zero entries for API_DECLARATION."""
        registry = SPLConstructRegistry.default()
        catalog = RepairCatalogBuilder.from_construct_registry(registry)

        api_decl_entries = [
            entry for entry in catalog.entries
            if entry.construct_type == "API_DECLARATION"
        ]
        assert len(api_decl_entries) == 0

    def test_call_api_target_slot_migration_and_alias_downgrade(self) -> None:
        """Verify CALL_API target slot migration shape and integration_evidence alias downgrade."""
        registry = SPLConstructRegistry.default()
        irs = registry.get("CALL_API")
        assert irs is not None

        slot_names = [slot.slot_name for slot in irs.slots]
        expected_slots = [
            "api_name",
            "declared_api_ref",
            "call_action",
            "request_bindings",
            "response_binding",
            "integration_evidence",
        ]
        assert slot_names == expected_slots

        # Assert declared_api_ref target slot
        declared_ref_slot = irs.get_slot("declared_api_ref")
        assert declared_ref_slot is not None
        assert declared_ref_slot.required_for_complete is True
        assert declared_ref_slot.missing_diagnostic == "type_or_contract_ambiguity"

        # Assert request_bindings target slot
        request_bindings_slot = irs.get_slot("request_bindings")
        assert request_bindings_slot is not None
        assert request_bindings_slot.required_for_complete is False

        # Assert integration_evidence compatibility alias is downgraded from completion authority
        integ_slot = irs.get_slot("integration_evidence")
        assert integ_slot is not None
        assert integ_slot.required_for_complete is False, "integration_evidence must not act as completion authority"

    def test_specify_api_integration_does_not_lookup_to_api_declaration(self) -> None:
        """Verify SpecifyAPIIntegration only routes to CALL_API, not API_DECLARATION."""
        registry = SPLConstructRegistry.default()
        catalog = RepairCatalogBuilder.from_construct_registry(registry)

        call_api_irs = registry.get("CALL_API")
        assert call_api_irs is not None
        integ_slot = call_api_irs.get_slot("integration_evidence")
        assert integ_slot is not None
        affordance_ids = [aff.affordance_id for aff in integ_slot.repair_affordances]
        assert "call_api.specify_integration_evidence" in affordance_ids

        for entry in catalog.entries:
            if "SpecifyAPIIntegration" in entry.supported_patch_types:
                assert entry.construct_type == "CALL_API"
