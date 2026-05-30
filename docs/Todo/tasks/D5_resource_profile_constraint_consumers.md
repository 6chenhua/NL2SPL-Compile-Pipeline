# Task D5: Resource, Profile, and Constraint Consumers

Date assigned: 2026-05-20

Owner: TBD

Reviewer: PM / Codex

Prerequisites:

- F0 through F4 approved.
- D0, D1, D2, D6, D4, and D3 approved.

Related docs:

- `docs/Todo/route_contract_refactor_02_downstream_migration.md`
- `docs/Todo/tasks/D2_flow_assembler_route_driven_exception_materialization.md`
- `docs/Todo/tasks/D3_worker_aware_exception_flow_migration.md`
- `docs/Todo/tasks/D6_step_extractor_executable_filtering.md`
- `docs/Todo/route_contract_refactor_progress_tracker.html`

## Objective

Teach non-flow downstream consumers to use route annotations and adapter facts
without confusing semantic roles.

D2/D3 moved failure modes into route-derived exception flows. D6 prevented
non-executable route material from becoming commands. D5 closes the adjacent
consumer gap: Stage 6, Stage 8, and Stage 9 must not accidentally reinterpret
failure conditions, resource contracts, profile hints, or delegation boundaries
through old route-list-only behavior.

The target behavior is:

```text
resource_contract annotations / hard facts
-> resource contracts and variables

profile/domain annotations
-> profile extraction context

constraint annotations / policy spans
-> constraints

failure_mode annotations
-> exception condition context only
-> not variables, not policies by default
```

## Scope

In scope:

- Stage 6 legacy/global resource extraction;
- Stage 6 worker-scoped resource extraction;
- Stage 6 resource context builder;
- Stage 8 profile extraction prompt context and fallback behavior;
- Stage 9 constraint extraction prompt context and filtering;
- tests proving failure modes are not reclassified as resources or policies.

Out of scope:

- Stage 4 exception materialization changes;
- Stage 5 partial skeleton changes;
- Stage 7 executable filtering changes;
- Stage 9.5 normalizer migration;
- Stage 10 worker assembly changes;
- Stage 11 renderer changes;
- deleting or deprecating bridge code.

## Affected Files

Expected production areas:

- `src/nl2spl/pipeline/stages/stage6_resource_extractor/legacy.py`
- `src/nl2spl/pipeline/stages/stage6_resource_extractor/worker_scoped.py`
- `src/nl2spl/pipeline/stages/stage6_resource_extractor/context_builder.py`
- `src/nl2spl/pipeline/stages/stage8_profile_extractor.py`
- `src/nl2spl/pipeline/stages/stage9_constraint_extractor.py`

Expected tests:

- `tests/unit/test_resource_extractor_hardening.py`
- `tests/unit/test_stage6_resource_context_v2.py`
- `tests/unit/pipeline/stages/test_stage6_worker_scoped.py`
- `tests/unit/test_profile_extractor.py` or equivalent Stage 8 test file
- `tests/unit/test_constraint_extractor.py` or equivalent Stage 9 test file
- `tests/unit/test_input_adapter_pipeline.py` only if end-to-end structural NL
  coverage is needed

## Required Implementation

### 1. Baseline Before Production Changes

Start by adding focused characterization tests for current behavior where useful.
Do not rewrite all three stages at once without tests that expose the intended
D5 contract.

At minimum, establish tests for:

- resource extraction with failure-mode annotations present;
- resource extraction with runtime input and required output hard facts;
- constraint extraction with failure-mode annotations present;
- profile extraction with profile/domain annotations present.

### 2. Stage 6 Resource Extraction

Stage 6 must keep resource extraction grounded in resource evidence.

Required behavior:

- hard-fact inputs and outputs remain authoritative contract variables;
- `semantic_role="input_contract"` and `semantic_role="output_contract"` may be
  used as resource context;
- failure-mode annotations are not shown as candidate variables;
- exception condition text may appear only as flow context, not as a resource
  declaration candidate;
- route metadata fields such as `semantic_role`, `slot_target`, `flow_id`,
  `block_id`, `span_id`, `source_section_id`, and `source_packet_id` are never
  extracted as variables;
- worker-scoped Stage 6 preserves the same behavior per worker.

Implementation notes:

- Preserve the existing hard-fact merge behavior in `legacy.py`.
- When building prompt context, separate authoritative contracts from source
  spans and exception conditions.
- In worker-scoped mode, preserve annotations when constructing worker-local
  `FieldRouteIR`; do not drop annotations needed by the context builder.
- If filtering LLM output, prefer a narrow guard: reject schema-looking or
  annotation-metadata variable names, but do not reject legitimate domain
  variables.

### 3. Stage 8 Profile Extraction

Stage 8 must prefer route annotations for profile-like material while keeping old
route lists as fallback.

Required behavior:

- `semantic_role` values such as `profile_domain`, `identity`, `persona`,
  `audience`, or equivalent profile annotations should be included in the
  profile prompt context;
- if annotations are absent, existing `routes.identity`, `routes.audience`, and
  `routes.domain` behavior remains unchanged;
- failure modes must not influence persona role inference;
- resource contract spans must not become persona/domain concepts unless their
  text explicitly states domain/profile semantics.

Implementation notes:

- Do not remove old route-list behavior in D5.
- Avoid feeding all source spans as equally strong profile evidence when
  annotations are available; distinguish annotated profile evidence from general
  context.

### 4. Stage 9 Constraint Extraction

Stage 9 must consume policy/constraint evidence without treating every
non-executable annotation as a policy.

Required behavior:

- policy/rule/constraint annotations are included as constraint evidence;
- old `routes.rules` remains a fallback for generic NL and no-annotation paths;
- `semantic_role="failure_mode"` is excluded from constraint candidates by
  default, even if the span still appears in `routes.rules` for backward
  compatibility;
- delegation boundary or delegation intent material is included as a constraint
  only when it expresses a boundary rule, not merely an intent to delegate;
- adapter constraint hints remain available, but hints do not override route
  role filtering when the text is clearly a failure condition.

Implementation notes:

- Add a candidate-selection helper rather than embedding ad hoc filtering in the
  prompt string.
- Preserve policy extraction behavior for existing tests.
- Do not create synthetic constraints for failure-mode exception conditions.

### 5. Diagnostics and Warnings

D5 should not invent new compiler diagnostics unless needed for local filtering.
If warnings are added, they must be local and test-covered.

Allowed:

- local resource filter warnings for rejected schema/route metadata variables;
- local comments in prompt context that mark exception conditions as
  non-resource/non-policy context.

Not allowed:

- new missing-handler diagnostics;
- normalizer changes;
- renderer changes;
- bridge deletion or deprecation.

## Required Tests

### Test 1: Resource Contracts Stay Authoritative

Input:

- structural/canonical input with hard-fact input and output variables;
- route annotations for input/output contracts.

Assert:

- `ResourceRegistryIR.variables` contains input and output variables;
- hard-fact type/required/source values win over LLM conflicts;
- no route metadata variable is produced.

### Test 2: Failure Mode Is Not A Resource

Input:

- failure-mode annotation for `Missing timeframe`;
- route-derived exception flow exists;
- LLM attempts to emit variable named `missing_timeframe` or similar.

Assert:

- no variable is created from the failure condition;
- filter warning or prompt guard evidence is present if output filtering is used;
- legitimate resource variables still survive.

### Test 3: Worker-Scoped Resource Extraction Follows D5

Input:

- worker plan with child-owned failure condition and normal child resource;
- worker-scoped Stage 6 path.

Assert:

- failure condition does not become a child variable;
- child resource/contract variables still appear in child scope;
- global hard-fact inputs/outputs are preserved.

### Test 4: Profile Extractor Uses Profile Annotations

Input:

- profile/domain annotation from structural `Task family`;
- unrelated failure-mode and resource-contract annotations.

Assert:

- profile prompt or output uses the profile/domain evidence;
- failure condition does not become persona role;
- no-annotation fallback still uses old identity/audience/domain routes.

### Test 5: Constraint Extractor Excludes Failure Modes

Input:

- `failure_mode` annotation whose span remains in `routes.rules`;
- policy/constraint annotation for a real policy span.

Assert:

- prompt candidates include the policy span;
- prompt candidates exclude the failure-mode span from rules/constraint evidence;
- LLM output sourced only from failure-mode span is rejected or never requested;
- valid policy constraints still survive.

### Test 6: Delegation Boundary Constraint Handling

Input:

- delegation boundary text that expresses an actual rule, such as "Only delegate
  source collection when external sources are required";
- delegation intent text that merely says "delegate research".

Assert:

- boundary rule may become a constraint;
- pure delegation intent does not become a constraint by default;
- worker planning/handoff behavior from D1 remains unchanged.

### Test 7: No Out-Of-Scope Changes

Review and `git diff --name-only` evidence must show:

- no Stage 4/D2/D3 behavior changes;
- no Stage 5/D4 behavior changes;
- no Stage 7/D6 behavior changes;
- no normalizer or renderer migration;
- no bridge deletion/deprecation.

## Acceptance Criteria

D5 is complete when:

- inputs and outputs remain authoritative resource contracts;
- failure modes do not become variables by default;
- failure modes do not become constraints by default;
- profile/domain annotations are consumed by Stage 8;
- policy extraction still works;
- delegation boundary constraints remain available;
- worker-scoped resource extraction follows the same filtering contract;
- no handler block, handler step, recovery action, renderer syntax, or
  normalizer behavior is changed;
- focused D5 tests and the full unit suite pass.

## Required Evidence For Review

When submitting D5 for review, provide:

1. changed files;
2. exact test commands and output summary;
3. sample Stage 6 resource output showing hard-fact input/output preservation;
4. sample failure-mode annotation that does not become a variable;
5. sample Stage 8 profile annotation usage;
6. sample Stage 9 policy span included while failure-mode span is excluded;
7. worker-scoped Stage 6 evidence;
8. confirmation that Stage 4, Stage 5, Stage 7, normalizer, renderer, and bridge
   deletion were not changed.

## PM Review Checklist

- [ ] Resource contracts are authoritative.
- [ ] Failure modes are not variables.
- [ ] Failure modes are not constraints by default.
- [ ] Stage 6 worker-scoped path follows D5.
- [ ] Stage 8 consumes profile/domain annotations.
- [ ] Stage 8 fallback still works without annotations.
- [ ] Stage 9 consumes policy/constraint annotations.
- [ ] Stage 9 excludes failure-mode rule-list leftovers.
- [ ] Delegation boundary rule behavior is covered.
- [ ] No out-of-scope Stage 4/5/7/normalizer/renderer/bridge-deletion work is mixed in.
- [ ] Full unit suite passes.
