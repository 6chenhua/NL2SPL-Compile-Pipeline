"""Missing output producer repair handler."""

from __future__ import annotations

import json

from nl2spl.compiler.spl_editing.core.catalog import RepairCatalogEntry
from nl2spl.compiler.spl_editing.core.errors import UnsupportedPatchTypeError
from nl2spl.compiler.spl_editing.core.model import (
    EditableIssue, RepairContext, RepairPatch, RepairSuggestion, RepairTarget,
)
from nl2spl.compiler.spl_editing.handlers.base import IssueRepairHandler, SuggestionPolicy
from nl2spl.compiler.spl_editing.handlers.missing_output_producer.prompt import (
    MISSING_OUTPUT_SYSTEM_PROMPT, build_missing_output_user_prompt,
)
from nl2spl.compiler.spl_editing.handlers.parser import parse_suggestion_payload


_JSON_RESPONSE = json.dumps


class MissingOutputProducerHandler(IssueRepairHandler):
    handler_id = "missing_output_producer"

    def __init__(self, policy: SuggestionPolicy | None = None) -> None:
        self._policy = policy or SuggestionPolicy()

    @property
    def policy(self) -> SuggestionPolicy:
        return self._policy

    def generate_suggestions(
        self, issue: EditableIssue, target: RepairTarget,
        context: RepairContext,
        catalog_entries: tuple[RepairCatalogEntry, ...],
        user_instruction: str | None = None,
    ) -> tuple[RepairSuggestion, ...]:
        allowed = tuple(pt for e in catalog_entries for pt in e.supported_patch_types)
        if not allowed:
            return ()

        entry = catalog_entries[0]
        output_name = self._output_name_from_target(issue)
        # Return a deterministic stub suggestion for each allowed patch type
        suggestions: list[RepairSuggestion] = []
        for i, pt in enumerate(allowed[: self._policy.max_suggestions]):
            payload = self._payload_for(pt, issue, target, context)
            if payload is None:
                continue
            preview = (
                f"Bind existing step '{payload.get('step_id', '?')}' "
                f"as producer of '{output_name}'"
                if pt == "BindExistingProducerStep"
                else f"[{payload.get('command_type', 'GENERAL_COMMAND')}] "
                     f"{payload.get('producer_text', 'Produce output.')}"
            )
            suggestions.append(RepairSuggestion(
                suggestion_id=f"{issue.issue_id}_sug_{i:02d}",
                session_id="",
                affordance_id=entry.affordance_id,
                title=f"Add producer step for '{output_name}'",
                explanation=f"Create a {pt} to produce the required output.",
                patch=RepairPatch(
                    patch_id="", affordance_id=entry.affordance_id,
                    patch_type=pt, target_ref=issue.target_ref,
                    irs_ref=issue.irs_ref,
                    base_compile_run_id="", artifact_snapshot_id="",
                    overlay_version=0, payload=payload,
                    verification_lane=entry.default_verification_lane,
                ),
                spl_preview=preview,
            ))
        return tuple(suggestions)

    @staticmethod
    def _output_name_from_target(issue) -> str:
        """Extract the real output name from target_ref
        like ``worker:{id}.output:{name}``."""
        ref = issue.target_ref
        marker = ".output:"
        idx = ref.find(marker)
        if idx > 0:
            return ref[idx + len(marker):]
        return issue.missing_slot or "unknown_output"

    @staticmethod
    def _payload_for(pt: str, issue, target, context):
        output_name = MissingOutputProducerHandler._output_name_from_target(issue)
        if pt == "InsertProducerStep":
            return {
                "worker_id": target.worker_id or "",
                "output_name": output_name,
                "producer_text": "Produce the required output.",
                "command_type": "GENERAL_COMMAND",
            }
        if pt == "BindExistingProducerStep":
            # Select the first renderable existing step from context
            candidate = MissingOutputProducerHandler._find_bindable_step(context)
            if candidate is None:
                return None
            return {
                "worker_id": target.worker_id or "",
                "step_id": candidate.step_id,
                "output_name": output_name,
                "binding_text": f"Bind step '{candidate.step_id}' as producer of '{output_name}'.",
            }
        return None

    @staticmethod
    def _find_bindable_step(context):
        """Find a renderable existing step that can be bound as producer."""
        steps = context.related_steps
        if not steps:
            return None
        for step in steps:
            if step.source_span_ids or step.metadata.get("origin") == "user_confirmed_repair":
                return step
        return None
