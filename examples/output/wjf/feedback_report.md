# NL2SPL Feedback Report

## 1. Overall Compile State

- Completeness: `blocked`
- SPL draft generated: `yes`
- Compile diagnostics: `44`
- Assumptions / suggestions: `31`
- Trace records: `49`
- Adapter warnings: `0`
- Validation errors: `1`
- Validation warnings: `7`

Result is blocked because validation errors remain.

## 2. Materialized Source-Backed Structure

### Workers
- `worker:MainWorker` (direct) -- spans=s20, s21, s22, s23, s24, s25, s26, s27, s28, s29, s30, s31, s32, s33, s34, s35, s36, s40, s48, s51, s52a, s52b, s53, s58, s60, s37; section=sec_reusable_process; packet=p_list_item_analyze_the_user_s_request_to_clarify_the_type_of_communication_material

### Profiles
- `profile:audience:0` (derived) -- spans=s6, s7, s8; section=sec_task_family
- `profile:concept:0` (derived) -- spans=s1, s5; section=sec_task_family
- `profile:concept:1` (derived) -- spans=s2, s5; section=sec_task_family
- `profile:concept:2` (normalized) -- spans=s3; section=sec_task_family; packet=p_list_item_periodic_update_digests
- `profile:concept:3` (derived) -- spans=s4, s6; section=sec_task_family
- `profile:concept:4` (normalized) -- spans=s5; section=sec_task_family; packet=p_list_item_other_internal_facing_communication_materials_these_materials_are_primarily_intended_for_reading_and_use_by_company_employees
- `profile:persona.aspect:1` (normalized) -- spans=s45; section=sec_policies; packet=p_list_item_fluency
- `profile:persona.aspect:2` (derived) -- spans=s21, s22, s31, s32, s33, s34; section=sec_reusable_process

### Flows
- `flow:alt_1` (direct) -- spans=s40; section=sec_reusable_process; packet=p_list_item_completion_status_if_the_user_requests_revisions_to_the_draft
- `flow:exc_adapter_00` (direct) -- spans=s52a, s52b; section=sec_conflicting_instructions; packet=p_list_item_if_the_user_s_requirements_conflict_and_impede_task_execution
- `flow:exc_adapter_01` (direct) -- spans=s47, s48; section=sec_failure_handling; packet=p_list_item_missing_critical_information_if_information_essential_to_task_completion_is_lacking
- `flow:main` (direct) -- spans=s20, s21, s22, s23, s24, s25, s27, s28, s29, s30, s31, s32, s33, s34, s35, s36, s48, s51, s52b, s53, s58, s60; section=sec_reusable_process; packet=p_list_item_analyze_the_user_s_request_to_clarify_the_type_of_communication_material

### Steps
- `step:st_1` (direct) -- spans=s20; section=sec_reusable_process; packet=p_list_item_analyze_the_user_s_request_to_clarify_the_type_of_communication_material
- `step:st_10` (direct) -- spans=s36; section=sec_reusable_process; packet=p_list_item_revise_it_based_on_the_verification_results_output_the_draft_communication_artifact
- `step:st_11` (direct) -- spans=s58; section=sec_delegation_policy; packet=p_list_item_though_delegation_is_not_mandatory_delegated_tasks_shall_not_expand_the_scope_of_the_original_task_nor_alter_the_user_s_original_requirements_the_main_process_shall_verify_that_delegated_results_comply_with_the_task_scope_and_user_requirements_before_adopting_them_if_delegation_fails_or_returns_results_beyond_the_authorized_scope
- `step:st_12` (direct) -- spans=s37; section=sec_reusable_process; packet=p_list_item_revise_it_based_on_the_verification_results_output_the_draft_communication_artifact
- `step:st_13` (direct) -- spans=s40; section=sec_reusable_process; packet=p_list_item_completion_status_if_the_user_requests_revisions_to_the_draft
- `step:st_2` (direct) -- spans=s21, s22, s23; section=sec_reusable_process; packet=p_list_item_communication_purpose
- `step:st_3` (direct) -- spans=s24; section=sec_reusable_process; packet=p_list_item_expression_requirements_check_if_the_facts_and_background_information_needed_to_generate_the_material_are_available_if_critical_information_that_affects_content_accuracy_is_missing
- `step:st_4` (direct) -- spans=s25; section=sec_reusable_process; packet=p_list_item_expression_requirements_check_if_the_facts_and_background_information_needed_to_generate_the_material_are_available_if_critical_information_that_affects_content_accuracy_is_missing
- `step:st_5` (direct) -- spans=s27; section=sec_reusable_process; packet=p_list_item_proceed_organize_the_obtained_facts_and_background_information
- `step:st_6` (direct) -- spans=s28; section=sec_reusable_process; packet=p_list_item_extract_core_messages_to_be_conveyed
- `step:st_7` (direct) -- spans=s29; section=sec_reusable_process; packet=p_list_item_structure_the_content_based_on_the_material_type_generate_a_draft_communication_artifact_and_verify_if_it_meets_the_user_s_specified_requirements_for_target_audience
- `step:st_8` (direct) -- spans=s30; section=sec_reusable_process; packet=p_list_item_structure_the_content_based_on_the_material_type_generate_a_draft_communication_artifact_and_verify_if_it_meets_the_user_s_specified_requirements_for_target_audience
- `step:st_9` (direct) -- spans=s31, s32, s33, s34, s35; section=sec_reusable_process; packet=p_list_item_tone

### Variables
- `variable:draft_communication_artifact` (direct) -- spans=s20; section=sec_reusable_process; packet=p_list_item_analyze_the_user_s_request_to_clarify_the_type_of_communication_material
- `variable:unresolved_items` (direct) -- spans=s58; section=sec_delegation_policy; packet=p_list_item_though_delegation_is_not_mandatory_delegated_tasks_shall_not_expand_the_scope_of_the_original_task_nor_alter_the_user_s_original_requirements_the_main_process_shall_verify_that_delegated_results_comply_with_the_task_scope_and_user_requirements_before_adopting_them_if_delegation_fails_or_returns_results_beyond_the_authorized_scope

### Constraints
- `constraint:c_1` (direct) -- spans=s41; section=sec_policies; packet=p_list_item_do_not_fabricate_facts
- `constraint:c_2` (direct) -- spans=s44; section=sec_policies; packet=p_list_item_sources_that_are_not_provided_by_the_user_or_obtained_from_available_information_sources_external_facts_must_have_traceable_sources_facts_directly_provided_by_the_user_shall_be_marked_as_user_provided_information_prioritize_information_already_provided_by_the_user_to_avoid_unnecessary_information_retrieval_and_clarifying_questions_do_not_alter_the_meaning_of_the_user_s_original_request_for_the_sake_of_completeness
- `constraint:c_3` (direct) -- spans=s46; section=sec_policies; packet=p_list_item_professionalism_of_expression_do_not_mark_the_task_as_complete_if_critical_information_is_missing_or_conflicting_instructions_remain_unresolved
- `constraint:c_4` (direct) -- spans=s57; section=sec_delegation_policy; packet=p_list_item_though_delegation_is_not_mandatory_delegated_tasks_shall_not_expand_the_scope_of_the_original_task_nor_alter_the_user_s_original_requirements_the_main_process_shall_verify_that_delegated_results_comply_with_the_task_scope_and_user_requirements_before_adopting_them_if_delegation_fails_or_returns_results_beyond_the_authorized_scope
- `constraint:c_5` (direct) -- spans=s59; section=sec_delegation_policy; packet=p_list_item_though_delegation_is_not_mandatory_delegated_tasks_shall_not_expand_the_scope_of_the_original_task_nor_alter_the_user_s_original_requirements_the_main_process_shall_verify_that_delegated_results_comply_with_the_task_scope_and_user_requirements_before_adopting_them_if_delegation_fails_or_returns_results_beyond_the_authorized_scope

## 3. Not Materialized / Kept Partial

- `worker:worker_main.exception_flow:exc_adapter_01`: `missing_handler` -- Exception flow 'exc_adapter_01' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_01, slot=handler_action]
  - Suggested resolution: Add a handler step for 'Missing Critical Information:', or mark this exception as acknowledged without handling.
- `worker:worker_main.exception_flow:exc_adapter_00`: `missing_handler` -- Exception flow 'exc_adapter_00' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_00, slot=handler_action]
  - Suggested resolution: Add a handler step for 'If the user’s requirements conflict and impede task execution', or mark this exception as acknowledged without handling.
- `resource_contract_demand:rcd_output_s17`: `missing_output_producer` -- Resource contract output 'rcd_output_s17' (requiredness=required) has materialized resource(s) source_evidence_set but no renderable producer. [construct=resource_contract_demand:rcd_output_s17, slot=producer]
  - Suggested resolution: Add a source-backed step or handoff that produces the materialized resource name with the same resource kind.
- `worker:worker_main.output:completion_status`: `missing_output_producer` -- Required output 'completion_status' (Final status of task completion.) has no source-backed producer step. [construct=worker:worker_main.output:completion_status, slot=producer]
  - Suggested resolution: Add a step that produces 'completion_status'. If the source requirement does not specify how to produce this output, mark it as optional or remove it from the output contract.
- `worker:worker_main.output:source_evidence_set`: `missing_output_producer` -- Required output 'source_evidence_set' (Collected evidence or supporting sources used for the draft.) has no source-backed producer step. [construct=worker:worker_main.output:source_evidence_set, slot=producer]
  - Suggested resolution: Add a step that produces 'source_evidence_set'. If the source requirement does not specify how to produce this output, mark it as optional or remove it from the output contract.
- `resource_contract_demand:rcd_output_s19`: `missing_output_producer` -- Resource contract output 'rcd_output_s19' (requiredness=required) has materialized resource(s) completion_status but no renderable producer. [construct=resource_contract_demand:rcd_output_s19, slot=producer]
  - Suggested resolution: Add a source-backed step or handoff that produces the materialized resource name with the same resource kind.
- `worker_promotion:del_s54`: `type_or_contract_ambiguity` -- WORKER_PROMOTION blocked by missing promotion slots.
  - Source spans: `s54`
  - `promotion_input_contract`: Missing clear input contract
  - `promotion_output_contract`: Missing clear output contract
  - `promotion_invocation_point`: Missing accepted decision or matching handoff with invocation hint
  - `promotion_result_handoff`: Missing matching handoff with output bindings
- `worker_promotion:del_s55`: `type_or_contract_ambiguity` -- WORKER_PROMOTION blocked by missing promotion slots.
  - Source spans: `s55`
  - `promotion_input_contract`: Missing clear input contract
  - `promotion_output_contract`: Missing clear output contract
  - `promotion_invocation_point`: Missing accepted decision or matching handoff with invocation hint
  - `promotion_result_handoff`: Missing matching handoff with output bindings
- `worker:worker_main.span:s26`: `unmapped_behavior_span` -- Worker 'worker_main' behavior span 's26' (proceed.) was not mapped to a step: Non-executable connective text ('proceed') without an actionable operation.

## 4. Diagnostics

### irs_d969ce57e92a: `missing_handler`
- Severity: `warning`
- Target: `worker:worker_main.exception_flow:exc_adapter_01`
- Source spans: `s47`
- Message: Exception flow 'exc_adapter_01' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_01, slot=handler_action]
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Add a handler step for 'Missing Critical Information:', or mark this exception as acknowledged without handling.
- Missing slot: `handler_action`
- Missing reason: Exception flow 'exc_adapter_01' has condition but no handler step.

### irs_def107932ceb: `missing_handler`
- Severity: `warning`
- Target: `worker:worker_main.exception_flow:exc_adapter_00`
- Source spans: `s52a`
- Message: Exception flow 'exc_adapter_00' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_00, slot=handler_action]
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Add a handler step for 'If the user’s requirements conflict and impede task execution', or mark this exception as acknowledged without handling.
- Missing slot: `handler_action`
- Missing reason: Exception flow 'exc_adapter_00' has condition but no handler step.

### irs_17b4cac9bea8: `missing_output_producer`
- Severity: `warning`
- Target: `resource_contract_demand:rcd_output_s17`
- Source spans: `s17`
- Message: Resource contract output 'rcd_output_s17' (requiredness=required) has materialized resource(s) source_evidence_set but no renderable producer. [construct=resource_contract_demand:rcd_output_s17, slot=producer]
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Add a source-backed step or handoff that produces the materialized resource name with the same resource kind.
- Missing slot: `producer`
- Missing reason: Resource contract output 'rcd_output_s17' (requiredness=required) has materialized resource(s) source_evidence_set but no renderable producer.

### irs_5143c9abd16e: `missing_output_producer`
- Severity: `warning`
- Target: `worker:worker_main.output:completion_status`
- Message: Required output 'completion_status' (Final status of task completion.) has no source-backed producer step. [construct=worker:worker_main.output:completion_status, slot=producer]
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Add a step that produces 'completion_status'. If the source requirement does not specify how to produce this output, mark it as optional or remove it from the output contract.
- Missing slot: `producer`
- Missing reason: Required output 'completion_status' (Final status of task completion.) has no source-backed producer step.

### irs_ae87eac80c3d: `missing_output_producer`
- Severity: `warning`
- Target: `worker:worker_main.output:source_evidence_set`
- Message: Required output 'source_evidence_set' (Collected evidence or supporting sources used for the draft.) has no source-backed producer step. [construct=worker:worker_main.output:source_evidence_set, slot=producer]
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Add a step that produces 'source_evidence_set'. If the source requirement does not specify how to produce this output, mark it as optional or remove it from the output contract.
- Missing slot: `producer`
- Missing reason: Required output 'source_evidence_set' (Collected evidence or supporting sources used for the draft.) has no source-backed producer step.

### irs_b096d94cafe8: `missing_output_producer`
- Severity: `warning`
- Target: `resource_contract_demand:rcd_output_s19`
- Source spans: `s19`
- Message: Resource contract output 'rcd_output_s19' (requiredness=required) has materialized resource(s) completion_status but no renderable producer. [construct=resource_contract_demand:rcd_output_s19, slot=producer]
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Add a source-backed step or handoff that produces the materialized resource name with the same resource kind.
- Missing slot: `producer`
- Missing reason: Resource contract output 'rcd_output_s19' (requiredness=required) has materialized resource(s) completion_status but no renderable producer.

### grouped:worker_promotion:del_s54: `type_or_contract_ambiguity`
- Severity: `warning`
- Target: `worker_promotion:del_s54`
- Source spans: `s54`
- Message: WORKER_PROMOTION blocked by missing promotion slots.
- Blocks rendering: `false`
- Blocks completion: `true`
- Missing slots:
  - `promotion_input_contract`: Missing clear input contract
    - Diagnostic: `irs_0297500e5eab`
  - `promotion_output_contract`: Missing clear output contract
    - Diagnostic: `irs_ef243c3fbeaa`
  - `promotion_invocation_point`: Missing accepted decision or matching handoff with invocation hint
    - Diagnostic: `irs_35d11eb78fc7`
  - `promotion_result_handoff`: Missing matching handoff with output bindings
    - Diagnostic: `irs_cbf0a65b4e21`

### grouped:worker_promotion:del_s55: `type_or_contract_ambiguity`
- Severity: `warning`
- Target: `worker_promotion:del_s55`
- Source spans: `s55`
- Message: WORKER_PROMOTION blocked by missing promotion slots.
- Blocks rendering: `false`
- Blocks completion: `true`
- Missing slots:
  - `promotion_input_contract`: Missing clear input contract
    - Diagnostic: `irs_17fdeaa57275`
  - `promotion_output_contract`: Missing clear output contract
    - Diagnostic: `irs_e4ee1be21120`
  - `promotion_invocation_point`: Missing accepted decision or matching handoff with invocation hint
    - Diagnostic: `irs_f2dba60ddc61`
  - `promotion_result_handoff`: Missing matching handoff with output bindings
    - Diagnostic: `irs_ea4169e64ade`

### diag_s7_0000: `unmapped_behavior_span`
- Severity: `warning`
- Target: `worker:worker_main.span:s26`
- Source spans: `s26`
- Message: Worker 'worker_main' behavior span 's26' (proceed.) was not mapped to a step: Non-executable connective text ('proceed') without an actionable operation.
- Blocks rendering: `false`
- Blocks completion: `true`

### diag_prov_0000: `missing_provenance`
- Severity: `warning`
- Target: `variable:known_topics`
- Message: Variable 'known_topics' (List[text]) is a contract input with no source-backed producer or adapter evidence.
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_prov_0001: `missing_provenance`
- Severity: `warning`
- Target: `variable:timeframe`
- Message: Variable 'timeframe' (text) is a contract input with no source-backed producer or adapter evidence.
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_prov_0002: `missing_provenance`
- Severity: `warning`
- Target: `variable:background_information`
- Message: Variable 'background_information' (text) is a contract input with no source-backed producer or adapter evidence.
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_prov_0003: `missing_provenance`
- Severity: `warning`
- Target: `variable:target_audience`
- Message: Variable 'target_audience' (text) is a contract input with no source-backed producer or adapter evidence.
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_prov_0004: `missing_provenance`
- Severity: `warning`
- Target: `variable:available_information_sources`
- Message: Variable 'available_information_sources' (List[text]) is a contract input with no source-backed producer or adapter evidence.
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_prov_0005: `missing_provenance`
- Severity: `warning`
- Target: `variable:format_preferences`
- Message: Variable 'format_preferences' (text) is a contract input with no source-backed producer or adapter evidence.
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_prov_0006: `missing_provenance`
- Severity: `warning`
- Target: `variable:user_communication_request`
- Message: Variable 'user_communication_request' (text) is a contract input with no source-backed producer or adapter evidence.
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_prov_0007: `missing_provenance`
- Severity: `warning`
- Target: `variable:source_evidence_set`
- Message: Variable 'source_evidence_set' (List[text]) is a contract output with no source-backed producer or adapter evidence.
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_prov_0008: `missing_provenance`
- Severity: `warning`
- Target: `variable:completion_status`
- Message: Variable 'completion_status' (text) is a contract output with no source-backed producer or adapter evidence.
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_prov_0009: `missing_provenance`
- Severity: `warning`
- Target: `profile:persona`
- Message: Rendered profile item 'profile:persona' has no source-backed provenance.
- Blocks rendering: `false`
- Blocks completion: `true`

### diag_prov_0010: `missing_provenance`
- Severity: `warning`
- Target: `profile:persona.aspect:0`
- Message: Unrendered profile item 'profile:persona.aspect:0' has no source-backed provenance.
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_prov_0011: `missing_provenance`
- Severity: `warning`
- Target: `profile:concept:5`
- Message: Unrendered profile item 'profile:concept:5' has no source-backed provenance.
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_prov_0012: `missing_provenance`
- Severity: `warning`
- Target: `profile:concept:6`
- Message: Unrendered profile item 'profile:concept:6' has no source-backed provenance.
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_prov_0013: `missing_provenance`
- Severity: `warning`
- Target: `profile:concept:7`
- Message: Unrendered profile item 'profile:concept:7' has no source-backed provenance.
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_prov_0014: `missing_provenance`
- Severity: `warning`
- Target: `profile:concept:8`
- Message: Unrendered profile item 'profile:concept:8' has no source-backed provenance.
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_prov_0015: `missing_provenance`
- Severity: `warning`
- Target: `profile:concept:9`
- Message: Unrendered profile item 'profile:concept:9' has no source-backed provenance.
- Blocks rendering: `false`
- Blocks completion: `false`

### arc4_annotation_missing_requiredness_s37_output_contract_requiredness: `annotation_missing_requiredness`
- Severity: `info`
- Target: `span:s37`
- Source spans: `s37`
- Message: [output_contract] requiredness: expected=required | optional | unspecified, got=None. Post-enrichment: span 's37' (output_contract) has no requiredness metadata
- Blocks rendering: `false`
- Blocks completion: `false`

### arc4_annotation_missing_requiredness_s38_output_contract_requiredness: `annotation_missing_requiredness`
- Severity: `info`
- Target: `span:s38`
- Source spans: `s38`
- Message: [output_contract] requiredness: expected=required | optional | unspecified, got=None. Post-enrichment: span 's38' (output_contract) has no requiredness metadata
- Blocks rendering: `false`
- Blocks completion: `false`

### arc4_annotation_missing_requiredness_s39_output_contract_requiredness: `annotation_missing_requiredness`
- Severity: `info`
- Target: `span:s39`
- Source spans: `s39`
- Message: [output_contract] requiredness: expected=required | optional | unspecified, got=None. Post-enrichment: span 's39' (output_contract) has no requiredness metadata
- Blocks rendering: `false`
- Blocks completion: `false`

### irs_e4be3c4bf046: `unspecified_output_missing_producer`
- Severity: `info`
- Target: `resource_contract_demand:rcd_output_s39`
- Source spans: `s39`
- Message: Resource contract output 'rcd_output_s39' has requiredness=unspecified and no renderable producer. Review whether this output should be declared optional or a producer step should be added. [construct=resource_contract_demand:rcd_output_s39, slot=producer]
- Blocks rendering: `false`
- Blocks completion: `false`
- Suggested resolution: Either add a producer step, or mark this output as optional in the source requirement.
- Missing slot: `producer`
- Missing reason: Resource contract output 'rcd_output_s39' has requiredness=unspecified and no renderable producer. Review whether this output should be declared optional or a producer step should be added.

### stage2_route_refinement_conflict_s52: `route_refinement_conflict`
- Severity: `info`
- Target: `span:s52`
- Source spans: `s52`
- Message: route_refinement_conflict: span 's52' has both executable and non-executable annotations with populated semantic roles
- Blocks rendering: `false`
- Blocks completion: `false`

### stage2_route_refinement_diagnostic_: `route_refinement_diagnostic`
- Severity: `info`
- Message: LLM route diagnostic [mixed_failure_semantics] span='s52': Condition and handler are mixed; emitted multi-label.
- Blocks rendering: `false`
- Blocks completion: `false`

### stage2_route_refinement_rejected_s49: `route_refinement_rejected`
- Severity: `info`
- Target: `span:s49`
- Source spans: `s49`
- Message: Rejected: exception_handler_action for span 's49' has no handler action verb in source text 'If such information cannot be obtained record the missing items'
- Blocks rendering: `false`
- Blocks completion: `false`

### stage2_route_refinement_rejected_s50: `route_refinement_rejected`
- Severity: `info`
- Target: `span:s50`
- Source spans: `s50`
- Message: Rejected: exception_handler_action for span 's50' has no handler action verb in source text 'do not generate a full draft'
- Blocks rendering: `false`
- Blocks completion: `false`

### stage2_route_refinement_split_s52: `route_refinement_split`
- Severity: `info`
- Target: `span:s52`
- Source spans: `s52`
- Message: Split recommended for s52: The span mixes a failure condition with a handler instruction.
- Blocks rendering: `false`
- Blocks completion: `false`

### view:resource-contract-annotation-missing-requiredness:rcd_output_s37: `resource_contract_annotation_missing_requiredness`
- Severity: `info`
- Target: `rcd_output_s37`
- Source spans: `s37`
- Message: Requiredness is unspecified for demand rcd_output_s37 (span s37).
- Blocks rendering: `false`
- Blocks completion: `false`

### view:resource-contract-annotation-missing-requiredness:rcd_output_s38: `resource_contract_annotation_missing_requiredness`
- Severity: `info`
- Target: `rcd_output_s38`
- Source spans: `s38`
- Message: Requiredness is unspecified for demand rcd_output_s38 (span s38).
- Blocks rendering: `false`
- Blocks completion: `false`

### view:resource-contract-annotation-missing-requiredness:rcd_output_s39: `resource_contract_annotation_missing_requiredness`
- Severity: `info`
- Target: `rcd_output_s39`
- Source spans: `s39`
- Message: Requiredness is unspecified for demand rcd_output_s39 (span s39).
- Blocks rendering: `false`
- Blocks completion: `false`

### condition_variable_not_available_before_decision_cond_ref_3512d2fc9b_llm_0: `condition_variable_not_available_before_decision`
- Severity: `warning`
- Target: `condition:block:worker_main:main:b_4`
- Source spans: `s30, s31, s32, s33, s34, s35`
- Message: Condition reference draft communication artifact is produced after or inside the decision it controls.
- Blocks rendering: `false`
- Blocks completion: `true`

## 5. Deferred Validation

No downstream validation was deferred.

## 6. Assumptions / Suggestions

- `ASM_0000` for `worker:worker_main.exception_flow:exc_adapter_00`: Exception flow has no handler action. The compiler suggests specifying what should happen when this failure occurs.
  - Reason: Source describes a failure condition but does not specify how to handle it.  The exception flow is preserved in SPL, but no handler command was rendered. (Exception flow 'exc_adapter_00' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adap)
  - Suggested resolution: Specify the handler action for worker:worker_main.exception_flow:exc_adapter_00: e.g. ask the user for missing information, block finalization, or continue with an explicit assumption.
  - Related diagnostic: `irs_def107932ceb`
- `ASM_0001` for `worker:worker_main.exception_flow:exc_adapter_01`: Exception flow has no handler action. The compiler suggests specifying what should happen when this failure occurs.
  - Reason: Source describes a failure condition but does not specify how to handle it.  The exception flow is preserved in SPL, but no handler command was rendered. (Exception flow 'exc_adapter_01' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adap)
  - Suggested resolution: Specify the handler action for worker:worker_main.exception_flow:exc_adapter_01: e.g. ask the user for missing information, block finalization, or continue with an explicit assumption.
  - Related diagnostic: `irs_d969ce57e92a`
- `ASM_0002` for `worker:worker_main.output:source_evidence_set`: Required output has no source-backed producer. The compiler suggests adding a step that explicitly produces this output.
  - Reason: The source requires this output but does not describe how it should be produced.  The output is kept in the OUTPUTS contract, but no producer step was rendered.
  - Suggested resolution: Add a source-backed step that produces worker:worker_main.output:source_evidence_set. If the source does not specify how to produce it, mark it as optional or remove it from the required output contract.
  - Related diagnostic: `irs_ae87eac80c3d`
- `ASM_0003` for `worker:worker_main.output:completion_status`: Required output has no source-backed producer. The compiler suggests adding a step that explicitly produces this output.
  - Reason: The source requires this output but does not describe how it should be produced.  The output is kept in the OUTPUTS contract, but no producer step was rendered.
  - Suggested resolution: Add a source-backed step that produces worker:worker_main.output:completion_status. If the source does not specify how to produce it, mark it as optional or remove it from the required output contract.
  - Related diagnostic: `irs_5143c9abd16e`
- `ASM_0004` for `resource_contract_demand:rcd_output_s17`: Required output has no source-backed producer. The compiler suggests adding a step that explicitly produces this output.
  - Reason: The source requires this output but does not describe how it should be produced.  The output is kept in the OUTPUTS contract, but no producer step was rendered.
  - Suggested resolution: Add a source-backed step that produces resource_contract_demand:rcd_output_s17. If the source does not specify how to produce it, mark it as optional or remove it from the required output contract.
  - Related diagnostic: `irs_17b4cac9bea8`
- `ASM_0005` for `resource_contract_demand:rcd_output_s19`: Required output has no source-backed producer. The compiler suggests adding a step that explicitly produces this output.
  - Reason: The source requires this output but does not describe how it should be produced.  The output is kept in the OUTPUTS contract, but no producer step was rendered.
  - Suggested resolution: Add a source-backed step that produces resource_contract_demand:rcd_output_s19. If the source does not specify how to produce it, mark it as optional or remove it from the required output contract.
  - Related diagnostic: `irs_b096d94cafe8`
- `ASM_0006` for `variable:known_topics`: Variable has no discoverable source provenance.
  - Reason: The compiler could not trace this variable back to a source span, adapter hard fact, or producer step.  Its origin is assumed.
  - Suggested resolution: For variable:known_topics: add source evidence (a span, adapter hint, or producer step) that justifies this variable's existence.
  - Related diagnostic: `diag_prov_0000`
- `ASM_0007` for `variable:timeframe`: Variable has no discoverable source provenance.
  - Reason: The compiler could not trace this variable back to a source span, adapter hard fact, or producer step.  Its origin is assumed.
  - Suggested resolution: For variable:timeframe: add source evidence (a span, adapter hint, or producer step) that justifies this variable's existence.
  - Related diagnostic: `diag_prov_0001`
- `ASM_0008` for `variable:background_information`: Variable has no discoverable source provenance.
  - Reason: The compiler could not trace this variable back to a source span, adapter hard fact, or producer step.  Its origin is assumed.
  - Suggested resolution: For variable:background_information: add source evidence (a span, adapter hint, or producer step) that justifies this variable's existence.
  - Related diagnostic: `diag_prov_0002`
- `ASM_0009` for `variable:target_audience`: Variable has no discoverable source provenance.
  - Reason: The compiler could not trace this variable back to a source span, adapter hard fact, or producer step.  Its origin is assumed.
  - Suggested resolution: For variable:target_audience: add source evidence (a span, adapter hint, or producer step) that justifies this variable's existence.
  - Related diagnostic: `diag_prov_0003`
- `ASM_0010` for `variable:available_information_sources`: Variable has no discoverable source provenance.
  - Reason: The compiler could not trace this variable back to a source span, adapter hard fact, or producer step.  Its origin is assumed.
  - Suggested resolution: For variable:available_information_sources: add source evidence (a span, adapter hint, or producer step) that justifies this variable's existence.
  - Related diagnostic: `diag_prov_0004`
- `ASM_0011` for `variable:format_preferences`: Variable has no discoverable source provenance.
  - Reason: The compiler could not trace this variable back to a source span, adapter hard fact, or producer step.  Its origin is assumed.
  - Suggested resolution: For variable:format_preferences: add source evidence (a span, adapter hint, or producer step) that justifies this variable's existence.
  - Related diagnostic: `diag_prov_0005`
- `ASM_0012` for `variable:user_communication_request`: Variable has no discoverable source provenance.
  - Reason: The compiler could not trace this variable back to a source span, adapter hard fact, or producer step.  Its origin is assumed.
  - Suggested resolution: For variable:user_communication_request: add source evidence (a span, adapter hint, or producer step) that justifies this variable's existence.
  - Related diagnostic: `diag_prov_0006`
- `ASM_0013` for `variable:source_evidence_set`: Variable has no discoverable source provenance.
  - Reason: The compiler could not trace this variable back to a source span, adapter hard fact, or producer step.  Its origin is assumed.
  - Suggested resolution: For variable:source_evidence_set: add source evidence (a span, adapter hint, or producer step) that justifies this variable's existence.
  - Related diagnostic: `diag_prov_0007`
- `ASM_0014` for `variable:completion_status`: Variable has no discoverable source provenance.
  - Reason: The compiler could not trace this variable back to a source span, adapter hard fact, or producer step.  Its origin is assumed.
  - Suggested resolution: For variable:completion_status: add source evidence (a span, adapter hint, or producer step) that justifies this variable's existence.
  - Related diagnostic: `diag_prov_0008`
- `ASM_0015` for `profile:persona`: Rendered profile item has no source-backed provenance.
  - Reason: The compiler rendered this required profile item, but could not trace it to a source span.
  - Suggested resolution: For profile:persona: add source evidence that justifies this profile item, or confirm the assumption-bearing draft.
  - Related diagnostic: `diag_prov_0009`
- `ASM_0016` for `profile:persona.aspect:0`: Unrendered profile item has no source-backed provenance.
  - Reason: The compiler did not render this optional profile item because it could not trace it to a source span.
  - Suggested resolution: For profile:persona.aspect:0: add source evidence that justifies this profile item, or confirm the assumption-bearing draft.
  - Related diagnostic: `diag_prov_0010`
- `ASM_0017` for `profile:concept:5`: Unrendered profile item has no source-backed provenance.
  - Reason: The compiler did not render this optional profile item because it could not trace it to a source span.
  - Suggested resolution: For profile:concept:5: add source evidence that justifies this profile item, or confirm the assumption-bearing draft.
  - Related diagnostic: `diag_prov_0011`
- `ASM_0018` for `profile:concept:6`: Unrendered profile item has no source-backed provenance.
  - Reason: The compiler did not render this optional profile item because it could not trace it to a source span.
  - Suggested resolution: For profile:concept:6: add source evidence that justifies this profile item, or confirm the assumption-bearing draft.
  - Related diagnostic: `diag_prov_0012`
- `ASM_0019` for `profile:concept:7`: Unrendered profile item has no source-backed provenance.
  - Reason: The compiler did not render this optional profile item because it could not trace it to a source span.
  - Suggested resolution: For profile:concept:7: add source evidence that justifies this profile item, or confirm the assumption-bearing draft.
  - Related diagnostic: `diag_prov_0013`
- `ASM_0020` for `profile:concept:8`: Unrendered profile item has no source-backed provenance.
  - Reason: The compiler did not render this optional profile item because it could not trace it to a source span.
  - Suggested resolution: For profile:concept:8: add source evidence that justifies this profile item, or confirm the assumption-bearing draft.
  - Related diagnostic: `diag_prov_0014`
- `ASM_0021` for `profile:concept:9`: Unrendered profile item has no source-backed provenance.
  - Reason: The compiler did not render this optional profile item because it could not trace it to a source span.
  - Suggested resolution: For profile:concept:9: add source evidence that justifies this profile item, or confirm the assumption-bearing draft.
  - Related diagnostic: `diag_prov_0015`
- `ASM_0022, ASM_0023, ASM_0024, ASM_0025` for `worker_promotion:del_s54`: Worker promotion has an incomplete contract.
  - Reason: The candidate is blocked by multiple missing promotion slots.
  - Suggested resolution: Provide the missing input/output contracts, invocation point, and result handoff details listed in the related diagnostics.
  - Related diagnostics: `irs_0297500e5eab, irs_ef243c3fbeaa, irs_35d11eb78fc7, irs_cbf0a65b4e21`
- `ASM_0026, ASM_0027, ASM_0028, ASM_0029` for `worker_promotion:del_s55`: Worker promotion has an incomplete contract.
  - Reason: The candidate is blocked by multiple missing promotion slots.
  - Suggested resolution: Provide the missing input/output contracts, invocation point, and result handoff details listed in the related diagnostics.
  - Related diagnostics: `irs_17fdeaa57275, irs_e4ee1be21120, irs_f2dba60ddc61, irs_ea4169e64ade`
- `ASM_0030` for `worker:worker_main.span:s26`: A behavior span from the source was not mapped to any executable step.
  - Reason: The source describes behavior that could not be translated into a concrete command.  This may be intentional (policy, non-executable description) or may indicate missing detail.
  - Suggested resolution: For worker:worker_main.span:s26: either add a step implementing this behavior, or acknowledge it as non-executable context.
  - Related diagnostic: `diag_s7_0000`

## 7. Provenance / TraceRecords

- `constraint:c_1` -> `direct`
  - Source: spans=`s41`, section=`sec_policies`, packet=`p_list_item_do_not_fabricate_facts`
  - Explanation: Constraint 'c_1' (prohibition): Do not fabricate facts.
- `constraint:c_2` -> `direct`
  - Source: spans=`s44`, section=`sec_policies`, packet=`p_list_item_sources_that_are_not_provided_by_the_user_or_obtained_from_available_information_sources_external_facts_must_have_traceable_sources_facts_directly_provided_by_the_user_shall_be_marked_as_user_provided_information_prioritize_information_already_provided_by_the_user_to_avoid_unnecessary_information_retrieval_and_clarifying_questions_do_not_alter_the_meaning_of_the_user_s_original_request_for_the_sake_of_completeness`
  - Explanation: Constraint 'c_2' (evidence): External facts must have traceable sources; facts directly provided by the user
- `constraint:c_3` -> `direct`
  - Source: spans=`s46`, section=`sec_policies`, packet=`p_list_item_professionalism_of_expression_do_not_mark_the_task_as_complete_if_critical_information_is_missing_or_conflicting_instructions_remain_unresolved`
  - Explanation: Constraint 'c_3' (gate): Do not mark the task as complete if critical information is missing or conflicti
- `constraint:c_4` -> `direct`
  - Source: spans=`s57`, section=`sec_delegation_policy`, packet=`p_list_item_though_delegation_is_not_mandatory_delegated_tasks_shall_not_expand_the_scope_of_the_original_task_nor_alter_the_user_s_original_requirements_the_main_process_shall_verify_that_delegated_results_comply_with_the_task_scope_and_user_requirements_before_adopting_them_if_delegation_fails_or_returns_results_beyond_the_authorized_scope`
  - Explanation: Constraint 'c_4' (delegation_boundary): Delegated tasks shall not expand the scope of the original task nor alter the us
- `constraint:c_5` -> `direct`
  - Source: spans=`s59`, section=`sec_delegation_policy`, packet=`p_list_item_though_delegation_is_not_mandatory_delegated_tasks_shall_not_expand_the_scope_of_the_original_task_nor_alter_the_user_s_original_requirements_the_main_process_shall_verify_that_delegated_results_comply_with_the_task_scope_and_user_requirements_before_adopting_them_if_delegation_fails_or_returns_results_beyond_the_authorized_scope`
  - Explanation: Constraint 'c_5' (gate): If delegation fails or returns results beyond the authorized scope, such results
- `flow:alt_1` -> `direct`
  - Source: spans=`s40`, section=`sec_reusable_process`, packet=`p_list_item_completion_status_if_the_user_requests_revisions_to_the_draft`
  - Explanation: Alternative flow 'alt_1': if the user requests revisions to the draft
- `flow:exc_adapter_00` -> `direct`
  - Source: spans=`s52a, s52b`, section=`sec_conflicting_instructions`, packet=`p_list_item_if_the_user_s_requirements_conflict_and_impede_task_execution`
  - Explanation: Exception flow 'exc_adapter_00': If the user’s requirements conflict and impede task execution
- `flow:exc_adapter_01` -> `direct`
  - Source: spans=`s47, s48`, section=`sec_failure_handling`, packet=`p_list_item_missing_critical_information_if_information_essential_to_task_completion_is_lacking`
  - Explanation: Exception flow 'exc_adapter_01': Missing Critical Information:
- `flow:main` -> `direct`
  - Source: spans=`s20, s21, s22, s23, s24, s25, s27, s28, s29, s30, s31, s32, s33, s34, s35, s36, s48, s51, s52b, s53, s58, s60`, section=`sec_reusable_process`, packet=`p_list_item_analyze_the_user_s_request_to_clarify_the_type_of_communication_material`
  - Explanation: Main flow with 12 block(s).
- `profile:audience:0` -> `derived`
  - Source: spans=`s6, s7, s8`, section=`sec_task_family`
  - Explanation: Audience: InternalCompanyAudience
- `profile:concept:0` -> `derived`
  - Source: spans=`s1, s5`, section=`sec_task_family`
  - Explanation: Concept: Internal newsletters -- Newsletter-style communication materials intended for internal company use.
- `profile:concept:1` -> `derived`
  - Source: spans=`s2, s5`, section=`sec_task_family`
  - Explanation: Concept: Internal announcements -- Announcements shared within a company for internal audiences.
- `profile:concept:2` -> `normalized`
  - Source: spans=`s3`, section=`sec_task_family`, packet=`p_list_item_periodic_update_digests`
  - Explanation: Concept: Periodic update digests -- Regular summary communications that compile updates over time.
- `profile:concept:3` -> `derived`
  - Source: spans=`s4, s6`, section=`sec_task_family`
  - Explanation: Concept: Executive briefs -- Concise communication materials prepared for executives or senior leadership.
- `profile:concept:4` -> `normalized`
  - Source: spans=`s5`, section=`sec_task_family`, packet=`p_list_item_other_internal_facing_communication_materials_these_materials_are_primarily_intended_for_reading_and_use_by_company_employees`
  - Explanation: Concept: Internal-facing communication materials -- Communication artifacts primarily intended to be read and used by company employees.
- `profile:concept:5` -> `assumed` [needs confirmation]
  - Explanation: Concept: Communication purpose -- The intended objective or function of the communication.
- `profile:concept:6` -> `assumed` [needs confirmation]
  - Explanation: Concept: Target audience -- The intended recipients or readers of the communication.
- `profile:concept:7` -> `assumed` [needs confirmation]
  - Explanation: Concept: Source/evidence set -- A collected set of supporting sources or evidence used to justify the draft.
- `profile:concept:8` -> `assumed` [needs confirmation]
  - Explanation: Concept: Unresolved items -- Open issues or missing points that could not be fully resolved during the task.
- `profile:concept:9` -> `assumed` [needs confirmation]
  - Explanation: Concept: Completion status -- A final indication of whether the task was completed or remains incomplete.
- `profile:persona` -> `assumed` [needs confirmation]
  - Explanation: Persona: Internal communication drafting assistant
- `profile:persona.aspect:0` -> `assumed` [needs confirmation]
  - Explanation: Persona aspect: AccuracyFocused
- `profile:persona.aspect:1` -> `normalized`
  - Source: spans=`s45`, section=`sec_policies`, packet=`p_list_item_fluency`
  - Explanation: Persona aspect: ProfessionalAndFluent
- `profile:persona.aspect:2` -> `derived`
  - Source: spans=`s21, s22, s31, s32, s33, s34`, section=`sec_reusable_process`
  - Explanation: Persona aspect: RequirementsDriven
- `step:st_1` -> `direct`
  - Source: spans=`s20`, section=`sec_reusable_process`, packet=`p_list_item_analyze_the_user_s_request_to_clarify_the_type_of_communication_material`
  - Explanation: Step 'st_1' maps to source span(s).
- `step:st_10` -> `direct`
  - Source: spans=`s36`, section=`sec_reusable_process`, packet=`p_list_item_revise_it_based_on_the_verification_results_output_the_draft_communication_artifact`
  - Explanation: Step 'st_10' maps to source span(s).
- `step:st_11` -> `direct`
  - Source: spans=`s58`, section=`sec_delegation_policy`, packet=`p_list_item_though_delegation_is_not_mandatory_delegated_tasks_shall_not_expand_the_scope_of_the_original_task_nor_alter_the_user_s_original_requirements_the_main_process_shall_verify_that_delegated_results_comply_with_the_task_scope_and_user_requirements_before_adopting_them_if_delegation_fails_or_returns_results_beyond_the_authorized_scope`
  - Explanation: Step 'st_11' maps to source span(s).
- `step:st_12` -> `direct`
  - Source: spans=`s37`, section=`sec_reusable_process`, packet=`p_list_item_revise_it_based_on_the_verification_results_output_the_draft_communication_artifact`
  - Explanation: Step 'st_12' maps to source span(s).
- `step:st_13` -> `direct`
  - Source: spans=`s40`, section=`sec_reusable_process`, packet=`p_list_item_completion_status_if_the_user_requests_revisions_to_the_draft`
  - Explanation: Step 'st_13' maps to source span(s).
- `step:st_2` -> `direct`
  - Source: spans=`s21, s22, s23`, section=`sec_reusable_process`, packet=`p_list_item_communication_purpose`
  - Explanation: Step 'st_2' maps to source span(s).
- `step:st_3` -> `direct`
  - Source: spans=`s24`, section=`sec_reusable_process`, packet=`p_list_item_expression_requirements_check_if_the_facts_and_background_information_needed_to_generate_the_material_are_available_if_critical_information_that_affects_content_accuracy_is_missing`
  - Explanation: Step 'st_3' maps to source span(s).
- `step:st_4` -> `direct`
  - Source: spans=`s25`, section=`sec_reusable_process`, packet=`p_list_item_expression_requirements_check_if_the_facts_and_background_information_needed_to_generate_the_material_are_available_if_critical_information_that_affects_content_accuracy_is_missing`
  - Explanation: Step 'st_4' maps to source span(s).
- `step:st_5` -> `direct`
  - Source: spans=`s27`, section=`sec_reusable_process`, packet=`p_list_item_proceed_organize_the_obtained_facts_and_background_information`
  - Explanation: Step 'st_5' maps to source span(s).
- `step:st_6` -> `direct`
  - Source: spans=`s28`, section=`sec_reusable_process`, packet=`p_list_item_extract_core_messages_to_be_conveyed`
  - Explanation: Step 'st_6' maps to source span(s).
- `step:st_7` -> `direct`
  - Source: spans=`s29`, section=`sec_reusable_process`, packet=`p_list_item_structure_the_content_based_on_the_material_type_generate_a_draft_communication_artifact_and_verify_if_it_meets_the_user_s_specified_requirements_for_target_audience`
  - Explanation: Step 'st_7' maps to source span(s).
- `step:st_8` -> `direct`
  - Source: spans=`s30`, section=`sec_reusable_process`, packet=`p_list_item_structure_the_content_based_on_the_material_type_generate_a_draft_communication_artifact_and_verify_if_it_meets_the_user_s_specified_requirements_for_target_audience`
  - Explanation: Step 'st_8' maps to source span(s).
- `step:st_9` -> `direct`
  - Source: spans=`s31, s32, s33, s34, s35`, section=`sec_reusable_process`, packet=`p_list_item_tone`
  - Explanation: Step 'st_9' maps to source span(s).
- `variable:available_information_sources` -> `assumed` [needs confirmation]
  - Explanation: Variable 'available_information_sources' is declared as worker input contract with no source evidence.
- `variable:background_information` -> `assumed` [needs confirmation]
  - Explanation: Variable 'background_information' is declared as worker input contract with no source evidence.
- `variable:completion_status` -> `assumed` [needs confirmation]
  - Explanation: Variable 'completion_status' is declared as worker output contract with no source evidence.
- `variable:draft_communication_artifact` -> `direct`
  - Source: spans=`s20`, section=`sec_reusable_process`, packet=`p_list_item_analyze_the_user_s_request_to_clarify_the_type_of_communication_material`
  - Explanation: Variable 'draft_communication_artifact' is produced by source-backed step 'st_1'.
- `variable:format_preferences` -> `assumed` [needs confirmation]
  - Explanation: Variable 'format_preferences' is declared as worker input contract with no source evidence.
- `variable:known_topics` -> `assumed` [needs confirmation]
  - Explanation: Variable 'known_topics' is declared as worker input contract with no source evidence.
- `variable:source_evidence_set` -> `assumed` [needs confirmation]
  - Explanation: Variable 'source_evidence_set' is declared as worker output contract with no source evidence.
- `variable:target_audience` -> `assumed` [needs confirmation]
  - Explanation: Variable 'target_audience' is declared as worker input contract with no source evidence.
- `variable:timeframe` -> `assumed` [needs confirmation]
  - Explanation: Variable 'timeframe' is declared as worker input contract with no source evidence.
- `variable:unresolved_items` -> `direct`
  - Source: spans=`s58`, section=`sec_delegation_policy`, packet=`p_list_item_though_delegation_is_not_mandatory_delegated_tasks_shall_not_expand_the_scope_of_the_original_task_nor_alter_the_user_s_original_requirements_the_main_process_shall_verify_that_delegated_results_comply_with_the_task_scope_and_user_requirements_before_adopting_them_if_delegation_fails_or_returns_results_beyond_the_authorized_scope`
  - Explanation: Variable 'unresolved_items' is produced by source-backed step 'st_11'.
- `variable:user_communication_request` -> `assumed` [needs confirmation]
  - Explanation: Variable 'user_communication_request' is declared as worker input contract with no source evidence.
- `worker:MainWorker` -> `direct`
  - Source: spans=`s20, s21, s22, s23, s24, s25, s26, s27, s28, s29, s30, s31, s32, s33, s34, s35, s36, s40, s48, s51, s52a, s52b, s53, s58, s60, s37`, section=`sec_reusable_process`, packet=`p_list_item_analyze_the_user_s_request_to_clarify_the_type_of_communication_material`
  - Explanation: Main worker 'MainWorker' assembled from flow and step IRs.

## 8. Anti-Fabrication Checks

- `missing_handler`: Exception conditions without handler action stay as partial exception flows; no handler command is invented.
- `missing_output_producer`: Required outputs without a source-backed producer stay in the contract; no synthetic producer command is invented.
- `type_or_contract_ambiguity`: Unresolved worker/API contracts are reported as ambiguity; they are not downgraded to generic commands.
- Rendered SPL contains no executable `[INVOKE ...]` command.

## 9. Adapter / Validation Notes

Validation errors:
- Worker worker_main step st_12 is DISPLAY_MESSAGE but declares outputs; Stage 9.5 will not reclassify it.

Validation warnings:
- ConstructPlan: cannot enforce ownership for exc_demand_03; condition spans have owners [].
- ConstructPlan: condition span s47 for exc_demand_03 has unowned; attached to main worker worker_main.
- ConstructPlan: cannot enforce ownership for exc_demand_03; condition spans have owners [].
- ConstructPlan: condition span s47 for exc_demand_03 has unowned; attached to main worker worker_main.
- Worker worker_main: variable 'draft_communication_artifact' produced by multiple steps
- Worker worker_main: variable 'draft_communication_artifact' produced by multiple steps
- Condition reference draft communication artifact is produced after or inside the decision it controls.

## 10. SPL Draft

```spl
[DEFINE_AGENT: MainWorker "Orchestrate the end-to-end process and delegate to sub-tasks."]
    [DEFINE_PERSONA:]
        ROLE: Internal communication drafting assistant
        ProfessionalAndFluent: Produces communication with professional expression and fluency.
        RequirementsDriven: Checks communication purpose, target audience, tone, language, length, structure, and format against user requirements before finalizing.
    [END_PERSONA]
    [DEFINE_AUDIENCE:]
        InternalCompanyAudience: Company employees and other internal audiences specified by the user, including management and department heads.
    [END_AUDIENCE]
    [DEFINE_CONCEPTS:]
        Internalnewsletters: Newsletter-style communication materials intended for internal company use.
        Internalannouncements: Announcements shared within a company for internal audiences.
        Periodicupdatedigests: Regular summary communications that compile updates over time.
        Executivebriefs: Concise communication materials prepared for executives or senior leadership.
        Internalfacingcommunicationmaterials: Communication artifacts primarily intended to be read and used by company employees.
    [END_CONCEPTS]
    [DEFINE_CONSTRAINTS:]
        Prohibition: Do not fabricate facts.
        Evidence: External facts must have traceable sources; facts directly provided by the user shall be marked as user-provided information. Prioritize information already provided by the user to avoid unnecessary information retrieval and clarifying questions. Do not alter the meaning of the user’s original request for the sake of completeness.
        Gate: Do not mark the task as complete if critical information is missing or conflicting instructions remain unresolved.
        DelegationBoundary: Delegated tasks shall not expand the scope of the original task nor alter the user’s original requirements.
        Gate: If delegation fails or returns results beyond the authorized scope, such results shall not be adopted.
    [END_CONSTRAINTS]
    [DEFINE_VARIABLES:]
        "Topics that the communication should address." known_topics: List [text]
        "Time period or deadline relevant to the communication." timeframe: text
        "Background context needed to prepare the communication." background_information: text
        "Intended audience for the communication." target_audience: text
        "Sources available to inform the communication." available_information_sources: List [text]
        "Preferred format and style constraints for the communication." format_preferences: text
        "The user's requested communication task." user_communication_request: text
        "Draft communication content produced for the user." draft_communication_artifact: text
        "Collected evidence or supporting sources used for the draft." source_evidence_set: List [text]
        "Items that remain unresolved during the task." unresolved_items: List [text]
        "Final status of task completion." completion_status: text
    [END_VARIABLES]
    [DEFINE_WORKER: "Orchestrate the end-to-end process and delegate to sub-tasks." MainWorker]
        [INPUTS]
            REQUIRED <REF>known_topics</REF>
            REQUIRED <REF>timeframe</REF>
            REQUIRED <REF>background_information</REF>
            REQUIRED <REF>target_audience</REF>
            REQUIRED <REF>available_information_sources</REF>
            REQUIRED <REF>format_preferences</REF>
            REQUIRED <REF>user_communication_request</REF>
        [END_INPUTS]
        [OUTPUTS]
            REQUIRED <REF>draft_communication_artifact</REF>
            REQUIRED <REF>source_evidence_set</REF>
            REQUIRED <REF>unresolved_items</REF>
            REQUIRED <REF>completion_status</REF>
            <REF>draft_communication_artifact</REF>
            <REF>unresolved_items</REF>
            <REF>completion_status</REF>
        [END_OUTPUTS]
        [MAIN_FLOW]
            [SEQUENTIAL_BLOCK]
                COMMAND-1 [COMMAND Analyze the user request to determine communication material type and produce draft communication artifact based on <REF>user_communication_request</REF> RESULT draft_communication_artifact: text SET]
                COMMAND-2 [COMMAND Check communication purpose, target audience, and expression requirements based on <REF>user_communication_request</REF>, <REF>target_audience</REF>, and <REF>format_preferences</REF>]
            [END_SEQUENTIAL_BLOCK]
            DECISION-1 [IF critical information that affects content accuracy is missing]
                COMMAND-3 [COMMAND Check whether required facts and background information are available based on <REF>background_information</REF> and <REF>known_topics</REF>]
            [END_IF]
            DECISION-2 [IF critical information that affects content accuracy is missing]
                COMMAND-4 [INPUT Ask the user clarifying questions and produce draft communication artifact VALUE <REF>draft_communication_artifact</REF> SET]
            [END_IF]
            [SEQUENTIAL_BLOCK]
                COMMAND-5 [COMMAND Organize the obtained facts and background information based on <REF>background_information</REF>, <REF>known_topics</REF>, and <REF>target_audience</REF>]
                COMMAND-6 [COMMAND Extract core messages based on <REF>background_information</REF> and <REF>known_topics</REF>]
                COMMAND-7 [COMMAND Structure the content by material type based on <REF>format_preferences</REF> and <REF>target_audience</REF>]
            [END_SEQUENTIAL_BLOCK]
            DECISION-3 [IF the <REF>draft_communication_artifact</REF> does not meet the user’s specified requirements for <REF>target_audience</REF> tone language length structure format]
                COMMAND-8 [COMMAND Generate the draft communication artifact based on <REF>background_information</REF>, <REF>known_topics</REF>, <REF>target_audience</REF>, and <REF>format_preferences</REF> RESULT <REF>draft_communication_artifact</REF> SET]
                COMMAND-9 [COMMAND Verify the draft against target audience, tone, language, length, structure, and format requirements based on <REF>target_audience</REF> and <REF>format_preferences</REF>]
                COMMAND-10 [DISPLAY Display the draft communication artifact based on <REF>draft_communication_artifact</REF>]
            [END_IF]
            DECISION-4 [IF not]
                COMMAND-11 [COMMAND Revise the draft based on verification results]
            [END_IF]
            [SEQUENTIAL_BLOCK]
                COMMAND-12 [COMMAND Verify delegated results against task scope and user requirements and produce unresolved items based on <REF>user_communication_request</REF> RESULT unresolved_items: List [text] SET]
            [END_SEQUENTIAL_BLOCK]
        [END_MAIN_FLOW]
        [ALTERNATIVE_FLOW: the user requests revisions to the draft]
            [SEQUENTIAL_BLOCK]
                COMMAND-13 [COMMAND Revise the draft and recheck compliance based on <REF>draft_communication_artifact</REF> and <REF>user_communication_request</REF>]
            [END_SEQUENTIAL_BLOCK]
        [END_ALTERNATIVE_FLOW]
        [EXCEPTION_FLOW: the user’s requirements conflict and impede task execution]
        [END_EXCEPTION_FLOW]
        [EXCEPTION_FLOW: Missing Critical Information:]
        [END_EXCEPTION_FLOW]
    [END_WORKER]
[END_AGENT]
```
