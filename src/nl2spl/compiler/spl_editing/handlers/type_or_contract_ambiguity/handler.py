"""Type-or-contract-ambiguity repair handler."""

from __future__ import annotations

from nl2spl.compiler.spl_editing.core.catalog import RepairCatalogEntry
from nl2spl.compiler.spl_editing.core.errors import (
    PatchValidationError,
    UnsupportedIssueError,
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
from nl2spl.compiler.spl_editing.handlers.parser import parse_suggestion_payload
from nl2spl.compiler.spl_editing.handlers.type_or_contract_ambiguity.prompt import (
    TYPE_OR_CONTRACT_SYSTEM_PROMPT,
    build_type_or_contract_user_prompt,
)

_MVP_SUBTYPES: frozenset[tuple[str, str, str]] = frozenset({
    ("WORKER_PROMOTION", "promotion_input_contract", "worker_promotion.resolve_contract"),
    ("WORKER_PROMOTION", "promotion_output_contract", "worker_promotion.resolve_contract"),
    ("WORKER_PROMOTION", "promotion_invocation_point", "worker_promotion.resolve_contract"),
    ("WORKER_PROMOTION", "promotion_result_handoff", "worker_promotion.resolve_contract"),
    ("WORKER_HANDOFF", "target", "worker_handoff.specify_target"),
    ("WORKER_HANDOFF", "input_bindings", "worker_handoff.specify_input_bindings"),
    ("WORKER_HANDOFF", "output_bindings", "worker_handoff.specify_output_bindings"),
    ("WORKER_HANDOFF", "invocation_site", "worker_handoff.specify_invocation_site"),
})


class TypeOrContractAmbiguityHandler(IssueRepairHandler):
    """Generate LLM-backed suggestions for type_or_contract_ambiguity."""

    handler_id = "type_or_contract_ambiguity"

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

    @staticmethod
    def _subtype_key(
        issue: EditableIssue,
        catalog_entries: tuple[RepairCatalogEntry, ...],
    ) -> tuple[str, str, str]:
        ct = issue.irs_ref.construct_type
        sn = issue.irs_ref.slot_name
        aff = catalog_entries[0].affordance_id if catalog_entries else ""
        return (ct, sn, aff)

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
        key = self._subtype_key(issue, catalog_entries)
        if key not in _MVP_SUBTYPES:
            raise UnsupportedIssueError(
                f"type_or_contract_ambiguity subtype "
                f"({key[0]}, {key[1]}, {key[2]}) is not supported in MVP."
            )
        ct = key[0]
        if ct == "WORKER_HANDOFF":
            raise UnsupportedIssueError(
                "WORKER_HANDOFF suggestions are not wired for this handler."
            )
        if ct != "WORKER_PROMOTION":
            raise UnsupportedIssueError(
                f"Construct type '{ct}' has no suggestion handler."
            )
        if not catalog_entries:
            return ()

        entry = catalog_entries[0]
        child_id = _string_or_none(context.metadata.get("derived_child_worker_id"))
        child_inputs = _string_tuple(context.metadata.get("child_input_fields"))
        child_outputs = _string_tuple(context.metadata.get("child_output_fields"))

        patch_types_to_generate = list(entry.supported_patch_types)
        if selected_patch_types:
            patch_types_to_generate = [
                pt for pt in patch_types_to_generate
                if pt in selected_patch_types
            ]
        suggestions: list[RepairSuggestion] = []
        parse_failures = 0
        previous_summaries: list[str] = []
        previous_payloads: list[dict] = []
        max_attempts = self._policy.max_suggestions * self._policy.max_attempts_ratio

        # Build ordered sequence of patch types to try.
        # Focused: all attempts on selected type(s).
        # Unfiltered: round-robin to cover every supported type.
        patch_type_sequence = [
            patch_types_to_generate[i % len(patch_types_to_generate)]
            for i in range(max_attempts)
        ]

        for patch_type in patch_type_sequence:
            if len(suggestions) >= self._policy.max_suggestions:
                break
            if patch_type == "CreateWorkerHandoffContract" and not child_id:
                continue
            raw = self._llm.generate_json(
                system_prompt=TYPE_OR_CONTRACT_SYSTEM_PROMPT,
                user_prompt=build_type_or_contract_user_prompt(
                    issue_message=issue.message,
                    target_ref=issue.target_ref,
                    construct_type=issue.irs_ref.construct_type,
                    slot_name=issue.irs_ref.slot_name,
                    allowed_patch_types=(patch_type,),
                    parent_worker_id=_string_or_none(
                        context.metadata.get("parent_worker_id"),
                    ) or target.worker_id,
                    child_worker_id=child_id,
                    child_input_fields=child_inputs,
                    child_output_fields=child_outputs,
                    user_instruction=user_instruction,
                    previous_suggestions=tuple(previous_summaries),
                ),
            )
            try:
                data = parse_suggestion_payload(raw, (patch_type,))
            except UnsupportedPatchTypeError:
                raise
            except PatchValidationError:
                parse_failures += 1
                continue

            payload = self._payload_for(
                patch_type, issue, target, context,
                data["payload"], child_id,
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
            suggestions.append(RepairSuggestion(
                    suggestion_id=f"{issue.issue_id}_sug_{len(suggestions):02d}",
                    session_id="",
                    affordance_id=entry.affordance_id,
                    title=data["title"],
                    explanation=data["explanation"],
                    patch=RepairPatch(
                        patch_id="",
                        affordance_id=entry.affordance_id,
                        patch_type=patch_type,
                        target_ref=issue.target_ref,
                        irs_ref=issue.irs_ref,
                        base_compile_run_id="",
                        artifact_snapshot_id="",
                        overlay_version=0,
                        payload=payload,
                        verification_lane=entry.default_verification_lane,
                    ),
                    spl_preview=self._preview_for(patch_type, payload),
                ))

        if len(suggestions) < self._policy.max_suggestions:
            raise PatchValidationError(
                "LLM did not produce a valid type_or_contract_ambiguity "
                f"suggestion set ({len(suggestions)} unique suggestions, "
                f"expected {self._policy.max_suggestions}; "
                f"{parse_failures} parse/schema/duplicate failures)."
            )
        return tuple(suggestions)

    @staticmethod
    def _payload_for(
        patch_type: str,
        issue: EditableIssue,
        target: RepairTarget,
        context: RepairContext,
        llm_payload: object,
        child_id: str | None,
    ) -> dict | None:
        if not isinstance(llm_payload, dict):
            return None
        if patch_type == "ConvertDelegationIntentToMainFlowStep":
            action_text = llm_payload.get("action_text")
            if not isinstance(action_text, str) or not action_text.strip():
                return None
            parent = _string_or_none(context.metadata.get("parent_worker_id"))
            return {
                "worker_id": parent or target.worker_id or "",
                "action_text": action_text,
                "outputs": _string_tuple(llm_payload.get("outputs")),
            }
        if patch_type == "ConvertDelegationIntentToRequestInput":
            prompt_text = llm_payload.get("prompt_text")
            value_target = llm_payload.get("value_target")
            if not isinstance(prompt_text, str) or not prompt_text.strip():
                return None
            if not isinstance(value_target, str) or not value_target.strip():
                return None
            parent = _string_or_none(context.metadata.get("parent_worker_id"))
            return {
                "worker_id": parent or target.worker_id or "",
                "prompt_text": prompt_text,
                "value_target": value_target,
            }
        if patch_type == "CreateWorkerHandoffContract":
            if not child_id:
                return None
            input_bindings = _string_mapping(llm_payload.get("input_bindings"))
            output_bindings = _string_mapping(llm_payload.get("output_bindings"))
            invocation_point = llm_payload.get("invocation_point")
            if not input_bindings or not output_bindings:
                return None
            if not isinstance(invocation_point, str) or not invocation_point.strip():
                return None
            return {
                "worker_promotion_id": issue.target_ref.replace("worker_promotion:", ""),
                "parent_worker_id": _string_or_none(
                    context.metadata.get("parent_worker_id"),
                ) or target.worker_id or "",
                "child_worker_id": child_id,
                "input_bindings": input_bindings,
                "output_bindings": output_bindings,
                "invocation_point": invocation_point,
            }
        return None

    @staticmethod
    def _preview_for(patch_type: str, payload: dict) -> str:
        if patch_type == "ConvertDelegationIntentToMainFlowStep":
            return f"[GENERAL_COMMAND] {payload.get('action_text', '')}"
        if patch_type == "ConvertDelegationIntentToRequestInput":
            return f"[REQUEST_INPUT] {payload.get('prompt_text', '')}"
        if patch_type == "CreateWorkerHandoffContract":
            return f"[INVOKE {payload.get('child_worker_id', '')}]"
        return ""


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(item for item in value if isinstance(item, str) and item)


def _string_mapping(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {
        k: v
        for k, v in value.items()
        if isinstance(k, str) and k.strip()
        and isinstance(v, str) and v.strip()
    }


def _string_or_none(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value
    return None
