"""Unit tests for Stage 10 block fallback utilities."""

from nl2spl.ir.block_structure_ir import BlockIR
from nl2spl.ir.step_ir import StepIR
from nl2spl.pipeline.stages.stage10_worker_assembler import WorkerAssembler


def test_before_span_fallback_block_inserts_before_target_block() -> None:
    """Empty-source handoff fallback should respect before:<span> marker."""
    assembler = WorkerAssembler()
    target_block = BlockIR("b_eval", "SEQUENTIAL", spans=["s19"])
    step = StepIR(
        step_id="st_invoke",
        text="Invoke sourcing worker",
        source_span_ids=[],
        command_type="INVOKE_WORKER",
        block_ref="before:s19",
    )

    blocks = assembler._ensure_renderable_blocks(
        [target_block],
        [step],
        "b_main_fallback",
    )

    assert [block.block_id for block in blocks] == ["b_main_fallback", "b_eval"]
    assert step.block_ref == "b_main_fallback"
