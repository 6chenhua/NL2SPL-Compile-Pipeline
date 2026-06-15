# NL2SPL Feedback Report

## 1. Overall Compile State

- Completeness: `partial`
- SPL draft generated: `yes`
- Compile diagnostics: `17`
- Assumptions / suggestions: `16`
- Trace records: `59`
- Adapter warnings: `0`
- Validation errors: `0`
- Validation warnings: `16`

Result is partial because the following requirement gaps remain:
- `missing_handler` on `worker:worker_main.exception_flow:exc_adapter_02`: Exception flow 'exc_adapter_02' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_02, slot=handler_action]
- `missing_handler` on `worker:worker_main.exception_flow:exc_adapter_01`: Exception flow 'exc_adapter_01' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_01, slot=handler_action]
- `missing_handler` on `worker:worker_main.exception_flow:exc_adapter_04`: Exception flow 'exc_adapter_04' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_04, slot=handler_action]
- `missing_handler` on `worker:worker_main.exception_flow:exc_adapter_05`: Exception flow 'exc_adapter_05' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_05, slot=handler_action]
- `missing_handler` on `worker:worker_main.exception_flow:exc_adapter_00`: Exception flow 'exc_adapter_00' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_00, slot=handler_action]
- `missing_handler` on `worker:worker_main.exception_flow:exc_adapter_03`: Exception flow 'exc_adapter_03' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_03, slot=handler_action]
- `missing_output_producer` on `resource_contract_demand:rcd_output_s13`: Resource contract output 'rcd_output_s13' (requiredness=required) has materialized resource(s) assumptions_log but no renderable producer. [construct=resource_contract_demand:rcd_output_s13, slot=producer]
- `missing_output_producer` on `worker:worker_main.output:assumptions_log`: Required output 'assumptions_log' (Short log of assumptions for unresolved items.) has no source-backed producer step. [construct=worker:worker_main.output:assumptions_log, slot=producer]
- `type_or_contract_ambiguity` on `worker_promotion:candidate_retrieve_approved_sources`: Missing accepted decision or matching handoff with invocation hint [construct=worker_promotion:candidate_retrieve_approved_sources, slot=promotion_invocation_point]

## 2. Materialized Source-Backed Structure

### Workers
- `worker:MainWorker` (direct) -- spans=s15, s16; section=sec_reusable_process; packet=p_list_item_first_determine_what_kind_of_communication_is_requested_then_identify_which_required_fields_are_still_missing_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward_if_sources_are_needed_and_available
- `worker:Worker_draft_communication` (direct) -- spans=s17, s18, s23; section=sec_reusable_process; packet=p_list_item_produce_a_draft_if_the_user_asks_for_revision
- `worker:draft_communication.variable:clarifying_questions` (direct) -- spans=s15; section=sec_reusable_process; packet=p_list_item_first_determine_what_kind_of_communication_is_requested_then_identify_which_required_fields_are_still_missing_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward_if_sources_are_needed_and_available
- `worker:draft_communication.variable:clarifying_questions` (direct) -- spans=s15; section=sec_reusable_process; packet=p_list_item_first_determine_what_kind_of_communication_is_requested_then_identify_which_required_fields_are_still_missing_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward_if_sources_are_needed_and_available
- `worker:draft_communication.variable:communication_type` (direct) -- spans=s15; section=sec_reusable_process; packet=p_list_item_first_determine_what_kind_of_communication_is_requested_then_identify_which_required_fields_are_still_missing_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward_if_sources_are_needed_and_available
- `worker:draft_communication.variable:communication_type` (direct) -- spans=s15; section=sec_reusable_process; packet=p_list_item_first_determine_what_kind_of_communication_is_requested_then_identify_which_required_fields_are_still_missing_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward_if_sources_are_needed_and_available
- `worker:draft_communication.variable:completion_status` (direct) -- spans=s16; section=sec_reusable_process; packet=p_list_item_retrieve_them_using_approved_source_recipes_maintain_provenance_for_externally_sourced_facts_when_enough_required_information_is_available
- `worker:draft_communication.variable:completion_status` (direct) -- spans=s16; section=sec_reusable_process; packet=p_list_item_retrieve_them_using_approved_source_recipes_maintain_provenance_for_externally_sourced_facts_when_enough_required_information_is_available
- `worker:draft_communication.variable:draft_communication_artifact` (direct) -- spans=s16; section=sec_reusable_process; packet=p_list_item_retrieve_them_using_approved_source_recipes_maintain_provenance_for_externally_sourced_facts_when_enough_required_information_is_available
- `worker:draft_communication.variable:draft_communication_artifact` (direct) -- spans=s16; section=sec_reusable_process; packet=p_list_item_retrieve_them_using_approved_source_recipes_maintain_provenance_for_externally_sourced_facts_when_enough_required_information_is_available
- `worker:draft_communication.variable:missing_required_fields` (direct) -- spans=s15; section=sec_reusable_process; packet=p_list_item_first_determine_what_kind_of_communication_is_requested_then_identify_which_required_fields_are_still_missing_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward_if_sources_are_needed_and_available
- `worker:draft_communication.variable:missing_required_fields` (direct) -- spans=s15; section=sec_reusable_process; packet=p_list_item_first_determine_what_kind_of_communication_is_requested_then_identify_which_required_fields_are_still_missing_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward_if_sources_are_needed_and_available
- `worker:draft_communication.variable:source_evidence_set` (direct) -- spans=s16; section=sec_reusable_process; packet=p_list_item_retrieve_them_using_approved_source_recipes_maintain_provenance_for_externally_sourced_facts_when_enough_required_information_is_available
- `worker:draft_communication.variable:source_evidence_set` (direct) -- spans=s16; section=sec_reusable_process; packet=p_list_item_retrieve_them_using_approved_source_recipes_maintain_provenance_for_externally_sourced_facts_when_enough_required_information_is_available

### Flows
- `flow:exc_adapter_00` (direct) -- spans=s25; section=sec_failure_handling; packet=p_list_item_conflicting_instructions
- `flow:exc_adapter_01` (direct) -- spans=s27; section=sec_failure_handling; packet=p_list_item_evidence_shortage
- `flow:exc_adapter_02` (direct) -- spans=s26; section=sec_failure_handling; packet=p_list_item_insufficient_source_access
- `flow:exc_adapter_03` (direct) -- spans=s24; section=sec_failure_handling; packet=p_list_item_missing_timeframe
- `flow:exc_adapter_04` (direct) -- spans=s29; section=sec_failure_handling; packet=p_list_item_provenance_failure
- `flow:exc_adapter_05` (direct) -- spans=s28; section=sec_failure_handling; packet=p_list_item_user_refusal_to_answer
- `flow:main` (direct) -- spans=s15, s16; section=sec_reusable_process; packet=p_list_item_first_determine_what_kind_of_communication_is_requested_then_identify_which_required_fields_are_still_missing_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward_if_sources_are_needed_and_available

### Steps
- `step:st_1` (direct) -- spans=s15; section=sec_reusable_process; packet=p_list_item_first_determine_what_kind_of_communication_is_requested_then_identify_which_required_fields_are_still_missing_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward_if_sources_are_needed_and_available
- `step:st_1` (direct) -- spans=s17; section=sec_reusable_process; packet=p_list_item_produce_a_draft_if_the_user_asks_for_revision
- `step:st_2` (direct) -- spans=s15; section=sec_reusable_process; packet=p_list_item_first_determine_what_kind_of_communication_is_requested_then_identify_which_required_fields_are_still_missing_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward_if_sources_are_needed_and_available
- `step:st_2` (direct) -- spans=s18; section=sec_reusable_process; packet=p_list_item_revise_while_re_checking_constraints_do_not_finalize_if_required_slots_remain_missing_unless_the_draft_is_explicitly_marked_as_assumption_bearing_and_the_user_confirms
- `step:st_3` (direct) -- spans=s15; section=sec_reusable_process; packet=p_list_item_first_determine_what_kind_of_communication_is_requested_then_identify_which_required_fields_are_still_missing_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward_if_sources_are_needed_and_available
- `step:st_4` (direct) -- spans=s16; section=sec_reusable_process; packet=p_list_item_retrieve_them_using_approved_source_recipes_maintain_provenance_for_externally_sourced_facts_when_enough_required_information_is_available
- `step:st_5` (direct) -- spans=s16; section=sec_reusable_process; packet=p_list_item_retrieve_them_using_approved_source_recipes_maintain_provenance_for_externally_sourced_facts_when_enough_required_information_is_available
- `step:st_invoke_handoff_draft_communication` (direct) -- spans=s16; section=sec_reusable_process; packet=p_list_item_retrieve_them_using_approved_source_recipes_maintain_provenance_for_externally_sourced_facts_when_enough_required_information_is_available

### Constraints
- `constraint:c_1` (direct) -- spans=s19; section=sec_policies; packet=p_sentence_do_not_invent_links_or_unseen_facts
- `constraint:c_2` (direct) -- spans=s20; section=sec_policies; packet=p_sentence_require_evidence_for_sourced_claims
- `constraint:c_3` (direct) -- spans=s21; section=sec_policies; packet=p_sentence_limit_questions_per_turn
- `constraint:c_4` (direct) -- spans=s22; section=sec_policies; packet=p_sentence_prefer_tool_evidence_over_unnecessary_user_questioning
- `constraint:c_5` (direct) -- spans=s23; section=sec_policies; packet=p_sentence_deny_finalization_if_critical_slots_are_missing_or_provenance_fails

### Handoffs
- `handoff:handoff_draft_communication` (direct) -- spans=s16; section=sec_reusable_process; packet=p_list_item_retrieve_them_using_approved_source_recipes_maintain_provenance_for_externally_sourced_facts_when_enough_required_information_is_available

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
- `resource_contract_demand:rcd_output_s13`: `missing_output_producer` -- Resource contract output 'rcd_output_s13' (requiredness=required) has materialized resource(s) assumptions_log but no renderable producer. [construct=resource_contract_demand:rcd_output_s13, slot=producer]
  - Suggested resolution: Add a source-backed step or handoff that produces the materialized resource name with the same resource kind.
- `worker:worker_main.output:assumptions_log`: `missing_output_producer` -- Required output 'assumptions_log' (Short log of assumptions for unresolved items.) has no source-backed producer step. [construct=worker:worker_main.output:assumptions_log, slot=producer]
  - Suggested resolution: Add a step that produces 'assumptions_log'. If the source requirement does not specify how to produce this output, mark it as optional or remove it from the output contract.
- `worker_promotion:candidate_retrieve_approved_sources`: `type_or_contract_ambiguity` -- Missing accepted decision or matching handoff with invocation hint [construct=worker_promotion:candidate_retrieve_approved_sources, slot=promotion_invocation_point]

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

### irs_b0d25f2c1af8: `missing_output_producer`
- Severity: `warning`
- Target: `resource_contract_demand:rcd_output_s13`
- Source spans: `s13`
- Message: Resource contract output 'rcd_output_s13' (requiredness=required) has materialized resource(s) assumptions_log but no renderable producer. [construct=resource_contract_demand:rcd_output_s13, slot=producer]
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Add a source-backed step or handoff that produces the materialized resource name with the same resource kind.
- Missing slot: `producer`
- Missing reason: Resource contract output 'rcd_output_s13' (requiredness=required) has materialized resource(s) assumptions_log but no renderable producer.

### irs_b1d5e94c6aec: `missing_output_producer`
- Severity: `warning`
- Target: `worker:worker_main.output:assumptions_log`
- Message: Required output 'assumptions_log' (Short log of assumptions for unresolved items.) has no source-backed producer step. [construct=worker:worker_main.output:assumptions_log, slot=producer]
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Add a step that produces 'assumptions_log'. If the source requirement does not specify how to produce this output, mark it as optional or remove it from the output contract.
- Missing slot: `producer`
- Missing reason: Required output 'assumptions_log' (Short log of assumptions for unresolved items.) has no source-backed producer step.

### irs_1731a8298869: `type_or_contract_ambiguity`
- Severity: `warning`
- Target: `worker_promotion:candidate_retrieve_approved_sources`
- Source spans: `s16, s22, s30`
- Message: Missing accepted decision or matching handoff with invocation hint [construct=worker_promotion:candidate_retrieve_approved_sources, slot=promotion_invocation_point]
- Blocks rendering: `false`
- Blocks completion: `true`
- Missing slot: `promotion_invocation_point`
- Missing reason: Missing accepted decision or matching handoff with invocation hint

### diag_prov_0000: `missing_provenance`
- Severity: `warning`
- Target: `worker:draft_communication.variable:format_preferences`
- Message: Variable 'format_preferences' (text) is a contract input with no source-backed producer or adapter evidence.
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_prov_0001: `missing_provenance`
- Severity: `warning`
- Target: `worker:draft_communication.variable:user_request`
- Message: Variable 'user_request' (text) is a contract input with no source-backed producer or adapter evidence.
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_prov_0002: `missing_provenance`
- Severity: `warning`
- Target: `worker:draft_communication.variable:known_topics`
- Message: Variable 'known_topics' (List[text]) is a contract input with no source-backed producer or adapter evidence.
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_prov_0003: `missing_provenance`
- Severity: `warning`
- Target: `worker:draft_communication.variable:timeframe`
- Message: Variable 'timeframe' (text) is a contract input with no source-backed producer or adapter evidence.
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_prov_0004: `missing_provenance`
- Severity: `warning`
- Target: `worker:draft_communication.variable:available_connectors_or_source_repositories`
- Message: Variable 'available_connectors_or_source_repositories' (List[text]) is a contract input with no source-backed producer or adapter evidence.
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_prov_0005: `missing_provenance`
- Severity: `warning`
- Target: `worker:draft_communication.variable:assumptions_log`
- Message: Variable 'assumptions_log' (text) is a contract output with no source-backed producer or adapter evidence.
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_prov_0006: `missing_provenance`
- Severity: `warning`
- Target: `worker:draft_communication.variable:source_access_needed`
- Message: Variable 'source_access_needed' (boolean) has no source-backed producer and no contract section evidence.
- Blocks rendering: `false`
- Blocks completion: `false`

### stage2_route_refinement_diagnostic_: `route_refinement_diagnostic`
- Severity: `info`
- Message: LLM route diagnostic [prior_overridden] span='s1': Structural prior suggested a generic domain field, but the text is a profile/domain artifact type.
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
- `ASM_0006` for `worker:worker_main.output:assumptions_log`: Required output has no source-backed producer. The compiler suggests adding a step that explicitly produces this output.
  - Reason: The source requires this output but does not describe how it should be produced.  The output is kept in the OUTPUTS contract, but no producer step was rendered.
  - Suggested resolution: Add a source-backed step that produces worker:worker_main.output:assumptions_log. If the source does not specify how to produce it, mark it as optional or remove it from the required output contract.
  - Related diagnostic: `irs_b1d5e94c6aec`
- `ASM_0007` for `resource_contract_demand:rcd_output_s13`: Required output has no source-backed producer. The compiler suggests adding a step that explicitly produces this output.
  - Reason: The source requires this output but does not describe how it should be produced.  The output is kept in the OUTPUTS contract, but no producer step was rendered.
  - Suggested resolution: Add a source-backed step that produces resource_contract_demand:rcd_output_s13. If the source does not specify how to produce it, mark it as optional or remove it from the required output contract.
  - Related diagnostic: `irs_b0d25f2c1af8`
- `ASM_0008` for `worker:draft_communication.variable:format_preferences`: Variable has no discoverable source provenance.
  - Reason: The compiler could not trace this variable back to a source span, adapter hard fact, or producer step.  Its origin is assumed.
  - Suggested resolution: For worker:draft_communication.variable:format_preferences: add source evidence (a span, adapter hint, or producer step) that justifies this variable's existence.
  - Related diagnostic: `diag_prov_0000`
- `ASM_0009` for `worker:draft_communication.variable:user_request`: Variable has no discoverable source provenance.
  - Reason: The compiler could not trace this variable back to a source span, adapter hard fact, or producer step.  Its origin is assumed.
  - Suggested resolution: For worker:draft_communication.variable:user_request: add source evidence (a span, adapter hint, or producer step) that justifies this variable's existence.
  - Related diagnostic: `diag_prov_0001`
- `ASM_0010` for `worker:draft_communication.variable:known_topics`: Variable has no discoverable source provenance.
  - Reason: The compiler could not trace this variable back to a source span, adapter hard fact, or producer step.  Its origin is assumed.
  - Suggested resolution: For worker:draft_communication.variable:known_topics: add source evidence (a span, adapter hint, or producer step) that justifies this variable's existence.
  - Related diagnostic: `diag_prov_0002`
- `ASM_0011` for `worker:draft_communication.variable:timeframe`: Variable has no discoverable source provenance.
  - Reason: The compiler could not trace this variable back to a source span, adapter hard fact, or producer step.  Its origin is assumed.
  - Suggested resolution: For worker:draft_communication.variable:timeframe: add source evidence (a span, adapter hint, or producer step) that justifies this variable's existence.
  - Related diagnostic: `diag_prov_0003`
- `ASM_0012` for `worker:draft_communication.variable:available_connectors_or_source_repositories`: Variable has no discoverable source provenance.
  - Reason: The compiler could not trace this variable back to a source span, adapter hard fact, or producer step.  Its origin is assumed.
  - Suggested resolution: For worker:draft_communication.variable:available_connectors_or_source_repositories: add source evidence (a span, adapter hint, or producer step) that justifies this variable's existence.
  - Related diagnostic: `diag_prov_0004`
- `ASM_0013` for `worker:draft_communication.variable:assumptions_log`: Variable has no discoverable source provenance.
  - Reason: The compiler could not trace this variable back to a source span, adapter hard fact, or producer step.  Its origin is assumed.
  - Suggested resolution: For worker:draft_communication.variable:assumptions_log: add source evidence (a span, adapter hint, or producer step) that justifies this variable's existence.
  - Related diagnostic: `diag_prov_0005`
- `ASM_0014` for `worker:draft_communication.variable:source_access_needed`: Variable has no discoverable source provenance.
  - Reason: The compiler could not trace this variable back to a source span, adapter hard fact, or producer step.  Its origin is assumed.
  - Suggested resolution: For worker:draft_communication.variable:source_access_needed: add source evidence (a span, adapter hint, or producer step) that justifies this variable's existence.
  - Related diagnostic: `diag_prov_0006`
- `ASM_0015` for `worker_promotion:candidate_retrieve_approved_sources`: Command has an ambiguous or incomplete contract. The compiler suggests providing the missing contract detail.
  - Reason: A command references an API, worker, or input source that is not fully specified.  The compiler cannot materialize the command without this information.
  - Suggested resolution: For worker_promotion:candidate_retrieve_approved_sources: provide the missing contract detail (API name, worker target, IO bindings, or source evidence).  See the related diagnostic for specifics.
  - Related diagnostic: `irs_1731a8298869`

## 6. Provenance / TraceRecords

- `constraint:c_1` -> `direct`
  - Source: spans=`s19`, section=`sec_policies`, packet=`p_sentence_do_not_invent_links_or_unseen_facts`
  - Explanation: Constraint 'c_1' (prohibition): Do not invent links or unseen facts
- `constraint:c_2` -> `direct`
  - Source: spans=`s20`, section=`sec_policies`, packet=`p_sentence_require_evidence_for_sourced_claims`
  - Explanation: Constraint 'c_2' (evidence): Require evidence for sourced claims
- `constraint:c_3` -> `direct`
  - Source: spans=`s21`, section=`sec_policies`, packet=`p_sentence_limit_questions_per_turn`
  - Explanation: Constraint 'c_3' (requirement): Limit questions per turn
- `constraint:c_4` -> `direct`
  - Source: spans=`s22`, section=`sec_policies`, packet=`p_sentence_prefer_tool_evidence_over_unnecessary_user_questioning`
  - Explanation: Constraint 'c_4' (requirement): Prefer tool evidence over unnecessary user questioning
- `constraint:c_5` -> `direct`
  - Source: spans=`s23`, section=`sec_policies`, packet=`p_sentence_deny_finalization_if_critical_slots_are_missing_or_provenance_fails`
  - Explanation: Constraint 'c_5' (gate): Deny finalization if critical slots are missing or provenance fails
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
  - Source: spans=`s15, s16`, section=`sec_reusable_process`, packet=`p_list_item_first_determine_what_kind_of_communication_is_requested_then_identify_which_required_fields_are_still_missing_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward_if_sources_are_needed_and_available`
  - Explanation: Main flow with 1 block(s).
- `handoff:handoff_draft_communication` -> `direct`
  - Source: spans=`s16`, section=`sec_reusable_process`, packet=`p_list_item_retrieve_them_using_approved_source_recipes_maintain_provenance_for_externally_sourced_facts_when_enough_required_information_is_available`
  - Explanation: Handoff 'handoff_draft_communication' (worker_main invoke to draft_communication) with 3 input(s) and 2 output(s).
- `profile:concept_0` -> `normalized`
  - Explanation: Concept: Internal newsletters -- Recurring internal communications sent within an organization to share updates and information.
- `profile:concept_1` -> `normalized`
  - Explanation: Concept: Announcements -- Formal internal messages intended to broadcast important information.
- `profile:concept_2` -> `normalized`
  - Explanation: Concept: Update digests -- Condensed summaries of recent updates collected into a single communication.
- `profile:concept_3` -> `normalized`
  - Explanation: Concept: Executive briefs -- Short, high-level summaries prepared for executives.
- `profile:concept_4` -> `normalized`
  - Explanation: Concept: Internal-comms artifacts -- Documents or outputs used in internal communications work, such as newsletters, briefs, or announcements.
- `profile:concept_5` -> `normalized`
  - Explanation: Concept: Provenance -- The traceable origin and evidence trail for facts used in the draft.
- `profile:concept_6` -> `normalized`
  - Explanation: Concept: Approved source recipes -- Permitted methods or procedures for retrieving information from sources.
- `profile:concept_7` -> `normalized`
  - Explanation: Concept: Approved evidence carriers -- Accepted formats or containers used to store and return supporting evidence.
- `profile:concept_8` -> `normalized`
  - Explanation: Concept: Assumption-bearing -- Marked as containing unresolved assumptions rather than fully verified information.
- `profile:persona` -> `inferred`
  - Explanation: Persona: Internal communications specialist
- `step:st_1` -> `direct`
  - Source: spans=`s15`, section=`sec_reusable_process`, packet=`p_list_item_first_determine_what_kind_of_communication_is_requested_then_identify_which_required_fields_are_still_missing_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward_if_sources_are_needed_and_available`
  - Explanation: Step 'st_1' maps to source span(s).
- `step:st_1` -> `direct`
  - Source: spans=`s17`, section=`sec_reusable_process`, packet=`p_list_item_produce_a_draft_if_the_user_asks_for_revision`
  - Explanation: Step 'st_1' maps to source span(s).
- `step:st_2` -> `direct`
  - Source: spans=`s15`, section=`sec_reusable_process`, packet=`p_list_item_first_determine_what_kind_of_communication_is_requested_then_identify_which_required_fields_are_still_missing_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward_if_sources_are_needed_and_available`
  - Explanation: Step 'st_2' maps to source span(s).
- `step:st_2` -> `direct`
  - Source: spans=`s18`, section=`sec_reusable_process`, packet=`p_list_item_revise_while_re_checking_constraints_do_not_finalize_if_required_slots_remain_missing_unless_the_draft_is_explicitly_marked_as_assumption_bearing_and_the_user_confirms`
  - Explanation: Step 'st_2' maps to source span(s).
- `step:st_3` -> `direct`
  - Source: spans=`s15`, section=`sec_reusable_process`, packet=`p_list_item_first_determine_what_kind_of_communication_is_requested_then_identify_which_required_fields_are_still_missing_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward_if_sources_are_needed_and_available`
  - Explanation: Step 'st_3' maps to source span(s).
- `step:st_4` -> `direct`
  - Source: spans=`s16`, section=`sec_reusable_process`, packet=`p_list_item_retrieve_them_using_approved_source_recipes_maintain_provenance_for_externally_sourced_facts_when_enough_required_information_is_available`
  - Explanation: Step 'st_4' maps to source span(s).
- `step:st_5` -> `direct`
  - Source: spans=`s16`, section=`sec_reusable_process`, packet=`p_list_item_retrieve_them_using_approved_source_recipes_maintain_provenance_for_externally_sourced_facts_when_enough_required_information_is_available`
  - Explanation: Step 'st_5' maps to source span(s).
- `step:st_invoke_handoff_draft_communication` -> `direct`
  - Source: spans=`s16`, section=`sec_reusable_process`, packet=`p_list_item_retrieve_them_using_approved_source_recipes_maintain_provenance_for_externally_sourced_facts_when_enough_required_information_is_available`
  - Explanation: Step 'st_invoke_handoff_draft_communication' maps to source span(s).
- `worker:MainWorker` -> `direct`
  - Source: spans=`s15, s16`, section=`sec_reusable_process`, packet=`p_list_item_first_determine_what_kind_of_communication_is_requested_then_identify_which_required_fields_are_still_missing_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward_if_sources_are_needed_and_available`
  - Explanation: Main worker 'MainWorker' assembled from flow and step IRs.
- `worker:Worker_draft_communication` -> `direct`
  - Source: spans=`s17, s18, s23`, section=`sec_reusable_process`, packet=`p_list_item_produce_a_draft_if_the_user_asks_for_revision`
  - Explanation: Child worker 'Worker_draft_communication' extracted from delegation pattern.
- `worker:draft_communication.variable:assumptions_log` -> `assumed` [needs confirmation]
  - Explanation: Variable 'assumptions_log' is declared as worker output contract with no source evidence.
- `worker:draft_communication.variable:assumptions_log` -> `assumed` [needs confirmation]
  - Explanation: Variable 'assumptions_log' is declared as worker input contract with no source evidence.
- `worker:draft_communication.variable:available_connectors_or_source_repositories` -> `assumed` [needs confirmation]
  - Explanation: Variable 'available_connectors_or_source_repositories' is declared as worker input contract with no source evidence.
- `worker:draft_communication.variable:available_connectors_or_source_repositories` -> `assumed` [needs confirmation]
  - Explanation: Variable 'available_connectors_or_source_repositories' is declared as worker input contract with no source evidence.
- `worker:draft_communication.variable:clarifying_questions` -> `direct`
  - Source: spans=`s15`, section=`sec_reusable_process`, packet=`p_list_item_first_determine_what_kind_of_communication_is_requested_then_identify_which_required_fields_are_still_missing_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward_if_sources_are_needed_and_available`
  - Explanation: Variable 'clarifying_questions' is produced by source-backed step 'st_3'.
- `worker:draft_communication.variable:clarifying_questions` -> `direct`
  - Source: spans=`s15`, section=`sec_reusable_process`, packet=`p_list_item_first_determine_what_kind_of_communication_is_requested_then_identify_which_required_fields_are_still_missing_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward_if_sources_are_needed_and_available`
  - Explanation: Variable 'clarifying_questions' is produced by source-backed step 'st_3'.
- `worker:draft_communication.variable:communication_type` -> `direct`
  - Source: spans=`s15`, section=`sec_reusable_process`, packet=`p_list_item_first_determine_what_kind_of_communication_is_requested_then_identify_which_required_fields_are_still_missing_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward_if_sources_are_needed_and_available`
  - Explanation: Variable 'communication_type' is produced by source-backed step 'st_1'.
- `worker:draft_communication.variable:communication_type` -> `direct`
  - Source: spans=`s15`, section=`sec_reusable_process`, packet=`p_list_item_first_determine_what_kind_of_communication_is_requested_then_identify_which_required_fields_are_still_missing_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward_if_sources_are_needed_and_available`
  - Explanation: Variable 'communication_type' is produced by source-backed step 'st_1'.
- `worker:draft_communication.variable:completion_status` -> `direct`
  - Source: spans=`s16`, section=`sec_reusable_process`, packet=`p_list_item_retrieve_them_using_approved_source_recipes_maintain_provenance_for_externally_sourced_facts_when_enough_required_information_is_available`
  - Explanation: Variable 'completion_status' is produced by source-backed step 'st_invoke_handoff_draft_communication'.
- `worker:draft_communication.variable:completion_status` -> `direct`
  - Source: spans=`s16`, section=`sec_reusable_process`, packet=`p_list_item_retrieve_them_using_approved_source_recipes_maintain_provenance_for_externally_sourced_facts_when_enough_required_information_is_available`
  - Explanation: Variable 'completion_status' is produced by source-backed step 'st_invoke_handoff_draft_communication'.
- `worker:draft_communication.variable:draft_communication_artifact` -> `direct`
  - Source: spans=`s16`, section=`sec_reusable_process`, packet=`p_list_item_retrieve_them_using_approved_source_recipes_maintain_provenance_for_externally_sourced_facts_when_enough_required_information_is_available`
  - Explanation: Variable 'draft_communication_artifact' is produced by source-backed step 'st_invoke_handoff_draft_communication'.
- `worker:draft_communication.variable:draft_communication_artifact` -> `direct`
  - Source: spans=`s16`, section=`sec_reusable_process`, packet=`p_list_item_retrieve_them_using_approved_source_recipes_maintain_provenance_for_externally_sourced_facts_when_enough_required_information_is_available`
  - Explanation: Variable 'draft_communication_artifact' is produced by source-backed step 'st_invoke_handoff_draft_communication'.
- `worker:draft_communication.variable:format_preferences` -> `assumed` [needs confirmation]
  - Explanation: Variable 'format_preferences' is declared as worker input contract with no source evidence.
- `worker:draft_communication.variable:format_preferences` -> `assumed` [needs confirmation]
  - Explanation: Variable 'format_preferences' is declared as worker input contract with no source evidence.
- `worker:draft_communication.variable:known_topics` -> `assumed` [needs confirmation]
  - Explanation: Variable 'known_topics' is declared as worker input contract with no source evidence.
- `worker:draft_communication.variable:known_topics` -> `assumed` [needs confirmation]
  - Explanation: Variable 'known_topics' is declared as worker input contract with no source evidence.
- `worker:draft_communication.variable:missing_required_fields` -> `direct`
  - Source: spans=`s15`, section=`sec_reusable_process`, packet=`p_list_item_first_determine_what_kind_of_communication_is_requested_then_identify_which_required_fields_are_still_missing_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward_if_sources_are_needed_and_available`
  - Explanation: Variable 'missing_required_fields' is produced by source-backed step 'st_2'.
- `worker:draft_communication.variable:missing_required_fields` -> `direct`
  - Source: spans=`s15`, section=`sec_reusable_process`, packet=`p_list_item_first_determine_what_kind_of_communication_is_requested_then_identify_which_required_fields_are_still_missing_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward_if_sources_are_needed_and_available`
  - Explanation: Variable 'missing_required_fields' is produced by source-backed step 'st_2'.
- `worker:draft_communication.variable:source_access_needed` -> `assumed` [needs confirmation]
  - Explanation: Variable 'source_access_needed' is a declared step variable with no discoverable source provenance.
- `worker:draft_communication.variable:source_access_needed` -> `assumed` [needs confirmation]
  - Explanation: Variable 'source_access_needed' is a declared step variable with no discoverable source provenance.
- `worker:draft_communication.variable:source_evidence_set` -> `direct`
  - Source: spans=`s16`, section=`sec_reusable_process`, packet=`p_list_item_retrieve_them_using_approved_source_recipes_maintain_provenance_for_externally_sourced_facts_when_enough_required_information_is_available`
  - Explanation: Variable 'source_evidence_set' is produced by source-backed step 'st_4'.
- `worker:draft_communication.variable:source_evidence_set` -> `direct`
  - Source: spans=`s16`, section=`sec_reusable_process`, packet=`p_list_item_retrieve_them_using_approved_source_recipes_maintain_provenance_for_externally_sourced_facts_when_enough_required_information_is_available`
  - Explanation: Variable 'source_evidence_set' is produced by source-backed step 'st_4'.
- `worker:draft_communication.variable:timeframe` -> `assumed` [needs confirmation]
  - Explanation: Variable 'timeframe' is declared as worker input contract with no source evidence.
- `worker:draft_communication.variable:timeframe` -> `assumed` [needs confirmation]
  - Explanation: Variable 'timeframe' is declared as worker input contract with no source evidence.
- `worker:draft_communication.variable:user_request` -> `assumed` [needs confirmation]
  - Explanation: Variable 'user_request' is declared as worker input contract with no source evidence.
- `worker:draft_communication.variable:user_request` -> `assumed` [needs confirmation]
  - Explanation: Variable 'user_request' is declared as worker input contract with no source evidence.

## 7. Anti-Fabrication Checks

- `missing_handler`: Exception conditions without handler action stay as partial exception flows; no handler command is invented.
- `missing_output_producer`: Required outputs without a source-backed producer stay in the contract; no synthetic producer command is invented.
- `type_or_contract_ambiguity`: Unresolved worker/API contracts are reported as ambiguity; they are not downgraded to generic commands.

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
- Worker worker_main: variable 'source_access_needed' consumed but not produced or declared as input
- Worker worker_main: variable 'assumptions_log' consumed but not produced or declared as input
- Worker draft_communication: variable 'completion_status' produced by multiple steps
- Worker draft_communication: variable 'missing_required_fields' consumed but not produced or declared as input

## 9. SPL Draft

```spl
[DEFINE_AGENT: MainWorker "Orchestrate the end-to-end process and delegate to sub-tasks."]
    [DEFINE_PERSONA:]
        ROLE: Internal communications specialist
        EvidenceDriven: Produces drafts only when required information is available and sourced claims have evidence.
        ConstraintAware: Checks missing required fields, re-checks constraints during revision, and avoids finalizing when critical slots are missing.
        ProvenanceFocused: Maintains provenance for externally sourced facts and requires evidence for sourced claims.
        ConciseQuestioning: Asks only the highest-value clarifying questions and limits questions per turn.
    [END_PERSONA]
    [DEFINE_CONCEPTS:]
        Internalnewsletters: Recurring internal communications sent within an organization to share updates and information.
        Announcements: Formal internal messages intended to broadcast important information.
        Updatedigests: Condensed summaries of recent updates collected into a single communication.
        Executivebriefs: Short, high-level summaries prepared for executives.
        Internalcommsartifacts: Documents or outputs used in internal communications work, such as newsletters, briefs, or announcements.
        Provenance: The traceable origin and evidence trail for facts used in the draft.
        Approvedsourcerecipes: Permitted methods or procedures for retrieving information from sources.
        Approvedevidencecarriers: Accepted formats or containers used to store and return supporting evidence.
        Assumptionbearing: Marked as containing unresolved assumptions rather than fully verified information.
    [END_CONCEPTS]
    [DEFINE_CONSTRAINTS:]
        Prohibition: Do not invent links or unseen facts
        Evidence: Require evidence for sourced claims
        Requirement: Limit questions per turn
        Requirement: Prefer tool evidence over unnecessary user questioning
        Gate: Deny finalization if critical slots are missing or provenance fails
    [END_CONSTRAINTS]
    [DEFINE_VARIABLES:]
        "Optional user format preferences." format_preferences: text
        "The user's request." user_request: text
        "Optional topics already known to be relevant." known_topics: List [text]
        "Optional time range or deadline context." timeframe: text
        "Available connectors or source repositories." available_connectors_or_source_repositories: List [text]
        "Draft communication artifact to be produced." draft_communication_artifact: text
        "Evidence set supporting sourced facts." source_evidence_set: List [text]
        "Short log of assumptions for unresolved items." assumptions_log: text
        "Final completion status." completion_status: text
        "Identified kind of communication requested." communication_type: text
        "Required fields that are still missing." missing_required_fields: List [text]
        "Whether external sources need to be retrieved." source_access_needed: boolean
        "Highest-value questions needed to proceed." clarifying_questions: List [text]
    [END_VARIABLES]
    [DEFINE_WORKER: "Create and iteratively refine a draft while enforcing completion and provenance constraints." Worker_draft_communication]
        [INPUTS]
            REQUIRED <REF>user_request</REF>
            OPTIONAL <REF>source_evidence_set</REF>
            OPTIONAL <REF>assumptions_log</REF>
        [END_INPUTS]
        [OUTPUTS]
            REQUIRED <REF>draft_communication_artifact</REF>
            REQUIRED <REF>completion_status</REF>
        [END_OUTPUTS]
        [MAIN_FLOW]
            [SEQUENTIAL_BLOCK]
                COMMAND-1 [COMMAND Produce the draft communication artifact based on <REF>source_evidence_set</REF> and <REF>user_request</REF> RESULT draft_communication_artifact: text, completion_status: text SET]
            [END_SEQUENTIAL_BLOCK]
            DECISION-1 [IF the user asks for revision]
                COMMAND-2 [COMMAND Revise the draft communication artifact while rechecking constraints based on <REF>draft_communication_artifact</REF>, <REF>assumptions_log</REF>, and <REF>missing_required_fields</REF> RESULT <REF>draft_communication_artifact</REF>, <REF>completion_status</REF> SET]
            [END_IF]
        [END_MAIN_FLOW]
    [END_WORKER]
    [DEFINE_WORKER: "Orchestrate the end-to-end process and delegate to sub-tasks." MainWorker]
        [INPUTS]
            OPTIONAL <REF>format_preferences</REF>
            REQUIRED <REF>user_request</REF>
            OPTIONAL <REF>known_topics</REF>
            OPTIONAL <REF>timeframe</REF>
            REQUIRED <REF>available_connectors_or_source_repositories</REF>
        [END_INPUTS]
        [OUTPUTS]
            REQUIRED <REF>draft_communication_artifact</REF>
            REQUIRED <REF>source_evidence_set</REF>
            REQUIRED <REF>assumptions_log</REF>
            REQUIRED <REF>completion_status</REF>
        [END_OUTPUTS]
        [MAIN_FLOW]
            [SEQUENTIAL_BLOCK]
                COMMAND-3 [COMMAND Determine the communication type based on <REF>user_request</REF> RESULT communication_type: text SET]
                COMMAND-4 [COMMAND Identify missing required fields based on <REF>user_request</REF>, <REF>communication_type</REF>, and <REF>timeframe</REF> RESULT missing_required_fields: List [text] SET]
                COMMAND-5 [INPUT Ask the highest-value clarifying questions based on <REF>missing_required_fields</REF> VALUE clarifying_questions: List [text] SET]
                COMMAND-6 [COMMAND Retrieve sources using approved source recipes based on <REF>available_connectors_or_source_repositories</REF> and <REF>source_access_needed</REF> RESULT source_evidence_set: List [text] SET]
                COMMAND-7 [COMMAND Maintain provenance for externally sourced facts based on <REF>source_evidence_set</REF> RESULT <REF>source_evidence_set</REF> SET]
                COMMAND-8 [INVOKE Worker_draft_communication WITH <REF>user_request</REF>, <REF>source_evidence_set</REF>, <REF>assumptions_log</REF> RESPONSE draft_communication_artifact: text, completion_status: text SET]
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
