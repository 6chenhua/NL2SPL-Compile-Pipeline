"""Missing handler repair handler.

Thin LLM caller: receives a rendered prompt plus target context, calls LLM,
parses JSON, and assembles ``RepairSuggestion`` objects.  Prompt construction
and business-context extraction are owned by the service LLM-context layer.
"""

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
from nl2spl.compiler.spl_editing.handlers.base import (
    IssueRepairHandler,
    SuggestionPolicy,
)
from nl2spl.compiler.spl_editing.handlers.llm_adapter import SuggestionLLM
from nl2spl.compiler.spl_editing.handlers.missing_handler.prompt import (
    MISSING_HANDLER_SYSTEM_PROMPT,
)
from nl2spl.compiler.spl_editing.handlers.parser import parse_suggestion_payload
from nl2spl.compiler.spl_editing.llm_context.rendering import (
    append_previous_suggestions,
)


class MissingHandlerRepairHandler(IssueRepairHandler):
    """Generate ``AddExceptionHandlerStep`` suggestions from rendered prompts."""

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
        selected_patch_types: tuple[str, ...] | None = None,
        *,
        rendered_user_prompt: str | None = None,
    ) -> tuple[RepairSuggestion, ...]:
        """Generate suggestions from a service-rendered prompt."""
        if rendered_user_prompt is None:
            raise PatchValidationError(
                "MissingHandlerRepairHandler requires a rendered_user_prompt "
                "from LLMRepairContext."
            )

        allowed = tuple(
            pt for entry in catalog_entries for pt in entry.supported_patch_types
        )
        if selected_patch_types:
            allowed = tuple(pt for pt in allowed if pt in selected_patch_types)
        if not allowed:
            return ()

        suggestions: list[RepairSuggestion] = []
        parse_failures = 0
        previous_summaries: list[str] = []
        previous_payloads: list[dict] = []
        max_attempts = self._policy.max_suggestions * self._policy.max_attempts_ratio

        for _ in range(max_attempts):
            if len(suggestions) >= self._policy.max_suggestions:
                break

            raw = self._llm.generate_json(
                system_prompt=MISSING_HANDLER_SYSTEM_PROMPT,
                user_prompt=append_previous_suggestions(
                    rendered_user_prompt,
                    tuple(previous_summaries),
                ),
            )
            try:
                data = parse_suggestion_payload(raw, allowed)
            except UnsupportedPatchTypeError:
                raise
            except PatchValidationError:
                parse_failures += 1
                continue

            entry = catalog_entries[0]
            payload = dict(data["payload"])
            payload.setdefault("worker_id", target.worker_id or "")
            payload.setdefault(
                "exception_flow_id",
                self._flow_id_from_target(target),
            )

            if payload in previous_payloads:
                parse_failures += 1
                continue

            previous_summaries.append(
                f"{data['title']}: {data['explanation']}"
            )
            previous_payloads.append(payload)

            suggestions.append(
                RepairSuggestion(
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
            )

        if not suggestions:
            raise PatchValidationError(
                "LLM did not produce any valid AddExceptionHandlerStep "
                f"suggestions ({parse_failures} parse/schema/duplicate failures)."
            )

        return tuple(suggestions[: self._policy.max_suggestions])

    @staticmethod
    def _flow_id_from_target(target: RepairTarget) -> str:
        cpath = target.construct_path or ()
        if len(cpath) >= 4 and cpath[-2] == "exception_flows":
            return str(cpath[-1])
        marker = ".exception_flow:"
        ref = target.target_ref
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
