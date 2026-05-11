# InputAdapter Test Matrix

Date: 2026-05-10

## Unit Tests

- Complete structural input matches.
- Missing, duplicate, empty, reordered, and Chinese-colon sections are handled.
- Generic freeform input falls back to `GenericNLAdapter`.
- Contract validator rejects duplicate packet ids and bad section references.
- Adapter output contains no `confidence`.

## Stage Tests

- Stage 1 adapter spans preserve provenance.
- Stage 1 generic path still calls the LLM.
- Stage 2 hard fact input/output spans do not enter behavior.
- Stage 2 policy/process/delegation packets route deterministically.
- Stage 6 hard facts seed variables and symbol table entries.
- Stage 6 hard fact type wins over conflicting LLM type.

## Regression Tests

- Internal-comms inputs and outputs come from hard facts.
- `source_evidence_set`, `assumptions_log`, and `completion_status` are required outputs.
- Required output producer reachability remains a later validator concern.
- Adapter warnings are visible but non-fatal.

