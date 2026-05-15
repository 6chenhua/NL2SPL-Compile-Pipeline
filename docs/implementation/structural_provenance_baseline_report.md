# Structural Provenance Baseline Report -- MVP+ Phase 0

**Date**: 2026-05-15
**Status**: Baseline frozen

## 1. Purpose

This report inventories the current `source_section_id` / `source_packet_id`
provenance chain from the `StructuralNLAdapter` through the pipeline IRs to
the `TraceRecord` and `readable_report`.  It identifies where the chain is
intact and where it breaks, so MVP+ Phase 1 can target the minimum viable
fixes without restructuring the pipeline.

## 2. Current Chain: What Works

### 2.1 Adapter to SpanIR (intact)

The `StructuralNLAdapter` (`adapters/structural_nl.py`) parses 7 structural
sections and produces `CanonicalCompileInput` with:

| Artifact type | Carries `source_section_id` | Example |
|---|---|---|
| `SemanticPacket` | Yes (required) | `source_section_id="sec_inputs_for_each_run"` |
| `VariableFact` | Yes (required) | `source_section_id="sec_required_outputs"` |
| `FailureModeFact` | Yes (required) | `source_section_id="sec_failure_handling"` |
| `CompileHint` | Yes (required) | `source_section_id="sec_delegation_policy"` |

Stage 1 (`SpanSlicer._execute_canonical()`) copies these onto `SpanIR`:

```python
SpanIR(
    source_section_id=packet.source_section_id,
    source_packet_id=packet.packet_id,
)
```

The `GenericNLAdapter` (fallback for unstructured text) produces NONE of
these -- `source_section_id` and `source_packet_id` remain `None`.

### 2.2 SpanIR to TraceRecord (intact, but only for 3 of 6 element types)

`ProvenanceAggregator._resolve_span_origin()` (provenance.py:570-584)
iterates `source_span_ids`, looks up each `SpanIR`, and returns the first
non-None `(source_section_id, source_packet_id)` pair.  This is called from:
- `_trace_steps` (line 218) -- steps get section/packet
- `_trace_constraints` (line 246) -- constraints get section/packet
- `_trace_variables` (line 476) -- variables get section/packet (when they
  have recovered span_ids)

It is NOT called from:
- `_trace_flows` -- flows never get section/packet
- `_trace_worker` -- workers never get section/packet
- `_trace_handoffs` -- handoffs never get section/packet

### 2.3 TraceRecord to Report (intact)

`ReportRenderer._render_traces()` (report_renderer.py:241-245) conditionally
appends `section={id}` and `packet={id}` to each trace line.  These display
correctly when the data is present.

### 2.4 Test coverage

- `test_span_resolves_section_and_packet_ids` -- verifies SpanIR to
  TraceRecord propagation (1 test, test_provenance.py:258)
- `test_input_adapter_pipeline.py` -- verifies Stage 1 populates the SpanIR
  fields from `CanonicalCompileInput`

## 3. Identified Breaks

### 3.1 Only SpanIR and TraceRecord carry section/packet fields

| IR type | Has `source_section_id` | Has `source_packet_id` | Span evidence |
|---|---|---|---|
| `SpanIR` | Yes | Yes | N/A (is the span) |
| `TraceRecord` | Yes | Yes | `source_span_ids` |
| `StepIR` | No | No | `source_span_ids` |
| `ConstraintIR` | No | No | `source_span_ids` |
| `WorkerSpecIR` | No | No | `owned_span_ids` |
| `CandidateTaskUnitIR` | No | No | `source_span_ids` |
| `WorkerHandoffIR` | No | No | None (no span field) |
| `HandoffFailurePolicyIR` | No | No | `source_span_ids` |

`StepIR`, `ConstraintIR`, `CandidateTaskUnitIR`, `WorkerSpecIR`, and
`HandoffFailurePolicyIR` carry span ID lists that can be resolved back to
`SpanIR` objects via a span index.  `WorkerHandoffIR` has no direct span
field -- its span-level provenance must be recovered indirectly through
`invoke_location_hint` (after_span_id / before_span_id), `failure_policy`
source spans, or the target worker's `owned_span_ids`.

### 3.2 Worker, flow, and handoff traces never resolve section/packet

`_trace_worker()`, `_trace_flows()`, and `_trace_handoffs()` produce
`TraceRecord` entries with `source_span_ids=[]` and do NOT call
`_resolve_span_origin()`.

Result: worker, flow (main / alternative / exception), and handoff entries
in the report never show section/packet provenance, even when:
- A worker's `owned_span_ids` point to spans with adapter metadata
- An exception flow's block spans carry `source_section_id`
- A handoff's `invoke_location_hint` references a span with adapter metadata
- A handoff's `failure_policy.source_span_ids` could provide provenance

### 3.3 Variable provenance from handoffs gets empty span_ids

When `_trace_variables()` matches a variable to a handoff output binding
(case 2, lines 365-427), the recovered `source_span_ids` is set to `[]`.
The section/packet info that could come from the handoff's owning worker
or delegation section is lost.

### 3.4 Adapter hard facts are unused in variable provenance

`VariableFact` objects carry `source_section_id` directly.  The adapter
declares variables with hard evidence (e.g. `VariableFact(name="user_request",
source_section_id="sec_inputs_for_each_run")`).  But `_trace_variables()` only
looks at producer steps, handoff bindings, and symbol table declarations -- it
never consults `VariableFact` or other adapter hard facts.

### 3.5 No end-to-end structural NL to report provenance test

No integration test takes a structural NL input through the full pipeline
and asserts `section=sec_...` and `packet=p_...` in the final report.

## 4. Where Each Structural Section Ends Up

| Adapter section | Produces | Span-level provenance | Trace-level provenance |
|---|---|---|---|
| `task_family` | Packet, CompileHint (profile) | `source_section_id` on span | Resolved via span to step trace |
| `inputs_for_each_run` | Packet, VariableFact (input) | `source_section_id` on span | Resolved via span to step trace; variable trace gets empty span_ids (break 3.3) |
| `required_outputs` | Packet, VariableFact (output) | `source_section_id` on span | Variable trace: if producer step has spans, yes; otherwise assumed (break 3.4) |
| `reusable_process` | Packet, CompileHint (process) | `source_section_id` on span | Resolved via span to step trace |
| `policies` | Packet, CompileHint (constraint) | `source_section_id` on span | Resolved via span to constraint trace |
| `failure_handling` | FailureModeFact, Packet, CompileHint | `source_section_id` on span | Flow trace: NO section/packet (break 3.2); step trace inside flow: resolved via span |
| `delegation_policy` | Packet, CompileHint | `source_section_id` on span | Handoff trace: NO section/packet (break 3.2); worker trace: NO section/packet (break 3.2) |

## 5. Minimum Viable MVP+ Landing Points

### Phase 1: Flow / worker / handoff / variable section provenance

1. **Flow traces from block spans** (highest priority): `_trace_flows()` resolves
   block `spans` through `_resolve_span_origin()` to get section/packet for
   main, alternative, and exception flows.  This unblocks the failure-handling
   fixture.
2. **Worker traces from owned spans**: `_trace_worker()` accepts a span index
   mapping `owned_span_ids` to `SpanIR` objects, and resolves section/packet
   via `_resolve_span_origin()`.
3. **Handoff traces from invoke location hints**: `_trace_handoffs()` accepts
   a span index and resolves `invoke_location_hint.after_span_id` or
   `failure_policy.source_span_ids` to recover section/packet.  (Direct
   candidate-to-handoff mapping is not available -- `WorkerHandoffIR` has no
   `candidate_id` field.  Location hints are the viable indirect path.)
4. **Variable traces from adapter VariableFact**: `_trace_variables()` checks
   `VariableFact` objects (when available) as an additional provenance source
   for input/output variables.
5. **Variable traces from handoff bindings**: when a variable's producer is a
   handoff output binding, resolve section/packet from the handoff's location
   hint spans or the target worker's owned spans.

### Out of scope for MVP+ Phase 1

- Adding `source_section_id` / `source_packet_id` fields to every IR type
  (TraceRef model -- full design extension, not MVP+)
- Adding `candidate_id` to `WorkerHandoffIR` (schema change)
- Multi-turn UI or interactive provenance exploration
- Structural NL adapter changes (it already produces the data)

## 6. Proposal for Phase 1

**Task**: `source_section_id / source_packet_id` propagation to flow,
worker, handoff, and variable traces.

**Files to modify**:
- `pipeline/provenance.py` -- extend `_trace_flows`, `_trace_worker`,
  `_trace_handoffs`, `_trace_variables` to resolve section/packet from
  span index where applicable
- `pipeline/orchestrator.py` -- pass `CanonicalCompileInput` hard facts to
  the aggregator; pass worker-plan span ownership info

**New tests**:
- Flow trace (exception/alternative/main) resolves section/packet from
  block spans
- Worker trace with owned_span_ids resolves section/packet
- Handoff trace resolves section/packet from invoke_location_hint /
  failure_policy spans
- Variable trace from adapter VariableFact
- Structural NL integration fixture with section/packet in report

**Acceptance criteria**:
- Flow `TraceRecord` carries `source_section_id` when block spans have it
- Worker `TraceRecord` carries `source_section_id` when owned spans have it
- Handoff `TraceRecord` carries `source_section_id` when location hint spans
  have it
- Variable `TraceRecord` carries `source_section_id` from adapter
  VariableFact when no producer step spans exist
- `readable_report` shows `section=sec_...` for these element types
- No regressions: existing 744 tests pass

## 7. Structural NL Fixture Candidates

### Fixture 1: Required output section

```text
Required outputs:
- final_report: A compiled report of gathered sources and internal analysis.
```

Expected: `variable:final_report` trace shows `section=sec_required_outputs`.

### Fixture 2: Failure handling section

```text
Failure handling:
- Missing timeframe: The user did not provide a timeframe for the report.
```

Expected: `flow:exc_1` trace shows `section=sec_failure_handling`.

### Fixture 3: Delegation policy section

```text
Delegation policy:
- Source gathering: Delegate to a specialized source gathering agent.
  Input: user_request. Output: gathered_sources.
```

Expected: `handoff:h1` trace shows `section=sec_delegation_policy` (via
invoke_location_hint spans or failure_policy spans);
`worker:SourceGatherer` trace shows section provenance (via owned_span_ids).
