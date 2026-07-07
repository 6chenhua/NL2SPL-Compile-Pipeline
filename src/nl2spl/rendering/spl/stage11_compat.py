from __future__ import annotations

from typing import TYPE_CHECKING

from nl2spl.rendering.model import RenderDiagnostic, RenderedDocument

if TYPE_CHECKING:
    from nl2spl.ir.agent_profile_ir import AgentProfileIR
    from nl2spl.ir.constraint_ir import ConstraintIR
    from nl2spl.ir.resource_registry_ir import ResourceRegistryIR
    from nl2spl.ir.step_ir import StepIR
    from nl2spl.ir.symbol_table import SymbolTable
    from nl2spl.ir.worker_ir import WorkerIR


def render_full_spl_from_legacy_inputs(
    worker: WorkerIR,
    profile: AgentProfileIR,
    resources: ResourceRegistryIR,
    symbol_table: SymbolTable,
    steps: list[StepIR],
    constraints: list[ConstraintIR],
) -> RenderedDocument:
    """Compatibility wrapper that delegates to the existing Stage 11 SPLRenderer."""
    from nl2spl.pipeline.stages.stage11_spl_renderer.renderer import SPLRenderer

    renderer = SPLRenderer()
    spl_text, errors, warnings = renderer.render(
        worker=worker,
        profile=profile,
        resources=resources,
        symbol_table=symbol_table,
        steps=steps,
        constraints=constraints,
    )

    # Map raw string warnings/errors to RenderDiagnostic
    render_diags = []
    for err in errors:
        render_diags.append(
            RenderDiagnostic(
                diagnostic_id="stage11_compat_error",
                kind="legacy_error",
                severity="error",
                message=err,
                target_ref=f"worker:{worker.worker_name}",
            )
        )
    for warn in warnings:
        render_diags.append(
            RenderDiagnostic(
                diagnostic_id="stage11_compat_warning",
                kind="legacy_warning",
                severity="warning",
                message=warn,
                target_ref=f"worker:{worker.worker_name}",
            )
        )

    return RenderedDocument(
        renderer_id="stage11_compat",
        format="spl_text",
        text=spl_text,
        render_diagnostics=tuple(render_diags),
    )
