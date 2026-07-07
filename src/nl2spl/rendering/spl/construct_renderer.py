from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from nl2spl.rendering.model import RenderedFragment

if TYPE_CHECKING:
    from nl2spl.rendering.context import SPLRenderContext
    from nl2spl.rendering.model import RenderMode


class RenderableSPLConstructType(StrEnum):
    AGENT = "AGENT"
    WORKER = "WORKER"
    FLOW = "FLOW"
    BLOCK = "BLOCK"
    STEP = "STEP"
    EXCEPTION_FLOW = "EXCEPTION_FLOW"


@runtime_checkable
class SPLConstructRenderer(Protocol):
    construct_type: RenderableSPLConstructType

    def render(
        self,
        ir: object,
        context: SPLRenderContext,
        mode: RenderMode,
    ) -> RenderedFragment: ...


_REGISTRY: dict[RenderableSPLConstructType, SPLConstructRenderer] = {}


def register_construct_renderer(renderer: SPLConstructRenderer) -> None:
    _REGISTRY[renderer.construct_type] = renderer


def render_spl_construct(
    construct_type: RenderableSPLConstructType,
    ir: object,
    context: SPLRenderContext,
    mode: RenderMode,
) -> RenderedFragment:
    """Dispatches rendering to the appropriate construct-level renderer."""
    if construct_type not in _REGISTRY:
        from nl2spl.rendering.model import RenderDiagnostic

        diag = RenderDiagnostic(
            diagnostic_id="missing_construct_renderer",
            kind="unsupported_construct",
            severity="error",
            message=f"No registered renderer found for construct type: {construct_type.value}",
            target_ref=f"construct_type:{construct_type.value}",
        )
        return RenderedFragment(
            format="spl_text",
            text=f"<!-- Error: unsupported construct type {construct_type.value} -->",
            render_diagnostics=(diag,),
        )
    return _REGISTRY[construct_type].render(ir, context, mode)
