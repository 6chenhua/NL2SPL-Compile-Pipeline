# InputAdapter Pipeline Integration

Date: 2026-05-10

## Orchestrator

`PipelineOrchestrator.run(raw_text: str)` remains the public API.

Internally the orchestrator adapts input first, validates the canonical contract, and records:

- `adapter_detection`
- `canonical_input`
- `adapter_diagnostics`

Adapter warnings are non-fatal. Contract validation errors are fatal.

## Stage 1

`SpanSlicer` accepts legacy `str` or `CanonicalCompileInput`.

For adapter input:

- packet-derived spans include `source_section_id` and `source_packet_id`
- section-derived spans include `source_section_id`
- generic input uses legacy LLM slicing

## Stage 2

`FieldRouter` accepts legacy spans or spans plus canonical input.

For adapter input:

- runtime input and required output packets are consumed as hard facts and excluded from normal field routing
- process packets route to behavior
- policy and failure packets route to rules
- delegation packets route to behavior only in this MVP

Delegation packets do not create delegation candidates.

## Stage 6

`ResourceExtractor` seeds variables from hard facts.

Merge rules:

- same name and type: merge
- same name and different type: hard fact type wins and warning is recorded
- required conflict: `required=True` wins
- source conflict: hard fact `input` or `output` wins
- output hard fact declares the output contract but does not imply a producer step

Seeded variables are declared in `SymbolTable` before StepExtractor.

## Stage 9

Constraint hints are prompt context only. They are not `ConstraintIR`.

Stage 9 may adopt, split, merge, reject, or reclassify hints. Final targets remain Stage 9 responsibility.

