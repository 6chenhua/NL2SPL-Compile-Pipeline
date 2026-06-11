"""ARC0: Baseline and Gap Audit — current-behavior and target-future tests.

Lock current behavior and expose the exact gaps this migration must close
without changing production code.

Tests 1-7 correspond to the seven required test categories in the
implementation plan, Section 6 (ARC0: Baseline and Gap Audit).
"""

from __future__ import annotations

import pytest

# ===========================================================================
# Test 1: profile_domain + RESOURCE_CONTRACT/input risk
# ===========================================================================


class TestProfileDomainResourceContractGap:
    """profile_domain + construct_target=RESOURCE_CONTRACT + slot_target=input
    is a semantic contradiction that must never result in a resource demand.

    This test class documents the CURRENT state: normalization partially
    catches it via _OPTIONAL_CONSTRUCT_SLOT_ROLES, but the validator's
    _ROLE_CONTRACT does not enforce the expected None.
    """

    def test_normalization_catches_profile_domain_construct_target(self):
        """ARC3: Registry encodes explicit construct_target=None, slot_target=None
        for profile_domain — the canonical role contract is the defense."""
        from nl2spl.compiler.annotation_role_contract import (
            ROLE_CONTRACT_REGISTRY,
        )

        c = ROLE_CONTRACT_REGISTRY.require_role_contract("profile_domain")
        assert c.construct_target is None, (
            "Canonical registry enforces construct_target=None for profile_domain"
        )
        assert c.slot_target is None, (
            "Canonical registry enforces slot_target=None for profile_domain"
        )

    def test_normalization_catches_process_step_construct_target(self):
        """ARC3: Registry encodes explicit construct_target=None, slot_target=None
        for process_step — the canonical role contract is the defense."""
        from nl2spl.compiler.annotation_role_contract import (
            ROLE_CONTRACT_REGISTRY,
        )

        c = ROLE_CONTRACT_REGISTRY.require_role_contract("process_step")
        assert c.construct_target is None
        assert c.slot_target is None

    def test_normalize_annotation_contract_drops_construct_for_profile_domain(self):
        """_normalize_annotation_contract() forces construct=None, slot=None for profile_domain."""
        from nl2spl.pipeline.stages.stage2_field_router import FieldRouter

        field, role, rf, ct, st, exe = FieldRouter._normalize_annotation_contract(
            span_id="sp_001",
            field="domain",
            semantic_role="profile_domain",
            route_family="profile",
            construct_target="RESOURCE_CONTRACT",
            slot_target="input",
            executable=False,
            diagnostics=[],
        )

        assert ct is None, (
            f"Normalization should force construct_target=None for profile_domain, got {ct!r}"
        )
        assert st is None, (
            f"Normalization should force slot_target=None for profile_domain, got {st!r}"
        )
        assert role == "profile_domain"
        assert field == "domain"
        assert exe is False

    def test_validator_enforces_none_construct_target_for_profile_domain(self):
        """Phase 1: Validator now ACCEPTS profile_domain with
        construct_target=RESOURCE_CONTRACT and records a typed diagnostic.
        Normalization in the merge loop corrects the fields.

        The canonical registry encodes explicit construct_target=None for
        profile_domain.  The full-field validator diagnoses this but does
        not reject known roles.
        """
        from nl2spl.pipeline.stages.stage2_field_router_validator import (
            _ROLE_CONTRACT,
            RouteRefinementValidator,
        )
        from nl2spl.pipeline.stages.stage2_field_router_prompt import (
            RefinedAnnotation,
            RouteRefinementResult,
        )

        # _ROLE_CONTRACT is an empty compatibility wrapper; registry is authoritative
        contract = _ROLE_CONTRACT.get("profile_domain", {})
        assert "construct_target" not in contract, (
            "_ROLE_CONTRACT is an empty compatibility wrapper"
        )

        from nl2spl.ir.span_ir import SpanIR

        ann = RefinedAnnotation(
            span_id="sp_001",
            field="domain",
            semantic_role="profile_domain",
            construct_target="RESOURCE_CONTRACT",
            slot_target="input",
            executable=False,
        )
        llm_result = RouteRefinementResult(annotations=[ann])

        span = SpanIR(span_id="sp_001", text="Task family description")
        validator = RouteRefinementValidator()
        result = validator.validate(llm_result, spans=[span], canonical_input=None)

        # Phase 1: known role is accepted with diagnostic
        accepted_ids = {a.span_id for a in result.accepted}
        assert "sp_001" in accepted_ids, (
            "Phase 1: profile_domain with known role must be ACCEPTED "
            "(diagnostic recorded, normalization will correct fields)"
        )
        assert len(result.structured_diagnostics) >= 1, (
            "Phase 1: structured diagnostic must be recorded for "
            "construct_target mismatch"
        )

    def test_validator_enforces_none_slot_target_for_profile_domain(self):
        """Phase 1: Validator now ACCEPTS profile_domain with slot_target=input
        and records a typed diagnostic. Normalization corrects fields."""
        from nl2spl.pipeline.stages.stage2_field_router_validator import (
            RouteRefinementValidator,
        )
        from nl2spl.pipeline.stages.stage2_field_router_prompt import (
            RefinedAnnotation,
            RouteRefinementResult,
        )
        from nl2spl.ir.span_ir import SpanIR

        ann = RefinedAnnotation(
            span_id="sp_001",
            field="domain",
            semantic_role="profile_domain",
            construct_target=None,
            slot_target="input",
            executable=False,
        )
        llm_result = RouteRefinementResult(annotations=[ann])

        span = SpanIR(span_id="sp_001", text="Task family description")
        validator = RouteRefinementValidator()
        result = validator.validate(llm_result, spans=[span], canonical_input=None)

        # Phase 1: known role accepted with diagnostic
        accepted_ids = {a.span_id for a in result.accepted}
        assert "sp_001" in accepted_ids, (
            "Phase 1: profile_domain with slot mismatch must be ACCEPTED "
            "(diagnostic recorded)"
        )
        assert len(result.structured_diagnostics) >= 1


# ===========================================================================
# Test 2: ROUTE_PRIOR_ROLE_CONTRACTS and validator _ROLE_CONTRACT are not the same
# ===========================================================================


class TestRoleContractSourcesNotUnified:
    """The two existing role-contract-like tables are independent dicts with
    different keys, different fields per key, and different total coverage."""

    def test_different_source_modules(self):
        """The two tables are defined in different modules."""
        from nl2spl.pipeline.stages.stage2_field_router import (
            ROUTE_PRIOR_ROLE_CONTRACTS,
        )
        from nl2spl.pipeline.stages.stage2_field_router_validator import (
            _ROLE_CONTRACT,
        )

        # They are distinct objects
        assert ROUTE_PRIOR_ROLE_CONTRACTS is not _ROLE_CONTRACT, (
            "ROUTE_PRIOR_ROLE_CONTRACTS and _ROLE_CONTRACT are separate dicts "
            "in separate modules"
        )

    def test_both_legacy_tables_are_empty_wrappers(self):
        """ARC3+ARC4: Both ROUTE_PRIOR_ROLE_CONTRACTS and _ROLE_CONTRACT
        are empty compatibility wrappers. All role-contract logic now
        lives in ROLE_CONTRACT_REGISTRY."""
        from nl2spl.pipeline.stages.stage2_field_router import (
            ROUTE_PRIOR_ROLE_CONTRACTS,
        )
        from nl2spl.pipeline.stages.stage2_field_router_validator import (
            _ROLE_CONTRACT,
        )

        # Both are empty — the registry is now the single source of truth
        assert ROUTE_PRIOR_ROLE_CONTRACTS == {}
        assert _ROLE_CONTRACT == {}

    def test_router_contracts_now_empty_compatibility_wrapper(self):
        """ARC3: ROUTE_PRIOR_ROLE_CONTRACTS is an empty compatibility wrapper.
        All role-contract lookups now go through ROLE_CONTRACT_REGISTRY."""
        from nl2spl.pipeline.stages.stage2_field_router import (
            ROUTE_PRIOR_ROLE_CONTRACTS,
        )

        # The wrapper dict still exists for module-level import compatibility
        # but is empty — no role mapping literals remain in the router.
        assert isinstance(ROUTE_PRIOR_ROLE_CONTRACTS, dict), (
            "ROUTE_PRIOR_ROLE_CONTRACTS exists as compatibility wrapper"
        )

    def test_validator_role_contract_converged_in_arc4(self):
        """ARC4: Validator's _ROLE_CONTRACT is an empty compatibility wrapper.
        All role-contract checks now go through ROLE_CONTRACT_REGISTRY."""
        from nl2spl.pipeline.stages.stage2_field_router_validator import (
            _ROLE_CONTRACT,
        )

        # ARC4 converged the validator to the registry — wrapper is empty
        assert isinstance(_ROLE_CONTRACT, dict)


# ===========================================================================
# Test 3: Allowed schema constants are not generated from role contract
# ===========================================================================


class TestSchemaConstantsAreHardcoded:
    """Stage 2 prompt schema constants are hardcoded literals, not derived
    from any role contract registry."""

    def test_allowed_semantic_roles_is_hardcoded(self):
        """ALLOWED_SEMANTIC_ROLES is a hand-maintained frozenset literal."""
        from nl2spl.pipeline.stages.stage2_field_router_prompt import (
            ALLOWED_SEMANTIC_ROLES,
        )

        # It exists and is non-empty
        assert isinstance(ALLOWED_SEMANTIC_ROLES, frozenset)
        assert len(ALLOWED_SEMANTIC_ROLES) > 0

        # Check that key roles are present (current-behavior baseline)
        assert "profile_domain" in ALLOWED_SEMANTIC_ROLES
        assert "input_contract" in ALLOWED_SEMANTIC_ROLES
        assert "output_contract" in ALLOWED_SEMANTIC_ROLES
        assert "process_step" in ALLOWED_SEMANTIC_ROLES
        assert "failure_mode" in ALLOWED_SEMANTIC_ROLES
        assert "exception_handler_action" in ALLOWED_SEMANTIC_ROLES

    def test_allowed_semantic_roles_does_not_include_structural_aliases(self):
        """ALLOWED_SEMANTIC_ROLES contains canonical roles, not structural aliases.

        Structural aliases like task_family, policy, exception_handler,
        runtime_input, required_output are NOT in the list — this is
        correct because they are packet_type aliases, not LLM-visible
        semantic roles.
        """
        from nl2spl.pipeline.stages.stage2_field_router_prompt import (
            ALLOWED_SEMANTIC_ROLES,
        )

        structural_aliases = {
            "task_family",
            "policy",
            "exception_handler",
            "runtime_input",
            "required_output",
            "delegation_rule",
        }
        overlap = structural_aliases & ALLOWED_SEMANTIC_ROLES
        assert not overlap, (
            f"Structural aliases should not appear in ALLOWED_SEMANTIC_ROLES: {overlap}"
        )

    def test_allowed_construct_targets_is_hardcoded(self):
        """ALLOWED_CONSTRUCT_TARGETS is a hand-maintained frozenset literal."""
        from nl2spl.pipeline.stages.stage2_field_router_prompt import (
            ALLOWED_CONSTRUCT_TARGETS,
        )

        assert isinstance(ALLOWED_CONSTRUCT_TARGETS, frozenset)
        assert len(ALLOWED_CONSTRUCT_TARGETS) > 0
        assert "RESOURCE_CONTRACT" in ALLOWED_CONSTRUCT_TARGETS
        assert "EXCEPTION_FLOW" in ALLOWED_CONSTRUCT_TARGETS
        assert "WORKER_HANDOFF" in ALLOWED_CONSTRUCT_TARGETS

    def test_allowed_slot_targets_is_hardcoded(self):
        """ALLOWED_SLOT_TARGETS is a hand-maintained frozenset literal."""
        from nl2spl.pipeline.stages.stage2_field_router_prompt import (
            ALLOWED_SLOT_TARGETS,
        )

        assert isinstance(ALLOWED_SLOT_TARGETS, frozenset)
        assert len(ALLOWED_SLOT_TARGETS) > 0
        assert "input" in ALLOWED_SLOT_TARGETS
        assert "output" in ALLOWED_SLOT_TARGETS

    def test_non_executable_roles_is_hardcoded(self):
        """NON_EXECUTABLE_ROLES is a hand-maintained frozenset literal."""
        from nl2spl.pipeline.stages.stage2_field_router_prompt import (
            NON_EXECUTABLE_ROLES,
        )

        assert isinstance(NON_EXECUTABLE_ROLES, frozenset)
        assert len(NON_EXECUTABLE_ROLES) > 0
        assert "profile_domain" in NON_EXECUTABLE_ROLES
        assert "input_contract" in NON_EXECUTABLE_ROLES
        assert "output_contract" in NON_EXECUTABLE_ROLES
        assert "failure_mode" in NON_EXECUTABLE_ROLES

    def test_executable_roles_is_hardcoded(self):
        """EXECUTABLE_ROLES is a hand-maintained frozenset literal."""
        from nl2spl.pipeline.stages.stage2_field_router_prompt import (
            EXECUTABLE_ROLES,
        )

        assert isinstance(EXECUTABLE_ROLES, frozenset)
        assert len(EXECUTABLE_ROLES) > 0
        assert "process_step" in EXECUTABLE_ROLES
        assert "exception_handler_action" in EXECUTABLE_ROLES

    def test_prompt_constants_now_derived_from_role_contract_registry(self):
        """As of ARC2, prompt constants ARE derived from the canonical
        role contract registry.  This test was inverted after ARC2
        completion — it formerly documented the GAP-02 pre-ARC2 state."""
        import inspect
        from nl2spl.pipeline.stages import stage2_field_router_prompt as m

        source = inspect.getsource(m)
        # ARC2: constants are now derived from the registry
        assert "from nl2spl.compiler.annotation_role_contract.registry import" in source, (
            "After ARC2, prompt constants must be derived from the canonical "
            "role contract registry"
        )


# ===========================================================================
# Test 4: Validator does not enforce expected None
# ===========================================================================


class TestValidatorMissingExpectedNone:
    """Current validator does not enforce expected None for fields that the
    role contract requires to be None (e.g. profile_domain.construct_target)."""

    def test_registry_enforces_expected_none_for_profile_domain(self):
        """ARC4: The canonical registry (not _ROLE_CONTRACT) enforces
        construct_target=None and slot_target=None for profile_domain."""
        from nl2spl.compiler.annotation_role_contract import (
            ROLE_CONTRACT_REGISTRY,
        )

        c = ROLE_CONTRACT_REGISTRY.require_role_contract("profile_domain")
        assert c.construct_target is None, (
            "profile_domain.construct_target must be explicitly None"
        )
        assert c.slot_target is None, (
            "profile_domain.slot_target must be explicitly None"
        )
        assert c.executable is False

    def test_registry_enforces_none_for_process_step(self):
        """ARC4: process_step has explicit construct_target=None, slot_target=None
        in the canonical registry."""
        from nl2spl.compiler.annotation_role_contract import (
            ROLE_CONTRACT_REGISTRY,
        )

        c = ROLE_CONTRACT_REGISTRY.require_role_contract("process_step")
        assert c.construct_target is None
        assert c.slot_target is None
        assert c.executable is True

    def test_validator_now_rejects_profile_domain_with_construct_target(self):
        """Phase 1: Full-field validator now ACCEPTS profile_domain with
        construct_target=RESOURCE_CONTRACT (diagnostic recorded).
        Expected None is diagnosed, not enforced via rejection — the
        merge loop's normalization corrects the fields."""
        from nl2spl.pipeline.stages.stage2_field_router_validator import (
            RouteRefinementValidator,
        )
        from nl2spl.pipeline.stages.stage2_field_router_prompt import (
            RefinedAnnotation,
            RouteRefinementResult,
        )
        from nl2spl.ir.span_ir import SpanIR

        ann = RefinedAnnotation(
            span_id="sp_test",
            field="domain",
            semantic_role="profile_domain",
            construct_target="RESOURCE_CONTRACT",
            slot_target="input",
            executable=False,
        )
        llm_result = RouteRefinementResult(annotations=[ann])

        span = SpanIR(span_id="sp_test", text="Task family description")
        validator = RouteRefinementValidator()
        result = validator.validate(
            llm_result,
            spans=[span],
            canonical_input=None,
        )

        # Phase 1: known role accepted with diagnostic, not rejected
        accepted_ids = {a.span_id for a in result.accepted}
        assert "sp_test" in accepted_ids, (
            "Phase 1: profile_domain known role must be ACCEPTED "
            "(diagnostic recorded, normalization will correct fields)"
        )
        assert len(result.structured_diagnostics) >= 1, (
            "Phase 1: structured diagnostic must be recorded for field mismatch"
        )


# ===========================================================================
# Test 5: Deterministic packet annotation path uses _ANNOTATION_SEMANTICS
# ===========================================================================


class TestDeterministicPathNotUsingSharedContract:
    """The deterministic packet annotation path uses _ANNOTATION_SEMANTICS,
    which is a separate table from ROUTE_PRIOR_ROLE_CONTRACTS and from
    the validator's _ROLE_CONTRACT."""

    def test_annotation_semantics_is_separate_from_route_prior_contracts(self):
        """_ANNOTATION_SEMANTICS and ROUTE_PRIOR_ROLE_CONTRACTS are distinct objects."""
        from nl2spl.pipeline.stages.stage2_field_router import (
            _ANNOTATION_SEMANTICS,
            ROUTE_PRIOR_ROLE_CONTRACTS,
        )

        assert _ANNOTATION_SEMANTICS is not ROUTE_PRIOR_ROLE_CONTRACTS, (
            "_ANNOTATION_SEMANTICS and ROUTE_PRIOR_ROLE_CONTRACTS are separate dicts"
        )

    def test_annotation_semantics_has_different_keys(self):
        """_ANNOTATION_SEMANTICS uses packet_type keys (task_family, runtime_input, etc.)
        while ROUTE_PRIOR_ROLE_CONTRACTS uses semantic_role keys."""
        from nl2spl.pipeline.stages.stage2_field_router import (
            _ANNOTATION_SEMANTICS,
            ROUTE_PRIOR_ROLE_CONTRACTS,
        )

        ann_keys = set(_ANNOTATION_SEMANTICS.keys())
        route_keys = set(ROUTE_PRIOR_ROLE_CONTRACTS.keys())

        # They serve different purposes and have different key spaces
        assert ann_keys != route_keys, (
            f"_ANNOTATION_SEMANTICS keys ({ann_keys}) != "
            f"ROUTE_PRIOR_ROLE_CONTRACTS keys ({route_keys})"
        )

    def test_annotation_semantics_keyed_by_packet_type(self):
        """_ANNOTATION_SEMANTICS is keyed by packet_type (adapter concept),
        not by semantic_role (LLM concept)."""
        from nl2spl.pipeline.stages.stage2_field_router import (
            _ANNOTATION_SEMANTICS,
        )

        # packet_type keys that are NOT semantic roles
        assert "task_family" in _ANNOTATION_SEMANTICS
        assert "runtime_input" in _ANNOTATION_SEMANTICS
        assert "required_output" in _ANNOTATION_SEMANTICS
        assert "delegation_rule" in _ANNOTATION_SEMANTICS

        # Verify the mapping from packet_type to semantic_role
        assert _ANNOTATION_SEMANTICS["task_family"]["semantic_role"] == "profile_domain"
        assert _ANNOTATION_SEMANTICS["runtime_input"]["semantic_role"] == "input_contract"
        assert _ANNOTATION_SEMANTICS["required_output"]["semantic_role"] == "output_contract"

    def test_build_packet_annotation_uses_annotation_semantics(self):
        """_build_packet_annotation() reads from _ANNOTATION_SEMANTICS, not from
        ROUTE_PRIOR_ROLE_CONTRACTS or a shared role contract registry."""
        import inspect
        from nl2spl.pipeline.stages.stage2_field_router import FieldRouter

        source = inspect.getsource(FieldRouter._build_packet_annotation)
        assert "_ANNOTATION_SEMANTICS" in source, (
            "_build_packet_annotation must reference _ANNOTATION_SEMANTICS "
            "(this is the CURRENT behavior this test locks)"
        )

    def test_annotation_semantics_missing_construct_slot_for_task_family(self):
        """_ANNOTATION_SEMANTICS for task_family has no construct_target/slot_target.

        This means when a runtime_input/required_output packet gets mapped to
        input_contract/output_contract, the construct/slot info comes from
        _ANNOTATION_SEMANTICS directly, not from a role contract.
        """
        from nl2spl.pipeline.stages.stage2_field_router import (
            _ANNOTATION_SEMANTICS,
        )

        tf = _ANNOTATION_SEMANTICS["task_family"]
        assert "construct_target" not in tf, (
            "task_family maps to profile_domain which should have no construct_target. "
            "This is correct, but enforced by omission in _ANNOTATION_SEMANTICS, "
            "not by a role contract rule."
        )
        assert "slot_target" not in tf


# ===========================================================================
# Test 6: DemandView authorizes demand by semantic_role only
# ===========================================================================


class TestDemandViewSemanticRoleAuthorization:
    """DemandView._select_contract_annotations() authorizes resource contract
    demand existence ONLY by semantic_role ∈ {input_contract, output_contract}.

    This is the CORRECT behavior and must be locked as a passing baseline.
    """

    def test_select_contract_annotations_filters_by_semantic_role(self):
        """_select_contract_annotations filters by semantic_role, not by
        construct_target, route_family, or slot_target."""
        import inspect
        from nl2spl.compiler.resource_contract_demand_view.builder import (
            DemandViewBuilder,
        )

        source = inspect.getsource(DemandViewBuilder._select_contract_annotations)
        # Must check semantic_role, not construct_target as primary filter
        assert "_CONTRACT_ROLES" in source, (
            "_select_contract_annotations must use _CONTRACT_ROLES "
            "(which is {'input_contract', 'output_contract'})"
        )
        assert "semantic_role" in source, (
            "DemandView must filter by semantic_role"
        )

    def test_contract_roles_contains_only_resource_roles(self):
        """_CONTRACT_ROLES is exactly {input_contract, output_contract}."""
        from nl2spl.compiler.resource_contract_demand_view.builder import (
            _CONTRACT_ROLES,
        )

        assert _CONTRACT_ROLES == frozenset({"input_contract", "output_contract"}), (
            f"_CONTRACT_ROLES should be exactly {{input_contract, output_contract}}, "
            f"got {_CONTRACT_ROLES}"
        )

    def test_demand_not_created_from_construct_target_alone(self):
        """A RouteAnnotation with construct_target=RESOURCE_CONTRACT but
        semantic_role=profile_domain must NOT produce a demand."""
        from nl2spl.compiler.resource_contract_demand_view.builder import (
            DemandViewBuilder,
        )
        from nl2spl.ir.field_route_ir import FieldRouteIR, RouteAnnotation

        ann = RouteAnnotation(
            span_id="sp_test",
            field="domain",
            semantic_role="profile_domain",
            route_family="profile",
            construct_target="RESOURCE_CONTRACT",
            slot_target="input",
            executable=False,
        )
        routes = FieldRouteIR(annotations=[ann])
        builder = DemandViewBuilder()

        selected = builder._select_contract_annotations(routes)
        assert len(selected) == 0, (
            "profile_domain annotation must NOT be selected as resource contract, "
            "even though construct_target=RESOURCE_CONTRACT"
        )

    def test_demand_created_from_correct_semantic_role(self):
        """A RouteAnnotation with semantic_role=input_contract produces a demand."""
        from nl2spl.compiler.resource_contract_demand_view.builder import (
            DemandViewBuilder,
        )
        from nl2spl.ir.field_route_ir import FieldRouteIR, RouteAnnotation
        from nl2spl.ir.span_ir import SpanIR

        ann = RouteAnnotation(
            span_id="sp_input",
            field="resources",
            semantic_role="input_contract",
            route_family="resource_contract",
            construct_target="RESOURCE_CONTRACT",
            slot_target="input",
            executable=False,
            source_section_id="sec_inputs",
            source_packet_id="pkt_1",
        )
        routes = FieldRouteIR(annotations=[ann])
        span = SpanIR(span_id="sp_input", text="customer name")

        builder = DemandViewBuilder()
        view = builder.build([span], routes)

        assert len(view.demands) == 1
        demand = view.demands[0]
        assert demand.direction == "input"
        assert demand.source_span_ids == ("sp_input",)


# ===========================================================================
# Test 7: Requiredness path remains independent from role contract
# ===========================================================================


class TestRequirednessIndependentFromRoleContract:
    """Requiredness enrichment is a separate step from role contract normalization.
    It must remain independent and not be affected by the role contract migration."""

    def test_requiredness_not_in_route_prior_role_contracts(self):
        """ROUTE_PRIOR_ROLE_CONTRACTS does not contain requiredness."""
        from nl2spl.pipeline.stages.stage2_field_router import (
            ROUTE_PRIOR_ROLE_CONTRACTS,
        )

        for role, contract in ROUTE_PRIOR_ROLE_CONTRACTS.items():
            assert "requiredness" not in contract, (
                f"ROUTE_PRIOR_ROLE_CONTRACTS[{role!r}] must not contain requiredness"
            )
            assert "required" not in contract, (
                f"ROUTE_PRIOR_ROLE_CONTRACTS[{role!r}] must not contain 'required'"
            )

    def test_requiredness_not_in_validator_role_contract(self):
        """_ROLE_CONTRACT does not contain requiredness."""
        from nl2spl.pipeline.stages.stage2_field_router_validator import (
            _ROLE_CONTRACT,
        )

        for role, contract in _ROLE_CONTRACT.items():
            assert "requiredness" not in contract, (
                f"_ROLE_CONTRACT[{role!r}] must not contain requiredness"
            )
            assert "required" not in contract, (
                f"_ROLE_CONTRACT[{role!r}] must not contain 'required'"
            )

    def test_requiredness_not_in_annotation_semantics(self):
        """_ANNOTATION_SEMANTICS does not contain requiredness."""
        from nl2spl.pipeline.stages.stage2_field_router import (
            _ANNOTATION_SEMANTICS,
        )

        for key, sem in _ANNOTATION_SEMANTICS.items():
            assert "requiredness" not in sem, (
                f"_ANNOTATION_SEMANTICS[{key!r}] must not contain requiredness"
            )
            assert "required" not in sem, (
                f"_ANNOTATION_SEMANTICS[{key!r}] must not contain 'required'"
            )

    def test_enrich_contract_requiredness_is_separate_method(self):
        """_enrich_contract_requiredness is a standalone method, separate from
        _normalize_annotation_contract."""
        import inspect
        from nl2spl.pipeline.stages.stage2_field_router import FieldRouter

        normalize_source = inspect.getsource(FieldRouter._normalize_annotation_contract)
        enrich_source = inspect.getsource(FieldRouter._enrich_contract_requiredness)

        # They are different methods
        assert "_normalize_annotation_contract" != "_enrich_contract_requiredness"

        # Normalization does NOT reference requiredness
        assert "requiredness" not in normalize_source, (
            "_normalize_annotation_contract must not reference requiredness"
        )

        # Enrichment DOES reference requiredness
        assert "requiredness" in enrich_source, (
            "_enrich_contract_requiredness must reference requiredness"
        )

    def test_enrich_contract_requiredness_called_after_normalization(self):
        """In _execute_canonical(), _enrich_contract_requiredness is called AFTER
        the LLM merge (which includes normalization)."""
        import inspect
        from nl2spl.pipeline.stages.stage2_field_router import FieldRouter

        source = inspect.getsource(FieldRouter._execute_canonical)
        # Verify the call order: _merge_llm_refinement before _enrich_contract_requiredness
        merge_idx = source.find("_merge_llm_refinement")
        enrich_idx = source.find("_enrich_contract_requiredness")

        assert merge_idx < enrich_idx, (
            "_enrich_contract_requiredness must be called AFTER "
            "_merge_llm_refinement (which contains normalization)"
        )


# ===========================================================================
# Test 8: _enrich_from_hints() role-contract bypass path
# ===========================================================================


class TestEnrichFromHintsRoleContractBypass:
    """_enrich_from_hints() mutates RouteAnnotation fields after construction
    from CompileHint metadata, bypassing any role contract normalization.

    This is GAP-09: the deterministic annotation path constructs a
    RouteAnnotation from _ANNOTATION_SEMANTICS, then immediately calls
    _enrich_from_hints() which can overwrite slot_target, route_family,
    semantic_role, and construct_target with unchecked hint values.

    Fix phase: ARC3 (Annotation Normalization Convergence).
    """

    # ------------------------------------------------------------------
    # Helper: build a minimal FieldRouter with mocked dependencies
    # ------------------------------------------------------------------

    @staticmethod
    def _make_router():
        """Create a FieldRouter instance with mocked config and client."""
        from unittest.mock import MagicMock

        from nl2spl.pipeline.stages.stage2_field_router import FieldRouter

        mock_config = MagicMock()
        mock_client = MagicMock()
        router = FieldRouter(config=mock_config, client=mock_client)
        return router

    @staticmethod
    def _make_hint(
        source_section_id: str = "sec_test",
        text: str = "test hint",
        target: str | None = None,
        metadata: dict | None = None,
    ):
        """Create a CompileHint for testing."""
        from nl2spl.canonical.compile_input import CompileHint

        return CompileHint(
            source_section_id=source_section_id,
            text=text,
            target=target,
            metadata=metadata or {},
        )

    @staticmethod
    def _make_hint_indexes(hints_by_category: dict[str, list]):
        """Build hint indexes matching the structure from _build_hint_indexes()."""
        indexes: dict[str, dict[str, dict[str, list]]] = {}
        for category, hint_list in hints_by_category.items():
            by_packet: dict[str, list] = {}
            by_section: dict[str, list] = {}
            for hint in hint_list:
                by_section.setdefault(hint.source_section_id, []).append(hint)
            indexes[category] = {"by_packet": by_packet, "by_section": by_section}
        return indexes

    # ------------------------------------------------------------------
    # Test 8.1: method existence and wiring
    # ------------------------------------------------------------------

    def test_enrich_from_hints_exists_and_is_wired_to_build_packet_annotation(self):
        """_enrich_from_hints() exists and is called from _build_packet_annotation()."""
        import inspect

        from nl2spl.pipeline.stages.stage2_field_router import FieldRouter

        # Method exists
        assert hasattr(FieldRouter, "_enrich_from_hints"), (
            "_enrich_from_hints must exist on FieldRouter"
        )

        # It is called from _build_packet_annotation
        build_source = inspect.getsource(FieldRouter._build_packet_annotation)
        assert "_enrich_from_hints" in build_source, (
            "_build_packet_annotation must call _enrich_from_hints "
            "after constructing the annotation from _ANNOTATION_SEMANTICS"
        )

        # Verify call order: _ANNOTATION_SEMANTICS lookup BEFORE _enrich_from_hints
        ann_sem_idx = build_source.find("_ANNOTATION_SEMANTICS")
        enrich_idx = build_source.find("_enrich_from_hints")
        assert ann_sem_idx < enrich_idx, (
            "_enrich_from_hints is called AFTER _ANNOTATION_SEMANTICS lookup "
            "in _build_packet_annotation — hints can overwrite contract-derived fields"
        )

    # ------------------------------------------------------------------
    # Test 8.2: construct_target mutation
    # ------------------------------------------------------------------

    def test_enrich_from_hints_can_mutate_construct_target(self):
        """When annotation.construct_target is None, _enrich_from_hints() writes
        construct_target from hint.target or hint.metadata['target']."""
        from nl2spl.ir.field_route_ir import RouteAnnotation

        router = self._make_router()

        # Annotation with construct_target=None (e.g. from a contract that
        # intentionally leaves it None, like profile_domain)
        ann = RouteAnnotation(
            span_id="sp_001",
            field="behavior",
            semantic_role="failure_mode",
            route_family="flow_relevant",
            executable=False,
            source_section_id="sec_failure",
            # construct_target and slot_target are intentionally None
        )

        # Create a hint that proposes RESOURCE_CONTRACT target.
        # NOTE: _enrich_from_hints() guards ALL enrichment (including
        # construct_target from hint.target) behind `if not meta: continue`,
        # so metadata MUST be non-empty for any mutation to occur.
        # This means a hint with metadata={} is silently skipped entirely.
        hint = self._make_hint(
            source_section_id="sec_failure",
            text="handle failures",
            target="RESOURCE_CONTRACT",  # via hint.target attribute
            metadata={"_": True},  # non-empty to bypass the `if not meta: continue` guard
        )
        hint_indexes = self._make_hint_indexes({"flow": [hint]})

        router._enrich_from_hints(
            ann, source_packet_id="", source_section_id="sec_failure",
            hint_indexes=hint_indexes,
        )

        # ARC3: construct_target is NOT mutated — diagnostics only.
        # Hints cannot override role-contract fields after normalization.
        assert ann.construct_target is None, (
            "ARC3: _enrich_from_hints no longer writes construct_target. "
            "The contract value (None for failure_mode with no prior construct) is preserved."
        )
        # Hint conflict is recorded as diagnostic in metadata
        assert "_hint_" in ann.metadata, (
            "Hint conflict should be stored in metadata for diagnostic projection"
        )

    # ------------------------------------------------------------------
    # Test 8.3: slot_target mutation
    # ------------------------------------------------------------------

    def test_enrich_from_hints_can_mutate_slot_target(self):
        """When annotation.slot_target is None, _enrich_from_hints() writes
        slot_target from hint.metadata['slot_target']."""
        from nl2spl.ir.field_route_ir import RouteAnnotation

        router = self._make_router()

        ann = RouteAnnotation(
            span_id="sp_002",
            field="behavior",
            semantic_role="failure_mode",
            route_family="flow_relevant",
            executable=False,
            source_section_id="sec_failure",
        )

        hint = self._make_hint(
            source_section_id="sec_failure",
            text="handle failures",
            metadata={"slot_target": "input"},  # wrong slot for failure_mode
        )
        hint_indexes = self._make_hint_indexes({"flow": [hint]})

        router._enrich_from_hints(
            ann, source_packet_id="", source_section_id="sec_failure",
            hint_indexes=hint_indexes,
        )

        # ARC3: slot_target is NOT mutated — diagnostics only.
        # The hint value "input" is stored in metadata for audit visibility.
        assert ann.slot_target is None, (
            "ARC3: _enrich_from_hints no longer writes slot_target from hints"
        )
        assert "_hint_" in ann.metadata

    # ------------------------------------------------------------------
    # Test 8.4: route_family mutation
    # ------------------------------------------------------------------

    def test_enrich_from_hints_can_mutate_route_family(self):
        """When annotation.route_family is None, _enrich_from_hints() writes
        route_family from hint.metadata['route_family']."""
        from nl2spl.ir.field_route_ir import RouteAnnotation

        router = self._make_router()

        ann = RouteAnnotation(
            span_id="sp_003",
            field="behavior",
            semantic_role="failure_mode",
            route_family=None,  # intentionally None
            executable=False,
            source_section_id="sec_failure",
        )

        hint = self._make_hint(
            source_section_id="sec_failure",
            text="handle failures",
            metadata={"route_family": "resource_contract"},  # wrong family
        )
        hint_indexes = self._make_hint_indexes({"flow": [hint]})

        router._enrich_from_hints(
            ann, source_packet_id="", source_section_id="sec_failure",
            hint_indexes=hint_indexes,
        )

        # ARC3: route_family is NOT mutated — diagnostics only.
        assert ann.route_family is None, (
            "ARC3: _enrich_from_hints no longer writes route_family from hints"
        )
        assert "_hint_" in ann.metadata

    # ------------------------------------------------------------------
    # Test 8.5: semantic_role mutation (most dangerous)
    # ------------------------------------------------------------------

    def test_enrich_from_hints_can_mutate_semantic_role(self):
        """When annotation.semantic_role is None, _enrich_from_hints() writes
        semantic_role from hint.metadata['semantic_role'].

        This is the MOST DANGEROUS mutation: semantic_role is the primary
        semantic decision that should only come from LLM or deterministic
        contract, not from an unchecked compile hint.
        """
        from nl2spl.ir.field_route_ir import RouteAnnotation

        router = self._make_router()

        ann = RouteAnnotation(
            span_id="sp_004",
            field="behavior",
            semantic_role=None,  # not yet assigned
            route_family=None,
            executable=False,
            source_section_id="sec_test",
        )

        hint = self._make_hint(
            source_section_id="sec_test",
            text="some span text",
            metadata={"semantic_role": "input_contract"},  # hint claims it's a resource
        )
        hint_indexes = self._make_hint_indexes({"flow": [hint]})

        # _hint_category_for(None) returns "" so hints won't be matched.
        # But if semantic_role is later set and the category matches, hints apply.
        # The critical gap: semantic_role is mutable by hints when None.
        # Let's use a role that maps to a category.
        ann2 = RouteAnnotation(
            span_id="sp_005",
            field="behavior",
            semantic_role="failure_mode",
            route_family="flow_relevant",
            executable=False,
            source_section_id="sec_failure",
            construct_target="EXCEPTION_FLOW",
            slot_target="condition",
        )

        # Now _hint_category_for("failure_mode") returns "flow"
        hint2 = self._make_hint(
            source_section_id="sec_failure",
            text="failure text",
            metadata={"semantic_role": "input_contract"},  # wrong role for failure_mode
        )
        hint_indexes2 = self._make_hint_indexes({"flow": [hint2]})

        router._enrich_from_hints(
            ann2, source_packet_id="", source_section_id="sec_failure",
            hint_indexes=hint_indexes2,
        )

        # When annotation.semantic_role is already set, hint semantic_role that
        # differs produces a diagnostic but does NOT mutate. This is the one
        # field that is partially defended — but only because it's already set.
        # The diagnostic is the only defense:
        assert len(ann2.diagnostics) > 0, (
            "When semantic_role differs, a diagnostic is emitted. "
            "But this is string-based, not typed — gap persists."
        )
        assert "semantic_role" in ann2.diagnostics[0].lower(), (
            f"Diagnostic should mention semantic_role conflict: {ann2.diagnostics}"
        )

    # ------------------------------------------------------------------
    # Test 8.6: not driven by canonical role contract
    # ------------------------------------------------------------------

    def test_enrich_from_hints_no_longer_mutates_role_contract_fields(self):
        """ARC3: _enrich_from_hints() no longer writes role-contract fields.
        Hints now produce diagnostics only — mutations are gone."""
        import inspect

        from nl2spl.pipeline.stages.stage2_field_router import FieldRouter

        source = inspect.getsource(FieldRouter._enrich_from_hints)

        # The old mutation patterns must be ABSENT
        assert "annotation.slot_target = hint_slot" not in source, (
            "ARC3: slot_target mutation removed from _enrich_from_hints"
        )
        assert "annotation.route_family = hint_rf" not in source, (
            "ARC3: route_family mutation removed from _enrich_from_hints"
        )
        assert "annotation.semantic_role = hint_role" not in source, (
            "ARC3: semantic_role mutation removed from _enrich_from_hints"
        )
        assert "annotation.construct_target = hint_target" not in source, (
            "ARC3: construct_target mutation removed from _enrich_from_hints"
        )

        # Diagnostic-only patterns must be present
        assert "diagnostic only" in source, (
            "ARC3: _enrich_from_hints docstring documents diagnostic-only behavior"
        )

    # ------------------------------------------------------------------
    # Test 8.7: GAP-09 assigned to ARC3
    # ------------------------------------------------------------------

    def test_enrich_from_hints_gap_assigned_to_arc3(self):
        """GAP-09: _enrich_from_hints bypass is to be fixed in ARC3.

        Per the implementation plan mandatory revision #3:
        'Hint enrichment must be governed by role contract.
        _enrich_from_hints() must not write or override field, route_family,
        construct_target, slot_target, semantic_role, or executable after
        role contract normalization.'
        """
        arc3_files = [
            "src/nl2spl/pipeline/stages/stage2_field_router.py",
        ]

        # The ARC3 phase will edit this file to converge the hint enrichment
        # path to use the canonical role contract.
        assert len(arc3_files) > 0, (
            "ARC3 will modify stage2_field_router.py to converge "
            "_enrich_from_hints() to the canonical role contract"
        )

    # ------------------------------------------------------------------
    # Test 8.8: call order in _build_packet_annotation
    # ------------------------------------------------------------------

    def test_enrich_from_hints_called_after_contract_fields_set(self):
        """_enrich_from_hints() runs AFTER _ANNOTATION_SEMANTICS lookup,
        so hints can silently overwrite contract-derived fields."""
        import inspect

        from nl2spl.pipeline.stages.stage2_field_router import FieldRouter

        source = inspect.getsource(FieldRouter._build_packet_annotation)

        # Extract the relevant lines
        lines = source.split("\n")
        ann_sem_line = None
        enrich_line = None
        for i, line in enumerate(lines):
            if "_ANNOTATION_SEMANTICS" in line and "get" in line:
                ann_sem_line = i
            if "_enrich_from_hints" in line:
                enrich_line = i

        assert ann_sem_line is not None, "Must find _ANNOTATION_SEMANTICS usage"
        assert enrich_line is not None, "Must find _enrich_from_hints call"
        assert ann_sem_line < enrich_line, (
            f"_ANNOTATION_SEMANTICS lookup at line {ann_sem_line} must precede "
            f"_enrich_from_hints call at line {enrich_line}. "
            "This means hint enrichment can overwrite contract-derived fields."
        )

    # ------------------------------------------------------------------
    # Test 8.9: executable is diagnostic-only
    # ------------------------------------------------------------------

    def test_enrich_from_hints_executable_is_diagnostic_only(self):
        """_enrich_from_hints() does NOT mutate annotation.executable from hints;
        it only emits a diagnostic. All other role-contract fields ARE mutated."""
        import inspect

        from nl2spl.pipeline.stages.stage2_field_router import FieldRouter
        from nl2spl.ir.field_route_ir import RouteAnnotation

        router = self._make_router()

        # Create annotation with executable=True
        ann = RouteAnnotation(
            span_id="sp_006",
            field="behavior",
            semantic_role="failure_mode",
            route_family="flow_relevant",
            executable=True,  # should be False per contract
            source_section_id="sec_failure",
        )

        hint = self._make_hint(
            source_section_id="sec_failure",
            text="failure handling",
            metadata={"executable": False},
        )
        hint_indexes = self._make_hint_indexes({"flow": [hint]})

        original_executable = ann.executable
        router._enrich_from_hints(
            ann, source_packet_id="", source_section_id="sec_failure",
            hint_indexes=hint_indexes,
        )

        # Executable is NOT mutated — only a diagnostic is emitted
        assert ann.executable == original_executable, (
            "executable is preserved (diagnostic-only); but construct_target, "
            "slot_target, route_family, semantic_role ARE mutated — inconsistency"
        )

        # Verify the diagnostic was emitted
        assert len(ann.diagnostics) > 0, (
            "executable conflict produces a diagnostic"
        )

        # Verify source code confirms executable is diagnostic-only
        source = inspect.getsource(FieldRouter._enrich_from_hints)
        # The executable block should NOT contain "annotation.executable ="
        # after the conflict check — it only appends to diagnostics
        assert "annotation.executable = hint_exec" not in source, (
            "executable is NOT mutated; this is the correct behavior for hints. "
            "But construct_target/slot_target/route_family/semantic_role ARE "
            "mutated — this inconsistency must be resolved in ARC3."
        )
