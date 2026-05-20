"""WorkerPlanIR - First-class worker boundary planning IR."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from nl2spl.ir.block_structure_ir import BlockStructureIR
from nl2spl.ir.flow_structure_ir import FlowStructureIR
from nl2spl.ir.step_ir import StepIR

BoundaryKind = Literal[
    "explicit_delegation",
    "bounded_subtask",
    "integration_wrapper",
    "complex_control_extraction",
    "loop_body_worker",
    "failure_recovery_protocol",
    "template_or_format_protocol",
    "main_worker",
    "not_a_worker",
    "call_api",
    "constraint",
    "exception_flow",
    "alternative_flow",
]

Signal = Literal[
    "explicit_delegation",
    "bounded_io",
    "multi_step_process",
    "independent_failure_policy",
    "external_integration",
    "provenance_or_audit",
    "evidence_normalization",
    "reuse_potential",
    "testability",
    "complex_control",
]

Risk = Literal[
    "no_clear_input_contract",
    "no_clear_output_contract",
    "no_parent_invocation_point",
    "single_api_call",
    "simple_control_flow",
    "ordinary_sequential_step",
    "policy_or_constraint",
    "alternative_flow",
    "exception_flow",
    "over_fragmentation",
    "unclear_result_handoff",
    "insufficient_semantic_boundary",
    "failure_recovery_protocol",
]


@dataclass
class ContractFieldIR:
    """Worker input or output contract field."""

    name: str
    data_type: str
    required: bool
    description: str
    source: Literal["input", "output", "state", "derived"]


@dataclass
class CandidateTaskUnitIR:
    """Potential worker boundary before a final decision is made."""

    candidate_id: str
    source_span_ids: list[str]
    task_text: str
    purpose: str
    candidate_kind: BoundaryKind
    possible_inputs: list[ContractFieldIR] = field(default_factory=list)
    possible_outputs: list[ContractFieldIR] = field(default_factory=list)
    signals: list[Signal] = field(default_factory=list)
    risks: list[Risk] = field(default_factory=list)


@dataclass
class ControlComplexityRegionIR:
    """Predicted or confirmed region with difficult control structure."""

    region_id: str
    source_span_ids: list[str]
    outer_control: Literal["SEQUENTIAL", "IF", "FOR", "WHILE", "unknown"]
    inner_control: Literal["IF", "FOR", "WHILE", "multiple", "unknown"]
    description: str
    discovery_phase: Literal["predicted", "confirmed"]
    severity: Literal["info", "warning", "error"]
    can_flatten: bool
    can_merge_condition: bool
    can_lift_guard: bool
    suggested_repairs: list[
        Literal[
            "split_blocks",
            "merge_condition",
            "guard_variable",
            "extract_child_worker",
            "compress_to_command",
            "raise_validation_error",
        ]
    ] = field(default_factory=list)


@dataclass
class WorkerBoundaryDecisionIR:
    """Accepted or rejected worker-boundary decision."""

    candidate_id: str
    decision: Literal[
        "extract_child_worker",
        "keep_in_main_worker",
        "compile_as_call_api",
        "compile_as_constraint",
        "compile_as_exception_flow",
        "compile_as_alternative_flow",
        "needs_repair_or_warning",
    ]
    boundary_strength: Literal["strong", "moderate", "weak"]
    boundary_kind: BoundaryKind
    rejection_reason: Risk | None
    reason: str
    evidence: list[Signal] = field(default_factory=list)


@dataclass
class WorkerSpecIR:
    """Concrete worker specification decided before flow assembly."""

    worker_id: str
    worker_name: str
    kind: Literal["main", "child", "api_adapter"]
    purpose: str
    owned_span_ids: list[str] = field(default_factory=list)
    input_contract: list[ContractFieldIR] = field(default_factory=list)
    output_contract: list[ContractFieldIR] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    boundary_kind: BoundaryKind = "main_worker"
    decision_evidence: list[Signal] = field(default_factory=list)
    reason: str = ""


@dataclass
class InputBindingIR:
    """Parent-to-child input binding for a handoff."""

    parent_variable: str
    child_input: str
    required: bool
    default_value: str | None = None


@dataclass
class OutputBindingIR:
    """Child-to-parent output binding for a handoff."""

    child_output: str
    parent_variable: str
    required: bool
    merge_strategy: Literal["set", "append", "merge_struct", "ignore_if_empty"]


@dataclass
class InvokeLocationHintIR:
    """Placement hint for downstream INVOKE_WORKER generation."""

    flow_kind: Literal["main", "alternative", "exception"]
    flow_id: str | None
    after_span_id: str | None
    before_span_id: str | None
    block_hint: Literal["sequential", "if", "for", "while", "unknown"]


@dataclass
class HandoffFailurePolicyIR:
    """Failure behavior when a handoff cannot complete."""

    policy_kind: Literal[
        "propagate_exception",
        "ask_user",
        "continue_with_assumption",
        "block_finalization",
        "return_empty_result",
        "custom",
    ]
    description: str
    source_span_ids: list[str] = field(default_factory=list)


@dataclass
class WorkerHandoffIR:
    """Parent-to-child invocation or direct API call edge."""

    handoff_id: str
    from_worker: str
    to_worker: str | None
    api_ref: str | None
    mode: Literal["invoke", "api_call"]
    condition_text: str | None
    ordering: Literal["before", "after", "conditional", "loop_body"]
    input_bindings: list[InputBindingIR] = field(default_factory=list)
    output_bindings: list[OutputBindingIR] = field(default_factory=list)
    invoke_location_hint: InvokeLocationHintIR = field(
        default_factory=lambda: InvokeLocationHintIR(
            flow_kind="main",
            flow_id=None,
            after_span_id=None,
            before_span_id=None,
            block_hint="unknown",
        )
    )
    failure_policy: HandoffFailurePolicyIR = field(
        default_factory=lambda: HandoffFailurePolicyIR(
            policy_kind="propagate_exception",
            description="Propagate handoff failure to the parent worker.",
        )
    )


@dataclass
class WorkerPlanIR:
    """Global worker boundary plan for the SPL program."""

    main_worker_id: str
    workers: list[WorkerSpecIR] = field(default_factory=list)
    handoffs: list[WorkerHandoffIR] = field(default_factory=list)
    candidates: list[CandidateTaskUnitIR] = field(default_factory=list)
    decisions: list[WorkerBoundaryDecisionIR] = field(default_factory=list)
    rejected_candidates: list[WorkerBoundaryDecisionIR] = field(default_factory=list)
    control_complexity_regions: list[ControlComplexityRegionIR] = field(default_factory=list)
    unassigned_span_ids: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def main_worker(self) -> WorkerSpecIR | None:
        """Return the declared main worker spec, if present."""
        return next(
            (
                worker
                for worker in self.workers
                if worker.worker_id == self.main_worker_id and worker.kind == "main"
            ),
            None,
        )


@dataclass
class WorkerScopedFlowIR:
    """Flow structure scoped to one worker."""

    worker_id: str
    flow: FlowStructureIR


@dataclass
class WorkerFlowPlanIR:
    """Envelope for worker-scoped flow checkpoints."""

    worker_flows: dict[str, FlowStructureIR] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


@dataclass
class WorkerBlockPlanIR:
    """Envelope for worker-scoped block checkpoints."""

    worker_blocks: dict[str, BlockStructureIR] = field(default_factory=dict)
    control_complexity_regions: list[ControlComplexityRegionIR] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class WorkerStepPlanIR:
    """Worker-scoped step extraction result.

    用途：存储按 worker 分组的步骤提取结果。

    字段说明：
    - main_worker_id: 主 worker 的 ID，从 WorkerPlanIR 获取
    - worker_steps: 按 worker_id 分组的步骤列表
    - warnings: 验证警告信息
    """

    main_worker_id: str
    worker_steps: dict[str, list[StepIR]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    @property
    def main_worker_steps(self) -> list[StepIR]:
        """获取主 worker 的步骤。"""
        return self.worker_steps.get(self.main_worker_id, [])

    def get_all_steps(self) -> list[StepIR]:
        """获取所有 worker 的步骤。"""
        all_steps: list[StepIR] = []
        for steps in self.worker_steps.values():
            all_steps.extend(steps)
        return all_steps


@dataclass
class HandoffContractIR:
    """Handoff contract between workers.

    Stores the contract for worker-to-worker handoffs:
    - Input variables passed from parent to child worker
    - Output variables returned from child to parent worker

    Attributes:
        handoff_id: Handoff identifier
        parent_worker_id: Parent worker ID
        child_worker_id: Child worker ID
        input_variables: Input variable contracts
        output_variables: Output variable contracts
    """

    handoff_id: str
    parent_worker_id: str
    child_worker_id: str
    input_variables: list[ContractFieldIR] = field(default_factory=list)
    output_variables: list[ContractFieldIR] = field(default_factory=list)
