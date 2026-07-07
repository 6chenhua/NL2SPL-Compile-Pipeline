"""
type_field_validator - Verify that field paths in qualified references
match structured type declarations.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nl2spl.validator.static_validator import ValidationError

DIAGNOSTIC_UNDECLARED_TOP_TIER_VARIABLE = "undeclared_top_tier_variable"
DIAGNOSTIC_NOT_STRUCTURED_TYPE = "not_structured_type"
DIAGNOSTIC_UNKNOWN_FIELD_IN_STRUCTURED_TYPE = "unknown_field_in_structured_type"


@dataclass(frozen=True)
class StructuredTypeDefinition:
    type_name: str
    fields: frozenset[str]


@dataclass(frozen=True)
class TypeFieldValidationContext:
    type_definitions: Mapping[str, StructuredTypeDefinition]
    variable_types: Mapping[str, str]


def _split_items(text: str) -> list[str]:
    """Helper to split fields/items on commas, matching bracket nesting."""
    items: list[str] = []
    start = 0
    depth = 0
    pairs = {"[": "]", "{": "}", "(": ")"}
    closing = set(pairs.values())

    for idx, char in enumerate(text):
        if char in pairs:
            depth += 1
        elif char in closing:
            depth = max(0, depth - 1)
        elif char == "," and depth == 0:
            items.append(text[start:idx].strip())
            start = idx + 1
    items.append(text[start:].strip())
    return [item for item in items if item]


def extract_type_field_context(spl_text: str) -> TypeFieldValidationContext:
    """Extract type definitions and variable declarations from SPL text."""
    type_definitions: dict[str, StructuredTypeDefinition] = {}
    variable_types: dict[str, str] = {}

    # 1. Parse named structured types in DEFINE_TYPES block
    for match in re.finditer(
        r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*\{\s*(.*?)\s*\}\s*$",
        spl_text,
        flags=re.MULTILINE,
    ):
        type_name = match.group(1).strip()
        fields: set[str] = set()
        for item in _split_items(match.group(2)):
            field_match = re.match(r"([A-Za-z_][A-Za-z0-9_]*)\s*:", item)
            if field_match:
                fields.add(field_match.group(1))
        type_definitions[type_name] = StructuredTypeDefinition(
            type_name=type_name,
            fields=frozenset(fields),
        )

    # 2. Parse inline result declarations from RESULT/RESPONSE/VALUE clauses
    # E.g. RESULT var: { f1: type } SET
    pattern = re.compile(r"\b(RESULT|RESPONSE|VALUE)\s+(.+?)\s+(?:SET|APPEND)(?=\])")
    for line in spl_text.split("\n"):
        for match in pattern.finditer(line):
            items = _split_items(match.group(2))
            for item in items:
                # Matches: name: type or name: { fields }
                decl_match = re.match(r"([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.+)$", item)
                if not decl_match:
                    continue
                var_name = decl_match.group(1).strip()
                type_expr = decl_match.group(2).strip()
                if type_expr.startswith("{") and type_expr.endswith("}"):
                    # Inline type
                    fields = set()
                    inner = type_expr[1:-1].strip()
                    for f_item in _split_items(inner):
                        f_match = re.match(r"([A-Za-z_][A-Za-z0-9_]*)\s*:", f_item)
                        if f_match:
                            fields.add(f_match.group(1))
                    synthetic_type = f"__inline_result_{var_name}"
                    type_definitions[synthetic_type] = StructuredTypeDefinition(
                        type_name=synthetic_type,
                        fields=frozenset(fields),
                    )
                    variable_types[var_name] = synthetic_type
                else:
                    variable_types[var_name] = type_expr

    # 3. Parse variable declarations in DEFINE_VARIABLES block
    # E.g. "Description" var_name: type
    # Or "Description" var_name: { fields }
    for match in re.finditer(r'"([^"]*)"\s+([A-Za-z_][A-Za-z0-9_]*)\s*:\s*([^#\n\]]+)', spl_text):
        var_name = match.group(2).strip()
        type_expr = match.group(3).strip()
        if type_expr.startswith("{") and type_expr.endswith("}"):
            # Inline structured type
            fields = set()
            inner = type_expr[1:-1].strip()
            for item in _split_items(inner):
                field_match = re.match(r"([A-Za-z_][A-Za-z0-9_]*)\s*:", item)
                if field_match:
                    fields.add(field_match.group(1))
            synthetic_type = f"__inline_var_{var_name}"
            type_definitions[synthetic_type] = StructuredTypeDefinition(
                type_name=synthetic_type,
                fields=frozenset(fields),
            )
            variable_types[var_name] = synthetic_type
        else:
            variable_types[var_name] = type_expr

    return TypeFieldValidationContext(
        type_definitions=type_definitions,
        variable_types=variable_types,
    )


def validate_qualified_ref_field(
    *,
    top_name: str,
    field_path: tuple[str, ...],
    context: TypeFieldValidationContext,
    line: int,
    column: int,
) -> list[ValidationError]:
    """Validate qualified reference top_name and field_path against TypeFieldValidationContext."""
    from nl2spl.validator.static_validator import ValidationError

    errors: list[ValidationError] = []

    # 1. Verify top-tier variable is declared
    if top_name not in context.variable_types:
        errors.append(
            ValidationError(
                line=line,
                column=column,
                message=f"Undeclared top-tier variable referenced: {top_name}",
                severity="error",
                diagnostic_code=DIAGNOSTIC_UNDECLARED_TOP_TIER_VARIABLE,
            )
        )
        return errors

    # 2. Verify top-tier variable type is structured
    var_type = context.variable_types[top_name]
    if var_type not in context.type_definitions:
        errors.append(
            ValidationError(
                line=line,
                column=column,
                message=f"Variable '{top_name}' type '{var_type}' is not a structured type",
                severity="error",
                diagnostic_code=DIAGNOSTIC_NOT_STRUCTURED_TYPE,
            )
        )
        return errors

    # 3. Verify field exists in the structured type
    type_def = context.type_definitions[var_type]
    target_field = field_path[0]
    if target_field not in type_def.fields:
        errors.append(
            ValidationError(
                line=line,
                column=column,
                message=(
                    f"Field '{target_field}' does not exist in structured type "
                    f"'{var_type}' of variable '{top_name}'"
                ),
                severity="error",
                diagnostic_code=DIAGNOSTIC_UNKNOWN_FIELD_IN_STRUCTURED_TYPE,
            )
        )

    return errors
