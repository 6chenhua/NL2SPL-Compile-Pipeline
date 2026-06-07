# NL2SPL Feedback Report

## 1. Overall Compile State

- Completeness: `partial`
- SPL draft generated: `yes`
- Compile diagnostics: `19`
- Assumptions / suggestions: `13`
- Trace records: `52`
- Adapter warnings: `9`
- Validation errors: `0`
- Validation warnings: `3`

Result is partial because the following requirement gaps remain:
- `missing_handler` on `worker:worker_main.exception_flow:exc_adapter_06`: Exception flow 'exc_adapter_06' ('Missing timeframe') has no handler step in worker 'worker_main'.
- `missing_handler` on `worker:worker_main.exception_flow:exc_adapter_07`: Exception flow 'exc_adapter_07' ('conflicting instructions') has no handler step in worker 'worker_main'.
- `missing_handler` on `worker:worker_main.exception_flow:exc_adapter_08`: Exception flow 'exc_adapter_08' ('insufficient source access') has no handler step in worker 'worker_main'.
- `missing_handler` on `worker:worker_main.exception_flow:exc_adapter_09`: Exception flow 'exc_adapter_09' ('evidence shortage') has no handler step in worker 'worker_main'.
- `missing_handler` on `worker:worker_main.exception_flow:exc_adapter_10`: Exception flow 'exc_adapter_10' ('user refusal to answer') has no handler step in worker 'worker_main'.
- `missing_handler` on `worker:worker_main.exception_flow:exc_adapter_11`: Exception flow 'exc_adapter_11' ('provenance failure') has no handler step in worker 'worker_main'.
- `missing_output_producer` on `worker:worker_main.output:assumptions_log`: Required output 'assumptions_log' (A short assumptions log for any unresolved items) has no source-backed producer step.
- `missing_output_producer` on `worker:worker_main.output:completion_status`: Required output 'completion_status' (A completion status) has no source-backed producer step.
- `type_or_contract_ambiguity` on `delegation_intent:s30`: Delegation intent 'Optional delegated subtasks such as source gathering or template matching may be' lacks a valid worker/API handoff contract.  No INVOKE_WORKER or CALL_API will be generated from this span.  [sec_delegation_policy/p_sentence_delegated_subtasks_such_as_source_gathering_or_template_matching_may_be_used_if_bounded_and_the_returned_evidence_is_normalized_into_approved_evidence_carriers]

## 2. Materialized Source-Backed Structure

### Workers
- `worker:MainWorker` (direct) -- spans=s15, s17, s18, s24, s25, s26, s27, s28, s29, s30; section=sec_reusable_process; packet=p_list_item_first_determine_what_kind_of_communication_is_requested_then_identify_which_required_fields_are_still_missing_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward_if_sources_are_needed_and_available
- `worker:Worker_source_retrieval` (direct) -- spans=s16; section=sec_reusable_process; packet=p_list_item_retrieve_them_using_approved_source_recipes_maintain_provenance_for_externally_sourced_facts_when_enough_required_information_is_available
- `worker:source_retrieval.variable:assumptions_log` (normalized) -- section=sec_required_outputs
- `worker:source_retrieval.variable:assumptions_log` (normalized) -- section=sec_required_outputs
- `worker:source_retrieval.variable:completion_status` (normalized) -- section=sec_required_outputs
- `worker:source_retrieval.variable:completion_status` (normalized) -- section=sec_required_outputs
- `worker:source_retrieval.variable:connectors_or_source_repositories` (normalized) -- section=sec_inputs_for_each_run
- `worker:source_retrieval.variable:connectors_or_source_repositories` (normalized) -- section=sec_inputs_for_each_run
- `worker:source_retrieval.variable:draft_communication_artifact` (direct) -- spans=s17; section=sec_reusable_process; packet=p_list_item_produce_a_draft_if_the_user_asks_for_revision
- `worker:source_retrieval.variable:draft_communication_artifact` (direct) -- spans=s17; section=sec_reusable_process; packet=p_list_item_produce_a_draft_if_the_user_asks_for_revision
- `worker:source_retrieval.variable:format_preferences` (normalized) -- section=sec_inputs_for_each_run
- `worker:source_retrieval.variable:format_preferences` (normalized) -- section=sec_inputs_for_each_run
- `worker:source_retrieval.variable:known_topics` (normalized) -- section=sec_inputs_for_each_run
- `worker:source_retrieval.variable:known_topics` (normalized) -- section=sec_inputs_for_each_run
- `worker:source_retrieval.variable:source_evidence_set` (direct) -- spans=s15; section=sec_reusable_process; packet=p_list_item_first_determine_what_kind_of_communication_is_requested_then_identify_which_required_fields_are_still_missing_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward_if_sources_are_needed_and_available
- `worker:source_retrieval.variable:source_evidence_set` (direct) -- spans=s15; section=sec_reusable_process; packet=p_list_item_first_determine_what_kind_of_communication_is_requested_then_identify_which_required_fields_are_still_missing_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward_if_sources_are_needed_and_available
- `worker:source_retrieval.variable:timeframe` (normalized) -- section=sec_inputs_for_each_run
- `worker:source_retrieval.variable:timeframe` (normalized) -- section=sec_inputs_for_each_run
- `worker:source_retrieval.variable:user_request` (normalized) -- section=sec_inputs_for_each_run
- `worker:source_retrieval.variable:user_request` (normalized) -- section=sec_inputs_for_each_run

### Flows
- `flow:alt_1` (direct) -- spans=s18; section=sec_reusable_process; packet=p_list_item_revise_while_rechecking_constraints_do_not_finalize_if_required_slots_remain_missing_unless_the_draft_is_explicitly_marked_as_assumption_bearing_and_the_user_confirms
- `flow:exc_adapter_06` (direct) -- spans=s24; section=sec_failure_handling; packet=p_list_item_missing_timeframe
- `flow:exc_adapter_07` (direct) -- spans=s25; section=sec_failure_handling; packet=p_list_item_conflicting_instructions
- `flow:exc_adapter_08` (direct) -- spans=s26; section=sec_failure_handling; packet=p_list_item_insufficient_source_access
- `flow:exc_adapter_09` (direct) -- spans=s27; section=sec_failure_handling; packet=p_list_item_evidence_shortage
- `flow:exc_adapter_10` (direct) -- spans=s28; section=sec_failure_handling; packet=p_list_item_user_refusal_to_answer
- `flow:exc_adapter_11` (direct) -- spans=s29; section=sec_failure_handling; packet=p_list_item_provenance_failure
- `flow:main` (direct) -- spans=s15, s17; section=sec_reusable_process; packet=p_list_item_first_determine_what_kind_of_communication_is_requested_then_identify_which_required_fields_are_still_missing_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward_if_sources_are_needed_and_available

### Steps
- `step:st_1` (direct) -- spans=s15; section=sec_reusable_process; packet=p_list_item_first_determine_what_kind_of_communication_is_requested_then_identify_which_required_fields_are_still_missing_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward_if_sources_are_needed_and_available
- `step:st_1` (direct) -- spans=s16; section=sec_reusable_process; packet=p_list_item_retrieve_them_using_approved_source_recipes_maintain_provenance_for_externally_sourced_facts_when_enough_required_information_is_available
- `step:st_2` (direct) -- spans=s15; section=sec_reusable_process; packet=p_list_item_first_determine_what_kind_of_communication_is_requested_then_identify_which_required_fields_are_still_missing_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward_if_sources_are_needed_and_available
- `step:st_3` (direct) -- spans=s15; section=sec_reusable_process; packet=p_list_item_first_determine_what_kind_of_communication_is_requested_then_identify_which_required_fields_are_still_missing_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward_if_sources_are_needed_and_available
- `step:st_4` (direct) -- spans=s17; section=sec_reusable_process; packet=p_list_item_produce_a_draft_if_the_user_asks_for_revision
- `step:st_5` (direct) -- spans=s18; section=sec_reusable_process; packet=p_list_item_revise_while_rechecking_constraints_do_not_finalize_if_required_slots_remain_missing_unless_the_draft_is_explicitly_marked_as_assumption_bearing_and_the_user_confirms
- `step:st_invoke_handoff_source_retrieval` (direct) -- spans=s15; section=sec_reusable_process; packet=p_list_item_first_determine_what_kind_of_communication_is_requested_then_identify_which_required_fields_are_still_missing_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward_if_sources_are_needed_and_available

### Constraints
- `constraint:c_1` (direct) -- spans=s19; section=sec_policies; packet=p_sentence_do_not_invent_links_or_unseen_facts
- `constraint:c_2` (direct) -- spans=s20; section=sec_policies; packet=p_sentence_require_evidence_for_sourced_claims
- `constraint:c_3` (direct) -- spans=s21; section=sec_policies; packet=p_sentence_limit_questions_per_turn
- `constraint:c_4` (direct) -- spans=s22; section=sec_policies; packet=p_sentence_prefer_tool_evidence_over_unnecessary_user_questioning
- `constraint:c_5` (direct) -- spans=s23; section=sec_policies; packet=p_sentence_deny_finalization_if_critical_slots_are_missing_or_provenance_fails

### Handoffs
- `handoff:handoff_source_retrieval` (direct) -- spans=s15, s17; section=sec_reusable_process; packet=p_list_item_first_determine_what_kind_of_communication_is_requested_then_identify_which_required_fields_are_still_missing_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward_if_sources_are_needed_and_available

### Delegation Intents
- `delegation_intent:delegated_subtasks` (inferred) -- spans=s30; section=sec_delegation_policy; packet=p_sentence_delegated_subtasks_such_as_source_gathering_or_template_matching_may_be_used_if_bounded_and_the_returned_evidence_is_normalized_into_approved_evidence_carriers

### Other
- `profile:concept_0` (normalized)
- `profile:concept_1` (normalized)
- `profile:concept_2` (normalized)
- `profile:concept_3` (normalized)
- `profile:concept_4` (normalized)
- `profile:persona` (inferred)

## 3. Not Materialized / Kept Partial

- `worker:worker_main.exception_flow:exc_adapter_06`: `missing_handler` -- Exception flow 'exc_adapter_06' ('Missing timeframe') has no handler step in worker 'worker_main'.
  - Suggested resolution: Add a handler step for 'Missing timeframe', or mark this exception as acknowledged without handling.
- `worker:worker_main.exception_flow:exc_adapter_07`: `missing_handler` -- Exception flow 'exc_adapter_07' ('conflicting instructions') has no handler step in worker 'worker_main'.
  - Suggested resolution: Add a handler step for 'conflicting instructions', or mark this exception as acknowledged without handling.
- `worker:worker_main.exception_flow:exc_adapter_08`: `missing_handler` -- Exception flow 'exc_adapter_08' ('insufficient source access') has no handler step in worker 'worker_main'.
  - Suggested resolution: Add a handler step for 'insufficient source access', or mark this exception as acknowledged without handling.
- `worker:worker_main.exception_flow:exc_adapter_09`: `missing_handler` -- Exception flow 'exc_adapter_09' ('evidence shortage') has no handler step in worker 'worker_main'.
  - Suggested resolution: Add a handler step for 'evidence shortage', or mark this exception as acknowledged without handling.
- `worker:worker_main.exception_flow:exc_adapter_10`: `missing_handler` -- Exception flow 'exc_adapter_10' ('user refusal to answer') has no handler step in worker 'worker_main'.
  - Suggested resolution: Add a handler step for 'user refusal to answer', or mark this exception as acknowledged without handling.
- `worker:worker_main.exception_flow:exc_adapter_11`: `missing_handler` -- Exception flow 'exc_adapter_11' ('provenance failure') has no handler step in worker 'worker_main'.
  - Suggested resolution: Add a handler step for 'provenance failure', or mark this exception as acknowledged without handling.
- `worker:worker_main.output:assumptions_log`: `missing_output_producer` -- Required output 'assumptions_log' (A short assumptions log for any unresolved items) has no source-backed producer step.
  - Suggested resolution: Add a step that produces 'assumptions_log', e.g. 'Record assumptions for unresolved items'. If the source requirement does not specify how to produce this output, mark it as optional or remove it from the output contract.
- `worker:worker_main.output:completion_status`: `missing_output_producer` -- Required output 'completion_status' (A completion status) has no source-backed producer step.
  - Suggested resolution: Add a step that produces 'completion_status', e.g. 'Set completion status for the normal completion path'. If the source requirement does not specify how to produce this output, mark it as optional or remove it from the output contract.
- `delegation_intent:s30`: `type_or_contract_ambiguity` -- Delegation intent 'Optional delegated subtasks such as source gathering or template matching may be' lacks a valid worker/API handoff contract.  No INVOKE_WORKER or CALL_API will be generated from this span.  [sec_delegation_policy/p_sentence_delegated_subtasks_such_as_source_gathering_or_template_matching_may_be_used_if_bounded_and_the_returned_evidence_is_normalized_into_approved_evidence_carriers]

## 4. Diagnostics

### diag_post_norm_0000: `missing_handler`
- Severity: `warning`
- Target: `worker:worker_main.exception_flow:exc_adapter_06`
- Source spans: `s24`
- Message: Exception flow 'exc_adapter_06' ('Missing timeframe') has no handler step in worker 'worker_main'.
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Add a handler step for 'Missing timeframe', or mark this exception as acknowledged without handling.

### diag_post_norm_0001: `missing_handler`
- Severity: `warning`
- Target: `worker:worker_main.exception_flow:exc_adapter_07`
- Source spans: `s25`
- Message: Exception flow 'exc_adapter_07' ('conflicting instructions') has no handler step in worker 'worker_main'.
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Add a handler step for 'conflicting instructions', or mark this exception as acknowledged without handling.

### diag_post_norm_0002: `missing_handler`
- Severity: `warning`
- Target: `worker:worker_main.exception_flow:exc_adapter_08`
- Source spans: `s26`
- Message: Exception flow 'exc_adapter_08' ('insufficient source access') has no handler step in worker 'worker_main'.
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Add a handler step for 'insufficient source access', or mark this exception as acknowledged without handling.

### diag_post_norm_0003: `missing_handler`
- Severity: `warning`
- Target: `worker:worker_main.exception_flow:exc_adapter_09`
- Source spans: `s27`
- Message: Exception flow 'exc_adapter_09' ('evidence shortage') has no handler step in worker 'worker_main'.
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Add a handler step for 'evidence shortage', or mark this exception as acknowledged without handling.

### diag_post_norm_0004: `missing_handler`
- Severity: `warning`
- Target: `worker:worker_main.exception_flow:exc_adapter_10`
- Source spans: `s28`
- Message: Exception flow 'exc_adapter_10' ('user refusal to answer') has no handler step in worker 'worker_main'.
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Add a handler step for 'user refusal to answer', or mark this exception as acknowledged without handling.

### diag_post_norm_0005: `missing_handler`
- Severity: `warning`
- Target: `worker:worker_main.exception_flow:exc_adapter_11`
- Source spans: `s29`
- Message: Exception flow 'exc_adapter_11' ('provenance failure') has no handler step in worker 'worker_main'.
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Add a handler step for 'provenance failure', or mark this exception as acknowledged without handling.

### diag_post_norm_0006: `missing_output_producer`
- Severity: `warning`
- Target: `worker:worker_main.output:assumptions_log`
- Message: Required output 'assumptions_log' (A short assumptions log for any unresolved items) has no source-backed producer step.
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Add a step that produces 'assumptions_log', e.g. 'Record assumptions for unresolved items'. If the source requirement does not specify how to produce this output, mark it as optional or remove it from the output contract.

### diag_post_norm_0007: `missing_output_producer`
- Severity: `warning`
- Target: `worker:worker_main.output:completion_status`
- Message: Required output 'completion_status' (A completion status) has no source-backed producer step.
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Add a step that produces 'completion_status', e.g. 'Set completion status for the normal completion path'. If the source requirement does not specify how to produce this output, mark it as optional or remove it from the output contract.

### diag_d10_0000: `type_or_contract_ambiguity`
- Severity: `warning`
- Target: `delegation_intent:s30`
- Source spans: `s30`
- Message: Delegation intent 'Optional delegated subtasks such as source gathering or template matching may be' lacks a valid worker/API handoff contract.  No INVOKE_WORKER or CALL_API will be generated from this span.  [sec_delegation_policy/p_sentence_delegated_subtasks_such_as_source_gathering_or_template_matching_may_be_used_if_bounded_and_the_returned_evidence_is_normalized_into_approved_evidence_carriers]
- Blocks rendering: `false`
- Blocks completion: `true`

### diag_prov_0000: `missing_provenance`
- Severity: `warning`
- Target: `worker:source_retrieval.variable:sources_needed`
- Message: Variable 'sources_needed' (boolean) has no source-backed producer and no contract section evidence.
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_prov_0001: `missing_provenance`
- Severity: `warning`
- Target: `worker:source_retrieval.variable:sources_available`
- Message: Variable 'sources_available' (boolean) has no source-backed producer and no contract section evidence.
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_prov_0002: `missing_provenance`
- Severity: `warning`
- Target: `worker:source_retrieval.variable:sources_needed`
- Message: Variable 'sources_needed' (boolean) has no source-backed producer and no contract section evidence.
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_prov_0003: `missing_provenance`
- Severity: `warning`
- Target: `worker:source_retrieval.variable:sources_available`
- Message: Variable 'sources_available' (boolean) has no source-backed producer and no contract section evidence.
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_rf_000: `route_refinement_diagnostic`
- Severity: `warning`
- Target: `stage2:field_route:`
- Message: LLM route diagnostic [prior_override] span='s1': Adjusted semantic role to profile_domain for internal newsletters.
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_rf_001: `route_refinement_diagnostic`
- Severity: `warning`
- Target: `stage2:field_route:`
- Message: LLM route diagnostic [prior_override] span='s2': Adjusted semantic role to profile_domain for announcements.
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_rf_002: `route_refinement_diagnostic`
- Severity: `warning`
- Target: `stage2:field_route:`
- Message: LLM route diagnostic [prior_override] span='s3': Adjusted semantic role to profile_domain for update digests.
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_rf_003: `route_refinement_diagnostic`
- Severity: `warning`
- Target: `stage2:field_route:`
- Message: LLM route diagnostic [prior_override] span='s4': Adjusted semantic role to profile_domain for executive briefs.
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_rf_004: `route_refinement_diagnostic`
- Severity: `warning`
- Target: `stage2:field_route:`
- Message: LLM route diagnostic [prior_override] span='s5': Adjusted semantic role to profile_domain for related internal-comms artifacts.
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_rf_005: `route_refinement_diagnostic`
- Severity: `warning`
- Target: `stage2:field_route:`
- Message: LLM route diagnostic [prior_override] span='s30': Adjusted semantic role to delegation_boundary_constraint for optional delegated subtasks.
- Blocks rendering: `false`
- Blocks completion: `false`

## 5. Assumptions / Suggestions

- `ASM_0000` for `worker:worker_main.exception_flow:exc_adapter_06`: Exception flow has no handler action. The compiler suggests specifying what should happen when this failure occurs.
  - Reason: Source describes a failure condition but does not specify how to handle it.  The exception flow is preserved in SPL, but no handler command was rendered. (Exception flow 'exc_adapter_06' ('Missing timeframe') has no handler step in worker 'worker_main'.)
  - Suggested resolution: Specify the handler action for worker:worker_main.exception_flow:exc_adapter_06: e.g. ask the user for missing information, block finalization, or continue with an explicit assumption.
  - Related diagnostic: `diag_post_norm_0000`
- `ASM_0001` for `worker:worker_main.exception_flow:exc_adapter_07`: Exception flow has no handler action. The compiler suggests specifying what should happen when this failure occurs.
  - Reason: Source describes a failure condition but does not specify how to handle it.  The exception flow is preserved in SPL, but no handler command was rendered. (Exception flow 'exc_adapter_07' ('conflicting instructions') has no handler step in worker 'worker_main'.)
  - Suggested resolution: Specify the handler action for worker:worker_main.exception_flow:exc_adapter_07: e.g. ask the user for missing information, block finalization, or continue with an explicit assumption.
  - Related diagnostic: `diag_post_norm_0001`
- `ASM_0002` for `worker:worker_main.exception_flow:exc_adapter_08`: Exception flow has no handler action. The compiler suggests specifying what should happen when this failure occurs.
  - Reason: Source describes a failure condition but does not specify how to handle it.  The exception flow is preserved in SPL, but no handler command was rendered. (Exception flow 'exc_adapter_08' ('insufficient source access') has no handler step in worker 'worker_main'.)
  - Suggested resolution: Specify the handler action for worker:worker_main.exception_flow:exc_adapter_08: e.g. ask the user for missing information, block finalization, or continue with an explicit assumption.
  - Related diagnostic: `diag_post_norm_0002`
- `ASM_0003` for `worker:worker_main.exception_flow:exc_adapter_09`: Exception flow has no handler action. The compiler suggests specifying what should happen when this failure occurs.
  - Reason: Source describes a failure condition but does not specify how to handle it.  The exception flow is preserved in SPL, but no handler command was rendered. (Exception flow 'exc_adapter_09' ('evidence shortage') has no handler step in worker 'worker_main'.)
  - Suggested resolution: Specify the handler action for worker:worker_main.exception_flow:exc_adapter_09: e.g. ask the user for missing information, block finalization, or continue with an explicit assumption.
  - Related diagnostic: `diag_post_norm_0003`
- `ASM_0004` for `worker:worker_main.exception_flow:exc_adapter_10`: Exception flow has no handler action. The compiler suggests specifying what should happen when this failure occurs.
  - Reason: Source describes a failure condition but does not specify how to handle it.  The exception flow is preserved in SPL, but no handler command was rendered. (Exception flow 'exc_adapter_10' ('user refusal to answer') has no handler step in worker 'worker_main'.)
  - Suggested resolution: Specify the handler action for worker:worker_main.exception_flow:exc_adapter_10: e.g. ask the user for missing information, block finalization, or continue with an explicit assumption.
  - Related diagnostic: `diag_post_norm_0004`
- `ASM_0005` for `worker:worker_main.exception_flow:exc_adapter_11`: Exception flow has no handler action. The compiler suggests specifying what should happen when this failure occurs.
  - Reason: Source describes a failure condition but does not specify how to handle it.  The exception flow is preserved in SPL, but no handler command was rendered. (Exception flow 'exc_adapter_11' ('provenance failure') has no handler step in worker 'worker_main'.)
  - Suggested resolution: Specify the handler action for worker:worker_main.exception_flow:exc_adapter_11: e.g. ask the user for missing information, block finalization, or continue with an explicit assumption.
  - Related diagnostic: `diag_post_norm_0005`
- `ASM_0006` for `worker:worker_main.output:assumptions_log`: Required output has no source-backed producer. The compiler suggests adding a step that explicitly produces this output.
  - Reason: The source requires this output but does not describe how it should be produced.  The output is kept in the OUTPUTS contract, but no producer step was rendered.
  - Suggested resolution: Add a source-backed step that produces worker:worker_main.output:assumptions_log. If the source does not specify how to produce it, mark it as optional or remove it from the required output contract.
  - Related diagnostic: `diag_post_norm_0006`
- `ASM_0007` for `worker:worker_main.output:completion_status`: Required output has no source-backed producer. The compiler suggests adding a step that explicitly produces this output.
  - Reason: The source requires this output but does not describe how it should be produced.  The output is kept in the OUTPUTS contract, but no producer step was rendered.
  - Suggested resolution: Add a source-backed step that produces worker:worker_main.output:completion_status. If the source does not specify how to produce it, mark it as optional or remove it from the required output contract.
  - Related diagnostic: `diag_post_norm_0007`
- `ASM_0008` for `worker:source_retrieval.variable:sources_needed`: Variable has no discoverable source provenance.
  - Reason: The compiler could not trace this variable back to a source span, adapter hard fact, or producer step.  Its origin is assumed.
  - Suggested resolution: For worker:source_retrieval.variable:sources_needed: add source evidence (a span, adapter hint, or producer step) that justifies this variable's existence.
  - Related diagnostic: `diag_prov_0000`
- `ASM_0009` for `worker:source_retrieval.variable:sources_available`: Variable has no discoverable source provenance.
  - Reason: The compiler could not trace this variable back to a source span, adapter hard fact, or producer step.  Its origin is assumed.
  - Suggested resolution: For worker:source_retrieval.variable:sources_available: add source evidence (a span, adapter hint, or producer step) that justifies this variable's existence.
  - Related diagnostic: `diag_prov_0001`
- `ASM_0010` for `worker:source_retrieval.variable:sources_needed`: Variable has no discoverable source provenance.
  - Reason: The compiler could not trace this variable back to a source span, adapter hard fact, or producer step.  Its origin is assumed.
  - Suggested resolution: For worker:source_retrieval.variable:sources_needed: add source evidence (a span, adapter hint, or producer step) that justifies this variable's existence.
  - Related diagnostic: `diag_prov_0002`
- `ASM_0011` for `worker:source_retrieval.variable:sources_available`: Variable has no discoverable source provenance.
  - Reason: The compiler could not trace this variable back to a source span, adapter hard fact, or producer step.  Its origin is assumed.
  - Suggested resolution: For worker:source_retrieval.variable:sources_available: add source evidence (a span, adapter hint, or producer step) that justifies this variable's existence.
  - Related diagnostic: `diag_prov_0003`
- `ASM_0012` for `delegation_intent:s30`: Command has an ambiguous or incomplete contract. The compiler suggests providing the missing contract detail.
  - Reason: A command references an API, worker, or input source that is not fully specified.  The compiler cannot materialize the command without this information.
  - Suggested resolution: For delegation_intent:s30: provide the missing contract detail (API name, worker target, IO bindings, or source evidence).  See the related diagnostic for specifics.
  - Related diagnostic: `diag_d10_0000`

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
- `delegation_intent:delegated_subtasks` -> `inferred`
  - Source: spans=`s30`, section=`sec_delegation_policy`, packet=`p_sentence_delegated_subtasks_such_as_source_gathering_or_template_matching_may_be_used_if_bounded_and_the_returned_evidence_is_normalized_into_approved_evidence_carriers`
  - Explanation: Delegation intent 'delegated_subtasks': Optional delegated subtasks such as source gathering or template matching may be used if bounded and the returned eviden
- `flow:alt_1` -> `direct`
  - Source: spans=`s18`, section=`sec_reusable_process`, packet=`p_list_item_revise_while_rechecking_constraints_do_not_finalize_if_required_slots_remain_missing_unless_the_draft_is_explicitly_marked_as_assumption_bearing_and_the_user_confirms`
  - Explanation: Alternative flow 'alt_1': the user asks for revision
- `flow:exc_adapter_06` -> `direct`
  - Source: spans=`s24`, section=`sec_failure_handling`, packet=`p_list_item_missing_timeframe`
  - Explanation: Exception flow 'exc_adapter_06': Missing timeframe
- `flow:exc_adapter_07` -> `direct`
  - Source: spans=`s25`, section=`sec_failure_handling`, packet=`p_list_item_conflicting_instructions`
  - Explanation: Exception flow 'exc_adapter_07': conflicting instructions
- `flow:exc_adapter_08` -> `direct`
  - Source: spans=`s26`, section=`sec_failure_handling`, packet=`p_list_item_insufficient_source_access`
  - Explanation: Exception flow 'exc_adapter_08': insufficient source access
- `flow:exc_adapter_09` -> `direct`
  - Source: spans=`s27`, section=`sec_failure_handling`, packet=`p_list_item_evidence_shortage`
  - Explanation: Exception flow 'exc_adapter_09': evidence shortage
- `flow:exc_adapter_10` -> `direct`
  - Source: spans=`s28`, section=`sec_failure_handling`, packet=`p_list_item_user_refusal_to_answer`
  - Explanation: Exception flow 'exc_adapter_10': user refusal to answer
- `flow:exc_adapter_11` -> `direct`
  - Source: spans=`s29`, section=`sec_failure_handling`, packet=`p_list_item_provenance_failure`
  - Explanation: Exception flow 'exc_adapter_11': provenance failure
- `flow:main` -> `direct`
  - Source: spans=`s15, s17`, section=`sec_reusable_process`, packet=`p_list_item_first_determine_what_kind_of_communication_is_requested_then_identify_which_required_fields_are_still_missing_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward_if_sources_are_needed_and_available`
  - Explanation: Main flow with 2 block(s).
- `handoff:handoff_source_retrieval` -> `direct`
  - Source: spans=`s15, s17`, section=`sec_reusable_process`, packet=`p_list_item_first_determine_what_kind_of_communication_is_requested_then_identify_which_required_fields_are_still_missing_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward_if_sources_are_needed_and_available`
  - Explanation: Handoff 'handoff_source_retrieval' (worker_main invoke to source_retrieval) with 1 input(s) and 1 output(s).
- `profile:concept_0` -> `normalized`
  - Explanation: Concept: Internal newsletters -- Regular publications distributed within an organization to communicate news and updates to employees.
- `profile:concept_1` -> `normalized`
  - Explanation: Concept: Announcements -- Official statements or communications made to inform a group about important events or changes.
- `profile:concept_2` -> `normalized`
  - Explanation: Concept: Update digests -- Summarized collections of recent updates or changes, typically distributed periodically.
- `profile:concept_3` -> `normalized`
  - Explanation: Concept: Executive briefs -- Concise reports or summaries prepared for executives, highlighting key information and insights.
- `profile:concept_4` -> `normalized`
  - Explanation: Concept: Related internal-comms artifacts -- Documents or materials used in internal communications to support or enhance messaging within an organization.
- `profile:persona` -> `inferred`
  - Explanation: Persona: Internal communications specialist
- `step:st_1` -> `direct`
  - Source: spans=`s15`, section=`sec_reusable_process`, packet=`p_list_item_first_determine_what_kind_of_communication_is_requested_then_identify_which_required_fields_are_still_missing_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward_if_sources_are_needed_and_available`
  - Explanation: Step 'st_1' maps to source span(s).
- `step:st_1` -> `direct`
  - Source: spans=`s16`, section=`sec_reusable_process`, packet=`p_list_item_retrieve_them_using_approved_source_recipes_maintain_provenance_for_externally_sourced_facts_when_enough_required_information_is_available`
  - Explanation: Step 'st_1' maps to source span(s).
- `step:st_2` -> `direct`
  - Source: spans=`s15`, section=`sec_reusable_process`, packet=`p_list_item_first_determine_what_kind_of_communication_is_requested_then_identify_which_required_fields_are_still_missing_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward_if_sources_are_needed_and_available`
  - Explanation: Step 'st_2' maps to source span(s).
- `step:st_3` -> `direct`
  - Source: spans=`s15`, section=`sec_reusable_process`, packet=`p_list_item_first_determine_what_kind_of_communication_is_requested_then_identify_which_required_fields_are_still_missing_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward_if_sources_are_needed_and_available`
  - Explanation: Step 'st_3' maps to source span(s).
- `step:st_4` -> `direct`
  - Source: spans=`s17`, section=`sec_reusable_process`, packet=`p_list_item_produce_a_draft_if_the_user_asks_for_revision`
  - Explanation: Step 'st_4' maps to source span(s).
- `step:st_5` -> `direct`
  - Source: spans=`s18`, section=`sec_reusable_process`, packet=`p_list_item_revise_while_rechecking_constraints_do_not_finalize_if_required_slots_remain_missing_unless_the_draft_is_explicitly_marked_as_assumption_bearing_and_the_user_confirms`
  - Explanation: Step 'st_5' maps to source span(s).
- `step:st_invoke_handoff_source_retrieval` -> `direct`
  - Source: spans=`s15`, section=`sec_reusable_process`, packet=`p_list_item_first_determine_what_kind_of_communication_is_requested_then_identify_which_required_fields_are_still_missing_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward_if_sources_are_needed_and_available`
  - Explanation: Step 'st_invoke_handoff_source_retrieval' maps to source span(s).
- `worker:MainWorker` -> `direct`
  - Source: spans=`s15, s17, s18, s24, s25, s26, s27, s28, s29, s30`, section=`sec_reusable_process`, packet=`p_list_item_first_determine_what_kind_of_communication_is_requested_then_identify_which_required_fields_are_still_missing_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward_if_sources_are_needed_and_available`
  - Explanation: Main worker 'MainWorker' assembled from flow and step IRs.
- `worker:Worker_source_retrieval` -> `direct`
  - Source: spans=`s16`, section=`sec_reusable_process`, packet=`p_list_item_retrieve_them_using_approved_source_recipes_maintain_provenance_for_externally_sourced_facts_when_enough_required_information_is_available`
  - Explanation: Child worker 'Worker_source_retrieval' extracted from delegation pattern.
- `worker:source_retrieval.variable:assumptions_log` -> `normalized`
  - Source: section=`sec_required_outputs`
  - Explanation: Variable 'assumptions_log' is declared by adapter hard fact in section 'sec_required_outputs'.
- `worker:source_retrieval.variable:assumptions_log` -> `normalized`
  - Source: section=`sec_required_outputs`
  - Explanation: Variable 'assumptions_log' is declared by adapter hard fact in section 'sec_required_outputs'.
- `worker:source_retrieval.variable:completion_status` -> `normalized`
  - Source: section=`sec_required_outputs`
  - Explanation: Variable 'completion_status' is declared by adapter hard fact in section 'sec_required_outputs'.
- `worker:source_retrieval.variable:completion_status` -> `normalized`
  - Source: section=`sec_required_outputs`
  - Explanation: Variable 'completion_status' is declared by adapter hard fact in section 'sec_required_outputs'.
- `worker:source_retrieval.variable:connectors_or_source_repositories` -> `normalized`
  - Source: section=`sec_inputs_for_each_run`
  - Explanation: Variable 'connectors_or_source_repositories' is declared by adapter hard fact in section 'sec_inputs_for_each_run'.
- `worker:source_retrieval.variable:connectors_or_source_repositories` -> `normalized`
  - Source: section=`sec_inputs_for_each_run`
  - Explanation: Variable 'connectors_or_source_repositories' is declared by adapter hard fact in section 'sec_inputs_for_each_run'.
- `worker:source_retrieval.variable:draft_communication_artifact` -> `direct`
  - Source: spans=`s17`, section=`sec_reusable_process`, packet=`p_list_item_produce_a_draft_if_the_user_asks_for_revision`
  - Explanation: Variable 'draft_communication_artifact' is produced by source-backed step 'st_4'.
- `worker:source_retrieval.variable:draft_communication_artifact` -> `direct`
  - Source: spans=`s17`, section=`sec_reusable_process`, packet=`p_list_item_produce_a_draft_if_the_user_asks_for_revision`
  - Explanation: Variable 'draft_communication_artifact' is produced by source-backed step 'st_4'.
- `worker:source_retrieval.variable:format_preferences` -> `normalized`
  - Source: section=`sec_inputs_for_each_run`
  - Explanation: Variable 'format_preferences' is declared by adapter hard fact in section 'sec_inputs_for_each_run'.
- `worker:source_retrieval.variable:format_preferences` -> `normalized`
  - Source: section=`sec_inputs_for_each_run`
  - Explanation: Variable 'format_preferences' is declared by adapter hard fact in section 'sec_inputs_for_each_run'.
- `worker:source_retrieval.variable:known_topics` -> `normalized`
  - Source: section=`sec_inputs_for_each_run`
  - Explanation: Variable 'known_topics' is declared by adapter hard fact in section 'sec_inputs_for_each_run'.
- `worker:source_retrieval.variable:known_topics` -> `normalized`
  - Source: section=`sec_inputs_for_each_run`
  - Explanation: Variable 'known_topics' is declared by adapter hard fact in section 'sec_inputs_for_each_run'.
- `worker:source_retrieval.variable:source_evidence_set` -> `direct`
  - Source: spans=`s15`, section=`sec_reusable_process`, packet=`p_list_item_first_determine_what_kind_of_communication_is_requested_then_identify_which_required_fields_are_still_missing_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward_if_sources_are_needed_and_available`
  - Explanation: Variable 'source_evidence_set' is produced by source-backed step 'st_invoke_handoff_source_retrieval'.
- `worker:source_retrieval.variable:source_evidence_set` -> `direct`
  - Source: spans=`s15`, section=`sec_reusable_process`, packet=`p_list_item_first_determine_what_kind_of_communication_is_requested_then_identify_which_required_fields_are_still_missing_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward_if_sources_are_needed_and_available`
  - Explanation: Variable 'source_evidence_set' is produced by source-backed step 'st_invoke_handoff_source_retrieval'.
- `worker:source_retrieval.variable:sources_available` -> `assumed` [needs confirmation]
  - Explanation: Variable 'sources_available' is a declared step variable with no discoverable source provenance.
- `worker:source_retrieval.variable:sources_available` -> `assumed` [needs confirmation]
  - Explanation: Variable 'sources_available' is a declared step variable with no discoverable source provenance.
- `worker:source_retrieval.variable:sources_needed` -> `assumed` [needs confirmation]
  - Explanation: Variable 'sources_needed' is a declared step variable with no discoverable source provenance.
- `worker:source_retrieval.variable:sources_needed` -> `assumed` [needs confirmation]
  - Explanation: Variable 'sources_needed' is a declared step variable with no discoverable source provenance.
- `worker:source_retrieval.variable:timeframe` -> `normalized`
  - Source: section=`sec_inputs_for_each_run`
  - Explanation: Variable 'timeframe' is declared by adapter hard fact in section 'sec_inputs_for_each_run'.
- `worker:source_retrieval.variable:timeframe` -> `normalized`
  - Source: section=`sec_inputs_for_each_run`
  - Explanation: Variable 'timeframe' is declared by adapter hard fact in section 'sec_inputs_for_each_run'.
- `worker:source_retrieval.variable:user_request` -> `normalized`
  - Source: section=`sec_inputs_for_each_run`
  - Explanation: Variable 'user_request' is declared by adapter hard fact in section 'sec_inputs_for_each_run'.
- `worker:source_retrieval.variable:user_request` -> `normalized`
  - Source: section=`sec_inputs_for_each_run`
  - Explanation: Variable 'user_request' is declared by adapter hard fact in section 'sec_inputs_for_each_run'.

## 7. Anti-Fabrication Checks

- `missing_handler`: Exception conditions without handler action stay as partial exception flows; no handler command is invented.
- `missing_output_producer`: Required outputs without a source-backed producer stay in the contract; no synthetic producer command is invented.
- `type_or_contract_ambiguity`: Unresolved worker/API contracts are reported as ambiguity; they are not downgraded to generic commands.

## 8. Adapter / Validation Notes

Adapter warnings:
- LLM_DUPLICATE_FACT: LLM input fact 'user_request' duplicates deterministic fact -- rejected.
- LLM_DUPLICATE_FACT: LLM input fact 'known_topics' duplicates deterministic fact -- rejected.
- LLM_DUPLICATE_FACT: LLM input fact 'timeframe' duplicates deterministic fact -- rejected.
- LLM_DUPLICATE_FACT: LLM input fact 'connectors_or_source_repositories' duplicates deterministic fact -- rejected.
- LLM_DUPLICATE_FACT: LLM input fact 'format_preferences' duplicates deterministic fact -- rejected.
- LLM_DUPLICATE_FACT: LLM output fact 'draft_communication_artifact' duplicates deterministic fact -- rejected.
- LLM_DUPLICATE_FACT: LLM output fact 'source_evidence_set' duplicates deterministic fact -- rejected.
- LLM_DUPLICATE_FACT: LLM output fact 'assumptions_log' duplicates deterministic fact -- rejected.
- LLM_DUPLICATE_FACT: LLM output fact 'completion_status' duplicates deterministic fact -- rejected.

Validation warnings:
- Worker worker_main: variable 'draft_communication_artifact' produced by multiple steps
- Unused variable declared: sources_needed
- Unused variable declared: sources_available

## 9. SPL Draft

```spl
[DEFINE_AGENT: MainWorker "Orchestrate the end-to-end process and delegate to sub-tasks."]
    [DEFINE_PERSONA:]
        ROLE: Internal communications specialist
    [END_PERSONA]
    [DEFINE_CONCEPTS:]
        Internalnewsletters: Regular publications distributed within an organization to communicate news and updates to employees.
        Announcements: Official statements or communications made to inform a group about important events or changes.
        Updatedigests: Summarized collections of recent updates or changes, typically distributed periodically.
        Executivebriefs: Concise reports or summaries prepared for executives, highlighting key information and insights.
        Relatedinternalcommsartifacts: Documents or materials used in internal communications to support or enhance messaging within an organization.
    [END_CONCEPTS]
    [DEFINE_CONSTRAINTS:]
        Prohibition: Do not invent links or unseen facts
        Evidence: Require evidence for sourced claims
        Requirement: Limit questions per turn
        Requirement: Prefer tool evidence over unnecessary user questioning
        Gate: Deny finalization if critical slots are missing or provenance fails
    [END_CONSTRAINTS]
    [DEFINE_VARIABLES:]
        "A user request" user_request: text
        "Optional known topics" known_topics: List [text]
        "Optional timeframe" timeframe: text
        "Available connectors or source repositories" connectors_or_source_repositories: List [text]
        "Optional format preferences" format_preferences: text
        "A draft communication artifact" draft_communication_artifact: text
        "A source/evidence set" source_evidence_set: text
        "A short assumptions log for any unresolved items" assumptions_log: List [text]
        "A completion status" completion_status: text
        "Whether sources are needed" sources_needed: boolean
        "Whether sources are available" sources_available: boolean
    [END_VARIABLES]
    [DEFINE_WORKER: "To gather necessary information from approved sources while maintaining provenance." Worker_source_retrieval]
        [INPUTS]
            OPTIONAL <REF>connectors_or_source_repositories</REF>
        [END_INPUTS]
        [OUTPUTS]
            REQUIRED <REF>source_evidence_set</REF>
        [END_OUTPUTS]
        [MAIN_FLOW]
            [SEQUENTIAL_BLOCK]
                COMMAND-1 [COMMAND Retrieve sources using approved source recipes based on <REF>connectors_or_source_repositories</REF> RESULT source_evidence_set: text SET]
            [END_SEQUENTIAL_BLOCK]
        [END_MAIN_FLOW]
    [END_WORKER]
    [DEFINE_WORKER: "Orchestrate the end-to-end process and delegate to sub-tasks." MainWorker]
        [INPUTS]
            REQUIRED <REF>user_request</REF>
            OPTIONAL <REF>known_topics</REF>
            OPTIONAL <REF>timeframe</REF>
            OPTIONAL <REF>connectors_or_source_repositories</REF>
            OPTIONAL <REF>format_preferences</REF>
        [END_INPUTS]
        [OUTPUTS]
            REQUIRED <REF>draft_communication_artifact</REF>
            REQUIRED <REF>source_evidence_set</REF>
            REQUIRED <REF>assumptions_log</REF>
            REQUIRED <REF>completion_status</REF>
        [END_OUTPUTS]
        [MAIN_FLOW]
            [SEQUENTIAL_BLOCK]
                COMMAND-2 [COMMAND Determine the kind of communication requested based on <REF>user_request</REF>]
                COMMAND-3 [COMMAND Identify missing required fields based on <REF>user_request</REF>]
                COMMAND-4 [DISPLAY Ask clarifying questions]
                COMMAND-5 [INVOKE Worker_source_retrieval WITH <REF>connectors_or_source_repositories</REF> RESPONSE source_evidence_set: text SET]
            [END_SEQUENTIAL_BLOCK]
            DECISION-1 [IF sources are needed and available]
                COMMAND-6 [COMMAND Produce the draft communication artifact RESULT draft_communication_artifact: text SET]
            [END_IF]
        [END_MAIN_FLOW]
        [ALTERNATIVE_FLOW: the user asks for revision]
            [SEQUENTIAL_BLOCK]
                COMMAND-7 [COMMAND Revise the draft while rechecking constraints based on <REF>draft_communication_artifact</REF> RESULT <REF>draft_communication_artifact</REF> SET]
            [END_SEQUENTIAL_BLOCK]
        [END_ALTERNATIVE_FLOW]
        [EXCEPTION_FLOW: Missing timeframe]
        [END_EXCEPTION_FLOW]
        [EXCEPTION_FLOW: conflicting instructions]
        [END_EXCEPTION_FLOW]
        [EXCEPTION_FLOW: insufficient source access]
        [END_EXCEPTION_FLOW]
        [EXCEPTION_FLOW: evidence shortage]
        [END_EXCEPTION_FLOW]
        [EXCEPTION_FLOW: user refusal to answer]
        [END_EXCEPTION_FLOW]
        [EXCEPTION_FLOW: provenance failure]
        [END_EXCEPTION_FLOW]
    [END_WORKER]
[END_AGENT]
```
