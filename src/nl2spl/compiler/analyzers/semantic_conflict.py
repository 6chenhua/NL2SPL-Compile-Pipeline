"""Semantic conflict analyzer -- protocol, NoOp, LLM, and evidence verifier.

The production orchestrator currently uses the no-op analyzer. All emitted
``semantic_conflict`` diagnostics must pass the evidence verifier.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

from nl2spl.ir.diagnostics import CompileDiagnostic

if TYPE_CHECKING:
    from nl2spl.canonical import CanonicalCompileInput
    from nl2spl.ir.constraint_ir import ConstraintIR
    from nl2spl.ir.flow_structure_ir import FlowStructureIR
    from nl2spl.ir.span_ir import SpanIR
    from nl2spl.ir.step_ir import StepIR
    from nl2spl.ir.symbol_table import SymbolTable
    from nl2spl.ir.worker_plan_ir import WorkerFlowPlanIR, WorkerPlanIR

_logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Context
# ------------------------------------------------------------------


@dataclass
class ConflictAnalysisContext:
    """Immutable input context for a semantic conflict analyzer."""

    spans: list[SpanIR] = field(default_factory=list)
    canonical_input: CanonicalCompileInput | None = None
    worker_plan: WorkerPlanIR | None = None


# ------------------------------------------------------------------
# Protocol
# ------------------------------------------------------------------


class SemanticConflictAnalyzer(Protocol):
    """Analyzer that detects likely semantic conflicts and returns diagnostics.

    Implementations MUST NOT mutate IR inputs or SPL text.
    """

    def analyze(
        self,
        constraints: list[ConstraintIR],
        steps: list[StepIR],
        flows: FlowStructureIR | WorkerFlowPlanIR,
        symbols: SymbolTable,
        context: ConflictAnalysisContext,
    ) -> list[CompileDiagnostic]:
        ...


# ------------------------------------------------------------------
# NoOp
# ------------------------------------------------------------------


class NoOpSemanticConflictAnalyzer:
    """Default no-op analyzer -- returns empty list, no LLM calls."""

    def analyze(
        self,
        constraints: list[ConstraintIR],
        steps: list[StepIR],
        flows: FlowStructureIR | WorkerFlowPlanIR,
        symbols: SymbolTable,
        context: ConflictAnalysisContext,
    ) -> list[CompileDiagnostic]:
        return []


# ------------------------------------------------------------------
# LLM analyzer
# ------------------------------------------------------------------

ALLOWED_SEVERITIES = frozenset({"info", "warning"})


class LLMSemanticConflictAnalyzer:
    """LLM-backed semantic conflict analyzer.

    Accepts an injectable ``call_json`` for testability.  Builds a
    structured JSON payload, calls the LLM, parses the response, and
    returns evidence-bound ``semantic_conflict`` diagnostics.

    Every returned diagnostic gets ``kind="semantic_conflict"``
    regardless of what the LLM outputs.  The orchestrator is expected
    to run ``LLMConflictDiagnosticVerifier`` as a second pass.
    """

    PROMPT = (
        "Identify only clear or likely semantic conflicts. "
        "Do not rewrite SPL. "
        "Do not invent missing steps. "
        "Do not create new workers, policies, variables, or commands. "
        "Return diagnostics only. "
        "Every diagnostic must cite existing spans or section/packet evidence."
    )

    def __init__(
        self,
        call_json: Callable[..., dict[str, Any]] | None = None,
    ) -> None:
        self._call_json = call_json

    # -- public ----------------------------------------------------------

    def analyze(
        self,
        constraints: list[ConstraintIR],
        steps: list[StepIR],
        flows: FlowStructureIR | WorkerFlowPlanIR,
        symbols: SymbolTable,
        context: ConflictAnalysisContext,
    ) -> list[CompileDiagnostic]:
        if self._call_json is None:
            return []

        payload = self._build_payload(constraints, steps, flows, symbols, context)
        user_prompt = json.dumps(payload, ensure_ascii=False, indent=2)
        try:
            raw = self._call_json(
                stage_name="semantic_conflict_analyzer",
                system_prompt=self.PROMPT,
                user_prompt=user_prompt,
            )
        except Exception:
            _logger.warning(
                "LLMSemanticConflictAnalyzer: LLM call failed, returning empty",
                exc_info=True,
            )
            return []

        return self._parse_response(raw)

    # -- payload ---------------------------------------------------------

    def _build_payload(
        self,
        constraints: list[ConstraintIR],
        steps: list[StepIR],
        flows: FlowStructureIR | WorkerFlowPlanIR,
        symbols: SymbolTable,
        context: ConflictAnalysisContext,
    ) -> dict[str, Any]:
        return {
            "constraints": [
                {
                    "id": c.constraint_id,
                    "text": c.text,
                    "kind": c.kind,
                    "source_span_ids": c.source_span_ids,
                }
                for c in constraints
            ],
            "steps": [
                {
                    "id": s.step_id,
                    "target_ref": f"step:{s.step_id}",
                    "text": s.text,
                    "command_type": s.command_type,
                    "inputs": list(s.inputs),
                    "outputs": list(s.outputs),
                    "source_span_ids": list(s.source_span_ids),
                    "integration_ref": s.integration_ref,
                    "handoff_id": s.handoff_id,
                }
                for s in steps
            ],
            "flows_summary": _flows_summary(flows),
            "symbols": [
                {
                    "name": name,
                    "data_type": getattr(info, "data_type", "unknown"),
                }
                for name, info in (
                    getattr(symbols, "variables", None) or {}
                ).items()
            ],
            "spans": [
                {"span_id": s.span_id, "text": s.text}
                for s in context.spans
            ],
            "worker_context": _worker_context(context.worker_plan),
        }

    # -- response parsing ------------------------------------------------

    def _parse_response(
        self, raw: dict[str, Any]
    ) -> list[CompileDiagnostic]:
        items = raw.get("diagnostics")
        if not isinstance(items, list):
            return []

        result: list[CompileDiagnostic] = []
        for i, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            target_ref = _as_str(item.get("target_ref"))
            source_span_ids = _as_str_list(item.get("source_span_ids"))
            message = _as_str(item.get("message")) or "Likely semantic conflict."

            if not target_ref or not source_span_ids:
                continue  # verifier would reject; skip early

            severity = _as_str(item.get("severity"), default="warning")
            if severity not in ALLOWED_SEVERITIES:
                severity = "warning"

            suggested = _as_str(item.get("suggested_resolution"))

            result.append(
                CompileDiagnostic(
                    diagnostic_id=f"sc_{i + 1:04d}",
                    kind="semantic_conflict",
                    severity=severity,
                    message=message,
                    target_ref=target_ref,
                    source_span_ids=source_span_ids,
                    suggested_resolution=suggested,
                    blocks_rendering=False,
                    blocks_completion=False,
                )
            )
        return result


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _flows_summary(flows: FlowStructureIR | WorkerFlowPlanIR) -> dict[str, Any]:
    from nl2spl.ir.worker_plan_ir import WorkerFlowPlanIR

    if isinstance(flows, WorkerFlowPlanIR):
        exc_count = sum(
            len(f.exception_flows) for f in flows.worker_flows.values()
        )
        return {
            "kind": "worker_scoped",
            "worker_count": len(flows.worker_flows),
            "exception_flows_total": exc_count,
        }
    exc_flow = getattr(flows, "exception_flows", None)
    return {
        "kind": "flat",
        "main_flow_spans": getattr(flows, "main_flow_spans", []),
        "exception_flows_count": len(exc_flow) if exc_flow else 0,
    }


def _worker_context(worker_plan: WorkerPlanIR | None) -> dict[str, Any]:
    if worker_plan is None:
        return {"present": False}
    return {
        "present": True,
        "main_worker_id": worker_plan.main_worker_id,
        "worker_count": len(worker_plan.workers),
        "handoff_count": len(worker_plan.handoffs),
    }


def _as_str(value: Any, *, default: str = "") -> str:
    if isinstance(value, str) and value:
        return value
    return default


def _as_str_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(v) for v in value if isinstance(v, str) and v]
    return []


# ------------------------------------------------------------------
# Verifier
# ------------------------------------------------------------------


class LLMConflictDiagnosticVerifier:
    """Structural evidence verifier for ``semantic_conflict`` diagnostics.

    Accept rules:
      - kind == "semantic_conflict"
      - source_span_ids non-empty
      - target_ref non-empty and contains ":"

    Rejected diagnostics do NOT enter compile_diagnostics.
    """

    def verify(
        self,
        diagnostics: list[CompileDiagnostic],
    ) -> tuple[list[CompileDiagnostic], list[str]]:
        """Return (accepted, warnings) for rejected diagnostics."""
        accepted: list[CompileDiagnostic] = []
        warnings: list[str] = []

        for diag in diagnostics:
            rejection = self._rejection_reason(diag)
            if rejection is None:
                accepted.append(diag)
            else:
                warnings.append(
                    f"SEMANTIC_CONFLICT_REJECTED: {rejection} "
                    f"(id={diag.diagnostic_id}, target={diag.target_ref})"
                )

        return accepted, warnings

    # -- internal --------------------------------------------------------

    @staticmethod
    def _rejection_reason(diag: CompileDiagnostic) -> str | None:
        if diag.kind != "semantic_conflict":
            return f"unsupported diagnostic kind '{diag.kind}'"
        if not diag.source_span_ids:
            return "missing source evidence"
        if not diag.target_ref or ":" not in diag.target_ref:
            return "invalid target_ref"
        return None
