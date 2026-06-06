# IRS Authority Boundary

## Authorities

| Concern | Authority |
|---|---|
| Slot satisfaction for materialized/source-demanded constructs | IRS checker / Post-normalize IRS |
| Stage-local early reports | IRSSubsystem stage-local runtime |
| Final diagnostic merge and deduplication | DiagnosticConsolidator |
| Step renderability | ExecutableElementGate |
| Required output producer coverage | ProducerIndex |
| Feedback text | Report renderer / feedback projector |
| SPL text | Renderer |

## Stage-Local vs Final

Stage-local IRS reports are early construct satisfaction evidence.  They are
stored in intermediate state and may appear in feedback.  They do not override
post-normalize IRS, Gate, or ProducerIndex.

Post-normalize IRS is the final construct-level diagnostic authority.

`DiagnosticConsolidator` merges all diagnostic sources and suppresses duplicate
or lower-authority diagnostics using the diagnostic dedup key:

```text
(kind, target_ref, missing_slot_name, sorted(source_span_ids))
```

## Feedback Boundary

Feedback may render:

- compile diagnostics
- construct satisfaction reports
- provenance traces
- final SPL text

Feedback must not:

- run IRS
- inspect raw NL to infer missing slots
- create CompileDiagnostic
- change IR or SPL

## Configuration Boundary

All runtime switches live under:

```python
PipelineConfig.irs: IRSRuntimeConfig
```

Do not use old top-level migration flags.  The orchestrator should call
`build_irs_subsystem(config.irs)` and should not import concrete checker
classes.
