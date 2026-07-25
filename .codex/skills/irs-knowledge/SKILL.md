---
name: irs-knowledge
description: >
  IRS (Information Requirements Specification) concepts, design patterns,
  coding rules, checker extension guidance, diagnostic projection,
  construct-level repair strategy declarations, frontier and cutline semantics for NL2SPL.
---

# IRS Knowledge Skill

## Required Post-Creation Audit

After creating or modifying any ConstructIRS, run audit-irs-contract.
Do not rely on this creation skill as the final completeness gate.

    python .agents/skills/audit-irs-contract/scripts/audit_irs_contract.py \
      --construct CONSTRUCT_TYPE --scope all --format json


IRS = **Information Requirements Specification**. IRS checker / runner
executes satisfaction analysis over source-demanded or materialized SPL
constructs.

IRS is construct-centered. It is not a general diagnostic framework and not a
place to register arbitrary route labels, planner records, or diagnostic names.

IRS does not parse raw NL, call LLMs, render SPL, modify IR, generate new
constructs, or fill missing slots.

## Current Package Boundaries

Use the v2 package owners for new imports:

- construct domain specs, satisfaction reports, graph schema, and default
  construct registry: `nl2spl.compiler.constructs`
- pure repair linkage metadata: `nl2spl.compiler.repair_contracts`
- diagnostic specs, registry, consolidator, and IRS-neutral authority DTOs:
  `nl2spl.compiler.diagnostics`
- IRS runtime context, checker, runner, projector, result store, and traversal:
  `nl2spl.compiler.irs`
- human-readable feedback and report rendering:
  `nl2spl.compiler.reporting`
- deterministic cross-layer IRS contract audit backend:
  `nl2spl.compiler.architecture_audit`

Legacy paths such as `nl2spl.compiler.construct_registry`,
`nl2spl.compiler.irs.graph`, `nl2spl.compiler.irs.frontier`,
`nl2spl.compiler.irs.patch_type_meta`, `nl2spl.compiler.irs.feedback_projector`,
and `nl2spl.compiler.irs.audit` are compatibility shims. Do not introduce new
production imports through those paths.

## Core Concept

Use this mental model:

```text
SPL grammar construct
+ requirement semantics
+ compiler materialization policy
-> ConstructIRS

source evidence / planner IR / stage IR
-> IRS construct instance
-> slot satisfaction
-> ConstructSatisfactionReport
-> DiagnosticProjector
-> CompileDiagnostic
```

IRS answers one question:

```text
For this construct instance, are the information slots required by its
ConstructIRS satisfied by structured evidence?
```

It must not answer these different questions directly:

- should the compiler invent or repair missing content?
- should a route annotation become a new construct type?
- should a planner demand be materialized?
- should a diagnostic kind exist?
- should final SPL rendering be allowed globally?

## Runtime Shape

```text
stage IR
  -> IRSCheckContext
  -> IRSSubsystem.run_stage_local(stage_name, context)
  -> IRSRunner
  -> IRSChecker.extract_instances()
  -> IRSChecker.check_instance()
  -> ConstructSatisfactionReport
  -> DiagnosticProjector
  -> CompileDiagnostic
  -> IRSResultStore
  -> intermediate["construct_satisfaction"][stage]
  -> intermediate["stage_local_diagnostics"][stage]
```

Post-normalize IRS is the final construct-level authority. It is not the final
authority for every global consistency concern:

```text
Stage 10 WorkerIR
  -> IRSSubsystem.run_post_normalize(...)
  -> PostNormalizeIRSCheckerV6
  -> DiagnosticConsolidator
  -> final compile_diagnostics
```

## Configuration

Use the productized runtime config:

```python
PipelineConfig.irs: IRSRuntimeConfig
```

Do not reintroduce old top-level migration flags.  IRS runtime behavior is
configured through `IRSRuntimeConfig`.

## Authority Boundary

| Concern | Authority |
|---|---|
| Construct slot satisfaction | IRS / Post-normalize IRS |
| Stage-local early reports | IRSSubsystem stage-local runtime |
| Final diagnostic merge / dedup | `diagnostics.consolidator.DiagnosticConsolidator` over IRS-neutral authority DTOs |
| Step renderability | ExecutableElementGate |
| Required output producer | ProducerIndex |
| Cross-construct graph consistency | Stage 9.5 / normalizer / dedicated graph checker |
| Feedback text | `reporting` renderers only |

Feedback report renders existing reports and diagnostics.  It must not redo
IRS checks or infer missing slots.

## ConstructIRS Admission Rules

Before adding a new `ConstructIRS`, prove that the candidate is a construct,
not just evidence, a planner record, or a diagnostic label.

A candidate may become `ConstructIRS` only if it satisfies all of these:

- It corresponds to an SPL grammar construct, or to a compiler materialization /
  analysis construct explicitly approved by architecture docs.
- It has a stable construct identity that can be extracted as an instance from
  structured IR.
- It has independent information slots whose satisfaction can be checked.
- It is not merely a `RouteAnnotation.semantic_role`, source signal, span label,
  planner demand, internal binding record, or `DiagnosticKind`.
- Its diagnostics cannot be more naturally projected from an existing
  construct's missing slot.

Use this checklist when reviewing a proposed IRS:

```text
1. What SPL or approved compiler construct does it represent?
2. What are its required slots?
3. What structured evidence satisfies each slot?
4. Which stage materializes or demands the construct instance?
5. Which existing construct would own this diagnostic if this IRS did not exist?
6. Why is a new ConstructIRS still necessary?
```

If question 5 has a clear answer, prefer the existing construct.

## Boundary: Construct vs Evidence vs Planner IR vs Diagnostic

### Can become ConstructIRS

Examples:

- `EXCEPTION_FLOW`
- `MAIN_WORKER`
- `CHILD_WORKER`
- `GENERAL_COMMAND`
- `REQUEST_INPUT`
- `CALL_API`
- `INVOKE_WORKER`
- `REQUIRED_OUTPUT`
- approved compiler analysis/materialization constructs such as
  `WORKER_CANDIDATE`, `WORKER_PROMOTION`, or `WORKER_HANDOFF`, if the
  architecture document defines their construct identity and slots.

### Source signal / evidence only

These may trigger extraction or satisfy slots, but must not be registered as
new `ConstructIRS` by themselves:

- `RouteAnnotation.semantic_role`
- source span labels
- section title priors
- route refinement labels
- `delegation_intent`
- `input_contract` / `output_contract` annotations
- `required_output` annotation
- source packet IDs and source span IDs

Example: `delegation_intent` is evidence for worker boundary analysis. Missing
handoff contract should be reported through `WORKER_PROMOTION`,
`WORKER_HANDOFF`, `CHILD_WORKER`, or `INVOKE_WORKER` slot satisfaction, not by
creating a `DELEGATION_INTENT` construct.

### Planner demand / internal IR only

These are compiler planning or binding records. They may create evidence for a
construct instance, but they are not automatically IRS constructs:

- `ConstructPlan`
- `ResourceContractPlan`
- `ResourceContractDemandIR`
- `ResourceContractBindingIR`
- resolver records
- producer index entries
- worker boundary planner records

Example: a resource contract demand should normally feed `REQUIRED_OUTPUT`,
`DEFINE_FILES` / `FileSpec`, `DEFINE_VARIABLES` / `VariableSpec`, binding, and
producer checks. Register it as `RESOURCE_CONTRACT_DEMAND` only if the
architecture explicitly promotes it to an approved compiler materialization
construct with its own slots and lifecycle.

### Diagnostic kind only

These are projected outcomes, not IRS constructs:

- `type_or_contract_ambiguity`
- `missing_output_producer`
- `missing_resource_contract`
- `resource_kind_mismatch`
- `assumed_command_not_renderable`
- `missing_handler`

Diagnostic kinds belong in `SlotSpec.missing_diagnostic` or projector policy.
They must not drive construct extraction and must not be registered as
`ConstructIRS`.

## Creating a New IRS

Follow this sequence:

1. Identify the construct owner from SPL grammar or approved architecture docs.
2. Define the `ConstructIRS` slots before writing checker logic.
3. For each slot, define:
   - whether it is syntax-required;
   - whether it is required for partial or complete construct satisfaction;
   - whether rendering can proceed without it;
   - which structured evidence kinds satisfy it;
   - which diagnostic kind is projected when it is missing.
4. Define instance extraction from structured IR only.
5. Implement `check_instance()` as slot satisfaction, not semantic invention.
6. Let `DiagnosticProjector` create `CompileDiagnostic`.
7. If a missing slot should be repairable through SPL Editing, read both
   `reference/repair-affordances.md` and
   `reference/construct-repair-strategies.md` before adding metadata.
8. Link the slot to an existing, architecture-confirmed construct-level
   `RepairStrategySpec`. Do not treat a patch type as the repair strategy and
   do not invent a strategy while creating an IRS.
9. Add tests for registry shape, strategy linkage, instance extraction, slot
   satisfaction, projection, and report storage.

Do not start with a diagnostic and then create a construct to host it. Start
with the construct and let missing slots produce diagnostics.

## Correct IRS Usage

Use IRS to:

- make construct information requirements explicit;
- drive stage prompts/checklists for construct assembly;
- check whether materialized or demanded construct instances have the required
  slots;
- emit `ConstructSatisfactionReport`;
- project user-actionable compile diagnostics from missing slots.

Do not use IRS to:

- replace planner logic;
- replace producer indexing;
- replace executable renderability gates;
- repair stage outputs;
- classify raw text with keywords;
- promote every annotation into a construct;
- create internal diagnostics that belong only in compile/debug reports.

## Diagnostic Pattern

Correct pattern:

```text
ConstructIRS(slot.missing_diagnostic="type_or_contract_ambiguity")
-> checker marks slot missing
-> ConstructSatisfactionReport
-> DiagnosticProjector
-> CompileDiagnostic(kind="type_or_contract_ambiguity")
```

Wrong pattern:

```text
manual if/else
-> CompileDiagnostic(kind="type_or_contract_ambiguity")
```

Also wrong:

```text
DiagnosticKind or RouteAnnotation label
-> new ConstructIRS
-> diagnostic host construct
```

The diagnostic should be owned by the real construct whose required slot is
missing.

## Checker Rules

Checkers must:

- consume `ConstructIRS` / `SlotSpec`
- consume structured IR evidence only
- output `ConstructSatisfactionReport`
- fill v6 fields: `construct_path`, `frontier_status`, `cutline_reason`,
  `source_span_ids`, and relevant `related_edges`
- let `DiagnosticProjector` create `CompileDiagnostic`

Checkers must not:

- call LLMs
- parse raw NL or use keyword semantic rules
- modify input IR
- generate SPL constructs
- fill missing slots
- directly create `CompileDiagnostic`
- create child reports without source demand
- register source signals, planner records, or diagnostic kinds as constructs

## SPL Editing Repair Contract (R12+)

IRS declares whether a missing construct slot has an approved repair
direction. SPL Editing owns strategy resolution, directives, closure planning,
preview, materialization, and verification.

### Repair Affordance on SlotSpec

`SlotSpec.repair_affordances: tuple[RepairAffordanceSpec, ...]` declares which
SPL Editing repair capabilities are allowed for a missing slot.

Use these references together:

- `reference/repair-affordances.md` for `RepairAffordanceSpec` fields,
  transition rules, catalog linkage, and admission checks.
- `reference/construct-repair-strategies.md` for `RepairStrategySpec`, construct
  closure, stage-slice authority, directive, preview/apply, and verification
  boundaries.
- `examples/add-repairable-slot.md` for an end-to-end IRS slot declaration
  example.

- `repair_strategy_id` is the semantic source for R12+ repair behavior. It must
  resolve to an approved `RepairStrategySpec` whose construct type, slot,
  diagnostic kind, closure, stage-slice chain, and verification lane are
  coherent with the IRS slot.
- `supported_patch_types` and `default_patch_type` are transitional execution
  adapter metadata. They must not define construct shape, user-visible repair
  semantics, stage authority, or the strategy itself.
- `affordance_id` names a stable repair capability. Related slots may share it
  only when they expose the same confirmed strategy set; the unique catalog key
  remains `{construct_type}.{slot_name}.{diagnostic_kind}.{affordance_id}`.
- IRS only declares affordances; it does NOT execute repairs, call LLMs, mutate
  IR, create directives, plan construct closure, execute stage slices, generate
  previews, or generate suggestions.
- When this skill is used to create or modify IRS constructs, repair strategies
  must be confirmed by the user or architecture documentation. If not
  confirmed, leave `repair_affordances=()` and state that SPL Editing repair is
  not yet defined for the slot.

### Required Repair Semantics

For every repairable slot, preserve this chain:

```text
ConstructIRS slot + missing diagnostic
-> RepairAffordanceSpec.repair_strategy_id
-> RepairStrategySpec
-> ConstructClosurePlan
-> repair-mode stage-slice chain
-> preview and user confirmation
-> confirmed materialization
-> compiler-authority verification
```

The strategy describes a missing construct closure, not a fixed answer. For
example, `EXCEPTION_FLOW.handler_action` maps to completing a handler `BLOCK +
COMMAND` closure. A minimal sequential block and one command may be the default
policy output, but it is not the strategy definition.

### Creation Response Requirement

When asked to create or modify an IRS, report separately:

1. the construct and slot satisfaction contract;
2. whether the slot is user-actionable;
3. the approved `repair_strategy_id`, if one exists;
4. the construct closure and owning stage slices;
5. authoritative context and selectable-ref requirements;
6. preview/apply and verification requirements;
7. any missing runtime component that prevents exposing the repair.

Do not silently create patch-action metadata just to make a diagnostic appear
editable.

### Diagnostic to IRS Slot Reverse Lookup (DiagnosticIRSRef)

`DiagnosticProjector.project()` writes into every `CompileDiagnostic.metadata`:

- `metadata["irs_ref"]`: dict with `construct_type`, `construct_id`,
  `slot_name`, `construct_path`, `source_authority`
- `metadata["authority"]`: `"post_normalize_irs"` | `"stage_local_irs"` |
  `"selected_promoted_stage_local_irs"`

SPL Editing reads these via `DiagnosticIRSRef.from_dict()`.

### RepairCatalog

`RepairCatalogBuilder.from_construct_registry(registry)` scans all
`SlotSpec.repair_affordances` and produces a `RepairCatalog`.

- `entry_id` = `{construct_type}.{slot_name}.{diagnostic_kind}.{affordance_id}`
- Multiple slots sharing the same `affordance_id` each produce a distinct entry
- Three lookup axes: `entry_id`, `affordance_id`,
  `construct_type+slot_name+diagnostic_kind`

### Issue Grouping

- `metadata["issue_role"]` = `"primary"` | `"alias"` | `"context"`
- `metadata["repairability"]` = `"editable"` | `"review_only"` | `"non_repairable"`
- Producer grouping: `REQUIRED_OUTPUT.producer` = primary,
  `RESOURCE_CONTRACT_DEMAND.producer` = alias
- Worker/delegation promotion: `WORKER_PROMOTION` slots grouped by candidate

### User-Confirmed Repair Evidence

`origin="user_confirmed_repair"` is recognized across compiler authorities:

- Gate `classify_origin()` returns `"user_confirmed_repair"`
- Gate `is_renderable()` uses the same structural guard rails as `source_backed`
- ProducerIndex `_step_is_renderable()` returns `True`
- Post-normalize IRS `_source_evidence_slot()` returns `status="satisfied"`

Unconfirmed AI suggestions (no `user_confirmed_repair` origin, no source
spans) remain non-renderable.

### DELEGATION_INTENT Boundary

- `delegation_intent` is a `RouteAnnotation.semantic_role`: source signal
  only.
- It is NOT a `ConstructIRS`, NOT in the default registry, NOT a catalog
  target or repair target.
- Real repair targets are slots on `WORKER_PROMOTION`, `WORKER_HANDOFF`,
  `CHILD_WORKER`, or `INVOKE_WORKER`.

## ConstructPlan Boundary

`ConstructPlan` is upstream of IRS.  It records source-demanded constructs
from `RouteAnnotation` evidence.  IRS checks the resulting materialized or
source-demanded construct instances; it does not decide slot pairing or
materialization.

`ConstructPlan` may consume `RouteAnnotation` evidence, deterministic section
evidence, or planner records. That does not make those inputs IRS constructs.
They remain evidence until an approved construct instance is extracted.




