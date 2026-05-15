# Structural Provenance MVP+ Acceptance Report

**Date**: 2026-05-15
**Status**: Accepted

## 1. Summary

This MVP+ phase extends the Partial SPL MVP with structural NL provenance:
`source_section_id` and `source_packet_id` from the `StructuralNLAdapter`
now propagate through the pipeline to `TraceRecord` entries for flow,
worker, handoff, and variable elements, and are displayed in the readable
compile report.

The work does NOT change any IR schema, adapter, or require full `TraceRef`
on every element.  It extends the `ProvenanceAggregator` to resolve
section/packet from existing span evidence and thread the results into
`TraceRecord`.

## 2. Test Baseline

```
760 passed, 4 skipped, 0 failures
Python 3.14.3, pytest 9.0.3
```

### Reproduction

```powershell
pip install -e ".[dev]"
python -m pytest tests/ -v --tb=short
```

## 3. Phase Summary

### Phase 0: Baseline Report

`docs/implementation/structural_provenance_baseline_report.md`

- Mapped the full provenance chain: adapter -> SpanIR -> TraceRecord -> report
- Identified 5 breaks where section/packet were not resolved
- Defined 3 structural NL fixture candidates

### Phase 1: Provenance Propagation

`src/nl2spl/pipeline/provenance.py` -- 4 trace methods extended:

| Method | Change | Tests |
|---|---|---|
| `_trace_flows` | Resolves section/packet from block spans for main/alt/exception flows | 3 |
| `_trace_worker` | Accepts `worker_owned_spans`, resolves section/packet per worker | 3 |
| `_trace_handoffs` | Resolves section/packet from `invoke_location_hint` and `failure_policy` spans | 2 |
| `_trace_variables` | Accepts `variable_facts`, uses adapter `VariableFact.source_section_id` | 4 |

`aggregate()` accepts two new optional kwargs: `worker_owned_spans`,
`variable_facts`.

Orchestrator (`orchestrator.py`) wired to pass `worker_owned_spans` (from
`WorkerSpecIR`) and `variable_facts` (from `CanonicalCompileInput.hard_facts`)
to the aggregator.

Orchestrator wiring test (in `test_orchestrator_result.py`) verifies the
real `ProvenanceAggregator` resolves section/packet through the full chain.

### Phase 2: Structural NL Integration Fixtures

`tests/integration/test_partial_spl_mvp.py` -- 3 new fixtures:

| Fixture | Real adapter path | Target trace | Assertion |
|---|---|---|---|
| Required output | `InputAdapterRegistry` -> `SpanSlicer` | `variable:final_report` | `source_section_id == "sec_required_outputs"` |
| Failure handling | `InputAdapterRegistry` -> `SpanSlicer` | `flow:exc_1` | `source_section_id == "sec_failure_handling"` |
| Delegation policy | `InputAdapterRegistry` -> `SpanSlicer` | `handoff:h1` | `source_section_id == "sec_delegation_policy"` |

Each fixture uses the real `StructuralNLAdapter` + `SpanSlicer` to produce
`SpanIR` objects with adapter provenance, then runs through the
deterministic post-compilation chain.

## 4. Module Changes

| File | Change |
|---|---|
| `pipeline/provenance.py` | 4 trace methods extended; 2 new aggregate() kwargs; ASCII cleanup |
| `pipeline/orchestrator.py` | Wired `worker_owned_spans` and `variable_facts` to aggregator |
| `tests/unit/test_provenance.py` | 12 new tests (flow/worker/handoff/variable section provenance) |
| `tests/unit/test_orchestrator_result.py` | 1 new test (real aggregator wiring) |
| `tests/integration/test_partial_spl_mvp.py` | 3 new structural NL fixtures |
| `docs/implementation/structural_provenance_baseline_report.md` | Phase 0 baseline |
| `docs/implementation/structural_provenance_acceptance_report.md` | This report |

## 5. Coverage

### What is covered

- Flow traces (main, alternative, exception) carry section/packet from block spans
- Worker traces carry section/packet from `WorkerSpecIR.owned_span_ids`
- Handoff traces carry section/packet from `invoke_location_hint` and `failure_policy` spans
- Variable traces carry section/packet from adapter `VariableFact.source_section_id`
- Section provenance appears in `readable_report` via `render_report()`
- Real adapter + SpanSlicer end-to-end for required_outputs, failure_handling, delegation_policy sections

### What is NOT covered (deferred)

- Adding `source_section_id` / `source_packet_id` fields to StepIR, ConstraintIR,
  WorkerSpecIR, WorkerHandoffIR, or other IR types (TraceRef model)
- `candidate_id` linkage from `WorkerHandoffIR` to `CandidateTaskUnitIR`
- Full structural NL pipeline end-to-end (adapter -> Stage 1-11 -> report)
  with LLM stages
- Worker-owned spans for legacy (non-worker-plan) path
- Section provenance for profile traces
- Interactive provenance exploration UI

## 6. Test Command

```powershell
python -m pytest tests/ -v --tb=short
# Expected: 760 passed, 4 skipped
```
