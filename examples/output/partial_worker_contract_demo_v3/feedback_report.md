# NL2SPL Feedback Report

## 1. Overall Compile State

- Completeness: `partial`
- SPL draft generated: `yes`
- Compile diagnostics: `8`
- Assumptions / suggestions: `6`
- Trace records: `30`
- Adapter warnings: `0`
- Validation errors: `0`
- Validation warnings: `0`

Result is partial because the following requirement gaps remain:
- `type_or_contract_ambiguity` on `worker_promotion:del_s8a`: WORKER_PROMOTION blocked by missing promotion slots.
  - `promotion_input_contract`: Missing clear input contract
  - `promotion_output_contract`: Missing clear output contract
  - `promotion_invocation_point`: Missing accepted decision or matching handoff with invocation hint
  - `promotion_result_handoff`: Missing matching handoff with output bindings

## 2. Materialized Source-Backed Structure

### Workers
- `worker:MainWorker` (direct) -- spans=s7, s8a, s8b, s10, s11, s12, s13, s14, s18, s19; section=sec_reusable_process; packet=p_sentence_then_extract_a_separate_child_worker_named_evidenceretrievalworker

### Flows
- `flow:main` (direct) -- spans=s7, s10, s11, s12, s13, s14, s19

### Steps
- `step:st_1` (direct) -- spans=s7
- `step:st_2` (direct) -- spans=s10
- `step:st_3` (direct) -- spans=s11
- `step:st_4` (direct) -- spans=s12
- `step:st_5` (direct) -- spans=s13
- `step:st_6` (direct) -- spans=s14
- `step:st_7` (direct) -- spans=s19

### Variables
- `variable:completion_status` (direct) -- spans=s14
- `variable:evidence_summary` (direct) -- spans=s11
- `variable:triage_response` (direct) -- spans=s19

### Constraints
- `constraint:c_1` (direct) -- spans=s15, s16
- `constraint:c_2` (direct) -- spans=s17, s22
- `constraint:c_3` (direct) -- spans=s20
- `constraint:c_4` (direct) -- spans=s21
- `constraint:c_5` (direct) -- spans=s23

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

- `worker_promotion:del_s8a`: `type_or_contract_ambiguity` -- WORKER_PROMOTION blocked by missing promotion slots.
  - Source spans: `s8a`
  - `promotion_input_contract`: Missing clear input contract
  - `promotion_output_contract`: Missing clear output contract
  - `promotion_invocation_point`: Missing accepted decision or matching handoff with invocation hint
  - `promotion_result_handoff`: Missing matching handoff with output bindings

## 4. Diagnostics

### grouped:worker_promotion:del_s8a: `type_or_contract_ambiguity`
- Severity: `warning`
- Target: `worker_promotion:del_s8a`
- Source spans: `s8a`
- Message: WORKER_PROMOTION blocked by missing promotion slots.
- Blocks rendering: `false`
- Blocks completion: `true`
- Missing slots:
  - `promotion_input_contract`: Missing clear input contract
    - Diagnostic: `irs_ea3b094c8454`
  - `promotion_output_contract`: Missing clear output contract
    - Diagnostic: `irs_c5bd45f2d8c9`
  - `promotion_invocation_point`: Missing accepted decision or matching handoff with invocation hint
    - Diagnostic: `irs_c64e7959d871`
  - `promotion_result_handoff`: Missing matching handoff with output bindings
    - Diagnostic: `irs_7c64c594a540`

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

### stage2_route_refinement_diagnostic_: `route_refinement_diagnostic`
- Severity: `info`
- Message: LLM route diagnostic [mixed_delegation_semantics] span='s8': Delegation intent and worker name are mixed; emitted multi-label annotation and split recommendation.
- Blocks rendering: `false`
- Blocks completion: `false`

### stage2_route_refinement_split_s8: `route_refinement_split`
- Severity: `info`
- Target: `span:s8`
- Source spans: `s8`
- Message: Split recommended for s8: Contains both a delegation intent and a specific worker target.
- Blocks rendering: `false`
- Blocks completion: `false`

## 5. Assumptions / Suggestions

- `ASM_0000` for `variable:user_incident_report`: Variable has no discoverable source provenance.
  - Reason: The compiler could not trace this variable back to a source span, adapter hard fact, or producer step.  Its origin is assumed.
  - Suggested resolution: For variable:user_incident_report: add source evidence (a span, adapter hint, or producer step) that justifies this variable's existence.
  - Related diagnostic: `diag_prov_0000`
- `ASM_0001` for `variable:approved_evidence_repositories`: Variable has no discoverable source provenance.
  - Reason: The compiler could not trace this variable back to a source span, adapter hard fact, or producer step.  Its origin is assumed.
  - Suggested resolution: For variable:approved_evidence_repositories: add source evidence (a span, adapter hint, or producer step) that justifies this variable's existence.
  - Related diagnostic: `diag_prov_0001`
- `ASM_0002, ASM_0003, ASM_0004, ASM_0005` for `worker_promotion:del_s8a`: Worker promotion has an incomplete contract.
  - Reason: The candidate is blocked by multiple missing promotion slots.
  - Suggested resolution: Provide the missing input/output contracts, invocation point, and result handoff details listed in the related diagnostics.
  - Related diagnostics: `irs_ea3b094c8454, irs_c5bd45f2d8c9, irs_c64e7959d871, irs_7c64c594a540`

## 6. Provenance / TraceRecords

- `constraint:c_1` -> `direct`
  - Source: spans=`s15, s16`
  - Explanation: Constraint 'c_1' (delegation_boundary): EvidenceRetrievalWorker is an explicit delegation with a strong semantic boundar
- `constraint:c_2` -> `direct`
  - Source: spans=`s17, s22`
  - Explanation: Constraint 'c_2' (prohibition): Do not invent missing child worker input or output contracts; keep the child wor
- `constraint:c_3` -> `direct`
  - Source: spans=`s20`
  - Explanation: Constraint 'c_3' (delegation_boundary): Evidence retrieval must remain a bounded child worker because it is reusable and
- `constraint:c_4` -> `direct`
  - Source: spans=`s21`
  - Explanation: Constraint 'c_4' (prohibition): Do not convert evidence retrieval into a generic main-flow command.
- `constraint:c_5` -> `direct`
  - Source: spans=`s23`
  - Explanation: Constraint 'c_5' (gate): Do not create an executable worker invocation unless the handoff contract is com
- `flow:main` -> `direct`
  - Source: spans=`s7, s10, s11, s12, s13, s14, s19`
  - Explanation: Main flow with 1 block(s).
- `profile:concept_0` -> `normalized`
  - Explanation: Concept: Incident-response investigation workflows -- A workflow for handling an incident report by triaging facts, gathering supporting evidence, and producing a short response with status.
- `profile:concept_1` -> `normalized`
  - Explanation: Concept: Approved evidence repositories -- A vetted list of repositories that may be queried to find supporting evidence for the incident report.
- `profile:concept_2` -> `normalized`
  - Explanation: Concept: Triage response -- A short summary of the incident-handling outcome or next-step assessment.
- `profile:concept_3` -> `normalized`
  - Explanation: Concept: Evidence summary -- A consolidated summary of collected evidence along with its provenance.
- `profile:concept_4` -> `normalized`
  - Explanation: Concept: Completion status -- The final state indicating whether the workflow has completed.
- `profile:concept_5` -> `normalized`
  - Explanation: Concept: EvidenceRetrievalWorker -- A separate child worker responsible for querying approved repositories, collecting matching evidence, normalizing provenance, and returning control to the main worker.
- `profile:concept_6` -> `normalized`
  - Explanation: Concept: Provenance -- The source origin and traceability information for collected evidence.
- `profile:concept_7` -> `normalized`
  - Explanation: Concept: Semantic boundary -- A meaningful separation that keeps evidence retrieval as its own reusable delegated unit rather than a simple sequential step.
- `profile:concept_8` -> `normalized`
  - Explanation: Concept: Invocation contract -- The defined interface for launching a worker, including its required inputs and outputs.
- `profile:concept_9` -> `normalized`
  - Explanation: Concept: Handoff contract -- The complete set of fields and expectations needed before creating an executable worker invocation.
- `profile:persona` -> `inferred`
  - Explanation: Persona: Incident-response workflow specialist
- `step:st_1` -> `direct`
  - Source: spans=`s7`
  - Explanation: Step 'st_1' maps to source span(s).
- `step:st_2` -> `direct`
  - Source: spans=`s10`
  - Explanation: Step 'st_2' maps to source span(s).
- `step:st_3` -> `direct`
  - Source: spans=`s11`
  - Explanation: Step 'st_3' maps to source span(s).
- `step:st_4` -> `direct`
  - Source: spans=`s12`
  - Explanation: Step 'st_4' maps to source span(s).
- `step:st_5` -> `direct`
  - Source: spans=`s13`
  - Explanation: Step 'st_5' maps to source span(s).
- `step:st_6` -> `direct`
  - Source: spans=`s14`
  - Explanation: Step 'st_6' maps to source span(s).
- `step:st_7` -> `direct`
  - Source: spans=`s19`
  - Explanation: Step 'st_7' maps to source span(s).
- `variable:approved_evidence_repositories` -> `assumed` [needs confirmation]
  - Explanation: Variable 'approved_evidence_repositories' is declared as worker input contract with no source evidence.
- `variable:completion_status` -> `direct`
  - Source: spans=`s14`
  - Explanation: Variable 'completion_status' is produced by source-backed step 'st_6'.
- `variable:evidence_summary` -> `direct`
  - Source: spans=`s11`
  - Explanation: Variable 'evidence_summary' is produced by source-backed step 'st_3'.
- `variable:triage_response` -> `direct`
  - Source: spans=`s19`
  - Explanation: Variable 'triage_response' is produced by source-backed step 'st_7'.
- `variable:user_incident_report` -> `assumed` [needs confirmation]
  - Explanation: Variable 'user_incident_report' is declared as worker input contract with no source evidence.
- `worker:MainWorker` -> `direct`
  - Source: spans=`s7, s8a, s8b, s10, s11, s12, s13, s14, s18, s19`, section=`sec_reusable_process`, packet=`p_sentence_then_extract_a_separate_child_worker_named_evidenceretrievalworker`
  - Explanation: Main worker 'MainWorker' assembled from flow and step IRs.

## 7. Anti-Fabrication Checks

- `type_or_contract_ambiguity`: Unresolved worker/API contracts are reported as ambiguity; they are not downgraded to generic commands.
- Rendered SPL contains no executable `[INVOKE ...]` command.

## 8. Adapter / Validation Notes

No adapter or validation notes.

## 9. SPL Draft

```spl
[DEFINE_AGENT: MainWorker "Orchestrate the end-to-end process and delegate to sub-tasks."]
    [DEFINE_PERSONA:]
        ROLE: Incident-response workflow specialist
        InferredRole: Role inferred from task context; no explicit identity description was provided in the source text.
        DelegationOriented: Works with explicit child-worker boundaries and treats evidence retrieval as a bounded delegated responsibility.
        ContractConstrained: Avoids inventing missing input/output contract fields and requires complete handoff contracts before execution.
        ProvenanceFocused: Maintains provenance responsibility by normalizing evidence sources and discarding unsupported claims.
    [END_PERSONA]
    [DEFINE_CONCEPTS:]
        Incidentresponseinvestigationworkflows: A workflow for handling an incident report by triaging facts, gathering supporting evidence, and producing a short response with status.
        Approvedevidencerepositories: A vetted list of repositories that may be queried to find supporting evidence for the incident report.
        Triageresponse: A short summary of the incident-handling outcome or next-step assessment.
        Evidencesummary: A consolidated summary of collected evidence along with its provenance.
        Completionstatus: The final state indicating whether the workflow has completed.
        EvidenceRetrievalWorker: A separate child worker responsible for querying approved repositories, collecting matching evidence, normalizing provenance, and returning control to the main worker.
        Provenance: The source origin and traceability information for collected evidence.
        Semanticboundary: A meaningful separation that keeps evidence retrieval as its own reusable delegated unit rather than a simple sequential step.
        Invocationcontract: The defined interface for launching a worker, including its required inputs and outputs.
        Handoffcontract: The complete set of fields and expectations needed before creating an executable worker invocation.
    [END_CONCEPTS]
    [DEFINE_CONSTRAINTS:]
        DelegationBoundary: EvidenceRetrievalWorker is an explicit delegation with a strong semantic boundary, not ordinary sequential step or simple control flow.
        Prohibition: Do not invent missing child worker input or output contracts; keep the child worker definition as a renderable skeleton with empty INPUTS and empty OUTPUTS.
        DelegationBoundary: Evidence retrieval must remain a bounded child worker because it is reusable and has its own provenance responsibility.
        Prohibition: Do not convert evidence retrieval into a generic main-flow command.
        Gate: Do not create an executable worker invocation unless the handoff contract is complete.
    [END_CONSTRAINTS]
    [DEFINE_VARIABLES:]
        "User-provided incident report for triage and evidence review." user_incident_report: text
        "List of approved repositories to query for supporting evidence." approved_evidence_repositories: List [text]
        "Short response summarizing the triage outcome." triage_response: text
        "Summary of the collected evidence and provenance." evidence_summary: text
        "Final completion state of the workflow." completion_status: text
    [END_VARIABLES]
    [DEFINE_WORKER: "Orchestrate the end-to-end process and delegate to sub-tasks." MainWorker]
        [INPUTS]
            REQUIRED <REF>user_incident_report</REF>
            REQUIRED <REF>approved_evidence_repositories</REF>
        [END_INPUTS]
        [OUTPUTS]
            REQUIRED <REF>triage_response</REF>
            REQUIRED <REF>evidence_summary</REF>
            REQUIRED <REF>completion_status</REF>
        [END_OUTPUTS]
        [MAIN_FLOW]
            [SEQUENTIAL_BLOCK]
                COMMAND-1 [COMMAND Review the incident report and identify facts requiring support based on <REF>user_incident_report</REF>]
                COMMAND-2 [COMMAND Query approved evidence repositories based on <REF>approved_evidence_repositories</REF>]
                COMMAND-3 [COMMAND Collect matching evidence RESULT evidence_summary: text SET]
                COMMAND-4 [COMMAND Normalize provenance based on <REF>evidence_summary</REF> RESULT <REF>evidence_summary</REF> SET]
                COMMAND-5 [COMMAND Discard unsupported claims based on <REF>evidence_summary</REF> RESULT <REF>evidence_summary</REF> SET]
                COMMAND-6 [COMMAND Return control to the main worker RESULT completion_status: text SET]
                COMMAND-7 [COMMAND Draft the triage response based on <REF>user_incident_report</REF> and <REF>evidence_summary</REF> RESULT triage_response: text SET]
            [END_SEQUENTIAL_BLOCK]
        [END_MAIN_FLOW]
    [END_WORKER]
[END_AGENT]
```
