"""Deterministic multi-worker rollout fixtures.

These fixtures exercise the WorkerPlanIR migration without calling an LLM.
They intentionally model the cases listed in the Developer E rollout plan.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from nl2spl.ir.agent_profile_ir import AgentProfileIR, Aspect, PersonaIR
from nl2spl.ir.block_structure_ir import BlockIR, BlockStructureIR
from nl2spl.ir.constraint_ir import ConstraintIR
from nl2spl.ir.flow_structure_ir import AlternativeFlow, FlowStructureIR
from nl2spl.ir.resource_registry_ir import (
    APIFunction,
    APISpec,
    ResourceRegistryIR,
    TypeSpec,
    VariableSpec,
)
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.ir.worker_plan_ir import (
    CandidateTaskUnitIR,
    ContractFieldIR,
    ControlComplexityRegionIR,
    HandoffFailurePolicyIR,
    InputBindingIR,
    InvokeLocationHintIR,
    OutputBindingIR,
    WorkerBoundaryDecisionIR,
    WorkerHandoffIR,
    WorkerPlanIR,
    WorkerSpecIR,
)


@dataclass
class MultiWorkerScenario:
    """Complete IR bundle for one rollout scenario."""

    name: str
    raw_text: str
    worker_plan: WorkerPlanIR
    flow: FlowStructureIR
    blocks: BlockStructureIR
    resources: ResourceRegistryIR
    symbols: SymbolTable
    steps: list[StepIR] = field(default_factory=list)
    constraints: list[ConstraintIR] = field(default_factory=list)
    profile: AgentProfileIR = field(default_factory=lambda: AgentProfileIR(
        persona=PersonaIR(role="Internal communications assistant"),
        audience_aspects=[Aspect("InternalUsers", "Employees requesting communication help.")],
    ))
    known_span_ids: set[str] = field(default_factory=set)
    should_validate: bool = True
    expected_validator_errors: tuple[str, ...] = ()


def contract(
    name: str,
    data_type: str = "text",
    required: bool = True,
    source: str = "input",
    description: str | None = None,
) -> ContractFieldIR:
    return ContractFieldIR(
        name=name,
        data_type=data_type,
        required=required,
        description=description or f"{name} field",
        source=source,  # type: ignore[arg-type]
    )


def variable(
    name: str,
    data_type: str = "text",
    source: str = "step",
    required: bool = True,
    description: str | None = None,
) -> VariableSpec:
    return VariableSpec(
        name=name,
        data_type=data_type,
        required=required,
        description=description or f"{name} variable",
        source=source,
    )


def symbols_from(resources: ResourceRegistryIR) -> SymbolTable:
    symbols = SymbolTable()
    for var in resources.variables:
        symbols.declare(var.name, var.data_type, var.source, var.description)
    return symbols


def main_worker(
    owned_spans: list[str],
    inputs: list[ContractFieldIR] | None = None,
    outputs: list[ContractFieldIR] | None = None,
    worker_name: str = "MainWorker",
) -> WorkerSpecIR:
    return WorkerSpecIR(
        worker_id="worker_main",
        worker_name=worker_name,
        kind="main",
        purpose="Coordinate the user-facing request.",
        owned_span_ids=owned_spans,
        input_contract=inputs or [contract("user_request")],
        output_contract=outputs or [contract("final_response", source="output")],
        boundary_kind="main_worker",
        reason="Main worker owns the end-to-end process.",
    )


def source_worker(worker_id: str = "worker_source_gathering") -> WorkerSpecIR:
    return WorkerSpecIR(
        worker_id=worker_id,
        worker_name="SourceGatheringWorker",
        kind="child",
        purpose="Gather approved source evidence and preserve provenance.",
        owned_span_ids=["s3"],
        input_contract=[
            contract("source_request"),
            contract("available_connectors", "List [text]"),
        ],
        output_contract=[
            contract("child_source_package", "SourcePackage", source="output"),
        ],
        boundary_kind="bounded_subtask",
        decision_evidence=["explicit_delegation", "bounded_io", "provenance_or_audit"],
        reason="Source gathering has bounded IO and a concrete handoff.",
    )


def accepted_source_candidate() -> tuple[CandidateTaskUnitIR, WorkerBoundaryDecisionIR]:
    candidate = CandidateTaskUnitIR(
        candidate_id="candidate_source_gathering",
        source_span_ids=["s3"],
        task_text="Delegate bounded source gathering when source evidence is required.",
        purpose="Gather source evidence and provenance.",
        candidate_kind="bounded_subtask",
        possible_inputs=[
            contract("source_request"),
            contract("available_connectors", "List [text]"),
        ],
        possible_outputs=[
            contract("child_source_package", "SourcePackage", source="output"),
        ],
        signals=["explicit_delegation", "bounded_io", "provenance_or_audit"],
    )
    decision = WorkerBoundaryDecisionIR(
        candidate_id="candidate_source_gathering",
        decision="extract_child_worker",
        boundary_strength="strong",
        boundary_kind="bounded_subtask",
        rejection_reason=None,
        reason="Clear IO, concrete invocation point, and explicit delegation.",
        evidence=["explicit_delegation", "bounded_io"],
    )
    return candidate, decision


def source_handoff() -> WorkerHandoffIR:
    return WorkerHandoffIR(
        handoff_id="handoff_source_gathering",
        from_worker="worker_main",
        to_worker="worker_source_gathering",
        api_ref=None,
        mode="invoke",
        condition_text="sources are needed and available",
        ordering="conditional",
        input_bindings=[
            InputBindingIR("user_request", "source_request", True),
            InputBindingIR("available_connectors", "available_connectors", True),
        ],
        output_bindings=[
            OutputBindingIR("child_source_package", "source_evidence_set", True, "set"),
        ],
        invoke_location_hint=InvokeLocationHintIR("main", None, "s2", None, "if"),
        failure_policy=HandoffFailurePolicyIR(
            "block_finalization",
            "Do not finalize when source evidence or provenance cannot be produced.",
            ["s6"],
        ),
    )


def internal_comms_source_gathering() -> MultiWorkerScenario:
    candidate, decision = accepted_source_candidate()
    resources = ResourceRegistryIR(
        variables=[
            variable("user_request", source="input", description="User communication request."),
            variable("available_connectors", "List [text]", "input"),
            variable("source_request", source="input"),
            variable("child_source_package", "SourcePackage", "worker_output"),
            variable("communication_type", source="step"),
            variable("source_evidence_set", "SourcePackage", "output"),
            variable("draft_communication_artifact", source="output"),
            variable("completion_status", source="output"),
        ],
        types=[
            TypeSpec(
                "SourcePackage",
                "structured",
                "{ retrieved_sources: List [text], provenance_log: text }",
            )
        ],
    )
    steps = [
        StepIR(
            "st1",
            "Determine the communication type",
            ["s1"],
            "GENERAL_COMMAND",
            inputs=["user_request"],
            outputs=["communication_type"],
            block_ref="b1",
        ),
        StepIR(
            "st2",
            "Produce the draft communication artifact",
            ["s4"],
            "GENERAL_COMMAND",
            inputs=["user_request", "source_evidence_set"],
            outputs=["draft_communication_artifact"],
            block_ref="b3",
        ),
        StepIR(
            "st3",
            "Set completion status",
            ["s5"],
            "GENERAL_COMMAND",
            inputs=["draft_communication_artifact"],
            outputs=["completion_status"],
            block_ref="b3",
        ),
    ]
    plan = WorkerPlanIR(
        main_worker_id="worker_main",
        workers=[
            main_worker(
                ["s1", "s2", "s4", "s5", "s6", "s7"],
                inputs=[
                    contract("user_request"),
                    contract("available_connectors", "List [text]"),
                ],
                outputs=[
                    contract("draft_communication_artifact", source="output"),
                    contract("source_evidence_set", "SourcePackage", source="output"),
                    contract("completion_status", source="output"),
                ],
            ),
            source_worker(),
        ],
        handoffs=[source_handoff()],
        candidates=[candidate],
        decisions=[decision],
    )
    return MultiWorkerScenario(
        name="internal_comms_source_gathering",
        raw_text=(
            "If sources are needed and available, delegate bounded source gathering; "
            "then produce the draft with provenance."
        ),
        worker_plan=plan,
        flow=FlowStructureIR(
            main_flow_spans=["s1", "s2", "s4", "s5"],
            alternative_flows=[
                AlternativeFlow("alt_revision", "user asks for revision", ["s7"])
            ],
        ),
        blocks=BlockStructureIR(
            main_flow_blocks=[
                BlockIR("b1", "SEQUENTIAL", None, ["s1"]),
                BlockIR("b2", "IF", "sources are needed and available", ["s2"]),
                BlockIR("b3", "SEQUENTIAL", None, ["s4", "s5"]),
            ],
            alternative_flow_blocks={
                "alt_revision": [
                    BlockIR("b4", "SEQUENTIAL", None, ["s7"]),
                ]
            },
        ),
        resources=resources,
        symbols=symbols_from(resources),
        steps=steps,
        constraints=[
            ConstraintIR(
                "c1",
                "Do not invent facts or unseen links.",
                "prohibition",
                ["global"],
                ["s6"],
            )
        ],
        known_span_ids={"s1", "s2", "s3", "s4", "s5", "s6", "s7"},
    )


def simple_single_worker() -> MultiWorkerScenario:
    resources = ResourceRegistryIR(
        variables=[
            variable("user_request", source="input"),
            variable("draft", source="output"),
        ]
    )
    plan = WorkerPlanIR(
        main_worker_id="worker_main",
        workers=[
            main_worker(
                ["s1", "s2"],
                outputs=[contract("draft", source="output")],
            )
        ],
    )
    return MultiWorkerScenario(
        name="simple_single_worker",
        raw_text="Summarize the request and produce a draft.",
        worker_plan=plan,
        flow=FlowStructureIR(main_flow_spans=["s1", "s2"]),
        blocks=BlockStructureIR([BlockIR("b1", "SEQUENTIAL", None, ["s1", "s2"])]),
        resources=resources,
        symbols=symbols_from(resources),
        steps=[
            StepIR(
                "st1",
                "Produce a draft response",
                ["s2"],
                "GENERAL_COMMAND",
                inputs=["user_request"],
                outputs=["draft"],
                block_ref="b1",
            )
        ],
        known_span_ids={"s1", "s2"},
    )


def rejected_decision(
    candidate_id: str,
    span_id: str,
    reason: str,
    decision: str = "keep_in_main_worker",
) -> tuple[CandidateTaskUnitIR, WorkerBoundaryDecisionIR]:
    candidate = CandidateTaskUnitIR(
        candidate_id=candidate_id,
        source_span_ids=[span_id],
        task_text=f"Rejected candidate for {reason}.",
        purpose=f"Rejected candidate for {reason}.",
        candidate_kind="not_a_worker",
        risks=[reason],  # type: ignore[list-item]
    )
    boundary_decision = WorkerBoundaryDecisionIR(
        candidate_id=candidate_id,
        decision=decision,  # type: ignore[arg-type]
        boundary_strength="weak",
        boundary_kind="not_a_worker",
        rejection_reason=reason,  # type: ignore[arg-type]
        reason=f"Rejected because {reason}.",
        evidence=[],
    )
    return candidate, boundary_decision


def explicit_subtask_without_io() -> MultiWorkerScenario:
    scenario = simple_single_worker()
    candidate, decision = rejected_decision(
        "candidate_weak_subtask",
        "s2",
        "no_clear_output_contract",
    )
    scenario.name = "explicit_subtask_without_io"
    scenario.worker_plan.candidates = [candidate]
    scenario.worker_plan.decisions = [decision]
    scenario.worker_plan.rejected_candidates = [decision]
    return scenario


def revision_not_worker() -> MultiWorkerScenario:
    scenario = simple_single_worker()
    candidate, decision = rejected_decision(
        "candidate_revision",
        "s3",
        "alternative_flow",
        "compile_as_alternative_flow",
    )
    scenario.name = "revision_not_worker"
    scenario.known_span_ids.add("s3")
    scenario.flow.alternative_flows = [
        AlternativeFlow("alt_revision", "user asks for revision", ["s3"])
    ]
    scenario.blocks.alternative_flow_blocks = {
        "alt_revision": [BlockIR("b2", "SEQUENTIAL", None, ["s3"])]
    }
    scenario.worker_plan.workers[0].owned_span_ids.append("s3")
    scenario.worker_plan.candidates = [candidate]
    scenario.worker_plan.decisions = [decision]
    scenario.worker_plan.rejected_candidates = [decision]
    return scenario


def single_api_call_not_worker() -> MultiWorkerScenario:
    resources = ResourceRegistryIR(
        variables=[
            variable("api_query", source="input"),
            variable("api_result", source="output"),
        ],
        apis=[
            APISpec(
                "SearchAPI",
                "none",
                "Search API",
                [APIFunction("search", "Search records", return_type="text")],
            )
        ],
    )
    candidate, decision = rejected_decision(
        "candidate_single_api",
        "s1",
        "single_api_call",
        "compile_as_call_api",
    )
    plan = WorkerPlanIR(
        main_worker_id="worker_main",
        workers=[
            main_worker(
                ["s1"],
                inputs=[contract("api_query")],
                outputs=[contract("api_result", source="output")],
            )
        ],
        handoffs=[
            WorkerHandoffIR(
                "handoff_search_api",
                "worker_main",
                None,
                "SearchAPI",
                "api_call",
                "search is needed",
                "conditional",
                input_bindings=[InputBindingIR("api_query", "query", True)],
                output_bindings=[OutputBindingIR("result", "api_result", True, "set")],
                invoke_location_hint=InvokeLocationHintIR("main", None, "s1", None, "if"),
            )
        ],
        candidates=[candidate],
        decisions=[decision],
        rejected_candidates=[decision],
    )
    return MultiWorkerScenario(
        name="single_api_call_not_worker",
        raw_text="Call the search API once when search is needed.",
        worker_plan=plan,
        flow=FlowStructureIR(main_flow_spans=["s1"]),
        blocks=BlockStructureIR([BlockIR("b1", "IF", "search is needed", ["s1"])]),
        resources=resources,
        symbols=symbols_from(resources),
        known_span_ids={"s1"},
    )


def api_adapter_with_provenance() -> MultiWorkerScenario:
    resources = ResourceRegistryIR(
        variables=[
            variable("user_request", source="input"),
            variable("adapter_request", source="input"),
            variable("adapter_evidence", source="worker_output"),
            variable("normalized_evidence", source="output"),
        ]
    )
    adapter = WorkerSpecIR(
        "worker_evidence_adapter",
        "EvidenceAdapterWorker",
        "api_adapter",
        "Fetch, normalize, and preserve provenance for evidence.",
        owned_span_ids=["s2"],
        input_contract=[contract("adapter_request")],
        output_contract=[contract("adapter_evidence", source="output")],
        boundary_kind="integration_wrapper",
        decision_evidence=["external_integration", "provenance_or_audit"],
    )
    plan = WorkerPlanIR(
        main_worker_id="worker_main",
        workers=[
            main_worker(
                ["s1"],
                outputs=[contract("normalized_evidence", source="output")],
            ),
            adapter,
        ],
        handoffs=[
            WorkerHandoffIR(
                "handoff_evidence_adapter",
                "worker_main",
                "worker_evidence_adapter",
                None,
                "invoke",
                "evidence normalization is needed",
                "conditional",
                input_bindings=[InputBindingIR("user_request", "adapter_request", True)],
                output_bindings=[
                    OutputBindingIR("adapter_evidence", "normalized_evidence", True, "set")
                ],
                invoke_location_hint=InvokeLocationHintIR("main", None, "s1", None, "if"),
            )
        ],
    )
    return MultiWorkerScenario(
        name="api_adapter_with_provenance",
        raw_text="Use an adapter worker to normalize evidence and preserve provenance.",
        worker_plan=plan,
        flow=FlowStructureIR(main_flow_spans=["s1"]),
        blocks=BlockStructureIR(
            [BlockIR("b1", "IF", "evidence normalization is needed", ["s1"])]
        ),
        resources=resources,
        symbols=symbols_from(resources),
        known_span_ids={"s1", "s2"},
    )


def api_call_vs_api_adapter() -> tuple[MultiWorkerScenario, MultiWorkerScenario]:
    return single_api_call_not_worker(), api_adapter_with_provenance()


def flattenable_nested_control() -> MultiWorkerScenario:
    scenario = simple_single_worker()
    scenario.name = "flattenable_nested_control"
    scenario.raw_text = "Do A. If sources are needed and available, retrieve them. Then draft."
    scenario.worker_plan.control_complexity_regions = [
        ControlComplexityRegionIR(
            "region_flattenable",
            ["s1", "s2"],
            "SEQUENTIAL",
            "IF",
            "A simple condition can be represented as a top-level IF block.",
            "predicted",
            "info",
            can_flatten=True,
            can_merge_condition=False,
            can_lift_guard=False,
            suggested_repairs=["split_blocks"],
        )
    ]
    scenario.flow = FlowStructureIR(main_flow_spans=["s1", "s2"])
    scenario.blocks = BlockStructureIR(
        [
            BlockIR("b1", "SEQUENTIAL", None, ["s1"]),
            BlockIR("b2", "IF", "sources are needed and available", ["s2"]),
        ]
    )
    scenario.steps = [
        StepIR("st1", "Do the first action", ["s1"], "GENERAL_COMMAND", inputs=["user_request"]),
        StepIR(
            "st2",
            "Produce a draft response",
            ["s2"],
            "GENERAL_COMMAND",
            inputs=["user_request"],
            outputs=["draft"],
            block_ref="b2",
        ),
    ]
    return scenario


def loop_body_child_worker() -> MultiWorkerScenario:
    resources = ResourceRegistryIR(
        variables=[
            variable("topics", "List [text]", "input"),
            variable("topic_evidence", "List [text]", "output"),
            variable("topic", source="step"),
            variable("child_topic_evidence", source="worker_output"),
        ]
    )
    child = WorkerSpecIR(
        "worker_topic_evidence",
        "TopicEvidenceWorker",
        "child",
        "Validate one topic and gather evidence.",
        owned_span_ids=["s2"],
        input_contract=[contract("topic")],
        output_contract=[contract("child_topic_evidence", source="output")],
        boundary_kind="loop_body_worker",
    )
    plan = WorkerPlanIR(
        main_worker_id="worker_main",
        workers=[
            main_worker(
                ["s1"],
                inputs=[contract("topics", "List [text]")],
                outputs=[contract("topic_evidence", "List [text]", source="output")],
            ),
            child,
        ],
        handoffs=[
            WorkerHandoffIR(
                "handoff_topic_evidence",
                "worker_main",
                "worker_topic_evidence",
                None,
                "invoke",
                "for each requested topic",
                "loop_body",
                input_bindings=[InputBindingIR("topic", "topic", True)],
                output_bindings=[
                    OutputBindingIR("child_topic_evidence", "topic_evidence", True, "append")
                ],
                invoke_location_hint=InvokeLocationHintIR("main", None, "s1", None, "for"),
            )
        ],
    )
    return MultiWorkerScenario(
        name="loop_body_child_worker",
        raw_text="For each requested topic, validate the topic and gather evidence.",
        worker_plan=plan,
        flow=FlowStructureIR(main_flow_spans=["s1"]),
        blocks=BlockStructureIR([BlockIR("b1", "FOR", "each requested topic", ["s1"])]),
        resources=resources,
        symbols=symbols_from(resources),
        known_span_ids={"s1", "s2"},
    )


def same_child_multiple_handoffs() -> MultiWorkerScenario:
    resources = ResourceRegistryIR(
        variables=[
            variable("user_request", source="input"),
            variable("available_connectors", "List [text]", "input"),
            variable("source_request", source="input"),
            variable("child_source_package", "SourcePackage", "worker_output"),
            variable("primary_source_evidence", "SourcePackage", "output"),
            variable("recovery_source_evidence", "SourcePackage", "output"),
        ],
        types=[
            TypeSpec(
                "SourcePackage",
                "structured",
                "{ retrieved_sources: List [text], provenance_log: text }",
            )
        ],
    )
    child = source_worker()
    plan = WorkerPlanIR(
        main_worker_id="worker_main",
        workers=[
            main_worker(
                ["s1", "s2", "s4"],
                inputs=[
                    contract("user_request"),
                    contract("available_connectors", "List [text]"),
                ],
                outputs=[
                    contract("primary_source_evidence", "SourcePackage", source="output"),
                    contract("recovery_source_evidence", "SourcePackage", source="output"),
                ],
            ),
            child,
        ],
        handoffs=[
            WorkerHandoffIR(
                "handoff_primary_sources",
                "worker_main",
                "worker_source_gathering",
                None,
                "invoke",
                "primary sources are needed",
                "conditional",
                input_bindings=[
                    InputBindingIR("user_request", "source_request", True),
                    InputBindingIR("available_connectors", "available_connectors", True),
                ],
                output_bindings=[
                    OutputBindingIR(
                        "child_source_package",
                        "primary_source_evidence",
                        True,
                        "set",
                    )
                ],
                invoke_location_hint=InvokeLocationHintIR("main", None, "s2", None, "if"),
            ),
            WorkerHandoffIR(
                "handoff_recovery_sources",
                "worker_main",
                "worker_source_gathering",
                None,
                "invoke",
                "recovery sources are needed",
                "conditional",
                input_bindings=[
                    InputBindingIR("user_request", "source_request", True),
                    InputBindingIR("available_connectors", "available_connectors", True),
                ],
                output_bindings=[
                    OutputBindingIR(
                        "child_source_package",
                        "recovery_source_evidence",
                        True,
                        "set",
                    )
                ],
                invoke_location_hint=InvokeLocationHintIR("main", None, "s4", None, "if"),
            ),
        ],
    )
    return MultiWorkerScenario(
        name="same_child_multiple_handoffs",
        raw_text=(
            "Invoke source gathering once for primary evidence and again for "
            "recovery evidence."
        ),
        worker_plan=plan,
        flow=FlowStructureIR(main_flow_spans=["s1", "s2", "s4"]),
        blocks=BlockStructureIR(
            [
                BlockIR("b1", "SEQUENTIAL", None, ["s1"]),
                BlockIR("b2", "IF", "primary sources are needed", ["s2"]),
                BlockIR("b3", "IF", "recovery sources are needed", ["s4"]),
            ]
        ),
        resources=resources,
        symbols=symbols_from(resources),
        steps=[
            StepIR(
                "st1",
                "Classify the request",
                ["s1"],
                "GENERAL_COMMAND",
                inputs=["user_request"],
                block_ref="b1",
            )
        ],
        known_span_ids={"s1", "s2", "s3", "s4"},
    )


def unresolved_invoke_worker_error() -> MultiWorkerScenario:
    scenario = internal_comms_source_gathering()
    scenario.name = "unresolved_invoke_worker_error"
    scenario.steps.append(
        StepIR(
            "st_unresolved",
            "Invoke a placeholder worker",
            ["s99"],
            "INVOKE_WORKER",
            inputs=["user_request"],
            outputs=["source_evidence_set"],
            integration_ref="Worker",
            kind="invoke",
        )
    )
    scenario.known_span_ids.add("s99")
    scenario.should_validate = False
    scenario.expected_validator_errors = ("no concrete child worker",)
    return scenario


def unused_child_worker_error() -> MultiWorkerScenario:
    scenario = internal_comms_source_gathering()
    scenario.name = "unused_child_worker_error"
    unused = WorkerSpecIR(
        "worker_unused",
        "UnusedWorker",
        "child",
        "This worker has no parent handoff.",
        owned_span_ids=["s8"],
        input_contract=[contract("unused_input")],
        output_contract=[contract("unused_output", source="output")],
        boundary_kind="bounded_subtask",
    )
    scenario.worker_plan.workers.append(unused)
    scenario.known_span_ids.add("s8")
    scenario.should_validate = False
    scenario.expected_validator_errors = ("Non-main worker has no handoff",)
    return scenario


def worker_plan_validator_errors() -> MultiWorkerScenario:
    scenario = unused_child_worker_error()
    scenario.name = "worker_plan_validator_errors"
    scenario.worker_plan.main_worker_id = "worker_missing"
    scenario.expected_validator_errors = (
        "main_worker_id does not reference a worker",
        "Non-main worker has no handoff",
    )
    return scenario


def duplicate_behavior_span_ownership() -> MultiWorkerScenario:
    scenario = internal_comms_source_gathering()
    scenario.name = "duplicate_behavior_span_ownership"
    scenario.worker_plan.workers[0].owned_span_ids.append("s3")
    scenario.should_validate = False
    scenario.expected_validator_errors = ("Duplicate behavior-span ownership",)
    return scenario


def duplicate_handoff_id() -> MultiWorkerScenario:
    scenario = same_child_multiple_handoffs()
    scenario.name = "duplicate_handoff_id"
    scenario.worker_plan.handoffs[1].handoff_id = scenario.worker_plan.handoffs[0].handoff_id
    scenario.should_validate = False
    scenario.expected_validator_errors = ("Duplicate handoff_id",)
    return scenario
