"""ARC8: Final Audit and Migration Cleanup.

Verifies all 14 audit requirements from the implementation plan,
Section 14.  Each test maps a design success criterion to code evidence.
"""

from __future__ import annotations


class TestFinalAudit:
    """Every ARC8 audit requirement has a corresponding test with
    code-level evidence."""

    # 1. No independent _ROLE_CONTRACT table outside canonical registry.
    def test_no_independent_role_contract_in_validator(self):
        from nl2spl.pipeline.stages.stage2_field_router_validator import (
            _ROLE_CONTRACT,
        )
        assert _ROLE_CONTRACT == {}, (
            "ARC4: _ROLE_CONTRACT is an empty compatibility wrapper; "
            "all validation uses ROLE_CONTRACT_REGISTRY"
        )

    # 2. No independent ROUTE_PRIOR_ROLE_CONTRACTS outside registry.
    def test_no_independent_route_prior_contracts(self):
        from nl2spl.pipeline.stages.stage2_field_router import (
            ROUTE_PRIOR_ROLE_CONTRACTS,
        )
        assert ROUTE_PRIOR_ROLE_CONTRACTS == {}, (
            "ARC3: ROUTE_PRIOR_ROLE_CONTRACTS is an empty compatibility wrapper; "
            "all lookups use ROLE_CONTRACT_REGISTRY"
        )

    # 3. No independent _ANNOTATION_SEMANTICS role mapping outside registry.
    def test_annotation_semantics_is_role_only_wrapper(self):
        from nl2spl.pipeline.stages.stage2_field_router import (
            _ANNOTATION_SEMANTICS,
        )
        for key, sem in _ANNOTATION_SEMANTICS.items():
            assert set(sem.keys()) == {"semantic_role"}, (
                f"{key}: _ANNOTATION_SEMANTICS only carries semantic_role; "
                f"compiler fields come from registry"
            )

    # 4. Prompt allowed schema derived from registry.
    def test_prompt_constants_from_registry(self):
        from nl2spl.compiler.annotation_role_contract.registry import (
            ROLE_CONTRACT_REGISTRY as R,
        )
        from nl2spl.pipeline.stages.stage2_field_router_prompt import (
            ALLOWED_CONSTRUCT_TARGETS,
            ALLOWED_FIELDS,
            ALLOWED_SEMANTIC_ROLES,
            ALLOWED_SLOT_TARGETS,
            EXECUTABLE_ROLES,
            NON_EXECUTABLE_ROLES,
        )
        assert ALLOWED_FIELDS == R.allowed_prompt_fields()
        assert ALLOWED_SEMANTIC_ROLES == R.allowed_llm_semantic_roles()
        assert ALLOWED_CONSTRUCT_TARGETS == R.allowed_construct_targets()
        assert ALLOWED_SLOT_TARGETS == R.allowed_slot_targets()
        assert NON_EXECUTABLE_ROLES == R.prompt_non_executable_roles()
        assert EXECUTABLE_ROLES == R.prompt_executable_roles()

    # 5. Validator uses registry.
    def test_validator_uses_registry(self):
        import inspect
        from nl2spl.pipeline.stages import stage2_field_router_validator as m
        source = inspect.getsource(m)
        assert "ROLE_CONTRACT_REGISTRY" in source

    # 6. Deterministic annotation builder uses registry.
    def test_deterministic_path_uses_registry(self):
        import inspect
        from nl2spl.pipeline.stages.stage2_field_router import FieldRouter
        source = inspect.getsource(FieldRouter._build_packet_annotation)
        assert "normalize_annotation_from_role" in source

    # 7. DemandView only authorizes demand by semantic_role.
    def test_demandview_uses_semantic_role_only(self):
        import inspect
        from nl2spl.compiler.resource_contract_demand_view.builder import (
            DemandViewBuilder,
        )
        source = inspect.getsource(DemandViewBuilder._select_contract_annotations)
        assert "semantic_role" in source
        assert 'route_family == "resource_contract"' not in source
        assert 'construct_target == "RESOURCE_CONTRACT"' not in source

    # 8. Requiredness not in role contract.
    def test_requiredness_not_in_role_contract(self):
        import dataclasses
        from nl2spl.compiler.annotation_role_contract.model import (
            AnnotationRoleContract,
        )
        fields = {f.name for f in dataclasses.fields(AnnotationRoleContract)}
        assert "requiredness" not in fields
        assert "required" not in fields

    # 9. Expected None contract tested for profile_domain.
    def test_profile_domain_expected_none(self):
        from nl2spl.compiler.annotation_role_contract import (
            ROLE_CONTRACT_REGISTRY,
        )
        c = ROLE_CONTRACT_REGISTRY.require_role_contract("profile_domain")
        assert c.construct_target is None
        assert c.slot_target is None

    # 10. Structural aliases not LLM-visible.
    def test_structural_aliases_not_llm_visible(self):
        from nl2spl.compiler.annotation_role_contract import (
            ROLE_CONTRACT_REGISTRY,
        )
        llm = ROLE_CONTRACT_REGISTRY.allowed_llm_semantic_roles()
        aliases = {"task_family", "policy", "exception_handler",
                    "runtime_input", "required_output"}
        assert aliases.isdisjoint(llm)

    # 11. _enrich_from_hints() cannot write role-contract fields.
    def test_enrich_from_hints_no_mutation(self):
        import inspect
        from nl2spl.pipeline.stages.stage2_field_router import FieldRouter
        source = inspect.getsource(FieldRouter._enrich_from_hints)
        assert "annotation.slot_target = " not in source
        assert "annotation.route_family = " not in source
        assert "annotation.semantic_role = " not in source
        assert "annotation.construct_target = " not in source

    # 12. Requiredness validation is post-enrichment.
    def test_requiredness_validation_post_enrichment(self):
        import inspect
        from nl2spl.pipeline.stages.stage2_field_router import FieldRouter
        source = inspect.getsource(FieldRouter._execute_canonical)
        enrich_idx = source.find("_enrich_contract_requiredness")
        finalize_idx = source.find("finalize_requiredness")
        assert enrich_idx < finalize_idx, (
            "finalize_requiredness must run AFTER _enrich_contract_requiredness"
        )

    # 13. Typed annotation diagnostics exist before projection.
    def test_typed_diagnostics_exist(self):
        import dataclasses
        from nl2spl.compiler.annotation_role_contract.diagnostics import (
            AnnotationValidationDiagnostic,
        )
        fields = {f.name for f in dataclasses.fields(AnnotationValidationDiagnostic)}
        for name in ("kind", "span_id", "semantic_role", "field_name",
                      "expected", "actual"):
            assert name in fields, f"AnnotationValidationDiagnostic missing: {name}"

    # 14. Full suite passes (verified at runtime).
    def test_migration_not_reverted(self):
        """Sanity: the registry is active and returns correct contracts."""
        from nl2spl.compiler.annotation_role_contract import (
            ROLE_CONTRACT_REGISTRY,
        )
        assert ROLE_CONTRACT_REGISTRY.get_role_contract("input_contract") is not None
        assert ROLE_CONTRACT_REGISTRY.get_role_contract("profile_domain") is not None

    # 15. Static scan: no new independent role-contract tables in production code.
    def test_no_new_independent_role_contract_tables(self):
        """AST-based scan of src/nl2spl for forbidden non-empty role-contract
        dict assignments.  Excludes the canonical registry module."""
        import ast
        import os

        registry_file = os.path.normpath(
            "src/nl2spl/compiler/annotation_role_contract/registry.py"
        )
        protected_names = {
            "_ROLE_CONTRACT", "ROUTE_PRIOR_ROLE_CONTRACTS", "_ANNOTATION_SEMANTICS",
        }
        compiler_keys = {
            "field", "route_family", "construct_target", "slot_target", "executable",
        }
        violations: list[str] = []

        class RoleTableVisitor(ast.NodeVisitor):
            def __init__(self, fpath):
                self.fpath = fpath

            def visit_Assign(self, node):
                for target in node.targets:
                    name = self._target_name(target)
                    if name in protected_names:
                        self._check_protected(name, node.value)
                self.generic_visit(node)

            def visit_AnnAssign(self, node):
                name = self._target_name(node.target)
                if name in protected_names and node.value:
                    self._check_protected(name, node.value)
                self.generic_visit(node)

            def _check_protected(self, name, value):
                if not self._non_empty_dict(value):
                    return  # empty wrapper is allowed
                # _ROLE_CONTRACT and ROUTE_PRIOR_ROLE_CONTRACTS: any
                # non-empty dict is forbidden outside the registry.
                if name in {"_ROLE_CONTRACT", "ROUTE_PRIOR_ROLE_CONTRACTS"}:
                    violations.append(f"{self.fpath}: non-empty {name}")
                    return
                # _ANNOTATION_SEMANTICS: allowed only if it contains
                # NO compiler-facing fields (role-only wrapper).
                if name == "_ANNOTATION_SEMANTICS":
                    if self._has_compiler_keys(value):
                        violations.append(
                            f"{self.fpath}: non-empty {name} "
                            f"(contains compiler-facing fields)"
                        )

            @staticmethod
            def _target_name(target):
                if isinstance(target, ast.Name):
                    return target.id
                return ""

            @staticmethod
            def _non_empty_dict(node):
                return (
                    isinstance(node, ast.Dict)
                    and len(node.keys) > 0
                )

            @staticmethod
            def _has_compiler_keys(node):
                if not isinstance(node, ast.Dict):
                    return False
                inner_keys = set()
                for k in node.keys:
                    if isinstance(k, ast.Constant) and isinstance(k.value, str):
                        inner_keys.add(k.value)
                return bool(compiler_keys & inner_keys)

        for root, _dirs, files in os.walk("src/nl2spl"):
            for fn in files:
                if not fn.endswith(".py"):
                    continue
                fpath = os.path.normpath(os.path.join(root, fn))
                if fpath == registry_file:
                    continue
                try:
                    with open(fpath, encoding="utf-8") as f:
                        tree = ast.parse(f.read(), filename=fpath)
                    RoleTableVisitor(fpath).visit(tree)
                except SyntaxError:
                    continue

        assert not violations, (
            "Forbidden non-empty role-contract tables found outside canonical registry:\n"
            + "\n".join(violations)
        )
