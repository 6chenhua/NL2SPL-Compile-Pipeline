"""Unit tests for FactVerifier (Phase 3)."""

from __future__ import annotations

from nl2spl.adapters.fact_verifier import FactVerifier
from nl2spl.adapters.llm_engine import AdapterFactExtraction
from nl2spl.canonical import (
    AdapterWarning,
    DelegationIntentFact,
    EvidenceRef,
    FailureModeFact,
    HardFacts,
    VariableFact,
)


# -- helpers -------------------------------------------------------------


def _ev(section: str) -> list[EvidenceRef]:
    return [EvidenceRef(source_section_id=section)]


def _det_var(name: str, section: str = "sec_inputs_for_each_run") -> VariableFact:
    """Deterministic fact -- evidence may be empty (legacy source_section_id)."""
    return VariableFact(
        name=name, description="A variable.",
        data_type="text", required=True,
        source_section_id=section,
    )


def _llm_var(name: str, section: str = "sec_other") -> VariableFact:
    """LLM fact -- must have evidence."""
    return VariableFact(
        name=name, description="A variable.",
        data_type="text", required=True,
        source_section_id=section,
        evidence=_ev(section),
    )


def _det_fail(name: str, text: str) -> FailureModeFact:
    return FailureModeFact(
        name=name, text=text,
        source_section_id="sec_failure_handling",
    )


def _llm_fail(name: str, text: str) -> FailureModeFact:
    return FailureModeFact(
        name=name, text=text,
        source_section_id="sec_failure_handling",
        evidence=_ev("sec_failure_handling"),
    )


def _det_intent(name: str, text: str = "Delegate something.") -> DelegationIntentFact:
    return DelegationIntentFact(name=name, text=text)


def _llm_intent(name: str, text: str = "Delegate something.") -> DelegationIntentFact:
    return DelegationIntentFact(
        name=name, text=text,
        evidence=_ev("sec_delegation_policy"),
    )


# -- Merge priority tests ------------------------------------------------


class TestMergePriority:
    def test_deterministic_facts_preserved(self) -> None:
        det = HardFacts(
            inputs=[_det_var("user_request")],
            outputs=[_det_var("final_report")],
        )
        llm = AdapterFactExtraction(
            inputs=[_llm_var("extra_input")],
            outputs=[],
        )
        verifier = FactVerifier()
        merged, warnings = verifier.verify_and_merge(det, llm)
        assert len(merged.inputs) == 2
        assert merged.inputs[0].name == "user_request"
        assert merged.inputs[1].name == "extra_input"
        assert merged.outputs[0].name == "final_report"
        assert warnings == []

    def test_llm_empty_extraction_keeps_deterministic(self) -> None:
        det = HardFacts(inputs=[_det_var("a")], outputs=[_det_var("b")])
        llm = AdapterFactExtraction()
        verifier = FactVerifier()
        merged, warnings = verifier.verify_and_merge(det, llm)
        assert len(merged.inputs) == 1
        assert len(merged.outputs) == 1
        assert warnings == []

    def test_deterministic_empty_keeps_llm(self) -> None:
        det = HardFacts()
        llm = AdapterFactExtraction(inputs=[_llm_var("new_input")])
        verifier = FactVerifier()
        merged, warnings = verifier.verify_and_merge(det, llm)
        assert len(merged.inputs) == 1
        assert warnings == []

    def test_llm_reserved_schema_input_rejected(self) -> None:
        det = HardFacts()
        llm = AdapterFactExtraction(inputs=[_llm_var("source_section_id")])
        verifier = FactVerifier()
        merged, warnings = verifier.verify_and_merge(det, llm)
        assert merged.inputs == []
        assert any(w.code == "LLM_RESERVED_VARIABLE_REJECTED" for w in warnings)

    def test_llm_reserved_schema_output_rejected(self) -> None:
        det = HardFacts()
        llm = AdapterFactExtraction(outputs=[_llm_var("main_flow_spans")])
        verifier = FactVerifier()
        merged, warnings = verifier.verify_and_merge(det, llm)
        assert merged.outputs == []
        assert any(w.code == "LLM_RESERVED_VARIABLE_REJECTED" for w in warnings)


# -- Duplicate name tests ------------------------------------------------


class TestDuplicateNames:
    def test_llm_duplicate_input_name_rejected(self) -> None:
        det = HardFacts(inputs=[_det_var("user_request")])
        llm = AdapterFactExtraction(inputs=[_llm_var("user_request", "sec_other")])
        verifier = FactVerifier()
        merged, warnings = verifier.verify_and_merge(det, llm)
        assert len(merged.inputs) == 1
        assert merged.inputs[0].source_section_id == "sec_inputs_for_each_run"
        assert any("duplicate" in w.message.lower() for w in warnings)

    def test_llm_duplicate_output_name_rejected(self) -> None:
        det = HardFacts(outputs=[_det_var("report", "sec_required_outputs")])
        llm = AdapterFactExtraction(outputs=[_llm_var("report", "sec_required_outputs")])
        verifier = FactVerifier()
        merged, warnings = verifier.verify_and_merge(det, llm)
        assert len(merged.outputs) == 1
        assert any("duplicate" in w.message.lower() for w in warnings)

    def test_llm_output_collides_with_deterministic_input(self) -> None:
        det = HardFacts(inputs=[_det_var("shared_name")])
        llm = AdapterFactExtraction(outputs=[_llm_var("shared_name")])
        verifier = FactVerifier()
        merged, warnings = verifier.verify_and_merge(det, llm)
        assert len(merged.outputs) == 0
        assert any("collides with input" in w.message.lower() for w in warnings)

    def test_llm_duplicate_failure_mode_rejected(self) -> None:
        det = HardFacts(failure_modes=[_det_fail("missing_timeframe", "Missing timeframe.")])
        llm = AdapterFactExtraction(failure_modes=[_llm_fail("missing_timeframe", "Missing timeframe again.")])
        verifier = FactVerifier()
        merged, warnings = verifier.verify_and_merge(det, llm)
        assert len(merged.failure_modes) == 1
        assert merged.failure_modes[0].text == "Missing timeframe."
        assert any("failure_mode" in w.message.lower() for w in warnings)

    def test_llm_duplicate_delegation_intent_rejected(self) -> None:
        det = HardFacts(delegation_intents=[_det_intent("source_gathering")])
        llm = AdapterFactExtraction(delegation_intents=[_llm_intent("source_gathering")])
        verifier = FactVerifier()
        merged, warnings = verifier.verify_and_merge(det, llm)
        assert len(merged.delegation_intents) == 1
        assert any("delegation_intent" in w.message.lower() for w in warnings)


# -- Failure mode sanity tests -------------------------------------------


class TestFailureModeSanity:
    def test_empty_failure_text_rejected(self) -> None:
        det = HardFacts()
        llm = AdapterFactExtraction(failure_modes=[_llm_fail("bad", "")])
        verifier = FactVerifier()
        merged, warnings = verifier.verify_and_merge(det, llm)
        assert len(merged.failure_modes) == 0
        assert any("rejected" in w.message.lower() for w in warnings)

    def test_single_word_failure_text_rejected(self) -> None:
        det = HardFacts()
        llm = AdapterFactExtraction(failure_modes=[_llm_fail("bad", "timeframe")])
        verifier = FactVerifier()
        merged, warnings = verifier.verify_and_merge(det, llm)
        assert len(merged.failure_modes) == 0

    def test_multi_word_condition_text_accepted(self) -> None:
        det = HardFacts()
        llm = AdapterFactExtraction(failure_modes=[_llm_fail("ok", "Missing timeframe.")])
        verifier = FactVerifier()
        merged, warnings = verifier.verify_and_merge(det, llm)
        assert len(merged.failure_modes) == 1
        assert warnings == []


# -- LLM warnings propagation --------------------------------------------


class TestLLMWarningsPreserved:
    def test_llm_warnings_are_kept(self) -> None:
        det = HardFacts()
        llm = AdapterFactExtraction(
            warnings=[AdapterWarning(code="LLM_UNCERTAIN", message="Unsure.")],
        )
        verifier = FactVerifier()
        _merged, warnings = verifier.verify_and_merge(det, llm)
        assert any("Unsure" in w.message for w in warnings)

    def test_deterministic_input_not_mutated(self) -> None:
        det = HardFacts(inputs=[_det_var("original")])
        original_inputs = list(det.inputs)
        llm = AdapterFactExtraction(inputs=[_llm_var("extra")])
        verifier = FactVerifier()
        verifier.verify_and_merge(det, llm)
        assert det.inputs == original_inputs
        assert len(det.inputs) == 1


# -- Delegation intent rules -----------------------------------------------


class TestDelegationIntentRules:
    def test_delegation_intent_accepted(self) -> None:
        det = HardFacts()
        llm = AdapterFactExtraction(delegation_intents=[_llm_intent("source_gathering")])
        verifier = FactVerifier()
        merged, warnings = verifier.verify_and_merge(det, llm)
        assert len(merged.delegation_intents) == 1
        assert warnings == []


# -- No-evidence rejection tests -------------------------------------------


class TestNoEvidenceRejection:
    def test_llm_input_without_evidence_rejected(self) -> None:
        det = HardFacts()
        llm = AdapterFactExtraction(inputs=[_det_var("orphan")])
        verifier = FactVerifier()
        merged, warnings = verifier.verify_and_merge(det, llm)
        assert merged.inputs == []
        assert any("no evidence" in w.message.lower() for w in warnings)

    def test_llm_output_without_evidence_rejected(self) -> None:
        det = HardFacts()
        llm = AdapterFactExtraction(outputs=[_det_var("orphan")])
        verifier = FactVerifier()
        merged, warnings = verifier.verify_and_merge(det, llm)
        assert merged.outputs == []
        assert any("no evidence" in w.message.lower() for w in warnings)

    def test_llm_failure_without_evidence_rejected(self) -> None:
        det = HardFacts()
        llm = AdapterFactExtraction(
            failure_modes=[FailureModeFact(
                name="bad", text="Missing timeframe.",
                source_section_id="sec_failure_handling",
            )],
        )
        verifier = FactVerifier()
        merged, warnings = verifier.verify_and_merge(det, llm)
        assert merged.failure_modes == []
        assert any("no evidence" in w.message.lower() for w in warnings)

    def test_llm_delegation_without_evidence_rejected(self) -> None:
        det = HardFacts()
        llm = AdapterFactExtraction(
            delegation_intents=[DelegationIntentFact(
                name="bad", text="Delegate something.",
            )],
        )
        verifier = FactVerifier()
        merged, warnings = verifier.verify_and_merge(det, llm)
        assert merged.delegation_intents == []
        assert any("no evidence" in w.message.lower() for w in warnings)
