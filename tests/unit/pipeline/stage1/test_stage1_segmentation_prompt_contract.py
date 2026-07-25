"""Unit tests checking the prompt contract requirements for Stage 1 Segmentation."""

from __future__ import annotations

from nl2spl.llm.prompts import load_prompt


def test_stage1_segmentation_prompts_contract() -> None:
    # 1. Load prompts
    sys_prompt = load_prompt("stage1_source_constrained")
    user_prompt = load_prompt("stage1_source_constrained_user")

    # 2. Check system prompt contains critical exact-copy and atomicity rules
    assert "exact copy" in sys_prompt.lower() or "copy exact" in sys_prompt.lower()
    assert "paraphrase" in sys_prompt.lower()
    assert "guarded_action" in sys_prompt.lower()
    assert "ambiguous_boundary" in sys_prompt.lower()
    assert "continuation_repaired" in sys_prompt.lower()

    # 3. Verify it instructs the LLM not to use SPL construct labels
    assert "not label" in sys_prompt.lower() or "no spl construct" in sys_prompt.lower()

    # 4. Check user prompt template placeholders
    assert "{section_id}" in user_prompt
    assert "{packets}" in user_prompt

    # 5. Check user prompt template contains few-shot examples
    assert "Example 8: Same-packet multiple independent guarded_action" in user_prompt
    assert "continuation_repaired" in user_prompt
