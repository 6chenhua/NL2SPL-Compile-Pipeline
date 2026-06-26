"""Missing output producer repair handler.

R6: InsertProducerStep goes through the intent path (ConstructRepairIntent).
Insert NEVER falls back to dict payload — missing refset/catalog/policy
results in generation_blocked, not silent degradation.
"""

from __future__ import annotations

import json
from dataclasses import replace
from typing import Any

from nl2spl.compiler.spl_editing.core.catalog import RepairCatalogEntry
from nl2spl.compiler.spl_editing.core.errors import (
    PatchValidationError,
    UnsupportedPatchTypeError,
)
from nl2spl.compiler.spl_editing.core.model import (
    EditableIssue,
    RepairContext,
    RepairPatch,
    RepairSuggestion,
    RepairTarget,
)
from nl2spl.compiler.spl_editing.handlers.base import IssueRepairHandler, SuggestionPolicy
from nl2spl.compiler.spl_editing.handlers.llm_adapter import SuggestionLLM
from nl2spl.compiler.spl_editing.handlers.missing_output_producer.prompt import (
    INSERT_PRODUCER_SYSTEM_PROMPT,
    build_missing_output_user_prompt,
)
from nl2spl.compiler.spl_editing.handlers.parser import (
    parse_suggestion_envelope,
)
from nl2spl.compiler.spl_editing.intent import (
    IntentValidator,
    parse_raw_intent,
)


class MissingOutputProducerHandler(IssueRepairHandler):
    handler_id = "missing_output_producer"

    def __init__(
        self,
        llm: SuggestionLLM,
        policy: SuggestionPolicy | None = None,
    ) -> None:
        self._llm = llm
        self._policy = policy or SuggestionPolicy()

    @property
    def policy(self) -> SuggestionPolicy:
        return self._policy

    def generate_suggestions(
        self,
        issue: EditableIssue,
        target: RepairTarget,
        context: RepairContext,
        catalog_entries: tuple[RepairCatalogEntry, ...],
        user_instruction: str | None = None,
        selected_patch_types: tuple[str, ...] | None = None,
        *,
        rendered_user_prompt: str | None = None,
        selectable_refset: Any | None = None,
        catalog_entry: Any | None = None,
    ) -> tuple[RepairSuggestion, ...]:
        allowed = tuple(pt for e in catalog_entries for pt in e.supported_patch_types)
        if selected_patch_types:
            allowed = tuple(pt for pt in allowed if pt in selected_patch_types)
        if not allowed:
            return ()

        entry = catalog_entry or catalog_entries[0]
        output_name = self._output_name_from_target(issue)
        suggestions: list[RepairSuggestion] = []
        parse_failures = 0
        previous_summaries: list[str] = []
        previous_payloads: list[Any] = []
        max_attempts = self._policy.max_suggestions * self._policy.max_attempts_ratio

        patch_type_sequence = [allowed[i % len(allowed)] for i in range(max_attempts)]

        for allowed_patch_type in patch_type_sequence:
            if len(suggestions) >= self._policy.max_suggestions:
                break

            # ── InsertProducerStep: intent path (R6) ─────────────────────
            if allowed_patch_type == "InsertProducerStep":
                suggestions_from_insert = self._try_insert_intent(
                    issue=issue,
                    target=target,
                    output_name=output_name,
                    entry=entry,
                    selectable_refset=selectable_refset,
                    user_instruction=user_instruction,
                    previous_summaries=previous_summaries,
                    previous_payloads=previous_payloads,
                    rendered_user_prompt=rendered_user_prompt,
                )
                for sug in suggestions_from_insert:
                    if len(suggestions) >= self._policy.max_suggestions:
                        break
                    suggestions.append(sug)
                    previous_summaries.append(f"{sug.title}: {sug.explanation}")
                if suggestions_from_insert:
                    continue
                parse_failures += 1
                continue

            # ── Unknown / future patch types ─────────────────────────────
            else:
                parse_failures += 1
                continue

        if len(suggestions) < self._policy.max_suggestions:
            raise PatchValidationError(
                "LLM did not produce a valid missing_output_producer "
                f"suggestion set ({len(suggestions)} unique suggestions, "
                f"expected {self._policy.max_suggestions}; "
                f"{parse_failures} parse/schema/duplicate failures)."
            )
        return tuple(suggestions)

    # ── InsertProducerStep intent path (R6) ─────────────────────────────

    def _try_insert_intent(
        self,
        *,
        issue: EditableIssue,
        target: RepairTarget,
        output_name: str,
        entry: RepairCatalogEntry,
        selectable_refset: Any,
        user_instruction: str | None,
        previous_summaries: list[str],
        previous_payloads: list[Any],
        rendered_user_prompt: str | None,
    ) -> list[RepairSuggestion]:
        """Attempt one InsertProducerStep via the intent path.

        Returns an empty list on any failure — NEVER falls back to dict
        payload.
        """
        # ── Hard requirement: refset + catalog must be available ─────
        if selectable_refset is None:
            return []
        if not selectable_refset.is_available:
            return []
        if (
            entry.selectable_ref_policy_id
            and entry.selectable_ref_policy_id != selectable_refset.policy_id
        ):
            return []

        # ── Call LLM with intent-aware prompt ─────────────────────────
        raw = self._llm.generate_json(
            system_prompt=INSERT_PRODUCER_SYSTEM_PROMPT,
            user_prompt=rendered_user_prompt
            or build_missing_output_user_prompt(
                output_name=output_name,
                target_ref=issue.target_ref,
                allowed_patch_types=("InsertProducerStep",),
                user_instruction=user_instruction,
                previous_suggestions=tuple(previous_summaries),
            ),
        )

        # ── Parse envelope ────────────────────────────────────────────
        try:
            envelope = parse_suggestion_envelope(raw, ("InsertProducerStep",))
        except (PatchValidationError, UnsupportedPatchTypeError):
            return []

        # ── Route inner payload to intent parser ──────────────────────
        intent_json = json.dumps({"payload": envelope.raw_payload})
        parse_result = parse_raw_intent(
            raw_json=intent_json,
            issue_id=issue.issue_id,
            patch_type="InsertProducerStep",
            affordance_id=entry.affordance_id,
        )
        if not parse_result.is_success or parse_result.intent is None:
            return []

        intent = parse_result.intent

        # ── Server authority override ─────────────────────────────────
        intent = replace(
            intent,
            affordance_id=entry.affordance_id,
            patch_type="InsertProducerStep",
            target_construct_type=entry.construct_type,
            target_construct_id=issue.irs_ref.construct_id,
            target_slot_name=entry.slot_name,
            materialization_plan_id=entry.materialization_plan_id,
        )

        # ── Validate against refset + catalog ─────────────────────────
        val_result = IntentValidator.validate(intent, selectable_refset, entry)
        if not val_result.is_success:
            return []

        # ── Deduplicate ────────────────────────────────────────────────
        if intent in previous_payloads:
            return []

        preview = (
            f"[GENERAL_COMMAND] {intent.repair_goal or intent.intent_summary or 'Produce output.'}"
        )
        suggestion = RepairSuggestion(
            suggestion_id=f"{issue.issue_id}_sug_{len(previous_payloads):02d}",
            session_id="",
            affordance_id=entry.affordance_id,
            title=envelope.title,
            explanation=envelope.explanation,
            patch=RepairPatch(
                patch_id="",
                affordance_id=entry.affordance_id,
                patch_type="InsertProducerStep",
                target_ref=issue.target_ref,
                irs_ref=issue.irs_ref,
                base_compile_run_id="",
                artifact_snapshot_id="",
                overlay_version=0,
                payload=intent,  # ConstructRepairIntent — not dict
                verification_lane=entry.default_verification_lane,
            ),
            spl_preview=preview,
        )
        return [suggestion]

    # ── Helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _output_name_from_target(issue) -> str:
        ref = issue.target_ref
        marker = ".output:"
        idx = ref.find(marker)
        if idx > 0:
            return ref[idx + len(marker) :]
        return issue.missing_slot or "unknown_output"


