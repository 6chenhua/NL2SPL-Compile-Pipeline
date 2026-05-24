# InputAdapter and FieldRoute Semantic Routing Refactor TODO

Date: 2026-05-18

## Purpose

This document defines a gradual correction plan for the current `InputAdapter`
and `FieldRoute` integration.

The target architecture is:

```text
InputAdapter = schema-aware pre-understanding layer
FieldRoute = schema-agnostic semantic routing layer
Later stages = SPL construct / IR generation layer
```

The current implementation already has the right high-level pipeline shape:

```text
raw text
-> InputAdapterRegistry
-> CanonicalCompileInput
-> SpanSlicer
-> FieldRouter
-> worker / flow / block / resource / step / constraint stages
-> SPL renderer and diagnostics
```

However, the responsibilities are not yet clean enough. `InputAdapter` is mostly
aligned with the intended design, while `FieldRoute` remains too thin and cannot
yet serve as the unified semantic routing layer.

This document is a correction plan, not a greenfield redesign. The refactor must
preserve existing pipeline behavior where it is correct, keep compatibility with
current tests, and progressively move semantic responsibility into the right
layer.

## Background

Natural language input can be organized in many ways:

- task background;
- process;
- inputs and outputs;
- policy;
- failure handling;
- delegation rules;
- mixed sentences that contain action, constraint, failure condition, and
  resource references at the same time.

Directly converting such input to SPL is unstable. The compiler needs a stable
intermediate semantic representation before materializing SPL constructs.

`FieldRoute` should be that representation:

```text
raw / adapted spans
-> normalized semantic fields and route annotations
-> stable input for SPL construct generation
```

`InputAdapter` should not replace `FieldRoute`. It should only reduce routing
uncertainty when the input already has known structure.

For structural NL, this means:

```text
raw text
-> InputAdapter parses sections, packets, hard facts, and hints
-> SpanSlicer creates section-aware / packet-aware spans
-> FieldRoute consumes spans plus adapter evidence
-> later stages generate partial or complete SPL IR
```

## Current Implementation Summary

The current implementation already includes several useful pieces:

- `CanonicalCompileInput` with `raw_sections`, `semantic_packets`,
  `hard_facts`, `compile_hints`, `warnings`, and `detection`.
- `StructuralNLAdapter`, which recognizes:
  - `task_family`
  - `inputs_for_each_run`
  - `required_outputs`
  - `reusable_process`
  - `policies`
  - `failure_handling`
  - `delegation_policy`
- `SpanSlicer` canonical path, which creates spans carrying
  `source_section_id` and `source_packet_id`.
- `FieldRouter` canonical path, which deterministically routes adapter-aware
  spans.
- `bridge_failure_modes()`, which converts `FailureModeFact` into partial
  `ExceptionFlow` skeletons without inventing handler commands.
- `bridge_delegation_intents()`, which emits diagnostics for delegation intents
  that lack valid handoff contracts.

These pieces are valuable and should be retained.

## Current Problems

### Problem 1: FieldRouteIR is too shallow

`FieldRouteIR` currently stores only six lists of span ids:

```text
identity
audience
rules
domain
integrations
behavior
```

This is enough for a first-pass classifier, but not enough for compiler-grade
semantic routing. It cannot express:

- semantic role;
- route rationale;
- adapter hint usage;
- construct target;
- slot target;
- packet provenance;
- route diagnostics;
- primary versus secondary routes;
- multi-label spans.

The current `validate_no_overlap()` also treats overlap as suspicious, while the
intended design explicitly allows a span to carry multiple semantic meanings.

### Problem 2: Adapter hints are not first-class routing evidence

For structural input, `FieldRouter._execute_canonical()` mainly routes by
`packet_type`.

It does not properly consume:

- `semantic_packets.compile_targets`;
- `compile_hints.flow_hints`;
- `compile_hints.process_hints`;
- `compile_hints.constraint_hints`;
- `compile_hints.delegation_hints`;
- `hard_facts` as authoritative non-command evidence.

As a result, `InputAdapter` produces useful hints, but `FieldRoute` is not yet
the central place where those hints are interpreted, corrected, or diagnosed.

### Problem 3: Failure handling reaches ExceptionFlow through a bridge, not through routing

The current failure path is approximately:

```text
failure_handling section
-> StructuralNLAdapter.hard_facts.failure_modes
-> failure_mode semantic packet
-> Stage 2 routes failure_mode to rules
-> Stage 4 runs flow assembly
-> bridge_failure_modes() appends partial ExceptionFlow skeletons
```

This prevents accidental command fabrication, which is good.

But semantically, the route is wrong or at least under-specified. A failure mode
is not a normal rule and not a normal action step. It should be represented as:

```text
semantic_role = failure_mode
route_family = flow_relevant
construct_target = EXCEPTION_FLOW
slot_target = condition
executable = false
```

The bridge currently compensates for the missing routing semantics.

### Problem 4: Stage 7 relies on `routes.behavior` as executable candidate input

`StepExtractor` extracts commands from behavior spans. Therefore, naively moving
failure modes into `behavior` would risk producing false commands such as:

```text
COMMAND: Handle missing timeframe
```

Any refactor that makes failure modes flow-relevant must also teach Stage 7 to
skip non-executable behavior-like route annotations.

### Problem 5: Worker-aware path may not receive adapter-derived exception flows

The current failure bridge updates the legacy `FlowStructureIR`. When worker
boundary planning is enabled, the pipeline uses worker-scoped flow plans. The
adapter-derived exception flow skeletons may not be materialized into the
worker-scoped flow path.

The refactor must make failure-mode materialization work consistently for both:

- legacy flow path;
- worker-aware flow path.

### Problem 6: Provenance exists but is not complete enough

`SpanIR` carries section and packet ids, but hard fact evidence often cites only
the section. Later bridge logic resolves span ids by section. This is acceptable
for an MVP, but the target architecture needs stronger evidence chains:

```text
source_section_id
source_packet_id
source_span_ids
quoted_text
```

## System-Wide Impact Inventory

This refactor affects more than `InputAdapter` and `FieldRoute`. Any stage that
currently treats `routes.behavior`, `routes.rules`, or `canonical_input.hard_facts`
as the direct semantic contract must be reviewed.

### Core Data Contracts

Affected files:

- `src/nl2spl/canonical/compile_input.py`
- `src/nl2spl/ir/span_ir.py`
- `src/nl2spl/ir/field_route_ir.py`
- `src/nl2spl/ir/flow_structure_ir.py`
- `src/nl2spl/ir/diagnostics.py`

Required changes:

- add route annotation IR;
- strengthen hint metadata and evidence references;
- keep `source_section_id` and `source_packet_id` available from adapter to
  diagnostics/report;
- avoid encoding route semantics only as six span-id lists.

### Adapter Layer

Affected files:

- `src/nl2spl/adapters/structural_nl.py`
- `src/nl2spl/adapters/generic_nl.py`
- `src/nl2spl/adapters/llm_engine.py`
- `src/nl2spl/adapters/fact_verifier.py`

Required changes:

- structural adapter should emit stronger compile hints for:
  - failure modes;
  - delegation intents;
  - input/output contracts;
  - policies;
  - process steps;
- failure-mode hints must identify `EXCEPTION_FLOW.condition`;
- delegation hints must remain non-executable until a valid contract exists;
- fact verifier should preserve packet-level evidence when available.

### Stage 1: SpanSlicer

Affected file:

- `src/nl2spl/pipeline/stages/stage1_span_slicer.py`

Required changes:

- keep packet-aware span generation;
- preserve packet and section provenance when spans are split later;
- optionally expose packet metadata needed by route annotations.

Expected change level: small.

### Stage 2: FieldRouter

Affected file:

- `src/nl2spl/pipeline/stages/stage2_field_router.py`

Required changes:

- add annotation-producing canonical routing;
- consume semantic packets, hard facts, and compile hints together;
- generate route diagnostics;
- keep legacy six-field lists for compatibility;
- no longer route `failure_mode` as ordinary `rules`;
- mark failure modes as flow-relevant, non-executable exception condition
  candidates.

Expected change level: high.

### Stage 3: AmbiguityResolver

Affected file:

- `src/nl2spl/pipeline/stages/stage3_ambiguity_resolver.py`

Current risk:

- ambiguous span splitting currently rebuilds `FieldRouteIR` from six lists and
  drops adapter provenance and any future route annotations.

Required changes:

- when a span is split, propagate:
  - `source_section_id`;
  - `source_packet_id`;
  - parent route annotations;
  - semantic role where still applicable;
- if split output changes route semantics, update annotations rather than only
  updating old field lists.

Expected change level: medium.

### Stage 3.5: WorkerBoundaryPlanner

Affected files:

- `src/nl2spl/pipeline/stages/stage3_5_worker_boundary_planner/executor.py`
- `src/nl2spl/pipeline/stages/stage3_5_worker_boundary_planner/prompt_builder.py`
- `src/nl2spl/pipeline/stages/stage3_5_worker_boundary_planner/materializer.py`

Current risk:

- worker planning is driven by `routes.behavior`;
- if failure modes become flow-relevant behavior-like annotations, they could
  be incorrectly assigned as worker-owned executable work;
- materializer recovers contracts from hard facts, which is useful but should
  not become a second routing system.

Required changes:

- candidate extraction must use executable behavior candidates, not all
  behavior-like annotations;
- failure condition annotations should be available as context, not worker task
  candidates;
- delegation intent annotations should inform boundary decisions but must not
  directly create executable workers without contracts;
- worker ownership must include flow condition spans where needed for exception
  flow placement, without treating them as step candidates.

Expected change level: high.

### Stage 4: FlowAssembler

Affected files:

- `src/nl2spl/pipeline/stages/stage4_flow_assembler/executor.py`
- `src/nl2spl/pipeline/stages/stage4_flow_assembler/flow_parser.py`
- `src/nl2spl/pipeline/stages/stage4_flow_assembler/span_filter.py`
- `src/nl2spl/pipeline/stages/stage4_flow_assembler/irs_checker.py`

Current risk:

- flow assembly currently reads `routes.behavior`;
- adapter failure modes are appended after Stage 4 by `bridge_failure_modes()`;
- worker-aware span filtering may drop exception condition spans if they are not
  owned behavior spans.

Required changes:

- assemble main flow from executable behavior candidates;
- materialize exception flows from route annotations targeting
  `EXCEPTION_FLOW.condition`;
- dedupe LLM-generated and route-derived exception flows;
- support route-derived exception flows in worker-aware `WorkerFlowPlanIR`;
- preserve `ExceptionFlow.spans` for provenance and missing-handler diagnostics.

Expected change level: high.

### Stage 5: BlockAssembler

Affected files:

- `src/nl2spl/pipeline/stages/stage5_block_assembler/executor.py`
- `src/nl2spl/pipeline/stages/stage5_block_assembler/prompt_enricher.py`
- `src/nl2spl/pipeline/stages/stage5_block_assembler/block_postprocess.py`

Current risk:

- block assembly receives exception flows but has no route semantics;
- partial exception flows with condition-only spans may need deterministic
  fallback blocks if the LLM does not create exception flow blocks.

Required changes:

- ensure every route-derived exception flow can render as a partial skeleton;
- avoid requiring a handler block for partial exception flows;
- in worker-aware mode, preserve worker-scoped exception flow blocks.

Expected change level: medium.

### Stage 6: ResourceExtractor

Affected files:

- `src/nl2spl/pipeline/stages/stage6_resource_extractor/legacy.py`
- `src/nl2spl/pipeline/stages/stage6_resource_extractor/worker_scoped.py`
- `src/nl2spl/pipeline/stages/stage6_resource_extractor/context_builder.py`
- `src/nl2spl/pipeline/stages/stage6_resource_extractor/resource_name_filter.py`

Current risk:

- resource extraction reads `routes.behavior` and `routes.integrations`;
- hard-fact inputs/outputs are merged separately from routing;
- exception conditions are visible through flow summary, but not through route
  annotations.

Required changes:

- treat input/output hard facts as authoritative contract resources;
- exclude non-executable failure condition spans from variable extraction unless
  they mention concrete resources;
- include route annotation summaries in resource context;
- keep resource name filter blocking compiler schema terms such as
  `source_section_id`, `source_packet_id`, and `exception_flows`.

Expected change level: medium.

### Stage 7: StepExtractor

Affected files:

- `src/nl2spl/pipeline/stages/stage7_step_extractor/extractor.py`
- `src/nl2spl/pipeline/stages/stage7_step_extractor/worker_scoped.py`
- `src/nl2spl/pipeline/stages/stage7_step_extractor/irs_checker.py`
- `src/nl2spl/pipeline/stages/stage7_step_extractor/legacy.py`

Current risk:

- Stage 7 uses `routes.behavior` as executable step input;
- source-backed non-executable failure conditions could become
  `GENERAL_COMMAND` if they enter behavior without an executable flag;
- worker-scoped Stage 7 also intersects `routes.behavior` with flow spans.

Required changes:

- select executable step candidates via route helper methods;
- skip annotations with `executable = false`;
- avoid unmapped behavior diagnostics for skipped non-executable semantic
  material;
- keep handoff-generated `INVOKE_WORKER` / `CALL_API` logic contract-driven;
- ensure `REQUEST_INPUT` is generated only from explicit ask/request evidence,
  not from missing failure handler assumptions.

Expected change level: high.

### Stage 8: ProfileExtractor

Affected file:

- `src/nl2spl/pipeline/stages/stage8_profile_extractor.py`

Current risk:

- profile extraction reads `routes.identity`, `routes.audience`, and
  `routes.domain`;
- structural `task_family` currently maps to domain, while adapter profile
  hints may carry richer persona/domain intent.

Required changes:

- optionally prefer route annotations with profile/domain semantic roles;
- keep old field lists as fallback;
- avoid using failure or policy annotations as profile concepts unless explicitly
  routed as domain context.

Expected change level: low to medium.

### Stage 9: ConstraintExtractor

Affected file:

- `src/nl2spl/pipeline/stages/stage9_constraint_extractor.py`

Current risk:

- constraint extraction reads only `routes.rules`;
- `failure_mode` is currently routed to rules, so changing failure routing may
  remove failure text from the constraint prompt;
- delegation boundary is currently represented partly as constraint hints.

Required changes:

- use route annotations for constraint candidates;
- keep policy spans as rules;
- treat delegation boundaries as constraints only when they express boundaries,
  not executable delegation;
- do not treat failure mode conditions as ordinary policy constraints unless
  the text explicitly states a policy.

Expected change level: medium.

### Stage 9.5: Normalizer

Affected files:

- `src/nl2spl/pipeline/stages/stage9_5_normalizer/normalizer.py`
- `src/nl2spl/pipeline/stages/stage9_5_normalizer/normalization.py`
- `src/nl2spl/pipeline/stages/stage9_5_normalizer/worker_scoped.py`
- `src/nl2spl/pipeline/stages/stage9_5_normalizer/flow_classification.py`
- `src/nl2spl/pipeline/stages/stage9_5_normalizer/worker_handoffs.py`

Current risk:

- missing-handler logic is mostly correct, but it sees only the resulting
  exception flows and steps;
- pseudo-handler detection must remain the guard against LLM restating a
  condition as a handler;
- worker-scoped normalization must diagnose route-derived exception flows too.

Required changes:

- preserve missing-handler diagnostics for route-derived exception flows;
- ensure pseudo-handler filtering applies when condition spans and handler spans
  overlap;
- ensure worker-scoped exception flows get scoped diagnostics;
- avoid normalizer inventing output producers or handler steps.

Expected change level: medium.

### Stage 10: WorkerAssembler

Affected files:

- `src/nl2spl/pipeline/stages/stage10_worker_assembler/assembler.py`
- `src/nl2spl/pipeline/stages/stage10_worker_assembler/child_worker_builder.py`

Current risk:

- assembler already carries exception flows into `WorkerIR`, but depends on
  Stage 4/5 preserving the flows and blocks;
- worker-aware assembly builds main and child exception flows from worker-scoped
  flow/block plans.

Required changes:

- no major semantic rewrite, but add tests proving route-derived exception flows
  render in main and child workers;
- ensure condition-only exception flows remain renderable partial structures.

Expected change level: low to medium.

### Executable Gate

Affected file:

- `src/nl2spl/pipeline/executable_gate.py`

Current risk:

- gate filters steps, not route annotations;
- it diagnoses handlers filtered after gate, but does not know whether a
  condition originated from route annotations.

Required changes:

- keep filtering executable steps;
- preserve route-derived missing-handler diagnostics after assumed handlers are
  blocked;
- optionally include route/provenance metadata in gate diagnostics.

Expected change level: low.

### Stage 11: SPLRenderer

Affected files:

- `src/nl2spl/pipeline/stages/stage11_spl_renderer/renderer.py`
- `src/nl2spl/pipeline/stages/stage11_spl_renderer/block_renderer.py`

Current risk:

- renderer already renders exception flow skeletons;
- it does not know route annotations and should not need to if upstream IR is
  correct.

Required changes:

- mostly test coverage;
- ensure empty exception-flow blocks still render a legal partial
  `EXCEPTION_FLOW` skeleton;
- ensure child worker exception flows render consistently.

Expected change level: low.

### Provenance and Reports

Affected files:

- `src/nl2spl/pipeline/provenance.py`
- `src/nl2spl/compiler/report_renderer.py`
- `src/nl2spl/compiler/feedback_report_renderer.py`
- `src/nl2spl/compiler/diagnostic_analyzer.py`
- `src/nl2spl/compiler/assumptions.py`

Current risk:

- provenance resolves from `source_span_ids` and hard facts;
- route annotations are not yet traceable objects;
- diagnostics may lose packet-level evidence if hard facts only cite sections.

Required changes:

- trace route-derived exception flows to section, packet, and span evidence;
- trace non-executable delegation intents without rendering executable SPL;
- include route diagnostics in reports;
- avoid duplicate missing-handler diagnostics from normalizer, diagnostic
  analyzer, and gate.

Expected change level: medium.

### Orchestrator

Affected file:

- `src/nl2spl/pipeline/orchestrator.py`

Current risk:

- orchestrator directly calls `bridge_failure_modes()` after Stage 4;
- orchestrator directly calls `bridge_delegation_intents()` during diagnostics;
- behavior span ownership repair uses `resolved_routes.behavior`;
- canonical hard facts are passed to several stages as side-channel evidence.

Required changes:

- route-derived materialization should happen before or inside Stage 4 output
  finalization;
- bridge calls should become guarded compatibility fallbacks, then be removed;
- ownership repair should use executable behavior route helpers;
- final diagnostics should include route diagnostics.

Expected change level: high.

### Tests and Fixtures

Affected areas:

- `tests/unit/test_field_router.py`
- `tests/unit/test_input_adapter_pipeline.py`
- `tests/unit/test_failure_mode_bridge.py`
- `tests/unit/test_flow_assembler.py`
- `tests/unit/test_step_extractor.py`
- `tests/unit/pipeline/stages/test_stage3_5_worker_boundary_planner.py`
- `tests/unit/pipeline/stages/test_stage7_worker_scoped.py`
- `tests/integration/test_partial_spl_mvp.py`
- `tests/integration/test_v5_irs_pipeline.py`
- `tests/integration/test_llm_adapter_engine_e2e.py`
- example intermediate JSON under `examples/output`

Required changes:

- add route annotation tests while keeping old field-list tests;
- migrate bridge tests to route-driven materializer tests;
- add worker-aware failure-mode regression tests;
- update fixtures that assume failure modes live in `routes.rules`;
- add anti-fabrication tests for failure modes, delegation intents, and
  hard-fact input/output contracts.

## Target Design

### Target Pipeline

```text
Generic NL:
    raw_text
    -> GenericNLAdapter
    -> CanonicalCompileInput
    -> SpanSlicer
    -> FieldRoute
    -> construct generation

Structural NL:
    raw_text
    -> StructuralNLAdapter
    -> CanonicalCompileInput
    -> packet-aware SpanSlicer
    -> hint-aware FieldRoute
    -> construct generation
```

All inputs should pass through the same canonical routing and compile pipeline.

### Target `InputAdapter` Responsibility

`InputAdapter` should:

- detect known input schema;
- parse sections;
- create semantic packets;
- extract deterministic hard facts;
- produce compile hints;
- preserve provenance;
- emit adapter warnings.

`InputAdapter` must not:

- generate SPL;
- generate final Flow/Step/Worker/Constraint IR;
- decide worker boundaries;
- fabricate missing handlers;
- convert delegation intent directly into executable invocation.

### Target `FieldRoute` Responsibility

`FieldRoute` should:

- classify spans and packets into normalized semantic fields;
- consume adapter evidence as routing priors;
- allow one span to have multiple semantic annotations;
- preserve section, packet, and span provenance;
- distinguish executable action candidates from non-executable semantic
  material;
- record diagnostics when adapter hints and content conflict;
- provide stable input to later construct generation.

`FieldRoute` must not:

- generate SPL;
- create final `ExceptionFlow`, `StepIR`, or `WorkerIR`;
- silently turn hard facts into commands;
- discard source-backed material because it is incomplete.

### Target Failure Handling Semantics

Structural NL:

```text
Failure handling:
Missing timeframe, conflicting instructions, insufficient source access.
```

should become:

```text
SemanticPacket:
    packet_type = failure_mode
    modality = hard_fact
    compile_targets = ["flow.exception.condition"]

HardFacts:
    failure_modes = [
        "Missing timeframe",
        "conflicting instructions",
        "insufficient source access"
    ]

CompileHint:
    route_family = flow_relevant
    construct_target = EXCEPTION_FLOW
    slot_target = condition
    executable = false
```

Then `FieldRoute` should produce route annotations such as:

```text
span_id = s7
primary_field = behavior
semantic_role = failure_mode
route_family = flow_relevant
construct_target = EXCEPTION_FLOW
slot_target = condition
executable = false
source_section_id = sec_failure_handling
source_packet_id = p_failure_mode_missing_timeframe
```

Later flow materialization can create a partial exception flow:

```text
[EXCEPTION_FLOW: Missing timeframe]
    # no invented handler
[END_EXCEPTION_FLOW]
```

and diagnostics should report:

```text
missing_handler: Failure condition exists but no handler action was provided.
```

## Refactor Principles

1. Keep `CanonicalCompileInput` as the single adapter output.
2. Preserve current adapter behavior unless a change is required for stronger
   provenance or clearer hints.
3. Extend `FieldRouteIR` compatibly; do not remove the six existing fields in
   the first phase.
4. Make route annotations additive first, then migrate stages to consume them.
5. Keep hard facts authoritative for resource contracts and failure conditions.
6. Never route hard facts into executable commands unless source text explicitly
   contains an action.
7. Support partial SPL and diagnostics instead of fabricating missing slots.
8. Keep legacy and worker-aware paths behaviorally aligned.

## Proposed Route Model

Introduce a new route annotation model while preserving the old lists:

```python
@dataclass
class RouteAnnotation:
    span_id: str
    field: str
    semantic_role: str | None = None
    route_family: str | None = None
    source_section_id: str | None = None
    source_packet_id: str | None = None
    source_hint_ids: list[str] = field(default_factory=list)
    construct_target: str | None = None
    slot_target: str | None = None
    executable: bool = True
    primary: bool = True
    diagnostics: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
```

Extend `FieldRouteIR`:

```python
@dataclass
class FieldRouteIR:
    identity: list[str] = field(default_factory=list)
    audience: list[str] = field(default_factory=list)
    rules: list[str] = field(default_factory=list)
    domain: list[str] = field(default_factory=list)
    integrations: list[str] = field(default_factory=list)
    behavior: list[str] = field(default_factory=list)
    annotations: list[RouteAnnotation] = field(default_factory=list)
```

Compatibility rules:

- existing stages may continue reading `routes.behavior`, `routes.rules`, etc.;
- new stages should prefer `routes.annotations`;
- helper APIs should expose:
  - `get_annotations(span_id)`;
  - `get_executable_behavior_span_ids()`;
  - `get_flow_condition_span_ids()`;
  - `get_annotations_by_construct("EXCEPTION_FLOW")`.

## Phased Plan

## Phase 0: Baseline and Safety Net

### Goal

Capture current behavior before changing routing semantics.

### Tasks

1. Add focused baseline tests for structural NL:
   - inputs and outputs are hard facts;
   - failure modes become `FailureModeFact`;
   - failure mode spans currently do not become commands;
   - partial `EXCEPTION_FLOW` is generated when no handler exists;
   - delegation intent does not render `INVOKE_WORKER` without a contract.
2. Add a worker-aware regression test showing current behavior for failure
   modes with `enable_worker_boundary_planner=True`.
3. Record current expected intermediate outputs for:
   - `canonical_input`;
   - Stage 1 spans;
   - Stage 2 routes;
   - Stage 4 flow;
   - diagnostics.

### Acceptance Criteria

- Baseline tests run locally and document current behavior.
- No production code behavior changes in this phase.
- Known gaps are marked explicitly as expected failures or TODO tests.

## Phase 1: Strengthen Adapter Hints and Evidence

### Goal

Make adapter output express the intended semantics clearly enough for
FieldRoute to consume later.

### Tasks

1. Extend `CompileHint` usage for failure modes:
   - `target = "EXCEPTION_FLOW"`;
   - `suggested_condition = failure text`;
   - `metadata["route_family"] = "flow_relevant"`;
   - `metadata["slot_target"] = "condition"`;
   - `metadata["executable"] = False`.
2. Update `failure_mode` semantic packets:
   - `compile_targets = ["flow.exception.condition"]`.
3. Add packet-level evidence refs for hard facts where possible:
   - `source_section_id`;
   - `source_packet_id`;
   - `quoted_text`.
4. Add similar hint metadata for delegation:
   - `route_family = "delegation_boundary"`;
   - `executable = False` unless a concrete handoff contract exists.
5. Update canonical validator if needed to verify hint evidence consistency.

### Acceptance Criteria

- `StructuralNLAdapter` output for `Failure handling` includes condition-level
  hints.
- Each failure mode hard fact has traceable section evidence and, where
  available, packet evidence.
- Existing adapter tests still pass.
- No SPL rendering behavior changes are required yet.

## Phase 2: Add RouteAnnotation Without Changing Stage Behavior

### Goal

Introduce richer route semantics while preserving existing field lists.

### Tasks

1. Add `RouteAnnotation` to the IR package.
2. Extend `FieldRouteIR` with `annotations`.
3. Add helper methods:
   - `get_annotations(span_id)`;
   - `get_primary_field(span_id)`;
   - `get_executable_behavior_span_ids()`;
   - `get_non_executable_flow_condition_span_ids()`;
   - `get_construct_slot_candidates(construct, slot)`.
4. Keep `identity`, `rules`, `behavior`, etc. unchanged for compatibility.
5. Update serialization/checkpoints to include annotations.
6. Add tests for:
   - old list fields still work;
   - annotations can represent multiple semantic roles;
   - `validate_no_overlap()` no longer blocks annotation-level multi-label
     semantics.

### Acceptance Criteria

- All existing callers of `FieldRouteIR` continue working.
- New annotation tests pass.
- Checkpoints include annotation data.
- No stage has to consume annotations yet.

## Phase 3: Make FieldRouter Consume Adapter Evidence

### Goal

Turn `FieldRouter` canonical path into a hint-aware semantic router.

### Tasks

1. Build indexes in `FieldRouter._execute_canonical()`:
   - packet by id;
   - section by id;
   - hints by section;
   - hints by packet where evidence exists;
   - hard facts by section / packet.
2. Route by semantic priority:
   - hard fact resource contracts first;
   - failure modes as flow condition candidates;
   - process steps as executable behavior candidates;
   - policies as rules;
   - delegation intents as non-executable delegation boundary candidates;
   - task family as domain/profile context.
3. Generate `RouteAnnotation` for every routed span.
4. Preserve old field lists from annotation primary fields.
5. Add route diagnostics for conflicts:
   - adapter says policy but text looks like executable action;
   - adapter says failure mode but text includes explicit handler action;
   - section says delegation but no worker contract exists.
6. Keep generic NL path compatible with legacy LLM routing, but optionally add
   simple annotations derived from LLM route fields.

### Acceptance Criteria

- Structural failure modes produce annotations:
  - `semantic_role = "failure_mode"`;
  - `construct_target = "EXCEPTION_FLOW"`;
  - `slot_target = "condition"`;
  - `executable = False`.
- Runtime inputs and required outputs are not routed as executable behavior.
- Policies route to rules with constraint annotations.
- Delegation policy routes to non-executable delegation annotations.
- Existing Stage 2 tests pass after updating expected route metadata.

## Phase 4: Protect Stage 7 From Non-Executable Semantic Material

### Goal

Ensure richer routing does not create fabricated commands.

### Tasks

1. Update `StepExtractor` to select executable behavior spans using
   `routes.get_executable_behavior_span_ids()` when annotations are available.
2. Keep fallback behavior for legacy `FieldRouteIR` without annotations.
3. Add explicit skip diagnostics for non-executable route annotations only when
   useful for debugging, not as user-facing compile warnings.
4. Add tests:
   - `failure_mode` route in behavior/flow-relevant family does not produce a
     `GENERAL_COMMAND`;
   - `delegation_policy` without handoff contract does not produce
     `INVOKE_WORKER`;
   - ordinary process steps still produce command candidates.

### Acceptance Criteria

- `Missing timeframe` is never emitted as `COMMAND: Handle missing timeframe`
  unless the source explicitly provides a handler action.
- Stage 7 unmapped behavior diagnostics do not fire for non-executable failure
  condition spans.
- Existing normal behavior extraction still works.

## Phase 5: Move Failure Materialization Into Flow Construction

### Goal

Make `EXCEPTION_FLOW` creation consume route annotations rather than bypassing
FieldRoute through a separate hard-fact bridge.

This phase is the first downstream migration phase. The intent is not only to
add a better path, but to start moving semantic ownership out of
`pipeline.fact_bridges` and into the normal route -> flow construction path.

### Tasks

1. Create a flow materialization helper that consumes:
   - `RouteAnnotation(construct_target="EXCEPTION_FLOW", slot_target="condition")`;
   - `FailureModeFact` as fallback evidence.
2. Use the helper inside or immediately adjacent to Stage 4.
3. Keep `bridge_failure_modes()` as a compatibility wrapper during migration.
4. Generate partial `ExceptionFlow` skeletons without handlers.
5. Preserve existing LLM-generated exception flows and dedupe by normalized
   condition text.
6. Ensure route annotation provenance flows into `ExceptionFlow.spans`.

### Acceptance Criteria

- Failure modes are materialized from FieldRoute annotations.
- If annotations are missing but hard facts exist, fallback still works.
- No duplicate exception flows for the same condition.
- Missing handler diagnostics still fire through IRS/normalizer path.
- Existing failure bridge tests pass or are migrated to the new helper.

### Downstream Migration Notes

The current orchestrator applies failure bridging after Stage 4:

```text
Stage 4 FlowAssembler
-> bridge_failure_modes()
-> Stage 4 IRS check
-> Stage 5 BlockAssembler
```

After this phase, the intended flow should become:

```text
Stage 2 FieldRoute annotations
-> Stage 4 FlowAssembler / flow materializer
-> Stage 4 IRS check
-> Stage 5 BlockAssembler
```

`bridge_failure_modes()` should remain temporarily, but only as a compatibility
fallback for inputs or tests that do not yet provide route annotations.

The orchestrator should stop treating `canonical_input.hard_facts.failure_modes`
as the primary materialization source once route annotations are available.

## Phase 6: Support Worker-Aware Exception Flow Materialization

### Goal

Make adapter-derived failure modes work in both legacy and worker-aware paths.

### Tasks

1. Determine ownership for failure condition spans:
   - if a failure condition span is owned by a worker, attach the exception flow
     to that worker;
   - if it is global and no worker owns it, attach to main worker or emit a
     diagnostic depending on worker plan semantics.
2. Extend worker-scoped flow plan materialization to include adapter-derived
   exception flows.
3. Ensure worker-scoped Stage 5/10/11 can render partial exception flows.
4. Add diagnostics when failure condition ownership is ambiguous.

### Acceptance Criteria

- With `enable_worker_boundary_planner=True`, structural failure modes still
  produce partial exception flows.
- Exception flow provenance points back to `sec_failure_handling` and the
  packet/span ids.
- No failure condition is silently dropped during worker scoping.
- Worker-aware and legacy outputs are semantically consistent.

### Downstream Migration Notes

This phase must update downstream worker-aware code, not only front-end routing.

Affected areas include:

- `WorkerBoundaryPlanner`, because behavior ownership currently drives worker
  scoped flow construction.
- `FlowAssembler._execute_worker_aware()`, because it currently filters by
  `routes.behavior`.
- worker-scoped Stage 5 and Stage 10, because exception flows must remain
  attached to the correct worker until rendering.
- renderer and provenance aggregation, because partial exception flows need
  trace records just like legacy flows.

Do not delete bridge compatibility before this phase is complete. Otherwise the
legacy path may pass while the worker-aware path silently drops failure modes.

## Phase 7: Route Diagnostics and Conflict Handling

### Goal

Make FieldRoute correction behavior visible and auditable.

### Tasks

1. Add structured route diagnostics or map route diagnostics into existing
   `CompileDiagnostic`.
2. Detect at least these cases:
   - section hint conflicts with text content;
   - hard fact is being interpreted as executable action;
   - failure mode includes condition but no handler;
   - delegation intent lacks valid contract;
   - input/output contract lacks producer or consumer where required.
3. Ensure diagnostics include:
   - `source_span_ids`;
   - `source_section_id` where available;
   - `source_packet_id` where available;
   - suggested resolution.
4. Add readable report rendering for route-level diagnostics if not already
   covered downstream.

### Acceptance Criteria

- Route conflicts are visible in `PipelineResult.diagnostics` or equivalent
  intermediate diagnostics.
- Diagnostics do not block rendering unless the missing slot makes rendering
  impossible.
- No diagnostic is emitted for source-backed partial structures merely because
  they are partial.

## Phase 8: Deprecate Bridge-Centric Semantics

### Goal

Remove or downgrade bridge logic once route-driven materialization is stable.

### Tasks

1. Audit all uses of:
   - `bridge_failure_modes()`;
   - `bridge_delegation_intents()`;
   - hard-fact-only materialization paths.
2. Replace orchestrator-level failure bridging with route-driven flow
   materialization:
   - remove direct post-Stage-4 calls that use
     `canonical_input.hard_facts.failure_modes` as the primary source;
   - keep a guarded fallback only when route annotations are absent.
3. Move bridge tests to the new route-driven materializer tests:
   - condition-only failure mode creates partial `ExceptionFlow`;
   - duplicate condition deduplication still works;
   - missing handler diagnostic still appears;
   - section / packet / span provenance is preserved.
4. Keep bridges only as compatibility adapters, diagnostic helpers, or test
   fixtures during one release window.
5. Add deprecation comments to bridge wrappers:
   - state the replacement API;
   - state the removal condition;
   - state which tests prove replacement coverage.
6. Delete bridge wrappers only after legacy and worker-aware route-driven tests
   cover all bridge behavior.
7. Update docs to state that FieldRoute annotations are the primary semantic
   contract for later stages.
8. Remove duplicated failure/delegation logic where safe.

### Acceptance Criteria

- Failure and delegation semantics are not split across unrelated pipeline
  locations.
- Later stages can explain their decisions from route annotations and
  provenance.
- `bridge_failure_modes()` is either removed or has no production call sites
  except a guarded compatibility fallback.
- `bridge_delegation_intents()` is either removed or reduced to diagnostic
  compatibility, with route annotations as the primary evidence source.
- Bridge wrappers have clear TODO or deprecation comments until removed.

## Bridge Deletion Strategy

Bridge deletion must be planned, not immediate.

### Keep Temporarily

Keep `bridge_failure_modes()` while:

- Stage 4 cannot yet materialize exception flows from route annotations;
- worker-aware flow materialization is incomplete;
- existing tests still assert bridge behavior directly.

Keep `bridge_delegation_intents()` while:

- delegation annotations do not yet feed diagnostics directly;
- worker handoff contract validation still depends on post-hoc hard fact scans.

### Convert To Compatibility Wrappers

Once route annotations are available, bridges should become thin wrappers:

```text
hard facts
-> synthesize route annotations if missing
-> call route-driven materializer / diagnostic analyzer
```

This keeps old callers working while ensuring only one semantic implementation
exists.

### Delete Or Restrict

Delete or restrict bridge code only when:

- route-driven legacy tests pass;
- route-driven worker-aware tests pass;
- diagnostics and provenance match or improve on bridge-era behavior;
- no production orchestrator path depends on bridge-first semantics;
- docs and examples use route annotations as the canonical path.

If deletion is too risky, move the wrappers to a compatibility module and mark
them as deprecated. They should not be the primary semantic path.

## Phase 9: Documentation and Migration Cleanup

### Goal

Make the new architecture understandable and enforceable.

### Tasks

1. Update InputAdapter docs to clarify:
   - adapter emits evidence and hints;
   - adapter does not decide final constructs.
2. Update pipeline architecture docs to clarify:
   - FieldRoute is the unified semantic routing layer;
   - route annotations are the contract between front-end understanding and
     construct generation.
3. Add examples:
   - structural input with failure handling;
   - structural input with delegation policy;
   - mixed freeform sentence containing action and policy;
   - input/output contract without producer.
4. Add migration notes for downstream stage authors.

### Acceptance Criteria

- Docs describe the same behavior that tests enforce.
- New developers can identify where to add a new semantic role.
- Existing examples are updated or annotated with expected partial diagnostics.

## End-State Acceptance Criteria

The full refactor is complete when all of the following are true:

1. All input formats pass through `CanonicalCompileInput`, `SpanSlicer`, and
   `FieldRoute`.
2. `InputAdapter` never directly generates final SPL IR.
3. `FieldRoute` consumes adapter hints and hard facts as evidence, not as
   unquestionable final decisions.
4. `FieldRouteIR` can represent semantic role, construct target, slot target,
   executable/non-executable status, and provenance.
5. A failure mode such as `Missing timeframe` becomes an
   `EXCEPTION_FLOW.condition` candidate, not a command.
6. Missing failure handlers produce partial SPL plus diagnostics, not fabricated
   handlers.
7. Inputs and outputs remain resource contracts, not ordinary behavior.
8. Delegation policy remains a delegation intent or boundary until a valid
   handoff contract exists.
9. Legacy and worker-aware paths both preserve adapter-derived failure semantics.
10. Provenance can trace generated SPL elements and diagnostics back to section,
    packet, and span evidence.

## Suggested Work Order

Recommended implementation order:

```text
Phase 0 -> Phase 1 -> Phase 2 -> Phase 3 -> Phase 4
```

At that point, the most important semantic correction is in place. Then continue:

```text
Phase 5 -> Phase 6 -> Phase 7
```

Finally clean up:

```text
Phase 8 -> Phase 9
```

Do not start Phase 8 until Phases 5 and 6 have regression coverage for both
legacy and worker-aware paths.

## Risk Assessment

### Low Risk

- Strengthening adapter hints.
- Adding route annotations compatibly.
- Adding tests and diagnostics.

### Medium Risk

- Changing Stage 7 executable span selection.
- Moving failure materialization closer to Stage 4.
- Updating checkpoint schemas.

### High Risk

- Worker-aware exception flow ownership.
- Removing bridge logic too early.
- Allowing multi-label route semantics without updating downstream consumers.

## Non-Goals

This refactor does not attempt to:

- redesign SPL grammar;
- replace IRS;
- replace worker boundary planning;
- introduce confidence scores;
- require all routing to be LLM-based;
- make incomplete input compile as complete SPL.

## Implementation Status (as of 2026-05-24)

All 15 phases (F0-F4 + D0-D8) plus the adapter-guided LLM FieldRoute refinement
group (Steps 01-05) have been implemented and approved:

- **F0-F4**: Frontend semantic contract — RouteAnnotation IR, hint-aware FieldRouter, annotation-aware AmbiguityResolver.
- **D0**: Downstream baseline and route helper adoption.
- **D1**: WorkerBoundaryPlanner annotation migration.
- **D2**: FlowAssembler route-driven exception materialization + condition-backed guard.
- **D3**: Worker-aware exception flow migration.
- **D4**: BlockAssembler partial skeleton support.
- **D5**: Resource, profile, constraint consumers made annotation-aware.
- **D6**: StepExtractor executable filtering (failure/delegation/api_candidate non-executable → no command).
- **D7**: Normalizer, gate, renderer, provenance.
- **D8**: Bridge deprecation (compatibility fallback only).

Adapter-Guided LLM FieldRoute Refinement (2026-05-24):
- Step 01: Baseline gap tests (4 baseline-current + 4 target, 1370 passed)
- Step 02: Prompt and schema contract
- Step 03: FieldRouter LLM refinement path (default enabled)
- Step 04: Validator and merge (11 rules)
- Step 05: Downstream alignment regression (Stage 4/7/9/worker-aware guards)

Final full unit test suite: **1375 passed, 0 xfailed**.

## Residual Work Register

1. **Full bridge deletion**: Failure and delegation bridges can be deleted once generic NL
   inputs have route annotation coverage (currently bridges are compatibility fallbacks).

2. **Stage 6 resource name filter hardening**: Could consume route annotations directly
   instead of text matching.

