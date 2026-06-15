# NL2SPL Feedback Report

## 1. Overall Compile State

- Completeness: `partial`
- SPL draft generated: `yes`
- Compile diagnostics: `7`
- Assumptions / suggestions: `4`
- Trace records: `22`
- Adapter warnings: `0`
- Validation errors: `0`
- Validation warnings: `0`

Result is partial because the following requirement gaps remain:
- `missing_output_producer` on `worker:worker_main.output:completion_status`: Required output 'completion_status' (Final completion status of the main worker.) has no source-backed producer step. [construct=worker:worker_main.output:completion_status, slot=producer]
- `missing_output_producer` on `resource_contract_demand:rcd_output_s4`: Resource contract output 'rcd_output_s4' (requiredness=required) has materialized resource(s) completion_status but no renderable producer. [construct=resource_contract_demand:rcd_output_s4, slot=producer]

## 2. Materialized Source-Backed Structure

### Workers
- `worker:MainWorker` (direct) -- spans=s5, s7, s8; section=sec_reusable_process; packet=p_list_item_first_read_the_incident_report_then_extract_a_separate_child_worker_named_complianceacknowledgement_this_child_worker_is_required_by_policy_as_a_bounded_subtask

### Flows
- `flow:main` (direct) -- spans=s5, s8; section=sec_reusable_process; packet=p_list_item_first_read_the_incident_report_then_extract_a_separate_child_worker_named_complianceacknowledgement_this_child_worker_is_required_by_policy_as_a_bounded_subtask

### Steps
- `step:st_1` (direct) -- spans=s5; section=sec_reusable_process; packet=p_list_item_first_read_the_incident_report_then_extract_a_separate_child_worker_named_complianceacknowledgement_this_child_worker_is_required_by_policy_as_a_bounded_subtask
- `step:st_2` (direct) -- spans=s8; section=sec_reusable_process; packet=p_list_item_main_worker_drafts_the_triage_response

### Variables
- `variable:short_triage_response` (direct) -- spans=s8; section=sec_reusable_process; packet=p_list_item_main_worker_drafts_the_triage_response

### Constraints
- `constraint:c_1` (direct) -- spans=s6; section=sec_reusable_process; packet=p_list_item_but_this_source_intentionally_does_not_specify_its_input_contract_or_output_contract_do_not_invent_those_contracts_keep_the_child_worker_definition_as_a_renderable_skeleton_with_empty_inputs_and_empty_outputs
- `constraint:c_2` (direct) -- spans=s9; section=sec_policies; packet=p_sentence_do_not_invent_missing_contract_fields
- `constraint:c_3` (direct) -- spans=s10; section=sec_policies; packet=p_sentence_do_not_convert_the_child_worker_into_a_generic_main_flow_command
- `constraint:c_4` (direct) -- spans=s11; section=sec_policies; packet=p_sentence_do_not_create_an_executable_worker_invocation_unless_the_handoff_contract_is_complete

### Other
- `profile:concept_0` (normalized)
- `profile:concept_1` (normalized)
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

- `worker:worker_main.output:completion_status`: `missing_output_producer` -- Required output 'completion_status' (Final completion status of the main worker.) has no source-backed producer step. [construct=worker:worker_main.output:completion_status, slot=producer]
  - Suggested resolution: Add a step that produces 'completion_status'. If the source requirement does not specify how to produce this output, mark it as optional or remove it from the output contract.
- `resource_contract_demand:rcd_output_s4`: `missing_output_producer` -- Resource contract output 'rcd_output_s4' (requiredness=required) has materialized resource(s) completion_status but no renderable producer. [construct=resource_contract_demand:rcd_output_s4, slot=producer]
  - Suggested resolution: Add a source-backed step or handoff that produces the materialized resource name with the same resource kind.

## 4. Diagnostics

### irs_5143c9abd16e: `missing_output_producer`
- Severity: `warning`
- Target: `worker:worker_main.output:completion_status`
- Message: Required output 'completion_status' (Final completion status of the main worker.) has no source-backed producer step. [construct=worker:worker_main.output:completion_status, slot=producer]
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Add a step that produces 'completion_status'. If the source requirement does not specify how to produce this output, mark it as optional or remove it from the output contract.
- Missing slot: `producer`
- Missing reason: Required output 'completion_status' (Final completion status of the main worker.) has no source-backed producer step.

### irs_9074dfd6c98d: `missing_output_producer`
- Severity: `warning`
- Target: `resource_contract_demand:rcd_output_s4`
- Source spans: `s4`
- Message: Resource contract output 'rcd_output_s4' (requiredness=required) has materialized resource(s) completion_status but no renderable producer. [construct=resource_contract_demand:rcd_output_s4, slot=producer]
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Add a source-backed step or handoff that produces the materialized resource name with the same resource kind.
- Missing slot: `producer`
- Missing reason: Resource contract output 'rcd_output_s4' (requiredness=required) has materialized resource(s) completion_status but no renderable producer.

### diag_prov_0000: `missing_provenance`
- Severity: `warning`
- Target: `variable:user_incident_report`
- Message: Variable 'user_incident_report' (text) is a contract input with no source-backed producer or adapter evidence.
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_prov_0001: `missing_provenance`
- Severity: `warning`
- Target: `variable:completion_status`
- Message: Variable 'completion_status' (text) is a contract output with no source-backed producer or adapter evidence.
- Blocks rendering: `false`
- Blocks completion: `false`

### arc4_annotation_missing_requiredness_s2_input_contract_requiredness: `annotation_missing_requiredness`
- Severity: `info`
- Target: `span:s2`
- Source spans: `s2`
- Message: [input_contract] requiredness: expected=required | optional | unspecified, got=None. Post-enrichment: span 's2' (input_contract) has no requiredness metadata
- Blocks rendering: `false`
- Blocks completion: `false`

### stage2_route_refinement_diagnostic_: `route_refinement_diagnostic`
- Severity: `info`
- Message: LLM route diagnostic [prior_overridden] span='s5': Structural prior suggested process_step; kept process_step because the text includes explicit instructions and worker extraction action.
- Blocks rendering: `false`
- Blocks completion: `false`

### view:resource-contract-annotation-missing-requiredness:rcd_input_s2: `resource_contract_annotation_missing_requiredness`
- Severity: `info`
- Target: `rcd_input_s2`
- Source spans: `s2`
- Message: Requiredness is unspecified for demand rcd_input_s2 (span s2).
- Blocks rendering: `false`
- Blocks completion: `false`

## 5. Assumptions / Suggestions

- `ASM_0000` for `worker:worker_main.output:completion_status`: Required output has no source-backed producer. The compiler suggests adding a step that explicitly produces this output.
  - Reason: The source requires this output but does not describe how it should be produced.  The output is kept in the OUTPUTS contract, but no producer step was rendered.
  - Suggested resolution: Add a source-backed step that produces worker:worker_main.output:completion_status. If the source does not specify how to produce it, mark it as optional or remove it from the required output contract.
  - Related diagnostic: `irs_5143c9abd16e`
- `ASM_0001` for `resource_contract_demand:rcd_output_s4`: Required output has no source-backed producer. The compiler suggests adding a step that explicitly produces this output.
  - Reason: The source requires this output but does not describe how it should be produced.  The output is kept in the OUTPUTS contract, but no producer step was rendered.
  - Suggested resolution: Add a source-backed step that produces resource_contract_demand:rcd_output_s4. If the source does not specify how to produce it, mark it as optional or remove it from the required output contract.
  - Related diagnostic: `irs_9074dfd6c98d`
- `ASM_0002` for `variable:user_incident_report`: Variable has no discoverable source provenance.
  - Reason: The compiler could not trace this variable back to a source span, adapter hard fact, or producer step.  Its origin is assumed.
  - Suggested resolution: For variable:user_incident_report: add source evidence (a span, adapter hint, or producer step) that justifies this variable's existence.
  - Related diagnostic: `diag_prov_0000`
- `ASM_0003` for `variable:completion_status`: Variable has no discoverable source provenance.
  - Reason: The compiler could not trace this variable back to a source span, adapter hard fact, or producer step.  Its origin is assumed.
  - Suggested resolution: For variable:completion_status: add source evidence (a span, adapter hint, or producer step) that justifies this variable's existence.
  - Related diagnostic: `diag_prov_0001`

## 6. Provenance / TraceRecords

- `constraint:c_1` -> `direct`
  - Source: spans=`s6`, section=`sec_reusable_process`, packet=`p_list_item_but_this_source_intentionally_does_not_specify_its_input_contract_or_output_contract_do_not_invent_those_contracts_keep_the_child_worker_definition_as_a_renderable_skeleton_with_empty_inputs_and_empty_outputs`
  - Explanation: Constraint 'c_1' (prohibition): Do not invent unspecified input or output contracts; keep the child worker defin
- `constraint:c_2` -> `direct`
  - Source: spans=`s9`, section=`sec_policies`, packet=`p_sentence_do_not_invent_missing_contract_fields`
  - Explanation: Constraint 'c_2' (prohibition): Do not invent missing contract fields.
- `constraint:c_3` -> `direct`
  - Source: spans=`s10`, section=`sec_policies`, packet=`p_sentence_do_not_convert_the_child_worker_into_a_generic_main_flow_command`
  - Explanation: Constraint 'c_3' (prohibition): Do not convert the child worker into a generic main-flow command.
- `constraint:c_4` -> `direct`
  - Source: spans=`s11`, section=`sec_policies`, packet=`p_sentence_do_not_create_an_executable_worker_invocation_unless_the_handoff_contract_is_complete`
  - Explanation: Constraint 'c_4' (prohibition): Do not create an executable worker invocation unless the handoff contract is com
- `flow:main` -> `direct`
  - Source: spans=`s5, s8`, section=`sec_reusable_process`, packet=`p_list_item_first_read_the_incident_report_then_extract_a_separate_child_worker_named_complianceacknowledgement_this_child_worker_is_required_by_policy_as_a_bounded_subtask`
  - Explanation: Main flow with 1 block(s).
- `profile:concept_0` -> `normalized`
  - Explanation: Concept: Incident-response triage workflows -- A workflow for quickly reviewing a user incident report and producing a brief triage response plus completion status.
- `profile:concept_1` -> `normalized`
  - Explanation: Concept: User incident report -- The report provided by a user describing an incident that needs to be analyzed during triage.
- `profile:concept_2` -> `normalized`
  - Explanation: Concept: Triage response -- A short response summarizing the initial assessment or handling of the incident.
- `profile:concept_3` -> `normalized`
  - Explanation: Concept: Completion status -- A final status indicator showing whether the main worker has completed its task.
- `profile:concept_4` -> `normalized`
  - Explanation: Concept: Child worker -- A separate bounded subtask worker created during processing; here it is named ComplianceAcknowledgement.
- `profile:concept_5` -> `normalized`
  - Explanation: Concept: ComplianceAcknowledgement -- The required child worker that must be extracted by policy, but whose input and output contracts are intentionally unspecified.
- `profile:concept_6` -> `normalized`
  - Explanation: Concept: Input contract -- The specification of what inputs a worker accepts.
- `profile:concept_7` -> `normalized`
  - Explanation: Concept: Output contract -- The specification of what outputs a worker must produce.
- `profile:concept_8` -> `normalized`
  - Explanation: Concept: Handoff contract -- The complete contract required before an executable worker invocation can be created.
- `profile:concept_9` -> `normalized`
  - Explanation: Concept: Invocation contract -- The contract governing a worker invocation; if incomplete, diagnostics should report that it is incomplete.
- `profile:persona` -> `inferred`
  - Explanation: Persona: Incident-response triage workflows
- `step:st_1` -> `direct`
  - Source: spans=`s5`, section=`sec_reusable_process`, packet=`p_list_item_first_read_the_incident_report_then_extract_a_separate_child_worker_named_complianceacknowledgement_this_child_worker_is_required_by_policy_as_a_bounded_subtask`
  - Explanation: Step 'st_1' maps to source span(s).
- `step:st_2` -> `direct`
  - Source: spans=`s8`, section=`sec_reusable_process`, packet=`p_list_item_main_worker_drafts_the_triage_response`
  - Explanation: Step 'st_2' maps to source span(s).
- `variable:completion_status` -> `assumed` [needs confirmation]
  - Explanation: Variable 'completion_status' is declared as worker output contract with no source evidence.
- `variable:short_triage_response` -> `direct`
  - Source: spans=`s8`, section=`sec_reusable_process`, packet=`p_list_item_main_worker_drafts_the_triage_response`
  - Explanation: Variable 'short_triage_response' is produced by source-backed step 'st_2'.
- `variable:user_incident_report` -> `assumed` [needs confirmation]
  - Explanation: Variable 'user_incident_report' is declared as worker input contract with no source evidence.
- `worker:MainWorker` -> `direct`
  - Source: spans=`s5, s7, s8`, section=`sec_reusable_process`, packet=`p_list_item_first_read_the_incident_report_then_extract_a_separate_child_worker_named_complianceacknowledgement_this_child_worker_is_required_by_policy_as_a_bounded_subtask`
  - Explanation: Main worker 'MainWorker' assembled from flow and step IRs.

## 7. Anti-Fabrication Checks

- `missing_output_producer`: Required outputs without a source-backed producer stay in the contract; no synthetic producer command is invented.
- Rendered SPL contains no executable `[INVOKE ...]` command.

## 8. Adapter / Validation Notes

No adapter or validation notes.

## 9. SPL Draft

```spl
[DEFINE_AGENT: MainWorker "Orchestrate the end-to-end process and delegate to sub-tasks."]
    [DEFINE_PERSONA:]
        ROLE: Incident-response triage workflows
        PolicyBoundProcess: Operates as a bounded, policy-driven workflow that must not invent missing contracts or executable invocations.
        ContractConstrained: Requires explicit input/output contracts for worker handoffs; incomplete contracts should be reported as diagnostics rather than filled in.
        SkeletonPreserving: Keeps the child worker definition as a renderable skeleton with empty INPUTS and OUTPUTS when contract details are absent.
    [END_PERSONA]
    [DEFINE_CONCEPTS:]
        Incidentresponsetriageworkflows: A workflow for quickly reviewing a user incident report and producing a brief triage response plus completion status.
        Userincidentreport: The report provided by a user describing an incident that needs to be analyzed during triage.
        Triageresponse: A short response summarizing the initial assessment or handling of the incident.
        Completionstatus: A final status indicator showing whether the main worker has completed its task.
        Childworker: A separate bounded subtask worker created during processing; here it is named ComplianceAcknowledgement.
        ComplianceAcknowledgement: The required child worker that must be extracted by policy, but whose input and output contracts are intentionally unspecified.
        Inputcontract: The specification of what inputs a worker accepts.
        Outputcontract: The specification of what outputs a worker must produce.
        Handoffcontract: The complete contract required before an executable worker invocation can be created.
        Invocationcontract: The contract governing a worker invocation; if incomplete, diagnostics should report that it is incomplete.
    [END_CONCEPTS]
    [DEFINE_CONSTRAINTS:]
        Prohibition: Do not invent unspecified input or output contracts; keep the child worker definition as a renderable skeleton with empty INPUTS and empty OUTPUTS.
        Prohibition: Do not invent missing contract fields.
        Prohibition: Do not convert the child worker into a generic main-flow command.
        Prohibition: Do not create an executable worker invocation unless the handoff contract is complete.
    [END_CONSTRAINTS]
    [DEFINE_VARIABLES:]
        "User-provided incident report to analyze." user_incident_report: text
        "Brief triage response produced by the main worker." short_triage_response: text
        "Final completion status of the main worker." completion_status: text
    [END_VARIABLES]
    [DEFINE_WORKER: "Orchestrate the end-to-end process and delegate to sub-tasks." MainWorker]
        [INPUTS]
            <REF>user_incident_report</REF>
        [END_INPUTS]
        [OUTPUTS]
            REQUIRED <REF>short_triage_response</REF>
            REQUIRED <REF>completion_status</REF>
        [END_OUTPUTS]
        [MAIN_FLOW]
            [SEQUENTIAL_BLOCK]
                COMMAND-1 [COMMAND Read the incident report based on <REF>user_incident_report</REF>]
                COMMAND-2 [COMMAND Draft the triage response based on <REF>user_incident_report</REF> RESULT short_triage_response: text SET]
            [END_SEQUENTIAL_BLOCK]
        [END_MAIN_FLOW]
    [END_WORKER]
[END_AGENT]
```
