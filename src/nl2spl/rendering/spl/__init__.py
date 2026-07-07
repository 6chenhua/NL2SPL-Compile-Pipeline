from __future__ import annotations

import nl2spl.rendering.spl.block_renderer  # noqa: F401
import nl2spl.rendering.spl.exception_flow_renderer  # noqa: F401

# Force registration of construct renderers
import nl2spl.rendering.spl.step_renderer  # noqa: F401
import nl2spl.rendering.spl.worker_renderer  # noqa: F401
from nl2spl.rendering.spl.construct_renderer import (
    RenderableSPLConstructType,
    render_spl_construct,
)
from nl2spl.rendering.spl.full_document_renderer import render_full_spl
from nl2spl.rendering.spl.repair_preview_renderer import (
    RenderedPreview,
    render_repair_preview_spl,
)
from nl2spl.rendering.spl.stage11_compat import render_full_spl_from_legacy_inputs

__all__ = [
    "render_full_spl_from_legacy_inputs",
    "render_full_spl",
    "RenderableSPLConstructType",
    "render_spl_construct",
    "RenderedPreview",
    "render_repair_preview_spl",
]
