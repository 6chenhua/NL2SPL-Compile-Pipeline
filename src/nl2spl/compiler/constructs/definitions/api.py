"""Default ConstructIRS definitions for api."""

from __future__ import annotations

from nl2spl.compiler.constructs.registry import SPLConstructRegistry
from nl2spl.compiler.constructs.spec import ConstructIRS, SlotSpec
from nl2spl.compiler.repair_contracts import RepairAffordanceSpec


def register(registry: SPLConstructRegistry) -> None:

# -- API_DECLARATION --------------------------------------------------
    registry.register(ConstructIRS(
        construct_type="API_DECLARATION",
        existence_policy="source_signal_required",
        source_signals=[
            "api_candidate",
            "integration_hint",
            "configured_api",
            "api_resource_contract",
        ],
        no_demand_behavior="do_not_generate",
        partial_rendering_allowed=True,
        description="Declaration of an external API specification.",
        slots=[
            SlotSpec(
                slot_name="api_name",
                syntax_required=True,
                required_for_partial=True,
                required_for_complete=True,
                renderable_without=False,
                evidence_kinds=["api_name", "api_ref"],
                missing_diagnostic="type_or_contract_ambiguity",
                repair_affordances=(),
            ),
            SlotSpec(
                slot_name="source_evidence",
                syntax_required=False,
                required_for_partial=True,
                required_for_complete=True,
                renderable_without=False,
                evidence_kinds=[
                    "source_span",
                    "integration_hint",
                    "configured_resource",
                    "user_confirmed_repair",
                ],
                missing_diagnostic="type_or_contract_ambiguity",
                repair_affordances=(),
            ),
            SlotSpec(
                slot_name="authentication",
                syntax_required=True,
                required_for_partial=False,
                required_for_complete=True,
                renderable_without=True,
                evidence_kinds=["auth_config", "explicit_auth"],
                missing_diagnostic="type_or_contract_ambiguity",
                repair_affordances=(),
            ),
            SlotSpec(
                slot_name="openapi_schema",
                syntax_required=True,
                required_for_partial=False,
                required_for_complete=True,
                renderable_without=True,
                evidence_kinds=["openapi_schema", "schema_definition"],
                missing_diagnostic="type_or_contract_ambiguity",
                repair_affordances=(),
            ),
            SlotSpec(
                slot_name="functions",
                syntax_required=True,
                required_for_partial=False,
                required_for_complete=True,
                renderable_without=True,
                evidence_kinds=["api_function", "function_definition"],
                missing_diagnostic="type_or_contract_ambiguity",
                repair_affordances=(),
            ),
        ],
    ))

# -- CALL_API --------------------------------------------------------
    registry.register(ConstructIRS(
        construct_type="CALL_API",
        existence_policy="source_signal_required",
        source_signals=["api_call_action", "tool_call_action", "connector_action"],
        partial_rendering_allowed=False,
        description=(
            "An executable API / tool / connector call. Requires a named "
            "integration reference, declared API reference, and explicit call-action evidence."
        ),
        slots=[
            SlotSpec(
                slot_name="api_name",
                syntax_required=True,
                required_for_complete=True,
                evidence_kinds=["api_ref", "integration_ref"],
                missing_diagnostic="type_or_contract_ambiguity",
            ),
            SlotSpec(
                slot_name="declared_api_ref",
                syntax_required=False,
                required_for_complete=True,
                evidence_kinds=["api_ref", "declared_api_ref"],
                missing_diagnostic="type_or_contract_ambiguity",
                notes="Resolves to a gate-approved APISpec.",
            ),
            SlotSpec(
                slot_name="call_action",
                required_for_complete=True,
                renderable_without=False,
                evidence_kinds=["call_action", "invoke_action"],
                missing_diagnostic="type_or_contract_ambiguity",
                notes=(
                    "Distinguishes an integration *mention* from executable "
                    "call evidence. Without an explicit call action the "
                    "construct should not become a rendered CALL_API."
                ),
            ),
            SlotSpec(
                slot_name="request_bindings",
                required_for_complete=False,
                evidence_kinds=["request_binding", "input_binding"],
            ),
            SlotSpec(
                slot_name="response_binding",
                required_for_complete=False,
                evidence_kinds=["response", "output_variable"],
                notes=(
                    "May be satisfied by a single StepIR.outputs rendered "
                    "as a single structured RESPONSE COMMAND_RESULT."
                ),
            ),
            SlotSpec(
                slot_name="integration_evidence",
                # Compatibility alias: does not participate in completion authority.
                required_for_complete=False,
                evidence_kinds=[
                    "api_ref",
                    "tool_ref",
                    "connector_ref",
                    "integration_ref",
                ],
                missing_diagnostic="type_or_contract_ambiguity",
                notes=(
                    "Compatibility alias slot for snapshot/diagnostic tracing. "
                    "Source context alone is not integration evidence."
                ),
                repair_affordances=(
                    RepairAffordanceSpec(
                        affordance_id="call_api.specify_integration_evidence",
                        description=(
                            "Provide integration evidence (API/tool/connector ref) "
                            "for a CALL_API step."
                        ),
                        supported_patch_types=("SpecifyAPIIntegration",),
                        default_patch_type="SpecifyAPIIntegration",
                        handler_id="type_or_contract_ambiguity",
                        context_id="call_api_context",
                        target_resolver_id="step_target",
                        default_verification_lane="A",
                        editable_artifacts=("WorkerStepPlanIR",),
                    ),
                ),
            ),
        ],
    ))
