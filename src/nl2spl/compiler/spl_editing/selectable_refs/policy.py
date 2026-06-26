"""SelectableRef policy validation logic and registry."""

from __future__ import annotations

from dataclasses import dataclass, field

from nl2spl.compiler.spl_editing.selectable_refs.errors import SelectableRefPolicyViolationError
from nl2spl.compiler.spl_editing.selectable_refs.model import SelectableRef, SelectableRefSet


@dataclass(frozen=True)
class SelectableRefRoleRequirement:
    """Constraints for a specific role in a SelectableRefPolicy."""

    ref_role: str
    min_count: int = 0
    max_count: int | None = None
    allowed_ref_kinds: tuple[str, ...] = ()
    worker_scope_required: bool = False


@dataclass(frozen=True)
class SelectableRefPolicy:
    """Policy defining selectable reference constraints for a repair scenario."""

    policy_id: str
    role_requirements: dict[str, SelectableRefRoleRequirement] = field(default_factory=dict)
    allow_cross_worker: bool = False

    def validate(
        self, refset: SelectableRefSet, selected_refs: list[SelectableRef], role: str
    ) -> None:
        """Validate a list of selected references against this policy and role."""
        req = self.role_requirements.get(role)
        if not req:
            return

        for ref in selected_refs:
            if ref.ref_role != role:
                raise SelectableRefPolicyViolationError(
                    f"Ref '{ref.ref_id}' has role '{ref.ref_role}', expected '{role}' under policy '{self.policy_id}'"  # noqa: E501
                )
            if ref.ref_kind not in req.allowed_ref_kinds:
                raise SelectableRefPolicyViolationError(
                    f"Ref '{ref.ref_id}' has kind '{ref.ref_kind}', which is not allowed for role '{role}' under policy '{self.policy_id}' (allowed: {req.allowed_ref_kinds})"  # noqa: E501
                )
            if req.worker_scope_required and refset.worker_scope is not None:
                if ref.worker_id is not None and ref.worker_id != refset.worker_scope:
                    if not self.allow_cross_worker:
                        raise SelectableRefPolicyViolationError(
                            f"Ref '{ref.ref_id}' is in worker scope '{ref.worker_id}', which does not match target worker scope '{refset.worker_scope}'"  # noqa: E501
                        )

        count = len(selected_refs)
        if count < req.min_count:
            raise SelectableRefPolicyViolationError(
                f"Role '{role}' requires at least {req.min_count} refs, but only {count} were provided under policy '{self.policy_id}'"  # noqa: E501
            )
        if req.max_count is not None and count > req.max_count:
            raise SelectableRefPolicyViolationError(
                f"Role '{role}' allows at most {req.max_count} refs, but {count} were provided under policy '{self.policy_id}'"  # noqa: E501
            )


_POLICIES: dict[str, SelectableRefPolicy] = {
    "required_output.producer.selectable_refs.v1": SelectableRefPolicy(
        policy_id="required_output.producer.selectable_refs.v1",
        role_requirements={
            "target_output": SelectableRefRoleRequirement(
                ref_role="target_output",
                min_count=1,
                max_count=1,
                allowed_ref_kinds=("required_output",),
                worker_scope_required=True,
            ),
            "selectable_input": SelectableRefRoleRequirement(
                ref_role="selectable_input",
                min_count=0,
                max_count=None,
                allowed_ref_kinds=("worker_input", "step_output", "variable", "resource"),
                worker_scope_required=True,
            ),
            "source_evidence": SelectableRefRoleRequirement(
                ref_role="source_evidence",
                min_count=0,
                max_count=None,
                allowed_ref_kinds=("source_span",),
                worker_scope_required=False,
            ),
        },
        allow_cross_worker=False,
    ),
    "exception_flow.handler.selectable_refs.v1": SelectableRefPolicy(
        policy_id="exception_flow.handler.selectable_refs.v1",
        role_requirements={
            "target_exception_flow": SelectableRefRoleRequirement(
                ref_role="target_exception_flow",
                min_count=1,
                max_count=1,
                allowed_ref_kinds=("exception_flow",),
                worker_scope_required=True,
            ),
            "selectable_input": SelectableRefRoleRequirement(
                ref_role="selectable_input",
                min_count=0,
                max_count=None,
                allowed_ref_kinds=("worker_input", "step_output", "variable", "resource"),
                worker_scope_required=True,
            ),
        },
        allow_cross_worker=False,
    ),
    "worker_promotion.handoff.selectable_refs.v1": SelectableRefPolicy(
        policy_id="worker_promotion.handoff.selectable_refs.v1",
        role_requirements={
            "target_worker": SelectableRefRoleRequirement(
                ref_role="target_worker",
                min_count=1,
                max_count=1,
                allowed_ref_kinds=("worker",),
                worker_scope_required=True,
            ),
            "selectable_input": SelectableRefRoleRequirement(
                ref_role="selectable_input",
                min_count=0,
                max_count=None,
                allowed_ref_kinds=("worker_input", "step_output", "variable", "resource"),
                worker_scope_required=True,
            ),
        },
        allow_cross_worker=False,
    ),
}


def get_policy(policy_id: str) -> SelectableRefPolicy | None:
    """Retrieve a policy by its ID from the registry."""
    return _POLICIES.get(policy_id)
