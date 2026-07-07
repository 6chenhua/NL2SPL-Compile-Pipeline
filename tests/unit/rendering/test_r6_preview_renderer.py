"""Tests for Phase R6 repair preview renderer."""

from nl2spl.compiler.spl_editing.preview.artifact import (
    PreviewConstructNode,
    TypedRepairPreviewArtifact,
)
from nl2spl.rendering import (
    RenderableSPLConstructType,
    SPLRenderContext,
    render_repair_preview_spl,
)


def test_render_repair_preview_spl_success() -> None:
    # A valid StepIR dict payload
    step_payload = {
        "step_id": "st1",
        "text": "Generate feedback report",
        "command_type": "DISPLAY_MESSAGE",
        "inputs": [],
        "outputs": [],
        "source_span_ids": [],
    }

    node = PreviewConstructNode(
        node_id="node1",
        node_kind="spl_construct",
        spl_construct_type=RenderableSPLConstructType.STEP,
        role="role1",
        ir_payload=step_payload,
    )

    artifact = TypedRepairPreviewArtifact(
        preview_id="prev1",
        base_snapshot_id="snap1",
        issue_id="issue1",
        strategy_id="strat1",
        option_id="opt1",
        directive_hash="dirhash",
        closure_plan_hash="closurehash",
        selected_refset_id="refset1",
        construct_nodes=(node,),
        artifact_changes=(),
        stage_slice_results=(),
        preview_hash="prevhash",
    )

    context = SPLRenderContext()
    res = render_repair_preview_spl(artifact, context)

    assert res.preview_id == "prev1"
    assert res.format == "spl_text"
    assert "COMMAND-1 [DISPLAY Generate feedback report]" in res.text


def test_render_repair_preview_fallback() -> None:
    # A node with missing or invalid materialized payload
    node = PreviewConstructNode(
        node_id="node2",
        node_kind="structured_fallback",  # Changed to match non-spl_construct node_kind constraints
        spl_construct_type=None,
        role="role2",
        ir_payload={"action": "ensure", "construct_type": "STEP"},
    )

    artifact = TypedRepairPreviewArtifact(
        preview_id="prev2",
        base_snapshot_id="snap1",
        issue_id="issue1",
        strategy_id="strat1",
        option_id="opt1",
        directive_hash="dirhash",
        closure_plan_hash="closurehash",
        selected_refset_id="refset1",
        construct_nodes=(node,),
        artifact_changes=(),
        stage_slice_results=(),
        preview_hash="prevhash",
    )

    context = SPLRenderContext()
    res = render_repair_preview_spl(artifact, context)

    assert res.text == "Will ensure STEP for role role2"
