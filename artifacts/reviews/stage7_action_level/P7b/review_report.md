# P7b Review Report - General Command Action Integration

Verdict: pass

Scope:
- Residual GENERAL_COMMAND materialization is integrated in the direct API path.
- Maintain provenance for externally sourced facts appears as a no-output residual command in final SPL.
- Duplicate retrieve GENERAL_COMMAND fallback is removed only through Stage-owned metadata.

Authority boundary:
- Fallback removal no longer depends on text overlap or LLM-controlled step_id naming.
- Residual commands have outputs=[] and do not satisfy ProducerIndex requirements.

Evidence anchor: ../P9_freeze

Shared verification:
- Full pytest: 4038 passed, 14 skipped, 3 warnings.
- Stage7 regression suite: 314 passed, 2 warnings.
- run_demo --list-only: editable=7, deferred_validation=1, no source_evidence_set missing producer.
- run_demo --e2e-worker-delegation: PASS.
- Ruff scoped check: passed.
- git diff --check: exit 0, CRLF warnings only.
