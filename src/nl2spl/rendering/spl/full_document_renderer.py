from __future__ import annotations

from typing import TYPE_CHECKING

from nl2spl.rendering.model import RenderedDocument, RenderMode
from nl2spl.rendering.spl.stage11_compat import render_full_spl_from_legacy_inputs

if TYPE_CHECKING:
    from nl2spl.compiler.final_ir_package import FinalIRPackage


def render_full_spl(
    package: FinalIRPackage,
    *,
    mode: RenderMode = RenderMode.FULL_DOCUMENT,
) -> RenderedDocument:
    """Render a full SPL document from a FinalIRPackage using the compatibility renderer."""
    return render_full_spl_from_legacy_inputs(
        worker=package.root_worker,
        profile=package.profile,
        resources=package.resources,
        symbol_table=package.symbol_table,
        steps=list(package.legacy_unscoped_steps),
        constraints=list(package.constraints),
    )
