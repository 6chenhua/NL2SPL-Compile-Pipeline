# NL2SPL Feedback Report

## 1. Overall Compile State

- Completeness: `partial`
- SPL draft generated: `yes`
- Compile diagnostics: `28`
- Assumptions / suggestions: `4`
- Trace records: `31`
- Adapter warnings: `0`
- Validation errors: `0`
- Validation warnings: `10`

Result is partial because the following requirement gaps remain:
- `missing_handler` on `worker:worker_main.exception_flow:exc_adapter_00`: Exception flow 'exc_adapter_00' ('Communications lead unresponsive for over two days') has no handler step in worker 'worker_main'.
- `missing_handler` on `worker:worker_main.exception_flow:exc_adapter_01`: Exception flow 'exc_adapter_01' ('Template unavailable') has no handler step in worker 'worker_main'.
- `missing_handler` on `worker:worker_main.exception_flow:exc_adapter_02`: Exception flow 'exc_adapter_02' ('Topic summary too vague to draft from') has no handler step in worker 'worker_main'.
- `type_or_contract_ambiguity` on `delegation_intent:s22`: Delegation intent 'Initial drafting using template and topic summary' lacks a valid worker/API handoff contract.  No INVOKE_WORKER or CALL_API will be generated from this span.  [sec_delegation_policy/p_list_item_initial_drafting_using_template_and_topic_summary]

## 2. Materialized Source-Backed Structure

### Workers
- `worker:MainWorker` (direct) -- spans=s13, s14, s15; section=sec_reusable_process; packet=p_list_item_requestor_provides_topic_audience

### Flows
- `flow:exc_adapter_00` (direct) -- spans=s21; section=sec_failure_handling; packet=p_list_item_communications_lead_unresponsive_for_over_two_days
- `flow:exc_adapter_01` (direct) -- spans=s20; section=sec_failure_handling; packet=p_list_item_template_unavailable
- `flow:exc_adapter_02` (direct) -- spans=s19; section=sec_failure_handling; packet=p_list_item_topic_summary_too_vague_to_draft_from
- `flow:main` (direct) -- spans=s13, s14, s15; section=sec_reusable_process; packet=p_list_item_requestor_provides_topic_audience

### Steps
- `step:st_1` (direct) -- spans=s13; section=sec_reusable_process; packet=p_list_item_requestor_provides_topic_audience
- `step:st_2` (direct) -- spans=s14; section=sec_reusable_process; packet=p_list_item_ic_writer_drafts_using_the_standard_internal_communications_template_appendix_a_of_the_style_guide
- `step:st_3` (direct) -- spans=s15; section=sec_reusable_process; packet=p_list_item_routes_to_the_relevant_communications_lead_for_review

### Variables
- `variable:finished_draft_word_or_google_doc_200_500_words_no_approval_marks` (normalized) -- section=sec_required_outputs
- `variable:key_dates_or_deadlines` (normalized) -- section=sec_inputs_for_each_run
- `variable:status_flag_values_drafting_ready_for_review_approved` (direct) -- spans=s15; section=sec_reusable_process; packet=p_list_item_routes_to_the_relevant_communications_lead_for_review
- `variable:target_audience` (normalized) -- section=sec_inputs_for_each_run
- `variable:topic_summary` (normalized) -- section=sec_inputs_for_each_run
- `variable:worker_main_st_1_result_structured` (direct) -- spans=s13; section=sec_reusable_process; packet=p_list_item_requestor_provides_topic_audience
- `variable:worker_main_st_2_result_structured` (direct) -- spans=s14; section=sec_reusable_process; packet=p_list_item_ic_writer_drafts_using_the_standard_internal_communications_template_appendix_a_of_the_style_guide

### Constraints
- `constraint:c_1` (direct) -- spans=s16; section=sec_policies; packet=p_list_item_must_use_the_approved_template
- `constraint:c_2` (direct) -- spans=s17; section=sec_policies; packet=p_list_item_must_follow_plain_language_and_inclusive_tone_guidelines
- `constraint:c_3` (direct) -- spans=s18, s23; section=sec_policies; packet=p_list_item_require_final_sign_off_from_the_communications_lead_before_flagging_as_approved

### Other
- `profile:concept_0` (normalized)
- `profile:concept_1` (normalized)
- `profile:concept_10` (normalized)
- `profile:concept_11` (normalized)
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

- `worker:worker_main.exception_flow:exc_adapter_00`: `missing_handler` -- Exception flow 'exc_adapter_00' ('Communications lead unresponsive for over two days') has no handler step in worker 'worker_main'.
  - Suggested resolution: Add a handler step for 'Communications lead unresponsive for over two days', or mark this exception as acknowledged without handling.
- `worker:worker_main.exception_flow:exc_adapter_01`: `missing_handler` -- Exception flow 'exc_adapter_01' ('Template unavailable') has no handler step in worker 'worker_main'.
  - Suggested resolution: Add a handler step for 'Template unavailable', or mark this exception as acknowledged without handling.
- `worker:worker_main.exception_flow:exc_adapter_02`: `missing_handler` -- Exception flow 'exc_adapter_02' ('Topic summary too vague to draft from') has no handler step in worker 'worker_main'.
  - Suggested resolution: Add a handler step for 'Topic summary too vague to draft from', or mark this exception as acknowledged without handling.
- `delegation_intent:s22`: `type_or_contract_ambiguity` -- Delegation intent 'Initial drafting using template and topic summary' lacks a valid worker/API handoff contract.  No INVOKE_WORKER or CALL_API will be generated from this span.  [sec_delegation_policy/p_list_item_initial_drafting_using_template_and_topic_summary]

## 4. Diagnostics

### diag_post_norm_0000: `missing_handler`
- Severity: `warning`
- Target: `worker:worker_main.exception_flow:exc_adapter_00`
- Source spans: `s21`
- Message: Exception flow 'exc_adapter_00' ('Communications lead unresponsive for over two days') has no handler step in worker 'worker_main'.
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Add a handler step for 'Communications lead unresponsive for over two days', or mark this exception as acknowledged without handling.
- Missing slot: `handler_action`
- Missing reason: Exception flow 'exc_adapter_00' has condition but no handler step.

### diag_post_norm_0001: `missing_handler`
- Severity: `warning`
- Target: `worker:worker_main.exception_flow:exc_adapter_01`
- Source spans: `s20`
- Message: Exception flow 'exc_adapter_01' ('Template unavailable') has no handler step in worker 'worker_main'.
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Add a handler step for 'Template unavailable', or mark this exception as acknowledged without handling.
- Missing slot: `handler_action`
- Missing reason: Exception flow 'exc_adapter_01' has condition but no handler step.

### diag_post_norm_0002: `missing_handler`
- Severity: `warning`
- Target: `worker:worker_main.exception_flow:exc_adapter_02`
- Source spans: `s19`
- Message: Exception flow 'exc_adapter_02' ('Topic summary too vague to draft from') has no handler step in worker 'worker_main'.
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Add a handler step for 'Topic summary too vague to draft from', or mark this exception as acknowledged without handling.
- Missing slot: `handler_action`
- Missing reason: Exception flow 'exc_adapter_02' has condition but no handler step.

### diag_d10_0000: `type_or_contract_ambiguity`
- Severity: `warning`
- Target: `delegation_intent:s22`
- Source spans: `s22`
- Message: Delegation intent 'Initial drafting using template and topic summary' lacks a valid worker/API handoff contract.  No INVOKE_WORKER or CALL_API will be generated from this span.  [sec_delegation_policy/p_list_item_initial_drafting_using_template_and_topic_summary]
- Blocks rendering: `false`
- Blocks completion: `true`

### diag_rf_000: `route_refinement_corrected`
- Severity: `warning`
- Target: `stage2:field_route:s1`
- Source spans: `s1`
- Message: LLM refinement corrected: role 'profile_domain' requires route_family='profile', got None for span 's1'
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_rf_003: `route_refinement_corrected`
- Severity: `warning`
- Target: `stage2:field_route:s2`
- Source spans: `s2`
- Message: LLM refinement corrected: role 'profile_domain' requires route_family='profile', got None for span 's2'
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_rf_006: `route_refinement_corrected`
- Severity: `warning`
- Target: `stage2:field_route:s3`
- Source spans: `s3`
- Message: LLM refinement corrected: role 'profile_domain' requires route_family='profile', got None for span 's3'
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_rf_009: `route_refinement_corrected`
- Severity: `warning`
- Target: `stage2:field_route:s4`
- Source spans: `s4`
- Message: LLM refinement corrected: role 'profile_domain' requires route_family='profile', got None for span 's4'
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_rf_012: `route_refinement_corrected`
- Severity: `warning`
- Target: `stage2:field_route:s5`
- Source spans: `s5`
- Message: LLM refinement corrected: role 'profile_domain' requires route_family='profile', got None for span 's5'
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_rf_015: `route_refinement_corrected`
- Severity: `warning`
- Target: `stage2:field_route:s6`
- Source spans: `s6`
- Message: LLM refinement corrected: role 'profile_domain' requires route_family='profile', got None for span 's6'
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_rf_018: `route_refinement_corrected`
- Severity: `warning`
- Target: `stage2:field_route:s7`
- Source spans: `s7`
- Message: LLM refinement corrected: role 'profile_domain' requires route_family='profile', got None for span 's7'
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_rf_021: `route_refinement_corrected`
- Severity: `warning`
- Target: `stage2:field_route:s8`
- Source spans: `s8`
- Message: LLM refinement corrected: role 'input_contract' requires route_family='resource_contract', got None for span 's8'
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_rf_022: `route_refinement_corrected`
- Severity: `warning`
- Target: `stage2:field_route:s9`
- Source spans: `s9`
- Message: LLM refinement corrected: role 'input_contract' requires field='resources', got 'audience' for span 's9'
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_rf_024: `route_refinement_corrected`
- Severity: `warning`
- Target: `stage2:field_route:s10`
- Source spans: `s10`
- Message: LLM refinement corrected: role 'input_contract' requires route_family='resource_contract', got None for span 's10'
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_rf_025: `route_refinement_corrected`
- Severity: `warning`
- Target: `stage2:field_route:s11`
- Source spans: `s11`
- Message: LLM refinement corrected: role 'output_contract' requires route_family='resource_contract', got None for span 's11'
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_rf_026: `route_refinement_corrected`
- Severity: `warning`
- Target: `stage2:field_route:s12`
- Source spans: `s12`
- Message: LLM refinement corrected: role 'output_contract' requires route_family='resource_contract', got None for span 's12'
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_rf_027: `route_refinement_corrected`
- Severity: `warning`
- Target: `stage2:field_route:s13`
- Source spans: `s13`
- Message: LLM refinement corrected: role 'process_step' requires route_family='flow_relevant', got None for span 's13'
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_rf_030: `route_refinement_corrected`
- Severity: `warning`
- Target: `stage2:field_route:s14`
- Source spans: `s14`
- Message: LLM refinement corrected: role 'process_step' requires route_family='flow_relevant', got None for span 's14'
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_rf_033: `route_refinement_corrected`
- Severity: `warning`
- Target: `stage2:field_route:s15`
- Source spans: `s15`
- Message: LLM refinement corrected: role 'process_step' requires route_family='flow_relevant', got None for span 's15'
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_rf_036: `route_refinement_corrected`
- Severity: `warning`
- Target: `stage2:field_route:s16`
- Source spans: `s16`
- Message: LLM refinement corrected: role 'constraint' requires route_family='constraint', got None for span 's16'
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_rf_037: `route_refinement_corrected`
- Severity: `warning`
- Target: `stage2:field_route:s17`
- Source spans: `s17`
- Message: LLM refinement corrected: role 'constraint' requires route_family='constraint', got None for span 's17'
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_rf_038: `route_refinement_corrected`
- Severity: `warning`
- Target: `stage2:field_route:s18`
- Source spans: `s18`
- Message: LLM refinement corrected: role 'constraint' requires route_family='constraint', got None for span 's18'
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_rf_039: `route_refinement_corrected`
- Severity: `warning`
- Target: `stage2:field_route:s19`
- Source spans: `s19`
- Message: LLM refinement corrected: role 'failure_mode' requires route_family='flow_relevant', got None for span 's19'
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_rf_040: `route_refinement_corrected`
- Severity: `warning`
- Target: `stage2:field_route:s20`
- Source spans: `s20`
- Message: LLM refinement corrected: role 'failure_mode' requires route_family='flow_relevant', got None for span 's20'
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_rf_041: `route_refinement_corrected`
- Severity: `warning`
- Target: `stage2:field_route:s21`
- Source spans: `s21`
- Message: LLM refinement corrected: role 'failure_mode' requires route_family='flow_relevant', got None for span 's21'
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_rf_042: `route_refinement_corrected`
- Severity: `warning`
- Target: `stage2:field_route:s22`
- Source spans: `s22`
- Message: LLM refinement corrected: role 'delegation_intent' requires route_family='delegation_boundary', got None for span 's22'
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_rf_043: `route_refinement_corrected`
- Severity: `warning`
- Target: `stage2:field_route:s23`
- Source spans: `s23`
- Message: LLM refinement corrected: role 'delegation_prohibition' requires field='rules', got 'behavior' for span 's23'
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_rf_045: `route_refinement_diagnostic`
- Severity: `warning`
- Target: `stage2:field_route:`
- Message: LLM route diagnostic [prior_overridden] span='s2': Structural prior suggested behavior, but the text is domain/scoping content rather than an executable step.
- Blocks rendering: `false`
- Blocks completion: `false`

## 5. Assumptions / Suggestions

- `ASM_0000` for `worker:worker_main.exception_flow:exc_adapter_00`: Exception flow has no handler action. The compiler suggests specifying what should happen when this failure occurs.
  - Reason: Source describes a failure condition but does not specify how to handle it.  The exception flow is preserved in SPL, but no handler command was rendered. (Exception flow 'exc_adapter_00' ('Communications lead unresponsive for over two days') has no handler step in worker 'wo)
  - Suggested resolution: Specify the handler action for worker:worker_main.exception_flow:exc_adapter_00: e.g. ask the user for missing information, block finalization, or continue with an explicit assumption.
  - Related diagnostic: `diag_post_norm_0000`
- `ASM_0001` for `worker:worker_main.exception_flow:exc_adapter_01`: Exception flow has no handler action. The compiler suggests specifying what should happen when this failure occurs.
  - Reason: Source describes a failure condition but does not specify how to handle it.  The exception flow is preserved in SPL, but no handler command was rendered. (Exception flow 'exc_adapter_01' ('Template unavailable') has no handler step in worker 'worker_main'.)
  - Suggested resolution: Specify the handler action for worker:worker_main.exception_flow:exc_adapter_01: e.g. ask the user for missing information, block finalization, or continue with an explicit assumption.
  - Related diagnostic: `diag_post_norm_0001`
- `ASM_0002` for `worker:worker_main.exception_flow:exc_adapter_02`: Exception flow has no handler action. The compiler suggests specifying what should happen when this failure occurs.
  - Reason: Source describes a failure condition but does not specify how to handle it.  The exception flow is preserved in SPL, but no handler command was rendered. (Exception flow 'exc_adapter_02' ('Topic summary too vague to draft from') has no handler step in worker 'worker_main'.)
  - Suggested resolution: Specify the handler action for worker:worker_main.exception_flow:exc_adapter_02: e.g. ask the user for missing information, block finalization, or continue with an explicit assumption.
  - Related diagnostic: `diag_post_norm_0002`
- `ASM_0003` for `delegation_intent:s22`: Command has an ambiguous or incomplete contract. The compiler suggests providing the missing contract detail.
  - Reason: A command references an API, worker, or input source that is not fully specified.  The compiler cannot materialize the command without this information.
  - Suggested resolution: For delegation_intent:s22: provide the missing contract detail (API name, worker target, IO bindings, or source evidence).  See the related diagnostic for specifics.
  - Related diagnostic: `diag_d10_0000`

## 6. Provenance / TraceRecords

- `constraint:c_1` -> `direct`
  - Source: spans=`s16`, section=`sec_policies`, packet=`p_list_item_must_use_the_approved_template`
  - Explanation: Constraint 'c_1' (requirement): Must use the approved template
- `constraint:c_2` -> `direct`
  - Source: spans=`s17`, section=`sec_policies`, packet=`p_list_item_must_follow_plain_language_and_inclusive_tone_guidelines`
  - Explanation: Constraint 'c_2' (requirement): Must follow plain-language and inclusive tone guidelines
- `constraint:c_3` -> `direct`
  - Source: spans=`s18, s23`, section=`sec_policies`, packet=`p_list_item_require_final_sign_off_from_the_communications_lead_before_flagging_as_approved`
  - Explanation: Constraint 'c_3' (approval): Require final sign-off from the communications lead before flagging as approved
- `flow:exc_adapter_00` -> `direct`
  - Source: spans=`s21`, section=`sec_failure_handling`, packet=`p_list_item_communications_lead_unresponsive_for_over_two_days`
  - Explanation: Exception flow 'exc_adapter_00': Communications lead unresponsive for over two days
- `flow:exc_adapter_01` -> `direct`
  - Source: spans=`s20`, section=`sec_failure_handling`, packet=`p_list_item_template_unavailable`
  - Explanation: Exception flow 'exc_adapter_01': Template unavailable
- `flow:exc_adapter_02` -> `direct`
  - Source: spans=`s19`, section=`sec_failure_handling`, packet=`p_list_item_topic_summary_too_vague_to_draft_from`
  - Explanation: Exception flow 'exc_adapter_02': Topic summary too vague to draft from
- `flow:main` -> `direct`
  - Source: spans=`s13, s14, s15`, section=`sec_reusable_process`, packet=`p_list_item_requestor_provides_topic_audience`
  - Explanation: Main flow with 1 block(s).
- `profile:concept_0` -> `normalized`
  - Explanation: Concept: Internal communications drafting -- The creation of internal company communications such as newsletters, announcements, update digests, and executive briefs.
- `profile:concept_1` -> `normalized`
  - Explanation: Concept: Recurring digests -- Regularly scheduled summary communications that compile updates over time.
- `profile:concept_10` -> `normalized`
  - Explanation: Concept: Inclusive tone guidelines -- Guidelines for writing in a respectful, inclusive manner.
- `profile:concept_11` -> `normalized`
  - Explanation: Concept: Status flag -- A field indicating workflow state, with values such as drafting, ready for review, or approved.
- `profile:concept_2` -> `normalized`
  - Explanation: Concept: Executive memos -- Internal memoranda intended for executive-level readers.
- `profile:concept_3` -> `normalized`
  - Explanation: Concept: Crisis communications -- Urgent communications used during a crisis; explicitly out of scope for this task family.
- `profile:concept_4` -> `normalized`
  - Explanation: Concept: Internal newsletters -- Newsletter-style communications distributed within the organization.
- `profile:concept_5` -> `normalized`
  - Explanation: Concept: Update digests -- Brief summary updates that collect recent information into a digest format.
- `profile:concept_6` -> `normalized`
  - Explanation: Concept: Executive briefs -- Concise briefing documents prepared for executives.
- `profile:concept_7` -> `normalized`
  - Explanation: Concept: Communications lead -- The person responsible for reviewing the draft and providing final sign-off.
- `profile:concept_8` -> `normalized`
  - Explanation: Concept: Approved template -- The required standard document format that must be used for drafting.
- `profile:concept_9` -> `normalized`
  - Explanation: Concept: Plain-language guidelines -- Rules requiring clear, simple wording that is easy to understand.
- `profile:persona` -> `inferred`
  - Explanation: Persona: Internal communications drafting specialist
- `step:st_1` -> `direct`
  - Source: spans=`s13`, section=`sec_reusable_process`, packet=`p_list_item_requestor_provides_topic_audience`
  - Explanation: Step 'st_1' maps to source span(s).
- `step:st_2` -> `direct`
  - Source: spans=`s14`, section=`sec_reusable_process`, packet=`p_list_item_ic_writer_drafts_using_the_standard_internal_communications_template_appendix_a_of_the_style_guide`
  - Explanation: Step 'st_2' maps to source span(s).
- `step:st_3` -> `direct`
  - Source: spans=`s15`, section=`sec_reusable_process`, packet=`p_list_item_routes_to_the_relevant_communications_lead_for_review`
  - Explanation: Step 'st_3' maps to source span(s).
- `variable:finished_draft_word_or_google_doc_200_500_words_no_approval_marks` -> `normalized`
  - Source: section=`sec_required_outputs`
  - Explanation: Variable 'finished_draft_word_or_google_doc_200_500_words_no_approval_marks' is declared by adapter hard fact in section 'sec_required_outputs'.
- `variable:key_dates_or_deadlines` -> `normalized`
  - Source: section=`sec_inputs_for_each_run`
  - Explanation: Variable 'key_dates_or_deadlines' is declared by adapter hard fact in section 'sec_inputs_for_each_run'.
- `variable:status_flag_values_drafting_ready_for_review_approved` -> `direct`
  - Source: spans=`s15`, section=`sec_reusable_process`, packet=`p_list_item_routes_to_the_relevant_communications_lead_for_review`
  - Explanation: Variable 'status_flag_values_drafting_ready_for_review_approved' is produced by source-backed step 'st_3'.
- `variable:target_audience` -> `normalized`
  - Source: section=`sec_inputs_for_each_run`
  - Explanation: Variable 'target_audience' is declared by adapter hard fact in section 'sec_inputs_for_each_run'.
- `variable:topic_summary` -> `normalized`
  - Source: section=`sec_inputs_for_each_run`
  - Explanation: Variable 'topic_summary' is declared by adapter hard fact in section 'sec_inputs_for_each_run'.
- `variable:worker_main_st_1_result_structured` -> `direct`
  - Source: spans=`s13`, section=`sec_reusable_process`, packet=`p_list_item_requestor_provides_topic_audience`
  - Explanation: Variable 'worker_main_st_1_result_structured' is produced by source-backed step 'st_1'.
- `variable:worker_main_st_2_result_structured` -> `direct`
  - Source: spans=`s14`, section=`sec_reusable_process`, packet=`p_list_item_ic_writer_drafts_using_the_standard_internal_communications_template_appendix_a_of_the_style_guide`
  - Explanation: Variable 'worker_main_st_2_result_structured' is produced by source-backed step 'st_2'.
- `worker:MainWorker` -> `direct`
  - Source: spans=`s13, s14, s15`, section=`sec_reusable_process`, packet=`p_list_item_requestor_provides_topic_audience`
  - Explanation: Main worker 'MainWorker' assembled from flow and step IRs.

## 7. Anti-Fabrication Checks

- `missing_handler`: Exception conditions without handler action stay as partial exception flows; no handler command is invented.
- `type_or_contract_ambiguity`: Unresolved worker/API contracts are reported as ambiguity; they are not downgraded to generic commands.
- Rendered SPL contains no executable `[INVOKE ...]` command.

## 8. Adapter / Validation Notes

Validation warnings:
- ConstructPlan: condition span s21 for exc_demand_00 has unowned; attached to main worker worker_main.
- ConstructPlan: condition span s20 for exc_demand_01 has unowned; attached to main worker worker_main.
- ConstructPlan: condition span s19 for exc_demand_02 has unowned; attached to main worker worker_main.
- ConstructPlan: condition span s21 for exc_demand_00 has unowned; attached to main worker worker_main.
- ConstructPlan: condition span s20 for exc_demand_01 has unowned; attached to main worker worker_main.
- ConstructPlan: condition span s19 for exc_demand_02 has unowned; attached to main worker worker_main.
- Aggregated multi-output step st_1 into worker_main_st_1_result_structured without unpack steps.
- Aggregated multi-output step st_2 into worker_main_st_2_result_structured without unpack steps.
- Unused variable declared: finished_draft_word_or_google_doc_200_500_words_no_approval_marks
- Unused variable declared: status_flag_values_drafting_ready_for_review_approved

## 9. SPL Draft

```spl
[DEFINE_AGENT: MainWorker "Orchestrate the end-to-end process and delegate to sub-tasks."]
    [DEFINE_PERSONA:]
        ROLE: Internal communications drafting specialist
        TemplateDriven: Uses the approved internal communications template and follows the standard style guide.
        PlainLanguageFocused: Writes using plain-language and inclusive tone guidelines.
        ReviewOriented: Routes drafts to the relevant communications lead for review and waits for final sign-off before approval.
    [END_PERSONA]
    [DEFINE_CONCEPTS:]
        Internalcommunicationsdrafting: The creation of internal company communications such as newsletters, announcements, update digests, and executive briefs.
        Recurringdigests: Regularly scheduled summary communications that compile updates over time.
        Executivememos: Internal memoranda intended for executive-level readers.
        Crisiscommunications: Urgent communications used during a crisis; explicitly out of scope for this task family.
        Internalnewsletters: Newsletter-style communications distributed within the organization.
        Updatedigests: Brief summary updates that collect recent information into a digest format.
        Executivebriefs: Concise briefing documents prepared for executives.
        Communicationslead: The person responsible for reviewing the draft and providing final sign-off.
        Approvedtemplate: The required standard document format that must be used for drafting.
        Plainlanguageguidelines: Rules requiring clear, simple wording that is easy to understand.
        Inclusivetoneguidelines: Guidelines for writing in a respectful, inclusive manner.
        Statusflag: A field indicating workflow state, with values such as drafting, ready for review, or approved.
    [END_CONCEPTS]
    [DEFINE_CONSTRAINTS:]
        Requirement: Must use the approved template
        Requirement: Must follow plain-language and inclusive tone guidelines
        Approval: Require final sign-off from the communications lead before flagging as approved
    [END_CONSTRAINTS]
    [DEFINE_VARIABLES:]
        "Topic summary" topic_summary: text
        "Target audience" target_audience: text
        "Key dates or deadlines" key_dates_or_deadlines: text
        "Finished draft word or google doc 200 500 words no approval marks" finished_draft_word_or_google_doc_200_500_words_no_approval_marks: text
        "Status flag (values: `'drafting'`, `'ready for review'`, `'approved'`)" status_flag_values_drafting_ready_for_review_approved: text
        "Structured result for st_1." worker_main_st_1_result_structured: worker_main_st_1_result_structured_type
        "Structured result for st_2." worker_main_st_2_result_structured: worker_main_st_2_result_structured_type
    [END_VARIABLES]
    [DEFINE_TYPES:]
        worker_main_st_1_result_structured_type = { topic_summary: text, target_audience: text }
        worker_main_st_2_result_structured_type = { finished_draft_word_or_google_doc_200_500_words_no_approval_marks: text, status_flag_values_drafting_ready_for_review_approved: text }
    [END_TYPES]
    [DEFINE_WORKER: "Orchestrate the end-to-end process and delegate to sub-tasks." MainWorker]
        [INPUTS]
            REQUIRED <REF>topic_summary</REF>
            REQUIRED <REF>target_audience</REF>
            REQUIRED <REF>key_dates_or_deadlines</REF>
        [END_INPUTS]
        [OUTPUTS]
            REQUIRED <REF>worker_main_st_2_result_structured</REF>
        [END_OUTPUTS]
        [MAIN_FLOW]
            [SEQUENTIAL_BLOCK]
                COMMAND-1 [INPUT Receive topic and audience information VALUE worker_main_st_1_result_structured: worker_main_st_1_result_structured_type SET]
                COMMAND-2 [COMMAND Draft the internal communications message using the standard template based on <REF>worker_main_st_1_result_structured</REF> RESULT worker_main_st_2_result_structured: worker_main_st_2_result_structured_type SET]
                COMMAND-3 [COMMAND Route the draft to the relevant communications lead for review based on <REF>worker_main_st_2_result_structured</REF> RESULT status_flag_values_drafting_ready_for_review_approved: text SET]
            [END_SEQUENTIAL_BLOCK]
        [END_MAIN_FLOW]
        [EXCEPTION_FLOW: Communications lead unresponsive for over two days]
        [END_EXCEPTION_FLOW]
        [EXCEPTION_FLOW: Template unavailable]
        [END_EXCEPTION_FLOW]
        [EXCEPTION_FLOW: Topic summary too vague to draft from]
        [END_EXCEPTION_FLOW]
    [END_WORKER]
[END_AGENT]
```
