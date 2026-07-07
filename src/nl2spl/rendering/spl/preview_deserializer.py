"""Renderer-local display-only deserializer for TypedRepairPreviewArtifact payloads."""

from typing import Any

from nl2spl.rendering.spl.construct_renderer import RenderableSPLConstructType


def deserialize_construct_from_dict(construct_type: RenderableSPLConstructType, data: dict) -> Any:
    """Safely deserialize a construct dict into display-only read-only value objects.

    This logic is strictly renderer-local and read-only. It MUST NOT perform
    ID allocation, evidence gathering, overlay mutation, validation state
    mutation, or any stateful backend operations.
    """
    from nl2spl.ir.block_structure_ir import BlockIR
    from nl2spl.ir.step_ir import StepIR
    from nl2spl.ir.worker_ir import (
        AlternativeFlowRef,
        ChildWorkerIR,
        ExceptionFlowRef,
        FlowRef,
        WorkerInput,
        WorkerIR,
        WorkerOutput,
    )

    def to_input(d: dict) -> WorkerInput:
        return WorkerInput(
            name=d["name"],
            required=d.get("required", True),
            requiredness=d.get("requiredness", "unspecified"),
        )

    def to_output(d: dict) -> WorkerOutput:
        return WorkerOutput(
            name=d["name"],
            required=d.get("required", True),
            requiredness=d.get("requiredness", "unspecified"),
        )

    def to_step(d: dict) -> StepIR:
        return StepIR(
            step_id=d["step_id"],
            text=d["text"],
            source_span_ids=list(d.get("source_span_ids", [])),
            command_type=d["command_type"],
            inputs=list(d.get("inputs", [])),
            outputs=list(d.get("outputs", [])),
            integration_ref=d.get("integration_ref"),
            flow_ref=d.get("flow_ref", "main"),
            block_ref=d.get("block_ref", ""),
            kind=d.get("kind", "normal"),
            handoff_id=d.get("handoff_id"),
            metadata=dict(d.get("metadata", {})),
        )

    def to_block(d: dict) -> BlockIR:
        return BlockIR(
            block_id=d["block_id"],
            block_type=d["block_type"],
            condition_text=d.get("condition_text"),
            spans=list(d.get("spans", [])),
        )

    def to_flow(d: dict | None) -> FlowRef:
        if not d:
            return FlowRef()
        return FlowRef(blocks=[to_block(b) for b in d.get("blocks", [])])

    def to_alt_flow(d: dict) -> AlternativeFlowRef:
        return AlternativeFlowRef(
            flow_id=d["flow_id"],
            condition_text=d["condition_text"],
            blocks=[to_block(b) for b in d.get("blocks", [])],
        )

    def to_exc_flow(d: dict) -> ExceptionFlowRef:
        return ExceptionFlowRef(
            flow_id=d["flow_id"],
            condition_text=d["condition_text"],
            blocks=[to_block(b) for b in d.get("blocks", [])],
            spans=list(d.get("spans", [])),
        )

    def to_child_worker(d: dict) -> ChildWorkerIR:
        return ChildWorkerIR(
            worker_name=d["worker_name"],
            description=d["description"],
            task_text=d["task_text"],
            inputs=[to_input(i) for i in d.get("inputs", [])],
            outputs=[to_output(o) for o in d.get("outputs", [])],
            main_flow=to_flow(d.get("main_flow")),
            alternative_flows=[to_alt_flow(f) for f in d.get("alternative_flows", [])],
            exception_flows=[to_exc_flow(f) for f in d.get("exception_flows", [])],
            api_refs=list(d.get("api_refs", [])),
            steps=[to_step(s) for s in d.get("steps", [])],
        )

    if construct_type == RenderableSPLConstructType.STEP:
        return to_step(data)
    elif construct_type == RenderableSPLConstructType.BLOCK:
        return to_block(data)
    elif construct_type == RenderableSPLConstructType.EXCEPTION_FLOW:
        return to_exc_flow(data)
    elif construct_type == RenderableSPLConstructType.WORKER:
        return WorkerIR(
            worker_name=data["worker_name"],
            description=data["description"],
            inputs=[to_input(i) for i in data.get("inputs", [])],
            outputs=[to_output(o) for o in data.get("outputs", [])],
            main_flow=to_flow(data.get("main_flow")),
            alternative_flows=[to_alt_flow(f) for f in data.get("alternative_flows", [])],
            exception_flows=[to_exc_flow(f) for f in data.get("exception_flows", [])],
            api_refs=list(data.get("api_refs", [])),
            steps=[to_step(s) for s in data.get("steps", [])],
            scoped_steps=data.get("scoped_steps", False),
            child_worker_refs=list(data.get("child_worker_refs", [])),
            child_workers=[to_child_worker(cw) for cw in data.get("child_workers", [])],
        )
    return None
