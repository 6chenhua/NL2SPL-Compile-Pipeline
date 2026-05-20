# LLM InputAdapter Engine Execution Plan

**Date**: 2026-05-15
**Status**: Draft for phased implementation
**Motivation**: Live LLM E2E exposed that structural failure facts can be
recognized by the adapter but still disappear before the compiler has an
`ExceptionFlow` to diagnose.  The next step is to improve input adaptation
without weakening the teacher-aligned fidelity rule: do not silently invent
missing design details.

## 1. Goal

Introduce an optional LLM-backed semantic engine inside the InputAdapter layer
to extract evidence-bound canonical facts from incomplete natural language.

The engine must improve recognition of:

- failure modes
- required outputs / runtime inputs
- delegation intent
- adapter-level compile hints

It must not replace the deterministic adapter envelope, provenance assignment,
or verifier.

## 2. Non-Goals

This project must not:

- replace `CanonicalCompileInput` with raw LLM output
- let LLM facts enter the pipeline without source evidence
- generate handler steps from failure modes
- generate producer steps for required outputs
- generate executable worker/API calls from vague delegation language
- introduce a multi-turn clarification UI
- require a full TraceRef schema migration

## 3. Target Architecture

```text
raw input
  -> deterministic adapter envelope
     - detect schema
     - split sections when available
     - assign section ids
     - create stable packet/span evidence anchors
  -> optional LLM adapter engine
     - extract fact candidates
     - every fact must cite packet/span/section evidence
  -> deterministic verifier
     - reject uncited facts
     - validate references
     - normalize names
     - emit adapter warnings
  -> CanonicalCompileInput
  -> deterministic fact-to-IR bridges
     - FailureModeFact -> partial ExceptionFlow skeleton
     - DelegationIntentFact -> non-renderable traceable candidate
  -> existing compiler pipeline
```

The LLM engine is an interpretation helper.  The adapter wrapper and verifier
remain the trust boundary.

## 4. Design Principles

1. **Evidence first**
   Every LLM-produced fact must cite existing evidence.  At minimum this means
   `source_section_id`; for MVP it should also include `source_packet_id` or
   `source_span_ids` when available.

2. **Facts are not executable behavior**
   A `FailureModeFact` is not a handler.  A `DelegationIntentFact` is not an
   executable `INVOKE_WORKER`.  A required output is not a producer.

3. **Verifier beats LLM**
   Invalid, uncited, or out-of-schema LLM output is dropped or downgraded to an
   adapter warning.  It must not silently enter `CanonicalCompileInput`.

4. **Partial structures are allowed**
   If the source states a failure condition but no handler, create a partial
   `ExceptionFlow` skeleton and let `missing_handler` explain the gap.

5. **No demand, no structure**
   Do not generate failure flows, delegation candidates, outputs, APIs, or
   worker contracts unless the input has evidence for them.

## 5. New / Extended Data Contracts

### 5.1 EvidenceRef

Add a small canonical evidence object instead of adding many loose fields:

```python
@dataclass
class EvidenceRef:
    source_section_id: str
    source_packet_id: str | None = None
    source_span_ids: list[str] = field(default_factory=list)
    quoted_text: str | None = None
```

Acceptance:

- `source_section_id` is required.
- `source_packet_id` is preferred for structural input.
- `source_span_ids` is filled after Stage 1 when possible, or left empty if the
  fact is created before spans exist.
- `quoted_text` is optional and used only for report/debugging.

### 5.2 Extend Existing Facts

Extend canonical facts conservatively:

```python
VariableFact.evidence: list[EvidenceRef] = field(default_factory=list)
FailureModeFact.evidence: list[EvidenceRef] = field(default_factory=list)
CompileHint.evidence: list[EvidenceRef] = field(default_factory=list)
```

Backward compatibility:

- Keep existing `source_section_id` fields.
- Existing deterministic adapters continue to work.
- If `evidence` is empty, derive a single `EvidenceRef` from
  `source_section_id`.

### 5.3 DelegationIntentFact

Add a non-executable hard/hint fact for delegation intent:

```python
@dataclass
class DelegationIntentFact:
    name: str
    text: str
    suggested_worker_name: str | None
    input_names: list[str] = field(default_factory=list)
    output_names: list[str] = field(default_factory=list)
    evidence: list[EvidenceRef] = field(default_factory=list)
```

Add to `HardFacts` or `CompileHints` depending on implementation preference.
Recommended MVP choice:

```python
HardFacts.delegation_intents: list[DelegationIntentFact]
```

Rationale: the source explicitly says delegation exists, but the compiler still
must decide whether it is renderable.

## 6. Phase Plan

## Phase 0: Baseline and Guardrails

**Purpose**: freeze current live E2E failure and prevent regressions.

Files:

- `docs/implementation/mvp_live_e2e_check_report.md`
- `tests/integration/test_partial_spl_mvp.py`
- new tests under `tests/integration/test_llm_adapter_engine_e2e.py` or
  deterministic fixtures first

Tasks:

- Add a regression fixture for structural failure handling:
  `failure_handling` section with one failure mode and no handler.
- Assert current expected future behavior as `xfail` or keep it in a planning
  fixture until Phase 4:
  - exception flow skeleton exists
  - no `REQUEST_INPUT`
  - `missing_handler`
  - `partial`
  - `section=sec_failure_handling`
- Add a second fixture for incomplete delegation:
  - no executable `INVOKE_WORKER`
  - diagnostic present
  - delegation evidence visible in report

Acceptance:

- Baseline documents the live gap.
- Tests make the target behavior concrete.
- No production code changes yet except optional test scaffolding.

## Phase 1: EvidenceRef and Canonical Contract Extension

**Purpose**: give adapter facts enough provenance to be verified and bridged
deterministically.

Files:

- `src/nl2spl/canonical/compile_input.py`
- `src/nl2spl/canonical/__init__.py`
- `src/nl2spl/adapters/structural_nl.py`
- `tests/unit/test_canonical_compile_input.py` or equivalent
- `tests/unit/test_input_adapter_pipeline.py`

Tasks:

1. Add `EvidenceRef`.
2. Add optional `evidence` to `VariableFact`, `FailureModeFact`, and
   `CompileHint`.
3. Add `DelegationIntentFact`.
4. Extend `HardFacts` with `delegation_intents`.
5. Update `CanonicalCompileInputValidator`:
   - evidence section ids must exist
   - evidence packet ids must belong to the referenced section when checkable
   - duplicate fact names still rejected
6. Update `StructuralNLAdapter` to populate evidence for:
   - runtime inputs
   - required outputs
   - failure modes
   - delegation intents/hints

Acceptance:

- Existing tests pass without caller changes.
- Deterministic structural adapter emits evidence for hard facts.
- Invalid evidence references become validation errors.
- No LLM is introduced in this phase.

## Phase 2: LLM Adapter Engine Interface

**Purpose**: create a narrow optional engine that can be used by generic or
structural adapters without changing the compiler pipeline.

Files:

- `src/nl2spl/adapters/llm_engine.py`
- `src/nl2spl/adapters/semantic_fact_engine.py` or similar
- `prompts/input_adapter_fact_extractor_system.txt`
- `tests/unit/test_llm_adapter_engine_parser.py`

Interfaces:

```python
class AdapterSemanticEngine(Protocol):
    def extract(
        self,
        raw_text: str,
        sections: list[RawSection],
        packets: list[SemanticPacket],
    ) -> AdapterFactExtraction:
        ...
```

Output DTO:

```python
@dataclass
class AdapterFactExtraction:
    inputs: list[VariableFact]
    outputs: list[VariableFact]
    failure_modes: list[FailureModeFact]
    delegation_intents: list[DelegationIntentFact]
    warnings: list[AdapterWarning] = field(default_factory=list)
```

Prompt rules:

- Return JSON only.
- Every fact must cite existing `source_section_id`.
- If packet ids are provided, cite `source_packet_id`.
- Do not invent missing handler actions.
- Do not invent producer steps.
- Do not invent worker/API contracts.
- If uncertain, emit no fact and add a warning.

Acceptance:

- Parser rejects malformed JSON.
- Parser rejects facts with missing evidence.
- Parser rejects citations to unknown sections/packets.
- Parser preserves adapter warnings.
- Unit tests use fake LLM responses; no network dependency.

## Phase 3: Evidence Verifier and Merge Policy

**Purpose**: keep LLM facts from polluting the canonical input.

Files:

- `src/nl2spl/adapters/fact_verifier.py`
- `tests/unit/test_adapter_fact_verifier.py`

Verifier rules:

- Unknown section id -> reject fact, emit adapter warning.
- Unknown packet id -> reject fact or downgrade to section-only evidence,
  depending on strictness setting.
- Empty evidence -> reject fact.
- Duplicate variable names:
  - deterministic structural fact wins
  - LLM duplicate is rejected or merged only if description is compatible
- Failure modes:
  - must have a failure-like condition text
  - no handler action is inferred
- Delegation intents:
  - may record suggested worker/input/output names
  - must not mark itself renderable

Merge priority:

```text
deterministic hard facts > verified LLM hard facts > hints > warnings
```

Acceptance:

- Verified facts are deterministic given the same LLM JSON.
- Rejected facts appear as adapter warnings.
- Existing `adapter_warnings` remain separate from compile diagnostics.

## Phase 4: FailureModeFact -> Partial ExceptionFlow Bridge

**Purpose**: fix the live E2E gap without asking Stage 4 to infer failure
flows from rules.

Files:

- `src/nl2spl/pipeline/fact_bridges.py`
- `src/nl2spl/pipeline/orchestrator.py`
- `src/nl2spl/pipeline/stages/stage4_flow_assembler/*` only if necessary
- `tests/unit/test_failure_mode_bridge.py`
- `tests/integration/test_partial_spl_mvp.py`

Bridge behavior:

```text
For each FailureModeFact:
  if no existing ExceptionFlow cites the same evidence:
    create ExceptionFlow(
      flow_id="exc_adapter_<n>",
      condition_text=fact.text,
      spans=<resolved span ids from evidence>
    )
```

Rules:

- Do not create handler blocks with executable steps.
- If span ids are unavailable, resolve from `SemanticPacket` or Stage 1
  `SpanIR` by section/packet.
- Preserve `source_section_id=sec_failure_handling` through provenance.
- Run before Stage 5 block assembly or immediately after Stage 4 with a
  compatible empty block strategy.

Recommended insertion point:

```text
Stage 4 flow assembly
  -> apply FailureModeFact bridge
  -> Stage 5 block assembly
```

Acceptance:

- Structural failure mode without handler yields exception-flow skeleton.
- SPL includes `[EXCEPTION_FLOW: ...]` and `[END_EXCEPTION_FLOW]`.
- SPL does not include invented `REQUEST_INPUT`.
- `missing_handler` emitted.
- completeness is `partial`.
- report trace includes `section=sec_failure_handling`.

## Phase 5: DelegationIntentFact -> Traceable Non-Renderable Candidate

**Purpose**: preserve delegation provenance even when the delegation is not
renderable.

Files:

- `src/nl2spl/pipeline/fact_bridges.py`
- `src/nl2spl/pipeline/provenance.py`
- `src/nl2spl/compiler/diagnostic_analyzer.py`
- `src/nl2spl/pipeline/executable_gate.py` only if needed
- `tests/unit/test_delegation_intent_bridge.py`
- `tests/integration/test_partial_spl_mvp.py`

Bridge behavior:

- Convert `DelegationIntentFact` into a non-executable candidate/diagnostic
  target.
- If planner later creates a valid handoff, normal worker/handoff rendering
  proceeds.
- If no valid handoff exists, do not render `INVOKE_WORKER`.
- Emit or preserve `type_or_contract_ambiguity` /
  `assumed_command_not_renderable`.
- Add provenance target such as:

```text
delegation_intent:<name>
```

Acceptance:

- Incomplete delegation still has no executable invoke.
- Report contains diagnostics.
- Report contains provenance for `section=sec_delegation_policy`.
- Complete delegation behavior remains unchanged.

## Phase 6: GenericNLAdapter LLM Fact Extraction

**Purpose**: use the LLM engine for unstructured natural language where no
section headings exist.

Files:

- `src/nl2spl/adapters/generic_nl.py`
- `src/nl2spl/adapters/registry.py`
- `tests/unit/test_generic_nl_llm_adapter.py`

Strategy:

- Deterministically create a synthetic section:

```text
section_id = sec_freeform_input
canonical_title = freeform_input
```

- Split raw text into packets using conservative sentence/paragraph boundaries.
- Ask LLM engine to extract evidence-bound facts citing packet ids.
- Verify and merge.

Acceptance:

- Freeform failure mode can become `FailureModeFact`.
- Freeform required output can become `VariableFact`.
- No uncited fact enters canonical input.
- If LLM unavailable, adapter falls back to current behavior with warning.

## Phase 7: StructuralNLAdapter Optional LLM Enrichment

**Purpose**: improve structural inputs when deterministic parsing is incomplete.

Files:

- `src/nl2spl/adapters/structural_nl.py`
- `src/nl2spl/config.py` or existing config location
- `tests/unit/test_structural_nl_llm_enrichment.py`

Config:

```text
NL2SPL_ADAPTER_LLM_ENGINE=off|generic_only|structural_enrich|all
```

Default recommendation:

```text
off in tests unless explicitly enabled
generic_only for early live experiments
```

Merge policy:

- Deterministic section facts win.
- LLM may add missing descriptions, additional failure modes, or delegation
  intents only with evidence.
- LLM may not overwrite deterministic names unless alias normalization confirms
  equivalence.

Acceptance:

- Existing structural deterministic tests pass with engine off.
- Engine-on tests use fake LLM responses.
- Live run can be enabled through config without code changes.

## Phase 8: Live E2E Acceptance

**Purpose**: prove the expected effect with real LLM calls.

Inputs:

- `docs/implementation/e2e_inputs/required_output_without_producer.txt`
- `docs/implementation/e2e_inputs/failure_condition_without_handler.txt`
- `docs/implementation/e2e_inputs/structural_provenance_sections.txt`
- add one freeform NL fixture for generic adapter behavior

Commands:

```powershell
$env:PYTHONPATH = ".pytest_deps;src"
python -m nl2spl.main docs/implementation/e2e_inputs/failure_condition_without_handler.txt --output-dir output/e2e-live --run-name failure-handler
```

Acceptance:

- Required output scenario remains `partial` with `missing_output_producer`.
- Failure-only scenario now has:
  - exception flow skeleton
  - no invented `REQUEST_INPUT`
  - `missing_handler`
  - `partial`
  - `section=sec_failure_handling`
- Incomplete delegation scenario has:
  - no executable `INVOKE_WORKER`
  - diagnostic present
  - `section=sec_delegation_policy` provenance visible
- Freeform scenario shows LLM adapter facts only when evidence-bound.

## 7. Test Matrix

| Layer | Test type | Required cases |
| --- | --- | --- |
| Canonical contract | unit | EvidenceRef validation, backward compatibility, duplicate facts |
| LLM parser | unit | valid JSON, malformed JSON, unknown citation, uncited fact |
| Verifier | unit | deterministic fact wins, rejected fact warning, merge behavior |
| Failure bridge | unit/integration | failure fact -> exception skeleton -> missing_handler |
| Delegation bridge | unit/integration | incomplete intent -> no invoke + provenance |
| Generic adapter | unit/integration | freeform failure/output facts with evidence |
| Structural adapter | unit/integration | enrichment on/off behavior |
| Live E2E | manual/optional CI | three MVP fixtures plus one freeform fixture |

## 8. Engineering Risks and Controls

| Risk | Control |
| --- | --- |
| LLM invents facts | verifier rejects uncited facts |
| LLM changes deterministic structural output | deterministic facts take precedence |
| Failure mode becomes invented handler | bridge creates only skeleton, never handler step |
| Delegation intent becomes executable invoke | gate still requires valid handoff contract |
| Report becomes noisy | adapter warnings separated; report can group rejected facts |
| Tests become network-dependent | unit tests use fake LLM responses; live E2E is separate |

## 9. Definition of Done

This work is complete when:

1. The adapter can optionally use an LLM semantic engine.
2. Every accepted LLM fact is evidence-bound.
3. Uncited LLM facts are rejected with adapter warnings.
4. Structural failure modes create partial exception-flow skeletons.
5. Missing handlers are diagnosed without invented handler commands.
6. Incomplete delegation is non-renderable but provenance-visible.
7. Required output behavior from MVP remains unchanged.
8. Live E2E passes the expected-output contract in
   `mvp_e2e_expected_outputs.md`.

## 10. Recommended Implementation Order

```text
Phase 0: Baseline tests and target fixtures
Phase 1: EvidenceRef + canonical contract extension
Phase 2: LLM adapter engine interface and parser
Phase 3: deterministic fact verifier and merge policy
Phase 4: FailureModeFact -> partial ExceptionFlow bridge
Phase 5: DelegationIntentFact -> traceable non-renderable candidate
Phase 6: GenericNLAdapter LLM extraction
Phase 7: StructuralNLAdapter optional enrichment
Phase 8: live E2E acceptance
```

Do not start with live LLM integration.  First make the evidence contract and
bridges deterministic, then let the LLM populate those contracts.
