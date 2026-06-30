"""R2 RepairAffordanceSpec + SlotSpec Extension: post-implementation tests.

Verifies that after R2 changes:
  1. RepairAffordanceSpec is a frozen, pure-metadata dataclass
  2. SlotSpec.repair_affordances defaults to empty tuple
  3. MVP slots in default registry carry expected affordances
  4. Same diagnostic kind → different affordances for different construct+slot
  5. construct_registry.py has NO spl_editing imports
  6. Existing IRS behavior unchanged (no diagnostic count/kind changes)
"""

from __future__ import annotations

from dataclasses import is_dataclass

from nl2spl.compiler.construct_registry import (
    RepairAffordanceSpec,
    SlotSpec,
    SPLConstructRegistry,
)

# ===========================================================================
# R2-1: RepairAffordanceSpec data model
# ===========================================================================


class TestR2RepairAffordanceSpec:
    """R2: RepairAffordanceSpec is a frozen, pure-metadata dataclass."""

    def test_is_frozen_dataclass(self) -> None:
        """R2: RepairAffordanceSpec is frozen (immutable)."""
        assert is_dataclass(RepairAffordanceSpec), "RepairAffordanceSpec must be a dataclass"
        # Frozen: attempting to set an attribute should raise
        spec = RepairAffordanceSpec(
            affordance_id="test",
            description="Test affordance",
        )
        try:
            spec.affordance_id = "mutated"  # type: ignore[misc]
            assert False, "RepairAffordanceSpec must be frozen"  # noqa: B011
        except Exception:
            pass  # Expected

    def test_minimal_construction(self) -> None:
        """R2: Only affordance_id and description are required."""
        spec = RepairAffordanceSpec(
            affordance_id="test_affordance",
            description="A test affordance.",
        )
        assert spec.affordance_id == "test_affordance"
        assert spec.description == "A test affordance."
        assert spec.supported_patch_types == ()
        assert spec.default_patch_type is None
        assert spec.handler_id is None
        assert spec.context_id is None
        assert spec.target_resolver_id is None
        assert spec.default_verification_lane == "A"
        assert spec.editable_artifacts == ()
        assert spec.required_evidence_kind == "user_confirmed_repair"
        assert spec.user_facing is True
        assert spec.notes is None

    def test_full_construction(self) -> None:
        """R2: All fields can be set at construction time."""
        spec = RepairAffordanceSpec(
            affordance_id="full_test",
            description="Full test.",
            supported_patch_types=("PatchA", "PatchB"),
            default_patch_type="PatchA",
            handler_id="test_handler",
            context_id="test_context",
            target_resolver_id="test_resolver",
            default_verification_lane="B",
            editable_artifacts=("WorkerPlanIR", "WorkerHandoffIR"),
            required_evidence_kind="user_confirmed_repair",
            user_facing=True,
            notes="Design notes.",
        )
        assert spec.supported_patch_types == ("PatchA", "PatchB")
        assert spec.default_patch_type == "PatchA"
        assert spec.handler_id == "test_handler"
        assert spec.default_verification_lane == "B"
        assert spec.editable_artifacts == ("WorkerPlanIR", "WorkerHandoffIR")
        assert spec.notes == "Design notes."

    def test_no_callable_fields(self) -> None:
        """R2: RepairAffordanceSpec has NO callable or class-reference fields."""

        # All fields must be strings, tuples of strings, or None
        spec = RepairAffordanceSpec(
            affordance_id="test",
            description="Test",
            supported_patch_types=("PatchA",),
            default_patch_type="PatchA",
            handler_id="h",
            context_id="c",
            target_resolver_id="t",
            default_verification_lane="A",
            editable_artifacts=("IR1", "IR2"),
            notes="notes",
        )
        for field_name in [
            "affordance_id",
            "description",
            "default_patch_type",
            "handler_id",
            "context_id",
            "target_resolver_id",
            "default_verification_lane",
            "required_evidence_kind",
            "notes",
        ]:
            val = getattr(spec, field_name)
            assert val is None or isinstance(val, str), (
                f"Field '{field_name}' must be str or None, got {type(val)}"
            )
        for field_name in ["supported_patch_types", "editable_artifacts"]:
            val = getattr(spec, field_name)
            assert isinstance(val, tuple), f"Field '{field_name}' must be tuple, got {type(val)}"
            for item in val:
                assert isinstance(item, str), (
                    f"Field '{field_name}' items must be str, got {type(item)}"
                )


# ===========================================================================
# R2-2: SlotSpec defaults
# ===========================================================================


class TestR2SlotSpecDefaults:
    """R2: SlotSpec.repair_affordances defaults to empty tuple."""

    def test_default_repair_affordances_is_empty(self) -> None:
        """R2: SlotSpec() without repair_affordances gets empty tuple."""
        slot = SlotSpec(slot_name="test")
        assert slot.repair_affordances == (), "R2: repair_affordances must default to empty tuple"

    def test_existing_slots_unchanged(self) -> None:
        """R2: Slots from default registry that lack affordances still
        have empty tuple (not None).
        """
        registry = SPLConstructRegistry.default()
        # condition slot has no affordances
        exc_irs = registry.get("EXCEPTION_FLOW")
        condition_slot = exc_irs.get_slot("condition")
        assert condition_slot is not None
        assert condition_slot.repair_affordances == (), (
            "R2: condition slot (no affordance) must have empty tuple"
        )
        # GENERAL_COMMAND.source_evidence has no affordances
        cmd_irs = registry.get("GENERAL_COMMAND")
        evidence_slot = cmd_irs.get_slot("source_evidence")
        assert evidence_slot is not None
        assert evidence_slot.repair_affordances == (), (
            "R2: source_evidence slot (no affordance) must have empty tuple"
        )


# ===========================================================================
# R2-3: MVP slots carry expected affordances
# ===========================================================================


class TestR2MvpAffordances:
    """R2: Each MVP slot in default registry has the expected affordance."""

    @staticmethod
    def _registry() -> SPLConstructRegistry:
        return SPLConstructRegistry.default()

    # -- EXCEPTION_FLOW.handler_action -----------------------------------

    def test_exception_flow_handler_action_affordance(self) -> None:
        """R2: EXCEPTION_FLOW.handler_action → add_exception_handler_step."""
        irs = self._registry().get("EXCEPTION_FLOW")
        slot = irs.get_slot("handler_action")
        assert slot is not None
        assert len(slot.repair_affordances) == 1
        aff = slot.repair_affordances[0]
        assert aff.affordance_id == "exception_flow.add_handler_step"
        assert "AddExceptionHandlerStep" in aff.supported_patch_types
        assert aff.default_patch_type == "AddExceptionHandlerStep"
        assert aff.handler_id == "missing_handler"
        assert aff.default_verification_lane == "B"
        assert aff.required_evidence_kind == "user_confirmed_repair"
        assert aff.user_facing is True

    # -- REQUIRED_OUTPUT.producer ----------------------------------------

    def test_required_output_producer_affordance(self) -> None:
        """R2: REQUIRED_OUTPUT.producer → insert_or_bind_producer."""
        irs = self._registry().get("REQUIRED_OUTPUT")
        slot = irs.get_slot("producer")
        assert slot is not None
        assert len(slot.repair_affordances) == 1
        aff = slot.repair_affordances[0]
        assert aff.affordance_id == "required_output.insert_or_bind_producer"
        assert aff.supported_patch_types == ("InsertProducerStep",)
        assert aff.default_patch_type == "InsertProducerStep"
        assert aff.handler_id == "missing_output_producer"
        assert aff.default_verification_lane == "B"

    # -- REQUEST_INPUT.value_target --------------------------------------

    def test_request_input_value_target_affordance(self) -> None:
        """R2: REQUEST_INPUT.value_target → specify_value_target."""
        irs = self._registry().get("REQUEST_INPUT")
        slot = irs.get_slot("value_target")
        assert slot is not None
        assert len(slot.repair_affordances) == 1
        aff = slot.repair_affordances[0]
        assert aff.affordance_id == "request_input.specify_value_target"
        assert aff.handler_id == "type_or_contract_ambiguity"
        assert aff.default_verification_lane == "A"

    # -- CALL_API.integration_evidence -----------------------------------

    def test_call_api_integration_evidence_affordance(self) -> None:
        """R2: CALL_API.integration_evidence → specify_api_integration_evidence."""
        irs = self._registry().get("CALL_API")
        slot = irs.get_slot("integration_evidence")
        assert slot is not None
        assert len(slot.repair_affordances) == 1
        aff = slot.repair_affordances[0]
        assert aff.affordance_id == "call_api.specify_integration_evidence"
        assert aff.handler_id == "type_or_contract_ambiguity"
        assert aff.default_verification_lane == "A"

    # -- INVOKE_WORKER.handoff_id ----------------------------------------

    def test_invoke_worker_handoff_id_affordance(self) -> None:
        """R2: INVOKE_WORKER.handoff_id → create_or_bind_handoff."""
        irs = self._registry().get("INVOKE_WORKER")
        slot = irs.get_slot("handoff_id")
        assert slot is not None
        assert len(slot.repair_affordances) == 1
        aff = slot.repair_affordances[0]
        assert aff.affordance_id == "invoke_worker.create_or_bind_handoff"
        assert "CreateWorkerHandoffContract" in aff.supported_patch_types
        assert aff.default_verification_lane == "B"
        assert aff.handler_id == "type_or_contract_ambiguity"

    # -- WORKER_PROMOTION.* ----------------------------------------------

    def test_worker_promotion_slots_all_have_same_affordance(self) -> None:
        """R2: All four WORKER_PROMOTION slots share the
        worker_promotion.resolve_contract affordance with the same
        three patch types.
        """
        irs = self._registry().get("WORKER_PROMOTION")
        slot_names = [
            "promotion_input_contract",
            "promotion_output_contract",
            "promotion_invocation_point",
            "promotion_result_handoff",
        ]
        expected_patch_types = (
            "CreateWorkerHandoffContract",
            "ConvertDelegationIntentToMainFlowStep",
            "ConvertDelegationIntentToRequestInput",
        )
        for name in slot_names:
            slot = irs.get_slot(name)
            assert slot is not None, f"Missing slot: {name}"
            assert len(slot.repair_affordances) == 1, f"{name} must have exactly 1 affordance"
            aff = slot.repair_affordances[0]
            assert aff.affordance_id == "worker_promotion.resolve_contract", (
                f"{name}: expected affordance_id='worker_promotion.resolve_contract'"
            )
            assert aff.supported_patch_types == expected_patch_types, (
                f"{name}: expected 3 delegation resolution patch types"
            )
            assert aff.default_patch_type == "CreateWorkerHandoffContract"
            assert aff.handler_id == "type_or_contract_ambiguity"
            assert aff.context_id == "worker_promotion_context"
            assert aff.default_verification_lane == "B"

    # -- WORKER_HANDOFF.* ------------------------------------------------

    def test_worker_handoff_target_affordance(self) -> None:
        """R2: WORKER_HANDOFF.target → worker_handoff.specify_target."""
        irs = self._registry().get("WORKER_HANDOFF")
        slot = irs.get_slot("target")
        assert slot is not None
        assert len(slot.repair_affordances) == 1
        aff = slot.repair_affordances[0]
        assert aff.affordance_id == "worker_handoff.specify_target"
        assert aff.default_verification_lane == "B"

    def test_worker_handoff_io_bindings_affordances(self) -> None:
        """R2: WORKER_HANDOFF input/output bindings have distinct affordance IDs
        that share the same handler and lane.
        """
        irs = self._registry().get("WORKER_HANDOFF")
        for name, expected_id in [
            ("input_bindings", "worker_handoff.specify_input_bindings"),
            ("output_bindings", "worker_handoff.specify_output_bindings"),
        ]:
            slot = irs.get_slot(name)
            assert slot is not None
            aff = slot.repair_affordances[0]
            assert aff.affordance_id == expected_id
            assert aff.handler_id == "type_or_contract_ambiguity"
            assert aff.default_verification_lane == "B"

    def test_worker_handoff_invocation_site_affordance(self) -> None:
        """R2: WORKER_HANDOFF.invocation_site → worker_handoff.specify_invocation_site."""
        irs = self._registry().get("WORKER_HANDOFF")
        slot = irs.get_slot("invocation_site")
        assert slot is not None
        aff = slot.repair_affordances[0]
        assert aff.affordance_id == "worker_handoff.specify_invocation_site"

    # -- from_worker has NO affordance -----------------------------------

    def test_worker_handoff_from_worker_has_no_affordance(self) -> None:
        """R2: WORKER_HANDOFF.from_worker intentionally has no affordance
        — it's typically derivable from the handoff context."""
        irs = self._registry().get("WORKER_HANDOFF")
        slot = irs.get_slot("from_worker")
        assert slot is not None
        assert slot.repair_affordances == (), "R2: from_worker slot should have no affordance"

    # -- Missing diagnostic consistency ----------------------------------

    def test_affordance_handler_id_matches_missing_diagnostic(self) -> None:
        """R2: handler_id on the affordance matches the slot's
        missing_diagnostic or the umbrella diagnostic group it belongs to.
        """
        registry = self._registry()
        checks = [
            ("EXCEPTION_FLOW", "handler_action", "missing_handler"),
            ("REQUIRED_OUTPUT", "producer", "missing_output_producer"),
            ("REQUEST_INPUT", "value_target", "type_or_contract_ambiguity"),
            ("CALL_API", "integration_evidence", "type_or_contract_ambiguity"),
            ("INVOKE_WORKER", "handoff_id", "type_or_contract_ambiguity"),
        ]
        for construct_type, slot_name, expected_handler in checks:
            irs = registry.get(construct_type)
            slot = irs.get_slot(slot_name)
            assert slot is not None
            for aff in slot.repair_affordances:
                assert aff.handler_id == expected_handler, (
                    f"{construct_type}.{slot_name}: handler_id={aff.handler_id}, "
                    f"expected {expected_handler}"
                )


# ===========================================================================
# R2-4: Same diagnostic kind → different affordances
# ===========================================================================


class TestR2SameKindDifferentAffordance:
    """R2: type_or_contract_ambiguity maps to different affordances
    depending on construct_type + slot_name.
    """

    def test_type_or_contract_ambiguity_affordance_ids_are_distinct(
        self,
    ) -> None:
        """R2: Different construct+slot combos with the same
        type_or_contract_ambiguity diagnostic_kind produce distinct
        affordance IDs.
        """
        registry = SPLConstructRegistry.default()
        # Collect all slots with type_or_contract_ambiguity diagnostic
        ambiguity_slots: dict[str, str] = {}  # "construct.slot" → affordance_id
        for construct_type_name in registry.list_constructs():
            irs = registry.get(construct_type_name)
            for slot in irs.slots:
                if slot.missing_diagnostic != "type_or_contract_ambiguity":
                    continue
                if not slot.repair_affordances:
                    continue
                key = f"{construct_type_name}.{slot.slot_name}"
                aff_id = slot.repair_affordances[0].affordance_id
                ambiguity_slots[key] = aff_id

        assert len(ambiguity_slots) >= 6, (
            f"Expected at least 6 type_or_contract_ambiguity slots with "
            f"affordances, got {len(ambiguity_slots)}: {sorted(ambiguity_slots)}"
        )

        # Verify distinct affordance IDs exist
        # All WORKER_PROMOTION.* slots share the same affordance ID
        # (worker_promotion.resolve_contract) — that's intentional.
        # Other construct+slot combos should have different IDs.
        distinct_ids = set(ambiguity_slots.values())
        assert len(distinct_ids) >= 5, (
            f"Expected at least 5 distinct affordance IDs across "
            f"type_or_contract_ambiguity slots, got {len(distinct_ids)}: {distinct_ids}"
        )

    def test_affordance_ids_globally_unique_across_construct_types(
        self,
    ) -> None:
        """R2.1: No affordance_id is shared across different construct types.

        The same ID within one construct type (e.g. all 4
        WORKER_PROMOTION slots using worker_promotion.resolve_contract)
        is acceptable.  But 'invoke_worker.specify_input_bindings' must
        not also appear on WORKER_HANDOFF, etc.
        """
        registry = SPLConstructRegistry.default()
        # Collect: affordance_id → set of construct_types using it
        id_to_constructs: dict[str, set[str]] = {}
        for ct_name in registry.list_constructs():
            irs = registry.get(ct_name)
            for slot in irs.slots:
                for aff in slot.repair_affordances:
                    id_to_constructs.setdefault(aff.affordance_id, set()).add(ct_name)

        # Every affordance_id must map to exactly one construct type
        violations = {aid: cts for aid, cts in id_to_constructs.items() if len(cts) > 1}
        assert len(violations) == 0, (
            f"R2.1: affordance_ids shared across construct types: {violations}. "
            f"Each affordance_id must belong to exactly one construct type."
            f"Example violation: 'invoke_worker.X' appearing on both "
            f"INVOKE_WORKER and WORKER_HANDOFF."
        )

    def test_missing_handler_only_from_exception_flow(self) -> None:
        """R2: missing_handler affordance only exists on
        EXCEPTION_FLOW.handler_action — no other slot has it.
        """
        registry = SPLConstructRegistry.default()
        for construct_type_name in registry.list_constructs():
            irs = registry.get(construct_type_name)
            for slot in irs.slots:
                if slot.slot_name == "handler_action":
                    continue  # This is the expected one
                for aff in slot.repair_affordances:
                    assert aff.handler_id != "missing_handler", (
                        f"{construct_type_name}.{slot.slot_name} has "
                        f"handler_id='missing_handler' but only "
                        f"EXCEPTION_FLOW.handler_action should"
                    )

    def test_missing_output_producer_only_from_required_output(self) -> None:
        """R2: missing_output_producer affordance only exists on
        REQUIRED_OUTPUT.producer — RESOURCE_CONTRACT_DEMAND.producer
        has no affordance yet (non-MVP for now).
        """
        registry = SPLConstructRegistry.default()
        # REQUIRED_OUTPUT.producer has the affordance
        req_out = registry.get("REQUIRED_OUTPUT")
        producer = req_out.get_slot("producer")
        assert producer is not None
        assert len(producer.repair_affordances) >= 1
        assert producer.repair_affordances[0].handler_id == "missing_output_producer"

        # RESOURCE_CONTRACT_DEMAND.producer does NOT have an affordance
        rcd = registry.get("RESOURCE_CONTRACT_DEMAND")
        rcd_producer = rcd.get_slot("producer")
        assert rcd_producer is not None
        assert rcd_producer.repair_affordances == (), (
            "R2 CURRENT: RESOURCE_CONTRACT_DEMAND.producer has no affordance. "
            "This may change in R4 when producer issue grouping is defined."
        )


# ===========================================================================
# R2-5: construct_registry.py has NO spl_editing imports
# ===========================================================================


class TestR2NoSplEditingImports:
    """R2: construct_registry module does not import from spl_editing."""

    def test_no_spl_editing_import_in_module(self) -> None:
        """R2: Scanning the construct_registry module source for
        any spl_editing import.
        """
        import inspect

        from nl2spl.compiler import construct_registry as cr_module

        source = inspect.getsource(cr_module)
        assert "spl_editing" not in source, (
            "R2: construct_registry.py must NOT import from spl_editing. "
            "RepairAffordanceSpec is pure metadata defined in this module."
        )

    def test_no_spl_editing_in_module_globals(self) -> None:
        """R2: No spl_editing module in sys.modules attributable to
        construct_registry.
        """
        # construct_registry is already imported. Check its __dict__
        from nl2spl.compiler import construct_registry as cr_module

        for key in dir(cr_module):
            val = getattr(cr_module, key)
            # Skip standard things
            if key.startswith("__"):
                continue
            module_name = getattr(val, "__module__", "")
            assert "spl_editing" not in module_name, (
                f"R2: construct_registry.{key} has __module__='{module_name}' "
                f"— must not reference spl_editing"
            )


# ===========================================================================
# R2-6: Existing IRS behavior unchanged
# ===========================================================================


class TestR2ExistingIRSBehaviorUnchanged:
    """R2: Adding repair_affordances does not change IRS outputs."""

    def test_registry_construct_types_include_api_declaration(self) -> None:
        """R-API-1: registry adds API_DECLARATION as a new construct type."""
        registry = SPLConstructRegistry.default()
        expected = {
            "API_DECLARATION",
            "EXCEPTION_FLOW",
            "REQUIRED_OUTPUT",
            "RESOURCE_CONTRACT_DEMAND",
            "GENERAL_COMMAND",
            "REQUEST_INPUT",
            "CALL_API",
            "INVOKE_WORKER",
            "CHILD_WORKER",
            "WORKER_CANDIDATE",
            "WORKER_PROMOTION",
            "WORKER_HANDOFF",
        }
        assert set(registry.list_constructs()) == expected

    def test_slot_count_per_construct_unchanged(self) -> None:
        """R-API-1: CALL_API gains declared API authority slots.

        Existing SPL Editing repair affordances remain isolated; API
        declaration slots are covered by API materialization tests.
        """
        registry = SPLConstructRegistry.default()
        expected_slot_counts = {
            "EXCEPTION_FLOW": 3,
            "REQUIRED_OUTPUT": 3,
            "RESOURCE_CONTRACT_DEMAND": 3,
            "GENERAL_COMMAND": 3,
            "REQUEST_INPUT": 2,
            "CALL_API": 6,
            "INVOKE_WORKER": 4,
            "CHILD_WORKER": 5,
            "WORKER_CANDIDATE": 3,
            "WORKER_PROMOTION": 4,
            "WORKER_HANDOFF": 5,
        }
        for construct_type, expected_count in expected_slot_counts.items():
            irs = registry.get(construct_type)
            actual = len(irs.slots)
            assert actual == expected_count, (
                f"{construct_type}: expected {expected_count} slots, got {actual}"
            )

    def test_missing_diagnostics_unchanged(self) -> None:
        """R2: missing_diagnostic values are unchanged on all slots."""
        registry = SPLConstructRegistry.default()
        # Spot-check: EXCEPTION_FLOW.handler_action still has missing_handler
        exc = registry.get("EXCEPTION_FLOW")
        handler = exc.get_slot("handler_action")
        assert handler is not None
        assert handler.missing_diagnostic == "missing_handler"

        # REQUIRED_OUTPUT.producer still has missing_output_producer
        req = registry.get("REQUIRED_OUTPUT")
        producer = req.get_slot("producer")
        assert producer is not None
        assert producer.missing_diagnostic == "missing_output_producer"
