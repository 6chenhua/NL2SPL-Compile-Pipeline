"""ProducerIndex — determine which variables have valid renderable producers.

Used by Stage 9.5 to decide whether a required output has a source-backed
or valid-handoff-backed producer.  The index applies the same origin /
renderability rules as the executable-element gate so missing-output-producer
diagnostics are consistent with what the gate would later allow through.

Handoff-backed steps never contribute producers via ``step.outputs`` — only
the handoff's own ``output_bindings`` are trusted, because the gate requires
exact match and blocks the entire step on mismatch.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Literal

from nl2spl.ir.composite_output_plan_ir import CompositeOutputPlan
from nl2spl.ir.resource_contract_ir import ResourceContractBindingIR, ResourceKind
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.step_variable_relation_ir import (
    RequiredOutputFulfillmentState,
    StepVariableRelationPlan,
)
from nl2spl.ir.worker_plan_ir import WorkerHandoffIR

ProducerKind = Literal[
    "step",
    "handoff",
    "api",
    "compiler_scaffold",
    "field_projection",
    "handoff_field_projection",
]


@dataclass
class ProducerRef:
    """A single producer of a resource.

    Attributes:
        variable_name: The resource being produced.
        producer_kind: How the resource is produced — step, handoff, API, or
            deterministic compiler scaffolding.
        producer_ref: Identifier for the producer (step_id, handoff_id, or
            API name).
        source_span_ids: Source spans backing this producer.
        renderable: Whether this producer would pass the executable-element
            gate and be renderable in SPL.
        resource_kind: ``variable`` or ``file`` (default ``variable``).
    """

    variable_name: str
    producer_kind: ProducerKind
    producer_ref: str
    source_span_ids: list[str] = field(default_factory=list)
    renderable: bool = False
    resource_kind: ResourceKind = "variable"


def _step_is_renderable(
    step: StepIR,
    handoff_index: dict[str, WorkerHandoffIR] | None = None,
) -> bool:
    """Apply the same origin / renderability classification as the executable gate.

    A step is renderable when it has source evidence, a *valid* handoff
    backing, is deterministic compiler_unpack scaffolding, or is a
    user-confirmed repair (R6).  When a step carries a ``handoff_id`` it
    must exist in *handoff_index* and its ``command_type`` must match the
    handoff's ``mode``.
    """
    if step.source_span_ids:
        return True

    if step.handoff_id is not None:
        if handoff_index is None:
            return False
        handoff = handoff_index.get(step.handoff_id)
        if handoff is None:
            return False
        if step.command_type == "INVOKE_WORKER" and handoff.mode != "invoke":
            return False
        if step.command_type == "CALL_API" and handoff.mode != "api_call":
            return False
        return True

    if step.metadata.get("origin") == "compiler_unpack":
        return True

    # R6: user-confirmed repair steps are renderable producers.
    if step.metadata.get("origin") == "user_confirmed_repair":
        return True

    return False


def _step_origin(step: StepIR) -> ProducerKind:
    """Map a step to its producer kind for the index."""
    if step.source_span_ids:
        return "step"
    if step.handoff_id is not None:
        return "handoff"
    if step.metadata.get("origin") == "compiler_unpack":
        return "compiler_scaffold"
    return "step"  # assumed — still recorded but marked non-renderable


def _looks_like_source_evidence_output(output_name: str) -> bool:
    normalized = output_name.lower()
    return (
        "source_evidence" in normalized
        or "evidence_set" in normalized
        or normalized in {"source_evidence_set", "evidence_sources"}
    )


def _call_api_has_unknown_retrieval_response(step: StepIR) -> bool:
    if step.command_type != "CALL_API" or not step.source_span_ids:
        return False
    metadata = step.metadata or {}
    if metadata.get("api_response_binding_status") == "deferred_until_api_return_contract_known":
        return True
    functions_unknown = metadata.get("api_functions_status") in {
        "unknown_placeholder",
        "unknown",
        None,
    }
    schema_unknown = metadata.get("api_schema_status") in {
        "unknown_placeholder",
        "unknown",
        None,
    }
    if not (functions_unknown or schema_unknown):
        return False
    text = step.text.lower()
    return any(marker in text for marker in ("retrieve", "fetch", "search", "source"))


class ProducerIndex:
    """Index of variable producers built from steps, handoffs, and API declarations.

    Normalized worker-aware runs use StepVariableRelationPlan as producer
    authority. StepIR.outputs is only a compatibility fallback when no
    non-empty relation plan is supplied; CALL_API outputs remain ignored there.

    A variable is *produced* when at least one of its producers is renderable.
    Worker OUTPUTS declarations alone do NOT count — the producer must be a
    concrete step, handoff output binding, or declared API call with evidence.

    Handoff-backed steps never contribute producers via ``step.outputs``
    because the gate requires exact IO binding match.  Only the handoff's
    ``output_bindings`` are trusted for handoff-produced variables.
    """

    def __init__(
        self,
        steps: list[StepIR] | None = None,
        handoffs: list[WorkerHandoffIR] | None = None,
        declared_apis: set[str] | None = None,
        extra_api_names: set[str] | None = None,
        api_handoff_refs: dict[str, str] | None = None,
        known_child_worker_ids: set[str] | None = None,
        resource_contract_bindings: list[ResourceContractBindingIR] | None = None,
        step_variable_relation_plan: StepVariableRelationPlan | None = None,
        composite_output_plans: tuple[CompositeOutputPlan, ...] = (),
    ) -> None:
        """Build the producer index.

        Args:
            steps: StepIR list (main-worker steps, or merged across workers).
            handoffs: WorkerHandoffIR list from the worker plan.
            declared_apis: API names declared in the resource registry.
            extra_api_names: Additional API names collected from handoffs.
            api_handoff_refs: Mapping of handoff_id → api_ref for CALL_API steps.
            known_child_worker_ids: Worker IDs of *child* workers (excludes
                the main worker and ``not_a_worker`` sentinel).  When
                provided, invoke-handoff target workers must be in this set
                for the handoff to count as renderable.
            composite_output_plans: Typed authority for structured aggregate
                producer registration. Debug metadata is never producer
                authority.
        """
        self._producers: dict[str, list[ProducerRef]] = defaultdict(list)
        self._deferred_outputs: dict[str, list[str]] = defaultdict(list)
        self._implicit_evidence_deferred_refs: list[str] = []
        self._handoff_index = self._build_handoff_index(handoffs)
        self._composite_output_plans = composite_output_plans
        self._known_child_worker_ids = known_child_worker_ids or set()
        self._resource_kind_by_name = self._build_resource_kind_lookup(
            resource_contract_bindings,
        )
        self.compat_warnings: list[str] = []

        steps = steps or []
        declared = declared_apis or set()
        extra = extra_api_names or set()
        api_refs = api_handoff_refs or {}

        # 1. Determine authority mode
        relation_outputs = (
            tuple(step_variable_relation_plan.producing_relations())
            if step_variable_relation_plan
            else ()
        )
        relation_authority_mode = bool(relation_outputs)

        if relation_authority_mode:
            self.mode = "relation_authority"
        else:
            self.mode = "legacy_fallback"
            self.compat_warnings.append(
                "ProducerIndex legacy_fallback: no non-empty StepVariableRelationPlan supplied; "
                "StepIR.outputs used for compatibility."
            )

        if relation_authority_mode and step_variable_relation_plan is not None:
            # RELATION AUTHORITY MODE
            step_by_id = {step.step_id: step for step in steps}

            # Step produces
            for relation in step_variable_relation_plan.producing_relations():
                step = step_by_id.get(relation.step_id)
                if step is not None and step.command_type == "CALL_API":
                    continue
                renderable = (
                    _step_is_renderable(step, self._handoff_index) if step is not None else False
                )
                self._producers[relation.variable_name].append(
                    ProducerRef(
                        variable_name=relation.variable_name,
                        producer_kind=_step_origin(step) if step is not None else "step",
                        producer_ref=relation.step_id,
                        source_span_ids=list(relation.source_span_ids),
                        renderable=renderable,
                        resource_kind=self._resource_kind_for_output(relation.variable_name),
                    )
                )

            # CALL_API produces
            for step in steps:
                if step.command_type != "CALL_API":
                    continue
                self._record_pending_api_response_bindings(step)
                api_ref = step.integration_ref
                if not api_ref:
                    continue
                step_renderable = _step_is_renderable(step, self._handoff_index)
                api_declared = self._api_is_declared(api_ref, declared, extra, api_refs, step)
                if not (step_renderable and api_declared):
                    continue

                for relation in step_variable_relation_plan.producing_relations():
                    if relation.step_id == step.step_id:
                        self._producers[relation.variable_name].append(
                            ProducerRef(
                                variable_name=relation.variable_name,
                                producer_kind="api",
                                producer_ref=step.step_id,
                                source_span_ids=list(relation.source_span_ids),
                                renderable=True,
                                resource_kind=self._resource_kind_for_output(
                                    relation.variable_name
                                ),
                            )
                        )

        else:
            # LEGACY FALLBACK MODE
            for step in steps:
                if step.command_type == "CALL_API":
                    self._record_pending_api_response_bindings(step)
                    self.compat_warnings.append(
                        "ProducerIndex legacy_fallback: CALL_API StepIR.outputs "
                        f"ignored for {step.step_id}; API producers require a "
                        "StepVariableRelationPlan or explicit response contract."
                    )
                    continue

                if step.handoff_id is not None:
                    self._add_structured_handoff_producer_from_plan(
                        step,
                        declared,
                        extra,
                        api_refs,
                    )
                    continue

                renderable = _step_is_renderable(step, self._handoff_index)
                kind = _step_origin(step)
                for output in step.outputs:
                    self._producers[output].append(
                        ProducerRef(
                            variable_name=output,
                            producer_kind=kind,
                            producer_ref=step.step_id,
                            source_span_ids=list(step.source_span_ids),
                            renderable=renderable,
                            resource_kind=self._resource_kind_for_output(output),
                        )
                    )

        # 2. Handoff output bindings
        if handoffs:
            for handoff in handoffs:
                handoff_renderable = self._handoff_renderable(handoff, declared, extra, api_refs)
                for binding in handoff.output_bindings:
                    self._producers[binding.parent_variable].append(
                        ProducerRef(
                            variable_name=binding.parent_variable,
                            producer_kind="handoff",
                            producer_ref=handoff.handoff_id,
                            source_span_ids=[],
                            renderable=handoff_renderable,
                            resource_kind=self._resource_kind_for_output(
                                binding.parent_variable,
                            ),
                        )
                    )

    # ------------------------------------------------------------------
    # Public query methods
    # ------------------------------------------------------------------

    def is_produced(
        self,
        variable_name: str,
        resource_kind: ResourceKind | None = None,
    ) -> bool:
        """Return True when *variable_name* has at least one renderable producer.

        When *resource_kind* is provided, only count producers of that kind.
        """
        refs = self._producers.get(variable_name, [])
        if resource_kind is not None:
            refs = [r for r in refs if r.resource_kind == resource_kind]
        return any(ref.renderable for ref in refs)

    def get_producers(self, variable_name: str) -> list[ProducerRef]:
        """Return all producers (renderable and non-renderable) for *variable_name*."""
        return list(self._producers.get(variable_name, []))

    def all_produced_variables(self) -> set[str]:
        """Return the set of variable names that have at least one renderable producer."""
        return {
            name for name, refs in self._producers.items() if any(ref.renderable for ref in refs)
        }

    def find_unproduced(self, required_outputs: list[str]) -> list[str]:
        """Return required outputs that lack a renderable producer."""
        return [name for name in required_outputs if not self.is_produced(name)]

    def fulfillment_for(
        self,
        output_name: str,
        resource_kind: ResourceKind | None = None,
    ) -> RequiredOutputFulfillmentState:
        producers = [
            ref
            for ref in self.get_producers(output_name)
            if ref.renderable and (resource_kind is None or ref.resource_kind == resource_kind)
        ]
        if producers:
            return RequiredOutputFulfillmentState(
                output_name=output_name,
                status="produced",
                producer_step_ids=tuple(ref.producer_ref for ref in producers),
                reason="source_backed_producer",
            )
        deferred_refs = tuple(self._deferred_outputs.get(output_name, ()))
        if not deferred_refs and _looks_like_source_evidence_output(output_name):
            deferred_refs = tuple(self._implicit_evidence_deferred_refs)
        if deferred_refs:
            return RequiredOutputFulfillmentState(
                output_name=output_name,
                status="deferred",
                deferred_refs=deferred_refs,
                reason="api_return_contract_unknown",
            )
        return RequiredOutputFulfillmentState(
            output_name=output_name,
            status="missing",
            reason="missing_source_backed_producer",
        )

    def fulfillment_for_many(
        self,
        output_names: list[str],
    ) -> list[RequiredOutputFulfillmentState]:
        return [self.fulfillment_for(name) for name in output_names]

    def _add_structured_handoff_producer_from_plan(
        self,
        step: StepIR,
        declared: set[str],
        extra: set[str],
        api_refs: dict[str, str],
    ) -> None:
        """Index structured handoff aggregate only from typed CompositeOutputPlan."""
        if not step.handoff_id:
            return
        handoff = self._handoff_index.get(step.handoff_id)
        if handoff is None:
            return

        plan = next(
            (
                candidate
                for candidate in self._composite_output_plans
                if candidate.step_id == step.step_id
            ),
            None,
        )
        if plan is None:
            return

        original_outputs = [intent.variable_name for intent in plan.original_output_intents]
        expected_outputs = [binding.parent_variable for binding in handoff.output_bindings]
        if (
            len(step.outputs) != 1
            or step.outputs[0] != plan.composite_variable_name
            or list(original_outputs) != expected_outputs
        ):
            return

        renderable = _step_is_renderable(step, self._handoff_index) and self._handoff_renderable(
            handoff, declared, extra, api_refs
        )
        self._producers[plan.composite_variable_name].append(
            ProducerRef(
                variable_name=plan.composite_variable_name,
                producer_kind="handoff",
                producer_ref=step.handoff_id,
                source_span_ids=list(step.source_span_ids),
                renderable=renderable,
                resource_kind=self._resource_kind_for_output(plan.composite_variable_name),
            )
        )

    def _record_pending_api_response_bindings(self, step: StepIR) -> None:
        pending = step.metadata.get("pending_response_bindings")
        if not isinstance(pending, dict):
            if _call_api_has_unknown_retrieval_response(step):
                self._implicit_evidence_deferred_refs.append(step.step_id)
            return
        for value in pending.values():
            if not isinstance(value, str) or not value:
                continue
            self._deferred_outputs[value].append(step.step_id)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_handoff_index(
        handoffs: list[WorkerHandoffIR] | None,
    ) -> dict[str, WorkerHandoffIR]:
        if handoffs is None:
            return {}
        return {h.handoff_id: h for h in handoffs}

    @staticmethod
    def _build_resource_kind_lookup(
        bindings: list[ResourceContractBindingIR] | None,
    ) -> dict[str, ResourceKind]:
        result: dict[str, ResourceKind] = {}
        conflicts: set[str] = set()
        for binding in bindings or []:
            existing = result.get(binding.resource_name)
            if existing is not None and existing != binding.resource_kind:
                conflicts.add(binding.resource_name)
                continue
            result[binding.resource_name] = binding.resource_kind
        for name in conflicts:
            result.pop(name, None)
        return result

    def _resource_kind_for_output(self, output_name: str) -> ResourceKind:
        return self._resource_kind_by_name.get(output_name, "variable")

    def _handoff_renderable(
        self,
        handoff: WorkerHandoffIR,
        declared_apis: set[str],
        extra_api_names: set[str],
        api_handoff_refs: dict[str, str],
    ) -> bool:
        """Check whether a handoff's output bindings count as renderable producers.

        Mirrors the gate's handoff validation:
        - invoke: must have to_worker, must be a known child worker (when
          *known_child_worker_ids* is provided), and must have both input
          and output bindings.
        - api_call: must have a concrete api_ref declared in the API
          registry or extra names.
        """
        if handoff.mode == "invoke":
            if not handoff.to_worker:
                return False
            if self._known_child_worker_ids:
                if handoff.to_worker not in self._known_child_worker_ids:
                    return False
            # Gate also requires both input and output bindings to exist
            if not handoff.input_bindings or not handoff.output_bindings:
                return False
            return True
        if handoff.mode == "api_call":
            api_name = handoff.api_ref or api_handoff_refs.get(handoff.handoff_id)
            if api_name and (api_name in declared_apis or api_name in extra_api_names):
                return True
            return False
        return False

    def _api_is_declared(
        self,
        api_ref: str,
        declared_apis: set[str],
        extra_api_names: set[str],
        api_handoff_refs: dict[str, str],
        step: StepIR,
    ) -> bool:
        """Check whether a CALL_API step's integration_ref has valid evidence.

        When the step carries a handoff_id the evidence MUST come from the
        handoff's api_ref — the gate rejects CALL_API steps whose handoff
        has no api_ref, so a global registry fallback would mask a
        diagnostic the gate will expose later.
        """
        if step.handoff_id is not None:
            handoff = self._handoff_index.get(step.handoff_id)
            if handoff is None:
                return False
            if not handoff.api_ref:
                return False
            return api_ref == handoff.api_ref
        if api_ref in declared_apis:
            return True
        return False
