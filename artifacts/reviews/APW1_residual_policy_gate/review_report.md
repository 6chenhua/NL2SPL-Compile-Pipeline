Verdict: pass

Phase:
  Residual Candidate Policy Gate between APW1 and APW2

Scope:
  touched files:
    - artifacts/reviews/APW1_residual_policy_gate/review_report.md
    - artifacts/reviews/APW1_residual_policy_gate/worker_boundary_exclusion_view.json
    - artifacts/reviews/APW1_residual_policy_gate/residual_policy_decision.md
  forbidden areas touched: no

P0 findings:
  - none

P1 findings:
  - none

P2 findings:
  - none

Evidence reviewed:
  commands:
    - .venv\Scripts\python.exe -m pytest tests/unit/pipeline/stages/stage3_5_worker_boundary_planner/test_api_exclusion_view.py -q
  artifacts:
    - examples/output/demo/external_capability_intent_resolver.json
    - artifacts/reviews/APW1_residual_policy_gate/worker_boundary_exclusion_view.json
  negative tests:
    - Gate policy forbids deleting mixed candidates merely because they contain API spans.
    - Gate policy forbids keeping original extract_child_worker after trimming API-covered spans.

Required follow-up:
  - APW2 sanitizer tests must cover API-only, mixed residual keep-main, unchanged, non-confirmed API, and silent residual loss.
  - APW3 validator/materializer must consume sanitizer result instead of re-inferring residual status from natural language.

Residual risk:
  - This gate is a policy decision and does not change production behavior by itself.

Gate answers:
  - residual candidate continues to Stage 3.5b LLM decision: no by default; it requires explicit deterministic re-evaluation evidence before extraction.
  - residual candidate risks/signals/status: APW2 must mark residual as requiring re-evaluation and, absent such evidence, auto-decide keep_in_main_worker.
  - ambiguous residual diagnostic vs audit: audit only in Stage 3.5; do not create a new diagnostic or IRS construct.
  - artifact explanation: APW2 must emit SanitizedCandidateResult showing removed_api_span_ids, residual_source_span_ids, api_call_demand_ids, result_kind, and audit reason.
