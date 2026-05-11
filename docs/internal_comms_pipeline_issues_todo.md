# Internal Comms Pipeline Issues TODO

Date: 2026-05-09

This document records current issues observed from the intermediate files under:

`examples/output/internal-comms`

These are intentionally kept separate from the input-adapter design discussion. The goal is to preserve the root causes and future fixes without implementing them immediately.

## Confirmed Reasonable Items

The following observations are considered reasonable for the current semantics:

- `s11: Do not finalize if required slots remain missing...` being routed to `rules` is reasonable. It is a gate constraint, not necessarily a behavior step.
- `s10: If the user asks for revision...` being represented as `ALTERNATIVE_FLOW` is reasonable. It is a user-triggered alternate path.

## Issue 1: Inputs And Required Outputs Routed To Domain

Observed in `stage2_field_router.json`:

```json
"domain": ["s1", "s2", "s3", "s17"]
```

Where:

- `s2` is the `Inputs for each run` section content.
- `s3` is the `Required outputs` section content.

Root cause:

- Stage 2 has no section-aware input adapter.
- The Stage 2 prompt has only six semantic buckets.
- `domain` is available as a bucket for concept-like descriptions.
- Although the prompt says behavior includes inputs and outputs, the model interpreted `s2` and `s3` as descriptive definitions rather than runtime resources.

Impact:

- Stage 6 does not receive the true input/output section content because it currently extracts resources from behavior and integrations spans.
- True run inputs such as `user_request`, `known_topics`, `timeframe`, `available_connectors`, and `format_preferences` are missed.
- True required outputs such as `draft_communication_artifact`, `source_evidence_set`, `assumptions_log`, and `completion_status` are missed.

Future fix candidates:

- Add a section-aware input adapter before Stage 2.
- Seed Stage 6 with structured input/output candidates from known sections.
- Consider separate route hints for `input_seed` and `output_seed` rather than forcing these spans into `behavior`.

## Issue 2: MainWorker Inputs Became Internal State Variables

Observed in final SPL:

```spl
[INPUTS]
    REQUIRED <REF>communication_type</REF>
    REQUIRED <REF>required_fields</REF>
    REQUIRED <REF>sources_needed</REF>
    REQUIRED <REF>sources_available</REF>
    REQUIRED <REF>source_recipes</REF>
    REQUIRED <REF>revision_requested</REF>
    REQUIRED <REF>source_requirements</REF>
    REQUIRED <REF>template_criteria</REF>
[END_INPUTS]
```

Root cause chain:

1. Stage 2 routed true input/output sections to `domain`.
2. Stage 6 did not see those sections during resource extraction.
3. Stage 6 inferred variables from process behavior spans.
4. Stage 6 marked several internal control variables as `source: "input"`.
5. Stage 10 mechanically maps every `VariableSpec` with `source == "input"` to `WorkerInput`.

Impact:

- Internal state variables become external worker inputs.
- Steps such as `Determine the type of communication requested based on communication_type` invert dataflow: `communication_type` should be produced from `user_request`, not required as input.

Future fix candidates:

- Use input adapter seeds for true worker inputs.
- Make Stage 6 distinguish runtime inputs, derived state, conditions, and outputs.
- Add a Stage 9.5 validation warning or error when a step consumes a variable whose name/description indicates it should be produced by that same step.

## Issue 3: Duplicate IF "sources are needed and available"

Observed in final SPL:

```spl
DECISION-1 [IF sources are needed and available]
    COMMAND-5 [COMMAND Retrieve sources using approved source recipes ...]
[END_IF]

DECISION-3 [IF sources are needed and available]
    COMMAND-8 [INVOKE child_dc_1 ...]
[END_IF]
```

Root cause:

- The first IF comes from `s7`, which is a legitimate main-flow conditional behavior span.
- The second IF comes from `s18`, which is delegation policy text.
- Stage 4 generated a child-worker `delegation_candidate` from `s18`.
- Stage 7 generated `INVOKE_WORKER` for `s18`.
- Stage 9.5 classified the candidate as source-related and inserted a main-flow IF block with hard-coded condition text `If sources are needed and available`.

Impact:

- The SPL expresses source handling twice: once as a normal command, once as a delegated worker invocation.
- Delegation policy is compiled as a separate executable step instead of modifying the execution strategy for `s7`.

Future fix candidates:

- Treat delegation policy as a strategy/worker-plan hint, not as a behavior step by default.
- Link delegation policy to concrete process spans such as `s7` instead of adding a second block.
- Introduce `DelegationPlanIR` / `WorkerPlanIR` so worker handoffs are planned before Flow/Block assembly.

## Issue 4: Delegation Candidate Is Too Abstract To Be A Concrete Child Worker

Observed in `stage4_flow_assembler.json`:

```json
{
  "candidate_id": "dc_1",
  "spans": ["s18"],
  "reason": "This describes optional, self-contained subtasks like source gathering or template matching...",
  "input_variables": ["source_requirements", "template_criteria"],
  "output_variables": ["normalized_evidence"]
}
```

Root cause:

- `s18` is policy-level delegation guidance.
- It names possible subtask categories but does not itself define concrete runtime inputs.
- Current `delegation_candidates` lacks a link to the process span that should be delegated.

Impact:

- The child worker is defined from policy text rather than a concrete process task.
- `source_requirements` and `template_criteria` are invented as required worker inputs.

Future fix candidates:

- Input adapter should split delegation policy into integration hints, subtask hints, and delegation constraints.
- Worker planning should bind subtask hints to process spans before child worker creation.
- A child worker should only be emitted when there is a concrete owned behavior span or planned handoff.

## Issue 5: Failure Handling Section Lost As Exception-Flow Seeds

Observed in `stage2_field_router.json`:

```json
"domain": ["s1", "s2", "s3", "s17"]
```

Where `s17` is:

```text
Missing timeframe, conflicting instructions, insufficient source access, evidence shortage, user refusal to answer, and provenance failure.
```

Root cause:

- Stage 2 treated the failure handling list as domain-like terminology.
- No input adapter preserved the section heading `Failure handling`.

Impact:

- Stage 4 saw no failure-handling behavior spans and produced zero exception flows.

Future fix candidates:

- Input adapter should emit `exception_seed` records from `Failure handling`.
- Stage 4 should consume exception seeds alongside behavior spans.
- Exception seeds should compile into exception flows only when enough handling action is available; otherwise they should become constraints/warnings requiring handling behavior.

## Issue 6: Required Output Reachability Is Based On Wrong Outputs

Observed in final SPL:

```spl
[OUTPUTS]
    REQUIRED <REF>draft_output</REF>
    OPTIONAL <REF>revised_output</REF>
    REQUIRED <REF>normalized_evidence</REF>
[END_OUTPUTS]
```

Root cause:

- True required outputs from `s3` did not reach Stage 6 as output seeds.
- Stage 6 inferred outputs from behavior/delegation text.

Impact:

- `source_evidence_set`, `assumptions_log`, and `completion_status` are absent.
- `normalized_evidence` becomes a required MainWorker output even though it is only part of delegation policy.

Future fix candidates:

- Seed required outputs from known `Required outputs` section.
- Add output-name normalization rules for common internal-comms concepts.
- Require Stage 9.5 to compare generated outputs against adapter-provided required output seeds.
