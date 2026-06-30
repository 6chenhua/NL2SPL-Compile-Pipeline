"""Unit tests for SPLConstructRegistry and ConstructIRS."""

import pytest

from nl2spl.compiler.construct_registry import (
    ConstructIRS,
    ConstructSatisfactionReport,
    SlotSatisfaction,
    SlotSpec,
    SPLConstructRegistry,
)

# ---------------------------------------------------------------------------
# default() registry shape
# ---------------------------------------------------------------------------

class TestDefaultRegistry:
    def test_contains_all_initial_constructs(self):
        registry = SPLConstructRegistry.default()
        expected = {
            "EXCEPTION_FLOW",
            "REQUIRED_OUTPUT",
            "RESOURCE_CONTRACT_DEMAND",
            "GENERAL_COMMAND",
            "REQUEST_INPUT",
            "CALL_API",
            "INVOKE_WORKER",
            "CHILD_WORKER",
            "WORKER_CANDIDATE",
            "WORKER_PROMOTION",
            "WORKER_HANDOFF",
            "API_DECLARATION",
        }
        assert set(registry.list_constructs()) == expected

    def test_default_is_deterministic(self):
        a = SPLConstructRegistry.default()
        b = SPLConstructRegistry.default()
        assert a.list_constructs() == b.list_constructs()

    @pytest.mark.parametrize("construct_type", [
        "EXCEPTION_FLOW",
        "REQUIRED_OUTPUT",
        "GENERAL_COMMAND",
        "REQUEST_INPUT",
        "CALL_API",
        "INVOKE_WORKER",
        "CHILD_WORKER",
        "WORKER_CANDIDATE",
    ])
    def test_every_construct_is_retrievable(self, construct_type):
        registry = SPLConstructRegistry.default()
        irs = registry.get(construct_type)
        assert irs.construct_type == construct_type

    def test_has_returns_true_for_known(self):
        registry = SPLConstructRegistry.default()
        assert registry.has("EXCEPTION_FLOW") is True

    def test_has_returns_false_for_unknown(self):
        registry = SPLConstructRegistry.default()
        assert registry.has("NO_SUCH_CONSTRUCT") is False

    def test_get_unknown_raises_key_error(self):
        registry = SPLConstructRegistry.default()
        with pytest.raises(KeyError, match="NO_SUCH"):
            registry.get("NO_SUCH_CONSTRUCT")

    def test_register_custom_construct(self):
        registry = SPLConstructRegistry()
        registry.register(ConstructIRS(
            construct_type="CUSTOM",
            existence_policy="compiler_default_allowed",
            source_signals=["custom_signal"],
            slots=[],
        ))
        assert registry.has("CUSTOM")
        assert registry.get("CUSTOM").construct_type == "CUSTOM"


# ---------------------------------------------------------------------------
# EXCEPTION_FLOW
# ---------------------------------------------------------------------------

class TestExceptionFlowIRS:
    @pytest.fixture(autouse=True)
    def _setup(self):
        self.irs = SPLConstructRegistry.default().get("EXCEPTION_FLOW")

    def test_condition_is_syntax_required(self):
        slot = self.irs.get_slot("condition")
        assert slot is not None
        assert slot.syntax_required is True

    def test_condition_is_required_for_partial(self):
        slot = self.irs.get_slot("condition")
        assert slot.required_for_partial is True

    def test_handler_action_renderable_without(self):
        slot = self.irs.get_slot("handler_action")
        assert slot is not None
        assert slot.renderable_without is True
        assert slot.missing_diagnostic == "missing_handler"

    def test_handler_action_is_not_required_for_partial(self):
        slot = self.irs.get_slot("handler_action")
        assert slot.required_for_partial is False

    def test_handler_action_is_required_for_complete(self):
        slot = self.irs.get_slot("handler_action")
        assert slot.required_for_complete is True

    def test_allows_partial_rendering(self):
        assert self.irs.partial_rendering_allowed is True

    def test_exists_only_on_source_signal(self):
        assert self.irs.existence_policy == "source_signal_required"

    def test_failure_signals_are_registered(self):
        assert "failure_mode" in self.irs.source_signals
        assert "exception_condition" in self.irs.source_signals

    def test_required_for_partial_slots(self):
        partial_slots = self.irs.required_slots_for_partial()
        names = {s.slot_name for s in partial_slots}
        assert "condition" in names
        assert "handler_action" not in names  # not needed for partial

    def test_required_for_complete_slots(self):
        complete_slots = self.irs.required_slots_for_complete()
        names = {s.slot_name for s in complete_slots}
        assert "condition" in names
        assert "handler_action" in names


# ---------------------------------------------------------------------------
# REQUIRED_OUTPUT
# ---------------------------------------------------------------------------

class TestRequiredOutputIRS:
    @pytest.fixture(autouse=True)
    def _setup(self):
        self.irs = SPLConstructRegistry.default().get("REQUIRED_OUTPUT")

    def test_output_type_not_syntax_required(self):
        slot = self.irs.get_slot("output_type")
        assert slot.syntax_required is False

    def test_output_type_not_required_for_partial(self):
        slot = self.irs.get_slot("output_type")
        assert slot.required_for_partial is False

    def test_output_type_not_required_for_complete(self):
        slot = self.irs.get_slot("output_type")
        assert slot.required_for_complete is False

    def test_output_type_renderable_without(self):
        slot = self.irs.get_slot("output_type")
        assert slot.renderable_without is True

    def test_output_type_can_be_inferred(self):
        slot = self.irs.get_slot("output_type")
        assert slot.can_be_inferred is True

    def test_producer_is_renderable_without(self):
        slot = self.irs.get_slot("producer")
        assert slot is not None
        assert slot.renderable_without is True
        assert slot.missing_diagnostic == "missing_output_producer"

    def test_producer_is_not_syntax_required(self):
        slot = self.irs.get_slot("producer")
        assert slot.syntax_required is False

    def test_allows_partial_rendering(self):
        assert self.irs.partial_rendering_allowed is True


# ---------------------------------------------------------------------------
# GENERAL_COMMAND
# ---------------------------------------------------------------------------

class TestGeneralCommandIRS:
    @pytest.fixture(autouse=True)
    def _setup(self):
        self.irs = SPLConstructRegistry.default().get("GENERAL_COMMAND")

    def test_source_evidence_is_not_renderable_without(self):
        slot = self.irs.get_slot("source_evidence")
        assert slot is not None
        assert slot.renderable_without is False
        assert slot.missing_diagnostic == "assumed_command_not_renderable"

    def test_source_evidence_is_required_for_complete(self):
        slot = self.irs.get_slot("source_evidence")
        assert slot.required_for_complete is True

    def test_no_partial_rendering(self):
        assert self.irs.partial_rendering_allowed is False


# ---------------------------------------------------------------------------
# REQUEST_INPUT
# ---------------------------------------------------------------------------

class TestRequestInputIRS:
    @pytest.fixture(autouse=True)
    def _setup(self):
        self.irs = SPLConstructRegistry.default().get("REQUEST_INPUT")

    def test_requires_ask_signal(self):
        assert "ask_user" in self.irs.source_signals
        assert "request_clarification" in self.irs.source_signals
        assert "prompt_user" in self.irs.source_signals

    def test_value_target_is_required_for_complete(self):
        slot = self.irs.get_slot("value_target")
        assert slot is not None
        assert slot.required_for_complete is True
        assert slot.missing_diagnostic == "type_or_contract_ambiguity"

    def test_no_partial_rendering(self):
        assert self.irs.partial_rendering_allowed is False


# ---------------------------------------------------------------------------
# CALL_API
# ---------------------------------------------------------------------------

class TestCallAPIIRS:
    @pytest.fixture(autouse=True)
    def _setup(self):
        self.irs = SPLConstructRegistry.default().get("CALL_API")

    def test_call_action_distinguishes_mention_from_evidence(self):
        slot = self.irs.get_slot("call_action")
        assert slot is not None
        assert slot.required_for_complete is True
        assert slot.renderable_without is False
        assert "call_action" in slot.evidence_kinds

    def test_api_name_is_syntax_required(self):
        slot = self.irs.get_slot("api_name")
        assert slot.syntax_required is True

    def test_integration_evidence_is_not_required_for_complete(self):
        slot = self.irs.get_slot("integration_evidence")
        assert slot.required_for_complete is False

    def test_declared_api_ref_is_required_for_complete(self):
        slot = self.irs.get_slot("declared_api_ref")
        assert slot is not None
        assert slot.required_for_complete is True

    def test_response_binding_is_not_required_for_complete(self):
        slot = self.irs.get_slot("response_binding")
        assert slot.required_for_complete is False

    def test_no_partial_rendering(self):
        assert self.irs.partial_rendering_allowed is False

    def test_source_signals_exclude_context_mentions(self):
        assert self.irs.source_signals == [
            "api_call_action",
            "tool_call_action",
            "connector_action",
        ]

    def test_source_signals_do_not_include_mention_signals(self):
        assert "source_repository" not in self.irs.source_signals
        assert "external_system" not in self.irs.source_signals
        assert "api" not in self.irs.source_signals
        assert "tool" not in self.irs.source_signals

    def test_integration_evidence_kinds_exclude_context_mentions(self):
        slot = self.irs.get_slot("integration_evidence")
        assert slot is not None
        assert "repository" not in slot.evidence_kinds
        assert "connector" not in slot.evidence_kinds
        assert "tool" not in slot.evidence_kinds

    def test_integration_evidence_kinds_use_ref_suffix(self):
        slot = self.irs.get_slot("integration_evidence")
        assert "api_ref" in slot.evidence_kinds
        assert "tool_ref" in slot.evidence_kinds
        assert "connector_ref" in slot.evidence_kinds
        assert "integration_ref" in slot.evidence_kinds

    def test_integration_evidence_has_context_note(self):
        slot = self.irs.get_slot("integration_evidence")
        assert slot.notes is not None
        assert "Compatibility alias slot" in slot.notes


# ---------------------------------------------------------------------------
# INVOKE_WORKER
# ---------------------------------------------------------------------------

class TestInvokeWorkerIRS:
    @pytest.fixture(autouse=True)
    def _setup(self):
        self.irs = SPLConstructRegistry.default().get("INVOKE_WORKER")

    def test_requires_accepted_handoff(self):
        assert "accepted_handoff" in self.irs.source_signals

    def test_target_worker_is_required_for_complete(self):
        slot = self.irs.get_slot("target_worker")
        assert slot.required_for_complete is True

    def test_input_bindings_are_required_for_complete(self):
        slot = self.irs.get_slot("input_bindings")
        assert slot.required_for_complete is True

    def test_output_bindings_are_required_for_complete(self):
        slot = self.irs.get_slot("output_bindings")
        assert slot.required_for_complete is True


# ---------------------------------------------------------------------------
# CHILD_WORKER vs WORKER_CANDIDATE
# ---------------------------------------------------------------------------

class TestWorkerCandidateVsChildWorker:
    @pytest.fixture(autouse=True)
    def _setup(self):
        self.registry = SPLConstructRegistry.default()
        self.child = self.registry.get("CHILD_WORKER")
        self.candidate = self.registry.get("WORKER_CANDIDATE")

    def test_are_separate_constructs(self):
        assert self.child.construct_type == "CHILD_WORKER"
        assert self.candidate.construct_type == "WORKER_CANDIDATE"

    def test_candidate_is_not_partial_rendering(self):
        assert self.candidate.partial_rendering_allowed is False

    def test_candidate_does_not_generate_on_no_demand(self):
        assert self.candidate.no_demand_behavior == "do_not_generate"

    def test_candidate_source_signals_include_optional_mentions(self):
        assert "optional_subtask" in self.candidate.source_signals
        assert "template_matching" in self.candidate.source_signals
        assert "source_gathering" in self.candidate.source_signals

    def test_child_worker_requires_worker_boundary_signal(self):
        assert "worker_boundary" in self.child.source_signals

    def test_child_worker_responsibility_is_required_for_partial(self):
        slot = self.child.get_slot("responsibility")
        assert slot.required_for_partial is True

    def test_child_worker_incomplete_slots_render_partial_skeleton(self):
        for name in ("input_contract", "output_contract", "invocation_point", "result_handoff"):
            slot = self.child.get_slot(name)
            assert slot is not None, f"Missing slot {name}"
            assert slot.required_for_partial is False
            assert slot.required_for_complete is True
            assert slot.renderable_without is True


# ---------------------------------------------------------------------------
# SlotSpec
# ---------------------------------------------------------------------------

class TestSlotSpec:
    def test_defaults(self):
        slot = SlotSpec(slot_name="test")
        assert slot.syntax_required is False
        assert slot.required_for_partial is False
        assert slot.required_for_complete is False
        assert slot.renderable_without is False
        assert slot.evidence_kinds == []
        assert slot.missing_diagnostic is None
        assert slot.can_be_inferred is False
        assert slot.can_be_suggested is True


# ---------------------------------------------------------------------------
# ConstructIRS helpers
# ---------------------------------------------------------------------------

class TestConstructIRSHelpers:
    @pytest.fixture(autouse=True)
    def _setup(self):
        self.irs = ConstructIRS(
            construct_type="TEST",
            existence_policy="source_signal_required",
            source_signals=["signal_a"],
            slots=[
                SlotSpec(slot_name="a", required_for_partial=True),
                SlotSpec(slot_name="b", required_for_complete=True),
                SlotSpec(slot_name="c"),
            ],
        )

    def test_get_slot_existing(self):
        assert self.irs.get_slot("a") is not None

    def test_get_slot_missing(self):
        assert self.irs.get_slot("z") is None

    def test_required_slots_for_partial(self):
        names = {s.slot_name for s in self.irs.required_slots_for_partial()}
        assert names == {"a"}

    def test_required_slots_for_complete(self):
        names = {s.slot_name for s in self.irs.required_slots_for_complete()}
        assert names == {"b"}


# ---------------------------------------------------------------------------
# SlotSatisfaction / ConstructSatisfactionReport
# ---------------------------------------------------------------------------

class TestSlotSatisfaction:
    def test_default_status_is_required(self):
        """SlotSatisfaction requires explicit status — ensure construction works."""
        sat = SlotSatisfaction(slot_name="x", status="missing")
        assert sat.slot_name == "x"
        assert sat.status == "missing"
        assert sat.source_span_ids == []


class TestConstructSatisfactionReport:
    def test_minimal_report(self):
        report = ConstructSatisfactionReport(
            construct_id="exc_1",
            construct_type="EXCEPTION_FLOW",
            slots=[
                SlotSatisfaction(slot_name="condition", status="satisfied", source_span_ids=["s1"]),
                SlotSatisfaction(slot_name="handler_action", status="missing",
                                 diagnostic_kind="missing_handler"),
            ],
            completeness="partial",
            renderable=True,
        )
        assert report.construct_id == "exc_1"
        assert report.completeness == "partial"
        assert report.renderable is True
        assert len(report.slots) == 2

    def test_complete_report(self):
        report = ConstructSatisfactionReport(
            construct_id="cmd_1",
            construct_type="GENERAL_COMMAND",
            slots=[
                SlotSatisfaction(
                    slot_name="action_text",
                    status="satisfied",
                    source_span_ids=["s5"],
                ),
                SlotSatisfaction(
                    slot_name="source_evidence",
                    status="satisfied",
                    source_span_ids=["s5"],
                ),
            ],
            completeness="complete",
            renderable=True,
        )
        assert report.completeness == "complete"
        assert all(s.status == "satisfied" for s in report.slots)
