"""Unit tests for Phase 5 diagnostic consolidation."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from nl2spl.compiler.compile_result import MissingSlot
from nl2spl.config import LLMConfig, PipelineConfig
from nl2spl.ir.diagnostics import CompileDiagnostic
from nl2spl.ir.flow_structure_ir import FlowStructureIR
from nl2spl.ir.resource_registry_ir import (
    ResourceRegistryIR,
    WorkerScopedResourceIR,
)
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.pipeline.orchestrator import PipelineOrchestrator, _dedup_key

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _diag(
    diagnostic_id: str = "d1",
    kind: str = "missing_handler",
    target_ref: str = "exception_flow:exc_1",
    source_span_ids: list[str] | None = None,
    message: str = "Test diagnostic",
    blocks_completion: bool = True,
    blocks_rendering: bool = False,
) -> CompileDiagnostic:
    return CompileDiagnostic(
        diagnostic_id=diagnostic_id,
        kind=kind,
        severity="warning",
        message=message,
        target_ref=target_ref,
        source_span_ids=source_span_ids or [],
        blocks_completion=blocks_completion,
        blocks_rendering=blocks_rendering,
    )


def _make_orchestrator(
    tmp_path: Path,
    consolidation_enabled: bool = True,
    stage4_check: bool = True,
    stage7_check: bool = True,
) -> PipelineOrchestrator:
    return PipelineOrchestrator(
        PipelineConfig(
            llm=LLMConfig(api_key="test-key"),
            output_dir=tmp_path / "output",
            save_intermediate=False,
            enable_worker_boundary_planner=True,
            enable_irs_stage4_exception_flow_check=stage4_check,
            enable_irs_stage7_step_check=stage7_check,
            enable_irs_diagnostic_consolidation=consolidation_enabled,
            enable_irs_post_normalize_check=False,
        )
    )


# ---------------------------------------------------------------------------
# _dedup_key
# ---------------------------------------------------------------------------


class TestDedupKey:
    def test_same_kind_target_spans_produce_same_key(self):
        a = _diag(
            kind="missing_handler", target_ref="exception_flow:exc_1", source_span_ids=["s1", "s2"]
        )
        b = _diag(
            kind="missing_handler", target_ref="exception_flow:exc_1", source_span_ids=["s2", "s1"]
        )
        assert _dedup_key(a) == _dedup_key(b)

    def test_different_kind_produces_different_key(self):
        a = _diag(kind="missing_handler", target_ref="exception_flow:exc_1")
        b = _diag(kind="type_or_contract_ambiguity", target_ref="exception_flow:exc_1")
        assert _dedup_key(a) != _dedup_key(b)

    def test_different_target_produces_different_key(self):
        a = _diag(kind="missing_handler", target_ref="exception_flow:exc_1")
        b = _diag(kind="missing_handler", target_ref="exception_flow:exc_2")
        assert _dedup_key(a) != _dedup_key(b)

    def test_different_spans_produces_different_key(self):
        a = _diag(kind="missing_handler", target_ref="exception_flow:exc_1", source_span_ids=["s1"])
        b = _diag(kind="missing_handler", target_ref="exception_flow:exc_1", source_span_ids=["s2"])
        assert _dedup_key(a) != _dedup_key(b)

    def test_empty_spans_treated_same(self):
        a = _diag(kind="missing_handler", target_ref="exception_flow:exc_1", source_span_ids=[])
        b = _diag(kind="missing_handler", target_ref="exception_flow:exc_1", source_span_ids=[])
        assert _dedup_key(a) == _dedup_key(b)

    def test_none_target_ref_handled(self):
        a = _diag(kind="type_or_contract_ambiguity", target_ref=None)
        b = _diag(kind="type_or_contract_ambiguity", target_ref=None)
        assert _dedup_key(a) == _dedup_key(b)

    def test_same_missing_slot_name_dedup(self):
        slot_a = MissingSlot(slot_name="handler_action", required_for="complete", reason=".")
        slot_b = MissingSlot(slot_name="handler_action", required_for="complete", reason="other")
        a = _diag(kind="missing_handler", target_ref="exception_flow:exc_1", source_span_ids=["s1"])
        b = _diag(kind="missing_handler", target_ref="exception_flow:exc_1", source_span_ids=["s1"])
        a.missing_slot = slot_a
        b.missing_slot = slot_b
        assert _dedup_key(a) == _dedup_key(b)

    def test_different_missing_slot_name_both_kept(self):
        slot_a = MissingSlot(slot_name="handler_action", required_for="complete", reason=".")
        slot_b = MissingSlot(slot_name="call_action", required_for="complete", reason=".")
        a = _diag(kind="type_or_contract_ambiguity", target_ref="step:st_1", source_span_ids=["s1"])
        b = _diag(kind="type_or_contract_ambiguity", target_ref="step:st_1", source_span_ids=["s1"])
        a.missing_slot = slot_a
        b.missing_slot = slot_b
        assert _dedup_key(a) != _dedup_key(b)

    def test_one_with_slot_one_without_both_kept(self):
        slot = MissingSlot(slot_name="handler_action", required_for="complete", reason=".")
        a = _diag(kind="missing_handler", target_ref="exception_flow:exc_1", source_span_ids=["s1"])
        b = _diag(kind="missing_handler", target_ref="exception_flow:exc_1", source_span_ids=["s1"])
        a.missing_slot = slot
        # b has no missing_slot
        assert _dedup_key(a) != _dedup_key(b)

    def test_both_without_missing_slot_still_dedup(self):
        a = _diag(
            kind="missing_handler", target_ref="exception_flow:exc_1", source_span_ids=["s1", "s2"]
        )
        b = _diag(
            kind="missing_handler", target_ref="exception_flow:exc_1", source_span_ids=["s2", "s1"]
        )
        assert _dedup_key(a) == _dedup_key(b)

    def test_none_missing_slot_same_as_unset(self):
        a = _diag(kind="missing_handler", target_ref="exception_flow:exc_1")
        b = _diag(kind="missing_handler", target_ref="exception_flow:exc_1")
        a.missing_slot = None
        # b has no missing_slot set (defaults to None)
        assert _dedup_key(a) == _dedup_key(b)


# ---------------------------------------------------------------------------
# Consolidation — calls real orchestrator method
# ---------------------------------------------------------------------------


class TestConsolidationReal:
    def test_stage4_and_stage7_both_merged(self, tmp_path: Path):
        orch = _make_orchestrator(tmp_path)
        existing = [_diag("d1", kind="missing_handler", target_ref="exception_flow:exc_1")]
        intermediate = {
            "stage_local_diagnostics": {
                "stage4": [
                    _diag(
                        "d_s4", kind="type_or_contract_ambiguity", target_ref="exception_flow:exc_2"
                    ),
                ],
                "stage7": [
                    _diag("d_s7", kind="assumed_command_not_renderable", target_ref="step:st_1"),
                ],
            }
        }
        result = orch._consolidate_compile_diagnostics(existing, intermediate)
        kinds = {d.kind for d in result}
        assert len(result) == 3
        assert kinds == {
            "missing_handler",
            "type_or_contract_ambiguity",
            "assumed_command_not_renderable",
        }

    def test_duplicate_skipped_existing_kept(self, tmp_path: Path):
        orch = _make_orchestrator(tmp_path)
        existing = [
            _diag(
                "d1",
                kind="missing_handler",
                target_ref="exception_flow:exc_1",
                source_span_ids=["s1"],
            )
        ]
        intermediate = {
            "stage_local_diagnostics": {
                "stage4": [
                    _diag(
                        "d_s4",
                        kind="missing_handler",
                        target_ref="exception_flow:exc_1",
                        source_span_ids=["s1"],
                    )
                ],
            }
        }
        result = orch._consolidate_compile_diagnostics(existing, intermediate)
        assert len(result) == 1
        assert result[0].diagnostic_id == "d1"

    def test_different_missing_slots_both_kept_in_consolidation(self, tmp_path: Path):
        orch = _make_orchestrator(tmp_path)
        existing_diag = _diag(
            "d1",
            kind="type_or_contract_ambiguity",
            target_ref="step:st_1",
            source_span_ids=["s1"],
        )
        existing_diag.missing_slot = MissingSlot(
            slot_name="api_name",
            required_for="complete",
            reason="Missing API name.",
        )
        stage_diag = _diag(
            "d_s7",
            kind="type_or_contract_ambiguity",
            target_ref="step:st_1",
            source_span_ids=["s1"],
        )
        stage_diag.missing_slot = MissingSlot(
            slot_name="call_action",
            required_for="complete",
            reason="Missing executable call action.",
        )
        intermediate = {
            "stage_local_diagnostics": {
                "stage7": [stage_diag],
            }
        }

        result = orch._consolidate_compile_diagnostics([existing_diag], intermediate)

        assert [diag.diagnostic_id for diag in result] == ["d1", "d_s7"]

    def test_different_targets_both_kept(self, tmp_path: Path):
        orch = _make_orchestrator(tmp_path)
        existing = [_diag("d1", kind="missing_handler", target_ref="exception_flow:exc_1")]
        intermediate = {
            "stage_local_diagnostics": {
                "stage4": [
                    _diag("d_s4", kind="missing_handler", target_ref="exception_flow:exc_2")
                ],
            }
        }
        result = orch._consolidate_compile_diagnostics(existing, intermediate)
        assert len(result) == 2

    def test_empty_side_channel_returns_existing(self, tmp_path: Path):
        orch = _make_orchestrator(tmp_path)
        existing = [_diag("d1")]
        result = orch._consolidate_compile_diagnostics(existing, {})
        assert result == existing
        assert result is not existing  # returns a copy

    def test_empty_stage_local_diagnostics_returns_existing(self, tmp_path: Path):
        orch = _make_orchestrator(tmp_path)
        existing = [_diag("d1")]
        intermediate = {"stage_local_diagnostics": {}}
        result = orch._consolidate_compile_diagnostics(existing, intermediate)
        assert len(result) == 1

    def test_non_list_stage_entry_skipped(self, tmp_path: Path):
        orch = _make_orchestrator(tmp_path)
        existing = [_diag("d1")]
        intermediate = {
            "stage_local_diagnostics": {
                "stage4": "not_a_list",
                "stage7": [
                    _diag("d_s7", kind="assumed_command_not_renderable", target_ref="step:st_1")
                ],
            }
        }
        result = orch._consolidate_compile_diagnostics(existing, intermediate)
        # Only stage7 (which is a list) is merged; stage4 is skipped.
        assert len(result) == 2

    def test_existing_order_preserved(self, tmp_path: Path):
        orch = _make_orchestrator(tmp_path)
        existing = [
            _diag("d1", "missing_handler", "exception_flow:exc_1"),
            _diag("d2", "missing_output_producer", "variable:out1"),
        ]
        intermediate = {
            "stage_local_diagnostics": {
                "stage7": [_diag("d_s7", "type_or_contract_ambiguity", "step:st_1")],
            }
        }
        result = orch._consolidate_compile_diagnostics(existing, intermediate)
        assert [d.diagnostic_id for d in result[:2]] == ["d1", "d2"]

    def test_multiple_stage_local_no_duplicates_all_merge(self, tmp_path: Path):
        orch = _make_orchestrator(tmp_path)
        existing = [_diag("d1", kind="missing_handler", target_ref="exception_flow:exc_1")]
        intermediate = {
            "stage_local_diagnostics": {
                "stage4": [_diag("d2", kind="type_or_contract_ambiguity", target_ref="step:st_1")],
                "stage7": [
                    _diag("d3", kind="assumed_command_not_renderable", target_ref="step:st_2")
                ],
            }
        }
        result = orch._consolidate_compile_diagnostics(existing, intermediate)
        assert len(result) == 3


# ---------------------------------------------------------------------------
# Flag on/off: end-to-end consolidation chain
# ---------------------------------------------------------------------------


class TestConsolidationE2E:
    def _config(self, tmp_path: Path, flag: bool) -> PipelineConfig:
        return PipelineConfig(
            llm=LLMConfig(api_key="test-key"),
            output_dir=tmp_path / "output",
            save_intermediate=False,
            enable_worker_boundary_planner=True,
            enable_irs_stage4_exception_flow_check=True,
            enable_irs_stage7_step_check=True,
            enable_irs_diagnostic_consolidation=flag,
            enable_irs_post_normalize_check=False,
        )

    def _run(self, tmp_path: Path, flag: bool, flow_plan, step_plan):
        """Run full pipeline with given IRS-triggering IRs."""
        from nl2spl.ir.block_structure_ir import BlockIR, BlockStructureIR
        from nl2spl.ir.field_route_ir import FieldRouteIR
        from nl2spl.ir.span_ir import SpanIR
        from nl2spl.ir.worker_plan_ir import (
            WorkerBlockPlanIR,
            WorkerPlanIR,
            WorkerSpecIR,
        )

        config = self._config(tmp_path, flag)
        orch = PipelineOrchestrator(config)
        spans = [SpanIR("s1", "Process request.")]
        routes = FieldRouteIR(behavior=["s1"])
        plan = WorkerPlanIR(
            main_worker_id="worker_main",
            workers=[
                WorkerSpecIR(
                    "worker_main",
                    "Main",
                    "main",
                    "Main worker",
                    ["s1"],
                    [],
                    [],
                    [],
                    [],
                    "main_worker",
                    [],
                    "",
                ),
            ],
            candidates=[],
            decisions=[],
            handoffs=[],
        )
        block_plan = WorkerBlockPlanIR(
            worker_blocks={
                "worker_main": BlockStructureIR(
                    main_flow_blocks=[BlockIR("b1", "SEQUENTIAL", None, ["s1"])]
                )
            }
        )
        symbols = SymbolTable()
        ws_resources = WorkerScopedResourceIR(global_resources=ResourceRegistryIR())
        worker_mock = MagicMock()
        worker_mock.steps = []
        worker_mock.child_workers = []
        worker_mock.scoped_steps = False

        with (
            patch.object(orch, "_run_stage1", return_value=spans),
            patch.object(orch, "_run_stage2", return_value=(routes, [])),
            patch.object(orch, "_run_stage3", return_value=(spans, routes)),
            patch.object(orch, "_run_stage3_5", return_value=plan),
            patch.object(orch, "_run_stage4", return_value=flow_plan),
            patch.object(orch, "_run_stage5", return_value=block_plan),
            patch.object(
                orch, "_run_stage6_worker_scoped", return_value=(ws_resources, symbols, [])
            ),
            patch.object(orch, "_run_stage7_worker_scoped", return_value=(step_plan, symbols, [])),
            patch.object(orch, "_run_stage8", return_value=MagicMock()),
            patch.object(orch, "_run_stage9", return_value=[]),
            patch.object(
                orch,
                "_run_normalization_worker_scoped",
                return_value=(flow_plan, block_plan, step_plan, symbols, [], []),
            ),
            patch.object(orch, "_run_stage10_worker_scoped", return_value=worker_mock),
            patch.object(orch, "_run_stage11", return_value=("SPL", [], [])),
        ):
            return orch.run("test")

    def test_flag_off_no_stage_local_in_compile_diagnostics(self, tmp_path: Path):
        from nl2spl.ir.flow_structure_ir import ExceptionFlow
        from nl2spl.ir.worker_plan_ir import WorkerFlowPlanIR, WorkerStepPlanIR

        flow_plan = WorkerFlowPlanIR(
            worker_flows={
                "worker_main": FlowStructureIR(
                    main_flow_spans=["s1"],
                    exception_flows=[ExceptionFlow("exc_1", "Vague", [])],
                ),
            }
        )
        step_plan = WorkerStepPlanIR(main_worker_id="worker_main", worker_steps={"worker_main": []})
        result = self._run(tmp_path, flag=False, flow_plan=flow_plan, step_plan=step_plan)
        kinds = {d.kind for d in result.compile_diagnostics}
        assert "type_or_contract_ambiguity" not in kinds

    def test_flag_on_stage4_diagnostic_enters_compile_diagnostics(self, tmp_path: Path):
        from nl2spl.ir.flow_structure_ir import ExceptionFlow
        from nl2spl.ir.worker_plan_ir import WorkerFlowPlanIR, WorkerStepPlanIR

        flow_plan = WorkerFlowPlanIR(
            worker_flows={
                "worker_main": FlowStructureIR(
                    main_flow_spans=["s1"],
                    exception_flows=[ExceptionFlow("exc_1", "Vague", [])],  # spans=[] -> assumed
                ),
            }
        )
        step_plan = WorkerStepPlanIR(main_worker_id="worker_main", worker_steps={"worker_main": []})
        result = self._run(tmp_path, flag=True, flow_plan=flow_plan, step_plan=step_plan)
        kinds = {d.kind for d in result.compile_diagnostics}
        assert "type_or_contract_ambiguity" in kinds

    def test_flag_on_stage7_diagnostic_enters_compile_diagnostics(self, tmp_path: Path):
        from nl2spl.ir.step_ir import StepIR
        from nl2spl.ir.worker_plan_ir import WorkerFlowPlanIR, WorkerStepPlanIR

        flow_plan = WorkerFlowPlanIR(
            worker_flows={
                "worker_main": FlowStructureIR(main_flow_spans=["s1"]),
            }
        )
        # Step with empty source_span_ids triggers assumed_command_not_renderable
        step_plan = WorkerStepPlanIR(
            main_worker_id="worker_main",
            worker_steps={
                "worker_main": [
                    StepIR("st_1", "Do", [], "GENERAL_COMMAND", [], [], None, "main", "b_1", None)
                ],
            },
        )
        result = self._run(tmp_path, flag=True, flow_plan=flow_plan, step_plan=step_plan)
        kinds = {d.kind for d in result.compile_diagnostics}
        assert "assumed_command_not_renderable" in kinds

    def test_flag_on_blocks_completion_diagnostic_makes_partial(self, tmp_path: Path):
        from nl2spl.ir.flow_structure_ir import ExceptionFlow
        from nl2spl.ir.step_ir import StepIR
        from nl2spl.ir.worker_plan_ir import WorkerFlowPlanIR, WorkerStepPlanIR

        flow_plan = WorkerFlowPlanIR(
            worker_flows={
                "worker_main": FlowStructureIR(
                    main_flow_spans=["s1"],
                    exception_flows=[ExceptionFlow("exc_1", "Vague", [])],
                ),
            }
        )
        step_plan = WorkerStepPlanIR(
            main_worker_id="worker_main",
            worker_steps={
                "worker_main": [
                    StepIR("st_1", "Do", [], "GENERAL_COMMAND", [], [], None, "main", "b_1", None)
                ],
            },
        )
        result = self._run(tmp_path, flag=True, flow_plan=flow_plan, step_plan=step_plan)
        # Both stage4 TOCA and stage7 ACNR block completion -> partial
        assert result.completeness == "partial"

    def test_flag_on_report_contains_diagnostics_section(self, tmp_path: Path):
        from nl2spl.ir.flow_structure_ir import ExceptionFlow
        from nl2spl.ir.worker_plan_ir import WorkerFlowPlanIR, WorkerStepPlanIR

        flow_plan = WorkerFlowPlanIR(
            worker_flows={
                "worker_main": FlowStructureIR(
                    main_flow_spans=["s1"],
                    exception_flows=[ExceptionFlow("exc_1", "Vague", [])],
                ),
            }
        )
        step_plan = WorkerStepPlanIR(main_worker_id="worker_main", worker_steps={"worker_main": []})
        result = self._run(tmp_path, flag=True, flow_plan=flow_plan, step_plan=step_plan)
        assert "Diagnostics" in result.readable_report
        assert "type_or_contract_ambiguity" in result.readable_report


# ===========================================================================
# D7: Route-derived missing-handler exactly-once
# ===========================================================================


def test_d7_route_derived_missing_handler_exactly_once(tmp_path: Path) -> None:
    """D7: duplicate exc_adapter_00 missing_handler consolidated to one."""
    orch = _make_orchestrator(tmp_path)
    existing = [
        _diag(
            "diag_001", "missing_handler",
            target_ref="exception_flow:exc_adapter_00",
            source_span_ids=["s_fail"],
            message="Exception flow 'exc_adapter_00': Missing timeframe. has no handler.",
        ),
    ]
    intermediate = {
        "stage_local_diagnostics": {
            "final_check": [
                _diag(
                    "diag_002", "missing_handler",
                    target_ref="exception_flow:exc_adapter_00",
                    source_span_ids=["s_fail"],
                    message="Exception flow 'exc_adapter_00': Missing timeframe. has no handler (duplicate).",
                ),
            ],
        },
    }
    result = orch._consolidate_compile_diagnostics(existing, intermediate)
    assert len(result) == 1, f"Expected 1, got {len(result)}: {[(d.diagnostic_id, d.target_ref) for d in result]}"
    assert result[0].diagnostic_id == "diag_001"
    assert result[0].kind == "missing_handler"
    assert result[0].target_ref == "exception_flow:exc_adapter_00"
    assert result[0].source_span_ids == ["s_fail"]


# ===========================================================================
# R7.4: Consolidation behavior tests
# ===========================================================================


class TestR7ConsolidationBehavior:
    """R7.4: Lock consolidation behavior for gate + post-normalize overlap."""

    def test_post_normalize_on_stage_local_not_merged(
        self,
        tmp_path: Path,
    ) -> None:
        """post-normalize ON → stage-local diags NOT merged into compile_diagnostics.

        When enable_irs_post_normalize_check=True, consolidation is skipped.
        Stage4/7 stage-local diagnostics must not leak into the final result.
        """
        orch = _make_orchestrator(
            tmp_path,
            consolidation_enabled=False,
        )
        # Simulate post-normalize diags as "existing"
        existing = [
            _diag("pn_1", "type_or_contract_ambiguity",
                  target_ref="step:st1", source_span_ids=["s1"]),
        ]
        # Stage-local diags from stage4 IRS
        intermediate = {
            "stage_local_diagnostics": {
                "stage4": [
                    _diag("s4_1", "type_or_contract_ambiguity",
                          target_ref="step:st1", source_span_ids=["s1"]),
                ],
            },
        }
        # With consolidation OFF (post-normalize ON), stage-local not merged
        result = orch._consolidate_compile_diagnostics(existing, intermediate)
        # Only the existing (post-normalize) diag should remain
        assert len(result) == 1
        assert result[0].diagnostic_id == "pn_1"

    def test_gate_and_post_norm_missing_handler_same_dedup_key(
        self,
    ) -> None:
        """Gate missing_handler and post-normalize missing_handler produce same dedup key.

        When both produce diagnostics for the same exception flow,
        _dedup_key should be identical, enabling dedup if consolidation runs.
        """
        gate_diag = _diag(
            "gate_1", "missing_handler",
            target_ref="exception_flow:exc_1",
            source_span_ids=["s1"],
        )
        post_norm_diag = _diag(
            "pn_1", "missing_handler",
            target_ref="exception_flow:exc_1",
            source_span_ids=["s1"],
        )
        key_gate = _dedup_key(gate_diag)
        key_pn = _dedup_key(post_norm_diag)
        assert key_gate == key_pn

    def test_different_exception_flows_not_deduped(
        self,
        tmp_path: Path,
    ) -> None:
        """Different exception flows produce different dedup keys."""
        orch = _make_orchestrator(tmp_path)
        existing = [
            _diag("d1", "missing_handler",
                  target_ref="exception_flow:exc_1",
                  source_span_ids=["s1"]),
        ]
        intermediate = {
            "stage_local_diagnostics": {
                "final_check": [
                    _diag("d2", "missing_handler",
                          target_ref="exception_flow:exc_2",
                          source_span_ids=["s1"]),
                ],
            },
        }
        result = orch._consolidate_compile_diagnostics(existing, intermediate)
        mh = [d for d in result if d.kind == "missing_handler"]
        assert len(mh) == 2

    def test_consolidation_merges_stage_local_when_post_normalize_off(
        self,
        tmp_path: Path,
    ) -> None:
        """post-normalize OFF + consolidation ON → stage-local diags merged."""
        orch = _make_orchestrator(tmp_path, consolidation_enabled=True)
        existing = [
            _diag("existing_1", "missing_handler",
                  target_ref="exception_flow:exc_1",
                  source_span_ids=["s1"]),
        ]
        intermediate = {
            "stage_local_diagnostics": {
                "stage4": [
                    _diag("s4_1", "type_or_contract_ambiguity",
                          target_ref="step:st1",
                          source_span_ids=["s2"]),
                ],
            },
        }
        result = orch._consolidate_compile_diagnostics(existing, intermediate)
        # Both should be present (different kind/target)
        assert len(result) == 2
        kinds = {d.kind for d in result}
        assert "missing_handler" in kinds
        assert "type_or_contract_ambiguity" in kinds
