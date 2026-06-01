"""Unit / snapshot tests for IRSDrivenPromptBuilder."""

import pytest

from nl2spl.compiler.construct_registry import (
    ConstructIRS,
    SlotSpec,
    SPLConstructRegistry,
)
from nl2spl.compiler.irs_prompt_builder import IRSDrivenPromptBuilder

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def registry() -> SPLConstructRegistry:
    return SPLConstructRegistry.default()


@pytest.fixture
def builder(registry: SPLConstructRegistry) -> IRSDrivenPromptBuilder:
    return IRSDrivenPromptBuilder(registry)


# ---------------------------------------------------------------------------
# Stage mappings
# ---------------------------------------------------------------------------

class TestStageMappings:
    def test_stage4_maps_to_exception_flow(self):
        mapping = IRSDrivenPromptBuilder(
            SPLConstructRegistry.default()
        ).stage_constructs
        assert mapping["stage4"] == ["EXCEPTION_FLOW"]

    def test_stage7_maps_to_all_command_constructs(self):
        mapping = IRSDrivenPromptBuilder(
            SPLConstructRegistry.default()
        ).stage_constructs
        assert "GENERAL_COMMAND" in mapping["stage7"]
        assert "REQUEST_INPUT" in mapping["stage7"]
        assert "CALL_API" in mapping["stage7"]
        assert "INVOKE_WORKER" in mapping["stage7"]
        assert len(mapping["stage7"]) == 4

    def test_stage9_5_maps_to_output_and_worker_constructs(self):
        mapping = IRSDrivenPromptBuilder(
            SPLConstructRegistry.default()
        ).stage_constructs
        assert "REQUIRED_OUTPUT" in mapping["stage9_5"]
        assert "CHILD_WORKER" in mapping["stage9_5"]
        assert "WORKER_CANDIDATE" in mapping["stage9_5"]
        assert len(mapping["stage9_5"]) == 3

    def test_stage3_5_stages_not_in_injection_map(self):
        mapping = IRSDrivenPromptBuilder(
            SPLConstructRegistry.default()
        ).stage_constructs
        assert "stage3_5" not in mapping
        assert "stage3_5a" not in mapping
        assert "stage3_5b" not in mapping

    def test_stage3_5_render_empty(self, builder):
        assert builder.render_for_stage("stage3_5") == ""

    def test_stage3_5a_render_empty(self, builder):
        assert builder.render_for_stage("stage3_5a") == ""

    def test_stage3_5b_render_empty(self, builder):
        assert builder.render_for_stage("stage3_5b") == ""


# ---------------------------------------------------------------------------
# Snapshot: determinism
# ---------------------------------------------------------------------------

class TestDeterminism:
    def test_stage4_output_is_identical_across_calls(self, builder):
        a = builder.render_for_stage("stage4")
        b = builder.render_for_stage("stage4")
        assert a == b

    def test_stage7_output_is_identical_across_calls(self, builder):
        a = builder.render_for_stage("stage7")
        b = builder.render_for_stage("stage7")
        assert a == b

    def test_different_builders_same_registry_produce_identical_output(self):
        a = IRSDrivenPromptBuilder(SPLConstructRegistry.default())
        b = IRSDrivenPromptBuilder(SPLConstructRegistry.default())
        assert a.render_for_stage("stage4") == b.render_for_stage("stage4")


# ---------------------------------------------------------------------------
# Unknown stage
# ---------------------------------------------------------------------------

class TestUnknownStage:
    def test_unknown_stage_returns_empty(self, builder):
        result = builder.render_for_stage("nonexistent_stage")
        assert result == ""

    def test_empty_string_stage_returns_empty(self, builder):
        result = builder.render_for_stage("")
        assert result == ""


# ---------------------------------------------------------------------------
# Stage 4: EXCEPTION_FLOW checklist content
# ---------------------------------------------------------------------------

class TestStage4Checklist:
    @pytest.fixture(autouse=True)
    def _setup(self, builder):
        self.text = builder.render_for_stage("stage4")

    def test_includes_construct_header(self):
        assert "CONSTRUCT: EXCEPTION_FLOW" in self.text

    def test_includes_existence_policy(self):
        assert "source_signal_required" in self.text

    def test_includes_partial_rendering_rule(self):
        assert "**Partial rendering:** ALLOWED" in self.text

    def test_includes_source_signals(self):
        assert "failure_mode" in self.text
        assert "exception_condition" in self.text

    def test_includes_condition_slot(self):
        assert "condition" in self.text
        assert "syntax_required" in self.text
        assert "required_for_partial" in self.text

    def test_includes_handler_action_slot(self):
        assert "handler_action" in self.text
        assert "renderable_without" in self.text
        assert "missing_handler" in self.text

    def test_includes_missing_handler_diagnostic(self):
        assert "missing_handler" in self.text

    def test_includes_no_failure_signal_rule(self):
        assert "No failure signal" in self.text
        assert "do NOT generate" in self.text

    def test_includes_concrete_failure_condition_rule(self):
        assert "Concrete failure condition" in self.text
        assert "partial EXCEPTION_FLOW" in self.text

    def test_includes_handler_action_guidance(self):
        assert "Do NOT invent handler actions" in self.text
        assert "missing_handler is diagnosed later" in self.text

    def test_includes_stage95_authority_note(self):
        assert "Stage 9.5" in self.text
        assert "Stage 7 will decide" in self.text

    def test_includes_vague_failure_rule(self):
        assert "Vague" in self.text
        assert "type_or_contract_ambiguity" in self.text


# ---------------------------------------------------------------------------
# Stage 7: command constructs checklist content
# ---------------------------------------------------------------------------

class TestStage7Checklist:
    @pytest.fixture(autouse=True)
    def _setup(self, builder):
        self.text = builder.render_for_stage("stage7")

    def test_includes_all_command_constructs(self):
        assert "CONSTRUCT: GENERAL_COMMAND" in self.text
        assert "CONSTRUCT: REQUEST_INPUT" in self.text
        assert "CONSTRUCT: CALL_API" in self.text
        assert "CONSTRUCT: INVOKE_WORKER" in self.text
        # Must NOT include constructs that don't belong to Stage 7
        assert "CONSTRUCT: EXCEPTION_FLOW" not in self.text
        assert "CONSTRUCT: REQUIRED_OUTPUT" not in self.text

    def test_includes_general_command_source_evidence_rule(self):
        assert "GENERAL_COMMAND requires source evidence" in self.text

    def test_includes_request_input_ask_signal_rule(self):
        assert "REQUEST_INPUT requires explicit ask" in self.text

    def test_includes_call_api_requires_named_api_and_executable_call(self):
        assert "CALL_API requires named API" in self.text
        assert "executable call action" in self.text

    def test_includes_invoke_worker_requires_accepted_handoff(self):
        assert "INVOKE_WORKER requires an accepted handoff" in self.text

    def test_includes_suggested_fix_rule(self):
        assert "suggested fix" in self.text.lower()
        assert "assumption" in self.text.lower()
        assert "NOT an executable StepIR" in self.text

    def test_general_command_includes_source_evidence_slot(self):
        assert "source_evidence" in self.text
        assert "assumed_command_not_renderable" in self.text

    def test_call_api_includes_call_action_slot(self):
        assert "call_action" in self.text

    def test_call_api_distinguishes_integration_mention(self):
        """call_action slot notes must surface the mention-vs-evidence distinction."""
        assert "call_action" in self.text
        assert "integration *mention*" in self.text
        assert "executable call evidence" in self.text

    def test_call_api_source_signals_exclude_context_mentions(self):
        """§15.6: source_repository must not appear as CALL_API source signal."""
        assert "source_repository" not in self.text
        assert "external_system" not in self.text

    def test_call_api_integration_evidence_excludes_repository(self):
        """§15.6: repository/source_repository/external_system absent case-insensitive."""
        lower = self.text.lower()
        assert "repository" not in lower
        assert "source_repository" not in lower
        assert "external_system" not in lower

    def test_call_api_integration_evidence_includes_ref_kinds(self):
        """integration_evidence.evidence_kinds uses _ref suffix variants."""
        assert "api_ref" in self.text
        assert "tool_ref" in self.text
        assert "connector_ref" in self.text
        assert "integration_ref" in self.text


# ---------------------------------------------------------------------------
# Stage 9.5 checklist content
# ---------------------------------------------------------------------------

class TestStage95Checklist:
    @pytest.fixture(autouse=True)
    def _setup(self, builder):
        self.text = builder.render_for_stage("stage9_5")

    def test_includes_required_output(self):
        assert "CONSTRUCT: REQUIRED_OUTPUT" in self.text

    def test_includes_child_worker(self):
        assert "CONSTRUCT: CHILD_WORKER" in self.text

    def test_includes_worker_candidate(self):
        assert "CONSTRUCT: WORKER_CANDIDATE" in self.text

    def test_does_not_include_exception_flow(self):
        assert "EXCEPTION_FLOW" not in self.text

    def test_required_output_includes_producer_slot(self):
        assert "producer" in self.text
        assert "missing_output_producer" in self.text

    def test_child_worker_includes_contract_slots(self):
        assert "input_contract" in self.text
        assert "output_contract" in self.text
        assert "invocation_point" in self.text
        assert "result_handoff" in self.text

    def test_worker_candidate_has_identification_slots(self):
        """WORKER_CANDIDATE has slots for identifying the candidate boundary"""
        assert "responsibility" in self.text
        assert "delegation_signal" in self.text
        assert "source_evidence" in self.text

    def test_worker_promotion_exists_in_registry(self):
        """WORKER_PROMOTION construct exists in registry with promotion slots"""
        # WORKER_PROMOTION is an analysis construct, not used in stage prompts
        # but it should exist in the registry
        registry = SPLConstructRegistry.default()
        assert registry.has("WORKER_PROMOTION")
        
        irs = registry.get("WORKER_PROMOTION")
        slot_names = [s.slot_name for s in irs.slots]
        assert "promotion_input_contract" in slot_names
        assert "promotion_output_contract" in slot_names
        assert "promotion_invocation_point" in slot_names
        assert "promotion_result_handoff" in slot_names


# ---------------------------------------------------------------------------
# Registry-change -> prompt-change linkage
# ---------------------------------------------------------------------------

class TestRegistryPromptLinkage:
    """A construct rule change in Phase 1 automatically affects prompt text."""

    def test_adding_slot_to_exception_flow_appears_in_stage4(self):
        registry = SPLConstructRegistry.default()
        irs = registry.get("EXCEPTION_FLOW")
        irs.slots.append(
            SlotSpec(
                slot_name="post_mvp_slot",
                required_for_complete=False,
                notes="Added in test to verify registry→prompt linkage.",
            )
        )
        builder = IRSDrivenPromptBuilder(registry)
        output = builder.render_for_stage("stage4")
        assert "post_mvp_slot" in output

    def test_changing_existence_policy_appears_in_output(self):
        registry = SPLConstructRegistry.default()
        irs = registry.get("EXCEPTION_FLOW")
        irs.existence_policy = "compiler_default_allowed"
        builder = IRSDrivenPromptBuilder(registry)
        output = builder.render_for_stage("stage4")
        assert "compiler_default_allowed" in output


# ---------------------------------------------------------------------------
# render_construct_checklist
# ---------------------------------------------------------------------------

class TestRenderConstructChecklist:
    def test_includes_construct_type_and_description(self, builder, registry):
        irs = registry.get("EXCEPTION_FLOW")
        text = builder.render_construct_checklist(irs)
        assert "EXCEPTION_FLOW" in text

    def test_includes_no_demand_behavior(self, builder, registry):
        irs = registry.get("WORKER_CANDIDATE")
        text = builder.render_construct_checklist(irs)
        assert "do_not_generate" in text

    def test_slot_with_no_tags_renders_cleanly(self, builder):
        irs = ConstructIRS(
            construct_type="MINIMAL",
            existence_policy="source_signal_required",
            source_signals=["signal_x"],
            slots=[SlotSpec(slot_name="bare_slot", can_be_suggested=False)],
        )
        text = builder.render_construct_checklist(irs)
        assert "bare_slot" in text
        # No tags → no brackets
        assert "[" not in text


# ---------------------------------------------------------------------------
# Snapshot verification (deterministic format)
# ---------------------------------------------------------------------------

class TestSnapshotFormat:
    def test_stage4_snapshot_lines(self, builder):
        text = builder.render_for_stage("stage4")
        lines = text.split("\n")
        assert lines[0].startswith("## IRS-Driven Construct Checklist")

    def test_stage7_snapshot_lines(self, builder):
        text = builder.render_for_stage("stage7")
        lines = text.split("\n")
        assert lines[0].startswith("## IRS-Driven Construct Checklist")

    def test_construct_checklist_starts_with_header(self, builder, registry):
        text = builder.render_construct_checklist(registry.get("CALL_API"))
        assert text.startswith("### CONSTRUCT:")

    def test_stage4_output_does_not_exceed_reasonable_size(self, builder):
        text = builder.render_for_stage("stage4")
        # Should be under 3000 chars for a single-construct checklist
        assert len(text) < 3000

    def test_stage7_output_does_not_exceed_reasonable_size(self, builder):
        text = builder.render_for_stage("stage7")
        # Four constructs — should be under 8000 chars
        assert len(text) < 8000
