from __future__ import annotations

from typing import TYPE_CHECKING

from nl2spl.ir.worker_ir import WorkerIR
from nl2spl.pipeline.stages.stage11_spl_renderer.renderer import SPLRenderer
from nl2spl.rendering.model import RenderDiagnostic, RenderedFragment
from nl2spl.rendering.spl.construct_renderer import (
    RenderableSPLConstructType,
    register_construct_renderer,
)

if TYPE_CHECKING:
    from nl2spl.rendering.context import SPLRenderContext
    from nl2spl.rendering.model import RenderMode


class WorkerRenderer:
    construct_type = RenderableSPLConstructType.WORKER

    def render(
        self,
        ir: object,
        context: SPLRenderContext,
        mode: RenderMode,
    ) -> RenderedFragment:
        if not isinstance(ir, WorkerIR):
            diag = RenderDiagnostic(
                diagnostic_id="invalid_worker_ir",
                kind="type_mismatch",
                severity="error",
                message=f"Expected WorkerIR construct, got: {type(ir).__name__}",
                target_ref="worker:unknown",
            )
            return RenderedFragment(format="spl_text", text="", render_diagnostics=(diag,))

        legacy = SPLRenderer()
        if context.resources and context.symbol_table:
            legacy._result_data_types = legacy._result_type_lookup(
                context.resources, context.symbol_table
            )
        else:
            legacy._result_data_types = {}

        if context.numbering:
            legacy._command_index = context.numbering.command_index
            legacy._decision_index = context.numbering.decision_index
        else:
            legacy._command_index = 1
            legacy._decision_index = 1

        try:
            # Delegate to child worker rendering logic
            lines = legacy._render_child_worker(ir)
            if context.numbering:
                context.numbering.command_index = legacy._command_index
                context.numbering.decision_index = legacy._decision_index
            return RenderedFragment(format="spl_text", text="\n".join(lines))
        except Exception as e:
            diag = RenderDiagnostic(
                diagnostic_id="worker_render_error",
                kind="render_failure",
                severity="error",
                message=str(e),
                target_ref=f"worker:{ir.worker_name}",
            )
            return RenderedFragment(format="spl_text", text="", render_diagnostics=(diag,))


register_construct_renderer(WorkerRenderer())
