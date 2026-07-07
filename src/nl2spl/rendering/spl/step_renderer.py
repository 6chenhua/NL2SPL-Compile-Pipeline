from __future__ import annotations

from typing import TYPE_CHECKING

from nl2spl.ir.step_ir import StepIR
from nl2spl.pipeline.stages.stage11_spl_renderer.renderer import SPLRenderer
from nl2spl.rendering.model import RenderDiagnostic, RenderedFragment
from nl2spl.rendering.spl.construct_renderer import (
    RenderableSPLConstructType,
    register_construct_renderer,
)

if TYPE_CHECKING:
    from nl2spl.rendering.context import SPLRenderContext
    from nl2spl.rendering.model import RenderMode


class StepRenderer:
    construct_type = RenderableSPLConstructType.STEP

    def render(
        self,
        ir: object,
        context: SPLRenderContext,
        mode: RenderMode,
    ) -> RenderedFragment:
        if not isinstance(ir, StepIR):
            diag = RenderDiagnostic(
                diagnostic_id="invalid_step_ir",
                kind="type_mismatch",
                severity="error",
                message=f"Expected StepIR construct, got: {type(ir).__name__}",
                target_ref="step:unknown",
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
            rendered_text = legacy._render_step(ir)
            if context.numbering:
                context.numbering.command_index = legacy._command_index
                context.numbering.decision_index = legacy._decision_index
            return RenderedFragment(format="spl_text", text=rendered_text)
        except ValueError as ve:
            # Handle context_required scenarios (e.g. missing integration_ref)
            diag = RenderDiagnostic(
                diagnostic_id="step_context_required",
                kind="context_required",
                severity="error",
                message=str(ve),
                target_ref=f"step:{ir.step_id}",
            )
            return RenderedFragment(format="spl_text", text="", render_diagnostics=(diag,))
        except Exception as e:
            diag = RenderDiagnostic(
                diagnostic_id="step_render_error",
                kind="render_failure",
                severity="error",
                message=str(e),
                target_ref=f"step:{ir.step_id}",
            )
            return RenderedFragment(format="spl_text", text="", render_diagnostics=(diag,))


register_construct_renderer(StepRenderer())
