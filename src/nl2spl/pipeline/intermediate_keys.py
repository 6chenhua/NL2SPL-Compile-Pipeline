"""Shared keys for pipeline intermediate artifacts.

These constants keep cross-stage handoff payloads from drifting through
near-duplicate string keys.
"""

EXECUTABLE_ACTION_CANDIDATES = "executable_action_candidates"
EXECUTABLE_ACTION_PLACEMENT_PLAN = "executable_action_placement_plan"
CONTROL_REGION_PLAN = "control_region_plan"
API_CALL_PLACEMENTS = "api_call_placements"
API_CALL_PLACEMENT_PAYLOAD = "api_call_placement_payload"
STEP_VARIABLE_RELATION_PLAN = "step_variable_relation_plan"
REQUIRED_OUTPUT_FULFILLMENT = "required_output_fulfillment"
CONDITION_VARIABLE_REFERENCE_PLAN = "condition_variable_reference_plan"
