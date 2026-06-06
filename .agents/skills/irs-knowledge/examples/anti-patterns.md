# IRS Anti-Patterns

## 1. Recomputing Semantics in a Checker

Do not parse raw NL or add keyword-based semantic rules inside an IRS checker.

```python
# Wrong
if "ask user" in span.text.lower():
    slot.status = "present"
```

IRS consumes structured evidence already present in IR, annotations, metadata,
or ConstructPlan.  If semantic understanding is required, propose the LLM or
rule-based approach separately and get approval before implementation.

## 2. Creating Diagnostics Inside a Checker

```python
# Wrong
return CompileDiagnostic(kind="type_or_contract_ambiguity")
```

Checkers return `ConstructSatisfactionReport`.  `DiagnosticProjector` converts
slot diagnostic kinds into `CompileDiagnostic` objects.

## 3. Hard-Coding Slot Contracts

```python
# Wrong
required = {"input_contract", "output_contract"}
```

Use `ConstructIRS.slots` and `SlotSpec`.  Registry definitions are the slot
contract authority.

## 4. Mutating IR

```python
# Wrong
worker_plan.workers.append(new_worker)
```

IRS is an analysis subsystem.  It must not generate or repair constructs.

## 5. Importing Concrete Checkers in Orchestrator

```python
# Wrong
from nl2spl.compiler.irs.checkers.worker_delegation import WorkerDelegationIRSChecker
```

The orchestrator should build `IRSSubsystem` from `PipelineConfig.irs` and call
the subsystem.  Concrete checker registration belongs in the factory.

## 6. Adding Migration Flags to PipelineConfig

```python
# Wrong
enable_irs_example_checker: bool = False
```

Use the productized policy object:

```python
PipelineConfig.irs: IRSRuntimeConfig
```

If a new feature toggle is necessary, add it to `IRSRuntimeConfig` and test the
factory behavior.

## 7. Treating Feedback as Authority

Feedback rendering must not rerun IRS, infer slots, or create diagnostics.  It
only projects existing reports and diagnostics into text.

## 8. Hiding Stage-Local Diagnostics in Final Compile Output

Stage-local diagnostics are early signals.  Final compile diagnostics are
merged by `DiagnosticConsolidator`, with post-normalize IRS and Gate carrying
final authority.  Stage-local diagnostics should remain in intermediate
results unless policy explicitly opts into including unique stage-local items.
