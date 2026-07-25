# IRS Constructs Refactor Shim Exit Plan

This note records the temporary compatibility shims introduced by the IRS
constructs refactor.  The shims keep old import paths working while production
code moves to the v2 package boundaries.

## Exit rules

Remove a shim only after all three conditions are true:

1. Production imports use the new owner package.
2. Tests, scripts, and demos no longer import the old path.
3. `tests/unit/compiler/architecture/test_import_boundaries.py` passes with the
   shim removed from its compatibility allowlist.

Do not remove multiple shims in the same review unless the removals are purely
mechanical and share one import-boundary test update.

## Compatibility shims

| Old path | New owner | Reason retained | Removal gate |
| --- | --- | --- | --- |
| `nl2spl.compiler.construct_registry` | `nl2spl.compiler.constructs` | Public legacy import path for `ConstructIRS`, `SlotSpec`, `SPLConstructRegistry`, and repair metadata. | No imports outside the shim and historical tests. |
| `nl2spl.compiler.irs.graph` | `nl2spl.compiler.constructs.graph` | Historical construct graph import path. | No production or test imports of `irs.graph`. |
| `nl2spl.compiler.irs.frontier` | `nl2spl.compiler.constructs.satisfaction` | Historical serialized satisfaction field import path. | No production or test imports of `irs.frontier`. |
| `nl2spl.compiler.irs.patch_type_meta` | `nl2spl.compiler.repair_contracts.model` | Historical repair metadata import path. | No production or test imports of `irs.patch_type_meta`. |
| `nl2spl.compiler.diagnostic_registry` | `nl2spl.compiler.diagnostics` | Public legacy diagnostic registry import path. | No imports outside the shim and historical tests. |
| `nl2spl.compiler.diagnostic_consolidator` | `nl2spl.compiler.diagnostics.consolidator` | Public legacy consolidator import path. | No imports outside the shim and historical tests. |
| `nl2spl.compiler.report_renderer` | `nl2spl.compiler.reporting.report_renderer` | Public legacy report renderer import path. | No imports outside the shim and historical tests. |
| `nl2spl.compiler.irs.feedback_projector` | `nl2spl.compiler.reporting.construct_satisfaction_renderer` (primary owner); `nl2spl.compiler.reporting.feedback_report_renderer` (compat facade) | Historical construct satisfaction feedback import path. | No imports outside the shim and historical tests. |
| `nl2spl.compiler.irs.audit` | `nl2spl.compiler.architecture_audit.irs_contract_audit` | Existing audit CLI/tests import this path; implementation is now outside IRS because it intentionally checks cross-layer repair closure. | Audit scripts and tests import `architecture_audit` directly. |

## Diagnostic DTO compatibility

`DiagnosticConsolidationInput.irs_store` remains as a read-only compatibility
alias for legacy monkeypatch hooks.  It returns the IRS-neutral
`DiagnosticAuthorityBundle`; it must not accept or expose `IRSResultStore`.

Removal gate:

1. Replace tests that branch on `data.irs_store` with
   `data.stage_local_authority`.
2. Confirm `nl2spl.compiler.diagnostics.consolidator` still has no imports from
   `nl2spl.compiler.irs`.
3. Remove the alias and rerun the full architecture boundary suite.

## Verification

Required checks for shim removal:

```powershell
.venv\Scripts\python.exe -m pytest tests\unit\compiler\architecture -q
.venv\Scripts\python.exe -m pytest tests\unit\test_construct_registry.py tests\unit\test_diagnostic_registry.py tests\unit\test_report_renderer.py -q
git diff --check
```
