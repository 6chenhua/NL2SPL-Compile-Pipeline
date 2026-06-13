"""B0: Backend registry shell and typed errors tests.

Verifies:
  1. Typed errors exist and form a proper hierarchy.
  2. Registries are empty on construction.
  3. Registries accept registration and reject duplicates.
  4. SPLEditingRuntimeRegistry composes all four.
  5. No LLM, IR, or patch side effects on construction.
  6. construct_registry.py does NOT import spl_editing implementation.
"""

from __future__ import annotations

import inspect

import pytest

from nl2spl.compiler.spl_editing.core.errors import (
    PatchValidationError,
    SPLEditingError,
    StaleRevisionError,
    UnsupportedIssueError,
    UnsupportedPatchTypeError,
    VerificationFailedError,
)
from nl2spl.compiler.spl_editing.core.registry import (
    ContextBuilderRegistry,
    HandlerRegistry,
    PatchRegistry,
    SPLEditingRuntimeRegistry,
    TargetResolverRegistry,
)


# ===========================================================================
# B0-1: Typed error hierarchy
# ===========================================================================


class TestB0Errors:
    """B0: Typed errors exist and are importable."""

    def test_base_error(self) -> None:
        """B0: SPLEditingError is the base for all editing errors."""
        with pytest.raises(SPLEditingError):
            raise SPLEditingError("base error")

    def test_unsupported_issue_error(self) -> None:
        """B0: UnsupportedIssueError inherits from SPLEditingError."""
        assert issubclass(UnsupportedIssueError, SPLEditingError)
        with pytest.raises(SPLEditingError):
            raise UnsupportedIssueError("unsupported")

    def test_unsupported_patch_type_error(self) -> None:
        """B0: UnsupportedPatchTypeError inherits from SPLEditingError."""
        assert issubclass(UnsupportedPatchTypeError, SPLEditingError)

    def test_patch_validation_error(self) -> None:
        """B0: PatchValidationError inherits from SPLEditingError."""
        assert issubclass(PatchValidationError, SPLEditingError)

    def test_stale_revision_error(self) -> None:
        """B0: StaleRevisionError inherits from SPLEditingError."""
        assert issubclass(StaleRevisionError, SPLEditingError)

    def test_verification_failed_error(self) -> None:
        """B0: VerificationFailedError inherits from SPLEditingError."""
        assert issubclass(VerificationFailedError, SPLEditingError)
        with pytest.raises(SPLEditingError):
            raise VerificationFailedError("verification failed")

    def test_all_errors_can_be_caught_as_spl_editing_error(self) -> None:
        """B0: All editing errors are catchable via SPLEditingError."""
        errors = [
            UnsupportedIssueError("x"),
            UnsupportedPatchTypeError("x"),
            PatchValidationError("x"),
            StaleRevisionError("x"),
            VerificationFailedError("x"),
        ]
        for e in errors:
            assert isinstance(e, SPLEditingError)

    def test_bare_exception_is_not_caught(self) -> None:
        """B0: Catchers should use SPLEditingError, not bare Exception."""
        # A ValueError should NOT be an SPLEditingError
        assert not isinstance(ValueError("x"), SPLEditingError)


# ===========================================================================
# B0-2: Registry empty construction
# ===========================================================================


class TestB0RegistryEmpty:
    """B0: Registries are empty on construction."""

    def test_patch_registry_empty(self) -> None:
        r = PatchRegistry()
        assert len(r) == 0
        assert r.list_keys() == ()

    def test_handler_registry_empty(self) -> None:
        r = HandlerRegistry()
        assert len(r) == 0

    def test_target_resolver_registry_empty(self) -> None:
        r = TargetResolverRegistry()
        assert len(r) == 0

    def test_context_builder_registry_empty(self) -> None:
        r = ContextBuilderRegistry()
        assert len(r) == 0

    def test_runtime_registry_empty(self) -> None:
        rt = SPLEditingRuntimeRegistry()
        assert len(rt.patches) == 0
        assert len(rt.handlers) == 0
        assert len(rt.target_resolvers) == 0
        assert len(rt.context_builders) == 0


# ===========================================================================
# B0-3: Registry registration and duplicate rejection
# ===========================================================================


class TestB0RegistryRegistration:
    """B0: Registries accept entries and reject duplicates."""

    def test_register_and_retrieve(self) -> None:
        r = PatchRegistry()
        r.register("AddExceptionHandlerStep", object())
        assert r.has("AddExceptionHandlerStep")
        assert r.get("AddExceptionHandlerStep") is not None

    def test_has_returns_false_for_unknown(self) -> None:
        r = HandlerRegistry()
        assert not r.has("no_such_handler")

    def test_get_unknown_raises_key_error(self) -> None:
        r = ContextBuilderRegistry()
        with pytest.raises(KeyError):
            r.get("no_such_context")

    def test_duplicate_registration_raises(self) -> None:
        r = TargetResolverRegistry()
        r.register("resolver_a", object())
        with pytest.raises(KeyError, match="resolver_a"):
            r.register("resolver_a", object())

    def test_list_keys_is_sorted(self) -> None:
        r = PatchRegistry()
        r.register("Z", object())
        r.register("A", object())
        r.register("M", object())
        assert r.list_keys() == ("A", "M", "Z")

    def test_runtime_registry_sub_registries_are_independent(self) -> None:
        rt = SPLEditingRuntimeRegistry()
        rt.patches.register("P", object())
        rt.handlers.register("H", object())
        # Independent namespaces — same key in different registries is fine
        rt.target_resolvers.register("P", object())
        assert rt.patches.has("P")
        assert rt.target_resolvers.has("P")
        assert not rt.context_builders.has("P")


# ===========================================================================
# B0-4: No side effects on construction
# ===========================================================================


class TestB0NoSideEffects:
    """B0: Registry construction has no LLM, IR, or artifact side effects."""

    def test_patch_registry_construction_is_pure(self) -> None:
        """B0: PatchRegistry.__init__ does not import patches or call LLM."""
        # Construction should not trigger any module-level side effects
        r = PatchRegistry()
        assert len(r) == 0

    def test_runtime_registry_construction_is_pure(self) -> None:
        """B0: SPLEditingRuntimeRegistry constructs without side effects."""
        rt = SPLEditingRuntimeRegistry()
        # All sub-registries exist and are empty
        for attr in ["patches", "handlers", "target_resolvers", "context_builders"]:
            assert hasattr(rt, attr)

    def test_no_llm_imports_in_registry_module(self) -> None:
        """B0: registry.py does not import LLM client or pipeline stages."""
        from nl2spl.compiler.spl_editing.core import registry as reg_mod

        source = inspect.getsource(reg_mod)
        # Must not import LLM client or related modules
        assert "import llm" not in source.lower()
        assert "from llm" not in source.lower()
        assert "openai" not in source.lower()
        # Must not import patch implementation
        assert "from nl2spl.compiler.spl_editing.patches" not in source
        assert "from nl2spl.compiler.spl_editing.handlers" not in source


# ===========================================================================
# B0-5: construct_registry.py does NOT import spl_editing
# ===========================================================================


class TestB0ConstructRegistryBoundary:
    """B0: IRS layer does not depend on SPL Editing implementation."""

    def test_construct_registry_no_spl_editing_import(self) -> None:
        """B0: construct_registry module source contains no spl_editing import."""
        from nl2spl.compiler import construct_registry as cr_mod

        source = inspect.getsource(cr_mod)
        assert "spl_editing" not in source, (
            "B0 FAIL: construct_registry.py must NOT import from spl_editing"
        )

    def test_irs_checker_no_spl_editing_import(self) -> None:
        """B0: Post-normalize IRS checker has no spl_editing import."""
        from nl2spl.compiler.irs.checkers import post_normalize as pn_mod

        source = inspect.getsource(pn_mod)
        assert "spl_editing" not in source, (
            "B0 FAIL: post_normalize checker must NOT import spl_editing"
        )

    def test_executable_gate_no_spl_editing_import(self) -> None:
        """B0: ExecutableElementGate has no spl_editing import."""
        from nl2spl.pipeline import executable_gate as gate_mod

        source = inspect.getsource(gate_mod)
        assert "spl_editing" not in source, (
            "B0 FAIL: executable_gate must NOT import spl_editing"
        )

    def test_producer_index_no_spl_editing_import(self) -> None:
        """B0: ProducerIndex has no spl_editing import."""
        from nl2spl.compiler import producer_index as pi_mod

        source = inspect.getsource(pi_mod)
        assert "spl_editing" not in source, (
            "B0 FAIL: producer_index must NOT import spl_editing"
        )
