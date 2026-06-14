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

from nl2spl.ir.resource_contract_ir import ResourceContractBindingIR, ResourceKind
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.worker_plan_ir import WorkerHandoffIR

ProducerKind = Literal["step", "handoff", "api", "compiler_scaffold"]


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


class ProducerIndex:
    """Index of variable producers built from steps, handoffs, and API declarations.

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
        """
        self._producers: dict[str, list[ProducerRef]] = defaultdict(list)
        self._handoff_index = self._build_handoff_index(handoffs)
        self._known_child_worker_ids = known_child_worker_ids or set()
        self._resource_kind_by_name = self._build_resource_kind_lookup(
            resource_contract_bindings,
        )
        steps = steps or []
        declared = declared_apis or set()
        extra = extra_api_names or set()
        api_refs = api_handoff_refs or {}

        # 1. Step producers — skip CALL_API and handoff-backed steps.
        #    CALL_API is handled in section 3.  Handoff-backed steps are
        #    NOT trusted for output production because the gate requires
        #    step.outputs to match handoff.output_bindings exactly and
        #    blocks the entire step on mismatch.
        for step in steps:
            if step.command_type == "CALL_API":
                continue
            if step.handoff_id is not None:
                self._add_structured_handoff_producer(
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

        # 2. Handoff output bindings — the authoritative producer for
        #    handoff-backed variables.  A handoff binding is renderable
        #    only when the handoff itself passes the same checks the gate
        #    would apply (target worker, IO bindings, API evidence).
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

        # 3. CALL_API steps with declared API evidence.
        #    When the step carries a handoff_id the API must be declared
        #    via that handoff's api_ref — no fallback to the global registry.
        for step in steps:
            if step.command_type != "CALL_API":
                continue
            api_ref = step.integration_ref
            if not api_ref:
                continue
            step_renderable = _step_is_renderable(step, self._handoff_index)
            api_declared = self._api_is_declared(api_ref, declared, extra, api_refs, step)
            if step_renderable and api_declared:
                for output in step.outputs:
                    self._producers[output].append(
                        ProducerRef(
                            variable_name=output,
                            producer_kind="api",
                            producer_ref=step.step_id,
                            source_span_ids=list(step.source_span_ids),
                            renderable=True,
                            resource_kind=self._resource_kind_for_output(output),
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
        return {name for name, refs in self._producers.items()
                if any(ref.renderable for ref in refs)}

    def find_unproduced(self, required_outputs: list[str]) -> list[str]:
        """Return required outputs that lack a renderable producer."""
        return [name for name in required_outputs if not self.is_produced(name)]

    def _add_structured_handoff_producer(
        self,
        step: StepIR,
        declared: set[str],
        extra: set[str],
        api_refs: dict[str, str],
    ) -> None:
        """Index legacy structured results that faithfully wrap handoff outputs."""
        if not step.handoff_id:
            return
        handoff = self._handoff_index.get(step.handoff_id)
        if handoff is None:
            return

        aggregation = step.metadata.get("structured_aggregation")
        if not isinstance(aggregation, dict):
            return

        result_name = aggregation.get("result_name")
        original_outputs = aggregation.get("original_outputs") or []
        expected_outputs = [
            binding.parent_variable
            for binding in handoff.output_bindings
        ]
        if (
            not result_name
            or len(step.outputs) != 1
            or step.outputs[0] != result_name
            or list(original_outputs) != expected_outputs
        ):
            return

        renderable = (
            _step_is_renderable(step, self._handoff_index)
            and self._handoff_renderable(handoff, declared, extra, api_refs)
        )
        self._producers[result_name].append(
            ProducerRef(
                variable_name=result_name,
                producer_kind="handoff",
                producer_ref=step.handoff_id,
                source_span_ids=list(step.source_span_ids),
                renderable=renderable,
                resource_kind=self._resource_kind_for_output(result_name),
            )
        )

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
        if api_ref in extra_api_names:
            return True
        return False
