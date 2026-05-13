"""Stage 5: BlockAssembler - RegionParserMixin (_parse_control_regions)."""

from __future__ import annotations

from typing import Any

from nl2spl.ir.worker_plan_ir import ControlComplexityRegionIR


class RegionParserMixin:
    """Mixin containing control complexity region parsing."""

    def _parse_control_regions(
        self,
        regions_data: list[dict[str, Any]],
        worker_id: str | None,
    ) -> list[ControlComplexityRegionIR]:
        """Parse optional model-reported control complexity regions."""
        regions: list[ControlComplexityRegionIR] = []
        for index, item in enumerate(regions_data, start=1):
            try:
                suggested_repairs = [
                    repair
                    for repair in item.get("suggested_repairs", [])
                    if repair != "extract_child_worker"
                ]
                regions.append(
                    ControlComplexityRegionIR(
                        region_id=item.get(
                            "region_id",
                            f"ccr_{worker_id}_{index}" if worker_id else f"ccr_{index}",
                        ),
                        source_span_ids=item["source_span_ids"],
                        outer_control=self._valid_outer_control(
                            item.get("outer_control", "unknown")
                        ),
                        inner_control=self._valid_inner_control(
                            item.get("inner_control", "unknown")
                        ),
                        description=item.get("description", "Nested control intent."),
                        discovery_phase="confirmed",
                        severity=self._valid_severity(item.get("severity", "warning")),
                        can_flatten=item.get("can_flatten", False),
                        can_merge_condition=item.get("can_merge_condition", False),
                        can_lift_guard=item.get("can_lift_guard", False),
                        suggested_repairs=suggested_repairs,
                    )
                )
            except (KeyError, TypeError, ValueError) as e:
                self.logger.warning("Skipping invalid control complexity region: %s", e)
        return regions
