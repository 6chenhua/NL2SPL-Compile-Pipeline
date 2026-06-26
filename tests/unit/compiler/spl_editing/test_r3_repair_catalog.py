"""R3 RepairCatalog Builder: post-implementation tests.

Verifies that after R3 changes:
  1. RepairCatalogBuilder.from_construct_registry() produces a non-empty catalog
  2. entry_id is a stable composite key
  3. Lookup by construct_type + slot_name + diagnostic_kind works
  4. Lookup by affordance_id works (returns multiple entries for shared IDs)
  5. Lookup by DiagnosticIRSRef + diagnostic_kind works
  6. Catalog is purely derived — no hand-written mapping
  7. Non-repairable diagnostics have no entries
  8. No spl_editing imports in construct_registry (cross-check from R2)
"""

from __future__ import annotations

import pytest

from nl2spl.compiler.construct_registry import SPLConstructRegistry
from nl2spl.compiler.spl_editing.core.catalog import (
    RepairCatalog,
    RepairCatalogBuilder,
)
from nl2spl.ir.diagnostics import DiagnosticIRSRef

# ===========================================================================
# R3-1: Builder produces a non-empty catalog
# ===========================================================================


class TestR3CatalogBuild:
    """R3: Catalog is built from the default registry."""

    def test_build_produces_non_empty_catalog(self) -> None:
        """R3: Default registry has affordances → catalog is non-empty."""
        registry = SPLConstructRegistry.default()
        catalog = RepairCatalogBuilder.from_construct_registry(registry)
        assert len(catalog) > 0, "R3: catalog must be non-empty"
        assert len(catalog.entries) > 0

    def test_build_from_empty_registry_produces_empty_catalog(self) -> None:
        """R3: Empty registry → empty catalog."""
        registry = SPLConstructRegistry()  # no constructs registered
        catalog = RepairCatalogBuilder.from_construct_registry(registry)
        assert len(catalog) == 0
        assert catalog.entries == ()

    def test_catalog_is_deterministic(self) -> None:
        """R3: Two builds from the same registry produce identical catalogs."""
        registry = SPLConstructRegistry.default()
        a = RepairCatalogBuilder.from_construct_registry(registry)
        b = RepairCatalogBuilder.from_construct_registry(registry)
        assert len(a) == len(b)
        assert a.list_affordance_ids() == b.list_affordance_ids()
        # Entry order is deterministic
        for ea, eb in zip(a.entries, b.entries):  # noqa: B905
            assert ea.entry_id == eb.entry_id


# ===========================================================================
# R3-2: entry_id is a stable composite key
# ===========================================================================


class TestR3EntryId:
    """R3: entry_id format and uniqueness."""

    def test_entry_id_format(self) -> None:
        """R3: entry_id = construct_type.slot_name.diagnostic_kind.affordance_id."""
        catalog = RepairCatalogBuilder.from_construct_registry(SPLConstructRegistry.default())
        for entry in catalog.entries:
            expected = ".".join(
                [
                    entry.construct_type,
                    entry.slot_name,
                    entry.diagnostic_kind,
                    entry.affordance_id,
                ]
            )
            assert entry.entry_id == expected, (
                f"entry_id '{entry.entry_id}' does not match expected '{expected}'"
            )

    def test_all_entry_ids_unique(self) -> None:
        """R3: No two entries share the same entry_id."""
        catalog = RepairCatalogBuilder.from_construct_registry(SPLConstructRegistry.default())
        ids = [e.entry_id for e in catalog.entries]
        assert len(ids) == len(set(ids)), (
            f"Duplicate entry_ids: {[i for i in ids if ids.count(i) > 1]}"
        )

    def test_shared_affordance_produces_multiple_entries(self) -> None:
        """R3: worker_promotion.resolve_contract is shared by 4 slots
        → 4 distinct entries with different entry_ids.
        """
        catalog = RepairCatalogBuilder.from_construct_registry(SPLConstructRegistry.default())
        entries = catalog.find_by_affordance_id("worker_promotion.resolve_contract")
        assert len(entries) == 4, (
            f"Expected 4 entries for shared WORKER_PROMOTION affordance, got {len(entries)}"
        )
        # All 4 entries have distinct slot_names
        slot_names = {e.slot_name for e in entries}
        assert slot_names == {
            "promotion_input_contract",
            "promotion_output_contract",
            "promotion_invocation_point",
            "promotion_result_handoff",
        }
        # All 4 entries share the same construct_type
        assert all(e.construct_type == "WORKER_PROMOTION" for e in entries)
        # All 4 have unique entry_ids
        entry_ids = {e.entry_id for e in entries}
        assert len(entry_ids) == 4


# ===========================================================================
# R3-3: Lookup by construct_type + slot_name + diagnostic_kind
# ===========================================================================


class TestR3ConstructSlotKindLookup:
    """R3: Primary lookup axis."""

    @staticmethod
    def _catalog() -> RepairCatalog:
        return RepairCatalogBuilder.from_construct_registry(SPLConstructRegistry.default())

    def test_find_missing_handler(self) -> None:
        """R3: EXCEPTION_FLOW.handler_action.missing_handler → 1 entry."""
        entries = self._catalog().find_by_construct_slot_kind(
            "EXCEPTION_FLOW",
            "handler_action",
            "missing_handler",
        )
        assert len(entries) == 1
        entry = entries[0]
        assert entry.affordance_id == "exception_flow.add_handler_step"
        assert entry.supported_patch_types == ("AddExceptionHandlerStep",)
        assert entry.default_verification_lane == "B"

    def test_find_missing_output_producer(self) -> None:
        """R3: REQUIRED_OUTPUT.producer.missing_output_producer → 1 entry."""
        entries = self._catalog().find_by_construct_slot_kind(
            "REQUIRED_OUTPUT",
            "producer",
            "missing_output_producer",
        )
        assert len(entries) == 1
        entry = entries[0]
        assert entry.affordance_id == "required_output.insert_or_bind_producer"
        assert entry.supported_patch_types == ("InsertProducerStep",)

    def test_find_type_or_contract_ambiguity_for_call_api(self) -> None:
        """R3: CALL_API.integration_evidence.type_or_contract_ambiguity → 1 entry."""
        entries = self._catalog().find_by_construct_slot_kind(
            "CALL_API",
            "integration_evidence",
            "type_or_contract_ambiguity",
        )
        assert len(entries) == 1
        assert entries[0].affordance_id == "call_api.specify_integration_evidence"

    def test_find_non_repairable_returns_empty(self) -> None:
        """R3: Slots without affordances return empty tuple."""
        # GENERAL_COMMAND.source_evidence has missing_diagnostic but no affordance
        entries = self._catalog().find_by_construct_slot_kind(
            "GENERAL_COMMAND",
            "source_evidence",
            "assumed_command_not_renderable",
        )
        assert entries == ()

    def test_find_unknown_construct_returns_empty(self) -> None:
        """R3: Unknown construct type → empty."""
        entries = self._catalog().find_by_construct_slot_kind(
            "NO_SUCH_CONSTRUCT",
            "any_slot",
            "any_kind",
        )
        assert entries == ()

    def test_resource_contract_demand_producer_has_no_entry(self) -> None:
        """R3: RESOURCE_CONTRACT_DEMAND.producer has missing_output_producer
        diagnostic but NO affordance yet → empty result.
        """
        entries = self._catalog().find_by_construct_slot_kind(
            "RESOURCE_CONTRACT_DEMAND",
            "producer",
            "missing_output_producer",
        )
        assert entries == (), (
            "R3 CURRENT: RESOURCE_CONTRACT_DEMAND.producer has no affordance. "
            "R4 will introduce producer issue grouping."
        )


# ===========================================================================
# R3-4: Lookup by affordance_id
# ===========================================================================


class TestR3AffordanceIdLookup:
    """R3: Lookup by globally unique affordance_id."""

    @staticmethod
    def _catalog() -> RepairCatalog:
        return RepairCatalogBuilder.from_construct_registry(SPLConstructRegistry.default())

    def test_find_by_affordance_id_single_entry(self) -> None:
        """R3: Affordance IDs used by exactly one slot return 1 entry."""
        entries = self._catalog().find_by_affordance_id("exception_flow.add_handler_step")
        assert len(entries) == 1
        assert entries[0].construct_type == "EXCEPTION_FLOW"
        assert entries[0].slot_name == "handler_action"

    def test_find_by_affordance_id_multiple_entries(self) -> None:
        """R3: Shared affordance ID returns all slot entries."""
        entries = self._catalog().find_by_affordance_id("worker_promotion.resolve_contract")
        assert len(entries) == 4

    def test_find_by_unknown_affordance_id_returns_empty(self) -> None:
        """R3: Unknown affordance_id → empty tuple."""
        entries = self._catalog().find_by_affordance_id("no_such_affordance")
        assert entries == ()

    def test_list_affordance_ids_contains_all_expected(self) -> None:
        """R3: list_affordance_ids() returns sorted unique IDs."""
        ids = self._catalog().list_affordance_ids()
        expected = {
            "exception_flow.add_handler_step",
            "required_output.insert_or_bind_producer",
            "request_input.specify_value_target",
            "call_api.specify_integration_evidence",
            "invoke_worker.specify_target_worker",
            "invoke_worker.create_or_bind_handoff",
            "invoke_worker.specify_input_bindings",
            "invoke_worker.specify_output_bindings",
            "worker_promotion.resolve_contract",
            "worker_handoff.specify_target",
            "worker_handoff.specify_input_bindings",
            "worker_handoff.specify_output_bindings",
            "worker_handoff.specify_invocation_site",
        }
        assert set(ids) == expected


# ===========================================================================
# R3-5: Lookup by DiagnosticIRSRef + diagnostic_kind
# ===========================================================================


class TestR3IRSRefLookup:
    """R3: Lookup using metadata from CompileDiagnostic."""

    @staticmethod
    def _catalog() -> RepairCatalog:
        return RepairCatalogBuilder.from_construct_registry(SPLConstructRegistry.default())

    def test_find_by_irs_ref_for_missing_handler(self) -> None:
        """R3: IRS ref from EXCEPTION_FLOW.handler_action + missing_handler
        → finds the correct entry.
        """
        irs_ref = DiagnosticIRSRef(
            construct_type="EXCEPTION_FLOW",
            construct_id="worker:w_main.exception_flow:exc_1",
            slot_name="handler_action",
            construct_path=("worker", "w_main", "exception_flows", "exc_1"),
            source_authority="post_normalize_irs",
        )
        entries = self._catalog().find_by_irs_ref(irs_ref, "missing_handler")
        assert len(entries) == 1
        assert entries[0].affordance_id == "exception_flow.add_handler_step"

    def test_find_by_irs_ref_for_invoke_worker_handoff(self) -> None:
        """R3: IRS ref from INVOKE_WORKER.handoff_id →
        invoke_worker.create_or_bind_handoff.
        """
        irs_ref = DiagnosticIRSRef(
            construct_type="INVOKE_WORKER",
            construct_id="worker:w_main.step:st_invoke",
            slot_name="handoff_id",
            source_authority="post_normalize_irs",
        )
        entries = self._catalog().find_by_irs_ref(irs_ref, "type_or_contract_ambiguity")
        assert len(entries) == 1
        assert entries[0].affordance_id == "invoke_worker.create_or_bind_handoff"
        assert entries[0].default_verification_lane == "B"

    def test_find_by_irs_ref_mismatched_kind_returns_empty(self) -> None:
        """R3: IRS ref pointing to handler_action with wrong diagnostic_kind
        → empty (the diagnostic_kind must match the slot's missing_diagnostic).
        """
        irs_ref = DiagnosticIRSRef(
            construct_type="EXCEPTION_FLOW",
            construct_id="exc_1",
            slot_name="handler_action",
        )
        # handler_action's missing_diagnostic is "missing_handler", not
        # "type_or_contract_ambiguity"
        entries = self._catalog().find_by_irs_ref(
            irs_ref,
            "type_or_contract_ambiguity",
        )
        assert entries == ()


# ===========================================================================
# R3-6: Catalog is purely derived — not hand-written
# ===========================================================================


class TestR3CatalogDerivation:
    """R3: The catalog is a pure derivation from the registry."""

    def test_catalog_size_matches_affordance_count(self) -> None:
        """R3: Number of entries = number of (slot × affordance) pairs
        in the registry.
        """
        registry = SPLConstructRegistry.default()
        expected_count = 0
        for ct_name in registry.list_constructs():
            irs = registry.get(ct_name)
            for slot in irs.slots:
                expected_count += len(slot.repair_affordances)

        catalog = RepairCatalogBuilder.from_construct_registry(registry)
        assert len(catalog) == expected_count, (
            f"Catalog has {len(catalog)} entries, but registry has "
            f"{expected_count} (slot × affordance) pairs"
        )

    def test_catalog_entry_fields_match_registry(self) -> None:
        """R3: Every catalog entry's fields match its source RepairAffordanceSpec."""
        registry = SPLConstructRegistry.default()
        catalog = RepairCatalogBuilder.from_construct_registry(registry)

        for entry in catalog.entries:
            irs = registry.get(entry.construct_type)
            slot = irs.get_slot(entry.slot_name)
            assert slot is not None
            # Find the matching affordance
            matching = [
                a for a in slot.repair_affordances if a.affordance_id == entry.affordance_id
            ]
            assert len(matching) == 1, f"No matching affordance for {entry.entry_id}"
            aff = matching[0]
            assert entry.supported_patch_types == aff.supported_patch_types
            assert entry.default_patch_type == aff.default_patch_type
            assert entry.handler_id == aff.handler_id
            assert entry.context_id == aff.context_id
            assert entry.target_resolver_id == aff.target_resolver_id
            assert entry.default_verification_lane == aff.default_verification_lane
            assert entry.editable_artifacts == aff.editable_artifacts
            assert entry.required_evidence_kind == aff.required_evidence_kind


# ===========================================================================
# R3-7: get by entry_id
# ===========================================================================


class TestR3GetByEntryId:
    """R3: Direct entry lookup by composite key."""

    def test_get_existing(self) -> None:
        """R3: get() with a valid entry_id returns the entry."""
        catalog = RepairCatalogBuilder.from_construct_registry(SPLConstructRegistry.default())
        eid = "EXCEPTION_FLOW.handler_action.missing_handler.exception_flow.add_handler_step"
        entry = catalog.get(eid)
        assert entry is not None
        assert entry.construct_type == "EXCEPTION_FLOW"

    def test_get_nonexistent(self) -> None:
        """R3: get() with unknown entry_id returns None."""
        catalog = RepairCatalogBuilder.from_construct_registry(SPLConstructRegistry.default())
        assert catalog.get("NO.SUCH.ENTRY.id") is None

    def test_all_entry_ids_are_gettable(self) -> None:
        """R3: Every entry in the catalog can be retrieved by its entry_id."""
        catalog = RepairCatalogBuilder.from_construct_registry(SPLConstructRegistry.default())
        for entry in catalog.entries:
            found = catalog.get(entry.entry_id)
            assert found is not None, f"entry_id '{entry.entry_id}' not found"
            assert found is entry


# ===========================================================================
# R3-8: non-repairable diagnostics have no entries
# ===========================================================================


class TestR3NonRepairable:
    """R3: Diagnostics without affordances are absent from the catalog."""

    def test_assumed_command_not_renderable_not_in_catalog(self) -> None:
        """R3: assumed_command_not_renderable is an internal compiler
        signal — no affordance, no catalog entry.
        """
        catalog = RepairCatalogBuilder.from_construct_registry(SPLConstructRegistry.default())
        for entry in catalog.entries:
            assert entry.diagnostic_kind != "assumed_command_not_renderable", (
                f"R3: {entry.entry_id} has assumed_command_not_renderable — "
                f"this diagnostic kind should NEVER appear in the repair catalog"
            )

    def test_route_refinement_corrected_not_in_catalog(self) -> None:
        """R3: route_refinement_corrected is not in the catalog."""
        catalog = RepairCatalogBuilder.from_construct_registry(SPLConstructRegistry.default())
        kinds = {e.diagnostic_kind for e in catalog.entries}
        assert "route_refinement_corrected" not in kinds

    def test_missing_provenance_not_in_catalog(self) -> None:
        """R3: missing_provenance is not a repair target."""
        catalog = RepairCatalogBuilder.from_construct_registry(SPLConstructRegistry.default())
        kinds = {e.diagnostic_kind for e in catalog.entries}
        assert "missing_provenance" not in kinds

    def test_only_mvp_diagnostic_kinds_have_entries(self) -> None:
        """R3: The catalog only contains entries for the three MVP
        diagnostic kinds: missing_handler, missing_output_producer,
        type_or_contract_ambiguity.
        """
        catalog = RepairCatalogBuilder.from_construct_registry(SPLConstructRegistry.default())
        kinds = {e.diagnostic_kind for e in catalog.entries}
        assert kinds == {
            "missing_handler",
            "missing_output_producer",
            "type_or_contract_ambiguity",
        }, f"R3: Unexpected diagnostic kinds in catalog: {kinds}"


# ===========================================================================
# R3-9: Metadata extension & user_facing downgrade tests
# ===========================================================================


class TestR3MetadataExtension:
    """R3: Metadata extension on RepairAffordanceSpec and RepairCatalogEntry."""

    def test_repair_affordance_has_materialization_metadata_for_required_output(self) -> None:
        """Verify required_output.insert_or_bind_producer spec contains correct metadata fields."""
        registry = SPLConstructRegistry.default()
        irs = registry.get("REQUIRED_OUTPUT")
        slot = irs.get_slot("producer")
        assert slot is not None
        aff = next(
            a
            for a in slot.repair_affordances
            if a.affordance_id == "required_output.insert_or_bind_producer"
        )
        assert aff.materialization_plan_id == "stage7.step_producer_repair.v1"
        assert aff.selectable_ref_policy_id == "required_output.producer.selectable_refs.v1"
        assert aff.intent_schema_id == "intent.insert_producer_step.v1"
        assert aff.required_context_facts == (
            "target_output_name",
            "worker_id",
            "available_variables",
            "nearby_steps",
            "symbol_table",
        )
        assert aff.stage_authority == "stage7.worker_step_plan"

    def test_catalog_entry_carries_materialization_metadata(self) -> None:
        """Verify RepairCatalogEntry instances receive correct field mappings from the registry."""
        catalog = RepairCatalogBuilder.from_construct_registry(SPLConstructRegistry.default())

        # Test required_output.insert_or_bind_producer
        ro_entries = catalog.find_by_affordance_id("required_output.insert_or_bind_producer")
        assert len(ro_entries) == 1
        ro_entry = ro_entries[0]
        assert ro_entry.materialization_plan_id == "stage7.step_producer_repair.v1"
        assert ro_entry.selectable_ref_policy_id == "required_output.producer.selectable_refs.v1"
        assert ro_entry.intent_schema_id == "intent.insert_producer_step.v1"
        assert ro_entry.required_context_facts == (
            "target_output_name",
            "worker_id",
            "available_variables",
            "nearby_steps",
            "symbol_table",
        )
        assert ro_entry.stage_authority == "stage7.worker_step_plan"
        assert ro_entry.user_facing is True

        # Test exception_flow.add_handler_step
        ef_entries = catalog.find_by_affordance_id("exception_flow.add_handler_step")
        assert len(ef_entries) == 1
        ef_entry = ef_entries[0]
        assert ef_entry.materialization_plan_id == "stage7.exception_handler_step_repair.v1"
        assert ef_entry.selectable_ref_policy_id == "exception_flow.handler.selectable_refs.v1"
        assert ef_entry.intent_schema_id == "intent.add_exception_handler_step.v1"
        assert ef_entry.required_context_facts == (
            "exception_condition",
            "worker_id",
            "available_variables",
            "nearby_steps",
            "symbol_table",
        )
        assert ef_entry.stage_authority == "stage7.worker_step_plan"
        assert ef_entry.user_facing is True

        # Test worker_promotion.resolve_contract (Verify all 4 generated entries)
        wp_entries = catalog.find_by_affordance_id("worker_promotion.resolve_contract")
        assert len(wp_entries) == 4
        for wp_entry in wp_entries:
            assert wp_entry.materialization_plan_id == "worker_handoff.contract_repair.v1"
            assert (
                wp_entry.selectable_ref_policy_id == "worker_promotion.handoff.selectable_refs.v1"
            )
            assert wp_entry.intent_schema_id == "intent.worker_promotion_resolution.v1"
            assert wp_entry.required_context_facts == (
                "delegation_intent",
                "worker_id",
                "candidate_name",
                "possible_inputs",
                "possible_outputs",
                "hierarchy_graph",
            )
            assert wp_entry.stage_authority == "stage3_5.worker_boundary + stage7.worker_step_plan"
            assert wp_entry.user_facing is True

    def test_construct_registry_does_not_import_runtime_materialization(self) -> None:
        """Verify construct_registry.py does not import materialization, intent, or selectable_refs."""  # noqa: E501
        import ast

        # Read the file content of construct_registry.py
        with open("src/nl2spl/compiler/construct_registry.py", encoding="utf-8") as f:
            content = f.read()

        tree = ast.parse(content, filename="construct_registry.py")

        def is_forbidden(name: str) -> bool:
            # Check if name contains any of the forbidden package chains
            for term in [
                "spl_editing.materialization",
                "spl_editing.intent",
                "spl_editing.selectable_refs",
            ]:
                if term in name:
                    return True
            return False

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not is_forbidden(alias.name), f"Forbidden import: {alias.name}"
            elif isinstance(node, ast.ImportFrom):
                module_name = node.module or ""
                assert not is_forbidden(module_name), f"Forbidden import from module: {module_name}"
                for alias in node.names:
                    full_name = f"{module_name}.{alias.name}" if module_name else alias.name
                    assert not is_forbidden(full_name), f"Forbidden import of target: {full_name}"

    @pytest.mark.parametrize("missing_plan", [None, "", "   "])
    def test_missing_materialization_plan_makes_editable_option_unavailable(
        self, missing_plan: str | None
    ) -> None:
        """Verify that missing/empty/whitespace plan metadata defaults/forces user_facing = False."""  # noqa: E501
        from nl2spl.compiler.construct_registry import ConstructIRS, RepairAffordanceSpec, SlotSpec

        custom_registry = SPLConstructRegistry()
        custom_registry.register(
            ConstructIRS(
                construct_type="CUSTOM_CONSTRUCT",
                existence_policy="source_signal_required",
                source_signals=["custom"],
                slots=[
                    SlotSpec(
                        slot_name="custom_slot",
                        missing_diagnostic="custom_diagnostic",
                        repair_affordances=(
                            RepairAffordanceSpec(
                                affordance_id="custom.affordance",
                                description="Test affordance",
                                supported_patch_types=("TestPatch",),
                                user_facing=True,
                                materialization_plan_id=missing_plan,
                            ),
                        ),
                    )
                ],
            )
        )
        catalog = RepairCatalogBuilder.from_construct_registry(custom_registry)
        entries = catalog.find_by_affordance_id("custom.affordance")
        assert len(entries) == 1
        entry = entries[0]
        assert entry.materialization_plan_id == missing_plan
        assert entry.user_facing is False

    def test_explicitly_non_user_facing_remains_hidden_even_with_valid_plan(self) -> None:
        """Verify that an affordance explicitly set to user_facing=False remains False after builder processing,
        even if it has a valid materialization_plan_id.
        """  # noqa: E501
        from nl2spl.compiler.construct_registry import ConstructIRS, RepairAffordanceSpec, SlotSpec

        custom_registry = SPLConstructRegistry()
        custom_registry.register(
            ConstructIRS(
                construct_type="CUSTOM_CONSTRUCT",
                existence_policy="source_signal_required",
                source_signals=["custom"],
                slots=[
                    SlotSpec(
                        slot_name="custom_slot",
                        missing_diagnostic="custom_diagnostic",
                        repair_affordances=(
                            RepairAffordanceSpec(
                                affordance_id="custom.affordance",
                                description="Test affordance",
                                supported_patch_types=("TestPatch",),
                                user_facing=False,  # Explicitly False
                                materialization_plan_id="valid.plan.id.v1",  # Valid plan
                            ),
                        ),
                    )
                ],
            )
        )
        catalog = RepairCatalogBuilder.from_construct_registry(custom_registry)
        entries = catalog.find_by_affordance_id("custom.affordance")
        assert len(entries) == 1
        entry = entries[0]
        assert entry.materialization_plan_id == "valid.plan.id.v1"
        assert entry.user_facing is False

    def test_catalog_builder_does_not_synthesize_default_materialization_plan(self) -> None:
        """Verify no fallback synthesis in the builder."""
        from nl2spl.compiler.construct_registry import ConstructIRS, RepairAffordanceSpec, SlotSpec

        # Create a registry with an affordance that has no materialization_plan_id, but user_facing is True in registry spec.  # noqa: E501
        custom_registry = SPLConstructRegistry()
        custom_registry.register(
            ConstructIRS(
                construct_type="CUSTOM_CONSTRUCT",
                existence_policy="source_signal_required",
                source_signals=["custom"],
                slots=[
                    SlotSpec(
                        slot_name="custom_slot",
                        missing_diagnostic="custom_diagnostic",
                        repair_affordances=(
                            RepairAffordanceSpec(
                                affordance_id="custom.affordance",
                                description="Test affordance",
                                supported_patch_types=("TestPatch",),
                                user_facing=True,  # In registry it is user_facing
                                materialization_plan_id=None,  # But plan is None
                            ),
                        ),
                    )
                ],
            )
        )
        catalog = RepairCatalogBuilder.from_construct_registry(custom_registry)
        entries = catalog.find_by_affordance_id("custom.affordance")
        assert len(entries) == 1
        entry = entries[0]
        assert entry.materialization_plan_id is None
        # Should be downgraded to False, not synthesized or kept as True
        assert entry.user_facing is False
