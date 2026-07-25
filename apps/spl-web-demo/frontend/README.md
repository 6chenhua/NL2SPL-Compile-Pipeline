# SPL Web Demo Frontend

Minimal API-first inspection workbench for the snapshot-driven SPL Web Demo.

## Scope

The frontend supports the T4 read workflow, T5 repair flow, and T6 live compile entry:

- natural-language requirement compilation through `POST /runs`;
- snapshot-path bootstrap;
- run and projection status;
- typed `Worker → Flow → Block → Command` SPL hierarchy;
- explicit `SEQUENTIAL`, `IF`, `WHILE`, and `FOR` Block presentation;
- hover provenance tooltips that display concrete source text without internal span IDs;
- selected-construct provenance and complete source detail;
- one unified, clickable IDE-style Problems dock and Issue Detail;
- cached explanation display and asynchronous explanation scheduling;
- `keep_in_main_flow` repair interaction for worker delegation;
- required `task_selection` and optional `additional_instruction` inputs;
- directive submission, typed preview summary, Apply, and local Cancel;
- verification result and refreshed issue/projection state;
- explicit loading, empty, error, and `unsupported_in_mvp` states.

Other repair contracts remain display-only until their public interaction and preview contracts are separately verified.

## Prerequisites

Start the FastAPI backend from the repository root:

```bash
uvicorn spl_web_demo.app:app \
  --app-dir apps/spl-web-demo/backend \
  --reload
```

The frontend development server proxies `/api` to `http://127.0.0.1:8000`, so no browser CORS configuration is required.

## Install and run

From `apps/spl-web-demo/frontend`:

```bash
npm install
npm run dev
```

Open `http://127.0.0.1:5173` and compile the prefilled example requirement. For local/debug
snapshot bootstrap, expand the secondary control and load:

```text
examples/output/demo/spl_editing_snapshot.json
```

To proxy to another backend origin:

```bash
SPL_WEB_DEMO_API_ORIGIN=http://127.0.0.1:9000 npm run dev
```

## Verification

```bash
npm run typecheck
npm test
npm run build
```

## Boundary rules

The frontend consumes only public HTTP DTOs. It does not:

- parse rendered SPL into application state;
- infer `Flow → Block → Command` containment when `parent_ref` is unavailable;
- inspect internal IR or snapshot JSON directly;
- parse diagnostic messages;
- infer repairability, patch structure, or forms for unknown interaction fields;
- send values for unsupported interaction fields;
- call a backend endpoint when the user cancels a preview;
- retain initial cards as current state when the API returns `projection_unavailable`.
