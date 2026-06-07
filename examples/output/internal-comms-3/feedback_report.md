# NL2SPL Feedback Report

## 1. Overall Compile State

- Completeness: `partial`
- SPL draft generated: `yes`
- Compile diagnostics: `23`
- Assumptions / suggestions: `17`
- Trace records: `47`
- Adapter warnings: `10`
- Validation errors: `0`
- Validation warnings: `4`

Result is partial because the following requirement gaps remain:
- `missing_handler` on `worker:worker_main.exception_flow:exc_adapter_01`: Exception flow 'exc_adapter_01' ('- missing inputs') has no handler step in worker 'worker_main'.
- `missing_handler` on `worker:worker_main.exception_flow:exc_adapter_01`: Exception flow 'exc_adapter_01' ('policy violations') has no handler step in worker 'worker_main'.
- `missing_handler` on `worker:worker_main.exception_flow:exc_adapter_02`: Exception flow 'exc_adapter_02' ('template mismatches') has no handler step in worker 'worker_main'.
- `missing_handler` on `worker:worker_main.exception_flow:exc_adapter_03`: Exception flow 'exc_adapter_03' ('tone mismatches') has no handler step in worker 'worker_main'.
- `missing_handler` on `worker:worker_main.exception_flow:exc_adapter_04`: Exception flow 'exc_adapter_04' ('unverified facts') has no handler step in worker 'worker_main'.
- `missing_handler` on `worker:worker_main.exception_flow:exc_adapter_05`: Exception flow 'exc_adapter_05' ('approval gaps') has no handler step in worker 'worker_main'.
- `missing_output_producer` on `worker:worker_main.output:assumptions_log`: Required output 'assumptions_log' (Assumptions log) has no source-backed producer step.
- `type_or_contract_ambiguity` on `delegation_intent:s24`: Delegation intent '- Initial drafting' lacks a valid worker/API handoff contract.  No INVOKE_WORKER or CALL_API will be generated from this span.  [sec_delegation_policy/p_list_item_initial_drafting]
- `type_or_contract_ambiguity` on `delegation_intent:s25`: Delegation intent 'approvals' lacks a valid worker/API handoff contract.  No INVOKE_WORKER or CALL_API will be generated from this span.  [sec_-_**non-delegable_work/p_list_item_approvals]
- `type_or_contract_ambiguity` on `delegation_intent:s24`: Delegation intent '- Initial drafting' lacks a valid worker/API handoff contract.  No INVOKE_WORKER or CALL_API will be generated from this span.  [sec_delegation_policy/p_list_item_initial_drafting]
- `type_or_contract_ambiguity` on `worker_promotion:candidate_prepare_internal_comm_draft`: Missing clear output contract [construct=worker_promotion:candidate_prepare_internal_comm_draft, slot=promotion_output_contract]
- `type_or_contract_ambiguity` on `worker_promotion:candidate_select_approved_template`: Missing clear output contract [construct=worker_promotion:candidate_select_approved_template, slot=promotion_output_contract]
- `type_or_contract_ambiguity` on `worker_promotion:candidate_prepare_internal_comm_draft`: Missing clear input contract [construct=worker_promotion:candidate_prepare_internal_comm_draft, slot=promotion_input_contract]
- `type_or_contract_ambiguity` on `worker_promotion:candidate_prepare_internal_comm_draft`: Missing matching handoff with output bindings [construct=worker_promotion:candidate_prepare_internal_comm_draft, slot=promotion_result_handoff]
- `type_or_contract_ambiguity` on `worker_promotion:candidate_select_approved_template`: Missing matching handoff with output bindings [construct=worker_promotion:candidate_select_approved_template, slot=promotion_result_handoff]
- `type_or_contract_ambiguity` on `worker_promotion:candidate_prepare_internal_comm_draft`: Missing accepted decision or matching handoff with invocation hint [construct=worker_promotion:candidate_prepare_internal_comm_draft, slot=promotion_invocation_point]
- `type_or_contract_ambiguity` on `worker_promotion:candidate_select_approved_template`: Missing accepted decision or matching handoff with invocation hint [construct=worker_promotion:candidate_select_approved_template, slot=promotion_invocation_point]

## 2. Materialized Source-Backed Structure

### Workers
- `worker:MainWorker` (direct) -- spans=s13, s14, s15, s16, s17, s18, s19, s20, s23, s24, s25; section=sec_reusable_process; packet=p_list_item_identify_audience_and_key_messages

### Flows
- `flow:exc_adapter_01` (direct) -- spans=s23; section=sec_failure_handling; packet=p_list_item_missing_inputs
- `flow:exc_adapter_01` (direct) -- spans=s23; section=sec_failure_handling; packet=p_list_item_missing_inputs
- `flow:exc_adapter_02` (direct) -- spans=s23; section=sec_failure_handling; packet=p_list_item_missing_inputs
- `flow:exc_adapter_03` (direct) -- spans=s23; section=sec_failure_handling; packet=p_list_item_missing_inputs
- `flow:exc_adapter_04` (direct) -- spans=s23; section=sec_failure_handling; packet=p_list_item_missing_inputs
- `flow:exc_adapter_05` (direct) -- spans=s23; section=sec_failure_handling; packet=p_list_item_missing_inputs
- `flow:main` (direct) -- spans=s13, s14, s15, s16, s17, s18, s19, s20, s24, s25; section=sec_reusable_process; packet=p_list_item_identify_audience_and_key_messages

### Steps
- `step:st_1` (direct) -- spans=s13; section=sec_reusable_process; packet=p_list_item_identify_audience_and_key_messages
- `step:st_2` (direct) -- spans=s14; section=sec_reusable_process; packet=p_list_item_select_approved_template
- `step:st_3` (direct) -- spans=s15; section=sec_reusable_process; packet=p_list_item_gather_source_materials
- `step:st_4` (direct) -- spans=s16; section=sec_reusable_process; packet=p_list_item_draft_content
- `step:st_5` (direct) -- spans=s17; section=sec_reusable_process; packet=p_list_item_review_for_tone_and_policy_compliance
- `step:st_6` (direct) -- spans=s18; section=sec_reusable_process; packet=p_list_item_insert_disclaimers_citations
- `step:st_7` (direct) -- spans=s19; section=sec_reusable_process; packet=p_list_item_attach_revision_history_and_evidence_trail
- `step:st_8` (direct) -- spans=s20; section=sec_reusable_process; packet=p_list_item_flag_readiness

### Variables
- `variable:assumptions_log` (normalized) -- section=sec_required_outputs
- `variable:evidence_trail` (normalized) -- section=sec_required_outputs
- `variable:final_draft` (direct) -- spans=s16; section=sec_reusable_process; packet=p_list_item_draft_content
- `variable:key_messages` (normalized) -- section=sec_inputs_for_each_run
- `variable:readiness_status_flag` (direct) -- spans=s20; section=sec_reusable_process; packet=p_list_item_flag_readiness
- `variable:revision_history` (normalized) -- section=sec_required_outputs
- `variable:target_audience` (normalized) -- section=sec_inputs_for_each_run
- `variable:template_selection` (normalized) -- section=sec_-_**optional
- `variable:tone` (normalized) -- section=sec_inputs_for_each_run
- `variable:topic` (normalized) -- section=sec_inputs_for_each_run
- `variable:worker_main_st_6_result_structured` (direct) -- spans=s18; section=sec_reusable_process; packet=p_list_item_insert_disclaimers_citations
- `variable:worker_main_st_7_result_structured` (direct) -- spans=s19; section=sec_reusable_process; packet=p_list_item_attach_revision_history_and_evidence_trail

### Constraints
- `constraint:c_1` (direct) -- spans=s4; section=sec_-_**scope; packet=p_list_item_routine_newsletters_exclude_sensitive_executive_messages_and_crisis_communications
- `constraint:c_2` (direct) -- spans=s22; section=sec_policies; packet=p_list_item_no_external_data

### Delegation Intents
- `delegation_intent:initial_drafting` (inferred) -- spans=s24; section=sec_delegation_policy

### Other
- `profile:audience_0` (inferred)
- `profile:audience_1` (inferred)
- `profile:concept_0` (normalized)
- `profile:concept_1` (normalized)
- `profile:concept_10` (normalized)
- `profile:concept_11` (normalized)
- `profile:concept_12` (normalized)
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

- `worker:worker_main.exception_flow:exc_adapter_01`: `missing_handler` -- Exception flow 'exc_adapter_01' ('- missing inputs') has no handler step in worker 'worker_main'.
  - Suggested resolution: Add a handler step for '- missing inputs', or mark this exception as acknowledged without handling.
- `worker:worker_main.exception_flow:exc_adapter_01`: `missing_handler` -- Exception flow 'exc_adapter_01' ('policy violations') has no handler step in worker 'worker_main'.
  - Suggested resolution: Add a handler step for 'policy violations', or mark this exception as acknowledged without handling.
- `worker:worker_main.exception_flow:exc_adapter_02`: `missing_handler` -- Exception flow 'exc_adapter_02' ('template mismatches') has no handler step in worker 'worker_main'.
  - Suggested resolution: Add a handler step for 'template mismatches', or mark this exception as acknowledged without handling.
- `worker:worker_main.exception_flow:exc_adapter_03`: `missing_handler` -- Exception flow 'exc_adapter_03' ('tone mismatches') has no handler step in worker 'worker_main'.
  - Suggested resolution: Add a handler step for 'tone mismatches', or mark this exception as acknowledged without handling.
- `worker:worker_main.exception_flow:exc_adapter_04`: `missing_handler` -- Exception flow 'exc_adapter_04' ('unverified facts') has no handler step in worker 'worker_main'.
  - Suggested resolution: Add a handler step for 'unverified facts', or mark this exception as acknowledged without handling.
- `worker:worker_main.exception_flow:exc_adapter_05`: `missing_handler` -- Exception flow 'exc_adapter_05' ('approval gaps') has no handler step in worker 'worker_main'.
  - Suggested resolution: Add a handler step for 'approval gaps', or mark this exception as acknowledged without handling.
- `worker:worker_main.output:assumptions_log`: `missing_output_producer` -- Required output 'assumptions_log' (Assumptions log) has no source-backed producer step.
  - Suggested resolution: Add a step that produces 'assumptions_log', e.g. 'Record assumptions for unresolved items'. If the source requirement does not specify how to produce this output, mark it as optional or remove it from the output contract.
- `delegation_intent:s24`: `type_or_contract_ambiguity` -- Delegation intent '- Initial drafting' lacks a valid worker/API handoff contract.  No INVOKE_WORKER or CALL_API will be generated from this span.  [sec_delegation_policy/p_list_item_initial_drafting]
- `delegation_intent:s25`: `type_or_contract_ambiguity` -- Delegation intent 'approvals' lacks a valid worker/API handoff contract.  No INVOKE_WORKER or CALL_API will be generated from this span.  [sec_-_**non-delegable_work/p_list_item_approvals]
- `delegation_intent:s24`: `type_or_contract_ambiguity` -- Delegation intent '- Initial drafting' lacks a valid worker/API handoff contract.  No INVOKE_WORKER or CALL_API will be generated from this span.  [sec_delegation_policy/p_list_item_initial_drafting]
- `worker_promotion:candidate_prepare_internal_comm_draft`: `type_or_contract_ambiguity` -- Missing clear output contract [construct=worker_promotion:candidate_prepare_internal_comm_draft, slot=promotion_output_contract]
- `worker_promotion:candidate_select_approved_template`: `type_or_contract_ambiguity` -- Missing clear output contract [construct=worker_promotion:candidate_select_approved_template, slot=promotion_output_contract]
- `worker_promotion:candidate_prepare_internal_comm_draft`: `type_or_contract_ambiguity` -- Missing clear input contract [construct=worker_promotion:candidate_prepare_internal_comm_draft, slot=promotion_input_contract]
- `worker_promotion:candidate_prepare_internal_comm_draft`: `type_or_contract_ambiguity` -- Missing matching handoff with output bindings [construct=worker_promotion:candidate_prepare_internal_comm_draft, slot=promotion_result_handoff]
- `worker_promotion:candidate_select_approved_template`: `type_or_contract_ambiguity` -- Missing matching handoff with output bindings [construct=worker_promotion:candidate_select_approved_template, slot=promotion_result_handoff]
- `worker_promotion:candidate_prepare_internal_comm_draft`: `type_or_contract_ambiguity` -- Missing accepted decision or matching handoff with invocation hint [construct=worker_promotion:candidate_prepare_internal_comm_draft, slot=promotion_invocation_point]
- `worker_promotion:candidate_select_approved_template`: `type_or_contract_ambiguity` -- Missing accepted decision or matching handoff with invocation hint [construct=worker_promotion:candidate_select_approved_template, slot=promotion_invocation_point]

## 4. Diagnostics

### diag_post_norm_0000: `missing_handler`
- Severity: `warning`
- Target: `worker:worker_main.exception_flow:exc_adapter_01`
- Source spans: `s23, s23`
- Message: Exception flow 'exc_adapter_01' ('- missing inputs') has no handler step in worker 'worker_main'.
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Add a handler step for '- missing inputs', or mark this exception as acknowledged without handling.

### diag_post_norm_0001: `missing_handler`
- Severity: `warning`
- Target: `worker:worker_main.exception_flow:exc_adapter_01`
- Source spans: `s23, s23`
- Message: Exception flow 'exc_adapter_01' ('policy violations') has no handler step in worker 'worker_main'.
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Add a handler step for 'policy violations', or mark this exception as acknowledged without handling.

### diag_post_norm_0002: `missing_handler`
- Severity: `warning`
- Target: `worker:worker_main.exception_flow:exc_adapter_02`
- Source spans: `s23`
- Message: Exception flow 'exc_adapter_02' ('template mismatches') has no handler step in worker 'worker_main'.
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Add a handler step for 'template mismatches', or mark this exception as acknowledged without handling.

### diag_post_norm_0003: `missing_handler`
- Severity: `warning`
- Target: `worker:worker_main.exception_flow:exc_adapter_03`
- Source spans: `s23`
- Message: Exception flow 'exc_adapter_03' ('tone mismatches') has no handler step in worker 'worker_main'.
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Add a handler step for 'tone mismatches', or mark this exception as acknowledged without handling.

### diag_post_norm_0004: `missing_handler`
- Severity: `warning`
- Target: `worker:worker_main.exception_flow:exc_adapter_04`
- Source spans: `s23`
- Message: Exception flow 'exc_adapter_04' ('unverified facts') has no handler step in worker 'worker_main'.
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Add a handler step for 'unverified facts', or mark this exception as acknowledged without handling.

### diag_post_norm_0005: `missing_handler`
- Severity: `warning`
- Target: `worker:worker_main.exception_flow:exc_adapter_05`
- Source spans: `s23`
- Message: Exception flow 'exc_adapter_05' ('approval gaps') has no handler step in worker 'worker_main'.
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Add a handler step for 'approval gaps', or mark this exception as acknowledged without handling.

### diag_post_norm_0006: `missing_output_producer`
- Severity: `warning`
- Target: `worker:worker_main.output:assumptions_log`
- Message: Required output 'assumptions_log' (Assumptions log) has no source-backed producer step.
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Add a step that produces 'assumptions_log', e.g. 'Record assumptions for unresolved items'. If the source requirement does not specify how to produce this output, mark it as optional or remove it from the output contract.

### diag_d10_0000: `type_or_contract_ambiguity`
- Severity: `warning`
- Target: `delegation_intent:s24`
- Source spans: `s24`
- Message: Delegation intent '- Initial drafting' lacks a valid worker/API handoff contract.  No INVOKE_WORKER or CALL_API will be generated from this span.  [sec_delegation_policy/p_list_item_initial_drafting]
- Blocks rendering: `false`
- Blocks completion: `true`

### diag_d10_0001: `type_or_contract_ambiguity`
- Severity: `warning`
- Target: `delegation_intent:s25`
- Source spans: `s25`
- Message: Delegation intent 'approvals' lacks a valid worker/API handoff contract.  No INVOKE_WORKER or CALL_API will be generated from this span.  [sec_-_**non-delegable_work/p_list_item_approvals]
- Blocks rendering: `false`
- Blocks completion: `true`

### diag_d10_0002: `type_or_contract_ambiguity`
- Severity: `warning`
- Target: `delegation_intent:s24`
- Source spans: `s24`
- Message: Delegation intent '- Initial drafting' lacks a valid worker/API handoff contract.  No INVOKE_WORKER or CALL_API will be generated from this span.  [sec_delegation_policy/p_list_item_initial_drafting]
- Blocks rendering: `false`
- Blocks completion: `true`

### irs_2444e5a5c547: `type_or_contract_ambiguity`
- Severity: `warning`
- Target: `worker_promotion:candidate_prepare_internal_comm_draft`
- Source spans: `s13, s15, s16, s17, s18, s19, s20`
- Message: Missing clear output contract [construct=worker_promotion:candidate_prepare_internal_comm_draft, slot=promotion_output_contract]
- Blocks rendering: `true`
- Blocks completion: `true`
- Missing slot: `promotion_output_contract`
- Missing reason: Missing clear output contract

### irs_4767aada0c3b: `type_or_contract_ambiguity`
- Severity: `warning`
- Target: `worker_promotion:candidate_select_approved_template`
- Source spans: `s14`
- Message: Missing clear output contract [construct=worker_promotion:candidate_select_approved_template, slot=promotion_output_contract]
- Blocks rendering: `true`
- Blocks completion: `true`
- Missing slot: `promotion_output_contract`
- Missing reason: Missing clear output contract

### irs_4789433061ec: `type_or_contract_ambiguity`
- Severity: `warning`
- Target: `worker_promotion:candidate_prepare_internal_comm_draft`
- Source spans: `s13, s15, s16, s17, s18, s19, s20`
- Message: Missing clear input contract [construct=worker_promotion:candidate_prepare_internal_comm_draft, slot=promotion_input_contract]
- Blocks rendering: `true`
- Blocks completion: `true`
- Missing slot: `promotion_input_contract`
- Missing reason: Missing clear input contract

### irs_839fb9f649c0: `type_or_contract_ambiguity`
- Severity: `warning`
- Target: `worker_promotion:candidate_prepare_internal_comm_draft`
- Source spans: `s13, s15, s16, s17, s18, s19, s20`
- Message: Missing matching handoff with output bindings [construct=worker_promotion:candidate_prepare_internal_comm_draft, slot=promotion_result_handoff]
- Blocks rendering: `true`
- Blocks completion: `true`
- Missing slot: `promotion_result_handoff`
- Missing reason: Missing matching handoff with output bindings

### irs_a4385a7dba3c: `type_or_contract_ambiguity`
- Severity: `warning`
- Target: `worker_promotion:candidate_select_approved_template`
- Source spans: `s14`
- Message: Missing matching handoff with output bindings [construct=worker_promotion:candidate_select_approved_template, slot=promotion_result_handoff]
- Blocks rendering: `true`
- Blocks completion: `true`
- Missing slot: `promotion_result_handoff`
- Missing reason: Missing matching handoff with output bindings

### irs_cf49c448d747: `type_or_contract_ambiguity`
- Severity: `warning`
- Target: `worker_promotion:candidate_prepare_internal_comm_draft`
- Source spans: `s13, s15, s16, s17, s18, s19, s20`
- Message: Missing accepted decision or matching handoff with invocation hint [construct=worker_promotion:candidate_prepare_internal_comm_draft, slot=promotion_invocation_point]
- Blocks rendering: `true`
- Blocks completion: `true`
- Missing slot: `promotion_invocation_point`
- Missing reason: Missing accepted decision or matching handoff with invocation hint

### irs_d2b05c5a69a7: `type_or_contract_ambiguity`
- Severity: `warning`
- Target: `worker_promotion:candidate_select_approved_template`
- Source spans: `s14`
- Message: Missing accepted decision or matching handoff with invocation hint [construct=worker_promotion:candidate_select_approved_template, slot=promotion_invocation_point]
- Blocks rendering: `true`
- Blocks completion: `true`
- Missing slot: `promotion_invocation_point`
- Missing reason: Missing accepted decision or matching handoff with invocation hint

### diag_rf_000: `route_refinement_diagnostic`
- Severity: `warning`
- Target: `stage2:field_route:`
- Message: LLM route diagnostic [prior_overridden] span='s2': Prior labeled this as profile_domain, but the text is a scope constraint about inclusion.
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_rf_001: `route_refinement_diagnostic`
- Severity: `warning`
- Target: `stage2:field_route:`
- Message: LLM route diagnostic [prior_overridden] span='s3': Prior labeled this as profile_domain, but the text is a scope constraint about inclusion.
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_rf_002: `route_refinement_diagnostic`
- Severity: `warning`
- Target: `stage2:field_route:`
- Message: LLM route diagnostic [prior_overridden] span='s4': Prior labeled this as constraint; refined to a scope boundary constraint over allowed and excluded content.
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_rf_003: `route_refinement_diagnostic`
- Severity: `warning`
- Target: `stage2:field_route:`
- Message: LLM route diagnostic [prior_confirmed] span='s23': Failure condition matches the prior.
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_rf_004: `route_refinement_diagnostic`
- Severity: `warning`
- Target: `stage2:field_route:`
- Message: LLM route diagnostic [prior_overridden] span='s24': Prior labeled this as delegation_intent under a boundary family; normalized to the allowed WORKER_HANDOFF construct with non-executable intent semantics.
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_rf_005: `route_refinement_diagnostic`
- Severity: `warning`
- Target: `stage2:field_route:`
- Message: LLM route diagnostic [prior_overridden] span='s25': Prior labeled this as delegation_intent, but the text is a prohibition on delegating approvals.
- Blocks rendering: `false`
- Blocks completion: `false`

## 5. Assumptions / Suggestions

- `ASM_0000` for `worker_promotion:candidate_prepare_internal_comm_draft`: Command has an ambiguous or incomplete contract. The compiler suggests providing the missing contract detail.
  - Reason: A command references an API, worker, or input source that is not fully specified.  The compiler cannot materialize the command without this information.
  - Suggested resolution: For worker_promotion:candidate_prepare_internal_comm_draft: provide the missing contract detail (API name, worker target, IO bindings, or source evidence).  See the related diagnostic for specifics.
  - Related diagnostic: `irs_4789433061ec`
- `ASM_0001` for `worker_promotion:candidate_prepare_internal_comm_draft`: Command has an ambiguous or incomplete contract. The compiler suggests providing the missing contract detail.
  - Reason: A command references an API, worker, or input source that is not fully specified.  The compiler cannot materialize the command without this information.
  - Suggested resolution: For worker_promotion:candidate_prepare_internal_comm_draft: provide the missing contract detail (API name, worker target, IO bindings, or source evidence).  See the related diagnostic for specifics.
  - Related diagnostic: `irs_2444e5a5c547`
- `ASM_0002` for `worker_promotion:candidate_prepare_internal_comm_draft`: Command has an ambiguous or incomplete contract. The compiler suggests providing the missing contract detail.
  - Reason: A command references an API, worker, or input source that is not fully specified.  The compiler cannot materialize the command without this information.
  - Suggested resolution: For worker_promotion:candidate_prepare_internal_comm_draft: provide the missing contract detail (API name, worker target, IO bindings, or source evidence).  See the related diagnostic for specifics.
  - Related diagnostic: `irs_cf49c448d747`
- `ASM_0003` for `worker_promotion:candidate_prepare_internal_comm_draft`: Command has an ambiguous or incomplete contract. The compiler suggests providing the missing contract detail.
  - Reason: A command references an API, worker, or input source that is not fully specified.  The compiler cannot materialize the command without this information.
  - Suggested resolution: For worker_promotion:candidate_prepare_internal_comm_draft: provide the missing contract detail (API name, worker target, IO bindings, or source evidence).  See the related diagnostic for specifics.
  - Related diagnostic: `irs_839fb9f649c0`
- `ASM_0004` for `worker_promotion:candidate_select_approved_template`: Command has an ambiguous or incomplete contract. The compiler suggests providing the missing contract detail.
  - Reason: A command references an API, worker, or input source that is not fully specified.  The compiler cannot materialize the command without this information.
  - Suggested resolution: For worker_promotion:candidate_select_approved_template: provide the missing contract detail (API name, worker target, IO bindings, or source evidence).  See the related diagnostic for specifics.
  - Related diagnostic: `irs_4767aada0c3b`
- `ASM_0005` for `worker_promotion:candidate_select_approved_template`: Command has an ambiguous or incomplete contract. The compiler suggests providing the missing contract detail.
  - Reason: A command references an API, worker, or input source that is not fully specified.  The compiler cannot materialize the command without this information.
  - Suggested resolution: For worker_promotion:candidate_select_approved_template: provide the missing contract detail (API name, worker target, IO bindings, or source evidence).  See the related diagnostic for specifics.
  - Related diagnostic: `irs_d2b05c5a69a7`
- `ASM_0006` for `worker_promotion:candidate_select_approved_template`: Command has an ambiguous or incomplete contract. The compiler suggests providing the missing contract detail.
  - Reason: A command references an API, worker, or input source that is not fully specified.  The compiler cannot materialize the command without this information.
  - Suggested resolution: For worker_promotion:candidate_select_approved_template: provide the missing contract detail (API name, worker target, IO bindings, or source evidence).  See the related diagnostic for specifics.
  - Related diagnostic: `irs_a4385a7dba3c`
- `ASM_0007` for `worker:worker_main.exception_flow:exc_adapter_01`: Exception flow has no handler action. The compiler suggests specifying what should happen when this failure occurs.
  - Reason: Source describes a failure condition but does not specify how to handle it.  The exception flow is preserved in SPL, but no handler command was rendered. (Exception flow 'exc_adapter_01' ('- missing inputs') has no handler step in worker 'worker_main'.)
  - Suggested resolution: Specify the handler action for worker:worker_main.exception_flow:exc_adapter_01: e.g. ask the user for missing information, block finalization, or continue with an explicit assumption.
  - Related diagnostic: `diag_post_norm_0000`
- `ASM_0008` for `worker:worker_main.exception_flow:exc_adapter_01`: Exception flow has no handler action. The compiler suggests specifying what should happen when this failure occurs.
  - Reason: Source describes a failure condition but does not specify how to handle it.  The exception flow is preserved in SPL, but no handler command was rendered. (Exception flow 'exc_adapter_01' ('policy violations') has no handler step in worker 'worker_main'.)
  - Suggested resolution: Specify the handler action for worker:worker_main.exception_flow:exc_adapter_01: e.g. ask the user for missing information, block finalization, or continue with an explicit assumption.
  - Related diagnostic: `diag_post_norm_0001`
- `ASM_0009` for `worker:worker_main.exception_flow:exc_adapter_02`: Exception flow has no handler action. The compiler suggests specifying what should happen when this failure occurs.
  - Reason: Source describes a failure condition but does not specify how to handle it.  The exception flow is preserved in SPL, but no handler command was rendered. (Exception flow 'exc_adapter_02' ('template mismatches') has no handler step in worker 'worker_main'.)
  - Suggested resolution: Specify the handler action for worker:worker_main.exception_flow:exc_adapter_02: e.g. ask the user for missing information, block finalization, or continue with an explicit assumption.
  - Related diagnostic: `diag_post_norm_0002`
- `ASM_0010` for `worker:worker_main.exception_flow:exc_adapter_03`: Exception flow has no handler action. The compiler suggests specifying what should happen when this failure occurs.
  - Reason: Source describes a failure condition but does not specify how to handle it.  The exception flow is preserved in SPL, but no handler command was rendered. (Exception flow 'exc_adapter_03' ('tone mismatches') has no handler step in worker 'worker_main'.)
  - Suggested resolution: Specify the handler action for worker:worker_main.exception_flow:exc_adapter_03: e.g. ask the user for missing information, block finalization, or continue with an explicit assumption.
  - Related diagnostic: `diag_post_norm_0003`
- `ASM_0011` for `worker:worker_main.exception_flow:exc_adapter_04`: Exception flow has no handler action. The compiler suggests specifying what should happen when this failure occurs.
  - Reason: Source describes a failure condition but does not specify how to handle it.  The exception flow is preserved in SPL, but no handler command was rendered. (Exception flow 'exc_adapter_04' ('unverified facts') has no handler step in worker 'worker_main'.)
  - Suggested resolution: Specify the handler action for worker:worker_main.exception_flow:exc_adapter_04: e.g. ask the user for missing information, block finalization, or continue with an explicit assumption.
  - Related diagnostic: `diag_post_norm_0004`
- `ASM_0012` for `worker:worker_main.exception_flow:exc_adapter_05`: Exception flow has no handler action. The compiler suggests specifying what should happen when this failure occurs.
  - Reason: Source describes a failure condition but does not specify how to handle it.  The exception flow is preserved in SPL, but no handler command was rendered. (Exception flow 'exc_adapter_05' ('approval gaps') has no handler step in worker 'worker_main'.)
  - Suggested resolution: Specify the handler action for worker:worker_main.exception_flow:exc_adapter_05: e.g. ask the user for missing information, block finalization, or continue with an explicit assumption.
  - Related diagnostic: `diag_post_norm_0005`
- `ASM_0013` for `worker:worker_main.output:assumptions_log`: Required output has no source-backed producer. The compiler suggests adding a step that explicitly produces this output.
  - Reason: The source requires this output but does not describe how it should be produced.  The output is kept in the OUTPUTS contract, but no producer step was rendered.
  - Suggested resolution: Add a source-backed step that produces worker:worker_main.output:assumptions_log. If the source does not specify how to produce it, mark it as optional or remove it from the required output contract.
  - Related diagnostic: `diag_post_norm_0006`
- `ASM_0014` for `delegation_intent:s24`: Command has an ambiguous or incomplete contract. The compiler suggests providing the missing contract detail.
  - Reason: A command references an API, worker, or input source that is not fully specified.  The compiler cannot materialize the command without this information.
  - Suggested resolution: For delegation_intent:s24: provide the missing contract detail (API name, worker target, IO bindings, or source evidence).  See the related diagnostic for specifics.
  - Related diagnostic: `diag_d10_0000`
- `ASM_0015` for `delegation_intent:s25`: Command has an ambiguous or incomplete contract. The compiler suggests providing the missing contract detail.
  - Reason: A command references an API, worker, or input source that is not fully specified.  The compiler cannot materialize the command without this information.
  - Suggested resolution: For delegation_intent:s25: provide the missing contract detail (API name, worker target, IO bindings, or source evidence).  See the related diagnostic for specifics.
  - Related diagnostic: `diag_d10_0001`
- `ASM_0016` for `delegation_intent:s24`: Command has an ambiguous or incomplete contract. The compiler suggests providing the missing contract detail.
  - Reason: A command references an API, worker, or input source that is not fully specified.  The compiler cannot materialize the command without this information.
  - Suggested resolution: For delegation_intent:s24: provide the missing contract detail (API name, worker target, IO bindings, or source evidence).  See the related diagnostic for specifics.
  - Related diagnostic: `diag_d10_0002`

## 6. Provenance / TraceRecords

- `constraint:c_1` -> `direct`
  - Source: spans=`s4`, section=`sec_-_**scope`, packet=`p_list_item_routine_newsletters_exclude_sensitive_executive_messages_and_crisis_communications`
  - Explanation: Constraint 'c_1' (delegation_boundary): The draft is limited to routine newsletters; exclude sensitive executive message
- `constraint:c_2` -> `direct`
  - Source: spans=`s22`, section=`sec_policies`, packet=`p_list_item_no_external_data`
  - Explanation: Constraint 'c_2' (prohibition): Do not use external data.
- `delegation_intent:initial_drafting` -> `inferred`
  - Source: spans=`s24`, section=`sec_delegation_policy`
  - Explanation: Delegation intent 'initial_drafting': - Initial drafting
- `flow:exc_adapter_01` -> `direct`
  - Source: spans=`s23`, section=`sec_failure_handling`, packet=`p_list_item_missing_inputs`
  - Explanation: Exception flow 'exc_adapter_01': - missing inputs
- `flow:exc_adapter_01` -> `direct`
  - Source: spans=`s23`, section=`sec_failure_handling`, packet=`p_list_item_missing_inputs`
  - Explanation: Exception flow 'exc_adapter_01': policy violations
- `flow:exc_adapter_02` -> `direct`
  - Source: spans=`s23`, section=`sec_failure_handling`, packet=`p_list_item_missing_inputs`
  - Explanation: Exception flow 'exc_adapter_02': template mismatches
- `flow:exc_adapter_03` -> `direct`
  - Source: spans=`s23`, section=`sec_failure_handling`, packet=`p_list_item_missing_inputs`
  - Explanation: Exception flow 'exc_adapter_03': tone mismatches
- `flow:exc_adapter_04` -> `direct`
  - Source: spans=`s23`, section=`sec_failure_handling`, packet=`p_list_item_missing_inputs`
  - Explanation: Exception flow 'exc_adapter_04': unverified facts
- `flow:exc_adapter_05` -> `direct`
  - Source: spans=`s23`, section=`sec_failure_handling`, packet=`p_list_item_missing_inputs`
  - Explanation: Exception flow 'exc_adapter_05': approval gaps
- `flow:main` -> `direct`
  - Source: spans=`s13, s14, s15, s16, s17, s18, s19, s20, s24, s25`, section=`sec_reusable_process`, packet=`p_list_item_identify_audience_and_key_messages`
  - Explanation: Main flow with 1 block(s).
- `profile:audience_0` -> `inferred`
  - Explanation: Audience: CompanyWideAudience
- `profile:audience_1` -> `inferred`
  - Explanation: Audience: TeamAudience
- `profile:concept_0` -> `normalized`
  - Explanation: Concept: internal communications drafting -- The preparation of written messages for use inside an organization.
- `profile:concept_1` -> `normalized`
  - Explanation: Concept: company-wide announcements -- Organization-wide messages intended for all employees.
- `profile:concept_10` -> `normalized`
  - Explanation: Concept: readiness status flag -- An indicator showing whether the draft is ready for release or further review.
- `profile:concept_11` -> `normalized`
  - Explanation: Concept: policy compliance -- Alignment of the draft with organizational rules or communication policies.
- `profile:concept_12` -> `normalized`
  - Explanation: Concept: disclaimers/citations -- Statements or references added to clarify limitations or support claims in the draft.
- `profile:concept_2` -> `normalized`
  - Explanation: Concept: team updates -- Internal messages that communicate progress, changes, or news to a specific team.
- `profile:concept_3` -> `normalized`
  - Explanation: Concept: routine newsletters -- Regular internal newsletter communications used for ongoing organizational updates.
- `profile:concept_4` -> `normalized`
  - Explanation: Concept: sensitive executive messages -- High-level leadership communications that require special handling and are excluded from this drafting scope.
- `profile:concept_5` -> `normalized`
  - Explanation: Concept: crisis communications -- Urgent messages used during incidents or emergencies; excluded from this drafting scope.
- `profile:concept_6` -> `normalized`
  - Explanation: Concept: template selection -- Choosing an approved formatting or content template for the draft.
- `profile:concept_7` -> `normalized`
  - Explanation: Concept: revision history -- A record of edits or changes made to the draft over time.
- `profile:concept_8` -> `normalized`
  - Explanation: Concept: assumptions log -- A written record of assumptions made when preparing the draft.
- `profile:concept_9` -> `normalized`
  - Explanation: Concept: evidence trail -- Supporting references or artifacts showing how the draft was derived.
- `profile:persona` -> `inferred`
  - Explanation: Persona: Internal communications drafter
- `step:st_1` -> `direct`
  - Source: spans=`s13`, section=`sec_reusable_process`, packet=`p_list_item_identify_audience_and_key_messages`
  - Explanation: Step 'st_1' maps to source span(s).
- `step:st_2` -> `direct`
  - Source: spans=`s14`, section=`sec_reusable_process`, packet=`p_list_item_select_approved_template`
  - Explanation: Step 'st_2' maps to source span(s).
- `step:st_3` -> `direct`
  - Source: spans=`s15`, section=`sec_reusable_process`, packet=`p_list_item_gather_source_materials`
  - Explanation: Step 'st_3' maps to source span(s).
- `step:st_4` -> `direct`
  - Source: spans=`s16`, section=`sec_reusable_process`, packet=`p_list_item_draft_content`
  - Explanation: Step 'st_4' maps to source span(s).
- `step:st_5` -> `direct`
  - Source: spans=`s17`, section=`sec_reusable_process`, packet=`p_list_item_review_for_tone_and_policy_compliance`
  - Explanation: Step 'st_5' maps to source span(s).
- `step:st_6` -> `direct`
  - Source: spans=`s18`, section=`sec_reusable_process`, packet=`p_list_item_insert_disclaimers_citations`
  - Explanation: Step 'st_6' maps to source span(s).
- `step:st_7` -> `direct`
  - Source: spans=`s19`, section=`sec_reusable_process`, packet=`p_list_item_attach_revision_history_and_evidence_trail`
  - Explanation: Step 'st_7' maps to source span(s).
- `step:st_8` -> `direct`
  - Source: spans=`s20`, section=`sec_reusable_process`, packet=`p_list_item_flag_readiness`
  - Explanation: Step 'st_8' maps to source span(s).
- `variable:assumptions_log` -> `normalized`
  - Source: section=`sec_required_outputs`
  - Explanation: Variable 'assumptions_log' is declared by adapter hard fact in section 'sec_required_outputs'.
- `variable:evidence_trail` -> `normalized`
  - Source: section=`sec_required_outputs`
  - Explanation: Variable 'evidence_trail' is declared by adapter hard fact in section 'sec_required_outputs'.
- `variable:final_draft` -> `direct`
  - Source: spans=`s16`, section=`sec_reusable_process`, packet=`p_list_item_draft_content`
  - Explanation: Variable 'final_draft' is produced by source-backed step 'st_4'.
- `variable:key_messages` -> `normalized`
  - Source: section=`sec_inputs_for_each_run`
  - Explanation: Variable 'key_messages' is declared by adapter hard fact in section 'sec_inputs_for_each_run'.
- `variable:readiness_status_flag` -> `direct`
  - Source: spans=`s20`, section=`sec_reusable_process`, packet=`p_list_item_flag_readiness`
  - Explanation: Variable 'readiness_status_flag' is produced by source-backed step 'st_8'.
- `variable:revision_history` -> `normalized`
  - Source: section=`sec_required_outputs`
  - Explanation: Variable 'revision_history' is declared by adapter hard fact in section 'sec_required_outputs'.
- `variable:target_audience` -> `normalized`
  - Source: section=`sec_inputs_for_each_run`
  - Explanation: Variable 'target_audience' is declared by adapter hard fact in section 'sec_inputs_for_each_run'.
- `variable:template_selection` -> `normalized`
  - Source: section=`sec_-_**optional`
  - Explanation: Variable 'template_selection' is declared by adapter hard fact in section 'sec_-_**optional'.
- `variable:tone` -> `normalized`
  - Source: section=`sec_inputs_for_each_run`
  - Explanation: Variable 'tone' is declared by adapter hard fact in section 'sec_inputs_for_each_run'.
- `variable:topic` -> `normalized`
  - Source: section=`sec_inputs_for_each_run`
  - Explanation: Variable 'topic' is declared by adapter hard fact in section 'sec_inputs_for_each_run'.
- `variable:worker_main_st_6_result_structured` -> `direct`
  - Source: spans=`s18`, section=`sec_reusable_process`, packet=`p_list_item_insert_disclaimers_citations`
  - Explanation: Variable 'worker_main_st_6_result_structured' is produced by source-backed step 'st_6'.
- `variable:worker_main_st_7_result_structured` -> `direct`
  - Source: spans=`s19`, section=`sec_reusable_process`, packet=`p_list_item_attach_revision_history_and_evidence_trail`
  - Explanation: Variable 'worker_main_st_7_result_structured' is produced by source-backed step 'st_7'.
- `worker:MainWorker` -> `direct`
  - Source: spans=`s13, s14, s15, s16, s17, s18, s19, s20, s23, s24, s25`, section=`sec_reusable_process`, packet=`p_list_item_identify_audience_and_key_messages`
  - Explanation: Main worker 'MainWorker' assembled from flow and step IRs.

## 7. Anti-Fabrication Checks

- `missing_handler`: Exception conditions without handler action stay as partial exception flows; no handler command is invented.
- `missing_output_producer`: Required outputs without a source-backed producer stay in the contract; no synthetic producer command is invented.
- `type_or_contract_ambiguity`: Unresolved worker/API contracts are reported as ambiguity; they are not downgraded to generic commands.
- Rendered SPL contains no executable `[INVOKE ...]` command.

## 8. Adapter / Validation Notes

Adapter warnings:
- EMPTY_SECTION: Section 'Internal Communications Drafting' is present but empty.
- LLM_DUPLICATE_FACT: LLM input fact 'target_audience' duplicates deterministic fact -- rejected.
- LLM_DUPLICATE_FACT: LLM output fact 'final_draft' duplicates deterministic fact -- rejected.
- LLM_DUPLICATE_FACT: LLM output fact 'revision_history' duplicates deterministic fact -- rejected.
- LLM_DUPLICATE_FACT: LLM output fact 'assumptions_log' duplicates deterministic fact -- rejected.
- LLM_DUPLICATE_FACT: LLM output fact 'evidence_trail' duplicates deterministic fact -- rejected.
- LLM_DUPLICATE_FACT: LLM output fact 'readiness_status_flag' duplicates deterministic fact -- rejected.
- LLM_DUPLICATE_FACT: LLM failure_mode fact 'missing_inputs' duplicates deterministic fact -- rejected.
- LLM_DUPLICATE_FACT: LLM delegation_intent fact 'initial_drafting' duplicates deterministic fact -- rejected.
- LLM_UNCERTAIN: Could not determine source packet IDs for some facts inferred from the raw text.

Validation warnings:
- Aggregated multi-output step st_6 into worker_main_st_6_result_structured without unpack steps.
- Aggregated multi-output step st_7 into worker_main_st_7_result_structured without unpack steps.
- Unused variable declared: revision_history
- Unused variable declared: evidence_trail

## 9. SPL Draft

```spl
[DEFINE_AGENT: MainWorker "Orchestrate the end-to-end process and delegate to sub-tasks."]
    [DEFINE_PERSONA:]
        ROLE: Internal communications drafter
        ProcessOriented: Follows a reusable drafting workflow: identify audience and key messages, select an approved template, gather source materials, draft, review for tone and policy compliance, add disclaimers/citations, and attach revision history and evidence trail.
        PolicyAware: Works within policy constraints, including no external data and handling missing inputs carefully.
        DocumentationFocused: Produces supporting logs and traces alongside the final draft, including revision history, assumptions, evidence trail, and readiness status.
        InferredRole: Role inferred from task context; no explicit identity description was provided in the source text.
    [END_PERSONA]
    [DEFINE_AUDIENCE:]
        CompanyWideAudience: Employees receiving company-wide announcements.
        TeamAudience: Team members receiving internal team updates.
    [END_AUDIENCE]
    [DEFINE_CONCEPTS:]
        Internalcommunicationsdrafting: The preparation of written messages for use inside an organization.
        Companywideannouncements: Organization-wide messages intended for all employees.
        Teamupdates: Internal messages that communicate progress, changes, or news to a specific team.
        Routinenewsletters: Regular internal newsletter communications used for ongoing organizational updates.
        Sensitiveexecutivemessages: High-level leadership communications that require special handling and are excluded from this drafting scope.
        Crisiscommunications: Urgent messages used during incidents or emergencies; excluded from this drafting scope.
        Templateselection: Choosing an approved formatting or content template for the draft.
        Revisionhistory: A record of edits or changes made to the draft over time.
        Assumptionslog: A written record of assumptions made when preparing the draft.
        Evidencetrail: Supporting references or artifacts showing how the draft was derived.
        Readinessstatusflag: An indicator showing whether the draft is ready for release or further review.
        Policycompliance: Alignment of the draft with organizational rules or communication policies.
        Disclaimerscitations: Statements or references added to clarify limitations or support claims in the draft.
    [END_CONCEPTS]
    [DEFINE_CONSTRAINTS:]
        DelegationBoundary: The draft is limited to routine newsletters; exclude sensitive executive messages and crisis communications.
        Prohibition: Do not use external data.
    [END_CONSTRAINTS]
    [DEFINE_VARIABLES:]
        "- target audience" target_audience: text
        "Topic of the internal communications draft." topic: text
        "Desired tone for the internal communications draft." tone: text
        "Key messages to be included in the internal communications draft." key_messages: text
        "Optional template selection for the draft." template_selection: text
        "Final draft" final_draft: text
        "Revision history" revision_history: text
        "Assumptions log" assumptions_log: text
        "Evidence trail" evidence_trail: text
        "Readiness status flag" readiness_status_flag: text
        "Structured result for st_6." worker_main_st_6_result_structured: worker_main_st_6_result_structured_type
        "Structured result for st_7." worker_main_st_7_result_structured: worker_main_st_7_result_structured_type
    [END_VARIABLES]
    [DEFINE_TYPES:]
        worker_main_st_6_result_structured_type = { final_draft: text, evidence_trail: text }
        worker_main_st_7_result_structured_type = { revision_history: text, evidence_trail: text }
    [END_TYPES]
    [DEFINE_WORKER: "Orchestrate the end-to-end process and delegate to sub-tasks." MainWorker]
        [INPUTS]
            REQUIRED <REF>target_audience</REF>
            REQUIRED <REF>topic</REF>
            REQUIRED <REF>tone</REF>
            REQUIRED <REF>key_messages</REF>
            OPTIONAL <REF>template_selection</REF>
        [END_INPUTS]
        [OUTPUTS]
            REQUIRED <REF>worker_main_st_6_result_structured</REF>
            REQUIRED <REF>worker_main_st_7_result_structured</REF>
            REQUIRED <REF>assumptions_log</REF>
            REQUIRED <REF>readiness_status_flag</REF>
        [END_OUTPUTS]
        [MAIN_FLOW]
            [SEQUENTIAL_BLOCK]
                COMMAND-1 [COMMAND Identify the target audience and key messages based on <REF>target_audience</REF> and <REF>key_messages</REF>]
                COMMAND-2 [COMMAND Select the approved template based on <REF>template_selection</REF>]
                COMMAND-3 [COMMAND Gather source materials based on <REF>topic</REF>]
                COMMAND-4 [COMMAND Draft the content based on <REF>topic</REF>, <REF>target_audience</REF>, <REF>tone</REF>, <REF>key_messages</REF>, and <REF>template_selection</REF> RESULT final_draft: text SET]
                COMMAND-5 [COMMAND Review the draft for tone and policy compliance based on <REF>final_draft</REF> and <REF>tone</REF>]
                COMMAND-6 [COMMAND Insert disclaimers and citations based on <REF>final_draft</REF> RESULT worker_main_st_6_result_structured: worker_main_st_6_result_structured_type SET]
                COMMAND-7 [COMMAND Attach the revision history and evidence trail based on <REF>worker_main_st_6_result_structured</REF> RESULT worker_main_st_7_result_structured: worker_main_st_7_result_structured_type SET]
                COMMAND-8 [COMMAND Flag readiness based on <REF>worker_main_st_6_result_structured</REF> and <REF>worker_main_st_7_result_structured</REF> RESULT readiness_status_flag: text SET]
            [END_SEQUENTIAL_BLOCK]
        [END_MAIN_FLOW]
        [EXCEPTION_FLOW: - missing inputs]
        [END_EXCEPTION_FLOW]
        [EXCEPTION_FLOW: policy violations]
        [END_EXCEPTION_FLOW]
        [EXCEPTION_FLOW: template mismatches]
        [END_EXCEPTION_FLOW]
        [EXCEPTION_FLOW: tone mismatches]
        [END_EXCEPTION_FLOW]
        [EXCEPTION_FLOW: unverified facts]
        [END_EXCEPTION_FLOW]
        [EXCEPTION_FLOW: approval gaps]
        [END_EXCEPTION_FLOW]
    [END_WORKER]
[END_AGENT]
```
