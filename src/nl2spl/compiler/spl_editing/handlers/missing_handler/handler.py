"""Missing handler repair handler.

Generates ``AddExceptionHandlerStep`` suggestions for exception flows
that have a condition but no handler action.
"""

from __future__ import annotations

import json

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
from nl2spl.compiler.spl_editing.handlers.base import (
    IssueRepairHandler,
    SuggestionPolicy,
)
from nl2spl.compiler.spl_editing.handlers.llm_adapter import SuggestionLLM
from nl2spl.compiler.spl_editing.handlers.missing_handler.prompt import (
    MISSING_HANDLER_SYSTEM_PROMPT,
    build_missing_handler_user_prompt,
)
from nl2spl.compiler.spl_editing.handlers.parser import parse_suggestion_payload


class MissingHandlerRepairHandler(IssueRepairHandler):
    """Generate AddExceptionHandlerStep suggestions."""

    handler_id = "missing_handler"

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
    ) -> tuple[RepairSuggestion, ...]:
        allowed = tuple(
            pt for e in catalog_entries for pt in e.supported_patch_types
        )
        if not allowed:
            return ()

        suggestions: list[RepairSuggestion] = []
        parse_failures = 0

        for _ in range(self._policy.max_suggestions):
            raw = self._llm.generate_json(
                system_prompt=MISSING_HANDLER_SYSTEM_PROMPT,
                user_prompt=build_missing_handler_user_prompt(
                    condition_text=issue.message,
                    target_ref=issue.target_ref,
                    allowed_patch_types=allowed,
                    user_instruction=user_instruction,
                ),
            )
            try:
                data = parse_suggestion_payload(raw, allowed)
            except UnsupportedPatchTypeError:
                # LLM returned a wrong patch type — reject explicitly.
                raise
            except PatchValidationError:
                # Parse / schema error on this attempt — may retry.
                parse_failures += 1
                continue

            entry = catalog_entries[0]
            # Inject target context fields from the issue that LLM cannot know
            payload = dict(data["payload"])
            payload.setdefault("worker_id", target.worker_id or "")
            payload.setdefault("exception_flow_id",
                                self._flow_id_from_target(issue))

            suggestion = RepairSuggestion(
                suggestion_id=f"{issue.issue_id}_sug_{len(suggestions):02d}",
                session_id="",
                affordance_id=entry.affordance_id,
                title=data["title"],
                explanation=data["explanation"],
                patch=RepairPatch(
                    patch_id="",
                    affordance_id=entry.affordance_id,
                    patch_type=data["patch_type"],
                    target_ref=issue.target_ref,
                    irs_ref=issue.irs_ref,
                    base_compile_run_id="",
                    artifact_snapshot_id="",
                    overlay_version=0,
                    payload=payload,
                    verification_lane=entry.default_verification_lane,
                ),
                spl_preview=self._build_preview(data),
            )
            suggestions.append(suggestion)

        if len(suggestions) < self._policy.min_suggestions and allowed:
            fb = self._fallback_suggestion(issue, catalog_entries[0], allowed)
            if fb is not None:
                suggestions.append(fb)

        return tuple(suggestions[: self._policy.max_suggestions])

    @staticmethod
    def _flow_id_from_target(issue: EditableIssue) -> str:
        """Extract exception_flow_id from target_ref
        like ``worker:{id}.exception_flow:{fid}``."""
        ref = issue.target_ref
        marker = ".exception_flow:"
        idx = ref.find(marker)
        if idx > 0:
            return ref[idx + len(marker):]
        return ""

    @staticmethod
    def _build_preview(data: dict) -> str:
        payload = data.get("payload", {})
        cmd = payload.get("command_type", "GENERAL_COMMAND")
        text = payload.get("handler_text", "")
        inputs = ", ".join(payload.get("inputs", []))
        outputs = ", ".join(payload.get("outputs", []))
        parts = [f"[{cmd}] {text}"]
        if inputs:
            parts.append(f"  inputs: {inputs}")
        if outputs:
            parts.append(f"  outputs: {outputs}")
        return "\n".join(parts)

    @staticmethod
    def _fallback_suggestion(
        issue: EditableIssue,
        entry: RepairCatalogEntry,
        allowed_patch_types: tuple[str, ...],
    ) -> RepairSuggestion | None:
        """Produce a safe deterministic suggestion when LLM fails.

        The fallback payload MUST pass the same parser + schema
        validation as LLM output.  Returns None if validation fails
        or the allowed patch set does not include the fallback type.
        """
        import json as _json

        fallback_patch_type = "AddExceptionHandlerStep"
        if fallback_patch_type not in allowed_patch_types:
            return None

        raw = _json.dumps({
            "patch_type": fallback_patch_type,
            "title": "Add a DISPLAY_MESSAGE handler",
            "explanation": (
                "Display a message explaining the exception to the "
                "user.  This is a safe deterministic fallback."
            ),
            "payload": {
                "handler_text": "Display exception explanation to user.",
                "command_type": "DISPLAY_MESSAGE",
                "inputs": [],
                "outputs": [],
            },
        })

        data = parse_suggestion_payload(raw, allowed_patch_types)

        return RepairSuggestion(
            suggestion_id=f"{issue.issue_id}_sug_fallback",
            session_id="",
            affordance_id=entry.affordance_id,
            title=data["title"],
            explanation=data["explanation"],
            patch=RepairPatch(
                patch_id="",
                affordance_id=entry.affordance_id,
                patch_type=data["patch_type"],
                target_ref=issue.target_ref,
                irs_ref=issue.irs_ref,
                base_compile_run_id="",
                artifact_snapshot_id="",
                overlay_version=0,
                payload=data["payload"],
                verification_lane=entry.default_verification_lane,
            ),
            spl_preview=MissingHandlerRepairHandler._build_preview(data),
        )
