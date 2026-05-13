"""WorkerIR - SPL Worker assembly."""

from __future__ import annotations

from dataclasses import dataclass, field

from nl2spl.ir.block_structure_ir import BlockIR
from nl2spl.ir.step_ir import StepIR


@dataclass
class FlowRef:
    """Flow reference with blocks.

    Attributes:
        blocks: Block IRs in this flow
    """

    blocks: list[BlockIR] = field(default_factory=list)


@dataclass
class AlternativeFlowRef:
    """Alternative flow reference.

    Attributes:
        flow_id: Flow ID
        condition_text: Trigger condition
        blocks: Block IRs in this flow
    """

    flow_id: str
    condition_text: str
    blocks: list[BlockIR] = field(default_factory=list)


@dataclass
class ExceptionFlowRef:
    """Exception flow reference.

    Attributes:
        flow_id: Flow ID
        condition_text: Trigger condition
        blocks: Block IRs in this flow
    """

    flow_id: str
    condition_text: str
    blocks: list[BlockIR] = field(default_factory=list)


@dataclass
class WorkerInput:
    """Worker input specification.

    Attributes:
        name: Variable name
        required: Whether input is required
    """

    name: str
    required: bool = True


@dataclass
class WorkerOutput:
    """Worker output specification.

    Attributes:
        name: Variable name
        required: Whether output is required
    """

    name: str
    required: bool = True


@dataclass
class ChildWorkerIR:
    """Concrete child worker with full flow and steps support.

    Attributes:
        worker_name: Child worker name
        description: Child worker description
        task_text: Command text for the delegated task
        inputs: Input specifications
        outputs: Output specifications
        main_flow: Main flow reference
        alternative_flows: Alternative flow references
        exception_flows: Exception flow references
        api_refs: Referenced API names
        steps: Step IRs in this worker
    """

    worker_name: str
    description: str
    task_text: str
    inputs: list[WorkerInput] = field(default_factory=list)
    outputs: list[WorkerOutput] = field(default_factory=list)
    main_flow: FlowRef = field(default_factory=FlowRef)
    alternative_flows: list[AlternativeFlowRef] = field(default_factory=list)
    exception_flows: list[ExceptionFlowRef] = field(default_factory=list)
    api_refs: list[str] = field(default_factory=list)
    steps: list[StepIR] = field(default_factory=list)


@dataclass
class WorkerIR:
    """Worker assembly result.

    Attributes:
        worker_name: Worker name
        description: Worker description
        inputs: Input specifications
        outputs: Output specifications
        main_flow: Main flow reference
        alternative_flows: Alternative flow references
        exception_flows: Exception flow references
        api_refs: Referenced API names
        child_worker_refs: Child worker names
        child_workers: Concrete child worker definitions
    """

    worker_name: str
    description: str
    inputs: list[WorkerInput] = field(default_factory=list)
    outputs: list[WorkerOutput] = field(default_factory=list)
    main_flow: FlowRef = field(default_factory=FlowRef)
    alternative_flows: list[AlternativeFlowRef] = field(default_factory=list)
    exception_flows: list[ExceptionFlowRef] = field(default_factory=list)
    api_refs: list[str] = field(default_factory=list)
    child_worker_refs: list[str] = field(default_factory=list)
    child_workers: list[ChildWorkerIR] = field(default_factory=list)
