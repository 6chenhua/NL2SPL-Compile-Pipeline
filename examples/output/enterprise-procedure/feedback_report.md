# NL2SPL Feedback Report

## 1. Overall Compile State

- Completeness: `partial`
- SPL draft generated: `yes`
- Compile diagnostics: `8`
- Assumptions / suggestions: `8`
- Trace records: `43`
- Adapter warnings: `21`
- Validation errors: `0`
- Validation warnings: `17`

Result is partial because the following requirement gaps remain:
- `missing_handler` on `worker:worker_main.exception_flow:exc_adapter_00`: Exception flow 'exc_adapter_00' ('Insufficient quotes') has no handler step in worker 'worker_main'.
- `missing_handler` on `worker:worker_main.exception_flow:exc_adapter_01`: Exception flow 'exc_adapter_01' ('Over-budget proposals') has no handler step in worker 'worker_main'.
- `missing_handler` on `worker:worker_main.exception_flow:exc_adapter_02`: Exception flow 'exc_adapter_02' ('Vendor ineligibility') has no handler step in worker 'worker_main'.
- `missing_handler` on `worker:worker_main.exception_flow:exc_adapter_03`: Exception flow 'exc_adapter_03' ('Approval denial') has no handler step in worker 'worker_main'.
- `missing_handler` on `worker:worker_main.exception_flow:exc_adapter_04`: Exception flow 'exc_adapter_04' ('Missing
documents') has no handler step in worker 'worker_main'.
- `missing_handler` on `worker:worker_main.exception_flow:exc_adapter_05`: Exception flow 'exc_adapter_05' ('Compliance failure') has no handler step in worker 'worker_main'.
- `missing_handler` on `worker:worker_main.exception_flow:exc_adapter_06`: Exception flow 'exc_adapter_06' ('Waiver rejection') has no handler step in worker 'worker_main'.
- `type_or_contract_ambiguity` on `delegation_intent:s37`: Delegation intent 'Bounded sourcing or quote-comparison subtasks may be delegated, but vendor
decis' lacks a valid worker/API handoff contract.  No INVOKE_WORKER or CALL_API will be generated from this span.  [sec_delegation_policy/p_delegation_rule_bounded_sourcing_or_quote_comparison_subtasks_may_be_delegated_but_vendor_decision_promotion_requires_normalized_quote_and_compliance_artifacts]

## 2. Materialized Source-Backed Structure

### Workers
- `worker:MainWorker` (direct) -- spans=s16, s17, s18, s19, s20, s21, s22, s23, s24, s37; section=sec_reusable_process; packet=p_process_step_normalize_the_request_and_determine_procurement_category

### Flows
- `flow:exc_adapter_00` (direct) -- spans=s30; section=sec_failure_handling; packet=p_failure_mode_insufficient_quotes
- `flow:exc_adapter_01` (direct) -- spans=s31; section=sec_failure_handling; packet=p_failure_mode_over_budget_proposals
- `flow:exc_adapter_02` (direct) -- spans=s32; section=sec_failure_handling; packet=p_failure_mode_vendor_ineligibility
- `flow:exc_adapter_03` (direct) -- spans=s33; section=sec_failure_handling; packet=p_failure_mode_approval_denial
- `flow:exc_adapter_04` (direct) -- spans=s34; section=sec_failure_handling; packet=p_failure_mode_missing_documents
- `flow:exc_adapter_05` (direct) -- spans=s35; section=sec_failure_handling; packet=p_failure_mode_compliance_failure
- `flow:exc_adapter_06` (direct) -- spans=s36; section=sec_failure_handling; packet=p_failure_mode_waiver_rejection
- `flow:main` (direct) -- spans=s16, s17, s18, s19, s22, s23, s24; section=sec_reusable_process; packet=p_process_step_normalize_the_request_and_determine_procurement_category

### Steps
- `step:st_1` (direct) -- spans=s16; section=sec_reusable_process; packet=p_process_step_normalize_the_request_and_determine_procurement_category
- `step:st_2` (direct) -- spans=s17; section=sec_reusable_process; packet=p_process_step_identify_eligible_vendor_pool
- `step:st_3` (direct) -- spans=s18; section=sec_reusable_process; packet=p_process_step_solicit_quotes_or_equivalent_offers_according_to_policy
- `step:st_4` (direct) -- spans=s19; section=sec_reusable_process; packet=p_process_step_evaluate_budget_compliance_and_vendor_eligibility
- `step:st_5` (direct) -- spans=s22; section=sec_reusable_process; packet=p_process_step_route_approval_based_on_thresholds_and_category
- `step:st_6` (direct) -- spans=s23; section=sec_reusable_process; packet=p_process_step_issue_po_only_after_all_gates_pass
- `step:st_7` (direct) -- spans=s24; section=sec_reusable_process; packet=p_process_step_archive_evidence_for_audit

### Variables
- `variable:any_initial_vendor_suggestions` (normalized) -- section=sec_inputs_for_each_run
- `variable:approval_record` (direct) -- spans=s22; section=sec_reusable_process; packet=p_process_step_route_approval_based_on_thresholds_and_category
- `variable:audit_evidence_bundle` (direct) -- spans=s24; section=sec_reusable_process; packet=p_process_step_archive_evidence_for_audit
- `variable:budget_owner` (normalized) -- section=sec_inputs_for_each_run
- `variable:cost_center` (normalized) -- section=sec_inputs_for_each_run
- `variable:po_or_equivalent_issuance_artifact` (direct) -- spans=s23; section=sec_reusable_process; packet=p_process_step_issue_po_only_after_all_gates_pass
- `variable:policy_profile` (normalized) -- section=sec_inputs_for_each_run
- `variable:procurement_category` (direct) -- spans=s16; section=sec_reusable_process; packet=p_process_step_normalize_the_request_and_determine_procurement_category
- `variable:purchase_request` (normalized) -- section=sec_inputs_for_each_run
- `variable:requested_item_or_service` (normalized) -- section=sec_inputs_for_each_run
- `variable:selected_vendor_decision_or_rejection_outcome` (direct) -- spans=s19; section=sec_reusable_process; packet=p_process_step_evaluate_budget_compliance_and_vendor_eligibility
- `variable:sourcing_evaluation_record` (direct) -- spans=s17; section=sec_reusable_process; packet=p_process_step_identify_eligible_vendor_pool
- `variable:urgency` (normalized) -- section=sec_inputs_for_each_run
- `variable:vendor_eligibility_context` (normalized) -- section=sec_inputs_for_each_run

### Constraints
- `constraint:c_1` (direct) -- spans=s25; section=sec_policies; packet=p_policy_require_minimum_quote_count_unless_exception_approved
- `constraint:c_2` (direct) -- spans=s26; section=sec_policies; packet=p_policy_do_not_proceed_with_ineligible_vendors
- `constraint:c_3` (direct) -- spans=s27; section=sec_policies; packet=p_policy_require_category_specific_approval_thresholds
- `constraint:c_4` (direct) -- spans=s28; section=sec_policies; packet=p_policy_record_justification_for_sole_source_or_waiver_cases
- `constraint:c_5` (direct) -- spans=s29; section=sec_policies; packet=p_policy_deny_issuance_without_audit_complete_evidence

### Delegation Intents
- `delegation_intent:bounded_sourcing_or_quote_comparison_delegation` (inferred) -- spans=s37; section=sec_delegation_policy; packet=p_delegation_rule_bounded_sourcing_or_quote_comparison_subtasks_may_be_delegated_but_vendor_decision_promotion_requires_normalized_quote_and_compliance_artifacts
- `delegation_intent:bounded_sourcing_or_quote_comparison_subtasks_may_be_delegated_but_vendor_decision_promotion_requires_normalized_quote_and_compliance_artifacts` (inferred) -- spans=s37; section=sec_delegation_policy; packet=p_delegation_rule_bounded_sourcing_or_quote_comparison_subtasks_may_be_delegated_but_vendor_decision_promotion_requires_normalized_quote_and_compliance_artifacts

### Other
- `profile:concept_0` (normalized)
- `profile:concept_1` (normalized)
- `profile:concept_2` (normalized)
- `profile:concept_3` (normalized)
- `profile:concept_4` (normalized)
- `profile:persona` (inferred)

## 3. Not Materialized / Kept Partial

- `worker:worker_main.exception_flow:exc_adapter_00`: `missing_handler` -- Exception flow 'exc_adapter_00' ('Insufficient quotes') has no handler step in worker 'worker_main'.
  - Suggested resolution: Add a handler step for 'Insufficient quotes', or mark this exception as acknowledged without handling.
- `worker:worker_main.exception_flow:exc_adapter_01`: `missing_handler` -- Exception flow 'exc_adapter_01' ('Over-budget proposals') has no handler step in worker 'worker_main'.
  - Suggested resolution: Add a handler step for 'Over-budget proposals', or mark this exception as acknowledged without handling.
- `worker:worker_main.exception_flow:exc_adapter_02`: `missing_handler` -- Exception flow 'exc_adapter_02' ('Vendor ineligibility') has no handler step in worker 'worker_main'.
  - Suggested resolution: Add a handler step for 'Vendor ineligibility', or mark this exception as acknowledged without handling.
- `worker:worker_main.exception_flow:exc_adapter_03`: `missing_handler` -- Exception flow 'exc_adapter_03' ('Approval denial') has no handler step in worker 'worker_main'.
  - Suggested resolution: Add a handler step for 'Approval denial', or mark this exception as acknowledged without handling.
- `worker:worker_main.exception_flow:exc_adapter_04`: `missing_handler` -- Exception flow 'exc_adapter_04' ('Missing
documents') has no handler step in worker 'worker_main'.
  - Suggested resolution: Add a handler step for 'Missing
documents', or mark this exception as acknowledged without handling.
- `worker:worker_main.exception_flow:exc_adapter_05`: `missing_handler` -- Exception flow 'exc_adapter_05' ('Compliance failure') has no handler step in worker 'worker_main'.
  - Suggested resolution: Add a handler step for 'Compliance failure', or mark this exception as acknowledged without handling.
- `worker:worker_main.exception_flow:exc_adapter_06`: `missing_handler` -- Exception flow 'exc_adapter_06' ('Waiver rejection') has no handler step in worker 'worker_main'.
  - Suggested resolution: Add a handler step for 'Waiver rejection', or mark this exception as acknowledged without handling.
- `delegation_intent:s37`: `type_or_contract_ambiguity` -- Delegation intent 'Bounded sourcing or quote-comparison subtasks may be delegated, but vendor
decis' lacks a valid worker/API handoff contract.  No INVOKE_WORKER or CALL_API will be generated from this span.  [sec_delegation_policy/p_delegation_rule_bounded_sourcing_or_quote_comparison_subtasks_may_be_delegated_but_vendor_decision_promotion_requires_normalized_quote_and_compliance_artifacts]
  - Suggested resolution: Provide a valid worker/API handoff contract with input/output/API bindings covering span 's37'. hints=hint_delegation_0_sec_delegation_policy

## 4. Diagnostics

### diag_post_norm_0000: `missing_handler`
- Severity: `warning`
- Target: `worker:worker_main.exception_flow:exc_adapter_00`
- Source spans: `s30`
- Message: Exception flow 'exc_adapter_00' ('Insufficient quotes') has no handler step in worker 'worker_main'.
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Add a handler step for 'Insufficient quotes', or mark this exception as acknowledged without handling.

### diag_post_norm_0001: `missing_handler`
- Severity: `warning`
- Target: `worker:worker_main.exception_flow:exc_adapter_01`
- Source spans: `s31`
- Message: Exception flow 'exc_adapter_01' ('Over-budget proposals') has no handler step in worker 'worker_main'.
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Add a handler step for 'Over-budget proposals', or mark this exception as acknowledged without handling.

### diag_post_norm_0002: `missing_handler`
- Severity: `warning`
- Target: `worker:worker_main.exception_flow:exc_adapter_02`
- Source spans: `s32`
- Message: Exception flow 'exc_adapter_02' ('Vendor ineligibility') has no handler step in worker 'worker_main'.
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Add a handler step for 'Vendor ineligibility', or mark this exception as acknowledged without handling.

### diag_post_norm_0003: `missing_handler`
- Severity: `warning`
- Target: `worker:worker_main.exception_flow:exc_adapter_03`
- Source spans: `s33`
- Message: Exception flow 'exc_adapter_03' ('Approval denial') has no handler step in worker 'worker_main'.
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Add a handler step for 'Approval denial', or mark this exception as acknowledged without handling.

### diag_post_norm_0004: `missing_handler`
- Severity: `warning`
- Target: `worker:worker_main.exception_flow:exc_adapter_04`
- Source spans: `s34`
- Message: Exception flow 'exc_adapter_04' ('Missing
documents') has no handler step in worker 'worker_main'.
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Add a handler step for 'Missing
documents', or mark this exception as acknowledged without handling.

### diag_post_norm_0005: `missing_handler`
- Severity: `warning`
- Target: `worker:worker_main.exception_flow:exc_adapter_05`
- Source spans: `s35`
- Message: Exception flow 'exc_adapter_05' ('Compliance failure') has no handler step in worker 'worker_main'.
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Add a handler step for 'Compliance failure', or mark this exception as acknowledged without handling.

### diag_post_norm_0006: `missing_handler`
- Severity: `warning`
- Target: `worker:worker_main.exception_flow:exc_adapter_06`
- Source spans: `s36`
- Message: Exception flow 'exc_adapter_06' ('Waiver rejection') has no handler step in worker 'worker_main'.
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Add a handler step for 'Waiver rejection', or mark this exception as acknowledged without handling.

### diag_d10_0000: `type_or_contract_ambiguity`
- Severity: `warning`
- Target: `delegation_intent:s37`
- Source spans: `s37`
- Message: Delegation intent 'Bounded sourcing or quote-comparison subtasks may be delegated, but vendor
decis' lacks a valid worker/API handoff contract.  No INVOKE_WORKER or CALL_API will be generated from this span.  [sec_delegation_policy/p_delegation_rule_bounded_sourcing_or_quote_comparison_subtasks_may_be_delegated_but_vendor_decision_promotion_requires_normalized_quote_and_compliance_artifacts]
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Provide a valid worker/API handoff contract with input/output/API bindings covering span 's37'. hints=hint_delegation_0_sec_delegation_policy

## 5. Assumptions / Suggestions

- `ASM_0000` for `worker:worker_main.exception_flow:exc_adapter_00`: Exception flow has no handler action. The compiler suggests specifying what should happen when this failure occurs.
  - Reason: Source describes a failure condition but does not specify how to handle it.  The exception flow is preserved in SPL, but no handler command was rendered. (Exception flow 'exc_adapter_00' ('Insufficient quotes') has no handler step in worker 'worker_main'.)
  - Suggested resolution: Specify the handler action for worker:worker_main.exception_flow:exc_adapter_00: e.g. ask the user for missing information, block finalization, or continue with an explicit assumption.
  - Related diagnostic: `diag_post_norm_0000`
- `ASM_0001` for `worker:worker_main.exception_flow:exc_adapter_01`: Exception flow has no handler action. The compiler suggests specifying what should happen when this failure occurs.
  - Reason: Source describes a failure condition but does not specify how to handle it.  The exception flow is preserved in SPL, but no handler command was rendered. (Exception flow 'exc_adapter_01' ('Over-budget proposals') has no handler step in worker 'worker_main'.)
  - Suggested resolution: Specify the handler action for worker:worker_main.exception_flow:exc_adapter_01: e.g. ask the user for missing information, block finalization, or continue with an explicit assumption.
  - Related diagnostic: `diag_post_norm_0001`
- `ASM_0002` for `worker:worker_main.exception_flow:exc_adapter_02`: Exception flow has no handler action. The compiler suggests specifying what should happen when this failure occurs.
  - Reason: Source describes a failure condition but does not specify how to handle it.  The exception flow is preserved in SPL, but no handler command was rendered. (Exception flow 'exc_adapter_02' ('Vendor ineligibility') has no handler step in worker 'worker_main'.)
  - Suggested resolution: Specify the handler action for worker:worker_main.exception_flow:exc_adapter_02: e.g. ask the user for missing information, block finalization, or continue with an explicit assumption.
  - Related diagnostic: `diag_post_norm_0002`
- `ASM_0003` for `worker:worker_main.exception_flow:exc_adapter_03`: Exception flow has no handler action. The compiler suggests specifying what should happen when this failure occurs.
  - Reason: Source describes a failure condition but does not specify how to handle it.  The exception flow is preserved in SPL, but no handler command was rendered. (Exception flow 'exc_adapter_03' ('Approval denial') has no handler step in worker 'worker_main'.)
  - Suggested resolution: Specify the handler action for worker:worker_main.exception_flow:exc_adapter_03: e.g. ask the user for missing information, block finalization, or continue with an explicit assumption.
  - Related diagnostic: `diag_post_norm_0003`
- `ASM_0004` for `worker:worker_main.exception_flow:exc_adapter_04`: Exception flow has no handler action. The compiler suggests specifying what should happen when this failure occurs.
  - Reason: Source describes a failure condition but does not specify how to handle it.  The exception flow is preserved in SPL, but no handler command was rendered. (Exception flow 'exc_adapter_04' ('Missing
documents') has no handler step in worker 'worker_main'.)
  - Suggested resolution: Specify the handler action for worker:worker_main.exception_flow:exc_adapter_04: e.g. ask the user for missing information, block finalization, or continue with an explicit assumption.
  - Related diagnostic: `diag_post_norm_0004`
- `ASM_0005` for `worker:worker_main.exception_flow:exc_adapter_05`: Exception flow has no handler action. The compiler suggests specifying what should happen when this failure occurs.
  - Reason: Source describes a failure condition but does not specify how to handle it.  The exception flow is preserved in SPL, but no handler command was rendered. (Exception flow 'exc_adapter_05' ('Compliance failure') has no handler step in worker 'worker_main'.)
  - Suggested resolution: Specify the handler action for worker:worker_main.exception_flow:exc_adapter_05: e.g. ask the user for missing information, block finalization, or continue with an explicit assumption.
  - Related diagnostic: `diag_post_norm_0005`
- `ASM_0006` for `worker:worker_main.exception_flow:exc_adapter_06`: Exception flow has no handler action. The compiler suggests specifying what should happen when this failure occurs.
  - Reason: Source describes a failure condition but does not specify how to handle it.  The exception flow is preserved in SPL, but no handler command was rendered. (Exception flow 'exc_adapter_06' ('Waiver rejection') has no handler step in worker 'worker_main'.)
  - Suggested resolution: Specify the handler action for worker:worker_main.exception_flow:exc_adapter_06: e.g. ask the user for missing information, block finalization, or continue with an explicit assumption.
  - Related diagnostic: `diag_post_norm_0006`
- `ASM_0007` for `delegation_intent:s37`: Command has an ambiguous or incomplete contract. The compiler suggests providing the missing contract detail.
  - Reason: A command references an API, worker, or input source that is not fully specified.  The compiler cannot materialize the command without this information.
  - Suggested resolution: For delegation_intent:s37: provide the missing contract detail (API name, worker target, IO bindings, or source evidence).  See the related diagnostic for specifics.
  - Related diagnostic: `diag_d10_0000`

## 6. Provenance / TraceRecords

- `constraint:c_1` -> `direct`
  - Source: spans=`s25`, section=`sec_policies`, packet=`p_policy_require_minimum_quote_count_unless_exception_approved`
  - Explanation: Constraint 'c_1' (requirement): Require minimum quote count unless exception approved
- `constraint:c_2` -> `direct`
  - Source: spans=`s26`, section=`sec_policies`, packet=`p_policy_do_not_proceed_with_ineligible_vendors`
  - Explanation: Constraint 'c_2' (prohibition): Do not proceed with ineligible vendors
- `constraint:c_3` -> `direct`
  - Source: spans=`s27`, section=`sec_policies`, packet=`p_policy_require_category_specific_approval_thresholds`
  - Explanation: Constraint 'c_3' (requirement): Require category-specific approval thresholds
- `constraint:c_4` -> `direct`
  - Source: spans=`s28`, section=`sec_policies`, packet=`p_policy_record_justification_for_sole_source_or_waiver_cases`
  - Explanation: Constraint 'c_4' (requirement): Record justification for sole source or waiver cases
- `constraint:c_5` -> `direct`
  - Source: spans=`s29`, section=`sec_policies`, packet=`p_policy_deny_issuance_without_audit_complete_evidence`
  - Explanation: Constraint 'c_5' (gate): Deny issuance without audit-complete evidence
- `delegation_intent:bounded_sourcing_or_quote_comparison_delegation` -> `inferred`
  - Source: spans=`s37`, section=`sec_delegation_policy`, packet=`p_delegation_rule_bounded_sourcing_or_quote_comparison_subtasks_may_be_delegated_but_vendor_decision_promotion_requires_normalized_quote_and_compliance_artifacts`
  - Explanation: Delegation intent 'bounded_sourcing_or_quote_comparison_delegation': Bounded sourcing or quote-comparison subtasks may be delegated, but vendor decision promotion requires normalized quote 
- `delegation_intent:bounded_sourcing_or_quote_comparison_subtasks_may_be_delegated_but_vendor_decision_promotion_requires_normalized_quote_and_compliance_artifacts` -> `inferred`
  - Source: spans=`s37`, section=`sec_delegation_policy`, packet=`p_delegation_rule_bounded_sourcing_or_quote_comparison_subtasks_may_be_delegated_but_vendor_decision_promotion_requires_normalized_quote_and_compliance_artifacts`
  - Explanation: Delegation intent 'bounded_sourcing_or_quote_comparison_subtasks_may_be_delegated_but_vendor_decision_promotion_requires_normalized_quote_and_compliance_artifacts': Bounded sourcing or quote-comparison subtasks may be delegated, but vendor
decision promotion requires normalized quote 
- `flow:exc_adapter_00` -> `direct`
  - Source: spans=`s30`, section=`sec_failure_handling`, packet=`p_failure_mode_insufficient_quotes`
  - Explanation: Exception flow 'exc_adapter_00': Insufficient quotes
- `flow:exc_adapter_01` -> `direct`
  - Source: spans=`s31`, section=`sec_failure_handling`, packet=`p_failure_mode_over_budget_proposals`
  - Explanation: Exception flow 'exc_adapter_01': Over-budget proposals
- `flow:exc_adapter_02` -> `direct`
  - Source: spans=`s32`, section=`sec_failure_handling`, packet=`p_failure_mode_vendor_ineligibility`
  - Explanation: Exception flow 'exc_adapter_02': Vendor ineligibility
- `flow:exc_adapter_03` -> `direct`
  - Source: spans=`s33`, section=`sec_failure_handling`, packet=`p_failure_mode_approval_denial`
  - Explanation: Exception flow 'exc_adapter_03': Approval denial
- `flow:exc_adapter_04` -> `direct`
  - Source: spans=`s34`, section=`sec_failure_handling`, packet=`p_failure_mode_missing_documents`
  - Explanation: Exception flow 'exc_adapter_04': Missing
documents
- `flow:exc_adapter_05` -> `direct`
  - Source: spans=`s35`, section=`sec_failure_handling`, packet=`p_failure_mode_compliance_failure`
  - Explanation: Exception flow 'exc_adapter_05': Compliance failure
- `flow:exc_adapter_06` -> `direct`
  - Source: spans=`s36`, section=`sec_failure_handling`, packet=`p_failure_mode_waiver_rejection`
  - Explanation: Exception flow 'exc_adapter_06': Waiver rejection
- `flow:main` -> `direct`
  - Source: spans=`s16, s17, s18, s19, s22, s23, s24`, section=`sec_reusable_process`, packet=`p_process_step_normalize_the_request_and_determine_procurement_category`
  - Explanation: Main flow with 1 block(s).
- `profile:concept_0` -> `normalized`
  - Explanation: Concept: Standard purchase requests -- Requests for routine purchases that follow established procedures and guidelines.
- `profile:concept_1` -> `normalized`
  - Explanation: Concept: Software and services procurement -- The process of acquiring software licenses and professional services.
- `profile:concept_2` -> `normalized`
  - Explanation: Concept: Equipment purchases -- The acquisition of physical assets or tools required for operations.
- `profile:concept_3` -> `normalized`
  - Explanation: Concept: Vendor renewals -- The process of extending or renewing contracts with existing vendors.
- `profile:concept_4` -> `normalized`
  - Explanation: Concept: Exception-handled procurement cases -- Procurement scenarios that deviate from standard procedures and require special handling or approvals.
- `profile:persona` -> `inferred`
  - Explanation: Persona: Procurement process manager
- `step:st_1` -> `direct`
  - Source: spans=`s16`, section=`sec_reusable_process`, packet=`p_process_step_normalize_the_request_and_determine_procurement_category`
  - Explanation: Step 'st_1' maps to source span(s).
- `step:st_2` -> `direct`
  - Source: spans=`s17`, section=`sec_reusable_process`, packet=`p_process_step_identify_eligible_vendor_pool`
  - Explanation: Step 'st_2' maps to source span(s).
- `step:st_3` -> `direct`
  - Source: spans=`s18`, section=`sec_reusable_process`, packet=`p_process_step_solicit_quotes_or_equivalent_offers_according_to_policy`
  - Explanation: Step 'st_3' maps to source span(s).
- `step:st_4` -> `direct`
  - Source: spans=`s19`, section=`sec_reusable_process`, packet=`p_process_step_evaluate_budget_compliance_and_vendor_eligibility`
  - Explanation: Step 'st_4' maps to source span(s).
- `step:st_5` -> `direct`
  - Source: spans=`s22`, section=`sec_reusable_process`, packet=`p_process_step_route_approval_based_on_thresholds_and_category`
  - Explanation: Step 'st_5' maps to source span(s).
- `step:st_6` -> `direct`
  - Source: spans=`s23`, section=`sec_reusable_process`, packet=`p_process_step_issue_po_only_after_all_gates_pass`
  - Explanation: Step 'st_6' maps to source span(s).
- `step:st_7` -> `direct`
  - Source: spans=`s24`, section=`sec_reusable_process`, packet=`p_process_step_archive_evidence_for_audit`
  - Explanation: Step 'st_7' maps to source span(s).
- `variable:any_initial_vendor_suggestions` -> `normalized`
  - Source: section=`sec_inputs_for_each_run`
  - Explanation: Variable 'any_initial_vendor_suggestions' is declared by adapter hard fact in section 'sec_inputs_for_each_run'.
- `variable:approval_record` -> `direct`
  - Source: spans=`s22`, section=`sec_reusable_process`, packet=`p_process_step_route_approval_based_on_thresholds_and_category`
  - Explanation: Variable 'approval_record' is produced by source-backed step 'st_5'.
- `variable:audit_evidence_bundle` -> `direct`
  - Source: spans=`s24`, section=`sec_reusable_process`, packet=`p_process_step_archive_evidence_for_audit`
  - Explanation: Variable 'audit_evidence_bundle' is produced by source-backed step 'st_7'.
- `variable:budget_owner` -> `normalized`
  - Source: section=`sec_inputs_for_each_run`
  - Explanation: Variable 'budget_owner' is declared by adapter hard fact in section 'sec_inputs_for_each_run'.
- `variable:cost_center` -> `normalized`
  - Source: section=`sec_inputs_for_each_run`
  - Explanation: Variable 'cost_center' is declared by adapter hard fact in section 'sec_inputs_for_each_run'.
- `variable:po_or_equivalent_issuance_artifact` -> `direct`
  - Source: spans=`s23`, section=`sec_reusable_process`, packet=`p_process_step_issue_po_only_after_all_gates_pass`
  - Explanation: Variable 'po_or_equivalent_issuance_artifact' is produced by source-backed step 'st_6'.
- `variable:policy_profile` -> `normalized`
  - Source: section=`sec_inputs_for_each_run`
  - Explanation: Variable 'policy_profile' is declared by adapter hard fact in section 'sec_inputs_for_each_run'.
- `variable:procurement_category` -> `direct`
  - Source: spans=`s16`, section=`sec_reusable_process`, packet=`p_process_step_normalize_the_request_and_determine_procurement_category`
  - Explanation: Variable 'procurement_category' is produced by source-backed step 'st_1'.
- `variable:purchase_request` -> `normalized`
  - Source: section=`sec_inputs_for_each_run`
  - Explanation: Variable 'purchase_request' is declared by adapter hard fact in section 'sec_inputs_for_each_run'.
- `variable:requested_item_or_service` -> `normalized`
  - Source: section=`sec_inputs_for_each_run`
  - Explanation: Variable 'requested_item_or_service' is declared by adapter hard fact in section 'sec_inputs_for_each_run'.
- `variable:selected_vendor_decision_or_rejection_outcome` -> `direct`
  - Source: spans=`s19`, section=`sec_reusable_process`, packet=`p_process_step_evaluate_budget_compliance_and_vendor_eligibility`
  - Explanation: Variable 'selected_vendor_decision_or_rejection_outcome' is produced by source-backed step 'st_4'.
- `variable:sourcing_evaluation_record` -> `direct`
  - Source: spans=`s17`, section=`sec_reusable_process`, packet=`p_process_step_identify_eligible_vendor_pool`
  - Explanation: Variable 'sourcing_evaluation_record' is produced by source-backed step 'st_2'.
- `variable:urgency` -> `normalized`
  - Source: section=`sec_inputs_for_each_run`
  - Explanation: Variable 'urgency' is declared by adapter hard fact in section 'sec_inputs_for_each_run'.
- `variable:vendor_eligibility_context` -> `normalized`
  - Source: section=`sec_inputs_for_each_run`
  - Explanation: Variable 'vendor_eligibility_context' is declared by adapter hard fact in section 'sec_inputs_for_each_run'.
- `worker:MainWorker` -> `direct`
  - Source: spans=`s16, s17, s18, s19, s20, s21, s22, s23, s24, s37`, section=`sec_reusable_process`, packet=`p_process_step_normalize_the_request_and_determine_procurement_category`
  - Explanation: Main worker 'MainWorker' assembled from flow and step IRs.

## 7. Anti-Fabrication Checks

- `missing_handler`: Exception conditions without handler action stay as partial exception flows; no handler command is invented.
- `type_or_contract_ambiguity`: Unresolved worker/API contracts are reported as ambiguity; they are not downgraded to generic commands.
- Rendered SPL contains no executable `[INVOKE ...]` command.

## 8. Adapter / Validation Notes

Adapter warnings:
- LLM_DUPLICATE_FACT: LLM input fact 'purchase_request' duplicates deterministic fact -- rejected.
- LLM_DUPLICATE_FACT: LLM input fact 'requested_item_or_service' duplicates deterministic fact -- rejected.
- LLM_DUPLICATE_FACT: LLM input fact 'budget_owner' duplicates deterministic fact -- rejected.
- LLM_DUPLICATE_FACT: LLM input fact 'cost_center' duplicates deterministic fact -- rejected.
- LLM_DUPLICATE_FACT: LLM input fact 'urgency' duplicates deterministic fact -- rejected.
- LLM_DUPLICATE_FACT: LLM input fact 'procurement_category' duplicates deterministic fact -- rejected.
- LLM_DUPLICATE_FACT: LLM input fact 'policy_profile' duplicates deterministic fact -- rejected.
- LLM_DUPLICATE_FACT: LLM input fact 'vendor_eligibility_context' duplicates deterministic fact -- rejected.
- LLM_DUPLICATE_FACT: LLM input fact 'any_initial_vendor_suggestions' duplicates deterministic fact -- rejected.
- LLM_DUPLICATE_FACT: LLM output fact 'sourcing_evaluation_record' duplicates deterministic fact -- rejected.
- LLM_DUPLICATE_FACT: LLM output fact 'selected_vendor_decision_or_rejection_outcome' duplicates deterministic fact -- rejected.
- LLM_DUPLICATE_FACT: LLM output fact 'approval_record' duplicates deterministic fact -- rejected.
- LLM_DUPLICATE_FACT: LLM output fact 'po_or_equivalent_issuance_artifact' duplicates deterministic fact -- rejected.
- LLM_DUPLICATE_FACT: LLM output fact 'audit_evidence_bundle' duplicates deterministic fact -- rejected.
- LLM_DUPLICATE_FACT: LLM failure_mode fact 'insufficient_quotes' duplicates deterministic fact -- rejected.
- LLM_DUPLICATE_FACT: LLM failure_mode fact 'over_budget_proposals' duplicates deterministic fact -- rejected.
- LLM_DUPLICATE_FACT: LLM failure_mode fact 'vendor_ineligibility' duplicates deterministic fact -- rejected.
- LLM_DUPLICATE_FACT: LLM failure_mode fact 'approval_denial' duplicates deterministic fact -- rejected.
- LLM_DUPLICATE_FACT: LLM failure_mode fact 'missing_documents' duplicates deterministic fact -- rejected.
- LLM_DUPLICATE_FACT: LLM failure_mode fact 'compliance_failure' duplicates deterministic fact -- rejected.
- LLM_DUPLICATE_FACT: LLM failure_mode fact 'waiver_rejection' duplicates deterministic fact -- rejected.

Validation warnings:
- Candidate candidate_normalize_request accepted but contract fields are not source-backed; rejecting.
- D3: failure condition span 's30' (Insufficient quotes) is not owned by any worker; attached to main worker 'worker_main'.
- D3: failure condition span 's31' (Over-budget proposals) is not owned by any worker; attached to main worker 'worker_main'.
- D3: failure condition span 's32' (Vendor ineligibility) is not owned by any worker; attached to main worker 'worker_main'.
- D3: failure condition span 's33' (Approval denial) is not owned by any worker; attached to main worker 'worker_main'.
- D3: failure condition span 's34' (Missing
documents) is not owned by any worker; attached to main worker 'worker_main'.
- D3: failure condition span 's35' (Compliance failure) is not owned by any worker; attached to main worker 'worker_main'.
- D3: failure condition span 's36' (Waiver rejection) is not owned by any worker; attached to main worker 'worker_main'.
- Candidate candidate_normalize_request accepted but contract fields are not source-backed; rejecting.
- D3: failure condition span 's30' (Insufficient quotes) is not owned by any worker; attached to main worker 'worker_main'.
- D3: failure condition span 's31' (Over-budget proposals) is not owned by any worker; attached to main worker 'worker_main'.
- D3: failure condition span 's32' (Vendor ineligibility) is not owned by any worker; attached to main worker 'worker_main'.
- D3: failure condition span 's33' (Approval denial) is not owned by any worker; attached to main worker 'worker_main'.
- D3: failure condition span 's34' (Missing
documents) is not owned by any worker; attached to main worker 'worker_main'.
- D3: failure condition span 's35' (Compliance failure) is not owned by any worker; attached to main worker 'worker_main'.
- D3: failure condition span 's36' (Waiver rejection) is not owned by any worker; attached to main worker 'worker_main'.
- Worker worker_main: variable 'sourcing_evaluation_record' produced by multiple steps

## 9. SPL Draft

```spl
[DEFINE_AGENT: MainWorker "Orchestrate the end-to-end process and delegate to sub-tasks."]
    [DEFINE_PERSONA:]
        ROLE: Procurement process manager
    [END_PERSONA]
    [DEFINE_CONCEPTS:]
        Standardpurchaserequests: Requests for routine purchases that follow established procedures and guidelines.
        Softwareandservicesprocurement: The process of acquiring software licenses and professional services.
        Equipmentpurchases: The acquisition of physical assets or tools required for operations.
        Vendorrenewals: The process of extending or renewing contracts with existing vendors.
        Exceptionhandledprocurementcases: Procurement scenarios that deviate from standard procedures and require special handling or approvals.
    [END_CONCEPTS]
    [DEFINE_CONSTRAINTS:]
        Requirement: Require minimum quote count unless exception approved
        Prohibition: Do not proceed with ineligible vendors
        Requirement: Require category-specific approval thresholds
        Requirement: Record justification for sole source or waiver cases
        Gate: Deny issuance without audit-complete evidence
    [END_CONSTRAINTS]
    [DEFINE_VARIABLES:]
        "Purchase request" purchase_request: text
        "Requested item or service" requested_item_or_service: text
        "Budget owner" budget_owner: text
        "Cost center" cost_center: text
        "Urgency" urgency: text
        "Procurement category" procurement_category: text
        "Policy profile" policy_profile: text
        "Vendor eligibility context" vendor_eligibility_context: text
        "Any initial vendor suggestions (LLM note: Any initial vendor suggestions (LLM note: Any initial vendor suggestions))" any_initial_vendor_suggestions: text
        "A sourcing/evaluation record" sourcing_evaluation_record: text
        "Selected vendor decision or rejection outcome" selected_vendor_decision_or_rejection_outcome: text
        "Approval record (LLM note: Approval record (LLM note: Approval record))" approval_record: text
        "PO or equivalent issuance artifact" po_or_equivalent_issuance_artifact: text
        "Audit evidence bundle" audit_evidence_bundle: text
    [END_VARIABLES]
    [DEFINE_WORKER: "Orchestrate the end-to-end process and delegate to sub-tasks." MainWorker]
        [INPUTS]
            REQUIRED <REF>purchase_request</REF>
            REQUIRED <REF>requested_item_or_service</REF>
            REQUIRED <REF>budget_owner</REF>
            REQUIRED <REF>cost_center</REF>
            REQUIRED <REF>urgency</REF>
            REQUIRED <REF>procurement_category</REF>
            REQUIRED <REF>policy_profile</REF>
            REQUIRED <REF>vendor_eligibility_context</REF>
            REQUIRED <REF>any_initial_vendor_suggestions</REF>
        [END_INPUTS]
        [OUTPUTS]
            REQUIRED <REF>sourcing_evaluation_record</REF>
            REQUIRED <REF>selected_vendor_decision_or_rejection_outcome</REF>
            REQUIRED <REF>approval_record</REF>
            REQUIRED <REF>po_or_equivalent_issuance_artifact</REF>
            REQUIRED <REF>audit_evidence_bundle</REF>
        [END_OUTPUTS]
        [MAIN_FLOW]
            [SEQUENTIAL_BLOCK]
                COMMAND-1 [COMMAND Normalize the request and determine procurement category based on <REF>purchase_request</REF> and <REF>requested_item_or_service</REF> RESULT <REF>procurement_category</REF> SET]
                COMMAND-2 [COMMAND Identify eligible vendor pool based on <REF>procurement_category</REF>, <REF>vendor_eligibility_context</REF>, and <REF>any_initial_vendor_suggestions</REF> RESULT sourcing_evaluation_record: text SET]
                COMMAND-3 [COMMAND Solicit quotes or equivalent offers according to policy based on <REF>sourcing_evaluation_record</REF> and <REF>policy_profile</REF> RESULT <REF>sourcing_evaluation_record</REF> SET]
                COMMAND-4 [COMMAND Evaluate budget, compliance, and vendor eligibility based on <REF>sourcing_evaluation_record</REF>, <REF>budget_owner</REF>, <REF>cost_center</REF>, <REF>urgency</REF>, and <REF>policy_profile</REF> RESULT selected_vendor_decision_or_rejection_outcome: text SET]
                COMMAND-5 [COMMAND Route approval based on thresholds and category based on <REF>selected_vendor_decision_or_rejection_outcome</REF> and <REF>policy_profile</REF> RESULT approval_record: text SET]
                COMMAND-6 [COMMAND Issue PO only after all gates pass based on <REF>approval_record</REF> RESULT po_or_equivalent_issuance_artifact: text SET]
                COMMAND-7 [COMMAND Archive evidence for audit based on <REF>po_or_equivalent_issuance_artifact</REF> RESULT audit_evidence_bundle: text SET]
            [END_SEQUENTIAL_BLOCK]
        [END_MAIN_FLOW]
        [EXCEPTION_FLOW: Insufficient quotes]
        [END_EXCEPTION_FLOW]
        [EXCEPTION_FLOW: Over-budget proposals]
        [END_EXCEPTION_FLOW]
        [EXCEPTION_FLOW: Vendor ineligibility]
        [END_EXCEPTION_FLOW]
        [EXCEPTION_FLOW: Approval denial]
        [END_EXCEPTION_FLOW]
        [EXCEPTION_FLOW: Missing documents]
        [END_EXCEPTION_FLOW]
        [EXCEPTION_FLOW: Compliance failure]
        [END_EXCEPTION_FLOW]
        [EXCEPTION_FLOW: Waiver rejection]
        [END_EXCEPTION_FLOW]
    [END_WORKER]
[END_AGENT]
```
