from __future__ import annotations

from nl2spl.ir.action_placement_ir import (
    ExecutableActionCandidate,
    ExecutableActionPlacementPlan,
)
from nl2spl.ir.block_structure_ir import BlockIR, BlockStructureIR
from nl2spl.ir.control_region_ir import ControlRegionPlan
from nl2spl.ir.flow_structure_ir import AlternativeFlow, FlowStructureIR
from nl2spl.ir.span_ir import SpanIR
from nl2spl.ir.worker_plan_ir import WorkerFlowPlanIR, WorkerPlanIR, WorkerSpecIR
from nl2spl.pipeline.control_region_plan import build_control_region_plan
from nl2spl.pipeline.stages.stage5_block_assembler.executor import (
    _apply_control_region_plan,
)


def test_cross_packet_guard_tail_binds_to_next_accepted_action() -> None:
    spans = [
        SpanIR(
            span_id="s15",
            text=(
                "Ask only the highest-value clarifying questions needed to move "
                "forward. If sources are needed and available"
            ),
            source_section_id="sec_reusable_process",
        ),
        SpanIR(
            span_id="s16",
            text=(
                "retrieve them using approved source recipes. Maintain provenance "
                "for externally sourced facts. When enough required information "
                "is available"
            ),
            source_section_id="sec_reusable_process",
        ),
        SpanIR(
            span_id="s17",
            text="produce a draft. If the user asks for revision",
            source_section_id="sec_reusable_process",
        ),
    ]
    worker_plan = WorkerPlanIR(
        main_worker_id="worker_main",
        workers=[
            WorkerSpecIR(
                worker_id="worker_main",
                worker_name="MainWorker",
                kind="main",
                purpose="Main worker.",
                owned_span_ids=["s15", "s16", "s17"],
            )
        ],
    )
    worker_flow_plan = WorkerFlowPlanIR(
        worker_flows={
            "worker_main": FlowStructureIR(main_flow_spans=["s15", "s16", "s17"])
        }
    )
    action_plan = ExecutableActionPlacementPlan(
        candidates=(
            ExecutableActionCandidate(
                candidate_id="action_s16",
                source_span_ids=("s16",),
                action_text="retrieve them using approved source recipes",
                source="construct_plan_executable_demand",
                status="accepted",
                reason="api_demand",
                command_type_hint="CALL_API",
            ),
            ExecutableActionCandidate(
                candidate_id="action_s17",
                source_span_ids=("s17",),
                action_text="produce a draft",
                source="route_executable_role",
                status="accepted",
                reason="route_behavior",
            ),
        )
    )

    plan = build_control_region_plan(
        spans,
        worker_plan,
        worker_flow_plan,
        action_plan,
    )

    by_action = {region.action_span_ids: region for region in plan.regions}
    assert by_action[("s16",)].condition_text == "sources are needed and available"
    assert by_action[("s16",)].condition_source_span_ids == ("s15",)
    assert by_action[("s17",)].condition_text == "enough required information is available"
    assert by_action[("s17",)].condition_source_span_ids == ("s16",)


def test_cross_packet_guard_tail_does_not_create_region_without_accepted_action() -> None:
    spans = [
        SpanIR(
            span_id="s1",
            text="If sources are needed and available",
            source_section_id="sec_reusable_process",
        ),
        SpanIR(
            span_id="s2",
            text="approved source recipes",
            source_section_id="sec_reusable_process",
        ),
    ]
    worker_plan = WorkerPlanIR(
        main_worker_id="worker_main",
        workers=[
            WorkerSpecIR(
                worker_id="worker_main",
                worker_name="MainWorker",
                kind="main",
                purpose="Main worker.",
                owned_span_ids=["s1", "s2"],
            )
        ],
    )
    worker_flow_plan = WorkerFlowPlanIR(
        worker_flows={"worker_main": FlowStructureIR(main_flow_spans=["s1", "s2"])}
    )

    plan = build_control_region_plan(
        spans,
        worker_plan,
        worker_flow_plan,
        ExecutableActionPlacementPlan(),
    )

    assert plan.regions == ()


def test_cross_packet_guard_tail_does_not_reuse_complete_guarded_action() -> None:
    spans = [
        SpanIR(
            span_id="s1",
            text="If sources are needed and available retrieve them.",
            source_section_id="sec_reusable_process",
            guard_text_exact="sources are needed and available",
            action_text_exact="retrieve them",
            segmentation_kind="guarded_action",
        ),
        SpanIR(
            span_id="s2",
            text="Maintain provenance for externally sourced facts.",
            source_section_id="sec_reusable_process",
            segmentation_kind="atomic_action_candidate",
        ),
    ]
    worker_plan = WorkerPlanIR(
        main_worker_id="worker_main",
        workers=[
            WorkerSpecIR(
                worker_id="worker_main",
                worker_name="MainWorker",
                kind="main",
                purpose="Main worker.",
                owned_span_ids=["s1", "s2"],
            )
        ],
    )
    worker_flow_plan = WorkerFlowPlanIR(
        worker_flows={"worker_main": FlowStructureIR(main_flow_spans=["s1", "s2"])}
    )
    action_plan = ExecutableActionPlacementPlan(
        candidates=(
            ExecutableActionCandidate(
                candidate_id="action_s1",
                source_span_ids=("s1",),
                action_text="retrieve them",
                source="stage1_action_segmentation",
                status="accepted",
                reason="guarded_action",
                command_type_hint="CALL_API",
            ),
            ExecutableActionCandidate(
                candidate_id="action_s2",
                source_span_ids=("s2",),
                action_text="Maintain provenance for externally sourced facts.",
                source="stage1_action_segmentation",
                status="accepted",
                reason="atomic_action",
            ),
        )
    )

    plan = build_control_region_plan(
        spans,
        worker_plan,
        worker_flow_plan,
        action_plan,
    )

    assert {region.action_span_ids for region in plan.regions} == {("s1",)}
    assert plan.regions[0].condition_text == "sources are needed and available"


def test_embedded_check_if_clause_is_not_a_control_region() -> None:
    span = SpanIR(
        span_id="s15",
        text="Check if the facts needed to generate the material are available",
        source_section_id="sec_reusable_process",
        guard_text_exact="the facts needed to generate the material are available",
        action_text_exact="Check",
        segmentation_kind="guarded_action",
    )
    worker_plan = WorkerPlanIR(
        main_worker_id="worker_main",
        workers=[
            WorkerSpecIR(
                worker_id="worker_main",
                worker_name="MainWorker",
                kind="main",
                purpose="Main worker.",
                owned_span_ids=["s15"],
            )
        ],
    )
    flow_plan = WorkerFlowPlanIR(
        worker_flows={"worker_main": FlowStructureIR(main_flow_spans=["s15"])}
    )
    action_plan = ExecutableActionPlacementPlan(
        candidates=(
            ExecutableActionCandidate(
                candidate_id="action_s15",
                source_span_ids=("s15",),
                action_text=span.text,
                source="stage1_action_segmentation",
                status="accepted",
                reason="source_action",
            ),
        )
    )

    plan = build_control_region_plan(
        [span],
        worker_plan,
        flow_plan,
        action_plan,
    )

    assert plan.regions == ()
    assert plan.diagnostics == ("guarded_action_not_guard_led:s15",)


def test_duplicate_resolved_span_keeps_guarded_metadata_for_cross_packet_decision() -> None:
    spans = [
        SpanIR(
            span_id="s1",
            text="If sources are needed and available retrieve them.",
            source_section_id="sec_reusable_process",
            guard_text_exact="sources are needed and available",
            action_text_exact="retrieve them",
            segmentation_kind="guarded_action",
        ),
        SpanIR(
            span_id="s2",
            text="Maintain provenance for externally sourced facts.",
            source_section_id="sec_reusable_process",
            segmentation_kind="atomic_action_candidate",
        ),
        SpanIR(
            span_id="s1",
            text="If sources are needed and available retrieve them.",
            source_section_id="sec_reusable_process",
        ),
        SpanIR(
            span_id="s2",
            text="Maintain provenance for externally sourced facts.",
            source_section_id="sec_reusable_process",
        ),
    ]
    worker_plan = WorkerPlanIR(
        main_worker_id="worker_main",
        workers=[
            WorkerSpecIR(
                worker_id="worker_main",
                worker_name="MainWorker",
                kind="main",
                purpose="Main worker.",
                owned_span_ids=["s1", "s2"],
            )
        ],
    )
    worker_flow_plan = WorkerFlowPlanIR(
        worker_flows={"worker_main": FlowStructureIR(main_flow_spans=["s1", "s2"])}
    )
    action_plan = ExecutableActionPlacementPlan(
        candidates=(
            ExecutableActionCandidate(
                candidate_id="action_s1",
                source_span_ids=("s1",),
                action_text="retrieve them",
                source="stage1_action_segmentation",
                status="accepted",
                reason="guarded_action",
            ),
            ExecutableActionCandidate(
                candidate_id="action_s2",
                source_span_ids=("s2",),
                action_text="Maintain provenance for externally sourced facts.",
                source="stage1_action_segmentation",
                status="accepted",
                reason="atomic_action",
            ),
        )
    )

    plan = build_control_region_plan(
        spans,
        worker_plan,
        worker_flow_plan,
        action_plan,
    )

    assert {region.action_span_ids for region in plan.regions} == {("s1",)}


def test_terminal_placement_guard_does_not_create_control_region() -> None:
    spans = [
        SpanIR(
            span_id="s1",
            text=(
                "At the end record a short assumptions log and set a "
                "completion status."
            ),
            source_section_id="sec_reusable_process",
            guard_text_exact="the end",
            action_text_exact=(
                "record a short assumptions log and set a completion status"
            ),
            segmentation_kind="guarded_action",
        ),
    ]
    worker_plan = WorkerPlanIR(
        main_worker_id="worker_main",
        workers=[
            WorkerSpecIR(
                worker_id="worker_main",
                worker_name="MainWorker",
                kind="main",
                purpose="Main worker.",
                owned_span_ids=["s1"],
            )
        ],
    )
    worker_flow_plan = WorkerFlowPlanIR(
        worker_flows={"worker_main": FlowStructureIR(main_flow_spans=["s1"])}
    )
    action_plan = ExecutableActionPlacementPlan(
        candidates=(
            ExecutableActionCandidate(
                candidate_id="action_s1",
                source_span_ids=("s1",),
                action_text="record a short assumptions log and set a completion status",
                source="stage1_action_segmentation",
                status="accepted",
                reason="terminal_action",
            ),
        )
    )

    plan = build_control_region_plan(
        spans,
        worker_plan,
        worker_flow_plan,
        action_plan,
    )

    assert plan.regions == ()
    assert plan.diagnostics == ("guarded_action_terminal_placement:s1",)


def test_revision_guarded_action_preserves_stage4_top_level_alternative() -> None:
    span = SpanIR(
        span_id="s21",
        text="If the user asks for revision revise while rechecking constraints.",
        source_section_id="sec_reusable_process",
        guard_text_exact="the user asks for revision",
        action_text_exact="revise while rechecking constraints",
        segmentation_kind="guarded_action",
    )
    worker_plan = WorkerPlanIR(
        main_worker_id="worker_main",
        workers=[
            WorkerSpecIR(
                worker_id="worker_main",
                worker_name="MainWorker",
                kind="main",
                purpose="Main worker.",
                owned_span_ids=["s21"],
            )
        ],
    )
    worker_flow_plan = WorkerFlowPlanIR(
        worker_flows={
            "worker_main": FlowStructureIR(
                alternative_flows=[
                    AlternativeFlow("alt_revision", "If the user asks for revision", ["s21"])
                ]
            )
        }
    )
    action_plan = ExecutableActionPlacementPlan(
        candidates=(
            ExecutableActionCandidate(
                candidate_id="action_s21",
                source_span_ids=("s21",),
                action_text="revise while rechecking constraints",
                source="stage1_action_segmentation",
                status="accepted",
                reason="guarded_action",
            ),
        )
    )

    plan = build_control_region_plan(
        [span],
        worker_plan,
        worker_flow_plan,
        action_plan,
    )

    assert len(plan.regions) == 1
    assert plan.regions[0].region_kind == "top_level_alternative"
    assert plan.regions[0].condition_text == "the user asks for revision"

    class _Stage5:
        stage5_warnings: list[str] = []

    blocks = _apply_control_region_plan(
        _Stage5(),
        BlockStructureIR(),
        plan,
        "worker_main",
    )
    block = blocks.alternative_flow_blocks[plan.regions[0].region_id][0]
    assert block.block_type == "SEQUENTIAL"
    assert block.condition_text is None


def test_anaphoric_if_not_is_resolved_from_prior_verification_action() -> None:
    spans = [
        SpanIR(
            span_id="s1",
            text=(
                "Generate a draft communication artifact and verify if it "
                "meets tone and format requirements."
            ),
            source_section_id="sec_reusable_process",
            segmentation_kind="atomic_action_candidate",
        ),
        SpanIR(
            span_id="s2",
            text="If not revise it based on the verification results.",
            source_section_id="sec_reusable_process",
            guard_text_exact="not",
            action_text_exact="revise it based on the verification results",
            segmentation_kind="guarded_action",
        ),
    ]
    worker_plan = WorkerPlanIR(
        main_worker_id="worker_main",
        workers=[
            WorkerSpecIR(
                worker_id="worker_main",
                worker_name="MainWorker",
                kind="main",
                purpose="Main worker.",
                owned_span_ids=["s1", "s2"],
            )
        ],
    )
    flow_plan = WorkerFlowPlanIR(
        worker_flows={
            "worker_main": FlowStructureIR(main_flow_spans=["s1", "s2"])
        }
    )
    action_plan = ExecutableActionPlacementPlan(
        candidates=(
            ExecutableActionCandidate(
                candidate_id="action_s1",
                source_span_ids=("s1",),
                action_text=spans[0].text,
                source="stage1_action_segmentation",
                status="accepted",
                reason="atomic_action",
            ),
            ExecutableActionCandidate(
                candidate_id="action_s2",
                source_span_ids=("s2",),
                action_text="revise it based on the verification results",
                source="stage1_action_segmentation",
                status="accepted",
                reason="guarded_action",
            ),
        )
    )

    plan = build_control_region_plan(
        spans,
        worker_plan,
        flow_plan,
        action_plan,
    )

    revision = next(
        region for region in plan.regions if region.action_span_ids == ("s2",)
    )
    assert revision.condition_text == (
        "draft communication artifact does not meet tone and format requirements"
    )
    assert revision.condition_source_span_ids == ("s1", "s2")


def test_unresolved_anaphoric_if_not_does_not_materialize_if_region() -> None:
    span = SpanIR(
        span_id="s1",
        text="If not revise it.",
        source_section_id="sec_reusable_process",
        guard_text_exact="not",
        action_text_exact="revise it",
        segmentation_kind="guarded_action",
    )
    worker_plan = WorkerPlanIR(
        main_worker_id="worker_main",
        workers=[
            WorkerSpecIR(
                worker_id="worker_main",
                worker_name="MainWorker",
                kind="main",
                purpose="Main worker.",
                owned_span_ids=["s1"],
            )
        ],
    )
    flow_plan = WorkerFlowPlanIR(
        worker_flows={"worker_main": FlowStructureIR(main_flow_spans=["s1"])}
    )
    action_plan = ExecutableActionPlacementPlan(
        candidates=(
            ExecutableActionCandidate(
                candidate_id="action_s1",
                source_span_ids=("s1",),
                action_text="revise it",
                source="stage1_action_segmentation",
                status="accepted",
                reason="guarded_action",
            ),
        )
    )

    plan = build_control_region_plan(
        [span],
        worker_plan,
        flow_plan,
        action_plan,
    )

    assert plan.regions == ()
    assert "guarded_action_incomplete_guard:s1:not" in plan.diagnostics


def test_stage5_demotes_unplanned_legacy_if_block() -> None:
    class _Stage5:
        stage5_warnings: list[str] = []

    result = _apply_control_region_plan(
        _Stage5(),
        BlockStructureIR(
            main_flow_blocks=[
                BlockIR(
                    block_id="b_bad",
                    block_type="IF",
                    condition_text="not",
                    spans=["s1"],
                )
            ]
        ),
        ControlRegionPlan(),
        "worker_main",
    )

    assert result.main_flow_blocks[0].block_type == "SEQUENTIAL"
    assert result.main_flow_blocks[0].condition_text is None
