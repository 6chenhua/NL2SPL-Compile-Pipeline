"""Default ConstructIRS definitions for output."""

from __future__ import annotations

from nl2spl.compiler.constructs.registry import SPLConstructRegistry
from nl2spl.compiler.constructs.spec import ConstructIRS, SlotSpec
from nl2spl.compiler.repair_contracts import RepairAffordanceSpec


def register(registry: SPLConstructRegistry) -> None:

# -- REQUIRED_OUTPUT -------------------------------------------------
    registry.register(ConstructIRS(
        construct_type="REQUIRED_OUTPUT",
        existence_policy="source_signal_required",
        source_signals=["required_output", "output_contract"],
        partial_rendering_allowed=True,
        description=(
            "A named output the process is expected to produce. "
            "The output declaration can be rendered even when the producer "
            "is unknown."
        ),
        slots=[
            SlotSpec(
                slot_name="output_name",
                syntax_required=True,
                required_for_partial=True,
                required_for_complete=True,
                evidence_kinds=["output_name", "output_contract"],
            ),
            SlotSpec(
                slot_name="output_type",
                syntax_required=False,
                required_for_partial=False,
                required_for_complete=False,
                renderable_without=True,
                evidence_kinds=["output_type", "output_description"],
                can_be_inferred=True,
            ),
            SlotSpec(
                slot_name="producer",
                syntax_required=False,
                required_for_complete=True,
                renderable_without=True,
                evidence_kinds=["producer_step", "handoff_output", "api_response"],
                missing_diagnostic="missing_output_producer",
                notes=(
                    "Must have a source-backed producer step, handoff, or API. "
                    "Missing producer is a completion diagnostic, not a reason "
                    "to synthesise a producer command."
                ),
                repair_affordances=(
                    RepairAffordanceSpec(
                        affordance_id="required_output.insert_or_bind_producer",
                        description=(
                            "Insert a new producer step or bind an existing step "
                            "as the producer for a required output."
                        ),
                        supported_patch_types=("InsertProducerStep",),
                        default_patch_type="InsertProducerStep",
                        handler_id="missing_output_producer",
                        context_id="required_output_context",
                        target_resolver_id="required_output_target",
                        default_verification_lane="B",
                        editable_artifacts=("WorkerStepPlanIR", "WorkerBlockPlanIR"),
                        materialization_plan_id="stage7.step_producer_repair.v1",
                        selectable_ref_policy_id="required_output.producer.selectable_refs.v1",
                        intent_schema_id="intent.insert_producer_step.v1",
                        required_context_facts=(
                            "target_output_name",
                            "worker_id",
                            "available_variables",
                            "nearby_steps",
                            "symbol_table",
                        ),
                        stage_authority="stage7.worker_step_plan",
                        repair_strategy_id="required_output.materialize_producer.v1",
                    ),
                ),
            ),
        ],
    ))
