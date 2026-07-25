# NL2SPL Feedback Report

## 1. Overall Compile State

- Completeness: `partial`
- SPL draft generated: `yes`
- Compile diagnostics: `39`
- Assumptions / suggestions: `30`
- Trace records: `50`
- Adapter warnings: `0`
- Validation errors: `0`
- Validation warnings: `3`

Result is partial because the following requirement gaps remain:
- `missing_handler` on `worker:worker_main.exception_flow:exc_adapter_03`: Exception flow 'exc_adapter_03' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_03, slot=handler_action]
- `missing_handler` on `worker:worker_main.exception_flow:exc_adapter_02`: Exception flow 'exc_adapter_02' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_02, slot=handler_action]
- `missing_handler` on `worker:worker_main.exception_flow:exc_adapter_01`: Exception flow 'exc_adapter_01' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_01, slot=handler_action]
- `missing_handler` on `worker:worker_main.exception_flow:exc_adapter_05`: Exception flow 'exc_adapter_05' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_05, slot=handler_action]
- `missing_handler` on `worker:worker_main.exception_flow:exc_adapter_04`: Exception flow 'exc_adapter_04' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_04, slot=handler_action]
- `missing_handler` on `worker:worker_main.exception_flow:exc_adapter_00`: Exception flow 'exc_adapter_00' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_00, slot=handler_action]
- `required_output_deferred` on `resource_contract_demand:rcd_output_s12`: Resource contract output 'rcd_output_s12' is deferred behind an API response whose return contract is not yet known. [construct=resource_contract_demand:rcd_output_s12, slot=producer]
- `missing_output_producer` on `resource_contract_demand:rcd_output_s14`: Resource contract output 'rcd_output_s14' (requiredness=required) has materialized resource(s) completion_status but no renderable producer. [construct=resource_contract_demand:rcd_output_s14, slot=producer]
- `required_output_deferred` on `worker:worker_main.output:source_evidence_set`: Required output 'source_evidence_set' (Set of sources and evidence produced as output.) is deferred behind an API response whose return contract is not yet known. [construct=worker:worker_main.output:source_evidence_set, slot=producer]
- `missing_output_producer` on `resource_contract_demand:rcd_output_s13`: Resource contract output 'rcd_output_s13' (requiredness=required) has materialized resource(s) assumptions_log but no renderable producer. [construct=resource_contract_demand:rcd_output_s13, slot=producer]
- `type_or_contract_ambiguity` on `worker_promotion:del_s37a`: WORKER_PROMOTION blocked by missing promotion slots.
  - `promotion_input_contract`: Missing clear input contract
  - `promotion_output_contract`: Missing clear output contract
  - `promotion_invocation_point`: Missing accepted decision or matching handoff with invocation hint
  - `promotion_result_handoff`: Missing matching handoff with output bindings
- `type_or_contract_ambiguity` on `worker:worker_main.step:st_3`: REQUEST_INPUT step has no value target (outputs). [construct=worker:worker_main.step:st_3, slot=value_target]
- `unmapped_behavior_span` on `worker:worker_main.span:s24`: Worker 'worker_main' behavior span 's24' (At the end) was not mapped to a step: Behavior span not mapped to any step by LLM
- `missing_provenance` on `profile:persona`: Rendered profile item 'profile:persona' has no source-backed provenance.
- `resource_kind_mismatch` on `resource_contract_demand:rcd_output_s14`: Resource contract demand 'rcd_output_s14' has binding(s) whose resource_kind/name do not match the materialized ResourceRegistryIR: variable:completion_status [construct=resource_contract_demand:rcd_output_s14, slot=resource_registry]
- `resource_kind_mismatch` on `resource_contract_demand:rcd_output_s13`: Resource contract demand 'rcd_output_s13' has binding(s) whose resource_kind/name do not match the materialized ResourceRegistryIR: variable:assumptions_log [construct=resource_contract_demand:rcd_output_s13, slot=resource_registry]

## 2. Materialized Source-Backed Structure

### Workers
- `worker:MainWorker` (direct) -- spans=s15, s16, s17, s19, s20, s21a, s22, s24, s25, s31, s32, s33, s34, s35, s36, s37a, s18, s23; section=sec_reusable_process; packet=p_list_item_produce_a_draft_if_the_user_asks_for_revision

### Profiles
- `profile:concept:0` (derived) -- spans=s1, s1
- `profile:concept:1` (derived) -- spans=s2, s2
- `profile:concept:2` (derived) -- spans=s3, s3
- `profile:concept:3` (derived) -- spans=s4, s4
- `profile:concept:4` (derived) -- spans=s5, s5
- `profile:persona.aspect:3` (derived) -- spans=s24, s24

### Flows
- `flow:alt_1` (direct) -- spans=s21a, s22; section=sec_reusable_process; packet=p_list_item_produce_a_draft_if_the_user_asks_for_revision
- `flow:exc_adapter_00` (direct) -- spans=s32
- `flow:exc_adapter_01` (direct) -- spans=s34
- `flow:exc_adapter_02` (direct) -- spans=s33
- `flow:exc_adapter_03` (direct) -- spans=s31
- `flow:exc_adapter_04` (direct) -- spans=s36
- `flow:exc_adapter_05` (direct) -- spans=s35
- `flow:main` (direct) -- spans=s15, s16, s17, s18, s19, s20, s23, s24, s25

### Steps
- `step:st_1` (direct) -- spans=s15
- `step:st_2` (direct) -- spans=s16
- `step:st_3` (direct) -- spans=s17
- `step:st_4` (direct) -- spans=s19
- `step:st_5` (direct) -- spans=s20
- `step:st_6` (direct) -- spans=s21a, s22; section=sec_reusable_process; packet=p_list_item_produce_a_draft_if_the_user_asks_for_revision
- `step:st_7` (direct) -- spans=s23
- `step:st_8` (direct) -- spans=s25
- `step:st_api_8564b1b8dc` (direct) -- spans=s18

### Variables
- `variable:assumptions_log_completion_status` (direct) -- spans=s25
- `variable:draft_communication_artifact` (direct) -- spans=s20

### Constraints
- `constraint:c_1` (direct) -- spans=s23
- `constraint:c_2` (direct) -- spans=s26
- `constraint:c_3` (direct) -- spans=s27
- `constraint:c_4` (direct) -- spans=s28
- `constraint:c_5` (direct) -- spans=s29
- `constraint:c_6` (direct) -- spans=s30
- `constraint:c_7` (direct) -- spans=s37b; section=sec_delegation_policy; packet=p_sentence_delegated_subtasks_such_as_source_gathering_or_template_matching_may_be_used_if_bounded_and_the_returned_evidence_is_normalized_into_approved_evidence_carriers

### Other
- `api:api:ApprovedSourceRecipesAPI` (direct) -- spans=s18

## 3. Not Materialized / Kept Partial

- `worker:worker_main.exception_flow:exc_adapter_03`: `missing_handler` -- Exception flow 'exc_adapter_03' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_03, slot=handler_action]
  - Suggested resolution: Add a handler step for 'Missing <REF>timeframe</REF>', or mark this exception as acknowledged without handling.
- `worker:worker_main.exception_flow:exc_adapter_02`: `missing_handler` -- Exception flow 'exc_adapter_02' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_02, slot=handler_action]
  - Suggested resolution: Add a handler step for 'insufficient source access', or mark this exception as acknowledged without handling.
- `worker:worker_main.exception_flow:exc_adapter_01`: `missing_handler` -- Exception flow 'exc_adapter_01' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_01, slot=handler_action]
  - Suggested resolution: Add a handler step for 'evidence shortage', or mark this exception as acknowledged without handling.
- `worker:worker_main.exception_flow:exc_adapter_05`: `missing_handler` -- Exception flow 'exc_adapter_05' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_05, slot=handler_action]
  - Suggested resolution: Add a handler step for 'user refusal to answer', or mark this exception as acknowledged without handling.
- `worker:worker_main.exception_flow:exc_adapter_04`: `missing_handler` -- Exception flow 'exc_adapter_04' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_04, slot=handler_action]
  - Suggested resolution: Add a handler step for 'provenance failure', or mark this exception as acknowledged without handling.
- `worker:worker_main.exception_flow:exc_adapter_00`: `missing_handler` -- Exception flow 'exc_adapter_00' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_00, slot=handler_action]
  - Suggested resolution: Add a handler step for 'conflicting instructions', or mark this exception as acknowledged without handling.
- `resource_contract_demand:rcd_output_s14`: `missing_output_producer` -- Resource contract output 'rcd_output_s14' (requiredness=required) has materialized resource(s) completion_status but no renderable producer. [construct=resource_contract_demand:rcd_output_s14, slot=producer]
  - Suggested resolution: Add a source-backed step or handoff that produces the materialized resource name with the same resource kind.
- `resource_contract_demand:rcd_output_s13`: `missing_output_producer` -- Resource contract output 'rcd_output_s13' (requiredness=required) has materialized resource(s) assumptions_log but no renderable producer. [construct=resource_contract_demand:rcd_output_s13, slot=producer]
  - Suggested resolution: Add a source-backed step or handoff that produces the materialized resource name with the same resource kind.
- `worker_promotion:del_s37a`: `type_or_contract_ambiguity` -- WORKER_PROMOTION blocked by missing promotion slots.
  - Source spans: `s37a`
  - `promotion_input_contract`: Missing clear input contract
  - `promotion_output_contract`: Missing clear output contract
  - `promotion_invocation_point`: Missing accepted decision or matching handoff with invocation hint
  - `promotion_result_handoff`: Missing matching handoff with output bindings
- `worker:worker_main.step:st_3`: `type_or_contract_ambiguity` -- REQUEST_INPUT step has no value target (outputs). [construct=worker:worker_main.step:st_3, slot=value_target]
- `worker:worker_main.span:s24`: `unmapped_behavior_span` -- Worker 'worker_main' behavior span 's24' (At the end) was not mapped to a step: Behavior span not mapped to any step by LLM

## 4. Diagnostics

### irs_02b0da72bfd4: `missing_handler`
- Severity: `warning`
- Target: `worker:worker_main.exception_flow:exc_adapter_03`
- Source spans: `s31`
- Message: Exception flow 'exc_adapter_03' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_03, slot=handler_action]
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Add a handler step for 'Missing <REF>timeframe</REF>', or mark this exception as acknowledged without handling.
- Missing slot: `handler_action`
- Missing reason: Exception flow 'exc_adapter_03' has condition but no handler step.

### irs_1353fbe13843: `missing_handler`
- Severity: `warning`
- Target: `worker:worker_main.exception_flow:exc_adapter_02`
- Source spans: `s33`
- Message: Exception flow 'exc_adapter_02' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_02, slot=handler_action]
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Add a handler step for 'insufficient source access', or mark this exception as acknowledged without handling.
- Missing slot: `handler_action`
- Missing reason: Exception flow 'exc_adapter_02' has condition but no handler step.

### irs_5dcf003db873: `missing_handler`
- Severity: `warning`
- Target: `worker:worker_main.exception_flow:exc_adapter_01`
- Source spans: `s34`
- Message: Exception flow 'exc_adapter_01' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_01, slot=handler_action]
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Add a handler step for 'evidence shortage', or mark this exception as acknowledged without handling.
- Missing slot: `handler_action`
- Missing reason: Exception flow 'exc_adapter_01' has condition but no handler step.

### irs_818c56cbc102: `missing_handler`
- Severity: `warning`
- Target: `worker:worker_main.exception_flow:exc_adapter_05`
- Source spans: `s35`
- Message: Exception flow 'exc_adapter_05' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_05, slot=handler_action]
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Add a handler step for 'user refusal to answer', or mark this exception as acknowledged without handling.
- Missing slot: `handler_action`
- Missing reason: Exception flow 'exc_adapter_05' has condition but no handler step.

### irs_92ae165af1b0: `missing_handler`
- Severity: `warning`
- Target: `worker:worker_main.exception_flow:exc_adapter_04`
- Source spans: `s36`
- Message: Exception flow 'exc_adapter_04' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_04, slot=handler_action]
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Add a handler step for 'provenance failure', or mark this exception as acknowledged without handling.
- Missing slot: `handler_action`
- Missing reason: Exception flow 'exc_adapter_04' has condition but no handler step.

### irs_eae84cf20dcd: `missing_handler`
- Severity: `warning`
- Target: `worker:worker_main.exception_flow:exc_adapter_00`
- Source spans: `s32`
- Message: Exception flow 'exc_adapter_00' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_00, slot=handler_action]
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Add a handler step for 'conflicting instructions', or mark this exception as acknowledged without handling.
- Missing slot: `handler_action`
- Missing reason: Exception flow 'exc_adapter_00' has condition but no handler step.

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
- Message: Required output 'source_evidence_set' (Set of sources and evidence produced as output.) is deferred behind an API response whose return contract is not yet known. [construct=worker:worker_main.output:source_evidence_set, slot=producer]
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Declare the API return contract or add a source-backed producer step for 'source_evidence_set'.
- Missing slot: `producer`
- Missing reason: Required output 'source_evidence_set' (Set of sources and evidence produced as output.) is deferred behind an API response whose return contract is not yet known.

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

### grouped:worker_promotion:del_s37a: `type_or_contract_ambiguity`
- Severity: `warning`
- Target: `worker_promotion:del_s37a`
- Source spans: `s37a`
- Message: WORKER_PROMOTION blocked by missing promotion slots.
- Blocks rendering: `false`
- Blocks completion: `true`
- Missing slots:
  - `promotion_input_contract`: Missing clear input contract
    - Diagnostic: `irs_b07e4440a217`
  - `promotion_output_contract`: Missing clear output contract
    - Diagnostic: `irs_bc2ac4dfedc3`
  - `promotion_invocation_point`: Missing accepted decision or matching handoff with invocation hint
    - Diagnostic: `irs_4003814ca554`
  - `promotion_result_handoff`: Missing matching handoff with output bindings
    - Diagnostic: `irs_47b7c7feaabc`

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
- Target: `worker:worker_main.span:s24`
- Source spans: `s24`
- Message: Worker 'worker_main' behavior span 's24' (At the end) was not mapped to a step: Behavior span not mapped to any step by LLM
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
- Target: `variable:available_connectors_or_source_repositories`
- Message: Variable 'available_connectors_or_source_repositories' (List[text]) is a contract input with no source-backed producer or adapter evidence.
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_prov_0005: `missing_provenance`
- Severity: `warning`
- Target: `variable:source_evidence_set`
- Message: Variable 'source_evidence_set' (List[text]) is a contract output with no source-backed producer or adapter evidence.
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_prov_0006: `missing_provenance`
- Severity: `warning`
- Target: `profile:persona`
- Message: Rendered profile item 'profile:persona' has no source-backed provenance.
- Blocks rendering: `false`
- Blocks completion: `true`

### diag_prov_0007: `missing_provenance`
- Severity: `warning`
- Target: `profile:persona.aspect:0`
- Message: Unrendered profile item 'profile:persona.aspect:0' has no source-backed provenance.
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_prov_0008: `missing_provenance`
- Severity: `warning`
- Target: `profile:persona.aspect:1`
- Message: Unrendered profile item 'profile:persona.aspect:1' has no source-backed provenance.
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_prov_0009: `missing_provenance`
- Severity: `warning`
- Target: `profile:persona.aspect:2`
- Message: Unrendered profile item 'profile:persona.aspect:2' has no source-backed provenance.
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_prov_0010: `missing_provenance`
- Severity: `warning`
- Target: `profile:concept:5`
- Message: Unrendered profile item 'profile:concept:5' has no source-backed provenance.
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_prov_0011: `missing_provenance`
- Severity: `warning`
- Target: `profile:concept:6`
- Message: Unrendered profile item 'profile:concept:6' has no source-backed provenance.
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_prov_0012: `missing_provenance`
- Severity: `warning`
- Target: `profile:concept:7`
- Message: Unrendered profile item 'profile:concept:7' has no source-backed provenance.
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_prov_0013: `missing_provenance`
- Severity: `warning`
- Target: `profile:concept:8`
- Message: Unrendered profile item 'profile:concept:8' has no source-backed provenance.
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_prov_0014: `missing_provenance`
- Severity: `warning`
- Target: `profile:concept:9`
- Message: Unrendered profile item 'profile:concept:9' has no source-backed provenance.
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_prov_0015: `missing_provenance`
- Severity: `warning`
- Target: `profile:concept:10`
- Message: Unrendered profile item 'profile:concept:10' has no source-backed provenance.
- Blocks rendering: `false`
- Blocks completion: `false`

### stage2_route_refinement_diagnostic_: `route_refinement_diagnostic`
- Severity: `info`
- Message: LLM route diagnostic [prior_overridden] span='s23': Structural prior suggested a process step, but the text is a constraint on finalization.
- Blocks rendering: `false`
- Blocks completion: `false`

### stage2_route_refinement_split_s21: `route_refinement_split`
- Severity: `info`
- Target: `span:s21`
- Source spans: `s21`
- Message: Split recommended for s21: The span is truncated but still expresses a revision process step; no separate semantic target is clearly recoverable.
- Blocks rendering: `false`
- Blocks completion: `false`

### stage2_route_refinement_split_s37: `route_refinement_split`
- Severity: `info`
- Target: `span:s37`
- Source spans: `s37`
- Message: Split recommended for s37: The span mixes delegation permission with conditions on delegation use and evidence normalization.
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
  - Related diagnostic: `irs_eae84cf20dcd`
- `ASM_0001` for `worker:worker_main.exception_flow:exc_adapter_01`: Exception flow has no handler action. The compiler suggests specifying what should happen when this failure occurs.
  - Reason: Source describes a failure condition but does not specify how to handle it.  The exception flow is preserved in SPL, but no handler command was rendered. (Exception flow 'exc_adapter_01' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adap)
  - Suggested resolution: Specify the handler action for worker:worker_main.exception_flow:exc_adapter_01: e.g. ask the user for missing information, block finalization, or continue with an explicit assumption.
  - Related diagnostic: `irs_5dcf003db873`
- `ASM_0002` for `worker:worker_main.exception_flow:exc_adapter_02`: Exception flow has no handler action. The compiler suggests specifying what should happen when this failure occurs.
  - Reason: Source describes a failure condition but does not specify how to handle it.  The exception flow is preserved in SPL, but no handler command was rendered. (Exception flow 'exc_adapter_02' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adap)
  - Suggested resolution: Specify the handler action for worker:worker_main.exception_flow:exc_adapter_02: e.g. ask the user for missing information, block finalization, or continue with an explicit assumption.
  - Related diagnostic: `irs_1353fbe13843`
- `ASM_0003` for `worker:worker_main.exception_flow:exc_adapter_03`: Exception flow has no handler action. The compiler suggests specifying what should happen when this failure occurs.
  - Reason: Source describes a failure condition but does not specify how to handle it.  The exception flow is preserved in SPL, but no handler command was rendered. (Exception flow 'exc_adapter_03' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adap)
  - Suggested resolution: Specify the handler action for worker:worker_main.exception_flow:exc_adapter_03: e.g. ask the user for missing information, block finalization, or continue with an explicit assumption.
  - Related diagnostic: `irs_02b0da72bfd4`
- `ASM_0004` for `worker:worker_main.exception_flow:exc_adapter_04`: Exception flow has no handler action. The compiler suggests specifying what should happen when this failure occurs.
  - Reason: Source describes a failure condition but does not specify how to handle it.  The exception flow is preserved in SPL, but no handler command was rendered. (Exception flow 'exc_adapter_04' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adap)
  - Suggested resolution: Specify the handler action for worker:worker_main.exception_flow:exc_adapter_04: e.g. ask the user for missing information, block finalization, or continue with an explicit assumption.
  - Related diagnostic: `irs_92ae165af1b0`
- `ASM_0005` for `worker:worker_main.exception_flow:exc_adapter_05`: Exception flow has no handler action. The compiler suggests specifying what should happen when this failure occurs.
  - Reason: Source describes a failure condition but does not specify how to handle it.  The exception flow is preserved in SPL, but no handler command was rendered. (Exception flow 'exc_adapter_05' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adap)
  - Suggested resolution: Specify the handler action for worker:worker_main.exception_flow:exc_adapter_05: e.g. ask the user for missing information, block finalization, or continue with an explicit assumption.
  - Related diagnostic: `irs_818c56cbc102`
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
- `ASM_0013` for `variable:available_connectors_or_source_repositories`: Variable has no discoverable source provenance.
  - Reason: The compiler could not trace this variable back to a source span, adapter hard fact, or producer step.  Its origin is assumed.
  - Suggested resolution: For variable:available_connectors_or_source_repositories: add source evidence (a span, adapter hint, or producer step) that justifies this variable's existence.
  - Related diagnostic: `diag_prov_0004`
- `ASM_0014` for `variable:source_evidence_set`: Variable has no discoverable source provenance.
  - Reason: The compiler could not trace this variable back to a source span, adapter hard fact, or producer step.  Its origin is assumed.
  - Suggested resolution: For variable:source_evidence_set: add source evidence (a span, adapter hint, or producer step) that justifies this variable's existence.
  - Related diagnostic: `diag_prov_0005`
- `ASM_0015` for `profile:persona`: Rendered profile item has no source-backed provenance.
  - Reason: The compiler rendered this required profile item, but could not trace it to a source span.
  - Suggested resolution: For profile:persona: add source evidence that justifies this profile item, or confirm the assumption-bearing draft.
  - Related diagnostic: `diag_prov_0006`
- `ASM_0016` for `profile:persona.aspect:0`: Unrendered profile item has no source-backed provenance.
  - Reason: The compiler did not render this optional profile item because it could not trace it to a source span.
  - Suggested resolution: For profile:persona.aspect:0: add source evidence that justifies this profile item, or confirm the assumption-bearing draft.
  - Related diagnostic: `diag_prov_0007`
- `ASM_0017` for `profile:persona.aspect:1`: Unrendered profile item has no source-backed provenance.
  - Reason: The compiler did not render this optional profile item because it could not trace it to a source span.
  - Suggested resolution: For profile:persona.aspect:1: add source evidence that justifies this profile item, or confirm the assumption-bearing draft.
  - Related diagnostic: `diag_prov_0008`
- `ASM_0018` for `profile:persona.aspect:2`: Unrendered profile item has no source-backed provenance.
  - Reason: The compiler did not render this optional profile item because it could not trace it to a source span.
  - Suggested resolution: For profile:persona.aspect:2: add source evidence that justifies this profile item, or confirm the assumption-bearing draft.
  - Related diagnostic: `diag_prov_0009`
- `ASM_0019` for `profile:concept:5`: Unrendered profile item has no source-backed provenance.
  - Reason: The compiler did not render this optional profile item because it could not trace it to a source span.
  - Suggested resolution: For profile:concept:5: add source evidence that justifies this profile item, or confirm the assumption-bearing draft.
  - Related diagnostic: `diag_prov_0010`
- `ASM_0020` for `profile:concept:6`: Unrendered profile item has no source-backed provenance.
  - Reason: The compiler did not render this optional profile item because it could not trace it to a source span.
  - Suggested resolution: For profile:concept:6: add source evidence that justifies this profile item, or confirm the assumption-bearing draft.
  - Related diagnostic: `diag_prov_0011`
- `ASM_0021` for `profile:concept:7`: Unrendered profile item has no source-backed provenance.
  - Reason: The compiler did not render this optional profile item because it could not trace it to a source span.
  - Suggested resolution: For profile:concept:7: add source evidence that justifies this profile item, or confirm the assumption-bearing draft.
  - Related diagnostic: `diag_prov_0012`
- `ASM_0022` for `profile:concept:8`: Unrendered profile item has no source-backed provenance.
  - Reason: The compiler did not render this optional profile item because it could not trace it to a source span.
  - Suggested resolution: For profile:concept:8: add source evidence that justifies this profile item, or confirm the assumption-bearing draft.
  - Related diagnostic: `diag_prov_0013`
- `ASM_0023` for `profile:concept:9`: Unrendered profile item has no source-backed provenance.
  - Reason: The compiler did not render this optional profile item because it could not trace it to a source span.
  - Suggested resolution: For profile:concept:9: add source evidence that justifies this profile item, or confirm the assumption-bearing draft.
  - Related diagnostic: `diag_prov_0014`
- `ASM_0024` for `profile:concept:10`: Unrendered profile item has no source-backed provenance.
  - Reason: The compiler did not render this optional profile item because it could not trace it to a source span.
  - Suggested resolution: For profile:concept:10: add source evidence that justifies this profile item, or confirm the assumption-bearing draft.
  - Related diagnostic: `diag_prov_0015`
- `ASM_0025, ASM_0026, ASM_0027, ASM_0028` for `worker_promotion:del_s37a`: Worker promotion has an incomplete contract.
  - Reason: The candidate is blocked by multiple missing promotion slots.
  - Suggested resolution: Provide the missing input/output contracts, invocation point, and result handoff details listed in the related diagnostics.
  - Related diagnostics: `irs_b07e4440a217, irs_bc2ac4dfedc3, irs_4003814ca554, irs_47b7c7feaabc`
- `ASM_0029` for `worker:worker_main.span:s24`: A behavior span from the source was not mapped to any executable step.
  - Reason: The source describes behavior that could not be translated into a concrete command.  This may be intentional (policy, non-executable description) or may indicate missing detail.
  - Suggested resolution: For worker:worker_main.span:s24: either add a step implementing this behavior, or acknowledge it as non-executable context.
  - Related diagnostic: `diag_s7_0000`

## 7. Provenance / TraceRecords

- `api:api:ApprovedSourceRecipesAPI` -> `direct`
  - Source: spans=`s18`
  - Explanation: API declaration 'ApprovedSourceRecipesAPI' materialized as grammar_minimal_partial.
- `constraint:c_1` -> `direct`
  - Source: spans=`s23`
  - Explanation: Constraint 'c_1' (gate): Do not finalize if required slots remain missing unless the draft is explicitly
- `constraint:c_2` -> `direct`
  - Source: spans=`s26`
  - Explanation: Constraint 'c_2' (prohibition): Do not invent links or unseen facts.
- `constraint:c_3` -> `direct`
  - Source: spans=`s27`
  - Explanation: Constraint 'c_3' (evidence): Require evidence for sourced claims.
- `constraint:c_4` -> `direct`
  - Source: spans=`s28`
  - Explanation: Constraint 'c_4' (requirement): Limit questions per turn.
- `constraint:c_5` -> `direct`
  - Source: spans=`s29`
  - Explanation: Constraint 'c_5' (requirement): Prefer tool evidence over unnecessary user questioning.
- `constraint:c_6` -> `direct`
  - Source: spans=`s30`
  - Explanation: Constraint 'c_6' (gate): Deny finalization if critical slots are missing or provenance fails.
- `constraint:c_7` -> `direct`
  - Source: spans=`s37b`, section=`sec_delegation_policy`, packet=`p_sentence_delegated_subtasks_such_as_source_gathering_or_template_matching_may_be_used_if_bounded_and_the_returned_evidence_is_normalized_into_approved_evidence_carriers`
  - Explanation: Constraint 'c_7' (delegation_boundary): Delegated subtasks such as source gathering or template matching may be used onl
- `flow:alt_1` -> `direct`
  - Source: spans=`s21a, s22`, section=`sec_reusable_process`, packet=`p_list_item_produce_a_draft_if_the_user_asks_for_revision`
  - Explanation: Alternative flow 'alt_1': the user asks for a revision
- `flow:exc_adapter_00` -> `direct`
  - Source: spans=`s32`
  - Explanation: Exception flow 'exc_adapter_00': conflicting instructions
- `flow:exc_adapter_01` -> `direct`
  - Source: spans=`s34`
  - Explanation: Exception flow 'exc_adapter_01': evidence shortage
- `flow:exc_adapter_02` -> `direct`
  - Source: spans=`s33`
  - Explanation: Exception flow 'exc_adapter_02': insufficient source access
- `flow:exc_adapter_03` -> `direct`
  - Source: spans=`s31`
  - Explanation: Exception flow 'exc_adapter_03': Missing <REF>timeframe</REF>
- `flow:exc_adapter_04` -> `direct`
  - Source: spans=`s36`
  - Explanation: Exception flow 'exc_adapter_04': provenance failure
- `flow:exc_adapter_05` -> `direct`
  - Source: spans=`s35`
  - Explanation: Exception flow 'exc_adapter_05': user refusal to answer
- `flow:main` -> `direct`
  - Source: spans=`s15, s16, s17, s18, s19, s20, s23, s24, s25`
  - Explanation: Main flow with 7 block(s).
- `profile:concept:0` -> `derived`
  - Source: spans=`s1, s1`
  - Explanation: Concept: Internal newsletters -- Newsletter-style communication intended for internal organizational audiences.
- `profile:concept:1` -> `derived`
  - Source: spans=`s2, s2`
  - Explanation: Concept: Announcements -- Short internal communications meant to inform people about updates or events.
- `profile:concept:10` -> `assumed` [needs confirmation]
  - Explanation: Concept: Approved evidence carriers -- Accepted formats or containers for normalized evidence returned by delegated subtasks.
- `profile:concept:2` -> `derived`
  - Source: spans=`s3, s3`
  - Explanation: Concept: Update digests -- Condensed summaries of updates collected into a single communication.
- `profile:concept:3` -> `derived`
  - Source: spans=`s4, s4`
  - Explanation: Concept: Executive briefs -- Concise communication artifacts prepared for executives, summarizing key information.
- `profile:concept:4` -> `derived`
  - Source: spans=`s5, s5`
  - Explanation: Concept: Internal-comms artifacts -- Communication materials used within an organization for internal communication purposes.
- `profile:concept:5` -> `assumed` [needs confirmation]
  - Explanation: Concept: Source recipes -- Approved procedures or methods for retrieving sources.
- `profile:concept:6` -> `assumed` [needs confirmation]
  - Explanation: Concept: Provenance -- Traceable origin and evidence chain for sourced facts.
- `profile:concept:7` -> `assumed` [needs confirmation]
  - Explanation: Concept: Assumptions log -- A short record of unresolved items and the assumptions made about them.
- `profile:concept:8` -> `assumed` [needs confirmation]
  - Explanation: Concept: Completion status -- A marker indicating the outcome state of the run.
- `profile:concept:9` -> `assumed` [needs confirmation]
  - Explanation: Concept: Critical slots -- Required information fields that must be present before finalization.
- `profile:persona` -> `assumed` [needs confirmation]
  - Explanation: Persona: Internal communications specialist
- `profile:persona.aspect:0` -> `assumed` [needs confirmation]
  - Explanation: Persona aspect: EvidenceDriven
- `profile:persona.aspect:1` -> `assumed` [needs confirmation]
  - Explanation: Persona aspect: ClarificationFocused
- `profile:persona.aspect:2` -> `assumed` [needs confirmation]
  - Explanation: Persona aspect: ConstraintAware
- `profile:persona.aspect:3` -> `derived`
  - Source: spans=`s24, s24`
  - Explanation: Persona aspect: StructuredCompletion
- `step:st_1` -> `direct`
  - Source: spans=`s15`
  - Explanation: Step 'st_1' maps to source span(s).
- `step:st_2` -> `direct`
  - Source: spans=`s16`
  - Explanation: Step 'st_2' maps to source span(s).
- `step:st_3` -> `direct`
  - Source: spans=`s17`
  - Explanation: Step 'st_3' maps to source span(s).
- `step:st_4` -> `direct`
  - Source: spans=`s19`
  - Explanation: Step 'st_4' maps to source span(s).
- `step:st_5` -> `direct`
  - Source: spans=`s20`
  - Explanation: Step 'st_5' maps to source span(s).
- `step:st_6` -> `direct`
  - Source: spans=`s21a, s22`, section=`sec_reusable_process`, packet=`p_list_item_produce_a_draft_if_the_user_asks_for_revision`
  - Explanation: Step 'st_6' maps to source span(s).
- `step:st_7` -> `direct`
  - Source: spans=`s23`
  - Explanation: Step 'st_7' maps to source span(s).
- `step:st_8` -> `direct`
  - Source: spans=`s25`
  - Explanation: Step 'st_8' maps to source span(s).
- `step:st_api_8564b1b8dc` -> `direct`
  - Source: spans=`s18`
  - Explanation: Step 'st_api_8564b1b8dc' maps to source span(s).
- `variable:assumptions_log_completion_status` -> `direct`
  - Source: spans=`s25`
  - Explanation: Variable 'assumptions_log_completion_status' is produced by source-backed step 'st_8'.
- `variable:available_connectors_or_source_repositories` -> `assumed` [needs confirmation]
  - Explanation: Variable 'available_connectors_or_source_repositories' is declared as worker input contract with no source evidence.
- `variable:draft_communication_artifact` -> `direct`
  - Source: spans=`s20`
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
  - Source: spans=`s15, s16, s17, s19, s20, s21a, s22, s24, s25, s31, s32, s33, s34, s35, s36, s37a, s18, s23`, section=`sec_reusable_process`, packet=`p_list_item_produce_a_draft_if_the_user_asks_for_revision`
  - Explanation: Main worker 'MainWorker' assembled from flow and step IRs.

## 8. Anti-Fabrication Checks

- `missing_handler`: Exception conditions without handler action stay as partial exception flows; no handler command is invented.
- `missing_output_producer`: Required outputs without a source-backed producer stay in the contract; no synthetic producer command is invented.
- `type_or_contract_ambiguity`: Unresolved worker/API contracts are reported as ambiguity; they are not downgraded to generic commands.
- Rendered SPL contains no executable `[INVOKE ...]` command.

## 9. Adapter / Validation Notes

Validation warnings:
- Aggregated multi-output step st_8 into assumptions_log_completion_status without unpack steps.
- Unused variable declared: assumptions_log
- Unused variable declared: completion_status

## 10. SPL Draft

```spl
[DEFINE_AGENT: MainWorker "Orchestrate the end-to-end process and delegate to sub-tasks."]
    [DEFINE_PERSONA:]
        ROLE: Internal communications specialist
        StructuredCompletion: Produces a draft, source/evidence set, assumptions log, and completion status, and records unresolved items at the end.
    [END_PERSONA]
    [DEFINE_CONCEPTS:]
        Internalnewsletters: Newsletter-style communication intended for internal organizational audiences.
        Announcements: Short internal communications meant to inform people about updates or events.
        Updatedigests: Condensed summaries of updates collected into a single communication.
        Executivebriefs: Concise communication artifacts prepared for executives, summarizing key information.
        Internalcommsartifacts: Communication materials used within an organization for internal communication purposes.
    [END_CONCEPTS]
    [DEFINE_CONSTRAINTS:]
        Gate: Do not finalize if required slots remain missing unless the draft is explicitly marked as assumption-bearing and the user confirms.
        Prohibition: Do not invent links or unseen facts.
        Evidence: Require evidence for sourced claims.
        Requirement: Limit questions per turn.
        Requirement: Prefer tool evidence over unnecessary user questioning.
        Gate: Deny finalization if critical slots are missing or provenance fails.
        DelegationBoundary: Delegated subtasks such as source gathering or template matching may be used only if bounded and the returned evidence is normalized into approved evidence carriers.
    [END_CONSTRAINTS]
    [DEFINE_TYPES:]
        AssumptionsLogCompletionStatus = { assumptions_log: text, completion_status: text }
    [END_TYPES]
    [DEFINE_VARIABLES:]
        "Optional preferences for output format." format_preferences: text
        "The user's request to be handled." user_request: text
        "Optional topics already known to the user or system." known_topics: List [text]
        "Optional timeframe for the requested work." timeframe: text
        "Available connectors or source repositories that can be used." available_connectors_or_source_repositories: List [text]
        "Draft communication artifact produced as output." draft_communication_artifact: text
        "Set of sources and evidence produced as output." source_evidence_set: List [text]
        "Structured result for step st_8." assumptions_log_completion_status: AssumptionsLogCompletionStatus
        "Short log of assumptions for unresolved items." assumptions_log: text
        "Completion status for the run." completion_status: text
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
            REQUIRED <REF>assumptions_log_completion_status</REF>
        [END_OUTPUTS]
        [MAIN_FLOW]
            [SEQUENTIAL_BLOCK]
                COMMAND-1 [COMMAND Determine the requested communication type based on <REF>user_request</REF>]
                COMMAND-2 [COMMAND Identify missing required fields based on <REF>user_request</REF>]
            [END_SEQUENTIAL_BLOCK]
            DECISION-1 [IF required fields are still missing]
                COMMAND-3 [INPUT Ask the user the highest-value clarifying questions based on <REF>user_request</REF> VALUE user_input:text SET]
            [END_IF]
            DECISION-2 [IF sources are needed and available]
                COMMAND-4 [CALL ApprovedSourceRecipesAPI]
            [END_IF]
            [SEQUENTIAL_BLOCK]
                COMMAND-5 [COMMAND Maintain provenance for externally sourced facts]
            [END_SEQUENTIAL_BLOCK]
            DECISION-3 [IF enough required information is available]
                COMMAND-6 [COMMAND Produce the draft communication artifact based on <REF>user_request</REF>, <REF>known_topics</REF>, <REF>format_preferences</REF>, and <REF>timeframe</REF> RESULT draft_communication_artifact: text SET]
            [END_IF]
            DECISION-4 [IF required slots remain missing unless the draft is explicitly marked as assumption-bearing and the user confirms]
                COMMAND-7 [COMMAND Avoid finalizing the draft when required slots remain missing unless the draft is assumption-bearing and the user confirms]
            [END_IF]
            [SEQUENTIAL_BLOCK]
                COMMAND-8 [COMMAND Record assumptions and set completion status RESULT assumptions_log_completion_status: AssumptionsLogCompletionStatus SET]
            [END_SEQUENTIAL_BLOCK]
        [END_MAIN_FLOW]
        [ALTERNATIVE_FLOW: the user asks for a revision]
            [SEQUENTIAL_BLOCK]
                COMMAND-9 [COMMAND Revise the draft while checking constraints based on <REF>user_request</REF>]
            [END_SEQUENTIAL_BLOCK]
        [END_ALTERNATIVE_FLOW]
        [EXCEPTION_FLOW: conflicting instructions]
        [END_EXCEPTION_FLOW]
        [EXCEPTION_FLOW: evidence shortage]
        [END_EXCEPTION_FLOW]
        [EXCEPTION_FLOW: insufficient source access]
        [END_EXCEPTION_FLOW]
        [EXCEPTION_FLOW: Missing <REF>timeframe</REF>]
        [END_EXCEPTION_FLOW]
        [EXCEPTION_FLOW: provenance failure]
        [END_EXCEPTION_FLOW]
        [EXCEPTION_FLOW: user refusal to answer]
        [END_EXCEPTION_FLOW]
    [END_WORKER]
[END_AGENT]
```
