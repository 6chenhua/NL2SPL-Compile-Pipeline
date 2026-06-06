---
name: irs-knowledge
description: >
  IRS (Information Requirements Specification) concepts, design patterns,
  coding rules, checker extension guidance, diagnostic projection, frontier
  and cutline semantics for NL2SPL.
---

# IRS Knowledge Skill

IRS = **Information Requirements Specification**.  IRS checker / runner
executes satisfaction analysis over source-demanded or materialized SPL
constructs.

IRS does not parse raw NL, call LLMs, render SPL, modify IR, generate new
constructs, or fill missing slots.

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

Post-normalize IRS is the final construct-level authority:

```text
Stage 10 WorkerIR
  -> IRSSubsystem.run_post_normalize(...)
  -> PostNormalizeIRSChecker
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
| Final diagnostic merge / dedup | DiagnosticConsolidator |
| Step renderability | ExecutableElementGate |
| Required output producer | ProducerIndex |
| Feedback text | Report projector / renderer only |

Feedback report renders existing reports and diagnostics.  It must not redo
IRS checks or infer missing slots.

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

## ConstructPlan Boundary

`ConstructPlan` is upstream of IRS.  It records source-demanded constructs
from `RouteAnnotation` evidence.  IRS checks the resulting materialized or
source-demanded construct instances; it does not decide slot pairing or
materialization.
