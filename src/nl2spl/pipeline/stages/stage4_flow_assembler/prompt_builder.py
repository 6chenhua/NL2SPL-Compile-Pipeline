"""Stage 4: FlowAssembler - PromptBuilderMixin (_format_span_text, _format_worker_context)."""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from nl2spl.ir.span_ir import SpanIR
from nl2spl.ir.worker_plan_ir import WorkerPlanIR, WorkerSpecIR


class PromptBuilderMixin:
    """Mixin containing prompt-building helper methods."""

    def _format_span_text(self, spans: list[SpanIR]) -> str:
        """Format spans as compact plain text for prompts."""
        if not spans:
            return "(none)"
        return "\n".join(f"{span.span_id}: {span.text}" for span in spans)

    def _format_worker_context(
        self,
        worker_plan: WorkerPlanIR | None,
        worker: WorkerSpecIR | None,
    ) -> str:
        """Return compact WorkerPlanIR context for the current worker."""
        if worker_plan is None or worker is None:
            return "(none)"

        relevant_handoffs = [
            handoff
            for handoff in worker_plan.handoffs
            if handoff.from_worker == worker.worker_id
            or handoff.to_worker == worker.worker_id
        ]
        context: dict[str, Any] = {
            "main_worker_id": worker_plan.main_worker_id,
            "current_worker": asdict(worker),
            "handoffs": [asdict(handoff) for handoff in relevant_handoffs],
            "unassigned_span_ids": worker_plan.unassigned_span_ids,
        }
        return json.dumps(context, ensure_ascii=False, indent=2)
