# NL2SPL Feedback Report

## 1. Overall Compile State

- Completeness: `partial`
- SPL draft generated: `yes`
- Compile diagnostics: `9`
- Assumptions / suggestions: `9`
- Trace records: `27`
- Adapter warnings: `0`
- Validation errors: `0`
- Validation warnings: `10`

Result is partial because the following requirement gaps remain:
- `missing_handler` on `worker:worker_main.exception_flow:exc_adapter_01`: Exception flow 'exc_adapter_01' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_01, slot=handler_action]
- `missing_handler` on `worker:worker_main.exception_flow:exc_adapter_00`: Exception flow 'exc_adapter_00' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_00, slot=handler_action]
- `missing_handler` on `worker:worker_main.exception_flow:exc_adapter_02`: Exception flow 'exc_adapter_02' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_02, slot=handler_action]
- `missing_output_producer` on `resource_contract_demand:rcd_output_s11`: Required resource contract output 'rcd_output_s11' has materialized resource(s) finished_draft but no renderable producer of the matching resource kind. [construct=resource_contract_demand:rcd_output_s11, slot=producer]
- `type_or_contract_ambiguity` on `delegation_intent:s22`: Delegation intent lacks a valid worker/API handoff contract. No INVOKE_WORKER or CALL_API will be generated from this span. [construct=delegation_intent:s22, slot=handoff_contract]

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
- `variable:status_flag` (direct) -- spans=s15; section=sec_reusable_process; packet=p_list_item_routes_to_the_relevant_communications_lead_for_review
- `variable:worker_main_st_1_result_structured` (direct) -- spans=s13; section=sec_reusable_process; packet=p_list_item_requestor_provides_topic_audience
- `variable:worker_main_st_2_result_structured` (direct) -- spans=s14; section=sec_reusable_process; packet=p_list_item_ic_writer_drafts_using_the_standard_internal_communications_template_appendix_a_of_the_style_guide

### Constraints
- `constraint:c_1` (direct) -- spans=s16; section=sec_policies; packet=p_list_item_must_use_the_approved_template
- `constraint:c_2` (direct) -- spans=s17; section=sec_policies; packet=p_list_item_must_follow_plain_language_and_inclusive_tone_guidelines
- `constraint:c_3` (direct) -- spans=s18, s23; section=sec_policies; packet=p_list_item_require_final_sign_off_from_the_communications_lead_before_flagging_as_approved

### Other
- `profile:concept_0` (normalized)
- `profile:concept_1` (normalized)
- `profile:concept_2` (normalized)
- `profile:concept_3` (normalized)
- `profile:concept_4` (normalized)
- `profile:concept_5` (normalized)
- `profile:concept_6` (normalized)
- `profile:concept_7` (normalized)
- `profile:persona` (inferred)

## 3. Not Materialized / Kept Partial

- `worker:worker_main.exception_flow:exc_adapter_01`: `missing_handler` -- Exception flow 'exc_adapter_01' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_01, slot=handler_action]
  - Suggested resolution: Add a handler step for 'Template unavailable', or mark this exception as acknowledged without handling.
- `worker:worker_main.exception_flow:exc_adapter_00`: `missing_handler` -- Exception flow 'exc_adapter_00' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_00, slot=handler_action]
  - Suggested resolution: Add a handler step for 'Communications lead unresponsive for over two days', or mark this exception as acknowledged without handling.
- `worker:worker_main.exception_flow:exc_adapter_02`: `missing_handler` -- Exception flow 'exc_adapter_02' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_02, slot=handler_action]
  - Suggested resolution: Add a handler step for 'Topic summary too vague to draft from', or mark this exception as acknowledged without handling.
- `resource_contract_demand:rcd_output_s11`: `missing_output_producer` -- Required resource contract output 'rcd_output_s11' has materialized resource(s) finished_draft but no renderable producer of the matching resource kind. [construct=resource_contract_demand:rcd_output_s11, slot=producer]
  - Suggested resolution: Add a source-backed step or handoff that produces the materialized resource name with the same resource kind.
- `delegation_intent:s22`: `type_or_contract_ambiguity` -- Delegation intent lacks a valid worker/API handoff contract. No INVOKE_WORKER or CALL_API will be generated from this span. [construct=delegation_intent:s22, slot=handoff_contract]
  - Suggested resolution: Provide a valid worker/API handoff contract with input/output/API bindings covering this delegation span.

## 4. Diagnostics

### irs_38cc1fbf4aa1: `missing_handler`
- Severity: `warning`
- Target: `worker:worker_main.exception_flow:exc_adapter_01`
- Source spans: `s20`
- Message: Exception flow 'exc_adapter_01' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_01, slot=handler_action]
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Add a handler step for 'Template unavailable', or mark this exception as acknowledged without handling.
- Missing slot: `handler_action`
- Missing reason: Exception flow 'exc_adapter_01' has condition but no handler step.

### irs_6c75ca545d04: `missing_handler`
- Severity: `warning`
- Target: `worker:worker_main.exception_flow:exc_adapter_00`
- Source spans: `s21`
- Message: Exception flow 'exc_adapter_00' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_00, slot=handler_action]
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Add a handler step for 'Communications lead unresponsive for over two days', or mark this exception as acknowledged without handling.
- Missing slot: `handler_action`
- Missing reason: Exception flow 'exc_adapter_00' has condition but no handler step.

### irs_b8f9448384d5: `missing_handler`
- Severity: `warning`
- Target: `worker:worker_main.exception_flow:exc_adapter_02`
- Source spans: `s19`
- Message: Exception flow 'exc_adapter_02' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adapter_02, slot=handler_action]
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Add a handler step for 'Topic summary too vague to draft from', or mark this exception as acknowledged without handling.
- Missing slot: `handler_action`
- Missing reason: Exception flow 'exc_adapter_02' has condition but no handler step.

### irs_b9b0a6118031: `missing_output_producer`
- Severity: `warning`
- Target: `resource_contract_demand:rcd_output_s11`
- Source spans: `s11`
- Message: Required resource contract output 'rcd_output_s11' has materialized resource(s) finished_draft but no renderable producer of the matching resource kind. [construct=resource_contract_demand:rcd_output_s11, slot=producer]
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Add a source-backed step or handoff that produces the materialized resource name with the same resource kind.
- Missing slot: `producer`
- Missing reason: Required resource contract output 'rcd_output_s11' has materialized resource(s) finished_draft but no renderable producer of the matching resource kind.

### irs_4f2130b27479: `type_or_contract_ambiguity`
- Severity: `warning`
- Target: `delegation_intent:s22`
- Source spans: `s22`
- Message: Delegation intent lacks a valid worker/API handoff contract. No INVOKE_WORKER or CALL_API will be generated from this span. [construct=delegation_intent:s22, slot=handoff_contract]
- Blocks rendering: `false`
- Blocks completion: `true`
- Suggested resolution: Provide a valid worker/API handoff contract with input/output/API bindings covering this delegation span.
- Missing slot: `handoff_contract`
- Missing reason: Delegation intent lacks a valid worker/API handoff contract. No INVOKE_WORKER or CALL_API will be generated from this span.

### diag_prov_0000: `missing_provenance`
- Severity: `warning`
- Target: `variable:key_dates_or_deadlines`
- Message: Variable 'key_dates_or_deadlines' (List[text]) is a contract input with no source-backed producer or adapter evidence.
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_prov_0001: `missing_provenance`
- Severity: `warning`
- Target: `variable:topic_summary`
- Message: Variable 'topic_summary' (text) is a contract input with no source-backed producer or adapter evidence.
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_prov_0002: `missing_provenance`
- Severity: `warning`
- Target: `variable:target_audience`
- Message: Variable 'target_audience' (text) is a contract input with no source-backed producer or adapter evidence.
- Blocks rendering: `false`
- Blocks completion: `false`

### diag_prov_0003: `missing_provenance`
- Severity: `warning`
- Target: `variable:finished_draft`
- Message: Variable 'finished_draft' (text) is a contract output with no source-backed producer or adapter evidence.
- Blocks rendering: `false`
- Blocks completion: `false`

## 5. Assumptions / Suggestions

- `ASM_0000` for `worker:worker_main.exception_flow:exc_adapter_00`: Exception flow has no handler action. The compiler suggests specifying what should happen when this failure occurs.
  - Reason: Source describes a failure condition but does not specify how to handle it.  The exception flow is preserved in SPL, but no handler command was rendered. (Exception flow 'exc_adapter_00' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adap)
  - Suggested resolution: Specify the handler action for worker:worker_main.exception_flow:exc_adapter_00: e.g. ask the user for missing information, block finalization, or continue with an explicit assumption.
  - Related diagnostic: `irs_6c75ca545d04`
- `ASM_0001` for `worker:worker_main.exception_flow:exc_adapter_01`: Exception flow has no handler action. The compiler suggests specifying what should happen when this failure occurs.
  - Reason: Source describes a failure condition but does not specify how to handle it.  The exception flow is preserved in SPL, but no handler command was rendered. (Exception flow 'exc_adapter_01' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adap)
  - Suggested resolution: Specify the handler action for worker:worker_main.exception_flow:exc_adapter_01: e.g. ask the user for missing information, block finalization, or continue with an explicit assumption.
  - Related diagnostic: `irs_38cc1fbf4aa1`
- `ASM_0002` for `worker:worker_main.exception_flow:exc_adapter_02`: Exception flow has no handler action. The compiler suggests specifying what should happen when this failure occurs.
  - Reason: Source describes a failure condition but does not specify how to handle it.  The exception flow is preserved in SPL, but no handler command was rendered. (Exception flow 'exc_adapter_02' has condition but no handler step. [construct=worker:worker_main.exception_flow:exc_adap)
  - Suggested resolution: Specify the handler action for worker:worker_main.exception_flow:exc_adapter_02: e.g. ask the user for missing information, block finalization, or continue with an explicit assumption.
  - Related diagnostic: `irs_b8f9448384d5`
- `ASM_0003` for `resource_contract_demand:rcd_output_s11`: Required output has no source-backed producer. The compiler suggests adding a step that explicitly produces this output.
  - Reason: The source requires this output but does not describe how it should be produced.  The output is kept in the OUTPUTS contract, but no producer step was rendered.
  - Suggested resolution: Add a source-backed step that produces resource_contract_demand:rcd_output_s11. If the source does not specify how to produce it, mark it as optional or remove it from the required output contract.
  - Related diagnostic: `irs_b9b0a6118031`
- `ASM_0004` for `variable:key_dates_or_deadlines`: Variable has no discoverable source provenance.
  - Reason: The compiler could not trace this variable back to a source span, adapter hard fact, or producer step.  Its origin is assumed.
  - Suggested resolution: For variable:key_dates_or_deadlines: add source evidence (a span, adapter hint, or producer step) that justifies this variable's existence.
  - Related diagnostic: `diag_prov_0000`
- `ASM_0005` for `variable:topic_summary`: Variable has no discoverable source provenance.
  - Reason: The compiler could not trace this variable back to a source span, adapter hard fact, or producer step.  Its origin is assumed.
  - Suggested resolution: For variable:topic_summary: add source evidence (a span, adapter hint, or producer step) that justifies this variable's existence.
  - Related diagnostic: `diag_prov_0001`
- `ASM_0006` for `variable:target_audience`: Variable has no discoverable source provenance.
  - Reason: The compiler could not trace this variable back to a source span, adapter hard fact, or producer step.  Its origin is assumed.
  - Suggested resolution: For variable:target_audience: add source evidence (a span, adapter hint, or producer step) that justifies this variable's existence.
  - Related diagnostic: `diag_prov_0002`
- `ASM_0007` for `variable:finished_draft`: Variable has no discoverable source provenance.
  - Reason: The compiler could not trace this variable back to a source span, adapter hard fact, or producer step.  Its origin is assumed.
  - Suggested resolution: For variable:finished_draft: add source evidence (a span, adapter hint, or producer step) that justifies this variable's existence.
  - Related diagnostic: `diag_prov_0003`
- `ASM_0008` for `delegation_intent:s22`: Command has an ambiguous or incomplete contract. The compiler suggests providing the missing contract detail.
  - Reason: A command references an API, worker, or input source that is not fully specified.  The compiler cannot materialize the command without this information.
  - Suggested resolution: For delegation_intent:s22: provide the missing contract detail (API name, worker target, IO bindings, or source evidence).  See the related diagnostic for specifics.
  - Related diagnostic: `irs_4f2130b27479`

## 6. Provenance / TraceRecords

- `constraint:c_1` -> `direct`
  - Source: spans=`s16`, section=`sec_policies`, packet=`p_list_item_must_use_the_approved_template`
  - Explanation: Constraint 'c_1' (requirement): Must use the approved template
- `constraint:c_2` -> `direct`
  - Source: spans=`s17`, section=`sec_policies`, packet=`p_list_item_must_follow_plain_language_and_inclusive_tone_guidelines`
  - Explanation: Constraint 'c_2' (requirement): Must follow plain-language and inclusive tone guidelines
- `constraint:c_3` -> `direct`
  - Source: spans=`s18, s23`, section=`sec_policies`, packet=`p_list_item_require_final_sign_off_from_the_communications_lead_before_flagging_as_approved`
  - Explanation: Constraint 'c_3' (gate): Require final sign-off from the communications lead before flagging the draft as
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
  - Explanation: Concept: Internal Communications Drafting -- The task family of creating internal organizational content such as newsletters, announcements, digests, and executive briefs.
- `profile:concept_1` -> `normalized`
  - Explanation: Concept: Recurring Digests -- Regularly scheduled summary updates compiled for internal audiences.
- `profile:concept_2` -> `normalized`
  - Explanation: Concept: Executive Memos -- Formal internal messages intended for executives.
- `profile:concept_3` -> `normalized`
  - Explanation: Concept: Crisis Communications -- Emergency or incident-related communications that are explicitly outside the scope of this drafting task.
- `profile:concept_4` -> `normalized`
  - Explanation: Concept: Internal-Communications Artifacts -- Documents or communication outputs produced as part of internal communications work.
- `profile:concept_5` -> `normalized`
  - Explanation: Concept: Approved Template -- The required standard format that must be used when drafting internal communications.
- `profile:concept_6` -> `normalized`
  - Explanation: Concept: Communications Lead -- The reviewer responsible for final review and approval of the draft.
- `profile:concept_7` -> `normalized`
  - Explanation: Concept: Status Flag -- A label indicating draft state, with allowed values such as drafting, ready for review, and approved.
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
- `variable:finished_draft` -> `assumed` [needs confirmation]
  - Explanation: Variable 'finished_draft' is declared as worker output contract with no source evidence.
- `variable:key_dates_or_deadlines` -> `assumed` [needs confirmation]
  - Explanation: Variable 'key_dates_or_deadlines' is declared as worker input contract with no source evidence.
- `variable:status_flag` -> `direct`
  - Source: spans=`s15`, section=`sec_reusable_process`, packet=`p_list_item_routes_to_the_relevant_communications_lead_for_review`
  - Explanation: Variable 'status_flag' is produced by source-backed step 'st_3'.
- `variable:target_audience` -> `assumed` [needs confirmation]
  - Explanation: Variable 'target_audience' is declared as worker input contract with no source evidence.
- `variable:topic_summary` -> `assumed` [needs confirmation]
  - Explanation: Variable 'topic_summary' is declared as worker input contract with no source evidence.
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
- `missing_output_producer`: Required outputs without a source-backed producer stay in the contract; no synthetic producer command is invented.
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
- Unused variable declared: status_flag
- Unused variable declared: finished_draft

## 9. SPL Draft

```spl
[DEFINE_AGENT: MainWorker "Orchestrate the end-to-end process and delegate to sub-tasks."]
    [DEFINE_PERSONA:]
        ROLE: Internal communications drafting specialist
        TemplateDriven: Uses the approved internal communications template and follows the standard internal communications style guide.
        PlainLanguageAndInclusiveTone: Writes in plain language and maintains an inclusive tone.
        ReviewOriented: Routes drafts to the relevant communications lead for review and waits for final sign-off before marking them approved.
    [END_PERSONA]
    [DEFINE_CONCEPTS:]
        InternalCommunicationsDrafting: The task family of creating internal organizational content such as newsletters, announcements, digests, and executive briefs.
        RecurringDigests: Regularly scheduled summary updates compiled for internal audiences.
        ExecutiveMemos: Formal internal messages intended for executives.
        CrisisCommunications: Emergency or incident-related communications that are explicitly outside the scope of this drafting task.
        InternalCommunicationsArtifacts: Documents or communication outputs produced as part of internal communications work.
        ApprovedTemplate: The required standard format that must be used when drafting internal communications.
        CommunicationsLead: The reviewer responsible for final review and approval of the draft.
        StatusFlag: A label indicating draft state, with allowed values such as drafting, ready for review, and approved.
    [END_CONCEPTS]
    [DEFINE_CONSTRAINTS:]
        Requirement: Must use the approved template
        Requirement: Must follow plain-language and inclusive tone guidelines
        Gate: Require final sign-off from the communications lead before flagging the draft as approved
    [END_CONSTRAINTS]
    [DEFINE_VARIABLES:]
        "Key dates or deadlines provided by the user." key_dates_or_deadlines: List [text]
        "Summary of the topic to draft about." topic_summary: text
        "Intended audience for the draft." target_audience: text
        "Status of the draft with allowed values drafting, ready for review, or approved." status_flag: text
        "Finished draft content in Word or Google Doc form, 200 to 500 words, with no approval marks." finished_draft: text
        "Structured result for st_1." worker_main_st_1_result_structured: worker_main_st_1_result_structured_type
        "Structured result for st_2." worker_main_st_2_result_structured: worker_main_st_2_result_structured_type
    [END_VARIABLES]
    [DEFINE_FILES:]
        "Finished draft as a Word or Google Doc document." finished_draft < >: text
    [END_FILES]
    [DEFINE_TYPES:]
        worker_main_st_1_result_structured_type = { topic_summary: text, target_audience: text }
        worker_main_st_2_result_structured_type = { finished_draft: text, status_flag: text }
    [END_TYPES]
    [DEFINE_WORKER: "Orchestrate the end-to-end process and delegate to sub-tasks." MainWorker]
        [INPUTS]
            REQUIRED <REF>key_dates_or_deadlines</REF>
            REQUIRED <REF>topic_summary</REF>
            REQUIRED <REF>target_audience</REF>
        [END_INPUTS]
        [OUTPUTS]
            REQUIRED <REF>worker_main_st_2_result_structured</REF>
        [END_OUTPUTS]
        [MAIN_FLOW]
            [SEQUENTIAL_BLOCK]
                COMMAND-1 [INPUT Request topic and audience from the requestor VALUE worker_main_st_1_result_structured: worker_main_st_1_result_structured_type SET]
                COMMAND-2 [COMMAND Draft the internal communications piece using the standard template based on <REF>worker_main_st_1_result_structured</REF> RESULT worker_main_st_2_result_structured: worker_main_st_2_result_structured_type SET]
                COMMAND-3 [COMMAND Route the draft to the relevant communications lead for review based on <REF>worker_main_st_2_result_structured</REF> RESULT status_flag: text SET]
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
