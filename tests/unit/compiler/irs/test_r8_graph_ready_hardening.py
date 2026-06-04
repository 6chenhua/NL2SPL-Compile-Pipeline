"""R8 Graph-ready Hardening tests.

Tests for edge generation, snapshot stability, and graph data integrity
across all v6 checkers.
"""

from __future__ import annotations

import pytest

from nl2spl.compiler.irs.checkers.worker_delegation import (
    WorkerDelegationIRSChecker,
)
from nl2spl.compiler.irs.context import IRSCheckContext
from nl2spl.compiler.irs.graph import ConstructGraph
from nl2spl.compiler.irs.instance import ConstructInstance
from nl2spl.ir.worker_plan_ir import (
    CandidateTaskUnitIR,
    WorkerPlanIR,
    WorkerSpecIR,
)


# ------------------------------------------------------------------
# R8.2: Worker/Delegation Edge Hardening
# ------------------------------------------------------------------


class TestR8WorkerDelegationEdges:
    """R8.2: Verify blocked_by, handoff_to, source_span_ids on edges."""

    def _make_context(self, plan: WorkerPlanIR) -> IRSCheckContext:
        return IRSCheckContext(
            stage_name="stage3_5",
            worker_plan=plan,
        )

    def test_blocked_promotion_has_blocked_by_edges(self) -> None:
        """Blocked promotion has one blocked_by edge per missing slot."""
        checker = WorkerDelegationIRSChecker()
        candidate = CandidateTaskUnitIR(
            candidate_id="cand_1",
            candidate_kind="explicit_delegation",
            source_span_ids=["s1"],
            task_text="Draft",
            purpose="Drafting",
            possible_inputs=[],
            possible_outputs=[],
            signals=["explicit_delegation"],
            risks=["no_clear_input_contract", "no_clear_output_contract"],
        )
        plan = WorkerPlanIR(
            main_worker_id="main",
            workers=[WorkerSpecIR(
                worker_id="main", worker_name="main", kind="main",
                purpose="Main", owned_span_ids=["s1"],
                input_contract=[], output_contract=[],
                depends_on=[], constraints=[],
                boundary_kind="main_worker",
                decision_evidence=[], reason="",
            )],
            candidates=[candidate],
            handoffs=[],
            decisions=[],
        )
        context = self._make_context(plan)
        instances = checker.extract_instances(context)
        promotion = [
            i for i in instances if i.construct_type == "WORKER_PROMOTION"
        ][0]
        from nl2spl.compiler.construct_registry import SPLConstructRegistry
        irs = SPLConstructRegistry.default().get("WORKER_PROMOTION")
        report = checker.check_instance(promotion, irs, context)

        blocked_by = [
            e for e in report.related_edges if e.edge_type == "blocked_by"
        ]
        # Promotion is blocked by missing input/output/invocation/handoff
        assert len(blocked_by) >= 1
        for edge in blocked_by:
            assert edge.from_id == report.construct_id
            assert "missing_slot:" in edge.to_id
            assert edge.source_span_ids == ["s1"]

    def test_blocked_by_count_matches_missing_slots(self) -> None:
        """blocked_by edge count equals number of missing promotion slots."""
        checker = WorkerDelegationIRSChecker()
        candidate = CandidateTaskUnitIR(
            candidate_id="cand_1",
            candidate_kind="explicit_delegation",
            source_span_ids=["s1"],
            task_text="Draft",
            purpose="Drafting",
            possible_inputs=[],
            possible_outputs=[],
            signals=["explicit_delegation"],
            risks=["no_clear_input_contract", "no_clear_output_contract"],
        )
        plan = WorkerPlanIR(
            main_worker_id="main",
            workers=[WorkerSpecIR(
                worker_id="main", worker_name="main", kind="main",
                purpose="Main", owned_span_ids=["s1"],
                input_contract=[], output_contract=[],
                depends_on=[], constraints=[],
                boundary_kind="main_worker",
                decision_evidence=[], reason="",
            )],
            candidates=[candidate],
            handoffs=[],
            decisions=[],
        )
        context = self._make_context(plan)
        instances = checker.extract_instances(context)
        promotion = [
            i for i in instances if i.construct_type == "WORKER_PROMOTION"
        ][0]
        from nl2spl.compiler.construct_registry import SPLConstructRegistry
        irs = SPLConstructRegistry.default().get("WORKER_PROMOTION")
        report = checker.check_instance(promotion, irs, context)

        blocked_by = [
            e for e in report.related_edges if e.edge_type == "blocked_by"
        ]
        # Missing slots from metadata
        missing = report.metadata.get("promotion_missing_slots", [])
        assert len(blocked_by) == len(missing)
        # Each blocked_by targets a different virtual node
        to_ids = {e.to_id for e in blocked_by}
        assert len(to_ids) == len(missing)

    def test_promotes_to_edge_has_source_spans(self) -> None:
        """promotes_to edge carries source_span_ids from candidate."""
        checker = WorkerDelegationIRSChecker()
        candidate = CandidateTaskUnitIR(
            candidate_id="cand_1",
            candidate_kind="explicit_delegation",
            source_span_ids=["s1", "s2"],
            task_text="Draft",
            purpose="Drafting",
            possible_inputs=[],
            possible_outputs=[],
            signals=["explicit_delegation"],
            risks=["no_clear_input_contract"],
        )
        plan = WorkerPlanIR(
            main_worker_id="main",
            workers=[WorkerSpecIR(
                worker_id="main", worker_name="main", kind="main",
                purpose="Main", owned_span_ids=["s1", "s2"],
                input_contract=[], output_contract=[],
                depends_on=[], constraints=[],
                boundary_kind="main_worker",
                decision_evidence=[], reason="",
            )],
            candidates=[candidate],
            handoffs=[],
            decisions=[],
        )
        context = self._make_context(plan)
        instances = checker.extract_instances(context)
        promotion = [
            i for i in instances if i.construct_type == "WORKER_PROMOTION"
        ][0]
        from nl2spl.compiler.construct_registry import SPLConstructRegistry
        irs = SPLConstructRegistry.default().get("WORKER_PROMOTION")
        report = checker.check_instance(promotion, irs, context)

        promotes = [
            e for e in report.related_edges if e.edge_type == "promotes_to"
        ]
        assert len(promotes) == 1
        assert promotes[0].source_span_ids == ["s1", "s2"]
        assert promotes[0].metadata["candidate_id"] == "cand_1"


# ------------------------------------------------------------------
# R8.3: Stage4 ExceptionFlow Edges
# ------------------------------------------------------------------


class TestR8ExceptionFlowEdges:
    """R8.3: Verify handles and contains edges on exception flow reports."""

    def test_exception_flow_has_handles_edge(self) -> None:
        """Source-backed exception flow has handles condition edge."""
        from nl2spl.compiler.construct_registry import SPLConstructRegistry
        from nl2spl.compiler.irs.checkers.exception_flow import (
            Stage4ExceptionFlowIRSChecker,
        )
        from nl2spl.ir.flow_structure_ir import ExceptionFlow, FlowStructureIR

        checker = Stage4ExceptionFlowIRSChecker()
        flow = FlowStructureIR(
            exception_flows=[
                ExceptionFlow("exc_1", "Missing timeframe", ["s1"]),
            ],
        )
        ctx = IRSCheckContext(stage_name="stage4", flow=flow)
        instances = checker.extract_instances(ctx)
        irs = SPLConstructRegistry.default().get("EXCEPTION_FLOW")
        report = checker.check_instance(instances[0], irs, ctx)

        handles = [
            e for e in report.related_edges if e.edge_type == "handles"
        ]
        assert len(handles) == 1
        assert handles[0].from_id == "exception_flow:exc_1"
        assert handles[0].to_id == "condition:exc_1"
        assert handles[0].source_span_ids == ["s1"]
        assert handles[0].metadata["condition_text"] == "Missing timeframe"

    def test_exception_flow_worker_contains_edge(self) -> None:
        """Worker-scoped exception flow has worker contains edge."""
        from nl2spl.compiler.construct_registry import SPLConstructRegistry
        from nl2spl.compiler.irs.checkers.exception_flow import (
            Stage4ExceptionFlowIRSChecker,
        )
        from nl2spl.ir.flow_structure_ir import ExceptionFlow, FlowStructureIR

        checker = Stage4ExceptionFlowIRSChecker()
        flow = FlowStructureIR(
            exception_flows=[
                ExceptionFlow("exc_1", "Cond", ["s1"]),
            ],
        )
        ctx = IRSCheckContext(
            stage_name="stage4",
            worker_flows=type("WFP", (), {
                "worker_flows": {"main": flow}
            })(),
        )
        instances = checker.extract_instances(ctx)
        irs = SPLConstructRegistry.default().get("EXCEPTION_FLOW")
        report = checker.check_instance(instances[0], irs, ctx)

        contains = [
            e for e in report.related_edges if e.edge_type == "contains"
        ]
        assert len(contains) == 1
        assert contains[0].from_id == "worker:main"
        assert contains[0].to_id == "worker:main.exception_flow:exc_1"

    def test_exception_flow_handles_edge_empty_spans(self) -> None:
        """Exception flow with no spans still has handles edge (empty spans)."""
        from nl2spl.compiler.construct_registry import SPLConstructRegistry
        from nl2spl.compiler.irs.checkers.exception_flow import (
            Stage4ExceptionFlowIRSChecker,
        )
        from nl2spl.ir.flow_structure_ir import ExceptionFlow, FlowStructureIR

        checker = Stage4ExceptionFlowIRSChecker()
        flow = FlowStructureIR(
            exception_flows=[
                ExceptionFlow("exc_1", "Vague", []),
            ],
        )
        ctx = IRSCheckContext(stage_name="stage4", flow=flow)
        instances = checker.extract_instances(ctx)
        irs = SPLConstructRegistry.default().get("EXCEPTION_FLOW")
        report = checker.check_instance(instances[0], irs, ctx)

        handles = [
            e for e in report.related_edges if e.edge_type == "handles"
        ]
        assert len(handles) == 1
        assert handles[0].source_span_ids == []


# ------------------------------------------------------------------
# R8.4: Stage7 Step Variable And Invocation Edges
# ------------------------------------------------------------------


class TestR8StepEdges:
    """R8.4: Verify produces/consumes/invokes/handoff_to edges on steps."""

    def _make_step(self, **kwargs):
        from nl2spl.ir.step_ir import StepIR
        defaults = dict(
            step_id="st_1", text="Do something",
            command_type="GENERAL_COMMAND", source_span_ids=["s1"],
        )
        defaults.update(kwargs)
        return StepIR(**defaults)

    def test_step_consumes_variable(self) -> None:
        """Step with inputs produces consumes edges with source spans."""
        from nl2spl.compiler.construct_registry import SPLConstructRegistry
        from nl2spl.compiler.irs.checkers.step import Stage7StepIRSChecker

        checker = Stage7StepIRSChecker()
        step = self._make_step(inputs=["topic", "tone"])
        ctx = IRSCheckContext(stage_name="stage7", steps=(step,))
        instances = checker.extract_instances(ctx)
        irs = SPLConstructRegistry.default().get("GENERAL_COMMAND")
        report = checker.check_instance(instances[0], irs, ctx)

        consumes = [
            e for e in report.related_edges if e.edge_type == "consumes"
        ]
        assert len(consumes) == 2
        for edge in consumes:
            assert edge.source_span_ids == ["s1"]
            assert edge.metadata["edge_source"] == "step_ir"
            assert "variable_name" in edge.metadata

    def test_step_produces_variable(self) -> None:
        """Step with outputs produces produces edges with source spans."""
        from nl2spl.compiler.construct_registry import SPLConstructRegistry
        from nl2spl.compiler.irs.checkers.step import Stage7StepIRSChecker

        checker = Stage7StepIRSChecker()
        step = self._make_step(outputs=["draft"])
        ctx = IRSCheckContext(stage_name="stage7", steps=(step,))
        instances = checker.extract_instances(ctx)
        irs = SPLConstructRegistry.default().get("GENERAL_COMMAND")
        report = checker.check_instance(instances[0], irs, ctx)

        produces = [
            e for e in report.related_edges if e.edge_type == "produces"
        ]
        assert len(produces) == 1
        assert produces[0].to_id == "variable:draft"
        assert produces[0].source_span_ids == ["s1"]
        assert produces[0].metadata["variable_name"] == "draft"

    def test_invoke_worker_invokes_child(self) -> None:
        """INVOKE_WORKER with integration_ref produces invokes edge."""
        from nl2spl.compiler.construct_registry import SPLConstructRegistry
        from nl2spl.compiler.irs.checkers.step import Stage7StepIRSChecker

        checker = Stage7StepIRSChecker()
        step = self._make_step(
            command_type="INVOKE_WORKER",
            integration_ref="child_worker",
            handoff_id="ho_1",
        )
        ctx = IRSCheckContext(stage_name="stage7", steps=(step,))
        instances = checker.extract_instances(ctx)
        irs = SPLConstructRegistry.default().get("INVOKE_WORKER")
        report = checker.check_instance(instances[0], irs, ctx)

        invokes = [
            e for e in report.related_edges if e.edge_type == "invokes"
        ]
        assert len(invokes) == 1
        assert invokes[0].to_id == "child_worker:child_worker"

        handoff = [
            e for e in report.related_edges if e.edge_type == "handoff_to"
        ]
        assert len(handoff) == 1
        assert handoff[0].to_id == "worker_handoff:ho_1"

    def test_call_api_invokes_api(self) -> None:
        """CALL_API with integration_ref produces invokes api edge."""
        from nl2spl.compiler.construct_registry import SPLConstructRegistry
        from nl2spl.compiler.irs.checkers.step import Stage7StepIRSChecker

        checker = Stage7StepIRSChecker()
        step = self._make_step(
            command_type="CALL_API",
            integration_ref="payment_api",
        )
        ctx = IRSCheckContext(stage_name="stage7", steps=(step,))
        instances = checker.extract_instances(ctx)
        irs = SPLConstructRegistry.default().get("CALL_API")
        report = checker.check_instance(instances[0], irs, ctx)

        invokes = [
            e for e in report.related_edges if e.edge_type == "invokes"
        ]
        assert len(invokes) == 1
        assert invokes[0].to_id == "api:payment_api"

    def test_step_edges_not_sharing_mutable_list(self) -> None:
        """Each edge has its own source_span_ids list (no shared mutation)."""
        from nl2spl.compiler.construct_registry import SPLConstructRegistry
        from nl2spl.compiler.irs.checkers.step import Stage7StepIRSChecker

        checker = Stage7StepIRSChecker()
        step = self._make_step(inputs=["inp1", "inp2"], outputs=["out"])
        ctx = IRSCheckContext(stage_name="stage7", steps=(step,))
        instances = checker.extract_instances(ctx)
        irs = SPLConstructRegistry.default().get("GENERAL_COMMAND")
        report = checker.check_instance(instances[0], irs, ctx)

        edges = report.related_edges
        # Mutate the first edge's spans
        edges[0].source_span_ids.append("MUTATED")
        # Other edges must not be affected
        for other in edges[1:]:
            assert "MUTATED" not in other.source_span_ids

    def test_display_message_no_edges(self) -> None:
        """DISPLAY_MESSAGE steps produce no instances or edges."""
        from nl2spl.compiler.irs.checkers.step import Stage7StepIRSChecker

        checker = Stage7StepIRSChecker()
        step = self._make_step(
            command_type="DISPLAY_MESSAGE",
            source_span_ids=["s1"],
        )
        ctx = IRSCheckContext(stage_name="stage7", steps=(step,))
        instances = checker.extract_instances(ctx)
        assert len(instances) == 0


# ------------------------------------------------------------------
# R8.5: Construct Path Stability
# ------------------------------------------------------------------


class TestR8ConstructPathStability:
    """R8.5: Verify construct_path is always a tuple."""

    def test_exception_flow_construct_path_tuple(self) -> None:
        """EXCEPTION_FLOW construct_path is a tuple."""
        from nl2spl.compiler.construct_registry import SPLConstructRegistry
        from nl2spl.compiler.irs.checkers.exception_flow import (
            Stage4ExceptionFlowIRSChecker,
        )
        from nl2spl.ir.flow_structure_ir import ExceptionFlow, FlowStructureIR

        checker = Stage4ExceptionFlowIRSChecker()
        flow = FlowStructureIR(
            exception_flows=[ExceptionFlow("exc_1", "Cond", ["s1"])],
        )
        ctx = IRSCheckContext(stage_name="stage4", flow=flow)
        instances = checker.extract_instances(ctx)
        assert isinstance(instances[0].construct_path, tuple)
        assert instances[0].construct_path == (
            "flow", "exception_flows", "exc_1",
        )

    def test_step_construct_path_tuple(self) -> None:
        """STEP construct_path is a tuple."""
        from nl2spl.compiler.irs.checkers.step import Stage7StepIRSChecker
        from nl2spl.ir.step_ir import StepIR

        checker = Stage7StepIRSChecker()
        step = StepIR(
            step_id="st_1", text="Do",
            command_type="GENERAL_COMMAND", source_span_ids=["s1"],
        )
        ctx = IRSCheckContext(stage_name="stage7", steps=(step,))
        instances = checker.extract_instances(ctx)
        assert isinstance(instances[0].construct_path, tuple)
        assert instances[0].construct_path == ("steps", "st_1")

    def test_worker_scoped_exception_flow_path(self) -> None:
        """Worker-scoped EXCEPTION_FLOW path includes worker_id."""
        from nl2spl.compiler.irs.checkers.exception_flow import (
            Stage4ExceptionFlowIRSChecker,
        )
        from nl2spl.ir.flow_structure_ir import ExceptionFlow, FlowStructureIR

        checker = Stage4ExceptionFlowIRSChecker()
        flow = FlowStructureIR(
            exception_flows=[ExceptionFlow("exc_1", "Cond", ["s1"])],
        )
        ctx = IRSCheckContext(
            stage_name="stage4",
            worker_flows=type("WFP", (), {
                "worker_flows": {"main": flow}
            })(),
        )
        instances = checker.extract_instances(ctx)
        assert instances[0].construct_path == (
            "worker_flow_plan", "main", "exception_flows", "exc_1",
        )

    def test_worker_scoped_step_path(self) -> None:
        """Worker-scoped STEP path includes worker_id."""
        from nl2spl.compiler.irs.checkers.step import Stage7StepIRSChecker
        from nl2spl.ir.step_ir import StepIR
        from nl2spl.ir.worker_plan_ir import WorkerStepPlanIR

        checker = Stage7StepIRSChecker()
        step = StepIR(
            step_id="st_1", text="Do",
            command_type="GENERAL_COMMAND", source_span_ids=["s1"],
        )
        wsp = WorkerStepPlanIR(
            main_worker_id="main",
            worker_steps={"main": [step]},
        )
        ctx = IRSCheckContext(stage_name="stage7", worker_steps=wsp)
        instances = checker.extract_instances(ctx)
        assert instances[0].construct_path == (
            "worker_step_plan", "main", "steps", "st_1",
        )


# ------------------------------------------------------------------
# R8.6: Runner-Level Edge Snapshot Tests
# ------------------------------------------------------------------


class TestR8RunnerEdgeSnapshot:
    """R8.6: Verify runner-produced edge snapshots are deterministic."""

    def test_runner_stage4_edge_snapshot_stable(self) -> None:
        """Runner stage4 reports have deterministic edge snapshots."""
        from nl2spl.compiler.irs import build_irs_runner
        from nl2spl.ir.flow_structure_ir import ExceptionFlow, FlowStructureIR

        runner = build_irs_runner(enable_exception_flow=True)
        flow = FlowStructureIR(
            exception_flows=[
                ExceptionFlow("exc_1", "Cond", ["s1"]),
            ],
        )
        ctx = IRSCheckContext(stage_name="stage4", flow=flow)
        result = runner.run_stage("stage4", ctx)

        # Collect all edges from all reports
        all_edges = []
        for report in result.reports:
            all_edges.extend(report.related_edges)

        # Snapshot must be deterministic
        graph = ConstructGraph(edges=all_edges)
        snap1 = graph.edge_snapshots()
        snap2 = graph.edge_snapshots()
        assert snap1 == snap2

        # Must contain handles edge
        handles = [s for s in snap1 if s["edge_type"] == "handles"]
        assert len(handles) == 1

    def test_runner_stage7_edge_snapshot_stable(self) -> None:
        """Runner stage7 reports have deterministic edge snapshots."""
        from nl2spl.compiler.irs import build_irs_runner
        from nl2spl.ir.step_ir import StepIR

        runner = build_irs_runner(enable_step=True)
        step = StepIR(
            step_id="st_1", text="Do",
            command_type="GENERAL_COMMAND",
            source_span_ids=["s1"],
            inputs=["topic"],
            outputs=["draft"],
        )
        ctx = IRSCheckContext(stage_name="stage7", steps=(step,))
        result = runner.run_stage("stage7", ctx)

        all_edges = []
        for report in result.reports:
            all_edges.extend(report.related_edges)

        graph = ConstructGraph(edges=all_edges)
        snap1 = graph.edge_snapshots()
        snap2 = graph.edge_snapshots()
        assert snap1 == snap2

        # Must contain consumes and produces edges
        consumes = [s for s in snap1 if s["edge_type"] == "consumes"]
        produces = [s for s in snap1 if s["edge_type"] == "produces"]
        assert len(consumes) == 1
        assert len(produces) == 1


# ------------------------------------------------------------------
# R8: Canonical snapshot and deduped nodes
# ------------------------------------------------------------------


class TestR8CanonicalSnapshot:
    """Verify edge_snapshots() is canonical regardless of input order."""

    def test_edge_snapshot_order_independent(self) -> None:
        """Same edges in different order produce same snapshot.

        Tests the critical case: same (edge_type, from_id, to_id) but
        different source_span_ids — old sorting key would not canonicalize.
        """
        from nl2spl.compiler.irs.graph import ConstructEdge

        e1 = ConstructEdge(
            from_id="a", to_id="b", edge_type="consumes",
            source_span_ids=["s2"],
        )
        e2 = ConstructEdge(
            from_id="a", to_id="b", edge_type="consumes",
            source_span_ids=["s1"],
        )
        g1 = ConstructGraph(edges=[e2, e1])
        g2 = ConstructGraph(edges=[e1, e2])
        assert g1.edge_snapshots() == g2.edge_snapshots()


class TestR8DedupedNodes:
    """Verify deduped() preserves nodes from edges."""

    def test_deduped_reconstructs_nodes_from_edges(self) -> None:
        """deduped().nodes includes all edge endpoints."""
        from nl2spl.compiler.irs.graph import ConstructEdge

        graph = ConstructGraph(edges=[
            ConstructEdge(from_id="a", to_id="b", edge_type="contains"),
            ConstructEdge(from_id="b", to_id="c", edge_type="produces"),
        ])
        deduped = graph.deduped()
        assert "a" in deduped.nodes
        assert "b" in deduped.nodes
        assert "c" in deduped.nodes

    def test_deduped_preserves_isolated_nodes(self) -> None:
        """deduped().nodes preserves explicitly added isolated nodes."""
        from nl2spl.compiler.irs.graph import ConstructEdge

        graph = ConstructGraph(
            nodes=["isolated"],
            edges=[
                ConstructEdge(from_id="a", to_id="b", edge_type="contains"),
            ],
        )
        deduped = graph.deduped()
        assert "isolated" in deduped.nodes
        assert "a" in deduped.nodes
        assert "b" in deduped.nodes
