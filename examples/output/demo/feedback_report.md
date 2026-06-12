# NL2SPL Feedback Report

## 1. Overall Compile State

- Completeness: `partial`
- SPL draft generated: `yes`
- Compile diagnostics: `18`
- Assumptions / suggestions: `18`
- Trace records: `37`
- Adapter warnings: `0`
- Validation errors: `0`
- Validation warnings: `12`

Result is partial because the following requirement gaps remain:
- `missing_handler` on `worker:worker_main.exception_flow:exc_adapter_02`: Exception flow 'exc_adapter_02' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_02, slot=handler_action]
- `missing_handler` on `worker:worker_main.exception_flow:exc_adapter_01`: Exception flow 'exc_adapter_01' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_01, slot=handler_action]
- `missing_handler` on `worker:worker_main.exception_flow:exc_adapter_04`: Exception flow 'exc_adapter_04' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_04, slot=handler_action]
- `missing_handler` on `worker:worker_main.exception_flow:exc_adapter_05`: Exception flow 'exc_adapter_05' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_05, slot=handler_action]
- `missing_handler` on `worker:worker_main.exception_flow:exc_adapter_00`: Exception flow 'exc_adapter_00' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_00, slot=handler_action]
- `missing_handler` on `worker:worker_main.exception_flow:exc_adapter_03`: Exception flow 'exc_adapter_03' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_03, slot=handler_action]
- `missing_output_producer` on `worker:worker_main.output:completion_status`: Required output 'completion_status' (Final completion status of the workflow.) has no source-backed producer step. [construct=worker:worker_main.output:completion_status, slot=producer]
- `missing_output_producer` on `resource_contract_demand:rcd_output_s14`: Resource contract output 'rcd_output_s14' (requiredness=required) has materialized resource(s) completion_status but no renderable producer. [construct=resource_contract_demand:rcd_output_s14, slot=producer]
- `type_or_contract_ambiguity` on `worker_promotion:del_s30`: WORKER_PROMOTION blocked by missing promotion slots.
  - `promotion_input_contract`: Missing clear input contract
  - `promotion_output_contract`: Missing clear output contract
  - `promotion_invocation_point`: Missing accepted decision or matching handoff with invocation hint
  - `promotion_result_handoff`: Missing matching handoff with output bindings

## 2. Materialized Source-Backed Structure

### Workers
- `worker:MainWorker` (direct) -- spans=s15, s16, s17; section=sec_reusable_process; packet=p_list_item_first_determine_what_kind_of_communication_is_requested_then_identify_which_required_fields_are_still_missing_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward_if_sources_are_needed_and_available

### Flows
- `flow:exc_adapter_00` (direct) -- spans=s25; section=sec_failure_handling; packet=p_list_item_conflicting_instructions
- `flow:exc_adapter_01` (direct) -- spans=s27; section=sec_failure_handling; packet=p_list_item_evidence_shortage
- `flow:exc_adapter_02` (direct) -- spans=s26; section=sec_failure_handling; packet=p_list_item_insufficient_source_access
- `flow:exc_adapter_03` (direct) -- spans=s24; section=sec_failure_handling; packet=p_list_item_missing_timeframe
- `flow:exc_adapter_04` (direct) -- spans=s29; section=sec_failure_handling; packet=p_list_item_provenance_failure
- `flow:exc_adapter_05` (direct) -- spans=s28; section=sec_failure_handling; packet=p_list_item_user_refusal_to_answer
- `flow:main` (direct) -- spans=s15, s16, s17; section=sec_reusable_process; packet=p_list_item_first_determine_what_kind_of_communication_is_requested_then_identify_which_required_fields_are_still_missing_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward_if_sources_are_needed_and_available

### Steps
- `step:st_1` (direct) -- spans=s15; section=sec_reusable_process; packet=p_list_item_first_determine_what_kind_of_communication_is_requested_then_identify_which_required_fields_are_still_missing_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward_if_sources_are_needed_and_available
- `step:st_2` (direct) -- spans=s15; section=sec_reusable_process; packet=p_list_item_first_determine_what_kind_of_communication_is_requested_then_identify_which_required_fields_are_still_missing_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward_if_sources_are_needed_and_available
- `step:st_3` (direct) -- spans=s16; section=sec_reusable_process; packet=p_list_item_retrieve_them_using_approved_source_recipes_maintain_provenance_for_externally_sourced_facts_when_enough_required_information_is_available
- `step:st_4` (direct) -- spans=s17; section=sec_reusable_process; packet=p_list_item_produce_a_draft_if_the_user_asks_for_revision

### Variables
- `variable:assumptions_log` (direct) -- spans=s15; section=sec_reusable_process; packet=p_list_item_first_determine_what_kind_of_communication_is_requested_then_identify_which_required_fields_are_still_missing_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward_if_sources_are_needed_and_available
- `variable:draft_communication_artifact` (direct) -- spans=s17; section=sec_reusable_process; packet=p_list_item_produce_a_draft_if_the_user_asks_for_revision
- `variable:source_evidence_set` (direct) -- spans=s16; section=sec_reusable_process; packet=p_list_item_retrieve_them_using_approved_source_recipes_maintain_provenance_for_externally_sourced_facts_when_enough_required_information_is_available

### Constraints
- `constraint:c_1` (direct) -- spans=s18; section=sec_reusable_process; packet=p_list_item_revise_while_re_checking_constraints_do_not_finalize_if_required_slots_remain_missing_unless_the_draft_is_explicitly_marked_as_assumption_bearing_and_the_user_confirms
- `constraint:c_2` (direct) -- spans=s19; section=sec_policies; packet=p_sentence_do_not_invent_links_or_unseen_facts
- `constraint:c_3` (direct) -- spans=s20; section=sec_policies; packet=p_sentence_require_evidence_for_sourced_claims
- `constraint:c_4` (direct) -- spans=s21; section=sec_policies; packet=p_sentence_limit_questions_per_turn
- `constraint:c_5` (direct) -- spans=s22; section=sec_policies; packet=p_sentence_prefer_tool_evidence_over_unnecessary_user_questioning
- `constraint:c_6` (direct) -- spans=s23; section=sec_policies; packet=p_sentence_deny_finalization_if_critical_slots_are_missing_or_provenance_fails

### Other
- `profile:concept_0` (normalized)
- `profile:concept_1` (normalized)
- `profile:concept_2` (normalized)
- `profile:concept_3` (normalized)
- `profile:concept_4` (normalized)
- `profile:concept_5` (normalized)
- `profile:concept_6` (normalized)
- `profile:concept_7` (normalized)
- `profile:concept_8` (normalized)
- `profile:persona` (inferred)

## 3. Not Materialized / Kept Partial

- `worker:worker_main.exception_flow:exc_adapter_02`: `missing_handler` -- Exception flow 'exc_adapter_02' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_02, slot=handler_action]
  - Suggested resolution: Add a handler step for 'insufficient source access', or mark this exception as acknowledged without handling.
- `worker:worker_main.exception_flow:exc_adapter_01`: `missing_handler` -- Exception flow 'exc_adapter_01' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_01, slot=handler_action]
  - Suggested resolution: Add a handler step for 'evidence
shortage', or mark this exception as acknowledged without handling.
- `worker:worker_main.exception_flow:exc_adapter_04`: `missing_handler` -- Exception flow 'exc_adapter_04' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_04, slot=handler_action]
  - Suggested resolution: Add a handler step for 'provenance failure', or mark this exception as acknowledged without handling.
- `worker:worker_main.exception_flow:exc_adapter_05`: `missing_handler` -- Exception flow 'exc_adapter_05' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_05, slot=handler_action]
  - Suggested resolution: Add a handler step for 'user refusal to answer', or mark this exception as acknowledged without handling.
- `worker:worker_main.exception_flow:exc_adapter_00`: `missing_handler` -- Exception flow 'exc_adapter_00' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_00, slot=handler_action]
  - Suggested resolution: Add a handler step for 'conflicting instructions', or mark this exception as acknowledged without handling.
- `worker:worker_main.exception_flow:exc_adapter_03`: `missing_handler` -- Exception flow 'exc_adapter_03' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_03, slot=handler_action]
  - Suggested resolution: Add a handler step for 'Missing timeframe', or mark this exception as acknowledged without handling.
- `worker:worker_main.output:completion_status`: `missing_output_producer` -- Required output 'completion_status' (Final completion status of the workflow.) has no source-backed producer step. [construct=worker:worker_main.output:completion_status, slot=producer]
  - Suggested resolution: Add a step that produces 'completion_status'. If the source requirement does not specify how to produce this output, mark it as optional or remove it from the output contract.
- `resource_contract_demand:rcd_output_s14`: `missing_output_producer` -- Resource contract output 'rcd_output_s14' (requiredness=required) has materialized resource(s) completion_status but no renderable producer. [construct=resource_contract_demand:rcd_output_s14, slot=producer]
  - Suggested resolution: Add a source-backed step or handoff that produces the materialized resource name with the same resource kind.
- `worker_promotion:del_s30`: `type_or_contract_ambiguity` -- WORKER_PROMOTION blocked by missing promotion slots.
  - Source spans: `s30`
  - `promotion_input_contract`: Missing clear input contract
  - `promotion_output_contract`: Missing clear output contract
  - `promotion_invocation_point`: Missing accepted decision or matching handoff with invocation hint
  - `promotion_result_handoff`: Missing matching handoff with output bindings

## 4. Diagnostics

### irs_06f031a82a83: `missing_handler`
- Severity: `warning`
- Target: `worker:worker_main.exception_flow:exc_adapter_02`
- Source spans: `s26`
- Message: Exception flow 'exc_adapter_02' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_02, slot=handler_action]
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Add a handler step for 'insufficient source access', or mark this exception as acknowledged without handling.
- Missing slot: `handler_action`
- Missing reason: Exception flow 'exc_adapter_02' has condition but no handler step.

### irs_093ba020afa9: `missing_handler`
- Severity: `warning`
- Target: `worker:worker_main.exception_flow:exc_adapter_01`
- Source spans: `s27`
- Message: Exception flow 'exc_adapter_01' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_01, slot=handler_action]
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Add a handler step for 'evidence
shortage', or mark this exception as acknowledged without handling.
- Missing slot: `handler_action`
- Missing reason: Exception flow 'exc_adapter_01' has condition but no handler step.

### irs_5163b277caf9: `missing_handler`
- Severity: `warning`
- Target: `worker:worker_main.exception_flow:exc_adapter_04`
- Source spans: `s29`
- Message: Exception flow 'exc_adapter_04' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_04, slot=handler_action]
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Add a handler step for 'provenance failure', or mark this exception as acknowledged without handling.
- Missing slot: `handler_action`
- Missing reason: Exception flow 'exc_adapter_04' has condition but no handler step.

### irs_a3b97086c1b3: `missing_handler`
- Severity: `warning`
- Target: `worker:worker_main.exception_flow:exc_adapter_05`
- Source spans: `s28`
- Message: Exception flow 'exc_adapter_05' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_05, slot=handler_action]
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Add a handler step for 'user refusal to answer', or mark this exception as acknowledged without handling.
- Missing slot: `handler_action`
- Missing reason: Exception flow 'exc_adapter_05' has condition but no handler step.

### irs_b03b3eca9942: `missing_handler`
- Severity: `warning`
- Target: `worker:worker_main.exception_flow:exc_adapter_00`
- Source spans: `s25`
- Message: Exception flow 'exc_adapter_00' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_00, slot=handler_action]
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Add a handler step for 'conflicting instructions', or mark this exception as acknowledged without handling.
- Missing slot: `handler_action`
- Missing reason: Exception flow 'exc_adapter_00' has condition but no handler step.

### irs_e82d6237c12f: `missing_handler`
- Severity: `warning`
- Target: `worker:worker_main.exception_flow:exc_adapter_03`
- Source spans: `s24`
- Message: Exception flow 'exc_adapter_03' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_03, slot=handler_action]
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Add a handler step for 'Missing timeframe', or mark this exception as acknowledged without handling.
- Missing slot: `handler_action`
- Missing reason: Exception flow 'exc_adapter_03' has condition but no handler step.

### irs_5143c9abd16e: `missing_output_producer`
- Severity: `warning`
- Target: `worker:worker_main.output:completion_status`
- Message: Required output 'completion_status' (Final completion status of the workflow.) has no source-backed producer step. [construct=worker:worker_main.output:completion_status, slot=producer]
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Add a step that produces 'completion_status'. If the source requirement does not specify how to produce this output, mark it as optional or remove it from the output contract.
- Missing slot: `producer`
- Missing reason: Required output 'completion_status' (Final completion status of the workflow.) has no source-backed producer step.

### irs_59fb5ecfa9e9: `missing_output_producer`
- Severity: `warning`
- Target: `resource_contract_demand:rcd_output_s14`
- Source spans: `s14`
- Message: Resource contract output 'rcd_output_s14' (requiredness=required) has materialized resource(s) completion_status but no renderable producer. [construct=resource_contract_demand:rcd_output_s14, slot=producer]
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Add a source-backed step or handoff that produces the materialized resource name with the same resource kind.
- Missing slot: `producer`
- Missing reason: Resource contract output 'rcd_output_s14' (requiredness=required) has materialized resource(s) completion_status but no renderable producer.

### grouped:worker_promotion:del_s30: `type_or_contract_ambiguity`
- Severity: `warning`
- Target: `worker_promotion:del_s30`
- Source spans: `s30`
- Message: WORKER_PROMOTION blocked by missing promotion slots.
- Blocks rendering: `false`
- Blocks completion: `true`
- Missing slots:
  - `promotion_input_contract`: Missing clear input contract
    - Diagnostic: `irs_235c6aad5e5b`
  - `promotion_output_contract`: Missing clear output contract
    - Diagnostic: `irs_4d7dc95d4357`
  - `promotion_invocation_point`: Missing accepted decision or matching handoff with invocation hint
    - Diagnostic: `irs_3eee831e90f3`
  - `promotion_result_handoff`: Missing matching handoff with output bindings
    - Diagnostic: `irs_40a561bc5259`

### diag_prov_0000: `missing_provenance`
- Severity: `warning`
- Target: `variable:format_preferences`
- Message: Variable 'format_preferences' (text) is a contract input with no source-backed producer or adapter evidence.
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_prov_0001: `missing_provenance`
- Severity: `warning`
- Target: `variable:user_request`
- Message: Variable 'user_request' (text) is a contract input with no source-backed producer or adapter evidence.
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_prov_0002: `missing_provenance`
- Severity: `warning`
- Target: `variable:known_topics`
- Message: Variable 'known_topics' (List[text]) is a contract input with no source-backed producer or adapter evidence.
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_prov_0003: `missing_provenance`
- Severity: `warning`
- Target: `variable:timeframe`
- Message: Variable 'timeframe' (text) is a contract input with no source-backed producer or adapter evidence.
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_prov_0004: `missing_provenance`
- Severity: `warning`
- Target: `variable:connectors_or_source_repositories`
- Message: Variable 'connectors_or_source_repositories' (List[text]) is a contract input with no source-backed producer or adapter evidence.
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_prov_0005: `missing_provenance`
- Severity: `warning`
- Target: `variable:completion_status`
- Message: Variable 'completion_status' (text) is a contract output with no source-backed producer or adapter evidence.
- Blocks rendering: `false`
- Blocks completion: `false`

## 5. Assumptions / Suggestions

- `ASM_0000` for `worker:worker_main.exception_flow:exc_adapter_00`: Exception flow has no handler action. The compiler suggests specifying what should happen when this failure occurs.
  - Reason: Source describes a failure condition but does not specify how to handle it.  The exception flow is preserved in SPL, but no handler command was rendered. (Exception flow 'exc_adapter_00' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adap)
  - Suggested resolution: Specify the handler action for worker:worker_main.exception_flow:exc_adapter_00: e.g. ask the user for missing information, block finalization, or continue with an explicit assumption.
  - Related diagnostic: `irs_b03b3eca9942`
- `ASM_0001` for `worker:worker_main.exception_flow:exc_adapter_01`: Exception flow has no handler action. The compiler suggests specifying what should happen when this failure occurs.
  - Reason: Source describes a failure condition but does not specify how to handle it.  The exception flow is preserved in SPL, but no handler command was rendered. (Exception flow 'exc_adapter_01' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adap)
  - Suggested resolution: Specify the handler action for worker:worker_main.exception_flow:exc_adapter_01: e.g. ask the user for missing information, block finalization, or continue with an explicit assumption.
  - Related diagnostic: `irs_093ba020afa9`
- `ASM_0002` for `worker:worker_main.exception_flow:exc_adapter_02`: Exception flow has no handler action. The compiler suggests specifying what should happen when this failure occurs.
  - Reason: Source describes a failure condition but does not specify how to handle it.  The exception flow is preserved in SPL, but no handler command was rendered. (Exception flow 'exc_adapter_02' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adap)
  - Suggested resolution: Specify the handler action for worker:worker_main.exception_flow:exc_adapter_02: e.g. ask the user for missing information, block finalization, or continue with an explicit assumption.
  - Related diagnostic: `irs_06f031a82a83`
- `ASM_0003` for `worker:worker_main.exception_flow:exc_adapter_03`: Exception flow has no handler action. The compiler suggests specifying what should happen when this failure occurs.
  - Reason: Source describes a failure condition but does not specify how to handle it.  The exception flow is preserved in SPL, but no handler command was rendered. (Exception flow 'exc_adapter_03' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adap)
  - Suggested resolution: Specify the handler action for worker:worker_main.exception_flow:exc_adapter_03: e.g. ask the user for missing information, block finalization, or continue with an explicit assumption.
  - Related diagnostic: `irs_e82d6237c12f`
- `ASM_0004` for `worker:worker_main.exception_flow:exc_adapter_04`: Exception flow has no handler action. The compiler suggests specifying what should happen when this failure occurs.
  - Reason: Source describes a failure condition but does not specify how to handle it.  The exception flow is preserved in SPL, but no handler command was rendered. (Exception flow 'exc_adapter_04' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adap)
  - Suggested resolution: Specify the handler action for worker:worker_main.exception_flow:exc_adapter_04: e.g. ask the user for missing information, block finalization, or continue with an explicit assumption.
  - Related diagnostic: `irs_5163b277caf9`
- `ASM_0005` for `worker:worker_main.exception_flow:exc_adapter_05`: Exception flow has no handler action. The compiler suggests specifying what should happen when this failure occurs.
  - Reason: Source describes a failure condition but does not specify how to handle it.  The exception flow is preserved in SPL, but no handler command was rendered. (Exception flow 'exc_adapter_05' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adap)
  - Suggested resolution: Specify the handler action for worker:worker_main.exception_flow:exc_adapter_05: e.g. ask the user for missing information, block finalization, or continue with an explicit assumption.
  - Related diagnostic: `irs_a3b97086c1b3`
- `ASM_0006` for `worker:worker_main.output:completion_status`: Required output has no source-backed producer. The compiler suggests adding a step that explicitly produces this output.
  - Reason: The source requires this output but does not describe how it should be produced.  The output is kept in the OUTPUTS contract, but no producer step was rendered.
  - Suggested resolution: Add a source-backed step that produces worker:worker_main.output:completion_status. If the source does not specify how to produce it, mark it as optional or remove it from the required output contract.
  - Related diagnostic: `irs_5143c9abd16e`
- `ASM_0007` for `resource_contract_demand:rcd_output_s14`: Required output has no source-backed producer. The compiler suggests adding a step that explicitly produces this output.
  - Reason: The source requires this output but does not describe how it should be produced.  The output is kept in the OUTPUTS contract, but no producer step was rendered.
  - Suggested resolution: Add a source-backed step that produces resource_contract_demand:rcd_output_s14. If the source does not specify how to produce it, mark it as optional or remove it from the required output contract.
  - Related diagnostic: `irs_59fb5ecfa9e9`
- `ASM_0008` for `variable:format_preferences`: Variable has no discoverable source provenance.
  - Reason: The compiler could not trace this variable back to a source span, adapter hard fact, or producer step.  Its origin is assumed.
  - Suggested resolution: For variable:format_preferences: add source evidence (a span, adapter hint, or producer step) that justifies this variable's existence.
  - Related diagnostic: `diag_prov_0000`
- `ASM_0009` for `variable:user_request`: Variable has no discoverable source provenance.
  - Reason: The compiler could not trace this variable back to a source span, adapter hard fact, or producer step.  Its origin is assumed.
  - Suggested resolution: For variable:user_request: add source evidence (a span, adapter hint, or producer step) that justifies this variable's existence.
  - Related diagnostic: `diag_prov_0001`
- `ASM_0010` for `variable:known_topics`: Variable has no discoverable source provenance.
  - Reason: The compiler could not trace this variable back to a source span, adapter hard fact, or producer step.  Its origin is assumed.
  - Suggested resolution: For variable:known_topics: add source evidence (a span, adapter hint, or producer step) that justifies this variable's existence.
  - Related diagnostic: `diag_prov_0002`
- `ASM_0011` for `variable:timeframe`: Variable has no discoverable source provenance.
  - Reason: The compiler could not trace this variable back to a source span, adapter hard fact, or producer step.  Its origin is assumed.
  - Suggested resolution: For variable:timeframe: add source evidence (a span, adapter hint, or producer step) that justifies this variable's existence.
  - Related diagnostic: `diag_prov_0003`
- `ASM_0012` for `variable:connectors_or_source_repositories`: Variable has no discoverable source provenance.
  - Reason: The compiler could not trace this variable back to a source span, adapter hard fact, or producer step.  Its origin is assumed.
  - Suggested resolution: For variable:connectors_or_source_repositories: add source evidence (a span, adapter hint, or producer step) that justifies this variable's existence.
  - Related diagnostic: `diag_prov_0004`
- `ASM_0013` for `variable:completion_status`: Variable has no discoverable source provenance.
  - Reason: The compiler could not trace this variable back to a source span, adapter hard fact, or producer step.  Its origin is assumed.
  - Suggested resolution: For variable:completion_status: add source evidence (a span, adapter hint, or producer step) that justifies this variable's existence.
  - Related diagnostic: `diag_prov_0005`
- `ASM_0014, ASM_0015, ASM_0016, ASM_0017` for `worker_promotion:del_s30`: Worker promotion has an incomplete contract.
  - Reason: The candidate is blocked by multiple missing promotion slots.
  - Suggested resolution: Provide the missing input/output contracts, invocation point, and result handoff details listed in the related diagnostics.
  - Related diagnostics: `irs_235c6aad5e5b, irs_4d7dc95d4357, irs_3eee831e90f3, irs_40a561bc5259`

## 6. Provenance / TraceRecords

- `constraint:c_1` -> `direct`
  - Source: spans=`s18`, section=`sec_reusable_process`, packet=`p_list_item_revise_while_re_checking_constraints_do_not_finalize_if_required_slots_remain_missing_unless_the_draft_is_explicitly_marked_as_assumption_bearing_and_the_user_confirms`
  - Explanation: Constraint 'c_1' (gate): Revise while re-checking constraints. Do not finalize if required slots remain m
- `constraint:c_2` -> `direct`
  - Source: spans=`s19`, section=`sec_policies`, packet=`p_sentence_do_not_invent_links_or_unseen_facts`
  - Explanation: Constraint 'c_2' (prohibition): Do not invent links or unseen facts.
- `constraint:c_3` -> `direct`
  - Source: spans=`s20`, section=`sec_policies`, packet=`p_sentence_require_evidence_for_sourced_claims`
  - Explanation: Constraint 'c_3' (evidence): Require evidence for sourced claims.
- `constraint:c_4` -> `direct`
  - Source: spans=`s21`, section=`sec_policies`, packet=`p_sentence_limit_questions_per_turn`
  - Explanation: Constraint 'c_4' (requirement): Limit questions per turn.
- `constraint:c_5` -> `direct`
  - Source: spans=`s22`, section=`sec_policies`, packet=`p_sentence_prefer_tool_evidence_over_unnecessary_user_questioning`
  - Explanation: Constraint 'c_5' (requirement): Prefer tool evidence over unnecessary user questioning.
- `constraint:c_6` -> `direct`
  - Source: spans=`s23`, section=`sec_policies`, packet=`p_sentence_deny_finalization_if_critical_slots_are_missing_or_provenance_fails`
  - Explanation: Constraint 'c_6' (gate): Deny finalization if critical slots are missing or provenance fails.
- `flow:exc_adapter_00` -> `direct`
  - Source: spans=`s25`, section=`sec_failure_handling`, packet=`p_list_item_conflicting_instructions`
  - Explanation: Exception flow 'exc_adapter_00': conflicting instructions
- `flow:exc_adapter_01` -> `direct`
  - Source: spans=`s27`, section=`sec_failure_handling`, packet=`p_list_item_evidence_shortage`
  - Explanation: Exception flow 'exc_adapter_01': evidence
shortage
- `flow:exc_adapter_02` -> `direct`
  - Source: spans=`s26`, section=`sec_failure_handling`, packet=`p_list_item_insufficient_source_access`
  - Explanation: Exception flow 'exc_adapter_02': insufficient source access
- `flow:exc_adapter_03` -> `direct`
  - Source: spans=`s24`, section=`sec_failure_handling`, packet=`p_list_item_missing_timeframe`
  - Explanation: Exception flow 'exc_adapter_03': Missing timeframe
- `flow:exc_adapter_04` -> `direct`
  - Source: spans=`s29`, section=`sec_failure_handling`, packet=`p_list_item_provenance_failure`
  - Explanation: Exception flow 'exc_adapter_04': provenance failure
- `flow:exc_adapter_05` -> `direct`
  - Source: spans=`s28`, section=`sec_failure_handling`, packet=`p_list_item_user_refusal_to_answer`
  - Explanation: Exception flow 'exc_adapter_05': user refusal to answer
- `flow:main` -> `direct`
  - Source: spans=`s15, s16, s17`, section=`sec_reusable_process`, packet=`p_list_item_first_determine_what_kind_of_communication_is_requested_then_identify_which_required_fields_are_still_missing_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward_if_sources_are_needed_and_available`
  - Explanation: Main flow with 3 block(s).
- `profile:concept_0` -> `normalized`
  - Explanation: Concept: Internal newsletters -- Company-internal newsletter communications distributed to employees or internal stakeholders.
- `profile:concept_1` -> `normalized`
  - Explanation: Concept: Announcements -- Formal internal messages intended to inform recipients about updates, events, or decisions.
- `profile:concept_2` -> `normalized`
  - Explanation: Concept: Update digests -- Condensed summaries that compile multiple updates into a single communication.
- `profile:concept_3` -> `normalized`
  - Explanation: Concept: Executive briefs -- Concise summary documents prepared for executives, highlighting key points and status.
- `profile:concept_4` -> `normalized`
  - Explanation: Concept: Internal-comms artifacts -- Output materials used in internal communications, such as newsletters, announcements, and briefs.
- `profile:concept_5` -> `normalized`
  - Explanation: Concept: Provenance -- Traceable evidence showing where externally sourced facts came from.
- `profile:concept_6` -> `normalized`
  - Explanation: Concept: Approved source recipes -- Allowed procedures or workflows for retrieving information from sources.
- `profile:concept_7` -> `normalized`
  - Explanation: Concept: Evidence carriers -- Approved formats or containers used to hold returned evidence so it can be normalized and reused.
- `profile:concept_8` -> `normalized`
  - Explanation: Concept: Critical slots -- Required information fields that must be filled before finalization.
- `profile:persona` -> `inferred`
  - Explanation: Persona: Internal communications specialist
- `step:st_1` -> `direct`
  - Source: spans=`s15`, section=`sec_reusable_process`, packet=`p_list_item_first_determine_what_kind_of_communication_is_requested_then_identify_which_required_fields_are_still_missing_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward_if_sources_are_needed_and_available`
  - Explanation: Step 'st_1' maps to source span(s).
- `step:st_2` -> `direct`
  - Source: spans=`s15`, section=`sec_reusable_process`, packet=`p_list_item_first_determine_what_kind_of_communication_is_requested_then_identify_which_required_fields_are_still_missing_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward_if_sources_are_needed_and_available`
  - Explanation: Step 'st_2' maps to source span(s).
- `step:st_3` -> `direct`
  - Source: spans=`s16`, section=`sec_reusable_process`, packet=`p_list_item_retrieve_them_using_approved_source_recipes_maintain_provenance_for_externally_sourced_facts_when_enough_required_information_is_available`
  - Explanation: Step 'st_3' maps to source span(s).
- `step:st_4` -> `direct`
  - Source: spans=`s17`, section=`sec_reusable_process`, packet=`p_list_item_produce_a_draft_if_the_user_asks_for_revision`
  - Explanation: Step 'st_4' maps to source span(s).
- `variable:assumptions_log` -> `direct`
  - Source: spans=`s15`, section=`sec_reusable_process`, packet=`p_list_item_first_determine_what_kind_of_communication_is_requested_then_identify_which_required_fields_are_still_missing_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward_if_sources_are_needed_and_available`
  - Explanation: Variable 'assumptions_log' is produced by source-backed step 'st_1'.
- `variable:completion_status` -> `assumed` [needs confirmation]
  - Explanation: Variable 'completion_status' is declared as worker output contract with no source evidence.
- `variable:connectors_or_source_repositories` -> `assumed` [needs confirmation]
  - Explanation: Variable 'connectors_or_source_repositories' is declared as worker input contract with no source evidence.
- `variable:draft_communication_artifact` -> `direct`
  - Source: spans=`s17`, section=`sec_reusable_process`, packet=`p_list_item_produce_a_draft_if_the_user_asks_for_revision`
  - Explanation: Variable 'draft_communication_artifact' is produced by source-backed step 'st_4'.
- `variable:format_preferences` -> `assumed` [needs confirmation]
  - Explanation: Variable 'format_preferences' is declared as worker input contract with no source evidence.
- `variable:known_topics` -> `assumed` [needs confirmation]
  - Explanation: Variable 'known_topics' is declared as worker input contract with no source evidence.
- `variable:source_evidence_set` -> `direct`
  - Source: spans=`s16`, section=`sec_reusable_process`, packet=`p_list_item_retrieve_them_using_approved_source_recipes_maintain_provenance_for_externally_sourced_facts_when_enough_required_information_is_available`
  - Explanation: Variable 'source_evidence_set' is produced by source-backed step 'st_3'.
- `variable:timeframe` -> `assumed` [needs confirmation]
  - Explanation: Variable 'timeframe' is declared as worker input contract with no source evidence.
- `variable:user_request` -> `assumed` [needs confirmation]
  - Explanation: Variable 'user_request' is declared as worker input contract with no source evidence.
- `worker:MainWorker` -> `direct`
  - Source: spans=`s15, s16, s17`, section=`sec_reusable_process`, packet=`p_list_item_first_determine_what_kind_of_communication_is_requested_then_identify_which_required_fields_are_still_missing_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward_if_sources_are_needed_and_available`
  - Explanation: Main worker 'MainWorker' assembled from flow and step IRs.

## 7. Anti-Fabrication Checks

- `missing_handler`: Exception conditions without handler action stay as partial exception flows; no handler command is invented.
- `missing_output_producer`: Required outputs without a source-backed producer stay in the contract; no synthetic producer command is invented.
- `type_or_contract_ambiguity`: Unresolved worker/API contracts are reported as ambiguity; they are not downgraded to generic commands.
- Rendered SPL contains no executable `[INVOKE ...]` command.

## 8. Adapter / Validation Notes

Validation warnings:
- ConstructPlan: condition span s25 for exc_demand_00 has unowned; attached to main worker worker_main.
- ConstructPlan: condition span s27 for exc_demand_01 has unowned; attached to main worker worker_main.
- ConstructPlan: condition span s26 for exc_demand_02 has unowned; attached to main worker worker_main.
- ConstructPlan: condition span s24 for exc_demand_03 has unowned; attached to main worker worker_main.
- ConstructPlan: condition span s29 for exc_demand_04 has unowned; attached to main worker worker_main.
- ConstructPlan: condition span s28 for exc_demand_05 has unowned; attached to main worker worker_main.
- ConstructPlan: condition span s25 for exc_demand_00 has unowned; attached to main worker worker_main.
- ConstructPlan: condition span s27 for exc_demand_01 has unowned; attached to main worker worker_main.
- ConstructPlan: condition span s26 for exc_demand_02 has unowned; attached to main worker worker_main.
- ConstructPlan: condition span s24 for exc_demand_03 has unowned; attached to main worker worker_main.
- ConstructPlan: condition span s29 for exc_demand_04 has unowned; attached to main worker worker_main.
- ConstructPlan: condition span s28 for exc_demand_05 has unowned; attached to main worker worker_main.

## 9. SPL Draft

```spl
[DEFINE_AGENT: MainWorker "Orchestrate the end-to-end process and delegate to sub-tasks."]
    [DEFINE_PERSONA:]
        ROLE: Internal communications specialist
        EvidenceDriven: Produces communication drafts based on available sources and requires evidence for sourced claims.
        ConstraintAware: Checks for missing required fields, conflicting instructions, and provenance issues before finalizing.
        MinimalClarification: Asks only the highest-value clarifying questions and limits questions per turn.
        NoFabrication: Does not invent links, unseen facts, or unsupported claims.
    [END_PERSONA]
    [DEFINE_CONCEPTS:]
        Internalnewsletters: Company-internal newsletter communications distributed to employees or internal stakeholders.
        Announcements: Formal internal messages intended to inform recipients about updates, events, or decisions.
        Updatedigests: Condensed summaries that compile multiple updates into a single communication.
        Executivebriefs: Concise summary documents prepared for executives, highlighting key points and status.
        Internalcommsartifacts: Output materials used in internal communications, such as newsletters, announcements, and briefs.
        Provenance: Traceable evidence showing where externally sourced facts came from.
        Approvedsourcerecipes: Allowed procedures or workflows for retrieving information from sources.
        Evidencecarriers: Approved formats or containers used to hold returned evidence so it can be normalized and reused.
        Criticalslots: Required information fields that must be filled before finalization.
    [END_CONCEPTS]
    [DEFINE_CONSTRAINTS:]
        Gate: Revise while re-checking constraints. Do not finalize if required slots remain missing unless the draft is explicitly marked as assumption-bearing and the user confirms.
        Prohibition: Do not invent links or unseen facts.
        Evidence: Require evidence for sourced claims.
        Requirement: Limit questions per turn.
        Requirement: Prefer tool evidence over unnecessary user questioning.
        Gate: Deny finalization if critical slots are missing or provenance fails.
    [END_CONSTRAINTS]
    [DEFINE_VARIABLES:]
        "Optional preferences for the output format." format_preferences: text
        "The user's request to process." user_request: text
        "Optional topics already known or provided by the user." known_topics: List [text]
        "Optional time range or date context for the request." timeframe: text
        "Available connectors or source repositories to retrieve evidence from." connectors_or_source_repositories: List [text]
        "Draft communication output produced by the workflow." draft_communication_artifact: text
        "Collected sources and evidence supporting the draft." source_evidence_set: List [text]
        "Short log of assumptions made for unresolved items." assumptions_log: text
        "Final completion status of the workflow." completion_status: text
    [END_VARIABLES]
    [DEFINE_WORKER: "Orchestrate the end-to-end process and delegate to sub-tasks." MainWorker]
        [INPUTS]
            OPTIONAL <REF>format_preferences</REF>
            REQUIRED <REF>user_request</REF>
            OPTIONAL <REF>known_topics</REF>
            OPTIONAL <REF>timeframe</REF>
            REQUIRED <REF>connectors_or_source_repositories</REF>
        [END_INPUTS]
        [OUTPUTS]
            REQUIRED <REF>draft_communication_artifact</REF>
            REQUIRED <REF>source_evidence_set</REF>
            REQUIRED <REF>assumptions_log</REF>
            REQUIRED <REF>completion_status</REF>
        [END_OUTPUTS]
        [MAIN_FLOW]
            [SEQUENTIAL_BLOCK]
                COMMAND-1 [COMMAND Determine the communication type and identify missing required fields based on <REF>user_request</REF> RESULT assumptions_log: text SET]
                COMMAND-2 [INPUT Ask the user the highest-value clarifying questions based on <REF>user_request</REF> VALUE user_input:text SET]
            [END_SEQUENTIAL_BLOCK]
            DECISION-1 [IF sources are needed and available]
                COMMAND-3 [COMMAND Retrieve approved source evidence and maintain provenance for externally sourced facts based on <REF>connectors_or_source_repositories</REF> RESULT source_evidence_set: List [text] SET]
            [END_IF]
            [SEQUENTIAL_BLOCK]
                COMMAND-4 [COMMAND Produce the draft communication artifact based on <REF>user_request</REF>, <REF>source_evidence_set</REF>, <REF>known_topics</REF>, <REF>timeframe</REF>, and <REF>format_preferences</REF> RESULT draft_communication_artifact: text SET]
            [END_SEQUENTIAL_BLOCK]
        [END_MAIN_FLOW]
        [EXCEPTION_FLOW: conflicting instructions]
        [END_EXCEPTION_FLOW]
        [EXCEPTION_FLOW: evidence shortage]
        [END_EXCEPTION_FLOW]
        [EXCEPTION_FLOW: insufficient source access]
        [END_EXCEPTION_FLOW]
        [EXCEPTION_FLOW: Missing timeframe]
        [END_EXCEPTION_FLOW]
        [EXCEPTION_FLOW: provenance failure]
        [END_EXCEPTION_FLOW]
        [EXCEPTION_FLOW: user refusal to answer]
        [END_EXCEPTION_FLOW]
    [END_WORKER]
[END_AGENT]
```
