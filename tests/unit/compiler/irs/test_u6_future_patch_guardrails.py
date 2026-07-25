"""Phase U6: Future Patch Compliance Guardrails.

Source-scanning tests that prevent regression of the UCR evidence contract.
"""

from __future__ import annotations

import inspect

# =============================================================================
# U6 Guardrail 1: No naked bool(step.source_span_ids) as sole renderable check
# =============================================================================


class TestNoNakedSourceSpanRenderable:
    """``bool(step.source_span_ids)`` must not be the sole renderability check.

    The post_normalize checker was the main violation point; these tests
    lock that the fix stays in place.
    """

    _FORBIDDEN_IN_RENDERABLE = [
        "renderable = bool(step.source_span_ids)",
        "all_ok = source_backed",
        "bool(step.source_span_ids) and not api_missing",
    ]

    def test_post_normalize_no_naked_source_span_renderable(self) -> None:
        """post_normalize.py must not use source_span_ids as sole renderable."""
        import nl2spl.compiler.irs.checkers.post_normalize as mod
        source = inspect.getsource(mod)
        for pattern in self._FORBIDDEN_IN_RENDERABLE:
            assert pattern not in source, (
                f"FORBIDDEN in post_normalize.py: '{pattern}'"
            )

    def test_post_normalize_request_input_not_using_source_backed(self) -> None:
        """_check_request_input must not define source_backed = bool(step.source_span_ids)."""
        from nl2spl.compiler.irs.checkers.post_normalize import PostNormalizeIRSCheckerV6
        source = inspect.getsource(PostNormalizeIRSCheckerV6._check_request_input)
        assert "source_backed = bool(step.source_span_ids)" not in source, (
            "U1 fix removed source_backed from _check_request_input — regression detected!"
        )

    def test_post_normalize_call_api_not_source_span_only(self) -> None:
        """_check_call_api renderable must not be gated solely on source_span_ids."""
        from nl2spl.compiler.irs.checkers.post_normalize import PostNormalizeIRSCheckerV6
        source = inspect.getsource(PostNormalizeIRSCheckerV6._check_call_api)
        # call_action now checks both text AND evidence, not just source_span_ids
        assert "step.source_span_ids" not in source or "has_call_action" in source, (
            "U1 fix introduced has_call_action in _check_call_api — regression detected!"
        )


# =============================================================================
# U6 Guardrail 2: StepIR-producing materializers stamp user_confirmed_repair
# =============================================================================


class TestAllStepProducingMaterializersStamped:
    """Every materializer that creates StepIR must write origin=user_confirmed_repair."""

    def test_all_step_producing_materializers_have_ucr(self) -> None:
        """Audit: stage-authorized materializers stamp UCR metadata."""
        import importlib

        materializer_modules = [
            "nl2spl.compiler.spl_editing.materialization.stage7.producer_step",
            "nl2spl.compiler.spl_editing.materialization.stage7.exception_handler_step",
            "nl2spl.compiler.spl_editing.materialization.worker_handoff.contract",
        ]
        for module_name in materializer_modules:
            mod = importlib.import_module(module_name)
            source = inspect.getsource(mod)
            assert "user_confirmed_repair" in source, (
                f"Materializer '{module_name}' must stamp user_confirmed_repair"
            )
            assert "repair_patch_id" in source
            assert "related_diagnostic_id" in source

    def test_patch_appliers_do_not_directly_construct_ir(self) -> None:
        """R11: patch appliers are no longer the StepIR/BlockIR construction authority."""
        import importlib

        applier_names = [
            "add_exception_handler_step",
            "convert_delegation_to_main_flow_step",
            "convert_delegation_to_request_input",
            "create_worker_handoff_contract",
        ]
        forbidden = ("StepIR(", "BlockIR(", "WorkerHandoffIR(")
        for name in applier_names:
            mod = importlib.import_module(
                f"nl2spl.compiler.spl_editing.patches.{name}.applier"
            )
            source = inspect.getsource(mod)
            assert not any(token in source for token in forbidden), (
                f"Applier '{name}' must delegate to materialization, not construct IR"
            )


# =============================================================================
# U6 Guardrail 3: Unconfirmed AI suggestion is never renderable
# =============================================================================


class TestUnconfirmedNotRenderable:
    """An AI suggestion without user confirmation must never become renderable."""

    def test_unconfirmed_without_source_is_assumed(self) -> None:
        """A step with no source spans and no UCR origin → assumed."""
        from nl2spl.compiler.evidence import classify_step_evidence
        from nl2spl.ir.step_ir import StepIR

        step = StepIR("st1", "AI suggested", [], "GENERAL_COMMAND")
        evidence = classify_step_evidence(step)
        assert evidence.primary_kind == "missing"
        assert evidence.satisfied is False

    def test_llm_suggestion_without_ucr_is_missing(self) -> None:
        """LLM suggestion payload must NOT carry origin — only apply time writes it."""
        from nl2spl.compiler.evidence import classify_step_evidence
        from nl2spl.ir.step_ir import StepIR

        # An AI suggestion that has NOT been confirmed
        step = StepIR("st_ai", "AI generated", [], "GENERAL_COMMAND",
                      metadata={"llm_generated": "true"})
        evidence = classify_step_evidence(step)
        assert evidence.primary_kind == "missing", (
            "llm_generated metadata is NOT a valid evidence origin"
        )
        assert evidence.satisfied is False
