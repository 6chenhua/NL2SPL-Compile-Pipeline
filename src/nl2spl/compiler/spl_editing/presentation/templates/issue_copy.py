"""Issue-level deterministic display copy."""

from __future__ import annotations

from nl2spl.compiler.spl_editing.presentation.contract.categories import (
    IssueCategory,
)

_CATEGORY_LABELS = {
    IssueCategory.EXCEPTION_HANDLING: "Exception handling",
    IssueCategory.REQUIRED_OUTPUTS: "Required outputs",
    IssueCategory.WORKER_DELEGATION: "Worker delegation",
    IssueCategory.API_CONTRACT_REVIEW: "API contract validation",
    IssueCategory.OTHER_EDITABLE: "Other editable issues",
    IssueCategory.REVIEW_ONLY: "Review needed",
    IssueCategory.DEVELOPER_DIAGNOSTIC: "Developer diagnostics",
}

_IMPACT = {
    IssueCategory.EXCEPTION_HANDLING: (
        "The SPL has an exception flow for this condition, but no action to take."
    ),
    IssueCategory.REQUIRED_OUTPUTS: (
        "This output is declared, but no renderable step produces it."
    ),
    IssueCategory.WORKER_DELEGATION: (
        "The compiler detected a possible delegated worker, but the handoff contract is incomplete."
    ),
    IssueCategory.API_CONTRACT_REVIEW: (
        "The API declaration is structurally renderable, but the real API contract "
        "must be validated downstream."
    ),
    IssueCategory.OTHER_EDITABLE: "This issue can be reviewed for repair.",
    IssueCategory.REVIEW_ONLY: "This item needs review but cannot be fixed here.",
    IssueCategory.DEVELOPER_DIAGNOSTIC: (
        "This diagnostic is not exposed as a user-actionable issue."
    ),
}

_WHAT_DETECTED = {
    IssueCategory.EXCEPTION_HANDLING: (
        "The compiler found an exception flow with a condition but no handler step."
    ),
    IssueCategory.REQUIRED_OUTPUTS: (
        "The compiler found a required output with no renderable producer."
    ),
    IssueCategory.WORKER_DELEGATION: (
        "The compiler found a possible delegated worker without enough handoff "
        "contract information."
    ),
    IssueCategory.API_CONTRACT_REVIEW: (
        "The compiler rendered grammar-safe API placeholders because no authoritative "
        "OpenAPI or functions contract was available."
    ),
    IssueCategory.OTHER_EDITABLE: "The compiler found an editable issue.",
    IssueCategory.REVIEW_ONLY: "The compiler found an item that needs review.",
    IssueCategory.DEVELOPER_DIAGNOSTIC: (
        "The compiler produced a diagnostic that is not user-actionable."
    ),
}

_WHY_IT_MATTERS = {
    IssueCategory.EXCEPTION_HANDLING: (
        "Without a handler, this exception flow can be rendered only as an "
        "empty branch. The compiler did not invent a fallback action."
    ),
    IssueCategory.REQUIRED_OUTPUTS: (
        "Without a producer, downstream consumers cannot know which step creates "
        "the required output."
    ),
    IssueCategory.WORKER_DELEGATION: (
        "Without a complete handoff contract, the compiler cannot safely decide "
        "what to pass to the child worker, when to invoke it, or how to bind "
        "the result back."
    ),
    IssueCategory.API_CONTRACT_REVIEW: (
        "NL2SPL can preserve a renderable API declaration, but the downstream SPL "
        "compiler or API validation layer remains the authority for semantic contract "
        "correctness."
    ),
    IssueCategory.OTHER_EDITABLE: "Review the issue before applying a repair.",
    IssueCategory.REVIEW_ONLY: "This cannot be repaired through the current flow.",
    IssueCategory.DEVELOPER_DIAGNOSTIC: (
        "This usually indicates an incomplete presentation or repair contract."
    ),
}


def category_label(category: IssueCategory) -> str:
    return _CATEGORY_LABELS.get(category, "Other issues")


def impact_text(category: IssueCategory) -> str:
    return _IMPACT.get(category, _IMPACT[IssueCategory.OTHER_EDITABLE])


def what_detected_text(category: IssueCategory) -> str:
    return _WHAT_DETECTED.get(category, _WHAT_DETECTED[IssueCategory.OTHER_EDITABLE])


def why_it_matters_text(category: IssueCategory) -> str:
    return _WHY_IT_MATTERS.get(category, _WHY_IT_MATTERS[IssueCategory.OTHER_EDITABLE])


def issue_title(
    category: IssueCategory,
    *,
    condition_text: str | None = None,
    output_name: str | None = None,
) -> str:
    if category == IssueCategory.EXCEPTION_HANDLING:
        return (
            f"Exception has no handler: {condition_text}"
            if condition_text
            else "Exception has no handler"
        )
    if category == IssueCategory.REQUIRED_OUTPUTS:
        return (
            f"Required output has no producer: {output_name}"
            if output_name
            else "Required output has no producer"
        )
    if category == IssueCategory.WORKER_DELEGATION:
        return "Worker delegation is underspecified"
    if category == IssueCategory.API_CONTRACT_REVIEW:
        return "API contract validation is deferred"
    if category == IssueCategory.REVIEW_ONLY:
        return "Review needed"
    if category == IssueCategory.DEVELOPER_DIAGNOSTIC:
        return "Developer diagnostic"
    return "Editable issue"


__all__ = [
    "category_label",
    "impact_text",
    "issue_title",
    "what_detected_text",
    "why_it_matters_text",
]
