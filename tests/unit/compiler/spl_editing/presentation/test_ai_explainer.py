from __future__ import annotations

import json

from nl2spl.compiler.spl_editing.presentation.ai_explainer import (
    IssueExplanationGenerator,
)
from nl2spl.compiler.spl_editing.presentation.contract.availability import (
    RepairOptionAvailability,
)
from nl2spl.compiler.spl_editing.presentation.model.advanced import IssueAdvancedDetails
from nl2spl.compiler.spl_editing.presentation.model.issue import (
    IssueDetailPresentationView,
    RepairOptionView,
)


class _LLM:
    def __init__(self, response: object = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.user_prompt = ""

    def generate_json(self, _system_prompt: str, user_prompt: str) -> str:
        self.user_prompt = user_prompt
        if self.error:
            raise self.error
        return json.dumps(self.response, ensure_ascii=False)


def _detail() -> IssueDetailPresentationView:
    return IssueDetailPresentationView(
        issue_id="issue_1",
        title="Worker delegation is underspecified",
        what_was_detected="A possible worker has no invocation point.",
        missing_items=("invocation point",),
        why_it_matters="The child cannot be invoked safely.",
        source_context="Optional delegated subtasks such as source gathering may be used.",
        available_repairs=(
            RepairOptionView(label="Create handoff", description="Use a worker."),
            RepairOptionView(
                label="Keep in main flow",
                description="Do not use a worker.",
                availability=RepairOptionAvailability.REVIEW_ONLY,
                unavailable_reason="Unavailable in this snapshot.",
            ),
        ),
        advanced=IssueAdvancedDetails(
            primary_diagnostic_id="diag_1",
            diagnostic_kind="type_or_contract_ambiguity",
            irs_construct_type="WORKER_PROMOTION",
        ),
    )


def _response(recommended_option: int | None = 1) -> dict[str, object]:
    return {
        "headline": "可选子任务缺少启动位置",
        "problem": "原文允许委派资料搜集，但未说明主流程何时启动它。",
        "impact": "编译器无法生成可靠的 worker 调用。",
        "source_interpretation": "委派是可选能力，不是完整交接协议。",
        "option_guidance": [
            {"option": 1, "when_to_choose": "需要独立执行时。", "tradeoff": "需定义交接。"},
            {"option": 2, "when_to_choose": "无需独立执行时。", "tradeoff": "当前不可用。"},
        ],
        "recommended_option": recommended_option,
        "recommendation_reason": "原文提到了可选委派。",
        "questions": ["应该在哪一步启动？"],
    }


def test_generates_contextual_json_and_preserves_compiler_owned_options() -> None:
    llm = _LLM(_response())

    result = IssueExplanationGenerator(llm).generate(_detail())

    assert result.generation_source == "llm"
    assert result.headline == "可选子任务缺少启动位置"
    assert result.options[0].label == "Create handoff"
    assert result.options[1].available is False
    assert "Optional delegated subtasks" in llm.user_prompt


def test_provider_failure_uses_explicit_fallback_without_recommendation() -> None:
    result = IssueExplanationGenerator(_LLM(error=RuntimeError("provider down"))).generate(
        _detail()
    )

    assert result.generation_source == "deterministic_fallback"
    assert result.recommended_option is None
    assert result.generation_warning == "provider down"


def test_unavailable_option_cannot_be_recommended() -> None:
    result = IssueExplanationGenerator(_LLM(_response(recommended_option=2))).generate(
        _detail()
    )

    assert result.generation_source == "deterministic_fallback"
    assert result.recommended_option is None
