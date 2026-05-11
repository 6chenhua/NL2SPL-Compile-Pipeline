"""Stage 3: AmbiguityResolver - Resolve ambiguous spans."""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from nl2spl.errors.exceptions import StageError
from nl2spl.ir.field_route_ir import FieldRouteIR
from nl2spl.ir.span_ir import SpanIR
from nl2spl.llm.prompts import load_prompt
from nl2spl.pipeline.stages.base import PipelineStage


class AmbiguityResolver(
    PipelineStage[
        tuple[list[SpanIR], FieldRouteIR, list[dict[str, Any]]],
        tuple[list[SpanIR], FieldRouteIR],
    ]
):
    """Resolve ambiguous spans by splitting them.

    This stage takes spans that were marked as ambiguous in Stage 2
    and splits them into multiple unambiguous sub-spans.
    """

    @property
    def name(self) -> str:
        """Stage name for logging and checkpointing."""
        return "stage3_ambiguity_resolver"

    def execute(
        self, input_data: tuple[list[SpanIR], FieldRouteIR, list[dict[str, Any]]]
    ) -> tuple[list[SpanIR], FieldRouteIR]:
        """Execute ambiguity resolution.

        Args:
            input_data: Tuple of (spans, routes, ambiguity_updates)

        Returns:
            Tuple of (resolved_spans, resolved_routes)

        Raises:
            StageError: If resolution fails
        """
        spans, routes, ambiguity_updates = input_data

        self.logger.info("Starting ambiguity resolution for %d spans", len(spans))

        # If no ambiguity updates, return as-is
        if not ambiguity_updates:
            self.logger.info("No ambiguity updates, returning original spans")
            return spans, routes

        # 1. Build prompts
        spans_json = json.dumps([s.to_dict() for s in spans], ensure_ascii=False, indent=2)
        routes_json = json.dumps(asdict(routes), ensure_ascii=False, indent=2)
        ambiguity_json = json.dumps(ambiguity_updates, ensure_ascii=False, indent=2)

        system_prompt = load_prompt("stage3")
        user_prompt = f"""以下 span 被标记为歧义，请拆分：

原始 spans：
---
{spans_json}
---

当前路由：
---
{routes_json}
---

歧义 span：
---
{ambiguity_json}
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
        resolved_spans_data = result.get("resolved_spans", [])
        resolved_routes_data = result.get("resolved_routes", {})

        # 4. Create new spans for resolved ambiguities
        new_spans = []
        for span_data in resolved_spans_data:
            try:
                span = SpanIR(
                    span_id=span_data["span_id"],
                    text=span_data["text"],
                )
                new_spans.append(span)
            except KeyError as e:
                self.logger.warning("Missing field in resolved span data: %s", e)
                continue
            except ValueError as e:
                self.logger.warning("Invalid resolved span data: %s", e)
                continue

        # 5. Merge spans: remove original ambiguous spans, add new resolved spans
        ambiguous_ids = {u.get("span_id") for u in ambiguity_updates if u.get("span_id")}
        resolved_spans = []
        for span in spans:
            if span.span_id not in ambiguous_ids:
                resolved_spans.append(span)
        resolved_spans.extend(new_spans)

        # 6. Create resolved routes
        resolved_routes = FieldRouteIR(
            identity=resolved_routes_data.get("identity", []),
            audience=resolved_routes_data.get("audience", []),
            rules=resolved_routes_data.get("rules", []),
            domain=resolved_routes_data.get("domain", []),
            integrations=resolved_routes_data.get("integrations", []),
            behavior=resolved_routes_data.get("behavior", []),
        )

        # 7. Validate no overlap in resolved routes
        overlaps = resolved_routes.validate_no_overlap()
        if overlaps:
            self.logger.warning("Overlapping spans in resolved routes: %s", overlaps)

        # 8. Log resolution summary
        self.logger.info(
            "Ambiguity resolution complete: %d original spans -> %d resolved spans",
            len(spans),
            len(resolved_spans),
        )

        # 9. Save checkpoint
        self.save_checkpoint({
            "original_spans_count": len(spans),
            "resolved_spans_count": len(resolved_spans),
            "resolved_spans": [s.to_dict() for s in resolved_spans],
            "resolved_routes": asdict(resolved_routes),
            "overlaps": overlaps,
        })

        return resolved_spans, resolved_routes
