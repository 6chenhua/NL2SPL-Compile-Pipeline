"""Unit tests for StructuralNLAdapter without LLM enrichment."""

from __future__ import annotations

from nl2spl.adapters.structural_nl import StructuralNLAdapter

STRUCTURAL_TEXT = """Task family:
Internal reports.

Inputs for each run:
- user_request: The user's request.

Required outputs:
- final_report: A compiled report.

Reusable process:
Read the request.

Failure handling:
Missing source material.

Delegation policy:
Source gathering may be delegated when bounded.
"""


class _FailingLLM:
    def __init__(self) -> None:
        self.calls = 0

    def call_json(self, **_kwargs: object) -> dict:
        self.calls += 1
        raise RuntimeError("LLM must not be called by StructuralNLAdapter")


def test_structural_adapter_ignores_llm_client() -> None:
    llm = _FailingLLM()
    adapter = StructuralNLAdapter(llm_client=llm)

    result = adapter.adapt(STRUCTURAL_TEXT)

    assert llm.calls == 0
    assert not any(w.code == "LLM_ENRICHMENT_FAILED" for w in result.warnings)
    assert result.route_priors == []


def test_structural_adapter_preserves_only_deterministic_variable_facts() -> None:
    result = StructuralNLAdapter(
        llm_client=_FailingLLM(), enable_hard_facts=True,
    ).adapt(STRUCTURAL_TEXT)

    input_names = {fact.name for fact in result.hard_facts.inputs}
    output_names = {fact.name for fact in result.hard_facts.outputs}

    assert input_names
    assert output_names
    assert result.hard_facts.delegation_intents == []
    assert not hasattr(result.hard_facts, "failure_modes")


def test_structural_adapter_keeps_semantic_packets_neutral() -> None:
    result = StructuralNLAdapter().adapt(STRUCTURAL_TEXT)

    assert result.semantic_packets
    assert all(packet.modality == "hint" for packet in result.semantic_packets)
    assert all(packet.metadata.get("executable") is False for packet in result.semantic_packets)
