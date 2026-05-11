# Structural NL Adapter Rules

Date: 2026-05-10

## Supported Sections

`structural_nl` supports:

- `Task family`
- `Inputs for each run`
- `Required outputs`
- `Reusable process`
- `Policies`
- `Failure handling`
- `Delegation policy`

## Heading Rules

Heading normalization:

1. trim whitespace
2. remove trailing `:` or `：`
3. lowercase
4. collapse internal whitespace

Detection matches if at least three standard sections are present, or at least two of `task_family`, `inputs_for_each_run`, and `required_outputs` are present. At least one matched section must have non-empty body text.

Unexpected headings are recorded only when a line looks like a heading, ends in `:` or `：`, is not a standard heading, and has non-empty body text after it.

## Extraction Rules

- `Task family` becomes profile/domain hints.
- `Inputs for each run` becomes input hard facts and runtime input packets.
- `Required outputs` becomes output hard facts and required output packets.
- `Reusable process` becomes process hints and process packets.
- `Policies` becomes constraint hints and policy packets.
- `Failure handling` becomes failure mode hard facts and exception-flow hints.
- `Delegation policy` becomes delegation hints and delegation-boundary constraint hints.

Delegation hints must not be converted into `WorkerPlanIR` or `FlowStructureIR.delegation_candidates` in the InputAdapter MVP.

## Naming And Types

Variable names use an alias table first, then snake_case normalization.

Type inference:

- `topics`, `connectors`, `repositories`, `items`, `sources` -> `List [text]`
- `whether ...` -> `boolean`
- default -> `text`

`completion status` remains `text`.

