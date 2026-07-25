"""R10: IRS Runtime Subsystem Foundation tests.

Covers the 9 required test cases from the R10 implementation plan:
1. IRSRuntimeConfig defaults
2. IRSResultStore multi-stage save
3. IRSResultStore deterministic payload
4. IRSResultStore no shared mutable list
5. IRSSubsystem.run_stage_local calls runner
6. Empty registry returns empty result
7. IRSSubsystem.run_post_normalize uses IRSRunner
8. No LLM import in new modules
9. No orchestrator import in new modules

Plus P1/P2 review fixes:
- Graph snapshot built and stored
- Warnings/post-normalize in payload
- Graph deep-copy isolation
- post-normalize runner/context proof
"""

from __future__ import annotations

import inspect
from unittest.mock import MagicMock

import pytest

from nl2spl.compiler.construct_registry import (
    ConstructSatisfactionReport,
    SPLConstructRegistry,
)
from nl2spl.compiler.irs.context import IRSCheckContext
from nl2spl.compiler.irs.factory import build_irs_subsystem
from nl2spl.compiler.irs.graph import ConstructEdge, ConstructGraph
from nl2spl.compiler.irs.instance import ConstructInstance
from nl2spl.compiler.irs.policy import IRSRuntimeConfig
from nl2spl.compiler.irs.registry import IRSCheckerRegistry
from nl2spl.compiler.irs.result_store import IRSResultStore, IRSStageResult
from nl2spl.compiler.irs.runner import IRSRunner, IRSRunResult
from nl2spl.compiler.irs.subsystem import IRSSubsystem
from nl2spl.ir.diagnostics import CompileDiagnostic

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


class _FakeChecker:
    """Minimal IRSChecker implementation for testing."""

    checker_id: str = "fake_checker"
    supported_construct_types: tuple[str, ...] = ("GENERAL_COMMAND",)
    supported_stages: tuple[str, ...] = ("test_stage",)

    def extract_instances(self, context: IRSCheckContext) -> list[ConstructInstance]:
        return [
            ConstructInstance(
                construct_id="cmd_1",
                construct_type="GENERAL_COMMAND",
                source_span_ids=["s1"],
            )
        ]

    def check_instance(
        self,
        instance: ConstructInstance,
        irs: object,
        context: IRSCheckContext,
    ) -> ConstructSatisfactionReport:
        return ConstructSatisfactionReport(
            construct_id=instance.construct_id,
            construct_type=instance.construct_type,
            slots=(),
            completeness="complete",
            renderable=True,
        )


class _FakeCheckerWithEdges:
    """Checker that produces reports with related_edges for graph testing."""

    checker_id: str = "fake_edge_checker"
    supported_construct_types: tuple[str, ...] = ("GENERAL_COMMAND",)
    supported_stages: tuple[str, ...] = ("test_stage",)

    def extract_instances(self, context: IRSCheckContext) -> list[ConstructInstance]:
        return [
            ConstructInstance(
                construct_id="cmd_1",
                construct_type="GENERAL_COMMAND",
                source_span_ids=["s1"],
            ),
            ConstructInstance(
                construct_id="cmd_2",
                construct_type="GENERAL_COMMAND",
                source_span_ids=["s2"],
            ),
        ]

    def check_instance(
        self,
        instance: ConstructInstance,
        irs: object,
        context: IRSCheckContext,
    ) -> ConstructSatisfactionReport:
        edges = []
        if instance.construct_id == "cmd_1":
            edges = [
                ConstructEdge(
                    from_id="cmd_1",
                    to_id="cmd_2",
                    edge_type="contains",
                    source_span_ids=["s1"],
                )
            ]
        return ConstructSatisfactionReport(
            construct_id=instance.construct_id,
            construct_type=instance.construct_type,
            slots=(),
            completeness="complete",
            renderable=True,
            related_edges=edges,
        )


def _make_report(construct_id: str = "r1") -> ConstructSatisfactionReport:
    """Create a minimal report for testing."""
    return ConstructSatisfactionReport(
        construct_id=construct_id,
        construct_type="GENERAL_COMMAND",
        slots=(),
        completeness="complete",
        renderable=True,
    )


def _make_diagnostic(diag_id: str = "diag_1") -> CompileDiagnostic:
    """Create a minimal diagnostic for testing."""
    return CompileDiagnostic(
        diagnostic_id=diag_id,
        kind="type_or_contract_ambiguity",
        severity="warning",
        message="test diagnostic",
        target_ref="cmd_1",
    )


def _make_report_with_edges(
    construct_id: str = "cmd_1",
    edges: list[ConstructEdge] | None = None,
) -> ConstructSatisfactionReport:
    """Create a report with related_edges for graph snapshot testing."""
    return ConstructSatisfactionReport(
        construct_id=construct_id,
        construct_type="GENERAL_COMMAND",
        slots=(),
        completeness="complete",
        renderable=True,
        related_edges=edges or [],
    )


# ------------------------------------------------------------------
# 1. IRSRuntimeConfig defaults
# ------------------------------------------------------------------


class TestIRSRuntimeConfigDefaults:
    """Verify IRSRuntimeConfig default values match product design."""

    def test_defaults(self) -> None:
        config = IRSRuntimeConfig()
        assert config.enabled is True
        assert config.stage_local_enabled is True
        assert config.worker_delegation_enabled is True
        assert config.exception_flow_enabled is True
        assert config.step_enabled is True
        assert config.post_normalize_enabled is True
        assert config.include_stage_local_diagnostics_in_compile is False
        assert config.include_construct_satisfaction_in_feedback is True
        assert config.collect_graph_snapshot is True

    def test_frozen(self) -> None:
        config = IRSRuntimeConfig()
        with pytest.raises(AttributeError):
            config.enabled = False  # type: ignore[misc]


# ------------------------------------------------------------------
# 2. IRSResultStore multi-stage save
# ------------------------------------------------------------------


class TestIRSResultStoreMultiStage:
    """Verify IRSResultStore can save and retrieve multiple stages."""

    def test_save_and_retrieve_multiple_stages(self) -> None:
        store = IRSResultStore()
        r1 = IRSStageResult(
            stage_name="stage3_5",
            reports=(_make_report("r1"),),
            diagnostics=(_make_diagnostic("d1"),),
        )
        r2 = IRSStageResult(
            stage_name="stage4",
            reports=(_make_report("r2"),),
            diagnostics=(),
        )
        store.put_stage_result(r1)
        store.put_stage_result(r2)

        assert store.get_stage_result("stage3_5") is r1
        assert store.get_stage_result("stage4") is r2
        assert store.get_stage_result("stage7") is None
        assert len(store.get_all_stage_results()) == 2

    def test_post_normalize_diagnostics(self) -> None:
        store = IRSResultStore()
        diags = [_make_diagnostic("pn1"), _make_diagnostic("pn2")]
        store.put_post_normalize_diagnostics(diags)

        retrieved = store.get_post_normalize_diagnostics()
        assert len(retrieved) == 2
        assert retrieved[0].diagnostic_id == "pn1"
        assert retrieved[1].diagnostic_id == "pn2"


# ------------------------------------------------------------------
# 3. IRSResultStore deterministic payload
# ------------------------------------------------------------------


class TestIRSResultStoreDeterministic:
    """Verify to_intermediate_payload is deterministic and complete."""

    def test_deterministic_output(self) -> None:
        store = IRSResultStore()
        store.put_stage_result(IRSStageResult(
            stage_name="stage4",
            reports=(_make_report("r2"),),
        ))
        store.put_stage_result(IRSStageResult(
            stage_name="stage3_5",
            reports=(_make_report("r1"),),
            diagnostics=(_make_diagnostic("d1"),),
        ))

        payload1 = store.to_intermediate_payload()
        payload2 = store.to_intermediate_payload()

        # Same structure
        assert payload1.keys() == payload2.keys()
        assert (
            payload1["construct_satisfaction"].keys()
            == payload2["construct_satisfaction"].keys()
        )
        # Sorted by stage name
        stage_names = list(payload1["construct_satisfaction"].keys())
        assert stage_names == ["stage3_5", "stage4"]
        # Reports are list copies, not same objects
        assert (
            payload1["construct_satisfaction"]["stage3_5"]
            == payload2["construct_satisfaction"]["stage3_5"]
        )

    def test_payload_contains_construct_satisfaction_and_stage_local_diagnostics(
        self,
    ) -> None:
        store = IRSResultStore()
        store.put_stage_result(IRSStageResult(
            stage_name="stage3_5",
            reports=(_make_report("r1"),),
            diagnostics=(_make_diagnostic("d1"),),
        ))
        payload = store.to_intermediate_payload()
        assert "construct_satisfaction" in payload
        assert "stage_local_diagnostics" in payload
        assert len(payload["construct_satisfaction"]["stage3_5"]) == 1
        assert len(payload["stage_local_diagnostics"]["stage3_5"]) == 1

    def test_payload_contains_graph_snapshot(self) -> None:
        """Graph snapshot from stage result appears as deterministic dict."""
        edge = ConstructEdge(
            from_id="cmd_1", to_id="cmd_2", edge_type="contains",
        )
        graph = ConstructGraph(nodes=["cmd_1", "cmd_2"], edges=[edge])
        store = IRSResultStore()
        store.put_stage_result(IRSStageResult(
            stage_name="stage3_5",
            reports=(_make_report("r1"),),
            graph=graph,
        ))
        payload = store.to_intermediate_payload()
        assert "irs_stage_results" in payload
        stage_data = payload["irs_stage_results"]["stage3_5"]

        # Graph is a snapshot dict, not a ConstructGraph object
        graph_snap = stage_data["graph"]
        assert isinstance(graph_snap, dict)
        assert "nodes" in graph_snap
        assert "edges" in graph_snap
        # Nodes are sorted
        assert graph_snap["nodes"] == ["cmd_1", "cmd_2"]
        # Edges are snapshot dicts
        assert len(graph_snap["edges"]) == 1
        assert isinstance(graph_snap["edges"][0], dict)
        assert graph_snap["edges"][0]["from_id"] == "cmd_1"
        assert graph_snap["edges"][0]["to_id"] == "cmd_2"

    def test_payload_graph_is_none_when_no_graph(self) -> None:
        """Graph in payload is None when stage result has no graph."""
        store = IRSResultStore()
        store.put_stage_result(IRSStageResult(
            stage_name="stage4",
            reports=(_make_report("r1"),),
            graph=None,
        ))
        payload = store.to_intermediate_payload()
        assert payload["irs_stage_results"]["stage4"]["graph"] is None

    def test_payload_graph_mutation_does_not_affect_store(self) -> None:
        """Mutating the payload graph snapshot does not pollute the store."""
        edge = ConstructEdge(
            from_id="cmd_1", to_id="cmd_2", edge_type="contains",
        )
        graph = ConstructGraph(nodes=["cmd_1", "cmd_2"], edges=[edge])
        store = IRSResultStore()
        store.put_stage_result(IRSStageResult(
            stage_name="stage3_5",
            reports=(_make_report("r1"),),
            graph=graph,
        ))

        payload1 = store.to_intermediate_payload()
        # Mutate the payload graph snapshot
        payload1["irs_stage_results"]["stage3_5"]["graph"]["nodes"].append("cmd_3")
        payload1["irs_stage_results"]["stage3_5"]["graph"]["edges"].append(
            {"from_id": "x", "to_id": "y", "edge_type": "produces",
             "source_span_ids": [], "metadata": {}}
        )

        # Re-generate payload — store is unaffected
        payload2 = store.to_intermediate_payload()
        assert payload2["irs_stage_results"]["stage3_5"]["graph"]["nodes"] == [
            "cmd_1", "cmd_2"
        ]
        assert len(payload2["irs_stage_results"]["stage3_5"]["graph"]["edges"]) == 1

    def test_payload_contains_warnings(self) -> None:
        """Warnings from stage result appear in payload."""
        store = IRSResultStore()
        store.put_stage_result(IRSStageResult(
            stage_name="stage4",
            reports=(),
            warnings=("skipped unknown type",),
        ))
        payload = store.to_intermediate_payload()
        stage_data = payload["irs_stage_results"]["stage4"]
        assert stage_data["warnings"] == ["skipped unknown type"]

    def test_payload_contains_post_normalize_diagnostics(self) -> None:
        """Post-normalize diagnostics appear in payload."""
        store = IRSResultStore()
        store.put_post_normalize_diagnostics([_make_diagnostic("pn1")])
        payload = store.to_intermediate_payload()
        assert "irs_post_normalize_diagnostics" in payload
        assert len(payload["irs_post_normalize_diagnostics"]) == 1
        assert payload["irs_post_normalize_diagnostics"][0].diagnostic_id == "pn1"


# ------------------------------------------------------------------
# 4. IRSResultStore no shared mutable list
# ------------------------------------------------------------------


class TestIRSResultStoreNoSharedMutableList:
    """Verify input list mutation does not affect stored data."""

    def test_reports_copied_to_tuple(self) -> None:
        reports_list = [_make_report("r1")]
        result = IRSStageResult(
            stage_name="test",
            reports=reports_list,
        )
        # Mutate original list
        reports_list.append(_make_report("r2"))
        # Stored tuple is unaffected
        assert len(result.reports) == 1

    def test_diagnostics_copied_to_tuple(self) -> None:
        diags_list = [_make_diagnostic("d1")]
        result = IRSStageResult(
            stage_name="test",
            diagnostics=diags_list,
        )
        diags_list.append(_make_diagnostic("d2"))
        assert len(result.diagnostics) == 1

    def test_post_normalize_diagnostics_copied(self) -> None:
        store = IRSResultStore()
        diags = [_make_diagnostic("d1")]
        store.put_post_normalize_diagnostics(diags)
        diags.append(_make_diagnostic("d2"))
        assert len(store.get_post_normalize_diagnostics()) == 1

    def test_get_post_normalize_returns_copy(self) -> None:
        store = IRSResultStore()
        store.put_post_normalize_diagnostics([_make_diagnostic("d1")])
        retrieved = store.get_post_normalize_diagnostics()
        retrieved.append(_make_diagnostic("d2"))
        # Original store unaffected
        assert len(store.get_post_normalize_diagnostics()) == 1

    def test_graph_deep_copied_on_store(self) -> None:
        """Mutating original graph after store does not affect stored snapshot."""
        edge = ConstructEdge(
            from_id="cmd_1", to_id="cmd_2", edge_type="contains",
        )
        graph = ConstructGraph(nodes=["cmd_1", "cmd_2"], edges=[edge])
        result = IRSStageResult(stage_name="test", graph=graph)

        # Mutate original graph
        graph.nodes.append("cmd_3")
        graph.edges.append(
            ConstructEdge(from_id="cmd_2", to_id="cmd_3", edge_type="produces")
        )
        # Stored graph is unaffected
        assert len(result.graph.nodes) == 2  # type: ignore[union-attr]
        assert len(result.graph.edges) == 1  # type: ignore[union-attr]

    def test_graph_edge_source_span_ids_deep_copied(self) -> None:
        """Edge source_span_ids are deep-copied, not shared."""
        edge = ConstructEdge(
            from_id="cmd_1",
            to_id="cmd_2",
            edge_type="contains",
            source_span_ids=["s1"],
        )
        graph = ConstructGraph(nodes=["cmd_1", "cmd_2"], edges=[edge])
        result = IRSStageResult(stage_name="test", graph=graph)

        # Mutate original edge's source_span_ids
        edge.source_span_ids.append("s2")
        # Stored edge is unaffected
        assert result.graph.edges[0].source_span_ids == ["s1"]  # type: ignore[union-attr]


# ------------------------------------------------------------------
# 5. IRSSubsystem.run_stage_local calls runner
# ------------------------------------------------------------------


class TestIRSSubsystemRunStageLocal:
    """Verify IRSSubsystem.run_stage_local delegates to IRSRunner."""

    def test_calls_runner_and_returns_stage_result(self) -> None:
        registry = IRSCheckerRegistry()
        registry.register(_FakeChecker())
        construct_registry = SPLConstructRegistry.default()
        runner = IRSRunner(
            registry=registry,
            construct_registry=construct_registry,
        )
        config = IRSRuntimeConfig()
        subsystem = IRSSubsystem(config=config, runner=runner)

        context = IRSCheckContext(stage_name="test_stage")
        result = subsystem.run_stage_local("test_stage", context)

        assert isinstance(result, IRSStageResult)
        assert result.stage_name == "test_stage"
        assert len(result.reports) == 1
        assert result.reports[0].construct_id == "cmd_1"
        assert result.reports[0].construct_type == "GENERAL_COMMAND"

    def test_returns_tuple_not_list(self) -> None:
        registry = IRSCheckerRegistry()
        registry.register(_FakeChecker())
        runner = IRSRunner(
            registry=registry,
            construct_registry=SPLConstructRegistry.default(),
        )
        subsystem = IRSSubsystem(config=IRSRuntimeConfig(), runner=runner)
        context = IRSCheckContext(stage_name="test_stage")
        result = subsystem.run_stage_local("test_stage", context)

        assert isinstance(result.reports, tuple)
        assert isinstance(result.diagnostics, tuple)
        assert isinstance(result.warnings, tuple)

    def test_graph_snapshot_built_when_enabled(self) -> None:
        """Graph snapshot is built from report edges when collect_graph_snapshot=True."""
        registry = IRSCheckerRegistry()
        registry.register(_FakeCheckerWithEdges())
        runner = IRSRunner(
            registry=registry,
            construct_registry=SPLConstructRegistry.default(),
        )
        config = IRSRuntimeConfig(collect_graph_snapshot=True)
        subsystem = IRSSubsystem(config=config, runner=runner)
        context = IRSCheckContext(stage_name="test_stage")
        result = subsystem.run_stage_local("test_stage", context)

        assert result.graph is not None
        assert "cmd_1" in result.graph.nodes
        assert "cmd_2" in result.graph.nodes
        assert len(result.graph.edges) == 1
        assert result.graph.edges[0].from_id == "cmd_1"
        assert result.graph.edges[0].to_id == "cmd_2"

    def test_graph_snapshot_none_when_disabled(self) -> None:
        """Graph snapshot is None when collect_graph_snapshot=False."""
        registry = IRSCheckerRegistry()
        registry.register(_FakeCheckerWithEdges())
        runner = IRSRunner(
            registry=registry,
            construct_registry=SPLConstructRegistry.default(),
        )
        config = IRSRuntimeConfig(collect_graph_snapshot=False)
        subsystem = IRSSubsystem(config=config, runner=runner)
        context = IRSCheckContext(stage_name="test_stage")
        result = subsystem.run_stage_local("test_stage", context)

        assert result.graph is None


# ------------------------------------------------------------------
# 6. Empty registry returns empty result
# ------------------------------------------------------------------


class TestIRSSubsystemEmptyRegistry:
    """Verify empty checker registry returns empty result."""

    def test_empty_registry_returns_empty(self) -> None:
        runner = IRSRunner(
            registry=IRSCheckerRegistry(),
            construct_registry=SPLConstructRegistry.default(),
        )
        subsystem = IRSSubsystem(config=IRSRuntimeConfig(), runner=runner)
        context = IRSCheckContext(stage_name="test_stage")
        result = subsystem.run_stage_local("test_stage", context)

        assert result.reports == ()
        assert result.diagnostics == ()
        assert result.warnings == ()

    def test_disabled_subsystem_returns_empty(self) -> None:
        runner = IRSRunner(
            registry=IRSCheckerRegistry(),
            construct_registry=SPLConstructRegistry.default(),
        )
        config = IRSRuntimeConfig(enabled=False)
        subsystem = IRSSubsystem(config=config, runner=runner)
        context = IRSCheckContext(stage_name="test_stage")
        result = subsystem.run_stage_local("test_stage", context)

        assert result.reports == ()
        assert result.stage_name == "test_stage"

    def test_stage_local_disabled_returns_empty(self) -> None:
        registry = IRSCheckerRegistry()
        registry.register(_FakeChecker())
        runner = IRSRunner(
            registry=registry,
            construct_registry=SPLConstructRegistry.default(),
        )
        config = IRSRuntimeConfig(stage_local_enabled=False)
        subsystem = IRSSubsystem(config=config, runner=runner)
        context = IRSCheckContext(stage_name="test_stage")
        result = subsystem.run_stage_local("test_stage", context)

        assert result.reports == ()


# ------------------------------------------------------------------
# 7. IRSSubsystem.run_post_normalize uses IRSRunner
# ------------------------------------------------------------------


class TestIRSSubsystemRunPostNormalize:
    """Verify run_post_normalize enters the spec-driven IRS runner path."""

    def test_delegates_to_post_normalize_checker(
        self,
    ) -> None:
        """run_post_normalize runs the post_normalize stage with WorkerIR."""
        from nl2spl.ir.worker_ir import WorkerIR

        sentinel_diags = [_make_diagnostic("sentinel_1")]
        runner = MagicMock(spec=IRSRunner)
        runner.run_stage.return_value = IRSRunResult(diagnostics=sentinel_diags)
        config = IRSRuntimeConfig()
        subsystem = IRSSubsystem(config=config, runner=runner)

        worker = WorkerIR(worker_name="main", description="main worker")
        diags = subsystem.run_post_normalize(
            worker=worker,
            worker_plan=None,
            symbol_table=None,
            resources=None,
        )

        runner.run_stage.assert_called_once()
        stage_name, context = runner.run_stage.call_args.args
        assert stage_name == "post_normalize"
        assert context.stage_name == "post_normalize"
        assert context.normalized_ir is worker
        assert context.worker_plan is None
        assert diags == sentinel_diags

    def test_delegates_with_all_params(
        self,
    ) -> None:
        """run_post_normalize passes optional inputs through IRSCheckContext."""
        from nl2spl.ir.resource_registry_ir import ResourceRegistryIR, WorkerScopedResourceIR
        from nl2spl.ir.symbol_table import SymbolTable
        from nl2spl.ir.worker_ir import WorkerIR
        from nl2spl.ir.worker_plan_ir import WorkerPlanIR, WorkerSpecIR

        runner = MagicMock(spec=IRSRunner)
        runner.run_stage.return_value = IRSRunResult(diagnostics=[])
        subsystem = IRSSubsystem(config=IRSRuntimeConfig(), runner=runner)

        worker = WorkerIR(worker_name="main", description="main")
        plan = WorkerPlanIR(
            main_worker_id="main",
            workers=[WorkerSpecIR(
                worker_id="main", worker_name="main", kind="main",
                purpose="Main", owned_span_ids=[], input_contract=[],
                output_contract=[], depends_on=[], constraints=[],
                boundary_kind="main_worker", decision_evidence=[], reason="",
            )],
        )
        symbol_table = SymbolTable()
        resources = ResourceRegistryIR()
        worker_scoped_resources = WorkerScopedResourceIR()
        subsystem.run_post_normalize(
            worker=worker,
            worker_plan=plan,
            symbol_table=symbol_table,
            resources=resources,
            worker_scoped_resources=worker_scoped_resources,
        )

        _, context = runner.run_stage.call_args.args
        assert context.worker_plan is plan
        assert context.symbol_table is symbol_table
        assert context.resources is resources
        assert context.metadata["worker_scoped_resources"] is worker_scoped_resources

    def test_factory_post_normalize_uses_spec_driven_checker(self) -> None:
        """Default subsystem registers the v6 post-normalize checker."""
        from nl2spl.ir.worker_ir import ExceptionFlowRef, WorkerIR

        subsystem = build_irs_subsystem(IRSRuntimeConfig())
        worker = WorkerIR(
            worker_name="main",
            description="main worker",
            exception_flows=[
                ExceptionFlowRef(
                    flow_id="exc_1",
                    condition_text="Missing timeframe.",
                    spans=["s1"],
                )
            ],
        )

        diags = subsystem.run_post_normalize(worker=worker)

        assert len(diags) == 1
        diag = diags[0]
        assert diag.kind == "missing_handler"
        assert diag.target_ref == "exception_flow:exc_1"
        assert diag.missing_slot is not None
        assert diag.missing_slot.slot_name == "handler_action"

    def test_post_normalize_disabled_returns_empty(self) -> None:
        """When post_normalize_enabled=False, method returns early without
        invoking IRSRunner."""
        from nl2spl.ir.worker_ir import WorkerIR

        runner = MagicMock(spec=IRSRunner)
        config = IRSRuntimeConfig(post_normalize_enabled=False)
        subsystem = IRSSubsystem(config=config, runner=runner)

        worker = WorkerIR(worker_name="main", description="main")
        diags = subsystem.run_post_normalize(worker=worker)

        assert diags == []
        runner.run_stage.assert_not_called()

    def test_subsystem_disabled_returns_empty(self) -> None:
        """When enabled=False, method returns early without importing or
        invoking IRSRunner."""
        from nl2spl.ir.worker_ir import WorkerIR

        runner = MagicMock(spec=IRSRunner)
        config = IRSRuntimeConfig(enabled=False)
        subsystem = IRSSubsystem(config=config, runner=runner)

        worker = WorkerIR(worker_name="main", description="main")
        diags = subsystem.run_post_normalize(worker=worker)

        assert diags == []
        runner.run_stage.assert_not_called()


# ------------------------------------------------------------------
# 8. No LLM import in new modules
# ------------------------------------------------------------------


class TestNoLLMImport:
    """Verify new IRS modules do not import LLM-related modules."""

    NEW_MODULES = [
        "nl2spl.compiler.irs.policy",
        "nl2spl.compiler.irs.result_store",
        "nl2spl.compiler.irs.subsystem",
    ]

    @pytest.mark.parametrize("module_path", NEW_MODULES)
    def test_no_llm_import(self, module_path: str) -> None:
        import importlib

        mod = importlib.import_module(module_path)
        source = inspect.getsource(mod)
        for term in ["LLMClient", "call_json", "call_text", "openai", "llm.client"]:
            assert term not in source, f"{module_path} imports LLM term: {term}"


# ------------------------------------------------------------------
# 9. No orchestrator import in new modules
# ------------------------------------------------------------------


class TestNoOrchestratorImport:
    """Verify new IRS modules do not import orchestrator."""

    NEW_MODULES = [
        "nl2spl.compiler.irs.policy",
        "nl2spl.compiler.irs.result_store",
        "nl2spl.compiler.irs.subsystem",
    ]

    @pytest.mark.parametrize("module_path", NEW_MODULES)
    def test_no_orchestrator_import(self, module_path: str) -> None:
        import importlib

        mod = importlib.import_module(module_path)
        source = inspect.getsource(mod)
        for line in source.splitlines():
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'''"):
                continue
            for term in ["PipelineOrchestrator"]:
                assert term not in stripped, (
                    f"{module_path} imports orchestrator: {stripped}"
                )
            # Check for actual import statements referencing orchestrator module
            if "import" in stripped and "orchestrator" in stripped.lower():
                raise AssertionError(f"{module_path} imports orchestrator module: {stripped}")
