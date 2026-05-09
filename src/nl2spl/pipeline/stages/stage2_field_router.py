"""Stage 2: FieldRouter - Route spans to semantic fields."""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from nl2spl.errors.exceptions import StageError
from nl2spl.ir.field_route_ir import FieldRouteIR
from nl2spl.ir.span_ir import SpanIR
from nl2spl.llm.prompts import load_prompt
from nl2spl.pipeline.stages.base import PipelineStage


class FieldRouter(PipelineStage[list[SpanIR], tuple[FieldRouteIR, list[dict[str, Any]]]]):
    """Route spans to 6 semantic fields.

    This stage takes a list of spans and routes each span to one of 6 semantic fields:
    identity, audience, rules, domain, integrations, behavior.

    It also identifies ambiguous spans that need to be split in Stage 3.
    """

    @property
    def name(self) -> str:
        """Stage name for logging and checkpointing."""
        return "stage2_field_router"

    def execute(self, input_data: list[SpanIR]) -> tuple[FieldRouteIR, list[dict[str, Any]]]:
        """Execute field routing.

        Args:
            input_data: List of spans to route

        Returns:
            Tuple of (FieldRouteIR, ambiguity_updates)

        Raises:
            StageError: If routing fails
        """
        spans = input_data
        self.logger.info("Starting field routing for %d spans", len(spans))

        # 1. Build prompts
        spans_json = json.dumps([asdict(s) for s in spans], ensure_ascii=False, indent=2)
        system_prompt = load_prompt("stage2")
        user_prompt = f"""请将以下 span 路由到 6 个语义字段：

---
{spans_json}
---

输出 JSON："""

        # 2. Call LLM
        try:
            result = self.client.call_json(
                stage_name=self.name,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
        except Exception as e:
            self.logger.error("LLM call failed: %s", e)
            raise StageError(
                message=f"LLM call failed in {self.name}: {e}",
                stage=self.name,
            ) from e

        # 3. Parse result
        routes_data = result.get("routes", {})
        ambiguity_updates = result.get("ambiguity_updates", [])

        # Create FieldRouteIR
        routes = FieldRouteIR(
            identity=routes_data.get("identity", []),
            audience=routes_data.get("audience", []),
            rules=routes_data.get("rules", []),
            domain=routes_data.get("domain", []),
            integrations=routes_data.get("integrations", []),
            behavior=routes_data.get("behavior", []),
        )

        # 4. Write back ambiguity info to spans
        for update in ambiguity_updates:
            span_id = update.get("span_id")
            if not span_id:
                self.logger.warning("Ambiguity update missing span_id: %s", update)
                continue

            # Find the span and update its ambiguity info
            for span in spans:
                if span.span_id == span_id:
                    span.ambiguity.is_ambiguous = update.get("is_ambiguous", False)
                    span.ambiguity.reasons = update.get("reasons", [])
                    span.ambiguity.needs_split = update.get("needs_split", False)
                    self.logger.debug("Updated ambiguity for span %s: %s", span_id, update)
                    break
            else:
                self.logger.warning("Span %s not found for ambiguity update", span_id)

        # 5. Validate no overlap
        overlaps = routes.validate_no_overlap()
        if overlaps:
            self.logger.warning("Overlapping spans detected: %s", overlaps)

        # 6. Log routing summary
        self.logger.info(
            "Routing complete: identity=%d, audience=%d, rules=%d, domain=%d, integrations=%d, behavior=%d",
            len(routes.identity),
            len(routes.audience),
            len(routes.rules),
            len(routes.domain),
            len(routes.integrations),
            len(routes.behavior),
        )

        # 7. Save checkpoint
        self.save_checkpoint({
            "routes": asdict(routes),
            "ambiguity_updates": ambiguity_updates,
            "overlaps": overlaps,
        })

        return routes, ambiguity_updates
