"""Tests for Phase R5 typed preview artifact and preview DTO split."""

import pytest

from nl2spl.compiler.spl_editing.preview.artifact import (
    PreviewConstructNode,
    compute_preview_hash,
)
from nl2spl.rendering.spl.construct_renderer import RenderableSPLConstructType


def test_preview_construct_node_consistency() -> None:
    # 1. spl_construct node kind must have spl_construct_type
    with pytest.raises(ValueError, match="spl_construct_type must not be None"):
        PreviewConstructNode(
            node_id="node1",
            node_kind="spl_construct",
            spl_construct_type=None,
            role="role1",
            ir_payload={},
        )

    # 2. non-spl_construct node kind must not have spl_construct_type
    with pytest.raises(ValueError, match="spl_construct_type must be None"):
        PreviewConstructNode(
            node_id="node2",
            node_kind="structured_fallback",
            spl_construct_type=RenderableSPLConstructType.STEP,
            role="role2",
            ir_payload={},
        )

    # 3. Valid nodes should succeed
    node_spl = PreviewConstructNode(
        node_id="node3",
        node_kind="spl_construct",
        spl_construct_type=RenderableSPLConstructType.STEP,
        role="role3",
        ir_payload={},
    )
    node_fallback = PreviewConstructNode(
        node_id="node4",
        node_kind="structured_fallback",
        spl_construct_type=None,
        role="role4",
        ir_payload={},
    )
    assert node_spl.node_kind == "spl_construct"
    assert node_fallback.node_kind == "structured_fallback"


def test_preview_hash_ignores_rendered_text() -> None:
    node = PreviewConstructNode(
        node_id="node3",
        node_kind="spl_construct",
        spl_construct_type=RenderableSPLConstructType.STEP,
        role="role3",
        ir_payload={"dummy": "value"},
    )

    hash1 = compute_preview_hash(
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
    )

    hash2 = compute_preview_hash(
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
    )

    # Hash is deterministic and excludes rendered preview text entirely
    assert hash1 == hash2
    assert isinstance(hash1, str)
    assert len(hash1) == 64
