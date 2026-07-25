# IRS Module Structure

IRS means **Information Requirements Specification**.  The runtime performs
satisfaction analysis over source-demanded or materialized SPL constructs.

## Productized Runtime

```text
src/nl2spl/compiler/irs/
  __init__.py          lazy public exports
  policy.py            IRSRuntimeConfig
  context.py           IRSCheckContext
  instance.py          ConstructInstance
  checker.py           IRSChecker protocol
  registry.py          IRSCheckerRegistry
  runner.py            IRSRunner / IRSRunResult
  projector.py         DiagnosticProjector
  result_store.py      IRSResultStore
  subsystem.py         IRSSubsystem
  factory.py           build_irs_subsystem / registry helpers
  checkers/
    worker_delegation.py
```

## Registry and Reports

```text
src/nl2spl/compiler/constructs/
  spec.py
  SlotSpec
  ConstructIRS
  satisfaction.py
  SlotSatisfaction
  ConstructSatisfactionReport
  graph.py
  ConstructEdge / ConstructGraph
  registry.py
  SPLConstructRegistry
  defaults.py
  definitions/
```

Legacy modules such as `compiler.construct_registry`, `compiler.irs.graph`,
`compiler.irs.frontier`, and `compiler.irs.feedback_projector` are compatibility
shims. New production code should import from `constructs` and `reporting`.

`ConstructSatisfactionReport` must carry v6 shape fields:

```text
construct_path
source_span_ids
related_edges
frontier_status
cutline_reason
```

## Diagnostic Flow

```text
IRSChecker
  -> ConstructSatisfactionReport
  -> DiagnosticProjector
  -> IRSResultStore
  -> irs.diagnostic_authority_adapter
  -> diagnostics.consolidator.DiagnosticConsolidator
  -> compile_diagnostics
```

`src/nl2spl/compiler/diagnostics/consolidator.py` is the single diagnostic
merge/dedup authority. It consumes IRS-neutral authority DTOs from
`diagnostics.authority`; conversion from `IRSResultStore` belongs in
`irs.diagnostic_authority_adapter`. Stage-local IRS diagnostics are early
signals and are suppressed from final compile diagnostics unless the runtime
policy explicitly includes them.

## Configuration

Use the productized runtime config:

```python
PipelineConfig.irs: IRSRuntimeConfig
```

Do not add per-checker migration flags to `PipelineConfig`.  Configure IRS
through `IRSRuntimeConfig` fields such as:

```text
enabled
stage_local_enabled
worker_delegation_enabled
exception_flow_enabled
step_enabled
post_normalize_enabled
include_stage_local_diagnostics_in_compile
include_construct_satisfaction_in_feedback
collect_graph_snapshot
```

## Orchestrator Boundary

The orchestrator builds and calls `IRSSubsystem`.  It must not import concrete
checker classes directly.

```text
PipelineOrchestrator
  -> build_irs_subsystem(config.irs)
  -> IRSSubsystem.run_stage_local(...)
  -> IRSSubsystem.run_post_normalize(...)
```

Intermediate storage:

```text
intermediate["irs_stage_results"]
intermediate["construct_satisfaction"][stage_name]
intermediate["stage_local_diagnostics"][stage_name]
intermediate["irs_graph_snapshots"][stage_name]
```

## Feedback

`ConstructSatisfactionFeedbackProjector` renders existing reports into feedback
text from `compiler.reporting.construct_satisfaction_renderer`.  It does not
run IRS, infer slots, or create diagnostics.
