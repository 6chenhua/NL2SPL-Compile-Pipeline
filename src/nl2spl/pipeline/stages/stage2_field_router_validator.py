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

from nl2spl.compiler.annotation_role_contract.diagnostics import (
    ANNOTATION_INVALID_CONSTRUCT_TARGET_FOR_ROLE,
    ANNOTATION_INVALID_EXECUTABLE_FOR_ROLE,
    ANNOTATION_INVALID_FIELD_FOR_ROLE,
    ANNOTATION_INVALID_ROUTE_FAMILY_FOR_ROLE,
    ANNOTATION_INVALID_SLOT_TARGET_FOR_ROLE,
    ANNOTATION_MISSING_REQUIREDNESS,
    ANNOTATION_REJECTED_AFTER_ROLE_CONTRACT_VALIDATION,
    AnnotationValidationDiagnostic,
)
from nl2spl.compiler.annotation_role_contract.registry import (
    ROLE_CONTRACT_REGISTRY,
)
from nl2spl.ir.field_route_ir import RouteAnnotation
from nl2spl.pipeline.stages.stage2_field_router_prompt import (
    ALLOWED_CONSTRUCT_TARGETS,
    ALLOWED_FIELDS,
    ALLOWED_SEMANTIC_ROLES,
    ALLOWED_SLOT_TARGETS,
    NON_EXECUTABLE_ROLES,
    RefinedAnnotation,
    RouteRefinementResult,
    SplitRecommendation,
)

# _ROLE_CONTRACT removed — ARC4: validator uses ROLE_CONTRACT_REGISTRY.
# A module-level alias exists only for tests that check convergence status.
_ROLE_CONTRACT: dict[str, dict[str, Any]] = {}

_HANDLER_ACTION_VERBS: frozenset[str] = frozenset(
    {
        "ask",
        "clarify",
        "handle",
        "return",
        "notify",
        "respond",
        "reply",
        "request",
        "query",
        "prompt",
        "alert",
        "warn",
        "report",
        "log",
        "fallback",
        "default",
        "skip",
        "ignore",
        "retry",
        "abort",
    }
)


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
    structured_diagnostics: list[AnnotationValidationDiagnostic] = field(
        default_factory=list
    )
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
        structural_priors: list[Any] | None = None,
        deterministic_annotations: list[RouteAnnotation] | None = None,
    ) -> ValidatedRefinementResult:
        diagnostics: list[str] = []
        rejected: list[RejectedItem] = []
        accepted: list[RefinedAnnotation] = []
        valid_span_ids = {s.span_id for s in spans}
        span_by_id = {s.span_id: s for s in spans}

        # Build structural prior index for provenance checks
        structural_prior_by_sid: dict[str, Any] = {}
        for sp in (structural_priors or []):
            if sp.span_id not in structural_prior_by_sid:
                structural_prior_by_sid[sp.span_id] = sp

        structured_diags: list[AnnotationValidationDiagnostic] = []

        for llm_ann in llm_result.annotations:
            ok, rej_msg, warns, s_diags = self._validate_one(
                llm_ann,
                valid_span_ids,
                span_by_id,
                structural_prior_by_sid,
                canonical_input,
            )
            if ok:
                accepted.append(llm_ann)
                diagnostics.extend(warns)
            else:
                rejected.append(RejectedItem(annotation=llm_ann, reason=rej_msg))
                diagnostics.append(rej_msg)
            if s_diags:
                structured_diags.extend(s_diags)

        # Validate split recommendations
        split_recs = self._validate_split_recommendations(
            llm_result.split_recommendations,
            valid_span_ids,
            span_by_id,
            diagnostics,
        )

        return ValidatedRefinementResult(
            accepted=accepted,
            rejected=rejected,
            split_recommendations=split_recs,
            diagnostics=diagnostics,
            structured_diagnostics=structured_diags,
            fallback_triggered=False,
        )

    # ------------------------------------------------------------------
    # Single-annotation validation
    # ------------------------------------------------------------------

    def _validate_one(
        self,
        ann: RefinedAnnotation,
        valid_span_ids: set[str],
        span_by_id: dict[str, Any],
        structural_prior_by_sid: dict[str, Any],
        canonical_input: Any,
    ) -> tuple[bool, str, list[str], list[AnnotationValidationDiagnostic]]:
        """Return (accepted, rejection_reason, warnings, structured_diagnostics)."""

        def reject(
            msg: str, struct: list | None = None,
        ) -> tuple[bool, str, list[str], list]:
            return False, msg, [], struct or []

        def ok(
            warns: list[str] | None = None,
            struct_diags: list[AnnotationValidationDiagnostic] | None = None,
        ) -> tuple[bool, str, list[str], list]:
            return True, "", warns or [], struct_diags or []

        # --- 1. Span existence ------------------------------------------
        if ann.span_id not in valid_span_ids:
            return reject(f"Rejected: unknown span_id '{ann.span_id}'")

        span = span_by_id.get(ann.span_id)

        # --- 2. Allowed schema (ARC6) ------------------------------------
        # semantic_role is the PRIMARY required field.  Legacy field-only
        # annotations without semantic_role are rejected.
        if ann.semantic_role is None:
            return reject(f"Rejected: missing semantic_role for span '{ann.span_id}'")

        has_known_role = ann.semantic_role in ALLOWED_SEMANTIC_ROLES
        if not has_known_role and ann.field is not None and ann.field not in ALLOWED_FIELDS:
            return reject(f"Rejected: invalid field '{ann.field}' for span '{ann.span_id}'")
        if ann.semantic_role is not None and ann.semantic_role not in ALLOWED_SEMANTIC_ROLES:
            return reject(
                f"Rejected: invalid semantic_role '{ann.semantic_role}' for span '{ann.span_id}'"
            )
        # ARC6: Known roles with invalid construct_target/slot_target are
        # diagnosed (step 5) but NOT rejected — normalization corrects them.
        if (
            ann.construct_target is not None
            and ann.construct_target not in ALLOWED_CONSTRUCT_TARGETS
        ):
            if not has_known_role:
                return reject(
                    f"Rejected: invalid construct_target '{ann.construct_target}' "
                    f"for span '{ann.span_id}'"
                )
        if ann.slot_target is not None and ann.slot_target not in ALLOWED_SLOT_TARGETS:
            if not has_known_role:
                return reject(
                    f"Rejected: invalid slot_target '{ann.slot_target}' "
                    f"for span '{ann.span_id}'"
                )

        # --- 3. Executable is optional (ARC6: compiler fills from contract) -
        if ann.executable is not None and not isinstance(ann.executable, bool):
            return reject(f"Rejected: malformed executable for span '{ann.span_id}'")

        # --- 4. NON_EXECUTABLE_ROLES (ARC6: diagnostic, not reject) -------
        # executable mismatches for known roles are recorded as diagnostics
        # by the contract check (step 5) and corrected by normalization.
        # This gate is now a soft diagnostic for legacy non-executable
        # mismatches — the annotation is accepted with correction.

        # --- 4.5. Placeholder spans and empty markers cannot be executable roles ----------
        if span is not None:
            # Check placeholder flag
            if getattr(span, "is_placeholder", False):
                if ann.semantic_role in ("failure_mode", "constraint", "process_step"):
                    return reject(
                        f"Rejected: placeholder span '{ann.span_id}' "
                        f"('{getattr(span, 'text', '')[:60]}') cannot be annotated as "
                        f"{ann.semantic_role}"
                    )

            # Check empty marker text (additional defense for LLM path)
            span_text = getattr(span, "text", "")
            if span_text and ann.semantic_role in ("failure_mode", "constraint", "process_step"):
                import re as _re

                candidate = span_text.strip()
                candidate = _re.sub(r"^\s*[-*+]\s+", "", candidate)
                candidate = _re.sub(r"^\s*\d+\.\s+", "", candidate)
                if ":" in candidate or "：" in candidate:
                    _label, candidate = _re.split(r"[:：]", candidate, maxsplit=1)
                candidate = candidate.replace("**", "").replace("__", "")
                normalized = _re.sub(r"[^\w\s]", "", candidate.lower()).strip()
                empty_markers = {"none", "na", "n a", "not applicable", "nil", "empty"}
                if normalized in empty_markers:
                    return reject(
                        f"Rejected: empty marker span '{ann.span_id}' "
                        f"('{span_text[:60]}') cannot be annotated as {ann.semantic_role}"
                    )

        # --- 4.7. Fill provenance from span before contract check ----------
        # ARC7: typed diagnostics need source_section_id / source_packet_id
        # for provenance projection.  LLM annotations often lack these, so
        # fill from the backing span before the role-contract check runs.
        if span is not None:
            if not ann.source_section_id:
                sid = getattr(span, "source_section_id", None)
                if sid:
                    ann.source_section_id = sid
            if not ann.source_packet_id:
                pid = getattr(span, "source_packet_id", None)
                if pid:
                    ann.source_packet_id = pid

        # --- 5. Full-field role contract check (ARC4: registry-driven) --
        # Phase 1: known-role mismatches produce diagnostics, NOT rejection.
        # The merge loop's _normalize_annotation_contract will correct fields.
        registry_struct_diags: list[AnnotationValidationDiagnostic] = []
        if ann.semantic_role:
            rej, struct_diags = self._check_against_registry(ann)
            registry_struct_diags = struct_diags
            if rej:
                # Only unknown semantic_role reaches here (Phase 1 change)
                return reject(rej, struct_diags)

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
        sp = structural_prior_by_sid.get(ann.span_id)

        # Fill missing provenance from structural prior
        if not ann.source_section_id and sp and sp.source_section_id:
            ann.source_section_id = sp.source_section_id
        if not ann.source_packet_id and sp and sp.source_packet_id:
            ann.source_packet_id = sp.source_packet_id

        # Check against span provenance
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

        # Check against structural prior provenance
        if sp:
            if (
                ann.source_section_id
                and sp.source_section_id
                and ann.source_section_id != sp.source_section_id
            ):
                warns.append(
                    f"Provenance mismatch: LLM source_section_id "
                    f"'{ann.source_section_id}' != structural prior "
                    f"source_section_id '{sp.source_section_id}' "
                    f"for span '{ann.span_id}'"
                )
            if (
                ann.source_packet_id
                and sp.source_packet_id
                and ann.source_packet_id != sp.source_packet_id
            ):
                warns.append(
                    f"Provenance mismatch: LLM source_packet_id "
                    f"'{ann.source_packet_id}' != structural prior "
                    f"source_packet_id '{sp.source_packet_id}' "
                    f"for span '{ann.span_id}'"
                )

        # --- 9. Hard fact conflict (warning, not reject) -----------------
        conflict = self._hard_fact_conflict(ann, span_by_id, canonical_input)
        if conflict:
            warns.append(conflict)

        return ok(warns, struct_diags=registry_struct_diags)

    # ------------------------------------------------------------------
    # Full-field role contract check (ARC4)
    # ------------------------------------------------------------------

    @staticmethod
    def _check_against_registry(
        ann: RefinedAnnotation,
    ) -> tuple[str | None, list[AnnotationValidationDiagnostic]]:
        """Validate *ann* against the canonical role contract registry.

        Checks all five compiler-facing fields including expected ``None``.

        For **known** semantic roles, field-value mismatches produce typed
        diagnostics but do NOT cause rejection — the merge loop's normalization
        will correct them.  Only **unknown** semantic roles are rejected.

        Returns ``(rejection_reason, structured_diagnostics)``.
        For known roles, rejection_reason is always ``None``.
        """
        role = ann.semantic_role
        source_section_id = getattr(ann, "source_section_id", None)
        source_packet_id = getattr(ann, "source_packet_id", None)
        structured: list[AnnotationValidationDiagnostic] = []

        if not role:
            return None, structured

        resolved = ROLE_CONTRACT_REGISTRY.resolve_semantic_role(role)
        if resolved is None:
            return (
                f"Rejected: unknown semantic_role '{role}' "
                f"for span '{ann.span_id}'",
                structured,
            )

        contract = ROLE_CONTRACT_REGISTRY.require_role_contract(resolved)

        def _record(
            kind: str, field_name: str, expected: object, actual: object,
        ) -> None:
            """Record a typed diagnostic for a contract field mismatch.

            The annotation is NOT rejected — the merge loop's
            ``_normalize_annotation_contract`` will correct the field.
            """
            diag = AnnotationValidationDiagnostic(
                kind=kind,
                span_id=ann.span_id,
                semantic_role=resolved,
                field_name=field_name,
                expected=expected,
                actual=actual,
                source_section_id=source_section_id,
                source_packet_id=source_packet_id,
                message=(
                    f"Role contract mismatch for {resolved}: "
                    f"{field_name} is {actual!r}, "
                    f"contract requires {expected!r} "
                    f"(will be normalized by merge loop)"
                ),
            )
            structured.append(diag)

        # field — record diagnostic, do not reject known roles
        if ann.field is not None and ann.field != contract.field:
            _record(
                ANNOTATION_INVALID_FIELD_FOR_ROLE,
                "field", contract.field, ann.field,
            )

        # route_family — record diagnostic for conflicting values, not missing
        if ann.route_family is not None and ann.route_family != contract.route_family:
            _record(
                ANNOTATION_INVALID_ROUTE_FAMILY_FOR_ROLE,
                "route_family", contract.route_family, ann.route_family,
            )

        # construct_target — record diagnostic (including expected None)
        if ann.construct_target is not None and ann.construct_target != contract.construct_target:
            _record(
                ANNOTATION_INVALID_CONSTRUCT_TARGET_FOR_ROLE,
                "construct_target", contract.construct_target, ann.construct_target,
            )

        # slot_target — record diagnostic (including expected None)
        if ann.slot_target is not None and ann.slot_target != contract.slot_target:
            _record(
                ANNOTATION_INVALID_SLOT_TARGET_FOR_ROLE,
                "slot_target", contract.slot_target, ann.slot_target,
            )

        # executable — record diagnostic only when LLM provided a value
        # (minimal schema omits executable; that is correct, not a conflict)
        if ann.executable is not None and ann.executable != contract.executable:
            _record(
                ANNOTATION_INVALID_EXECUTABLE_FOR_ROLE,
                "executable", contract.executable, ann.executable,
            )

        return None, structured

    # ------------------------------------------------------------------
    # Post-enrichment requiredness finalizer (ARC4)
    # ------------------------------------------------------------------

    @staticmethod
    def finalize_requiredness(
        annotations: list[RouteAnnotation],
    ) -> tuple[list[str], list[AnnotationValidationDiagnostic]]:
        """Post-enrichment check: ensure resource contract annotations
        carry valid requiredness metadata.

        Runs AFTER ``_enrich_contract_requiredness()`` has injected
        requiredness from structural sources.  Must NOT reject annotations
        for missing requiredness before enrichment.

        Returns ``(string_diagnostics, structured_diagnostics)``.
        """
        string_diags: list[str] = []
        structured: list[AnnotationValidationDiagnostic] = []

        for ann in annotations:
            if ann.semantic_role not in ("input_contract", "output_contract"):
                continue

            rv = ann.metadata.get("requiredness")
            if rv is None:
                msg = (
                    f"Post-enrichment: span '{ann.span_id}' "
                    f"({ann.semantic_role}) has no requiredness metadata"
                )
                string_diags.append(msg)
                structured.append(
                    AnnotationValidationDiagnostic(
                        kind=ANNOTATION_MISSING_REQUIREDNESS,
                        span_id=ann.span_id,
                        semantic_role=ann.semantic_role,
                        field_name="requiredness",
                        expected="required | optional | unspecified",
                        actual=None,
                        source_section_id=ann.source_section_id,
                        source_packet_id=ann.source_packet_id,
                        message=msg,
                    )
                )
            elif rv not in ("required", "optional", "unspecified"):
                msg = (
                    f"Post-enrichment: span '{ann.span_id}' "
                    f"({ann.semantic_role}) has invalid requiredness "
                    f"value {rv!r}"
                )
                string_diags.append(msg)
                structured.append(
                    AnnotationValidationDiagnostic(
                        kind=ANNOTATION_MISSING_REQUIREDNESS,
                        span_id=ann.span_id,
                        semantic_role=ann.semantic_role,
                        field_name="requiredness",
                        expected="required | optional | unspecified",
                        actual=rv,
                        source_section_id=ann.source_section_id,
                        source_packet_id=ann.source_packet_id,
                        message=msg,
                    )
                )

        return string_diags, structured

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
                    f"Split recommendation rejected: unknown parent_span_id '{sr.parent_span_id}'"
                )
                continue

            parent_span = span_by_id.get(sr.parent_span_id)
            parent_text = getattr(parent_span, "text", "") if parent_span else ""
            valid_segments: list[dict[str, Any]] = []

            for seg in sr.segments:
                seg_text = (seg.text or "").strip()
                if not seg_text:
                    diagnostics.append(
                        f"Split segment rejected: empty text for parent '{sr.parent_span_id}'"
                    )
                    continue
                in_parent = parent_text and seg_text.lower() in parent_text.lower()
                if not in_parent:
                    diagnostics.append(
                        f"Split segment warning: segment text "
                        f"'{seg_text[:60]}' not found in parent span text "
                        f"'{parent_text[:60]}' for parent '{sr.parent_span_id}'"
                    )
                # Validate segment semantic_role against registry.
                # Unknown roles are diagnosed but the segment is NOT dropped —
                # Stage 3 will resolve and skip gracefully.
                seg_role = seg.semantic_role
                if seg_role is not None:
                    from nl2spl.compiler.annotation_role_contract.registry import (
                        ROLE_CONTRACT_REGISTRY,
                    )
                    resolved = ROLE_CONTRACT_REGISTRY.resolve_semantic_role(seg_role)
                    if resolved is None:
                        diagnostics.append(
                            f"Split segment warning: unknown semantic_role "
                            f"'{seg_role}' in segment "
                            f"'{seg_text[:60]}' for parent "
                            f"'{sr.parent_span_id}'; Stage 3 will skip "
                            f"annotation for this child."
                        )
                valid_segments.append(
                    {
                        "text": seg_text,
                        "semantic_role": seg.semantic_role,
                        "construct_target": seg.construct_target,
                        "slot_target": seg.slot_target,
                        "executable": seg.executable,
                    }
                )

            if valid_segments:
                out.append(
                    {
                        "parent_span_id": sr.parent_span_id,
                        "reason": sr.reason,
                        "segments": valid_segments,
                    }
                )
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
