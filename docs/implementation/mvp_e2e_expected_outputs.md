# Partial SPL MVP End-to-End Expected Outputs

**Date**: 2026-05-15
**Purpose**: Define the expected observable behavior before running real LLM
end-to-end checks.  The goal is not exact SPL text equality; the LLM stages
may vary wording.  The acceptance criteria below focus on the teacher-aligned
contract: materialize source-backed information, preserve partial SPL, and
surface missing / ambiguous / assumed information through diagnostics,
assumptions, provenance, and the readable report.

## Global Expected Behavior

For each end-to-end run:

- `final_spl.txt` is generated unless validation fails before rendering.
- `compile_report.txt` is generated.
- `PipelineResult.completeness` is one of `complete`, `partial`, or `blocked`.
- Missing or ambiguous requirements are not silently repaired.
- Unsupported executable commands do not appear in SPL.
- `CompileDiagnostic` records explain missing handlers, missing output
  producers, unresolved contracts, assumed commands, unmapped behavior, or
  missing provenance.
- `CompileAssumption` records appear only in the report, not as executable SPL.
- `TraceRecord` entries appear in the report's `Provenance Traces` section.
- For structural NL input, report traces include `section=sec_...` when adapter
  provenance is available.

## Scenario A: Required Output Without Producer

### Input Shape

Structural NL declares a required output, but the reusable process does not
include any source-backed step that produces it.

### Expected SPL

- Contains the required output contract, for example `final_report`.
- Does **not** contain a synthetic command such as:
  - `Produce required output`
  - `Generate final_report` if no source-backed behavior supports it.

### Expected Diagnostics

- At least one `missing_output_producer` diagnostic for the required output.
- No diagnostic should be hidden by validation warnings.

### Expected Completeness

- `partial`, unless an unrelated hard validation error makes the run `blocked`.

### Expected Report / Provenance

- Report contains `Diagnostics`.
- Report contains `missing_output_producer`.
- Report contains `Assumptions / Suggestions`.
- Report contains `Provenance Traces`.
- For structural NL, `variable:final_report` should trace to
  `section=sec_required_outputs`.

## Scenario B: Failure Condition Without Handler

### Input Shape

Structural NL or freeform NL states a failure condition, such as missing
timeframe, but does not specify a concrete handler action.

### Expected SPL

- Preserves an exception flow skeleton for the failure condition.
- Does **not** invent an executable handler such as `REQUEST_INPUT` unless the
  source explicitly asks to request input from the user.

### Expected Diagnostics

- At least one `missing_handler` diagnostic.
- If the LLM emits a vague or unsupported handler step, the gate should block it
  and surface `assumed_command_not_renderable`.

### Expected Completeness

- `partial`, unless an unrelated hard validation error makes the run `blocked`.

### Expected Report / Provenance

- Report contains `missing_handler`.
- Report contains a trace for the exception flow.
- For structural NL, the exception flow trace should include
  `section=sec_failure_handling`.

## Scenario C: Structural NL Section Provenance

### Input Shape

Structural NL includes required outputs, failure handling, and delegation policy
sections.

### Expected SPL

- Materializes only source-backed steps and valid worker / handoff structures.
- Does not downgrade unresolved worker or API references to generic commands.

### Expected Diagnostics

- Incomplete delegation should produce `type_or_contract_ambiguity` and/or
  `assumed_command_not_renderable`.
- Complete, bounded delegation may render a child worker / invoke if the source
  and planner establish a valid handoff contract.

### Expected Completeness

- `complete` only when there are no completion-blocking diagnostics and no
  validation errors.
- `partial` when required output producers, handlers, or contracts remain
  unresolved.

### Expected Report / Provenance

- Required output variable traces include `section=sec_required_outputs`.
- Failure flow traces include `section=sec_failure_handling`.
- Handoff or worker traces include `section=sec_delegation_policy` when a valid
  location hint or worker-owned span exists.

## Acceptance Summary

The MVP is considered to behave as expected if real end-to-end runs demonstrate:

1. Partial SPL is emitted instead of fabricated complete SPL.
2. Missing output producers are diagnostics, not synthetic commands.
3. Missing handlers are diagnostics, not invented `REQUEST_INPUT` steps.
4. Unresolved worker/API behavior is blocked or diagnosed, not silently
   downgraded to generic executable commands.
5. `compile_report.txt` contains status, diagnostics, assumptions, validation,
   provenance traces, and generated SPL.
6. Structural NL provenance appears as `section=sec_...` in relevant trace lines.

