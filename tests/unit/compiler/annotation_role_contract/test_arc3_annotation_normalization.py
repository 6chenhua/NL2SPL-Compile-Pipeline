"""ARC3: Annotation Normalization Convergence — normalize API and path tests.

Verifies that every annotation generation path derives compiler-facing
fields from the canonical role contract, and that raw LLM/hint values
are preserved only as diagnostics, not as authoritative fields.
"""

from __future__ import annotations

import pytest


# ===========================================================================
# Helpers
# ===========================================================================


def _make_annotation_from_llm(**overrides):
    """Simulate an LLM returning a RefinedAnnotation."""
    from nl2spl.pipeline.stages.stage2_field_router_prompt import (
        RefinedAnnotation,
    )

    defaults = {
        "span_id": "sp_test",
        "field": "behavior",
        "semantic_role": None,
        "route_family": None,
        "construct_target": None,
        "slot_target": None,
        "executable": False,
        "source_section_id": None,
        "source_packet_id": None,
        "primary": True,
    }
    defaults.update(overrides)
    return RefinedAnnotation(**defaults)


# ===========================================================================
# Test 1: LLM returns profile_domain + RESOURCE_CONTRACT/input → corrected
# ===========================================================================


class TestProfileDomainResourceContractCorrected:
    """LLM returns profile_domain with construct_target=RESOURCE_CONTRACT
    and slot_target=input.  Normalization must force these to None."""

    def test_normalize_api_drops_construct_and_slot_for_profile_domain(self):
        from nl2spl.compiler.annotation_role_contract.normalize import (
            normalize_annotation_from_role,
        )

        result = normalize_annotation_from_role(
            span_id="sp_001",
            semantic_role="profile_domain",
            raw_construct_target="RESOURCE_CONTRACT",
            raw_slot_target="input",
        )

        ann = result.annotation
        assert ann.construct_target is None, (
            f"profile_domain + RESOURCE_CONTRACT: construct_target must be None, "
            f"got {ann.construct_target!r}"
        )
        assert ann.slot_target is None, (
            f"profile_domain + RESOURCE_CONTRACT: slot_target must be None, "
            f"got {ann.slot_target!r}"
        )
        # Raw values preserved for diagnostics
        assert result.raw_construct_target == "RESOURCE_CONTRACT"
        assert result.raw_slot_target == "input"
        # Diagnostics report the correction
        assert len(result.diagnostics) >= 2

    def test_normalize_api_preserves_correct_semantic_role(self):
        from nl2spl.compiler.annotation_role_contract.normalize import (
            normalize_annotation_from_role,
        )

        result = normalize_annotation_from_role(
            span_id="sp_001",
            semantic_role="profile_domain",
        )

        assert result.annotation.semantic_role == "profile_domain"
        assert result.annotation.field == "domain"
        assert result.annotation.executable is False
        assert result.annotation.route_family == "profile"

    def test_normalize_in_merge_path_drops_profile_domain_construct(self):
        """_normalize_annotation_contract() (merge path) also corrects this."""
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

        assert ct is None
        assert st is None
        assert role == "profile_domain"
        assert field == "domain"
        assert exe is False


# ===========================================================================
# Test 2: LLM returns input_contract with wrong field → corrected
# ===========================================================================


class TestWrongFieldCorrected:
    """LLM returns the correct semantic_role but wrong compiler-facing fields."""

    def test_normalize_api_corrects_wrong_field(self):
        from nl2spl.compiler.annotation_role_contract.normalize import (
            normalize_annotation_from_role,
        )

        result = normalize_annotation_from_role(
            span_id="sp_002",
            semantic_role="input_contract",
            raw_field="behavior",  # LLM gave wrong field
        )

        assert result.annotation.field == "resources", (
            f"input_contract must have field='resources', got {result.annotation.field!r}"
        )
        assert len(result.diagnostics) >= 1
        assert "field" in result.diagnostics[0]

    def test_normalize_merge_path_corrects_wrong_field(self):
        from nl2spl.pipeline.stages.stage2_field_router import FieldRouter

        diagnostics: list[str] = []
        field, role, rf, ct, st, exe = FieldRouter._normalize_annotation_contract(
            span_id="sp_002",
            field="behavior",  # LLM gave wrong field
            semantic_role="input_contract",
            route_family="resource_contract",
            construct_target="RESOURCE_CONTRACT",
            slot_target="input",
            executable=False,
            diagnostics=diagnostics,
        )

        assert field == "resources"
        assert len(diagnostics) > 0


# ===========================================================================
# Test 3: LLM returns process_step with executable=False → corrected
# ===========================================================================


class TestExecutableCorrected:
    """process_step must be executable=True per contract."""

    def test_normalize_api_corrects_executable(self):
        from nl2spl.compiler.annotation_role_contract.normalize import (
            normalize_annotation_from_role,
        )

        result = normalize_annotation_from_role(
            span_id="sp_003",
            semantic_role="process_step",
            raw_executable=False,  # LLM says non-executable
        )

        assert result.annotation.executable is True, (
            f"process_step must be executable=True, got {result.annotation.executable}"
        )
        assert len(result.diagnostics) >= 1


# ===========================================================================
# Test 4: Deterministic + LLM paths produce identical annotation shape
# ===========================================================================


class TestPathsProduceIdenticalShape:
    """For the same semantic_role and provenance, deterministic packet
    path and LLM normalization path must produce identical compiler fields."""

    def test_both_paths_identical_for_input_contract(self):
        from nl2spl.compiler.annotation_role_contract.normalize import (
            normalize_annotation_from_role,
        )

        # Simulate deterministic path (packet_type → semantic_role → normalize)
        det_result = normalize_annotation_from_role(
            span_id="sp_004",
            semantic_role="input_contract",
            source_section_id="sec_inputs",
            source_packet_id="pkt_1",
        )

        # Simulate LLM path (LLM proposes semantic_role → normalize)
        llm_result = normalize_annotation_from_role(
            span_id="sp_004",
            semantic_role="input_contract",
            source_section_id="sec_inputs",
            source_packet_id="pkt_1",
            raw_field="behavior",  # LLM guessed wrong
            raw_executable=True,   # LLM guessed wrong
        )

        # Compiler-facing fields must be identical
        det = det_result.annotation
        llm = llm_result.annotation
        assert det.field == llm.field == "resources"
        assert det.route_family == llm.route_family == "resource_contract"
        assert det.construct_target == llm.construct_target == "RESOURCE_CONTRACT"
        assert det.slot_target == llm.slot_target == "input"
        assert det.executable == llm.executable == False

        # LLM path produces diagnostics about raw values
        assert len(llm_result.diagnostics) >= 2


# ===========================================================================
# Test 5: Requiredness survives normalization untouched
# ===========================================================================


class TestRequirednessSurvivesNormalization:
    """Requiredness metadata passes through normalization without being
    derived or changed by the role contract."""

    def test_requiredness_passed_through(self):
        from nl2spl.compiler.annotation_role_contract.normalize import (
            normalize_annotation_from_role,
        )

        result = normalize_annotation_from_role(
            span_id="sp_005",
            semantic_role="input_contract",
            metadata={"requiredness": "required"},
        )

        assert result.annotation.metadata.get("requiredness") == "required"

    def test_requiredness_not_added_by_normalization(self):
        from nl2spl.compiler.annotation_role_contract.normalize import (
            normalize_annotation_from_role,
        )

        result = normalize_annotation_from_role(
            span_id="sp_006",
            semantic_role="input_contract",
        )

        assert "requiredness" not in result.annotation.metadata


# ===========================================================================
# Test 6: Multi-label same span with distinct roles
# ===========================================================================


class TestMultiLabelSameSpan:
    """A span can have multiple annotations with different semantic roles."""

    def test_two_distinct_roles_same_span(self):
        from nl2spl.compiler.annotation_role_contract.normalize import (
            normalize_annotation_from_role,
        )

        r1 = normalize_annotation_from_role(
            span_id="sp_multi",
            semantic_role="input_contract",
        )
        r2 = normalize_annotation_from_role(
            span_id="sp_multi",
            semantic_role="output_contract",
        )

        assert r1.annotation.span_id == r2.annotation.span_id == "sp_multi"
        assert r1.annotation.semantic_role == "input_contract"
        assert r2.annotation.semantic_role == "output_contract"
        assert r1.annotation.slot_target != r2.annotation.slot_target


# ===========================================================================
# Test 7: Compile hint proposes wrong construct for profile_domain
# ===========================================================================


class TestHintConflictDiagnostics:
    """When a compile hint proposes values conflicting with the role contract,
    the annotation keeps the contract value and the hint conflict is recorded."""

    def test_hint_proposes_wrong_construct_for_profile_domain(self):
        self._test_hint_keeps_contract_not_hint(
            semantic_role="profile_domain",
            contract_construct=None,
            contract_slot=None,
            hint_construct="RESOURCE_CONTRACT",
            hint_slot="input",
        )

    def test_hint_proposes_wrong_slot_for_failure_mode(self):
        # failure_mode has hint_category "flow" so _enrich_from_hints runs
        self._test_hint_keeps_contract_not_hint(
            semantic_role="failure_mode",
            contract_construct="EXCEPTION_FLOW",
            contract_slot="condition",
            hint_construct="RESOURCE_CONTRACT",
            hint_slot="handler",
        )

    @staticmethod
    def _test_hint_keeps_contract_not_hint(
        semantic_role: str,
        contract_construct: str | None,
        contract_slot: str | None,
        hint_construct: str,
        hint_slot: str,
    ):
        """The annotation keeps the contract value; hint conflict is stored
        in metadata and diagnostics."""
        from unittest.mock import MagicMock

        from nl2spl.canonical.compile_input import CompileHint
        from nl2spl.ir.field_route_ir import RouteAnnotation
        from nl2spl.pipeline.stages.stage2_field_router import FieldRouter

        # Build a contract-conformant annotation first
        from nl2spl.compiler.annotation_role_contract.normalize import (
            normalize_annotation_from_role,
        )

        result = normalize_annotation_from_role(
            span_id="sp_hint",
            semantic_role=semantic_role,
        )
        annotation = result.annotation

        # Now simulate _enrich_from_hints with a conflicting hint
        router = _make_minimal_router()
        hint = CompileHint(
            source_section_id="sec_test",
            text="test hint",
            target=hint_construct,
            metadata={"slot_target": hint_slot, "_": True},
        )
        hint_indexes = _make_hint_indexes_for_role(semantic_role, [hint])

        router._enrich_from_hints(
            annotation, source_packet_id="", source_section_id="sec_test",
            hint_indexes=hint_indexes,
        )

        # Contract values are preserved
        assert annotation.construct_target == contract_construct, (
            f"{semantic_role}: construct_target must remain {contract_construct!r}, "
            f"got {annotation.construct_target!r}"
        )
        assert annotation.slot_target == contract_slot, (
            f"{semantic_role}: slot_target must remain {contract_slot!r}, "
            f"got {annotation.slot_target!r}"
        )

        # Hint conflict is visible in metadata
        hint_meta = annotation.metadata.get("_hint_", {})
        if hint_construct != contract_construct:
            assert "construct_target" in hint_meta, (
                f"Hint construct_target conflict not recorded"
            )
        if hint_slot != contract_slot:
            assert "slot_target" in hint_meta, (
                f"Hint slot_target conflict not recorded"
            )


# ===========================================================================
# Test 8: _ANNOTATION_SEMANTICS is now a role-only compatibility wrapper
# ===========================================================================


class TestAnnotationSemanticsCompatibilityWrapper:
    """_ANNOTATION_SEMANTICS now only maps packet_type → semantic_role.
    All compiler-facing fields come from the registry."""

    def test_annotation_semantics_has_no_field_keys(self):
        """The compatibility wrapper should NOT contain field, route_family,
        construct_target, slot_target, or executable."""
        from nl2spl.pipeline.stages.stage2_field_router import (
            _ANNOTATION_SEMANTICS,
        )

        for packet_type, sem in _ANNOTATION_SEMANTICS.items():
            assert "field" not in sem, (
                f"{packet_type}: field must not be in _ANNOTATION_SEMANTICS"
            )
            assert "route_family" not in sem, (
                f"{packet_type}: route_family must not be in _ANNOTATION_SEMANTICS"
            )
            assert "construct_target" not in sem, (
                f"{packet_type}: construct_target must not be in _ANNOTATION_SEMANTICS"
            )
            assert "slot_target" not in sem, (
                f"{packet_type}: slot_target must not be in _ANNOTATION_SEMANTICS"
            )
            assert "executable" not in sem, (
                f"{packet_type}: executable must not be in _ANNOTATION_SEMANTICS"
            )
            # The only key should be semantic_role
            assert set(sem.keys()) == {"semantic_role"}, (
                f"{packet_type}: _ANNOTATION_SEMANTICS should only have "
                f"'semantic_role', got {set(sem.keys())}"
            )

    def test_annotation_semantics_still_has_all_packet_types(self):
        from nl2spl.pipeline.stages.stage2_field_router import (
            _ANNOTATION_SEMANTICS,
        )

        required_packet_types = {
            "task_family", "runtime_input", "required_output",
            "process_step", "policy", "failure_mode", "delegation_rule",
        }
        assert set(_ANNOTATION_SEMANTICS.keys()) == required_packet_types


# ===========================================================================
# Test 9: ROUTE_PRIOR_ROLE_CONTRACTS is empty compatibility wrapper
# ===========================================================================


class TestRoutePriorContractsCompatibilityWrapper:
    """ROUTE_PRIOR_ROLE_CONTRACTS is now an empty dict — a compatibility
    wrapper that no longer carries any role mapping literals."""

    def test_route_prior_contracts_is_empty(self):
        from nl2spl.pipeline.stages.stage2_field_router import (
            ROUTE_PRIOR_ROLE_CONTRACTS,
        )

        assert ROUTE_PRIOR_ROLE_CONTRACTS == {}, (
            "ROUTE_PRIOR_ROLE_CONTRACTS must be empty after ARC3 convergence"
        )


# ===========================================================================
# Test 10: packet_type_context fallback derives field from registry
# ===========================================================================


class TestPacketTypeContextFieldFromRegistry:
    """The packet_type_context fallback branch in _build_structural_route_context()
    must derive ``suggested_field`` from the canonical registry, not from the
    old ``_ANNOTATION_SEMANTICS`` wrapper (which no longer carries ``field``)."""

    @staticmethod
    def _make_router():
        from unittest.mock import MagicMock

        from nl2spl.pipeline.stages.stage2_field_router import FieldRouter

        return FieldRouter(config=MagicMock(), client=MagicMock())

    @staticmethod
    def _make_canonical_input(packets: list, route_priors: list | None = None):
        from nl2spl.canonical.compile_input import (
            CanonicalCompileInput,
            CompileHints,
            HardFacts,
        )

        return CanonicalCompileInput(
            source_schema="structural_nl",
            schema_version="1.0",
            raw_text="test",
            raw_sections=[],
            semantic_packets=packets,
            compile_hints=CompileHints(),
            hard_facts=HardFacts(),
            route_priors=route_priors or [],
        )

    @staticmethod
    def _make_span(span_id: str, packet_id: str, section_id: str = "sec_test"):
        from nl2spl.ir.span_ir import SpanIR

        return SpanIR(
            span_id=span_id,
            text="test span",
            source_section_id=section_id,
            source_packet_id=packet_id,
        )

    @staticmethod
    def _make_packet(packet_id: str, packet_type: str, section_id: str = "sec_test"):
        from nl2spl.canonical.compile_input import SemanticPacket

        return SemanticPacket(
            packet_id=packet_id,
            source_section_id=section_id,
            packet_type=packet_type,
            text="test packet",
            modality="hint",
            compile_targets=[],
        )

    def test_policy_packet_type_context_yields_rules_field(self):
        """policy packet → constraint role → field='rules' from registry."""
        router = self._make_router()
        packet = self._make_packet("p_pol", "policy")
        span = self._make_span("sp_pol", "p_pol")
        canonical = self._make_canonical_input([packet])

        # Section context is "sec_test" — won't match any section mapping,
        # so it falls through to packet_type_context
        structural_priors, annotations = router._build_structural_route_context(
            [span], canonical
        )

        # Find the packet_type_context prior
        pkt_priors = [p for p in structural_priors if p.prior_kind == "packet_type_context"]
        assert len(pkt_priors) >= 1, (
            f"Expected at least 1 packet_type_context prior, got {len(pkt_priors)}"
        )
        policy_prior = [p for p in pkt_priors if p.packet_type == "policy"]
        assert len(policy_prior) == 1
        assert policy_prior[0].suggested_field == "rules", (
            f"policy packet must suggest field='rules' from registry, "
            f"got {policy_prior[0].suggested_field!r}"
        )
        assert policy_prior[0].metadata.get("suggested_semantic_role") == "constraint"

    def test_task_family_packet_type_context_yields_domain_field(self):
        """task_family packet → profile_domain role → field='domain' from registry."""
        router = self._make_router()
        packet = self._make_packet("p_task", "task_family")
        span = self._make_span("sp_task", "p_task")
        canonical = self._make_canonical_input([packet])

        structural_priors, annotations = router._build_structural_route_context(
            [span], canonical
        )

        pkt_priors = [p for p in structural_priors if p.prior_kind == "packet_type_context"]
        task_prior = [p for p in pkt_priors if p.packet_type == "task_family"]
        assert len(task_prior) == 1
        assert task_prior[0].suggested_field == "domain", (
            f"task_family packet must suggest field='domain' from registry, "
            f"got {task_prior[0].suggested_field!r}"
        )
        assert task_prior[0].metadata.get("suggested_semantic_role") == "profile_domain"

    def test_process_step_packet_type_context_yields_behavior_field(self):
        """process_step packet → process_step role → field='behavior' from registry."""
        router = self._make_router()
        packet = self._make_packet("p_step", "process_step")
        span = self._make_span("sp_step", "p_step")
        canonical = self._make_canonical_input([packet])

        structural_priors, annotations = router._build_structural_route_context(
            [span], canonical
        )

        pkt_priors = [p for p in structural_priors if p.prior_kind == "packet_type_context"]
        step_prior = [p for p in pkt_priors if p.packet_type == "process_step"]
        assert len(step_prior) == 1
        assert step_prior[0].suggested_field == "behavior", (
            f"process_step packet must suggest field='behavior' from registry, "
            f"got {step_prior[0].suggested_field!r}"
        )


# ===========================================================================
# Helpers for hint testing
# ===========================================================================


def _make_minimal_router():
    """Create a minimal FieldRouter with mocked dependencies."""
    from unittest.mock import MagicMock

    from nl2spl.pipeline.stages.stage2_field_router import FieldRouter

    return FieldRouter(config=MagicMock(), client=MagicMock())


def _make_hint_indexes_for_role(semantic_role: str, hints: list):
    """Build hint indexes for a specific semantic_role's hint category."""
    from nl2spl.pipeline.stages.stage2_field_router import FieldRouter

    category = FieldRouter._hint_category_for(semantic_role)
    if not category:
        return {}
    indexes: dict[str, dict[str, dict[str, list]]] = {}
    by_section: dict[str, list] = {}
    for hint in hints:
        by_section.setdefault(hint.source_section_id, []).append(hint)
    indexes[category] = {"by_packet": {}, "by_section": by_section}
    return indexes
