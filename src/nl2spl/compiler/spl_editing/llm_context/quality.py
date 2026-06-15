"""ContextQuality evaluator (Phase L1)."""

from __future__ import annotations

from nl2spl.compiler.spl_editing.llm_context.model import ContextQuality


def evaluate_quality(
    *,
    has_primary_business_fact: bool = False,
    has_source_excerpt: bool = False,
    has_workflow_context: bool = False,
    has_selectable_references: bool = False,
    missing_context_fields: tuple[str, ...] = (),
    warnings: tuple[str, ...] = (),
) -> ContextQuality:
    """Evaluate context quality from boolean dimensions."""
    positives = sum([
        has_primary_business_fact,
        has_source_excerpt,
        has_workflow_context,
    ])
    if positives >= 3:
        confidence = "high"
    elif positives >= 1:
        confidence = "medium"
    else:
        confidence = "low"

    return ContextQuality(
        confidence=confidence,
        has_primary_business_fact=has_primary_business_fact,
        has_source_excerpt=has_source_excerpt,
        has_workflow_context=has_workflow_context,
        has_selectable_references=has_selectable_references,
        missing_context_fields=missing_context_fields,
        warnings=warnings,
    )
