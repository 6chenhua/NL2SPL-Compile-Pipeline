"""ARC1: Canonical Role Contract Model — comprehensive contract value and registry tests.

Validates the canonical role contract registry against every acceptance
criterion in the implementation plan, Section 7 (ARC1).
"""

from __future__ import annotations

import pytest

# ===========================================================================
# Helpers
# ===========================================================================


def _assert_contract(registry, role: str, *, field: str, route_family: str | None,
                     construct_target: str | None, slot_target: str | None,
                     executable: bool):
    """Assert exact contract values for *role*."""
    c = registry.require_role_contract(role)
    assert c.semantic_role == role, f"{role}: semantic_role mismatch"
    assert c.field == field, f"{role}: expected field={field!r}, got {c.field!r}"
    assert c.route_family == route_family, (
        f"{role}: expected route_family={route_family!r}, got {c.route_family!r}"
    )
    assert c.construct_target == construct_target, (
        f"{role}: expected construct_target={construct_target!r}, got {c.construct_target!r}"
    )
    assert c.slot_target == slot_target, (
        f"{role}: expected slot_target={slot_target!r}, got {c.slot_target!r}"
    )
    assert c.executable == executable, (
        f"{role}: expected executable={executable}, got {c.executable}"
    )


# ===========================================================================
# Test 1: Exact contract values for every canonical role
# ===========================================================================


class TestExactContractValues:
    """Every canonical semantic role must have an exact, typed contract."""

    @pytest.fixture(autouse=True)
    def registry(self):
        from nl2spl.compiler.annotation_role_contract import (
            ROLE_CONTRACT_REGISTRY,
        )
        return ROLE_CONTRACT_REGISTRY

    # -- profile / domain --------------------------------------------------

    def test_profile_domain(self, registry):
        _assert_contract(registry, "profile_domain",
            field="domain", route_family="profile",
            construct_target=None, slot_target=None, executable=False)

    # -- resource contracts ------------------------------------------------

    def test_input_contract(self, registry):
        _assert_contract(registry, "input_contract",
            field="resources", route_family="resource_contract",
            construct_target="RESOURCE_CONTRACT", slot_target="input",
            executable=False)

    def test_output_contract(self, registry):
        _assert_contract(registry, "output_contract",
            field="resources", route_family="resource_contract",
            construct_target="RESOURCE_CONTRACT", slot_target="output",
            executable=False)

    # -- flow / behavior ---------------------------------------------------

    def test_process_step(self, registry):
        _assert_contract(registry, "process_step",
            field="behavior", route_family="flow_relevant",
            construct_target=None, slot_target=None, executable=True)

    def test_failure_mode(self, registry):
        _assert_contract(registry, "failure_mode",
            field="behavior", route_family="flow_relevant",
            construct_target="EXCEPTION_FLOW", slot_target="condition",
            executable=False)

    def test_failure_condition(self, registry):
        _assert_contract(registry, "failure_condition",
            field="behavior", route_family="flow_relevant",
            construct_target="EXCEPTION_FLOW", slot_target="condition",
            executable=False)

    def test_exception_handler_action(self, registry):
        _assert_contract(registry, "exception_handler_action",
            field="behavior", route_family="flow_relevant",
            construct_target="EXCEPTION_FLOW", slot_target="handler",
            executable=True)

    # -- delegation --------------------------------------------------------

    def test_delegation_intent(self, registry):
        _assert_contract(registry, "delegation_intent",
            field="behavior", route_family="delegation_boundary",
            construct_target="WORKER_HANDOFF", slot_target="target",
            executable=False)

    def test_delegation_boundary_constraint(self, registry):
        _assert_contract(registry, "delegation_boundary_constraint",
            field="rules", route_family="delegation_boundary",
            construct_target="CONSTRAINT", slot_target="boundary",
            executable=False)

    def test_delegation_prohibition(self, registry):
        _assert_contract(registry, "delegation_prohibition",
            field="rules", route_family="delegation_boundary",
            construct_target="CONSTRAINT", slot_target="prohibition",
            executable=False)

    def test_worker_handoff_candidate(self, registry):
        _assert_contract(registry, "worker_handoff_candidate",
            field="behavior", route_family="delegation_boundary",
            construct_target="WORKER_HANDOFF", slot_target="target",
            executable=False)

    def test_handoff_condition(self, registry):
        _assert_contract(registry, "handoff_condition",
            field="rules", route_family="delegation_boundary",
            construct_target="WORKER_HANDOFF", slot_target="condition",
            executable=False)

    # -- constraints -------------------------------------------------------

    def test_constraint(self, registry):
        _assert_contract(registry, "constraint",
            field="rules", route_family="constraint",
            construct_target=None, slot_target=None, executable=False)

    # -- integrations ------------------------------------------------------

    def test_api_candidate(self, registry):
        _assert_contract(registry, "api_candidate",
            field="integrations", route_family="integration_candidate",
            construct_target="API_DECLARATION", slot_target="source_evidence",
            executable=False)

    def test_integration_hint(self, registry):
        _assert_contract(registry, "integration_hint",
            field="integrations", route_family="integration_candidate",
            construct_target="API_DECLARATION", slot_target="source_evidence",
            executable=False)

    # -- contract count ----------------------------------------------------

    def test_total_contract_count(self, registry):
        """Exactly 15 canonical semantic roles (14 LLM-visible + 1 internal)."""
        assert len(registry.allowed_semantic_roles()) == 15
        assert len(registry.allowed_llm_semantic_roles()) == 14
        assert len(registry.allowed_internal_prior_roles()) == 1


# ===========================================================================
# Test 2: No duplicate semantic roles
# ===========================================================================


class TestNoDuplicates:
    """The canonical role set must have no duplicates."""

    def test_no_duplicate_semantic_roles(self):
        from nl2spl.compiler.annotation_role_contract import (
            ROLE_CONTRACT_REGISTRY,
        )

        roles = sorted(ROLE_CONTRACT_REGISTRY.allowed_semantic_roles())
        assert len(roles) == len(set(roles)), (
            f"Duplicate semantic roles detected: {roles}"
        )

    def test_no_duplicate_aliases(self):
        from nl2spl.compiler.annotation_role_contract import (
            ROLE_CONTRACT_REGISTRY,
        )

        aliases = [a.alias for a in ROLE_CONTRACT_REGISTRY.iter_aliases()]
        assert len(aliases) == len(set(aliases)), (
            f"Duplicate aliases detected: {aliases}"
        )

    def test_no_alias_equals_canonical_role(self):
        """An alias must not use the same string as a canonical role."""
        from nl2spl.compiler.annotation_role_contract import (
            ROLE_CONTRACT_REGISTRY,
        )

        roles = ROLE_CONTRACT_REGISTRY.allowed_semantic_roles()
        aliases = {a.alias for a in ROLE_CONTRACT_REGISTRY.iter_aliases()}
        overlap = roles & aliases
        assert not overlap, (
            f"Aliases must not shadow canonical roles: {overlap}"
        )


# ===========================================================================
# Test 3: All fields are typed; expected None is explicit
# ===========================================================================


class TestTypedFieldsAndExplicitNone:
    """Contract fields are typed (not dict[str, Any]); expected None is explicit."""

    def test_contract_is_frozen_dataclass_not_dict(self):
        from nl2spl.compiler.annotation_role_contract import (
            ROLE_CONTRACT_REGISTRY,
        )
        from nl2spl.compiler.annotation_role_contract.model import (
            AnnotationRoleContract,
        )

        for role in ROLE_CONTRACT_REGISTRY.allowed_semantic_roles():
            c = ROLE_CONTRACT_REGISTRY.require_role_contract(role)
            assert isinstance(c, AnnotationRoleContract), (
                f"Contract for {role!r} must be AnnotationRoleContract, "
                f"got {type(c).__name__}"
            )
            # Verify it is frozen (dataclass with frozen=True)
            with pytest.raises(Exception):  # noqa: B017 - frozen dataclass raises implementation-specific error
                c._immutable_test = True  # type: ignore[attr-defined]

    def test_construct_target_none_is_explicit_for_profile_domain(self):
        """profile_domain.construct_target is explicitly None — not a missing key."""
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

    def test_construct_target_none_is_explicit_for_process_step(self):
        """process_step.construct_target is explicitly None."""
        from nl2spl.compiler.annotation_role_contract import (
            ROLE_CONTRACT_REGISTRY,
        )

        c = ROLE_CONTRACT_REGISTRY.require_role_contract("process_step")
        assert c.construct_target is None, (
            "process_step.construct_target must be explicitly None"
        )
        assert c.slot_target is None, (
            "process_step.slot_target must be explicitly None"
        )

    def test_construct_target_none_is_explicit_for_constraint(self):
        """constraint.construct_target is explicitly None."""
        from nl2spl.compiler.annotation_role_contract import (
            ROLE_CONTRACT_REGISTRY,
        )

        c = ROLE_CONTRACT_REGISTRY.require_role_contract("constraint")
        assert c.construct_target is None, (
            "constraint.construct_target must be explicitly None"
        )
        assert c.slot_target is None, (
            "constraint.slot_target must be explicitly None"
        )

    def test_every_contract_has_materialization_authority(self):
        from nl2spl.compiler.annotation_role_contract import (
            ROLE_CONTRACT_REGISTRY,
        )

        for role in ROLE_CONTRACT_REGISTRY.allowed_semantic_roles():
            c = ROLE_CONTRACT_REGISTRY.require_role_contract(role)
            assert c.materialization_authority == "annotation_role_contract", (
                f"{role}: materialization_authority must be 'annotation_role_contract'"
            )

    # -- typed visibility --------------------------------------------------

    def test_contract_model_has_typed_llm_visible_field(self):
        """AnnotationRoleContract has a typed ``llm_visible: bool`` field."""
        import dataclasses

        from nl2spl.compiler.annotation_role_contract.model import (
            AnnotationRoleContract,
        )

        field_names = {f.name: f.type for f in dataclasses.fields(AnnotationRoleContract)}
        assert "llm_visible" in field_names, (
            f"AnnotationRoleContract must have 'llm_visible' field. "
            f"Fields: {list(field_names.keys())}"
        )
        # Default value must be True (LLM-visible by default)
        assert field_names["llm_visible"] == "bool", (
            f"llm_visible must be typed as bool, got {field_names['llm_visible']}"
        )

    def test_failure_condition_llm_visible_is_false(self):
        """failure_condition.llm_visible is explicitly False."""
        from nl2spl.compiler.annotation_role_contract import (
            ROLE_CONTRACT_REGISTRY,
        )

        c = ROLE_CONTRACT_REGISTRY.require_role_contract("failure_condition")
        assert c.llm_visible is False, (
            f"failure_condition.llm_visible must be False, got {c.llm_visible}"
        )

    def test_all_prompt_visible_roles_have_llm_visible_true(self):
        """Every role in allowed_llm_semantic_roles() has llm_visible=True."""
        from nl2spl.compiler.annotation_role_contract import (
            ROLE_CONTRACT_REGISTRY,
        )

        for role in ROLE_CONTRACT_REGISTRY.allowed_llm_semantic_roles():
            c = ROLE_CONTRACT_REGISTRY.require_role_contract(role)
            assert c.llm_visible is True, (
                f"LLM-visible role {role!r} must have llm_visible=True, "
                f"got {c.llm_visible}"
            )

    def test_internal_prior_roles_derived_from_typed_field_not_notes(self):
        """allowed_internal_prior_roles() uses llm_visible field, not notes matching."""
        import inspect

        from nl2spl.compiler.annotation_role_contract import (
            ROLE_CONTRACT_REGISTRY,
        )
        from nl2spl.compiler.annotation_role_contract.registry import (
            AnnotationRoleContractRegistry,
        )

        source = inspect.getsource(
            AnnotationRoleContractRegistry.allowed_internal_prior_roles
        )
        # Must NOT contain string matching on notes
        assert "NOT LLM-visible" not in source, (
            "allowed_internal_prior_roles() must not use notes string matching. "
            f"Source: {source[:200]}"
        )
        # Must use llm_visible field
        assert "llm_visible" in source, (
            "allowed_internal_prior_roles() must use the typed llm_visible field"
        )

        # Verify the result is still correct
        internal = ROLE_CONTRACT_REGISTRY.allowed_internal_prior_roles()
        assert "failure_condition" in internal
        assert len(internal) == 1

    def test_clearing_notes_does_not_change_visibility(self):
        """Notes carry no machine semantics — visibility survives notes mutation."""
        from dataclasses import replace

        from nl2spl.compiler.annotation_role_contract import (
            ROLE_CONTRACT_REGISTRY,
        )

        fc = ROLE_CONTRACT_REGISTRY.require_role_contract("failure_condition")
        # llm_visible is False regardless of notes
        assert fc.llm_visible is False

        # If someone cleared the notes, visibility is unchanged
        no_notes = replace(fc, notes=None)
        assert no_notes.llm_visible is False, (
            "Visibility must not depend on notes — clearing notes should not "
            "make failure_condition LLM-visible"
        )

        # If someone changed the notes to something friendly, visibility unchanged
        friendly = replace(fc, notes="This is a perfectly normal role.")
        assert friendly.llm_visible is False, (
            "Visibility must not depend on notes — changing notes should not "
            "make failure_condition LLM-visible"
        )

    def test_default_llm_visible_is_true(self):
        """New contracts are LLM-visible by default — opt-out, not opt-in."""
        from nl2spl.compiler.annotation_role_contract.model import (
            AnnotationRoleContract,
        )

        # Construct a fresh contract without specifying llm_visible
        c = AnnotationRoleContract(
            semantic_role="test_role",
            field="behavior",
            route_family=None,
            construct_target=None,
            slot_target=None,
            executable=False,
        )
        assert c.llm_visible is True, (
            "Default llm_visible must be True — new roles are LLM-visible "
            "unless explicitly marked otherwise"
        )


# ===========================================================================
# Test 4: Requiredness is absent from the contract model
# ===========================================================================


class TestRequirednessAbsent:
    """The role contract model must NOT contain requiredness anywhere."""

    def test_no_requiredness_field_in_contract_model(self):
        """AnnotationRoleContract has no 'requiredness' or 'required' attribute."""
        import dataclasses

        from nl2spl.compiler.annotation_role_contract.model import (
            AnnotationRoleContract,
        )

        field_names = {f.name for f in dataclasses.fields(AnnotationRoleContract)}
        assert "requiredness" not in field_names, (
            f"AnnotationRoleContract must not have 'requiredness' field. "
            f"Fields: {field_names}"
        )
        assert "required" not in field_names, (
            f"AnnotationRoleContract must not have 'required' field. "
            f"Fields: {field_names}"
        )

    def test_no_requiredness_in_registry_contracts(self):
        """No contract instance carries requiredness in metadata or notes."""
        from nl2spl.compiler.annotation_role_contract import (
            ROLE_CONTRACT_REGISTRY,
        )

        for role in ROLE_CONTRACT_REGISTRY.allowed_semantic_roles():
            c = ROLE_CONTRACT_REGISTRY.require_role_contract(role)
            # Check notes don't encode requiredness
            if c.notes:
                assert "required" not in c.notes.lower(), (
                    f"{role}: notes must not mention requiredness: {c.notes}"
                )

    def test_no_requiredness_in_alias_model(self):
        """AnnotationRoleAlias has no 'requiredness' field."""
        import dataclasses

        from nl2spl.compiler.annotation_role_contract.model import (
            AnnotationRoleAlias,
        )

        field_names = {f.name for f in dataclasses.fields(AnnotationRoleAlias)}
        assert "requiredness" not in field_names
        assert "required" not in field_names


# ===========================================================================
# Test 5: Exact alias resolution for every structural alias
# ===========================================================================


class TestAliasResolution:
    """Every structural alias must resolve to the correct canonical role."""

    @pytest.fixture(autouse=True)
    def registry(self):
        from nl2spl.compiler.annotation_role_contract import (
            ROLE_CONTRACT_REGISTRY,
        )
        return ROLE_CONTRACT_REGISTRY

    # -- the five required aliases -----------------------------------------

    def test_task_family_resolves_to_profile_domain(self, registry):
        assert registry.resolve_semantic_role("task_family") == "profile_domain"

    def test_policy_resolves_to_constraint(self, registry):
        assert registry.resolve_semantic_role("policy") == "constraint"

    def test_exception_handler_resolves_to_exception_handler_action(self, registry):
        assert registry.resolve_semantic_role("exception_handler") == "exception_handler_action"

    def test_runtime_input_resolves_to_input_contract(self, registry):
        assert registry.resolve_semantic_role("runtime_input") == "input_contract"

    def test_required_output_resolves_to_output_contract(self, registry):
        assert registry.resolve_semantic_role("required_output") == "output_contract"

    # -- canonical role returns itself -------------------------------------

    def test_canonical_role_resolves_to_itself(self, registry):
        for role in registry.allowed_semantic_roles():
            assert registry.resolve_semantic_role(role) == role, (
                f"Canonical role {role!r} must resolve to itself"
            )

    # -- unknown returns None ----------------------------------------------

    def test_unknown_role_returns_none(self, registry):
        assert registry.resolve_semantic_role("nonexistent_role_xyz") is None

    # -- alias source kinds ------------------------------------------------

    def test_alias_source_kinds(self, registry):
        expected_kinds = {
            "task_family": "packet_type",
            "policy": "packet_type",
            "exception_handler": "route_prior",
            "runtime_input": "packet_type",
            "required_output": "packet_type",
        }
        for alias_name, expected_kind in expected_kinds.items():
            a = registry.get_alias(alias_name)
            assert a is not None, f"Alias {alias_name!r} not found"
            assert a.source_kind == expected_kind, (
                f"{alias_name}: expected source_kind={expected_kind!r}, "
                f"got {a.source_kind!r}"
            )

    # -- resolved target must be in canonical registry ---------------------

    def test_all_alias_targets_are_valid_canonical_roles(self, registry):
        for a in registry.iter_aliases():
            c = registry.get_role_contract(a.canonical_semantic_role)
            assert c is not None, (
                f"Alias {a.alias!r} resolves to {a.canonical_semantic_role!r} "
                f"which has no contract"
            )


# ===========================================================================
# Test 6: Structural aliases are not LLM-visible
# ===========================================================================


class TestStructuralAliasesNotLLMVisible:
    """Structural aliases must NOT appear in LLM-visible semantic roles."""

    def test_aliases_not_in_allowed_llm_semantic_roles(self):
        from nl2spl.compiler.annotation_role_contract import (
            ROLE_CONTRACT_REGISTRY,
        )

        llm_roles = ROLE_CONTRACT_REGISTRY.allowed_llm_semantic_roles()
        alias_names = {a.alias for a in ROLE_CONTRACT_REGISTRY.iter_aliases()}

        overlap = alias_names & llm_roles
        assert not overlap, (
            f"Structural aliases must not be LLM-visible: {overlap}"
        )

    def test_aliases_marked_not_llm_visible(self):
        from nl2spl.compiler.annotation_role_contract import (
            ROLE_CONTRACT_REGISTRY,
        )

        for a in ROLE_CONTRACT_REGISTRY.iter_aliases():
            assert a.llm_visible is False, (
                f"Alias {a.alias!r}: llm_visible must be False (default)"
            )

    def test_task_family_is_not_llm_visible(self):
        from nl2spl.compiler.annotation_role_contract import (
            ROLE_CONTRACT_REGISTRY,
        )

        a = ROLE_CONTRACT_REGISTRY.get_alias("task_family")
        assert a is not None
        assert a.llm_visible is False
        assert "task_family" not in ROLE_CONTRACT_REGISTRY.allowed_llm_semantic_roles()

    def test_policy_is_not_llm_visible(self):
        from nl2spl.compiler.annotation_role_contract import (
            ROLE_CONTRACT_REGISTRY,
        )

        a = ROLE_CONTRACT_REGISTRY.get_alias("policy")
        assert a is not None
        assert a.llm_visible is False
        assert "policy" not in ROLE_CONTRACT_REGISTRY.allowed_llm_semantic_roles()

    def test_runtime_input_is_not_llm_visible(self):
        from nl2spl.compiler.annotation_role_contract import (
            ROLE_CONTRACT_REGISTRY,
        )

        a = ROLE_CONTRACT_REGISTRY.get_alias("runtime_input")
        assert a is not None
        assert a.llm_visible is False
        assert "runtime_input" not in ROLE_CONTRACT_REGISTRY.allowed_llm_semantic_roles()

    def test_required_output_is_not_llm_visible(self):
        from nl2spl.compiler.annotation_role_contract import (
            ROLE_CONTRACT_REGISTRY,
        )

        a = ROLE_CONTRACT_REGISTRY.get_alias("required_output")
        assert a is not None
        assert a.llm_visible is False
        assert "required_output" not in ROLE_CONTRACT_REGISTRY.allowed_llm_semantic_roles()


# ===========================================================================
# Test 7: Allowed schema values are derived from registry
# ===========================================================================


class TestAllowedSchemaDerived:
    """The registry generates allowed-schema sets from contracts.

    Two families are tested:
    - Contract-derived sets (complete universe, includes internal roles)
    - Prompt-visible sets (LLM-safe, byte-for-byte equivalent to current constants)
    """

    # -- contract-derived sets ------------------------------------------------

    def test_allowed_fields_from_registry(self):
        from nl2spl.compiler.annotation_role_contract import (
            ROLE_CONTRACT_REGISTRY,
        )

        fields = ROLE_CONTRACT_REGISTRY.allowed_fields()
        # The five fields actually used by at least one role
        assert "behavior" in fields
        assert "domain" in fields
        assert "resources" in fields
        assert "rules" in fields
        assert "integrations" in fields

    def test_allowed_construct_targets_from_registry(self):
        from nl2spl.compiler.annotation_role_contract import (
            ROLE_CONTRACT_REGISTRY,
        )

        ct = ROLE_CONTRACT_REGISTRY.allowed_construct_targets()
        assert "EXCEPTION_FLOW" in ct
        assert "WORKER_HANDOFF" in ct
        assert "API_DECLARATION" in ct
        assert "CALL_API" in ct
        assert "RESOURCE_CONTRACT" in ct
        assert "CONSTRAINT" in ct
        # None is NOT in the allowed set — it's a contract value, not a schema literal
        assert None not in ct

    def test_allowed_slot_targets_from_registry(self):
        from nl2spl.compiler.annotation_role_contract import (
            ROLE_CONTRACT_REGISTRY,
        )

        st = ROLE_CONTRACT_REGISTRY.allowed_slot_targets()
        assert "condition" in st
        assert "handler" in st
        assert "input" in st
        assert "output" in st
        assert "target" in st
        assert "source_evidence" in st
        assert "call_action" in st
        assert "boundary" in st
        assert "prohibition" in st

    def test_non_executable_roles_from_registry(self):
        from nl2spl.compiler.annotation_role_contract import (
            ROLE_CONTRACT_REGISTRY,
        )

        ne = ROLE_CONTRACT_REGISTRY.non_executable_roles()
        assert "input_contract" in ne
        assert "output_contract" in ne
        assert "profile_domain" in ne
        assert "failure_mode" in ne
        assert "constraint" in ne
        # contract-derived set includes internal roles
        assert "failure_condition" in ne

    def test_executable_roles_from_registry(self):
        from nl2spl.compiler.annotation_role_contract import (
            ROLE_CONTRACT_REGISTRY,
        )

        exe = ROLE_CONTRACT_REGISTRY.executable_roles()
        assert exe == frozenset({"process_step", "exception_handler_action"})

    def test_non_executable_and_executable_are_disjoint(self):
        from nl2spl.compiler.annotation_role_contract import (
            ROLE_CONTRACT_REGISTRY,
        )

        ne = ROLE_CONTRACT_REGISTRY.non_executable_roles()
        exe = ROLE_CONTRACT_REGISTRY.executable_roles()
        assert ne.isdisjoint(exe), (
            f"non_executable and executable must be disjoint. "
            f"Overlap: {ne & exe}"
        )

    def test_non_executable_plus_executable_equals_all(self):
        from nl2spl.compiler.annotation_role_contract import (
            ROLE_CONTRACT_REGISTRY,
        )

        ne = ROLE_CONTRACT_REGISTRY.non_executable_roles()
        exe = ROLE_CONTRACT_REGISTRY.executable_roles()
        all_roles = ROLE_CONTRACT_REGISTRY.allowed_semantic_roles()
        assert ne | exe == all_roles, (
            f"non_executable ∪ executable must cover all roles. "
            f"Missing: {all_roles - (ne | exe)}"
        )

    # -- prompt-visible sets --------------------------------------------------

    def test_contract_fields_are_subset_of_prompt_fields(self):
        """Contract-derived fields are a proper subset of prompt-visible fields."""
        from nl2spl.compiler.annotation_role_contract import (
            ROLE_CONTRACT_REGISTRY,
        )

        contract = ROLE_CONTRACT_REGISTRY.allowed_fields()
        prompt = ROLE_CONTRACT_REGISTRY.allowed_prompt_fields()
        assert contract < prompt, (
            f"Contract fields must be a proper subset of prompt fields. "
            f"Contract only: {contract - prompt}. Prompt only: {prompt - contract}."
        )
        # The two extra fields are the legacy identity/audience
        assert prompt - contract == frozenset({"identity", "audience"})

    def test_prompt_non_executable_is_subset_of_contract_non_executable(self):
        """Prompt-visible non-executable is a proper subset (excludes internal)."""
        from nl2spl.compiler.annotation_role_contract import (
            ROLE_CONTRACT_REGISTRY,
        )

        contract_ne = ROLE_CONTRACT_REGISTRY.non_executable_roles()
        prompt_ne = ROLE_CONTRACT_REGISTRY.prompt_non_executable_roles()
        assert prompt_ne < contract_ne, (
            f"Prompt non-executable must be a proper subset of contract. "
            f"Internal only: {contract_ne - prompt_ne}."
        )
        # failure_condition is the internal role excluded from prompt
        assert "failure_condition" in contract_ne
        assert "failure_condition" not in prompt_ne


# ===========================================================================
# Test 8: Prompt-visible set preservation
# ===========================================================================


class TestPromptVisibleSetPreserved:
    """Every prompt-visible derived set must be byte-for-byte identical to
    the current pre-ARC1 prompt constant in ``stage2_field_router_prompt.py``.

    This is the invariant that lets ARC2 source prompt constants from the
    registry without changing the LLM-facing schema.
    """

    # -- all 6 prompt constants, byte-for-byte -------------------------------

    def test_allowed_prompt_fields_equals_current_constant(self):
        from nl2spl.compiler.annotation_role_contract import (
            ROLE_CONTRACT_REGISTRY,
        )
        from nl2spl.pipeline.stages.stage2_field_router_prompt import (
            ALLOWED_FIELDS,
        )

        assert ROLE_CONTRACT_REGISTRY.allowed_prompt_fields() == ALLOWED_FIELDS, (
            f"allowed_prompt_fields must equal ALLOWED_FIELDS. "
            f"Registry only: {ROLE_CONTRACT_REGISTRY.allowed_prompt_fields() - ALLOWED_FIELDS}. "
            f"Prompt only: {ALLOWED_FIELDS - ROLE_CONTRACT_REGISTRY.allowed_prompt_fields()}."
        )

    def test_allowed_llm_semantic_roles_equals_current_constant(self):
        from nl2spl.compiler.annotation_role_contract import (
            ROLE_CONTRACT_REGISTRY,
        )
        from nl2spl.pipeline.stages.stage2_field_router_prompt import (
            ALLOWED_SEMANTIC_ROLES,
        )

        assert ROLE_CONTRACT_REGISTRY.allowed_llm_semantic_roles() == ALLOWED_SEMANTIC_ROLES, (
            "allowed_llm_semantic_roles must equal ALLOWED_SEMANTIC_ROLES."
        )

    def test_allowed_construct_targets_equals_current_constant(self):
        from nl2spl.compiler.annotation_role_contract import (
            ROLE_CONTRACT_REGISTRY,
        )
        from nl2spl.pipeline.stages.stage2_field_router_prompt import (
            ALLOWED_CONSTRUCT_TARGETS,
        )

        assert ROLE_CONTRACT_REGISTRY.allowed_construct_targets() == ALLOWED_CONSTRUCT_TARGETS

    def test_allowed_slot_targets_equals_current_constant(self):
        from nl2spl.compiler.annotation_role_contract import (
            ROLE_CONTRACT_REGISTRY,
        )
        from nl2spl.pipeline.stages.stage2_field_router_prompt import (
            ALLOWED_SLOT_TARGETS,
        )

        assert ROLE_CONTRACT_REGISTRY.allowed_slot_targets() == ALLOWED_SLOT_TARGETS

    def test_prompt_non_executable_roles_equals_current_constant(self):
        from nl2spl.compiler.annotation_role_contract import (
            ROLE_CONTRACT_REGISTRY,
        )
        from nl2spl.pipeline.stages.stage2_field_router_prompt import (
            NON_EXECUTABLE_ROLES,
        )

        assert ROLE_CONTRACT_REGISTRY.prompt_non_executable_roles() == NON_EXECUTABLE_ROLES, (
            f"prompt_non_executable_roles must equal NON_EXECUTABLE_ROLES. "
            f"Registry only: {ROLE_CONTRACT_REGISTRY.prompt_non_executable_roles() - NON_EXECUTABLE_ROLES}. "
            f"Prompt only: {NON_EXECUTABLE_ROLES - ROLE_CONTRACT_REGISTRY.prompt_non_executable_roles()}."
        )

    def test_prompt_executable_roles_equals_current_constant(self):
        from nl2spl.compiler.annotation_role_contract import (
            ROLE_CONTRACT_REGISTRY,
        )
        from nl2spl.pipeline.stages.stage2_field_router_prompt import (
            EXECUTABLE_ROLES,
        )

        assert ROLE_CONTRACT_REGISTRY.prompt_executable_roles() == EXECUTABLE_ROLES

    # -- internal role boundaries --------------------------------------------

    def test_failure_condition_not_in_llm_visible(self):
        """failure_condition is internal — NOT in the LLM-visible set."""
        from nl2spl.compiler.annotation_role_contract import (
            ROLE_CONTRACT_REGISTRY,
        )

        llm = ROLE_CONTRACT_REGISTRY.allowed_llm_semantic_roles()
        assert "failure_condition" not in llm, (
            "failure_condition is an internal prior role, NOT LLM-visible"
        )

    def test_failure_condition_is_in_all_semantic_roles(self):
        """failure_condition IS in the full canonical set (but not LLM-visible)."""
        from nl2spl.compiler.annotation_role_contract import (
            ROLE_CONTRACT_REGISTRY,
        )

        all_roles = ROLE_CONTRACT_REGISTRY.allowed_semantic_roles()
        assert "failure_condition" in all_roles, (
            "failure_condition must be in the canonical set"
        )

    def test_no_structural_alias_in_llm_visible(self):
        """Verify none of the 5 structural aliases appear in LLM-visible set."""
        from nl2spl.compiler.annotation_role_contract import (
            ROLE_CONTRACT_REGISTRY,
        )

        llm = ROLE_CONTRACT_REGISTRY.allowed_llm_semantic_roles()
        aliases = {"task_family", "policy", "exception_handler",
                    "runtime_input", "required_output"}
        overlap = aliases & llm
        assert not overlap, (
            f"Structural aliases leaked into LLM-visible set: {overlap}"
        )

    def test_llm_visible_set_size_is_14(self):
        """Exactly 14 LLM-visible roles — same as current ALLOWED_SEMANTIC_ROLES."""
        from nl2spl.compiler.annotation_role_contract import (
            ROLE_CONTRACT_REGISTRY,
        )

        assert len(ROLE_CONTRACT_REGISTRY.allowed_llm_semantic_roles()) == 14


# ===========================================================================
# Test 9: Registry API completeness
# ===========================================================================


class TestRegistryAPI:
    """Verify all required registry API methods exist and work."""

    @pytest.fixture(autouse=True)
    def registry(self):
        from nl2spl.compiler.annotation_role_contract import (
            ROLE_CONTRACT_REGISTRY,
        )
        return ROLE_CONTRACT_REGISTRY

    def test_get_role_contract_known(self, registry):
        c = registry.get_role_contract("input_contract")
        assert c is not None
        assert c.semantic_role == "input_contract"

    def test_get_role_contract_unknown(self, registry):
        c = registry.get_role_contract("nonexistent")
        assert c is None

    def test_require_role_contract_known(self, registry):
        c = registry.require_role_contract("input_contract")
        assert c is not None

    def test_require_role_contract_unknown_raises(self, registry):
        with pytest.raises(KeyError):
            registry.require_role_contract("nonexistent")

    def test_iter_contracts(self, registry):
        contracts = list(registry.iter_contracts())
        assert len(contracts) == 15
        roles = {c.semantic_role for c in contracts}
        assert len(roles) == 15  # no duplicates

    def test_iter_aliases(self, registry):
        aliases = list(registry.iter_aliases())
        assert len(aliases) == 5

    def test_internal_prior_roles_is_subset_of_all_roles(self, registry):
        internal = registry.allowed_internal_prior_roles()
        all_roles = registry.allowed_semantic_roles()
        assert internal.issubset(all_roles)

    def test_internal_and_llm_visible_are_disjoint(self, registry):
        internal = registry.allowed_internal_prior_roles()
        llm = registry.allowed_llm_semantic_roles()
        assert internal.isdisjoint(llm)

    def test_internal_plus_llm_equals_all(self, registry):
        internal = registry.allowed_internal_prior_roles()
        llm = registry.allowed_llm_semantic_roles()
        all_roles = registry.allowed_semantic_roles()
        assert internal | llm == all_roles
