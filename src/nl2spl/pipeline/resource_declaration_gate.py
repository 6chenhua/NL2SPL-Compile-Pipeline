"""Resource declaration gate for renderable resource registry views.

The gate is read-only. It consumes post-normalize API_DECLARATION authority
reports and exposes only renderable API declarations to downstream rendering
and executable producer checks.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from nl2spl.compiler.constructs import ConstructSatisfactionReport
from nl2spl.ir.resource_registry_ir import APISpec, ResourceRegistryIR


@dataclass
class RenderableResourceRegistryView(ResourceRegistryIR):
    """Resource registry view with APIs filtered by ResourceDeclarationGate."""

    api_reports: dict[str, ConstructSatisfactionReport] = field(default_factory=dict)
    incomplete_api_names: set[str] = field(default_factory=set)
    blocked_api_names: set[str] = field(default_factory=set)

    @property
    def api_names(self) -> set[str]:
        return {api.api_name for api in self.apis if api.api_name}

    def to_payload(self) -> dict[str, object]:
        return {
            "api_names": sorted(self.api_names),
            "incomplete_api_names": sorted(self.incomplete_api_names),
            "blocked_api_names": sorted(self.blocked_api_names),
            "api_report_ids": sorted(self.api_reports),
        }


class ResourceDeclarationGate:
    """Build a renderable registry view from API_DECLARATION reports."""

    def apply(
        self,
        resources: ResourceRegistryIR,
        reports: Iterable[ConstructSatisfactionReport],
        *,
        authority: str = "post_normalize_irs",
    ) -> RenderableResourceRegistryView:
        """Return a read-only filtered view of renderable resources.

        Only post-normalize API_DECLARATION reports can authorize rendering.
        Stage-local reports are intentionally ignored by passing a non
        post-normalize authority.
        """
        api_reports = [
            report
            for report in reports
            if report.construct_type == "API_DECLARATION"
            and report.metadata.get("authority") == "post_normalize_irs"
        ]
        if authority != "post_normalize_irs":
            return self._view(resources, apis=[], reports={}, blocked=set())

        reports_by_key: dict[str, ConstructSatisfactionReport] = {}
        for report in api_reports:
            for key in self._report_keys(report):
                reports_by_key[key] = report

        renderable_apis: list[APISpec] = []
        accepted_reports: dict[str, ConstructSatisfactionReport] = {}
        incomplete: set[str] = set()
        blocked: set[str] = set()

        for api in resources.apis:
            report = self._lookup_report(api, reports_by_key)
            if report is None:
                blocked.add(api.api_name)
                continue
            if not self._has_required_slots(report):
                blocked.add(api.api_name)
                continue
            renderable_apis.append(api)
            accepted_reports[api.api_name] = report
            if report.completeness != "complete":
                incomplete.add(api.api_name)

        return self._view(
            resources,
            apis=renderable_apis,
            reports=accepted_reports,
            incomplete=incomplete,
            blocked=blocked,
        )

    @staticmethod
    def _view(
        resources: ResourceRegistryIR,
        *,
        apis: list[APISpec],
        reports: dict[str, ConstructSatisfactionReport],
        incomplete: set[str] | None = None,
        blocked: set[str] | None = None,
    ) -> RenderableResourceRegistryView:
        return RenderableResourceRegistryView(
            variables=list(resources.variables),
            files=list(resources.files),
            apis=list(apis),
            types=list(resources.types),
            api_reports=dict(reports),
            incomplete_api_names=set(incomplete or set()),
            blocked_api_names=set(blocked or set()),
        )

    @staticmethod
    def _has_required_slots(report: ConstructSatisfactionReport) -> bool:
        slots = {slot.slot_name: slot for slot in report.slots}
        api_name = slots.get("api_name")
        source_evidence = slots.get("source_evidence")
        return (
            report.renderable
            and report.metadata.get("grammar_validation_status")
            in {"grammar_minimal_partial", "complete"}
            and report.metadata.get("grammar_valid") is True
            and api_name is not None
            and api_name.status == "satisfied"
            and source_evidence is not None
            and source_evidence.status == "satisfied"
        )

    @staticmethod
    def _lookup_report(
        api: APISpec,
        reports_by_key: dict[str, ConstructSatisfactionReport],
    ) -> ConstructSatisfactionReport | None:
        for key in (
            api.api_id,
            api.api_name,
            f"api_declaration:{api.api_id}",
            f"api_declaration:{api.api_name}",
        ):
            if key and key in reports_by_key:
                return reports_by_key[key]
        return None

    @staticmethod
    def _report_keys(report: ConstructSatisfactionReport) -> set[str]:
        keys = {report.construct_id}
        suffix = report.construct_id.removeprefix("api_declaration:")
        if suffix:
            keys.add(suffix)
        api_id = report.metadata.get("api_id")
        api_name = report.metadata.get("api_name")
        if isinstance(api_id, str) and api_id:
            keys.add(api_id)
            keys.add(f"api_declaration:{api_id}")
        if isinstance(api_name, str) and api_name:
            keys.add(api_name)
            keys.add(f"api_declaration:{api_name}")
        if report.construct_path:
            keys.add(report.construct_path[-1])
        return keys
