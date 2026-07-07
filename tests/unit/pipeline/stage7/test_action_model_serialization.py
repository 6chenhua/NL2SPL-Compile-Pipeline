from __future__ import annotations

from nl2spl.ir.diagnostics import CompileDiagnostic
from nl2spl.pipeline.stages.stage7_step_extractor.action_model import (
    ActionCoverageReportIR,
    ExecutableActionIR,
    SourceRangeIR,
    WorkerActionPlanIR,
    canonicalize_action_text,
)


def test_action_model_roundtrip_serialization() -> None:
    # 1. Setup SourceRangeIR
    r1 = SourceRangeIR(
        source_span_id="s16",
        char_start=44,
        char_end=87,
        relation="direct",
    )
    assert r1.to_dict() == {
        "source_span_id": "s16",
        "char_start": 44,
        "char_end": 87,
        "relation": "direct",
    }
    assert SourceRangeIR.from_dict(r1.to_dict()) == r1

    # 2. Setup ExecutableActionIR
    norm_key = canonicalize_action_text("retrieve them using approved source recipes")
    a1 = ExecutableActionIR(
        action_id="act_s16_1",
        action_kind="source_slice",
        source_span_ids=("s16",),
        covered_ranges=(r1,),
        action_text="retrieve them using approved source recipes",
        normalized_action_key=norm_key,
        command_type="CALL_API",
        owning_authority="api_call_materializer",
        placement_status="unplaced",
        output_policy="no_output",
        coverage_status="exact",
    )
    a1_dict = a1.to_dict()
    assert a1_dict["action_id"] == "act_s16_1"
    assert a1_dict["output_policy"] == "no_output"
    assert a1_dict["placement_status"] == "unplaced"
    assert a1_dict["flow_ref"] is None
    assert a1_dict["block_ref"] is None
    assert ExecutableActionIR.from_dict(a1_dict) == a1

    # 3. Setup ActionCoverageReportIR with CompileDiagnostic
    diag = CompileDiagnostic(
        diagnostic_id="diag_1",
        kind="stage7_api_residual_coverage_ambiguous",
        severity="warning",
        message="Ambiguous coverage",
        target_ref="api_call_demand:api_call_s16",
        source_span_ids=["s16"],
        metadata={"reason": "offsets_missing"},
        blocks_rendering=False,
        blocks_completion=True,
    )
    report = ActionCoverageReportIR(
        report_id="rep_s16",
        source_span_id="s16",
        covered_ranges=(r1,),
        uncovered_ranges=(),
        overlapping_ranges=(),
        action_ids=("act_s16_1",),
        status="fully_partitioned",
        diagnostics=(diag,),
    )
    report_dict = report.to_dict()
    assert report_dict["status"] == "fully_partitioned"
    assert len(report_dict["diagnostics"]) == 1
    # Check that diagnostic field is structured and not a weak string
    assert report_dict["diagnostics"][0]["diagnostic_id"] == "diag_1"
    assert ActionCoverageReportIR.from_dict(report_dict) == report

    # 4. Setup WorkerActionPlanIR
    plan = WorkerActionPlanIR(
        main_worker_id="worker_main",
        worker_actions={"worker_main": (a1,)},
        coverage_reports=(report,),
        diagnostics=(diag,),
    )
    plan_dict = plan.to_dict()
    assert plan_dict["main_worker_id"] == "worker_main"
    assert len(plan_dict["worker_actions"]["worker_main"]) == 1
    assert WorkerActionPlanIR.from_dict(plan_dict) == plan


def test_normalized_action_key_canonicalization() -> None:
    cases = [
        ("Retrieve sources using approved recipes.", "retrieve sources using approved recipes"),
        ("  Maintain provenance;  ", "maintain provenance"),
        ("Retrieve approved sources using SearchAPI!", "retrieve approved sources using searchapi"),
        ("Normal key without Lemmatization", "normal key without lemmatization"),
        ("No stopword removal and normal", "no stopword removal and normal"),
    ]
    for orig, expected in cases:
        assert canonicalize_action_text(orig) == expected


def test_ambiguous_action_unplaced() -> None:
    action = ExecutableActionIR(
        action_id="act_ambig",
        action_kind="residual_slice",
        source_span_ids=("s1",),
        action_text="ambiguous action text",
        normalized_action_key=canonicalize_action_text("ambiguous action text"),
        command_type="GENERAL_COMMAND",
        owning_authority="general_command_materializer",
        placement_status="ambiguous",  # no fabricated placement
        flow_ref=None,
        block_ref=None,
        coverage_status="ambiguous",
    )
    a_dict = action.to_dict()
    assert a_dict["placement_status"] == "ambiguous"
    assert a_dict["flow_ref"] is None
    assert a_dict["block_ref"] is None


def test_no_output_action_no_output_hints() -> None:
    action = ExecutableActionIR(
        action_id="act_no_out",
        action_kind="residual_slice",
        source_span_ids=("s16",),
        action_text="Maintain provenance",
        normalized_action_key=canonicalize_action_text("Maintain provenance"),
        command_type="GENERAL_COMMAND",
        owning_authority="general_command_materializer",
        placement_status="placed",
        flow_ref="main",
        block_ref="block_main",
        output_policy="no_output",
        output_hints=(),  # no output variables fabricated
        coverage_status="residual",
    )
    a_dict = action.to_dict()
    assert a_dict["output_policy"] == "no_output"
    assert len(a_dict["output_hints"]) == 0
