# Route Contract Refactor Document Map

Date: 2026-05-18

## Purpose

This directory splits the InputAdapter / FieldRoute semantic routing refactor
into coordinated documents.

The previous single document remains useful as a comprehensive background
record:

- `input_adapter_fieldroute_semantic_routing_refactor_todo.md`

For actual execution, use the split documents below.

## Document Order

Read and execute in this order:

```text
00 route_contract_refactor_00_readme.md
01 route_contract_refactor_01_frontend_semantic_contract.md
02 route_contract_refactor_02_downstream_migration.md
```

## Document Responsibilities

### 01 Frontend Semantic Contract

File:

- `route_contract_refactor_01_frontend_semantic_contract.md`

Scope:

- `CanonicalCompileInput`
- `InputAdapter`
- `SpanSlicer`
- `FieldRouteIR`
- `FieldRouter`
- `AmbiguityResolver`

This document defines the front-end compiler contract:

```text
adapter evidence / hints
-> packet-aware spans
-> route annotations
```

It should be completed before downstream stages rely on route annotations.

### 02 Downstream Migration

File:

- `route_contract_refactor_02_downstream_migration.md`

Scope:

- worker boundary planning
- flow assembly
- block assembly
- resource extraction
- step extraction
- profile and constraint extraction
- normalizer
- executable gate
- worker assembler
- renderer
- provenance
- bridge deletion

This document defines how later stages migrate from:

```text
routes.behavior / routes.rules / hard_fact bridges
```

to:

```text
RouteAnnotation-driven construct generation
```

## Global Refactor Rule

The refactor must be gradual. Never switch all downstream stages to route
annotations at once.

The safe sequence is:

```text
1. Add annotations while preserving old FieldRoute lists.
2. Teach FieldRouter to populate annotations.
3. Add downstream helper methods that prefer annotations but fall back to lists.
4. Migrate Stage 4 and Stage 7 first, because they control exception flows and
   executable commands.
5. Migrate surrounding stages.
6. Convert bridge functions into compatibility wrappers.
7. Delete bridge-first production paths only after legacy and worker-aware tests
   pass.
```

## Cross-Document Gates

### Gate A: Frontend Contract Ready

Required before downstream migration begins:

- `RouteAnnotation` exists.
- `FieldRouteIR` remains backward compatible.
- `FieldRouter` emits annotations for structural NL.
- Failure modes have:
  - `semantic_role = failure_mode`
  - `construct_target = EXCEPTION_FLOW`
  - `slot_target = condition`
  - `executable = false`
- Inputs and outputs remain non-executable resource contracts.
- Delegation policy remains non-executable unless a valid handoff contract
  exists.

### Gate B: Downstream Safe Consumption Ready

Required before changing route placement for failure modes:

- Stage 7 can filter executable behavior spans via route helpers.
- Stage 4 can materialize exception flows from route annotations.
- Stage 3.5 worker planning does not treat failure conditions as worker task
  candidates.
- Worker-aware flow materialization has tests.

### Gate C: Bridge Deletion Ready

Required before deleting bridge-first paths:

- route-driven legacy failure tests pass;
- route-driven worker-aware failure tests pass;
- route-driven delegation diagnostics pass;
- provenance includes section, packet, and span evidence;
- no production orchestrator path depends on `bridge_failure_modes()` as the
  primary materialization mechanism.

## Terminology

`Frontend` in these documents means compiler front-end semantic understanding:

```text
InputAdapter -> SpanSlicer -> FieldRouter -> AmbiguityResolver
```

`Downstream` means construct and IR generation:

```text
WorkerBoundaryPlanner -> FlowAssembler -> BlockAssembler -> ResourceExtractor
-> StepExtractor -> ProfileExtractor -> ConstraintExtractor -> Normalizer
-> WorkerAssembler -> Renderer -> Reports
```

