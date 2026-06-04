"""IRS v6 Stage 4 Exception Flow Checker.

R6.2 implementation:
    - Extracts EXCEPTION_FLOW instances from FlowStructureIR / WorkerFlowPlanIR
    - Checks condition slot satisfaction (source-backed vs assumed)
    - handler_action and trigger_step are not_applicable at Stage 4
    - Does NOT emit missing_handler (Stage 9.5 authority)
    - Does NOT call LLM or parse raw NL
    - Does NOT modify input IR
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

# Guard message for no-spans condition ambiguity.
_CONDITION_ASSUMED_EXPLANATION = (
    "Exception flow has condition text but no source-span evidence. "
    "The condition may be an LLM inference rather than a source-backed fact."
)


class Stage4ExceptionFlowIRSChecker:
    """IRS v6 checker for EXCEPTION_FLOW at Stage 4.

    Checks condition slot satisfaction against the EXCEPTION_FLOW
    ConstructIRS.  handler_action and trigger_step are always
    not_applicable at Stage 4 (cross-stage slots).

    Design principles:
        - Only consumes structured IR fields
        - Does not infer semantics from text
        - Does not modify context or IR
        - Does not generate new constructs
        - Uses diagnostic_kind for missing slots
        - Does NOT emit missing_handler
    """

    checker_id = "stage4_exception_flow"
    supported_construct_types = ("EXCEPTION_FLOW",)
    supported_stages = ("stage4",)

    def extract_instances(
        self,
        context: IRSCheckContext,
    ) -> list[ConstructInstance]:
        """Extract EXCEPTION_FLOW instances from context.

        Supports both legacy (FlowStructureIR via context.flow) and
        worker-scoped (WorkerFlowPlanIR via context.worker_flows) paths.

        Args:
            context: Pipeline context with flow / worker_flows

        Returns:
            List of EXCEPTION_FLOW construct instances
        """
        instances: list[ConstructInstance] = []

        # Legacy path: context.flow (FlowStructureIR)
        if context.flow is not None:
            for exc_flow in context.flow.exception_flows:
                instances.append(
                    self._make_instance(exc_flow, worker_id=None)
                )

        # Worker-scoped path: context.worker_flows
        # Supports WorkerFlowPlanIR (has .worker_flows) or plain dict
        if context.worker_flows is not None:
            if hasattr(context.worker_flows, "worker_flows"):
                items = context.worker_flows.worker_flows.items()
            elif isinstance(context.worker_flows, dict):
                items = context.worker_flows.items()
            else:
                items = []
            for worker_id, flow in items:
                for exc_flow in flow.exception_flows:
                    instances.append(
                        self._make_instance(exc_flow, worker_id=worker_id)
                    )

        return instances

    def check_instance(
        self,
        instance: ConstructInstance,
        irs: ConstructIRS,
        context: IRSCheckContext,
    ) -> ConstructSatisfactionReport:
        """Check IRS satisfaction for an EXCEPTION_FLOW instance.

        Slots:
            - condition: satisfied if condition_text + spans; assumed otherwise
            - handler_action: always not_applicable (Stage 9.5 authority)
            - trigger_step: always not_applicable (post-MVP)

        Args:
            instance: EXCEPTION_FLOW construct instance
            irs: EXCEPTION_FLOW ConstructIRS
            context: Pipeline context

        Returns:
            Satisfaction report with slot-level evidence
        """
        exc_flow = instance.metadata["exception_flow_ir"]
        condition_source_backed = bool(exc_flow.condition_text and exc_flow.spans)

        # -- condition slot ------------------------------------------------
        condition_slot_spec = irs.get_slot("condition")
        if condition_source_backed:
            condition_sat = SlotSatisfaction(
                slot_name="condition",
                status="satisfied",
                source_span_ids=list(exc_flow.spans),
                relation="direct",
            )
        else:
            condition_sat = SlotSatisfaction(
                slot_name="condition",
                status="assumed",
                source_span_ids=list(exc_flow.spans),
                relation="assumed",
                diagnostic_kind=(
                    condition_slot_spec.missing_diagnostic
                    or "type_or_contract_ambiguity"
                ),
                explanation=_CONDITION_ASSUMED_EXPLANATION,
            )

        # -- handler_action (not_applicable at Stage 4) --------------------
        handler_sat = SlotSatisfaction(
            slot_name="handler_action",
            status="not_applicable",
            explanation=(
                "handler_action is a cross-stage slot — Stage 7 / Stage 9.5 "
                "are authoritative for handler presence."
            ),
        )

        # -- trigger_step (not_applicable at Stage 4) ----------------------
        trigger_sat = SlotSatisfaction(
            slot_name="trigger_step",
            status="not_applicable",
            explanation=(
                "trigger_step is post-MVP and not assessed at Stage 4."
            ),
        )

        # -- completeness & renderability ----------------------------------
        # Always partial: handler_action is required_for_complete but
        # not assessed at Stage 4.
        completeness = "partial"
        renderable = condition_source_backed

        # -- frontier / cutline --------------------------------------------
        if condition_source_backed:
            frontier_status = "cutline_partial"
            cutline_reason = "missing_required_for_complete"
        else:
            frontier_status = "cutline_blocked"
            cutline_reason = "missing_required_for_partial"

        # -- related edges -------------------------------------------------
        flow_id = exc_flow.flow_id  # type: ignore[attr-defined]
        worker_id = instance.metadata.get("worker_id")
        related_edges: list[ConstructEdge] = []

        # handles edge: EXCEPTION_FLOW handles CONDITION (virtual node)
        related_edges.append(ConstructEdge(
            from_id=instance.construct_id,
            to_id=(
                f"worker:{worker_id}.condition:{flow_id}"
                if worker_id else f"condition:{flow_id}"
            ),
            edge_type="handles",
            source_span_ids=list(exc_flow.spans),  # type: ignore[attr-defined]
            metadata={
                "condition_text": exc_flow.condition_text,  # type: ignore[attr-defined]
                "flow_id": flow_id,
            },
        ))

        # contains edge: WORKER contains EXCEPTION_FLOW (worker-scoped only)
        if worker_id is not None:
            related_edges.append(ConstructEdge(
                from_id=f"worker:{worker_id}",
                to_id=instance.construct_id,
                edge_type="contains",
            ))

        return ConstructSatisfactionReport(
            construct_id=instance.construct_id,
            construct_type="EXCEPTION_FLOW",
            slots=[condition_sat, handler_sat, trigger_sat],
            completeness=completeness,
            renderable=renderable,
            primary_parent_id=instance.primary_parent_id,
            construct_path=instance.construct_path,
            source_span_ids=list(exc_flow.spans),  # type: ignore[attr-defined]
            frontier_status=frontier_status,
            cutline_reason=cutline_reason,
            related_edges=related_edges,
            metadata=instance.metadata,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _make_instance(
        exc_flow: object,
        worker_id: str | None,
    ) -> ConstructInstance:
        """Build a ConstructInstance for an ExceptionFlow."""
        flow_id = exc_flow.flow_id  # type: ignore[attr-defined]
        if worker_id:
            construct_id = f"worker:{worker_id}.exception_flow:{flow_id}"
            parent_id = f"worker:{worker_id}"
            path = ("worker_flow_plan", worker_id, "exception_flows", flow_id)
        else:
            construct_id = f"exception_flow:{flow_id}"
            parent_id = None
            path = ("flow", "exception_flows", flow_id)

        return ConstructInstance(
            construct_id=construct_id,
            construct_type="EXCEPTION_FLOW",
            materialized=True,
            source_demanded=True,
            candidate_only=False,
            ir_ref=exc_flow,
            primary_parent_id=parent_id,
            construct_path=path,
            source_span_ids=list(exc_flow.spans),  # type: ignore[attr-defined]
            metadata={"exception_flow_ir": exc_flow, "worker_id": worker_id},
        )
