"""Unit tests for StructuralNLAdapter LLM enrichment."""

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
"""


class _FakeLLM:
    def __init__(self, response: dict) -> None:
        self.response = response
        self.calls: list[dict[str, str]] = []

    def call_json(
        self,
        stage_name: str = "",
        system_prompt: str = "",
        user_prompt: str = "",
        **_kwargs: object,
    ) -> dict:
        self.calls.append({
            "stage_name": stage_name,
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
        })
        return dict(self.response)


class _FailingLLM:
    def call_json(self, **_kwargs: object) -> dict:
        raise RuntimeError("unavailable")


def test_structural_enrichment_merges_non_duplicate_fact() -> None:
    adapter = StructuralNLAdapter(llm_client=_FakeLLM({
        "failure_modes": [
            {
                "name": "missing_source",
                "text": "Missing source: source material was not provided.",
                "source_section_id": "sec_reusable_process",
            }
        ]
    }))

    result = adapter.adapt(STRUCTURAL_TEXT)

    names = {fact.name for fact in result.hard_facts.failure_modes}
    assert "missing_source" in names
    assert not any(w.code == "LLM_ENRICHMENT_FAILED" for w in result.warnings)


def test_structural_enrichment_duplicate_deterministic_fact_rejected() -> None:
    adapter = StructuralNLAdapter(llm_client=_FakeLLM({
        "outputs": [
            {
                "name": "final_report_a_compiled_report",
                "description": "Duplicate report output.",
                "data_type": "text",
                "required": True,
                "source_section_id": "sec_required_outputs",
            }
        ]
    }))

    result = adapter.adapt(STRUCTURAL_TEXT)

    outputs = [
        fact
        for fact in result.hard_facts.outputs
        if fact.name == "final_report_a_compiled_report"
    ]
    assert len(outputs) == 1
    assert any(w.code == "LLM_DUPLICATE_FACT" for w in result.warnings)


def test_structural_enrichment_failure_preserves_deterministic_facts() -> None:
    adapter = StructuralNLAdapter(llm_client=_FailingLLM())

    result = adapter.adapt(STRUCTURAL_TEXT)

    assert result.hard_facts.outputs
    assert any(w.code == "LLM_ENRICHMENT_FAILED" for w in result.warnings)
