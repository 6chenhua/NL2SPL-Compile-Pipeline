"""Type-or-contract-ambiguity repair handler (stub for B7).

Subtype dispatch skeleton — must be resolved by
``construct_type + slot_name + affordance_id``, not free-form
classifier.  B7 sub-handlers will be registered per subtype.
"""

from __future__ import annotations

from nl2spl.compiler.spl_editing.core.catalog import RepairCatalogEntry
from nl2spl.compiler.spl_editing.core.errors import UnsupportedIssueError
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

# MVP subtypes: (construct_type, slot_name, affordance_id) for B7.
# B7 will register sub-handlers for each of these.
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
    """Stub handler for type_or_contract_ambiguity diagnostics.

    Subtypes are keyed by ``(construct_type, slot_name, affordance_id)``.
    B7 will register per-subtype sub-handlers.  Until then, unsupported
    subtypes raise ``UnsupportedIssueError``; recognised subtypes return
    empty (no sub-handler wired yet).
    """

    handler_id = "type_or_contract_ambiguity"

    def __init__(self, policy: SuggestionPolicy | None = None) -> None:
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
        aff = (
            catalog_entries[0].affordance_id
            if catalog_entries else ""
        )
        return (ct, sn, aff)

    def generate_suggestions(
        self,
        issue: EditableIssue,
        target: RepairTarget,
        context: RepairContext,
        catalog_entries: tuple[RepairCatalogEntry, ...],
        user_instruction: str | None = None,
    ) -> tuple[RepairSuggestion, ...]:
        key = self._subtype_key(issue, catalog_entries)
        if key not in _MVP_SUBTYPES:
            raise UnsupportedIssueError(
                f"type_or_contract_ambiguity subtype "
                f"({key[0]}, {key[1]}, {key[2]}) is not supported "
                f"in MVP."
            )
        ct = key[0]
        if ct == "WORKER_HANDOFF":
            raise UnsupportedIssueError(
                f"WORKER_HANDOFF requires B7d (CreateWorkerHandoffContract) "
                f"which depends on B4.5 Lane B proof."
            )
        if ct != "WORKER_PROMOTION":
            raise UnsupportedIssueError(
                f"Construct type '{ct}' has no suggestion handler."
            )
        entry = catalog_entries[0] if catalog_entries else None
        if entry is None:
            return ()
        # Return one stub suggestion per supported patch type
        patch_types = entry.supported_patch_types or ()
        result: list[RepairSuggestion] = []
        for i, pt in enumerate(patch_types[:3]):
            payload: dict = {}
            preview = ""
            if pt == "ConvertDelegationIntentToMainFlowStep":
                payload = {
                    "worker_id": (target.worker_id or ""),
                    "action_text": "Execute the delegated task.",
                    "outputs": [],
                }
                preview = "[GENERAL_COMMAND] Execute the delegated task."
            elif pt == "ConvertDelegationIntentToRequestInput":
                payload = {
                    "worker_id": (target.worker_id or ""),
                    "prompt_text": "Ask the user to provide the missing information.",
                    "value_target": "user_input",
                }
                preview = "[REQUEST_INPUT] Ask the user to provide the missing information."
            elif pt == "CreateWorkerHandoffContract":
                child_id = context.metadata.get("derived_child_worker_id")
                if not child_id:
                    continue
                payload = {
                    "worker_promotion_id": issue.target_ref.replace("worker_promotion:", ""),
                    "parent_worker_id": context.metadata.get("parent_worker_id",
                                                               target.worker_id or ""),
                    "child_worker_id": child_id,
                    "input_bindings": {},
                    "output_bindings": {},
                    "invocation_point": "main",
                }
                preview = f"[INVOKE {child_id}]"
            else:
                continue
            result.append(RepairSuggestion(
                suggestion_id=f"{issue.issue_id}_stub_{i:02d}",
                session_id="",
                affordance_id=entry.affordance_id,
                title=f"Convert delegation ({pt})",
                explanation=f"Apply {pt} to resolve the unresolved delegation intent.",
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
        return tuple(result)
