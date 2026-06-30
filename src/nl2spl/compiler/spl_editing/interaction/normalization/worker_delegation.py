"""Normalize validated Worker Delegation drafts into sealed directives."""

from __future__ import annotations

import hashlib
import json

from nl2spl.compiler.spl_editing.interaction.model import (
    InvocationTimingDraft,
    NormalizedResultUsage,
    NormalizedWorkerDelegationDirective,
)
from nl2spl.compiler.spl_editing.selectable_refs.model import ResolvedSelectableRef


def normalize_worker_delegation_directive(
    draft,
    *,
    target_ref: str,
    refset,
    admitted_outputs,
) -> NormalizedWorkerDelegationDirective:
    selected = tuple(_resolved(refset.get_ref(ref_id)) for ref_id in draft.selected_input_ref_ids)
    placement = None
    timing = draft.invocation_timing or InvocationTimingDraft("append")
    if timing.placement_ref_id:
        placement = _resolved(refset.get_ref(timing.placement_ref_id))
    outputs_by_local = {
        declaration.local_id: admitted
        for declaration, admitted in zip(draft.returned_results, admitted_outputs, strict=True)
    }
    usage = []
    for item in draft.result_usage:
        admitted = outputs_by_local[item.output_local_id]
        parent_ref = _resolved(refset.get_ref(item.parent_ref_id)) if item.parent_ref_id else None
        temporary = (
            f"tmp_{admitted.canonical_name}_{draft.draft_id[-8:]}"
            if item.create_parent_local_temporary
            else None
        )
        usage.append(NormalizedResultUsage(admitted.output_id, parent_ref, temporary))
    responsibility = draft.delegated_responsibility.text
    payload = {
        "draft": draft.draft_id,
        "target": target_ref,
        "responsibility": responsibility,
        "refs": [item.ref.ref_id for item in selected],
        "outputs": [item.output_id for item in admitted_outputs],
        "timing": timing.placement_mode,
        "placement": timing.placement_ref_id,
        "usage": [(item.output_id, item.parent_temporary_name) for item in usage],
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return NormalizedWorkerDelegationDirective(
        directive_id=f"directive_{digest[:20]}",
        strategy_id=draft.strategy_id,
        option_id=draft.option_id,
        target_ref=target_ref,
        base_revision=draft.base_revision,
        delegated_responsibility=responsibility,
        selected_input_refs=selected,
        admitted_outputs=admitted_outputs,
        invocation_timing=timing,
        placement_ref=placement,
        result_usage=tuple(usage),
        additional_instruction=draft.additional_instruction,
        input_contract_hash=digest,
    )


def _resolved(ref):
    if ref is None:
        raise ValueError("Validated ref disappeared during normalization")
    return ResolvedSelectableRef(ref=ref, resolved_role=ref.ref_role, scope_matched=True)
