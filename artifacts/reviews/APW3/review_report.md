Verdict: pass

Phase:
  APW3 Prompt Context + Decision / Materializer Guard

Scope:
  touched files:
    - src/nl2spl/pipeline/stages/stage3_5_worker_boundary_planner/prompt_builder.py
    - src/nl2spl/pipeline/stages/stage3_5_worker_boundary_planner/decision_validator.py
    - src/nl2spl/pipeline/stages/stage3_5_worker_boundary_planner/materializer.py
    - src/nl2spl/pipeline/stages/stage3_5_worker_boundary_planner/executor.py
    - src/nl2spl/pipeline/orchestrator.py
    - tests/unit/pipeline/stages/stage3_5_worker_boundary_planner/test_api_exclusion_decision_guard.py
  forbidden areas touched: no

P0 findings:
  - none

P1 findings:
  - none

P2 findings:
  - none

Evidence reviewed:
  commands:
    - .venv\Scripts\python.exe -m pytest tests/unit/pipeline/stages/stage3_5_worker_boundary_planner tests/unit/pipeline/stages/test_stage3_5_worker_boundary_planner.py -q
    - .venv\Scripts\ruff.exe check src/nl2spl/pipeline/stages/stage3_5_worker_boundary_planner src/nl2spl/pipeline/orchestrator.py tests/unit/pipeline/stages/stage3_5_worker_boundary_planner
    - git diff --check -- src/nl2spl/pipeline/stages/stage3_5_worker_boundary_planner src/nl2spl/pipeline/orchestrator.py tests/unit/pipeline/stages/stage3_5_worker_boundary_planner
  artifacts:
    - Stage 3.5a checkpoint now carries worker_boundary_exclusion_view and sanitization_results when an external capability plan is supplied.
  negative tests:
    - prompt contains API-consumed span section
    - stale boundary_kind=integration_call rejected
    - stale extract_child_worker consuming API span rejected
    - mixed extract_child_worker with API span rejected
    - materializer rejects API-owned child worker even if validator is bypassed

Required follow-up:
  - APW7a must verify real demo artifacts after orchestrator passes external_capability_intent_plan to Stage 3.5.

Residual risk:
  - APW3 does not yet fix WORKER_PROMOTION subject presentation; APW4 owns that.

APW3 checks:
  - Prompt contains API-consumed spans and mixed candidate instruction: pass
  - Prompt is not the only defense: pass
  - Validator rejects stale enum integration_call: pass
  - Validator/materializer reject API-owned extract_child_worker: pass
  - Materializer does not create API-owned child worker: pass
  - Mixed accepted child decision lacking residual re-evaluation fails closed: pass
