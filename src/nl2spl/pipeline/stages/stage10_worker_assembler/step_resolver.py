"""Step resolution methods for Stage 10 WorkerAssembler."""

from __future__ import annotations

from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.resource_registry_ir import ResourceRegistryIR


class StepResolverMixin:
    """Mixin class containing step resolution methods for WorkerAssembler."""

    def _find_invoke_step_for_candidate(
        self,
        steps: list[StepIR],
        candidate_spans: list[str],
    ) -> StepIR | None:
        """Find the INVOKE_WORKER step backed by the delegation candidate."""
        candidate_span_set = set(candidate_spans)
        for step in steps:
            if step.command_type != "INVOKE_WORKER":
                continue
            if candidate_span_set.intersection(step.source_span_ids):
                return step
        return None

    def _find_invoke_step_by_worker_name(
        self,
        steps: list[StepIR],
        worker_name: str,
    ) -> StepIR | None:
        for step in steps:
            if step.command_type == "INVOKE_WORKER" and step.integration_ref == worker_name:
                return step
        return None

    def _is_required(self, resources: ResourceRegistryIR, variable_name: str) -> bool:
        """Look up a variable's required flag."""
        for variable in resources.variables:
            if variable.name == variable_name:
                return variable.required
        return True
