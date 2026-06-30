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
from nl2spl.compiler.evidence import StepEvidence, classify_step_evidence
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
                    if field.required is False:  # explicitly optional → skip
                        continue
                    rq = getattr(field, "requiredness", None)
                    if rq == "unspecified" and field.required is not True:
                        # B5: unspecified + not-legacy-required → skip
                        # legacy ContractFieldIR(required=True) → still check producer
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
                if variable.required is False or variable.source != "output":
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
        # B5: prefer DemandView; fall back to ResourceContractPlanIR (migration shim).
        demand_view = context.metadata.get("demand_view")
        demands: list[object] = []
        if demand_view is not None:
            demands = list(getattr(demand_view, "valid_demands", lambda: [])())
        else:
            resource_contract_plan = context.metadata.get("resource_contract_plan")
            if isinstance(resource_contract_plan, ResourceContractPlanIR):
                demands = list(resource_contract_plan.demands)
        bindings = self._get_bindings(context)
        for demand in demands:
            demand_id = getattr(demand, "demand_id", "")
            matching_bindings = [
                b for b in bindings if b.contract_demand_id == demand_id
            ]
            instances.append(ConstructInstance(
                construct_id=f"resource_contract_demand:{demand_id}",
                construct_type="RESOURCE_CONTRACT_DEMAND",
                materialized=len(matching_bindings) > 0,
                source_demanded=True,
                primary_parent_id=None,
                construct_path=("resource_contract", demand_id),
                source_span_ids=list(getattr(demand, "source_span_ids", [])),
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
        declared_apis = self._declared_api_names(context, resources)
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

    @staticmethod
    def _demand_attr(demand: object, attr: str, default: object = None) -> object:
        """Read an attribute from either ResourceContractDemandIR or DemandViewDemand."""
        return getattr(demand, attr, default)

    def _check_resource_contract_demand(
        self,
        instance: ConstructInstance,
        irs: ConstructIRS,
        context: IRSCheckContext,
    ) -> ConstructSatisfactionReport:
        demand: object = instance.metadata["demand"]
        demand_id = str(self._demand_attr(demand, "demand_id", ""))
        direction = str(self._demand_attr(demand, "direction", "output"))
        requiredness = str(self._demand_attr(demand, "requiredness", "unspecified"))
        demand_required = self._demand_attr(demand, "required", None)
        evidence_text = str(self._demand_attr(demand, "evidence_text", ""))
        source_span_ids = list(self._demand_attr(demand, "source_span_ids", []))
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
                diagnostic_required_for=demand_id,
                diagnostic_blocks_rendering=False,
                explanation=(
                    f"Resource contract demand '{demand_id}' "
                    f"({direction}, requiredness={requiredness}) "
                    f"has no materialized resource. "
                    f"Evidence: \"{evidence_text[:120]}\""
                ),
                suggested_resolution=(
                    "Ensure a Stage 6 resource_contracts entry references "
                    f"demand_id '{demand_id}'."
                ),
            )

        # Slot 2: registry consistency
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
                diagnostic_required_for=demand_id,
                diagnostic_blocks_rendering=False,
                explanation=(
                    f"Resource contract demand '{demand_id}' has "
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

        # Slot 3: producer — tri-state requiredness (B5).
        producer_spec = irs.get_slot("producer")
        producer = SlotSatisfaction(
            slot_name="producer",
            status="satisfied",
        )
        if direction == "output" and requiredness == "required" and matching_bindings:
            index = ProducerIndex(
                steps=self._all_steps(worker),
                handoffs=worker_plan.handoffs if worker_plan else None,
                declared_apis=self._declared_api_names(context, resources),
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
                    diagnostic_required_for=demand_id,
                    diagnostic_blocks_rendering=False,
                    explanation=(
                        f"Resource contract output '{demand_id}' "
                        f"(requiredness={requiredness}) has materialized "
                        f"resource(s) {', '.join(b.resource_name for b in matching_bindings)} "
                        "but no renderable producer."
                    ),
                    suggested_resolution=(
                        "Add a source-backed step or handoff that produces the "
                        "materialized resource name with the same resource kind."
                    ),
                )
        elif direction == "output" and requiredness == "unspecified" and matching_bindings:
            # B5: unspecified output → check producers, warn if missing.
            index = ProducerIndex(
                steps=self._all_steps(worker),
                handoffs=worker_plan.handoffs if worker_plan else None,
                declared_apis=self._declared_api_names(context, resources),
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
                # B5: unspecified output without producer → satisfied slot
                # but with a warning diagnostic.
                producer = SlotSatisfaction(
                    slot_name="producer",
                    status="satisfied",
                    diagnostic_kind="unspecified_output_missing_producer",
                    diagnostic_required_for=demand_id,
                    diagnostic_blocks_rendering=False,
                    explanation=(
                        f"Resource contract output '{demand_id}' "
                        f"has requiredness=unspecified and no renderable producer. "
                        f"Review whether this output should be declared optional "
                        f"or a producer step should be added."
                    ),
                    suggested_resolution=(
                        "Either add a producer step, or mark this output as "
                        "optional in the source requirement."
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
            source_span_ids=list(source_span_ids),
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
        declared_apis = self._declared_api_names(context, resources)
        extra_api_names = self._collect_extra_api_names(worker_plan)
        api_handoff_refs = self._build_api_handoff_refs(worker_plan)
        # None → no handoff index available (compat mode).
        # set (possibly empty) → index explicitly present.
        if worker_plan is not None:
            _handoff_ids = {h.handoff_id for h in worker_plan.handoffs}
        else:
            _handoff_ids = None
        handoff_index = {
            h.handoff_id: h
            for h in (worker_plan.handoffs if worker_plan else [])
        }
        child_worker_names = self._child_worker_names(worker_plan)
        worker_by_id = self._worker_id_to_name(worker_plan)

        if step.command_type == "CALL_API":
            return self._check_call_api(
                instance, step, irs,
                declared_apis=declared_apis,
                extra_api_names=extra_api_names,
                api_handoff_refs=api_handoff_refs,
                valid_handoff_ids=_handoff_ids,
            )
        if step.command_type == "INVOKE_WORKER":
            return self._check_invoke_worker(
                instance, step, irs,
                handoff_index=handoff_index,
                child_worker_names=child_worker_names,
                worker_by_id=worker_by_id,
                valid_handoff_ids=_handoff_ids,
            )
        if step.command_type == "REQUEST_INPUT":
            return self._check_request_input(instance, step, irs, _handoff_ids)
        return self._check_general_command(instance, step, irs, _handoff_ids)

    @staticmethod
    def _check_general_command(
        instance: ConstructInstance,
        step: StepIR,
        irs: ConstructIRS,
        valid_handoff_ids: set[str] | None,
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
        valid_handoff_ids: set[str] | None,
    ) -> ConstructSatisfactionReport:
        """Check REQUEST_INPUT with layered evidence+structure separation (U1).

        Evidence and structure are independent axes:
        * ``prompt_text`` — satisfied when ``step.text`` is non-empty (structural).
        * ``value_target`` — satisfied when ``step.outputs`` is non-empty (structural).
        * ``source_evidence`` — satisfied via the unified evidence model.

        ``user_confirmed_repair`` satisfies the evidence slot but never
        compensates for missing structural slots.
        """
        prompt_spec = irs.get_slot("prompt_text")
        value_spec = irs.get_slot("value_target")

        has_prompt_text = bool(step.text and step.text.strip())
        has_value_target = bool(step.outputs)

        prompt = SlotSatisfaction(
            slot_name="prompt_text",
            status="satisfied" if has_prompt_text else "missing",
            source_span_ids=list(step.source_span_ids),
            diagnostic_kind=None if has_prompt_text else (
                prompt_spec.missing_diagnostic
                if prompt_spec else "assumed_command_not_renderable"
            ),
            diagnostic_required_for=step.step_id,
            diagnostic_blocks_rendering=True,
            explanation=None if has_prompt_text else (
                f"Step '{step.step_id}' has no prompt text."
            ),
        )
        value_target = SlotSatisfaction(
            slot_name="value_target",
            status="satisfied" if has_value_target else "missing",
            source_span_ids=list(step.source_span_ids),
            diagnostic_kind=None if has_value_target else (
                value_spec.missing_diagnostic
                if value_spec else "type_or_contract_ambiguity"
            ),
            diagnostic_required_for=step.step_id,
            diagnostic_blocks_rendering=False,
            explanation=None if has_value_target else (
                "REQUEST_INPUT step has no value target (outputs)."
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

        renderable = has_prompt_text and has_value_target and evidence.status != "missing"
        return PostNormalizeIRSCheckerV6._step_report(
            instance,
            step,
            [prompt, value_target, evidence],
            renderable,
        )

    @staticmethod
    def _check_call_api(
        instance: ConstructInstance,
        step: StepIR,
        irs: ConstructIRS,
        declared_apis: set[str],
        extra_api_names: set[str],
        api_handoff_refs: dict[str, str],
        *,
        valid_handoff_ids: set[str] | None = None,
    ) -> ConstructSatisfactionReport:
        """Check CALL_API with unified evidence model (U1+r2).

        ``valid_handoff_ids=None`` → no handoff index, compat mode.
        ``valid_handoff_ids`` is a set (possibly empty) → index present.

        * ``api_name`` — satisfied when ``integration_ref`` is declared (structural).
        * ``call_action`` — satisfied when ``step.text`` is non-empty AND evidence
          satisfied via ``classify_step_evidence`` (validating handoffs against
          ``valid_handoff_ids``, NOT treating any handoff_id as valid).

        ``user_confirmed_repair`` satisfies evidence but never compensates for
        missing integration_ref or undeclared API.
        """
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

        # call_action: structural (has text) AND evidence satisfied
        has_call_text = bool(step.text and step.text.strip())
        # Use unified evidence model — validates handoff against valid_handoff_ids.
        # None → compat (no index); set (possibly empty) → explicit index.
        evidence = PostNormalizeIRSCheckerV6._confirmed_evidence(
            step,
            valid_handoff_ids=valid_handoff_ids,
        )
        has_call_action = has_call_text and evidence.satisfied

        call_explanation: str | None = None
        if not has_call_action:
            if not has_call_text:
                call_explanation = "CALL_API has no call action text."
            elif not evidence.satisfied:
                call_explanation = (
                    "CALL_API has no valid source-span, handoff, or user-confirmed evidence."
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
                status="satisfied" if has_call_action else "missing",
                source_span_ids=list(step.source_span_ids),
                diagnostic_kind=None if has_call_action else (
                    action_spec.missing_diagnostic
                    if action_spec else "type_or_contract_ambiguity"
                ),
                diagnostic_required_for=step.step_id,
                diagnostic_blocks_rendering=True,
                explanation=call_explanation,
            ),
        ]
        renderable = not api_missing and has_call_action
        return PostNormalizeIRSCheckerV6._step_report(instance, step, slots, renderable)

    @staticmethod
    def _check_invoke_worker(
        instance: ConstructInstance,
        step: StepIR,
        irs: ConstructIRS,
        *,
        handoff_index: dict[str, object] | None = None,
        child_worker_names: set[str] | None = None,
        worker_by_id: dict[str, str] | None = None,
        valid_handoff_ids: set[str] | None = None,
    ) -> ConstructSatisfactionReport:
        """Check INVOKE_WORKER with full handoff contract validation (U1+r2).

        * ``target_worker`` — satisfied when ``integration_ref`` is present
          AND points to a declared child worker (when workers are known).
          Additionally, when the handoff is available, ``step.integration_ref``
          must match the resolved handoff's target worker name.
        * ``handoff_id`` — satisfied when ``handoff_id`` exists AND
          resolves to a handoff in ``handoff_index``.  When the handoff is
          available, ``handoff.to_worker`` must resolve to a declared child.
        * ``user_confirmed_repair`` does NOT bypass handoff contract slots.
        """
        target_spec = irs.get_slot("target_worker")
        handoff_spec = irs.get_slot("handoff_id")

        has_target_ref = bool(step.integration_ref)
        has_handoff = bool(step.handoff_id)
        handoff_valid = (
            has_handoff
            and (
                handoff_index is None
                or step.handoff_id in handoff_index
            )
        )

        # ------------------------------------------------------------------
        # Resolve the handoff object for deeper contract checks
        # ------------------------------------------------------------------
        handoff = handoff_index.get(step.handoff_id) if (
            handoff_index is not None and step.handoff_id
        ) else None

        # Handoff to_worker must resolve to a declared child
        handoff_to_worker_exists = True
        if handoff is not None:
            h_to_worker = getattr(handoff, "to_worker", None)
            if h_to_worker and worker_by_id:
                resolved_name = worker_by_id.get(h_to_worker)
                if resolved_name is None and child_worker_names:
                    # to_worker not found by id; check if it names a child directly
                    if h_to_worker not in (child_worker_names or set()):
                        handoff_to_worker_exists = False

        # step.integration_ref must match the resolved handoff target
        target_matches_handoff = True
        if handoff is not None and has_target_ref:
            h_to_worker = getattr(handoff, "to_worker", None)
            if h_to_worker and worker_by_id:
                resolved_name = worker_by_id.get(h_to_worker, h_to_worker)
                if resolved_name and resolved_name != step.integration_ref:
                    target_matches_handoff = False
                elif not resolved_name:
                    target_matches_handoff = False

        # ------------------------------------------------------------------
        # Input/output binding validation (U1+r2)
        # ------------------------------------------------------------------
        inputs_match_bindings = True
        outputs_match_bindings = True
        if handoff is not None and handoff_valid:
            input_bindings = getattr(handoff, "input_bindings", [])
            output_bindings = getattr(handoff, "output_bindings", [])
            if input_bindings:
                binding_parent_vars = {
                    getattr(ib, "parent_variable", "") for ib in input_bindings
                }
                step_inputs = set(step.inputs)
                if binding_parent_vars and not binding_parent_vars.issubset(step_inputs):
                    inputs_match_bindings = False
            if output_bindings:
                binding_parent_vars = {
                    getattr(ob, "parent_variable", "") for ob in output_bindings
                }
                step_outputs = set(step.outputs)
                if binding_parent_vars and not binding_parent_vars.issubset(step_outputs):
                    outputs_match_bindings = False

        # ------------------------------------------------------------------
        # Structural checks for target_worker
        # ------------------------------------------------------------------
        target_exists = (
            has_target_ref
            and (child_worker_names is None or step.integration_ref in child_worker_names)
        )
        target_worker_satisfied = has_target_ref and target_exists and target_matches_handoff
        # When we have the handoff, require that to_worker can be resolved
        if handoff is not None and target_worker_satisfied:
            target_worker_satisfied = handoff_to_worker_exists

        # ------------------------------------------------------------------
        # Explanations
        # ------------------------------------------------------------------
        if not has_target_ref:
            target_explanation = "INVOKE_WORKER step has no concrete worker target."
        elif not target_exists:
            target_explanation = (
                f"INVOKE_WORKER target '{step.integration_ref}' "
                "is not a declared child worker."
            )
        elif not target_matches_handoff:
            h_to_worker = getattr(handoff, "to_worker", "?") if handoff else "?"
            target_explanation = (
                f"INVOKE_WORKER target '{step.integration_ref}' "
                f"does not match handoff '{step.handoff_id}' "
                f"target worker '{h_to_worker}'."
            )
        elif not handoff_to_worker_exists:
            h_to_worker = getattr(handoff, "to_worker", "?") if handoff else "?"
            target_explanation = (
                f"INVOKE_WORKER handoff '{step.handoff_id}' "
                f"to_worker '{h_to_worker}' does not resolve to a declared child."
            )
        else:
            target_explanation = None

        if not has_handoff:
            handoff_explanation = "INVOKE_WORKER step has no handoff_id."
        elif not handoff_valid:
            handoff_explanation = (
                f"INVOKE_WORKER handoff '{step.handoff_id}' "
                "not found in worker plan."
            )
        else:
            handoff_explanation = None

        # Binding slot explanations
        binding_explanation = None
        if handoff is not None and handoff_valid:
            if not inputs_match_bindings:
                binding_explanation = (
                    f"Step inputs {step.inputs} do not cover handoff "
                    f"input_bindings parent variables."
                )
            elif not outputs_match_bindings:
                binding_explanation = (
                    f"Step outputs {step.outputs} do not cover handoff "
                    f"output_bindings parent variables."
                )

        binding_spec = irs.get_slot("input_bindings") or irs.get_slot("output_bindings")
        bindings_satisfied = inputs_match_bindings and outputs_match_bindings

        slots = [
            SlotSatisfaction(
                slot_name="target_worker",
                status="satisfied" if target_worker_satisfied else "missing",
                source_span_ids=list(step.source_span_ids),
                diagnostic_kind=None if target_worker_satisfied else (
                    target_spec.missing_diagnostic
                    if target_spec else "type_or_contract_ambiguity"
                ),
                diagnostic_required_for=step.step_id,
                diagnostic_blocks_rendering=True,
                explanation=target_explanation,
            ),
            SlotSatisfaction(
                slot_name="handoff_id",
                status="satisfied" if handoff_valid else "missing",
                diagnostic_kind=None if handoff_valid else (
                    handoff_spec.missing_diagnostic
                    if handoff_spec else "type_or_contract_ambiguity"
                ),
                diagnostic_required_for=step.step_id,
                diagnostic_blocks_rendering=True,
                explanation=handoff_explanation,
            ),
            SlotSatisfaction(
                slot_name="input_bindings",
                status="satisfied" if bindings_satisfied else "missing",
                diagnostic_kind=None if bindings_satisfied else (
                    binding_spec.missing_diagnostic
                    if binding_spec else "type_or_contract_ambiguity"
                ),
                diagnostic_required_for=step.step_id,
                diagnostic_blocks_rendering=True,
                explanation=binding_explanation,
            ),
        ]
        renderable = target_worker_satisfied and handoff_valid and bindings_satisfied
        return PostNormalizeIRSCheckerV6._step_report(
            instance,
            step,
            slots,
            renderable,
        )

    # ------------------------------------------------------------------
    # Unified evidence helpers (Phase U0 — compiler.evidence integration)
    # ------------------------------------------------------------------

    @staticmethod
    def _confirmed_evidence(
        step: StepIR,
        valid_handoff_ids: set[str] | None,
    ) -> StepEvidence:
        """Classify step evidence through the unified model.

        ``valid_handoff_ids=None`` means "no handoff index available"
        (compat mode — any handoff_id is treated as satisfied).

        ``valid_handoff_ids`` is a set means the index is explicitly
        present. An empty set means there are zero valid handoffs
        (handoffs must be validated).
        """
        return classify_step_evidence(
            step,
            valid_handoff_ids=valid_handoff_ids,
            allow_unknown_handoff_when_no_index=True,
        )

    @staticmethod
    def _source_evidence_slot_from_evidence(
        step: StepIR,
        irs: ConstructIRS,
        evidence: StepEvidence,
    ) -> SlotSatisfaction:
        """Convert unified ``StepEvidence`` to a ``SlotSatisfaction``.

        This is the IRS-specific adapter; it lives in post_normalize.py
        per the implementation plan §7.7 to keep ``compiler.evidence``
        free of IRS types.
        """
        if evidence.satisfied:
            return SlotSatisfaction(
                slot_name="source_evidence",
                status="satisfied",
                source_span_ids=list(evidence.source_span_ids),
                relation=evidence.relation or "inferred",
                explanation=evidence.explanation,
            )

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
            explanation=(
                evidence.explanation
                or f"Step '{step.step_id}' has no source-span evidence."
            ),
            suggested_resolution=(
                "Provide a source span that describes this behavior, or remove "
                "the step if the behavior is not required."
            ),
        )

    @staticmethod
    def _source_evidence_slot(
        step: StepIR,
        irs: ConstructIRS,
        valid_handoff_ids: set[str] | None,
    ) -> SlotSatisfaction:
        """Compatibility facade over the unified evidence model.

        Delegates to ``_confirmed_evidence`` + ``_source_evidence_slot_from_evidence``,
        keeping the old call signature intact for all existing callers.
        """
        evidence = PostNormalizeIRSCheckerV6._confirmed_evidence(
            step, valid_handoff_ids,
        )
        return PostNormalizeIRSCheckerV6._source_evidence_slot_from_evidence(
            step, irs, evidence,
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
        # A step is "demanded" when it has source-span evidence, a valid
        # handoff, compiler-unpack origin, or user-confirmed-repair origin.
        source_demanded = bool(
            step.source_span_ids
            or step.handoff_id is not None
            or step.metadata.get("origin") == "compiler_unpack"
            or step.metadata.get("origin") == "user_confirmed_repair"
        )
        instances.append(ConstructInstance(
            construct_id=construct_id,
            construct_type=step.command_type,
            ir_ref=step,
            materialized=True,
            source_demanded=source_demanded,
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
        renderable_resources = context.metadata.get("renderable_resource_registry_view")
        if resources is None:
            return ResourceRegistryIR()
        if not isinstance(worker_scoped, WorkerScopedResourceIR):
            return resources
        apis = (
            list(renderable_resources.apis)
            if renderable_resources is not None and hasattr(renderable_resources, "apis")
            else worker_scoped.get_all_apis()
        )
        return ResourceRegistryIR(
            variables=worker_scoped.get_all_variables(),
            apis=apis,
            files=resources.files + [
                f for wr in worker_scoped.worker_resources.values()
                for f in wr.files
            ],
            types=resources.types,
        )

    @staticmethod
    def _declared_api_names(
        context: IRSCheckContext,
        resources: ResourceRegistryIR,
    ) -> set[str]:
        renderable_resources = context.metadata.get(
            "renderable_resource_registry_view"
        )
        if renderable_resources is not None and hasattr(renderable_resources, "api_names"):
            return set(renderable_resources.api_names)
        if hasattr(resources, "api_reports") and hasattr(resources, "api_names"):
            return set(resources.api_names)
        return set()

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
    def _child_worker_names(worker_plan: WorkerPlanIR | None) -> set[str]:
        """Return the set of declared child worker names from the plan."""
        if worker_plan is None:
            return set()
        return {
            w.worker_name
            for w in worker_plan.workers
            if w.worker_id != worker_plan.main_worker_id
            and w.boundary_kind != "main_worker"
            and w.boundary_kind != "not_a_worker"
        }

    @staticmethod
    def _worker_id_to_name(worker_plan: WorkerPlanIR | None) -> dict[str, str]:
        """Return a mapping from worker_id to worker_name."""
        if worker_plan is None:
            return {}
        return {w.worker_id: w.worker_name for w in worker_plan.workers}

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
        return False

