from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from nl2spl.ir.diagnostics import CompileDiagnostic


def canonicalize_action_text(text: str) -> str:
    """Canonicalize action text according to stage 7 rules.

    Rules:
    1. lowercase
    2. trim surrounding punctuation and whitespace
    3. collapse whitespace to single space
    4. remove trailing sentence punctuation (. ? !)
    5. do not lemmatize
    6. do not remove stopwords
    """
    if not text:
        return ""
    text = text.lower()
    text = re.sub(r"\s+", " ", text).strip()
    text = text.strip(" ,;.\"'`()[]{}")
    text = re.sub(r"[.!?]+$", "", text)
    return text.strip()


def compile_diagnostic_to_dict(d: CompileDiagnostic) -> dict[str, Any]:
    return {
        "diagnostic_id": d.diagnostic_id,
        "kind": d.kind,
        "severity": d.severity,
        "message": d.message,
        "target_ref": d.target_ref,
        "source_span_ids": list(d.source_span_ids),
        "source_section_id": d.source_section_id,
        "source_packet_id": d.source_packet_id,
        "suggested_resolution": d.suggested_resolution,
        "metadata": dict(d.metadata),
        "blocks_rendering": d.blocks_rendering,
        "blocks_completion": d.blocks_completion,
    }


def compile_diagnostic_from_dict(data: dict[str, Any]) -> CompileDiagnostic:
    return CompileDiagnostic(
        diagnostic_id=str(data["diagnostic_id"]),
        kind=str(data["kind"]),
        severity=str(data["severity"]),
        message=str(data["message"]),
        target_ref=str(data["target_ref"]) if data.get("target_ref") is not None else None,
        source_span_ids=list(data.get("source_span_ids") or []),
        source_section_id=str(data["source_section_id"]) if data.get("source_section_id") else None,
        source_packet_id=str(data["source_packet_id"]) if data.get("source_packet_id") else None,
        suggested_resolution=(
            str(data["suggested_resolution"]) if data.get("suggested_resolution") else None
        ),
        metadata=dict(data.get("metadata") or {}),
        blocks_rendering=bool(data.get("blocks_rendering", False)),
        blocks_completion=bool(data.get("blocks_completion", True)),
    )


@dataclass(frozen=True)
class SourceRangeIR:
    source_span_id: str
    char_start: int | None
    char_end: int | None
    relation: Literal[
        "direct",
        "normalized_whitespace",
        "derived",
        "ambiguous",
    ]

    def to_dict(self) -> dict[str, object]:
        return {
            "source_span_id": self.source_span_id,
            "char_start": self.char_start,
            "char_end": self.char_end,
            "relation": self.relation,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> SourceRangeIR:
        return cls(
            source_span_id=str(data["source_span_id"]),
            char_start=int(data["char_start"]) if data.get("char_start") is not None else None,
            char_end=int(data["char_end"]) if data.get("char_end") is not None else None,
            relation=data["relation"],  # type: ignore[arg-type]
        )


@dataclass(frozen=True)
class ExecutableActionIR:
    action_id: str
    action_kind: Literal[
        "source_slice",
        "residual_slice",
        "construct_derived",
        "handoff_derived",
    ]
    source_span_ids: tuple[str, ...]
    action_text: str
    normalized_action_key: str
    command_type: Literal[
        "GENERAL_COMMAND",
        "CALL_API",
        "REQUEST_INPUT",
        "INVOKE_WORKER",
        "DISPLAY_MESSAGE",
    ]
    owning_authority: str
    coverage_status: Literal[
        "exact",
        "residual",
        "derived",
        "ambiguous",
        "uncovered",
    ]

    source_section_id: str | None = None
    source_packet_id: str | None = None
    coverage_refs: tuple[str, ...] = ()
    covered_ranges: tuple[SourceRangeIR, ...] = ()
    excluded_ranges: tuple[SourceRangeIR, ...] = ()

    source_construct_demand_id: str | None = None
    source_handoff_id: str | None = None
    capability_intent_id: str | None = None
    worker_promotion_id: str | None = None

    flow_ref: str | None = None
    block_ref: str | None = None
    placement_status: Literal["placed", "unplaced", "ambiguous"] = "unplaced"

    input_hints: tuple[str, ...] = ()
    output_hints: tuple[str, ...] = ()
    output_policy: Literal[
        "no_output",
        "produces_output",
        "refines_existing_output",
        "validates_existing_output",
        "unknown",
    ] = "unknown"

    metadata: Mapping[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "action_id": self.action_id,
            "action_kind": self.action_kind,
            "source_span_ids": list(self.source_span_ids),
            "source_section_id": self.source_section_id,
            "source_packet_id": self.source_packet_id,
            "coverage_refs": list(self.coverage_refs),
            "covered_ranges": [r.to_dict() for r in self.covered_ranges],
            "excluded_ranges": [r.to_dict() for r in self.excluded_ranges],
            "action_text": self.action_text,
            "normalized_action_key": self.normalized_action_key,
            "command_type": self.command_type,
            "owning_authority": self.owning_authority,
            "source_construct_demand_id": self.source_construct_demand_id,
            "source_handoff_id": self.source_handoff_id,
            "capability_intent_id": self.capability_intent_id,
            "worker_promotion_id": self.worker_promotion_id,
            "flow_ref": self.flow_ref,
            "block_ref": self.block_ref,
            "placement_status": self.placement_status,
            "input_hints": list(self.input_hints),
            "output_hints": list(self.output_hints),
            "output_policy": self.output_policy,
            "coverage_status": self.coverage_status,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> ExecutableActionIR:
        cov_ranges = tuple(
            SourceRangeIR.from_dict(r) for r in (data.get("covered_ranges") or [])
        )
        exc_ranges = tuple(
            SourceRangeIR.from_dict(r) for r in (data.get("excluded_ranges") or [])
        )
        return cls(
            action_id=str(data["action_id"]),
            action_kind=data["action_kind"],  # type: ignore[arg-type]
            source_span_ids=tuple(data.get("source_span_ids") or ()),
            source_section_id=(
                str(data["source_section_id"]) if data.get("source_section_id") else None
            ),
            source_packet_id=(
                str(data["source_packet_id"]) if data.get("source_packet_id") else None
            ),
            coverage_refs=tuple(data.get("coverage_refs") or ()),
            covered_ranges=cov_ranges,
            excluded_ranges=exc_ranges,
            action_text=str(data["action_text"]),
            normalized_action_key=str(data["normalized_action_key"]),
            command_type=data["command_type"],  # type: ignore[arg-type]
            owning_authority=str(data["owning_authority"]),
            source_construct_demand_id=(
                str(data["source_construct_demand_id"])
                if data.get("source_construct_demand_id")
                else None
            ),
            source_handoff_id=(
                str(data["source_handoff_id"]) if data.get("source_handoff_id") else None
            ),
            capability_intent_id=(
                str(data["capability_intent_id"]) if data.get("capability_intent_id") else None
            ),
            worker_promotion_id=(
                str(data["worker_promotion_id"]) if data.get("worker_promotion_id") else None
            ),
            flow_ref=str(data["flow_ref"]) if data.get("flow_ref") else None,
            block_ref=str(data["block_ref"]) if data.get("block_ref") else None,
            placement_status=data.get("placement_status", "unplaced"),  # type: ignore[arg-type]
            input_hints=tuple(data.get("input_hints") or ()),
            output_hints=tuple(data.get("output_hints") or ()),
            output_policy=data.get("output_policy", "unknown"),  # type: ignore[arg-type]
            coverage_status=data["coverage_status"],  # type: ignore[arg-type]
            metadata=dict(data.get("metadata") or {}),
        )


@dataclass(frozen=True)
class ActionCoverageReportIR:
    report_id: str
    source_span_id: str
    covered_ranges: tuple[SourceRangeIR, ...]
    uncovered_ranges: tuple[SourceRangeIR, ...]
    overlapping_ranges: tuple[SourceRangeIR, ...]
    action_ids: tuple[str, ...]
    status: Literal[
        "fully_partitioned",
        "has_uncovered_residual",
        "has_incompatible_overlap",
        "ambiguous",
    ]
    diagnostics: tuple[CompileDiagnostic, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "report_id": self.report_id,
            "source_span_id": self.source_span_id,
            "covered_ranges": [r.to_dict() for r in self.covered_ranges],
            "uncovered_ranges": [r.to_dict() for r in self.uncovered_ranges],
            "overlapping_ranges": [r.to_dict() for r in self.overlapping_ranges],
            "action_ids": list(self.action_ids),
            "status": self.status,
            "diagnostics": [compile_diagnostic_to_dict(d) for d in self.diagnostics],
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> ActionCoverageReportIR:
        cov_ranges = tuple(
            SourceRangeIR.from_dict(r) for r in (data.get("covered_ranges") or [])
        )
        unc_ranges = tuple(
            SourceRangeIR.from_dict(r) for r in (data.get("uncovered_ranges") or [])
        )
        ovl_ranges = tuple(
            SourceRangeIR.from_dict(r) for r in (data.get("overlapping_ranges") or [])
        )
        diags = tuple(
            compile_diagnostic_from_dict(d) for d in (data.get("diagnostics") or [])
        )
        return cls(
            report_id=str(data["report_id"]),
            source_span_id=str(data["source_span_id"]),
            covered_ranges=cov_ranges,
            uncovered_ranges=unc_ranges,
            overlapping_ranges=ovl_ranges,
            action_ids=tuple(data.get("action_ids") or ()),
            status=data["status"],  # type: ignore[arg-type]
            diagnostics=diags,
        )


@dataclass(frozen=True)
class WorkerActionPlanIR:
    main_worker_id: str
    worker_actions: Mapping[str, tuple[ExecutableActionIR, ...]]
    coverage_reports: tuple[ActionCoverageReportIR, ...] = ()
    diagnostics: tuple[CompileDiagnostic, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "main_worker_id": self.main_worker_id,
            "worker_actions": {
                worker_id: [a.to_dict() for a in actions]
                for worker_id, actions in self.worker_actions.items()
            },
            "coverage_reports": [r.to_dict() for r in self.coverage_reports],
            "diagnostics": [compile_diagnostic_to_dict(d) for d in self.diagnostics],
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> WorkerActionPlanIR:
        actions_dict = {}
        for worker_id, actions_list in data.get("worker_actions", {}).items():
            actions_dict[str(worker_id)] = tuple(
                ExecutableActionIR.from_dict(a) for a in actions_list
            )
        diags = tuple(
            compile_diagnostic_from_dict(d) for d in (data.get("diagnostics") or [])
        )
        return cls(
            main_worker_id=str(data["main_worker_id"]),
            worker_actions=actions_dict,
            coverage_reports=tuple(
                ActionCoverageReportIR.from_dict(r) for r in (data.get("coverage_reports") or [])
            ),
            diagnostics=diags,
        )
