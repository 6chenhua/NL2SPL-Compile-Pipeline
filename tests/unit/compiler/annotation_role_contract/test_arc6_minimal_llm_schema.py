"""ARC6: Minimal LLM schema acceptance tests.

Verify that the Stage 2 LLM boundary accepts minimal responses
(span_id + semantic_role only) and correctly derives compiler-facing
fields via the canonical role contract.
"""

from __future__ import annotations


# ===========================================================================
# Test 1: Minimal LLM response accepted by parser
# ===========================================================================


class TestMinimalLLMResponseAcceptedByParser:
    """The parser must accept annotations with only span_id + semantic_role."""

    def test_minimal_annotation_parsed_without_diagnostics(self):
        from nl2spl.pipeline.stages.stage2_field_router_prompt import (
            parse_refinement_result,
        )

        data = {
            "annotations": [
                {"span_id": "s1", "semantic_role": "profile_domain"},
            ],
        }
        result = parse_refinement_result(data)
        assert len(result.annotations) == 1
        ann = result.annotations[0]
        assert ann.span_id == "s1"
        assert ann.semantic_role == "profile_domain"
        assert ann.field is None  # compiler fills in
        assert ann.executable is None  # compiler fills in
        assert ann.construct_target is None  # compiler fills in
        # No parse diagnostics for optional fields
        assert len(result.parse_diagnostics) == 0

    def test_minimal_annotation_with_reason_parsed(self):
        from nl2spl.pipeline.stages.stage2_field_router_prompt import (
            parse_refinement_result,
        )

        data = {
            "annotations": [
                {"span_id": "s2", "semantic_role": "failure_mode",
                 "primary": False, "reason": "Failure condition detected"},
            ],
        }
        result = parse_refinement_result(data)
        assert len(result.annotations) == 1
        ann = result.annotations[0]
        assert ann.semantic_role == "failure_mode"
        assert ann.primary is False
        assert ann.reason == "Failure condition detected"

    def test_multiple_minimal_annotations_parsed(self):
        from nl2spl.pipeline.stages.stage2_field_router_prompt import (
            parse_refinement_result,
        )

        data = {
            "annotations": [
                {"span_id": "s1", "semantic_role": "input_contract"},
                {"span_id": "s2", "semantic_role": "output_contract"},
                {"span_id": "s3", "semantic_role": "process_step"},
            ],
        }
        result = parse_refinement_result(data)
        assert len(result.annotations) == 3
        roles = {a.semantic_role for a in result.annotations}
        assert roles == {"input_contract", "output_contract", "process_step"}


# ===========================================================================
# Test 2: Minimal LLM response accepted by validator
# ===========================================================================


class TestMinimalAnnotationAcceptedByValidator:
    """The validator must accept annotations with only semantic_role
    (missing field/executable are OK — compiler fills them in)."""

    def test_minimal_annotation_accepted_by_validator(self):
        from nl2spl.ir.span_ir import SpanIR
        from nl2spl.pipeline.stages.stage2_field_router_prompt import (
            RefinedAnnotation,
            RouteRefinementResult,
        )
        from nl2spl.pipeline.stages.stage2_field_router_validator import (
            RouteRefinementValidator,
        )

        ann = RefinedAnnotation(
            span_id="sp_min",
            semantic_role="profile_domain",
            # No field, no executable, no construct_target, no slot_target
        )
        llm_result = RouteRefinementResult(annotations=[ann])
        span = SpanIR(span_id="sp_min", text="Profile description")

        validator = RouteRefinementValidator()
        validated = validator.validate(llm_result, spans=[span], canonical_input=None)

        assert "sp_min" in {a.span_id for a in validated.accepted}, (
            f"Minimal annotation must be accepted. "
            f"Rejected: {[(r.annotation.span_id, r.reason[:80]) for r in validated.rejected]}"
        )

    def test_minimal_input_contract_accepted(self):
        from nl2spl.ir.span_ir import SpanIR
        from nl2spl.pipeline.stages.stage2_field_router_prompt import (
            RefinedAnnotation,
            RouteRefinementResult,
        )
        from nl2spl.pipeline.stages.stage2_field_router_validator import (
            RouteRefinementValidator,
        )

        ann = RefinedAnnotation(
            span_id="sp_ic",
            semantic_role="input_contract",
        )
        llm_result = RouteRefinementResult(annotations=[ann])
        span = SpanIR(span_id="sp_ic", text="customer name")

        validator = RouteRefinementValidator()
        validated = validator.validate(llm_result, spans=[span], canonical_input=None)
        assert "sp_ic" in {a.span_id for a in validated.accepted}

    def test_minimal_process_step_accepted(self):
        from nl2spl.ir.span_ir import SpanIR
        from nl2spl.pipeline.stages.stage2_field_router_prompt import (
            RefinedAnnotation,
            RouteRefinementResult,
        )
        from nl2spl.pipeline.stages.stage2_field_router_validator import (
            RouteRefinementValidator,
        )

        ann = RefinedAnnotation(
            span_id="sp_ps",
            semantic_role="process_step",
        )
        llm_result = RouteRefinementResult(annotations=[ann])
        span = SpanIR(span_id="sp_ps", text="process the data")

        validator = RouteRefinementValidator()
        validated = validator.validate(llm_result, spans=[span], canonical_input=None)
        assert "sp_ps" in {a.span_id for a in validated.accepted}


# ===========================================================================
# Test 3: Normalization derives correct compiler fields from minimal LLM
# ===========================================================================


class TestNormalizationFromMinimalLLM:
    """normalize_annotation_from_role() must derive all compiler-facing
    fields from the canonical role contract when given only semantic_role."""

    def test_profile_domain_gets_correct_fields(self):
        from nl2spl.compiler.annotation_role_contract.normalize import (
            normalize_annotation_from_role,
        )

        result = normalize_annotation_from_role(
            span_id="sp_pd",
            semantic_role="profile_domain",
        )

        ann = result.annotation
        assert ann.field == "domain"
        assert ann.route_family == "profile"
        assert ann.construct_target is None
        assert ann.slot_target is None
        assert ann.executable is False

    def test_input_contract_gets_correct_fields(self):
        from nl2spl.compiler.annotation_role_contract.normalize import (
            normalize_annotation_from_role,
        )

        result = normalize_annotation_from_role(
            span_id="sp_ic",
            semantic_role="input_contract",
        )

        ann = result.annotation
        assert ann.field == "resources"
        assert ann.route_family == "resource_contract"
        assert ann.construct_target == "RESOURCE_CONTRACT"
        assert ann.slot_target == "input"
        assert ann.executable is False

    def test_failure_mode_gets_correct_fields(self):
        from nl2spl.compiler.annotation_role_contract.normalize import (
            normalize_annotation_from_role,
        )

        result = normalize_annotation_from_role(
            span_id="sp_fm",
            semantic_role="failure_mode",
        )

        ann = result.annotation
        assert ann.field == "behavior"
        assert ann.route_family == "flow_relevant"
        assert ann.construct_target == "EXCEPTION_FLOW"
        assert ann.slot_target == "condition"
        assert ann.executable is False

    def test_process_step_gets_correct_fields(self):
        from nl2spl.compiler.annotation_role_contract.normalize import (
            normalize_annotation_from_role,
        )

        result = normalize_annotation_from_role(
            span_id="sp_ps",
            semantic_role="process_step",
        )

        ann = result.annotation
        assert ann.field == "behavior"
        assert ann.route_family == "flow_relevant"
        assert ann.executable is True
        assert ann.construct_target is None
        assert ann.slot_target is None


# ===========================================================================
# Test 4: Old full-schema response still accepted and corrected
# ===========================================================================


class TestOldSchemaResponseStillNormalized:
    """LLM responses with old full-schema fields (field, construct_target,
    slot_target, executable) are still accepted but corrected against the
    role contract, with diagnostics for corrected fields."""

    def test_old_schema_with_wrong_fields_is_normalized(self):
        from nl2spl.compiler.annotation_role_contract.normalize import (
            normalize_annotation_from_role,
        )

        result = normalize_annotation_from_role(
            span_id="sp_old",
            semantic_role="profile_domain",
            raw_field="behavior",  # wrong!
            raw_construct_target="RESOURCE_CONTRACT",  # wrong!
            raw_slot_target="input",  # wrong!
            raw_executable=True,  # wrong!
        )

        ann = result.annotation
        # Contract-correct fields
        assert ann.field == "domain"
        assert ann.construct_target is None
        assert ann.slot_target is None
        assert ann.executable is False
        # Diagnostics for all corrected fields
        assert len(result.diagnostics) >= 3

    def test_old_schema_with_correct_fields_accepted_cleanly(self):
        from nl2spl.compiler.annotation_role_contract.normalize import (
            normalize_annotation_from_role,
        )

        result = normalize_annotation_from_role(
            span_id="sp_correct",
            semantic_role="input_contract",
            raw_field="resources",  # correct
            raw_executable=False,  # correct
        )

        ann = result.annotation
        assert ann.field == "resources"
        assert ann.executable is False
        # No corrections needed
        assert len(result.diagnostics) == 0


# ===========================================================================
# Test 5: Merge path accepts minimal LLM annotation
# ===========================================================================


class TestMergePathWithMinimalLLM:
    """_normalize_annotation_contract() in the merge path accepts minimal
    annotations and fills in compiler fields from the registry."""

    def test_merge_normalize_fills_missing_fields(self):
        from nl2spl.pipeline.stages.stage2_field_router import FieldRouter

        diagnostics: list[str] = []
        field, role, rf, ct, st, exe = FieldRouter._normalize_annotation_contract(
            span_id="sp_min",
            field=None,          # missing — compiler fills
            semantic_role="profile_domain",
            route_family=None,   # missing — compiler fills
            construct_target=None,
            slot_target=None,
            executable=None,     # missing — compiler fills
            diagnostics=diagnostics,
        )

        assert field == "domain", f"Expected domain, got {field}"
        assert role == "profile_domain"
        assert rf == "profile"
        assert ct is None
        assert st is None
        assert exe is False


# ===========================================================================
# Test 6: Prompt payload is minimal
# ===========================================================================


class TestPromptPayloadIsMinimal:
    """The allowed_schema in the LLM prompt payload must only carry
    semantic_roles — no compiler-facing fields."""

    def test_prompt_allowed_schema_only_has_semantic_roles(self):
        from nl2spl.pipeline.stages.stage2_field_router_prompt import (
            build_adapter_guided_user_prompt,
        )
        from nl2spl.ir.span_ir import SpanIR

        # Call with empty inputs — just check the payload structure
        import json
        payload = build_adapter_guided_user_prompt(
            spans=[SpanIR(span_id="s1", text="test")],
            canonical_input=None,  # type: ignore
            structural_priors=[],
            deterministic_annotations=[],
        )
        parsed = json.loads(payload)
        schema = parsed["allowed_schema"]
        assert "role_policy" in parsed

        # Only semantic_roles must be present
        assert "semantic_roles" in schema
        assert "fields" not in schema, "ARC6: fields must not be in LLM allowed_schema"
        assert "construct_targets" not in schema, "ARC6: construct_targets must not be in LLM allowed_schema"
        assert "slot_targets" not in schema, "ARC6: slot_targets must not be in LLM allowed_schema"
        assert "non_executable_roles" not in schema, "ARC6: non_executable_roles must not be in LLM allowed_schema"
        assert "executable_roles" not in schema, "ARC6: executable_roles must not be in LLM allowed_schema"
