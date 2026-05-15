"""Unit tests for provenance aggregation (MVP + MVP+)."""

from __future__ import annotations

from dataclasses import dataclass

from nl2spl.ir.agent_profile_ir import AgentProfileIR, Aspect, Concept, PersonaIR
from nl2spl.ir.block_structure_ir import BlockIR
from nl2spl.ir.constraint_ir import ConstraintIR
from nl2spl.ir.resource_registry_ir import ResourceRegistryIR, VariableSpec
from nl2spl.ir.span_ir import SpanIR
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.ir.worker_ir import (
    AlternativeFlowRef,
    ChildWorkerIR,
    ExceptionFlowRef,
    FlowRef,
    WorkerInput,
    WorkerOutput,
    WorkerIR,
)
from nl2spl.pipeline.provenance import ProvenanceAggregator


# Minimal VariableFact-like stub for testing adapter hard fact provenance
@dataclass
class _FakeVariableFact:
    name: str
    source_section_id: str


class TestProvenanceAggregator:
    """Tests for ProvenanceAggregator."""

    def test_worker_trace_created(self) -> None:
        """Main and child workers get trace records."""
        worker = WorkerIR(
            worker_name="MainWorker",
            description="Main worker",
            main_flow=FlowRef(blocks=[BlockIR("b1", "SEQUENTIAL", spans=["s1"])]),
            child_workers=[
                ChildWorkerIR(
                    worker_name="ChildWorker",
                    description="Child",
                    task_text="Do child work",
                )
            ],
        )
        aggregator = ProvenanceAggregator()
        traces, _ = aggregator.aggregate(
            worker, [], [], ResourceRegistryIR(), SymbolTable(), [], None
        )

        worker_traces = [t for t in traces if t.target_ref.startswith("worker:")]
        assert len(worker_traces) == 2
        assert any("MainWorker" in t.target_ref for t in worker_traces)
        assert any("ChildWorker" in t.target_ref for t in worker_traces)

    def test_flow_traces_with_conditions(self) -> None:
        """Alternative and exception flows get traces with condition text."""
        worker = WorkerIR(
            worker_name="TestWorker",
            description="Test",
            main_flow=FlowRef(blocks=[BlockIR("b1", "SEQUENTIAL", spans=["s1"])]),
            alternative_flows=[
                AlternativeFlowRef(
                    flow_id="alt_1",
                    condition_text="If alternative needed",
                    blocks=[BlockIR("b_alt", "IF", "If alternative needed", ["s_alt"])],
                )
            ],
            exception_flows=[
                ExceptionFlowRef(
                    flow_id="exc_1",
                    condition_text="Missing timeframe.",
                    blocks=[],
                )
            ],
        )
        aggregator = ProvenanceAggregator()
        traces, _ = aggregator.aggregate(
            worker, [], [], ResourceRegistryIR(), SymbolTable(), [], None
        )

        flow_traces = [t for t in traces if t.target_ref.startswith("flow:")]
        assert len(flow_traces) == 3  # main, alt_1, exc_1
        assert any("alt_1" in t.target_ref for t in flow_traces)
        assert any("exc_1" in t.target_ref for t in flow_traces)

    def test_step_source_backed_is_direct(self) -> None:
        """Steps with source_span_ids get relation=direct."""
        steps = [StepIR("st1", "Do work", ["s1"], "GENERAL_COMMAND")]
        spans = [SpanIR("s1", "Do the work.")]
        aggregator = ProvenanceAggregator()
        traces, _ = aggregator.aggregate(
            WorkerIR("W", "Test"),
            steps, [], ResourceRegistryIR(), SymbolTable(), spans, None
        )

        step_trace = next(t for t in traces if t.target_ref == "step:st1")
        assert step_trace.relation == "direct"
        assert step_trace.source_span_ids == ["s1"]

    def test_step_without_source_is_assumed(self) -> None:
        """Steps with no source_span_ids and no handoff get relation=assumed."""
        steps = [StepIR("st1", "Synthetic", [], "GENERAL_COMMAND")]
        aggregator = ProvenanceAggregator()
        traces, _ = aggregator.aggregate(
            WorkerIR("W", "Test"),
            steps, [], ResourceRegistryIR(), SymbolTable(), [], None
        )

        step_trace = next(t for t in traces if t.target_ref == "step:st1")
        assert step_trace.relation == "assumed"
        assert step_trace.needs_confirmation is True

    def test_step_handoff_is_direct(self) -> None:
        """Steps with handoff_id get relation=direct."""
        steps = [
            StepIR(
                "st_invoke", "Invoke child", [],
                "INVOKE_WORKER", integration_ref="Child", handoff_id="h1",
            )
        ]
        aggregator = ProvenanceAggregator()
        traces, _ = aggregator.aggregate(
            WorkerIR("W", "Test"),
            steps, [], ResourceRegistryIR(), SymbolTable(), [], None
        )

        step_trace = next(t for t in traces if t.target_ref == "step:st_invoke")
        assert step_trace.relation == "direct"

    def test_compiler_unpack_step_is_normalized(self) -> None:
        """Compiler unpack steps get relation=normalized."""
        steps = [
            StepIR(
                "st_unpack", "Extract field", [],
                "GENERAL_COMMAND", metadata={"origin": "compiler_unpack"},
            )
        ]
        aggregator = ProvenanceAggregator()
        traces, _ = aggregator.aggregate(
            WorkerIR("W", "Test"),
            steps, [], ResourceRegistryIR(), SymbolTable(), [], None
        )

        step_trace = next(t for t in traces if t.target_ref == "step:st_unpack")
        assert step_trace.relation == "normalized"

    def test_constraint_trace_with_source(self) -> None:
        """Constraints with source_span_ids get relation=direct."""
        constraints = [
            ConstraintIR("c1", "Must use approved source", "obligation", targets=["s_rule"], source_span_ids=["s_rule"])
        ]
        spans = [SpanIR("s_rule", "Use approved sources only.")]
        aggregator = ProvenanceAggregator()
        traces, _ = aggregator.aggregate(
            WorkerIR("W", "Test"),
            [], constraints, ResourceRegistryIR(), SymbolTable(), spans, None
        )

        c_trace = next(t for t in traces if t.target_ref == "constraint:c1")
        assert c_trace.relation == "direct"
        assert c_trace.source_span_ids == ["s_rule"]
        assert not c_trace.needs_confirmation

    def test_constraint_without_source_needs_confirmation(self) -> None:
        """Constraints without source spans get needs_confirmation=True."""
        constraints = [
            ConstraintIR("c1", "Must validate", "obligation")
        ]
        aggregator = ProvenanceAggregator()
        traces, _ = aggregator.aggregate(
            WorkerIR("W", "Test"),
            [], constraints, ResourceRegistryIR(), SymbolTable(), [], None
        )

        c_trace = next(t for t in traces if t.target_ref == "constraint:c1")
        assert c_trace.relation == "assumed"
        assert c_trace.needs_confirmation is True

    def test_variable_produced_by_source_backed_step_is_direct(self) -> None:
        """Variable from a source-backed producer step → relation=direct."""
        steps = [StepIR("st1", "Produce draft", ["s1"], "GENERAL_COMMAND", outputs=["draft"])]
        resources = ResourceRegistryIR(
            variables=[VariableSpec("draft", "text", True, "Draft", "output")]
        )
        symbols = SymbolTable()
        symbols.declare("draft", "text", "output", "Draft")
        spans = [SpanIR("s1", "Produce a draft.")]
        aggregator = ProvenanceAggregator()
        traces, diags = aggregator.aggregate(
            WorkerIR("W", "Test"),
            steps, [], resources, symbols, spans, None
        )

        var_trace = next(t for t in traces if t.target_ref == "variable:draft")
        assert var_trace.relation == "direct"
        assert var_trace.source_span_ids == ["s1"]
        assert not any(d.kind == "missing_provenance" for d in diags)

    def test_variable_with_contract_only_is_assumed(self) -> None:
        """Contract variable with no source evidence → assumed + missing_provenance."""
        resources = ResourceRegistryIR(
            variables=[VariableSpec("user_request", "text", True, "Request", "input")]
        )
        symbols = SymbolTable()
        symbols.declare("user_request", "text", "input", "Request")
        aggregator = ProvenanceAggregator()
        traces, diags = aggregator.aggregate(
            WorkerIR("W", "Test"),
            [], [], resources, symbols, [], None
        )

        var_trace = next(t for t in traces if t.target_ref == "variable:user_request")
        assert var_trace.relation == "assumed"
        assert var_trace.needs_confirmation is True
        missing_diags = [d for d in diags if d.kind == "missing_provenance"]
        assert len(missing_diags) == 1
        assert "user_request" in missing_diags[0].message

    def test_variable_with_no_evidence_gets_missing_provenance(self) -> None:
        """Variable with no producer, no contract, no declaration → assumed + diag."""
        resources = ResourceRegistryIR(
            variables=[VariableSpec("orphan", "text", False, "No source", "step")]
        )
        symbols = SymbolTable()
        # Not declared in symbol table
        aggregator = ProvenanceAggregator()
        traces, diags = aggregator.aggregate(
            WorkerIR("W", "Test"),
            [], [], resources, symbols, [], None
        )

        var_trace = next(t for t in traces if t.target_ref == "variable:orphan")
        assert var_trace.relation == "assumed"
        assert var_trace.needs_confirmation is True
        missing_diags = [d for d in diags if d.kind == "missing_provenance"]
        assert len(missing_diags) == 1
        assert "orphan" in missing_diags[0].message

    def test_variable_from_unpack_step_is_normalized(self) -> None:
        """Variable from compiler_unpack step → relation=normalized."""
        steps = [
            StepIR(
                "st_unpack", "Extract field", [],
                "GENERAL_COMMAND", outputs=["field"],
                metadata={"origin": "compiler_unpack"},
            )
        ]
        resources = ResourceRegistryIR(
            variables=[VariableSpec("field", "text", True, "Field", "step")]
        )
        symbols = SymbolTable()
        symbols.declare("field", "text", "step", "Field")
        aggregator = ProvenanceAggregator()
        traces, _ = aggregator.aggregate(
            WorkerIR("W", "Test"),
            steps, [], resources, symbols, [], None
        )

        var_trace = next(t for t in traces if t.target_ref == "variable:field")
        assert var_trace.relation == "normalized"

    def test_span_resolves_section_and_packet_ids(self) -> None:
        """Span with source_section_id/packet_id propagates to trace."""
        steps = [StepIR("st1", "Do work", ["s1"], "GENERAL_COMMAND")]
        spans = [
            SpanIR(
                "s1", "Do the work.",
                source_section_id="behavior",
                source_packet_id="pkt_1",
            )
        ]
        aggregator = ProvenanceAggregator()
        traces, _ = aggregator.aggregate(
            WorkerIR("W", "Test"),
            steps, [], ResourceRegistryIR(), SymbolTable(), spans, None
        )

        step_trace = next(t for t in traces if t.target_ref == "step:st1")
        assert step_trace.source_section_id == "behavior"
        assert step_trace.source_packet_id == "pkt_1"

    def test_worker_scoped_variable_uses_scoped_target_ref(self) -> None:
        """Worker-local variables get worker:{id}.variable:{name} target_ref."""
        resources = ResourceRegistryIR(
            variables=[VariableSpec("result", "text", True, "Result", "output")]
        )
        symbols = SymbolTable()
        symbols.declare("result", "text", "output", "Result")
        steps = [StepIR("st1", "Produce result", ["s_child"], "GENERAL_COMMAND", outputs=["result"])]
        spans = [SpanIR("s_child", "Produce final result.")]
        aggregator = ProvenanceAggregator()
        traces, _ = aggregator.aggregate(
            WorkerIR("W", "Test"),
            steps, [], resources, symbols, spans, None,
            worker_var_scopes={"result": "worker_child"},
        )

        var_trace = next(t for t in traces if "result" in t.target_ref)
        assert var_trace.target_ref == "worker:worker_child.variable:result"

    def test_global_variable_keeps_flat_target_ref(self) -> None:
        """Global variables (not in worker_var_scopes) keep variable:{name}."""
        resources = ResourceRegistryIR(
            variables=[VariableSpec("draft", "text", True, "Draft", "output")]
        )
        symbols = SymbolTable()
        symbols.declare("draft", "text", "output", "Draft")
        steps = [StepIR("st1", "Produce", ["s1"], "GENERAL_COMMAND", outputs=["draft"])]
        spans = [SpanIR("s1", "Draft it.")]
        aggregator = ProvenanceAggregator()
        traces, _ = aggregator.aggregate(
            WorkerIR("W", "Test"),
            steps, [], resources, symbols, spans, None,
            worker_var_scopes={},  # empty — no worker-local vars
        )

        var_trace = next(t for t in traces if t.target_ref == "variable:draft")
        assert var_trace.target_ref == "variable:draft"

    def test_profile_traces(self) -> None:
        """Profile generates persona, audience, and concept traces."""
        profile = AgentProfileIR(
            persona=PersonaIR(role="Code Reviewer"),
            audience_aspects=[Aspect(name="Developer", text="For developers")],
            concepts=[Concept(term="PR", definition="Pull Request")],
        )
        aggregator = ProvenanceAggregator()
        traces, _ = aggregator.aggregate(
            WorkerIR("W", "Test"),
            [], [], ResourceRegistryIR(), SymbolTable(), [], profile
        )

        profile_traces = [t for t in traces if t.target_ref.startswith("profile:")]
        assert len(profile_traces) == 3
        assert any("Code Reviewer" in t.explanation for t in profile_traces)


# ---------------------------------------------------------------------------
# Phase 6: handoff traces
# ---------------------------------------------------------------------------

class TestHandoffTraces:
    def test_handoff_trace_created(self) -> None:
        from nl2spl.ir.worker_plan_ir import (
            InputBindingIR, OutputBindingIR, WorkerHandoffIR,
        )
        handoffs = [
            WorkerHandoffIR(
                handoff_id="h1", from_worker="w_main", to_worker="w_child",
                api_ref=None, mode="invoke", condition_text=None,
                ordering="after",
                input_bindings=[InputBindingIR("req", "child_req", True)],
                output_bindings=[OutputBindingIR("child_out", "result", True, "set")],
            )
        ]
        aggregator = ProvenanceAggregator()
        traces, _ = aggregator.aggregate(
            WorkerIR("W", "Test"), [], [],
            ResourceRegistryIR(), SymbolTable(), [],
            handoffs=handoffs,
        )
        ht = [t for t in traces if t.target_ref.startswith("handoff:")]
        assert len(ht) == 1
        assert ht[0].target_ref == "handoff:h1"
        assert "invoke" in ht[0].explanation

    def test_api_call_handoff_trace(self) -> None:
        from nl2spl.ir.worker_plan_ir import WorkerHandoffIR
        handoffs = [
            WorkerHandoffIR(
                handoff_id="h_api", from_worker="w_main", to_worker=None,
                api_ref="SearchAPI", mode="api_call", condition_text=None,
                ordering="after",
            )
        ]
        aggregator = ProvenanceAggregator()
        traces, _ = aggregator.aggregate(
            WorkerIR("W", "Test"), [], [],
            ResourceRegistryIR(), SymbolTable(), [],
            handoffs=handoffs,
        )
        ht = [t for t in traces if t.target_ref == "handoff:h_api"]
        assert len(ht) == 1
        assert "api_call" in ht[0].explanation
        assert "SearchAPI" in ht[0].explanation

    def test_multiple_handoffs(self) -> None:
        from nl2spl.ir.worker_plan_ir import WorkerHandoffIR
        handoffs = [
            WorkerHandoffIR(
                handoff_id=f"h{i}", from_worker="w_main",
                to_worker=f"w_{i}", api_ref=None, mode="invoke",
                condition_text=None, ordering="after",
            )
            for i in range(3)
        ]
        aggregator = ProvenanceAggregator()
        traces, _ = aggregator.aggregate(
            WorkerIR("W", "Test"), [], [],
            ResourceRegistryIR(), SymbolTable(), [],
            handoffs=handoffs,
        )
        ht = [t for t in traces if t.target_ref.startswith("handoff:")]
        assert len(ht) == 3

    def test_no_handoffs_no_traces(self) -> None:
        aggregator = ProvenanceAggregator()
        traces, _ = aggregator.aggregate(
            WorkerIR("W", "Test"), [], [],
            ResourceRegistryIR(), SymbolTable(), [],
        )
        ht = [t for t in traces if t.target_ref.startswith("handoff:")]
        assert len(ht) == 0


# ---------------------------------------------------------------------------
# Phase 6: handoff-backed variable provenance
# ---------------------------------------------------------------------------

class TestHandoffVariableProvenance:
    def test_variable_from_handoff_binding_is_direct(self) -> None:
        """Variable produced by handoff output binding → relation=direct.
        No missing_provenance diagnostic."""
        from nl2spl.ir.worker_plan_ir import (
            InputBindingIR, OutputBindingIR, WorkerHandoffIR,
        )
        resources = ResourceRegistryIR(
            variables=[VariableSpec("result", "text", True, "Result", "output")]
        )
        symbols = SymbolTable()
        symbols.declare("result", "text", "output", "Result")
        handoffs = [
            WorkerHandoffIR(
                handoff_id="h1", from_worker="w_main", to_worker="w_child",
                api_ref=None, mode="invoke", condition_text=None,
                ordering="after",
                input_bindings=[InputBindingIR("req", "child_req", True)],
                output_bindings=[OutputBindingIR("child_out", "result", True, "set")],
            )
        ]
        aggregator = ProvenanceAggregator()
        traces, diags = aggregator.aggregate(
            WorkerIR("W", "Test"), [], [],
            resources, symbols, [],
            handoffs=handoffs,
        )
        var_trace = next(t for t in traces if t.target_ref == "variable:result")
        assert var_trace.relation == "direct"
        assert "handoff" in var_trace.explanation.lower()
        assert not any(d.kind == "missing_provenance" and "result" in d.message
                       for d in diags)

    def test_contract_variable_without_handoff_still_assumed(self) -> None:
        """Contract variable with no handoff binding → still assumed + diag."""
        resources = ResourceRegistryIR(
            variables=[VariableSpec("orphan", "text", True, "Orphan", "output")]
        )
        symbols = SymbolTable()
        symbols.declare("orphan", "text", "output", "Orphan")
        aggregator = ProvenanceAggregator()
        traces, diags = aggregator.aggregate(
            WorkerIR("W", "Test"), [], [],
            resources, symbols, [],
            handoffs=[],
        )
        var_trace = next(t for t in traces if t.target_ref == "variable:orphan")
        assert var_trace.relation == "assumed"
        assert any(d.kind == "missing_provenance" and "orphan" in d.message
                   for d in diags)

    def test_handoff_without_to_worker_not_direct(self) -> None:
        """P1: handoff with to_worker=None → inferred + missing_provenance.
        Invalid handoff must not serve as direct evidence."""
        from nl2spl.ir.worker_plan_ir import (
            InputBindingIR, OutputBindingIR, WorkerHandoffIR,
        )
        resources = ResourceRegistryIR(
            variables=[VariableSpec("result", "text", True, "Result", "output")]
        )
        symbols = SymbolTable()
        symbols.declare("result", "text", "output", "Result")
        handoffs = [
            WorkerHandoffIR(
                handoff_id="h_bad", from_worker="w_main",
                to_worker=None, api_ref=None, mode="invoke",
                condition_text=None, ordering="after",
                input_bindings=[InputBindingIR("req", "cr", True)],
                output_bindings=[OutputBindingIR("co", "result", True, "set")],
            )
        ]
        aggregator = ProvenanceAggregator()
        traces, diags = aggregator.aggregate(
            WorkerIR("W", "Test"), [], [],
            resources, symbols, [],
            handoffs=handoffs,
        )
        var_trace = next(t for t in traces if t.target_ref == "variable:result")
        assert var_trace.relation != "direct", (
            f"Invalid handoff must not be direct, got {var_trace.relation}"
        )
        assert any(d.kind == "missing_provenance" and "result" in d.message
                   for d in diags)

    def test_handoff_without_input_bindings_not_direct(self) -> None:
        """P1: invoke handoff with no input bindings → inferred + diag."""
        from nl2spl.ir.worker_plan_ir import OutputBindingIR, WorkerHandoffIR
        resources = ResourceRegistryIR(
            variables=[VariableSpec("result", "text", True, "Result", "output")]
        )
        symbols = SymbolTable()
        symbols.declare("result", "text", "output", "Result")
        handoffs = [
            WorkerHandoffIR(
                handoff_id="h_no_in", from_worker="w_main",
                to_worker="w_child", api_ref=None, mode="invoke",
                condition_text=None, ordering="after",
                input_bindings=[],
                output_bindings=[OutputBindingIR("co", "result", True, "set")],
            )
        ]
        aggregator = ProvenanceAggregator()
        traces, diags = aggregator.aggregate(
            WorkerIR("W", "Test"), [], [],
            resources, symbols, [],
            handoffs=handoffs,
        )
        var_trace = next(t for t in traces if t.target_ref == "variable:result")
        assert var_trace.relation != "direct"

    def test_handoff_ghost_worker_with_child_ids_not_direct(self) -> None:
        """P2: handoff to_worker='ghost' — known_child_worker_ids excludes it.
        Must NOT be direct provenance."""
        from nl2spl.ir.worker_plan_ir import (
            InputBindingIR, OutputBindingIR, WorkerHandoffIR,
        )
        resources = ResourceRegistryIR(
            variables=[VariableSpec("result", "text", True, "Result", "output")]
        )
        symbols = SymbolTable()
        symbols.declare("result", "text", "output", "Result")
        handoffs = [
            WorkerHandoffIR(
                handoff_id="h1", from_worker="w_main",
                to_worker="ghost", api_ref=None, mode="invoke",
                condition_text=None, ordering="after",
                input_bindings=[InputBindingIR("r", "c", True)],
                output_bindings=[OutputBindingIR("co", "result", True, "set")],
            )
        ]
        aggregator = ProvenanceAggregator()
        traces, diags = aggregator.aggregate(
            WorkerIR("W", "Test"), [], [],
            resources, symbols, [],
            handoffs=handoffs,
            known_child_worker_ids={"w_child"},
        )
        var_trace = next(t for t in traces if t.target_ref == "variable:result")
        assert var_trace.relation != "direct", (
            f"ghost worker must not be direct, got {var_trace.relation}"
        )

    def test_handoff_with_child_ids_valid_is_direct(self) -> None:
        """Handoff to_worker in known_child_worker_ids → direct."""
        from nl2spl.ir.worker_plan_ir import (
            InputBindingIR, OutputBindingIR, WorkerHandoffIR,
        )
        resources = ResourceRegistryIR(
            variables=[VariableSpec("result", "text", True, "Result", "output")]
        )
        symbols = SymbolTable()
        symbols.declare("result", "text", "output", "Result")
        handoffs = [
            WorkerHandoffIR(
                handoff_id="h1", from_worker="w_main",
                to_worker="w_child", api_ref=None, mode="invoke",
                condition_text=None, ordering="after",
                input_bindings=[InputBindingIR("r", "c", True)],
                output_bindings=[OutputBindingIR("co", "result", True, "set")],
            )
        ]
        aggregator = ProvenanceAggregator()
        traces, diags = aggregator.aggregate(
            WorkerIR("W", "Test"), [], [],
            resources, symbols, [],
            handoffs=handoffs,
            known_child_worker_ids={"w_child"},
        )
        var_trace = next(t for t in traces if t.target_ref == "variable:result")
        assert var_trace.relation == "direct"
        assert not any(d.kind == "missing_provenance" and "result" in d.message
                       for d in diags)

    def test_api_call_handoff_undeclared_not_direct(self) -> None:
        """P2: api_call handoff with undeclared api_ref → not direct."""
        from nl2spl.ir.worker_plan_ir import OutputBindingIR, WorkerHandoffIR
        resources = ResourceRegistryIR(
            variables=[VariableSpec("data", "text", True, "Data", "output")]
        )
        symbols = SymbolTable()
        symbols.declare("data", "text", "output", "Data")
        handoffs = [
            WorkerHandoffIR(
                handoff_id="h_api", from_worker="w_main",
                to_worker=None, api_ref="UndeclaredAPI", mode="api_call",
                condition_text=None, ordering="after",
                output_bindings=[OutputBindingIR("ao", "data", True, "set")],
            )
        ]
        aggregator = ProvenanceAggregator()
        traces, diags = aggregator.aggregate(
            WorkerIR("W", "Test"), [], [],
            resources, symbols, [],
            handoffs=handoffs,
            declared_apis={"RealAPI"},
        )
        var_trace = next(t for t in traces if t.target_ref == "variable:data")
        assert var_trace.relation != "direct"


# ---------------------------------------------------------------------------
# Phase 6 P1: post-gate step filtering
# ---------------------------------------------------------------------------

class TestPostGateStepFiltering:
    def test_blocked_step_output_not_direct_variable_provenance(self) -> None:
        """P1: steps passed to aggregator must be post-gate.  A step that
        was blocked by the gate (and thus absent from prov_steps) must NOT
        contribute its outputs as producer provenance."""
        resources = ResourceRegistryIR(
            variables=[VariableSpec("orphan", "text", True, "OrphanOut", "output")]
        )
        symbols = SymbolTable()
        symbols.declare("orphan", "text", "output", "OrphanOut")
        # Simulate a step that was blocked by the gate and is NOT in prov_steps
        # The aggregator receives an empty step list (post-gate)
        aggregator = ProvenanceAggregator()
        traces, diags = aggregator.aggregate(
            WorkerIR("W", "Test"), [], [],  # steps=[] — blocked step absent
            resources, symbols, [],
        )
        var_trace = next(t for t in traces if t.target_ref == "variable:orphan")
        # Without the step in the post-gate list, the variable has no producer
        assert var_trace.relation != "direct", (
            f"Blocked step output must not be direct, got {var_trace.relation}"
        )
        assert any(d.kind == "missing_provenance" and "orphan" in d.message
                   for d in diags)

    def test_post_gate_step_with_output_is_direct(self) -> None:
        """A step that survives the gate and is in prov_steps → direct trace."""
        resources = ResourceRegistryIR(
            variables=[VariableSpec("report", "text", True, "Report", "output")]
        )
        symbols = SymbolTable()
        symbols.declare("report", "text", "output", "Report")
        steps = [
            StepIR("st1", "Produce report", ["s1"], "GENERAL_COMMAND",
                   outputs=["report"])
        ]
        spans = [SpanIR("s1", "Produce report.")]
        aggregator = ProvenanceAggregator()
        traces, diags = aggregator.aggregate(
            WorkerIR("W", "Test"), steps, [],
            resources, symbols, spans,
        )
        var_trace = next(t for t in traces if t.target_ref == "variable:report")
        assert var_trace.relation == "direct"
        assert not any(d.kind == "missing_provenance" for d in diags)


# ---------------------------------------------------------------------------
# MVP+ Phase 1: flow trace section/packet provenance
# ---------------------------------------------------------------------------

class TestFlowTraceSectionPacket:
    def test_main_flow_resolves_section(self) -> None:
        spans = [
            SpanIR("s1", "Do work.", source_section_id="sec_reusable_process",
                   source_packet_id="p_process_1"),
        ]
        worker = WorkerIR(
            worker_name="W", description="Test",
            main_flow=FlowRef(blocks=[BlockIR("b1", "SEQUENTIAL", spans=["s1"])]),
        )
        aggregator = ProvenanceAggregator()
        traces, _ = aggregator.aggregate(
            worker, [], [], ResourceRegistryIR(), SymbolTable(), spans,
        )
        ft = next(t for t in traces if t.target_ref == "flow:main")
        assert ft.source_section_id == "sec_reusable_process"
        assert ft.source_packet_id == "p_process_1"

    def test_exception_flow_resolves_section(self) -> None:
        spans = [
            SpanIR("s_fail", "Missing timeframe.",
                   source_section_id="sec_failure_handling"),
        ]
        worker = WorkerIR(
            worker_name="W", description="Test",
            main_flow=FlowRef(),
            exception_flows=[
                ExceptionFlowRef(
                    flow_id="exc_1", condition_text="Missing timeframe.",
                    blocks=[BlockIR("b_exc", "SEQUENTIAL", spans=["s_fail"])],
                )
            ],
        )
        aggregator = ProvenanceAggregator()
        traces, _ = aggregator.aggregate(
            worker, [], [], ResourceRegistryIR(), SymbolTable(), spans,
        )
        ft = next(t for t in traces if t.target_ref == "flow:exc_1")
        assert ft.source_section_id == "sec_failure_handling"

    def test_flow_without_adapter_spans_gets_none(self) -> None:
        spans = [SpanIR("s1", "No adapter data.")]
        worker = WorkerIR(
            worker_name="W", description="Test",
            main_flow=FlowRef(blocks=[BlockIR("b1", "SEQUENTIAL", spans=["s1"])]),
        )
        aggregator = ProvenanceAggregator()
        traces, _ = aggregator.aggregate(
            worker, [], [], ResourceRegistryIR(), SymbolTable(), spans,
        )
        ft = next(t for t in traces if t.target_ref == "flow:main")
        assert ft.source_section_id is None


# ---------------------------------------------------------------------------
# MVP+ Phase 1: worker trace section/packet provenance
# ---------------------------------------------------------------------------

class TestWorkerTraceSectionPacket:
    def test_main_worker_resolves_section_from_owned_spans(self) -> None:
        spans = [
            SpanIR("s_main", "Main task.",
                   source_section_id="sec_task_family"),
        ]
        worker = WorkerIR(
            worker_name="MainWorker", description="Test",
            main_flow=FlowRef(),
        )
        aggregator = ProvenanceAggregator()
        traces, _ = aggregator.aggregate(
            worker, [], [], ResourceRegistryIR(), SymbolTable(), spans,
            worker_owned_spans={"MainWorker": ["s_main"]},
        )
        wt = next(t for t in traces if t.target_ref == "worker:MainWorker")
        assert wt.source_section_id == "sec_task_family"

    def test_child_worker_resolves_section(self) -> None:
        spans = [
            SpanIR("s_child", "Child task.",
                   source_section_id="sec_delegation_policy"),
        ]
        worker = WorkerIR(
            worker_name="Main", description="Test",
            main_flow=FlowRef(),
            child_workers=[
                ChildWorkerIR(worker_name="Child", description="C",
                              task_text="Child task"),
            ],
        )
        aggregator = ProvenanceAggregator()
        traces, _ = aggregator.aggregate(
            worker, [], [], ResourceRegistryIR(), SymbolTable(), spans,
            worker_owned_spans={"Child": ["s_child"]},
        )
        ct = next(t for t in traces if t.target_ref == "worker:Child")
        assert ct.source_section_id == "sec_delegation_policy"

    def test_worker_without_owned_spans_gets_none(self) -> None:
        worker = WorkerIR(
            worker_name="MainWorker", description="Test",
            main_flow=FlowRef(),
        )
        aggregator = ProvenanceAggregator()
        traces, _ = aggregator.aggregate(
            worker, [], [], ResourceRegistryIR(), SymbolTable(), [],
        )
        wt = next(t for t in traces if t.target_ref == "worker:MainWorker")
        assert wt.source_section_id is None


# ---------------------------------------------------------------------------
# MVP+ Phase 1: handoff trace section/packet provenance
# ---------------------------------------------------------------------------

class TestHandoffTraceSectionPacket:
    def test_handoff_resolves_section_from_location_hint(self) -> None:
        from nl2spl.ir.worker_plan_ir import InvokeLocationHintIR, WorkerHandoffIR
        spans = [
            SpanIR("s_delegate", "Delegate to child.",
                   source_section_id="sec_delegation_policy"),
        ]
        handoffs = [
            WorkerHandoffIR(
                handoff_id="h1", from_worker="w_main",
                to_worker="w_child", api_ref=None, mode="invoke",
                condition_text=None, ordering="after",
                invoke_location_hint=InvokeLocationHintIR(
                    flow_kind="main", flow_id=None,
                    after_span_id="s_delegate", before_span_id=None,
                    block_hint="unknown",
                ),
            ),
        ]
        aggregator = ProvenanceAggregator()
        traces, _ = aggregator.aggregate(
            WorkerIR("W", "Test"), [], [],
            ResourceRegistryIR(), SymbolTable(), spans,
            handoffs=handoffs,
        )
        ht = next(t for t in traces if t.target_ref == "handoff:h1")
        assert ht.source_section_id == "sec_delegation_policy"

    def test_handoff_without_hint_spans_gets_none(self) -> None:
        from nl2spl.ir.worker_plan_ir import InvokeLocationHintIR, WorkerHandoffIR
        handoffs = [
            WorkerHandoffIR(
                handoff_id="h1", from_worker="w_main",
                to_worker="w_child", api_ref=None, mode="invoke",
                condition_text=None, ordering="after",
                invoke_location_hint=InvokeLocationHintIR(
                    flow_kind="main", flow_id=None,
                    after_span_id=None, before_span_id=None,
                    block_hint="unknown",
                ),
            ),
        ]
        aggregator = ProvenanceAggregator()
        traces, _ = aggregator.aggregate(
            WorkerIR("W", "Test"), [], [],
            ResourceRegistryIR(), SymbolTable(), [],
            handoffs=handoffs,
        )
        ht = next(t for t in traces if t.target_ref == "handoff:h1")
        assert ht.source_section_id is None


# ---------------------------------------------------------------------------
# MVP+ Phase 1: variable trace from adapter VariableFact
# ---------------------------------------------------------------------------

class TestVariableFactProvenance:
    def test_variable_from_adapter_fact_gets_section(self) -> None:
        resources = ResourceRegistryIR(
            variables=[VariableSpec("user_request", "text", True, "Request", "input")]
        )
        symbols = SymbolTable()
        symbols.declare("user_request", "text", "input", "Request")
        facts = [_FakeVariableFact("user_request", "sec_inputs_for_each_run")]
        aggregator = ProvenanceAggregator()
        traces, diags = aggregator.aggregate(
            WorkerIR("W", "Test"), [], [],
            resources, symbols, [],
            variable_facts=facts,
        )
        vt = next(t for t in traces if t.target_ref == "variable:user_request")
        assert vt.source_section_id == "sec_inputs_for_each_run"
        assert vt.relation == "normalized"
        assert not any(d.kind == "missing_provenance" and "user_request" in d.message
                       for d in diags)

    def test_variable_with_step_producer_still_prefers_step(self) -> None:
        """Step producer is stronger evidence than variable fact."""
        resources = ResourceRegistryIR(
            variables=[VariableSpec("result", "text", True, "Result", "output")]
        )
        symbols = SymbolTable()
        symbols.declare("result", "text", "output", "Result")
        steps = [StepIR("st1", "Produce", ["s_prod"], "GENERAL_COMMAND",
                        outputs=["result"])]
        spans = [SpanIR("s_prod", "Produce result.",
                        source_section_id="sec_reusable_process")]
        facts = [_FakeVariableFact("result", "sec_required_outputs")]
        aggregator = ProvenanceAggregator()
        traces, _ = aggregator.aggregate(
            WorkerIR("W", "Test"), steps, [],
            resources, symbols, spans,
            variable_facts=facts,
        )
        vt = next(t for t in traces if t.target_ref == "variable:result")
        # Step producer wins over variable fact
        assert vt.relation == "direct"
        assert vt.source_section_id == "sec_reusable_process"

    def test_variable_without_fact_or_producer_still_assumed(self) -> None:
        resources = ResourceRegistryIR(
            variables=[VariableSpec("orphan", "text", True, "Orphan", "output")]
        )
        symbols = SymbolTable()
        symbols.declare("orphan", "text", "output", "Orphan")
        aggregator = ProvenanceAggregator()
        traces, diags = aggregator.aggregate(
            WorkerIR("W", "Test"), [], [],
            resources, symbols, [],
            variable_facts=[],  # empty
        )
        vt = next(t for t in traces if t.target_ref == "variable:orphan")
        assert vt.relation == "assumed"

    def test_variable_fact_does_not_affect_unrelated_variable(self) -> None:
        resources = ResourceRegistryIR(
            variables=[
                VariableSpec("has_fact", "text", True, "Has", "input"),
                VariableSpec("no_fact", "text", True, "Missing", "output"),
            ]
        )
        symbols = SymbolTable()
        symbols.declare("has_fact", "text", "input", "Has")
        symbols.declare("no_fact", "text", "output", "Missing")
        facts = [_FakeVariableFact("has_fact", "sec_inputs_for_each_run")]
        aggregator = ProvenanceAggregator()
        traces, diags = aggregator.aggregate(
            WorkerIR("W", "Test"), [], [],
            resources, symbols, [],
            variable_facts=facts,
        )
        vt_has = next(t for t in traces if t.target_ref == "variable:has_fact")
        vt_no = next(t for t in traces if t.target_ref == "variable:no_fact")
        assert vt_has.source_section_id == "sec_inputs_for_each_run"
        assert vt_no.relation == "assumed"
