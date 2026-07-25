"""Prompt construction for Stage 6.5 condition reference extraction."""

from __future__ import annotations

import json

from nl2spl.compiler.reference_parser import ReferenceToken
from nl2spl.pipeline.stages.stage6_5_condition_reference_resolver.candidate_symbols import (
    CandidateSymbol,
    candidate_payloads,
)
from nl2spl.pipeline.stages.stage6_5_condition_reference_resolver.owner import (
    ConditionOwner,
)


def build_condition_reference_user_prompt(
    *,
    owner: ConditionOwner,
    candidates: tuple[CandidateSymbol, ...],
    explicit_tokens: tuple[ReferenceToken, ...],
    source_excerpt: str = "",
) -> str:
    """Build an owner-scoped user prompt for Stage 6.5."""
    payload = {
        "owner_ref": owner.owner_ref,
        "owner_kind": owner.owner_kind,
        "worker_id": owner.worker_id,
        "flow_ref": owner.flow_ref,
        "block_ref": owner.block_ref,
        "condition_text": owner.condition_text,
        "source_span_ids": list(owner.source_span_ids),
        "source_excerpt": source_excerpt,
        "candidate_symbols": candidate_payloads(candidates),
        "explicit_ref_tokens": [
            {
                "raw_text": token.raw_text,
                "name": token.name,
                "is_by_value": token.is_by_value,
                "top_level_name": token.top_level_name,
                "qualified_path": list(token.qualified_path),
                "start_offset": token.start_offset,
                "end_offset": token.end_offset,
            }
            for token in explicit_tokens
        ],
    }
    return (
        "Extract condition variable read references for this single condition owner.\n"
        "Use only candidate_symbols for resolved references.\n"
        "Return JSON only using the required schema.\n"
        "---\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )
