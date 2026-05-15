"""Unit tests for DiagnosticAnalyzer (Phase 4)."""

from __future__ import annotations

from nl2spl.compiler.diagnostic_analyzer import AnalyzeInput, DiagnosticAnalyzer
from nl2spl.compiler.producer_index import ProducerIndex
from nl2spl.ir.block_structure_ir import BlockIR
from nl2spl.ir.resource_registry_ir import ResourceRegistryIR, VariableSpec
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.ir.worker_ir import (
    ChildWorkerIR,
    ExceptionFlowRef,
    FlowRef,
    WorkerIR,
)


# ---------------------------------------------------------------------------
# 1. unmapped_behavior_span
# ---------------------------------------------------------------------------

class TestUnmappedBehaviorSpan:
    def test_single_unmapped_span(self) -> None:
        inp = AnalyzeInput(
            unmapped_behavior_spans=[
                {"span_id": "s5", "text": "Handle failures.", "reason": "Policy span"}
            ]
        )
        analyzer = DiagnosticAnalyzer()
        diags = analyzer.analyze(inp)
        um = [d for d in diags if d.kind == "unmapped_behavior_span"]
        assert len(um) == 1
        assert "s5" in um[0].message
        assert um[0].target_ref == "span:s5"
        assert um[0].source_span_ids == ["s5"]
        assert um[0].blocks_rendering is False

    def test_multiple_unmapped(self) -> None:
        inp = AnalyzeInput(
            unmapped_behavior_spans=[
                {"span_id": "s1", "text": "Policy A"},
                {"span_id": "s2", "text": "Policy B", "reason": "Vague"},
            ]
        )
        analyzer = DiagnosticAnalyzer()
        um = [d for d in analyzer.analyze(inp)
              if d.kind == "unmapped_behavior_span"]
        assert len(um) == 2

    def test_empty_unmapped_produces_no_diags(self) -> None:
        inp = AnalyzeInput()
        analyzer = DiagnosticAnalyzer()
        assert analyzer.analyze(inp) == []


# ---------------------------------------------------------------------------
# 2. missing_handler
# ---------------------------------------------------------------------------

class TestMissingHandler:
    def test_exception_flow_without_handler(self) -> None:
        worker = WorkerIR(
            worker_name="MainWorker",
            description="Test",
            main_flow=FlowRef(),
            exception_flows=[
                ExceptionFlowRef(
                    flow_id="exc_1",
                    condition_text="Missing timeframe.",
                    blocks=[],
                )
            ],
            steps=[],
        )
        inp = AnalyzeInput(worker=worker)
        analyzer = DiagnosticAnalyzer()
        mh = [d for d in analyzer.analyze(inp)
              if d.kind == "missing_handler"]
        assert len(mh) == 1
        assert mh[0].target_ref == "exception_flow:exc_1"
        assert "Missing timeframe" in mh[0].message

    def test_exception_flow_with_handler_no_diagnostic(self) -> None:
        worker = WorkerIR(
            worker_name="W",
            description="Test",
            main_flow=FlowRef(),
            exception_flows=[
                ExceptionFlowRef(
                    flow_id="exc_1",
                    condition_text="Missing data.",
                    blocks=[],
                )
            ],
            steps=[
                StepIR("st_handler", "Handle missing data", ["s1"],
                       "GENERAL_COMMAND", flow_ref="exc_1"),
            ],
        )
        inp = AnalyzeInput(worker=worker)
        analyzer = DiagnosticAnalyzer()
        mh = [d for d in analyzer.analyze(inp)
              if d.kind == "missing_handler"]
        assert len(mh) == 0

    def test_empty_condition_text_skipped(self) -> None:
        """No-demand rule: exception flow with empty condition is
        compiler-fabricated → no diagnostic."""
        worker = WorkerIR(
            worker_name="W",
            description="Test",
            main_flow=FlowRef(),
            exception_flows=[
                ExceptionFlowRef(
                    flow_id="exc_empty", condition_text="", blocks=[],
                )
            ],
            steps=[],
        )
        inp = AnalyzeInput(worker=worker)
        analyzer = DiagnosticAnalyzer()
        mh = [d for d in analyzer.analyze(inp)
              if d.kind == "missing_handler"]
        assert len(mh) == 0

    def test_no_exception_flows_no_diagnostic(self) -> None:
        """No demand: no exception flows → no missing_handler."""
        worker = WorkerIR(
            worker_name="W", description="Test", main_flow=FlowRef(),
        )
        inp = AnalyzeInput(worker=worker)
        analyzer = DiagnosticAnalyzer()
        assert analyzer.analyze(inp) == []

    def test_child_worker_exception_flow_without_handler(self) -> None:
        worker = WorkerIR(
            worker_name="Main",
            description="Parent",
            main_flow=FlowRef(),
            child_workers=[
                ChildWorkerIR(
                    worker_name="Child",
                    description="Child",
                    task_text="Child task",
                    exception_flows=[
                        ExceptionFlowRef(
                            flow_id="exc_child",
                            condition_text="Child failure.",
                            blocks=[],
                        )
                    ],
                )
            ],
        )
        inp = AnalyzeInput(worker=worker)
        analyzer = DiagnosticAnalyzer()
        mh = [d for d in analyzer.analyze(inp)
              if d.kind == "missing_handler"]
        assert len(mh) == 1
        assert "Child" in mh[0].message
        assert "exc_child" in mh[0].target_ref

    def test_child_worker_exception_with_handler_no_diagnostic(self) -> None:
        worker = WorkerIR(
            worker_name="Main",
            description="Parent",
            main_flow=FlowRef(),
            child_workers=[
                ChildWorkerIR(
                    worker_name="Child",
                    description="Child",
                    task_text="Child task",
                    exception_flows=[
                        ExceptionFlowRef(
                            flow_id="exc_c", condition_text="Fail.",
                            blocks=[],
                        )
                    ],
                    steps=[
                        StepIR("st_h", "Handle", ["s1"],
                               "GENERAL_COMMAND", flow_ref="exc_c"),
                    ],
                )
            ],
        )
        inp = AnalyzeInput(worker=worker)
        analyzer = DiagnosticAnalyzer()
        mh = [d for d in analyzer.analyze(inp)
              if d.kind == "missing_handler"]
        assert len(mh) == 0

    def test_two_child_workers_missing_handlers_unique_ids(self) -> None:
        """P2 fix: two child workers with missing handlers must have
        unique diagnostic_ids."""
        worker = WorkerIR(
            worker_name="Main",
            description="Parent",
            main_flow=FlowRef(),
            child_workers=[
                ChildWorkerIR(
                    worker_name="ChildA",
                    description="A",
                    task_text="Task A",
                    exception_flows=[
                        ExceptionFlowRef(
                            flow_id="exc_a", condition_text="Fail A.",
                            blocks=[],
                        )
                    ],
                ),
                ChildWorkerIR(
                    worker_name="ChildB",
                    description="B",
                    task_text="Task B",
                    exception_flows=[
                        ExceptionFlowRef(
                            flow_id="exc_b", condition_text="Fail B.",
                            blocks=[],
                        )
                    ],
                ),
            ],
        )
        inp = AnalyzeInput(worker=worker)
        analyzer = DiagnosticAnalyzer()
        mh = [d for d in analyzer.analyze(inp)
              if d.kind == "missing_handler"]
        assert len(mh) == 2
        ids = {d.diagnostic_id for d in mh}
        assert len(ids) == 2, f"Diagnostic IDs must be unique, got {ids}"

    def test_main_second_flow_child_first_flow_unique_ids(self) -> None:
        """Main worker has two exception flows, first has handler (skipped),
        second is missing. Child worker also has a missing handler.
        All generated diagnostic_ids must be unique."""
        worker = WorkerIR(
            worker_name="Main",
            description="Parent",
            main_flow=FlowRef(),
            exception_flows=[
                ExceptionFlowRef(
                    flow_id="exc_ok", condition_text="Has handler.",
                    blocks=[],
                ),
                ExceptionFlowRef(
                    flow_id="exc_missing", condition_text="No handler.",
                    blocks=[],
                ),
            ],
            steps=[
                StepIR("st_h", "Handle exc_ok", ["s1"],
                       "GENERAL_COMMAND", flow_ref="exc_ok"),
            ],
            child_workers=[
                ChildWorkerIR(
                    worker_name="Child",
                    description="Child",
                    task_text="Task",
                    exception_flows=[
                        ExceptionFlowRef(
                            flow_id="exc_child", condition_text="Child fail.",
                            blocks=[],
                        )
                    ],
                ),
            ],
        )
        inp = AnalyzeInput(worker=worker)
        analyzer = DiagnosticAnalyzer()
        mh = [d for d in analyzer.analyze(inp)
              if d.kind == "missing_handler"]
        # exc_ok has handler → skipped. exc_missing + exc_child → 2 diagnostics
        assert len(mh) == 2
        ids = {d.diagnostic_id for d in mh}
        assert len(ids) == 2, f"Expected 2 unique IDs, got {ids}"


# ---------------------------------------------------------------------------
# 3. missing_output_producer
# ---------------------------------------------------------------------------

class TestMissingOutputProducer:
    def test_required_output_without_producer(self) -> None:
        resources = ResourceRegistryIR(
            variables=[VariableSpec("report", "text", True, "Final report", "output")]
        )
        producer_index = ProducerIndex(steps=[])
        inp = AnalyzeInput(resources=resources, producer_index=producer_index)
        analyzer = DiagnosticAnalyzer()
        mp = [d for d in analyzer.analyze(inp)
              if d.kind == "missing_output_producer"]
        assert len(mp) == 1
        assert mp[0].target_ref == "variable:report"
        assert "report" in mp[0].message

    def test_required_output_with_producer_no_diagnostic(self) -> None:
        steps = [StepIR("st1", "Produce", ["s1"], "GENERAL_COMMAND", outputs=["report"])]
        resources = ResourceRegistryIR(
            variables=[VariableSpec("report", "text", True, "Report", "output")]
        )
        producer_index = ProducerIndex(steps=steps)
        inp = AnalyzeInput(resources=resources, producer_index=producer_index)
        analyzer = DiagnosticAnalyzer()
        mp = [d for d in analyzer.analyze(inp)
              if d.kind == "missing_output_producer"]
        assert len(mp) == 0

    def test_no_required_outputs_no_diagnostic(self) -> None:
        """No demand: no required outputs → no missing_output_producer."""
        resources = ResourceRegistryIR(variables=[])
        producer_index = ProducerIndex(steps=[])
        inp = AnalyzeInput(resources=resources, producer_index=producer_index)
        analyzer = DiagnosticAnalyzer()
        assert analyzer.analyze(inp) == []

    def test_no_resources_no_diagnostic(self) -> None:
        """No resources input → skip the rule entirely."""
        inp = AnalyzeInput(producer_index=ProducerIndex(steps=[]))
        analyzer = DiagnosticAnalyzer()
        assert analyzer.analyze(inp) == []

    def test_multiple_required_outputs_mixed(self) -> None:
        steps = [StepIR("st1", "A", ["s1"], "GENERAL_COMMAND", outputs=["a"])]
        resources = ResourceRegistryIR(
            variables=[
                VariableSpec("a", "text", True, "Produced", "output"),
                VariableSpec("b", "text", True, "Missing", "output"),
                VariableSpec("c", "text", False, "Optional", "output"),
            ]
        )
        producer_index = ProducerIndex(steps=steps)
        inp = AnalyzeInput(resources=resources, producer_index=producer_index)
        analyzer = DiagnosticAnalyzer()
        mp = [d for d in analyzer.analyze(inp)
              if d.kind == "missing_output_producer"]
        assert len(mp) == 1
        assert "b" in mp[0].message  # only "b" is required and unproduced


# ---------------------------------------------------------------------------
# 4. type_or_contract_ambiguity
# ---------------------------------------------------------------------------

class TestTypeContractAmbiguity:
    def test_call_api_without_integration_ref(self) -> None:
        steps = [StepIR("st_api", "Call API", ["s1"], "CALL_API")]
        inp = AnalyzeInput(steps=steps)
        analyzer = DiagnosticAnalyzer()
        tc = [d for d in analyzer.analyze(inp)
              if d.kind == "type_or_contract_ambiguity"]
        assert len(tc) == 1
        assert "integration_ref" in tc[0].message
        assert tc[0].target_ref == "step:st_api"

    def test_call_api_with_undeclared_api(self) -> None:
        steps = [
            StepIR("st_api", "Call ghost", ["s1"], "CALL_API", integration_ref="Ghost")
        ]
        inp = AnalyzeInput(steps=steps, declared_apis={"RealAPI"})
        analyzer = DiagnosticAnalyzer()
        tc = [d for d in analyzer.analyze(inp)
              if d.kind == "type_or_contract_ambiguity"]
        assert len(tc) == 1
        assert "Ghost" in tc[0].message

    def test_call_api_with_ref_without_api_registry_no_undeclared(self) -> None:
        """P1 fix: CALL_API with integration_ref but no API registry context
        must NOT be flagged as undeclared — we simply lack the evidence."""
        steps = [
            StepIR("st_api", "Call", ["s1"], "CALL_API", integration_ref="SearchAPI")
        ]
        # No declared_apis → can't judge whether undeclared
        inp = AnalyzeInput(steps=steps)
        analyzer = DiagnosticAnalyzer()
        tc = [d for d in analyzer.analyze(inp)
              if d.kind == "type_or_contract_ambiguity"]
        assert tc == [], f"Expected no ambiguity diag, got {[(d.message) for d in tc]}"

    def test_call_api_with_declared_api_no_diagnostic(self) -> None:
        steps = [
            StepIR("st_api", "Call", ["s1"], "CALL_API", integration_ref="SearchAPI")
        ]
        inp = AnalyzeInput(steps=steps, declared_apis={"SearchAPI"})
        analyzer = DiagnosticAnalyzer()
        assert analyzer.analyze(inp) == []

    def test_invoke_worker_without_target(self) -> None:
        steps = [StepIR("st_inv", "Invoke", [], "INVOKE_WORKER")]
        inp = AnalyzeInput(steps=steps)
        analyzer = DiagnosticAnalyzer()
        tc = [d for d in analyzer.analyze(inp)
              if d.kind == "type_or_contract_ambiguity"]
        assert len(tc) == 1
        assert "worker target" in tc[0].message.lower()

    def test_request_input_without_source_spans(self) -> None:
        steps = [StepIR("st_ask", "Ask user", [], "REQUEST_INPUT")]
        inp = AnalyzeInput(steps=steps)
        analyzer = DiagnosticAnalyzer()
        tc = [d for d in analyzer.analyze(inp)
              if d.kind == "type_or_contract_ambiguity"]
        assert len(tc) == 1

    def test_normal_commands_no_diagnostic(self) -> None:
        steps = [
            StepIR("st1", "Work", ["s1"], "GENERAL_COMMAND"),
            StepIR("st2", "Ask", ["s2"], "REQUEST_INPUT"),
        ]
        inp = AnalyzeInput(steps=steps)
        analyzer = DiagnosticAnalyzer()
        assert analyzer.analyze(inp) == []

    def test_no_steps_no_diagnostic(self) -> None:
        inp = AnalyzeInput(steps=[])
        analyzer = DiagnosticAnalyzer()
        assert analyzer.analyze(inp) == []


# ---------------------------------------------------------------------------
# 5. assumed_command_not_renderable
# ---------------------------------------------------------------------------

class TestAssumedCommand:
    def test_step_without_source_evidence(self) -> None:
        steps = [StepIR("st_synth", "Synthetic command", [], "GENERAL_COMMAND")]
        inp = AnalyzeInput(steps=steps)
        analyzer = DiagnosticAnalyzer()
        ac = [d for d in analyzer.analyze(inp)
              if d.kind == "assumed_command_not_renderable"]
        assert len(ac) == 1
        assert ac[0].target_ref == "step:st_synth"
        assert ac[0].blocks_rendering is True

    def test_source_backed_step_no_diagnostic(self) -> None:
        steps = [StepIR("st1", "Real work", ["s1"], "GENERAL_COMMAND")]
        inp = AnalyzeInput(steps=steps)
        analyzer = DiagnosticAnalyzer()
        assert analyzer.analyze(inp) == []

    def test_handoff_step_with_valid_id_no_diagnostic(self) -> None:
        steps = [
            StepIR("st_invoke", "Invoke child", [], "INVOKE_WORKER", handoff_id="h1")
        ]
        inp = AnalyzeInput(steps=steps, valid_handoff_ids={"h1"})
        analyzer = DiagnosticAnalyzer()
        ac = [d for d in analyzer.analyze(inp)
              if d.kind == "assumed_command_not_renderable"]
        assert len(ac) == 0

    def test_handoff_step_with_invalid_id_diagnostic(self) -> None:
        steps = [
            StepIR("st_invoke", "Invoke ghost", [], "INVOKE_WORKER", handoff_id="fake")
        ]
        inp = AnalyzeInput(steps=steps, valid_handoff_ids={"h1"})
        analyzer = DiagnosticAnalyzer()
        ac = [d for d in analyzer.analyze(inp)
              if d.kind == "assumed_command_not_renderable"]
        assert len(ac) == 1

    def test_compiler_unpack_no_diagnostic(self) -> None:
        steps = [
            StepIR("st_u", "Extract", [], "GENERAL_COMMAND",
                   metadata={"origin": "compiler_unpack"})
        ]
        inp = AnalyzeInput(steps=steps)
        analyzer = DiagnosticAnalyzer()
        ac = [d for d in analyzer.analyze(inp)
              if d.kind == "assumed_command_not_renderable"]
        assert len(ac) == 0

    def test_mixed_steps(self) -> None:
        steps = [
            StepIR("st_ok", "Real", ["s1"], "GENERAL_COMMAND"),
            StepIR("st_bad", "Fake", [], "GENERAL_COMMAND"),
            StepIR("st_u", "Unpack", [], "GENERAL_COMMAND",
                   metadata={"origin": "compiler_unpack"}),
        ]
        inp = AnalyzeInput(steps=steps)
        analyzer = DiagnosticAnalyzer()
        ac = [d for d in analyzer.analyze(inp)
              if d.kind == "assumed_command_not_renderable"]
        assert len(ac) == 1
        assert ac[0].target_ref == "step:st_bad"


# ---------------------------------------------------------------------------
# Integration: multiple diagnostic kinds in one analyze() call
# ---------------------------------------------------------------------------

class TestMultipleKinds:
    def test_all_kinds_simultaneously(self) -> None:
        worker = WorkerIR(
            worker_name="W",
            description="Test",
            main_flow=FlowRef(),
            exception_flows=[
                ExceptionFlowRef(
                    flow_id="exc_1",
                    condition_text="Missing data.",
                    blocks=[],
                )
            ],
            steps=[],  # no handler → missing_handler
        )
        resources = ResourceRegistryIR(
            variables=[
                VariableSpec("report", "text", True, "Report", "output"),
                VariableSpec("unproduced_out", "text", True, "MissingOut", "output"),
            ]
        )
        steps = [
            StepIR("st1", "Real", ["s1"], "GENERAL_COMMAND", outputs=["report"]),
            StepIR("st_synth", "Fake", [], "GENERAL_COMMAND"),
            StepIR("st_api", "Call", [], "CALL_API"),
        ]
        producer_index = ProducerIndex(steps=steps)
        inp = AnalyzeInput(
            worker=worker,
            resources=resources,
            producer_index=producer_index,
            steps=steps,
            unmapped_behavior_spans=[
                {"span_id": "s99", "text": "Vague policy."}
            ],
            declared_apis={"RealAPI"},
        )
        analyzer = DiagnosticAnalyzer()
        diags = analyzer.analyze(inp)

        kinds = {d.kind for d in diags}
        assert kinds == {
            "unmapped_behavior_span",
            "missing_handler",
            "missing_output_producer",
            "type_or_contract_ambiguity",
            "assumed_command_not_renderable",
        }, f"Expected all 5 kinds, got {kinds}"

    def test_clean_happy_path_no_diagnostics(self) -> None:
        """A fully source-backed, complete worker → zero diagnostics."""
        worker = WorkerIR(
            worker_name="W",
            description="Test",
            main_flow=FlowRef(),
            steps=[
                StepIR("st1", "Produce report", ["s1"], "GENERAL_COMMAND",
                       outputs=["report"]),
            ],
        )
        resources = ResourceRegistryIR(
            variables=[VariableSpec("report", "text", True, "Report", "output")]
        )
        producer_index = ProducerIndex(
            steps=[StepIR("st1", "Produce", ["s1"], "GENERAL_COMMAND",
                         outputs=["report"])]
        )
        inp = AnalyzeInput(
            worker=worker,
            resources=resources,
            producer_index=producer_index,
            steps=worker.steps,
        )
        analyzer = DiagnosticAnalyzer()
        diags = analyzer.analyze(inp)
        assert diags == [], f"Expected no diagnostics, got {[(d.kind, d.message) for d in diags]}"


# ---------------------------------------------------------------------------
# No demand, no structure
# ---------------------------------------------------------------------------

class TestNoDemandNoStructure:
    def test_no_exception_flows_no_missing_handler(self) -> None:
        worker = WorkerIR(worker_name="W", description="Test", main_flow=FlowRef())
        inp = AnalyzeInput(worker=worker)
        analyzer = DiagnosticAnalyzer()
        assert analyzer.analyze(inp) == []

    def test_empty_condition_skipped_no_diagnostic(self) -> None:
        worker = WorkerIR(
            worker_name="W",
            description="Test",
            main_flow=FlowRef(),
            exception_flows=[
                ExceptionFlowRef(flow_id="e", condition_text="", blocks=[]),
            ],
        )
        inp = AnalyzeInput(worker=worker)
        analyzer = DiagnosticAnalyzer()
        mh = [d for d in analyzer.analyze(inp)
              if d.kind == "missing_handler"]
        assert len(mh) == 0

    def test_no_required_outputs_no_missing_producer(self) -> None:
        resources = ResourceRegistryIR(variables=[])
        producer_index = ProducerIndex(steps=[])
        inp = AnalyzeInput(resources=resources, producer_index=producer_index)
        analyzer = DiagnosticAnalyzer()
        mp = [d for d in analyzer.analyze(inp)
              if d.kind == "missing_output_producer"]
        assert len(mp) == 0

    def test_no_exception_flow_no_call_api_no_orphan_diagnostics(self) -> None:
        """Pure clean worker: no exception, no API calls, source-backed steps.
        Must produce ZERO diagnostics of any kind."""
        worker = WorkerIR(
            worker_name="W",
            description="Clean",
            main_flow=FlowRef(),
            steps=[
                StepIR("st1", "Real work", ["s1"], "GENERAL_COMMAND"),
                StepIR("st2", "More work", ["s2"], "GENERAL_COMMAND"),
            ],
        )
        inp = AnalyzeInput(worker=worker, steps=list(worker.steps))
        analyzer = DiagnosticAnalyzer()
        assert analyzer.analyze(inp) == []
