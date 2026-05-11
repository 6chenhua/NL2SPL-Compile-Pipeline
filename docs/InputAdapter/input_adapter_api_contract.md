# InputAdapter API Contract

Date: 2026-05-10

## Purpose

InputAdapter is a pre-compile normalization layer. It converts raw input into `CanonicalCompileInput`. It does not generate SPL or final compiler IR such as `WorkerPlanIR`, `FlowStructureIR`, `StepIR`, or `ConstraintIR`.

## Modules

- `src/nl2spl/canonical/compile_input.py`
- `src/nl2spl/adapters/base.py`
- `src/nl2spl/adapters/registry.py`
- `src/nl2spl/adapters/structural_nl.py`
- `src/nl2spl/adapters/generic_nl.py`

## Canonical Models

`CanonicalCompileInput` contains:

- `source_schema`
- `schema_version`
- `raw_text`
- `raw_sections`
- `semantic_packets`
- `hard_facts`
- `compile_hints`
- `warnings`
- `detection`

`detect()` returns `AdapterDetectionResult` and must not contain `confidence`.

## Adapter Interface

```python
class InputAdapter:
    name: str
    schema_version: str

    def detect(self, raw_text: str) -> AdapterDetectionResult: ...
    def adapt(self, raw_text: str) -> CanonicalCompileInput: ...
```

## Registry Contract

Selection order:

1. `StructuralNLAdapter`
2. `GenericNLAdapter`

If no specific adapter matches, `GenericNLAdapter` preserves legacy freeform behavior.

## Contract Validation

`CanonicalCompileInputValidator` checks:

- non-empty `source_schema`
- non-empty `raw_text`
- unique section ids
- unique packet ids
- packet source sections exist
- hard fact names are unique
- hard fact and hint section references are traceable
- no `confidence` field is present anywhere in adapter output

