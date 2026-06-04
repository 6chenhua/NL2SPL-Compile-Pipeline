"""IRS v6 Stage 7 Step Checker.

R6.3 implementation:
    - Extracts step-level instances from context.steps / context.worker_steps
    - Checks GENERAL_COMMAND, REQUEST_INPUT, CALL_API, INVOKE_WORKER
    - Skips DISPLAY_MESSAGE and unknown command types
    - Does NOT call LLM or parse raw NL
    - Does NOT modify StepIR
    - Uses DiagnosticProjector for diagnostic generation
"""

from __future__ import annotations

from nl2spl.compiler.construct_registry import (
    ConstructIRS,
    ConstructSatisfactionReport,
    SlotSatisfaction,
)
from nl2spl.compiler.irs.context import IRSCheckContext
from nl2spl.compiler.irs.graph import ConstructEdge
from nl2spl.compiler.irs.instance import ConstructInstance

# Command types that map to IRS constructs.
_SUPPORTED_COMMAND_TYPES: frozenset[str] = frozenset({
    "GENERAL_COMMAND",
    "REQUEST_INPUT",
    "CALL_API",
    "INVOKE_WORKER",
})

# Mapping from command_type to construct_type (identity for all supported).
_COMMAND_TYPE_TO_CONSTRUCT: dict[str, str] = {
    "GENERAL_COMMAND": "GENERAL_COMMAND",
    "REQUEST_INPUT": "REQUEST_INPUT",
    "CALL_API": "CALL_API",
    "INVOKE_WORKER": "INVOKE_WORKER",
}


class Stage7StepIRSChecker:
    """IRS v6 checker for step-level constructs at Stage 7.

    Supported constructs:
        - GENERAL_COMMAND: action + source evidence
        - REQUEST_INPUT: prompt + value target
        - CALL_API: api name + call action
        - INVOKE_WORKER: target worker + handoff

    Design principles:
        - Only consumes structured IR fields
        - Does not infer semantics from text
        - Does not modify context or IR
        - Does not generate new constructs
        - Uses diagnostic_kind for missing slots
    """

    checker_id = "stage7_step"
    supported_construct_types = (
        "GENERAL_COMMAND",
        "REQUEST_INPUT",
        "CALL_API",
        "INVOKE_WORKER",
    )
    supported_stages = ("stage7",)

    def extract_instances(
        self,
        context: IRSCheckContext,
    ) -> list[ConstructInstance]:
        """Extract step construct instances from context.

        Supports both legacy (context.steps tuple) and worker-scoped
        (context.worker_steps WorkerStepPlanIR) paths.

        Args:
            context: Pipeline context with steps / worker_steps

        Returns:
            List of step construct instances
        """
        instances: list[ConstructInstance] = []

        # Legacy path: context.steps (tuple of StepIR)
        if context.steps:
            for step in context.steps:
                construct_type = _COMMAND_TYPE_TO_CONSTRUCT.get(step.command_type)
                if construct_type is None:
                    continue  # DISPLAY_MESSAGE etc.
                instances.append(
                    self._make_instance(step, construct_type, worker_id=None)
                )

        # Worker-scoped path: context.worker_steps
        # Supports WorkerStepPlanIR (has .worker_steps) or plain dict
        if context.worker_steps is not None:
            if hasattr(context.worker_steps, "worker_steps"):
                items = context.worker_steps.worker_steps.items()
            elif isinstance(context.worker_steps, dict):
                items = context.worker_steps.items()
            else:
                items = []
            for worker_id, steps in items:
                for step in steps:
                    construct_type = _COMMAND_TYPE_TO_CONSTRUCT.get(step.command_type)
                    if construct_type is None:
                        continue
                    instances.append(
                        self._make_instance(step, construct_type, worker_id=worker_id)
                    )

        return instances

    def check_instance(
        self,
        instance: ConstructInstance,
        irs: ConstructIRS,
        context: IRSCheckContext,
    ) -> ConstructSatisfactionReport:
        """Check IRS satisfaction for a step instance.

        Dispatches to per-command-type checkers based on construct_type.

        Args:
            instance: Step construct instance
            irs: ConstructIRS for the command type
            context: Pipeline context

        Returns:
            Satisfaction report with slot-level evidence
        """
        step = instance.metadata["step_ir"]

        if instance.construct_type == "GENERAL_COMMAND":
            return self._check_general_command(instance, step, irs)
        elif instance.construct_type == "REQUEST_INPUT":
            return self._check_request_input(instance, step, irs)
        elif instance.construct_type == "CALL_API":
            return self._check_call_api(instance, step, irs)
        elif instance.construct_type == "INVOKE_WORKER":
            return self._check_invoke_worker(instance, step, irs)
        else:
            raise ValueError(f"Unsupported construct type: {instance.construct_type}")

    # ------------------------------------------------------------------
    # Per-command-type checkers
    # ------------------------------------------------------------------

    @staticmethod
    def _check_general_command(
        instance: ConstructInstance,
        step: object,
        irs: ConstructIRS,
    ) -> ConstructSatisfactionReport:
        """Check GENERAL_COMMAND slots."""
        source_backed = bool(step.source_span_ids)

        # action_text — always satisfied from step.text
        action_sat = SlotSatisfaction(
            slot_name="action_text",
            status="satisfied",
            source_span_ids=list(step.source_span_ids),
            relation="direct" if source_backed else None,
        )

        # source_evidence — required_for_complete
        evidence_spec = irs.get_slot("source_evidence")
        if source_backed:
            evidence_sat = SlotSatisfaction(
                slot_name="source_evidence",
                status="satisfied",
                source_span_ids=list(step.source_span_ids),
                relation="direct",
            )
        else:
            evidence_sat = SlotSatisfaction(
                slot_name="source_evidence",
                status="missing",
                diagnostic_kind=evidence_spec.missing_diagnostic
                or "assumed_command_not_renderable",
                explanation="Step has no source-span evidence.",
            )

        # result_variable — optional
        result_status = "satisfied" if step.outputs else "not_applicable"
        result_sat = SlotSatisfaction(slot_name="result_variable", status=result_status)

        all_ok = source_backed
        worker_id = instance.metadata.get("worker_id")
        return ConstructSatisfactionReport(
            construct_id=instance.construct_id,
            construct_type="GENERAL_COMMAND",
            slots=[action_sat, evidence_sat, result_sat],
            completeness="complete" if all_ok else "partial",
            renderable=all_ok,
            construct_path=instance.construct_path,
            source_span_ids=list(step.source_span_ids),
            frontier_status="leaf",
            related_edges=Stage7StepIRSChecker._build_step_edges(
                step, instance.construct_id, worker_id,
            ),
            metadata=instance.metadata,
        )

    @staticmethod
    def _check_request_input(
        instance: ConstructInstance,
        step: object,
        irs: ConstructIRS,
    ) -> ConstructSatisfactionReport:
        """Check REQUEST_INPUT slots."""
        source_backed = bool(step.source_span_ids)

        # prompt_text — always satisfied from step.text
        prompt_sat = SlotSatisfaction(
            slot_name="prompt_text",
            status="satisfied",
            source_span_ids=list(step.source_span_ids),
            relation="direct" if source_backed else None,
        )

        # value_target — required_for_complete
        target_spec = irs.get_slot("value_target")
        if source_backed:
            target_sat = SlotSatisfaction(
                slot_name="value_target",
                status="satisfied",
                source_span_ids=list(step.source_span_ids),
                relation="direct",
            )
        else:
            target_sat = SlotSatisfaction(
                slot_name="value_target",
                status="missing",
                diagnostic_kind=target_spec.missing_diagnostic
                or "type_or_contract_ambiguity",
                explanation=(
                    "REQUEST_INPUT step has no source-span evidence — "
                    "missing explicit ask/request/prompt signal."
                ),
            )

        all_ok = source_backed
        worker_id = instance.metadata.get("worker_id")
        return ConstructSatisfactionReport(
            construct_id=instance.construct_id,
            construct_type="REQUEST_INPUT",
            slots=[prompt_sat, target_sat],
            completeness="complete" if all_ok else "partial",
            renderable=all_ok,
            construct_path=instance.construct_path,
            source_span_ids=list(step.source_span_ids),
            frontier_status="leaf",
            related_edges=Stage7StepIRSChecker._build_step_edges(
                step, instance.construct_id, worker_id,
            ),
            metadata=instance.metadata,
        )

    @staticmethod
    def _check_call_api(
        instance: ConstructInstance,
        step: object,
        irs: ConstructIRS,
    ) -> ConstructSatisfactionReport:
        """Check CALL_API slots."""
        has_api = bool(step.integration_ref)
        has_call_action = bool(step.source_span_ids)

        slots: list[SlotSatisfaction] = []

        # api_name — required_for_complete
        api_spec = irs.get_slot("api_name")
        if has_api:
            slots.append(SlotSatisfaction(
                slot_name="api_name",
                status="satisfied",
                source_span_ids=list(step.source_span_ids),
                relation="direct" if has_call_action else None,
            ))
        else:
            slots.append(SlotSatisfaction(
                slot_name="api_name",
                status="missing",
                diagnostic_kind=api_spec.missing_diagnostic
                or "type_or_contract_ambiguity",
                explanation="CALL_API has no integration_ref (API name).",
            ))

        # call_action — required_for_complete
        action_spec = irs.get_slot("call_action")
        if has_call_action:
            slots.append(SlotSatisfaction(
                slot_name="call_action",
                status="satisfied",
                source_span_ids=list(step.source_span_ids),
                relation="direct",
            ))
        else:
            slots.append(SlotSatisfaction(
                slot_name="call_action",
                status="missing",
                diagnostic_kind=action_spec.missing_diagnostic
                or "type_or_contract_ambiguity",
                explanation=(
                    "CALL_API has no source-span evidence for "
                    "executable call action."
                ),
            ))

        # integration_evidence — satisfied if api_name present
        slots.append(SlotSatisfaction(
            slot_name="integration_evidence",
            status="satisfied" if has_api else "missing",
        ))

        # response_binding — optional
        slots.append(SlotSatisfaction(
            slot_name="response_binding",
            status="satisfied" if step.outputs else "not_applicable",
        ))

        all_ok = has_api and has_call_action
        worker_id = instance.metadata.get("worker_id")
        return ConstructSatisfactionReport(
            construct_id=instance.construct_id,
            construct_type="CALL_API",
            slots=slots,
            completeness="complete" if all_ok else "partial",
            renderable=all_ok,
            construct_path=instance.construct_path,
            source_span_ids=list(step.source_span_ids),
            frontier_status="leaf",
            related_edges=Stage7StepIRSChecker._build_step_edges(
                step, instance.construct_id, worker_id,
            ),
            metadata=instance.metadata,
        )

    @staticmethod
    def _check_invoke_worker(
        instance: ConstructInstance,
        step: object,
        irs: ConstructIRS,
    ) -> ConstructSatisfactionReport:
        """Check INVOKE_WORKER slots."""
        has_target = bool(step.integration_ref)
        has_handoff = bool(step.handoff_id)

        slots: list[SlotSatisfaction] = []

        # target_worker — required_for_complete
        target_spec = irs.get_slot("target_worker")
        if has_target:
            slots.append(SlotSatisfaction(
                slot_name="target_worker",
                status="satisfied",
                source_span_ids=list(step.source_span_ids),
            ))
        else:
            slots.append(SlotSatisfaction(
                slot_name="target_worker",
                status="missing",
                diagnostic_kind=target_spec.missing_diagnostic
                or "type_or_contract_ambiguity",
                explanation="INVOKE_WORKER has no integration_ref (target worker).",
            ))

        # handoff_id — required_for_complete
        handoff_spec = irs.get_slot("handoff_id")
        if has_handoff:
            slots.append(SlotSatisfaction(
                slot_name="handoff_id",
                status="satisfied",
            ))
        else:
            slots.append(SlotSatisfaction(
                slot_name="handoff_id",
                status="missing",
                diagnostic_kind=handoff_spec.missing_diagnostic
                or "type_or_contract_ambiguity",
                explanation="INVOKE_WORKER has no handoff_id.",
            ))

        # input_bindings — basic check
        slots.append(SlotSatisfaction(
            slot_name="input_bindings",
            status="satisfied" if step.inputs else "not_applicable",
        ))

        # output_bindings — basic check
        slots.append(SlotSatisfaction(
            slot_name="output_bindings",
            status="satisfied" if step.outputs else "not_applicable",
        ))

        all_ok = has_target and has_handoff
        worker_id = instance.metadata.get("worker_id")
        return ConstructSatisfactionReport(
            construct_id=instance.construct_id,
            construct_type="INVOKE_WORKER",
            slots=slots,
            completeness="complete" if all_ok else "partial",
            renderable=all_ok,
            construct_path=instance.construct_path,
            source_span_ids=list(step.source_span_ids),
            frontier_status="leaf",
            related_edges=Stage7StepIRSChecker._build_step_edges(
                step, instance.construct_id, worker_id,
            ),
            metadata=instance.metadata,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_step_edges(
        step: object,
        construct_id: str,
        worker_id: str | None,
    ) -> list[ConstructEdge]:
        """Build graph edges for a step (consumes/produces/invokes/handoff)."""
        edges: list[ConstructEdge] = []
        var_prefix = (
            f"worker:{worker_id}.variable" if worker_id else "variable"
        )

        # consumes edges from inputs
        for inp in step.inputs:
            edges.append(ConstructEdge(
                from_id=construct_id,
                to_id=f"{var_prefix}:{inp}",
                edge_type="consumes",
            ))

        # produces edges from outputs
        for out in step.outputs:
            edges.append(ConstructEdge(
                from_id=construct_id,
                to_id=f"{var_prefix}:{out}",
                edge_type="produces",
            ))

        # INVOKE_WORKER specific edges
        if step.command_type == "INVOKE_WORKER":
            if step.integration_ref:
                edges.append(ConstructEdge(
                    from_id=construct_id,
                    to_id=f"child_worker:{step.integration_ref}",
                    edge_type="invokes",
                ))
            if step.handoff_id:
                edges.append(ConstructEdge(
                    from_id=construct_id,
                    to_id=f"worker_handoff:{step.handoff_id}",
                    edge_type="handoff_to",
                ))

        # CALL_API specific edges
        if step.command_type == "CALL_API" and step.integration_ref:
            edges.append(ConstructEdge(
                from_id=construct_id,
                to_id=f"api:{step.integration_ref}",
                edge_type="invokes",
            ))

        return edges

    @staticmethod
    def _make_instance(
        step: object,
        construct_type: str,
        worker_id: str | None,
    ) -> ConstructInstance:
        """Build a ConstructInstance for a StepIR."""
        step_id = step.step_id
        if worker_id:
            construct_id = f"worker:{worker_id}.step:{step_id}"
            parent_id = f"worker:{worker_id}"
            path = ("worker_step_plan", worker_id, "steps", step_id)
        else:
            construct_id = f"step:{step_id}"
            parent_id = None
            path = ("steps", step_id)

        return ConstructInstance(
            construct_id=construct_id,
            construct_type=construct_type,
            materialized=True,
            source_demanded=True,
            candidate_only=False,
            ir_ref=step,
            primary_parent_id=parent_id,
            construct_path=path,
            source_span_ids=list(step.source_span_ids),
            metadata={"step_ir": step, "worker_id": worker_id},
        )
