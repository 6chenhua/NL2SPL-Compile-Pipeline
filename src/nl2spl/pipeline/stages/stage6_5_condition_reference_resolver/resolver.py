"""Stage 6.5 LLM-guided condition variable reference extraction."""

from __future__ import annotations

from typing import Any

from nl2spl.compiler.reference_parser import ReferenceToken, parse_description_reference_result
from nl2spl.ir.condition_variable_reference_ir import (
    ConditionVariableReferenceIR,
    ConditionVariableReferencePlan,
    build_condition_reference_id,
)
from nl2spl.ir.resource_registry_ir import ResourceRegistryIR
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.ir.worker_plan_ir import WorkerBlockPlanIR, WorkerFlowPlanIR
from nl2spl.llm.prompts import load_prompt
from nl2spl.pipeline.stages.stage6_5_condition_reference_resolver.candidate_symbols import (
    CandidateSymbol,
    build_candidate_symbol_view,
    candidate_by_name,
)
from nl2spl.pipeline.stages.stage6_5_condition_reference_resolver.diagnostics import (
    resolver_diagnostic,
)
from nl2spl.pipeline.stages.stage6_5_condition_reference_resolver.owner import (
    ConditionOwner,
    collect_condition_owners,
)
from nl2spl.pipeline.stages.stage6_5_condition_reference_resolver.prompt_builder import (
    build_condition_reference_user_prompt,
)
from nl2spl.pipeline.stages.stage6_5_condition_reference_resolver.qualified_ref import (
    qualified_ref_is_valid,
    resolve_visible_variable,
)
from nl2spl.pipeline.stages.stage6_5_condition_reference_resolver.response_parser import (
    LLMConditionReferenceCandidate,
    LLMUnresolvedConditionCandidate,
    parse_condition_reference_response,
)


class ConditionReferenceResolver:
    """Extract condition variable references and admit them deterministically."""

    def __init__(self, llm_client: Any | None = None) -> None:
        self.llm_client = llm_client

    def resolve(
        self,
        *,
        worker_flow_plan: WorkerFlowPlanIR,
        worker_block_plan: WorkerBlockPlanIR,
        symbol_table: SymbolTable,
        resource_registry: ResourceRegistryIR,
    ) -> ConditionVariableReferencePlan:
        references: list[ConditionVariableReferenceIR] = []
        diagnostics = []

        for owner in collect_condition_owners(worker_flow_plan, worker_block_plan):
            candidates = build_candidate_symbol_view(
                symbol_table,
                resource_registry,
                owner.worker_id,
            )
            parse_result = parse_description_reference_result(owner.condition_text)
            for parser_diagnostic in parse_result.diagnostics:
                diagnostics.append(
                    resolver_diagnostic(
                        diagnostic_id=f"condition_ref_parse_{len(diagnostics)}",
                        kind=parser_diagnostic.kind,
                        message=parser_diagnostic.message,
                        owner_ref=owner.owner_ref,
                        source_span_ids=owner.source_span_ids,
                        metadata={
                            "stage": "stage6_5",
                            "raw_text": parser_diagnostic.raw_text,
                            "start_offset": parser_diagnostic.start_offset,
                            "end_offset": parser_diagnostic.end_offset,
                        },
                    )
                )

            owner_refs: list[ConditionVariableReferenceIR] = []
            owner_refs.extend(
                self._explicit_references(
                    owner=owner,
                    tokens=parse_result.tokens,
                    symbol_table=symbol_table,
                    resource_registry=resource_registry,
                )
            )
            llm_refs, llm_diags = self._llm_references(
                owner=owner,
                candidates=candidates,
                explicit_tokens=parse_result.tokens,
                resource_registry=resource_registry,
            )
            owner_refs.extend(llm_refs)
            diagnostics.extend(llm_diags)

            owner_refs = _dedupe_owner_references(owner_refs)
            filtered_owner_refs = [
                ref for ref in owner_refs if not _is_anti_fabrication_reject(ref)
            ]
            references.extend(filtered_owner_refs)
            for reference in filtered_owner_refs:
                if reference.status != "resolved":
                    # S6V5: explicit missing <REF> blocks completion;
                    # LLM unresolved/rejected is report/audit only.
                    is_explicit_missing = (
                        reference.evidence_kind == "explicit_ref_token"
                        and reference.status == "unresolved"
                    )
                    diagnostics.append(
                        resolver_diagnostic(
                            diagnostic_id=f"condition_ref_{reference.reference_id}",
                            kind=_resolver_kind_for_status(reference.status),
                            message=(
                                f"Condition reference "
                                f"{reference.ref_text or reference.evidence_text or reference.proposed_symbol_text} "
                                f"is {reference.status}."
                            ),
                            owner_ref=owner.owner_ref,
                            source_span_ids=owner.source_span_ids,
                            metadata={
                                "stage": "stage6_5",
                                "reference_id": reference.reference_id,
                                "reason": reference.reason,
                                "evidence_kind": reference.evidence_kind,
                            },
                            blocks_completion=is_explicit_missing,
                        )
                    )

        return ConditionVariableReferencePlan(
            references=tuple(references),
            diagnostics=tuple(diagnostics),
            metadata={"authority": "stage6_5_condition_reference_extractor"},
        )

    def _explicit_references(
        self,
        *,
        owner: ConditionOwner,
        tokens: tuple[ReferenceToken, ...],
        symbol_table: SymbolTable,
        resource_registry: ResourceRegistryIR,
    ) -> list[ConditionVariableReferenceIR]:
        references: list[ConditionVariableReferenceIR] = []
        for index, token in enumerate(tokens):
            variable = resolve_visible_variable(
                symbol_table,
                owner.worker_id,
                token.top_level_name,
            )
            status = "resolved"
            canonical_ref = token.name
            selected_symbol = token.top_level_name
            reason = None
            if variable is None:
                status = "unresolved"
                canonical_ref = None
                selected_symbol = None
                reason = "top_level_variable_not_visible"
            elif not qualified_ref_is_valid(
                variable,
                token.qualified_path,
                resource_registry,
            ):
                status = "invalid_qualified_ref"
                reason = "qualified_field_not_defined"

            references.append(
                ConditionVariableReferenceIR(
                    reference_id=build_condition_reference_id(
                        owner.owner_ref,
                        index,
                        "explicit",
                    ),
                    owner_kind=owner.owner_kind,
                    owner_ref=owner.owner_ref,
                    condition_text=owner.condition_text,
                    ref_text=token.raw_text,
                    canonical_ref=canonical_ref,
                    top_level_name=token.top_level_name,
                    qualified_path=token.qualified_path,
                    status=status,  # type: ignore[arg-type]
                    source_span_ids=owner.source_span_ids,
                    worker_id=owner.worker_id,
                    flow_ref=owner.flow_ref,
                    block_ref=owner.block_ref,
                    evidence_kind="explicit_ref_token",
                    evidence_text=token.raw_text,
                    selected_symbol=selected_symbol,
                    confidence="high" if status == "resolved" else None,
                    reason=reason,
                )
            )
        return references

    def _llm_references(
        self,
        *,
        owner: ConditionOwner,
        candidates: tuple[CandidateSymbol, ...],
        explicit_tokens: tuple[ReferenceToken, ...],
        resource_registry: ResourceRegistryIR,
    ) -> tuple[list[ConditionVariableReferenceIR], list[Any]]:
        diagnostics: list[Any] = []
        if self.llm_client is None:
            return [], diagnostics
        if not owner.condition_text.strip():
            return [], diagnostics

        try:
            result = self.llm_client.call_json(
                stage_name="stage6_5_condition_reference",
                system_prompt=load_prompt("stage6_5_condition_reference"),
                user_prompt=build_condition_reference_user_prompt(
                    owner=owner,
                    candidates=candidates,
                    explicit_tokens=explicit_tokens,
                    source_excerpt="",
                ),
            )
            response = parse_condition_reference_response(
                result,
                expected_owner_ref=owner.owner_ref,
            )
        except Exception as exc:
            diagnostics.append(
                resolver_diagnostic(
                    diagnostic_id=f"condition_ref_llm_failed_{len(diagnostics)}",
                    kind="condition_variable_llm_extraction_failed",
                    message=f"Stage 6.5 condition-reference LLM extraction failed: {exc}",
                    owner_ref=owner.owner_ref,
                    source_span_ids=owner.source_span_ids,
                    metadata={
                        "stage": "stage6_5",
                        "reason": "llm_extraction_failed",
                    },
                )
            )
            return [], diagnostics

        references: list[ConditionVariableReferenceIR] = []
        for index, candidate in enumerate(
            sorted(response.references, key=lambda item: (item.selected_symbol, item.evidence_text))
        ):
            references.append(
                self._admit_llm_reference(
                    owner=owner,
                    candidate=candidate,
                    candidates=candidates,
                    resource_registry=resource_registry,
                    index=index,
                )
            )
        for index, unresolved in enumerate(
            sorted(
                response.unresolved_candidates,
                key=lambda item: (item.proposed_symbol_text, item.evidence_text),
            )
        ):
            references.append(
                self._unresolved_llm_reference(owner, unresolved, index)
            )
        return references, diagnostics

    def _admit_llm_reference(
        self,
        *,
        owner: ConditionOwner,
        candidate: LLMConditionReferenceCandidate,
        candidates: tuple[CandidateSymbol, ...],
        resource_registry: ResourceRegistryIR,
        index: int,
    ) -> ConditionVariableReferenceIR:
        selected = candidate_by_name(candidates, candidate.selected_symbol)
        reason = candidate.reason
        status = "resolved"
        canonical_ref = candidate.qualified_ref
        top_level_name = candidate.selected_symbol
        qualified_path = tuple(part for part in candidate.qualified_ref.split(".") if part)

        if selected is None:
            status = "rejected"
            canonical_ref = None
            top_level_name = None
            qualified_path = ()
            reason = "selected_symbol_not_in_candidate_symbols"
        elif not qualified_path or qualified_path[0] != selected.name:
            status = "rejected"
            canonical_ref = None
            top_level_name = selected.name
            reason = "qualified_ref_top_level_mismatch"
        elif candidate.evidence_text not in owner.condition_text:
            status = "rejected"
            canonical_ref = None
            reason = "evidence_text_not_source_backed"
        elif candidate.evidence_text == owner.condition_text.strip() and not (
            owner.condition_text.strip().lower() == selected.name.lower()
            or owner.condition_text.strip().lower() == selected.name.lower().replace("_", " ")
            or owner.condition_text.strip().lower() == candidate.qualified_ref.lower()
        ):
            status = "rejected"
            canonical_ref = None
            reason = "full_condition_overmatch"
        elif not evidence_text_is_direct_symbol_anchor(candidate.evidence_text, selected, candidate.qualified_ref):
            status = "rejected"
            canonical_ref = None
            reason = "direct_symbol_anchor_missing"
        elif not _candidate_qualified_ref_is_valid(selected, qualified_path, resource_registry):
            status = "invalid_qualified_ref"
            reason = "qualified_field_not_defined"

        return ConditionVariableReferenceIR(
            reference_id=build_condition_reference_id(owner.owner_ref, index, "llm"),
            owner_kind=owner.owner_kind,
            owner_ref=owner.owner_ref,
            condition_text=owner.condition_text,
            ref_text=None,
            canonical_ref=canonical_ref,
            top_level_name=top_level_name,
            qualified_path=qualified_path,
            status=status,  # type: ignore[arg-type]
            source_span_ids=owner.source_span_ids,
            worker_id=owner.worker_id,
            flow_ref=owner.flow_ref,
            block_ref=owner.block_ref,
            evidence_kind="llm_condition_semantic_match",
            evidence_text=candidate.evidence_text,
            selected_symbol=candidate.selected_symbol,
            confidence=candidate.confidence,
            reason=reason,
        )

    def _unresolved_llm_reference(
        self,
        owner: ConditionOwner,
        candidate: LLMUnresolvedConditionCandidate,
        index: int,
    ) -> ConditionVariableReferenceIR:
        return ConditionVariableReferenceIR(
            reference_id=build_condition_reference_id(owner.owner_ref, index, "unresolved"),
            owner_kind=owner.owner_kind,
            owner_ref=owner.owner_ref,
            condition_text=owner.condition_text,
            ref_text=None,
            canonical_ref=None,
            top_level_name=None,
            qualified_path=(),
            status="unresolved",
            source_span_ids=owner.source_span_ids,
            worker_id=owner.worker_id,
            flow_ref=owner.flow_ref,
            block_ref=owner.block_ref,
            evidence_kind="llm_unresolved_condition_symbol",
            evidence_text=candidate.evidence_text,
            proposed_symbol_text=candidate.proposed_symbol_text,
            reason=candidate.reason,
        )


def _candidate_qualified_ref_is_valid(
    candidate: CandidateSymbol,
    qualified_path: tuple[str, ...],
    resource_registry: ResourceRegistryIR,
) -> bool:
    if len(qualified_path) <= 1:
        return True
    if not candidate.fields:
        # Match explicit-ref behavior: unknown schemas are not rejected by
        # Stage 6.5; only known structured type definitions can invalidate a
        # field path.
        return True
    return all(part in candidate.fields for part in qualified_path[1:])


def _dedupe_owner_references(
    references: list[ConditionVariableReferenceIR],
) -> list[ConditionVariableReferenceIR]:
    result: list[ConditionVariableReferenceIR] = []
    seen: set[tuple[str, str | None, str | None]] = set()
    explicit_refs = {
        reference.canonical_ref
        for reference in references
        if reference.evidence_kind == "explicit_ref_token" and reference.canonical_ref
    }
    for reference in references:
        if (
            reference.evidence_kind == "llm_condition_semantic_match"
            and reference.canonical_ref in explicit_refs
        ):
            continue
        key = (
            reference.evidence_kind,
            reference.canonical_ref,
            reference.evidence_text or reference.ref_text or reference.proposed_symbol_text,
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(reference)
    return result


def _resolver_kind_for_status(status: str) -> str:
    if status == "unresolved":
        return "condition_variable_ref_unresolved"
    if status == "ambiguous":
        return "condition_variable_ref_ambiguous"
    if status == "invalid_qualified_ref":
        return "condition_variable_invalid_qualified_ref"
    if status == "rejected":
        return "condition_variable_llm_candidate_rejected"
    return f"condition_variable_{status}"
def evidence_text_is_direct_symbol_anchor(
    evidence_text: str,
    selected_symbol: CandidateSymbol,
    qualified_ref: str,
) -> bool:
    """Check if evidence_text is a direct textual anchor for the selected symbol."""
    et_lower = evidence_text.lower().strip()
    
    # 1. Exact variable name (e.g. "timeframe")
    if et_lower == selected_symbol.name.lower():
        return True
        
    # 2. Normalized variable name (replacing "_" with " ")
    normalized_name = selected_symbol.name.lower().replace("_", " ")
    if et_lower == normalized_name:
        return True
        
    # 3. Qualified ref (e.g. "user_request.field")
    if et_lower == qualified_ref.lower():
        return True
        
    # 4. Space-normalized qualified ref
    normalized_qualified = qualified_ref.lower().replace("_", " ")
    if et_lower == normalized_qualified:
        return True
        
    # 5. Final field segment for known structured fields
    parts = qualified_ref.split(".")
    if len(parts) > 1:
        final_segment = parts[-1].lower()
        if et_lower == final_segment:
            return True
            
    return False


def _is_anti_fabrication_reject(reference: ConditionVariableReferenceIR) -> bool:
    return (
        reference.status == "rejected"
        and reference.reason in {"direct_symbol_anchor_missing", "full_condition_overmatch"}
    )


def resolve_condition_variable_references(
    *,
    worker_flow_plan: WorkerFlowPlanIR,
    worker_block_plan: WorkerBlockPlanIR,
    symbol_table: SymbolTable,
    resource_registry: ResourceRegistryIR,
    llm_client: Any | None = None,
) -> ConditionVariableReferencePlan:
    return ConditionReferenceResolver(llm_client=llm_client).resolve(
        worker_flow_plan=worker_flow_plan,
        worker_block_plan=worker_block_plan,
        symbol_table=symbol_table,
        resource_registry=resource_registry,
    )
