"""Regression test for worker handoff structured unpack orphan issue."""

from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.worker_ir import WorkerIR, ChildWorkerIR, FlowRef, WorkerOutput, WorkerInput
from nl2spl.ir.worker_plan_ir import (
    WorkerPlanIR,
    WorkerSpecIR,
    WorkerHandoffIR,
    OutputBindingIR,
    InputBindingIR,
)
from nl2spl.pipeline.executable_gate import ExecutableElementGate
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.ir.resource_registry_ir import ResourceRegistryIR, VariableSpec
from nl2spl.pipeline.stages.stage9_5_normalizer.normalization import NormalizationMixin


class _TestNormalizer(NormalizationMixin):
    """Test normalizer with access to normalization methods."""
    
    def __init__(self):
        self.construct_findings = {}
        self._pruned_variable_names = set()
        self._synthetic_step_counter = 0
    
    def _next_synthetic_step_id(self, used_ids: set[str]) -> str:
        """Generate unique synthetic step ID."""
        while True:
            self._synthetic_step_counter += 1
            step_id = f"st_synthetic_{self._synthetic_step_counter}"
            if step_id not in used_ids:
                used_ids.add(step_id)
                return step_id
    
    def _safe_name(self, name: str) -> str:
        """Convert name to safe identifier."""
        return name.replace("-", "_").replace(" ", "_")


def test_internal_comms_2_regression() -> None:
    """
    Regression test for the issue where a multi-output handoff step was normalized
    into a structured variable, but the executable gate blocked the producer step
    and left the compiler_unpack steps orphaned.
    """
    
    # 1. Setup Symbol Table and Resources
    symbols = SymbolTable()
    resources = ResourceRegistryIR()
    
    inputs = ["user_request", "context"]
    outputs = [
        "draft_communication_artifact",
        "source_evidence_set",
        "assumptions_log",
        "completion_status"
    ]
    
    for inp in inputs:
        symbols.declare(
            name=inp,
            data_type="text",
            source="input",
            description=f"Input: {inp}",
        )
        resources.variables.append(
            VariableSpec(
                name=inp,
                data_type="text",
                required=True,
                description=f"Input: {inp}",
                source="input",
            )
        )
    
    for out in outputs:
        symbols.declare(
            name=out,
            data_type="text",
            source="output",
            description=f"Output: {out}",
        )
        resources.variables.append(
            VariableSpec(
                name=out,
                data_type="text",
                required=True,
                description=f"Output: {out}",
                source="output",
            )
        )
        
    # 2. Setup WorkerPlanIR and initial StepIR
    handoff_id = "handoff_generate_draft_communication"
    
    handoff = WorkerHandoffIR(
        handoff_id=handoff_id,
        from_worker="worker_main",
        to_worker="generate_draft_communication",
        api_ref=None,
        mode="invoke",
        condition_text=None,
        ordering="after",
        input_bindings=[
            InputBindingIR(
                parent_variable=inp,
                child_input=inp,
                required=True,
            )
            for inp in inputs
        ],
        output_bindings=[
            OutputBindingIR(
                child_output=o,
                parent_variable=o,
                required=True,
                merge_strategy="set",
            )
            for o in outputs
        ],
    )
    
    main_worker_spec = WorkerSpecIR(
        worker_id="worker_main",
        worker_name="MainWorker",
        kind="main",
        purpose="Main worker",
    )
    
    child_worker_spec = WorkerSpecIR(
        worker_id="generate_draft_communication",
        worker_name="Worker_generate_draft_communication",
        kind="child",
        purpose="Draft communication",
    )
    
    worker_plan = WorkerPlanIR(
        main_worker_id="worker_main",
        workers=[main_worker_spec, child_worker_spec],
        handoffs=[handoff],
    )
    
    # Simulate the handoff step in Stage 7 before normalizer
    producer_step = StepIR(
        step_id="st_invoke",
        text="Invoke child",
        source_span_ids=[],
        command_type="INVOKE_WORKER",
        handoff_id=handoff_id,
        integration_ref="Worker_generate_draft_communication",
        inputs=inputs,
        outputs=outputs,
        block_ref="blk1",
        flow_ref="main",
    )
    
    child_worker = ChildWorkerIR(
        worker_name="Worker_generate_draft_communication",
        description="Draft communication",
        task_text="Draft communication",
        inputs=[WorkerInput(name=inp, required=True) for inp in inputs],
        outputs=[WorkerOutput(name=o, required=True) for o in outputs],
    )
    
    main_worker = WorkerIR(
        worker_name="MainWorker",
        description="Main worker",
        steps=[producer_step],
        child_workers=[child_worker],
    )

    # 3. Run Normalizer
    normalizer = _TestNormalizer()
    steps = list(main_worker.steps)
    warnings = normalizer._normalize_multi_output_steps(
        resources, symbols, steps, worker_id="worker_main", worker_plan=worker_plan
    )
    main_worker.steps = steps
    
    # The normalizer should have converted the producer step to single structured output
    # and added 4 compiler_unpack steps.
    assert len(main_worker.steps) == 5, f"Expected 5 steps, got {len(main_worker.steps)}"
    structured_result = main_worker.steps[0].outputs[0]
    assert "structured" in structured_result
    
    # Verify metadata was added
    assert "structured_aggregation" in main_worker.steps[0].metadata
    aggregation = main_worker.steps[0].metadata["structured_aggregation"]
    assert aggregation["result_name"] == structured_result
    assert aggregation["original_outputs"] == outputs
    assert "type_name" in aggregation
    
    # 4. Run ExecutableElementGate
    gate = ExecutableElementGate()
    filtered_main_worker, infos, diags = gate.apply(main_worker, worker_plan)
    
    # The gate should allow ALL 5 steps (producer + 4 unpacks)
    # No blocked steps
    blocked_infos = [i for i in infos if not i.renderable]
    assert len(blocked_infos) == 0, f"Steps blocked: {[i.render_block_reason for i in blocked_infos]}"
    
    assert len(filtered_main_worker.steps) == 5
    
    # 5. Verify the order and validity of the final sequence
    # Producer must be first
    assert filtered_main_worker.steps[0].command_type == "INVOKE_WORKER"
    assert filtered_main_worker.steps[0].step_id == "st_invoke"
    
    for i in range(1, 5):
        unpack_step = filtered_main_worker.steps[i]
        assert unpack_step.command_type == "GENERAL_COMMAND"
        assert unpack_step.metadata.get("origin") == "compiler_unpack"
        # Verify it unpacks from the structured result
        assert structured_result in unpack_step.text
        # Verify metadata links to producer
        assert unpack_step.metadata.get("structured_source_step_id") == "st_invoke"
        assert unpack_step.metadata.get("structured_result") == structured_result


def test_unpack_strong_binding_validation() -> None:
    """
    Test that compiler_unpack steps are validated with strong binding to their producer.
    This ensures unpack steps cannot reference arbitrary producers or have mismatched
    inputs/outputs.
    """
    gate = ExecutableElementGate()
    
    # Case 1: Unpack with wrong structured_result (not in producer outputs)
    worker1 = WorkerIR(
        worker_name="MainWorker",
        description="Test",
        main_flow=FlowRef(),
        steps=[
            StepIR(
                "st_producer", "Produce", ["s1"], "GENERAL_COMMAND",
                outputs=["result_structured"],
                metadata={
                    "structured_aggregation": {
                        "result_name": "result_structured",
                        "original_outputs": ["field1"],
                        "type_name": "result_type",
                    }
                },
            ),
            StepIR(
                "st_unpack", "Extract field", [],
                "GENERAL_COMMAND",
                inputs=["wrong_result"],  # Wrong input
                outputs=["field1"],
                metadata={
                    "origin": "compiler_unpack",
                    "structured_source_step_id": "st_producer",
                    "structured_result": "wrong_result",  # Doesn't match producer output
                    "unpacked_output": "field1",
                },
            ),
        ],
    )
    
    filtered1, infos1, diags1 = gate.apply(worker1)
    blocked1 = [i for i in infos1 if not i.renderable and i.step_id == "st_unpack"]
    assert len(blocked1) == 1
    assert "not in producer outputs" in blocked1[0].render_block_reason
    
    # Case 2: Unpack with mismatched inputs
    worker2 = WorkerIR(
        worker_name="MainWorker",
        description="Test",
        main_flow=FlowRef(),
        steps=[
            StepIR(
                "st_producer", "Produce", ["s1"], "GENERAL_COMMAND",
                outputs=["result_structured"],
                metadata={
                    "structured_aggregation": {
                        "result_name": "result_structured",
                        "original_outputs": ["field1"],
                        "type_name": "result_type",
                    }
                },
            ),
            StepIR(
                "st_unpack", "Extract field", [],
                "GENERAL_COMMAND",
                inputs=["result_structured", "extra_input"],  # Wrong number of inputs
                outputs=["field1"],
                metadata={
                    "origin": "compiler_unpack",
                    "structured_source_step_id": "st_producer",
                    "structured_result": "result_structured",
                    "unpacked_output": "field1",
                },
            ),
        ],
    )
    
    filtered2, infos2, diags2 = gate.apply(worker2)
    blocked2 = [i for i in infos2 if not i.renderable and i.step_id == "st_unpack"]
    assert len(blocked2) == 1
    assert "do not match structured_result" in blocked2[0].render_block_reason
    
    # Case 3: Unpack with output not in original_outputs
    worker3 = WorkerIR(
        worker_name="MainWorker",
        description="Test",
        main_flow=FlowRef(),
        steps=[
            StepIR(
                "st_producer", "Produce", ["s1"], "GENERAL_COMMAND",
                outputs=["result_structured"],
                metadata={
                    "structured_aggregation": {
                        "result_name": "result_structured",
                        "original_outputs": ["field1", "field2"],
                        "type_name": "result_type",
                    }
                },
            ),
            StepIR(
                "st_unpack", "Extract field", [],
                "GENERAL_COMMAND",
                inputs=["result_structured"],
                outputs=["field3"],  # Not in original_outputs
                metadata={
                    "origin": "compiler_unpack",
                    "structured_source_step_id": "st_producer",
                    "structured_result": "result_structured",
                    "unpacked_output": "field3",
                },
            ),
        ],
    )
    
    filtered3, infos3, diags3 = gate.apply(worker3)
    blocked3 = [i for i in infos3 if not i.renderable and i.step_id == "st_unpack"]
    assert len(blocked3) == 1
    assert "not in producer original_outputs" in blocked3[0].render_block_reason
    
    # Case 4: Valid unpack passes all checks
    worker4 = WorkerIR(
        worker_name="MainWorker",
        description="Test",
        main_flow=FlowRef(),
        steps=[
            StepIR(
                "st_producer", "Produce", ["s1"], "GENERAL_COMMAND",
                outputs=["result_structured"],
                metadata={
                    "structured_aggregation": {
                        "result_name": "result_structured",
                        "original_outputs": ["field1"],
                        "type_name": "result_type",
                    }
                },
            ),
            StepIR(
                "st_unpack", "Extract field", [],
                "GENERAL_COMMAND",
                inputs=["result_structured"],
                outputs=["field1"],
                metadata={
                    "origin": "compiler_unpack",
                    "structured_source_step_id": "st_producer",
                    "structured_result": "result_structured",
                    "unpacked_output": "field1",
                },
            ),
        ],
    )
    
    filtered4, infos4, diags4 = gate.apply(worker4)
    blocked4 = [i for i in infos4 if not i.renderable]
    assert len(blocked4) == 0, f"Unexpected blocked steps: {[i.render_block_reason for i in blocked4]}"
    assert len(filtered4.steps) == 2
