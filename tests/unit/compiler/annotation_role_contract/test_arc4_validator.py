"""ARC4: Full-Field Validator — registry-driven contract validation tests.

Verifies that the validator enforces all five compiler-facing fields
including expected None, rejects invalid annotations, and correctly
handles pre-/post-enrichment requiredness boundaries.
"""

from __future__ import annotations

import pytest


# ===========================================================================
# Helpers
# ===========================================================================


def _make_validator():
    from nl2spl.pipeline.stages.stage2_field_router_validator import (
        RouteRefinementValidator,
    )
    return RouteRefinementValidator()


def _make_annotation(**overrides):
    from nl2spl.pipeline.stages.stage2_field_router_prompt import (
        RefinedAnnotation,
    )
    defaults = {
        "span_id": "sp_001",
        "field": None,
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


def _validate(annotations: list, spans=None):
    from nl2spl.pipeline.stages.stage2_field_router_prompt import (
        RouteRefinementResult,
    )
    from nl2spl.ir.span_ir import SpanIR

    if spans is None:
        spans = [SpanIR(span_id=a.span_id, text="test") for a in annotations]
    result = RouteRefinementResult(annotations=annotations)
    return _make_validator().validate(result, spans=spans, canonical_input=None)


# ===========================================================================
# Test 1: profile_domain + RESOURCE_CONTRACT/input → rejected
# ===========================================================================


class TestProfileDomainContractRejection:
    """Phase 1: profile_domain with mismatched construct_target/slot_target
    is now ACCEPTED with diagnostics (normalization will correct fields)."""

    def test_accepts_with_diagnostic_for_construct_target_mismatch(self):
        ann = _make_annotation(
            span_id="sp_pd",
            field="domain",
            semantic_role="profile_domain",
            construct_target="RESOURCE_CONTRACT",
            slot_target="input",
        )
        v = _validate([ann])
        assert "sp_pd" in {a.span_id for a in v.accepted}, (
            "Phase 1: known role must be accepted with diagnostic"
        )
        assert len(v.structured_diagnostics) >= 1, (
            "Phase 1: diagnostic must be recorded for construct_target/slot mismatch"
        )

    def test_accepts_with_diagnostic_for_slot_target_only(self):
        ann = _make_annotation(
            span_id="sp_pd",
            field="domain",
            semantic_role="profile_domain",
            slot_target="input",
        )
        v = _validate([ann])
        assert "sp_pd" in {a.span_id for a in v.accepted}, (
            "Phase 1: known role with slot mismatch must be accepted"
        )
        assert len(v.structured_diagnostics) >= 1

    def test_accepts_correct_profile_domain(self):
        ann = _make_annotation(
            span_id="sp_pd",
            field="domain",
            semantic_role="profile_domain",
            executable=False,
        )
        v = _validate([ann])
        assert "sp_pd" in {a.span_id for a in v.accepted}


# ===========================================================================
# Test 2: Expected None enforced for appropriate roles
# ===========================================================================


class TestExpectedNoneEnforced:
    """Phase 1: roles with expected None for construct_target/slot_target
    now ACCEPT annotations with non-None values (diagnostics recorded).
    Normalization will correct the fields in the merge loop."""

    def test_constraint_accepted_with_diagnostic_for_construct_target(self):
        ann = _make_annotation(
            span_id="sp_c",
            field="rules",
            semantic_role="constraint",
            construct_target="RESOURCE_CONTRACT",
            slot_target="input",
        )
        v = _validate([ann])
        assert "sp_c" in {a.span_id for a in v.accepted}, (
            "Phase 1: constraint with known role must be accepted"
        )
        assert len(v.structured_diagnostics) >= 1, (
            "Phase 1: diagnostic must be recorded for construct_target mismatch"
        )

    def test_process_step_accepted_with_diagnostic_for_construct_target(self):
        ann = _make_annotation(
            span_id="sp_ps",
            field="behavior",
            semantic_role="process_step",
            construct_target="EXCEPTION_FLOW",
            slot_target="condition",
            executable=True,
        )
        v = _validate([ann])
        assert "sp_ps" in {a.span_id for a in v.accepted}, (
            "Phase 1: process_step with known role must be accepted"
        )
        assert len(v.structured_diagnostics) >= 1, (
            "Phase 1: diagnostic must be recorded for construct_target/slot mismatch"
        )


# ===========================================================================
# Test 3: Valid contract annotations accepted
# ===========================================================================


class TestValidContractAnnotationsAccepted:
    """Annotations matching the contract on all fields are accepted."""

    def test_input_contract_accepted(self):
        ann = _make_annotation(
            span_id="sp_ic",
            field="resources",
            semantic_role="input_contract",
            route_family="resource_contract",
            construct_target="RESOURCE_CONTRACT",
            slot_target="input",
            executable=False,
        )
        v = _validate([ann])
        assert "sp_ic" in {a.span_id for a in v.accepted}

    def test_failure_mode_accepted(self):
        ann = _make_annotation(
            span_id="sp_fm",
            field="behavior",
            semantic_role="failure_mode",
            route_family="flow_relevant",
            construct_target="EXCEPTION_FLOW",
            slot_target="condition",
            executable=False,
        )
        v = _validate([ann])
        assert "sp_fm" in {a.span_id for a in v.accepted}

    def test_exception_handler_accepted(self):
        ann = _make_annotation(
            span_id="sp_eh",
            field="behavior",
            semantic_role="exception_handler_action",
            route_family="flow_relevant",
            construct_target="EXCEPTION_FLOW",
            slot_target="handler",
            executable=True,
        )
        from nl2spl.ir.span_ir import SpanIR
        span = SpanIR(span_id="sp_eh", text="notify the user and return an error")
        from nl2spl.pipeline.stages.stage2_field_router_prompt import (
            RouteRefinementResult,
        )
        result = RouteRefinementResult(annotations=[ann])
        v = _make_validator()
        validated = v.validate(result, spans=[span], canonical_input=None)
        assert "sp_eh" in {a.span_id for a in validated.accepted}


# ===========================================================================
# Test 4: Wrong field detected
# ===========================================================================


class TestWrongFieldDetected:
    """Phase 1: annotations with wrong field for their semantic_role
    are now ACCEPTED with diagnostics (normalization corrects the field)."""

    def test_input_contract_with_wrong_field_accepted(self):
        ann = _make_annotation(
            span_id="sp_wf",
            field="behavior",  # should be "resources"
            semantic_role="input_contract",
            route_family="resource_contract",
            construct_target="RESOURCE_CONTRACT",
            slot_target="input",
            executable=False,
        )
        v = _validate([ann])
        assert "sp_wf" in {a.span_id for a in v.accepted}, (
            "Phase 1: known role with wrong field must be accepted"
        )
        assert len(v.structured_diagnostics) >= 1, (
            "Phase 1: diagnostic must be recorded for field mismatch"
        )


# ===========================================================================
# Test 5: Pre-enrichment does not reject for missing requiredness
# ===========================================================================


class TestPreEnrichmentSkipsRequiredness:
    """The validator must NOT reject resource contract annotations for
    missing requiredness — that metadata is injected later by
    _enrich_contract_requiredness()."""

    def test_input_contract_accepted_without_requiredness(self):
        ann = _make_annotation(
            span_id="sp_nr",
            field="resources",
            semantic_role="input_contract",
            route_family="resource_contract",
            construct_target="RESOURCE_CONTRACT",
            slot_target="input",
            executable=False,
            # No requiredness metadata — should still be accepted
        )
        v = _validate([ann])
        assert "sp_nr" in {a.span_id for a in v.accepted}, (
            "Pre-enrichment validator must not reject for missing requiredness"
        )

    def test_output_contract_accepted_without_requiredness(self):
        ann = _make_annotation(
            span_id="sp_or",
            field="resources",
            semantic_role="output_contract",
            route_family="resource_contract",
            construct_target="RESOURCE_CONTRACT",
            slot_target="output",
            executable=False,
        )
        v = _validate([ann])
        assert "sp_or" in {a.span_id for a in v.accepted}


# ===========================================================================
# Test 6: Post-enrichment requiredness finalizer
# ===========================================================================


class TestPostEnrichmentFinalizer:
    """finalize_requiredness() checks that resource contract annotations
    carry valid requiredness after _enrich_contract_requiredness()."""

    def test_missing_requiredness_detected(self):
        from nl2spl.ir.field_route_ir import RouteAnnotation
        from nl2spl.pipeline.stages.stage2_field_router_validator import (
            RouteRefinementValidator,
        )

        ann = RouteAnnotation(
            span_id="sp_mr",
            field="resources",
            semantic_role="input_contract",
            executable=False,
        )
        str_diags, struct_diags = RouteRefinementValidator.finalize_requiredness([ann])
        assert len(str_diags) >= 1
        assert "sp_mr" in str_diags[0]
        # Structured diagnostic
        assert len(struct_diags) >= 1
        d = struct_diags[0]
        assert d.kind == "annotation_missing_requiredness"
        assert d.span_id == "sp_mr"
        assert d.semantic_role == "input_contract"
        assert d.field_name == "requiredness"

    def test_valid_requiredness_accepted(self):
        from nl2spl.ir.field_route_ir import RouteAnnotation
        from nl2spl.pipeline.stages.stage2_field_router_validator import (
            RouteRefinementValidator,
        )

        ann = RouteAnnotation(
            span_id="sp_ok",
            field="resources",
            semantic_role="input_contract",
            executable=False,
        )
        ann.metadata["requiredness"] = "required"
        str_diags, struct_diags = RouteRefinementValidator.finalize_requiredness([ann])
        assert len(str_diags) == 0
        assert len(struct_diags) == 0

    def test_invalid_requiredness_value_detected(self):
        from nl2spl.ir.field_route_ir import RouteAnnotation
        from nl2spl.pipeline.stages.stage2_field_router_validator import (
            RouteRefinementValidator,
        )

        ann = RouteAnnotation(
            span_id="sp_iv",
            field="resources",
            semantic_role="output_contract",
            executable=False,
        )
        ann.metadata["requiredness"] = "always"
        str_diags, struct_diags = RouteRefinementValidator.finalize_requiredness([ann])
        assert len(str_diags) >= 1
        assert len(struct_diags) >= 1
        assert struct_diags[0].actual == "always"

    def test_unspecified_requiredness_accepted(self):
        from nl2spl.ir.field_route_ir import RouteAnnotation
        from nl2spl.pipeline.stages.stage2_field_router_validator import (
            RouteRefinementValidator,
        )

        ann = RouteAnnotation(
            span_id="sp_us",
            field="resources",
            semantic_role="input_contract",
            executable=False,
        )
        ann.metadata["requiredness"] = "unspecified"
        str_diags, struct_diags = RouteRefinementValidator.finalize_requiredness([ann])
        assert len(str_diags) == 0
        assert len(struct_diags) == 0

    def test_non_resource_role_skipped(self):
        from nl2spl.ir.field_route_ir import RouteAnnotation
        from nl2spl.pipeline.stages.stage2_field_router_validator import (
            RouteRefinementValidator,
        )

        ann = RouteAnnotation(
            span_id="sp_nr",
            field="behavior",
            semantic_role="process_step",
            executable=True,
        )
        str_diags, struct_diags = RouteRefinementValidator.finalize_requiredness([ann])
        assert len(str_diags) == 0
        assert len(struct_diags) == 0

    def test_finalizer_wired_into_execute_canonical(self):
        """ARC4: _execute_canonical() calls finalize_requiredness after
        _enrich_contract_requiredness(), so missing requiredness produces
        visible diagnostics in the Stage2 output."""
        from unittest.mock import MagicMock

        from nl2spl.canonical.compile_input import (
            CanonicalCompileInput,
            CompileHints,
            HardFacts,
            SemanticPacket,
        )
        from nl2spl.ir.span_ir import SpanIR
        from nl2spl.pipeline.stages.stage2_field_router import (
            FieldRouter,
        )

        router = FieldRouter(config=MagicMock(), client=MagicMock())
        packet = SemanticPacket(
            packet_id="p_1",
            source_section_id="sec_inputs",
            packet_type="runtime_input",
            text="customer name",
            modality="hint",
            compile_targets=[],
            required=None,
        )
        span = SpanIR(
            span_id="sp_input",
            text="customer name",
            source_section_id="sec_inputs",
            source_packet_id="p_1",
        )
        canonical = CanonicalCompileInput(
            source_schema="structural_nl",
            schema_version="1.0",
            raw_text="Inputs: customer name",
            raw_sections=[],
            semantic_packets=[packet],
            compile_hints=CompileHints(),
            hard_facts=HardFacts(),
        )

        routes, _ = router._execute_canonical([span], canonical)

        # String diagnostics
        req_diags = [
            d for d in routes.route_diagnostics
            if "requiredness" in d.lower()
        ]
        assert len(req_diags) >= 1, (
            f"Post-enrichment finalizer must produce requiredness diagnostic. "
            f"Got: {routes.route_diagnostics}"
        )

        # Structured diagnostics in output
        struct_diags = routes.structured_route_diagnostics
        req_struct = [
            d for d in struct_diags
            if d.get("kind") == "annotation_missing_requiredness"
        ]
        assert len(req_struct) >= 1, (
            f"Structured requiredness diagnostics must land in "
            f"structured_route_diagnostics. Got: {struct_diags}"
        )
        d = req_struct[0]
        assert d["span_id"] == "sp_input"
        assert d["semantic_role"] == "input_contract"
        assert d["field_name"] == "requiredness"


# ===========================================================================
# Test 7: Validator uses registry, not _ROLE_CONTRACT
# ===========================================================================


class TestValidatorUsesRegistry:
    """The validator now imports from ROLE_CONTRACT_REGISTRY."""

    def test_validator_imports_registry(self):
        import inspect
        from nl2spl.pipeline.stages import stage2_field_router_validator as m

        source = inspect.getsource(m)
        assert "ROLE_CONTRACT_REGISTRY" in source

    def test_validator_checks_against_registry(self):
        from nl2spl.pipeline.stages.stage2_field_router_validator import (
            RouteRefinementValidator,
        )
        assert hasattr(RouteRefinementValidator, "_check_against_registry")

    def test_check_against_registry_accepts_null_role(self):
        v = _make_validator()
        ann = _make_annotation(semantic_role=None)
        rej, diags = v._check_against_registry(ann)
        assert rej is None
        assert diags == []

    def test_check_against_registry_returns_structured_diagnostic(self):
        """Phase 1: known roles produce diagnostics without rejection.
        rej is None, but structured_diagnostics are populated."""
        v = _make_validator()
        ann = _make_annotation(
            span_id="sp_sd",
            field="domain",
            semantic_role="profile_domain",
            construct_target="RESOURCE_CONTRACT",
            slot_target="input",
        )
        rej, diags = v._check_against_registry(ann)
        assert rej is None, (
            "Phase 1: known role must NOT be rejected — rejection_reason is None"
        )
        assert len(diags) >= 1, (
            "Phase 1: structured diagnostics must be populated"
        )
        d = diags[0]
        assert d.kind == "annotation_invalid_construct_target_for_role"
        assert d.span_id == "sp_sd"
        assert d.semantic_role == "profile_domain"
        assert d.field_name == "construct_target"
        # Raw values, no repr() wrapping
        assert d.actual == "RESOURCE_CONTRACT", f"got {d.actual!r}"
        assert d.expected is None, f"got {d.expected!r}"
        # to_dict() is also clean
        dd = d.to_dict()
        assert dd["actual"] == "RESOURCE_CONTRACT"
        assert dd["expected"] is None


# ===========================================================================
# Test 8: Existing anti-fabrication checks preserved
# ===========================================================================


class TestAntiFabricationPreserved:
    """ARC4 must not remove existing anti-fabrication checks."""

    def test_handler_without_verb_rejected(self):
        ann = _make_annotation(
            span_id="sp_h",
            field="behavior",
            semantic_role="exception_handler_action",
            route_family="flow_relevant",
            construct_target="EXCEPTION_FLOW",
            slot_target="handler",
            executable=True,
        )
        from nl2spl.ir.span_ir import SpanIR
        span = SpanIR(span_id="sp_h", text="just a description with no action verb")
        from nl2spl.pipeline.stages.stage2_field_router_prompt import (
            RouteRefinementResult,
        )
        result = RouteRefinementResult(annotations=[ann])
        v = _make_validator()
        validated = v.validate(result, spans=[span], canonical_input=None)
        assert "sp_h" in {r.annotation.span_id for r in validated.rejected}

    def test_worker_candidate_without_worker_rejected(self):
        ann = _make_annotation(
            span_id="sp_w",
            field="behavior",
            semantic_role="worker_handoff_candidate",
            route_family="delegation_boundary",
            construct_target="WORKER_HANDOFF",
            slot_target="target",
            executable=False,
        )
        from nl2spl.ir.span_ir import SpanIR
        span = SpanIR(span_id="sp_w", text="an unrelated sentence about nothing")
        from nl2spl.pipeline.stages.stage2_field_router_prompt import (
            RouteRefinementResult,
        )
        result = RouteRefinementResult(annotations=[ann])
        v = _make_validator()
        validated = v.validate(result, spans=[span], canonical_input=None)
        assert "sp_w" in {r.annotation.span_id for r in validated.rejected}
