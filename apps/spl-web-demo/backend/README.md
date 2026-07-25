# SPL Web Demo Backend

This directory exposes the framework-agnostic `SplWebDemoApi` handlers through a thin FastAPI adapter.

## Install

From the repository root:

```bash
pip install -e ".[web-demo]"
```

## Run

```bash
uvicorn spl_web_demo.app:app \
  --app-dir apps/spl-web-demo/backend \
  --reload
```

The API prefix is `/api/demo/v1`. Interactive OpenAPI documentation is available at `/api/demo/docs`.

The initial local/debug bootstrap endpoint is:

```text
POST /api/demo/v1/runs/from-snapshot
```

It registers an existing canonical SPL Editing snapshot. The initial structured read-model is available through:

```text
GET /api/demo/v1/runs/{run_id}/spl
GET /api/demo/v1/runs/{run_id}/constructs
GET /api/demo/v1/runs/{run_id}/constructs/{construct_ref}/provenance
GET /api/demo/v1/runs/{run_id}/spans/{span_id}
```

These endpoints project a typed SPL presentation hierarchy from snapshot artifacts:

```text
WORKER
  → FLOW / EXCEPTION_FLOW
    → BLOCK (SEQUENTIAL / IF / WHILE / FOR)
      → COMMAND
```

Every card exposes `parent_ref` and `construct_path`. A `StepIR` is presented as an SPL `COMMAND`, not as a user-facing `STEP`. Commands without a verified Flow/Block placement are returned as `review_only` with `hierarchy_status=unplaced`; the projector does not invent a containing Block.

The same endpoints expose `TraceRecord` provenance and complete source text. They do not reverse-parse rendered output, human-readable reports, or diagnostic messages.

Issue explanations can be requested through:

```text
POST /api/demo/v1/runs/{run_id}/issues/{issue_id}/explanation
```

The route schedules snapshot-level explanation generation through an injected scheduler and returns only the target issue envelope. It never calls an LLM directly. `ready` requests are idempotent; an existing `pending` job is not duplicated.

Preview cancel has no backend endpoint in this MVP. Cancel means the client discards the current `preview_id` and does not call apply. This does not create an overlay, run verification, or change issue state. Server-side cleanup will be added only after a stable public preview lifecycle contract exists.

Live compilation is available through:

```text
POST /api/demo/v1/runs
```

The request accepts `raw_text`, optional `language`, and
`precompute_issue_explanations` (default `false`). The thin route delegates to an injected compiler
facade; it does not orchestrate pipeline stages. A successful snapshot is registered through the
same read-model path as `from-snapshot`.

The passing real-LLM gate is recorded at:

```text
apps/spl-web-demo/.probe-output/20260710T100142Z/live_compile_smoke.summary.json
```

It completed in 56.19 seconds and selected `synchronous_candidate` against a 120-second budget.

Run the dedicated `live_compile_smoke` contract-probe case from the repository root:

```powershell
.\.venv\Scripts\python.exe apps/spl-web-demo/backend/contract_probe/live_compile_probe.py
```

The case uses the checked-in smoke input unless `--raw-text` or `--input-file` is supplied. It records compile duration, success rate, the runtime `PipelineResult` field manifest, snapshot state, Web Demo registration/read results, and a synchronous-versus-asynchronous transport recommendation. Snapshot persistence explicitly uses `precompute_issue_explanations=false`.

Optional stability and latency parameters:

```powershell
.\.venv\Scripts\python.exe apps/spl-web-demo/backend/contract_probe/live_compile_probe.py `
  --compile-attempts 3 `
  --sync-budget-seconds 120
```
