"""Phase L4 guardrail: handler does NOT own prompt construction in production path."""

from __future__ import annotations

import inspect


class TestHandlerDoesNotOwnPromptConstruction:
    """The handler receives a pre-rendered prompt from the service layer.
    It must NOT construct prompts from issue.message / suggested_resolution.
    """

    def test_handler_no_build_missing_handler_user_prompt_in_default_path(self) -> None:
        """The generate_suggestions method uses rendered_user_prompt when provided."""
        from nl2spl.compiler.spl_editing.handlers.missing_handler.handler import (
            MissingHandlerRepairHandler,
        )

        src = inspect.getsource(MissingHandlerRepairHandler.generate_suggestions)
        # Check that rendered_user_prompt path exists and is required.
        assert "rendered_user_prompt" in src
        assert "requires a rendered_user_prompt" in src
        assert "build_missing_handler_user_prompt" not in src

    def test_handler_no_extract_condition(self) -> None:
        """The handler module must NOT contain _extract_condition function."""
        from nl2spl.compiler.spl_editing.handlers.missing_handler import handler as mod

        assert not hasattr(mod, "_extract_condition"), (
            "Handler must not extract condition from issue.message/suggested_resolution"
        )

    def test_service_passes_rendered_prompt(self) -> None:
        """The service builds LLMRepairContext and passes rendered_user_prompt."""
        from nl2spl.compiler.spl_editing.core import service as svc_mod

        src = (
            inspect.getsource(svc_mod.SPLEditingService._generate_suggestions_inner)
            if hasattr(svc_mod.SPLEditingService, "_generate_suggestions_inner")
            else inspect.getsource(svc_mod.SPLEditingService.generate_suggestions)
        )
        # Service must build LLMRepairContext
        assert "llm_ctx_builder" in src
        assert "rendered_prompt" in src
        assert "rendered_user_prompt" in src


class TestNoSnapshotHack:
    """Service must not inject snapshot via context.metadata hack."""

    def test_service_no_context_metadata_snapshot_injection(self) -> None:
        """The service must pass snapshot directly to builder, not via metadata."""
        from nl2spl.compiler.spl_editing.core import service as svc_mod

        src = inspect.getsource(svc_mod.SPLEditingService.generate_suggestions)
        # Must NOT use context.metadata hack
        assert 'metadata["artifact_snapshot"]' not in src
        assert 'metadata.get("artifact_snapshot")' not in src
