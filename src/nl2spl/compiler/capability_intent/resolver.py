"""Deterministic resolution and admission for external capability intents."""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from typing import Iterable

from nl2spl.compiler.capability_intent.admission import (
    capability_admission,
    invocation_admission,
)
from nl2spl.compiler.capability_intent.candidate_validator import normalize_surface
from nl2spl.compiler.capability_intent.demand_binding_view import (
    CapabilityDemandBindingViewIR,
    project_capability_binding_view,
)
from nl2spl.compiler.capability_intent.model import (
    CapabilityEvidenceIR,
    EarlyCapabilityEvidenceView,
    ExternalCapabilityExtractionResult,
    ExternalCapabilityIntentCandidateIR,
    ExternalCapabilityIntentIR,
    ExternalCapabilityIntentPlanIR,
)
from nl2spl.compiler.resource_contract_demand_view.model import (
    ResourceContractDemandView,
)
from nl2spl.ir.diagnostics import CompileDiagnostic


class ExternalCapabilityIntentResolver:
    """Merge, bind, admit, and identify candidates without reading raw NL."""

    def resolve(
        self,
        *,
        source_schema: str,
        extraction: ExternalCapabilityExtractionResult,
        early_evidence: EarlyCapabilityEvidenceView,
        demand_view: ResourceContractDemandView | None,
    ) -> ExternalCapabilityIntentPlanIR:
        binding_view = project_capability_binding_view(demand_view)
        if extraction.status == "unavailable":
            return self._unavailable_plan(
                source_schema, extraction, early_evidence
            )

        groups = self._merge_groups(extraction.candidates)
        intents: list[ExternalCapabilityIntentIR] = []
        resolution_map: dict[str, str | None] = {}
        diagnostics = list(extraction.diagnostics)
        for group in groups:
            intent = self._resolve_group(source_schema, group, binding_view)
            intents.append(intent)
            for candidate_id in intent.source_candidate_ids:
                resolution_map[candidate_id] = intent.intent_id
            if intent.capability_admission_status != "confirmed_capability":
                diagnostics.append(_candidate_diagnostic(intent))

        plan_id = _plan_id(source_schema, intents, extraction.status)
        return ExternalCapabilityIntentPlanIR(
            plan_id=plan_id,
            intents=tuple(sorted(intents, key=lambda item: item.intent_id)),
            dispositions=extraction.dispositions,
            candidate_resolution_map=resolution_map,
            diagnostics=tuple(sorted(diagnostics, key=lambda item: item.diagnostic_id)),
            metadata={
                "resolver_version": "ExternalCapabilityIntentResolverV1",
                "extraction_status": extraction.status,
                "binding_view_available": demand_view is not None,
                "authority": "external_capability_intent_plan",
            },
        )

    def _merge_groups(
        self,
        candidates: Iterable[ExternalCapabilityIntentCandidateIR],
    ) -> tuple[tuple[ExternalCapabilityIntentCandidateIR, ...], ...]:
        grouped: dict[tuple[str, ...], list[ExternalCapabilityIntentCandidateIR]] = (
            defaultdict(list)
        )
        for candidate in candidates:
            if candidate.identity_claim == "explicit_name" and candidate.capability_ref_candidate:
                key = ("explicit", normalize_surface(candidate.capability_ref_candidate))
            elif candidate.identity_claim == "described_unnamed" and candidate.capability_surface:
                key = (
                    "described",
                    normalize_surface(candidate.capability_surface),
                    normalize_surface(candidate.operation_text),
                    candidate.source_section_id or "",
                    candidate.source_packet_id or "",
                )
            else:
                key = ("candidate", candidate.candidate_id)
            grouped[key].append(candidate)
        return tuple(
            tuple(sorted(group, key=lambda item: item.candidate_id))
            for _, group in sorted(grouped.items())
        )

    def _resolve_group(
        self,
        source_schema: str,
        candidates: tuple[ExternalCapabilityIntentCandidateIR, ...],
        binding_view: tuple[CapabilityDemandBindingViewIR, ...],
    ) -> ExternalCapabilityIntentIR:
        source_span_ids = tuple(
            sorted({sid for item in candidates for sid in item.source_span_ids}, key=_span_sort_key)
        )
        evidence = tuple(
            sorted(
                {item.evidence_id: item for candidate in candidates for item in candidate.evidence}.values(),
                key=lambda item: item.evidence_id,
            )
        )
        boundary_claim = _unanimous(
            item.boundary_claim for item in candidates
        )
        identity_claim = _unanimous(
            item.identity_claim for item in candidates
        )
        invocation_claim = _unanimous(
            item.invocation_claim for item in candidates
        )
        representative = candidates[0]
        synthetic = ExternalCapabilityIntentCandidateIR(
            candidate_id=representative.candidate_id,
            source_span_ids=source_span_ids,
            operation_surface=representative.operation_surface,
            operation_text=representative.operation_text,
            capability_surface=representative.capability_surface,
            capability_ref_candidate=representative.capability_ref_candidate,
            boundary_claim=boundary_claim if boundary_claim in {
                "external", "candidate_external", "unresolved"
            } else "unresolved",
            identity_claim=identity_claim if identity_claim in {
                "explicit_name", "described_unnamed", "missing", "ambiguous"
            } else "ambiguous",
            invocation_claim=invocation_claim if invocation_claim in {
                "executable", "mention_only", "policy_only", "unresolved"
            } else "unresolved",
            evidence=evidence,
            source_section_id=representative.source_section_id,
            source_packet_id=representative.source_packet_id,
        )
        boundary_status, capability_status = capability_admission(synthetic)
        identity_status = synthetic.identity_claim
        capability_ref = (
            synthetic.capability_ref_candidate
            if identity_status == "explicit_name"
            and synthetic.capability_ref_candidate is not None
            and _grammar_safe_name(synthetic.capability_ref_candidate)
            else None
        )
        if identity_status == "explicit_name" and capability_ref is None:
            identity_status = "ambiguous"
            capability_status = "candidate_capability"
        invocation_status = synthetic.invocation_claim
        invocation_status_admission = invocation_admission(
            invocation_status, evidence, capability_status
        )
        input_refs, output_refs, binding_status, unresolved = _bind_resources(
            source_span_ids,
            synthetic.source_section_id,
            synthetic.source_packet_id,
            binding_view,
        )
        intent_id = _intent_id(
            source_schema,
            source_span_ids,
            synthetic.capability_surface,
            synthetic.operation_text,
        )
        return ExternalCapabilityIntentIR(
            intent_id=intent_id,
            source_candidate_ids=tuple(item.candidate_id for item in candidates),
            source_span_ids=source_span_ids,
            operation_text=synthetic.operation_text,
            capability_surface=synthetic.capability_surface,
            capability_ref=capability_ref,
            boundary_status=boundary_status,
            identity_status=identity_status,
            invocation_status=invocation_status,
            capability_admission_status=capability_status,
            invocation_admission_status=invocation_status_admission,
            evidence=evidence,
            input_refs=input_refs,
            output_refs=output_refs,
            binding_status=binding_status,
            unresolved_binding_claims=unresolved,
            source_section_id=synthetic.source_section_id,
            source_packet_id=synthetic.source_packet_id,
            metadata={
                "resolver_version": "ExternalCapabilityIntentResolverV1",
                "merged_candidate_count": len(candidates),
            },
        )

    def _unavailable_plan(
        self,
        source_schema: str,
        extraction: ExternalCapabilityExtractionResult,
        early_evidence: EarlyCapabilityEvidenceView,
    ) -> ExternalCapabilityIntentPlanIR:
        explicit = [
            item
            for item in early_evidence.candidates
            if item.claim_hint == "adapter_declaration"
        ]
        diagnostics: list[CompileDiagnostic] = []
        # Explicit adapter declarations remain declaration-only source facts.
        intents: list[ExternalCapabilityIntentIR] = []
        for item in explicit:
            surface = item.surface_text.strip()
            ref = surface if _grammar_safe_name(surface) else None
            evidence = CapabilityEvidenceIR(
                evidence_id=f"semantic_{item.evidence_id}",
                source_span_id=item.source_span_id or f"adapter:{item.evidence_id}",
                claim="boundary",
                surface_text=surface,
                relation="direct",
                source_section_id=item.source_section_id,
                source_packet_id=item.source_packet_id,
                metadata={"origin": "adapter_declaration"},
            )
            intent_id = _intent_id(
                source_schema,
                (item.source_span_id,) if item.source_span_id else (),
                surface,
                "",
            )
            intents.append(
                ExternalCapabilityIntentIR(
                    intent_id=intent_id,
                    source_candidate_ids=(),
                    source_span_ids=(item.source_span_id,) if item.source_span_id else (),
                    operation_text="",
                    capability_surface=surface,
                    capability_ref=ref,
                    boundary_status="confirmed_external",
                    identity_status="explicit_name" if ref else "described_unnamed",
                    invocation_status="unresolved",
                    capability_admission_status="confirmed_capability",
                    invocation_admission_status="no_invocation",
                    evidence=(evidence,),
                    source_section_id=item.source_section_id,
                    source_packet_id=item.source_packet_id,
                    metadata={"fallback_authority": "explicit_adapter_declaration"},
                )
            )
        if early_evidence.candidates:
            diagnostics.append(_unavailable_diagnostic(extraction, early_evidence))
        return ExternalCapabilityIntentPlanIR(
            plan_id=_plan_id(source_schema, intents, extraction.status),
            intents=tuple(sorted(intents, key=lambda item: item.intent_id)),
            dispositions=extraction.dispositions,
            candidate_resolution_map={},
            diagnostics=tuple(diagnostics),
            metadata={
                "resolver_version": "ExternalCapabilityIntentResolverV1",
                "extraction_status": "unavailable",
                "failure_reason": extraction.failure_reason or "",
                "suppressed_without_early_evidence": not bool(early_evidence.candidates),
            },
        )


def _bind_resources(
    source_span_ids: tuple[str, ...],
    source_section_id: str | None,
    source_packet_id: str | None,
    view: tuple[CapabilityDemandBindingViewIR, ...],
) -> tuple[tuple[str, ...], tuple[str, ...], str, tuple[str, ...]]:
    relevant = [
        item
        for item in view
        if item.view_status == "valid"
        and (
            bool(set(item.source_span_ids).intersection(source_span_ids))
            or (source_packet_id is not None and item.source_packet_id == source_packet_id)
            or (source_section_id is not None and item.source_section_id == source_section_id)
        )
    ]
    if not relevant:
        return (), (), "not_required", ()
    inputs = tuple(sorted({item.resource_ref for item in relevant if item.direction == "input" and item.resource_ref}))
    outputs = tuple(sorted({item.resource_ref for item in relevant if item.direction == "output" and item.resource_ref}))
    unresolved = tuple(
        sorted(
            f"{item.direction}:{item.demand_id}"
            for item in relevant
            if item.resource_ref is None and item.requiredness == "required"
        )
    )
    bound_count = sum(item.resource_ref is not None for item in relevant)
    if unresolved and bound_count:
        status = "partially_bound"
    elif unresolved:
        status = "unbound"
    else:
        status = "fully_bound"
    return inputs, outputs, status, unresolved


def _unanimous(values: Iterable[str]) -> str:
    unique = sorted(set(values))
    return unique[0] if len(unique) == 1 else "conflict"


def _grammar_safe_name(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value))


def _intent_id(
    source_schema: str,
    source_span_ids: tuple[str, ...],
    capability_surface: str | None,
    operation_text: str,
) -> str:
    stable = json.dumps(
        [
            source_schema,
            list(source_span_ids),
            normalize_surface(capability_surface or ""),
            normalize_surface(operation_text),
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return "cap_intent_" + hashlib.sha256(stable.encode("utf-8")).hexdigest()[:16]


def _plan_id(
    source_schema: str,
    intents: Iterable[ExternalCapabilityIntentIR],
    extraction_status: str,
) -> str:
    stable = json.dumps(
        [source_schema, extraction_status, sorted(item.intent_id for item in intents)],
        separators=(",", ":"),
    )
    return "cap_plan_" + hashlib.sha256(stable.encode("utf-8")).hexdigest()[:16]


def _candidate_diagnostic(intent: ExternalCapabilityIntentIR) -> CompileDiagnostic:
    return CompileDiagnostic(
        diagnostic_id=f"diag_{intent.intent_id}_candidate",
        kind="external_capability_candidate_not_admitted",
        severity="warning",
        message="External capability evidence is incomplete or conflicting; no API demand was authorized.",
        target_ref=f"capability_intent:{intent.intent_id}",
        source_span_ids=list(intent.source_span_ids),
        source_section_id=intent.source_section_id,
        source_packet_id=intent.source_packet_id,
        metadata={
            "capability_admission_status": intent.capability_admission_status,
            "invocation_admission_status": intent.invocation_admission_status,
        },
        blocks_rendering=False,
        blocks_completion=False,
    )


def _unavailable_diagnostic(
    extraction: ExternalCapabilityExtractionResult,
    early_evidence: EarlyCapabilityEvidenceView,
) -> CompileDiagnostic:
    span_ids = sorted(
        {item.source_span_id for item in early_evidence.candidates if item.source_span_id},
        key=_span_sort_key,
    )
    digest = hashlib.sha256("|".join(span_ids).encode("utf-8")).hexdigest()[:12]
    return CompileDiagnostic(
        diagnostic_id=f"diag_capability_extraction_unavailable_{digest}",
        kind="capability_intent_extraction_unavailable",
        severity="error",
        message="External capability semantic extraction was unavailable for source-backed clues.",
        target_ref="external_capability_extraction",
        source_span_ids=span_ids,
        metadata={"failure_reason": extraction.failure_reason or ""},
        blocks_rendering=True,
        blocks_completion=True,
    )


def _span_sort_key(span_id: str) -> tuple[str, int, str]:
    match = re.match(r"^(.*?)(\d+)(.*)$", span_id)
    if match is None:
        return span_id, -1, ""
    return match.group(1), int(match.group(2)), match.group(3)
