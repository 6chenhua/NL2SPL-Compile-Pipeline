# NL2SPL Feedback Report

## 1. Overall Compile State

- Completeness: `partial`
- SPL draft generated: `yes`
- Compile diagnostics: `25`
- Assumptions / suggestions: `22`
- Trace records: `52`
- Adapter warnings: `0`
- Validation errors: `0`
- Validation warnings: `19`

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
- `step:st_3` (direct) -- spans=s15; section=sec_reusable_process; packet=p_list_item_first_determine_what_kind_of_communication_is_requested_then_identify_which_required_fields_are_still_missing_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward_if_sources_are_needed_and_available
- `step:st_4` (direct) -- spans=s16; section=sec_reusable_process; packet=p_list_item_retrieve_them_using_approved_source_recipes_maintain_provenance_for_externally_sourced_facts_when_enough_required_information_is_available
- `step:st_5` (direct) -- spans=s17; section=sec_reusable_process; packet=p_list_item_produce_a_draft_if_the_user_asks_for_revision
- `step:st_6` (direct) -- spans=s18; section=sec_reusable_process; packet=p_list_item_revise_while_re_checking_constraints_do_not_finalize_if_required_slots_remain_missing_unless_the_draft_is_explicitly_marked_as_assumption_bearing_and_the_user_confirms_at_the_end
- `step:st_7` (direct) -- spans=s19; section=sec_reusable_process; packet=p_list_item_record_a_short_assumptions_log_for_any_unresolved_items_and_set_a_completion_status_for_the_run
- `step:st_api_b7a71aa435` (direct) -- spans=s16; section=sec_reusable_process; packet=p_list_item_retrieve_them_using_approved_source_recipes_maintain_provenance_for_externally_sourced_facts_when_enough_required_information_is_available

### Variables
- `variable:assumptions_log` (direct) -- spans=s19; section=sec_reusable_process; packet=p_list_item_record_a_short_assumptions_log_for_any_unresolved_items_and_set_a_completion_status_for_the_run
- `variable:completion_status` (direct) -- spans=s19; section=sec_reusable_process; packet=p_list_item_record_a_short_assumptions_log_for_any_unresolved_items_and_set_a_completion_status_for_the_run
- `variable:draft_communication_artifact` (direct) -- spans=s17; section=sec_reusable_process; packet=p_list_item_produce_a_draft_if_the_user_asks_for_revision
- `variable:missing_required_fields` (direct) -- spans=s15; section=sec_reusable_process; packet=p_list_item_first_determine_what_kind_of_communication_is_requested_then_identify_which_required_fields_are_still_missing_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward_if_sources_are_needed_and_available
- `variable:requested_communication_kind` (direct) -- spans=s15; section=sec_reusable_process; packet=p_list_item_first_determine_what_kind_of_communication_is_requested_then_identify_which_required_fields_are_still_missing_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward_if_sources_are_needed_and_available
- `variable:source_evidence_set` (direct) -- spans=s16; section=sec_reusable_process; packet=p_list_item_retrieve_them_using_approved_source_recipes_maintain_provenance_for_externally_sourced_facts_when_enough_required_information_is_available
- `variable:user_confirmed` (direct) -- spans=s15; section=sec_reusable_process; packet=p_list_item_first_determine_what_kind_of_communication_is_requested_then_identify_which_required_fields_are_still_missing_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward_if_sources_are_needed_and_available

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
- `profile:concept_2` (normalized)
- `profile:concept_3` (normalized)
- `profile:concept_4` (normalized)
- `profile:concept_5` (normalized)
- `profile:concept_6` (normalized)
- `profile:concept_7` (normalized)
- `profile:concept_8` (normalized)
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
- Target: `variable:sources_needed`
- Message: Variable 'sources_needed' (boolean) has no source-backed producer and no contract section evidence.
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_prov_0006: `missing_provenance`
- Severity: `warning`
- Target: `variable:sources_available`
- Message: Variable 'sources_available' (boolean) has no source-backed producer and no contract section evidence.
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_prov_0007: `missing_provenance`
- Severity: `warning`
- Target: `variable:required_information_available`
- Message: Variable 'required_information_available' (boolean) has no source-backed producer and no contract section evidence.
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_prov_0008: `missing_provenance`
- Severity: `warning`
- Target: `variable:revision_requested`
- Message: Variable 'revision_requested' (boolean) has no source-backed producer and no contract section evidence.
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_prov_0009: `missing_provenance`
- Severity: `warning`
- Target: `variable:constraints_rechecked`
- Message: Variable 'constraints_rechecked' (boolean) has no source-backed producer and no contract section evidence.
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_prov_0010: `missing_provenance`
- Severity: `warning`
- Target: `variable:required_slots_missing`
- Message: Variable 'required_slots_missing' (boolean) has no source-backed producer and no contract section evidence.
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_prov_0011: `missing_provenance`
- Severity: `warning`
- Target: `variable:draft_explicitly_marked_as_assumption_bearing`
- Message: Variable 'draft_explicitly_marked_as_assumption_bearing' (boolean) has no source-backed producer and no contract section evidence.
- Blocks rendering: `false`
- Blocks completion: `false`

### stage2_route_refinement_diagnostic_: `route_refinement_diagnostic`
- Severity: `info`
- Message: LLM route diagnostic [prior_overridden] span='s1': Structural prior suggested a domain route, but the span is better classified as profile_domain because it names a content type in the task family.
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
- `ASM_0006` for `variable:format_preferences`: Variable has no discoverable source provenance.
  - Reason: The compiler could not trace this variable back to a source span, adapter hard fact, or producer step.  Its origin is assumed.
  - Suggested resolution: For variable:format_preferences: add source evidence (a span, adapter hint, or producer step) that justifies this variable's existence.
  - Related diagnostic: `diag_prov_0000`
- `ASM_0007` for `variable:user_request`: Variable has no discoverable source provenance.
  - Reason: The compiler could not trace this variable back to a source span, adapter hard fact, or producer step.  Its origin is assumed.
  - Suggested resolution: For variable:user_request: add source evidence (a span, adapter hint, or producer step) that justifies this variable's existence.
  - Related diagnostic: `diag_prov_0001`
- `ASM_0008` for `variable:known_topics`: Variable has no discoverable source provenance.
  - Reason: The compiler could not trace this variable back to a source span, adapter hard fact, or producer step.  Its origin is assumed.
  - Suggested resolution: For variable:known_topics: add source evidence (a span, adapter hint, or producer step) that justifies this variable's existence.
  - Related diagnostic: `diag_prov_0002`
- `ASM_0009` for `variable:timeframe`: Variable has no discoverable source provenance.
  - Reason: The compiler could not trace this variable back to a source span, adapter hard fact, or producer step.  Its origin is assumed.
  - Suggested resolution: For variable:timeframe: add source evidence (a span, adapter hint, or producer step) that justifies this variable's existence.
  - Related diagnostic: `diag_prov_0003`
- `ASM_0010` for `variable:connectors_or_source_repositories`: Variable has no discoverable source provenance.
  - Reason: The compiler could not trace this variable back to a source span, adapter hard fact, or producer step.  Its origin is assumed.
  - Suggested resolution: For variable:connectors_or_source_repositories: add source evidence (a span, adapter hint, or producer step) that justifies this variable's existence.
  - Related diagnostic: `diag_prov_0004`
- `ASM_0011` for `variable:sources_needed`: Variable has no discoverable source provenance.
  - Reason: The compiler could not trace this variable back to a source span, adapter hard fact, or producer step.  Its origin is assumed.
  - Suggested resolution: For variable:sources_needed: add source evidence (a span, adapter hint, or producer step) that justifies this variable's existence.
  - Related diagnostic: `diag_prov_0005`
- `ASM_0012` for `variable:sources_available`: Variable has no discoverable source provenance.
  - Reason: The compiler could not trace this variable back to a source span, adapter hard fact, or producer step.  Its origin is assumed.
  - Suggested resolution: For variable:sources_available: add source evidence (a span, adapter hint, or producer step) that justifies this variable's existence.
  - Related diagnostic: `diag_prov_0006`
- `ASM_0013` for `variable:required_information_available`: Variable has no discoverable source provenance.
  - Reason: The compiler could not trace this variable back to a source span, adapter hard fact, or producer step.  Its origin is assumed.
  - Suggested resolution: For variable:required_information_available: add source evidence (a span, adapter hint, or producer step) that justifies this variable's existence.
  - Related diagnostic: `diag_prov_0007`
- `ASM_0014` for `variable:revision_requested`: Variable has no discoverable source provenance.
  - Reason: The compiler could not trace this variable back to a source span, adapter hard fact, or producer step.  Its origin is assumed.
  - Suggested resolution: For variable:revision_requested: add source evidence (a span, adapter hint, or producer step) that justifies this variable's existence.
  - Related diagnostic: `diag_prov_0008`
- `ASM_0015` for `variable:constraints_rechecked`: Variable has no discoverable source provenance.
  - Reason: The compiler could not trace this variable back to a source span, adapter hard fact, or producer step.  Its origin is assumed.
  - Suggested resolution: For variable:constraints_rechecked: add source evidence (a span, adapter hint, or producer step) that justifies this variable's existence.
  - Related diagnostic: `diag_prov_0009`
- `ASM_0016` for `variable:required_slots_missing`: Variable has no discoverable source provenance.
  - Reason: The compiler could not trace this variable back to a source span, adapter hard fact, or producer step.  Its origin is assumed.
  - Suggested resolution: For variable:required_slots_missing: add source evidence (a span, adapter hint, or producer step) that justifies this variable's existence.
  - Related diagnostic: `diag_prov_0010`
- `ASM_0017` for `variable:draft_explicitly_marked_as_assumption_bearing`: Variable has no discoverable source provenance.
  - Reason: The compiler could not trace this variable back to a source span, adapter hard fact, or producer step.  Its origin is assumed.
  - Suggested resolution: For variable:draft_explicitly_marked_as_assumption_bearing: add source evidence (a span, adapter hint, or producer step) that justifies this variable's existence.
  - Related diagnostic: `diag_prov_0011`
- `ASM_0018, ASM_0019, ASM_0020, ASM_0021` for `worker_promotion:del_s31`: Worker promotion has an incomplete contract.
  - Reason: The candidate is blocked by multiple missing promotion slots.
  - Suggested resolution: Provide the missing input/output contracts, invocation point, and result handoff details listed in the related diagnostics.
  - Related diagnostics: `irs_16c0d5b20df4, irs_6b43a592b006, irs_6c2ebb9b34e6, irs_d422db06a1ca`

## 7. Provenance / TraceRecords

- `api:api:ApprovedSourceRecipesAPI` -> `direct`
  - Source: spans=`s16`, section=`sec_reusable_process`, packet=`p_list_item_retrieve_them_using_approved_source_recipes_maintain_provenance_for_externally_sourced_facts_when_enough_required_information_is_available`
  - Explanation: API declaration 'ApprovedSourceRecipesAPI' materialized as grammar_minimal_partial.
- `constraint:c_1` -> `direct`
  - Source: spans=`s20`, section=`sec_policies`, packet=`p_sentence_do_not_invent_links_or_unseen_facts`
  - Explanation: Constraint 'c_1' (prohibition): Do not invent links or unseen facts
- `constraint:c_2` -> `direct`
  - Source: spans=`s21`, section=`sec_policies`, packet=`p_sentence_require_evidence_for_sourced_claims`
  - Explanation: Constraint 'c_2' (evidence): Require evidence for sourced claims
- `constraint:c_3` -> `direct`
  - Source: spans=`s22`, section=`sec_policies`, packet=`p_sentence_limit_questions_per_turn`
  - Explanation: Constraint 'c_3' (requirement): Limit questions per turn
- `constraint:c_4` -> `direct`
  - Source: spans=`s23`, section=`sec_policies`, packet=`p_sentence_prefer_tool_evidence_over_unnecessary_user_questioning`
  - Explanation: Constraint 'c_4' (requirement): Prefer tool evidence over unnecessary user questioning
- `constraint:c_5` -> `direct`
  - Source: spans=`s24`, section=`sec_policies`, packet=`p_sentence_deny_finalization_if_critical_slots_are_missing_or_provenance_fails`
  - Explanation: Constraint 'c_5' (gate): Deny finalization if critical slots are missing or provenance fails
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
  - Explanation: Main flow with 1 block(s).
- `profile:concept_0` -> `normalized`
  - Explanation: Concept: Internal newsletters -- Internal company newsletter communications intended for employees or internal stakeholders.
- `profile:concept_1` -> `normalized`
  - Explanation: Concept: Announcements -- Internal communications that notify the organization about updates, events, or decisions.
- `profile:concept_2` -> `normalized`
  - Explanation: Concept: Update digests -- Condensed summaries of recent updates gathered into a single communication.
- `profile:concept_3` -> `normalized`
  - Explanation: Concept: Executive briefs -- Concise, high-level summaries prepared for executives.
- `profile:concept_4` -> `normalized`
  - Explanation: Concept: Internal-comms artifacts -- Materials produced as part of internal communications work, such as newsletters, announcements, or briefs.
- `profile:concept_5` -> `normalized`
  - Explanation: Concept: Source/evidence set -- A collection of sources or supporting evidence used to justify the draft communication.
- `profile:concept_6` -> `normalized`
  - Explanation: Concept: Provenance -- Traceability showing where externally sourced facts came from.
- `profile:concept_7` -> `normalized`
  - Explanation: Concept: Approved source recipes -- Authorized procedures or patterns for retrieving information from sources.
- `profile:concept_8` -> `normalized`
  - Explanation: Concept: Approved evidence carriers -- Accepted formats or containers for normalized evidence returned from delegated subtasks.
- `profile:persona` -> `inferred`
  - Explanation: Persona: Internal communications specialist
- `step:st_1` -> `direct`
  - Source: spans=`s15`, section=`sec_reusable_process`, packet=`p_list_item_first_determine_what_kind_of_communication_is_requested_then_identify_which_required_fields_are_still_missing_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward_if_sources_are_needed_and_available`
  - Explanation: Step 'st_1' maps to source span(s).
- `step:st_2` -> `direct`
  - Source: spans=`s15`, section=`sec_reusable_process`, packet=`p_list_item_first_determine_what_kind_of_communication_is_requested_then_identify_which_required_fields_are_still_missing_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward_if_sources_are_needed_and_available`
  - Explanation: Step 'st_2' maps to source span(s).
- `step:st_3` -> `direct`
  - Source: spans=`s15`, section=`sec_reusable_process`, packet=`p_list_item_first_determine_what_kind_of_communication_is_requested_then_identify_which_required_fields_are_still_missing_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward_if_sources_are_needed_and_available`
  - Explanation: Step 'st_3' maps to source span(s).
- `step:st_4` -> `direct`
  - Source: spans=`s16`, section=`sec_reusable_process`, packet=`p_list_item_retrieve_them_using_approved_source_recipes_maintain_provenance_for_externally_sourced_facts_when_enough_required_information_is_available`
  - Explanation: Step 'st_4' maps to source span(s).
- `step:st_5` -> `direct`
  - Source: spans=`s17`, section=`sec_reusable_process`, packet=`p_list_item_produce_a_draft_if_the_user_asks_for_revision`
  - Explanation: Step 'st_5' maps to source span(s).
- `step:st_6` -> `direct`
  - Source: spans=`s18`, section=`sec_reusable_process`, packet=`p_list_item_revise_while_re_checking_constraints_do_not_finalize_if_required_slots_remain_missing_unless_the_draft_is_explicitly_marked_as_assumption_bearing_and_the_user_confirms_at_the_end`
  - Explanation: Step 'st_6' maps to source span(s).
- `step:st_7` -> `direct`
  - Source: spans=`s19`, section=`sec_reusable_process`, packet=`p_list_item_record_a_short_assumptions_log_for_any_unresolved_items_and_set_a_completion_status_for_the_run`
  - Explanation: Step 'st_7' maps to source span(s).
- `step:st_api_b7a71aa435` -> `direct`
  - Source: spans=`s16`, section=`sec_reusable_process`, packet=`p_list_item_retrieve_them_using_approved_source_recipes_maintain_provenance_for_externally_sourced_facts_when_enough_required_information_is_available`
  - Explanation: Step 'st_api_b7a71aa435' maps to source span(s).
- `variable:assumptions_log` -> `direct`
  - Source: spans=`s19`, section=`sec_reusable_process`, packet=`p_list_item_record_a_short_assumptions_log_for_any_unresolved_items_and_set_a_completion_status_for_the_run`
  - Explanation: Variable 'assumptions_log' is produced by source-backed step 'st_7'.
- `variable:completion_status` -> `direct`
  - Source: spans=`s19`, section=`sec_reusable_process`, packet=`p_list_item_record_a_short_assumptions_log_for_any_unresolved_items_and_set_a_completion_status_for_the_run`
  - Explanation: Variable 'completion_status' is produced by source-backed step 'st_7'.
- `variable:connectors_or_source_repositories` -> `assumed` [needs confirmation]
  - Explanation: Variable 'connectors_or_source_repositories' is declared as worker input contract with no source evidence.
- `variable:constraints_rechecked` -> `assumed` [needs confirmation]
  - Explanation: Variable 'constraints_rechecked' is a declared step variable with no discoverable source provenance.
- `variable:draft_communication_artifact` -> `direct`
  - Source: spans=`s17`, section=`sec_reusable_process`, packet=`p_list_item_produce_a_draft_if_the_user_asks_for_revision`
  - Explanation: Variable 'draft_communication_artifact' is produced by source-backed step 'st_5'.
- `variable:draft_explicitly_marked_as_assumption_bearing` -> `assumed` [needs confirmation]
  - Explanation: Variable 'draft_explicitly_marked_as_assumption_bearing' is a declared step variable with no discoverable source provenance.
- `variable:format_preferences` -> `assumed` [needs confirmation]
  - Explanation: Variable 'format_preferences' is declared as worker input contract with no source evidence.
- `variable:known_topics` -> `assumed` [needs confirmation]
  - Explanation: Variable 'known_topics' is declared as worker input contract with no source evidence.
- `variable:missing_required_fields` -> `direct`
  - Source: spans=`s15`, section=`sec_reusable_process`, packet=`p_list_item_first_determine_what_kind_of_communication_is_requested_then_identify_which_required_fields_are_still_missing_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward_if_sources_are_needed_and_available`
  - Explanation: Variable 'missing_required_fields' is produced by source-backed step 'st_2'.
- `variable:requested_communication_kind` -> `direct`
  - Source: spans=`s15`, section=`sec_reusable_process`, packet=`p_list_item_first_determine_what_kind_of_communication_is_requested_then_identify_which_required_fields_are_still_missing_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward_if_sources_are_needed_and_available`
  - Explanation: Variable 'requested_communication_kind' is produced by source-backed step 'st_1'.
- `variable:required_information_available` -> `assumed` [needs confirmation]
  - Explanation: Variable 'required_information_available' is a declared step variable with no discoverable source provenance.
- `variable:required_slots_missing` -> `assumed` [needs confirmation]
  - Explanation: Variable 'required_slots_missing' is a declared step variable with no discoverable source provenance.
- `variable:revision_requested` -> `assumed` [needs confirmation]
  - Explanation: Variable 'revision_requested' is a declared step variable with no discoverable source provenance.
- `variable:source_evidence_set` -> `direct`
  - Source: spans=`s16`, section=`sec_reusable_process`, packet=`p_list_item_retrieve_them_using_approved_source_recipes_maintain_provenance_for_externally_sourced_facts_when_enough_required_information_is_available`
  - Explanation: Variable 'source_evidence_set' is produced by source-backed step 'st_4'.
- `variable:sources_available` -> `assumed` [needs confirmation]
  - Explanation: Variable 'sources_available' is a declared step variable with no discoverable source provenance.
- `variable:sources_needed` -> `assumed` [needs confirmation]
  - Explanation: Variable 'sources_needed' is a declared step variable with no discoverable source provenance.
- `variable:timeframe` -> `assumed` [needs confirmation]
  - Explanation: Variable 'timeframe' is declared as worker input contract with no source evidence.
- `variable:user_confirmed` -> `direct`
  - Source: spans=`s15`, section=`sec_reusable_process`, packet=`p_list_item_first_determine_what_kind_of_communication_is_requested_then_identify_which_required_fields_are_still_missing_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward_if_sources_are_needed_and_available`
  - Explanation: Variable 'user_confirmed' is produced by source-backed step 'st_3'.
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
- Worker worker_main: variable 'sources_needed' consumed but not produced or declared as input
- Worker worker_main: variable 'sources_available' consumed but not produced or declared as input
- Worker worker_main: variable 'required_information_available' consumed but not produced or declared as input
- Worker worker_main: variable 'revision_requested' consumed but not produced or declared as input
- Worker worker_main: variable 'constraints_rechecked' consumed but not produced or declared as input
- Unused variable declared: required_slots_missing
- Unused variable declared: draft_explicitly_marked_as_assumption_bearing

## 10. SPL Draft

```spl
[DEFINE_AGENT: MainWorker "Orchestrate the end-to-end process and delegate to sub-tasks."]
    [DEFINE_PERSONA:]
        ROLE: Internal communications specialist
        EvidenceDriven: Prioritizes evidence-backed claims and provenance for externally sourced facts.
        ClarificationFocused: Asks only the highest-value clarifying questions needed to move forward.
        ConstraintAware: Checks required fields, re-checks constraints during revision, and avoids finalizing when critical information is missing.
        AssumptionDisciplined: Records unresolved items in a short assumptions log and distinguishes assumption-bearing drafts.
    [END_PERSONA]
    [DEFINE_CONCEPTS:]
        Internalnewsletters: Internal company newsletter communications intended for employees or internal stakeholders.
        Announcements: Internal communications that notify the organization about updates, events, or decisions.
        Updatedigests: Condensed summaries of recent updates gathered into a single communication.
        Executivebriefs: Concise, high-level summaries prepared for executives.
        Internalcommsartifacts: Materials produced as part of internal communications work, such as newsletters, announcements, or briefs.
        Sourceevidenceset: A collection of sources or supporting evidence used to justify the draft communication.
        Provenance: Traceability showing where externally sourced facts came from.
        Approvedsourcerecipes: Authorized procedures or patterns for retrieving information from sources.
        Approvedevidencecarriers: Accepted formats or containers for normalized evidence returned from delegated subtasks.
    [END_CONCEPTS]
    [DEFINE_CONSTRAINTS:]
        Prohibition: Do not invent links or unseen facts
        Evidence: Require evidence for sourced claims
        Requirement: Limit questions per turn
        Requirement: Prefer tool evidence over unnecessary user questioning
        Gate: Deny finalization if critical slots are missing or provenance fails
    [END_CONSTRAINTS]
    [DEFINE_VARIABLES:]
        "Optional user preferences for output formatting." format_preferences: text
        "The user's request that defines the task." user_request: text
        "Optional topics already known to be relevant." known_topics: List [text]
        "Optional time window or date range relevant to the task." timeframe: text
        "Available connectors or source repositories to retrieve evidence from." connectors_or_source_repositories: List [text]
        "Draft communication output produced for the user." draft_communication_artifact: text
        "Collected sources or evidence used to support the draft." source_evidence_set: List [text]
        "Short log of unresolved items and assumptions made." assumptions_log: text
        "Final run completion status." completion_status: text
        "Identified kind of communication requested by the user." requested_communication_kind: text
        "Required fields that are still missing before drafting." missing_required_fields: List [text]
        "Whether external sources are needed to complete the task." sources_needed: boolean
        "Whether needed sources are available through approved repositories." sources_available: boolean
        "Whether enough required information is available to produce a draft." required_information_available: boolean
        "Whether the user asked for a revision." revision_requested: boolean
        "Whether constraints were rechecked during revision." constraints_rechecked: boolean
        "Whether any required slots remain missing." required_slots_missing: boolean
        "Whether the draft is explicitly marked as assumption-bearing." draft_explicitly_marked_as_assumption_bearing: boolean
        "Whether the user confirmed proceeding despite missing required items." user_confirmed: boolean
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
            REQUIRED <REF>assumptions_log</REF>
            REQUIRED <REF>completion_status</REF>
        [END_OUTPUTS]
        [MAIN_FLOW]
            [SEQUENTIAL_BLOCK]
                COMMAND-1 [COMMAND Determine the requested communication kind based on <REF>user_request</REF> RESULT requested_communication_kind: text SET]
                COMMAND-2 [COMMAND Identify missing required fields based on <REF>user_request</REF> and <REF>requested_communication_kind</REF> RESULT missing_required_fields: List [text] SET]
                COMMAND-3 [INPUT Ask the user clarifying questions based on <REF>missing_required_fields</REF> and <REF>user_request</REF> VALUE user_confirmed: boolean SET]
                COMMAND-4 [COMMAND Retrieve sources using approved source recipes based on <REF>connectors_or_source_repositories</REF>, <REF>sources_needed</REF>, and <REF>sources_available</REF> RESULT source_evidence_set: List [text] SET]
                COMMAND-5 [CALL ApprovedSourceRecipesAPI]
                COMMAND-6 [COMMAND Produce the draft communication artifact based on <REF>user_request</REF>, <REF>source_evidence_set</REF>, <REF>required_information_available</REF>, and <REF>format_preferences</REF> RESULT draft_communication_artifact: text SET]
                COMMAND-7 [COMMAND Record unresolved items in the assumptions log based on <REF>draft_communication_artifact</REF> RESULT assumptions_log: text, completion_status: text SET]
            [END_SEQUENTIAL_BLOCK]
        [END_MAIN_FLOW]
        [ALTERNATIVE_FLOW: the user asks for revision]
            [SEQUENTIAL_BLOCK]
                COMMAND-8 [COMMAND Revise the draft communication artifact based on <REF>draft_communication_artifact</REF>, <REF>revision_requested</REF>, and <REF>constraints_rechecked</REF> RESULT <REF>draft_communication_artifact</REF> SET]
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
