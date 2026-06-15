"""Phase L2-L3 tests — common facts builder, renderer, no raw message fallback."""

from __future__ import annotations

from unittest.mock import MagicMock

from nl2spl.compiler.spl_editing.llm_context.builder import LLMRepairContextBuilder
from nl2spl.compiler.spl_editing.llm_context.common_facts import (
    build_issue_facts,
    build_target_facts,
)
from nl2spl.compiler.spl_editing.llm_context.rendering import PromptRenderer
from nl2spl.compiler.spl_editing.llm_context.model import (
    LLMRepairContext,
    IssueFacts,
    SourceFacts,
    TargetFacts,
    WorkflowFacts,
    GenerationReadiness,
)


# ------------------------------------------------------------------
# L2: IssueFacts — no raw message fallback
# ------------------------------------------------------------------


class TestIssueFactsNoRawMessage:
    def test_what_was_detected_uses_suggested_resolution_not_message(self) -> None:
        issue = MagicMock()
        issue.kind = "missing_handler"
        issue.suggested_resolution = "Add handler for 'Missing timeframe'"
        issue.message = "Exception flow 'exc_adapter_03' has no handler"  # raw text
        issue.repairable = True
        issue.missing_slot = ""

        facts = build_issue_facts(issue)
        # MUST use suggested_resolution, NOT raw message
        assert "Missing timeframe" in facts.what_was_detected
        assert "exc_adapter_03" not in facts.what_was_detected

    def test_user_facing_title_from_presentation_preferred(self) -> None:
        issue = MagicMock()
        issue.kind = "missing_handler"
        issue.suggested_resolution = "Resolution"
        issue.repairable = True
        issue.missing_slot = ""

        pres = MagicMock()
        pres.user_facing_title = "Exception has no handler: Missing timeframe"
        pres.what_was_detected = "The SPL has an exception flow with no handler action"

        facts = build_issue_facts(issue, presentation_view=pres)
        assert facts.user_facing_title == "Exception has no handler: Missing timeframe"
        assert "SPL has an exception flow" in facts.what_was_detected


# ------------------------------------------------------------------
# L2: TargetFacts — no raw message
# ------------------------------------------------------------------


class TestTargetFactsNoRawMessage:
    def test_summary_uses_suggested_resolution_not_message(self) -> None:
        issue = MagicMock()
        issue.suggested_resolution = "Add handler for 'Missing timeframe'"
        issue.message = "Some diagnostic message"

        target = MagicMock()
        target.irs_ref = MagicMock()
        target.irs_ref.construct_type = "EXCEPTION_FLOW"
        target.irs_ref.slot_name = "handler_action"

        facts = build_target_facts(issue, target)
        assert "Missing timeframe" in facts.human_readable_target_summary


# ------------------------------------------------------------------
# L3: PromptRenderer — no construct_type branching
# ------------------------------------------------------------------


class TestPromptRenderer:
    def test_renders_without_crashing(self) -> None:
        renderer = PromptRenderer()
        ctx = LLMRepairContext(
            context_id="c1", session_id="s1",
            issue_facts=IssueFacts(
                issue_category="missing_handler",
                user_facing_title="T",
                what_was_detected="Missing handler",
                missing_items=(),
            ),
            source_facts=SourceFacts(primary_source_excerpt="Source text."),
            target_facts=TargetFacts(construct_type="EXCEPTION_FLOW", slot_name="handler_action"),
            workflow_facts=WorkflowFacts(worker_name="MainWorker"),
            generation_readiness=GenerationReadiness(status="ready"),
        )
        prompt = renderer.render(ctx)
        assert "Missing handler" in prompt
        assert "EXCEPTION_FLOW" in prompt
        assert "handler_action" in prompt

    def test_low_confidence_includes_conservative_instruction(self) -> None:
        renderer = PromptRenderer()
        ctx = LLMRepairContext(
            context_id="c1", session_id="s1",
            issue_facts=IssueFacts(
                issue_category="test", user_facing_title="T",
                what_was_detected="X", missing_items=(),
            ),
            source_facts=SourceFacts(),
            target_facts=TargetFacts(construct_type="TEST", slot_name="s"),
            workflow_facts=WorkflowFacts(),
            generation_readiness=GenerationReadiness(
                status="ready_low_confidence",
                reasons=("Context quality is low.",),
            ),
        )
        prompt = renderer.render(ctx)
        assert "incomplete" in prompt.lower()

    def test_section_order_constant_unchanged(self) -> None:
        from nl2spl.compiler.spl_editing.llm_context.constants import PROMPT_SECTION_ORDER
        assert PROMPT_SECTION_ORDER[0] == "task"
        assert PROMPT_SECTION_ORDER[-1] == "json_only_output"


# ------------------------------------------------------------------
# L3: no construct_type enum in renderer source
# ------------------------------------------------------------------


class TestRendererNoConstructEnum:
    def test_renderer_source_no_construct_type_if_else(self) -> None:
        import inspect
        from nl2spl.compiler.spl_editing.llm_context.rendering import PromptRenderer
        src = inspect.getsource(PromptRenderer._render_section)
        # Must not branch on EXCEPTION_FLOW / REQUIRED_OUTPUT / WORKER_PROMOTION
        assert "EXCEPTION_FLOW" not in src
        assert "REQUIRED_OUTPUT" not in src
        assert "WORKER_PROMOTION" not in src

    def test_common_facts_no_raw_message_fallback(self) -> None:
        import inspect
        from nl2spl.compiler.spl_editing.llm_context import common_facts
        src = inspect.getsource(common_facts.build_issue_facts)
        # Strip comments and docstrings
        lines = [l for l in src.split("\n") if not l.strip().startswith("#") and not l.strip().startswith('"""')]
        code = "\n".join(lines)
        # Must not use issue.message as business fact source in executable code
        assert 'issue.message' not in code
        assert '.message' not in code
