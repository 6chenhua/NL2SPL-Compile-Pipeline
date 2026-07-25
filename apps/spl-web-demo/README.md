# SPL Web Demo

Lightweight service-contract workbench for live NL2SPL compilation, structured SPL inspection,
source provenance, issue explanations, and the verified worker-delegation repair flow.

## Install

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev,web-demo]"
Set-Location apps/spl-web-demo/frontend
npm install
```

## Run

Start the backend from the repository root:

```powershell
.\.venv\Scripts\python.exe -m uvicorn spl_web_demo.app:app `
  --app-dir apps/spl-web-demo/backend `
  --host 127.0.0.1 `
  --port 8000
```

Start the frontend in a second terminal:

```powershell
Set-Location apps/spl-web-demo/frontend
npm run dev
```

Open `http://127.0.0.1:5173/`. The frontend proxies `/api` to the backend, so local CORS setup is
not required.

## Demo Flows

- Enter an initial natural-language requirement and select **Generate SPL IR**.
- Inspect the typed `Worker → Flow → Block → Command` hierarchy.
- Hover a construct to read concrete source evidence without internal span identifiers.
- Review all clickable diagnostics in the unified IDE-style Problems dock.
- Open Issue Detail for cached or scheduled AI explanations and repair controls.
- For the verified worker-delegation issue, run interaction -> directive -> preview -> apply, or
  cancel the preview without applying.
- Expand **Debug snapshot bootstrap** to load
  `examples/output/demo/spl_editing_snapshot.json` without a live compile.

The live endpoint is synchronous:

```text
POST /api/demo/v1/runs
```

The real-LLM Contract Probe completed in 56.19 seconds against a 120-second budget. Runtime outputs
are written below `apps/spl-web-demo/.runtime-output/` and are intentionally ignored by Git.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/apps/spl_web_demo -q
.\.venv\Scripts\python.exe -m ruff check `
  apps/spl-web-demo/backend `
  tests/unit/apps/spl_web_demo
.\.venv\Scripts\python.exe -m ruff format --check `
  apps/spl-web-demo/backend `
  tests/unit/apps/spl_web_demo

Set-Location apps/spl-web-demo/frontend
npm run typecheck
npm test
npm run build
npm audit --audit-level=moderate
```

## Known Limits

- Live compilation is a synchronous local-demo request; no job queue is included.
- After repair apply, no public patched SPL/Card read-model exists. The API returns HTTP 200 with
  `projection_unavailable`, `rendered_spl=null`, and empty cards instead of stale initial output.
- Only the probed worker-delegation `keep_in_main_flow` repair is enabled in the frontend.
- Other repair contracts remain display-only until each has its own public-contract probe.
- `POST /runs/from-snapshot` is local/debug-only.
- The current FastAPI TestClient stack emits one non-blocking Starlette/httpx deprecation warning.
