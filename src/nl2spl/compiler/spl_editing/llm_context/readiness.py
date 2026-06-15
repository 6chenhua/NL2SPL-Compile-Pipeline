"""GenerationReadiness evaluator (Phase L1).

Determines whether LLM generation should proceed and at what confidence
level, based on the availability of required facts.
"""

from __future__ import annotations

from nl2spl.compiler.spl_editing.llm_context.model import (
    ContextQuality,
    GenerationReadiness,
    GenerationStatus,
)


def evaluate_readiness(
    *,
    repair_available: bool,
    required_facts_present: tuple[str, ...] = (),
    required_facts_missing: tuple[str, ...] = (),
    quality: ContextQuality | None = None,
    blocking_authority=None,
) -> GenerationReadiness:
    """Evaluate generation readiness.

    Args:
        repair_available: Whether the selected repair is supported at all
            (from RepairCatalog / PatchRegistry).
        required_facts_present: Names of required facts that ARE present.
        required_facts_missing: Names of required facts that ARE missing.
        quality: Optional context quality assessment.
        blocking_authority: Which authority is blocking, if any.

    Returns:
        ``GenerationReadiness`` with appropriate status.
    """
    if not repair_available:
        return GenerationReadiness(
            status="repair_unavailable",
            reasons=("Selected repair is not available for this issue.",),
            blocking_authority="repair_catalog",
        )

    if required_facts_missing:
        return GenerationReadiness(
            status="generation_blocked",
            reasons=tuple(
                f"Missing required fact: '{f}'" for f in required_facts_missing
            ),
            missing_required_facts=required_facts_missing,
            blocking_authority=blocking_authority or "context_provider",
        )

    if quality is not None and quality.confidence == "low":
        status: GenerationStatus = "ready_low_confidence"
        reasons = tuple(
            f"Missing context field: '{f}'"
            for f in quality.missing_context_fields
        ) or ("Context quality is low.",)
        return GenerationReadiness(
            status=status,
            reasons=reasons,
            missing_required_facts=quality.missing_context_fields,
        )

    return GenerationReadiness(status="ready")
