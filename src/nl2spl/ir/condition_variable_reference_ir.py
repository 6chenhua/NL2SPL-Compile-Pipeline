"""Condition variable reference read-analysis IR."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Literal

from nl2spl.compiler.artifacts.snapshot.serialization.serializers_diagnostics import (
    CompileDiagnosticSerializer,
)
from nl2spl.ir.diagnostics import CompileDiagnostic

ConditionOwnerKind = Literal[
    "block_condition",
    "alternative_flow_condition",
    "exception_flow_condition",
]

ConditionVariableReferenceStatus = Literal[
    "resolved",
    "unresolved",
    "ambiguous",
    "invalid_qualified_ref",
    "rejected",
]

ConditionReferenceEvidenceKind = Literal[
    "explicit_ref_token",
    "llm_condition_semantic_match",
    "llm_unresolved_condition_symbol",
]

ConditionTextRewriteReason = Literal[
    "composite_output_rewrite",
    "qualified_ref_normalization",
    "llm_semantic_ref_materialization",
]

_SOURCE_KIND_BY_EVIDENCE: dict[str, str] = {
    "explicit_ref_token": "explicit",
    "llm_condition_semantic_match": "llm",
    "llm_unresolved_condition_symbol": "unresolved",
}

_LEGACY_EVIDENCE_KIND_MAP: dict[str, ConditionReferenceEvidenceKind] = {
    "explicit_ref": "explicit_ref_token",
    "implicit_source_text_match": "llm_condition_semantic_match",
}


def normalize_condition_evidence_kind(value: str) -> ConditionReferenceEvidenceKind:
    """Normalize legacy and v2 evidence-kind values."""
    normalized = _LEGACY_EVIDENCE_KIND_MAP.get(value, value)
    if normalized not in _SOURCE_KIND_BY_EVIDENCE:
        raise ValueError(f"Unknown condition reference evidence_kind: {value!r}")
    return normalized  # type: ignore[return-value]


def build_condition_reference_id(
    owner_ref: str,
    index: int,
    source_kind: str = "explicit",
) -> str:
    """Build a stable condition-reference identifier."""
    owner_ref_hash = hashlib.sha256(owner_ref.encode("utf-8")).hexdigest()[:10]
    safe_source_kind = source_kind or "explicit"
    return f"cond_ref_{owner_ref_hash}_{safe_source_kind}_{index}"


def condition_reference_source_kind(evidence_kind: str) -> str:
    """Return the reference-id source-kind segment for an evidence kind."""
    return _SOURCE_KIND_BY_EVIDENCE[normalize_condition_evidence_kind(evidence_kind)]


@dataclass(frozen=True)
class ConditionVariableReferenceIR:
    """Variable reference read by a condition owner.

    Stage 6.5 may derive a reference from either an explicit SPL ``<REF>`` token
    or an LLM semantic condition match.  The LLM output is only evidence; the
    resolved status is admitted by deterministic SymbolTable/ResourceRegistry
    checks.
    """

    reference_id: str
    owner_kind: ConditionOwnerKind
    owner_ref: str
    condition_text: str
    ref_text: str | None
    canonical_ref: str | None
    top_level_name: str | None
    qualified_path: tuple[str, ...]
    status: ConditionVariableReferenceStatus
    source_span_ids: tuple[str, ...]
    worker_id: str | None
    flow_ref: str | None
    block_ref: str | None
    evidence_kind: ConditionReferenceEvidenceKind = "explicit_ref_token"
    evidence_text: str | None = None
    selected_symbol: str | None = None
    proposed_symbol_text: str | None = None
    confidence: Literal["high", "medium", "low"] | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        normalized_evidence = normalize_condition_evidence_kind(self.evidence_kind)
        object.__setattr__(self, "evidence_kind", normalized_evidence)
        object.__setattr__(self, "qualified_path", tuple(self.qualified_path))
        object.__setattr__(self, "source_span_ids", tuple(self.source_span_ids))
        if normalized_evidence == "explicit_ref_token" and self.ref_text is None:
            raise ValueError("explicit_ref_token condition refs require ref_text.")
        if normalized_evidence == "llm_condition_semantic_match":
            if self.selected_symbol is None:
                raise ValueError(
                    "llm_condition_semantic_match condition refs require selected_symbol."
                )
            if self.evidence_text is None:
                raise ValueError(
                    "llm_condition_semantic_match condition refs require evidence_text."
                )
        if normalized_evidence == "llm_unresolved_condition_symbol":
            if self.proposed_symbol_text is None:
                raise ValueError(
                    "llm_unresolved_condition_symbol refs require proposed_symbol_text."
                )
            if self.status not in {"unresolved", "rejected"}:
                raise ValueError(
                    "llm_unresolved_condition_symbol refs must be unresolved or rejected."
                )

    def to_payload(self) -> dict[str, object]:
        return {
            "reference_id": self.reference_id,
            "owner_kind": self.owner_kind,
            "owner_ref": self.owner_ref,
            "condition_text": self.condition_text,
            "ref_text": self.ref_text,
            "canonical_ref": self.canonical_ref,
            "top_level_name": self.top_level_name,
            "qualified_path": list(self.qualified_path),
            "status": self.status,
            "source_span_ids": list(self.source_span_ids),
            "worker_id": self.worker_id,
            "flow_ref": self.flow_ref,
            "block_ref": self.block_ref,
            "evidence_kind": self.evidence_kind,
            "evidence_text": self.evidence_text,
            "selected_symbol": self.selected_symbol,
            "proposed_symbol_text": self.proposed_symbol_text,
            "confidence": self.confidence,
            "reason": self.reason,
        }

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, object],
    ) -> ConditionVariableReferenceIR:
        return cls(
            reference_id=str(payload["reference_id"]),
            owner_kind=payload["owner_kind"],  # type: ignore[arg-type]
            owner_ref=str(payload["owner_ref"]),
            condition_text=str(payload["condition_text"]),
            ref_text=(
                str(payload["ref_text"])
                if payload.get("ref_text") is not None
                else None
            ),
            canonical_ref=(
                str(payload["canonical_ref"])
                if payload.get("canonical_ref") is not None
                else None
            ),
            top_level_name=(
                str(payload["top_level_name"])
                if payload.get("top_level_name") is not None
                else None
            ),
            qualified_path=tuple(str(x) for x in payload.get("qualified_path", [])),  # type: ignore[arg-type]
            status=payload["status"],  # type: ignore[arg-type]
            source_span_ids=tuple(str(x) for x in payload.get("source_span_ids", [])),  # type: ignore[arg-type]
            worker_id=(
                str(payload["worker_id"])
                if payload.get("worker_id") is not None
                else None
            ),
            flow_ref=(
                str(payload["flow_ref"])
                if payload.get("flow_ref") is not None
                else None
            ),
            block_ref=(
                str(payload["block_ref"])
                if payload.get("block_ref") is not None
                else None
            ),
            evidence_kind=payload.get("evidence_kind", "explicit_ref_token"),  # type: ignore[arg-type]
            evidence_text=(
                str(payload["evidence_text"])
                if payload.get("evidence_text") is not None
                else None
            ),
            selected_symbol=(
                str(payload["selected_symbol"])
                if payload.get("selected_symbol") is not None
                else None
            ),
            proposed_symbol_text=(
                str(payload["proposed_symbol_text"])
                if payload.get("proposed_symbol_text") is not None
                else None
            ),
            confidence=payload.get("confidence"),  # type: ignore[arg-type]
            reason=str(payload["reason"]) if payload.get("reason") is not None else None,
        )


@dataclass(frozen=True)
class ConditionTextRewrite:
    """Rewrite-approved condition text for a condition owner."""

    owner_ref: str
    original_condition_text: str
    rewritten_condition_text: str
    rewrite_reason: ConditionTextRewriteReason
    source_reference_ids: tuple[str, ...]

    def to_payload(self) -> dict[str, object]:
        return {
            "owner_ref": self.owner_ref,
            "original_condition_text": self.original_condition_text,
            "rewritten_condition_text": self.rewritten_condition_text,
            "rewrite_reason": self.rewrite_reason,
            "source_reference_ids": list(self.source_reference_ids),
        }

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> ConditionTextRewrite:
        return cls(
            owner_ref=str(payload["owner_ref"]),
            original_condition_text=str(payload["original_condition_text"]),
            rewritten_condition_text=str(payload["rewritten_condition_text"]),
            rewrite_reason=payload["rewrite_reason"],  # type: ignore[arg-type]
            source_reference_ids=tuple(
                str(x) for x in payload.get("source_reference_ids", [])  # type: ignore[arg-type]
            ),
        )


@dataclass(frozen=True)
class ConditionVariableReferencePlan:
    """Read-only analysis plan for condition variable references."""

    references: tuple[ConditionVariableReferenceIR, ...] = ()
    text_rewrites: tuple[ConditionTextRewrite, ...] = ()
    diagnostics: tuple[CompileDiagnostic, ...] = ()
    metadata: dict[str, object] = field(default_factory=dict)

    def to_payload(self) -> dict[str, object]:
        diag_ser = CompileDiagnosticSerializer()
        return {
            "schema_version": "condition_variable_reference_plan.v2",
            "references": [ref.to_payload() for ref in self.references],
            "text_rewrites": [rewrite.to_payload() for rewrite in self.text_rewrites],
            "diagnostics": [
                diag_ser.to_canonical(diagnostic)
                for diagnostic in self.diagnostics
            ],
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, object],
    ) -> ConditionVariableReferencePlan:
        schema_version = payload.get("schema_version")
        if schema_version not in {
            "condition_variable_reference_plan.v1",
            "condition_variable_reference_plan.v2",
        }:
            raise ValueError("Invalid ConditionVariableReferencePlan schema_version")
        diag_ser = CompileDiagnosticSerializer()
        return cls(
            references=tuple(
                ConditionVariableReferenceIR.from_payload(item)
                for item in payload.get("references", [])  # type: ignore[arg-type]
            ),
            text_rewrites=tuple(
                ConditionTextRewrite.from_payload(item)
                for item in payload.get("text_rewrites", [])  # type: ignore[arg-type]
            ),
            diagnostics=tuple(
                diag_ser.from_canonical(item)
                for item in payload.get("diagnostics", [])  # type: ignore[arg-type]
            ),
            metadata=dict(payload.get("metadata", {})),  # type: ignore[arg-type]
        )

    def references_by_owner(self) -> dict[str, tuple[ConditionVariableReferenceIR, ...]]:
        grouped: dict[str, list[ConditionVariableReferenceIR]] = {}
        for reference in self.references:
            grouped.setdefault(reference.owner_ref, []).append(reference)
        return {key: tuple(value) for key, value in grouped.items()}

    def rewrites_by_owner(self) -> dict[str, ConditionTextRewrite]:
        return {rewrite.owner_ref: rewrite for rewrite in self.text_rewrites}

    def final_condition_text(self, owner_ref: str, original_text: str) -> str:
        rewrite = self.rewrites_by_owner().get(owner_ref)
        return rewrite.rewritten_condition_text if rewrite else original_text
