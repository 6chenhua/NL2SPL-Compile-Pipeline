"""Render construct satisfaction reports into feedback/report text.

This module renders existing ConstructSatisfactionReport objects.  It does
not perform IRS checks, infer missing slots, or create diagnostics.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from nl2spl.compiler.constructs import ConstructSatisfactionReport


class ConstructSatisfactionFeedbackProjector:
    """Render stage-local construct satisfaction reports."""

    def project(
        self,
        construct_satisfaction: (
            Mapping[str, Sequence[ConstructSatisfactionReport]] | None
        ),
    ) -> list[str]:
        """Return report lines for construct satisfaction."""
        if not construct_satisfaction:
            return []

        lines: list[str] = [
            "Construct Satisfaction",
            "-" * 40,
        ]

        any_report = False
        for stage_name in sorted(construct_satisfaction):
            reports = list(construct_satisfaction.get(stage_name) or [])
            if not reports:
                continue
            any_report = True
            lines.append("")
            lines.append(f"Stage: {stage_name}")
            for report in sorted(
                reports,
                key=lambda r: (r.construct_type, r.construct_id),
            ):
                lines.extend(self._render_report(report))

        if not any_report:
            return []
        return lines

    def _render_report(self, report: ConstructSatisfactionReport) -> list[str]:
        lines = [
            (
                f"  - {report.construct_type} {report.construct_id}: "
                f"{report.completeness}; renderable={str(report.renderable).lower()}"
            )
        ]
        if report.frontier_status:
            lines.append(f"    frontier: {report.frontier_status}")
        if report.cutline_reason:
            lines.append(f"    cutline: {report.cutline_reason}")
        if report.construct_path:
            lines.append(f"    path: {' / '.join(report.construct_path)}")
        if report.source_span_ids:
            lines.append(f"    source spans: {', '.join(report.source_span_ids)}")

        missing_slots = [
            slot for slot in report.slots
            if slot.status in {"missing", "assumed"}
        ]
        if missing_slots:
            lines.append("    missing / assumed slots:")
            for slot in sorted(missing_slots, key=lambda s: s.slot_name):
                suffix = f" ({slot.explanation})" if slot.explanation else ""
                lines.append(f"      - {slot.slot_name}: {slot.status}{suffix}")

        return lines
