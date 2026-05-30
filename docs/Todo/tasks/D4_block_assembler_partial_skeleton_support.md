# Task D4: BlockAssembler Partial Skeleton Support

Date assigned: 2026-05-20

Owner: TBD

Reviewer: PM / Codex

Prerequisites:

- F0 through F4 approved.
- D0, D1, D2, and D6 approved.

Related docs:

- `docs/Todo/route_contract_refactor_02_downstream_migration.md`
- `docs/Todo/tasks/D2_flow_assembler_route_driven_exception_materialization.md`
- `docs/Todo/tasks/D6_step_extractor_executable_filtering.md`
- `docs/Todo/route_contract_refactor_progress_tracker.html`

## Objective

Ensure condition-only `ExceptionFlow` structures produced by D2 remain legal,
visible partial IR through Stage 5.

D2 now creates route-derived exception flows from non-executable failure-mode
annotations. D6 prevents those failure conditions from becoming commands.
D4 must make sure Stage 5 does not erase, reinterpret, or "complete" these
condition-only exception flows by inventing handler blocks.

The intended shape is:

```text
ExceptionFlow:
  flow_id = exc_adapter_00
  condition_text = "Missing timeframe."
  spans = ["s_failure"]

BlockStructureIR:
  may contain a condition-only placeholder block if required by current IR
  conventions, but must not contain a fabricated handler/action block.
```

## Scope

In scope:

- preserve route-derived `ExceptionFlow` ids through Stage 5;
- support exception flows that have a condition and source spans but no handler
  blocks;
- make Stage 5 prompt/context explicit that condition-only exception flows are
  legal partial skeletons;
- add deterministic post-processing only if current downstream IR requires an
  exception-flow block container;
- prevent LLM-generated handler blocks when the source only supplies a failure
  condition;
- preserve existing LLM-provided exception blocks when they are source-backed;
- preserve existing normal main/alternative block behavior;
- add focused tests for route-derived partial exception flows.

Out of scope:

- Stage 4 route materialization changes;
- Stage 7 executable filtering changes;
- worker-aware exception ownership migration;
- renderer or SPL syntax changes;
- normalizer/final diagnostic migration;
- deleting or deprecating bridge code;
- creating handler steps or recovery actions.

## Affected Files

Expected production areas:

- `src/nl2spl/pipeline/stages/stage5_block_assembler/executor.py`
- `src/nl2spl/pipeline/stages/stage5_block_assembler/prompt_enricher.py`
- `src/nl2spl/pipeline/stages/stage5_block_assembler/block_parser.py`
- `src/nl2spl/pipeline/stages/stage5_block_assembler/span_boundary.py`
- any existing Stage 5 post-process module, if present

Expected tests:

- `tests/unit/test_block_assembler.py`
- `tests/unit/test_block_postprocess.py`
- `tests/unit/test_stage5_prompt.py`
- integration-style Stage 4 -> Stage 5 test if needed

## Required Implementation

### 1. Identify Condition-Only Exception Flows

Stage 5 must recognize exception flows where:

- `condition_text` is present;
- `spans` contains source span ids;
- there are no source-backed handler/action spans;
- D6 has removed any bad handler command sourced only from the condition.

Do not infer handler behavior from:

- the failure condition text itself;
- section names such as `Failure handling`;
- generic phrases like `Missing timeframe`;
- hard facts without explicit handler action evidence.

### 2. Prompt Contract

Stage 5 prompt/context should tell the LLM that condition-only exception flows
are valid partial structures.

The prompt must communicate:

```text
Do not invent handler blocks. If an exception flow only has condition evidence,
preserve it as a partial exception skeleton.
```

This must be tested by inspecting the Stage 5 user prompt or enriched flow
context.

### 3. Block Materialization Rules

Allowed behavior:

- keep `exception_flow_blocks[flow_id] == []` if current downstream stages can
  handle it;
- or create a deterministic non-handler placeholder/container block only if the
  IR contract requires a block entry for visibility.

Forbidden behavior:

- creating a `SEQUENTIAL` or `ACTION` block that implies a handler action;
- copying the condition text into a handler block as if it were an action;
- creating a pseudo step or command for the handler;
- silently dropping the exception flow because it lacks handler blocks.

If a placeholder/container block is introduced, it must be clearly typed and
tested as non-executable / non-handler according to the existing block schema.

### 4. Preserve Source-Backed Handler Blocks

If Stage 5 receives an existing exception flow where the LLM output includes a
block backed by explicit handler/recovery source spans, preserve that behavior.

D4 is not a blanket ban on exception-flow blocks. It is a ban on invented
handler blocks for condition-only flows.

### 5. Post-Processing And Span Boundaries

Post-processing must not drop condition-only exception flows or their
condition span ids.

If span-boundary filtering sees an exception-flow block with no handler spans,
it must preserve the exception flow metadata and avoid fabricating spans.

### 6. Missing Handler Diagnostics

D4 does not need to implement the final diagnostic migration, but it must
preserve enough structure for existing later checks to emit or preserve
`missing_handler`.

Do not suppress `missing_handler` by creating fake handler blocks.

## Required Tests

### Test 1: Condition-Only Exception Flow Survives Stage 5

Input:

- `FlowStructureIR.exception_flows` contains
  `ExceptionFlow("exc_adapter_00", "Missing timeframe.", ["s_failure"])`;
- Stage 5 LLM output has no exception blocks for that flow.

Assert:

- output `BlockStructureIR` does not drop `exc_adapter_00`;
- condition span id remains associated with the flow through existing IR
  structure or by preserving the `FlowStructureIR` side input unchanged;
- no handler/action block is fabricated.

### Test 2: Stage 5 Prompt Allows Partial Exception Skeletons

Input:

- condition-only exception flow.

Assert:

- Stage 5 prompt/context contains the exception flow id and condition;
- prompt explicitly says not to invent handler blocks;
- prompt explicitly allows partial/condition-only exception skeletons.

### Test 3: LLM-Fabricated Handler Block Is Rejected Or Neutralized

Input:

- condition-only exception flow;
- LLM returns an exception-flow block that uses the condition span as a handler
  action, e.g. text equivalent to `Handle missing timeframe`.

Assert:

- fabricated handler block is rejected, dropped, or marked non-handler;
- no executable handler structure is created;
- a warning/diagnostic is emitted if current Stage 5 diagnostics support it.

### Test 4: Source-Backed Handler Block Still Preserved

Input:

- exception flow with separate explicit handler/recovery span;
- LLM returns a block sourced from that handler span.

Assert:

- source-backed exception block is preserved;
- D4 guard does not remove legitimate handler material.

### Test 5: Normal Main Flow Blocks Are Unchanged

Input:

- no exception flows, ordinary process spans.

Assert:

- existing main-flow block behavior remains unchanged.

### Test 6: No Bridge / Stage 7 / Normalizer Changes

This can be a review assertion plus `git diff --name-only` evidence.

Assert:

- no D4 production change touches Stage 4 route materialization;
- no Stage 7 executable filtering changes are included;
- no bridge deletion/deprecation is included;
- no renderer/normalizer migration is included.

## Acceptance Criteria

D4 is complete when:

- condition-only route-derived exception flows survive Stage 5;
- Stage 5 prompt/context explicitly permits partial exception skeletons;
- no synthetic handler block, handler step, or recovery action is created from a
  failure condition alone;
- fabricated handler-like LLM output from condition-only spans is rejected or
  neutralized deterministically;
- source-backed handler blocks still work;
- normal main and alternative block assembly remains unchanged;
- downstream `missing_handler` remains possible because no fake handler masks
  the gap;
- no Stage 4, Stage 7, D3 worker ownership, D7 normalizer/renderer, or D8
  bridge-deletion work is mixed into this phase;
- focused Stage 5 tests and the full unit suite pass.

## Required Evidence For Review

When submitting D4 for review, provide:

1. changed files;
2. exact test commands and output summary;
3. sample condition-only `ExceptionFlow` input;
4. sample `BlockStructureIR` output showing the flow was preserved without a
   fabricated handler;
5. prompt excerpt or test proof showing "do not invent handler blocks" and
   partial skeleton allowance;
6. fabricated-handler rejection example;
7. source-backed handler preservation example;
8. confirmation that Stage 4, Stage 7, bridge deletion, normalizer, and renderer
   were not changed.

## PM Review Checklist

- [ ] Condition-only exception flow survives Stage 5.
- [ ] Prompt/context explicitly permits partial exception skeletons.
- [ ] Prompt/context explicitly forbids invented handler blocks.
- [ ] LLM-fabricated handler block from condition-only span is blocked.
- [ ] Source-backed handler block is preserved.
- [ ] No fake handler masks downstream `missing_handler`.
- [ ] Normal main-flow block behavior remains unchanged.
- [ ] D4 does not mix in D3, D7, or D8 scope.
- [ ] Full unit suite passes.
