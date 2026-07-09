"""S6V1: Stage 6 prompt contract tests.

Verify the prompt:
- Does NOT contain condition variable declaration rules.
- Does NOT contain SPL grammar authority terms.
- Does NOT contain demo fixture-specific variable names or sentences.
- DOES contain source-document role rules.
- DOES explicitly prohibit guard/control/read-only declaration.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[4]
PROMPT_DIR = REPO_ROOT / "prompts"


def _read_stage6_prompt() -> str:
    path = PROMPT_DIR / "stage6_system.txt"
    if not path.exists():
        pytest.skip("Prompt file not found")
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Negative assertions: prompt must NOT contain
# ---------------------------------------------------------------------------


class TestS6V1PromptNoConditionVariableRule:
    """Verify the condition variable declaration rule has been removed."""

    def test_no_every_condition_variable_rule(self) -> None:
        prompt = _read_stage6_prompt()
        assert "Every condition variable" not in prompt, (
            "S6V1: prompt must not contain the old rule 'Every condition "
            "variable (used in IF conditions) has been declared as a step "
            "variable'."
        )

    def test_no_if_condition_reference(self) -> None:
        prompt = _read_stage6_prompt()
        assert "used in IF conditions" not in prompt, (
            "S6V1: prompt must not reference IF conditions as declaration "
            "authority."
        )


class TestS6V1PromptNoGrammarAuthority:
    """Verify SPL grammar terms are not used as authority."""

    def test_no_condition_keyword_as_role(self) -> None:
        prompt = _read_stage6_prompt()
        # "condition" should only appear in the PROHIBITION context
        # (describing what NOT to do), not as a role to declare from.
        # Verify the declaration section mentions conditions only in the
        # "Do not" list.
        if "### Declaration Authority" in prompt:
            declaration_section = prompt.split("### Declaration Authority")[1].split("###")[0]
            # "condition" should appear only in "Do **not**" context
            do_not_pos = declaration_section.find("Do **not**")
            condition_pos = declaration_section.find("condition")
            if condition_pos >= 0 and do_not_pos >= 0:
                assert condition_pos > do_not_pos, (
                    "S6V1: 'condition' in Declaration Authority section "
                    "must appear only in the 'Do not' prohibition."
                )

    def test_no_uppercase_spl_grammar_tokens_as_roles(self) -> None:
        prompt = _read_stage6_prompt()
        # These SPL grammar tokens must not appear as declaration authority
        forbidden_tokens = [
            "CONDITION",
            "DESCRIPTION_WITH_REFERENCES",
            "COMMAND_RESULT",
            "IF_BLOCK",
            "ALTERNATIVE_FLOW",
            "EXCEPTION_FLOW",
        ]
        for token in forbidden_tokens:
            assert token not in prompt, (
                f"S6V1: prompt must not contain SPL grammar token '{token}'."
            )


class TestS6V1PromptNoDemoAnswerLeakage:
    """Verify the prompt has no internal_comms fixture-specific answers."""

    def test_no_demo_variable_names(self) -> None:
        prompt = _read_stage6_prompt()
        demo_names = [
            "enough_required_information",
            "user_asks_for_revision",
            "sources_needed",
            "sources_available",
            "required_slots_remain_missing",
            "user_confirms",
            "draft_marked_as_assumption_bearing",
        ]
        for name in demo_names:
            assert name not in prompt, (
                f"S6V1: prompt must not contain demo variable name '{name}'."
            )

    def test_no_demo_fixture_sentences(self) -> None:
        prompt = _read_stage6_prompt()
        demo_sentences = [
            "approved source recipes",
            "source evidence set",
            "draft communication artifact",
            "when enough required information is available",
            "if the user asks for revision",
        ]
        for sentence in demo_sentences:
            assert sentence not in prompt, (
                f"S6V1: prompt must not contain demo sentence '{sentence}'."
            )


# ---------------------------------------------------------------------------
# Positive assertions: prompt MUST contain
# ---------------------------------------------------------------------------


class TestS6V1PromptHasSourceRoleRules:
    """Verify the prompt uses source-document role vocabulary."""

    def test_declaration_authority_section_exists(self) -> None:
        prompt = _read_stage6_prompt()
        assert "### Declaration Authority" in prompt, (
            "S6V1: prompt must have a Declaration Authority section."
        )

    def test_explicit_run_input_role(self) -> None:
        prompt = _read_stage6_prompt()
        assert "run input" in prompt.lower() or "run input" in prompt, (
            "S6V1: prompt must describe run inputs as a declaration role."
        )

    def test_explicit_required_deliverable_role(self) -> None:
        prompt = _read_stage6_prompt()
        assert "required deliverable" in prompt.lower(), (
            "S6V1: prompt must describe required deliverables as a "
            "declaration role."
        )

    def test_explicit_action_output_role(self) -> None:
        prompt = _read_stage6_prompt()
        assert "explicit action output" in prompt.lower() or "action output" in prompt.lower(), (
            "S6V1: prompt must describe explicit action outputs as a "
            "declaration role."
        )

    def test_explicitly_prohibits_guard_control_declaration(self) -> None:
        prompt = _read_stage6_prompt()
        prohibitions = [
            "guard clauses",
            "branch conditions",
            "rules, constraints",
            "display text",
        ]
        found = sum(1 for p in prohibitions if p.lower() in prompt.lower())
        assert found >= 2, (
            f"S6V1: prompt must prohibit declaring variables from guard/"
            f"control/read-only text. Found {found}/4 prohibition terms."
        )

    def test_completeness_check_no_longer_mentions_condition_variables(
        self,
    ) -> None:
        prompt = _read_stage6_prompt()
        cc_section = prompt.split("### Completeness Check")[1] if "### Completeness Check" in prompt else ""
        assert "condition variable" not in cc_section.lower(), (
            "S6V1: Completeness Check must not mention 'condition variable'."
        )
