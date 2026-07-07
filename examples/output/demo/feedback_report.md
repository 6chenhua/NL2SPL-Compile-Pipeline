# NL2SPL Feedback Report

## 1. Overall Compile State

- Completeness: `partial`
- SPL draft generated: `yes`
- Compile diagnostics: `23`
- Assumptions / suggestions: `16`
- Trace records: `44`
- Adapter warnings: `0`
- Validation errors: `0`
- Validation warnings: `15`

Result is partial because the following requirement gaps remain:
- `missing_handler` on `worker:worker_main.exception_flow:exc_adapter_00`: Exception flow 'exc_adapter_00' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_00, slot=handler_action]
- `missing_handler` on `worker:worker_main.exception_flow:exc_adapter_02`: Exception flow 'exc_adapter_02' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_02, slot=handler_action]
- `missing_handler` on `worker:worker_main.exception_flow:exc_adapter_03`: Exception flow 'exc_adapter_03' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_03, slot=handler_action]
- `missing_handler` on `worker:worker_main.exception_flow:exc_adapter_01`: Exception flow 'exc_adapter_01' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_01, slot=handler_action]
- `missing_handler` on `worker:worker_main.exception_flow:exc_adapter_04`: Exception flow 'exc_adapter_04' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_04, slot=handler_action]
- `missing_handler` on `worker:worker_main.exception_flow:exc_adapter_05`: Exception flow 'exc_adapter_05' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_05, slot=handler_action]
- `required_output_deferred` on `resource_contract_demand:rcd_output_s12`: Resource contract output 'rcd_output_s12' is deferred behind an API response whose return contract is not yet known. [construct=resource_contract_demand:rcd_output_s12, slot=producer]
- `missing_output_producer` on `resource_contract_demand:rcd_output_s14`: Resource contract output 'rcd_output_s14' (requiredness=required) has materialized resource(s) completion_status but no renderable producer. [construct=resource_contract_demand:rcd_output_s14, slot=producer]
- `required_output_deferred` on `worker:worker_main.output:source_evidence_set`: Required output 'source_evidence_set' (Set of sources and evidence supporting the draft.) is deferred behind an API response whose return contract is not yet known. [construct=worker:worker_main.output:source_evidence_set, slot=producer]
- `missing_output_producer` on `resource_contract_demand:rcd_output_s13`: Resource contract output 'rcd_output_s13' (requiredness=required) has materialized resource(s) assumptions_log but no renderable producer. [construct=resource_contract_demand:rcd_output_s13, slot=producer]
- `type_or_contract_ambiguity` on `worker:worker_main.step:st_3`: REQUEST_INPUT step has no value target (outputs). [construct=worker:worker_main.step:st_3, slot=value_target]
- `unmapped_behavior_span` on `worker:worker_main.span:s22`: Worker 'worker_main' behavior span 's22' (Do not finalize if required slots remain missing unless the draft is explicitly ) was not mapped to a step: Non-executable policy/constraint statement; it restricts finalization but does not specify an action to perform.
- `resource_kind_mismatch` on `resource_contract_demand:rcd_output_s14`: Resource contract demand 'rcd_output_s14' has binding(s) whose resource_kind/name do not match the materialized ResourceRegistryIR: variable:completion_status [construct=resource_contract_demand:rcd_output_s14, slot=resource_registry]
- `resource_kind_mismatch` on `resource_contract_demand:rcd_output_s13`: Resource contract demand 'rcd_output_s13' has binding(s) whose resource_kind/name do not match the materialized ResourceRegistryIR: variable:assumptions_log [construct=resource_contract_demand:rcd_output_s13, slot=resource_registry]

## 2. Materialized Source-Backed Structure

### Workers
- `worker:MainWorker` (direct) -- spans=s15, s16, s17, s19, s20, s21, s23, s18, s22; section=sec_reusable_process; packet=p_list_item_first_determine_what_kind_of_communication_is_requested_then_identify_which_required_fields_are_still_missing_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward_if_sources_are_needed_and_available

### Flows
- `flow:alt_1` (direct) -- spans=s21; section=sec_reusable_process; packet=p_list_item_produce_a_draft_if_the_user_asks_for_revision
- `flow:exc_adapter_00` (direct) -- spans=s30; section=sec_failure_handling; packet=p_list_item_conflicting_instructions
- `flow:exc_adapter_01` (direct) -- spans=s32; section=sec_failure_handling; packet=p_list_item_evidence_shortage
- `flow:exc_adapter_02` (direct) -- spans=s31; section=sec_failure_handling; packet=p_list_item_insufficient_source_access
- `flow:exc_adapter_03` (direct) -- spans=s29; section=sec_failure_handling; packet=p_list_item_missing_timeframe
- `flow:exc_adapter_04` (direct) -- spans=s34; section=sec_failure_handling; packet=p_list_item_provenance_failure
- `flow:exc_adapter_05` (direct) -- spans=s33; section=sec_failure_handling; packet=p_list_item_user_refusal_to_answer
- `flow:main` (direct) -- spans=s15, s16, s17, s18, s19, s20, s22, s23; section=sec_reusable_process; packet=p_list_item_first_determine_what_kind_of_communication_is_requested_then_identify_which_required_fields_are_still_missing_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward_if_sources_are_needed_and_available

### Steps
- `step:st_1` (direct) -- spans=s15; section=sec_reusable_process; packet=p_list_item_first_determine_what_kind_of_communication_is_requested_then_identify_which_required_fields_are_still_missing_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward_if_sources_are_needed_and_available
- `step:st_2` (direct) -- spans=s16; section=sec_reusable_process; packet=p_list_item_first_determine_what_kind_of_communication_is_requested_then_identify_which_required_fields_are_still_missing_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward_if_sources_are_needed_and_available
- `step:st_3` (direct) -- spans=s17; section=sec_reusable_process; packet=p_list_item_first_determine_what_kind_of_communication_is_requested_then_identify_which_required_fields_are_still_missing_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward_if_sources_are_needed_and_available
- `step:st_4` (direct) -- spans=s19; section=sec_reusable_process; packet=p_list_item_retrieve_them_using_approved_source_recipes_maintain_provenance_for_externally_sourced_facts_when_enough_required_information_is_available
- `step:st_5` (direct) -- spans=s20; section=sec_reusable_process; packet=p_list_item_retrieve_them_using_approved_source_recipes_maintain_provenance_for_externally_sourced_facts_when_enough_required_information_is_available
- `step:st_6` (direct) -- spans=s21; section=sec_reusable_process; packet=p_list_item_produce_a_draft_if_the_user_asks_for_revision
- `step:st_7` (direct) -- spans=s23; section=sec_reusable_process; packet=p_list_item_revise_while_re_checking_constraints_do_not_finalize_if_required_slots_remain_missing_unless_the_draft_is_explicitly_marked_as_assumption_bearing_and_the_user_confirms_at_the_end
- `step:st_api_8564b1b8dc` (direct) -- spans=s18; section=sec_reusable_process; packet=p_list_item_first_determine_what_kind_of_communication_is_requested_then_identify_which_required_fields_are_still_missing_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward_if_sources_are_needed_and_available

### Variables
- `variable:assumptions_log_completion_status` (direct) -- spans=s23; section=sec_reusable_process; packet=p_list_item_revise_while_re_checking_constraints_do_not_finalize_if_required_slots_remain_missing_unless_the_draft_is_explicitly_marked_as_assumption_bearing_and_the_user_confirms_at_the_end
- `variable:draft_communication_artifact` (direct) -- spans=s20; section=sec_reusable_process; packet=p_list_item_retrieve_them_using_approved_source_recipes_maintain_provenance_for_externally_sourced_facts_when_enough_required_information_is_available

### Constraints
- `constraint:c_1` (direct) -- spans=s22; section=sec_reusable_process; packet=p_list_item_revise_while_re_checking_constraints_do_not_finalize_if_required_slots_remain_missing_unless_the_draft_is_explicitly_marked_as_assumption_bearing_and_the_user_confirms_at_the_end
- `constraint:c_2` (direct) -- spans=s24; section=sec_policies; packet=p_sentence_do_not_invent_links_or_unseen_facts
- `constraint:c_3` (direct) -- spans=s25; section=sec_policies; packet=p_sentence_require_evidence_for_sourced_claims
- `constraint:c_4` (direct) -- spans=s26; section=sec_policies; packet=p_sentence_limit_questions_per_turn
- `constraint:c_5` (direct) -- spans=s27; section=sec_policies; packet=p_sentence_prefer_tool_evidence_over_unnecessary_user_questioning
- `constraint:c_6` (direct) -- spans=s28; section=sec_policies; packet=p_sentence_deny_finalization_if_critical_slots_are_missing_or_provenance_fails
- `constraint:c_7` (direct) -- spans=s35; section=sec_delegation_policy; packet=p_sentence_delegated_subtasks_such_as_source_gathering_or_template_matching_may_be_used_if_bounded_and_the_returned_evidence_is_normalized_into_approved_evidence_carriers

### Other
- `api:api:ApprovedSourceRecipesAPI` (direct) -- spans=s18; section=sec_reusable_process; packet=p_list_item_first_determine_what_kind_of_communication_is_requested_then_identify_which_required_fields_are_still_missing_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward_if_sources_are_needed_and_available
- `profile:concept_0` (normalized)
- `profile:concept_1` (normalized)
- `profile:concept_2` (normalized)
- `profile:concept_3` (normalized)
- `profile:concept_4` (normalized)
- `profile:concept_5` (normalized)
- `profile:concept_6` (normalized)
- `profile:concept_7` (normalized)
- `profile:concept_8` (normalized)
- `profile:concept_9` (normalized)
- `profile:persona` (inferred)

## 3. Not Materialized / Kept Partial

- `worker:worker_main.exception_flow:exc_adapter_00`: `missing_handler` -- Exception flow 'exc_adapter_00' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_00, slot=handler_action]
  - Suggested resolution: Add a handler step for 'conflicting instructions', or mark this exception as acknowledged without handling.
- `worker:worker_main.exception_flow:exc_adapter_02`: `missing_handler` -- Exception flow 'exc_adapter_02' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_02, slot=handler_action]
  - Suggested resolution: Add a handler step for 'insufficient source access', or mark this exception as acknowledged without handling.
- `worker:worker_main.exception_flow:exc_adapter_03`: `missing_handler` -- Exception flow 'exc_adapter_03' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_03, slot=handler_action]
  - Suggested resolution: Add a handler step for 'Missing timeframe', or mark this exception as acknowledged without handling.
- `worker:worker_main.exception_flow:exc_adapter_01`: `missing_handler` -- Exception flow 'exc_adapter_01' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_01, slot=handler_action]
  - Suggested resolution: Add a handler step for 'evidence shortage', or mark this exception as acknowledged without handling.
- `worker:worker_main.exception_flow:exc_adapter_04`: `missing_handler` -- Exception flow 'exc_adapter_04' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_04, slot=handler_action]
  - Suggested resolution: Add a handler step for 'provenance failure', or mark this exception as acknowledged without handling.
- `worker:worker_main.exception_flow:exc_adapter_05`: `missing_handler` -- Exception flow 'exc_adapter_05' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_05, slot=handler_action]
  - Suggested resolution: Add a handler step for 'user refusal to answer', or mark this exception as acknowledged without handling.
- `resource_contract_demand:rcd_output_s14`: `missing_output_producer` -- Resource contract output 'rcd_output_s14' (requiredness=required) has materialized resource(s) completion_status but no renderable producer. [construct=resource_contract_demand:rcd_output_s14, slot=producer]
  - Suggested resolution: Add a source-backed step or handoff that produces the materialized resource name with the same resource kind.
- `resource_contract_demand:rcd_output_s13`: `missing_output_producer` -- Resource contract output 'rcd_output_s13' (requiredness=required) has materialized resource(s) assumptions_log but no renderable producer. [construct=resource_contract_demand:rcd_output_s13, slot=producer]
  - Suggested resolution: Add a source-backed step or handoff that produces the materialized resource name with the same resource kind.
- `worker:worker_main.step:st_3`: `type_or_contract_ambiguity` -- REQUEST_INPUT step has no value target (outputs). [construct=worker:worker_main.step:st_3, slot=value_target]
- `worker:worker_main.span:s22`: `unmapped_behavior_span` -- Worker 'worker_main' behavior span 's22' (Do not finalize if required slots remain missing unless the draft is explicitly ) was not mapped to a step: Non-executable policy/constraint statement; it restricts finalization but does not specify an action to perform.

## 4. Diagnostics

### irs_10f7a121636a: `missing_handler`
- Severity: `warning`
- Target: `worker:worker_main.exception_flow:exc_adapter_00`
- Source spans: `s30`
- Message: Exception flow 'exc_adapter_00' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_00, slot=handler_action]
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Add a handler step for 'conflicting instructions', or mark this exception as acknowledged without handling.
- Missing slot: `handler_action`
- Missing reason: Exception flow 'exc_adapter_00' has condition but no handler step.

### irs_1b3f3d9cba5a: `missing_handler`
- Severity: `warning`
- Target: `worker:worker_main.exception_flow:exc_adapter_02`
- Source spans: `s31`
- Message: Exception flow 'exc_adapter_02' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_02, slot=handler_action]
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Add a handler step for 'insufficient source access', or mark this exception as acknowledged without handling.
- Missing slot: `handler_action`
- Missing reason: Exception flow 'exc_adapter_02' has condition but no handler step.

### irs_3adc6ceae481: `missing_handler`
- Severity: `warning`
- Target: `worker:worker_main.exception_flow:exc_adapter_03`
- Source spans: `s29`
- Message: Exception flow 'exc_adapter_03' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_03, slot=handler_action]
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Add a handler step for 'Missing timeframe', or mark this exception as acknowledged without handling.
- Missing slot: `handler_action`
- Missing reason: Exception flow 'exc_adapter_03' has condition but no handler step.

### irs_7a31fdca542e: `missing_handler`
- Severity: `warning`
- Target: `worker:worker_main.exception_flow:exc_adapter_01`
- Source spans: `s32`
- Message: Exception flow 'exc_adapter_01' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_01, slot=handler_action]
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Add a handler step for 'evidence shortage', or mark this exception as acknowledged without handling.
- Missing slot: `handler_action`
- Missing reason: Exception flow 'exc_adapter_01' has condition but no handler step.

### irs_e04bc1cd67b3: `missing_handler`
- Severity: `warning`
- Target: `worker:worker_main.exception_flow:exc_adapter_04`
- Source spans: `s34`
- Message: Exception flow 'exc_adapter_04' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_04, slot=handler_action]
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Add a handler step for 'provenance failure', or mark this exception as acknowledged without handling.
- Missing slot: `handler_action`
- Missing reason: Exception flow 'exc_adapter_04' has condition but no handler step.

### irs_eadd3506d14d: `missing_handler`
- Severity: `warning`
- Target: `worker:worker_main.exception_flow:exc_adapter_05`
- Source spans: `s33`
- Message: Exception flow 'exc_adapter_05' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_05, slot=handler_action]
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Add a handler step for 'user refusal to answer', or mark this exception as acknowledged without handling.
- Missing slot: `handler_action`
- Missing reason: Exception flow 'exc_adapter_05' has condition but no handler step.

### irs_39b7f5d959d3: `required_output_deferred`
- Severity: `warning`
- Target: `resource_contract_demand:rcd_output_s12`
- Source spans: `s12`
- Message: Resource contract output 'rcd_output_s12' is deferred behind an API response whose return contract is not yet known. [construct=resource_contract_demand:rcd_output_s12, slot=producer]
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Declare the API return contract or add a source-backed producer for the deferred resource.
- Missing slot: `producer`
- Missing reason: Resource contract output 'rcd_output_s12' is deferred behind an API response whose return contract is not yet known.

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

### irs_76ff1b8cd4f1: `required_output_deferred`
- Severity: `warning`
- Target: `worker:worker_main.output:source_evidence_set`
- Message: Required output 'source_evidence_set' (Set of sources and evidence supporting the draft.) is deferred behind an API response whose return contract is not yet known. [construct=worker:worker_main.output:source_evidence_set, slot=producer]
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Declare the API return contract or add a source-backed producer step for 'source_evidence_set'.
- Missing slot: `producer`
- Missing reason: Required output 'source_evidence_set' (Set of sources and evidence supporting the draft.) is deferred behind an API response whose return contract is not yet known.

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

### irs_43bfae5d542e: `type_or_contract_ambiguity`
- Severity: `warning`
- Target: `worker:worker_main.step:st_3`
- Source spans: `s17`
- Message: REQUEST_INPUT step has no value target (outputs). [construct=worker:worker_main.step:st_3, slot=value_target]
- Blocks rendering: `false`
- Blocks completion: `true`
- Missing slot: `value_target`
- Missing reason: REQUEST_INPUT step has no value target (outputs).

### grouped:api_declaration:api:ApprovedSourceRecipesAPI: `deferred_api_contract_validation`
- Severity: `info`
- Target: `api_declaration:api:ApprovedSourceRecipesAPI`
- Message: API declaration is renderable with grammar-safe placeholders; semantic contract validation is deferred downstream.
- Blocks rendering: `false`
- Blocks completion: `false`
- Placeholder slots:
  - `functions`: Functions placeholder is valid; downstream API validation is pending.
    - Diagnostic: `irs_70bf830821c3`
  - `openapi_schema`: Schema placeholder is valid; downstream API validation is pending.
    - Diagnostic: `irs_4922b19aef41`

### diag_s7_0000: `unmapped_behavior_span`
- Severity: `warning`
- Target: `worker:worker_main.span:s22`
- Source spans: `s22`
- Message: Worker 'worker_main' behavior span 's22' (Do not finalize if required slots remain missing unless the draft is explicitly ) was not mapped to a step: Non-executable policy/constraint statement; it restricts finalization but does not specify an action to perform.
- Blocks rendering: `false`
- Blocks completion: `true`

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
- Target: `variable:source_evidence_set`
- Message: Variable 'source_evidence_set' (List[text]) is a contract output with no source-backed producer or adapter evidence.
- Blocks rendering: `false`
- Blocks completion: `false`

### stage2_route_refinement_diagnostic_: `route_refinement_diagnostic`
- Severity: `info`
- Message: LLM route diagnostic [override_prior] span='s1': Structural prior suggested domain, but the span is a task-family label and is better classified as profile_domain.
- Blocks rendering: `false`
- Blocks completion: `false`

### irs_33ac12d54292: `resource_kind_mismatch`
- Severity: `warning`
- Target: `resource_contract_demand:rcd_output_s14`
- Source spans: `s14`
- Message: Resource contract demand 'rcd_output_s14' has binding(s) whose resource_kind/name do not match the materialized ResourceRegistryIR: variable:completion_status [construct=resource_contract_demand:rcd_output_s14, slot=resource_registry]
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Ensure Stage 6 materializes every resource_contracts binding into the matching registry collection (variables/files/apis/types).
- Missing slot: `resource_registry`
- Missing reason: Resource contract demand 'rcd_output_s14' has binding(s) whose resource_kind/name do not match the materialized ResourceRegistryIR: variable:completion_status

### irs_a859fb4e95e1: `resource_kind_mismatch`
- Severity: `warning`
- Target: `resource_contract_demand:rcd_output_s13`
- Source spans: `s13`
- Message: Resource contract demand 'rcd_output_s13' has binding(s) whose resource_kind/name do not match the materialized ResourceRegistryIR: variable:assumptions_log [construct=resource_contract_demand:rcd_output_s13, slot=resource_registry]
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Ensure Stage 6 materializes every resource_contracts binding into the matching registry collection (variables/files/apis/types).
- Missing slot: `resource_registry`
- Missing reason: Resource contract demand 'rcd_output_s13' has binding(s) whose resource_kind/name do not match the materialized ResourceRegistryIR: variable:assumptions_log

## 5. Deferred Validation

- `api_declaration:api:ApprovedSourceRecipesAPI`: API contract validation deferred downstream.
  - Placeholder fields: `functions`, `openapi_schema`
  - Validation authority: `downstream_spl_compiler`

## 6. Assumptions / Suggestions

- `ASM_0000` for `worker:worker_main.exception_flow:exc_adapter_00`: Exception flow has no handler action. The compiler suggests specifying what should happen when this failure occurs.
  - Reason: Source describes a failure condition but does not specify how to handle it.  The exception flow is preserved in SPL, but no handler command was rendered. (Exception flow 'exc_adapter_00' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adap)
  - Suggested resolution: Specify the handler action for worker:worker_main.exception_flow:exc_adapter_00: e.g. ask the user for missing information, block finalization, or continue with an explicit assumption.
  - Related diagnostic: `irs_10f7a121636a`
- `ASM_0001` for `worker:worker_main.exception_flow:exc_adapter_01`: Exception flow has no handler action. The compiler suggests specifying what should happen when this failure occurs.
  - Reason: Source describes a failure condition but does not specify how to handle it.  The exception flow is preserved in SPL, but no handler command was rendered. (Exception flow 'exc_adapter_01' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adap)
  - Suggested resolution: Specify the handler action for worker:worker_main.exception_flow:exc_adapter_01: e.g. ask the user for missing information, block finalization, or continue with an explicit assumption.
  - Related diagnostic: `irs_7a31fdca542e`
- `ASM_0002` for `worker:worker_main.exception_flow:exc_adapter_02`: Exception flow has no handler action. The compiler suggests specifying what should happen when this failure occurs.
  - Reason: Source describes a failure condition but does not specify how to handle it.  The exception flow is preserved in SPL, but no handler command was rendered. (Exception flow 'exc_adapter_02' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adap)
  - Suggested resolution: Specify the handler action for worker:worker_main.exception_flow:exc_adapter_02: e.g. ask the user for missing information, block finalization, or continue with an explicit assumption.
  - Related diagnostic: `irs_1b3f3d9cba5a`
- `ASM_0003` for `worker:worker_main.exception_flow:exc_adapter_03`: Exception flow has no handler action. The compiler suggests specifying what should happen when this failure occurs.
  - Reason: Source describes a failure condition but does not specify how to handle it.  The exception flow is preserved in SPL, but no handler command was rendered. (Exception flow 'exc_adapter_03' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adap)
  - Suggested resolution: Specify the handler action for worker:worker_main.exception_flow:exc_adapter_03: e.g. ask the user for missing information, block finalization, or continue with an explicit assumption.
  - Related diagnostic: `irs_3adc6ceae481`
- `ASM_0004` for `worker:worker_main.exception_flow:exc_adapter_04`: Exception flow has no handler action. The compiler suggests specifying what should happen when this failure occurs.
  - Reason: Source describes a failure condition but does not specify how to handle it.  The exception flow is preserved in SPL, but no handler command was rendered. (Exception flow 'exc_adapter_04' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adap)
  - Suggested resolution: Specify the handler action for worker:worker_main.exception_flow:exc_adapter_04: e.g. ask the user for missing information, block finalization, or continue with an explicit assumption.
  - Related diagnostic: `irs_e04bc1cd67b3`
- `ASM_0005` for `worker:worker_main.exception_flow:exc_adapter_05`: Exception flow has no handler action. The compiler suggests specifying what should happen when this failure occurs.
  - Reason: Source describes a failure condition but does not specify how to handle it.  The exception flow is preserved in SPL, but no handler command was rendered. (Exception flow 'exc_adapter_05' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adap)
  - Suggested resolution: Specify the handler action for worker:worker_main.exception_flow:exc_adapter_05: e.g. ask the user for missing information, block finalization, or continue with an explicit assumption.
  - Related diagnostic: `irs_eadd3506d14d`
- `ASM_0006` for `resource_contract_demand:rcd_output_s13`: Required output has no source-backed producer. The compiler suggests adding a step that explicitly produces this output.
  - Reason: The source requires this output but does not describe how it should be produced.  The output is kept in the OUTPUTS contract, but no producer step was rendered.
  - Suggested resolution: Add a source-backed step that produces resource_contract_demand:rcd_output_s13. If the source does not specify how to produce it, mark it as optional or remove it from the required output contract.
  - Related diagnostic: `irs_b0d25f2c1af8`
- `ASM_0007` for `resource_contract_demand:rcd_output_s14`: Required output has no source-backed producer. The compiler suggests adding a step that explicitly produces this output.
  - Reason: The source requires this output but does not describe how it should be produced.  The output is kept in the OUTPUTS contract, but no producer step was rendered.
  - Suggested resolution: Add a source-backed step that produces resource_contract_demand:rcd_output_s14. If the source does not specify how to produce it, mark it as optional or remove it from the required output contract.
  - Related diagnostic: `irs_59fb5ecfa9e9`
- `ASM_0008` for `worker:worker_main.step:st_3`: Command has an ambiguous or incomplete contract. The compiler suggests providing the missing contract detail.
  - Reason: A command references an API, worker, or input source that is not fully specified.  The compiler cannot materialize the command without this information.
  - Suggested resolution: For worker:worker_main.step:st_3: provide the missing contract detail (API name, worker target, IO bindings, or source evidence).  See the related diagnostic for specifics.
  - Related diagnostic: `irs_43bfae5d542e`
- `ASM_0009` for `variable:format_preferences`: Variable has no discoverable source provenance.
  - Reason: The compiler could not trace this variable back to a source span, adapter hard fact, or producer step.  Its origin is assumed.
  - Suggested resolution: For variable:format_preferences: add source evidence (a span, adapter hint, or producer step) that justifies this variable's existence.
  - Related diagnostic: `diag_prov_0000`
- `ASM_0010` for `variable:user_request`: Variable has no discoverable source provenance.
  - Reason: The compiler could not trace this variable back to a source span, adapter hard fact, or producer step.  Its origin is assumed.
  - Suggested resolution: For variable:user_request: add source evidence (a span, adapter hint, or producer step) that justifies this variable's existence.
  - Related diagnostic: `diag_prov_0001`
- `ASM_0011` for `variable:known_topics`: Variable has no discoverable source provenance.
  - Reason: The compiler could not trace this variable back to a source span, adapter hard fact, or producer step.  Its origin is assumed.
  - Suggested resolution: For variable:known_topics: add source evidence (a span, adapter hint, or producer step) that justifies this variable's existence.
  - Related diagnostic: `diag_prov_0002`
- `ASM_0012` for `variable:timeframe`: Variable has no discoverable source provenance.
  - Reason: The compiler could not trace this variable back to a source span, adapter hard fact, or producer step.  Its origin is assumed.
  - Suggested resolution: For variable:timeframe: add source evidence (a span, adapter hint, or producer step) that justifies this variable's existence.
  - Related diagnostic: `diag_prov_0003`
- `ASM_0013` for `variable:connectors_or_source_repositories`: Variable has no discoverable source provenance.
  - Reason: The compiler could not trace this variable back to a source span, adapter hard fact, or producer step.  Its origin is assumed.
  - Suggested resolution: For variable:connectors_or_source_repositories: add source evidence (a span, adapter hint, or producer step) that justifies this variable's existence.
  - Related diagnostic: `diag_prov_0004`
- `ASM_0014` for `variable:source_evidence_set`: Variable has no discoverable source provenance.
  - Reason: The compiler could not trace this variable back to a source span, adapter hard fact, or producer step.  Its origin is assumed.
  - Suggested resolution: For variable:source_evidence_set: add source evidence (a span, adapter hint, or producer step) that justifies this variable's existence.
  - Related diagnostic: `diag_prov_0005`
- `ASM_0015` for `worker:worker_main.span:s22`: A behavior span from the source was not mapped to any executable step.
  - Reason: The source describes behavior that could not be translated into a concrete command.  This may be intentional (policy, non-executable description) or may indicate missing detail.
  - Suggested resolution: For worker:worker_main.span:s22: either add a step implementing this behavior, or acknowledge it as non-executable context.
  - Related diagnostic: `diag_s7_0000`

## 7. Provenance / TraceRecords

- `api:api:ApprovedSourceRecipesAPI` -> `direct`
  - Source: spans=`s18`, section=`sec_reusable_process`, packet=`p_list_item_first_determine_what_kind_of_communication_is_requested_then_identify_which_required_fields_are_still_missing_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward_if_sources_are_needed_and_available`
  - Explanation: API declaration 'ApprovedSourceRecipesAPI' materialized as grammar_minimal_partial.
- `constraint:c_1` -> `direct`
  - Source: spans=`s22`, section=`sec_reusable_process`, packet=`p_list_item_revise_while_re_checking_constraints_do_not_finalize_if_required_slots_remain_missing_unless_the_draft_is_explicitly_marked_as_assumption_bearing_and_the_user_confirms_at_the_end`
  - Explanation: Constraint 'c_1' (gate): Do not finalize if <REF>draft_communication_artifact</REF> still has required sl
- `constraint:c_2` -> `direct`
  - Source: spans=`s24`, section=`sec_policies`, packet=`p_sentence_do_not_invent_links_or_unseen_facts`
  - Explanation: Constraint 'c_2' (prohibition): Do not invent links or unseen facts.
- `constraint:c_3` -> `direct`
  - Source: spans=`s25`, section=`sec_policies`, packet=`p_sentence_require_evidence_for_sourced_claims`
  - Explanation: Constraint 'c_3' (evidence): Require evidence for sourced claims.
- `constraint:c_4` -> `direct`
  - Source: spans=`s26`, section=`sec_policies`, packet=`p_sentence_limit_questions_per_turn`
  - Explanation: Constraint 'c_4' (requirement): Limit questions per turn.
- `constraint:c_5` -> `direct`
  - Source: spans=`s27`, section=`sec_policies`, packet=`p_sentence_prefer_tool_evidence_over_unnecessary_user_questioning`
  - Explanation: Constraint 'c_5' (requirement): Prefer tool evidence over unnecessary user questioning.
- `constraint:c_6` -> `direct`
  - Source: spans=`s28`, section=`sec_policies`, packet=`p_sentence_deny_finalization_if_critical_slots_are_missing_or_provenance_fails`
  - Explanation: Constraint 'c_6' (gate): Deny finalization if critical slots are missing or provenance fails.
- `constraint:c_7` -> `direct`
  - Source: spans=`s35`, section=`sec_delegation_policy`, packet=`p_sentence_delegated_subtasks_such_as_source_gathering_or_template_matching_may_be_used_if_bounded_and_the_returned_evidence_is_normalized_into_approved_evidence_carriers`
  - Explanation: Constraint 'c_7' (delegation_boundary): Optional delegated subtasks such as source gathering or template matching may be
- `flow:alt_1` -> `direct`
  - Source: spans=`s21`, section=`sec_reusable_process`, packet=`p_list_item_produce_a_draft_if_the_user_asks_for_revision`
  - Explanation: Alternative flow 'alt_1': the user asks for revision
- `flow:exc_adapter_00` -> `direct`
  - Source: spans=`s30`, section=`sec_failure_handling`, packet=`p_list_item_conflicting_instructions`
  - Explanation: Exception flow 'exc_adapter_00': conflicting instructions
- `flow:exc_adapter_01` -> `direct`
  - Source: spans=`s32`, section=`sec_failure_handling`, packet=`p_list_item_evidence_shortage`
  - Explanation: Exception flow 'exc_adapter_01': evidence shortage
- `flow:exc_adapter_02` -> `direct`
  - Source: spans=`s31`, section=`sec_failure_handling`, packet=`p_list_item_insufficient_source_access`
  - Explanation: Exception flow 'exc_adapter_02': insufficient source access
- `flow:exc_adapter_03` -> `direct`
  - Source: spans=`s29`, section=`sec_failure_handling`, packet=`p_list_item_missing_timeframe`
  - Explanation: Exception flow 'exc_adapter_03': Missing timeframe
- `flow:exc_adapter_04` -> `direct`
  - Source: spans=`s34`, section=`sec_failure_handling`, packet=`p_list_item_provenance_failure`
  - Explanation: Exception flow 'exc_adapter_04': provenance failure
- `flow:exc_adapter_05` -> `direct`
  - Source: spans=`s33`, section=`sec_failure_handling`, packet=`p_list_item_user_refusal_to_answer`
  - Explanation: Exception flow 'exc_adapter_05': user refusal to answer
- `flow:main` -> `direct`
  - Source: spans=`s15, s16, s17, s18, s19, s20, s22, s23`, section=`sec_reusable_process`, packet=`p_list_item_first_determine_what_kind_of_communication_is_requested_then_identify_which_required_fields_are_still_missing_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward_if_sources_are_needed_and_available`
  - Explanation: Main flow with 7 block(s).
- `profile:concept_0` -> `normalized`
  - Explanation: Concept: Internal newsletters -- Newsletter-style communications intended for internal organizational audiences.
- `profile:concept_1` -> `normalized`
  - Explanation: Concept: Announcements -- Short internal communications that notify people about updates, events, or decisions.
- `profile:concept_2` -> `normalized`
  - Explanation: Concept: Update digests -- Condensed summaries of recent updates collected into a brief format.
- `profile:concept_3` -> `normalized`
  - Explanation: Concept: Executive briefs -- Concise summaries prepared for executives, emphasizing key points and status.
- `profile:concept_4` -> `normalized`
  - Explanation: Concept: Internal-comms artifacts -- Communication materials used in internal communications, such as newsletters, briefs, or announcements.
- `profile:concept_5` -> `normalized`
  - Explanation: Concept: Provenance -- The traceable origin of facts or claims, used to verify where sourced information came from.
- `profile:concept_6` -> `normalized`
  - Explanation: Concept: Assumptions log -- A short record of unresolved items that required assumptions in the draft.
- `profile:concept_7` -> `normalized`
  - Explanation: Concept: Completion status -- A status indicator showing whether the run or task is complete.
- `profile:concept_8` -> `normalized`
  - Explanation: Concept: Approved source recipes -- Authorized procedures or methods for retrieving information from sources.
- `profile:concept_9` -> `normalized`
  - Explanation: Concept: Approved evidence carriers -- Accepted formats or containers for normalized evidence returned from delegated subtasks.
- `profile:persona` -> `inferred`
  - Explanation: Persona: Internal communications specialist
- `step:st_1` -> `direct`
  - Source: spans=`s15`, section=`sec_reusable_process`, packet=`p_list_item_first_determine_what_kind_of_communication_is_requested_then_identify_which_required_fields_are_still_missing_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward_if_sources_are_needed_and_available`
  - Explanation: Step 'st_1' maps to source span(s).
- `step:st_2` -> `direct`
  - Source: spans=`s16`, section=`sec_reusable_process`, packet=`p_list_item_first_determine_what_kind_of_communication_is_requested_then_identify_which_required_fields_are_still_missing_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward_if_sources_are_needed_and_available`
  - Explanation: Step 'st_2' maps to source span(s).
- `step:st_3` -> `direct`
  - Source: spans=`s17`, section=`sec_reusable_process`, packet=`p_list_item_first_determine_what_kind_of_communication_is_requested_then_identify_which_required_fields_are_still_missing_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward_if_sources_are_needed_and_available`
  - Explanation: Step 'st_3' maps to source span(s).
- `step:st_4` -> `direct`
  - Source: spans=`s19`, section=`sec_reusable_process`, packet=`p_list_item_retrieve_them_using_approved_source_recipes_maintain_provenance_for_externally_sourced_facts_when_enough_required_information_is_available`
  - Explanation: Step 'st_4' maps to source span(s).
- `step:st_5` -> `direct`
  - Source: spans=`s20`, section=`sec_reusable_process`, packet=`p_list_item_retrieve_them_using_approved_source_recipes_maintain_provenance_for_externally_sourced_facts_when_enough_required_information_is_available`
  - Explanation: Step 'st_5' maps to source span(s).
- `step:st_6` -> `direct`
  - Source: spans=`s21`, section=`sec_reusable_process`, packet=`p_list_item_produce_a_draft_if_the_user_asks_for_revision`
  - Explanation: Step 'st_6' maps to source span(s).
- `step:st_7` -> `direct`
  - Source: spans=`s23`, section=`sec_reusable_process`, packet=`p_list_item_revise_while_re_checking_constraints_do_not_finalize_if_required_slots_remain_missing_unless_the_draft_is_explicitly_marked_as_assumption_bearing_and_the_user_confirms_at_the_end`
  - Explanation: Step 'st_7' maps to source span(s).
- `step:st_api_8564b1b8dc` -> `direct`
  - Source: spans=`s18`, section=`sec_reusable_process`, packet=`p_list_item_first_determine_what_kind_of_communication_is_requested_then_identify_which_required_fields_are_still_missing_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward_if_sources_are_needed_and_available`
  - Explanation: Step 'st_api_8564b1b8dc' maps to source span(s).
- `variable:assumptions_log_completion_status` -> `direct`
  - Source: spans=`s23`, section=`sec_reusable_process`, packet=`p_list_item_revise_while_re_checking_constraints_do_not_finalize_if_required_slots_remain_missing_unless_the_draft_is_explicitly_marked_as_assumption_bearing_and_the_user_confirms_at_the_end`
  - Explanation: Variable 'assumptions_log_completion_status' is produced by source-backed step 'st_7'.
- `variable:connectors_or_source_repositories` -> `assumed` [needs confirmation]
  - Explanation: Variable 'connectors_or_source_repositories' is declared as worker input contract with no source evidence.
- `variable:draft_communication_artifact` -> `direct`
  - Source: spans=`s20`, section=`sec_reusable_process`, packet=`p_list_item_retrieve_them_using_approved_source_recipes_maintain_provenance_for_externally_sourced_facts_when_enough_required_information_is_available`
  - Explanation: Variable 'draft_communication_artifact' is produced by source-backed step 'st_5'.
- `variable:format_preferences` -> `assumed` [needs confirmation]
  - Explanation: Variable 'format_preferences' is declared as worker input contract with no source evidence.
- `variable:known_topics` -> `assumed` [needs confirmation]
  - Explanation: Variable 'known_topics' is declared as worker input contract with no source evidence.
- `variable:source_evidence_set` -> `assumed` [needs confirmation]
  - Explanation: Variable 'source_evidence_set' is declared as worker output contract with no source evidence.
- `variable:timeframe` -> `assumed` [needs confirmation]
  - Explanation: Variable 'timeframe' is declared as worker input contract with no source evidence.
- `variable:user_request` -> `assumed` [needs confirmation]
  - Explanation: Variable 'user_request' is declared as worker input contract with no source evidence.
- `worker:MainWorker` -> `direct`
  - Source: spans=`s15, s16, s17, s19, s20, s21, s23, s18, s22`, section=`sec_reusable_process`, packet=`p_list_item_first_determine_what_kind_of_communication_is_requested_then_identify_which_required_fields_are_still_missing_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward_if_sources_are_needed_and_available`
  - Explanation: Main worker 'MainWorker' assembled from flow and step IRs.

## 8. Anti-Fabrication Checks

- `missing_handler`: Exception conditions without handler action stay as partial exception flows; no handler command is invented.
- `missing_output_producer`: Required outputs without a source-backed producer stay in the contract; no synthetic producer command is invented.
- `type_or_contract_ambiguity`: Unresolved worker/API contracts are reported as ambiguity; they are not downgraded to generic commands.
- Rendered SPL contains no executable `[INVOKE ...]` command.

## 9. Adapter / Validation Notes

Validation warnings:
- ConstructPlan: condition span s30 for exc_demand_00 has unowned; attached to main worker worker_main.
- ConstructPlan: condition span s32 for exc_demand_01 has unowned; attached to main worker worker_main.
- ConstructPlan: condition span s31 for exc_demand_02 has unowned; attached to main worker worker_main.
- ConstructPlan: condition span s29 for exc_demand_03 has unowned; attached to main worker worker_main.
- ConstructPlan: condition span s34 for exc_demand_04 has unowned; attached to main worker worker_main.
- ConstructPlan: condition span s33 for exc_demand_05 has unowned; attached to main worker worker_main.
- ConstructPlan: condition span s30 for exc_demand_00 has unowned; attached to main worker worker_main.
- ConstructPlan: condition span s32 for exc_demand_01 has unowned; attached to main worker worker_main.
- ConstructPlan: condition span s31 for exc_demand_02 has unowned; attached to main worker worker_main.
- ConstructPlan: condition span s29 for exc_demand_03 has unowned; attached to main worker worker_main.
- ConstructPlan: condition span s34 for exc_demand_04 has unowned; attached to main worker worker_main.
- ConstructPlan: condition span s33 for exc_demand_05 has unowned; attached to main worker worker_main.
- Aggregated multi-output step st_7 into assumptions_log_completion_status without unpack steps.
- Unused variable declared: assumptions_log
- Unused variable declared: completion_status

## 10. SPL Draft

```spl
[DEFINE_AGENT: MainWorker "Orchestrate the end-to-end process and delegate to sub-tasks."]
    [DEFINE_PERSONA:]
        ROLE: Internal communications specialist
        EvidenceDriven: Produces communication drafts using source evidence and maintains provenance for externally sourced facts.
        ConservativeFinalization: Avoids finalizing when critical information is missing or provenance is not established.
        ClarificationFocused: Asks only the highest-value clarifying questions needed to move forward and limits questions per turn.
        ConstraintAware: Rechecks constraints during revision and does not invent links or unseen facts.
    [END_PERSONA]
    [DEFINE_CONCEPTS:]
        Internalnewsletters: Newsletter-style communications intended for internal organizational audiences.
        Announcements: Short internal communications that notify people about updates, events, or decisions.
        Updatedigests: Condensed summaries of recent updates collected into a brief format.
        Executivebriefs: Concise summaries prepared for executives, emphasizing key points and status.
        Internalcommsartifacts: Communication materials used in internal communications, such as newsletters, briefs, or announcements.
        Provenance: The traceable origin of facts or claims, used to verify where sourced information came from.
        Assumptionslog: A short record of unresolved items that required assumptions in the draft.
        Completionstatus: A status indicator showing whether the run or task is complete.
        Approvedsourcerecipes: Authorized procedures or methods for retrieving information from sources.
        Approvedevidencecarriers: Accepted formats or containers for normalized evidence returned from delegated subtasks.
    [END_CONCEPTS]
    [DEFINE_CONSTRAINTS:]
        Gate: Do not finalize if <REF>draft_communication_artifact</REF> still has required slots missing, unless the draft is explicitly marked as assumption-bearing and the user confirms.
        Prohibition: Do not invent links or unseen facts.
        Evidence: Require evidence for sourced claims.
        Requirement: Limit questions per turn.
        Requirement: Prefer tool evidence over unnecessary user questioning.
        Gate: Deny finalization if critical slots are missing or provenance fails.
        DelegationBoundary: Optional delegated subtasks such as source gathering or template matching may be used only if bounded and the returned evidence is normalized into approved evidence carriers.
    [END_CONSTRAINTS]
    [DEFINE_TYPES:]
        AssumptionsLogCompletionStatus = { assumptions_log: text, completion_status: text }
    [END_TYPES]
    [DEFINE_VARIABLES:]
        "Optional user preferences for output format." format_preferences: text
        "The user's request or prompt." user_request: text
        "Optional topics already known to be relevant." known_topics: List [text]
        "Optional time range or deadline context." timeframe: text
        "Available connectors or source repositories." connectors_or_source_repositories: List [text]
        "Draft communication artifact to be produced." draft_communication_artifact: text
        "Set of sources and evidence supporting the draft." source_evidence_set: List [text]
        "Structured result for step st_7." assumptions_log_completion_status: AssumptionsLogCompletionStatus
        "Short log of assumptions for unresolved items." assumptions_log: text
        "Run completion status." completion_status: text
    [END_VARIABLES]
    [DEFINE_APIS:]
        "Partial API declaration skeleton for ApprovedSourceRecipesAPI." ApprovedSourceRecipesAPI <none>
        {}
        {"functions":[]}
    [END_APIS]
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
            REQUIRED <REF>assumptions_log_completion_status</REF>
        [END_OUTPUTS]
        [MAIN_FLOW]
            [SEQUENTIAL_BLOCK]
                COMMAND-1 [COMMAND Determine the requested communication type based on <REF>user_request</REF>]
                COMMAND-2 [COMMAND Identify missing required fields based on <REF>user_request</REF>, <REF>known_topics</REF>, and <REF>timeframe</REF>]
            [END_SEQUENTIAL_BLOCK]
            DECISION-1 [IF required fields are still missing]
                COMMAND-3 [INPUT Ask the highest-value clarifying questions based on <REF>user_request</REF> VALUE user_input:text SET]
            [END_IF]
            DECISION-2 [IF sources are needed and available]
                COMMAND-4 [CALL ApprovedSourceRecipesAPI]
            [END_IF]
            [SEQUENTIAL_BLOCK]
                COMMAND-5 [COMMAND Maintain provenance for externally sourced facts]
            [END_SEQUENTIAL_BLOCK]
            DECISION-3 [IF enough required information is available]
                COMMAND-6 [COMMAND Produce the draft communication artifact based on <REF>user_request</REF>, <REF>format_preferences</REF>, <REF>known_topics</REF>, and <REF>timeframe</REF> RESULT draft_communication_artifact: text SET]
            [END_IF]
            [SEQUENTIAL_BLOCK]
                COMMAND-7 [COMMAND Record an assumptions log and set completion status RESULT assumptions_log_completion_status: AssumptionsLogCompletionStatus SET]
            [END_SEQUENTIAL_BLOCK]
        [END_MAIN_FLOW]
        [ALTERNATIVE_FLOW: the user asks for revision]
            [SEQUENTIAL_BLOCK]
                COMMAND-8 [COMMAND Revise the draft while rechecking constraints based on <REF>user_request</REF>, <REF>format_preferences</REF>, <REF>known_topics</REF>, and <REF>timeframe</REF>]
            [END_SEQUENTIAL_BLOCK]
        [END_ALTERNATIVE_FLOW]
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
