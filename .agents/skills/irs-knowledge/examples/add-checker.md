# Add an IRS Checker

Use this guide when adding a new IRS checker.  IRS checkers analyze
structured IR evidence against `ConstructIRS`; they do not call LLMs, parse
raw NL, mutate IR, or create SPL constructs.

## Step 1: Add or Update ConstructIRS

Edit the construct definition in `src/nl2spl/compiler/constructs/definitions/`
or the default registry assembly in `src/nl2spl/compiler/constructs/defaults.py`.
Do not add new construct definitions to the legacy
`src/nl2spl/compiler/construct_registry.py` shim.

```python
SlotSpec(
    slot_name="source_evidence",
    required_for_partial=True,
    renderable_without=False,
    diagnostic_kind="type_or_contract_ambiguity",
)
```

The `constructs` registry is the source of truth for slot names, requiredness, and
diagnostic kinds.  Do not hard-code a parallel slot contract inside the
checker.

## Step 2: Implement the Checker

Place the checker under `src/nl2spl/compiler/irs/checkers/`.

```python
class ExampleIRSChecker:
    checker_id = "example"
    supported_construct_types = ("EXAMPLE_CONSTRUCT",)
    supported_stages = ("stageX",)

    def extract_instances(self, context: IRSCheckContext) -> list[ConstructInstance]:
        return []

    def check_instance(
        self,
        instance: ConstructInstance,
        irs: ConstructIRS,
        context: IRSCheckContext,
    ) -> ConstructSatisfactionReport:
        ...
```

Required checker boundaries:

- consume structured IR fields only
- use `irs.slots` / `SlotSpec` for slot contract
- fill `construct_path`, `source_span_ids`, `frontier_status`,
  `cutline_reason`, and relevant `related_edges`
- return `ConstructSatisfactionReport`
- let `DiagnosticProjector` create `CompileDiagnostic`

Forbidden:

- LLM calls
- raw NL parsing or keyword semantic rules
- mutating input IR
- generating constructs
- filling missing slots
- direct `CompileDiagnostic` creation

## Step 3: Register via Factory

Add the checker to `build_irs_checker_registry()` in
`src/nl2spl/compiler/irs/factory.py`.  Registration must be driven by
`IRSRuntimeConfig`, not by ad-hoc `PipelineConfig` flags.

```python
def build_irs_checker_registry(policy: IRSRuntimeConfig) -> IRSCheckerRegistry:
    registry = IRSCheckerRegistry()
    if policy.example_enabled:
        registry.register(ExampleIRSChecker())
    return registry
```

If a new policy field is required, add it to `IRSRuntimeConfig`.

## Step 4: Orchestrator Integration

The orchestrator should call `IRSSubsystem`; it should not import the concrete
checker.

```python
irs_subsystem = build_irs_subsystem(config.irs)
result = irs_subsystem.run_stage_local("stageX", context)
irs_store.add_stage_result("stageX", result)
```

Expected intermediate payload:

```text
intermediate["irs_stage_results"][stage]
intermediate["construct_satisfaction"][stage]
intermediate["stage_local_diagnostics"][stage]
intermediate["irs_graph_snapshots"][stage]
```

## Step 5: Tests

Add tests for:

- instance extraction from real IR shapes
- required slot satisfaction
- missing slot `diagnostic_kind`
- `ConstructSatisfactionReport` v6 fields
- graph edges and deterministic snapshots
- factory registration through `IRSRuntimeConfig`
- orchestrator/subsystem integration only if the stage is newly connected

Tests must not use `skip` or broad weak assertions for acceptance behavior.
