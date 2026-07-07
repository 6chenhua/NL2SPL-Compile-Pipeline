"""Tests for Phase R4 construct-level renderers."""

import copy

from nl2spl.ir.block_structure_ir import BlockIR
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.worker_ir import WorkerIR
from nl2spl.rendering import (
    RenderableSPLConstructType,
    RenderedFragment,
    RenderMode,
    SPLRenderContext,
    render_spl_construct,
)


def test_step_renderer_general_command() -> None:
    step = StepIR(
        step_id="st1",
        text="Calculate total amount",
        source_span_ids=[],
        command_type="GENERAL_COMMAND",
        inputs=["price", "tax"],
        outputs=["total"],
    )
    context = SPLRenderContext()

    # Render without numbering state (defaults to 1)
    res = render_spl_construct(
        RenderableSPLConstructType.STEP,
        step,
        context,
        RenderMode.STEP,
    )

    assert isinstance(res, RenderedFragment)
    assert res.format == "spl_text"
    assert (
        "COMMAND-1 [COMMAND Calculate total amount based on <REF>price</REF> "
        "and <REF>tax</REF> RESULT total: text SET]" in res.text
    )


def test_step_renderer_context_required() -> None:
    # CALL_API without integration_ref is context_required / invalid
    step = StepIR(
        step_id="st2",
        text="Call external calculator",
        source_span_ids=[],
        command_type="CALL_API",
        integration_ref=None,
    )
    context = SPLRenderContext()

    res = render_spl_construct(
        RenderableSPLConstructType.STEP,
        step,
        context,
        RenderMode.STEP,
    )

    assert len(res.render_diagnostics) == 1
    assert res.render_diagnostics[0].kind == "context_required"


def test_block_renderer_context_required() -> None:
    # Rendering BlockIR requires a parent_worker in context
    block = BlockIR(block_id="b1", block_type="SEQUENTIAL")
    context = SPLRenderContext(parent_worker=None)

    res = render_spl_construct(
        RenderableSPLConstructType.BLOCK,
        block,
        context,
        RenderMode.BLOCK,
    )

    assert len(res.render_diagnostics) == 1
    assert res.render_diagnostics[0].kind == "context_required"


def test_block_renderer_success() -> None:
    block = BlockIR(block_id="b1", block_type="SEQUENTIAL")
    step = StepIR(
        step_id="st1",
        text="Calculate total amount",
        source_span_ids=[],
        command_type="GENERAL_COMMAND",
        block_ref="b1",
    )
    worker = WorkerIR(
        worker_name="Coord",
        description="Desc",
        steps=[step],
    )
    context = SPLRenderContext(parent_worker=worker)

    res = render_spl_construct(
        RenderableSPLConstructType.BLOCK,
        block,
        context,
        RenderMode.BLOCK,
    )

    assert res.format == "spl_text"
    assert "[SEQUENTIAL_BLOCK]" in res.text
    assert "[END_SEQUENTIAL_BLOCK]" in res.text


def test_renderer_immutability() -> None:
    # Verify that rendering does not mutate the input IR objects
    step = StepIR(
        step_id="st1",
        text="Calculate total amount",
        source_span_ids=[],
        command_type="GENERAL_COMMAND",
        inputs=["price", "tax"],
        outputs=["total"],
    )
    original_step = copy.deepcopy(step)
    context = SPLRenderContext()

    render_spl_construct(
        RenderableSPLConstructType.STEP,
        step,
        context,
        RenderMode.STEP,
    )

    assert step == original_step
