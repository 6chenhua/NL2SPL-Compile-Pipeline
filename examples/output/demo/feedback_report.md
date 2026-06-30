# NL2SPL Feedback Report

## 1. Overall Compile State

- Completeness: `partial`
- SPL draft generated: `yes`
- Compile diagnostics: `19`
- Assumptions / suggestions: `16`
- Trace records: `43`
- Adapter warnings: `0`
- Validation errors: `0`
- Validation warnings: `12`

Result is partial because the following requirement gaps remain:
- `missing_handler` on `worker:worker_main.exception_flow:exc_adapter_03`: Exception flow 'exc_adapter_03' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_03, slot=handler_action]
- `missing_handler` on `worker:worker_main.exception_flow:exc_adapter_05`: Exception flow 'exc_adapter_05' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_05, slot=handler_action]
- `missing_handler` on `worker:worker_main.exception_flow:exc_adapter_04`: Exception flow 'exc_adapter_04' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_04, slot=handler_action]
- `missing_handler` on `worker:worker_main.exception_flow:exc_adapter_01`: Exception flow 'exc_adapter_01' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_01, slot=handler_action]
- `missing_handler` on `worker:worker_main.exception_flow:exc_adapter_00`: Exception flow 'exc_adapter_00' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_00, slot=handler_action]
- `missing_handler` on `worker:worker_main.exception_flow:exc_adapter_02`: Exception flow 'exc_adapter_02' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_02, slot=handler_action]
- `type_or_contract_ambiguity` on `worker_promotion:del_s31`: WORKER_PROMOTION blocked by missing promotion slots.
  - `promotion_input_contract`: Missing clear input contract
  - `promotion_output_contract`: Missing clear output contract
  - `promotion_invocation_point`: Missing accepted decision or matching handoff with invocation hint
  - `promotion_result_handoff`: Missing matching handoff with output bindings
- `type_or_contract_ambiguity` on `worker:worker_main.step:st_2`: REQUEST_INPUT step has no value target (outputs). [construct=worker:worker_main.step:st_2, slot=value_target]

## 2. Materialized Source-Backed Structure

### Workers
- `worker:MainWorker` (direct) -- spans=s15, s16, s17, s18, s19; section=sec_reusable_process; packet=p_list_item_first_determine_what_kind_of_communication_is_requested_then_identify_which_required_fields_are_still_missing_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward_if_sources_are_needed_and_available

### Flows
- `flow:alt_1` (direct) -- spans=s18; section=sec_reusable_process; packet=p_list_item_revise_while_re_checking_constraints_do_not_finalize_if_required_slots_remain_missing_unless_the_draft_is_explicitly_marked_as_assumption_bearing_and_the_user_confirms_at_the_end
- `flow:exc_adapter_00` (direct) -- spans=s26; section=sec_failure_handling; packet=p_list_item_conflicting_instructions
- `flow:exc_adapter_01` (direct) -- spans=s28; section=sec_failure_handling; packet=p_list_item_evidence_shortage
- `flow:exc_adapter_02` (direct) -- spans=s27; section=sec_failure_handling; packet=p_list_item_insufficient_source_access
- `flow:exc_adapter_03` (direct) -- spans=s25; section=sec_failure_handling; packet=p_list_item_missing_timeframe
- `flow:exc_adapter_04` (direct) -- spans=s30; section=sec_failure_handling; packet=p_list_item_provenance_failure
- `flow:exc_adapter_05` (direct) -- spans=s29; section=sec_failure_handling; packet=p_list_item_user_refusal_to_answer
- `flow:main` (direct) -- spans=s15, s16, s17, s19; section=sec_reusable_process; packet=p_list_item_first_determine_what_kind_of_communication_is_requested_then_identify_which_required_fields_are_still_missing_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward_if_sources_are_needed_and_available

### Steps
- `step:st_1` (direct) -- spans=s15; section=sec_reusable_process; packet=p_list_item_first_determine_what_kind_of_communication_is_requested_then_identify_which_required_fields_are_still_missing_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward_if_sources_are_needed_and_available
- `step:st_2` (direct) -- spans=s15; section=sec_reusable_process; packet=p_list_item_first_determine_what_kind_of_communication_is_requested_then_identify_which_required_fields_are_still_missing_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward_if_sources_are_needed_and_available
- `step:st_3` (direct) -- spans=s16; section=sec_reusable_process; packet=p_list_item_retrieve_them_using_approved_source_recipes_maintain_provenance_for_externally_sourced_facts_when_enough_required_information_is_available
- `step:st_4` (direct) -- spans=s17; section=sec_reusable_process; packet=p_list_item_produce_a_draft_if_the_user_asks_for_revision
- `step:st_5` (direct) -- spans=s18; section=sec_reusable_process; packet=p_list_item_revise_while_re_checking_constraints_do_not_finalize_if_required_slots_remain_missing_unless_the_draft_is_explicitly_marked_as_assumption_bearing_and_the_user_confirms_at_the_end
- `step:st_6` (direct) -- spans=s19; section=sec_reusable_process; packet=p_list_item_record_a_short_assumptions_log_for_any_unresolved_items_and_set_a_completion_status_for_the_run
- `step:st_api_b7a71aa435` (direct) -- spans=s16; section=sec_reusable_process; packet=p_list_item_retrieve_them_using_approved_source_recipes_maintain_provenance_for_externally_sourced_facts_when_enough_required_information_is_available

### Variables
- `variable:assumptions_log` (direct) -- spans=s19; section=sec_reusable_process; packet=p_list_item_record_a_short_assumptions_log_for_any_unresolved_items_and_set_a_completion_status_for_the_run
- `variable:completion_status` (direct) -- spans=s19; section=sec_reusable_process; packet=p_list_item_record_a_short_assumptions_log_for_any_unresolved_items_and_set_a_completion_status_for_the_run
- `variable:draft_communication_artifact` (direct) -- spans=s17; section=sec_reusable_process; packet=p_list_item_produce_a_draft_if_the_user_asks_for_revision
- `variable:source_evidence_set` (direct) -- spans=s16; section=sec_reusable_process; packet=p_list_item_retrieve_them_using_approved_source_recipes_maintain_provenance_for_externally_sourced_facts_when_enough_required_information_is_available

### Constraints
- `constraint:c_1` (direct) -- spans=s20; section=sec_policies; packet=p_sentence_do_not_invent_links_or_unseen_facts
- `constraint:c_2` (direct) -- spans=s21; section=sec_policies; packet=p_sentence_require_evidence_for_sourced_claims
- `constraint:c_3` (direct) -- spans=s22; section=sec_policies; packet=p_sentence_limit_questions_per_turn
- `constraint:c_4` (direct) -- spans=s23; section=sec_policies; packet=p_sentence_prefer_tool_evidence_over_unnecessary_user_questioning
- `constraint:c_5` (direct) -- spans=s24; section=sec_policies; packet=p_sentence_deny_finalization_if_critical_slots_are_missing_or_provenance_fails

### Other
- `api:api:ApprovedSourceRecipesAPI` (direct) -- spans=s16; section=sec_reusable_process; packet=p_list_item_retrieve_them_using_approved_source_recipes_maintain_provenance_for_externally_sourced_facts_when_enough_required_information_is_available
- `profile:concept_0` (normalized)
- `profile:concept_1` (normalized)
- `profile:concept_10` (normalized)
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

- `worker:worker_main.exception_flow:exc_adapter_03`: `missing_handler` -- Exception flow 'exc_adapter_03' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_03, slot=handler_action]
  - Suggested resolution: Add a handler step for 'Missing timeframe', or mark this exception as acknowledged without handling.
- `worker:worker_main.exception_flow:exc_adapter_05`: `missing_handler` -- Exception flow 'exc_adapter_05' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_05, slot=handler_action]
  - Suggested resolution: Add a handler step for 'user refusal to answer', or mark this exception as acknowledged without handling.
- `worker:worker_main.exception_flow:exc_adapter_04`: `missing_handler` -- Exception flow 'exc_adapter_04' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_04, slot=handler_action]
  - Suggested resolution: Add a handler step for 'provenance failure', or mark this exception as acknowledged without handling.
- `worker:worker_main.exception_flow:exc_adapter_01`: `missing_handler` -- Exception flow 'exc_adapter_01' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_01, slot=handler_action]
  - Suggested resolution: Add a handler step for 'evidence
shortage', or mark this exception as acknowledged without handling.
- `worker:worker_main.exception_flow:exc_adapter_00`: `missing_handler` -- Exception flow 'exc_adapter_00' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_00, slot=handler_action]
  - Suggested resolution: Add a handler step for 'conflicting instructions', or mark this exception as acknowledged without handling.
- `worker:worker_main.exception_flow:exc_adapter_02`: `missing_handler` -- Exception flow 'exc_adapter_02' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_02, slot=handler_action]
  - Suggested resolution: Add a handler step for 'insufficient source access', or mark this exception as acknowledged without handling.
- `worker_promotion:del_s31`: `type_or_contract_ambiguity` -- WORKER_PROMOTION blocked by missing promotion slots.
  - Source spans: `s31`
  - `promotion_input_contract`: Missing clear input contract
  - `promotion_output_contract`: Missing clear output contract
  - `promotion_invocation_point`: Missing accepted decision or matching handoff with invocation hint
  - `promotion_result_handoff`: Missing matching handoff with output bindings
- `worker:worker_main.step:st_2`: `type_or_contract_ambiguity` -- REQUEST_INPUT step has no value target (outputs). [construct=worker:worker_main.step:st_2, slot=value_target]

## 4. Diagnostics

### irs_82aa44be011f: `missing_handler`
- Severity: `warning`
- Target: `worker:worker_main.exception_flow:exc_adapter_03`
- Source spans: `s25`
- Message: Exception flow 'exc_adapter_03' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_03, slot=handler_action]
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Add a handler step for 'Missing timeframe', or mark this exception as acknowledged without handling.
- Missing slot: `handler_action`
- Missing reason: Exception flow 'exc_adapter_03' has condition but no handler step.

### irs_b5c75258c745: `missing_handler`
- Severity: `warning`
- Target: `worker:worker_main.exception_flow:exc_adapter_05`
- Source spans: `s29`
- Message: Exception flow 'exc_adapter_05' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_05, slot=handler_action]
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Add a handler step for 'user refusal to answer', or mark this exception as acknowledged without handling.
- Missing slot: `handler_action`
- Missing reason: Exception flow 'exc_adapter_05' has condition but no handler step.

### irs_de963025d6c8: `missing_handler`
- Severity: `warning`
- Target: `worker:worker_main.exception_flow:exc_adapter_04`
- Source spans: `s30`
- Message: Exception flow 'exc_adapter_04' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_04, slot=handler_action]
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Add a handler step for 'provenance failure', or mark this exception as acknowledged without handling.
- Missing slot: `handler_action`
- Missing reason: Exception flow 'exc_adapter_04' has condition but no handler step.

### irs_ea4aabf8f488: `missing_handler`
- Severity: `warning`
- Target: `worker:worker_main.exception_flow:exc_adapter_01`
- Source spans: `s28`
- Message: Exception flow 'exc_adapter_01' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_01, slot=handler_action]
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Add a handler step for 'evidence
shortage', or mark this exception as acknowledged without handling.
- Missing slot: `handler_action`
- Missing reason: Exception flow 'exc_adapter_01' has condition but no handler step.

### irs_eb6a6a2f0b5c: `missing_handler`
- Severity: `warning`
- Target: `worker:worker_main.exception_flow:exc_adapter_00`
- Source spans: `s26`
- Message: Exception flow 'exc_adapter_00' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_00, slot=handler_action]
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Add a handler step for 'conflicting instructions', or mark this exception as acknowledged without handling.
- Missing slot: `handler_action`
- Missing reason: Exception flow 'exc_adapter_00' has condition but no handler step.

### irs_fd83d44e3194: `missing_handler`
- Severity: `warning`
- Target: `worker:worker_main.exception_flow:exc_adapter_02`
- Source spans: `s27`
- Message: Exception flow 'exc_adapter_02' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_02, slot=handler_action]
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Add a handler step for 'insufficient source access', or mark this exception as acknowledged without handling.
- Missing slot: `handler_action`
- Missing reason: Exception flow 'exc_adapter_02' has condition but no handler step.

### grouped:worker_promotion:del_s31: `type_or_contract_ambiguity`
- Severity: `warning`
- Target: `worker_promotion:del_s31`
- Source spans: `s31`
- Message: WORKER_PROMOTION blocked by missing promotion slots.
- Blocks rendering: `false`
- Blocks completion: `true`
- Missing slots:
  - `promotion_input_contract`: Missing clear input contract
    - Diagnostic: `irs_16c0d5b20df4`
  - `promotion_output_contract`: Missing clear output contract
    - Diagnostic: `irs_6b43a592b006`
  - `promotion_invocation_point`: Missing accepted decision or matching handoff with invocation hint
    - Diagnostic: `irs_6c2ebb9b34e6`
  - `promotion_result_handoff`: Missing matching handoff with output bindings
    - Diagnostic: `irs_d422db06a1ca`

### irs_1ab82003e884: `type_or_contract_ambiguity`
- Severity: `warning`
- Target: `worker:worker_main.step:st_2`
- Source spans: `s15`
- Message: REQUEST_INPUT step has no value target (outputs). [construct=worker:worker_main.step:st_2, slot=value_target]
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
    - Diagnostic: `irs_b1a69d1cc286`
  - `openapi_schema`: Schema placeholder is valid; downstream API validation is pending.
    - Diagnostic: `irs_995dca55be8f`

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
- Message: Variable 'known_topics' (text) is a contract input with no source-backed producer or adapter evidence.
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
- Target: `variable:available_connectors_or_source_repositories`
- Message: Variable 'available_connectors_or_source_repositories' (List[text]) is a contract input with no source-backed producer or adapter evidence.
- Blocks rendering: `false`
- Blocks completion: `false`

### stage2_route_refinement_diagnostic_: `route_refinement_diagnostic`
- Severity: `info`
- Message: LLM route diagnostic [mixed_delegation_semantics] span='s31': Delegation permission and delegation boundary condition are mixed; emitted multi-label.
- Blocks rendering: `false`
- Blocks completion: `false`

## 5. Deferred Validation

- `api_declaration:api:ApprovedSourceRecipesAPI`: API contract validation deferred downstream.
  - Placeholder fields: `functions`, `openapi_schema`
  - Validation authority: `downstream_spl_compiler`

## 6. Assumptions / Suggestions

- `ASM_0000` for `worker:worker_main.exception_flow:exc_adapter_00`: Exception flow has no handler action. The compiler suggests specifying what should happen when this failure occurs.
  - Reason: Source describes a failure condition but does not specify how to handle it.  The exception flow is preserved in SPL, but no handler command was rendered. (Exception flow 'exc_adapter_00' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adap)
  - Suggested resolution: Specify the handler action for worker:worker_main.exception_flow:exc_adapter_00: e.g. ask the user for missing information, block finalization, or continue with an explicit assumption.
  - Related diagnostic: `irs_eb6a6a2f0b5c`
- `ASM_0001` for `worker:worker_main.exception_flow:exc_adapter_01`: Exception flow has no handler action. The compiler suggests specifying what should happen when this failure occurs.
  - Reason: Source describes a failure condition but does not specify how to handle it.  The exception flow is preserved in SPL, but no handler command was rendered. (Exception flow 'exc_adapter_01' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adap)
  - Suggested resolution: Specify the handler action for worker:worker_main.exception_flow:exc_adapter_01: e.g. ask the user for missing information, block finalization, or continue with an explicit assumption.
  - Related diagnostic: `irs_ea4aabf8f488`
- `ASM_0002` for `worker:worker_main.exception_flow:exc_adapter_02`: Exception flow has no handler action. The compiler suggests specifying what should happen when this failure occurs.
  - Reason: Source describes a failure condition but does not specify how to handle it.  The exception flow is preserved in SPL, but no handler command was rendered. (Exception flow 'exc_adapter_02' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adap)
  - Suggested resolution: Specify the handler action for worker:worker_main.exception_flow:exc_adapter_02: e.g. ask the user for missing information, block finalization, or continue with an explicit assumption.
  - Related diagnostic: `irs_fd83d44e3194`
- `ASM_0003` for `worker:worker_main.exception_flow:exc_adapter_03`: Exception flow has no handler action. The compiler suggests specifying what should happen when this failure occurs.
  - Reason: Source describes a failure condition but does not specify how to handle it.  The exception flow is preserved in SPL, but no handler command was rendered. (Exception flow 'exc_adapter_03' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adap)
  - Suggested resolution: Specify the handler action for worker:worker_main.exception_flow:exc_adapter_03: e.g. ask the user for missing information, block finalization, or continue with an explicit assumption.
  - Related diagnostic: `irs_82aa44be011f`
- `ASM_0004` for `worker:worker_main.exception_flow:exc_adapter_04`: Exception flow has no handler action. The compiler suggests specifying what should happen when this failure occurs.
  - Reason: Source describes a failure condition but does not specify how to handle it.  The exception flow is preserved in SPL, but no handler command was rendered. (Exception flow 'exc_adapter_04' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adap)
  - Suggested resolution: Specify the handler action for worker:worker_main.exception_flow:exc_adapter_04: e.g. ask the user for missing information, block finalization, or continue with an explicit assumption.
  - Related diagnostic: `irs_de963025d6c8`
- `ASM_0005` for `worker:worker_main.exception_flow:exc_adapter_05`: Exception flow has no handler action. The compiler suggests specifying what should happen when this failure occurs.
  - Reason: Source describes a failure condition but does not specify how to handle it.  The exception flow is preserved in SPL, but no handler command was rendered. (Exception flow 'exc_adapter_05' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adap)
  - Suggested resolution: Specify the handler action for worker:worker_main.exception_flow:exc_adapter_05: e.g. ask the user for missing information, block finalization, or continue with an explicit assumption.
  - Related diagnostic: `irs_b5c75258c745`
- `ASM_0006` for `worker:worker_main.step:st_2`: Command has an ambiguous or incomplete contract. The compiler suggests providing the missing contract detail.
  - Reason: A command references an API, worker, or input source that is not fully specified.  The compiler cannot materialize the command without this information.
  - Suggested resolution: For worker:worker_main.step:st_2: provide the missing contract detail (API name, worker target, IO bindings, or source evidence).  See the related diagnostic for specifics.
  - Related diagnostic: `irs_1ab82003e884`
- `ASM_0007` for `variable:format_preferences`: Variable has no discoverable source provenance.
  - Reason: The compiler could not trace this variable back to a source span, adapter hard fact, or producer step.  Its origin is assumed.
  - Suggested resolution: For variable:format_preferences: add source evidence (a span, adapter hint, or producer step) that justifies this variable's existence.
  - Related diagnostic: `diag_prov_0000`
- `ASM_0008` for `variable:user_request`: Variable has no discoverable source provenance.
  - Reason: The compiler could not trace this variable back to a source span, adapter hard fact, or producer step.  Its origin is assumed.
  - Suggested resolution: For variable:user_request: add source evidence (a span, adapter hint, or producer step) that justifies this variable's existence.
  - Related diagnostic: `diag_prov_0001`
- `ASM_0009` for `variable:known_topics`: Variable has no discoverable source provenance.
  - Reason: The compiler could not trace this variable back to a source span, adapter hard fact, or producer step.  Its origin is assumed.
  - Suggested resolution: For variable:known_topics: add source evidence (a span, adapter hint, or producer step) that justifies this variable's existence.
  - Related diagnostic: `diag_prov_0002`
- `ASM_0010` for `variable:timeframe`: Variable has no discoverable source provenance.
  - Reason: The compiler could not trace this variable back to a source span, adapter hard fact, or producer step.  Its origin is assumed.
  - Suggested resolution: For variable:timeframe: add source evidence (a span, adapter hint, or producer step) that justifies this variable's existence.
  - Related diagnostic: `diag_prov_0003`
- `ASM_0011` for `variable:available_connectors_or_source_repositories`: Variable has no discoverable source provenance.
  - Reason: The compiler could not trace this variable back to a source span, adapter hard fact, or producer step.  Its origin is assumed.
  - Suggested resolution: For variable:available_connectors_or_source_repositories: add source evidence (a span, adapter hint, or producer step) that justifies this variable's existence.
  - Related diagnostic: `diag_prov_0004`
- `ASM_0012, ASM_0013, ASM_0014, ASM_0015` for `worker_promotion:del_s31`: Worker promotion has an incomplete contract.
  - Reason: The candidate is blocked by multiple missing promotion slots.
  - Suggested resolution: Provide the missing input/output contracts, invocation point, and result handoff details listed in the related diagnostics.
  - Related diagnostics: `irs_16c0d5b20df4, irs_6b43a592b006, irs_6c2ebb9b34e6, irs_d422db06a1ca`

## 7. Provenance / TraceRecords

- `api:api:ApprovedSourceRecipesAPI` -> `direct`
  - Source: spans=`s16`, section=`sec_reusable_process`, packet=`p_list_item_retrieve_them_using_approved_source_recipes_maintain_provenance_for_externally_sourced_facts_when_enough_required_information_is_available`
  - Explanation: API declaration 'ApprovedSourceRecipesAPI' materialized as grammar_minimal_partial.
- `constraint:c_1` -> `direct`
  - Source: spans=`s20`, section=`sec_policies`, packet=`p_sentence_do_not_invent_links_or_unseen_facts`
  - Explanation: Constraint 'c_1' (prohibition): Do not invent links or unseen facts.
- `constraint:c_2` -> `direct`
  - Source: spans=`s21`, section=`sec_policies`, packet=`p_sentence_require_evidence_for_sourced_claims`
  - Explanation: Constraint 'c_2' (evidence): Require evidence for sourced claims.
- `constraint:c_3` -> `direct`
  - Source: spans=`s22`, section=`sec_policies`, packet=`p_sentence_limit_questions_per_turn`
  - Explanation: Constraint 'c_3' (requirement): Limit questions per turn.
- `constraint:c_4` -> `direct`
  - Source: spans=`s23`, section=`sec_policies`, packet=`p_sentence_prefer_tool_evidence_over_unnecessary_user_questioning`
  - Explanation: Constraint 'c_4' (requirement): Prefer tool evidence over unnecessary user questioning.
- `constraint:c_5` -> `direct`
  - Source: spans=`s24`, section=`sec_policies`, packet=`p_sentence_deny_finalization_if_critical_slots_are_missing_or_provenance_fails`
  - Explanation: Constraint 'c_5' (gate): Deny finalization if critical slots are missing or provenance fails.
- `flow:alt_1` -> `direct`
  - Source: spans=`s18`, section=`sec_reusable_process`, packet=`p_list_item_revise_while_re_checking_constraints_do_not_finalize_if_required_slots_remain_missing_unless_the_draft_is_explicitly_marked_as_assumption_bearing_and_the_user_confirms_at_the_end`
  - Explanation: Alternative flow 'alt_1': the user asks for revision
- `flow:exc_adapter_00` -> `direct`
  - Source: spans=`s26`, section=`sec_failure_handling`, packet=`p_list_item_conflicting_instructions`
  - Explanation: Exception flow 'exc_adapter_00': conflicting instructions
- `flow:exc_adapter_01` -> `direct`
  - Source: spans=`s28`, section=`sec_failure_handling`, packet=`p_list_item_evidence_shortage`
  - Explanation: Exception flow 'exc_adapter_01': evidence
shortage
- `flow:exc_adapter_02` -> `direct`
  - Source: spans=`s27`, section=`sec_failure_handling`, packet=`p_list_item_insufficient_source_access`
  - Explanation: Exception flow 'exc_adapter_02': insufficient source access
- `flow:exc_adapter_03` -> `direct`
  - Source: spans=`s25`, section=`sec_failure_handling`, packet=`p_list_item_missing_timeframe`
  - Explanation: Exception flow 'exc_adapter_03': Missing timeframe
- `flow:exc_adapter_04` -> `direct`
  - Source: spans=`s30`, section=`sec_failure_handling`, packet=`p_list_item_provenance_failure`
  - Explanation: Exception flow 'exc_adapter_04': provenance failure
- `flow:exc_adapter_05` -> `direct`
  - Source: spans=`s29`, section=`sec_failure_handling`, packet=`p_list_item_user_refusal_to_answer`
  - Explanation: Exception flow 'exc_adapter_05': user refusal to answer
- `flow:main` -> `direct`
  - Source: spans=`s15, s16, s17, s19`, section=`sec_reusable_process`, packet=`p_list_item_first_determine_what_kind_of_communication_is_requested_then_identify_which_required_fields_are_still_missing_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward_if_sources_are_needed_and_available`
  - Explanation: Main flow with 4 block(s).
- `profile:concept_0` -> `normalized`
  - Explanation: Concept: Internal newsletters -- Newsletters intended for an internal organizational audience.
- `profile:concept_1` -> `normalized`
  - Explanation: Concept: announcements -- Official internal messages sharing important updates or information.
- `profile:concept_10` -> `normalized`
  - Explanation: Concept: approved evidence carriers -- Accepted formats or containers for returned evidence so it can be normalized and used safely.
- `profile:concept_2` -> `normalized`
  - Explanation: Concept: update digests -- Condensed summaries of recent updates compiled into one communication.
- `profile:concept_3` -> `normalized`
  - Explanation: Concept: executive briefs -- Short, high-level summaries prepared for executives.
- `profile:concept_4` -> `normalized`
  - Explanation: Concept: internal-comms artifacts -- Deliverables used in internal communications work, such as drafts or structured messages.
- `profile:concept_5` -> `normalized`
  - Explanation: Concept: source/evidence set -- A collection of sources and supporting evidence used to justify the draft communication.
- `profile:concept_6` -> `normalized`
  - Explanation: Concept: assumptions log -- A brief record of unresolved items and the assumptions made about them.
- `profile:concept_7` -> `normalized`
  - Explanation: Concept: completion status -- A final indicator of whether the run is complete or blocked.
- `profile:concept_8` -> `normalized`
  - Explanation: Concept: provenance -- Traceability showing where a claim or fact came from.
- `profile:concept_9` -> `normalized`
  - Explanation: Concept: approved source recipes -- Authorized procedures for retrieving information from sources.
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
- `step:st_5` -> `direct`
  - Source: spans=`s18`, section=`sec_reusable_process`, packet=`p_list_item_revise_while_re_checking_constraints_do_not_finalize_if_required_slots_remain_missing_unless_the_draft_is_explicitly_marked_as_assumption_bearing_and_the_user_confirms_at_the_end`
  - Explanation: Step 'st_5' maps to source span(s).
- `step:st_6` -> `direct`
  - Source: spans=`s19`, section=`sec_reusable_process`, packet=`p_list_item_record_a_short_assumptions_log_for_any_unresolved_items_and_set_a_completion_status_for_the_run`
  - Explanation: Step 'st_6' maps to source span(s).
- `step:st_api_b7a71aa435` -> `direct`
  - Source: spans=`s16`, section=`sec_reusable_process`, packet=`p_list_item_retrieve_them_using_approved_source_recipes_maintain_provenance_for_externally_sourced_facts_when_enough_required_information_is_available`
  - Explanation: Step 'st_api_b7a71aa435' maps to source span(s).
- `variable:assumptions_log` -> `direct`
  - Source: spans=`s19`, section=`sec_reusable_process`, packet=`p_list_item_record_a_short_assumptions_log_for_any_unresolved_items_and_set_a_completion_status_for_the_run`
  - Explanation: Variable 'assumptions_log' is produced by source-backed step 'st_6'.
- `variable:available_connectors_or_source_repositories` -> `assumed` [needs confirmation]
  - Explanation: Variable 'available_connectors_or_source_repositories' is declared as worker input contract with no source evidence.
- `variable:completion_status` -> `direct`
  - Source: spans=`s19`, section=`sec_reusable_process`, packet=`p_list_item_record_a_short_assumptions_log_for_any_unresolved_items_and_set_a_completion_status_for_the_run`
  - Explanation: Variable 'completion_status' is produced by source-backed step 'st_6'.
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
  - Source: spans=`s15, s16, s17, s18, s19`, section=`sec_reusable_process`, packet=`p_list_item_first_determine_what_kind_of_communication_is_requested_then_identify_which_required_fields_are_still_missing_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward_if_sources_are_needed_and_available`
  - Explanation: Main worker 'MainWorker' assembled from flow and step IRs.

## 8. Anti-Fabrication Checks

- `missing_handler`: Exception conditions without handler action stay as partial exception flows; no handler command is invented.
- `type_or_contract_ambiguity`: Unresolved worker/API contracts are reported as ambiguity; they are not downgraded to generic commands.
- Rendered SPL contains no executable `[INVOKE ...]` command.

## 9. Adapter / Validation Notes

Validation warnings:
- ConstructPlan: condition span s26 for exc_demand_00 has unowned; attached to main worker worker_main.
- ConstructPlan: condition span s28 for exc_demand_01 has unowned; attached to main worker worker_main.
- ConstructPlan: condition span s27 for exc_demand_02 has unowned; attached to main worker worker_main.
- ConstructPlan: condition span s25 for exc_demand_03 has unowned; attached to main worker worker_main.
- ConstructPlan: condition span s30 for exc_demand_04 has unowned; attached to main worker worker_main.
- ConstructPlan: condition span s29 for exc_demand_05 has unowned; attached to main worker worker_main.
- ConstructPlan: condition span s26 for exc_demand_00 has unowned; attached to main worker worker_main.
- ConstructPlan: condition span s28 for exc_demand_01 has unowned; attached to main worker worker_main.
- ConstructPlan: condition span s27 for exc_demand_02 has unowned; attached to main worker worker_main.
- ConstructPlan: condition span s25 for exc_demand_03 has unowned; attached to main worker worker_main.
- ConstructPlan: condition span s30 for exc_demand_04 has unowned; attached to main worker worker_main.
- ConstructPlan: condition span s29 for exc_demand_05 has unowned; attached to main worker worker_main.

## 10. SPL Draft

```spl
[DEFINE_AGENT: MainWorker "Orchestrate the end-to-end process and delegate to sub-tasks."]
    [DEFINE_PERSONA:]
        ROLE: Internal communications specialist
        EvidenceDriven: Produces communication drafts based on available sources and evidence, and avoids inventing unseen facts.
        ClarificationFocused: Asks only the highest-value clarifying questions needed to proceed.
        ConstraintAware: Rechecks requirements before finalizing and records unresolved assumptions.
        ProvenanceConscious: Maintains provenance for externally sourced facts and requires evidence for sourced claims.
    [END_PERSONA]
    [DEFINE_CONCEPTS:]
        Internalnewsletters: Newsletters intended for an internal organizational audience.
        Announcements: Official internal messages sharing important updates or information.
        Updatedigests: Condensed summaries of recent updates compiled into one communication.
        Executivebriefs: Short, high-level summaries prepared for executives.
        Internalcommsartifacts: Deliverables used in internal communications work, such as drafts or structured messages.
        Sourceevidenceset: A collection of sources and supporting evidence used to justify the draft communication.
        Assumptionslog: A brief record of unresolved items and the assumptions made about them.
        Completionstatus: A final indicator of whether the run is complete or blocked.
        Provenance: Traceability showing where a claim or fact came from.
        Approvedsourcerecipes: Authorized procedures for retrieving information from sources.
        Approvedevidencecarriers: Accepted formats or containers for returned evidence so it can be normalized and used safely.
    [END_CONCEPTS]
    [DEFINE_CONSTRAINTS:]
        Prohibition: Do not invent links or unseen facts.
        Evidence: Require evidence for sourced claims.
        Requirement: Limit questions per turn.
        Requirement: Prefer tool evidence over unnecessary user questioning.
        Gate: Deny finalization if critical slots are missing or provenance fails.
    [END_CONSTRAINTS]
    [DEFINE_VARIABLES:]
        "Optional formatting preferences provided by the user." format_preferences: text
        "The user request describing what communication is needed." user_request: text
        "Optional topics already known or provided." known_topics: text
        "Optional time range or deadline context." timeframe: text
        "Available connectors or source repositories that can be used for retrieval." available_connectors_or_source_repositories: List [text]
        "Draft communication artifact produced by the workflow." draft_communication_artifact: text
        "Collected sources and evidence supporting the draft." source_evidence_set: text
        "Short log of assumptions made for unresolved items." assumptions_log: text
        "Final completion status for the run." completion_status: text
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
                COMMAND-1 [COMMAND Determine the communication type and missing required fields based on <REF>user_request</REF>, <REF>known_topics</REF>, and <REF>timeframe</REF>]
                COMMAND-2 [INPUT Ask the highest-value clarifying questions based on <REF>user_request</REF> VALUE user_input:text SET]
            [END_SEQUENTIAL_BLOCK]
            DECISION-1 [IF sources are needed and available]
                COMMAND-3 [COMMAND Retrieve approved sources and maintain provenance based on <REF>available_connectors_or_source_repositories</REF> RESULT source_evidence_set: text SET]
                COMMAND-4 [CALL ApprovedSourceRecipesAPI]
            [END_IF]
            DECISION-2 [IF the user asks for revision]
                COMMAND-5 [COMMAND Produce the draft communication artifact based on <REF>user_request</REF>, <REF>known_topics</REF>, <REF>timeframe</REF>, <REF>format_preferences</REF>, and <REF>source_evidence_set</REF> RESULT draft_communication_artifact: text SET]
            [END_IF]
            [SEQUENTIAL_BLOCK]
                COMMAND-6 [COMMAND Record the assumptions log and set the completion status based on <REF>draft_communication_artifact</REF> and <REF>source_evidence_set</REF> RESULT assumptions_log: text, completion_status: text SET]
            [END_SEQUENTIAL_BLOCK]
        [END_MAIN_FLOW]
        [ALTERNATIVE_FLOW: the user asks for revision]
            [SEQUENTIAL_BLOCK]
                COMMAND-7 [COMMAND Revise the draft communication artifact based on <REF>draft_communication_artifact</REF>, <REF>user_request</REF>, <REF>format_preferences</REF>, and <REF>source_evidence_set</REF> RESULT <REF>draft_communication_artifact</REF> SET]
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
