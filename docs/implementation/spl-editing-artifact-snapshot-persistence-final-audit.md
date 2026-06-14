# SPL Editing Artifact Snapshot Persistence - Final Audit

Status: delivered.

This final audit covers S-1 through S9 of the canonical JSON snapshot
persistence work.

## Delivered Scope

- `spl_editing_snapshot.json` is emitted by the NL2SPL pipeline when snapshot
  persistence is enabled.
- The local JSON file is the MVP simulation of the future database JSON or
  JSONB snapshot record.
- `SnapshotLoader` and `JsonFileSnapshotRepository` load validated snapshot
  documents; stage debug JSON and reports are not accepted as authority input.
- `payload_hash` and `artifact_set_hash` are validated on load.
- SPL Editing converts a loaded `SnapshotDocument` into `ArtifactSnapshot`
  accessors before issue extraction, suggestion generation, patch application,
  and verification.
- Applied repairs persist full overlay JSON documents under
  `spl_editing_overlays/`.
- Verification records are appended to the persisted overlay document.
- The demo CLI reads `spl_editing_snapshot.json` directly from the run
  directory.

## End-to-End Coverage

The persisted snapshot path is covered for all MVP issue families:

- `missing_handler`: pipeline emits JSON snapshot, service loads it, suggestion
  is applied, Lane A replay verifies accepted.
- `missing_output_producer`: pipeline emits JSON snapshot, service loads it,
  producer patch is applied, ProducerIndex-backed verification accepts.
- `type_or_contract_ambiguity`: pipeline emits JSON snapshot, service derives
  child worker context, `CreateWorkerHandoffContract` is applied, Lane B replay
  verifies accepted.

Negative coverage:

- Stage debug JSON alone is rejected.
- Report files are not parsed as snapshot input.
- Tampered snapshot JSON is rejected by hash validation.
- Non-editable diagnostics without `irs_ref` do not become editable issues.

## Validation

Command:

```powershell
$env:PYTEST_DEBUG_TEMPROOT=(Resolve-Path .pytest_tmp).Path
.\.venv\Scripts\pytest.exe tests/unit/compiler/artifacts/snapshot `
  tests/unit/compiler/spl_editing/test_s5_s6_persisted_snapshot_flow.py `
  tests/unit/compiler/spl_editing/test_c2_demo_cli.py `
  tests/unit/compiler/spl_editing/test_b8_editing_service.py `
  tests/integration/compiler/spl_editing -q
```

Result:

```text
513 passed
```

Expanded final regression including the IRS compiler subset:

```powershell
$env:PYTEST_DEBUG_TEMPROOT=(Resolve-Path .pytest_tmp).Path
.\.venv\Scripts\pytest.exe tests/unit/compiler/artifacts/snapshot `
  tests/unit/compiler/spl_editing `
  tests/integration/compiler/spl_editing `
  tests/unit/compiler/irs -q
```

Result:

```text
1283 passed
```

Targeted lint for modified files:

```text
All checks passed
```

## Known Boundaries

- The MVP repository is file-backed. Production storage should implement the
  same repository boundary over a database JSON or JSONB record.
- Historical run directories without `spl_editing_snapshot.json` remain
  non-editable unless explicitly migrated.
- Compact overlay patch persistence is not part of this MVP; overlays are full
  JSON documents.
