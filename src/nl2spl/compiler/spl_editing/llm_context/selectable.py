"""SelectableReference builder helpers (Phase L2).

Builds ``SelectableReference`` objects from typed backend artifacts.
Each reference carries the internal id, a human-readable summary, and
the ``payload_field`` where the LLM may use it.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from nl2spl.compiler.spl_editing.llm_context.model import (
    SelectableReference,
)


def build_step_reference(
    *,
    step_id: str,
    step_text: str,
    inputs: tuple[str, ...] = (),
    outputs: tuple[str, ...] = (),
    command_type: str = "GENERAL_COMMAND",
    renderability_status: str | None = None,
    extra: Mapping[str, Any] | None = None,
) -> SelectableReference:
    """Build a selectable reference for an existing step."""
    summary_parts: dict[str, Any] = {
        "inputs": list(inputs),
        "outputs": list(outputs),
        "command_type": command_type,
    }
    if renderability_status:
        summary_parts["renderability_status"] = renderability_status
    if extra:
        summary_parts.update(extra)

    return SelectableReference(
        id=step_id,
        label="Existing step"
        if not renderability_status
        else f"Existing step ({renderability_status})",
        summary=step_text or f"Step {step_id}",
        kind="step",
        payload_field="step_id",
        business_summary=summary_parts,
    )


def build_variable_reference(
    *,
    var_name: str,
    description: str = "",
    source_hint: str = "",
) -> SelectableReference:
    return SelectableReference(
        id=var_name,
        label="Available variable" if not source_hint else f"Variable ({source_hint})",
        summary=description or var_name,
        kind="variable",
        payload_field="variable_name",
        business_summary={"description": description} if description else {},
    )


def build_worker_reference(
    *,
    worker_id: str,
    worker_name: str = "",
    purpose: str = "",
) -> SelectableReference:
    return SelectableReference(
        id=worker_id,
        label="Worker",
        summary=worker_name or worker_id,
        kind="worker",
        payload_field="worker_id",
        business_summary={"purpose": purpose} if purpose else {},
    )


def build_output_reference(
    *,
    output_name: str,
    description: str = "",
    requiredness: str = "required",
) -> SelectableReference:
    return SelectableReference(
        id=output_name,
        label=f"{requiredness.title()} output",
        summary=description or output_name,
        kind="output",
        payload_field="output_name",
        business_summary={
            "description": description,
            "requiredness": requiredness,
        },
    )
