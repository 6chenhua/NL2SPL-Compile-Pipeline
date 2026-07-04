# Residual Candidate Policy Decision

Decision:

```text
If a candidate contains api_consumed_span_ids, those spans must be removed from
child-worker ownership.

API-only candidate:
  decision = compile_as_call_api
  boundary_kind = call_api

Mixed candidate:
  residual_source_span_ids = candidate.source_span_ids - api_consumed_span_ids
  removed_api_span_ids = candidate.source_span_ids & api_consumed_span_ids
  requires_residual_re_evaluation = true

If residual does not have explicit deterministic re-evaluation evidence:
  decision = keep_in_main_worker
  boundary_kind = not_a_worker
  rejection_reason = insufficient_semantic_boundary
  audit reason = residual_after_api_exclusion_insufficient
```

Rationale:

```text
Trimming API-covered spans must not inherit the original extract_child_worker
decision. The residual may later become a worker only after independent
re-evaluation proves a worker boundary. Ambiguous residuals are audit-only at
Stage 3.5 and must not create a new diagnostic or IRS construct.
```
