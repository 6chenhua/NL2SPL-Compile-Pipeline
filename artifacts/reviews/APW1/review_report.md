Verdict: pass

Phase:
  APW1 WorkerBoundaryExclusionView

Scope:
  touched files:
    - src/nl2spl/pipeline/stages/stage3_5_worker_boundary_planner/api_exclusion.py
    - src/nl2spl/pipeline/stages/stage3_5_worker_boundary_planner/__init__.py
    - tests/unit/pipeline/stages/stage3_5_worker_boundary_planner/test_api_exclusion_view.py
    - tests/unit/pipeline/stages/stage3_5_worker_boundary_planner/test_apw0_current_gap_lock.py
    - artifacts/reviews/APW1/review_report.md
    - artifacts/reviews/APW1/commands.log
    - artifacts/reviews/APW1/pytest_output.txt
    - artifacts/reviews/APW1/ruff_output.txt
    - artifacts/reviews/APW1/diff_check_output.txt
    - artifacts/reviews/APW1/manifest.json
  forbidden areas touched: no

P0 findings:
  - none

P1 findings:
  - none

P2 findings:
  - none

Evidence reviewed:
  commands:
    - .venv\Scripts\python.exe -m pytest tests/unit/pipeline/stages/stage3_5_worker_boundary_planner/test_api_exclusion_view.py tests/unit/pipeline/stages/stage3_5_worker_boundary_planner/test_apw0_current_gap_lock.py tests/unit/pipeline/stages/test_stage3_5_worker_boundary_planner.py -q
    - .venv\Scripts\ruff.exe check src/nl2spl/pipeline/stages/stage3_5_worker_boundary_planner/api_exclusion.py src/nl2spl/pipeline/stages/stage3_5_worker_boundary_planner/__init__.py tests/unit/pipeline/stages/stage3_5_worker_boundary_planner/test_api_exclusion_view.py tests/unit/pipeline/stages/stage3_5_worker_boundary_planner/test_apw0_current_gap_lock.py
    - git diff --check -- src/nl2spl/pipeline/stages/stage3_5_worker_boundary_planner/api_exclusion.py src/nl2spl/pipeline/stages/stage3_5_worker_boundary_planner/__init__.py tests/unit/pipeline/stages/stage3_5_worker_boundary_planner/test_api_exclusion_view.py tests/unit/pipeline/stages/stage3_5_worker_boundary_planner/test_apw0_current_gap_lock.py
  artifacts:
    - examples/output/demo/external_capability_intent_resolver.json
    - WorkerBoundaryExclusionView payload generated in unit test from real demo artifact
  negative tests:
    - non-confirmed / non-executable API intent does not enter api_consumed_span_ids
    - missing plan builds an empty view without side effects
    - module does not define CompileDiagnostic, ConstructIRS, diagnostic_id, or missing_slot

Required follow-up:
  - Use the APW1 view payload for the Residual Candidate Policy gate before APW2.
  - APW2 must project sanitizer result into real deterministic intermediate / artifact.

Residual risk:
  - APW1 intentionally does not connect the view into Stage 3.5 execution, so current bad Stage 3.5 output remains locked by APW0.

APW1 checks:
  - View only reads structured resolver output: pass
  - confirmed/executable/admitted invocation enters consumed set: pass
  - non-confirmed / non-executable API does not enter consumed set: pass
  - api_call_demand_ids_by_span is auditable: pass
  - View does not create diagnostic / IRS / repair target: pass
  - Stage 3.5 output unchanged; original Stage 3.5 tests pass: pass
