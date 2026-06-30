"""Presentation issue category keys."""

from __future__ import annotations

from enum import StrEnum


class IssueCategory(StrEnum):
    EXCEPTION_HANDLING = "exception_handling"
    REQUIRED_OUTPUTS = "required_outputs"
    WORKER_DELEGATION = "worker_delegation"
    API_CONTRACT_REVIEW = "api_contract_review"
    OTHER_EDITABLE = "other_editable"
    REVIEW_ONLY = "review_only"
    DEVELOPER_DIAGNOSTIC = "developer_diagnostic"


__all__ = ["IssueCategory"]
