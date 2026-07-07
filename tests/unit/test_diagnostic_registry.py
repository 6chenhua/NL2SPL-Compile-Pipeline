"""Unit tests for DiagnosticRegistry and DiagnosticSpec."""

import pytest

from nl2spl.compiler.diagnostic_registry import DiagnosticRegistry, DiagnosticSpec


class TestDiagnosticSpec:
    def test_default_enabled(self):
        spec = DiagnosticSpec(
            kind="test_kind",
            default_severity="warning",
            blocks_completion=False,
            description="A test diagnostic.",
        )
        assert spec.enabled is True

    def test_explicitly_disabled(self):
        spec = DiagnosticSpec(
            kind="test_kind",
            default_severity="info",
            blocks_completion=False,
            description="Reserved for future use.",
            enabled=False,
        )
        assert spec.enabled is False

    def test_allowed_targets_default_empty(self):
        spec = DiagnosticSpec(
            kind="test_kind",
            default_severity="warning",
            blocks_completion=False,
            description="No targets specified.",
        )
        assert spec.allowed_targets == []


class TestDefaultRegistry:
    @pytest.fixture(autouse=True)
    def _setup(self):
        self.registry = DiagnosticRegistry.default()

    # -- enabled kinds -------------------------------------------------------

    @pytest.mark.parametrize("kind", [
        "missing_handler",
        "missing_output_producer",
        "required_output_deferred",
        "type_or_contract_ambiguity",
        "assumed_command_not_renderable",
        "unmapped_behavior_span",
        "missing_provenance",
        "semantic_conflict",
    ])
    def test_enabled_kind_is_present(self, kind):
        assert self.registry.has(kind), f"Missing enabled kind: {kind}"

    @pytest.mark.parametrize("kind", [
        "missing_handler",
        "missing_output_producer",
        "type_or_contract_ambiguity",
        "assumed_command_not_renderable",
        "unmapped_behavior_span",
    ])
    def test_completion_blocking_kinds(self, kind):
        spec = self.registry.get(kind)
        assert spec.blocks_completion is True, f"{kind} should block completion"

    def test_missing_handler_allowed_targets(self):
        spec = self.registry.get("missing_handler")
        assert "exception_flow" in spec.allowed_targets

    def test_semantic_conflict_is_not_blocking(self):
        spec = self.registry.get("semantic_conflict")
        assert spec.blocks_completion is False

    def test_semantic_conflict_default_warning(self):
        spec = self.registry.get("semantic_conflict")
        assert spec.default_severity == "warning"

    def test_assumed_command_targets_step(self):
        spec = self.registry.get("assumed_command_not_renderable")
        assert "step" in spec.allowed_targets

    # -- reserved / disabled kinds ------------------------------------------

    @pytest.mark.parametrize("kind", [
        "redundant_requirement",
        "policy_step_conflict",
        "use_before_def",
        "worker_graph_inconsistency",
    ])
    def test_reserved_kind_is_present(self, kind):
        assert self.registry.has(kind), f"Missing reserved kind: {kind}"

    @pytest.mark.parametrize("kind", [
        "redundant_requirement",
        "policy_step_conflict",
        "use_before_def",
        "worker_graph_inconsistency",
    ])
    def test_reserved_kind_is_disabled(self, kind):
        spec = self.registry.get(kind)
        assert spec.enabled is False, f"{kind} should be disabled"

    # -- list_kinds ----------------------------------------------------------

    def test_list_kinds_all(self):
        kinds = self.registry.list_kinds()
        assert "missing_handler" in kinds
        assert "redundant_requirement" in kinds  # reserved but still listed
        assert len(kinds) == 17  # enabled + reserved, including R8 output states

    def test_list_kinds_enabled_only(self):
        kinds = self.registry.list_kinds(enabled_only=True)
        assert "missing_handler" in kinds
        assert "redundant_requirement" not in kinds
        assert len(kinds) == 12  # B5 + R8 required output deferred

    # -- validation ----------------------------------------------------------

    def test_get_unknown_raises_key_error(self):
        with pytest.raises(KeyError, match="NO_SUCH"):
            self.registry.get("NO_SUCH_DIAGNOSTIC")

    def test_has_unknown_returns_false(self):
        assert self.registry.has("NO_SUCH_DIAGNOSTIC") is False

    def test_register_rejects_duplicate_by_overwriting(self):
        registry = DiagnosticRegistry()
        registry.register(DiagnosticSpec(
            kind="dup", default_severity="info", blocks_completion=False,
            description="First.",
        ))
        registry.register(DiagnosticSpec(
            kind="dup", default_severity="error", blocks_completion=True,
            description="Second — overwrites.",
        ))
        assert registry.get("dup").default_severity == "error"

    # -- determinism ---------------------------------------------------------

    def test_default_is_deterministic(self):
        a = DiagnosticRegistry.default()
        b = DiagnosticRegistry.default()
        assert a.list_kinds() == b.list_kinds()


def test_deferred_api_contract_validation_contract() -> None:
    registry = DiagnosticRegistry.default()
    spec = registry.get("deferred_api_contract_validation")
    assert spec.enabled is True
    assert spec.default_severity == "info"
    assert spec.blocks_completion is False
    assert spec.allowed_targets == ["api"]

    structural = registry.get("type_or_contract_ambiguity")
    assert structural.default_severity == "warning"
    assert structural.blocks_completion is True


def test_required_output_deferred_contract() -> None:
    registry = DiagnosticRegistry.default()
    spec = registry.get("required_output_deferred")
    assert spec.enabled is True
    assert spec.default_severity == "warning"
    assert spec.blocks_completion is True
    assert spec.allowed_targets == ["variable", "output"]
