"""IRS v6 post-normalize checker.

This checker consumes assembled ``WorkerIR`` through
``IRSCheckContext.normalized_ir`` and emits
``ConstructSatisfactionReport`` objects; ``DiagnosticProjector`` then
produces ``CompileDiagnostic``.
"""

from __future__ import annotations

from nl2spl.compiler.construct_registry import (
    ConstructIRS,
    ConstructSatisfactionReport,
    SlotSatisfaction,
)
from nl2spl.compiler.irs.context import IRSCheckContext
from nl2spl.compiler.irs.instance import ConstructInstance
from nl2spl.compiler.producer_index import ProducerIndex
from nl2spl.ir.resource_contract_ir import (
    ResourceContractBindingIR,
    ResourceContractDemandIR,
    ResourceContractPlanIR,
)
from nl2spl.ir.resource_registry_ir import ResourceRegistryIR, WorkerScopedResourceIR
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.worker_ir import ChildWorkerIR, WorkerIR
from nl2spl.ir.worker_plan_ir import WorkerPlanIR, WorkerSpecIR


_STEP_CONSTRUCT_TYPES = {
    "GENERAL_COMMAND",
    "REQUEST_INPUT",
    "CALL_API",
    "INVOKE_WORKER",
}


class PostNormalizeIRSCheckerV6:
    """Final construct-level IRS checker for assembled IR.

    The checker uses ``ConstructIRS`` slot definitions for diagnostic kinds.
    Cross-construct facts such as producer existence are computed by helper
    indexes, but missing-slot semantics come from the registry.
    """

    checker_id = "post_normalize_v6"
    supported_construct_types = (
        "EXCEPTION_FLOW",
        "REQUIRED_OUTPUT",
        "RESOURCE_CONTRACT_DEMAND",
        "GENERAL_COMMAND",
        "REQUEST_INPUT",
        "CALL_API",
        "INVOKE_WORKER",
    )
    supported_stages = ("post_normalize",)

    def extract_instances(self, context: IRSCheckContext) -> list[ConstructInstance]:
        worker = self._worker_from_context(context)
        if worker is None:
            return []

        instances: list[ConstructInstance] = []
        worker_plan = context.worker_plan
        main_worker_id = worker_plan.main_worker_id if worker_plan else None

        # Exception flows: main worker + child workers.
        for exc_flow in worker.exception_flows:
            construct_id = (
                f"worker:{main_worker_id}.exception_flow:{exc_flow.flow_id}"
                if main_worker_id else f"exception_flow:{exc_flow.flow_id}"
            )
            instances.append(ConstructInstance(
                construct_id=construct_id,
                construct_type="EXCEPTION_FLOW",
                ir_ref=exc_flow,
                materialized=True,
                source_demanded=True,
                primary_parent_id=f"worker:{main_worker_id}" if main_worker_id else None,
                construct_path=("worker", main_worker_id or "main", "exception_flows", exc_flow.flow_id),
                source_span_ids=list(exc_flow.spans),
                metadata={
                    "kind": "exception_flow",
                    "exception_flow": exc_flow,
                    "steps": list(worker.steps),
                    "worker_id": main_worker_id,
                },
            ))

        for child in worker.child_workers:
            for exc_flow in child.exception_flows:
                worker_id = child.worker_name
                instances.append(ConstructInstance(
                    construct_id=f"worker:{worker_id}.exception_flow:{exc_flow.flow_id}",
                    construct_type="EXCEPTION_FLOW",
                    ir_ref=exc_flow,
                    materialized=True,
                    source_demanded=True,
                    primary_parent_id=f"worker:{worker_id}",
                    construct_path=("worker", worker_id, "exception_flows", exc_flow.flow_id),
                    source_span_ids=list(exc_flow.spans),
                    metadata={
                        "kind": "exception_flow",
                        "exception_flow": exc_flow,
                        "steps": list(child.steps),
                        "worker_id": worker_id,
                    },
                ))

        # Required outputs: worker-scoped path uses WorkerPlanIR contracts.
        if worker_plan is not None:
            for spec in worker_plan.workers:
                for field in spec.output_contract:
                    if not field.required:
                        continue
                    instances.append(ConstructInstance(
                        construct_id=self._required_output_construct_id(
                            spec.worker_id,
                            field.name,
                            worker_plan,
                        ),
                        construct_type="REQUIRED_OUTPUT",
                        materialized=True,
                        source_demanded=True,
                        primary_parent_id=f"worker:{spec.worker_id}",
                        construct_path=("worker_plan", spec.worker_id, "output_contract", field.name),
                        metadata={
                            "kind": "required_output",
                            "worker_spec": spec,
                            "output_name": field.name,
                            "output_description": field.description,
                        },
                    ))
        else:
            resources = self._merged_resources(context)
            for variable in resources.variables:
                if not (variable.required and variable.source == "output"):
                    continue
                instances.append(ConstructInstance(
                    construct_id=f"variable:{variable.name}",
                    construct_type="REQUIRED_OUTPUT",
                    materialized=True,
                    source_demanded=True,
                    construct_path=("resources", "variables", variable.name),
                    metadata={
                        "kind": "required_output",
                        "output_name": variable.name,
                        "output_description": variable.description,
                    },
                ))

        # Resource contract demands: check materialization against source demands.
        resource_contract_plan = context.metadata.get("resource_contract_plan")
        if isinstance(resource_contract_plan, ResourceContractPlanIR):
            bindings = self._get_bindings(context)
            for demand in resource_contract_plan.demands:
                matching_bindings = [
                    b for b in bindings if b.contract_demand_id == demand.demand_id
                ]
                instances.append(ConstructInstance(
                    construct_id=f"resource_contract_demand:{demand.demand_id}",
                    construct_type="RESOURCE_CONTRACT_DEMAND",
                    materialized=len(matching_bindings) > 0,
                    source_demanded=True,
                    primary_parent_id=None,
                    construct_path=("resource_contract", demand.demand_id),
                    source_span_ids=list(demand.source_span_ids),
                    metadata={
                        "kind": "resource_contract_demand",
                        "demand": demand,
                        "matching_bindings": matching_bindings,
                    },
                ))

        # Steps: main worker + child workers.
        for step in worker.steps:
            self._append_step_instance(instances, step, worker_id=main_worker_id)
        for child in worker.child_workers:
            for step in child.steps:
                self._append_step_instance(instances, step, worker_id=child.worker_name)

        return instances

    def check_instance(
        self,
        instance: ConstructInstance,
        irs: ConstructIRS,
        context: IRSCheckContext,
    ) -> ConstructSatisfactionReport:
        kind = instance.metadata.get("kind")
        if kind == "exception_flow":
            return self._check_exception_flow(instance, irs)
        if kind == "required_output":
            return self._check_required_output(instance, irs, context)
        if kind == "resource_contract_demand":
            return self._check_resource_contract_demand(instance, irs, context)
        if kind == "step":
            return self._check_step(instance, irs, context)
        raise ValueError(f"Unsupported post-normalize instance kind: {kind}")

    # ------------------------------------------------------------------
    # Exception flows
    # ------------------------------------------------------------------

    @staticmethod
    def _check_exception_flow(
        instance: ConstructInstance,
        irs: ConstructIRS,
    ) -> ConstructSatisfactionReport:
        exc_flow = instance.metadata["exception_flow"]
        steps = instance.metadata["steps"]
        handler_steps = [s for s in steps if s.flow_ref == exc_flow.flow_id]

        condition = SlotSatisfaction(
            slot_name="condition",
            status="satisfied" if exc_flow.condition_text else "missing",
            source_span_ids=list(exc_flow.spans),
            relation="direct" if exc_flow.spans else None,
        )

        handler_spec = irs.get_slot("handler_action")
        if handler_steps:
            handler = SlotSatisfaction(
                slot_name="handler_action",
                status="satisfied",
                source_span_ids=[
                    sid for step in handler_steps for sid in step.source_span_ids
                ],
                relation="direct",
            )
            completeness = "complete"
            frontier_status = "leaf"
            cutline_reason = None
        else:
            handler = SlotSatisfaction(
                slot_name="handler_action",
                status="missing",
                source_span_ids=list(exc_flow.spans),
                diagnostic_kind=(
                    handler_spec.missing_diagnostic
                    if handler_spec else "missing_handler"
                ),
                diagnostic_required_for=exc_flow.flow_id,
                diagnostic_blocks_rendering=False,
                explanation=(
                    f"Exception flow '{exc_flow.flow_id}' has condition "
                    "but no handler step."
                ),
                suggested_resolution=(
                    f"Add a handler step for '{exc_flow.condition_text}', "
                    "or mark this exception as acknowledged without handling."
                ),
            )
            completeness = "partial"
            frontier_status = "cutline_partial"
            cutline_reason = "missing_required_for_complete"

        return ConstructSatisfactionReport(
            construct_id=instance.construct_id,
            construct_type="EXCEPTION_FLOW",
            slots=[condition, handler],
            completeness=completeness,
            renderable=True,
            primary_parent_id=instance.primary_parent_id,
            construct_path=instance.construct_path,
            source_span_ids=list(exc_flow.spans),
            frontier_status=frontier_status,
            cutline_reason=cutline_reason,
            metadata=dict(instance.metadata),
        )

    # ------------------------------------------------------------------
    # Required outputs
    # ------------------------------------------------------------------

    def _check_required_output(
        self,
        instance: ConstructInstance,
        irs: ConstructIRS,
        context: IRSCheckContext,
    ) -> ConstructSatisfactionReport:
        output_name = instance.metadata["output_name"]
        output_desc = instance.metadata.get("output_description", output_name)
        worker_plan = context.worker_plan
        worker = self._worker_from_context(context)
        all_steps = self._all_steps(worker)
        resources = self._merged_resources(context)
        declared_apis = {api.api_name for api in resources.apis}
        extra_api_names = self._collect_extra_api_names(worker_plan)
        api_handoff_refs = self._build_api_handoff_refs(worker_plan)
        child_ids = self._child_worker_ids(worker_plan)

        if worker_plan is not None:
            worker_spec = instance.metadata["worker_spec"]
            scope_steps = self._scope_steps(worker, worker_spec)
            handoffs = [
                h for h in worker_plan.handoffs
                if h.from_worker == worker_spec.worker_id
            ] or None
            own_child_ids = {
                w.worker_id for w in worker_plan.workers
                if w.worker_id != worker_spec.worker_id
                and w.worker_id != worker_plan.main_worker_id
                and w.boundary_kind != "main_worker"
                and w.boundary_kind != "not_a_worker"
            }
            index = ProducerIndex(
                steps=scope_steps,
                handoffs=handoffs,
                declared_apis=declared_apis,
                extra_api_names=extra_api_names,
                api_handoff_refs=api_handoff_refs,
                known_child_worker_ids=own_child_ids,
                resource_contract_bindings=self._get_bindings(context),
            )
        else:
            index = ProducerIndex(
                steps=all_steps,
                handoffs=None,
                declared_apis=declared_apis,
                extra_api_names=extra_api_names,
                api_handoff_refs=api_handoff_refs,
                known_child_worker_ids=child_ids,
                resource_contract_bindings=self._get_bindings(context),
            )

        name_slot = SlotSatisfaction(
            slot_name="output_name",
            status="satisfied",
            relation="direct",
        )
        producer_spec = irs.get_slot("producer")
        if index.is_produced(output_name):
            producer = SlotSatisfaction(slot_name="producer", status="satisfied")
            completeness = "complete"
        else:
            producer = SlotSatisfaction(
                slot_name="producer",
                status="missing",
                diagnostic_kind=(
                    producer_spec.missing_diagnostic
                    if producer_spec else "missing_output_producer"
                ),
                diagnostic_required_for="complete",
                diagnostic_blocks_rendering=False,
                explanation=(
                    f"Required output '{output_name}' ({output_desc}) has "
                    "no source-backed producer step."
                ),
                suggested_resolution=(
                    f"Add a step that produces '{output_name}'. If the source "
                    "requirement does not specify how to produce this output, "
                    "mark it as optional or remove it from the output contract."
                ),
            )
            completeness = "partial"

        return ConstructSatisfactionReport(
            construct_id=instance.construct_id,
            construct_type="REQUIRED_OUTPUT",
            slots=[name_slot, producer],
            completeness=completeness,
            renderable=True,
            primary_parent_id=instance.primary_parent_id,
            construct_path=instance.construct_path,
            source_span_ids=list(instance.source_span_ids),
            frontier_status="leaf",
            metadata=dict(instance.metadata),
        )

    # ------------------------------------------------------------------
    # Resource contract demands
    # ------------------------------------------------------------------

    def _check_resource_contract_demand(
        self,
        instance: ConstructInstance,
        irs: ConstructIRS,
        context: IRSCheckContext,
    ) -> ConstructSatisfactionReport:
        demand: ResourceContractDemandIR = instance.metadata["demand"]
        matching_bindings: list[ResourceContractBindingIR] = instance.metadata[
            "matching_bindings"
        ]
        resources = self._merged_resources(context)
        worker_plan = context.worker_plan
        worker = self._worker_from_context(context)

        # Slot 1: materialization — does the demand have at least one binding?
        mat_spec = irs.get_slot("materialization")
        if matching_bindings:
            materialization = SlotSatisfaction(
                slot_name="materialization",
                status="satisfied",
                relation="direct",
            )
        else:
            materialization = SlotSatisfaction(
                slot_name="materialization",
                status="missing",
                diagnostic_kind=(
                    mat_spec.missing_diagnostic
                    if mat_spec else "missing_resource_contract"
                ),
                diagnostic_required_for=demand.demand_id,
                diagnostic_blocks_rendering=False,
                explanation=(
                    f"Resource contract demand '{demand.demand_id}' "
                    f"({demand.direction}, required={demand.required}) "
                    f"has no materialized resource. "
                    f"Evidence: \"{demand.evidence_text[:120]}\""
                ),
                suggested_resolution=(
                    "Ensure a Stage 6 resource_contracts entry references "
                    f"demand_id '{demand.demand_id}'."
                ),
            )

        # Slot 2: registry consistency — does each binding point to the
        # declared resource kind in ResourceRegistryIR?
        registry_spec = (
            irs.get_slot("resource_registry")
            or irs.get_slot("resource_kind")
        )
        missing_registry_bindings = [
            binding for binding in matching_bindings
            if not self._binding_exists_in_registry(binding, resources)
        ]
        if missing_registry_bindings:
            registry = SlotSatisfaction(
                slot_name="resource_registry",
                status="missing",
                diagnostic_kind=(
                    registry_spec.missing_diagnostic
                    if registry_spec else "resource_kind_mismatch"
                ),
                diagnostic_required_for=demand.demand_id,
                diagnostic_blocks_rendering=False,
                explanation=(
                    f"Resource contract demand '{demand.demand_id}' has "
                    "binding(s) whose resource_kind/name do not match the "
                    "materialized ResourceRegistryIR: "
                    + ", ".join(
                        f"{b.resource_kind}:{b.resource_name}"
                        for b in missing_registry_bindings
                    )
                ),
                suggested_resolution=(
                    "Ensure Stage 6 materializes every resource_contracts "
                    "binding into the matching registry collection "
                    "(variables/files/apis/types)."
                ),
            )
        else:
            registry = SlotSatisfaction(
                slot_name="resource_registry",
                status="satisfied",
                relation="direct",
            )

        # Slot 3: producer — required output demands need a renderable
        # producer of the same resource kind.  A declaration alone is not a
        # producer.
        producer_spec = irs.get_slot("producer")
        producer = SlotSatisfaction(
            slot_name="producer",
            status="satisfied",
        )
        if demand.direction == "output" and demand.required and matching_bindings:
            index = ProducerIndex(
                steps=self._all_steps(worker),
                handoffs=worker_plan.handoffs if worker_plan else None,
                declared_apis={api.api_name for api in resources.apis},
                extra_api_names=self._collect_extra_api_names(worker_plan),
                api_handoff_refs=self._build_api_handoff_refs(worker_plan),
                known_child_worker_ids=self._child_worker_ids(worker_plan),
                resource_contract_bindings=self._get_bindings(context),
            )
            produced_bindings = [
                binding for binding in matching_bindings
                if index.is_produced(
                    binding.resource_name,
                    resource_kind=binding.resource_kind,
                )
            ]
            if not produced_bindings:
                producer = SlotSatisfaction(
                    slot_name="producer",
                    status="missing",
                    diagnostic_kind=(
                        producer_spec.missing_diagnostic
                        if producer_spec else "missing_output_producer"
                    ),
                    diagnostic_required_for=demand.demand_id,
                    diagnostic_blocks_rendering=False,
                    explanation=(
                        f"Required resource contract output "
                        f"'{demand.demand_id}' has materialized resource(s) "
                        f"{', '.join(b.resource_name for b in matching_bindings)} "
                        "but no renderable producer of the matching resource kind."
                    ),
                    suggested_resolution=(
                        "Add a source-backed step or handoff that produces the "
                        "materialized resource name with the same resource kind."
                    ),
                )

        slots = [materialization, registry, producer]
        all_satisfied = all(s.status == "satisfied" for s in slots)

        return ConstructSatisfactionReport(
            construct_id=instance.construct_id,
            construct_type="RESOURCE_CONTRACT_DEMAND",
            slots=slots,
            completeness="complete" if all_satisfied else "partial",
            renderable=True,
            primary_parent_id=instance.primary_parent_id,
            construct_path=instance.construct_path,
            source_span_ids=list(demand.source_span_ids),
            frontier_status="leaf",
            metadata=dict(instance.metadata),
        )

    @staticmethod
    def _get_bindings(
        context: IRSCheckContext,
    ) -> list[ResourceContractBindingIR]:
        ws_resources = context.metadata.get("worker_scoped_resources")
        if isinstance(ws_resources, WorkerScopedResourceIR):
            return list(ws_resources.resource_contract_bindings)
        return []

    @staticmethod
    def _binding_exists_in_registry(
        binding: ResourceContractBindingIR,
        resources: ResourceRegistryIR,
    ) -> bool:
        if binding.resource_kind == "variable":
            return any(v.name == binding.resource_name for v in resources.variables)
        if binding.resource_kind == "file":
            return any(f.name == binding.resource_name for f in resources.files)
        if binding.resource_kind == "api":
            return any(api.api_name == binding.resource_name for api in resources.apis)
        if binding.resource_kind == "type":
            return any(t.type_name == binding.resource_name for t in resources.types)
        return False

    # ------------------------------------------------------------------
    # Steps
    # ------------------------------------------------------------------

    def _check_step(
        self,
        instance: ConstructInstance,
        irs: ConstructIRS,
        context: IRSCheckContext,
    ) -> ConstructSatisfactionReport:
        step: StepIR = instance.metadata["step"]
        worker_plan = context.worker_plan
        resources = self._merged_resources(context)
        declared_apis = {api.api_name for api in resources.apis}
        extra_api_names = self._collect_extra_api_names(worker_plan)
        api_handoff_refs = self._build_api_handoff_refs(worker_plan)
        valid_handoff_ids = {
            h.handoff_id for h in (worker_plan.handoffs if worker_plan else [])
        }

        if step.command_type == "CALL_API":
            return self._check_call_api(instance, step, irs, declared_apis, extra_api_names, api_handoff_refs)
        if step.command_type == "INVOKE_WORKER":
            return self._check_invoke_worker(instance, step, irs)
        if step.command_type == "REQUEST_INPUT":
            return self._check_request_input(instance, step, irs, valid_handoff_ids)
        return self._check_general_command(instance, step, irs, valid_handoff_ids)

    @staticmethod
    def _check_general_command(
        instance: ConstructInstance,
        step: StepIR,
        irs: ConstructIRS,
        valid_handoff_ids: set[str],
    ) -> ConstructSatisfactionReport:
        action = SlotSatisfaction(
            slot_name="action_text",
            status="satisfied",
            source_span_ids=list(step.source_span_ids),
            relation="direct" if step.source_span_ids else None,
        )
        evidence = PostNormalizeIRSCheckerV6._source_evidence_slot(
            step,
            irs,
            valid_handoff_ids,
        )
        renderable = evidence.status != "missing"
        return PostNormalizeIRSCheckerV6._step_report(
            instance,
            step,
            [action, evidence],
            renderable,
        )

    @staticmethod
    def _check_request_input(
        instance: ConstructInstance,
        step: StepIR,
        irs: ConstructIRS,
        valid_handoff_ids: set[str],
    ) -> ConstructSatisfactionReport:
        prompt_spec = irs.get_slot("prompt_text")
        value_spec = irs.get_slot("value_target")
        source_backed = bool(step.source_span_ids)
        prompt = SlotSatisfaction(
            slot_name="prompt_text",
            status="satisfied" if source_backed else "missing",
            source_span_ids=list(step.source_span_ids),
            diagnostic_kind=None if source_backed else (
                prompt_spec.missing_diagnostic
                if prompt_spec else "assumed_command_not_renderable"
            ),
            diagnostic_required_for=step.step_id,
            diagnostic_blocks_rendering=True,
            explanation=None if source_backed else (
                f"Step '{step.step_id}' has no source-span evidence."
            ),
        )
        value_target = SlotSatisfaction(
            slot_name="value_target",
            status="satisfied" if source_backed else "missing",
            source_span_ids=list(step.source_span_ids),
            diagnostic_kind=None if source_backed else (
                value_spec.missing_diagnostic
                if value_spec else "type_or_contract_ambiguity"
            ),
            diagnostic_required_for=step.step_id,
            diagnostic_blocks_rendering=False,
            explanation=None if source_backed else (
                "REQUEST_INPUT step has no source-span evidence -- "
                "may be an assumed interaction."
            ),
        )
        evidence = PostNormalizeIRSCheckerV6._source_evidence_slot(
            step,
            irs,
            valid_handoff_ids,
        )
        # prompt_text already carries the assumed-command diagnostic for this
        # construct; keep the cross-cutting evidence slot non-diagnostic here.
        if prompt.diagnostic_kind:
            evidence.diagnostic_kind = None
        return PostNormalizeIRSCheckerV6._step_report(
            instance,
            step,
            [prompt, value_target, evidence],
            source_backed,
        )

    @staticmethod
    def _check_call_api(
        instance: ConstructInstance,
        step: StepIR,
        irs: ConstructIRS,
        declared_apis: set[str],
        extra_api_names: set[str],
        api_handoff_refs: dict[str, str],
    ) -> ConstructSatisfactionReport:
        api_spec = irs.get_slot("api_name")
        action_spec = irs.get_slot("call_action")
        has_api = bool(step.integration_ref)
        declared = (
            has_api
            and PostNormalizeIRSCheckerV6._call_api_is_declared(
                step,
                declared_apis,
                extra_api_names,
                api_handoff_refs,
            )
        )
        api_missing = not has_api or not declared
        api_explanation = (
            "CALL_API step has no integration_ref (API name)."
            if not has_api else
            f"CALL_API references undeclared API '{step.integration_ref}'."
            if not declared else None
        )
        slots = [
            SlotSatisfaction(
                slot_name="api_name",
                status="satisfied" if not api_missing else "missing",
                source_span_ids=list(step.source_span_ids),
                diagnostic_kind=None if not api_missing else (
                    api_spec.missing_diagnostic
                    if api_spec else "type_or_contract_ambiguity"
                ),
                diagnostic_required_for=step.step_id,
                diagnostic_blocks_rendering=True,
                explanation=api_explanation,
            ),
            SlotSatisfaction(
                slot_name="call_action",
                status="satisfied" if step.source_span_ids else "missing",
                source_span_ids=list(step.source_span_ids),
                diagnostic_kind=None if step.source_span_ids else (
                    action_spec.missing_diagnostic
                    if action_spec else "type_or_contract_ambiguity"
                ),
                diagnostic_required_for=step.step_id,
                diagnostic_blocks_rendering=True,
                explanation=None if step.source_span_ids else (
                    "CALL_API has no source-span evidence for executable call action."
                ),
            ),
        ]
        renderable = not api_missing and bool(step.source_span_ids)
        return PostNormalizeIRSCheckerV6._step_report(instance, step, slots, renderable)

    @staticmethod
    def _check_invoke_worker(
        instance: ConstructInstance,
        step: StepIR,
        irs: ConstructIRS,
    ) -> ConstructSatisfactionReport:
        target_spec = irs.get_slot("target_worker")
        handoff_spec = irs.get_slot("handoff_id")
        slots = [
            SlotSatisfaction(
                slot_name="target_worker",
                status="satisfied" if step.integration_ref else "missing",
                source_span_ids=list(step.source_span_ids),
                diagnostic_kind=None if step.integration_ref else (
                    target_spec.missing_diagnostic
                    if target_spec else "type_or_contract_ambiguity"
                ),
                diagnostic_required_for=step.step_id,
                diagnostic_blocks_rendering=True,
                explanation=None if step.integration_ref else (
                    "INVOKE_WORKER step has no concrete worker target."
                ),
            ),
            SlotSatisfaction(
                slot_name="handoff_id",
                status="satisfied" if step.handoff_id else "missing",
                diagnostic_kind=None if step.handoff_id else (
                    handoff_spec.missing_diagnostic
                    if handoff_spec else "type_or_contract_ambiguity"
                ),
                diagnostic_required_for=step.step_id,
                diagnostic_blocks_rendering=True,
                explanation=None if step.handoff_id else (
                    "INVOKE_WORKER step has no handoff_id."
                ),
            ),
        ]
        return PostNormalizeIRSCheckerV6._step_report(
            instance,
            step,
            slots,
            bool(step.integration_ref and step.handoff_id),
        )

    @staticmethod
    def _source_evidence_slot(
        step: StepIR,
        irs: ConstructIRS,
        valid_handoff_ids: set[str],
    ) -> SlotSatisfaction:
        if step.source_span_ids:
            return SlotSatisfaction(
                slot_name="source_evidence",
                status="satisfied",
                source_span_ids=list(step.source_span_ids),
                relation="direct",
            )
        if step.handoff_id is not None and step.handoff_id in valid_handoff_ids:
            return SlotSatisfaction(slot_name="source_evidence", status="satisfied")
        if step.handoff_id is not None and not valid_handoff_ids:
            return SlotSatisfaction(slot_name="source_evidence", status="satisfied")
        if step.metadata.get("origin") == "compiler_unpack":
            return SlotSatisfaction(slot_name="source_evidence", status="satisfied")

        evidence_spec = irs.get_slot("source_evidence")
        return SlotSatisfaction(
            slot_name="source_evidence",
            status="missing",
            diagnostic_kind=(
                evidence_spec.missing_diagnostic
                if evidence_spec else "assumed_command_not_renderable"
            ),
            diagnostic_required_for=step.step_id,
            diagnostic_blocks_rendering=True,
            explanation=f"Step '{step.step_id}' has no source-span evidence.",
            suggested_resolution=(
                "Provide a source span that describes this behavior, or remove "
                "the step if the behavior is not required."
            ),
        )

    @staticmethod
    def _step_report(
        instance: ConstructInstance,
        step: StepIR,
        slots: list[SlotSatisfaction],
        renderable: bool,
    ) -> ConstructSatisfactionReport:
        return ConstructSatisfactionReport(
            construct_id=instance.construct_id,
            construct_type=instance.construct_type,
            slots=slots,
            completeness="complete" if renderable else "partial",
            renderable=renderable,
            primary_parent_id=instance.primary_parent_id,
            construct_path=instance.construct_path,
            source_span_ids=list(step.source_span_ids),
            frontier_status="leaf",
            metadata=dict(instance.metadata),
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _worker_from_context(context: IRSCheckContext) -> WorkerIR | None:
        worker = context.normalized_ir
        return worker if isinstance(worker, WorkerIR) else None

    @staticmethod
    def _append_step_instance(
        instances: list[ConstructInstance],
        step: StepIR,
        worker_id: str | None,
    ) -> None:
        if step.command_type not in _STEP_CONSTRUCT_TYPES:
            return
        construct_id = (
            f"worker:{worker_id}.step:{step.step_id}"
            if worker_id else f"step:{step.step_id}"
        )
        instances.append(ConstructInstance(
            construct_id=construct_id,
            construct_type=step.command_type,
            ir_ref=step,
            materialized=True,
            source_demanded=bool(step.source_span_ids),
            primary_parent_id=f"worker:{worker_id}" if worker_id else None,
            construct_path=("worker", worker_id or "main", "steps", step.step_id),
            source_span_ids=list(step.source_span_ids),
            metadata={"kind": "step", "step": step, "worker_id": worker_id},
        ))

    @staticmethod
    def _all_steps(worker: WorkerIR | None) -> list[StepIR]:
        if worker is None:
            return []
        steps = list(worker.steps)
        for child in worker.child_workers:
            steps.extend(child.steps)
        return steps

    @staticmethod
    def _scope_steps(worker: WorkerIR | None, spec: WorkerSpecIR) -> list[StepIR]:
        if worker is None:
            return []
        if spec.worker_name == worker.worker_name or spec.worker_id == worker.worker_name:
            return list(worker.steps)
        if spec.boundary_kind == "main_worker":
            return list(worker.steps)
        for child in worker.child_workers:
            if child.worker_name in {spec.worker_name, spec.worker_id}:
                return list(child.steps)
        return []

    @staticmethod
    def _merged_resources(context: IRSCheckContext) -> ResourceRegistryIR:
        resources = context.resources
        worker_scoped = context.metadata.get("worker_scoped_resources")
        if resources is None:
            return ResourceRegistryIR()
        if not isinstance(worker_scoped, WorkerScopedResourceIR):
            return resources
        return ResourceRegistryIR(
            variables=worker_scoped.get_all_variables(),
            apis=worker_scoped.get_all_apis(),
            files=resources.files + [
                f for wr in worker_scoped.worker_resources.values()
                for f in wr.files
            ],
            types=resources.types,
        )

    @staticmethod
    def _required_output_construct_id(
        worker_id: str,
        output_name: str,
        worker_plan: WorkerPlanIR,
    ) -> str:
        if worker_id != worker_plan.main_worker_id:
            return f"worker:{worker_id}.output:{output_name}"
        return f"worker:{worker_plan.main_worker_id}.output:{output_name}"

    @staticmethod
    def _child_worker_ids(worker_plan: WorkerPlanIR | None) -> set[str]:
        if worker_plan is None:
            return set()
        return {
            w.worker_id for w in worker_plan.workers
            if w.worker_id != worker_plan.main_worker_id
            and w.boundary_kind != "main_worker"
            and w.boundary_kind != "not_a_worker"
        }

    @staticmethod
    def _collect_extra_api_names(worker_plan: WorkerPlanIR | None) -> set[str]:
        if worker_plan is None:
            return set()
        return {
            h.api_ref for h in worker_plan.handoffs
            if h.mode == "api_call" and h.api_ref
        }

    @staticmethod
    def _build_api_handoff_refs(worker_plan: WorkerPlanIR | None) -> dict[str, str]:
        if worker_plan is None:
            return {}
        return {
            h.handoff_id: h.api_ref for h in worker_plan.handoffs
            if h.mode == "api_call" and h.api_ref
        }

    @staticmethod
    def _call_api_is_declared(
        step: StepIR,
        declared_apis: set[str],
        extra_api_names: set[str],
        api_handoff_refs: dict[str, str],
    ) -> bool:
        if step.handoff_id is not None and step.handoff_id in api_handoff_refs:
            return step.integration_ref == api_handoff_refs[step.handoff_id]
        if step.integration_ref in declared_apis:
            return True
        if step.integration_ref in extra_api_names:
            return True
        return False

