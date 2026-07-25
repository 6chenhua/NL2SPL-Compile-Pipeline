# NL2SPL Feedback Report

## 1. Overall Compile State

- Completeness: `partial`
- SPL draft generated: `yes`
- Compile diagnostics: `31`
- Assumptions / suggestions: `29`
- Trace records: `50`
- Adapter warnings: `0`
- Validation errors: `0`
- Validation warnings: `0`

Result is partial because the following requirement gaps remain:
- `missing_output_producer` on `resource_contract_demand:rcd_output_s12`: Resource contract output 'rcd_output_s12' (requiredness=required) has materialized resource(s) record_of_unresolved_items but no renderable producer. [construct=resource_contract_demand:rcd_output_s12, slot=producer]
- `missing_output_producer` on `worker:worker_main.output:completion_status`: Required output 'completion_status' (Task completion status) has no source-backed producer step. [construct=worker:worker_main.output:completion_status, slot=producer]
- `missing_output_producer` on `worker:worker_main.output:record_of_unresolved_items`: Required output 'record_of_unresolved_items' (List of unresolved items) has no source-backed producer step. [construct=worker:worker_main.output:record_of_unresolved_items, slot=producer]
- `missing_output_producer` on `worker:worker_main.output:source_evidence_set`: Required output 'source_evidence_set' (Collected source and evidence items) has no source-backed producer step. [construct=worker:worker_main.output:source_evidence_set, slot=producer]
- `missing_output_producer` on `resource_contract_demand:rcd_output_s13`: Resource contract output 'rcd_output_s13' (requiredness=required) has materialized resource(s) completion_status but no renderable producer. [construct=resource_contract_demand:rcd_output_s13, slot=producer]
- `missing_output_producer` on `resource_contract_demand:rcd_output_s11`: Resource contract output 'rcd_output_s11' (requiredness=required) has materialized resource(s) source_evidence_set but no renderable producer. [construct=resource_contract_demand:rcd_output_s11, slot=producer]
- `type_or_contract_ambiguity` on `worker_promotion:del_s31`: WORKER_PROMOTION blocked by missing promotion slots.
  - `promotion_input_contract`: Missing clear input contract
  - `promotion_output_contract`: Missing clear output contract
  - `promotion_invocation_point`: Missing accepted decision or matching handoff with invocation hint
  - `promotion_result_handoff`: Missing matching handoff with output bindings
- `type_or_contract_ambiguity` on `worker:worker_main.step:st_3`: REQUEST_INPUT step has no value target (outputs). [construct=worker:worker_main.step:st_3, slot=value_target]
- `missing_provenance` on `profile:persona`: Rendered profile item 'profile:persona' has no source-backed provenance.

## 2. Materialized Source-Backed Structure

### Workers
- `worker:MainWorker` (direct) -- spans=s14, s15, s16, s17, s18, s19, s20, s21, s27, s28, s29, s30; section=sec_reusable_process; packet=p_sentence_analyze_the_user_s_request_to_clarify_the_type_of_communication_material_communication_purpose_target_audience_and_expression_requirements

### Profiles
- `profile:concept:0` (normalized) -- spans=s1; section=sec_task_family; packet=p_sentence_internal_newsletters_internal_announcements_periodic_update_digests_executive_briefs_and_other_internal_facing_communication_materials
- `profile:concept:1` (normalized) -- spans=s1; section=sec_task_family; packet=p_sentence_internal_newsletters_internal_announcements_periodic_update_digests_executive_briefs_and_other_internal_facing_communication_materials
- `profile:concept:2` (normalized) -- spans=s1; section=sec_task_family; packet=p_sentence_internal_newsletters_internal_announcements_periodic_update_digests_executive_briefs_and_other_internal_facing_communication_materials
- `profile:concept:3` (normalized) -- spans=s1; section=sec_task_family; packet=p_sentence_internal_newsletters_internal_announcements_periodic_update_digests_executive_briefs_and_other_internal_facing_communication_materials
- `profile:concept:4` (normalized) -- spans=s1; section=sec_task_family; packet=p_sentence_internal_newsletters_internal_announcements_periodic_update_digests_executive_briefs_and_other_internal_facing_communication_materials
- `profile:persona.aspect:1` (normalized) -- spans=s7; section=sec_inputs_for_each_run; packet=p_list_item_target_audience

### Flows
- `flow:alt_1` (direct) -- spans=s16, s16; section=sec_reusable_process; packet=p_sentence_if_critical_information_that_affects_content_accuracy_is_missing_ask_the_user_necessary_clarifying_questions_if_the_information_is_available_proceed
- `flow:exc_adapter_00` (direct) -- spans=s28, s28; section=sec_failure_handling; packet=p_sentence_if_such_information_cannot_be_obtained_record_the_missing_items_do_not_generate_a_full_draft_and_mark_the_task_as_incomplete
- `flow:exc_adapter_01` (direct) -- spans=s29, s29, s30; section=sec_conflicting_instructions; packet=p_sentence_if_the_user_s_requirements_conflict_and_impede_task_execution_document_the_specific_conflicts
- `flow:exc_adapter_02` (direct) -- spans=s27, s27; section=sec_failure_handling; packet=p_sentence_missing_critical_information_if_information_essential_to_task_completion_is_lacking_inquire_with_the_user
- `flow:main` (direct) -- spans=s14, s15, s17, s18, s19, s20, s21; section=sec_reusable_process; packet=p_sentence_analyze_the_user_s_request_to_clarify_the_type_of_communication_material_communication_purpose_target_audience_and_expression_requirements

### Steps
- `step:st_1` (direct) -- spans=s14; section=sec_reusable_process; packet=p_sentence_analyze_the_user_s_request_to_clarify_the_type_of_communication_material_communication_purpose_target_audience_and_expression_requirements
- `step:st_2` (direct) -- spans=s15; section=sec_reusable_process; packet=p_sentence_check_if_the_facts_and_background_information_needed_to_generate_the_material_are_available
- `step:st_3` (direct) -- spans=s16; section=sec_reusable_process; packet=p_sentence_if_critical_information_that_affects_content_accuracy_is_missing_ask_the_user_necessary_clarifying_questions_if_the_information_is_available_proceed
- `step:st_4` (direct) -- spans=s17; section=sec_reusable_process; packet=p_sentence_organize_the_obtained_facts_and_background_information_extract_core_messages_to_be_conveyed_and_structure_the_content_based_on_the_material_type
- `step:st_5` (direct) -- spans=s18; section=sec_reusable_process; packet=p_sentence_generate_a_draft_communication_artifact_and_verify_if_it_meets_the_user_s_specified_requirements_for_target_audience_tone_language_length_structure_and_format
- `step:st_6` (direct) -- spans=s19, s21; section=sec_reusable_process; packet=p_sentence_if_not_revise_it_based_on_the_verification_results
- `step:st_7` (direct) -- spans=s20; section=sec_reusable_process; packet=p_sentence_output_the_draft_communication_artifact_record_of_unresolved_items_and_completion_status
- `step:st_exception_exc_adapter_00_s28` (direct) -- spans=s28; section=sec_failure_handling; packet=p_sentence_if_such_information_cannot_be_obtained_record_the_missing_items_do_not_generate_a_full_draft_and_mark_the_task_as_incomplete
- `step:st_exception_exc_adapter_01_s29` (direct) -- spans=s29; section=sec_conflicting_instructions; packet=p_sentence_if_the_user_s_requirements_conflict_and_impede_task_execution_document_the_specific_conflicts
- `step:st_exception_exc_adapter_01_s30` (direct) -- spans=s30; section=sec_conflicting_instructions; packet=p_sentence_do_not_generate_a_full_draft_and_mark_the_task_as_incomplete_until_the_conflicts_are_resolved
- `step:st_exception_exc_adapter_02_s27` (direct) -- spans=s27; section=sec_failure_handling; packet=p_sentence_missing_critical_information_if_information_essential_to_task_completion_is_lacking_inquire_with_the_user

### Variables
- `variable:draft_communication_artifact` (direct) -- spans=s18; section=sec_reusable_process; packet=p_sentence_generate_a_draft_communication_artifact_and_verify_if_it_meets_the_user_s_specified_requirements_for_target_audience_tone_language_length_structure_and_format

### Constraints
- `constraint:c_1` (direct) -- spans=s22; section=sec_policies; packet=p_sentence_do_not_fabricate_facts_data_events_or_sources_that_are_not_provided_by_the_user_or_obtained_from_available_information_sources
- `constraint:c_2` (direct) -- spans=s23; section=sec_policies; packet=p_sentence_external_facts_must_have_traceable_sources_facts_directly_provided_by_the_user_shall_be_marked_as_user_provided_information
- `constraint:c_3` (direct) -- spans=s24; section=sec_policies; packet=p_sentence_prioritize_information_already_provided_by_the_user_to_avoid_unnecessary_information_retrieval_and_clarifying_questions
- `constraint:c_4` (direct) -- spans=s25; section=sec_policies; packet=p_sentence_do_not_alter_the_meaning_of_the_user_s_original_request_for_the_sake_of_completeness_fluency_or_professionalism_of_expression
- `constraint:c_5` (direct) -- spans=s26; section=sec_policies; packet=p_sentence_do_not_mark_the_task_as_complete_if_critical_information_is_missing_or_conflicting_instructions_remain_unresolved
- `constraint:c_6` (direct) -- spans=s32; section=sec_delegation_policy; packet=p_sentence_delegated_tasks_shall_not_expand_the_scope_of_the_original_task_nor_alter_the_user_s_original_requirements
- `constraint:c_7` (direct) -- spans=s33; section=sec_delegation_policy; packet=p_sentence_main_process_shall_verify_that_delegated_results_comply_with_the_task_scope_and_user_requirements_before_adopting_them
- `constraint:c_8` (direct) -- spans=s34; section=sec_delegation_policy; packet=p_sentence_if_delegation_fails_or_returns_results_beyond_the_authorized_scope_such_results_shall_not_be_adopted_if_the_results_are_essential_to_task_completion_record_unresolved_items_and_mark_the_task_as_incomplete

## 3. Not Materialized / Kept Partial

- `resource_contract_demand:rcd_output_s12`: `missing_output_producer` -- Resource contract output 'rcd_output_s12' (requiredness=required) has materialized resource(s) record_of_unresolved_items but no renderable producer. [construct=resource_contract_demand:rcd_output_s12, slot=producer]
  - Suggested resolution: Add a source-backed step or handoff that produces the materialized resource name with the same resource kind.
- `worker:worker_main.output:completion_status`: `missing_output_producer` -- Required output 'completion_status' (Task completion status) has no source-backed producer step. [construct=worker:worker_main.output:completion_status, slot=producer]
  - Suggested resolution: Add a step that produces 'completion_status'. If the source requirement does not specify how to produce this output, mark it as optional or remove it from the output contract.
- `worker:worker_main.output:record_of_unresolved_items`: `missing_output_producer` -- Required output 'record_of_unresolved_items' (List of unresolved items) has no source-backed producer step. [construct=worker:worker_main.output:record_of_unresolved_items, slot=producer]
  - Suggested resolution: Add a step that produces 'record_of_unresolved_items'. If the source requirement does not specify how to produce this output, mark it as optional or remove it from the output contract.
- `worker:worker_main.output:source_evidence_set`: `missing_output_producer` -- Required output 'source_evidence_set' (Collected source and evidence items) has no source-backed producer step. [construct=worker:worker_main.output:source_evidence_set, slot=producer]
  - Suggested resolution: Add a step that produces 'source_evidence_set'. If the source requirement does not specify how to produce this output, mark it as optional or remove it from the output contract.
- `resource_contract_demand:rcd_output_s13`: `missing_output_producer` -- Resource contract output 'rcd_output_s13' (requiredness=required) has materialized resource(s) completion_status but no renderable producer. [construct=resource_contract_demand:rcd_output_s13, slot=producer]
  - Suggested resolution: Add a source-backed step or handoff that produces the materialized resource name with the same resource kind.
- `resource_contract_demand:rcd_output_s11`: `missing_output_producer` -- Resource contract output 'rcd_output_s11' (requiredness=required) has materialized resource(s) source_evidence_set but no renderable producer. [construct=resource_contract_demand:rcd_output_s11, slot=producer]
  - Suggested resolution: Add a source-backed step or handoff that produces the materialized resource name with the same resource kind.
- `worker_promotion:del_s31`: `type_or_contract_ambiguity` -- WORKER_PROMOTION blocked by missing promotion slots.
  - Source spans: `s31`
  - `promotion_input_contract`: Missing clear input contract
  - `promotion_output_contract`: Missing clear output contract
  - `promotion_invocation_point`: Missing accepted decision or matching handoff with invocation hint
  - `promotion_result_handoff`: Missing matching handoff with output bindings
- `worker:worker_main.step:st_3`: `type_or_contract_ambiguity` -- REQUEST_INPUT step has no value target (outputs). [construct=worker:worker_main.step:st_3, slot=value_target]

## 4. Diagnostics

### irs_1af17bef9d62: `missing_output_producer`
- Severity: `warning`
- Target: `resource_contract_demand:rcd_output_s12`
- Source spans: `s12`
- Message: Resource contract output 'rcd_output_s12' (requiredness=required) has materialized resource(s) record_of_unresolved_items but no renderable producer. [construct=resource_contract_demand:rcd_output_s12, slot=producer]
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Add a source-backed step or handoff that produces the materialized resource name with the same resource kind.
- Missing slot: `producer`
- Missing reason: Resource contract output 'rcd_output_s12' (requiredness=required) has materialized resource(s) record_of_unresolved_items but no renderable producer.

### irs_5143c9abd16e: `missing_output_producer`
- Severity: `warning`
- Target: `worker:worker_main.output:completion_status`
- Message: Required output 'completion_status' (Task completion status) has no source-backed producer step. [construct=worker:worker_main.output:completion_status, slot=producer]
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Add a step that produces 'completion_status'. If the source requirement does not specify how to produce this output, mark it as optional or remove it from the output contract.
- Missing slot: `producer`
- Missing reason: Required output 'completion_status' (Task completion status) has no source-backed producer step.

### irs_7ef204235405: `missing_output_producer`
- Severity: `warning`
- Target: `worker:worker_main.output:record_of_unresolved_items`
- Message: Required output 'record_of_unresolved_items' (List of unresolved items) has no source-backed producer step. [construct=worker:worker_main.output:record_of_unresolved_items, slot=producer]
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Add a step that produces 'record_of_unresolved_items'. If the source requirement does not specify how to produce this output, mark it as optional or remove it from the output contract.
- Missing slot: `producer`
- Missing reason: Required output 'record_of_unresolved_items' (List of unresolved items) has no source-backed producer step.

### irs_ae87eac80c3d: `missing_output_producer`
- Severity: `warning`
- Target: `worker:worker_main.output:source_evidence_set`
- Message: Required output 'source_evidence_set' (Collected source and evidence items) has no source-backed producer step. [construct=worker:worker_main.output:source_evidence_set, slot=producer]
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Add a step that produces 'source_evidence_set'. If the source requirement does not specify how to produce this output, mark it as optional or remove it from the output contract.
- Missing slot: `producer`
- Missing reason: Required output 'source_evidence_set' (Collected source and evidence items) has no source-backed producer step.

### irs_b0d25f2c1af8: `missing_output_producer`
- Severity: `warning`
- Target: `resource_contract_demand:rcd_output_s13`
- Source spans: `s13`
- Message: Resource contract output 'rcd_output_s13' (requiredness=required) has materialized resource(s) completion_status but no renderable producer. [construct=resource_contract_demand:rcd_output_s13, slot=producer]
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Add a source-backed step or handoff that produces the materialized resource name with the same resource kind.
- Missing slot: `producer`
- Missing reason: Resource contract output 'rcd_output_s13' (requiredness=required) has materialized resource(s) completion_status but no renderable producer.

### irs_b9b0a6118031: `missing_output_producer`
- Severity: `warning`
- Target: `resource_contract_demand:rcd_output_s11`
- Source spans: `s11`
- Message: Resource contract output 'rcd_output_s11' (requiredness=required) has materialized resource(s) source_evidence_set but no renderable producer. [construct=resource_contract_demand:rcd_output_s11, slot=producer]
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Add a source-backed step or handoff that produces the materialized resource name with the same resource kind.
- Missing slot: `producer`
- Missing reason: Resource contract output 'rcd_output_s11' (requiredness=required) has materialized resource(s) source_evidence_set but no renderable producer.

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

### irs_66bff530dacd: `type_or_contract_ambiguity`
- Severity: `warning`
- Target: `worker:worker_main.step:st_3`
- Source spans: `s16`
- Message: REQUEST_INPUT step has no value target (outputs). [construct=worker:worker_main.step:st_3, slot=value_target]
- Blocks rendering: `false`
- Blocks completion: `true`
- Missing slot: `value_target`
- Missing reason: REQUEST_INPUT step has no value target (outputs).

### diag_prov_0000: `missing_provenance`
- Severity: `warning`
- Target: `variable:communication_request`
- Message: Variable 'communication_request' (text) is a contract input with no source-backed producer or adapter evidence.
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_prov_0001: `missing_provenance`
- Severity: `warning`
- Target: `variable:known_topics`
- Message: Variable 'known_topics' (List[text]) is a contract input with no source-backed producer or adapter evidence.
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_prov_0002: `missing_provenance`
- Severity: `warning`
- Target: `variable:timeframe`
- Message: Variable 'timeframe' (text) is a contract input with no source-backed producer or adapter evidence.
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_prov_0003: `missing_provenance`
- Severity: `warning`
- Target: `variable:background_information`
- Message: Variable 'background_information' (text) is a contract input with no source-backed producer or adapter evidence.
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_prov_0004: `missing_provenance`
- Severity: `warning`
- Target: `variable:target_audience`
- Message: Variable 'target_audience' (text) is a contract input with no source-backed producer or adapter evidence.
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_prov_0005: `missing_provenance`
- Severity: `warning`
- Target: `variable:available_information_sources`
- Message: Variable 'available_information_sources' (List[text]) is a contract input with no source-backed producer or adapter evidence.
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_prov_0006: `missing_provenance`
- Severity: `warning`
- Target: `variable:format_preferences`
- Message: Variable 'format_preferences' (text) is a contract input with no source-backed producer or adapter evidence.
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
- Target: `variable:record_of_unresolved_items`
- Message: Variable 'record_of_unresolved_items' (List[text]) is a contract output with no source-backed producer or adapter evidence.
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_prov_0009: `missing_provenance`
- Severity: `warning`
- Target: `variable:completion_status`
- Message: Variable 'completion_status' (text) is a contract output with no source-backed producer or adapter evidence.
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_prov_0010: `missing_provenance`
- Severity: `warning`
- Target: `profile:persona`
- Message: Rendered profile item 'profile:persona' has no source-backed provenance.
- Blocks rendering: `false`
- Blocks completion: `true`

### diag_prov_0011: `missing_provenance`
- Severity: `warning`
- Target: `profile:persona.aspect:0`
- Message: Unrendered profile item 'profile:persona.aspect:0' has no source-backed provenance.
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_prov_0012: `missing_provenance`
- Severity: `warning`
- Target: `profile:persona.aspect:2`
- Message: Unrendered profile item 'profile:persona.aspect:2' has no source-backed provenance.
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_prov_0013: `missing_provenance`
- Severity: `warning`
- Target: `profile:audience:0`
- Message: Unrendered profile item 'profile:audience:0' has no source-backed provenance.
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_prov_0014: `missing_provenance`
- Severity: `warning`
- Target: `profile:concept:5`
- Message: Unrendered profile item 'profile:concept:5' has no source-backed provenance.
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_prov_0015: `missing_provenance`
- Severity: `warning`
- Target: `profile:concept:6`
- Message: Unrendered profile item 'profile:concept:6' has no source-backed provenance.
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_prov_0016: `missing_provenance`
- Severity: `warning`
- Target: `profile:concept:7`
- Message: Unrendered profile item 'profile:concept:7' has no source-backed provenance.
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_prov_0017: `missing_provenance`
- Severity: `warning`
- Target: `profile:concept:8`
- Message: Unrendered profile item 'profile:concept:8' has no source-backed provenance.
- Blocks rendering: `false`
- Blocks completion: `false`

### stage2_route_refinement_conflict_: `route_refinement_conflict`
- Severity: `info`
- Message: LLM route diagnostic [override_prior] span='s30': No route prior was provided, but the text clearly describes the response to unresolved conflicts.
- Blocks rendering: `false`
- Blocks completion: `false`

### stage2_route_refinement_diagnostic_: `route_refinement_diagnostic`
- Severity: `info`
- Message: LLM route diagnostic [override_prior] span='s1': Overrode structural task_family prior with profile_domain because the text describes internal communication materials as the domain context.
- Blocks rendering: `false`
- Blocks completion: `false`

## 5. Deferred Validation

No downstream validation was deferred.

## 6. Assumptions / Suggestions

- `ASM_0000` for `worker:worker_main.output:source_evidence_set`: Required output has no source-backed producer. The compiler suggests adding a step that explicitly produces this output.
  - Reason: The source requires this output but does not describe how it should be produced.  The output is kept in the OUTPUTS contract, but no producer step was rendered.
  - Suggested resolution: Add a source-backed step that produces worker:worker_main.output:source_evidence_set. If the source does not specify how to produce it, mark it as optional or remove it from the required output contract.
  - Related diagnostic: `irs_ae87eac80c3d`
- `ASM_0001` for `worker:worker_main.output:record_of_unresolved_items`: Required output has no source-backed producer. The compiler suggests adding a step that explicitly produces this output.
  - Reason: The source requires this output but does not describe how it should be produced.  The output is kept in the OUTPUTS contract, but no producer step was rendered.
  - Suggested resolution: Add a source-backed step that produces worker:worker_main.output:record_of_unresolved_items. If the source does not specify how to produce it, mark it as optional or remove it from the required output contract.
  - Related diagnostic: `irs_7ef204235405`
- `ASM_0002` for `worker:worker_main.output:completion_status`: Required output has no source-backed producer. The compiler suggests adding a step that explicitly produces this output.
  - Reason: The source requires this output but does not describe how it should be produced.  The output is kept in the OUTPUTS contract, but no producer step was rendered.
  - Suggested resolution: Add a source-backed step that produces worker:worker_main.output:completion_status. If the source does not specify how to produce it, mark it as optional or remove it from the required output contract.
  - Related diagnostic: `irs_5143c9abd16e`
- `ASM_0003` for `resource_contract_demand:rcd_output_s11`: Required output has no source-backed producer. The compiler suggests adding a step that explicitly produces this output.
  - Reason: The source requires this output but does not describe how it should be produced.  The output is kept in the OUTPUTS contract, but no producer step was rendered.
  - Suggested resolution: Add a source-backed step that produces resource_contract_demand:rcd_output_s11. If the source does not specify how to produce it, mark it as optional or remove it from the required output contract.
  - Related diagnostic: `irs_b9b0a6118031`
- `ASM_0004` for `resource_contract_demand:rcd_output_s12`: Required output has no source-backed producer. The compiler suggests adding a step that explicitly produces this output.
  - Reason: The source requires this output but does not describe how it should be produced.  The output is kept in the OUTPUTS contract, but no producer step was rendered.
  - Suggested resolution: Add a source-backed step that produces resource_contract_demand:rcd_output_s12. If the source does not specify how to produce it, mark it as optional or remove it from the required output contract.
  - Related diagnostic: `irs_1af17bef9d62`
- `ASM_0005` for `resource_contract_demand:rcd_output_s13`: Required output has no source-backed producer. The compiler suggests adding a step that explicitly produces this output.
  - Reason: The source requires this output but does not describe how it should be produced.  The output is kept in the OUTPUTS contract, but no producer step was rendered.
  - Suggested resolution: Add a source-backed step that produces resource_contract_demand:rcd_output_s13. If the source does not specify how to produce it, mark it as optional or remove it from the required output contract.
  - Related diagnostic: `irs_b0d25f2c1af8`
- `ASM_0006` for `worker:worker_main.step:st_3`: Command has an ambiguous or incomplete contract. The compiler suggests providing the missing contract detail.
  - Reason: A command references an API, worker, or input source that is not fully specified.  The compiler cannot materialize the command without this information.
  - Suggested resolution: For worker:worker_main.step:st_3: provide the missing contract detail (API name, worker target, IO bindings, or source evidence).  See the related diagnostic for specifics.
  - Related diagnostic: `irs_66bff530dacd`
- `ASM_0007` for `variable:communication_request`: Variable has no discoverable source provenance.
  - Reason: The compiler could not trace this variable back to a source span, adapter hard fact, or producer step.  Its origin is assumed.
  - Suggested resolution: For variable:communication_request: add source evidence (a span, adapter hint, or producer step) that justifies this variable's existence.
  - Related diagnostic: `diag_prov_0000`
- `ASM_0008` for `variable:known_topics`: Variable has no discoverable source provenance.
  - Reason: The compiler could not trace this variable back to a source span, adapter hard fact, or producer step.  Its origin is assumed.
  - Suggested resolution: For variable:known_topics: add source evidence (a span, adapter hint, or producer step) that justifies this variable's existence.
  - Related diagnostic: `diag_prov_0001`
- `ASM_0009` for `variable:timeframe`: Variable has no discoverable source provenance.
  - Reason: The compiler could not trace this variable back to a source span, adapter hard fact, or producer step.  Its origin is assumed.
  - Suggested resolution: For variable:timeframe: add source evidence (a span, adapter hint, or producer step) that justifies this variable's existence.
  - Related diagnostic: `diag_prov_0002`
- `ASM_0010` for `variable:background_information`: Variable has no discoverable source provenance.
  - Reason: The compiler could not trace this variable back to a source span, adapter hard fact, or producer step.  Its origin is assumed.
  - Suggested resolution: For variable:background_information: add source evidence (a span, adapter hint, or producer step) that justifies this variable's existence.
  - Related diagnostic: `diag_prov_0003`
- `ASM_0011` for `variable:target_audience`: Variable has no discoverable source provenance.
  - Reason: The compiler could not trace this variable back to a source span, adapter hard fact, or producer step.  Its origin is assumed.
  - Suggested resolution: For variable:target_audience: add source evidence (a span, adapter hint, or producer step) that justifies this variable's existence.
  - Related diagnostic: `diag_prov_0004`
- `ASM_0012` for `variable:available_information_sources`: Variable has no discoverable source provenance.
  - Reason: The compiler could not trace this variable back to a source span, adapter hard fact, or producer step.  Its origin is assumed.
  - Suggested resolution: For variable:available_information_sources: add source evidence (a span, adapter hint, or producer step) that justifies this variable's existence.
  - Related diagnostic: `diag_prov_0005`
- `ASM_0013` for `variable:format_preferences`: Variable has no discoverable source provenance.
  - Reason: The compiler could not trace this variable back to a source span, adapter hard fact, or producer step.  Its origin is assumed.
  - Suggested resolution: For variable:format_preferences: add source evidence (a span, adapter hint, or producer step) that justifies this variable's existence.
  - Related diagnostic: `diag_prov_0006`
- `ASM_0014` for `variable:source_evidence_set`: Variable has no discoverable source provenance.
  - Reason: The compiler could not trace this variable back to a source span, adapter hard fact, or producer step.  Its origin is assumed.
  - Suggested resolution: For variable:source_evidence_set: add source evidence (a span, adapter hint, or producer step) that justifies this variable's existence.
  - Related diagnostic: `diag_prov_0007`
- `ASM_0015` for `variable:record_of_unresolved_items`: Variable has no discoverable source provenance.
  - Reason: The compiler could not trace this variable back to a source span, adapter hard fact, or producer step.  Its origin is assumed.
  - Suggested resolution: For variable:record_of_unresolved_items: add source evidence (a span, adapter hint, or producer step) that justifies this variable's existence.
  - Related diagnostic: `diag_prov_0008`
- `ASM_0016` for `variable:completion_status`: Variable has no discoverable source provenance.
  - Reason: The compiler could not trace this variable back to a source span, adapter hard fact, or producer step.  Its origin is assumed.
  - Suggested resolution: For variable:completion_status: add source evidence (a span, adapter hint, or producer step) that justifies this variable's existence.
  - Related diagnostic: `diag_prov_0009`
- `ASM_0017` for `profile:persona`: Rendered profile item has no source-backed provenance.
  - Reason: The compiler rendered this required profile item, but could not trace it to a source span.
  - Suggested resolution: For profile:persona: add source evidence that justifies this profile item, or confirm the assumption-bearing draft.
  - Related diagnostic: `diag_prov_0010`
- `ASM_0018` for `profile:persona.aspect:0`: Unrendered profile item has no source-backed provenance.
  - Reason: The compiler did not render this optional profile item because it could not trace it to a source span.
  - Suggested resolution: For profile:persona.aspect:0: add source evidence that justifies this profile item, or confirm the assumption-bearing draft.
  - Related diagnostic: `diag_prov_0011`
- `ASM_0019` for `profile:persona.aspect:2`: Unrendered profile item has no source-backed provenance.
  - Reason: The compiler did not render this optional profile item because it could not trace it to a source span.
  - Suggested resolution: For profile:persona.aspect:2: add source evidence that justifies this profile item, or confirm the assumption-bearing draft.
  - Related diagnostic: `diag_prov_0012`
- `ASM_0020` for `profile:audience:0`: Unrendered profile item has no source-backed provenance.
  - Reason: The compiler did not render this optional profile item because it could not trace it to a source span.
  - Suggested resolution: For profile:audience:0: add source evidence that justifies this profile item, or confirm the assumption-bearing draft.
  - Related diagnostic: `diag_prov_0013`
- `ASM_0021` for `profile:concept:5`: Unrendered profile item has no source-backed provenance.
  - Reason: The compiler did not render this optional profile item because it could not trace it to a source span.
  - Suggested resolution: For profile:concept:5: add source evidence that justifies this profile item, or confirm the assumption-bearing draft.
  - Related diagnostic: `diag_prov_0014`
- `ASM_0022` for `profile:concept:6`: Unrendered profile item has no source-backed provenance.
  - Reason: The compiler did not render this optional profile item because it could not trace it to a source span.
  - Suggested resolution: For profile:concept:6: add source evidence that justifies this profile item, or confirm the assumption-bearing draft.
  - Related diagnostic: `diag_prov_0015`
- `ASM_0023` for `profile:concept:7`: Unrendered profile item has no source-backed provenance.
  - Reason: The compiler did not render this optional profile item because it could not trace it to a source span.
  - Suggested resolution: For profile:concept:7: add source evidence that justifies this profile item, or confirm the assumption-bearing draft.
  - Related diagnostic: `diag_prov_0016`
- `ASM_0024` for `profile:concept:8`: Unrendered profile item has no source-backed provenance.
  - Reason: The compiler did not render this optional profile item because it could not trace it to a source span.
  - Suggested resolution: For profile:concept:8: add source evidence that justifies this profile item, or confirm the assumption-bearing draft.
  - Related diagnostic: `diag_prov_0017`
- `ASM_0025, ASM_0026, ASM_0027, ASM_0028` for `worker_promotion:del_s31`: Worker promotion has an incomplete contract.
  - Reason: The candidate is blocked by multiple missing promotion slots.
  - Suggested resolution: Provide the missing input/output contracts, invocation point, and result handoff details listed in the related diagnostics.
  - Related diagnostics: `irs_16c0d5b20df4, irs_6b43a592b006, irs_6c2ebb9b34e6, irs_d422db06a1ca`

## 7. Provenance / TraceRecords

- `constraint:c_1` -> `direct`
  - Source: spans=`s22`, section=`sec_policies`, packet=`p_sentence_do_not_fabricate_facts_data_events_or_sources_that_are_not_provided_by_the_user_or_obtained_from_available_information_sources`
  - Explanation: Constraint 'c_1' (prohibition): Do not fabricate facts, data, events, or sources that are not provided by the us
- `constraint:c_2` -> `direct`
  - Source: spans=`s23`, section=`sec_policies`, packet=`p_sentence_external_facts_must_have_traceable_sources_facts_directly_provided_by_the_user_shall_be_marked_as_user_provided_information`
  - Explanation: Constraint 'c_2' (evidence): External facts must have traceable sources; facts directly provided by the user
- `constraint:c_3` -> `direct`
  - Source: spans=`s24`, section=`sec_policies`, packet=`p_sentence_prioritize_information_already_provided_by_the_user_to_avoid_unnecessary_information_retrieval_and_clarifying_questions`
  - Explanation: Constraint 'c_3' (requirement): Prioritize information already provided by the user to avoid unnecessary informa
- `constraint:c_4` -> `direct`
  - Source: spans=`s25`, section=`sec_policies`, packet=`p_sentence_do_not_alter_the_meaning_of_the_user_s_original_request_for_the_sake_of_completeness_fluency_or_professionalism_of_expression`
  - Explanation: Constraint 'c_4' (prohibition): Do not alter the meaning of the user’s original request for the sake of complete
- `constraint:c_5` -> `direct`
  - Source: spans=`s26`, section=`sec_policies`, packet=`p_sentence_do_not_mark_the_task_as_complete_if_critical_information_is_missing_or_conflicting_instructions_remain_unresolved`
  - Explanation: Constraint 'c_5' (gate): Do not mark the task as complete if critical information is missing or conflicti
- `constraint:c_6` -> `direct`
  - Source: spans=`s32`, section=`sec_delegation_policy`, packet=`p_sentence_delegated_tasks_shall_not_expand_the_scope_of_the_original_task_nor_alter_the_user_s_original_requirements`
  - Explanation: Constraint 'c_6' (delegation_boundary): Delegated tasks shall not expand the scope of the original task nor alter the us
- `constraint:c_7` -> `direct`
  - Source: spans=`s33`, section=`sec_delegation_policy`, packet=`p_sentence_main_process_shall_verify_that_delegated_results_comply_with_the_task_scope_and_user_requirements_before_adopting_them`
  - Explanation: Constraint 'c_7' (requirement): The main process shall verify that delegated results comply with the task scope
- `constraint:c_8` -> `direct`
  - Source: spans=`s34`, section=`sec_delegation_policy`, packet=`p_sentence_if_delegation_fails_or_returns_results_beyond_the_authorized_scope_such_results_shall_not_be_adopted_if_the_results_are_essential_to_task_completion_record_unresolved_items_and_mark_the_task_as_incomplete`
  - Explanation: Constraint 'c_8' (gate): If delegation fails or returns results beyond the authorized scope, such results
- `flow:alt_1` -> `direct`
  - Source: spans=`s16, s16`, section=`sec_reusable_process`, packet=`p_sentence_if_critical_information_that_affects_content_accuracy_is_missing_ask_the_user_necessary_clarifying_questions_if_the_information_is_available_proceed`
  - Explanation: Alternative flow 'alt_1': Critical information affecting content accuracy is missing
- `flow:exc_adapter_00` -> `direct`
  - Source: spans=`s28, s28`, section=`sec_failure_handling`, packet=`p_sentence_if_such_information_cannot_be_obtained_record_the_missing_items_do_not_generate_a_full_draft_and_mark_the_task_as_incomplete`
  - Explanation: Exception flow 'exc_adapter_00': such information cannot be obtained
- `flow:exc_adapter_01` -> `direct`
  - Source: spans=`s29, s29, s30`, section=`sec_conflicting_instructions`, packet=`p_sentence_if_the_user_s_requirements_conflict_and_impede_task_execution_document_the_specific_conflicts`
  - Explanation: Exception flow 'exc_adapter_01': the user’s requirements conflict and impede task execution
- `flow:exc_adapter_02` -> `direct`
  - Source: spans=`s27, s27`, section=`sec_failure_handling`, packet=`p_sentence_missing_critical_information_if_information_essential_to_task_completion_is_lacking_inquire_with_the_user`
  - Explanation: Exception flow 'exc_adapter_02': information essential to task completion is lacking
- `flow:main` -> `direct`
  - Source: spans=`s14, s15, s17, s18, s19, s20, s21`, section=`sec_reusable_process`, packet=`p_sentence_analyze_the_user_s_request_to_clarify_the_type_of_communication_material_communication_purpose_target_audience_and_expression_requirements`
  - Explanation: Main flow with 4 block(s).
- `profile:audience:0` -> `assumed` [needs confirmation]
  - Explanation: Audience: InternalAudience
- `profile:concept:0` -> `normalized`
  - Source: spans=`s1`, section=`sec_task_family`, packet=`p_sentence_internal_newsletters_internal_announcements_periodic_update_digests_executive_briefs_and_other_internal_facing_communication_materials`
  - Explanation: Concept: Internal-facing communication materials -- Communication content intended for use within an organization rather than for external audiences.
- `profile:concept:1` -> `normalized`
  - Source: spans=`s1`, section=`sec_task_family`, packet=`p_sentence_internal_newsletters_internal_announcements_periodic_update_digests_executive_briefs_and_other_internal_facing_communication_materials`
  - Explanation: Concept: Internal newsletters -- Newsletter-style communications distributed to people inside the company.
- `profile:concept:2` -> `normalized`
  - Source: spans=`s1`, section=`sec_task_family`, packet=`p_sentence_internal_newsletters_internal_announcements_periodic_update_digests_executive_briefs_and_other_internal_facing_communication_materials`
  - Explanation: Concept: Internal announcements -- Announcements meant for an internal company audience.
- `profile:concept:3` -> `normalized`
  - Source: spans=`s1`, section=`sec_task_family`, packet=`p_sentence_internal_newsletters_internal_announcements_periodic_update_digests_executive_briefs_and_other_internal_facing_communication_materials`
  - Explanation: Concept: Periodic update digests -- Regularly issued summaries that compile recent updates for internal readers.
- `profile:concept:4` -> `normalized`
  - Source: spans=`s1`, section=`sec_task_family`, packet=`p_sentence_internal_newsletters_internal_announcements_periodic_update_digests_executive_briefs_and_other_internal_facing_communication_materials`
  - Explanation: Concept: Executive briefs -- Concise internal summaries prepared for executives or senior leadership.
- `profile:concept:5` -> `assumed` [needs confirmation]
  - Explanation: Concept: Traceable sources -- Sources that can be identified and verified for any external facts used in the output.
- `profile:concept:6` -> `assumed` [needs confirmation]
  - Explanation: Concept: Critical information -- Information essential to producing an accurate and complete communication artifact.
- `profile:concept:7` -> `assumed` [needs confirmation]
  - Explanation: Concept: Controlled components -- System-configured components that may be delegated well-defined subtasks for processing.
- `profile:concept:8` -> `assumed` [needs confirmation]
  - Explanation: Concept: Template matching -- A well-defined subtask that can be delegated to controlled components when available.
- `profile:persona` -> `assumed` [needs confirmation]
  - Explanation: Persona: Internal communications specialist
- `profile:persona.aspect:0` -> `assumed` [needs confirmation]
  - Explanation: Persona aspect: InformationDisciplined
- `profile:persona.aspect:1` -> `normalized`
  - Source: spans=`s7`, section=`sec_inputs_for_each_run`, packet=`p_list_item_target_audience`
  - Explanation: Persona aspect: RequirementsFocused
- `profile:persona.aspect:2` -> `assumed` [needs confirmation]
  - Explanation: Persona aspect: CarefulFailureHandling
- `step:st_1` -> `direct`
  - Source: spans=`s14`, section=`sec_reusable_process`, packet=`p_sentence_analyze_the_user_s_request_to_clarify_the_type_of_communication_material_communication_purpose_target_audience_and_expression_requirements`
  - Explanation: Step 'st_1' maps to source span(s).
- `step:st_2` -> `direct`
  - Source: spans=`s15`, section=`sec_reusable_process`, packet=`p_sentence_check_if_the_facts_and_background_information_needed_to_generate_the_material_are_available`
  - Explanation: Step 'st_2' maps to source span(s).
- `step:st_3` -> `direct`
  - Source: spans=`s16`, section=`sec_reusable_process`, packet=`p_sentence_if_critical_information_that_affects_content_accuracy_is_missing_ask_the_user_necessary_clarifying_questions_if_the_information_is_available_proceed`
  - Explanation: Step 'st_3' maps to source span(s).
- `step:st_4` -> `direct`
  - Source: spans=`s17`, section=`sec_reusable_process`, packet=`p_sentence_organize_the_obtained_facts_and_background_information_extract_core_messages_to_be_conveyed_and_structure_the_content_based_on_the_material_type`
  - Explanation: Step 'st_4' maps to source span(s).
- `step:st_5` -> `direct`
  - Source: spans=`s18`, section=`sec_reusable_process`, packet=`p_sentence_generate_a_draft_communication_artifact_and_verify_if_it_meets_the_user_s_specified_requirements_for_target_audience_tone_language_length_structure_and_format`
  - Explanation: Step 'st_5' maps to source span(s).
- `step:st_6` -> `direct`
  - Source: spans=`s19, s21`, section=`sec_reusable_process`, packet=`p_sentence_if_not_revise_it_based_on_the_verification_results`
  - Explanation: Step 'st_6' maps to source span(s).
- `step:st_7` -> `direct`
  - Source: spans=`s20`, section=`sec_reusable_process`, packet=`p_sentence_output_the_draft_communication_artifact_record_of_unresolved_items_and_completion_status`
  - Explanation: Step 'st_7' maps to source span(s).
- `step:st_exception_exc_adapter_00_s28` -> `direct`
  - Source: spans=`s28`, section=`sec_failure_handling`, packet=`p_sentence_if_such_information_cannot_be_obtained_record_the_missing_items_do_not_generate_a_full_draft_and_mark_the_task_as_incomplete`
  - Explanation: Step 'st_exception_exc_adapter_00_s28' maps to source span(s).
- `step:st_exception_exc_adapter_01_s29` -> `direct`
  - Source: spans=`s29`, section=`sec_conflicting_instructions`, packet=`p_sentence_if_the_user_s_requirements_conflict_and_impede_task_execution_document_the_specific_conflicts`
  - Explanation: Step 'st_exception_exc_adapter_01_s29' maps to source span(s).
- `step:st_exception_exc_adapter_01_s30` -> `direct`
  - Source: spans=`s30`, section=`sec_conflicting_instructions`, packet=`p_sentence_do_not_generate_a_full_draft_and_mark_the_task_as_incomplete_until_the_conflicts_are_resolved`
  - Explanation: Step 'st_exception_exc_adapter_01_s30' maps to source span(s).
- `step:st_exception_exc_adapter_02_s27` -> `direct`
  - Source: spans=`s27`, section=`sec_failure_handling`, packet=`p_sentence_missing_critical_information_if_information_essential_to_task_completion_is_lacking_inquire_with_the_user`
  - Explanation: Step 'st_exception_exc_adapter_02_s27' maps to source span(s).
- `variable:available_information_sources` -> `assumed` [needs confirmation]
  - Explanation: Variable 'available_information_sources' is declared as worker input contract with no source evidence.
- `variable:background_information` -> `assumed` [needs confirmation]
  - Explanation: Variable 'background_information' is declared as worker input contract with no source evidence.
- `variable:communication_request` -> `assumed` [needs confirmation]
  - Explanation: Variable 'communication_request' is declared as worker input contract with no source evidence.
- `variable:completion_status` -> `assumed` [needs confirmation]
  - Explanation: Variable 'completion_status' is declared as worker output contract with no source evidence.
- `variable:draft_communication_artifact` -> `direct`
  - Source: spans=`s18`, section=`sec_reusable_process`, packet=`p_sentence_generate_a_draft_communication_artifact_and_verify_if_it_meets_the_user_s_specified_requirements_for_target_audience_tone_language_length_structure_and_format`
  - Explanation: Variable 'draft_communication_artifact' is produced by source-backed step 'st_5'.
- `variable:format_preferences` -> `assumed` [needs confirmation]
  - Explanation: Variable 'format_preferences' is declared as worker input contract with no source evidence.
- `variable:known_topics` -> `assumed` [needs confirmation]
  - Explanation: Variable 'known_topics' is declared as worker input contract with no source evidence.
- `variable:record_of_unresolved_items` -> `assumed` [needs confirmation]
  - Explanation: Variable 'record_of_unresolved_items' is declared as worker output contract with no source evidence.
- `variable:source_evidence_set` -> `assumed` [needs confirmation]
  - Explanation: Variable 'source_evidence_set' is declared as worker output contract with no source evidence.
- `variable:target_audience` -> `assumed` [needs confirmation]
  - Explanation: Variable 'target_audience' is declared as worker input contract with no source evidence.
- `variable:timeframe` -> `assumed` [needs confirmation]
  - Explanation: Variable 'timeframe' is declared as worker input contract with no source evidence.
- `worker:MainWorker` -> `direct`
  - Source: spans=`s14, s15, s16, s17, s18, s19, s20, s21, s27, s28, s29, s30`, section=`sec_reusable_process`, packet=`p_sentence_analyze_the_user_s_request_to_clarify_the_type_of_communication_material_communication_purpose_target_audience_and_expression_requirements`
  - Explanation: Main worker 'MainWorker' assembled from flow and step IRs.

## 8. Anti-Fabrication Checks

- `missing_output_producer`: Required outputs without a source-backed producer stay in the contract; no synthetic producer command is invented.
- `type_or_contract_ambiguity`: Unresolved worker/API contracts are reported as ambiguity; they are not downgraded to generic commands.
- Rendered SPL contains no executable `[INVOKE ...]` command.

## 9. Adapter / Validation Notes

No adapter or validation notes.

## 10. SPL Draft

```spl
[DEFINE_AGENT: MainWorker "Orchestrate the end-to-end process and delegate to sub-tasks."]
    [DEFINE_PERSONA:]
        ROLE: Internal communications specialist
        RequirementsFocused: Clarifies communication type, purpose, target audience, and expression requirements before drafting, then verifies the draft against audience, tone, language, length, structure, and format.
    [END_PERSONA]
    [DEFINE_CONCEPTS:]
        Internalfacingcommunicationmaterials: Communication content intended for use within an organization rather than for external audiences.
        Internalnewsletters: Newsletter-style communications distributed to people inside the company.
        Internalannouncements: Announcements meant for an internal company audience.
        Periodicupdatedigests: Regularly issued summaries that compile recent updates for internal readers.
        Executivebriefs: Concise internal summaries prepared for executives or senior leadership.
    [END_CONCEPTS]
    [DEFINE_CONSTRAINTS:]
        Prohibition: Do not fabricate facts, data, events, or sources that are not provided by the user or obtained from available information sources.
        Evidence: External facts must have traceable sources; facts directly provided by the user shall be marked as user-provided information.
        Requirement: Prioritize information already provided by the user to avoid unnecessary information retrieval and clarifying questions.
        Prohibition: Do not alter the meaning of the user’s original request for the sake of completeness, fluency, or professionalism of expression.
        Gate: Do not mark the task as complete if critical information is missing or conflicting instructions remain unresolved.
        DelegationBoundary: Delegated tasks shall not expand the scope of the original task nor alter the user’s original requirements.
        Requirement: The main process shall verify that delegated results comply with the task scope and user requirements before adopting them.
        Gate: If delegation fails or returns results beyond the authorized scope, such results shall not be adopted; if the results are essential to task completion, record unresolved items and mark the task as incomplete.
    [END_CONSTRAINTS]
    [DEFINE_VARIABLES:]
        "User's communication request" communication_request: text
        "Known topics provided by the user" known_topics: List [text]
        "Requested time range or deadline" timeframe: text
        "Background information relevant to the request" background_information: text
        "Intended audience for the communication" target_audience: text
        "Information sources available for use" available_information_sources: List [text]
        "Preferred format requirements" format_preferences: text
        "Draft communication artifact to produce" draft_communication_artifact: text
        "Collected source and evidence items" source_evidence_set: List [text]
        "List of unresolved items" record_of_unresolved_items: List [text]
        "Task completion status" completion_status: text
    [END_VARIABLES]
    [DEFINE_WORKER: "Orchestrate the end-to-end process and delegate to sub-tasks." MainWorker]
        [INPUTS]
            REQUIRED <REF>communication_request</REF>
            OPTIONAL <REF>known_topics</REF>
            OPTIONAL <REF>timeframe</REF>
            OPTIONAL <REF>background_information</REF>
            OPTIONAL <REF>target_audience</REF>
            OPTIONAL <REF>available_information_sources</REF>
            OPTIONAL <REF>format_preferences</REF>
        [END_INPUTS]
        [OUTPUTS]
            REQUIRED <REF>draft_communication_artifact</REF>
            REQUIRED <REF>source_evidence_set</REF>
            REQUIRED <REF>record_of_unresolved_items</REF>
            REQUIRED <REF>completion_status</REF>
        [END_OUTPUTS]
        [MAIN_FLOW]
            [SEQUENTIAL_BLOCK]
                COMMAND-1 [COMMAND Analyze the communication request based on <REF>communication_request</REF>]
                COMMAND-2 [COMMAND Check availability of required facts and background information based on <REF>background_information</REF> and <REF>available_information_sources</REF>]
                COMMAND-3 [COMMAND Organize the facts and extract core messages based on <REF>background_information</REF> and <REF>known_topics</REF>]
                COMMAND-4 [COMMAND Generate the draft communication artifact based on <REF>communication_request</REF>, <REF>background_information</REF>, <REF>known_topics</REF>, <REF>target_audience</REF>, <REF>format_preferences</REF>, and <REF>timeframe</REF> RESULT draft_communication_artifact: text SET]
            [END_SEQUENTIAL_BLOCK]
            DECISION-1 [IF <REF>draft_communication_artifact</REF> does not meet the user’s specified requirements for <REF>target_audience</REF>, tone, language, length, structure, and format]
                COMMAND-5 [COMMAND Revise the draft communication artifact based on <REF>target_audience</REF> and <REF>format_preferences</REF>]
            [END_IF]
            [SEQUENTIAL_BLOCK]
                COMMAND-6 [DISPLAY Output the draft communication artifact, record of unresolved items, and completion status based on <REF>draft_communication_artifact</REF>]
            [END_SEQUENTIAL_BLOCK]
        [END_MAIN_FLOW]
        [ALTERNATIVE_FLOW: Critical information affecting content accuracy is missing]
            [SEQUENTIAL_BLOCK]
                COMMAND-7 [INPUT Request missing clarifying information from the user based on <REF>communication_request</REF> VALUE user_input:text SET]
            [END_SEQUENTIAL_BLOCK]
        [END_ALTERNATIVE_FLOW]
        [EXCEPTION_FLOW: such information cannot be obtained]
            [SEQUENTIAL_BLOCK]
                COMMAND-8 [COMMAND Record the missing items, do not generate a full draft, and mark the task as incomplete]
            [END_SEQUENTIAL_BLOCK]
        [END_EXCEPTION_FLOW]
        [EXCEPTION_FLOW: the user’s requirements conflict and impede task execution]
            [SEQUENTIAL_BLOCK]
                COMMAND-9 [COMMAND Document the specific conflicts]
                COMMAND-10 [COMMAND Do not generate a full draft and mark the task as incomplete until the conflicts are resolved]
            [END_SEQUENTIAL_BLOCK]
        [END_EXCEPTION_FLOW]
        [EXCEPTION_FLOW: information essential to task completion is lacking]
            [SEQUENTIAL_BLOCK]
                COMMAND-11 [COMMAND Inquire with the user]
            [END_SEQUENTIAL_BLOCK]
        [END_EXCEPTION_FLOW]
    [END_WORKER]
[END_AGENT]
```
