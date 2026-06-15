"""Unit tests for ExecutableElementGate (TODO 6)."""

from __future__ import annotations

from nl2spl.ir.diagnostics import StepRenderInfo
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.worker_ir import (
    ChildWorkerIR,
    ExceptionFlowRef,
    FlowRef,
    WorkerInput,
    WorkerOutput,
    WorkerIR,
)
from nl2spl.ir.worker_plan_ir import (
    ContractFieldIR,
    InputBindingIR,
    InvokeLocationHintIR,
    OutputBindingIR,
    WorkerHandoffIR,
    WorkerPlanIR,
    WorkerSpecIR,
)
from nl2spl.pipeline.executable_gate import ExecutableElementGate


class TestOriginClassification:
    """Tests for step origin classification."""

    def test_source_spans_mean_source_backed(self) -> None:
        gate = ExecutableElementGate()
        step = StepIR("st1", "Do work", ["s1"], "GENERAL_COMMAND")
        assert gate.classify_origin(step) == "source_backed"

    def test_handoff_id_means_handoff_generated(self) -> None:
        gate = ExecutableElementGate()
        step = StepIR("st1", "Invoke", [], "INVOKE_WORKER", handoff_id="h1")
        assert gate.classify_origin(step) == "handoff_generated"

    def test_compiler_unpack_is_compiler_synthetic(self) -> None:
        gate = ExecutableElementGate()
        step = StepIR(
            "st_unpack", "Extract field", [],
            "GENERAL_COMMAND", metadata={"origin": "compiler_unpack"},
        )
        assert gate.classify_origin(step) == "compiler_synthetic"

    def test_empty_source_no_handoff_is_assumed(self) -> None:
        gate = ExecutableElementGate()
        step = StepIR("st1", "Synthetic", [], "GENERAL_COMMAND")
        assert gate.classify_origin(step) == "assumed"


class TestRenderability:
    """Tests for renderability rules."""

    def test_source_backed_is_renderable(self) -> None:
        gate = ExecutableElementGate()
        step = StepIR("st1", "Do work", ["s1"], "GENERAL_COMMAND")
        ok, reason = gate.is_renderable(step, "source_backed", {}, set(), {})
        assert ok is True
        assert reason is None

    def test_assumed_is_not_renderable(self) -> None:
        gate = ExecutableElementGate()
        step = StepIR("st1", "Synthetic", [], "GENERAL_COMMAND")
        ok, reason = gate.is_renderable(step, "assumed", {}, set(), {})
        assert ok is False
        assert reason is not None

    def test_compiler_unpack_is_renderable(self) -> None:
        gate = ExecutableElementGate()
        step = StepIR(
            "st_unpack", "Extract", [],
            "GENERAL_COMMAND", metadata={"origin": "compiler_unpack"},
        )
        ok, _ = gate.is_renderable(step, "compiler_synthetic", {}, set(), {})
        assert ok is True

    def _invoke_handoff(self, **kw: object) -> WorkerHandoffIR:
        defaults: dict[str, object] = dict(
            handoff_id="h1",
            from_worker="w_main",
            to_worker="w_child",
            api_ref=None,
            mode="invoke",
            condition_text=None,
            ordering="after",
            input_bindings=[
                InputBindingIR("req", "child_req", True),
            ],
            output_bindings=[
                OutputBindingIR("child_out", "out", True, "set"),
            ],
            invoke_location_hint=InvokeLocationHintIR("main", None, "s1", None, "if"),
        )
        defaults.update(kw)
        return WorkerHandoffIR(**defaults)  # type: ignore[arg-type]

    def test_handoff_invoke_target_mismatch_not_renderable(self) -> None:
        gate = ExecutableElementGate()
        step = StepIR(
            "st1", "Invoke", [], "INVOKE_WORKER",
            handoff_id="h1", integration_ref="OtherWorker",
            inputs=["req"], outputs=["out"],
        )
        h = self._invoke_handoff()  # to_worker = "w_child"
        ok, reason = gate.is_renderable(
            step, "handoff_generated", {"h1": h},
            {"Child"}, {"w_child": "Child"},  # maps to "Child", not "OtherWorker"
        )
        assert ok is False
        assert "does not match handoff to_worker target" in (reason or "")

    def test_handoff_to_worker_unknown_is_blocked(self) -> None:
        gate = ExecutableElementGate()
        step = StepIR(
            "st1", "Invoke", [], "INVOKE_WORKER",
            handoff_id="h1", integration_ref="Child",
            inputs=["req"], outputs=["out"],
        )
        h = self._invoke_handoff(to_worker="ghost_worker")
        ok, reason = gate.is_renderable(
            step, "handoff_generated", {"h1": h},
            {"Child"}, {"w_child": "Child"},
        )
        assert ok is False
        assert "not found in worker plan" in (reason or "")

    def test_handoff_to_worker_empty_is_blocked(self) -> None:
        gate = ExecutableElementGate()
        step = StepIR(
            "st1", "Invoke", [], "INVOKE_WORKER",
            handoff_id="h1", integration_ref="Child",
            inputs=["req"], outputs=["out"],
        )
        h = self._invoke_handoff(to_worker=None)
        ok, reason = gate.is_renderable(
            step, "handoff_generated", {"h1": h},
            {"Child"}, {"w_child": "Child"},
        )
        assert ok is False
        assert "no to_worker" in (reason or "")

    def test_handoff_invoke_without_io_bindings_not_renderable(self) -> None:
        gate = ExecutableElementGate()
        step = StepIR(
            "st1", "Invoke", [], "INVOKE_WORKER",
            handoff_id="h1", integration_ref="Child",
            inputs=["req"], outputs=["wrong_output"],
        )
        h = self._invoke_handoff()
        ok, reason = gate.is_renderable(
            step, "handoff_generated", {"h1": h},
            {"Child"}, {"w_child": "Child"},
        )
        assert ok is False
        assert "do not match handoff bindings" in (reason or "")

    def test_handoff_invoke_with_valid_contract_is_renderable(self) -> None:
        gate = ExecutableElementGate()
        step = StepIR(
            "st1", "Invoke", [], "INVOKE_WORKER",
            handoff_id="h1", integration_ref="Child",
            inputs=["req"], outputs=["out"],
        )
        h = self._invoke_handoff()
        ok, reason = gate.is_renderable(
            step, "handoff_generated", {"h1": h},
            {"Child"}, {"w_child": "Child"},
        )
        assert ok is True
        assert reason is None

    def test_handoff_invoke_with_multiple_outputs_is_renderable(self) -> None:
        gate = ExecutableElementGate()
        step = StepIR(
            "st1",
            "Invoke",
            [],
            "INVOKE_WORKER",
            handoff_id="h1",
            integration_ref="Child",
            inputs=["req"],
            outputs=["out_one", "out_two"],
        )
        handoff = self._invoke_handoff(
            output_bindings=[
                OutputBindingIR("child_one", "out_one", True, "set"),
                OutputBindingIR("child_two", "out_two", True, "set"),
            ]
        )

        ok, reason = gate.is_renderable(
            step,
            "handoff_generated",
            {"h1": handoff},
            {"Child"},
            {"w_child": "Child"},
        )

        assert ok is True
        assert reason is None

    def test_handoff_mode_mismatch_blocks_rendering(self) -> None:
        gate = ExecutableElementGate()
        step = StepIR(
            "st1", "Call API", [], "CALL_API",
            handoff_id="h1", integration_ref="SearchAPI",
        )
        h = self._invoke_handoff(mode="invoke")  # step is CALL_API but handoff is invoke
        ok, reason = gate.is_renderable(
            step, "handoff_generated", {"h1": h}, set(), {},
        )
        assert ok is False
        assert "mode" in (reason or "")

    def test_handoff_structured_outputs_match_rejects_missing_type_name(self) -> None:
        gate = ExecutableElementGate()
        step = StepIR(
            "st1", "Invoke", [], "INVOKE_WORKER",
            handoff_id="h1", integration_ref="Child",
            inputs=["req"], outputs=["result_structured"],
            metadata={
                "structured_aggregation": {
                    "result_name": "result_structured",
                    "original_outputs": ["out"],
                    # type_name is missing
                }
            }
        )
        h = self._invoke_handoff()
        ok, reason = gate.is_renderable(
            step, "handoff_generated", {"h1": h},
            {"Child"}, {"w_child": "Child"},
        )
        assert ok is False

    def test_handoff_structured_outputs_match_rejects_mismatched_result_name(self) -> None:
        gate = ExecutableElementGate()
        step = StepIR(
            "st1", "Invoke", [], "INVOKE_WORKER",
            handoff_id="h1", integration_ref="Child",
            inputs=["req"], outputs=["wrong_result_name"],
            metadata={
                "structured_aggregation": {
                    "result_name": "result_structured",
                    "type_name": "result_structured_type",
                    "original_outputs": ["out"],
                }
            }
        )
        h = self._invoke_handoff()
        ok, reason = gate.is_renderable(
            step, "handoff_generated", {"h1": h},
            {"Child"}, {"w_child": "Child"},
        )
        assert ok is False


class TestGateFiltering:
    """Integration-level tests for gate.apply()."""

    def _plan_with_handoff(self) -> WorkerPlanIR:
        return WorkerPlanIR(
            main_worker_id="w_main",
            workers=[
                WorkerSpecIR(
                    "w_main", "MainWorker", "main", "Main",
                    owned_span_ids=["s1"],
                    input_contract=[
                        ContractFieldIR("req", "text", True, "Request", "input"),
                    ],
                    output_contract=[
                        ContractFieldIR("out", "text", True, "Output", "output"),
                    ],
                    boundary_kind="main_worker",
                ),
            ],
            handoffs=[],
        )

    def test_source_backed_steps_are_preserved(self) -> None:
        gate = ExecutableElementGate()
        worker = WorkerIR(
            worker_name="MainWorker",
            description="Test",
            main_flow=FlowRef(),
            steps=[StepIR("st1", "Do work", ["s1"], "GENERAL_COMMAND")],
        )

        filtered, infos, diags = gate.apply(worker)
        assert len(filtered.steps) == 1
        assert filtered.steps[0].step_id == "st1"
        assert len(diags) == 0
        assert all(i.renderable for i in infos)

    def test_assumed_steps_are_blocked(self) -> None:
        gate = ExecutableElementGate()
        worker = WorkerIR(
            worker_name="MainWorker",
            description="Test",
            main_flow=FlowRef(),
            steps=[
                StepIR("st1", "Do work", ["s1"], "GENERAL_COMMAND"),
                StepIR("st_synth", "Synthetic", [], "GENERAL_COMMAND"),
            ],
        )

        filtered, infos, diags = gate.apply(worker)
        assert len(filtered.steps) == 1
        assert filtered.steps[0].step_id == "st1"
        blocked = [i for i in infos if not i.renderable]
        assert len(blocked) == 1
        assert blocked[0].step_id == "st_synth"
        assert blocked[0].origin == "assumed"
        # Gate no longer emits diagnostics for blocked steps; that is
        # post-normalize IRS responsibility.

    def test_compiler_unpack_passes_through(self) -> None:
        gate = ExecutableElementGate()
        worker = WorkerIR(
            worker_name="MainWorker",
            description="Test",
            main_flow=FlowRef(),
            steps=[
                StepIR(
                    "st1", "Do work", ["s1"], "GENERAL_COMMAND",
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
                        "structured_source_step_id": "st1",
                        "structured_result": "result_structured",
                        "unpacked_output": "field1",
                    },
                ),
            ],
        )

        filtered, infos, diags = gate.apply(worker)
        assert len(filtered.steps) == 2
        assert len(diags) == 0

    def test_compiler_unpack_blocked_when_source_step_not_renderable(self) -> None:
        gate = ExecutableElementGate()
        worker = WorkerIR(
            worker_name="MainWorker",
            description="Test",
            main_flow=FlowRef(),
            steps=[
                StepIR("st1", "Assumed step", [], "GENERAL_COMMAND"),  # not renderable
                StepIR(
                    "st_unpack", "Extract field", [],
                    "GENERAL_COMMAND", metadata={
                        "origin": "compiler_unpack",
                        "structured_source_step_id": "st1",
                        "structured_result": "result_structured",
                        "unpacked_output": "field1",
                    },
                ),
            ],
        )

        filtered, infos, diags = gate.apply(worker)
        assert len(filtered.steps) == 0
        
        blocked_infos = [i for i in infos if not i.renderable]
        assert len(blocked_infos) == 2
        
        unpack_info = next(i for i in blocked_infos if i.step_id == "st_unpack")
        assert "source step is not renderable" in (unpack_info.render_block_reason or "")
        
        # Check diagnostic
        unpack_diag = next(d for d in diags if d.diagnostic_id == "unpack_blocked_st_unpack")
        assert unpack_diag.severity == "warning"

    def test_child_worker_steps_also_filtered(self) -> None:
        gate = ExecutableElementGate()
        worker = WorkerIR(
            worker_name="MainWorker",
            description="Parent",
            main_flow=FlowRef(),
            child_workers=[
                ChildWorkerIR(
                    worker_name="Child",
                    description="Child",
                    task_text="Child task",
                    steps=[
                        StepIR("st_child_real", "Real work", ["s_child"], "GENERAL_COMMAND"),
                        StepIR("st_child_synth", "Synthetic", [], "GENERAL_COMMAND"),
                    ],
                )
            ],
        )

        filtered, infos, diags = gate.apply(worker)
        child = filtered.child_workers[0]
        assert len(child.steps) == 1
        assert child.steps[0].step_id == "st_child_real"
        blocked = [i for i in infos if not i.renderable]
        assert any("st_child_synth" == i.step_id for i in blocked)

    def test_child_worker_renderable_steps_appear_in_infos(self) -> None:
        """P2 fix: child worker renderable steps must be in StepRenderInfo
        alongside blocked steps, so report/completeness can show which
        child steps were allowed through."""
        gate = ExecutableElementGate()
        worker = WorkerIR(
            worker_name="MainWorker",
            description="Parent",
            main_flow=FlowRef(),
            child_workers=[
                ChildWorkerIR(
                    worker_name="Child",
                    description="Child",
                    task_text="Child task",
                    steps=[
                        StepIR("st_ok", "Real work", ["s_ok"], "GENERAL_COMMAND"),
                        StepIR("st_bad", "Synthetic", [], "GENERAL_COMMAND"),
                    ],
                )
            ],
        )
        filtered, infos, diags = gate.apply(worker)
        # Both renderable and blocked child steps appear in infos
        renderable_ids = {i.step_id for i in infos if i.renderable}
        blocked_ids = {i.step_id for i in infos if not i.renderable}
        assert "st_ok" in renderable_ids, f"renderable child step missing from infos"
        assert "st_bad" in blocked_ids, f"blocked child step missing from infos"
        # Filtered worker still has only the real step
        child = filtered.child_workers[0]
        assert len(child.steps) == 1
        assert child.steps[0].step_id == "st_ok"

    def test_vague_handler_gate_chain(self) -> None:
        """Gate filters assumed handler step from exception flow + re-emits
        missing_handler after the handler is removed."""
        gate = ExecutableElementGate()
        worker = WorkerIR(
            worker_name="MainWorker",
            description="Test",
            main_flow=FlowRef(),
            exception_flows=[
                ExceptionFlowRef(
                    flow_id="exc_1",
                    condition_text="Handle failures properly.",
                    blocks=[],
                )
            ],
            steps=[
                StepIR("st1", "Do work", ["s1"], "GENERAL_COMMAND"),
                StepIR(
                    "st_fail", "Handle failures", [], "GENERAL_COMMAND",
                    flow_ref="exc_1",
                ),
            ],
        )

        filtered, infos, diags = gate.apply(worker)

        # The assumed handler step is removed from filtered steps
        assert len(filtered.steps) == 1
        assert filtered.steps[0].step_id == "st1"
        assert "st_fail" not in {s.step_id for s in filtered.steps}

        # The step is in render_info as non-renderable
        blocked = [i for i in infos if not i.renderable]
        assert any(i.step_id == "st_fail" and i.origin == "assumed" for i in blocked)

        # Gate no longer emits assumed_command_not_renderable;
        # that is post-normalize IRS responsibility.
        # The step is filtered from worker.steps and recorded in render_info.

        # Post-gate missing_handler is emitted because the assumed handler
        # was filtered out, leaving exc_1 with no renderable handler step
        post_gate_mh = [d for d in diags if d.kind == "missing_handler"]
        assert any("exc_1" in d.target_ref for d in post_gate_mh), (
            f"Expected post-gate missing_handler for exc_1, "
            f"got {[d.target_ref for d in post_gate_mh]}"
        )

    def test_pseudo_handler_no_duplicate_post_gate_missing_handler(self) -> None:
        """Pseudo-handler (marked by Stage 9.5 metadata) does NOT cause
        gate to emit duplicate missing_handler."""
        gate = ExecutableElementGate()
        worker = WorkerIR(
            worker_name="MainWorker",
            description="Test",
            main_flow=FlowRef(),
            exception_flows=[
                ExceptionFlowRef(
                    flow_id="exc_1",
                    condition_text="If required slots remain missing.",
                    blocks=[],
                )
            ],
            steps=[
                StepIR("st1", "Do work", ["s1"], "GENERAL_COMMAND"),
                # Pseudo-handler: Stage 9.5 would have marked this
                StepIR(
                    "st_pseudo",
                    "Check if required slots remain missing",
                    ["s18"],
                    "GENERAL_COMMAND",
                    flow_ref="exc_1",
                    metadata={"pseudo_exception_handler": "true"},
                ),
            ],
        )
        # Gate runs after Stage 9.5 -- pseudo-handler is in worker.steps
        # but marked with metadata.
        filtered, infos, diags = gate.apply(worker)

        # The pseudo-handler should still be in pre-gate steps BUT
        # excluded from pre_gate_handler_flows. So no post-gate
        # missing_handler for exc_1.
        post_gate_mh = [d for d in diags if d.kind == "missing_handler"]
        exc_1_mh = [d for d in post_gate_mh if "exc_1" in (d.target_ref or "")]
        assert len(exc_1_mh) == 0, (
            f"Pseudo-handler should NOT cause post-gate missing_handler, "
            f"got {[d.target_ref for d in exc_1_mh]}"
        )

        # Exception flow is still present (skeleton preserved)
        assert len(filtered.exception_flows) == 1

    def test_child_worker_pseudo_handler_no_duplicate_gate_mh(self) -> None:
        """Child worker pseudo-handler does NOT trigger gate missing_handler."""
        gate = ExecutableElementGate()
        child = WorkerIR(
            worker_name="ChildWorker",
            description="Child",
            main_flow=FlowRef(),
            exception_flows=[
                ExceptionFlowRef(
                    flow_id="exc_child",
                    condition_text="If provenance fails.",
                    blocks=[],
                )
            ],
            steps=[
                StepIR(
                    "st_child_pseudo",
                    "Ensure provenance is tracked",
                    ["s15"],
                    "GENERAL_COMMAND",
                    flow_ref="exc_child",
                    metadata={"pseudo_exception_handler": "true"},
                ),
            ],
        )
        worker = WorkerIR(
            worker_name="MainWorker",
            description="Test",
            main_flow=FlowRef(),
            steps=[StepIR("st1", "Do work", ["s1"], "GENERAL_COMMAND")],
            child_workers=[child],
        )
        filtered, infos, diags = gate.apply(worker)

        # No gate missing_handler for child exc_child (pseudo-handler excluded)
        gate_mh = [d for d in diags if d.kind == "missing_handler"]
        child_mh = [d for d in gate_mh if "exc_child" in (d.target_ref or "")]
        assert len(child_mh) == 0, (
            f"Child pseudo-handler should NOT cause gate mh, "
            f"got {[d.target_ref for d in child_mh]}"
        )

    def test_child_worker_real_handler_filtered_gate_reports_mh(self) -> None:
        """Child worker REAL handler (assumed, no source) filtered by gate
        -> gate emits missing_handler."""
        gate = ExecutableElementGate()
        child = WorkerIR(
            worker_name="ChildWorker",
            description="Child",
            main_flow=FlowRef(),
            exception_flows=[
                ExceptionFlowRef(
                    flow_id="exc_child",
                    condition_text="If provenance fails.",
                    blocks=[],
                )
            ],
            steps=[
                StepIR(
                    "st_child_handler",
                    "Handle provenance failure",
                    [],  # no source spans -> gate blocks
                    "GENERAL_COMMAND",
                    flow_ref="exc_child",
                ),
            ],
        )
        worker = WorkerIR(
            worker_name="MainWorker",
            description="Test",
            main_flow=FlowRef(),
            steps=[StepIR("st1", "Do work", ["s1"], "GENERAL_COMMAND")],
            child_workers=[child],
        )
        filtered, infos, diags = gate.apply(worker)

        # Assumed handler without source spans -> gate filters it
        # exc_child should get post-gate missing_handler
        gate_mh = [d for d in diags if d.kind == "missing_handler"]
        child_mh = [d for d in gate_mh if "exc_child" in (d.target_ref or "")]
        assert len(child_mh) >= 1, (
            f"Real child handler filtered -> gate should report mh, "
            f"got {[d.target_ref for d in gate_mh]}"
        )

    def test_incomplete_delegation_gate_no_executable_invoke(self) -> None:
        """Incomplete INVOKE_WORKER (no source, no target) is filtered out
        by the gate -- SPL must not contain an executable INVOKE."""
        gate = ExecutableElementGate()
        worker = WorkerIR(
            worker_name="MainWorker",
            description="Test",
            main_flow=FlowRef(),
            steps=[
                StepIR("st1", "Do work", ["s1"], "GENERAL_COMMAND"),
                StepIR(
                    "st_delegate", "Delegate work", [], "INVOKE_WORKER",
                ),
            ],
        )

        filtered, infos, diags = gate.apply(worker)

        # The incomplete delegation step is removed
        assert len(filtered.steps) == 1
        assert filtered.steps[0].step_id == "st1"
        assert "st_delegate" not in {s.step_id for s in filtered.steps}

        # It is in render_info as non-renderable
        blocked = [i for i in infos if not i.renderable]
        assert any(
            i.step_id == "st_delegate"
            and i.origin == "assumed"
            for i in blocked
        ), f"Expected st_delegate blocked as assumed, got {[(i.step_id, i.origin) for i in blocked]}"

        # Gate no longer emits assumed_command_not_renderable;
        # that is post-normalize IRS responsibility.
        # The step is filtered from worker.steps and recorded in render_info.


# ---------------------------------------------------------------------------
# Phase 3: classification priority fix
# ---------------------------------------------------------------------------

class TestClassifyOriginPriority:
    def test_handoff_before_source_spans(self) -> None:
        """A step with BOTH source_spans and handoff_id -> handoff_generated.
        The handoff must be validated, not silently bypassed."""
        gate = ExecutableElementGate()
        step = StepIR(
            "st1", "Invoke child worker", ["s1"], "INVOKE_WORKER",
            handoff_id="h1",
        )
        assert gate.classify_origin(step) == "handoff_generated"

    def test_source_backed_without_handoff(self) -> None:
        gate = ExecutableElementGate()
        step = StepIR("st1", "Do work", ["s1"], "GENERAL_COMMAND")
        assert gate.classify_origin(step) == "source_backed"

    def test_handoff_without_source(self) -> None:
        gate = ExecutableElementGate()
        step = StepIR("st1", "Invoke", [], "INVOKE_WORKER", handoff_id="h1")
        assert gate.classify_origin(step) == "handoff_generated"


# ---------------------------------------------------------------------------
# Phase 3: command-type guards on source_backed steps
# ---------------------------------------------------------------------------

class TestCommandTypeGuards:
    """Source-backed steps get extra validation for specific command types."""

    def test_invoke_worker_without_handoff_blocked(self) -> None:
        """INVOKE_WORKER must be handoff-backed. Source-backed without handoff
        -> blocked because no delegation contract exists."""
        gate = ExecutableElementGate()
        step = StepIR("st1", "Invoke something", ["s1"], "INVOKE_WORKER")
        # Classified as source_backed (no handoff_id), but _source_backed_renderable
        # blocks INVOKE_WORKER without handoff
        ok, reason = gate.is_renderable(step, "source_backed", {}, set(), {})
        assert ok is False
        assert "handoff" in (reason or "").lower()

    def test_source_backed_call_api_without_integration_ref_blocked(self) -> None:
        """CALL_API must name a concrete API target."""
        gate = ExecutableElementGate()
        step = StepIR("st1", "Call API", ["s1"], "CALL_API")
        ok, reason = gate.is_renderable(step, "source_backed", {}, set(), {})
        assert ok is False
        assert "integration_ref" in (reason or "").lower()

    def test_source_backed_call_api_with_integration_ref_is_renderable(self) -> None:
        """CALL_API with integration_ref + source spans -> renderable."""
        gate = ExecutableElementGate()
        step = StepIR(
            "st1", "Call search API", ["s1"], "CALL_API",
            integration_ref="SearchAPI",
        )
        ok, reason = gate.is_renderable(step, "source_backed", {}, set(), {})
        assert ok is True

    def test_source_backed_request_input_is_renderable(self) -> None:
        """REQUEST_INPUT with source_span_ids -> renderable (source says ask user)."""
        gate = ExecutableElementGate()
        step = StepIR("st1", "Ask user for input", ["s1"], "REQUEST_INPUT")
        ok, reason = gate.is_renderable(step, "source_backed", {}, set(), {})
        assert ok is True

    def test_source_backed_general_command_is_renderable(self) -> None:
        """GENERAL_COMMAND with source_span_ids -> renderable."""
        gate = ExecutableElementGate()
        step = StepIR("st1", "Do normal work", ["s1"], "GENERAL_COMMAND")
        ok, reason = gate.is_renderable(step, "source_backed", {}, set(), {})
        assert ok is True


# ---------------------------------------------------------------------------
# Phase 3: full gate.apply() integration with new guards
# ---------------------------------------------------------------------------

class TestGateApplyWithGuards:
    def test_source_backed_invoke_without_handoff_blocked_in_apply(self) -> None:
        """Full apply() integration: source-backed INVOKE_WORKER without
        handoff -> filtered out + diagnostic."""
        gate = ExecutableElementGate()
        worker = WorkerIR(
            worker_name="MainWorker",
            description="Test",
            main_flow=FlowRef(),
            steps=[
                StepIR("st1", "Do work", ["s1"], "GENERAL_COMMAND"),
                StepIR("st_invoke", "Invoke child", ["s_child"], "INVOKE_WORKER"),
            ],
        )
        filtered, infos, diags = gate.apply(worker)
        assert len(filtered.steps) == 1
        assert filtered.steps[0].step_id == "st1"
        blocked = [i for i in infos if not i.renderable]
        assert any(
            i.step_id == "st_invoke" and i.origin == "source_backed"
            for i in blocked
        ), f"st_invoke should be source_backed but blocked, got {[(i.step_id, i.origin, i.renderable) for i in blocked]}"
        # Step is filtered and in render_info; diagnostics come from post-normalize IRS.

    def test_source_backed_call_api_without_ref_blocked_in_apply(self) -> None:
        """Source-backed CALL_API without integration_ref -> blocked."""
        gate = ExecutableElementGate()
        worker = WorkerIR(
            worker_name="MainWorker",
            description="Test",
            main_flow=FlowRef(),
            steps=[
                StepIR("st1", "Real work", ["s1"], "GENERAL_COMMAND"),
                StepIR("st_api", "Call service", ["s_api"], "CALL_API"),
            ],
        )
        filtered, infos, diags = gate.apply(worker)
        assert len(filtered.steps) == 1
        # Step is filtered; diagnostics come from post-normalize IRS.
        blocked = [i for i in infos if not i.renderable]
        assert any(i.step_id == "st_api" for i in blocked)

    def test_source_backed_call_api_with_ref_passes(self) -> None:
        """Source-backed CALL_API with integration_ref -> passes gate."""
        gate = ExecutableElementGate()
        worker = WorkerIR(
            worker_name="MainWorker",
            description="Test",
            main_flow=FlowRef(),
            steps=[
                StepIR(
                    "st_api", "Call search", ["s_api"], "CALL_API",
                    integration_ref="SearchAPI",
                ),
            ],
        )
        filtered, infos, diags = gate.apply(worker)
        assert len(filtered.steps) == 1
        assert len(diags) == 0

    def test_source_backed_request_input_passes(self) -> None:
        """Source-backed REQUEST_INPUT -> passes through."""
        gate = ExecutableElementGate()
        worker = WorkerIR(
            worker_name="MainWorker",
            description="Test",
            main_flow=FlowRef(),
            steps=[
                StepIR("st_ask", "Ask user for timeframe", ["s_time"], "REQUEST_INPUT"),
            ],
        )
        filtered, infos, diags = gate.apply(worker)
        assert len(filtered.steps) == 1
        assert len(diags) == 0

    def test_resolved_worker_api_never_downgrades_to_generic(self) -> None:
        """Acceptance: 未解析 worker/API 不降级为 generic command.
        INVOKE_WORKER without handoff is BLOCKED, not silently converted."""
        gate = ExecutableElementGate()
        worker = WorkerIR(
            worker_name="MainWorker",
            description="Test",
            main_flow=FlowRef(),
            steps=[
                StepIR("st1", "Do work", ["s1"], "GENERAL_COMMAND"),
                StepIR("st_invoke", "Invoke child", ["s_child"], "INVOKE_WORKER"),
                StepIR("st_api", "Call API", ["s_api"], "CALL_API"),
            ],
        )
        filtered, infos, _diags = gate.apply(worker)
        # Only the source-backed GENERAL_COMMAND passes
        assert len(filtered.steps) == 1
        assert filtered.steps[0].step_id == "st1"
        # No steps were downgraded -- they were simply removed
        command_types = {s.command_type for s in filtered.steps}
        assert command_types == {"GENERAL_COMMAND"}
        # Both blocked steps have diagnostics
        blocked = {i.step_id for i in infos if not i.renderable}
        assert "st_invoke" in blocked
        assert "st_api" in blocked


# ===========================================================================
# R7.5: Gate boundary tests — lock diagnostic authority
# ===========================================================================


class TestR7GateBoundary:
    """Verify Gate does not emit post-normalize IRS diagnostics."""

    def test_gate_does_not_emit_assumed_command_not_renderable(self) -> None:
        """Gate filters assumed steps but does NOT emit assumed_command_not_renderable."""
        gate = ExecutableElementGate()
        worker = WorkerIR(
            worker_name="Main",
            description="Test",
            main_flow=FlowRef(),
            steps=[
                StepIR("st1", "Do work", ["s1"], "GENERAL_COMMAND"),
                StepIR("st_assumed", "Assumed step", [], "GENERAL_COMMAND"),
            ],
        )
        filtered, infos, diags = gate.apply(worker)

        # Assumed step was filtered
        assert not any(s.step_id == "st_assumed" for s in filtered.steps)

        # Gate does NOT emit assumed_command_not_renderable
        acr = [d for d in diags if d.kind == "assumed_command_not_renderable"]
        assert len(acr) == 0

    def test_gate_does_not_emit_type_or_contract_ambiguity(self) -> None:
        """Gate filters INVOKE_WORKER without target but does NOT emit type_or_contract_ambiguity."""
        gate = ExecutableElementGate()
        worker = WorkerIR(
            worker_name="Main",
            description="Test",
            main_flow=FlowRef(),
            steps=[
                StepIR("st1", "Do work", ["s1"], "GENERAL_COMMAND"),
                StepIR(
                    "st_invoke", "Invoke worker", [], "INVOKE_WORKER",
                    integration_ref=None, handoff_id=None,
                ),
            ],
        )
        filtered, infos, diags = gate.apply(worker)

        # Invoke step was filtered
        assert not any(s.step_id == "st_invoke" for s in filtered.steps)

        # Gate does NOT emit type_or_contract_ambiguity
        toca = [d for d in diags if d.kind == "type_or_contract_ambiguity"]
        assert len(toca) == 0

    def test_gate_missing_handler_only_for_filtered_handlers(self) -> None:
        """Gate emits missing_handler only when a handler was filtered, not when none existed."""
        gate = ExecutableElementGate()
        worker = WorkerIR(
            worker_name="Main",
            description="Test",
            main_flow=FlowRef(),
            exception_flows=[
                ExceptionFlowRef(
                    flow_id="exc_filtered",
                    condition_text="Handle failures.",
                    blocks=[],
                ),
                ExceptionFlowRef(
                    flow_id="exc_never",
                    condition_text="Missing timeframe.",
                    blocks=[],
                ),
            ],
            steps=[
                StepIR("st1", "Do work", ["s1"], "GENERAL_COMMAND"),
                StepIR(
                    "st_handler", "Handle failures", [], "GENERAL_COMMAND",
                    flow_ref="exc_filtered",
                ),
                # No step for exc_never → handler never existed
            ],
        )
        _, _, diags = gate.apply(worker)

        mh = [d for d in diags if d.kind == "missing_handler"]
        # Only exc_filtered (handler was filtered) should produce missing_handler
        # exc_never (handler never existed) should NOT
        assert len(mh) == 1
        assert "exc_filtered" in mh[0].target_ref


# ===========================================================================
# Phase U2: user_confirmed_repair gate tests
# ===========================================================================


class TestGateUserConfirmedRepair:
    """Gate correctly classifies and renders user_confirmed_repair steps."""

    _EMPTY_INDEX: dict[str, object] = {}
    _EMPTY_SET: set[str] = set()
    _EMPTY_DICT: dict[str, str] = {}

    def test_classify_origin_ucr(self) -> None:
        gate = ExecutableElementGate()
        step = StepIR("st1", "User step", [], "GENERAL_COMMAND",
                      metadata={"origin": "user_confirmed_repair"})
        origin = gate.classify_origin(step)
        assert origin == "user_confirmed_repair"

    def test_ucr_origin_renders_like_source_backed(self) -> None:
        gate = ExecutableElementGate()
        step = StepIR("st1", "Do work", [], "GENERAL_COMMAND",
                      metadata={"origin": "user_confirmed_repair"})
        origin = gate.classify_origin(step)
        result, _block_reason = gate.is_renderable(
            step, origin, self._EMPTY_INDEX, self._EMPTY_SET, self._EMPTY_DICT,
        )
        assert result is True

    def test_ucr_request_input_with_outputs_renderable(self) -> None:
        gate = ExecutableElementGate()
        step = StepIR("st_input", "Ask user", [], "REQUEST_INPUT",
                      outputs=["answer"],
                      metadata={"origin": "user_confirmed_repair"})
        origin = gate.classify_origin(step)
        result, _block_reason = gate.is_renderable(
            step, origin, self._EMPTY_INDEX, self._EMPTY_SET, self._EMPTY_DICT,
        )
        assert result is True

    def test_ucr_call_api_without_integration_ref_blocked(self) -> None:
        gate = ExecutableElementGate()
        step = StepIR("st_api", "Call API", [], "CALL_API",
                      metadata={"origin": "user_confirmed_repair"})
        origin = gate.classify_origin(step)
        result, _block_reason = gate.is_renderable(
            step, origin, self._EMPTY_INDEX, self._EMPTY_SET, self._EMPTY_DICT,
        )
        assert result is False

    def test_ucr_call_api_with_integration_ref_renderable(self) -> None:
        gate = ExecutableElementGate()
        step = StepIR("st_api", "Call API", [], "CALL_API",
                      integration_ref="SomeAPI",
                      metadata={"origin": "user_confirmed_repair"})
        origin = gate.classify_origin(step)
        result, _block_reason = gate.is_renderable(
            step, origin, self._EMPTY_INDEX, self._EMPTY_SET, self._EMPTY_DICT,
        )
        assert result is True

    def test_ucr_invoke_worker_without_handoff_blocked(self) -> None:
        gate = ExecutableElementGate()
        step = StepIR("st_invoke", "Invoke", [], "INVOKE_WORKER",
                      metadata={"origin": "user_confirmed_repair"})
        origin = gate.classify_origin(step)
        result, _block_reason = gate.is_renderable(
            step, origin, self._EMPTY_INDEX, self._EMPTY_SET, self._EMPTY_DICT,
        )
        assert result is False

    def test_ucr_invoke_worker_with_handoff_handoff_first(self) -> None:
        """When step has both handoff_id and UCR, classify_origin returns handoff_generated first."""
        gate = ExecutableElementGate()
        step = StepIR("st_invoke", "Invoke", [], "INVOKE_WORKER",
                      handoff_id="h1",
                      metadata={"origin": "user_confirmed_repair"})
        origin = gate.classify_origin(step)
        # handoff_id check takes priority over user_confirmed_repair — by design
        assert origin == "handoff_generated"

    def test_ucr_invoke_worker_no_handoff_not_renderable(self) -> None:
        """UCR INVOKE_WORKER without handoff_id maps to user_confirmed_repair
        but _source_backed_renderable blocks it (no handoff_id)."""
        gate = ExecutableElementGate()
        step = StepIR("st_invoke", "Invoke", [], "INVOKE_WORKER",
                      metadata={"origin": "user_confirmed_repair"})
        origin = gate.classify_origin(step)
        assert origin == "user_confirmed_repair"
        result, _block_reason = gate.is_renderable(
            step, origin, self._EMPTY_INDEX, self._EMPTY_SET, self._EMPTY_DICT,
        )
        # UCR goes through _source_backed_renderable which blocks INVOKE_WORKER without handoff
        assert result is False

    def test_ucr_apply_allows_ucr_steps(self) -> None:
        """Gate.apply() keeps UCR GENERAL_COMMAND steps."""
        gate = ExecutableElementGate()
        worker = WorkerIR(
            worker_name="Main",
            description="Test",
            main_flow=FlowRef(),
            steps=[
                StepIR("st1", "Do work", ["s1"], "GENERAL_COMMAND"),
                StepIR("st2", "User confirmed", [], "GENERAL_COMMAND",
                       metadata={"origin": "user_confirmed_repair"}),
                StepIR("st3", "", [], "GENERAL_COMMAND"),  # assumed → filtered
            ],
        )
        filtered, _, _ = gate.apply(worker)
        step_ids = {s.step_id for s in filtered.steps}
        assert "st1" in step_ids
        assert "st2" in step_ids  # UCR kept
        assert "st3" not in step_ids  # assumed filtered

