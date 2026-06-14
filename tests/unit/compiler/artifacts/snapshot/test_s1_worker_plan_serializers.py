"""S1 plan-layer serializer round-trip tests — using actual IR field names."""

from __future__ import annotations

from nl2spl.compiler.artifacts.snapshot.hash_policy import canonical_json_dumps
from nl2spl.compiler.artifacts.snapshot.serialization.registry import (
    build_default_registry,
)
from nl2spl.ir.block_structure_ir import BlockIR, BlockStructureIR
from nl2spl.ir.flow_structure_ir import DelegationCandidate, FlowStructureIR
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.worker_plan_ir import (
    CandidateTaskUnitIR,
    ContractFieldIR,
    ControlComplexityRegionIR,
    HandoffContractIR,
    HandoffFailurePolicyIR,
    InputBindingIR,
    InvokeLocationHintIR,
    OutputBindingIR,
    WorkerBlockPlanIR,
    WorkerBoundaryDecisionIR,
    WorkerFlowPlanIR,
    WorkerHandoffIR,
    WorkerPlanIR,
    WorkerSpecIR,
    WorkerStepPlanIR,
)


def _rt(registry, obj):
    data = registry.serialize(obj)
    restored = registry.deserialize(data)
    return data, restored


class TestContractFieldIRRoundTrip:
    def test_roundtrip(self) -> None:
        reg = build_default_registry()
        cf = ContractFieldIR(name="draft", data_type="text", required=True,
                             description="Draft content", source="input")
        data, restored = _rt(reg, cf)
        assert data["$type"] == "ContractFieldIR"
        assert restored.name == "draft"

    def test_required_none_preserved(self) -> None:
        reg = build_default_registry()
        cf = ContractFieldIR(name="opt", data_type="text", required=None,
                             description="Optional", source="step")
        _data, restored = _rt(reg, cf)
        assert restored.required is None


class TestBindingIRSerializers:
    def test_input_binding_roundtrip(self) -> None:
        reg = build_default_registry()
        b = InputBindingIR(parent_variable="draft", child_input="payload", required=True)
        data, restored = _rt(reg, b)
        assert data["$type"] == "InputBindingIR"
        assert restored.parent_variable == "draft"

    def test_output_binding_roundtrip(self) -> None:
        reg = build_default_registry()
        b = OutputBindingIR(child_output="result", parent_variable="response", required=True,
                            merge_strategy="set")
        data, restored = _rt(reg, b)
        assert data["$type"] == "OutputBindingIR"
        assert restored.child_output == "result"


class TestInvokeLocationHintRoundTrip:
    def test_roundtrip(self) -> None:
        reg = build_default_registry()
        h = InvokeLocationHintIR(flow_kind="main", flow_id="main", after_span_id="s1",
                                 before_span_id=None, block_hint="sequential")
        data, restored = _rt(reg, h)
        assert data["$type"] == "InvokeLocationHintIR"
        assert restored.block_hint == "sequential"


class TestHandoffFailurePolicyRoundTrip:
    def test_roundtrip(self) -> None:
        reg = build_default_registry()
        p = HandoffFailurePolicyIR(policy_kind="block_finalization",
                                   description="Fail on error")
        data, restored = _rt(reg, p)
        assert data["$type"] == "HandoffFailurePolicyIR"
        assert restored.policy_kind == "block_finalization"


class TestHandoffContractIRRoundTrip:
    def test_roundtrip(self) -> None:
        reg = build_default_registry()
        hc = HandoffContractIR(
            handoff_id="h_001", parent_worker_id="MainWorker", child_worker_id="SubWorker",
        )
        data, restored = _rt(reg, hc)
        assert data["$type"] == "HandoffContractIR"


class TestWorkerSpecIRRoundTrip:
    def test_roundtrip(self) -> None:
        reg = build_default_registry()
        ws = WorkerSpecIR(
            worker_id="MainWorker", worker_name="Main Processor",
            kind="main", purpose="Process input",
            input_contract=[ContractFieldIR(name="draft", data_type="text", required=True,
                                            description="Draft", source="input")],
        )
        data, restored = _rt(reg, ws)
        assert data["$type"] == "WorkerSpecIR"
        assert restored.worker_id == "MainWorker"
        assert len(restored.input_contract) == 1


class TestWorkerHandoffIRRoundTrip:
    def test_roundtrip(self) -> None:
        reg = build_default_registry()
        wh = WorkerHandoffIR(
            handoff_id="h_001", from_worker="MainWorker", to_worker=None,
            api_ref=None, condition_text=None, mode="invoke", ordering="after",
        )
        data, restored = _rt(reg, wh)
        assert data["$type"] == "WorkerHandoffIR"
        assert restored.mode == "invoke"


class TestCandidateTaskUnitIRRoundTrip:
    def test_roundtrip(self) -> None:
        reg = build_default_registry()
        c = CandidateTaskUnitIR(
            candidate_id="c1", source_span_ids=["s1"], task_text="Send email",
            purpose="Email sending", candidate_kind="worker_boundary",
        )
        data, restored = _rt(reg, c)
        assert data["$type"] == "CandidateTaskUnitIR"
        assert restored.task_text == "Send email"


class TestWorkerBoundaryDecisionIRRoundTrip:
    def test_roundtrip(self) -> None:
        reg = build_default_registry()
        d = WorkerBoundaryDecisionIR(
            candidate_id="c1", decision="extract_child_worker",
            boundary_strength="strong", boundary_kind="worker_boundary",
            rejection_reason=None, reason="Different responsibilities",
        )
        data, restored = _rt(reg, d)
        assert data["$type"] == "WorkerBoundaryDecisionIR"
        assert restored.decision == "extract_child_worker"


class TestStepIRRoundTrip:
    def test_roundtrip(self) -> None:
        reg = build_default_registry()
        s = StepIR(step_id="st1", text="Extract draft content", source_span_ids=["s1"],
                   command_type="GENERAL_COMMAND", flow_ref="main")
        data, restored = _rt(reg, s)
        assert data["$type"] == "StepIR"
        assert restored.step_id == "st1"
        assert restored.command_type == "GENERAL_COMMAND"


class TestBlockAndFlowRoundTrip:
    def test_block_ir_roundtrip(self) -> None:
        reg = build_default_registry()
        b = BlockIR(block_id="b1", block_type="SEQUENTIAL", spans=["s1"])
        data, restored = _rt(reg, b)
        assert data["$type"] == "BlockIR"
        assert restored.block_type == "SEQUENTIAL"

    def test_block_structure_ir(self) -> None:
        reg = build_default_registry()
        bs = BlockStructureIR(
            main_flow_blocks=[BlockIR(block_id="b1", block_type="SEQUENTIAL")],
        )
        data, restored = _rt(reg, bs)
        assert data["$type"] == "BlockStructureIR"
        assert len(restored.main_flow_blocks) == 1

    def test_flow_structure_ir(self) -> None:
        reg = build_default_registry()
        fs = FlowStructureIR(main_flow_spans=["s1", "s2"])
        data, restored = _rt(reg, fs)
        assert data["$type"] == "FlowStructureIR"
        assert restored.main_flow_spans == ["s1", "s2"]

    def test_delegation_candidate(self) -> None:
        reg = build_default_registry()
        dc = DelegationCandidate(candidate_id="dc1", spans=["s1"], reason="Sub-task detected",
                                 suggested_type="child_worker")
        data, restored = _rt(reg, dc)
        assert data["$type"] == "DelegationCandidate"


class TestTopLevelPlanRoundTrip:
    def test_worker_plan_ir_minimal(self) -> None:
        reg = build_default_registry()
        wp = WorkerPlanIR(
            main_worker_id="MainWorker",
            workers=[WorkerSpecIR(worker_id="MainWorker", worker_name="Main",
                                  kind="main", purpose="Process")],
        )
        data, restored = _rt(reg, wp)
        assert data["$type"] == "WorkerPlanIR"
        assert restored.main_worker_id == "MainWorker"
        assert len(restored.workers) == 1

    def test_worker_flow_plan_ir(self) -> None:
        reg = build_default_registry()
        fp = WorkerFlowPlanIR()
        fp.worker_flows["MainWorker"] = FlowStructureIR(main_flow_spans=["s1"])
        data, restored = _rt(reg, fp)
        assert data["$type"] == "WorkerFlowPlanIR"
        assert "MainWorker" in restored.worker_flows

    def test_worker_block_plan_ir(self) -> None:
        reg = build_default_registry()
        bp = WorkerBlockPlanIR()
        bp.worker_blocks["MainWorker"] = BlockStructureIR(
            main_flow_blocks=[BlockIR(block_id="b1", block_type="SEQUENTIAL")],
        )
        data, restored = _rt(reg, bp)
        assert data["$type"] == "WorkerBlockPlanIR"
        assert "MainWorker" in restored.worker_blocks

    def test_worker_step_plan_ir(self) -> None:
        reg = build_default_registry()
        sp = WorkerStepPlanIR(main_worker_id="MainWorker")
        sp.worker_steps["MainWorker"] = [
            StepIR(step_id="st1", text="Extract", source_span_ids=["s1"],
                   command_type="GENERAL_COMMAND", flow_ref="main"),
        ]
        data, restored = _rt(reg, sp)
        assert data["$type"] == "WorkerStepPlanIR"
        assert restored.main_worker_id == "MainWorker"
        assert "MainWorker" in restored.worker_steps
        assert len(restored.worker_steps["MainWorker"]) == 1


class TestControlComplexityRegionIRRoundTrip:
    def test_roundtrip(self) -> None:
        reg = build_default_registry()
        r = ControlComplexityRegionIR(
            region_id="cr1", source_span_ids=["s10", "s11"],
            outer_control="IF", inner_control="FOR",
            description="Nested control flow in error handling",
            discovery_phase="confirmed", severity="warning",
            can_flatten=True, can_merge_condition=False, can_lift_guard=True,
            suggested_repairs=["split_blocks", "merge_condition"],
        )
        data, restored = _rt(reg, r)
        assert data["$type"] == "ControlComplexityRegionIR"
        assert restored.region_id == "cr1"
        assert restored.source_span_ids == ["s10", "s11"]
        assert restored.outer_control == "IF"
        assert restored.inner_control == "FOR"
        assert restored.discovery_phase == "confirmed"
        assert restored.severity == "warning"
        assert restored.can_flatten is True
        assert restored.can_merge_condition is False
        assert restored.can_lift_guard is True
        assert restored.suggested_repairs == ["split_blocks", "merge_condition"]


class TestConstructPlanRoundTrip:
    def test_minimal_roundtrip(self) -> None:
        reg = build_default_registry()
        from nl2spl.compiler.construct_plan.model import ConstructPlan

        cp = ConstructPlan(plan_id="cp_1")
        data, restored = _rt(reg, cp)
        assert data["$type"] == "ConstructPlan"
        assert restored.plan_id == "cp_1"

    def test_exception_flow_demand_roundtrip_is_json_safe(self) -> None:
        reg = build_default_registry()
        from nl2spl.compiler.construct_plan.model import (
            ConstructPlan,
            ConstructSlotDemand,
            ExceptionFlowDemand,
        )

        demand = ExceptionFlowDemand(
            demand_id="exc_1",
            slots={
                "condition": ConstructSlotDemand(
                    slot_name="condition",
                    source_span_ids=["s1"],
                    semantic_roles=["exception_condition"],
                ),
                "handler_action": ConstructSlotDemand(
                    slot_name="handler_action",
                    source_span_ids=["s2"],
                    semantic_roles=["exception_handler"],
                    status="missing",
                ),
            },
            condition_span_ids=["s1"],
            handler_span_ids=["s2"],
            condition_text="when external sources fail",
            reserved_span_ids={"s2"},
            source_span_ids=["s1", "s2"],
            metadata={"issue_group_id": "grp_1"},
        )
        cp = ConstructPlan(
            plan_id="cp_exception",
            demands=[demand],
            reserved_span_ids={"s2"},
        )

        data, restored = _rt(reg, cp)

        canonical_json_dumps(data)
        assert data["demands"][0]["$demand_type"] == "ExceptionFlowDemand"
        assert data["demands"][0]["condition_span_ids"] == ["s1"]
        assert restored.demands[0].demand_id == "exc_1"
        assert isinstance(restored.demands[0], ExceptionFlowDemand)
        assert restored.exception_flow_demands()[0].condition_text == (
            "when external sources fail"
        )
