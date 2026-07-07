from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from nl2spl.compiler.final_ir_package import _deterministic_serialize
from nl2spl.rendering.spl.construct_renderer import RenderableSPLConstructType


@dataclass(frozen=True)
class PreviewConstructNode:
    node_id: str
    node_kind: Literal[
        "spl_construct",
        "artifact_change",
        "diagnostic_display",
        "structured_fallback",
    ]
    spl_construct_type: RenderableSPLConstructType | None
    role: str
    ir_payload: Mapping[str, Any]
    source_refs: tuple[str, ...] = ()
    materialization_status: Literal[
        "planned",
        "dry_run_materialized",
        "context_required",
    ] = "planned"

    def __post_init__(self) -> None:
        if self.node_kind == "spl_construct":
            if self.spl_construct_type is None:
                raise ValueError("spl_construct_type must not be None for spl_construct node_kind")
        else:
            if self.spl_construct_type is not None:
                raise ValueError("spl_construct_type must be None for non-spl_construct node_kind")


@dataclass(frozen=True)
class PreviewArtifactChange:
    change_id: str
    artifact_type: str
    change_type: Literal["add", "modify", "delete"]
    target_path: str
    description: str


@dataclass(frozen=True)
class PreviewStageSliceResult:
    slice_id: str
    stage_name: str
    status: str
    diagnostic_count: int


def compute_preview_hash(
    base_snapshot_id: str,
    issue_id: str,
    strategy_id: str,
    option_id: str,
    directive_hash: str,
    closure_plan_hash: str,
    selected_refset_id: str,
    construct_nodes: tuple[PreviewConstructNode, ...],
    artifact_changes: tuple[PreviewArtifactChange, ...],
    stage_slice_results: tuple[PreviewStageSliceResult, ...],
) -> str:
    """Compute a deterministic hash for the preview artifact excluding any rendered text."""
    payload = {
        "base_snapshot_id": base_snapshot_id,
        "issue_id": issue_id,
        "strategy_id": strategy_id,
        "option_id": option_id,
        "directive_hash": directive_hash,
        "closure_plan_hash": closure_plan_hash,
        "selected_refset_id": selected_refset_id,
        "construct_nodes": _deterministic_serialize(construct_nodes),
        "artifact_changes": _deterministic_serialize(artifact_changes),
        "stage_slice_results": _deterministic_serialize(stage_slice_results),
    }
    serialized = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class TypedRepairPreviewArtifact:
    preview_id: str
    base_snapshot_id: str
    issue_id: str
    strategy_id: str
    option_id: str
    directive_hash: str
    closure_plan_hash: str
    selected_refset_id: str
    construct_nodes: tuple[PreviewConstructNode, ...]
    artifact_changes: tuple[PreviewArtifactChange, ...]
    stage_slice_results: tuple[PreviewStageSliceResult, ...]
    preview_hash: str
