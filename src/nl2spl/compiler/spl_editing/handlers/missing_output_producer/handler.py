"""Missing output producer repair handler."""

from __future__ import annotations

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
    MISSING_OUTPUT_SYSTEM_PROMPT,
    build_missing_output_user_prompt,
)
from nl2spl.compiler.spl_editing.handlers.parser import parse_suggestion_payload


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
        self, issue: EditableIssue, target: RepairTarget,
        context: RepairContext,
        catalog_entries: tuple[RepairCatalogEntry, ...],
        user_instruction: str | None = None,
        selected_patch_types: tuple[str, ...] | None = None,
        *,
        rendered_user_prompt: str | None = None,
    ) -> tuple[RepairSuggestion, ...]:
        allowed = tuple(pt for e in catalog_entries for pt in e.supported_patch_types)
        if selected_patch_types:
            allowed = tuple(pt for pt in allowed if pt in selected_patch_types)
        if not allowed:
            return ()

        entry = catalog_entries[0]
        output_name = self._output_name_from_target(issue)
        suggestions: list[RepairSuggestion] = []
        parse_failures = 0
        previous_summaries: list[str] = []
        previous_payloads: list[dict] = []
        max_attempts = self._policy.max_suggestions * self._policy.max_attempts_ratio
        bindable_step_ids = tuple(
            step.step_id for step in self._bindable_steps(context)
        )

        # Build ordered sequence of patch types to try.
        # Focused: all attempts on selected type(s).
        # Unfiltered: round-robin to cover every supported type.
        patch_type_sequence = [
            allowed[i % len(allowed)]
            for i in range(max_attempts)
        ]

        for allowed_patch_type in patch_type_sequence:
            if len(suggestions) >= self._policy.max_suggestions:
                break
            if (
                allowed_patch_type == "BindExistingProducerStep"
                and self._find_bindable_step(context) is None
            ):
                continue
            raw = self._llm.generate_json(
                system_prompt=MISSING_OUTPUT_SYSTEM_PROMPT,
                user_prompt=build_missing_output_user_prompt(
                    output_name=output_name,
                    target_ref=issue.target_ref,
                    allowed_patch_types=(allowed_patch_type,),
                    user_instruction=user_instruction,
                    previous_suggestions=tuple(previous_summaries),
                    bindable_step_ids=bindable_step_ids,
                ),
            )
            try:
                data = parse_suggestion_payload(raw, (allowed_patch_type,))
            except UnsupportedPatchTypeError:
                raise
            except PatchValidationError:
                parse_failures += 1
                continue

            pt = data["patch_type"]
            payload = self._payload_for(
                pt, issue, target, context, data["payload"],
            )
            if payload is None:
                parse_failures += 1
                continue

            # Skip duplicate payloads
            if payload in previous_payloads:
                parse_failures += 1
                continue

            previous_summaries.append(
                f"{data['title']}: {data['explanation']}"
            )
            previous_payloads.append(payload)
            preview = (
                f"Bind existing step '{payload.get('step_id', '?')}' "
                f"as producer of '{output_name}'"
                if pt == "BindExistingProducerStep"
                else f"[{payload.get('command_type', 'GENERAL_COMMAND')}] "
                     f"{payload.get('producer_text', 'Produce output.')}"
            )
            suggestions.append(RepairSuggestion(
                suggestion_id=f"{issue.issue_id}_sug_{len(suggestions):02d}",
                session_id="",
                affordance_id=entry.affordance_id,
                title=data["title"],
                explanation=data["explanation"],
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
        if len(suggestions) < self._policy.max_suggestions:
            raise PatchValidationError(
                "LLM did not produce a valid missing_output_producer "
                f"suggestion set ({len(suggestions)} unique suggestions, "
                f"expected {self._policy.max_suggestions}; "
                f"{parse_failures} parse/schema/duplicate failures)."
            )
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
    def _payload_for(pt: str, issue, target, context, llm_payload):
        output_name = MissingOutputProducerHandler._output_name_from_target(issue)
        if pt == "InsertProducerStep":
            producer_text = llm_payload.get("producer_text") or llm_payload.get("handler_text")
            command_type = llm_payload.get("command_type", "GENERAL_COMMAND")
            if not isinstance(producer_text, str) or not producer_text.strip():
                return None
            if command_type not in {"GENERAL_COMMAND", "REQUEST_INPUT"}:
                return None
            return {
                "worker_id": target.worker_id or "",
                "output_name": output_name,
                "producer_text": producer_text,
                "command_type": command_type,
                "inputs": tuple(llm_payload.get("inputs", ())),
                "outputs": tuple(llm_payload.get("outputs", ())),
            }
        if pt == "BindExistingProducerStep":
            requested_step_id = llm_payload.get("step_id")
            if not isinstance(requested_step_id, str) or not requested_step_id.strip():
                return None
            candidate = None
            for step in MissingOutputProducerHandler._bindable_steps(context):
                if step.step_id == requested_step_id:
                    candidate = step
                    break
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
        steps = MissingOutputProducerHandler._bindable_steps(context)
        return steps[0] if steps else None

    @staticmethod
    def _bindable_steps(context):
        """Find renderable existing steps that can be bound as producers."""
        steps = context.related_steps
        if not steps:
            return ()
        result = []
        for step in steps:
            if step.source_span_ids or step.metadata.get("origin") == "user_confirmed_repair":
                result.append(step)
        return tuple(result)

