from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
BACKEND_ROOT = REPO_ROOT / "apps" / "spl-web-demo" / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from spl_web_demo.card_projector import CardProjector  # noqa: E402

from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot  # noqa: E402
from nl2spl.ir.agent_profile_ir import AgentProfileIR, PersonaIR  # noqa: E402
from nl2spl.ir.block_structure_ir import BlockIR  # noqa: E402
from nl2spl.ir.constraint_ir import ConstraintIR  # noqa: E402
from nl2spl.ir.step_ir import StepIR  # noqa: E402
from nl2spl.ir.worker_ir import ExceptionFlowRef, FlowRef, WorkerIR, WorkerOutput  # noqa: E402


def _snapshot(*, duplicate_step: bool = False) -> ArtifactSnapshot:
    steps = [
        StepIR(
            step_id="st1",
            text="Collect the approved source material.",
            source_span_ids=["span-step", "span-step"],
            command_type="GENERAL_COMMAND",
            flow_ref="main",
            block_ref="b1",
            outputs=["source_material"],
        )
    ]
    if duplicate_step:
        steps.append(
            StepIR(
                step_id="st1",
                text="Duplicate identity.",
                source_span_ids=[],
                command_type="GENERAL_COMMAND",
            )
        )

    return ArtifactSnapshot(
        snapshot_id="snap-test",
        compile_run_id="run-test",
        overlay_version=0,
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
                        spans=["span-step"],
                    )
                ]
            ),
            steps=steps,
            exception_flows=[
                ExceptionFlowRef(
                    flow_id="ex1",
                    condition_text="when source access is unavailable",
                    spans=["span-exception"],
                )
            ],
        ),
        agent_profile=AgentProfileIR(
            persona=PersonaIR(
                role="Internal communications specialist",
                source_span_ids=["span-profile"],
                provenance_relation="direct",
            )
        ),
        constraints=(
            ConstraintIR(
                constraint_id="c1",
                text="Use only approved evidence.",
                kind="evidence",
                source_span_ids=["span-constraint"],
            ),
        ),
    )


def test_projects_supported_initial_construct_types_with_stable_identity() -> None:
    projector = CardProjector()

    first = projector.project_snapshot(_snapshot())
    second = projector.project_snapshot(_snapshot())

    assert {card.construct_type for card in first} == {
        "WORKER",
        "FLOW",
        "EXCEPTION_FLOW",
        "BLOCK",
        "COMMAND",
        "REQUIRED_OUTPUT",
        "PROFILE",
        "CONSTRAINT",
    }
    assert [card.construct_ref for card in first] == [card.construct_ref for card in second]
    assert len({card.construct_ref for card in first}) == len(first)

    command = next(card for card in first if card.construct_type == "COMMAND")
    block = next(card for card in first if card.construct_type == "BLOCK")
    flow = next(card for card in first if card.construct_type == "FLOW")
    worker = next(card for card in first if card.construct_type == "WORKER")

    assert command.source_span_ids == ("span-step",)
    assert command.provenance_summary.kind == "source_backed"
    assert command.provenance_summary.source_span_count == 1
    assert command.parent_ref == block.construct_ref
    assert block.parent_ref == flow.construct_ref
    assert flow.parent_ref == worker.construct_ref
    assert command.construct_path == (
        worker.construct_ref,
        flow.construct_ref,
        block.construct_ref,
        command.construct_ref,
    )
    assert worker.provenance_summary.kind == "inferred"


def test_command_without_verified_block_placement_is_review_only() -> None:
    snapshot = _snapshot()
    worker = snapshot.final_worker
    assert isinstance(worker, WorkerIR)
    unplaced_step = replace(worker.steps[0], block_ref="missing-block")
    unplaced_snapshot = replace(snapshot, final_worker=replace(worker, steps=[unplaced_step]))

    cards = CardProjector().project_snapshot(unplaced_snapshot)

    command = next(card for card in cards if card.construct_type == "COMMAND")
    worker_card = next(card for card in cards if card.construct_type == "WORKER")
    assert command.status == "review_only"
    assert command.payload_summary["hierarchy_status"] == "unplaced"
    assert command.parent_ref == worker_card.construct_ref
    assert all(
        card.construct_type != "BLOCK" or card.construct_ref != command.parent_ref for card in cards
    )


def test_rendered_spl_text_is_not_a_card_projection_input() -> None:
    projector = CardProjector()
    baseline = projector.project_snapshot(_snapshot())
    misleading_rendered_text = replace(
        _snapshot(),
        final_spl="[DEFINE_WORKER: InventedFromText]",
    )

    projected = projector.project_snapshot(misleading_rendered_text)

    assert projected == baseline
    assert all(card.title != "InventedFromText" for card in projected)


def test_duplicate_structured_identity_fails_closed() -> None:
    with pytest.raises(ValueError, match="duplicate construct_ref"):
        CardProjector().project_snapshot(_snapshot(duplicate_step=True))


def test_canonical_snapshot_projects_real_cards() -> None:
    cards = CardProjector().project_snapshot_file(
        REPO_ROOT / "examples" / "output" / "demo" / "spl_editing_snapshot.json"
    )

    assert cards
    assert {card.construct_type for card in cards} >= {
        "WORKER",
        "FLOW",
        "BLOCK",
        "COMMAND",
    }
    assert all(card.construct_ref for card in cards)
    assert all(card.construct_path for card in cards)
