# NL2SPL Feedback Report

## 1. Overall Compile State

- Completeness: `partial`
- SPL draft generated: `yes`
- Compile diagnostics: `14`
- Assumptions / suggestions: `8`
- Trace records: `25`
- Adapter warnings: `0`
- Validation errors: `0`
- Validation warnings: `0`

Result is partial because the following requirement gaps remain:
- `missing_output_producer` on `resource_contract_demand:rcd_output_s5`: Resource contract output 'rcd_output_s5' (requiredness=required) has materialized resource(s) evidence_summary but no renderable producer. [construct=resource_contract_demand:rcd_output_s5, slot=producer]
- `missing_output_producer` on `worker:worker_main.output:completion_status`: Required output 'completion_status' (The final completion status of the workflow.) has no source-backed producer step. [construct=worker:worker_main.output:completion_status, slot=producer]
- `missing_output_producer` on `worker:worker_main.output:evidence_summary`: Required output 'evidence_summary' (A summary of the evidence collected for the incident.) has no source-backed producer step. [construct=worker:worker_main.output:evidence_summary, slot=producer]
- `missing_output_producer` on `resource_contract_demand:rcd_output_s6`: Resource contract output 'rcd_output_s6' (requiredness=required) has materialized resource(s) completion_status but no renderable producer. [construct=resource_contract_demand:rcd_output_s6, slot=producer]

## 2. Materialized Source-Backed Structure

### Workers
- `worker:MainWorker` (direct) -- spans=s7, s8, s9, s10, s11, s12, s13, s14a, s15a, s16; section=sec_reusable_process; packet=p_sentence_first_read_the_incident_report_and_identify_which_facts_require_support

### Flows
- `flow:main` (direct) -- spans=s7, s16; section=sec_reusable_process; packet=p_sentence_first_read_the_incident_report_and_identify_which_facts_require_support

### Steps
- `step:st_1` (direct) -- spans=s7; section=sec_reusable_process; packet=p_sentence_first_read_the_incident_report_and_identify_which_facts_require_support
- `step:st_2` (direct) -- spans=s16; section=sec_an_independently_reusable_source_gathering_lifecycle; packet=p_list_item_main_worker_drafts_the_triage_response_from_available_information

### Variables
- `variable:short_triage_response` (direct) -- spans=s16; section=sec_an_independently_reusable_source_gathering_lifecycle; packet=p_list_item_main_worker_drafts_the_triage_response_from_available_information

### Constraints
- `constraint:c_1` (direct) -- spans=s17; section=sec_policies; packet=p_sentence_evidence_retrieval_must_remain_a_bounded_child_worker_because_it_is_reusable_and_has_its_own_provenance_responsibility
- `constraint:c_2` (direct) -- spans=s18; section=sec_policies; packet=p_sentence_do_not_convert_it_into_a_generic_main_flow_command
- `constraint:c_3` (direct) -- spans=s19; section=sec_policies; packet=p_sentence_do_not_invent_missing_contract_fields
- `constraint:c_4` (direct) -- spans=s20; section=sec_policies; packet=p_sentence_do_not_create_an_executable_worker_invocation_unless_the_handoff_contract_is_complete
- `constraint:c_5` (direct) -- spans=s14b; section=sec_an_independently_reusable_source_gathering_lifecycle; packet=p_list_item_return_control_to_the_main_worker_for_triage_drafting_the_source_intentionally_does_not_specify_the_child_worker_input_contract_or_output_contract_do_not_invent_those_contracts_keep_the_child_worker_definition_as_a_renderable_skeleton_with_empty_inputs_and_empty_outputs
- `constraint:c_6` (direct) -- spans=s15b; section=sec_an_independently_reusable_source_gathering_lifecycle; packet=p_list_item_let_diagnostics_report_that_the_invocation_contract_is_incomplete_after_the_child_worker_definition_exists

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
- `profile:persona` (inferred)

## 3. Not Materialized / Kept Partial

- `resource_contract_demand:rcd_output_s5`: `missing_output_producer` -- Resource contract output 'rcd_output_s5' (requiredness=required) has materialized resource(s) evidence_summary but no renderable producer. [construct=resource_contract_demand:rcd_output_s5, slot=producer]
  - Suggested resolution: Add a source-backed step or handoff that produces the materialized resource name with the same resource kind.
- `worker:worker_main.output:completion_status`: `missing_output_producer` -- Required output 'completion_status' (The final completion status of the workflow.) has no source-backed producer step. [construct=worker:worker_main.output:completion_status, slot=producer]
  - Suggested resolution: Add a step that produces 'completion_status'. If the source requirement does not specify how to produce this output, mark it as optional or remove it from the output contract.
- `worker:worker_main.output:evidence_summary`: `missing_output_producer` -- Required output 'evidence_summary' (A summary of the evidence collected for the incident.) has no source-backed producer step. [construct=worker:worker_main.output:evidence_summary, slot=producer]
  - Suggested resolution: Add a step that produces 'evidence_summary'. If the source requirement does not specify how to produce this output, mark it as optional or remove it from the output contract.
- `resource_contract_demand:rcd_output_s6`: `missing_output_producer` -- Resource contract output 'rcd_output_s6' (requiredness=required) has materialized resource(s) completion_status but no renderable producer. [construct=resource_contract_demand:rcd_output_s6, slot=producer]
  - Suggested resolution: Add a source-backed step or handoff that produces the materialized resource name with the same resource kind.

## 4. Diagnostics

### irs_39f8865b7fc7: `missing_output_producer`
- Severity: `warning`
- Target: `resource_contract_demand:rcd_output_s5`
- Source spans: `s5`
- Message: Resource contract output 'rcd_output_s5' (requiredness=required) has materialized resource(s) evidence_summary but no renderable producer. [construct=resource_contract_demand:rcd_output_s5, slot=producer]
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Add a source-backed step or handoff that produces the materialized resource name with the same resource kind.
- Missing slot: `producer`
- Missing reason: Resource contract output 'rcd_output_s5' (requiredness=required) has materialized resource(s) evidence_summary but no renderable producer.

### irs_5143c9abd16e: `missing_output_producer`
- Severity: `warning`
- Target: `worker:worker_main.output:completion_status`
- Message: Required output 'completion_status' (The final completion status of the workflow.) has no source-backed producer step. [construct=worker:worker_main.output:completion_status, slot=producer]
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Add a step that produces 'completion_status'. If the source requirement does not specify how to produce this output, mark it as optional or remove it from the output contract.
- Missing slot: `producer`
- Missing reason: Required output 'completion_status' (The final completion status of the workflow.) has no source-backed producer step.

### irs_750738a4dbce: `missing_output_producer`
- Severity: `warning`
- Target: `worker:worker_main.output:evidence_summary`
- Message: Required output 'evidence_summary' (A summary of the evidence collected for the incident.) has no source-backed producer step. [construct=worker:worker_main.output:evidence_summary, slot=producer]
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Add a step that produces 'evidence_summary'. If the source requirement does not specify how to produce this output, mark it as optional or remove it from the output contract.
- Missing slot: `producer`
- Missing reason: Required output 'evidence_summary' (A summary of the evidence collected for the incident.) has no source-backed producer step.

### irs_e3b277547492: `missing_output_producer`
- Severity: `warning`
- Target: `resource_contract_demand:rcd_output_s6`
- Source spans: `s6`
- Message: Resource contract output 'rcd_output_s6' (requiredness=required) has materialized resource(s) completion_status but no renderable producer. [construct=resource_contract_demand:rcd_output_s6, slot=producer]
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Add a source-backed step or handoff that produces the materialized resource name with the same resource kind.
- Missing slot: `producer`
- Missing reason: Resource contract output 'rcd_output_s6' (requiredness=required) has materialized resource(s) completion_status but no renderable producer.

### diag_prov_0000: `missing_provenance`
- Severity: `warning`
- Target: `variable:user_incident_report`
- Message: Variable 'user_incident_report' (text) is a contract input with no source-backed producer or adapter evidence.
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_prov_0001: `missing_provenance`
- Severity: `warning`
- Target: `variable:approved_evidence_repositories`
- Message: Variable 'approved_evidence_repositories' (List[text]) is a contract input with no source-backed producer or adapter evidence.
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_prov_0002: `missing_provenance`
- Severity: `warning`
- Target: `variable:evidence_summary`
- Message: Variable 'evidence_summary' (text) is a contract output with no source-backed producer or adapter evidence.
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_prov_0003: `missing_provenance`
- Severity: `warning`
- Target: `variable:completion_status`
- Message: Variable 'completion_status' (text) is a contract output with no source-backed producer or adapter evidence.
- Blocks rendering: `false`
- Blocks completion: `false`

### stage2_route_refinement_conflict_s14: `route_refinement_conflict`
- Severity: `info`
- Target: `span:s14`
- Source spans: `s14`
- Message: route_refinement_conflict: span 's14' has both executable and non-executable annotations with populated semantic roles
- Blocks rendering: `false`
- Blocks completion: `false`

### stage2_route_refinement_conflict_s15: `route_refinement_conflict`
- Severity: `info`
- Target: `span:s15`
- Source spans: `s15`
- Message: route_refinement_conflict: span 's15' has both executable and non-executable annotations with populated semantic roles
- Blocks rendering: `false`
- Blocks completion: `false`

### stage2_route_refinement_conflict_s8: `route_refinement_conflict`
- Severity: `info`
- Target: `span:s8`
- Source spans: `s8`
- Message: route_refinement_conflict: span 's8' has both executable and non-executable annotations with populated semantic roles
- Blocks rendering: `false`
- Blocks completion: `false`

### stage2_route_refinement_diagnostic_: `route_refinement_diagnostic`
- Severity: `info`
- Message: Split segment warning: segment text 'The source intentionally does not specify the child worker i' not found in parent span text 'return control to the main worker for triage drafting.
The s' for parent 's14'
- Blocks rendering: `false`
- Blocks completion: `false`

### stage2_route_refinement_split_s14: `route_refinement_split`
- Severity: `info`
- Target: `span:s14`
- Source spans: `s14`
- Message: Split recommended for s14: The span mixes a process instruction with explicit constraints about contracts and skeleton structure.
- Blocks rendering: `false`
- Blocks completion: `false`

### stage2_route_refinement_split_s15: `route_refinement_split`
- Severity: `info`
- Target: `span:s15`
- Source spans: `s15`
- Message: Split recommended for s15: The span mixes a diagnostic/reporting instruction with a completion condition.
- Blocks rendering: `false`
- Blocks completion: `false`

## 5. Assumptions / Suggestions

- `ASM_0000` for `worker:worker_main.output:evidence_summary`: Required output has no source-backed producer. The compiler suggests adding a step that explicitly produces this output.
  - Reason: The source requires this output but does not describe how it should be produced.  The output is kept in the OUTPUTS contract, but no producer step was rendered.
  - Suggested resolution: Add a source-backed step that produces worker:worker_main.output:evidence_summary. If the source does not specify how to produce it, mark it as optional or remove it from the required output contract.
  - Related diagnostic: `irs_750738a4dbce`
- `ASM_0001` for `worker:worker_main.output:completion_status`: Required output has no source-backed producer. The compiler suggests adding a step that explicitly produces this output.
  - Reason: The source requires this output but does not describe how it should be produced.  The output is kept in the OUTPUTS contract, but no producer step was rendered.
  - Suggested resolution: Add a source-backed step that produces worker:worker_main.output:completion_status. If the source does not specify how to produce it, mark it as optional or remove it from the required output contract.
  - Related diagnostic: `irs_5143c9abd16e`
- `ASM_0002` for `resource_contract_demand:rcd_output_s5`: Required output has no source-backed producer. The compiler suggests adding a step that explicitly produces this output.
  - Reason: The source requires this output but does not describe how it should be produced.  The output is kept in the OUTPUTS contract, but no producer step was rendered.
  - Suggested resolution: Add a source-backed step that produces resource_contract_demand:rcd_output_s5. If the source does not specify how to produce it, mark it as optional or remove it from the required output contract.
  - Related diagnostic: `irs_39f8865b7fc7`
- `ASM_0003` for `resource_contract_demand:rcd_output_s6`: Required output has no source-backed producer. The compiler suggests adding a step that explicitly produces this output.
  - Reason: The source requires this output but does not describe how it should be produced.  The output is kept in the OUTPUTS contract, but no producer step was rendered.
  - Suggested resolution: Add a source-backed step that produces resource_contract_demand:rcd_output_s6. If the source does not specify how to produce it, mark it as optional or remove it from the required output contract.
  - Related diagnostic: `irs_e3b277547492`
- `ASM_0004` for `variable:user_incident_report`: Variable has no discoverable source provenance.
  - Reason: The compiler could not trace this variable back to a source span, adapter hard fact, or producer step.  Its origin is assumed.
  - Suggested resolution: For variable:user_incident_report: add source evidence (a span, adapter hint, or producer step) that justifies this variable's existence.
  - Related diagnostic: `diag_prov_0000`
- `ASM_0005` for `variable:approved_evidence_repositories`: Variable has no discoverable source provenance.
  - Reason: The compiler could not trace this variable back to a source span, adapter hard fact, or producer step.  Its origin is assumed.
  - Suggested resolution: For variable:approved_evidence_repositories: add source evidence (a span, adapter hint, or producer step) that justifies this variable's existence.
  - Related diagnostic: `diag_prov_0001`
- `ASM_0006` for `variable:evidence_summary`: Variable has no discoverable source provenance.
  - Reason: The compiler could not trace this variable back to a source span, adapter hard fact, or producer step.  Its origin is assumed.
  - Suggested resolution: For variable:evidence_summary: add source evidence (a span, adapter hint, or producer step) that justifies this variable's existence.
  - Related diagnostic: `diag_prov_0002`
- `ASM_0007` for `variable:completion_status`: Variable has no discoverable source provenance.
  - Reason: The compiler could not trace this variable back to a source span, adapter hard fact, or producer step.  Its origin is assumed.
  - Suggested resolution: For variable:completion_status: add source evidence (a span, adapter hint, or producer step) that justifies this variable's existence.
  - Related diagnostic: `diag_prov_0003`

## 6. Provenance / TraceRecords

- `constraint:c_1` -> `direct`
  - Source: spans=`s17`, section=`sec_policies`, packet=`p_sentence_evidence_retrieval_must_remain_a_bounded_child_worker_because_it_is_reusable_and_has_its_own_provenance_responsibility`
  - Explanation: Constraint 'c_1' (delegation_boundary): Evidence retrieval must remain a bounded child worker because it is reusable and
- `constraint:c_2` -> `direct`
  - Source: spans=`s18`, section=`sec_policies`, packet=`p_sentence_do_not_convert_it_into_a_generic_main_flow_command`
  - Explanation: Constraint 'c_2' (prohibition): Do not convert evidence retrieval into a generic main-flow command.
- `constraint:c_3` -> `direct`
  - Source: spans=`s19`, section=`sec_policies`, packet=`p_sentence_do_not_invent_missing_contract_fields`
  - Explanation: Constraint 'c_3' (prohibition): Do not invent missing contract fields.
- `constraint:c_4` -> `direct`
  - Source: spans=`s20`, section=`sec_policies`, packet=`p_sentence_do_not_create_an_executable_worker_invocation_unless_the_handoff_contract_is_complete`
  - Explanation: Constraint 'c_4' (gate): Do not create an executable worker invocation unless the handoff contract is com
- `constraint:c_5` -> `direct`
  - Source: spans=`s14b`, section=`sec_an_independently_reusable_source_gathering_lifecycle`, packet=`p_list_item_return_control_to_the_main_worker_for_triage_drafting_the_source_intentionally_does_not_specify_the_child_worker_input_contract_or_output_contract_do_not_invent_those_contracts_keep_the_child_worker_definition_as_a_renderable_skeleton_with_empty_inputs_and_empty_outputs`
  - Explanation: Constraint 'c_5' (prohibition): Do not invent the child worker input contract or output contract; keep the child
- `constraint:c_6` -> `direct`
  - Source: spans=`s15b`, section=`sec_an_independently_reusable_source_gathering_lifecycle`, packet=`p_list_item_let_diagnostics_report_that_the_invocation_contract_is_incomplete_after_the_child_worker_definition_exists`
  - Explanation: Constraint 'c_6' (requirement): After the child worker definition exists, diagnostics may report that the invoca
- `flow:main` -> `direct`
  - Source: spans=`s7, s16`, section=`sec_reusable_process`, packet=`p_sentence_first_read_the_incident_report_and_identify_which_facts_require_support`
  - Explanation: Main flow with 1 block(s).
- `profile:concept_0` -> `normalized`
  - Explanation: Concept: Incident-response investigation workflows -- A workflow family for investigating user incidents, identifying facts that need support, retrieving evidence, and drafting a triage response.
- `profile:concept_1` -> `normalized`
  - Explanation: Concept: User incident report -- A report provided by the user that describes the incident and serves as the starting input for investigation.
- `profile:concept_2` -> `normalized`
  - Explanation: Concept: Approved evidence repositories -- An approved set of repositories that may be queried to find supporting evidence.
- `profile:concept_3` -> `normalized`
  - Explanation: Concept: Triage response -- A short response drafted from available information to summarize the incident's initial handling.
- `profile:concept_4` -> `normalized`
  - Explanation: Concept: Evidence summary -- A summary of the evidence collected during the investigation.
- `profile:concept_5` -> `normalized`
  - Explanation: Concept: Completion status -- The final status indicating whether the workflow has completed.
- `profile:concept_6` -> `normalized`
  - Explanation: Concept: EvidenceRetrievalWorker -- A separate child worker responsible for querying approved evidence repositories, collecting matching evidence, normalizing provenance, and discarding unsupported claims.
- `profile:concept_7` -> `normalized`
  - Explanation: Concept: Provenance -- The source and traceability information associated with collected evidence.
- `profile:concept_8` -> `normalized`
  - Explanation: Concept: Handoff contract -- The defined input/output contract required before a worker invocation can be executed.
- `profile:persona` -> `inferred`
  - Explanation: Persona: Incident-response investigation workflow
- `step:st_1` -> `direct`
  - Source: spans=`s7`, section=`sec_reusable_process`, packet=`p_sentence_first_read_the_incident_report_and_identify_which_facts_require_support`
  - Explanation: Step 'st_1' maps to source span(s).
- `step:st_2` -> `direct`
  - Source: spans=`s16`, section=`sec_an_independently_reusable_source_gathering_lifecycle`, packet=`p_list_item_main_worker_drafts_the_triage_response_from_available_information`
  - Explanation: Step 'st_2' maps to source span(s).
- `variable:approved_evidence_repositories` -> `assumed` [needs confirmation]
  - Explanation: Variable 'approved_evidence_repositories' is declared as worker input contract with no source evidence.
- `variable:completion_status` -> `assumed` [needs confirmation]
  - Explanation: Variable 'completion_status' is declared as worker output contract with no source evidence.
- `variable:evidence_summary` -> `assumed` [needs confirmation]
  - Explanation: Variable 'evidence_summary' is declared as worker output contract with no source evidence.
- `variable:short_triage_response` -> `direct`
  - Source: spans=`s16`, section=`sec_an_independently_reusable_source_gathering_lifecycle`, packet=`p_list_item_main_worker_drafts_the_triage_response_from_available_information`
  - Explanation: Variable 'short_triage_response' is produced by source-backed step 'st_2'.
- `variable:user_incident_report` -> `assumed` [needs confirmation]
  - Explanation: Variable 'user_incident_report' is declared as worker input contract with no source evidence.
- `worker:MainWorker` -> `direct`
  - Source: spans=`s7, s8, s9, s10, s11, s12, s13, s14a, s15a, s16`, section=`sec_reusable_process`, packet=`p_sentence_first_read_the_incident_report_and_identify_which_facts_require_support`
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
        ROLE: Incident-response investigation workflow
        BoundedChildWorker: Uses a separate child worker for evidence retrieval rather than turning it into a generic main-flow command.
        ProvenanceFocused: Has explicit responsibility for normalizing provenance and discarding unsupported claims.
        ContractDisciplined: Does not invent missing contract fields and only creates executable worker invocations when the handoff contract is complete.
    [END_PERSONA]
    [DEFINE_CONCEPTS:]
        Incidentresponseinvestigationworkflows: A workflow family for investigating user incidents, identifying facts that need support, retrieving evidence, and drafting a triage response.
        Userincidentreport: A report provided by the user that describes the incident and serves as the starting input for investigation.
        Approvedevidencerepositories: An approved set of repositories that may be queried to find supporting evidence.
        Triageresponse: A short response drafted from available information to summarize the incident's initial handling.
        Evidencesummary: A summary of the evidence collected during the investigation.
        Completionstatus: The final status indicating whether the workflow has completed.
        EvidenceRetrievalWorker: A separate child worker responsible for querying approved evidence repositories, collecting matching evidence, normalizing provenance, and discarding unsupported claims.
        Provenance: The source and traceability information associated with collected evidence.
        Handoffcontract: The defined input/output contract required before a worker invocation can be executed.
    [END_CONCEPTS]
    [DEFINE_CONSTRAINTS:]
        DelegationBoundary: Evidence retrieval must remain a bounded child worker because it is reusable and has its own provenance responsibility.
        Prohibition: Do not convert evidence retrieval into a generic main-flow command.
        Prohibition: Do not invent missing contract fields.
        Gate: Do not create an executable worker invocation unless the handoff contract is complete.
        Prohibition: Do not invent the child worker input contract or output contract; keep the child worker definition as a renderable skeleton with empty INPUTS and empty OUTPUTS.
        Requirement: After the child worker definition exists, diagnostics may report that the invocation contract is incomplete.
    [END_CONSTRAINTS]
    [DEFINE_VARIABLES:]
        "A user-provided incident report." user_incident_report: text
        "A list of approved evidence repositories." approved_evidence_repositories: List [text]
        "A brief triage response drafted from available information." short_triage_response: text
        "A summary of the evidence collected for the incident." evidence_summary: text
        "The final completion status of the workflow." completion_status: text
    [END_VARIABLES]
    [DEFINE_WORKER: "Orchestrate the end-to-end process and delegate to sub-tasks." MainWorker]
        [INPUTS]
            REQUIRED <REF>user_incident_report</REF>
            REQUIRED <REF>approved_evidence_repositories</REF>
        [END_INPUTS]
        [OUTPUTS]
            REQUIRED <REF>short_triage_response</REF>
            REQUIRED <REF>evidence_summary</REF>
            REQUIRED <REF>completion_status</REF>
        [END_OUTPUTS]
        [MAIN_FLOW]
            [SEQUENTIAL_BLOCK]
                COMMAND-1 [COMMAND Review the incident report and identify facts requiring support based on <REF>user_incident_report</REF>]
                COMMAND-2 [COMMAND Draft the triage response from available information RESULT short_triage_response: text SET]
            [END_SEQUENTIAL_BLOCK]
        [END_MAIN_FLOW]
    [END_WORKER]
[END_AGENT]
```
