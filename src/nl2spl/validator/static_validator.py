"""StaticValidator - Validate SPL text statically."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from nl2spl.validator.qualified_ref_parser import (
    parse_qualified_ref,
    parse_ref_name,
    unwrap_ref_tag,
)
from nl2spl.validator.type_field_validator import (
    DIAGNOSTIC_UNDECLARED_TOP_TIER_VARIABLE,
    DIAGNOSTIC_UNKNOWN_FIELD_IN_STRUCTURED_TYPE,
    extract_type_field_context,
    validate_qualified_ref_field,
)

DIAGNOSTIC_MULTI_COMMAND_RESULT = "multi_command_result"
DIAGNOSTIC_INVALID_FIELD_ASSIGNMENT_TARGET = "invalid_field_assignment_target"
DIAGNOSTIC_INVALID_REF_IDENTIFIER = "invalid_ref_identifier"


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
    diagnostic_code: str | None = None


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

            errors.extend(self._validate_ref_tags(stripped, i))

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
        errors.extend(self._validate_result_clauses(lines))
        errors.extend(self._validate_field_assignment_targets(lines))
        errors.extend(self._validate_variable_references(spl_text, lines))

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

        type_context = extract_type_field_context(spl_text)

        # Extract all REF matches in spl_text
        var_references: list[tuple[str, tuple[str, ...], int, int]] = []
        for line_idx, line in enumerate(spl_text.split("\n")):
            for match in re.finditer(r"<REF>\s*\*?([^<]+?)\s*</REF>", line):
                ref_text = match.group(1).strip()
                parsed = parse_qualified_ref(ref_text)
                if parsed:
                    var_references.append((parsed[0], parsed[1], line_idx, match.start()))
                else:
                    simple_name = parse_ref_name(ref_text)
                    if simple_name:
                        var_references.append((simple_name[0], (), line_idx, match.start()))

        # Check for undeclared variables/fields using validate_qualified_ref_field
        for top_name, field_path, line, col in var_references:
            if field_path:
                field_errors = validate_qualified_ref_field(
                    top_name=top_name,
                    field_path=field_path,
                    context=type_context,
                    line=line,
                    column=col,
                )
                for fe in field_errors:
                    if fe.diagnostic_code == DIAGNOSTIC_UNDECLARED_TOP_TIER_VARIABLE:
                        errors.append(f"Undeclared variable referenced: {top_name}")
                    elif fe.diagnostic_code == DIAGNOSTIC_UNKNOWN_FIELD_IN_STRUCTURED_TYPE:
                        errors.append(
                            f"Unknown field referenced: {top_name}.{'.'.join(field_path)}"
                        )
            else:
                if top_name not in type_context.variable_types:
                    errors.append(f"Undeclared variable referenced: {top_name}")

        # Check for unused variables
        # We can extract all declared variable names from variable_types
        # and inline declarations
        used_vars = {top_name for top_name, _, _, _ in var_references}

        # Get variable declarations for unused check (to preserve exact name list from spl_text)
        var_declarations = re.findall(r'"([^"]+)"\s+(\w+):', spl_text)
        # also inline result vars
        inline_result_vars = self._inline_result_declarations(spl_text)
        used_vars.update(inline_result_vars)
        for _, var in var_declarations:
            if var not in used_vars:
                errors.append(f"Unused variable declared: {var}")

        return errors

    def _validate_variable_references(
        self,
        spl_text: str,
        lines: list[str],
    ) -> list[ValidationError]:
        """Validate variable references against declarations and types."""
        errors: list[ValidationError] = []
        if "[DEFINE_VARIABLES:]" not in spl_text:
            return errors

        type_context = extract_type_field_context(spl_text)

        for line_idx, line in enumerate(lines):
            stripped = line.strip()
            for match in re.finditer(r"<REF>\s*\*?([^<]+?)\s*</REF>", stripped):
                ref_text = match.group(1).strip()
                parsed = parse_qualified_ref(ref_text)
                if parsed:
                    top_name, field_path = parsed
                    errors.extend(
                        validate_qualified_ref_field(
                            top_name=top_name,
                            field_path=field_path,
                            context=type_context,
                            line=line_idx,
                            column=match.start(),
                        )
                    )
                else:
                    simple_name = parse_ref_name(ref_text)
                    if simple_name:
                        top_name = simple_name[0]
                        if top_name not in type_context.variable_types:
                            errors.append(
                                ValidationError(
                                    line=line_idx,
                                    column=match.start(),
                                    message=f"Undeclared variable referenced: {top_name}",
                                    severity="error",
                                    diagnostic_code=DIAGNOSTIC_UNDECLARED_TOP_TIER_VARIABLE,
                                )
                            )
        return errors

    def _inline_result_declarations(self, spl_text: str) -> set[str]:
        """Extract VAR_NAME declarations from RESULT/RESPONSE/VALUE clauses."""
        declared: set[str] = set()
        pattern = re.compile(
            r"\b(?:RESULT|RESPONSE|VALUE)\s+(.+?)\s+(?:SET|APPEND)(?=\])",
            flags=re.DOTALL,
        )
        for match in pattern.finditer(spl_text):
            for item in self._split_result_items(match.group(1)):
                if item.startswith("<REF>"):
                    continue
                name_match = re.match(r"([A-Za-z_][A-Za-z0-9_]*)\s*:", item)
                if name_match:
                    declared.add(name_match.group(1))
        return declared

    def _structured_type_definitions(self, spl_text: str) -> dict[str, set[str]]:
        """Parse simple DEFINE_TYPES structured declarations."""
        definitions: dict[str, set[str]] = {}
        for match in re.finditer(
            r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*\{\s*(.*?)\s*\}\s*$",
            spl_text,
            flags=re.MULTILINE,
        ):
            type_name = match.group(1)
            fields: set[str] = set()
            for item in self._split_result_items(match.group(2)):
                field_match = re.match(r"([A-Za-z_][A-Za-z0-9_]*)\s*:", item)
                if field_match:
                    fields.add(field_match.group(1))
            definitions[type_name] = fields
        return definitions

    def _validate_ref_tags(
        self,
        stripped_line: str,
        line_idx: int,
    ) -> list[ValidationError]:
        """Validate REF tags, including qualified read references."""
        errors: list[ValidationError] = []
        for match in re.finditer(r"<REF>\s*\*?([^<]+?)\s*</REF>", stripped_line):
            ref_text = match.group(1).strip()
            if parse_ref_name(ref_text) is None:
                errors.append(
                    ValidationError(
                        line=line_idx,
                        column=match.start(),
                        message=f"Invalid REF tag identifier: {ref_text}",
                        severity="warning",
                        diagnostic_code=DIAGNOSTIC_INVALID_REF_IDENTIFIER,
                    )
                )
        return errors

    def _validate_result_clauses(
        self,
        lines: list[str],
    ) -> list[ValidationError]:
        """Reject top-level comma-separated COMMAND_RESULT lists."""
        errors: list[ValidationError] = []
        pattern = re.compile(r"\b(RESULT|RESPONSE|VALUE)\s+(.+?)\s+(?:SET|APPEND)(?=\])")
        for line_idx, line in enumerate(lines):
            for match in pattern.finditer(line):
                items = self._split_result_items(match.group(2))
                if len(items) > 1:
                    errors.append(
                        ValidationError(
                            line=line_idx,
                            column=match.start(2),
                            message=(
                                "Multi COMMAND_RESULT is not allowed: use one "
                                "structured composite variable"
                            ),
                            severity="error",
                            diagnostic_code=DIAGNOSTIC_MULTI_COMMAND_RESULT,
                        )
                    )
        return errors

    def _validate_field_assignment_targets(
        self,
        lines: list[str],
    ) -> list[ValidationError]:
        """Reject qualified references as SET/APPEND targets in MVP."""
        errors: list[ValidationError] = []
        pattern = re.compile(r"\b(RESULT|RESPONSE|VALUE)\s+(.+?)\s+(?:SET|APPEND)(?=\])")
        for line_idx, line in enumerate(lines):
            for match in pattern.finditer(line):
                for item in self._split_result_items(match.group(2)):
                    unwrapped = unwrap_ref_tag(item)
                    if unwrapped is None:
                        continue
                    inner, _is_value_ref = unwrapped
                    if parse_qualified_ref(inner) is not None:
                        errors.append(
                            ValidationError(
                                line=line_idx,
                                column=match.start(2),
                                message=(
                                    "Qualified reference cannot be used as SET/APPEND target in MVP"
                                ),
                                severity="error",
                                diagnostic_code=(DIAGNOSTIC_INVALID_FIELD_ASSIGNMENT_TARGET),
                            )
                        )
        return errors

    @staticmethod
    def _split_result_items(text: str) -> list[str]:
        """Split result bindings on top-level commas only."""
        items: list[str] = []
        start = 0
        depth = 0
        pairs = {"[": "]", "{": "}", "(": ")"}
        closing = set(pairs.values())

        for index, char in enumerate(text):
            if char in pairs:
                depth += 1
            elif char in closing and depth > 0:
                depth -= 1
            elif char == "," and depth == 0:
                items.append(text[start:index].strip())
                start = index + 1

        items.append(text[start:].strip())
        return [item for item in items if item]

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
