"""Default ConstructIRS definitions for worker."""

from __future__ import annotations

from nl2spl.compiler.constructs.registry import SPLConstructRegistry
from nl2spl.compiler.constructs.spec import ConstructIRS, SlotSpec
from nl2spl.compiler.repair_contracts import RepairAffordanceSpec


def register(registry: SPLConstructRegistry) -> None:

# -- INVOKE_WORKER ---------------------------------------------------
    registry.register(ConstructIRS(
        construct_type="INVOKE_WORKER",
        existence_policy="source_signal_required",
        source_signals=["accepted_handoff", "delegated_subtask", "invoke_worker"],
        partial_rendering_allowed=False,
        description=(
            "A cross-worker invocation step.  Only materialised when a "
            "complete handoff (target worker + input/output bindings) exists."
        ),
        slots=[
            SlotSpec(
                slot_name="target_worker",
                syntax_required=True,
                required_for_complete=True,
                evidence_kinds=["worker_spec", "accepted_worker_boundary"],
                missing_diagnostic="type_or_contract_ambiguity",
                repair_affordances=(
                    RepairAffordanceSpec(
                        affordance_id="invoke_worker.specify_target_worker",
                        description="Specify the target worker for an INVOKE_WORKER step.",
                        supported_patch_types=("SpecifyInvokeTarget",),
                        default_patch_type="SpecifyInvokeTarget",
                        handler_id="type_or_contract_ambiguity",
                        context_id="invoke_worker_context",
                        target_resolver_id="step_target",
                        default_verification_lane="A",
                        editable_artifacts=("WorkerStepPlanIR",),
                    ),
                ),
            ),
            SlotSpec(
                slot_name="handoff_id",
                required_for_complete=True,
                evidence_kinds=["worker_handoff"],
                missing_diagnostic="type_or_contract_ambiguity",
                repair_affordances=(
                    RepairAffordanceSpec(
                        affordance_id="invoke_worker.create_or_bind_handoff",
                        description=(
                            "Create a new worker handoff contract or bind an "
                            "existing one for an INVOKE_WORKER step."
                        ),
                        supported_patch_types=(
                            "CreateWorkerHandoffContract",
                            "BindExistingHandoff",
                        ),
                        default_patch_type="CreateWorkerHandoffContract",
                        handler_id="type_or_contract_ambiguity",
                        context_id="invoke_worker_context",
                        target_resolver_id="step_target",
                        default_verification_lane="B",
                        editable_artifacts=("WorkerPlanIR", "WorkerHandoffIR"),
                    ),
                ),
            ),
            SlotSpec(
                slot_name="input_bindings",
                required_for_complete=True,
                evidence_kinds=["input_binding"],
                missing_diagnostic="type_or_contract_ambiguity",
                repair_affordances=(
                    RepairAffordanceSpec(
                        affordance_id="invoke_worker.specify_input_bindings",
                        description="Specify input bindings for a worker handoff.",
                        supported_patch_types=("UpdateHandoffContract",),
                        default_patch_type="UpdateHandoffContract",
                        handler_id="type_or_contract_ambiguity",
                        context_id="handoff_context",
                        target_resolver_id="handoff_target",
                        default_verification_lane="B",
                        editable_artifacts=("WorkerHandoffIR",),
                    ),
                ),
            ),
            SlotSpec(
                slot_name="output_bindings",
                required_for_complete=True,
                evidence_kinds=["output_binding"],
                missing_diagnostic="type_or_contract_ambiguity",
                repair_affordances=(
                    RepairAffordanceSpec(
                        affordance_id="invoke_worker.specify_output_bindings",
                        description="Specify output bindings for a worker handoff.",
                        supported_patch_types=("UpdateHandoffContract",),
                        default_patch_type="UpdateHandoffContract",
                        handler_id="type_or_contract_ambiguity",
                        context_id="handoff_context",
                        target_resolver_id="handoff_target",
                        default_verification_lane="B",
                        editable_artifacts=("WorkerHandoffIR",),
                    ),
                ),
            ),
        ],
    ))

# -- CHILD_WORKER ----------------------------------------------------
    registry.register(ConstructIRS(
        construct_type="CHILD_WORKER",
        existence_policy="source_signal_required",
        source_signals=["delegation", "subtask", "bounded_task", "worker_boundary"],
        partial_rendering_allowed=True,
        description=(
            "An independently callable sub-worker with a clear responsibility, "
            "input/output contract, invocation point, and result handoff."
        ),
        slots=[
            SlotSpec(
                slot_name="responsibility",
                required_for_partial=True,
                required_for_complete=True,
                evidence_kinds=["subtask_purpose", "delegated_responsibility"],
            ),
            SlotSpec(
                slot_name="input_contract",
                required_for_partial=False,
                required_for_complete=True,
                renderable_without=True,
                evidence_kinds=["input_contract", "parent_binding"],
                missing_diagnostic="type_or_contract_ambiguity",
            ),
            SlotSpec(
                slot_name="output_contract",
                required_for_partial=False,
                required_for_complete=True,
                renderable_without=True,
                evidence_kinds=["output_contract", "returned_result"],
                missing_diagnostic="type_or_contract_ambiguity",
            ),
            SlotSpec(
                slot_name="invocation_point",
                required_for_complete=True,
                renderable_without=True,
                evidence_kinds=["condition", "handoff_point"],
                missing_diagnostic="type_or_contract_ambiguity",
            ),
            SlotSpec(
                slot_name="result_handoff",
                required_for_complete=True,
                renderable_without=True,
                evidence_kinds=["output_binding", "result_binding"],
                missing_diagnostic="type_or_contract_ambiguity",
            ),
        ],
    ))

# -- WORKER_CANDIDATE ------------------------------------------------
    registry.register(ConstructIRS(
        construct_type="WORKER_CANDIDATE",
        existence_policy="source_signal_required",
        source_signals=[
            "delegation",
            "subtask",
            "optional_subtask",
            "template_matching",
            "source_gathering",
        ],
        partial_rendering_allowed=False,
        no_demand_behavior="do_not_generate",
        description=(
            "A delegation mention identified as a candidate task boundary. "
            "Represents that a candidate boundary exists, not whether it can "
            "be promoted to a child worker. Stays as a report / provenance trace; "
            "not rendered as SPL."
        ),
        slots=[
            SlotSpec(
                slot_name="responsibility",
                required_for_partial=True,
                required_for_complete=True,
                evidence_kinds=["subtask_purpose", "delegation_mention"],
            ),
            SlotSpec(
                slot_name="delegation_signal",
                required_for_complete=True,
                evidence_kinds=["delegation_signal", "candidate_kind"],
            ),
            SlotSpec(
                slot_name="source_evidence",
                required_for_complete=True,
                evidence_kinds=["source_span", "candidate_source"],
            ),
        ],
    ))

# -- WORKER_PROMOTION ------------------------------------------------
    registry.register(ConstructIRS(
        construct_type="WORKER_PROMOTION",
        existence_policy="source_signal_required",
        source_signals=[
            "delegation",
            "subtask",
            "explicit_delegation",
        ],
        partial_rendering_allowed=False,
        no_demand_behavior="do_not_generate",
        description=(
            "Promotion readiness assessment for a worker candidate. "
            "Expresses whether a candidate has the necessary conditions "
            "(contract, invocation point, handoff) to be promoted to a child worker. "
            "This is an analysis construct, not a renderable SPL construct."
        ),
        slots=[
            SlotSpec(
                slot_name="promotion_input_contract",
                required_for_partial=True,
                required_for_complete=True,
                renderable_without=False,
                evidence_kinds=["input_contract", "possible_inputs"],
                missing_diagnostic="type_or_contract_ambiguity",
                notes=(
                    "Satisfied when possible_inputs is non-empty and risks "
                    "does not contain no_clear_input_contract."
                ),
                repair_affordances=(
                    RepairAffordanceSpec(
                        affordance_id="worker_promotion.resolve_contract",
                        description=(
                            "Resolve a delegation-intent-sourced WORKER_PROMOTION gap. "
                            "User can define a complete child-worker closure or keep an "
                            "explicitly selected task in the main flow."
                        ),
                        supported_patch_types=(
                            "DefineChildWorkerClosure",
                            "ConvertDelegationIntentToMainFlowStep",
                        ),
                        default_patch_type="DefineChildWorkerClosure",
                        handler_id="type_or_contract_ambiguity",
                        context_id="worker_promotion_context",
                        target_resolver_id="worker_promotion_target",
                        default_verification_lane="B",
                        editable_artifacts=(
                            "WorkerPlanIR",
                            "WorkerFlowPlanIR",
                            "WorkerBlockPlanIR",
                            "WorkerStepPlanIR",
                            "SymbolTable",
                        ),
                        materialization_plan_id="worker_delegation.complete_closure.v2",
                        selectable_ref_policy_id="worker_promotion.handoff.selectable_refs.v1",
                        intent_schema_id="intent.worker_promotion_resolution.v1",
                        required_context_facts=(
                            "delegation_intent",
                            "worker_id",
                            "candidate_name",
                            "possible_inputs",
                            "possible_outputs",
                            "hierarchy_graph",
                        ),
                        stage_authority=(
                            "stage3_5.worker_boundary + stage4.worker_flow_plan + "
                            "stage5.worker_block_plan + stage7.worker_step_plan"
                        ),
                        repair_strategy_id="worker_delegation.complete_closure.v2",
                        patch_type_metadata=(),
                        notes=(
                            "delegation-intent-sourced WORKER_PROMOTION gap. "
                            "All four promotion slots share the same repair "
                            "strategy set; the specific missing slots control "
                            "what the patch payload must provide."
                        ),
                    ),
                ),
            ),
            SlotSpec(
                slot_name="promotion_output_contract",
                required_for_partial=True,
                required_for_complete=True,
                renderable_without=False,
                evidence_kinds=["output_contract", "possible_outputs"],
                missing_diagnostic="type_or_contract_ambiguity",
                notes=(
                    "Satisfied when possible_outputs is non-empty and risks "
                    "does not contain no_clear_output_contract."
                ),
                repair_affordances=(
                    RepairAffordanceSpec(
                        affordance_id="worker_promotion.resolve_contract",
                        description=(
                            "Resolve a delegation-intent-sourced WORKER_PROMOTION gap. "
                            "User can define a complete child-worker closure or keep an "
                            "explicitly selected task in the main flow."
                        ),
                        supported_patch_types=(
                            "DefineChildWorkerClosure",
                            "ConvertDelegationIntentToMainFlowStep",
                        ),
                        default_patch_type="DefineChildWorkerClosure",
                        handler_id="type_or_contract_ambiguity",
                        context_id="worker_promotion_context",
                        target_resolver_id="worker_promotion_target",
                        default_verification_lane="B",
                        editable_artifacts=(
                            "WorkerPlanIR",
                            "WorkerFlowPlanIR",
                            "WorkerBlockPlanIR",
                            "WorkerStepPlanIR",
                            "SymbolTable",
                        ),
                        materialization_plan_id="worker_delegation.complete_closure.v2",
                        selectable_ref_policy_id="worker_promotion.handoff.selectable_refs.v1",
                        intent_schema_id="intent.worker_promotion_resolution.v1",
                        required_context_facts=(
                            "delegation_intent",
                            "worker_id",
                            "candidate_name",
                            "possible_inputs",
                            "possible_outputs",
                            "hierarchy_graph",
                        ),
                        stage_authority=(
                            "stage3_5.worker_boundary + stage4.worker_flow_plan + "
                            "stage5.worker_block_plan + stage7.worker_step_plan"
                        ),
                        repair_strategy_id="worker_delegation.complete_closure.v2",
                        patch_type_metadata=(),
                    ),
                ),
            ),
            SlotSpec(
                slot_name="promotion_invocation_point",
                required_for_partial=True,
                required_for_complete=True,
                renderable_without=False,
                evidence_kinds=["invocation_point", "handoff_point"],
                missing_diagnostic="type_or_contract_ambiguity",
                notes=(
                    "Satisfied when risks does not contain no_parent_invocation_point "
                    "and there is evidence of where to invoke the worker."
                ),
                repair_affordances=(
                    RepairAffordanceSpec(
                        affordance_id="worker_promotion.resolve_contract",
                        description=(
                            "Resolve a delegation-intent-sourced WORKER_PROMOTION gap. "
                            "User can define a complete child-worker closure or keep an "
                            "explicitly selected task in the main flow."
                        ),
                        supported_patch_types=(
                            "DefineChildWorkerClosure",
                            "ConvertDelegationIntentToMainFlowStep",
                        ),
                        default_patch_type="DefineChildWorkerClosure",
                        handler_id="type_or_contract_ambiguity",
                        context_id="worker_promotion_context",
                        target_resolver_id="worker_promotion_target",
                        default_verification_lane="B",
                        editable_artifacts=(
                            "WorkerPlanIR",
                            "WorkerFlowPlanIR",
                            "WorkerBlockPlanIR",
                            "WorkerStepPlanIR",
                            "SymbolTable",
                        ),
                        materialization_plan_id="worker_delegation.complete_closure.v2",
                        selectable_ref_policy_id="worker_promotion.handoff.selectable_refs.v1",
                        intent_schema_id="intent.worker_promotion_resolution.v1",
                        required_context_facts=(
                            "delegation_intent",
                            "worker_id",
                            "candidate_name",
                            "possible_inputs",
                            "possible_outputs",
                            "hierarchy_graph",
                        ),
                        stage_authority=(
                            "stage3_5.worker_boundary + stage4.worker_flow_plan + "
                            "stage5.worker_block_plan + stage7.worker_step_plan"
                        ),
                        repair_strategy_id="worker_delegation.complete_closure.v2",
                        patch_type_metadata=(),
                    ),
                ),
            ),
            SlotSpec(
                slot_name="promotion_result_handoff",
                required_for_partial=True,
                required_for_complete=True,
                renderable_without=False,
                evidence_kinds=["result_handoff", "output_binding"],
                missing_diagnostic="type_or_contract_ambiguity",
                notes=(
                    "Satisfied when risks does not contain unclear_result_handoff "
                    "and there is a matching handoff with output_bindings."
                ),
                repair_affordances=(
                    RepairAffordanceSpec(
                        affordance_id="worker_promotion.resolve_contract",
                        description=(
                            "Resolve a delegation-intent-sourced WORKER_PROMOTION gap. "
                            "User can define a complete child-worker closure or keep an "
                            "explicitly selected task in the main flow."
                        ),
                        supported_patch_types=(
                            "DefineChildWorkerClosure",
                            "ConvertDelegationIntentToMainFlowStep",
                        ),
                        default_patch_type="DefineChildWorkerClosure",
                        handler_id="type_or_contract_ambiguity",
                        context_id="worker_promotion_context",
                        target_resolver_id="worker_promotion_target",
                        default_verification_lane="B",
                        editable_artifacts=(
                            "WorkerPlanIR",
                            "WorkerFlowPlanIR",
                            "WorkerBlockPlanIR",
                            "WorkerStepPlanIR",
                            "SymbolTable",
                        ),
                        materialization_plan_id="worker_delegation.complete_closure.v2",
                        selectable_ref_policy_id="worker_promotion.handoff.selectable_refs.v1",
                        intent_schema_id="intent.worker_promotion_resolution.v1",
                        required_context_facts=(
                            "delegation_intent",
                            "worker_id",
                            "candidate_name",
                            "possible_inputs",
                            "possible_outputs",
                            "hierarchy_graph",
                        ),
                        stage_authority=(
                            "stage3_5.worker_boundary + stage4.worker_flow_plan + "
                            "stage5.worker_block_plan + stage7.worker_step_plan"
                        ),
                        repair_strategy_id="worker_delegation.complete_closure.v2",
                        patch_type_metadata=(),
                    ),
                ),
            ),
        ],
    ))

# -- WORKER_HANDOFF --------------------------------------------------
    registry.register(ConstructIRS(
        construct_type="WORKER_HANDOFF",
        existence_policy="source_signal_required",
        source_signals=[
            "worker_handoff",
            "worker_invocation",
            "api_call",
        ],
        partial_rendering_allowed=False,
        no_demand_behavior="do_not_generate",
        description=(
            "A materialized worker handoff representing data flow and invocation "
            "between workers or from worker to API. Expresses whether the handoff "
            "has complete contract bindings."
        ),
        slots=[
            SlotSpec(
                slot_name="from_worker",
                required_for_complete=True,
                evidence_kinds=["from_worker"],
                missing_diagnostic="type_or_contract_ambiguity",
            ),
            SlotSpec(
                slot_name="target",
                required_for_complete=True,
                evidence_kinds=["to_worker", "api_ref"],
                missing_diagnostic="type_or_contract_ambiguity",
                notes=(
                    "For mode='invoke', uses to_worker. "
                    "For mode='api_call', uses api_ref."
                ),
                repair_affordances=(
                    RepairAffordanceSpec(
                        affordance_id="worker_handoff.specify_target",
                        description=(
                            "Specify the target (to_worker or api_ref) for an "
                            "incomplete worker handoff."
                        ),
                        supported_patch_types=("UpdateHandoffContract",),
                        default_patch_type="UpdateHandoffContract",
                        handler_id="type_or_contract_ambiguity",
                        context_id="handoff_context",
                        target_resolver_id="handoff_target",
                        default_verification_lane="B",
                        editable_artifacts=("WorkerHandoffIR",),
                    ),
                ),
            ),
            SlotSpec(
                slot_name="input_bindings",
                required_for_complete=True,
                evidence_kinds=["input_binding"],
                missing_diagnostic="type_or_contract_ambiguity",
                repair_affordances=(
                    RepairAffordanceSpec(
                        affordance_id="worker_handoff.specify_input_bindings",
                        description="Specify input bindings for an incomplete worker handoff.",
                        supported_patch_types=("UpdateHandoffContract",),
                        default_patch_type="UpdateHandoffContract",
                        handler_id="type_or_contract_ambiguity",
                        context_id="handoff_context",
                        target_resolver_id="handoff_target",
                        default_verification_lane="B",
                        editable_artifacts=("WorkerHandoffIR",),
                    ),
                ),
            ),
            SlotSpec(
                slot_name="output_bindings",
                required_for_complete=True,
                evidence_kinds=["output_binding"],
                missing_diagnostic="type_or_contract_ambiguity",
                repair_affordances=(
                    RepairAffordanceSpec(
                        affordance_id="worker_handoff.specify_output_bindings",
                        description="Specify output bindings for an incomplete worker handoff.",
                        supported_patch_types=("UpdateHandoffContract",),
                        default_patch_type="UpdateHandoffContract",
                        handler_id="type_or_contract_ambiguity",
                        context_id="handoff_context",
                        target_resolver_id="handoff_target",
                        default_verification_lane="B",
                        editable_artifacts=("WorkerHandoffIR",),
                    ),
                ),
            ),
            SlotSpec(
                slot_name="invocation_site",
                required_for_complete=True,
                evidence_kinds=["invoke_location_hint"],
                missing_diagnostic="type_or_contract_ambiguity",
                notes=(
                    "Uses invoke_location_hint structured fields: "
                    "after_span_id, before_span_id, block_hint (non-unknown), "
                    "or handoff-level condition_text. "
                    "Does NOT use ordering (required Literal) as evidence."
                ),
                repair_affordances=(
                    RepairAffordanceSpec(
                        affordance_id="worker_handoff.specify_invocation_site",
                        description=(
                            "Specify the invocation site for an incomplete "
                            "worker handoff."
                        ),
                        supported_patch_types=("UpdateHandoffContract",),
                        default_patch_type="UpdateHandoffContract",
                        handler_id="type_or_contract_ambiguity",
                        context_id="handoff_context",
                        target_resolver_id="handoff_target",
                        default_verification_lane="B",
                        editable_artifacts=("WorkerHandoffIR",),
                    ),
                ),
            ),
        ],
    ))

    # R10: DELEGATION_INTENT removed — delegation_intent is a source
    # signal / evidence routed through WORKER_CANDIDATE / WORKER_PROMOTION.
