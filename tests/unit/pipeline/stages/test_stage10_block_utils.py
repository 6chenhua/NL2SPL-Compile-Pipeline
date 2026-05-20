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


def test_non_main_flow_step_does_not_create_main_fallback_block() -> None:
    """Alternative/exception steps must not be pulled into main fallback."""
    assembler = WorkerAssembler()
    main_block = BlockIR("b_main", "SEQUENTIAL", spans=["s1"])
    alt_step = StepIR(
        step_id="st_alt",
        text="Revise the draft",
        source_span_ids=["s2"],
        command_type="GENERAL_COMMAND",
        flow_ref="alt_1",
        block_ref="b_alt",
    )

    blocks = assembler._ensure_renderable_blocks(
        [main_block],
        [alt_step],
        "b_main_fallback",
    )

    assert blocks == [main_block]
    assert alt_step.block_ref == "b_alt"


def test_only_non_main_flow_steps_with_no_blocks_get_no_main_fallback() -> None:
    """A main fallback is not a home for alt/exception-only behavior."""
    assembler = WorkerAssembler()
    exc_step = StepIR(
        step_id="st_exc",
        text="Handle error",
        source_span_ids=["s_error"],
        command_type="GENERAL_COMMAND",
        flow_ref="exc_1",
    )

    blocks = assembler._ensure_renderable_blocks(
        [],
        [exc_step],
        "b_main_fallback",
    )

    assert blocks == []
    assert exc_step.block_ref == ""
