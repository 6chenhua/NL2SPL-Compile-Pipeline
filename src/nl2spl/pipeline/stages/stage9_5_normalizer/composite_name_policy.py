"""
CompositeNamePolicy - Validate variable and type names for composite lowering.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

DIAGNOSTIC_COMPOSITE_NAME_POLICY_VIOLATION = "composite_name_policy_violation"


@dataclass(frozen=True)
class NamePolicyResult:
    accepted: bool
    diagnostic_code: str | None = None
    reason: str | None = None


class CompositeNamePolicy:
    """Validate naming conventions for composite variables and types."""

    def validate_variable_name(self, name: str) -> NamePolicyResult:
        """Validate composite variable name conventions."""
        # 1. Patterns to reject
        rejected_patterns = [
            r"^tmp_\d",
            r"^result_\d",
            r"^var_[0-9a-f]+",
            r".*_structured$",
            r".*_st_\d+",
            r".*step.*result",
            r".*command.*",
            r".*_type$",
        ]
        for pattern in rejected_patterns:
            if re.match(pattern, name, re.IGNORECASE):
                return NamePolicyResult(
                    accepted=False,
                    diagnostic_code=DIAGNOSTIC_COMPOSITE_NAME_POLICY_VIOLATION,
                    reason=f"Name '{name}' matches forbidden pattern: {pattern}",
                )

        # 2. Segments check: at least 2 word segments, each segment at least 2 chars
        segments = name.split("_")
        if len(segments) < 2:
            return NamePolicyResult(
                accepted=False,
                diagnostic_code=DIAGNOSTIC_COMPOSITE_NAME_POLICY_VIOLATION,
                reason=(
                    f"Name '{name}' must contain at least 2 word segments "
                    "separated by underscores"
                ),
            )
        for seg in segments:
            if len(seg) < 2:
                return NamePolicyResult(
                    accepted=False,
                    diagnostic_code=DIAGNOSTIC_COMPOSITE_NAME_POLICY_VIOLATION,
                    reason=f"Segment '{seg}' in '{name}' is too short (must be >= 2 characters)",
                )

        # 3. Reject pure step_id/worker_id combinations
        for seg in segments:
            seg_lower = seg.lower()
            if seg_lower in ("step", "worker", "command"):
                return NamePolicyResult(
                    accepted=False,
                    diagnostic_code=DIAGNOSTIC_COMPOSITE_NAME_POLICY_VIOLATION,
                    reason=f"Name '{name}' contains forbidden term: {seg}",
                )
            if re.match(r"^st\d+$", seg_lower) or re.match(r"^step\d+$", seg_lower):
                return NamePolicyResult(
                    accepted=False,
                    diagnostic_code=DIAGNOSTIC_COMPOSITE_NAME_POLICY_VIOLATION,
                    reason=f"Name '{name}' contains forbidden step pattern: {seg}",
                )

        return NamePolicyResult(accepted=True)

    def validate_type_name(self, name: str) -> NamePolicyResult:
        """Validate composite type name conventions."""
        # Type name is camel case of variable name, but must not contain mechanical suffixes
        rejected_patterns = [
            r".*Type$",
            r".*StructuredType$",
            r".*Structured$",
            r".*St\d+.*",
            r".*Step.*Result",
        ]
        for pattern in rejected_patterns:
            if re.match(pattern, name, re.IGNORECASE):
                return NamePolicyResult(
                    accepted=False,
                    diagnostic_code=DIAGNOSTIC_COMPOSITE_NAME_POLICY_VIOLATION,
                    reason=f"Type name '{name}' matches forbidden pattern: {pattern}",
                )

        # Minimum length check for name (e.g. at least 6 characters total to represent 2 segments)
        if len(name) < 6:
            return NamePolicyResult(
                accepted=False,
                diagnostic_code=DIAGNOSTIC_COMPOSITE_NAME_POLICY_VIOLATION,
                reason=f"Type name '{name}' is too short",
            )

        return NamePolicyResult(accepted=True)
