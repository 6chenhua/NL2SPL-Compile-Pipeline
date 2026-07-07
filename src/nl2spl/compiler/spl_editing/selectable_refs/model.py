"""Data models for SelectableRef and SelectableRefSet."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


def build_ref_id(
    ref_kind: str,
    worker_id: str | None,
    source_artifact_ref: str | None,
    scope_path: tuple[str, ...],
    canonical_name: str,
) -> str:
    """Generate a stable, collision-free ref_id for a selectable reference."""
    scope_path_str = ".".join(scope_path) if scope_path else ""
    w_part = worker_id if worker_id is not None else "global"
    s_part = source_artifact_ref if source_artifact_ref is not None else ""
    return f"{ref_kind}:{w_part}:{s_part}:{scope_path_str}:{canonical_name}"


@dataclass(frozen=True)
class SelectableRef:
    """A single selectable reference fact for SPL Editing repair suggestion."""

    ref_id: str
    ref_kind: Literal[
        "variable",
        "worker_input",
        "step_output",
        "required_output",
        "existing_step",
        "exception_flow",
        "worker",
        "handoff",
        "source_span",
        "resource",
    ]
    ref_role: Literal[
        "target_output",
        "selectable_input",
        "placement_anchor",
        "binding_source",
        "binding_target",
        "target_worker",
        "target_exception_flow",
        "source_evidence",
        "api_resource",
    ]
    canonical_name: str
    display_label: str
    worker_id: str | None = None
    source_artifact: str | None = None
    source_artifact_ref: str | None = None
    source_artifact_version: int | None = None
    scope_path: tuple[str, ...] = ()
    construct_path: tuple[str, ...] = ()
    type_hint: str | None = None
    scope: str | None = None
    provenance: str | None = None
    selectable_for: tuple[str, ...] = ()
    confidence: float = 1.0


@dataclass(frozen=True)
class SelectableRefSet:
    """A collection of selectable references for a given issue repair scenario."""

    set_id: str
    issue_id: str
    snapshot_id: str
    worker_scope: str | None
    refs: tuple[SelectableRef, ...]
    policy_id: str
    quality: str | None = None
    missing_required_ref_kinds: tuple[str, ...] = ()
    is_available: bool = True

    def get_ref(self, ref_id: str) -> SelectableRef | None:
        """Retrieve a SelectableRef by its unique ref_id."""
        for r in self.refs:
            if r.ref_id == ref_id:
                return r
        return None


@dataclass(frozen=True)
class ResolvedSelectableRef:
    """Represents a successfully resolved SelectableRef with metadata."""

    ref: SelectableRef
    resolved_role: str
    scope_matched: bool


@dataclass(frozen=True)
class SelectableRefResolutionResult:
    """Structured result of resolving multiple ref IDs."""

    resolved_refs: tuple[ResolvedSelectableRef, ...] = ()
    errors: tuple[str, ...] = ()
    is_success: bool = True
    reconciliation_diagnostics: tuple[str, ...] = ()
