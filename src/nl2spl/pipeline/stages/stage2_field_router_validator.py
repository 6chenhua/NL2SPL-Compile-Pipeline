"""Standalone validator for adapter-guided FieldRoute LLM refinement output.

No LLM calls.  No pipeline dependencies beyond IR types and allowed-schema
constants.  Validates every LLM annotation against:

- Span existence
- Allowed schema (field, role, construct, slot)
- Executable constraints
- Role-specific contracts
- Anti-fabrication rules
- Provenance alignment (LLM provenance must match span/prior)
- Hard-fact conflict detection (diagnostic only)
- Split recommendation sanity
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from nl2spl.ir.field_route_ir import RouteAnnotation
from nl2spl.pipeline.stages.stage2_field_router_prompt import (
    ALLOWED_CONSTRUCT_TARGETS,
    ALLOWED_FIELDS,
    ALLOWED_SEMANTIC_ROLES,
    ALLOWED_SLOT_TARGETS,
    EXECUTABLE_ROLES,
    NON_EXECUTABLE_ROLES,
    RefinedAnnotation,
    SplitRecommendation,
    RouteRefinementResult,
)


# ===========================================================================
# Role-specific contracts
# ===========================================================================

_ROLE_CONTRACT: dict[str, dict[str, Any]] = {
    "failure_mode": {
        "construct_target": "EXCEPTION_FLOW",
        "slot_target": "condition",
        "executable": False,
    },
    "exception_handler_action": {
        "construct_target": "EXCEPTION_FLOW",
        "slot_target": "handler",
        "executable": True,
    },
    "input_contract": {"executable": False},
    "output_contract": {"executable": False},
    "delegation_intent": {"executable": False},
    "delegation_boundary_constraint": {"executable": False},
    "delegation_prohibition": {"executable": False},
    "api_candidate": {"executable": False},
    "worker_handoff_candidate": {"executable": False},
    "constraint": {"executable": False},
    "profile_domain": {"executable": False},
    "handoff_condition": {"executable": False},
    "integration_hint": {"executable": False},
}

_HANDLER_ACTION_VERBS: frozenset[str] = frozenset({
    "ask", "clarify", "handle", "return", "notify", "respond", "reply",
    "request", "query", "prompt", "alert", "warn", "report", "log",
    "fallback", "default", "skip", "ignore", "retry", "abort",
})


# ===========================================================================
# Output types
# ===========================================================================


@dataclass
class RejectedItem:
    annotation: RefinedAnnotation
    reason: str


@dataclass
class ValidatedRefinementResult:
    accepted: list[RefinedAnnotation] = field(default_factory=list)
    rejected: list[RejectedItem] = field(default_factory=list)
    split_recommendations: list[dict[str, Any]] = field(default_factory=list)
    diagnostics: list[str] = field(default_factory=list)
    fallback_triggered: bool = False


# ===========================================================================
# Validator
# ===========================================================================


class RouteRefinementValidator:

    def validate(
        self,
        llm_result: RouteRefinementResult,
        spans: list[Any],
        canonical_input: Any,
        priors: list[RouteAnnotation],
    ) -> ValidatedRefinementResult:
        diagnostics: list[str] = []
        rejected: list[RejectedItem] = []
        accepted: list[RefinedAnnotation] = []
        valid_span_ids = {s.span_id for s in spans}
        span_by_id = {s.span_id: s for s in spans}
        prior_by_sid: dict[str, RouteAnnotation] = {}
        for p in priors:
            if p.span_id not in prior_by_sid:
                prior_by_sid[p.span_id] = p

        for llm_ann in llm_result.annotations:
            ok, rej_msg, warns = self._validate_one(
                llm_ann, valid_span_ids, span_by_id, prior_by_sid, canonical_input,
            )
            if ok:
                accepted.append(llm_ann)
                diagnostics.extend(warns)
            else:
                rejected.append(RejectedItem(annotation=llm_ann, reason=rej_msg))
                diagnostics.append(rej_msg)

        # Fallback if > 50 % rejected
        total = len(llm_result.annotations)
        fallback = total > 0 and len(rejected) > total / 2
        if fallback:
            diagnostics.append(
                f"LLM refinement fallback triggered: {len(rejected)}/{total} "
                f"annotations rejected.  Using deterministic priors."
            )

        # Validate split recommendations
        split_recs = self._validate_split_recommendations(
            llm_result.split_recommendations, valid_span_ids, span_by_id, diagnostics,
        )

        return ValidatedRefinementResult(
            accepted=accepted,
            rejected=rejected,
            split_recommendations=split_recs,
            diagnostics=diagnostics,
            fallback_triggered=fallback,
        )

    # ------------------------------------------------------------------
    # Single-annotation validation
    # ------------------------------------------------------------------

    def _validate_one(
        self,
        ann: RefinedAnnotation,
        valid_span_ids: set[str],
        span_by_id: dict[str, Any],
        prior_by_sid: dict[str, RouteAnnotation],
        canonical_input: Any,
    ) -> tuple[bool, str, list[str]]:
        """Return (accepted, rejection_reason, warnings)."""

        def reject(msg: str) -> tuple[bool, str, list[str]]:
            return False, msg, []

        def ok(warns: list[str] | None = None) -> tuple[bool, str, list[str]]:
            return True, "", warns or []

        # --- 1. Span existence ------------------------------------------
        if ann.span_id not in valid_span_ids:
            return reject(f"Rejected: unknown span_id '{ann.span_id}'")

        span = span_by_id.get(ann.span_id)
        prior = prior_by_sid.get(ann.span_id)

        # --- 2. Allowed schema ------------------------------------------
        if ann.field is None or ann.field not in ALLOWED_FIELDS:
            return reject(
                f"Rejected: invalid field '{ann.field}' for span '{ann.span_id}'"
            )
        if ann.semantic_role is not None and ann.semantic_role not in ALLOWED_SEMANTIC_ROLES:
            return reject(
                f"Rejected: invalid semantic_role '{ann.semantic_role}' "
                f"for span '{ann.span_id}'"
            )
        if ann.construct_target is not None and ann.construct_target not in ALLOWED_CONSTRUCT_TARGETS:
            return reject(
                f"Rejected: invalid construct_target '{ann.construct_target}' "
                f"for span '{ann.span_id}'"
            )
        if ann.slot_target is not None and ann.slot_target not in ALLOWED_SLOT_TARGETS:
            return reject(
                f"Rejected: invalid slot_target '{ann.slot_target}' "
                f"for span '{ann.span_id}'"
            )

        # --- 3. Executable must be a bool -------------------------------
        if not isinstance(ann.executable, bool):
            return reject(
                f"Rejected: missing or malformed executable for span '{ann.span_id}'"
            )

        # --- 4. NON_EXECUTABLE_ROLES ------------------------------------
        if ann.semantic_role and ann.semantic_role in NON_EXECUTABLE_ROLES:
            if ann.executable:
                return reject(
                    f"Rejected: {ann.semantic_role} must be non-executable "
                    f"for span '{ann.span_id}'"
                )

        # --- 5. Role-specific contract ----------------------------------
        contract = _ROLE_CONTRACT.get(ann.semantic_role or "")
        if contract:
            exp_ct = contract.get("construct_target")
            if exp_ct is not None and ann.construct_target != exp_ct:
                return reject(
                    f"Rejected: {ann.semantic_role} requires "
                    f"construct_target='{exp_ct}', got '{ann.construct_target}' "
                    f"for span '{ann.span_id}'"
                )
            exp_st = contract.get("slot_target")
            if exp_st is not None and ann.slot_target != exp_st:
                return reject(
                    f"Rejected: {ann.semantic_role} requires "
                    f"slot_target='{exp_st}', got '{ann.slot_target}' "
                    f"for span '{ann.span_id}'"
                )
            exp_ex = contract.get("executable")
            if exp_ex is not None and ann.executable != exp_ex:
                return reject(
                    f"Rejected: {ann.semantic_role} requires "
                    f"executable={exp_ex}, got {ann.executable} "
                    f"for span '{ann.span_id}'"
                )

        # --- 6. Anti-fabrication: handler must have source text ----------
        if ann.semantic_role == "exception_handler_action":
            if span is not None:
                span_text = getattr(span, "text", "").lower()
                if not any(v in span_text for v in _HANDLER_ACTION_VERBS):
                    return reject(
                        f"Rejected: exception_handler_action for span "
                        f"'{ann.span_id}' has no handler action verb in "
                        f"source text '{getattr(span, 'text', '')[:80]}'"
                    )

        # --- 7. Anti-fabrication: worker / API must be in source --------
        if ann.semantic_role == "worker_handoff_candidate":
            st = getattr(span, "text", "").lower() if span else ""
            if not self._worker_mentioned(st, canonical_input):
                return reject(
                    f"Rejected: worker_handoff_candidate for span "
                    f"'{ann.span_id}' — no worker named in span text "
                    f"or delegation intents"
                )

        if ann.semantic_role == "api_candidate":
            st = getattr(span, "text", "").lower() if span else ""
            if not self._api_mentioned(st):
                return reject(
                    f"Rejected: api_candidate for span "
                    f"'{ann.span_id}' — no API-like name in span text"
                )

        # --- 8. Provenance alignment (warning, not reject) ---------------
        warns: list[str] = []
        if ann.source_section_id and span is not None:
            span_sid = getattr(span, "source_section_id", None)
            if span_sid and ann.source_section_id != span_sid:
                warns.append(
                    f"Provenance mismatch: LLM source_section_id "
                    f"'{ann.source_section_id}' != span source_section_id "
                    f"'{span_sid}' for span '{ann.span_id}'"
                )
        if ann.source_packet_id and span is not None:
            span_pid = getattr(span, "source_packet_id", None)
            if span_pid and ann.source_packet_id != span_pid:
                warns.append(
                    f"Provenance mismatch: LLM source_packet_id "
                    f"'{ann.source_packet_id}' != span source_packet_id "
                    f"'{span_pid}' for span '{ann.span_id}'"
                )

        # --- 9. Hard fact conflict (warning, not reject) -----------------
        conflict = self._hard_fact_conflict(ann, span_by_id, canonical_input)
        if conflict:
            warns.append(conflict)

        return ok(warns)

    # ------------------------------------------------------------------
    # Split recommendation validation
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_split_recommendations(
        split_recs: list[SplitRecommendation],
        valid_span_ids: set[str],
        span_by_id: dict[str, Any],
        diagnostics: list[str],
    ) -> list[dict[str, Any]]:
        """Validate split recommendations; reject invalid ones."""
        out: list[dict[str, Any]] = []
        for sr in split_recs:
            # parent_span_id must exist
            if sr.parent_span_id not in valid_span_ids:
                diagnostics.append(
                    f"Split recommendation rejected: unknown parent_span_id "
                    f"'{sr.parent_span_id}'"
                )
                continue

            parent_span = span_by_id.get(sr.parent_span_id)
            parent_text = getattr(parent_span, "text", "") if parent_span else ""
            valid_segments: list[dict[str, Any]] = []

            for seg in sr.segments:
                seg_text = (seg.text or "").strip()
                if not seg_text:
                    diagnostics.append(
                        f"Split segment rejected: empty text for "
                        f"parent '{sr.parent_span_id}'"
                    )
                    continue
                in_parent = parent_text and seg_text.lower() in parent_text.lower()
                if not in_parent:
                    diagnostics.append(
                        f"Split segment warning: segment text "
                        f"'{seg_text[:60]}' not found in parent span text "
                        f"'{parent_text[:60]}' for parent '{sr.parent_span_id}'"
                    )
                valid_segments.append({
                    "text": seg_text,
                    "semantic_role": seg.semantic_role,
                    "construct_target": seg.construct_target,
                    "slot_target": seg.slot_target,
                    "executable": seg.executable,
                })

            if valid_segments:
                out.append({
                    "parent_span_id": sr.parent_span_id,
                    "reason": sr.reason,
                    "segments": valid_segments,
                })
            else:
                diagnostics.append(
                    f"Split recommendation dropped: no valid segments "
                    f"for parent '{sr.parent_span_id}'"
                )
        return out

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _worker_mentioned(span_text: str, canonical_input: Any) -> bool:
        if hasattr(canonical_input, "hard_facts") and canonical_input.hard_facts:
            for di in getattr(canonical_input.hard_facts, "delegation_intents", []):
                name = getattr(di, "name", "")
                if name and name.lower() in span_text:
                    return True
                tv = getattr(di, "text", "")
                if tv and tv.lower() in span_text:
                    return True
        return any(s in span_text.lower() for s in ("worker", "service", "agent"))

    @staticmethod
    def _api_mentioned(span_text: str) -> bool:
        return any(s in span_text.lower() for s in ("api", "endpoint", "service", "search"))

    @staticmethod
    def _hard_fact_conflict(
        ann: RefinedAnnotation,
        span_by_id: dict[str, Any],
        canonical_input: Any,
    ) -> str | None:
        span = span_by_id.get(ann.span_id)
        if span is None:
            return None
        source_pid = getattr(span, "source_packet_id", None) or ann.source_packet_id
        if not source_pid:
            return None
        if canonical_input is None:
            return None
        if not hasattr(canonical_input, "hard_facts") or canonical_input.hard_facts is None:
            return None
        hf = canonical_input.hard_facts

        for fm in getattr(hf, "failure_modes", []):
            fm_pid = None
            if hasattr(fm, "evidence") and fm.evidence:
                for ev in fm.evidence:
                    if getattr(ev, "source_packet_id", None) == source_pid:
                        fm_pid = source_pid
                        break
            if fm_pid and ann.semantic_role not in (
                "failure_mode", "exception_handler_action", None,
            ):
                return (
                    f"Hard fact conflict: span '{ann.span_id}' packet "
                    f"'{source_pid}' has failure_mode hard fact but LLM "
                    f"returned semantic_role='{ann.semantic_role}'"
                )

        for di in getattr(hf, "delegation_intents", []):
            di_pid = None
            if hasattr(di, "evidence") and di.evidence:
                for ev in di.evidence:
                    if getattr(ev, "source_packet_id", None) == source_pid:
                        di_pid = source_pid
                        break
            if di_pid and ann.executable:
                return (
                    f"Hard fact conflict: span '{ann.span_id}' packet "
                    f"'{source_pid}' has delegation_intent hard fact but "
                    f"LLM returned executable=True"
                )
        return None
