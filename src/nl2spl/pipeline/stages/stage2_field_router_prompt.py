"""Prompt builder and output schema for adapter-guided FieldRoute LLM refinement.

This module defines:

- **Allowed schema constants**: derived from ``ROLE_CONTRACT_REGISTRY`` for
  semantic_role validation, and retained for legacy compatibility with older
  LLM responses that may still include compiler-facing fields.
- **Output schema dataclasses**: Pydantic v2 dataclasses representing the
  expected LLM output shape.  Used for validation.  ``field`` and ``executable``
  are optional (ARC6: compiler derives them from role contract).
- **Prompt builder**: constructs the user-prompt JSON payload from adapter
  evidence.  The LLM payload only exposes ``semantic_roles`` in the
  ``allowed_schema`` — compiler-facing fields are NOT sent to the LLM.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field as dataclass_field
from typing import Any

from nl2spl.canonical import CanonicalCompileInput
from nl2spl.compiler.annotation_role_contract.registry import (
    ROLE_CONTRACT_REGISTRY,
)
from nl2spl.ir.field_route_ir import StructuralPrior
from nl2spl.ir.span_ir import SpanIR

# ===========================================================================
# Allowed schema — closed sets for validation (Step 4)
#
# All constants are derived from the canonical AnnotationRoleContractRegistry.
# Modifying the registry automatically updates these schema values.
# ===========================================================================

ALLOWED_FIELDS: frozenset[str] = ROLE_CONTRACT_REGISTRY.allowed_prompt_fields()
"""All valid ``field`` values (contract-derived + legacy ``identity``/``audience``)."""

ALLOWED_SEMANTIC_ROLES: frozenset[str] = (
    ROLE_CONTRACT_REGISTRY.allowed_llm_semantic_roles()
)
"""LLM-visible canonical semantic roles.  Structural aliases and internal
roles (e.g. ``failure_condition``) are excluded."""

ALLOWED_CONSTRUCT_TARGETS: frozenset[str] = (
    ROLE_CONTRACT_REGISTRY.allowed_construct_targets()
)
"""All valid ``construct_target`` values across all canonical contracts."""

ALLOWED_SLOT_TARGETS: frozenset[str] = (
    ROLE_CONTRACT_REGISTRY.allowed_slot_targets()
)
"""All valid ``slot_target`` values across all canonical contracts."""

# Semantic roles that MUST have executable=False regardless of LLM output
NON_EXECUTABLE_ROLES: frozenset[str] = (
    ROLE_CONTRACT_REGISTRY.prompt_non_executable_roles()
)
"""LLM-visible roles whose contract specifies ``executable=False``."""

# Semantic roles ALLOWED to have executable=True
EXECUTABLE_ROLES: frozenset[str] = (
    ROLE_CONTRACT_REGISTRY.prompt_executable_roles()
)
"""LLM-visible roles whose contract specifies ``executable=True``."""

ROLE_POLICY: dict[str, Any] = {
    "input_contract": {
        "use_only_when": (
            "The span explicitly declares an input, field, parameter, "
            "runtime value, source, connector, repository, or required item "
            "received by the workflow."
        ),
        "do_not_use_when": (
            "The span describes actions, sequencing, process instructions, "
            "questions to ask, checks to perform, or other executable "
            "workflow behavior. Use process_step for those spans."
        ),
    },
    "output_contract": {
        "use_only_when": (
            "The span explicitly declares an artifact, field, result, file, "
            "status, evidence set, or other value produced by the workflow."
        ),
        "do_not_use_when": (
            "The span merely describes how to produce something. Use "
            "process_step for executable production instructions."
        ),
    },
    "process_step": {
        "use_when": (
            "The span tells the agent to determine, identify, ask, retrieve, "
            "produce, revise, validate, deny, or otherwise perform an action."
        ),
    },
}
"""LLM-visible role policy.  This is guidance, not compiler-facing schema."""


# ===========================================================================
# Output schema dataclasses (Pydantic v2 — validation target for Step 4)
# ===========================================================================


@dataclass
class RefinedAnnotation:
    """A single route-level annotation from LLM refinement.

    ``field``, ``executable``, ``construct_target``, and ``slot_target``
    are optional (ARC6): the compiler derives them from the canonical
    role contract via ``_normalize_annotation_contract``.  ``semantic_role``
    is the only required LLM decision — legacy fields are accepted as
    debug hints but do not gate acceptance.
    """

    span_id: str
    field: str | None = None
    semantic_role: str | None = None
    route_family: str | None = None
    construct_target: str | None = None
    slot_target: str | None = None
    executable: bool | None = None
    source_section_id: str | None = None
    source_packet_id: str | None = None
    primary: bool = True
    reason: str | None = None
    metadata: dict[str, Any] = dataclass_field(default_factory=dict)


@dataclass
class SplitSegment:
    """A segment within a split recommendation."""

    text: str
    semantic_role: str | None = None
    construct_target: str | None = None
    slot_target: str | None = None
    executable: bool | None = None


@dataclass
class SplitRecommendation:
    """A recommendation to split a mixed span into segments."""

    parent_span_id: str
    reason: str
    segments: list[SplitSegment] = dataclass_field(default_factory=list)


@dataclass
class RouteDiagnostic:
    """A route-level diagnostic from LLM refinement."""

    span_id: str
    kind: str
    message: str


@dataclass
class ParseDiagnostic:
    """A diagnostic produced during parsing (not from the LLM)."""

    field: str       # which field had the issue
    issue: str       # description of the problem
    raw_value: Any = None  # the raw value that caused the issue


@dataclass
class RouteRefinementResult:
    """Top-level LLM output for adapter-guided FieldRoute refinement."""

    annotations: list[RefinedAnnotation] = dataclass_field(default_factory=list)
    split_recommendations: list[SplitRecommendation] = dataclass_field(default_factory=list)
    diagnostics: list[RouteDiagnostic] = dataclass_field(default_factory=list)
    parse_diagnostics: list[ParseDiagnostic] = dataclass_field(default_factory=list)


# ===========================================================================
# Serialisation helpers
# ===========================================================================


def _evidence_to_dict(ev: Any) -> dict[str, Any]:
    """Serialize an EvidenceRef for the LLM prompt."""
    d: dict[str, Any] = {}
    if getattr(ev, "source_section_id", None):
        d["source_section_id"] = ev.source_section_id
    if getattr(ev, "source_packet_id", None):
        d["source_packet_id"] = ev.source_packet_id
    if getattr(ev, "source_span_ids", None):
        d["source_span_ids"] = list(ev.source_span_ids)
    if getattr(ev, "quoted_text", None):
        d["quoted_text"] = ev.quoted_text
    return d


def _span_to_dict(span: SpanIR) -> dict[str, Any]:
    """Serialize a span for the LLM prompt."""
    d: dict[str, Any] = {
        "span_id": span.span_id,
        "text": span.text,
    }
    if span.source_section_id:
        d["source_section_id"] = span.source_section_id
    if span.source_packet_id:
        d["source_packet_id"] = span.source_packet_id
    return d


def _section_to_dict(section: Any) -> dict[str, Any]:
    """Serialize a raw section for the LLM prompt."""
    return {
        "section_id": section.section_id,
        "canonical_title": section.canonical_title,
        "original_title": section.original_title,
        "text": section.text,
    }


def _packet_to_dict(packet: Any) -> dict[str, Any]:
    """Serialize a semantic packet for the LLM prompt."""
    d: dict[str, Any] = {
        "packet_id": packet.packet_id,
        "source_section_id": packet.source_section_id,
        "packet_type": packet.packet_type,
        "text": packet.text,
    }
    if hasattr(packet, "compile_targets") and packet.compile_targets:
        d["compile_targets"] = list(packet.compile_targets)
    if hasattr(packet, "metadata") and packet.metadata:
        d["metadata"] = dict(packet.metadata)
    return d


def _hint_to_dict(hint: Any) -> dict[str, Any]:
    """Serialize a compile hint for the LLM prompt — ALL CompileHint fields + evidence."""
    d: dict[str, Any] = {
        "source_section_id": hint.source_section_id,
        "text": hint.text,
    }
    if getattr(hint, "target", None):
        d["target"] = hint.target
    if getattr(hint, "suggested_kind", None):
        d["suggested_kind"] = hint.suggested_kind
    if getattr(hint, "suggested_flow", None):
        d["suggested_flow"] = hint.suggested_flow
    if getattr(hint, "suggested_block_type", None):
        d["suggested_block_type"] = hint.suggested_block_type
    if getattr(hint, "suggested_step_type", None):
        d["suggested_step_type"] = hint.suggested_step_type
    if getattr(hint, "suggested_condition", None):
        d["suggested_condition"] = hint.suggested_condition
    if getattr(hint, "suggested_type", None):
        d["suggested_type"] = hint.suggested_type
    if getattr(hint, "suggested_worker_name", None):
        d["suggested_worker_name"] = hint.suggested_worker_name
    if hasattr(hint, "metadata") and hint.metadata:
        d["metadata"] = dict(hint.metadata)
    # Evidence chain
    if hasattr(hint, "evidence") and hint.evidence:
        d["evidence"] = [_evidence_to_dict(ev) for ev in hint.evidence]
    return d


def _prior_to_dict(annotation: Any) -> dict[str, Any]:
    """Serialize a deterministic prior annotation for the LLM prompt."""
    d: dict[str, Any] = {
        "span_id": annotation.span_id,
        "field": annotation.field,
        "prior_source": "packet_type_deterministic_mapping",
    }
    if annotation.semantic_role:
        d["semantic_role"] = annotation.semantic_role
    if annotation.route_family:
        d["route_family"] = annotation.route_family
    if annotation.construct_target:
        d["construct_target"] = annotation.construct_target
    if annotation.slot_target:
        d["slot_target"] = annotation.slot_target
    d["executable"] = annotation.executable
    if annotation.source_section_id:
        d["source_section_id"] = annotation.source_section_id
    if annotation.source_packet_id:
        d["source_packet_id"] = annotation.source_packet_id
    return d


def _structural_prior_to_dict(prior: StructuralPrior) -> dict[str, Any]:
    """Serialize a structural prior for the LLM prompt."""
    d: dict[str, Any] = {
        "span_id": prior.span_id,
        "prior_kind": prior.prior_kind,
        "confidence": prior.confidence,
    }
    if prior.suggested_field:
        d["suggested_field"] = prior.suggested_field
    if prior.source_section_id:
        d["source_section_id"] = prior.source_section_id
    if prior.source_packet_id:
        d["source_packet_id"] = prior.source_packet_id
    if prior.packet_type:
        d["packet_type"] = prior.packet_type
    if prior.reason:
        d["reason"] = prior.reason
    return d


def _fact_to_dict(
    fact: Any,
    extra_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Serialize a hard fact (VariableFact, DelegationIntentFact).

    Always includes the evidence chain.
    """
    fact_text = getattr(fact, "text", None) or getattr(fact, "description", "")
    d: dict[str, Any] = {"name": fact.name, "text": fact_text}
    if getattr(fact, "required", None) is not None:
        d["required"] = fact.required
    if getattr(fact, "source_section_id", None):
        d["source_section_id"] = fact.source_section_id
    if getattr(fact, "data_type", None):
        d["data_type"] = fact.data_type
    if extra_fields:
        d.update(extra_fields)
    # Evidence chain — critical for LLM to see adapter provenance
    if hasattr(fact, "evidence") and fact.evidence:
        d["evidence"] = [_evidence_to_dict(ev) for ev in fact.evidence]
    return d


# ===========================================================================
# Prompt builder
# ===========================================================================


def build_adapter_guided_user_prompt(
    spans: list[SpanIR],
    canonical_input: CanonicalCompileInput,
    structural_priors: list[Any],
    deterministic_annotations: list[Any],
) -> str:
    """Build the user-prompt JSON payload for adapter-guided FieldRoute refinement.

    Payload keys:
      - ``spans``: text spans to classify
      - ``structural_priors``: deterministic structural evidence (NOT final decisions)
      - ``deterministic_annotations``: already-accepted semantic routing decisions
      - ``allowed_schema``: output constraints
    """
    payload: dict[str, Any] = {
        "spans": [_span_to_dict(s) for s in spans],
        "structural_priors": [
            _structural_prior_to_dict(p) for p in structural_priors
        ],
        "deterministic_annotations": [
            _prior_to_dict(a) for a in deterministic_annotations
        ],
        "allowed_schema": {
            "semantic_roles": sorted(ALLOWED_SEMANTIC_ROLES),
        },
        "role_policy": ROLE_POLICY,
    }

    return json.dumps(payload, ensure_ascii=False, indent=2)


# ===========================================================================
# Parse helper — convert raw LLM JSON into RouteRefinementResult
# ===========================================================================


def parse_refinement_result(data: dict[str, Any]) -> RouteRefinementResult:
    """Parse a raw LLM JSON dict into a RouteRefinementResult.

    Missing or malformed fields are captured as-is (``None``) so the
    validator (Step 4) can reject or fix them.  No business defaults are
    injected — the parser must not silently turn malformed LLM output
    into executable behavior.
    """
    parse_diags: list[ParseDiagnostic] = []

    annotations: list[RefinedAnnotation] = []
    for i, raw in enumerate(data.get("annotations", []) or []):
        span_id = raw.get("span_id", "")
        if not span_id:
            parse_diags.append(ParseDiagnostic(
                field=f"annotations[{i}].span_id",
                issue="missing required span_id",
            ))
        # ARC6: field and executable are optional — the compiler derives
        # them from the canonical role contract.  Missing values are NOT
        # parse errors; they are filled in by normalize_annotation_from_role().
        field_val = raw.get("field")  # optional, may be None
        executable_val = raw.get("executable")
        executable: bool | None = None
        if executable_val is None:
            pass  # acceptable — compiler fills this in
        elif isinstance(executable_val, bool):
            executable = executable_val
        else:
            parse_diags.append(ParseDiagnostic(
                field=f"annotations[{i}].executable",
                issue=(
                    "malformed executable value "
                    f"(must be bool, got {type(executable_val).__name__})"
                ),
                raw_value=executable_val,
            ))

        annotations.append(RefinedAnnotation(
            span_id=span_id,
            field=field_val,
            semantic_role=raw.get("semantic_role"),
            route_family=raw.get("route_family"),
            construct_target=raw.get("construct_target"),
            slot_target=raw.get("slot_target"),
            executable=executable,
            source_section_id=raw.get("source_section_id"),
            source_packet_id=raw.get("source_packet_id"),
            primary=raw.get("primary", True),
            reason=raw.get("reason"),
            metadata=dict(raw.get("metadata") or {}),
        ))

    split_recs: list[SplitRecommendation] = []
    for i, raw in enumerate(data.get("split_recommendations", []) or []):
        parent_id = raw.get("parent_span_id", "")
        if not parent_id:
            parse_diags.append(ParseDiagnostic(
                field=f"split_recommendations[{i}].parent_span_id",
                issue="missing required parent_span_id",
            ))
        segments: list[SplitSegment] = []
        for j, seg in enumerate(raw.get("segments", []) or []):
            seg_text = seg.get("text", "")
            if not seg_text:
                parse_diags.append(ParseDiagnostic(
                    field=f"split_recommendations[{i}].segments[{j}].text",
                    issue="missing required segment text",
                ))
            segments.append(SplitSegment(
                text=seg_text,
                semantic_role=seg.get("semantic_role"),
                construct_target=seg.get("construct_target"),
                slot_target=seg.get("slot_target"),
                executable=seg.get("executable"),
            ))
        split_recs.append(SplitRecommendation(
            parent_span_id=parent_id,
            reason=raw.get("reason", ""),
            segments=segments,
        ))

    diagnostics: list[RouteDiagnostic] = []
    for i, raw in enumerate(data.get("diagnostics", []) or []):
        diag_span = raw.get("span_id", "")
        if not diag_span:
            parse_diags.append(ParseDiagnostic(
                field=f"diagnostics[{i}].span_id",
                issue="missing required span_id on diagnostic",
            ))
        diagnostics.append(RouteDiagnostic(
            span_id=diag_span,
            kind=raw.get("kind", ""),
            message=raw.get("message", ""),
        ))

    return RouteRefinementResult(
        annotations=annotations,
        split_recommendations=split_recs,
        diagnostics=diagnostics,
        parse_diagnostics=parse_diags,
    )
