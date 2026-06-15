"""Phase 0 baseline: Renderer must render child worker with empty INPUTS/OUTPUTS.

These tests verify that Stage 11 already handles empty contract without error.
The bug is upstream — the renderer never receives the partial worker.
"""

from __future__ import annotations

from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.worker_ir import (
    ChildWorkerIR,
    FlowRef,
    WorkerInput,
    WorkerIR,
    WorkerOutput,
)


def _minimal_child_worker(
    *,
    inputs: list[WorkerInput] | None = None,
    outputs: list[WorkerOutput] | None = None,
    steps: list[StepIR] | None = None,
) -> ChildWorkerIR:
    return ChildWorkerIR(
        worker_name="MinimalChild",
        description="Minimal child worker for testing.",
        task_text="Perform subtask.",
        inputs=inputs or [],
        outputs=outputs or [],
        steps=steps or [],
    )


def _worker_ir_with_child(
    child: ChildWorkerIR | None = None,
) -> WorkerIR:
    return WorkerIR(
        worker_name="MainWorker",
        description="Main worker.",
        inputs=[],
        outputs=[],
        main_flow=FlowRef(blocks=[]),
        child_worker_refs=["MinimalChild"] if child else [],
        child_workers=[child] if child else [],
    )


def _render_minimal(worker_ir):
    """Thin helper to call SPLRenderer with all required args."""
    from nl2spl.ir.agent_profile_ir import AgentProfileIR, PersonaIR
    from nl2spl.ir.constraint_ir import ConstraintIR
    from nl2spl.ir.resource_registry_ir import ResourceRegistryIR
    from nl2spl.ir.symbol_table import SymbolTable
    from nl2spl.pipeline.stages.stage11_spl_renderer.renderer import SPLRenderer

    profile = AgentProfileIR(persona=PersonaIR(role="Test agent"))
    resources = ResourceRegistryIR()
    sym = SymbolTable()
    constraints: list[ConstraintIR] = []
    renderer = SPLRenderer()
    return renderer.render(worker_ir, profile, resources, sym, [], constraints)


class TestRendererEmptyWorkerContract:
    """Stage 11 renderer must not error on empty INPUTS / OUTPUTS / MAIN_FLOW."""

    def test_renderer_accepts_child_worker_with_empty_inputs_outputs(self) -> None:
        """Child worker with no inputs/outputs/steps should render without error."""
        child = _minimal_child_worker()
        worker_ir = _worker_ir_with_child(child)

        spl_text, errors, _warnings = _render_minimal(worker_ir)
        assert errors == [], f"Renderer errors: {errors}"

        assert "DEFINE_WORKER" in spl_text, (
            f"Rendered SPL should contain DEFINE_WORKER for child. Got:\n{spl_text[:500]}"
        )

    def test_renderer_no_fallback_command_for_empty_main_flow(self) -> None:
        """Renderer must not synthesize a fallback command when MAIN_FLOW is empty."""
        child = _minimal_child_worker(steps=[])
        worker_ir = _worker_ir_with_child(child)

        spl_text, errors, _warnings = _render_minimal(worker_ir)
        assert errors == [], f"Renderer errors: {errors}"

        # The child's main flow blocks should not contain invented commands
        if "[MAIN_FLOW]" in spl_text:
            main_flow_start = spl_text.index("[MAIN_FLOW]")
            main_flow_end = spl_text.index("[END_MAIN_FLOW]", main_flow_start)
            main_flow_body = spl_text[main_flow_start:main_flow_end]
            # No synthesized COMMAND — must be empty or only block structure
            assert "COMMAND-" not in main_flow_body, (
                f"Empty main flow should not have synthesized commands. "
                f"Got:\n{main_flow_body}"
            )
