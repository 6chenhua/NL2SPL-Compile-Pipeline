# NL2SPL Feedback Report

## 1. Overall Compile State

- Completeness: `partial`
- SPL draft generated: `yes`
- Compile diagnostics: `8`
- Assumptions / suggestions: `8`
- Trace records: `62`
- Adapter warnings: `15`
- Validation errors: `0`
- Validation warnings: `14`

Result is partial because the following requirement gaps remain:
- `missing_handler` on `worker:worker_main.exception_flow:exc_adapter_00`: Exception flow 'exc_adapter_00' ('Missing timeframe') has no handler step in worker 'worker_main'.
- `missing_handler` on `worker:worker_main.exception_flow:exc_adapter_01`: Exception flow 'exc_adapter_01' ('Conflicting instructions') has no handler step in worker 'worker_main'.
- `missing_handler` on `worker:worker_main.exception_flow:exc_adapter_02`: Exception flow 'exc_adapter_02' ('Insufficient source access') has no handler step in worker 'worker_main'.
- `missing_handler` on `worker:worker_main.exception_flow:exc_adapter_03`: Exception flow 'exc_adapter_03' ('Evidence
shortage') has no handler step in worker 'worker_main'.
- `missing_handler` on `worker:worker_main.exception_flow:exc_adapter_04`: Exception flow 'exc_adapter_04' ('User refusal to answer') has no handler step in worker 'worker_main'.
- `missing_handler` on `worker:worker_main.exception_flow:exc_adapter_05`: Exception flow 'exc_adapter_05' ('Provenance failure') has no handler step in worker 'worker_main'.
- `missing_output_producer` on `worker:worker_main.output:completion_status`: Required output 'completion_status' (A completion status) has no source-backed producer step.
- `type_or_contract_ambiguity` on `delegation_intent:s30`: Delegation intent 'Optional delegated subtasks such as source gathering or template matching may be' lacks a valid worker/API handoff contract.  No INVOKE_WORKER or CALL_API will be generated from this span.  [sec_delegation_policy/p_delegation_rule_delegated_subtasks_such_as_source_gathering_or_template_matching_may_be_used_if_bounded_and_the_returned_evidence_is_normalized_into_approved_evidence_carriers]

## 2. Materialized Source-Backed Structure

### Workers
- `worker:MainWorker` (direct) -- spans=s11, s12, s13, s17, s18, s30; section=sec_reusable_process; packet=p_process_step_first_determine_what_kind_of_communication_is_requested
- `worker:Worker_produce_draft` (direct) -- spans=s16; section=sec_reusable_process; packet=p_process_step_when_enough_required_information_is_available_produce_a_draft
- `worker:Worker_retrieve_sources` (direct) -- spans=s14, s15; section=sec_reusable_process; packet=p_process_step_if_sources_are_needed_and_available_retrieve_them_using_approved_source_recipes
- `worker:produce_draft.variable:assumptions_log` (direct) -- spans=s13; section=sec_reusable_process; packet=p_process_step_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward
- `worker:produce_draft.variable:assumptions_log` (direct) -- spans=s13; section=sec_reusable_process; packet=p_process_step_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward
- `worker:produce_draft.variable:assumptions_log` (direct) -- spans=s13; section=sec_reusable_process; packet=p_process_step_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward
- `worker:produce_draft.variable:completion_status` (normalized) -- section=sec_required_outputs
- `worker:produce_draft.variable:completion_status` (normalized) -- section=sec_required_outputs
- `worker:produce_draft.variable:completion_status` (normalized) -- section=sec_required_outputs
- `worker:produce_draft.variable:connectors_or_source_repositories` (normalized) -- section=sec_inputs_for_each_run
- `worker:produce_draft.variable:connectors_or_source_repositories` (normalized) -- section=sec_inputs_for_each_run
- `worker:produce_draft.variable:connectors_or_source_repositories` (normalized) -- section=sec_inputs_for_each_run
- `worker:produce_draft.variable:draft_communication_artifact` (direct) -- spans=s17; section=sec_reusable_process; packet=p_process_step_if_the_user_asks_for_revision_revise_while_re_checking_constraints
- `worker:produce_draft.variable:draft_communication_artifact` (direct) -- spans=s17; section=sec_reusable_process; packet=p_process_step_if_the_user_asks_for_revision_revise_while_re_checking_constraints
- `worker:produce_draft.variable:draft_communication_artifact` (direct) -- spans=s17; section=sec_reusable_process; packet=p_process_step_if_the_user_asks_for_revision_revise_while_re_checking_constraints
- `worker:produce_draft.variable:format_preferences` (normalized) -- section=sec_inputs_for_each_run
- `worker:produce_draft.variable:format_preferences` (normalized) -- section=sec_inputs_for_each_run
- `worker:produce_draft.variable:format_preferences` (normalized) -- section=sec_inputs_for_each_run
- `worker:produce_draft.variable:known_topics` (normalized) -- section=sec_inputs_for_each_run
- `worker:produce_draft.variable:known_topics` (normalized) -- section=sec_inputs_for_each_run
- `worker:produce_draft.variable:known_topics` (normalized) -- section=sec_inputs_for_each_run
- `worker:produce_draft.variable:source_evidence_set` (direct) -- spans=s13; section=sec_reusable_process; packet=p_process_step_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward
- `worker:produce_draft.variable:source_evidence_set` (direct) -- spans=s13; section=sec_reusable_process; packet=p_process_step_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward
- `worker:produce_draft.variable:source_evidence_set` (direct) -- spans=s13; section=sec_reusable_process; packet=p_process_step_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward
- `worker:produce_draft.variable:timeframe` (normalized) -- section=sec_inputs_for_each_run
- `worker:produce_draft.variable:timeframe` (normalized) -- section=sec_inputs_for_each_run
- `worker:produce_draft.variable:timeframe` (normalized) -- section=sec_inputs_for_each_run
- `worker:produce_draft.variable:user_request` (normalized) -- section=sec_inputs_for_each_run
- `worker:produce_draft.variable:user_request` (normalized) -- section=sec_inputs_for_each_run
- `worker:produce_draft.variable:user_request` (normalized) -- section=sec_inputs_for_each_run

### Flows
- `flow:alt_1` (direct) -- spans=s17; section=sec_reusable_process; packet=p_process_step_if_the_user_asks_for_revision_revise_while_re_checking_constraints
- `flow:exc_adapter_00` (direct) -- spans=s24; section=sec_failure_handling; packet=p_failure_mode_missing_timeframe
- `flow:exc_adapter_01` (direct) -- spans=s25; section=sec_failure_handling; packet=p_failure_mode_conflicting_instructions
- `flow:exc_adapter_02` (direct) -- spans=s26; section=sec_failure_handling; packet=p_failure_mode_insufficient_source_access
- `flow:exc_adapter_03` (direct) -- spans=s27; section=sec_failure_handling; packet=p_failure_mode_evidence_shortage
- `flow:exc_adapter_04` (direct) -- spans=s28; section=sec_failure_handling; packet=p_failure_mode_user_refusal_to_answer
- `flow:exc_adapter_05` (direct) -- spans=s29; section=sec_failure_handling; packet=p_failure_mode_provenance_failure
- `flow:main` (direct) -- spans=s11, s12, s13, s30; section=sec_reusable_process; packet=p_process_step_first_determine_what_kind_of_communication_is_requested

### Steps
- `step:st_1` (direct) -- spans=s11; section=sec_reusable_process; packet=p_process_step_first_determine_what_kind_of_communication_is_requested
- `step:st_1` (direct) -- spans=s14; section=sec_reusable_process; packet=p_process_step_if_sources_are_needed_and_available_retrieve_them_using_approved_source_recipes
- `step:st_1` (direct) -- spans=s16; section=sec_reusable_process; packet=p_process_step_when_enough_required_information_is_available_produce_a_draft
- `step:st_2` (direct) -- spans=s12; section=sec_reusable_process; packet=p_process_step_then_identify_which_required_fields_are_still_missing
- `step:st_2` (direct) -- spans=s15; section=sec_reusable_process; packet=p_process_step_maintain_provenance_for_externally_sourced_facts
- `step:st_3` (direct) -- spans=s13; section=sec_reusable_process; packet=p_process_step_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward
- `step:st_4` (direct) -- spans=s17; section=sec_reusable_process; packet=p_process_step_if_the_user_asks_for_revision_revise_while_re_checking_constraints
- `step:st_invoke_handoff_produce_draft` (direct) -- spans=s13; section=sec_reusable_process; packet=p_process_step_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward
- `step:st_invoke_handoff_retrieve_sources` (direct) -- spans=s13; section=sec_reusable_process; packet=p_process_step_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward

### Constraints
- `constraint:c_1` (direct) -- spans=s19; section=sec_policies; packet=p_policy_do_not_invent_links_or_unseen_facts
- `constraint:c_2` (direct) -- spans=s20; section=sec_policies; packet=p_policy_require_evidence_for_sourced_claims
- `constraint:c_3` (direct) -- spans=s21; section=sec_policies; packet=p_policy_limit_questions_per_turn
- `constraint:c_4` (direct) -- spans=s22; section=sec_policies; packet=p_policy_prefer_tool_evidence_over_unnecessary_user_questioning
- `constraint:c_5` (direct) -- spans=s23; section=sec_policies; packet=p_policy_deny_finalization_if_critical_slots_are_missing_or_provenance_fails

### Handoffs
- `handoff:handoff_produce_draft` (direct) -- spans=s13, s17; section=sec_reusable_process; packet=p_process_step_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward
- `handoff:handoff_retrieve_sources` (direct) -- spans=s13, s17; section=sec_reusable_process; packet=p_process_step_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward

### Delegation Intents
- `delegation_intent:delegated_subtasks` (inferred) -- spans=s30; section=sec_delegation_policy; packet=p_delegation_rule_delegated_subtasks_such_as_source_gathering_or_template_matching_may_be_used_if_bounded_and_the_returned_evidence_is_normalized_into_approved_evidence_carriers
- `delegation_intent:delegated_subtasks_such_as_source_gathering_or_template_matching_may_be_used_if_bounded_and_the_returned_evidence_is_normalized_into_approved_evidence_carriers` (inferred) -- spans=s30; section=sec_delegation_policy; packet=p_delegation_rule_delegated_subtasks_such_as_source_gathering_or_template_matching_may_be_used_if_bounded_and_the_returned_evidence_is_normalized_into_approved_evidence_carriers

### Other
- `profile:concept_0` (normalized)
- `profile:concept_1` (normalized)
- `profile:concept_2` (normalized)
- `profile:concept_3` (normalized)
- `profile:concept_4` (normalized)
- `profile:persona` (inferred)

## 3. Not Materialized / Kept Partial

- `worker:worker_main.exception_flow:exc_adapter_00`: `missing_handler` -- Exception flow 'exc_adapter_00' ('Missing timeframe') has no handler step in worker 'worker_main'.
  - Suggested resolution: Add a handler step for 'Missing timeframe', or mark this exception as acknowledged without handling.
- `worker:worker_main.exception_flow:exc_adapter_01`: `missing_handler` -- Exception flow 'exc_adapter_01' ('Conflicting instructions') has no handler step in worker 'worker_main'.
  - Suggested resolution: Add a handler step for 'Conflicting instructions', or mark this exception as acknowledged without handling.
- `worker:worker_main.exception_flow:exc_adapter_02`: `missing_handler` -- Exception flow 'exc_adapter_02' ('Insufficient source access') has no handler step in worker 'worker_main'.
  - Suggested resolution: Add a handler step for 'Insufficient source access', or mark this exception as acknowledged without handling.
- `worker:worker_main.exception_flow:exc_adapter_03`: `missing_handler` -- Exception flow 'exc_adapter_03' ('Evidence
shortage') has no handler step in worker 'worker_main'.
  - Suggested resolution: Add a handler step for 'Evidence
shortage', or mark this exception as acknowledged without handling.
- `worker:worker_main.exception_flow:exc_adapter_04`: `missing_handler` -- Exception flow 'exc_adapter_04' ('User refusal to answer') has no handler step in worker 'worker_main'.
  - Suggested resolution: Add a handler step for 'User refusal to answer', or mark this exception as acknowledged without handling.
- `worker:worker_main.exception_flow:exc_adapter_05`: `missing_handler` -- Exception flow 'exc_adapter_05' ('Provenance failure') has no handler step in worker 'worker_main'.
  - Suggested resolution: Add a handler step for 'Provenance failure', or mark this exception as acknowledged without handling.
- `worker:worker_main.output:completion_status`: `missing_output_producer` -- Required output 'completion_status' (A completion status) has no source-backed producer step.
  - Suggested resolution: Add a step that produces 'completion_status', e.g. 'Set completion status for the normal completion path'. If the source requirement does not specify how to produce this output, mark it as optional or remove it from the output contract.
- `delegation_intent:s30`: `type_or_contract_ambiguity` -- Delegation intent 'Optional delegated subtasks such as source gathering or template matching may be' lacks a valid worker/API handoff contract.  No INVOKE_WORKER or CALL_API will be generated from this span.  [sec_delegation_policy/p_delegation_rule_delegated_subtasks_such_as_source_gathering_or_template_matching_may_be_used_if_bounded_and_the_returned_evidence_is_normalized_into_approved_evidence_carriers]
  - Suggested resolution: Provide a valid worker/API handoff contract with input/output/API bindings covering span 's30'. hints=hint_delegation_0_sec_delegation_policy

## 4. Diagnostics

### diag_post_norm_0000: `missing_handler`
- Severity: `warning`
- Target: `worker:worker_main.exception_flow:exc_adapter_00`
- Source spans: `s24`
- Message: Exception flow 'exc_adapter_00' ('Missing timeframe') has no handler step in worker 'worker_main'.
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Add a handler step for 'Missing timeframe', or mark this exception as acknowledged without handling.

### diag_post_norm_0001: `missing_handler`
- Severity: `warning`
- Target: `worker:worker_main.exception_flow:exc_adapter_01`
- Source spans: `s25`
- Message: Exception flow 'exc_adapter_01' ('Conflicting instructions') has no handler step in worker 'worker_main'.
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Add a handler step for 'Conflicting instructions', or mark this exception as acknowledged without handling.

### diag_post_norm_0002: `missing_handler`
- Severity: `warning`
- Target: `worker:worker_main.exception_flow:exc_adapter_02`
- Source spans: `s26`
- Message: Exception flow 'exc_adapter_02' ('Insufficient source access') has no handler step in worker 'worker_main'.
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Add a handler step for 'Insufficient source access', or mark this exception as acknowledged without handling.

### diag_post_norm_0003: `missing_handler`
- Severity: `warning`
- Target: `worker:worker_main.exception_flow:exc_adapter_03`
- Source spans: `s27`
- Message: Exception flow 'exc_adapter_03' ('Evidence
shortage') has no handler step in worker 'worker_main'.
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Add a handler step for 'Evidence
shortage', or mark this exception as acknowledged without handling.

### diag_post_norm_0004: `missing_handler`
- Severity: `warning`
- Target: `worker:worker_main.exception_flow:exc_adapter_04`
- Source spans: `s28`
- Message: Exception flow 'exc_adapter_04' ('User refusal to answer') has no handler step in worker 'worker_main'.
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Add a handler step for 'User refusal to answer', or mark this exception as acknowledged without handling.

### diag_post_norm_0005: `missing_handler`
- Severity: `warning`
- Target: `worker:worker_main.exception_flow:exc_adapter_05`
- Source spans: `s29`
- Message: Exception flow 'exc_adapter_05' ('Provenance failure') has no handler step in worker 'worker_main'.
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Add a handler step for 'Provenance failure', or mark this exception as acknowledged without handling.

### diag_post_norm_0006: `missing_output_producer`
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
- Message: Delegation intent 'Optional delegated subtasks such as source gathering or template matching may be' lacks a valid worker/API handoff contract.  No INVOKE_WORKER or CALL_API will be generated from this span.  [sec_delegation_policy/p_delegation_rule_delegated_subtasks_such_as_source_gathering_or_template_matching_may_be_used_if_bounded_and_the_returned_evidence_is_normalized_into_approved_evidence_carriers]
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Provide a valid worker/API handoff contract with input/output/API bindings covering span 's30'. hints=hint_delegation_0_sec_delegation_policy

## 5. Assumptions / Suggestions

- `ASM_0000` for `worker:worker_main.exception_flow:exc_adapter_00`: Exception flow has no handler action. The compiler suggests specifying what should happen when this failure occurs.
  - Reason: Source describes a failure condition but does not specify how to handle it.  The exception flow is preserved in SPL, but no handler command was rendered. (Exception flow 'exc_adapter_00' ('Missing timeframe') has no handler step in worker 'worker_main'.)
  - Suggested resolution: Specify the handler action for worker:worker_main.exception_flow:exc_adapter_00: e.g. ask the user for missing information, block finalization, or continue with an explicit assumption.
  - Related diagnostic: `diag_post_norm_0000`
- `ASM_0001` for `worker:worker_main.exception_flow:exc_adapter_01`: Exception flow has no handler action. The compiler suggests specifying what should happen when this failure occurs.
  - Reason: Source describes a failure condition but does not specify how to handle it.  The exception flow is preserved in SPL, but no handler command was rendered. (Exception flow 'exc_adapter_01' ('Conflicting instructions') has no handler step in worker 'worker_main'.)
  - Suggested resolution: Specify the handler action for worker:worker_main.exception_flow:exc_adapter_01: e.g. ask the user for missing information, block finalization, or continue with an explicit assumption.
  - Related diagnostic: `diag_post_norm_0001`
- `ASM_0002` for `worker:worker_main.exception_flow:exc_adapter_02`: Exception flow has no handler action. The compiler suggests specifying what should happen when this failure occurs.
  - Reason: Source describes a failure condition but does not specify how to handle it.  The exception flow is preserved in SPL, but no handler command was rendered. (Exception flow 'exc_adapter_02' ('Insufficient source access') has no handler step in worker 'worker_main'.)
  - Suggested resolution: Specify the handler action for worker:worker_main.exception_flow:exc_adapter_02: e.g. ask the user for missing information, block finalization, or continue with an explicit assumption.
  - Related diagnostic: `diag_post_norm_0002`
- `ASM_0003` for `worker:worker_main.exception_flow:exc_adapter_03`: Exception flow has no handler action. The compiler suggests specifying what should happen when this failure occurs.
  - Reason: Source describes a failure condition but does not specify how to handle it.  The exception flow is preserved in SPL, but no handler command was rendered. (Exception flow 'exc_adapter_03' ('Evidence
shortage') has no handler step in worker 'worker_main'.)
  - Suggested resolution: Specify the handler action for worker:worker_main.exception_flow:exc_adapter_03: e.g. ask the user for missing information, block finalization, or continue with an explicit assumption.
  - Related diagnostic: `diag_post_norm_0003`
- `ASM_0004` for `worker:worker_main.exception_flow:exc_adapter_04`: Exception flow has no handler action. The compiler suggests specifying what should happen when this failure occurs.
  - Reason: Source describes a failure condition but does not specify how to handle it.  The exception flow is preserved in SPL, but no handler command was rendered. (Exception flow 'exc_adapter_04' ('User refusal to answer') has no handler step in worker 'worker_main'.)
  - Suggested resolution: Specify the handler action for worker:worker_main.exception_flow:exc_adapter_04: e.g. ask the user for missing information, block finalization, or continue with an explicit assumption.
  - Related diagnostic: `diag_post_norm_0004`
- `ASM_0005` for `worker:worker_main.exception_flow:exc_adapter_05`: Exception flow has no handler action. The compiler suggests specifying what should happen when this failure occurs.
  - Reason: Source describes a failure condition but does not specify how to handle it.  The exception flow is preserved in SPL, but no handler command was rendered. (Exception flow 'exc_adapter_05' ('Provenance failure') has no handler step in worker 'worker_main'.)
  - Suggested resolution: Specify the handler action for worker:worker_main.exception_flow:exc_adapter_05: e.g. ask the user for missing information, block finalization, or continue with an explicit assumption.
  - Related diagnostic: `diag_post_norm_0005`
- `ASM_0006` for `worker:worker_main.output:completion_status`: Required output has no source-backed producer. The compiler suggests adding a step that explicitly produces this output.
  - Reason: The source requires this output but does not describe how it should be produced.  The output is kept in the OUTPUTS contract, but no producer step was rendered.
  - Suggested resolution: Add a source-backed step that produces worker:worker_main.output:completion_status. If the source does not specify how to produce it, mark it as optional or remove it from the required output contract.
  - Related diagnostic: `diag_post_norm_0006`
- `ASM_0007` for `delegation_intent:s30`: Command has an ambiguous or incomplete contract. The compiler suggests providing the missing contract detail.
  - Reason: A command references an API, worker, or input source that is not fully specified.  The compiler cannot materialize the command without this information.
  - Suggested resolution: For delegation_intent:s30: provide the missing contract detail (API name, worker target, IO bindings, or source evidence).  See the related diagnostic for specifics.
  - Related diagnostic: `diag_d10_0000`

## 6. Provenance / TraceRecords

- `constraint:c_1` -> `direct`
  - Source: spans=`s19`, section=`sec_policies`, packet=`p_policy_do_not_invent_links_or_unseen_facts`
  - Explanation: Constraint 'c_1' (prohibition): Do not invent links or unseen facts
- `constraint:c_2` -> `direct`
  - Source: spans=`s20`, section=`sec_policies`, packet=`p_policy_require_evidence_for_sourced_claims`
  - Explanation: Constraint 'c_2' (evidence): Require evidence for sourced claims
- `constraint:c_3` -> `direct`
  - Source: spans=`s21`, section=`sec_policies`, packet=`p_policy_limit_questions_per_turn`
  - Explanation: Constraint 'c_3' (requirement): Limit questions per turn
- `constraint:c_4` -> `direct`
  - Source: spans=`s22`, section=`sec_policies`, packet=`p_policy_prefer_tool_evidence_over_unnecessary_user_questioning`
  - Explanation: Constraint 'c_4' (requirement): Prefer tool evidence over unnecessary user questioning
- `constraint:c_5` -> `direct`
  - Source: spans=`s23`, section=`sec_policies`, packet=`p_policy_deny_finalization_if_critical_slots_are_missing_or_provenance_fails`
  - Explanation: Constraint 'c_5' (gate): Deny finalization if critical slots are missing or provenance fails
- `delegation_intent:delegated_subtasks` -> `inferred`
  - Source: spans=`s30`, section=`sec_delegation_policy`, packet=`p_delegation_rule_delegated_subtasks_such_as_source_gathering_or_template_matching_may_be_used_if_bounded_and_the_returned_evidence_is_normalized_into_approved_evidence_carriers`
  - Explanation: Delegation intent 'delegated_subtasks': Optional delegated subtasks such as source gathering or template matching may be used if bounded and the returned eviden
- `delegation_intent:delegated_subtasks_such_as_source_gathering_or_template_matching_may_be_used_if_bounded_and_the_returned_evidence_is_normalized_into_approved_evidence_carriers` -> `inferred`
  - Source: spans=`s30`, section=`sec_delegation_policy`, packet=`p_delegation_rule_delegated_subtasks_such_as_source_gathering_or_template_matching_may_be_used_if_bounded_and_the_returned_evidence_is_normalized_into_approved_evidence_carriers`
  - Explanation: Delegation intent 'delegated_subtasks_such_as_source_gathering_or_template_matching_may_be_used_if_bounded_and_the_returned_evidence_is_normalized_into_approved_evidence_carriers': Optional delegated subtasks such as source gathering or template matching may be
used if bounded and the returned eviden
- `flow:alt_1` -> `direct`
  - Source: spans=`s17`, section=`sec_reusable_process`, packet=`p_process_step_if_the_user_asks_for_revision_revise_while_re_checking_constraints`
  - Explanation: Alternative flow 'alt_1': If the user asks for revision
- `flow:exc_adapter_00` -> `direct`
  - Source: spans=`s24`, section=`sec_failure_handling`, packet=`p_failure_mode_missing_timeframe`
  - Explanation: Exception flow 'exc_adapter_00': Missing timeframe
- `flow:exc_adapter_01` -> `direct`
  - Source: spans=`s25`, section=`sec_failure_handling`, packet=`p_failure_mode_conflicting_instructions`
  - Explanation: Exception flow 'exc_adapter_01': Conflicting instructions
- `flow:exc_adapter_02` -> `direct`
  - Source: spans=`s26`, section=`sec_failure_handling`, packet=`p_failure_mode_insufficient_source_access`
  - Explanation: Exception flow 'exc_adapter_02': Insufficient source access
- `flow:exc_adapter_03` -> `direct`
  - Source: spans=`s27`, section=`sec_failure_handling`, packet=`p_failure_mode_evidence_shortage`
  - Explanation: Exception flow 'exc_adapter_03': Evidence
shortage
- `flow:exc_adapter_04` -> `direct`
  - Source: spans=`s28`, section=`sec_failure_handling`, packet=`p_failure_mode_user_refusal_to_answer`
  - Explanation: Exception flow 'exc_adapter_04': User refusal to answer
- `flow:exc_adapter_05` -> `direct`
  - Source: spans=`s29`, section=`sec_failure_handling`, packet=`p_failure_mode_provenance_failure`
  - Explanation: Exception flow 'exc_adapter_05': Provenance failure
- `flow:main` -> `direct`
  - Source: spans=`s11, s12, s13, s30`, section=`sec_reusable_process`, packet=`p_process_step_first_determine_what_kind_of_communication_is_requested`
  - Explanation: Main flow with 1 block(s).
- `handoff:handoff_produce_draft` -> `direct`
  - Source: spans=`s13, s17`, section=`sec_reusable_process`, packet=`p_process_step_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward`
  - Explanation: Handoff 'handoff_produce_draft' (worker_main invoke to produce_draft) with 1 input(s) and 1 output(s).
- `handoff:handoff_retrieve_sources` -> `direct`
  - Source: spans=`s13, s17`, section=`sec_reusable_process`, packet=`p_process_step_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward`
  - Explanation: Handoff 'handoff_retrieve_sources' (worker_main invoke to retrieve_sources) with 1 input(s) and 1 output(s).
- `profile:concept_0` -> `normalized`
  - Explanation: Concept: Internal newsletters -- Periodic publications intended for internal distribution within an organization to share updates, news, and information.
- `profile:concept_1` -> `normalized`
  - Explanation: Concept: Announcements -- Official statements or notifications shared within an organization to inform employees about important updates or events.
- `profile:concept_2` -> `normalized`
  - Explanation: Concept: Update digests -- Summarized collections of updates or information, typically shared periodically within an organization.
- `profile:concept_3` -> `normalized`
  - Explanation: Concept: Executive briefs -- Concise documents or summaries prepared for executives, providing key information or updates on specific topics.
- `profile:concept_4` -> `normalized`
  - Explanation: Concept: Internal-comms artifacts -- Documents or materials created for the purpose of internal communication within an organization, such as newsletters, announcements, or briefs.
- `profile:persona` -> `inferred`
  - Explanation: Persona: Internal communications specialist
- `step:st_1` -> `direct`
  - Source: spans=`s11`, section=`sec_reusable_process`, packet=`p_process_step_first_determine_what_kind_of_communication_is_requested`
  - Explanation: Step 'st_1' maps to source span(s).
- `step:st_1` -> `direct`
  - Source: spans=`s14`, section=`sec_reusable_process`, packet=`p_process_step_if_sources_are_needed_and_available_retrieve_them_using_approved_source_recipes`
  - Explanation: Step 'st_1' maps to source span(s).
- `step:st_1` -> `direct`
  - Source: spans=`s16`, section=`sec_reusable_process`, packet=`p_process_step_when_enough_required_information_is_available_produce_a_draft`
  - Explanation: Step 'st_1' maps to source span(s).
- `step:st_2` -> `direct`
  - Source: spans=`s12`, section=`sec_reusable_process`, packet=`p_process_step_then_identify_which_required_fields_are_still_missing`
  - Explanation: Step 'st_2' maps to source span(s).
- `step:st_2` -> `direct`
  - Source: spans=`s15`, section=`sec_reusable_process`, packet=`p_process_step_maintain_provenance_for_externally_sourced_facts`
  - Explanation: Step 'st_2' maps to source span(s).
- `step:st_3` -> `direct`
  - Source: spans=`s13`, section=`sec_reusable_process`, packet=`p_process_step_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward`
  - Explanation: Step 'st_3' maps to source span(s).
- `step:st_4` -> `direct`
  - Source: spans=`s17`, section=`sec_reusable_process`, packet=`p_process_step_if_the_user_asks_for_revision_revise_while_re_checking_constraints`
  - Explanation: Step 'st_4' maps to source span(s).
- `step:st_invoke_handoff_produce_draft` -> `direct`
  - Source: spans=`s13`, section=`sec_reusable_process`, packet=`p_process_step_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward`
  - Explanation: Step 'st_invoke_handoff_produce_draft' maps to source span(s).
- `step:st_invoke_handoff_retrieve_sources` -> `direct`
  - Source: spans=`s13`, section=`sec_reusable_process`, packet=`p_process_step_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward`
  - Explanation: Step 'st_invoke_handoff_retrieve_sources' maps to source span(s).
- `worker:MainWorker` -> `direct`
  - Source: spans=`s11, s12, s13, s17, s18, s30`, section=`sec_reusable_process`, packet=`p_process_step_first_determine_what_kind_of_communication_is_requested`
  - Explanation: Main worker 'MainWorker' assembled from flow and step IRs.
- `worker:Worker_produce_draft` -> `direct`
  - Source: spans=`s16`, section=`sec_reusable_process`, packet=`p_process_step_when_enough_required_information_is_available_produce_a_draft`
  - Explanation: Child worker 'Worker_produce_draft' extracted from delegation pattern.
- `worker:Worker_retrieve_sources` -> `direct`
  - Source: spans=`s14, s15`, section=`sec_reusable_process`, packet=`p_process_step_if_sources_are_needed_and_available_retrieve_them_using_approved_source_recipes`
  - Explanation: Child worker 'Worker_retrieve_sources' extracted from delegation pattern.
- `worker:produce_draft.variable:assumptions_log` -> `direct`
  - Source: spans=`s13`, section=`sec_reusable_process`, packet=`p_process_step_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward`
  - Explanation: Variable 'assumptions_log' is produced by source-backed step 'st_3'.
- `worker:produce_draft.variable:assumptions_log` -> `direct`
  - Source: spans=`s13`, section=`sec_reusable_process`, packet=`p_process_step_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward`
  - Explanation: Variable 'assumptions_log' is produced by source-backed step 'st_3'.
- `worker:produce_draft.variable:assumptions_log` -> `direct`
  - Source: spans=`s13`, section=`sec_reusable_process`, packet=`p_process_step_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward`
  - Explanation: Variable 'assumptions_log' is produced by source-backed step 'st_3'.
- `worker:produce_draft.variable:completion_status` -> `normalized`
  - Source: section=`sec_required_outputs`
  - Explanation: Variable 'completion_status' is declared by adapter hard fact in section 'sec_required_outputs'.
- `worker:produce_draft.variable:completion_status` -> `normalized`
  - Source: section=`sec_required_outputs`
  - Explanation: Variable 'completion_status' is declared by adapter hard fact in section 'sec_required_outputs'.
- `worker:produce_draft.variable:completion_status` -> `normalized`
  - Source: section=`sec_required_outputs`
  - Explanation: Variable 'completion_status' is declared by adapter hard fact in section 'sec_required_outputs'.
- `worker:produce_draft.variable:connectors_or_source_repositories` -> `normalized`
  - Source: section=`sec_inputs_for_each_run`
  - Explanation: Variable 'connectors_or_source_repositories' is declared by adapter hard fact in section 'sec_inputs_for_each_run'.
- `worker:produce_draft.variable:connectors_or_source_repositories` -> `normalized`
  - Source: section=`sec_inputs_for_each_run`
  - Explanation: Variable 'connectors_or_source_repositories' is declared by adapter hard fact in section 'sec_inputs_for_each_run'.
- `worker:produce_draft.variable:connectors_or_source_repositories` -> `normalized`
  - Source: section=`sec_inputs_for_each_run`
  - Explanation: Variable 'connectors_or_source_repositories' is declared by adapter hard fact in section 'sec_inputs_for_each_run'.
- `worker:produce_draft.variable:draft_communication_artifact` -> `direct`
  - Source: spans=`s17`, section=`sec_reusable_process`, packet=`p_process_step_if_the_user_asks_for_revision_revise_while_re_checking_constraints`
  - Explanation: Variable 'draft_communication_artifact' is produced by source-backed step 'st_4'.
- `worker:produce_draft.variable:draft_communication_artifact` -> `direct`
  - Source: spans=`s17`, section=`sec_reusable_process`, packet=`p_process_step_if_the_user_asks_for_revision_revise_while_re_checking_constraints`
  - Explanation: Variable 'draft_communication_artifact' is produced by source-backed step 'st_4'.
- `worker:produce_draft.variable:draft_communication_artifact` -> `direct`
  - Source: spans=`s17`, section=`sec_reusable_process`, packet=`p_process_step_if_the_user_asks_for_revision_revise_while_re_checking_constraints`
  - Explanation: Variable 'draft_communication_artifact' is produced by source-backed step 'st_4'.
- `worker:produce_draft.variable:format_preferences` -> `normalized`
  - Source: section=`sec_inputs_for_each_run`
  - Explanation: Variable 'format_preferences' is declared by adapter hard fact in section 'sec_inputs_for_each_run'.
- `worker:produce_draft.variable:format_preferences` -> `normalized`
  - Source: section=`sec_inputs_for_each_run`
  - Explanation: Variable 'format_preferences' is declared by adapter hard fact in section 'sec_inputs_for_each_run'.
- `worker:produce_draft.variable:format_preferences` -> `normalized`
  - Source: section=`sec_inputs_for_each_run`
  - Explanation: Variable 'format_preferences' is declared by adapter hard fact in section 'sec_inputs_for_each_run'.
- `worker:produce_draft.variable:known_topics` -> `normalized`
  - Source: section=`sec_inputs_for_each_run`
  - Explanation: Variable 'known_topics' is declared by adapter hard fact in section 'sec_inputs_for_each_run'.
- `worker:produce_draft.variable:known_topics` -> `normalized`
  - Source: section=`sec_inputs_for_each_run`
  - Explanation: Variable 'known_topics' is declared by adapter hard fact in section 'sec_inputs_for_each_run'.
- `worker:produce_draft.variable:known_topics` -> `normalized`
  - Source: section=`sec_inputs_for_each_run`
  - Explanation: Variable 'known_topics' is declared by adapter hard fact in section 'sec_inputs_for_each_run'.
- `worker:produce_draft.variable:source_evidence_set` -> `direct`
  - Source: spans=`s13`, section=`sec_reusable_process`, packet=`p_process_step_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward`
  - Explanation: Variable 'source_evidence_set' is produced by source-backed step 'st_invoke_handoff_retrieve_sources'.
- `worker:produce_draft.variable:source_evidence_set` -> `direct`
  - Source: spans=`s13`, section=`sec_reusable_process`, packet=`p_process_step_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward`
  - Explanation: Variable 'source_evidence_set' is produced by source-backed step 'st_invoke_handoff_retrieve_sources'.
- `worker:produce_draft.variable:source_evidence_set` -> `direct`
  - Source: spans=`s13`, section=`sec_reusable_process`, packet=`p_process_step_ask_only_the_highest_value_clarifying_questions_needed_to_move_forward`
  - Explanation: Variable 'source_evidence_set' is produced by source-backed step 'st_invoke_handoff_retrieve_sources'.
- `worker:produce_draft.variable:timeframe` -> `normalized`
  - Source: section=`sec_inputs_for_each_run`
  - Explanation: Variable 'timeframe' is declared by adapter hard fact in section 'sec_inputs_for_each_run'.
- `worker:produce_draft.variable:timeframe` -> `normalized`
  - Source: section=`sec_inputs_for_each_run`
  - Explanation: Variable 'timeframe' is declared by adapter hard fact in section 'sec_inputs_for_each_run'.
- `worker:produce_draft.variable:timeframe` -> `normalized`
  - Source: section=`sec_inputs_for_each_run`
  - Explanation: Variable 'timeframe' is declared by adapter hard fact in section 'sec_inputs_for_each_run'.
- `worker:produce_draft.variable:user_request` -> `normalized`
  - Source: section=`sec_inputs_for_each_run`
  - Explanation: Variable 'user_request' is declared by adapter hard fact in section 'sec_inputs_for_each_run'.
- `worker:produce_draft.variable:user_request` -> `normalized`
  - Source: section=`sec_inputs_for_each_run`
  - Explanation: Variable 'user_request' is declared by adapter hard fact in section 'sec_inputs_for_each_run'.
- `worker:produce_draft.variable:user_request` -> `normalized`
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
- LLM_DUPLICATE_FACT: LLM failure_mode fact 'missing_timeframe' duplicates deterministic fact -- rejected.
- LLM_DUPLICATE_FACT: LLM failure_mode fact 'conflicting_instructions' duplicates deterministic fact -- rejected.
- LLM_DUPLICATE_FACT: LLM failure_mode fact 'insufficient_source_access' duplicates deterministic fact -- rejected.
- LLM_DUPLICATE_FACT: LLM failure_mode fact 'evidence_shortage' duplicates deterministic fact -- rejected.
- LLM_DUPLICATE_FACT: LLM failure_mode fact 'user_refusal_to_answer' duplicates deterministic fact -- rejected.
- LLM_DUPLICATE_FACT: LLM failure_mode fact 'provenance_failure' duplicates deterministic fact -- rejected.

Validation warnings:
- D3: failure condition span 's24' (Missing timeframe) is not owned by any worker; attached to main worker 'worker_main'.
- D3: failure condition span 's25' (Conflicting instructions) is not owned by any worker; attached to main worker 'worker_main'.
- D3: failure condition span 's26' (Insufficient source access) is not owned by any worker; attached to main worker 'worker_main'.
- D3: failure condition span 's27' (Evidence
shortage) is not owned by any worker; attached to main worker 'worker_main'.
- D3: failure condition span 's28' (User refusal to answer) is not owned by any worker; attached to main worker 'worker_main'.
- D3: failure condition span 's29' (Provenance failure) is not owned by any worker; attached to main worker 'worker_main'.
- D3: failure condition span 's24' (Missing timeframe) is not owned by any worker; attached to main worker 'worker_main'.
- D3: failure condition span 's25' (Conflicting instructions) is not owned by any worker; attached to main worker 'worker_main'.
- D3: failure condition span 's26' (Insufficient source access) is not owned by any worker; attached to main worker 'worker_main'.
- D3: failure condition span 's27' (Evidence
shortage) is not owned by any worker; attached to main worker 'worker_main'.
- D3: failure condition span 's28' (User refusal to answer) is not owned by any worker; attached to main worker 'worker_main'.
- D3: failure condition span 's29' (Provenance failure) is not owned by any worker; attached to main worker 'worker_main'.
- Worker worker_main: variable 'draft_communication_artifact' produced by multiple steps
- Worker retrieve_sources: variable 'source_evidence_set' produced by multiple steps

## 9. SPL Draft

```spl
[DEFINE_AGENT: MainWorker "Orchestrate the end-to-end process and delegate to sub-tasks."]
    [DEFINE_PERSONA:]
        ROLE: Internal communications specialist
    [END_PERSONA]
    [DEFINE_CONCEPTS:]
        Internalnewsletters: Periodic publications intended for internal distribution within an organization to share updates, news, and information.
        Announcements: Official statements or notifications shared within an organization to inform employees about important updates or events.
        Updatedigests: Summarized collections of updates or information, typically shared periodically within an organization.
        Executivebriefs: Concise documents or summaries prepared for executives, providing key information or updates on specific topics.
        Internalcommsartifacts: Documents or materials created for the purpose of internal communication within an organization, such as newsletters, announcements, or briefs.
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
        "Available connectors or source repositories (LLM note: Available connectors or source repositories (LLM note: Available connectors or source repositories))" connectors_or_source_repositories: List [text]
        "Optional format preferences" format_preferences: text
        "A draft communication artifact" draft_communication_artifact: text
        "A source/evidence set" source_evidence_set: text
        "A short assumptions log for any unresolved items (LLM note: A short assumptions log for any unresolved items (LLM note: A short assumptions log for any unresolved items))" assumptions_log: List [text]
        "A completion status" completion_status: text
    [END_VARIABLES]
    [DEFINE_WORKER: "To gather necessary external information and ensure its provenance is tracked." Worker_retrieve_sources]
        [INPUTS]
            OPTIONAL <REF>connectors_or_source_repositories</REF>
        [END_INPUTS]
        [OUTPUTS]
            REQUIRED <REF>source_evidence_set</REF>
        [END_OUTPUTS]
        [MAIN_FLOW]
            DECISION-1 [IF sources are needed and available]
                COMMAND-1 [COMMAND Retrieve sources using approved source recipes based on <REF>connectors_or_source_repositories</REF> RESULT source_evidence_set: text SET]
            [END_IF]
            [SEQUENTIAL_BLOCK]
                COMMAND-2 [COMMAND Maintain provenance for externally sourced facts based on <REF>source_evidence_set</REF> RESULT <REF>source_evidence_set</REF> SET]
            [END_SEQUENTIAL_BLOCK]
        [END_MAIN_FLOW]
    [END_WORKER]
    [DEFINE_WORKER: "To create an initial version of the communication artifact." Worker_produce_draft]
        [INPUTS]
            REQUIRED <REF>user_request</REF>
        [END_INPUTS]
        [OUTPUTS]
            REQUIRED <REF>draft_communication_artifact</REF>
        [END_OUTPUTS]
        [MAIN_FLOW]
            [SEQUENTIAL_BLOCK]
                COMMAND-3 [COMMAND Produce the draft communication artifact RESULT draft_communication_artifact: text SET]
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
                COMMAND-4 [COMMAND Determine what kind of communication is requested based on <REF>user_request</REF>]
                COMMAND-5 [COMMAND Identify which required fields are still missing based on <REF>user_request</REF>]
                COMMAND-6 [DISPLAY Ask the highest-value clarifying questions needed to move forward]
                COMMAND-7 [INVOKE Worker_retrieve_sources WITH <REF>connectors_or_source_repositories</REF> RESPONSE source_evidence_set: text SET]
                COMMAND-8 [INVOKE Worker_produce_draft WITH <REF>user_request</REF> RESPONSE draft_communication_artifact: text SET]
            [END_SEQUENTIAL_BLOCK]
        [END_MAIN_FLOW]
        [ALTERNATIVE_FLOW: the user asks for revision]
            [SEQUENTIAL_BLOCK]
                COMMAND-9 [COMMAND Revise while rechecking constraints based on <REF>draft_communication_artifact</REF> RESULT <REF>draft_communication_artifact</REF> SET]
            [END_SEQUENTIAL_BLOCK]
        [END_ALTERNATIVE_FLOW]
        [EXCEPTION_FLOW: Missing timeframe]
        [END_EXCEPTION_FLOW]
        [EXCEPTION_FLOW: Conflicting instructions]
        [END_EXCEPTION_FLOW]
        [EXCEPTION_FLOW: Insufficient source access]
        [END_EXCEPTION_FLOW]
        [EXCEPTION_FLOW: Evidence shortage]
        [END_EXCEPTION_FLOW]
        [EXCEPTION_FLOW: User refusal to answer]
        [END_EXCEPTION_FLOW]
        [EXCEPTION_FLOW: Provenance failure]
        [END_EXCEPTION_FLOW]
    [END_WORKER]
[END_AGENT]
```
