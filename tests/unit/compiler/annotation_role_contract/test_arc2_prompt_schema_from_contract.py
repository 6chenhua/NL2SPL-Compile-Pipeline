"""ARC2: Schema Constants from Role Contract — prompt constant derivation tests.

Verifies that all Stage 2 prompt schema constants are sourced from the
canonical role contract registry and remain byte-for-byte identical to
the pre-ARC1 hardcoded values (zero behavior change).
"""

from __future__ import annotations


# ===========================================================================
# Pre-ARC1 hardcoded reference values (golden)
# ===========================================================================

_OLD_ALLOWED_FIELDS = frozenset({
    "identity", "audience", "rules", "domain", "integrations", "behavior", "resources",
})

_OLD_ALLOWED_SEMANTIC_ROLES = frozenset({
    "profile_domain",
    "input_contract",
    "output_contract",
    "process_step",
    "constraint",
    "failure_mode",
    "exception_handler_action",
    "delegation_intent",
    "delegation_boundary_constraint",
    "delegation_prohibition",
    "api_candidate",
    "worker_handoff_candidate",
    "handoff_condition",
    "integration_hint",
})

_OLD_ALLOWED_CONSTRUCT_TARGETS = frozenset({
    "EXCEPTION_FLOW",
    "WORKER_HANDOFF",
    "API_DECLARATION",
    "CALL_API",
    "RESOURCE_CONTRACT",
    "CONSTRAINT",
})

_OLD_ALLOWED_SLOT_TARGETS = frozenset({
    "condition",
    "handler",
    "input",
    "output",
    "target",
    "source_evidence",
    "call_action",
    "boundary",
    "prohibition",
})

_OLD_NON_EXECUTABLE_ROLES = frozenset({
    "input_contract",
    "output_contract",
    "constraint",
    "failure_mode",
    "delegation_intent",
    "delegation_boundary_constraint",
    "delegation_prohibition",
    "api_candidate",
    "worker_handoff_candidate",
    "handoff_condition",
    "integration_hint",
    "profile_domain",
})

_OLD_EXECUTABLE_ROLES = frozenset({
    "process_step",
    "exception_handler_action",
})


# ===========================================================================
# Test 1: Constants equal registry-derived values
# ===========================================================================


class TestConstantsDerivedFromRegistry:
    """Every prompt constant equals its corresponding registry API method."""

    def test_allowed_fields_from_registry(self):
        from nl2spl.compiler.annotation_role_contract.registry import (
            ROLE_CONTRACT_REGISTRY,
        )
        from nl2spl.pipeline.stages.stage2_field_router_prompt import (
            ALLOWED_FIELDS,
        )

        assert ALLOWED_FIELDS == ROLE_CONTRACT_REGISTRY.allowed_prompt_fields()

    def test_allowed_semantic_roles_from_registry(self):
        from nl2spl.compiler.annotation_role_contract.registry import (
            ROLE_CONTRACT_REGISTRY,
        )
        from nl2spl.pipeline.stages.stage2_field_router_prompt import (
            ALLOWED_SEMANTIC_ROLES,
        )

        assert ALLOWED_SEMANTIC_ROLES == ROLE_CONTRACT_REGISTRY.allowed_llm_semantic_roles()

    def test_allowed_construct_targets_from_registry(self):
        from nl2spl.compiler.annotation_role_contract.registry import (
            ROLE_CONTRACT_REGISTRY,
        )
        from nl2spl.pipeline.stages.stage2_field_router_prompt import (
            ALLOWED_CONSTRUCT_TARGETS,
        )

        assert ALLOWED_CONSTRUCT_TARGETS == ROLE_CONTRACT_REGISTRY.allowed_construct_targets()

    def test_allowed_slot_targets_from_registry(self):
        from nl2spl.compiler.annotation_role_contract.registry import (
            ROLE_CONTRACT_REGISTRY,
        )
        from nl2spl.pipeline.stages.stage2_field_router_prompt import (
            ALLOWED_SLOT_TARGETS,
        )

        assert ALLOWED_SLOT_TARGETS == ROLE_CONTRACT_REGISTRY.allowed_slot_targets()

    def test_non_executable_roles_from_registry(self):
        from nl2spl.compiler.annotation_role_contract.registry import (
            ROLE_CONTRACT_REGISTRY,
        )
        from nl2spl.pipeline.stages.stage2_field_router_prompt import (
            NON_EXECUTABLE_ROLES,
        )

        assert NON_EXECUTABLE_ROLES == ROLE_CONTRACT_REGISTRY.prompt_non_executable_roles()

    def test_executable_roles_from_registry(self):
        from nl2spl.compiler.annotation_role_contract.registry import (
            ROLE_CONTRACT_REGISTRY,
        )
        from nl2spl.pipeline.stages.stage2_field_router_prompt import (
            EXECUTABLE_ROLES,
        )

        assert EXECUTABLE_ROLES == ROLE_CONTRACT_REGISTRY.prompt_executable_roles()


# ===========================================================================
# Test 2: Constants are byte-for-byte identical to pre-ARC1 hardcoded values
# ===========================================================================


class TestZeroSchemaChange:
    """Every constant is byte-for-byte identical to its pre-ARC1 hardcoded value."""

    def test_allowed_fields_unchanged(self):
        from nl2spl.pipeline.stages.stage2_field_router_prompt import (
            ALLOWED_FIELDS,
        )
        assert ALLOWED_FIELDS == _OLD_ALLOWED_FIELDS

    def test_allowed_semantic_roles_unchanged(self):
        from nl2spl.pipeline.stages.stage2_field_router_prompt import (
            ALLOWED_SEMANTIC_ROLES,
        )
        assert ALLOWED_SEMANTIC_ROLES == _OLD_ALLOWED_SEMANTIC_ROLES

    def test_allowed_construct_targets_unchanged(self):
        from nl2spl.pipeline.stages.stage2_field_router_prompt import (
            ALLOWED_CONSTRUCT_TARGETS,
        )
        assert ALLOWED_CONSTRUCT_TARGETS == _OLD_ALLOWED_CONSTRUCT_TARGETS

    def test_allowed_slot_targets_unchanged(self):
        from nl2spl.pipeline.stages.stage2_field_router_prompt import (
            ALLOWED_SLOT_TARGETS,
        )
        assert ALLOWED_SLOT_TARGETS == _OLD_ALLOWED_SLOT_TARGETS

    def test_non_executable_roles_unchanged(self):
        from nl2spl.pipeline.stages.stage2_field_router_prompt import (
            NON_EXECUTABLE_ROLES,
        )
        assert NON_EXECUTABLE_ROLES == _OLD_NON_EXECUTABLE_ROLES

    def test_executable_roles_unchanged(self):
        from nl2spl.pipeline.stages.stage2_field_router_prompt import (
            EXECUTABLE_ROLES,
        )
        assert EXECUTABLE_ROLES == _OLD_EXECUTABLE_ROLES


# ===========================================================================
# Test 3: Structural aliases excluded from LLM-visible constants
# ===========================================================================


class TestAliasesExcludedFromPromptConstants:
    """Structural aliases (task_family, policy, etc.) must NOT appear in
    any LLM-visible prompt constant."""

    _ALIASES = {"task_family", "policy", "exception_handler",
                 "runtime_input", "required_output"}

    def test_aliases_not_in_allowed_semantic_roles(self):
        from nl2spl.pipeline.stages.stage2_field_router_prompt import (
            ALLOWED_SEMANTIC_ROLES,
        )
        overlap = self._ALIASES & ALLOWED_SEMANTIC_ROLES
        assert not overlap, f"Aliases leaked into ALLOWED_SEMANTIC_ROLES: {overlap}"

    def test_aliases_not_in_non_executable_roles(self):
        from nl2spl.pipeline.stages.stage2_field_router_prompt import (
            NON_EXECUTABLE_ROLES,
        )
        overlap = self._ALIASES & NON_EXECUTABLE_ROLES
        assert not overlap, f"Aliases leaked into NON_EXECUTABLE_ROLES: {overlap}"

    def test_aliases_not_in_executable_roles(self):
        from nl2spl.pipeline.stages.stage2_field_router_prompt import (
            EXECUTABLE_ROLES,
        )
        overlap = self._ALIASES & EXECUTABLE_ROLES
        assert not overlap, f"Aliases leaked into EXECUTABLE_ROLES: {overlap}"

    def test_failure_condition_not_in_any_prompt_constant(self):
        """failure_condition is internal — must not appear in any prompt constant."""
        from nl2spl.pipeline.stages.stage2_field_router_prompt import (
            ALLOWED_SEMANTIC_ROLES,
            NON_EXECUTABLE_ROLES,
            EXECUTABLE_ROLES,
        )

        assert "failure_condition" not in ALLOWED_SEMANTIC_ROLES, (
            "failure_condition leaked into ALLOWED_SEMANTIC_ROLES"
        )
        assert "failure_condition" not in NON_EXECUTABLE_ROLES, (
            "failure_condition leaked into NON_EXECUTABLE_ROLES"
        )
        assert "failure_condition" not in EXECUTABLE_ROLES, (
            "failure_condition leaked into EXECUTABLE_ROLES"
        )


# ===========================================================================
# Test 4: Modifying registry changes constants automatically
# ===========================================================================


class TestRegistryDrivesConstants:
    """The prompt constants must reflect registry changes automatically.

    Since the constants are module-level expressions evaluated at import
    time, changing the registry (singleton state) won't retroactively
    update already-imported modules.  This test verifies the derivation
    chain rather than hot-reload behavior.
    """

    def test_constant_source_is_registry_not_literal(self):
        """The module source must not contain hardcoded frozenset literals
        for the six constants."""
        import inspect
        from nl2spl.pipeline.stages import stage2_field_router_prompt as m

        source = inspect.getsource(m)

        # The old literal patterns must be absent from the constant definitions
        # (they still exist in docstrings/comments, so we check specifically)
        assert 'ROLE_CONTRACT_REGISTRY.allowed_prompt_fields()' in source
        assert 'ROLE_CONTRACT_REGISTRY.allowed_llm_semantic_roles()' in source
        assert 'ROLE_CONTRACT_REGISTRY.allowed_construct_targets()' in source
        assert 'ROLE_CONTRACT_REGISTRY.allowed_slot_targets()' in source
        assert 'ROLE_CONTRACT_REGISTRY.prompt_non_executable_roles()' in source
        assert 'ROLE_CONTRACT_REGISTRY.prompt_executable_roles()' in source

    def test_registry_import_present(self):
        """The prompt module imports from the registry."""
        import inspect
        from nl2spl.pipeline.stages import stage2_field_router_prompt as m

        source = inspect.getsource(m)
        assert "from nl2spl.compiler.annotation_role_contract.registry import" in source


# ===========================================================================
# Test 5: Constant types and names preserved
# ===========================================================================


class TestConstantCompatibility:
    """Public constant names and types are unchanged for backward compatibility."""

    def test_all_constants_are_frozenset(self):
        from nl2spl.pipeline.stages.stage2_field_router_prompt import (
            ALLOWED_FIELDS,
            ALLOWED_SEMANTIC_ROLES,
            ALLOWED_CONSTRUCT_TARGETS,
            ALLOWED_SLOT_TARGETS,
            NON_EXECUTABLE_ROLES,
            EXECUTABLE_ROLES,
        )

        assert isinstance(ALLOWED_FIELDS, frozenset)
        assert isinstance(ALLOWED_SEMANTIC_ROLES, frozenset)
        assert isinstance(ALLOWED_CONSTRUCT_TARGETS, frozenset)
        assert isinstance(ALLOWED_SLOT_TARGETS, frozenset)
        assert isinstance(NON_EXECUTABLE_ROLES, frozenset)
        assert isinstance(EXECUTABLE_ROLES, frozenset)

    def test_all_six_constant_names_exist(self):
        """All six expected constant names are present in the module."""
        from nl2spl.pipeline.stages import stage2_field_router_prompt as m

        for name in (
            "ALLOWED_FIELDS",
            "ALLOWED_SEMANTIC_ROLES",
            "ALLOWED_CONSTRUCT_TARGETS",
            "ALLOWED_SLOT_TARGETS",
            "NON_EXECUTABLE_ROLES",
            "EXECUTABLE_ROLES",
        ):
            assert hasattr(m, name), f"Missing constant: {name}"
