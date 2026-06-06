"""R13: Construct satisfaction feedback projection tests."""

from __future__ import annotations

from copy import deepcopy

from nl2spl.compiler.construct_registry import (
    ConstructSatisfactionReport,
    SlotSatisfaction,
)
from nl2spl.compiler.irs.feedback_projector import (
    ConstructSatisfactionFeedbackProjector,
)
from nl2spl.compiler.report_renderer import render_report


def _candidate_report() -> ConstructSatisfactionReport:
    return ConstructSatisfactionReport(
        construct_id="worker_candidate:c1",
        construct_type="WORKER_CANDIDATE",
        slots=[
            SlotSatisfaction("responsibility", "satisfied", ["s1"]),
            SlotSatisfaction("delegation_signal", "satisfied", ["s1"]),
        ],
        completeness="complete",
        renderable=False,
        source_span_ids=["s1"],
        construct_path=("worker_plan", "candidates", "c1"),
    )


def _promotion_report() -> ConstructSatisfactionReport:
    return ConstructSatisfactionReport(
        construct_id="worker_promotion:c1",
        construct_type="WORKER_PROMOTION",
        slots=[
            SlotSatisfaction(
                "promotion_input_contract",
                "missing",
                ["s1"],
                explanation="No source-backed input contract.",
            ),
            SlotSatisfaction(
                "promotion_output_contract",
                "missing",
                ["s1"],
                explanation="No source-backed output contract.",
            ),
            SlotSatisfaction(
                "promotion_invocation_point",
                "missing",
                ["s1"],
                explanation="No invocation site.",
            ),
            SlotSatisfaction(
                "promotion_result_handoff",
                "missing",
                ["s1"],
                explanation="No result handoff.",
            ),
        ],
        completeness="blocked",
        renderable=False,
        source_span_ids=["s1"],
        frontier_status="cutline_blocked",
        cutline_reason="missing_promotion_contract",
        construct_path=("worker_plan", "promotions", "c1"),
    )


def test_feedback_projector_renders_construct_satisfaction_section() -> None:
    lines = ConstructSatisfactionFeedbackProjector().project(
        {"stage3_5": [_candidate_report()]}
    )
    text = "\n".join(lines)

    assert "Construct Satisfaction" in text
    assert "Stage: stage3_5" in text
    assert "WORKER_CANDIDATE worker_candidate:c1: complete" in text
    assert "source spans: s1" in text


def test_worker_promotion_blocked_lists_four_missing_slots() -> None:
    text = "\n".join(
        ConstructSatisfactionFeedbackProjector().project(
            {"stage3_5": [_promotion_report()]}
        )
    )

    assert "WORKER_PROMOTION worker_promotion:c1: blocked" in text
    assert "promotion_input_contract: missing" in text
    assert "promotion_output_contract: missing" in text
    assert "promotion_invocation_point: missing" in text
    assert "promotion_result_handoff: missing" in text


def test_candidate_complete_and_promotion_blocked_are_separate() -> None:
    text = render_report(
        spl_text="SPL",
        construct_satisfaction={
            "stage3_5": [_candidate_report(), _promotion_report()],
        },
    )

    assert "WORKER_CANDIDATE worker_candidate:c1: complete" in text
    assert "WORKER_PROMOTION worker_promotion:c1: blocked" in text
    assert "candidate complete != child worker ready" not in text


def test_no_construct_satisfaction_section_when_no_reports() -> None:
    text = render_report(spl_text="SPL", construct_satisfaction={})

    assert "Construct Satisfaction" not in text


def test_feedback_projector_does_not_mutate_reports() -> None:
    report = _promotion_report()
    before = deepcopy(report)

    ConstructSatisfactionFeedbackProjector().project({"stage3_5": [report]})

    assert report == before
