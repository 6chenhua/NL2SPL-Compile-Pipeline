"""R8: Static and behavioral guardrails test."""

import os
import re


def test_static_guardrails_no_hardcoded_spl_syntax() -> None:
    """Scan all Python files in the SPL Editing backend to ensure zero hardcoded SPL syntax."""
    target_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "../../../src/nl2spl/compiler/spl_editing")
    )

    forbidden_patterns = [
        r"\[DEFINE_AGENT:",
        r"\[MAIN_FLOW\]",
        r"\[END_MAIN_FLOW\]",
        r"\[EXCEPTION_FLOW",
        r"\[END_EXCEPTION_FLOW\]",
        r"\[SEQUENTIAL_BLOCK\]",
        r"\[END_SEQUENTIAL_BLOCK\]",
        r"\[STEP:",
        r"\[CALL_API:",
        r"\[INVOKE_WORKER:",
    ]

    violations = []

    for root, _, files in os.walk(target_dir):
        for file in files:
            if file.endswith(".py") and not file.endswith("verifier.py"):
                filepath = os.path.join(root, file)
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()

                for pattern in forbidden_patterns:
                    matches = re.findall(pattern, content)
                    if matches:
                        violations.append(
                            f"File '{file}' contains forbidden SPL syntax pattern '{pattern}': matches={matches}"
                        )

    assert not violations, "\n".join(violations)
