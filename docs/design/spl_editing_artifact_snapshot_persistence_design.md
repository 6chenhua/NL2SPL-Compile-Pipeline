# SPL Editing ArtifactSnapshot Persistence Design

Status: Design proposal

Related documents:

- `docs/design/spl_editing_architecture_design_v2.md`
- `docs/implementation/spl-editing-backend-implementation-plan.md`
- `docs/implementation/spl-editing-readiness-implementation-plan.md`

## 1. Purpose

AI-assisted SPL Editing needs a structured compiler-state artifact that can be
loaded after an NL2SPL compile run. The editing backend must not reconstruct
state from rendered SPL, compile reports, feedback reports, or debug text.

The purpose of this design is to define the persistence contract for a frozen
`ArtifactSnapshot` emitted by NL2SPL at the end of a compile run.

This snapshot is the handoff point between:

- NL2SPL compile pipeline
- SPL Editing issue extraction
- SPL Editing repair suggestion generation
- patch application
- Lane A / Lane B compiler-authority replay
- future UI diagnostics console

## 2. Current Gap

Current NL2SPL output directories contain files such as:

- `final_spl.txt`
- `compile_report.txt`
- `feedback_report.md`
- stage-level `stage*.json` debug artifacts

These are not sufficient as the primary input for SPL Editing.

The missing artifact is a single structured snapshot that preserves the typed
IR objects and final diagnostics needed by the editing backend.

## 3. Design Goal

After a normal NL2SPL run, the run output directory should contain a persisted
SPL Editing snapshot:

```text
output/<run_name>/snapshot.pkl
```

or an equivalent configured filename that is treated as the canonical SPL
Editing artifact.

The persisted snapshot represents overlay version `0` of the compile result.
All future editing overlays are derived from this immutable base snapshot.

## 4. Non-Goals

This design does not introduce:

- parsing `final_spl.txt` back into IR;
- parsing `compile_report.txt` or `feedback_report.md` for issue discovery;
- a second diagnostic model for SPL Editing;
- repair execution inside IRS;
- LLM calls during snapshot persistence;
- automatic patch generation during NL2SPL compilation;
- a new compiler replay path outside Lane A / Lane B.

The snapshot is a persistence boundary, not a repair engine.

## 5. Artifact Contract

The persisted artifact should be a complete `ArtifactSnapshot` for one compile
run.

Required identity fields:

- `compile_run_id`
- `snapshot_id`
- `overlay_version`

For a base compile output:

- `overlay_version` must be `0`.
- `compile_run_id` must identify the NL2SPL run.
- `snapshot_id` must identify the frozen artifact set for that run.

Required compiler artifacts:

- canonical input
- span list
- route IR
- worker plan
- worker flow plan
- worker block plan
- worker step plan
- global resource registry
- worker-scoped resources, if produced
- symbol table
- constraints
- agent profile
- post-gate final worker, if available
- final SPL text
- final compile diagnostics
- provenance traces

The exact storage format can evolve, but the loaded object must provide the
same semantic information as `ArtifactSnapshot`.

## 6. Diagnostic Contract

`compile_diagnostics` inside the snapshot are part of the editing contract.
They must be the final consolidated diagnostics exposed by the compiler, not a
raw stage-local debug list.

Each editable IRS-derived diagnostic must preserve:

- diagnostic id
- diagnostic kind
- severity
- message
- target reference
- completion-blocking status
- source span references, when available
- `metadata["irs_ref"]`
- `metadata["authority"]`
- repairability metadata, when produced
- issue grouping metadata, when produced

The following metadata is especially important for SPL Editing:

```text
metadata["irs_ref"].construct_type
metadata["irs_ref"].construct_id
metadata["irs_ref"].slot_name
metadata["irs_ref"].source_authority
metadata["authority"]
metadata["repairability"]
metadata["issue_role"]
metadata["issue_group_id"]
```

Without `irs_ref`, SPL Editing cannot deterministically map a diagnostic back
to `ConstructIRS / SlotSpec.repair_affordances`.

## 7. Producer Boundary

The NL2SPL pipeline owns snapshot production.

The snapshot should be produced after:

1. worker-scoped IR normalization has completed;
2. Stage 10 worker assembly has completed;
3. post-normalize IRS has run;
4. executable gate has run;
5. Stage 11 rendering has produced final SPL;
6. diagnostic consolidation has produced final `compile_diagnostics`;
7. provenance aggregation has produced final traces.

This ensures the snapshot matches the same compiler authority surface shown to
users.

## 8. Consumer Boundary

SPL Editing owns snapshot consumption.

The editing backend should load the persisted snapshot and then use existing
service APIs:

```text
register_compile_result(snapshot)
list_editable_issues(run_id)
create_session(run_id, issue)
generate_suggestions(session_id)
apply_suggestion(session_id, suggestion_id)
verify_session(session_id)
```

The editing backend must not read `feedback_report.md`, `compile_report.txt`,
or `final_spl.txt` as a substitute for the snapshot.

## 9. Directory-Level Contract

A run directory intended for SPL Editing should contain:

```text
output/<run_name>/
  final_spl.txt
  snapshot.pkl
  stage*.json
  compile_report.txt             optional
  feedback_report.md             optional
```

Only `snapshot.pkl` is authoritative for SPL Editing.

The other files remain useful for inspection, debugging, or human review, but
they are not part of issue extraction or patch verification.

## 10. Snapshot Versioning

The snapshot file should carry a schema identity that allows future migration.

Design-level requirements:

- the reader can reject unknown incompatible versions;
- the persisted format can evolve without silently changing editing behavior;
- base snapshots and overlay snapshots remain distinguishable;
- stale patch detection continues to use the revision triple:

```text
(compile_run_id, snapshot_id, overlay_version)
```

The base snapshot emitted by NL2SPL always starts at overlay version `0`.

## 11. Serialization Format

The MVP can use a Python-native serialized artifact because current SPL Editing
backend and NL2SPL runtime share the same codebase and dataclass model.

Longer term, a portable JSON-compatible artifact may be desirable.

The architecture requirement is not a specific serialization mechanism. The
requirement is that loading the persisted artifact restores typed compiler
state without re-parsing human-readable reports.

## 12. Configuration Surface

Snapshot persistence should be controlled by pipeline configuration.

Recommended configuration concepts:

- whether to emit the SPL Editing snapshot;
- snapshot filename;
- whether emission is required or best-effort;
- whether to include large optional debug payloads;
- whether to include final worker / traces when available.

For production SPL Editing flows, snapshot emission should be treated as a
required output. Failure to write a valid snapshot should be visible as a
compile-run artifact error, not hidden by a fallback to report parsing.

## 13. Failure Semantics

Snapshot persistence should fail loudly when required artifacts are missing.

Examples of invalid persisted snapshots:

- missing `worker_plan`;
- missing `worker_step_plan`;
- missing `worker_flow_plan` or `worker_block_plan` for replay lanes that need
  them;
- missing `resources`;
- missing `symbol_table`;
- missing final `compile_diagnostics`;
- editable diagnostics missing `irs_ref`;
- base snapshot emitted with non-zero `overlay_version`;
- snapshot identity not tied to the compile run.

SPL Editing should reject invalid snapshots rather than attempting fallback
behavior.

## 14. Relationship to Stage JSON

Stage JSON files remain debug artifacts.

They should not become the primary loader for SPL Editing because:

- they may not contain every typed object needed by replay;
- they may serialize dataclasses as lossy dictionaries;
- they may omit runtime-only metadata;
- they are stage-local rather than a single final compiler-state contract;
- reconstructing typed IR from them would duplicate compiler assembly logic.

If JSON export is later required, it should be designed as a first-class
snapshot format, not inferred from current debug persistence.

## 15. UI Flow Enabled by Snapshot Persistence

Once the snapshot exists, the UI or CLI can operate on real compile output:

```text
NL2SPL compile run
  -> output/<run_name>/snapshot.pkl
  -> SPL Editing service loads snapshot
  -> list user-facing editable issues
  -> user selects issue
  -> backend generates allowed repair suggestions
  -> user applies one suggestion
  -> overlay snapshot produced
  -> Lane A/B replay verifies result
  -> patched SPL shown to user
```

This is the expected bridge from compiler diagnostics to AI-assisted editing.

## 16. Security and Integrity

Because the snapshot may contain structured source information and generated
compiler state, it should be treated as a trusted local artifact.

Design constraints:

- do not load arbitrary snapshot files from untrusted sources in production UI
  without a trust boundary;
- validate schema identity before use;
- validate revision identity before apply;
- keep unconfirmed AI suggestions outside renderable compiler state;
- only user-confirmed patches may produce `origin="user_confirmed_repair"`.

## 17. Acceptance Criteria

Snapshot persistence is ready when:

- every successful NL2SPL run configured for SPL Editing emits a snapshot file;
- the emitted snapshot can be loaded by the SPL Editing CLI without manual
  fixture construction;
- `list_editable_issues()` uses the loaded diagnostics and does not parse
  reports;
- the three MVP issue families can be exercised from a real run snapshot:
  - `missing_handler`;
  - `missing_output_producer`;
  - `type_or_contract_ambiguity` for worker promotion / handoff repair;
- applying a suggestion creates an overlay snapshot with incremented
  `overlay_version`;
- verification uses Lane A or Lane B replay from the loaded snapshot;
- stale revision checks still reject mismatched run, snapshot, or overlay;
- snapshot loading fails fast when required artifacts are missing.

## 18. Open Design Decisions

The following decisions should be made before implementation:

- canonical filename: `snapshot.pkl` vs `spl_editing_snapshot.pkl`;
- whether snapshot persistence is always enabled or controlled by config;
- whether failure to persist should fail the compile run or only mark editing
  unavailable;
- whether `PipelineResult` should expose the snapshot path;
- whether to persist only the base snapshot or also later editing overlays;
- whether a portable JSON snapshot format is needed before UI integration;
- whether old run directories should receive a one-time migration path or be
  treated as non-editable historical runs.
