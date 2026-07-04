Verdict: pass

Phase:
  APW2 Candidate Sanitizer

Scope:
  touched files:
    - src/nl2spl/pipeline/stages/stage3_5_worker_boundary_planner/candidate_sanitizer.py
    - src/nl2spl/pipeline/stages/stage3_5_worker_boundary_planner/executor.py
    - src/nl2spl/pipeline/stages/stage3_5_worker_boundary_planner/__init__.py
    - tests/unit/pipeline/stages/stage3_5_worker_boundary_planner/test_candidate_sanitizer.py
    - artifacts/reviews/APW2/review_report.md
    - artifacts/reviews/APW2/commands.log
    - artifacts/reviews/APW2/pytest_output.txt
    - artifacts/reviews/APW2/ruff_output.txt
    - artifacts/reviews/APW2/diff_check_output.txt
    - artifacts/reviews/APW2/manifest.json
  forbidden areas touched: no

P0 findings:
  - none

P1 findings:
  - none

P2 findings:
  - none

Evidence reviewed:
  commands:
    - .venv\Scripts\python.exe -m pytest tests/unit/pipeline/stages/stage3_5_worker_boundary_planner/test_candidate_sanitizer.py tests/unit/pipeline/stages/stage3_5_worker_boundary_planner/test_api_exclusion_view.py tests/unit/pipeline/stages/stage3_5_worker_boundary_planner/test_apw0_current_gap_lock.py tests/unit/pipeline/stages/test_stage3_5_worker_boundary_planner.py -q
    - .venv\Scripts\ruff.exe check <APW2 touched files>
    - git diff --check -- <APW2 touched files>
    - rg -n "SanitizedCandidateResult|mixed_trimmed_candidate|api_only_auto_decision|if .*overlap|integration_call|drop candidate|api_consumed_span_ids" src/nl2spl/pipeline/stages/stage3_5_worker_boundary_planner tests/unit/pipeline/stages/stage3_5_worker_boundary_planner
  artifacts:
    - Stage 3.5a checkpoint projection verified in test_candidate_sanitizer.py
  negative tests:
    - API-only candidate auto-decides compile_as_call_api/call_api
    - mixed candidate removes only API spans and keeps residual
    - mixed residual defaults to keep_in_main_worker plus audit reason
    - non-overlapping and non-consumed residual API spans are unchanged
    - executor writes sanitization_results to real checkpoint payload

Required follow-up:
  - APW3 must add prompt context and fail-closed validator/materializer guards that consume sanitizer result.
  - Orchestrator must pass external_capability_intent_plan into Stage 3.5 before APW7a E2E.

Residual risk:
  - APW2 executor supports a five-element input for the external capability plan, but production orchestrator is not wired to pass it yet.

APW2 checks:
  - API-only candidate -> compile_as_call_api / call_api: pass
  - mixed candidate only removes API spans and preserves residual: pass
  - residual ambiguous -> keep_in_main_worker + audit reason: pass
  - SanitizedCandidateResult enters deterministic checkpoint payload: pass
  - APW3 can consume structured sanitizer result: pass
  - existing WorkerPlanIR enum unchanged: pass
