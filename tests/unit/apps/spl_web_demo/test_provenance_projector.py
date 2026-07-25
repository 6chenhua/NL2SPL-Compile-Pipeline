from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
BACKEND_ROOT = REPO_ROOT / "apps" / "spl-web-demo" / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from spl_web_demo.card_projector import CardProjector  # noqa: E402
from spl_web_demo.provenance_projector import ProvenanceProjector  # noqa: E402

from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot  # noqa: E402
from nl2spl.ir.agent_profile_ir import AgentProfileIR, PersonaIR  # noqa: E402
from nl2spl.ir.block_structure_ir import BlockIR  # noqa: E402
from nl2spl.ir.constraint_ir import ConstraintIR  # noqa: E402
from nl2spl.ir.diagnostics import TraceRecord  # noqa: E402
from nl2spl.ir.span_ir import SpanIR  # noqa: E402
from nl2spl.ir.step_ir import StepIR  # noqa: E402
from nl2spl.ir.worker_ir import ExceptionFlowRef, FlowRef, WorkerIR, WorkerOutput  # noqa: E402


def _snapshot(*, duplicate_span: bool = False) -> ArtifactSnapshot:
    spans = [
        SpanIR(
            span_id="s1",
            text="Collect the approved source material.",
            source_section_id="sec-workflow",
            source_packet_id="packet-1",
        ),
        SpanIR(
            span_id="s2",
            text="When source access is unavailable, request clarification.",
            section_context="Exception handling",
        ),
    ]
    if duplicate_span:
        spans.append(SpanIR(span_id="s1", text="Duplicate span identity."))

    return ArtifactSnapshot(
        snapshot_id="snap-provenance",
        compile_run_id="run-provenance",
        overlay_version=0,
        spans=tuple(spans),
        final_worker=WorkerIR(
            worker_name="MainWorker",
            description="Coordinate the workflow.",
            outputs=[
                WorkerOutput(
                    name="newsletter",
                    required=True,
                    requiredness="required",
                )
            ],
            main_flow=FlowRef(
                blocks=[
                    BlockIR(
                        block_id="b1",
                        block_type="SEQUENTIAL",
                        spans=["s1"],
                    )
                ]
            ),
            steps=[
                StepIR(
                    step_id="st1",
                    text="Collect the approved source material.",
                    source_span_ids=["s1"],
                    command_type="GENERAL_COMMAND",
                    flow_ref="main",
                    block_ref="b1",
                ),
                StepIR(
                    step_id="st2",
                    text="Add the confirmed fallback action.",
                    source_span_ids=[],
                    command_type="GENERAL_COMMAND",
                    flow_ref="ex1",
                    block_ref="b2",
                    metadata={"origin": "user_confirmed_repair"},
                ),
            ],
            exception_flows=[
                ExceptionFlowRef(
                    flow_id="ex1",
                    condition_text="when source access is unavailable",
                    blocks=[
                        BlockIR(
                            block_id="b2",
                            block_type="SEQUENTIAL",
                            spans=[],
                        )
                    ],
                    spans=["s2"],
                )
            ],
        ),
        agent_profile=AgentProfileIR(
            persona=PersonaIR(
                role="Internal communications specialist",
                provenance_relation="assumed",
            )
        ),
        constraints=(
            ConstraintIR(
                constraint_id="c1",
                text="Use only approved evidence.",
                kind="evidence",
                source_span_ids=[],
            ),
        ),
        traces=(
            TraceRecord(
                target_ref="worker:MainWorker",
                source_span_ids=["s1"],
                relation="direct",
                explanation="Main worker is source backed.",
            ),
            TraceRecord(
                target_ref="step:st1",
                source_span_ids=["s1"],
                source_section_id="sec-workflow",
                source_packet_id="packet-1",
                relation="direct",
                explanation="Step maps to the workflow source.",
            ),
            TraceRecord(
                target_ref="step:st2",
                relation="user_confirmed_repair",
                explanation="Step was accepted by the user.",
                metadata={
                    "repair_patch_id": "patch-1",
                    "related_diagnostic_id": "diag-1",
                    "user_text": "Request clarification instead.",
                },
            ),
            TraceRecord(
                target_ref="flow:ex1",
                source_span_ids=["s2"],
                relation="direct",
                explanation="Exception flow maps to source.",
            ),
            TraceRecord(
                target_ref="variable:newsletter",
                relation="assumed",
                explanation="Required output has no direct source span.",
                needs_confirmation=True,
            ),
            TraceRecord(
                target_ref="profile:persona",
                relation="assumed",
                explanation="Persona is assumed.",
                needs_confirmation=True,
            ),
            TraceRecord(
                target_ref="constraint:c1",
                source_span_ids=["s-missing"],
                relation="direct",
                explanation="Constraint references a missing source span.",
            ),
        ),
    )


def _project(snapshot: ArtifactSnapshot):
    cards = CardProjector().project_snapshot(snapshot)
    return cards, ProvenanceProjector().project_snapshot(snapshot, cards)


def test_construct_trace_resolves_complete_span_text() -> None:
    cards, model = _project(_snapshot())
    command_card = next(
        card
        for card in cards
        if card.construct_type == "COMMAND" and card.payload_summary["command_id"] == "st1"
    )

    provenance = model.get_construct(command_card.construct_ref)

    assert provenance is not None
    assert provenance.trace_status == "available"
    assert provenance.provenance_kind == "direct"
    assert provenance.matched_target_refs == ("step:st1",)
    assert provenance.source_span_ids == ("s1",)
    assert provenance.unresolved_span_ids == ()
    assert provenance.spans[0].text == "Collect the approved source material."
    assert provenance.spans[0].source_section_id == "sec-workflow"


def test_no_source_construct_is_explicit_and_does_not_fabricate_span() -> None:
    cards, model = _project(_snapshot())
    profile_card = next(card for card in cards if card.construct_type == "PROFILE")

    provenance = model.get_construct(profile_card.construct_ref)

    assert provenance is not None
    assert provenance.trace_status == "available"
    assert provenance.provenance_kind == "assumed"
    assert provenance.source_span_ids == ()
    assert provenance.spans == ()
    assert provenance.traces[0].needs_confirmation is True


def test_user_confirmed_repair_metadata_is_projected_structurally() -> None:
    cards, model = _project(_snapshot())
    command_card = next(
        card
        for card in cards
        if card.construct_type == "COMMAND" and card.payload_summary["command_id"] == "st2"
    )

    provenance = model.get_construct(command_card.construct_ref)

    assert provenance is not None
    assert provenance.provenance_kind == "user_confirmed_repair"
    repair = provenance.traces[0].repair
    assert repair is not None
    assert repair.repair_patch_id == "patch-1"
    assert repair.related_diagnostic_id == "diag-1"
    assert repair.user_text == "Request clarification instead."


def test_unresolved_trace_span_is_reported_without_fabricated_content() -> None:
    cards, model = _project(_snapshot())
    constraint_card = next(card for card in cards if card.construct_type == "CONSTRAINT")

    provenance = model.get_construct(constraint_card.construct_ref)

    assert provenance is not None
    assert provenance.source_span_ids == ("s-missing",)
    assert provenance.unresolved_span_ids == ("s-missing",)
    assert provenance.spans == ()


def test_duplicate_span_identity_fails_closed() -> None:
    snapshot = _snapshot(duplicate_span=True)
    cards = CardProjector().project_snapshot(snapshot)

    with pytest.raises(ValueError, match="duplicate span_id"):
        ProvenanceProjector().project_snapshot(snapshot, cards)


def test_canonical_snapshot_contains_resolved_and_no_source_provenance() -> None:
    snapshot = CardProjector.load_snapshot_file(
        REPO_ROOT / "examples" / "output" / "demo" / "spl_editing_snapshot.json"
    )
    cards = CardProjector().project_snapshot(snapshot)

    model = ProvenanceProjector().project_snapshot(snapshot, cards)

    assert len(model.constructs) == len(cards)
    assert {item.construct_type for item in model.constructs} >= {
        "WORKER",
        "FLOW",
        "BLOCK",
        "COMMAND",
    }
    assert any(item.spans for item in model.constructs)
    assert all(item.construct_ref for item in model.constructs)
