"""StaticValidator - Validate SPL text statically."""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class ValidationError:
    """Validation error.

    Attributes:
        line: Line number (0-indexed)
        column: Column number (0-indexed)
        message: Error message
        severity: Error severity (error, warning)
    """

    line: int
    column: int
    message: str
    severity: str = "error"


@dataclass
class ValidationResult:
    """Validation result.

    Attributes:
        is_valid: Whether validation passed
        errors: List of validation errors
    """

    is_valid: bool
    errors: list[ValidationError] = field(default_factory=list)


class StaticValidator:
    """Static SPL validator.

    This class validates SPL text for syntax errors and structural issues.
    """

    STRUCTURAL_OPEN_TAGS = {
        "DEFINE_AGENT",
        "DEFINE_PERSONA",
        "DEFINE_AUDIENCE",
        "DEFINE_CONCEPTS",
        "DEFINE_CONSTRAINTS",
        "DEFINE_VARIABLES",
        "DEFINE_FILES",
        "DEFINE_APIS",
        "DEFINE_TYPES",
        "DEFINE_WORKER",
        "INPUTS",
        "CONTROLLED_INPUTS",
        "OUTPUTS",
        "CONTROLLED_OUTPUT",
        "CONTROLLED_OUTPUTS",
        "MAIN_FLOW",
        "ALTERNATIVE_FLOW",
        "EXCEPTION_FLOW",
        "SEQUENTIAL_BLOCK",
        "IF",
        "FOR",
        "WHILE",
    }

    def validate(self, spl_text: str) -> ValidationResult:
        """Validate SPL text.

        Args:
            spl_text: SPL text to validate

        Returns:
            ValidationResult object
        """
        errors = []
        lines = spl_text.split("\n")

        # Track bracket matching
        bracket_stack: list[tuple[int, str]] = []  # (line, tag_name)

        for i, line in enumerate(lines):
            stripped = line.strip()

            # Skip empty lines
            if not stripped:
                continue

            # Check for opening structural tags. Command bodies such as
            # [COMMAND ...], [CALL ...], and [INPUT ...] are single-line
            # command syntax, not nested sections that require END_* tags.
            opening_tag = self._get_opening_tag(stripped)
            if opening_tag:
                bracket_stack.append((i, opening_tag))

            # Check for closing tags
            closing_match = re.match(r"\[END_([A-Z_]+)\]", stripped)
            if closing_match:
                closing_tag = closing_match.group(1)

                if not bracket_stack:
                    errors.append(
                        ValidationError(
                            line=i,
                            column=0,
                            message=f"Unmatched closing bracket: [END_{closing_tag}]",
                            severity="error",
                        )
                    )
                else:
                    opening_line, opening_tag = bracket_stack.pop()

                    # Normalize opening tag for comparison
                    # DEFINE_PERSONA -> PERSONA
                    # INPUTS -> INPUTS
                    # DEFINE_AGENT -> AGENT
                    expected_closing = opening_tag
                    if expected_closing.startswith("DEFINE_"):
                        expected_closing = expected_closing[7:]  # Remove DEFINE_ prefix

                    # Check if brackets match (case-insensitive)
                    if expected_closing.lower() != closing_tag.lower():
                        errors.append(
                            ValidationError(
                                line=i,
                                column=0,
                                message=(
                                    "Mismatched brackets: expected "
                                    f"[END_{expected_closing}], got [END_{closing_tag}]"
                                ),
                                severity="error",
                            )
                        )

            # Check for REF tags
            ref_tags = re.findall(r"<REF>([^<]+)</REF>", stripped)
            for ref in ref_tags:
                # REF tags should contain valid identifiers
                ref = ref.strip()
                if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", ref):
                    errors.append(
                        ValidationError(
                            line=i,
                            column=0,
                            message=f"Invalid REF tag identifier: {ref}",
                            severity="warning",
                        )
                    )

            # Check for required sections
            if i == 0 and not stripped.startswith("[DEFINE_AGENT:"):
                errors.append(
                    ValidationError(
                        line=i,
                        column=0,
                        message="SPL must start with [DEFINE_AGENT: ...]",
                        severity="error",
                    )
                )

        # Check for unmatched opening brackets
        for line_num, tag in bracket_stack:
            errors.append(
                ValidationError(
                    line=line_num,
                    column=0,
                    message=f"Unmatched opening bracket: [{tag}]",
                    severity="error",
                )
            )

        # Check for required sections
        required_sections = [
            "[DEFINE_AGENT:",
            "[DEFINE_PERSONA:]",
            "[DEFINE_WORKER:",
            "[END_WORKER]",
            "[END_AGENT]",
        ]

        spl_text_upper = spl_text.upper()
        for section in required_sections:
            if section.upper() not in spl_text_upper:
                errors.append(
                    ValidationError(
                        line=0,
                        column=0,
                        message=f"Missing required section: {section}",
                        severity="error",
                    )
                )

        errors.extend(self._validate_required_role(lines))

        # is_valid is True only if there are no errors (warnings are OK)
        is_valid = not any(e.severity == "error" for e in errors)

        return ValidationResult(is_valid=is_valid, errors=errors)

    def _get_opening_tag(self, stripped_line: str) -> str | None:
        """Return the structural opening tag on a line, if any."""
        stripped_line = re.sub(r"^DECISION-\d+\s+", "", stripped_line)
        if stripped_line.startswith("[END_"):
            return None

        match = re.match(r"\[(DEFINE_[A-Z_]+|[A-Z_]+)(?::|\]|\s)", stripped_line)
        if not match:
            return None

        tag = match.group(1)
        if tag in self.STRUCTURAL_OPEN_TAGS:
            return tag
        return None

    def _validate_required_role(self, lines: list[str]) -> list[ValidationError]:
        """Validate that DEFINE_PERSONA contains a non-empty ROLE aspect."""
        errors: list[ValidationError] = []
        persona_start: int | None = None

        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped == "[DEFINE_PERSONA:]":
                persona_start = i
                continue
            if stripped == "[END_PERSONA]" and persona_start is not None:
                role_line = next(
                    (
                        (line_num, candidate.strip())
                        for line_num, candidate in enumerate(
                            lines[persona_start + 1 : i],
                            start=persona_start + 1,
                        )
                        if candidate.strip().startswith("ROLE:")
                    ),
                    None,
                )
                if role_line is None:
                    errors.append(
                        ValidationError(
                            line=persona_start,
                            column=0,
                            message="DEFINE_PERSONA must include ROLE",
                            severity="error",
                        )
                    )
                elif not role_line[1].split(":", 1)[1].strip():
                    errors.append(
                        ValidationError(
                            line=role_line[0],
                            column=0,
                            message="ROLE must not be empty",
                            severity="error",
                        )
                    )
                persona_start = None

        return errors

    def validate_structure(self, spl_text: str) -> list[str]:
        """Validate SPL structure.

        Args:
            spl_text: SPL text to validate

        Returns:
            List of structural validation errors
        """
        errors = []

        # Check for DEFINE_AGENT
        if not re.search(r"\[DEFINE_AGENT:", spl_text):
            errors.append("Missing DEFINE_AGENT section")

        # Check for DEFINE_WORKER
        if not re.search(r"\[DEFINE_WORKER:", spl_text):
            errors.append("Missing DEFINE_WORKER section")

        # Check for END_AGENT
        if not re.search(r"\[END_AGENT\]", spl_text):
            errors.append("Missing END_AGENT")

        # Check for END_WORKER
        if not re.search(r"\[END_WORKER\]", spl_text):
            errors.append("Missing END_WORKER")

        # Check for INPUTS section
        if not re.search(r"\[INPUTS\]", spl_text):
            errors.append("Missing INPUTS section")

        # Check for OUTPUTS section
        if not re.search(r"\[OUTPUTS\]", spl_text):
            errors.append("Missing OUTPUTS section")

        # Check for MAIN_FLOW section
        if not re.search(r"\[MAIN_FLOW\]", spl_text):
            errors.append("Missing MAIN_FLOW section")

        return errors

    def validate_variables(self, spl_text: str) -> list[str]:
        """Validate variable declarations and references.

        Args:
            spl_text: SPL text to validate

        Returns:
            List of variable validation errors
        """
        errors = []

        # Extract variable declarations
        var_declarations = re.findall(r'"([^"]+)"\s+(\w+):', spl_text)
        declared_vars = {var for _, var in var_declarations}

        # Extract variable references
        var_references = re.findall(r"<REF>(\w+)</REF>", spl_text)

        # Check for undeclared variables
        for ref in var_references:
            if ref not in declared_vars:
                errors.append(f"Undeclared variable referenced: {ref}")

        # Check for unused variables
        used_vars = set(var_references)
        for _, var in var_declarations:
            if var not in used_vars:
                errors.append(f"Unused variable declared: {var}")

        return errors

    def get_validation_summary(self, result: ValidationResult) -> str:
        """Get validation summary.

        Args:
            result: ValidationResult object

        Returns:
            Summary string
        """
        error_count = sum(1 for e in result.errors if e.severity == "error")
        warning_count = sum(1 for e in result.errors if e.severity == "warning")

        if result.is_valid:
            return "✓ Validation passed"

        lines = [f"✗ Validation failed: {error_count} error(s), {warning_count} warning(s)"]
        for error in result.errors:
            lines.append(f"  Line {error.line + 1}: {error.message}")

        return "\n".join(lines)
