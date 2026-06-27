"""Transition guards for preview/apply lifecycle exposure on the default service."""

from __future__ import annotations

import importlib.util

from nl2spl.compiler.spl_editing.core.service import SPLEditingService


class TestPreviewApplyContractBaseline:
    def test_spl_editing_service_exposes_r13_preview_apply_apis(self) -> None:
        """R13.3 exposes preview/apply lifecycle APIs on the default service path."""
        assert not hasattr(SPLEditingService, "preview_repair")
        assert hasattr(SPLEditingService, "preview_suggestion")
        assert hasattr(SPLEditingService, "apply_preview_result")
        assert hasattr(SPLEditingService, "get_preview_store")

    def test_stage_slice_substrate_is_isolated_from_default_service_api(self) -> None:
        """R12.5+ provides stage_slices while service APIs stay lifecycle-oriented."""
        assert importlib.util.find_spec("nl2spl.compiler.spl_editing.stage_slices") is not None
        assert importlib.util.find_spec("nl2spl.compiler.spl_editing.stage_slices.registry") is not None