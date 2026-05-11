# InputAdapter Implementation Progress

Date: 2026-05-10

Status: MVP implemented, deeper integration pending

Related documents:

- `docs/input_adapter_api_contract.md`
- `docs/structural_nl_adapter_rules.md`
- `docs/input_adapter_pipeline_integration.md`
- `docs/input_adapter_test_matrix.md`
- `docs/input_adapter_implementation_plan.md`
- `docs/nl_2_spl_input_adapter_design.md`

## 1. Current State

InputAdapter has been implemented as an independent pre-compile normalization layer.

It does not generate SPL and does not generate final compiler IR such as:

- `WorkerPlanIR`
- `FlowStructureIR`
- `StepIR`
- `ConstraintIR`
- `WorkerIR`

The current implementation supports:

- `CanonicalCompileInput`
- `CanonicalCompileInputValidator`
- `InputAdapter` base interface
- `InputAdapterRegistry`
- `StructuralNLAdapter`
- `GenericNLAdapter`
- MVP integration with Stage 1, Stage 2, Stage 6, Stage 9, and `PipelineOrchestrator`

## 2. Implemented Files

### Canonical contract

- `src/nl2spl/canonical/__init__.py`
- `src/nl2spl/canonical/compile_input.py`

Implemented models:

- `AdapterDetectionResult`
- `RawSection`
- `SemanticPacket`
- `VariableFact`
- `FailureModeFact`
- `HardFacts`
- `CompileHint`
- `CompileHints`
- `AdapterWarning`
- `CanonicalCompileInput`
- `CanonicalCompileInputValidator`

### Adapters

- `src/nl2spl/adapters/__init__.py`
- `src/nl2spl/adapters/base.py`
- `src/nl2spl/adapters/registry.py`
- `src/nl2spl/adapters/structural_nl.py`
- `src/nl2spl/adapters/generic_nl.py`

Implemented behavior:

- `StructuralNLAdapter` detects seven-section structural NL input.
- `GenericNLAdapter` preserves legacy freeform input behavior.
- `InputAdapterRegistry` selects `StructuralNLAdapter` first, otherwise falls back to `GenericNLAdapter`.

### Pipeline integration

- `src/nl2spl/ir/span_ir.py`
- `src/nl2spl/pipeline/orchestrator.py`
- `src/nl2spl/pipeline/stages/stage1_span_slicer.py`
- `src/nl2spl/pipeline/stages/stage2_field_router.py`
- `src/nl2spl/pipeline/stages/stage3_ambiguity_resolver.py`
- `src/nl2spl/pipeline/stages/stage6_resource_extractor.py`
- `src/nl2spl/pipeline/stages/stage7_step_extractor.py`
- `src/nl2spl/pipeline/stages/stage8_profile_extractor.py`
- `src/nl2spl/pipeline/stages/stage9_constraint_extractor.py`

Integration summary:

- `PipelineOrchestrator.run(raw_text: str)` remains the public API.
- Orchestrator now adapts raw input before Stage 1.
- `intermediate_results` records adapter detection, canonical input, and adapter diagnostics.
- `SpanIR` now supports optional `source_section_id` and `source_packet_id`.
- Stages that serialize spans use `SpanIR.to_dict()` so absent adapter provenance does not pollute legacy prompts.

## 3. Implemented Behavior

### Structural input detection

`StructuralNLAdapter.detect()` is deterministic:

- normalizes headings by trimming, removing trailing `:` or `：`, lowercasing, and collapsing whitespace
- matches when at least three standard sections are present, or at least two of `task_family`, `inputs_for_each_run`, and `required_outputs` are present
- requires at least one matched section with non-empty body text
- records missing, duplicate, empty, and unexpected sections
- does not emit confidence

Supported sections:

- `Task family`
- `Inputs for each run`
- `Required outputs`
- `Reusable process`
- `Policies`
- `Failure handling`
- `Delegation policy`

### Canonical output

Structural input now produces:

- `raw_sections`
- `semantic_packets`
- `hard_facts.inputs`
- `hard_facts.outputs`
- `hard_facts.failure_modes`
- `compile_hints.profile_hints`
- `compile_hints.process_hints`
- `compile_hints.constraint_hints`
- `compile_hints.flow_hints`
- `compile_hints.delegation_hints`
- adapter warnings

### Stage 1 MVP

`SpanSlicer` accepts either:

- legacy `str`
- `CanonicalCompileInput`

For `structural_nl`, Stage 1 creates:

- packet-aware spans with `source_section_id` and `source_packet_id`
- section-aware spans for section text not covered by packets

For `generic_nl`, Stage 1 uses the original LLM slicing path.

### Stage 2 MVP

`FieldRouter` accepts either:

- legacy `list[SpanIR]`
- `(list[SpanIR], CanonicalCompileInput)`

For `structural_nl`:

- runtime input packets are not routed to normal six-field routes
- required output packets are not routed to normal six-field routes
- process packets route to behavior
- policy and failure packets route to rules
- delegation packets route to behavior only in this MVP
- adapter-consumed/non-routed spans are saved in the Stage 2 checkpoint

Delegation packets do not create `delegation_candidates`.

### Stage 6 MVP

`ResourceExtractor` consumes `hard_facts.inputs` and `hard_facts.outputs`.

Merge rules:

- hard fact inputs become `VariableSpec(source="input")`
- hard fact outputs become `VariableSpec(source="output")`
- same name and same type are merged
- same name and different type keeps the hard fact type and records a warning
- `required=True` wins
- hard fact source wins over step-derived source
- output hard facts declare output contracts but do not imply producer steps

Seeded variables are declared in `SymbolTable` before StepExtractor.

### Stage 9 MVP

`ConstraintExtractor` includes adapter constraint hints in the prompt as context.

Constraint hints are not `ConstraintIR`.

Stage 9 may adopt, split, merge, reject, or reclassify hints. Final target selection remains Stage 9 responsibility.

## 4. Added Tests

Added test files:

- `tests/unit/test_input_adapters.py`
- `tests/unit/test_input_adapter_pipeline.py`

Covered scenarios:

- no confidence field in detection output
- invalid packet source section fails validator
- duplicate packet id fails validator
- duplicate hard fact names fail validator
- full structural input detection
- missing, duplicate, empty, reordered, and Chinese-colon section handling
- generic freeform fallback
- hard fact extraction for inputs, outputs, and failure modes
- constraint and delegation hint extraction
- Stage 1 adapter provenance
- Stage 1 generic legacy path
- Stage 2 hard fact spans excluded from behavior
- Stage 6 seeded variables and output producer unset
- orchestrator records adapter intermediate results

## 5. Verification Performed

Completed:

```bash
python -m compileall -q ...
```

Manual smoke checks confirmed:

- `InputAdapterRegistry` selects `structural_nl` for seven-section input.
- `CanonicalCompileInputValidator` returns no errors for valid structural input.
- structural input produces expected hard fact inputs and outputs.
- Stage 1 produces adapter-aware spans with provenance.
- Stage 2 routes process/policy/delegation packets and excludes hard fact input/output packets.
- Stage 6 seeds hard facts into `ResourceRegistryIR` and `SymbolTable`.
- required output variables have no producer step at declaration time.

Not completed:

```bash
pytest tests/unit
pytest tests/integration
ruff check src tests
```

Reason:

- current Python environment does not have `pytest`
- current Python environment does not have `ruff`
- current Python environment does not have `python-dotenv`
- current Python environment does not have `openai`

The failure was environment dependency related, not an observed test failure.

## 6. Remaining Work

### Phase 2: Deeper pipeline integration

Can start independently from Multi-Worker:

1. Add dedicated adapter checkpoint, for example `stage0_input_adapter.json`.
2. Pass `profile_hints` to Stage 8.
3. Pass `process_hints`, `flow_hints`, and `failure_modes` to Stage 4.
4. Pass `process_hints` and suggested block information to Stage 5.
5. Improve Stage 7 use of seeded variables and adapter provenance.
6. Add adapter-derived diagnostics into final `PipelineResult` more explicitly.

Should wait for downstream validator/normalizer maturity:

1. Required output producer/reachability validation.
2. Failure mode coverage validation.
3. Policy/constraint coverage validation.
4. Packet-level semantic coverage validation.

### Phase 3: Adapter expansion

Not implemented:

- `skill_md` adapter
- `api_task_spec` adapter
- `workflow_spec` adapter
- `policy_doc` adapter
- advanced adapter conflict resolution
- LLM-assisted adapter parsing

### Parser improvements

Not implemented:

- robust markdown bullet parsing
- numbered list parsing
- nested list parsing
- semicolon-separated list parsing
- mixed Chinese/English list parsing
- richer data type inference

## 7. Multi-Worker Dependency Boundary

InputAdapter itself does not depend on Multi-Worker.

Already independent:

- canonical input contract
- structural adapter
- generic fallback
- hard facts
- hints
- Stage 1/2/6/9 MVP integration

Depends on Multi-Worker later:

- using `delegation_hints` as WorkerBoundaryPlanner evidence
- mapping failure modes into worker handoff failure policy
- validating required output reachability when child workers produce outputs

InputAdapter must continue to provide section-aware facts and hints only. It must not directly generate worker boundaries.

## 8. Recommended Next Steps

Recommended immediate next batch:

1. Add `stage0_input_adapter.json` checkpoint.
2. Integrate `profile_hints` into Stage 8 prompt.
3. Integrate `flow_hints` and `failure_modes` into Stage 4 prompt.
4. Integrate `process_hints` into Stage 5 prompt.
5. Run full tests after installing project dev dependencies.

Recommended later batch:

1. Build semantic coverage validator.
2. Add required output reachability validation.
3. Add failure mode coverage validation.
4. Connect `delegation_hints` to WorkerBoundaryPlanner after Multi-Worker Stage 3.5 stabilizes.

## 9. Known Risks

- Current list parsing is intentionally simple and may over/under-split complex input sections.
- Stage 2 adapter routing is deterministic and conservative; it may need refinement once more fixtures are added.
- Stage 6 hard fact merging preserves LLM duplicate descriptions as notes; future code may want structured aliases instead of inline notes.
- Full regression tests have not been run in the current environment due missing dev dependencies.
- Existing working tree contains other Multi-Worker changes; future merges should avoid conflating InputAdapter changes with those edits.

