# IRS / Constructs 分层重构实施计划 v2

**文档状态**: Implementation plan for staged execution
**设计输入**: `docs/handoff/irs_constructs_refactor_design.md`
**适用仓库**: `NL2SPL-Compile-Pipeline`
**实施目标**: 在行为冻结前提下，把 IRS / Constructs / Repair Contracts / Diagnostics / Reporting 分层落到代码结构中。
**核心约束**: Phase 0 baseline 先行；`RESOURCE_CONTRACT_DEMAND` admission review 前置；legacy import path 必须 shim；每阶段独立验证、可回滚。

---

## 1. 执行总览

本计划把 v2 设计拆成 12 个阶段。Phase 0 和 Phase 1 是实施 gate，不通过不得移动 default registry。

| Phase | 名称 | 允许行为变化 | 主要风险 |
|---|---|---:|---|
| 0 | Characterization and import-boundary baseline | 否 | baseline 不完整导致后续无法判定漂移 |
| 1 | `RESOURCE_CONTRACT_DEMAND` admission decision | 可能，仅限显式决策 | 过早固化 planner/evidence record 为 construct |
| 2 | Add package skeletons and compatibility shims | 否 | shim identity / circular import |
| 3 | Move repair metadata contracts | 否 | `repair_contracts` 反向 import SPL Editing |
| 4 | Move construct graph / satisfaction / spec / registry shell | 否 | type identity duplication |
| 5 | Update production imports and boundary tests | 否 | 漏改跨层 import |
| 6 | Decouple and move diagnostics | 否 | `DiagnosticConsolidator` 继续依赖 `IRSResultStore` |
| 7 | Split reporting from IRS | 否 | report text drift |
| 8 | Split prompt profile policy | 否 | stage prompt text drift |
| 9 | Split default construct definitions | 否，除 Phase 1 决策要求 | registry / RepairCatalog entry drift |
| 10 | Tighten import-boundary tests and CI gates | 否 | 测试过宽或误报 |
| 11 | Final verification, docs, and shim exit plan | 否 | 未清理新代码 legacy imports |

执行原则：

1. 每个 Phase 单独提交，提交说明必须列出验证命令。
2. 除 Phase 1 的显式 admission decision 外，其余 Phase 不改变 compiler 行为。
3. 任何 snapshot 变化必须在同一 Phase 的 review notes 中解释。
4. 所有 legacy modules 第一轮只能 re-export，不能承载新逻辑。
5. 先建立 baseline 和 admission decision，再拆 package。

---

## 2. Authority Chain

实施期间必须保持以下权威链不变：

```text
ConstructIRS slot + missing diagnostic
-> RepairAffordanceSpec.repair_strategy_id
-> RepairStrategySpec
-> ConstructClosurePlan
-> repair-mode stage-slice chain
-> preview and user confirmation
-> confirmed materialization
-> compiler-authority verification
```

边界规则：

```text
constructs          declares construct and slot contracts
repair_contracts    declares local metadata contract only
irs                 checks slot satisfaction and projects diagnostics
spl_editing         resolves strategy, closure, preview, apply, verification
diagnostics         owns compiler-wide diagnostic registry and consolidation
reporting           renders human-readable output
pipeline            owns stage prompt profiles and orchestration
```

禁止事项：

1. `constructs` import `irs` or `spl_editing`。
2. `repair_contracts` import `irs` or `spl_editing`。
3. `diagnostics` import `irs`。
4. `irs` import `reporting` or `spl_editing`。
5. `construct_plan` import `irs.graph`。
6. `reporting` import `irs.feedback_projector`。

---

## 3. Current Implementation Facts

当前代码事实会驱动 Phase 0 baseline：

```text
construct_registry.py
  imports irs.frontier
  imports irs.graph
  imports irs.patch_type_meta
  defines RepairAffordanceSpec
  defines SlotActionabilityDecision
  defines SlotSpec / ConstructIRS / SPLConstructRegistry
  registers RESOURCE_CONTRACT_DEMAND

construct_plan/model.py
construct_plan/planner.py
  import irs.graph.ConstructEdge

diagnostic_consolidator.py
  imports irs.result_store.IRSResultStore

report_renderer.py
  imports irs.feedback_projector

irs_prompt_builder.py
  owns _STAGE_CONSTRUCT_MAP and _STAGE_NOTES

spl_editing/core/catalog.py
  derives RepairCatalog entries from SPLConstructRegistry
```

这些事实不是实现目标；它们是需要在阶段性迁移中消除或隔离的 baseline。

---

## 4. Phase 0 — Characterization and Import-Boundary Baseline

### 4.1 Goal

在移动任何类型前冻结当前行为、registry shape、repair catalog identity、diagnostic kind set、prompt/report output 和 import violations。后续每个阶段只允许 intentional diff。

### 4.2 Files to Add

建议新增：

```text
tests/fixtures/irs_constructs_refactor/
  construct_registry_shape.json
  repair_catalog_entries.json
  diagnostic_registry_kinds.json
  import_boundary_baseline.json
  stage_prompt_snapshots.json
  report_renderer_snapshot.txt

tests/unit/compiler/architecture/test_irs_constructs_refactor_baseline.py
tests/unit/compiler/architecture/test_import_boundaries.py
```

Optional helper:

```text
scripts/dev/snapshot_irs_constructs_refactor.py
```

or, if this repo keeps test-only tooling beside tests:

```text
tests/unit/compiler/architecture/snapshot_irs_constructs_refactor.py
```

Do not hand-write snapshot JSON when it can be generated from the current registry/catalog APIs.

如果 repo 已有 snapshot fixture 约定，优先沿用现有目录。

### 4.3 Snapshot Content

`construct_registry_shape.json` 每个 construct 至少记录：

```json
{
  "construct_type": "EXCEPTION_FLOW",
  "existence_policy": "...",
  "no_demand_behavior": "...",
  "slots": [
    {
      "slot_name": "handler_action",
      "required_for_partial": false,
      "required_for_complete": true,
      "renderable_without": true,
      "missing_diagnostic": "missing_handler",
      "repair_affordance_ids": ["exception_flow.add_handler_step"],
      "repair_strategy_ids": ["exception_flow.complete_handler_action.v1"],
      "actionability": "editable"
    }
  ]
}
```

`repair_catalog_entries.json` 每个 entry 至少记录：

```json
{
  "entry_id": "EXCEPTION_FLOW.handler_action.missing_handler.exception_flow.add_handler_step",
  "affordance_id": "exception_flow.add_handler_step",
  "construct_type": "EXCEPTION_FLOW",
  "slot_name": "handler_action",
  "diagnostic_kind": "missing_handler",
  "repair_strategy_id": "exception_flow.complete_handler_action.v1",
  "supported_patch_types": ["AddExceptionHandlerStep"],
  "default_patch_type": "AddExceptionHandlerStep"
}
```

`diagnostic_registry_kinds.json` records:

```json
{
  "enabled": ["missing_handler"],
  "reserved": ["..."],
  "all": ["..."]
}
```

`import_boundary_baseline.json` records current known violations by rule. This is a temporary characterization artifact; Phase 10 must tighten it.

### 4.4 Suggested Baseline Commands

Use repo-local Python:

```powershell
.venv\Scripts\python.exe -m pytest tests\unit\compiler\irs tests\unit\compiler\spl_editing tests\unit\test_construct_registry.py tests\unit\test_diagnostic_registry.py tests\unit\test_report_renderer.py
.venv\Scripts\python.exe -m pytest tests\integration\compiler\spl_editing
```

Ruff:

```powershell
.venv\Scripts\python.exe -m ruff check src tests
```

Import baseline discovery:

```powershell
rg -n "from nl2spl\.compiler\.irs\.(graph|frontier|patch_type_meta)|from nl2spl\.compiler\.construct_registry|from nl2spl\.compiler\.diagnostic_registry|from nl2spl\.compiler\.diagnostic_consolidator|from nl2spl\.compiler\.report_renderer|from nl2spl\.compiler\.irs_prompt_builder" src tests
```

### 4.5 Acceptance

Phase 0 passes only if:

1. baseline fixtures exist and are reviewed;
2. focused tests pass or existing failures are documented as baseline failures;
3. import-boundary baseline records current violations explicitly;
4. `RepairCatalog` entry IDs are snapshotted;
5. `DiagnosticRegistry` enabled/reserved/all kind lists are snapshotted;
6. prompt and report snapshots exist for at least Stage 4, Stage 7, and one repair/report scenario.

---

## 5. Phase 1 — `RESOURCE_CONTRACT_DEMAND` Admission Decision

### 5.1 Goal

Decide before package migration whether `RESOURCE_CONTRACT_DEMAND` remains an IRS construct or is demoted to `resource_contract_demand_view` evidence / alias diagnostic ownership.

Do not create:

```text
constructs/definitions/resource_contract_demand.py
```

until this decision is explicit.

### 5.2 Inputs to Review

Review at minimum:

```text
src/nl2spl/compiler/construct_registry.py
src/nl2spl/compiler/irs/checkers/post_normalize.py
src/nl2spl/compiler/resource_contract_demand_view/
src/nl2spl/compiler/spl_editing/issues/grouper.py
src/nl2spl/compiler/producer_index.py
tests/unit/test_post_normalize_resource_contract_irs.py
```

### 5.3 Admission Checklist

The decision document must answer:

1. What stable construct identity does `RESOURCE_CONTRACT_DEMAND` represent?
2. Which stage materializes or demands it?
3. What independent slots does it own?
4. Which structured evidence satisfies each slot?
5. Which diagnostics would be owned by `REQUIRED_OUTPUT`, file/variable declarations, or producer checks if this construct did not exist?
6. Are its diagnostics primary, alias, or context?
7. Does it need a `RepairCatalog` entry, or should it remain non-editable / alias-only?

### 5.4 Output

Add:

```text
docs/handoff/resource_contract_demand_admission_decision.md
```

Required structure:

```text
# RESOURCE_CONTRACT_DEMAND Admission Decision

Decision: keep as IRS construct | demote to evidence / alias
Owner:
Lifecycle:
Slots:
Diagnostic ownership:
Repairability:
Implementation consequences:
Required tests:
```

### 5.5 Branching Consequences

If kept:

1. It may later move into `constructs/definitions/resource_contract_demand.py`.
2. Its slots and diagnostics must remain in the Phase 0 registry snapshot.
3. Issue grouping must keep primary/alias semantics explicit.

If demoted:

1. Remove it from default construct registry in the Phase that applies the decision.
2. Route its evidence through `resource_contract_demand_view`.
3. Move diagnostics to `REQUIRED_OUTPUT` / producer / file-variable owners.
4. Update RepairCatalog snapshot expectations accordingly.
5. Run the IRS contract audit for affected constructs.

### 5.6 Acceptance

Phase 1 passes only if:

1. admission decision doc exists;
2. the decision explicitly addresses every checklist question;
3. implementation consequences are listed before code movement;
4. Phase 0 snapshots are updated only if the explicit decision changes behavior;
5. reviewer signs off that default registry split may proceed.

---

## 6. Phase 2 — Package Skeletons and Compatibility Shims

### 6.1 Goal

Create package structure and shim entry points without moving behavior.

### 6.2 Files to Add

```text
src/nl2spl/compiler/constructs/__init__.py
src/nl2spl/compiler/constructs/definitions/__init__.py
src/nl2spl/compiler/repair_contracts/__init__.py
src/nl2spl/compiler/diagnostics/__init__.py
src/nl2spl/compiler/reporting/__init__.py
src/nl2spl/pipeline/prompt_profiles/__init__.py
src/nl2spl/compiler/architecture_audit/__init__.py
```

No class definitions move in this phase. This phase proves that new packages can exist without import side effects.

### 6.3 Shim Rule

Existing modules remain authoritative in Phase 2:

```text
compiler/construct_registry.py
compiler/diagnostic_registry.py
compiler/diagnostic_consolidator.py
compiler/irs/graph.py
compiler/irs/frontier.py
compiler/irs/patch_type_meta.py
compiler/irs_prompt_builder.py
compiler/report_renderer.py
```

### 6.4 Acceptance

1. New packages import cleanly.
2. Phase 0 snapshots unchanged.
3. No production import is updated yet except import smoke tests.
4. Focused tests and Ruff pass.

---

## 7. Phase 3 — Move Repair Metadata Contracts

### 7.1 Goal

Move pure repair metadata contract types out of `construct_registry.py` / `irs.patch_type_meta` into `repair_contracts`, without importing SPL Editing runtime.

### 7.2 Target Files

```text
src/nl2spl/compiler/repair_contracts/model.py
src/nl2spl/compiler/repair_contracts/constants.py
src/nl2spl/compiler/repair_contracts/audit.py
```

Move:

```text
RepairAffordanceSpec
SlotActionabilityDecision
PatchTypeMeta
```

`repair_contracts.audit` may only validate local shape.

### 7.3 Shims

```python
# compiler/irs/patch_type_meta.py
from nl2spl.compiler.repair_contracts.model import PatchTypeMeta

__all__ = ["PatchTypeMeta"]
```

`construct_registry.py` may temporarily re-export `RepairAffordanceSpec` and `SlotActionabilityDecision` for compatibility.

### 7.4 Forbidden Imports

This phase must fail review if any of these appear:

```text
repair_contracts -> spl_editing
repair_contracts -> irs
repair_contracts -> pipeline
```

Cross-layer strategy linkage audit belongs in:

```text
src/nl2spl/compiler/architecture_audit/repair_linkage_audit.py
```

or existing external audit tooling, not in `repair_contracts`.

### 7.5 Acceptance

1. `PatchTypeMeta` identity is shared through old and new paths.
2. `RepairCatalogBuilder.from_construct_registry()` entries match Phase 0 snapshot.
3. No `repair_contracts/*` import `irs` or `spl_editing`.
4. `RepairStrategySpec` remains in `spl_editing.strategy` and is not imported by `repair_contracts`.
5. SPL Editing tests using old `construct_registry` imports still pass.

---

## 8. Phase 4 — Move Construct Domain Types

### 8.1 Goal

Move construct domain schema out of IRS/root modules while preserving type identity and legacy imports.

### 8.2 Target Files

```text
src/nl2spl/compiler/constructs/spec.py
src/nl2spl/compiler/constructs/satisfaction.py
src/nl2spl/compiler/constructs/graph.py
src/nl2spl/compiler/constructs/registry.py
src/nl2spl/compiler/constructs/defaults.py
```

Move:

```text
SlotSpec
ConstructIRS
ExistencePolicy
NoDemandBehavior
SlotSatisfaction
ConstructSatisfactionReport
ConstructCompleteness
FrontierStatus
CutlineReason
ConstructEdge
ConstructEdgeType
ConstructGraph
SPLConstructRegistry
```

### 8.3 Boundary Detail

`FrontierStatus` and `CutlineReason` can live in `constructs.satisfaction` only as serialized report fields.

Do not move:

```text
frontier expansion
cutline decision algorithm
recursive traversal
runtime graph snapshot construction
```

Those stay in IRS runtime.

### 8.4 Temporary Default Registry Rule

Phase 4 may expose the default registry through the new `constructs/defaults.py` path, but it must not split construct-family definitions.

Allowed in this phase:

```text
constructs/defaults.py delegates to the existing monolithic implementation
```

or:

```text
the monolithic default builder moves as-is into constructs/defaults.py
```

Forbidden in this phase:

```text
constructs/definitions/*.py with construct-family registration logic
```

Phase 9 is the first phase allowed to split default construct definitions into family modules. This prevents Phase 4 from bypassing the Phase 1 `RESOURCE_CONTRACT_DEMAND` admission gate and keeps new-path and legacy-path registry behavior identical during type migration.

### 8.5 Shims

```python
# compiler/construct_registry.py
from nl2spl.compiler.constructs import *

# compiler/irs/graph.py
from nl2spl.compiler.constructs.graph import *

# compiler/irs/frontier.py
from nl2spl.compiler.constructs.satisfaction import CutlineReason, FrontierStatus
```

Shims must not duplicate dataclass definitions.

### 8.6 Acceptance

1. New imports work:

```python
from nl2spl.compiler.constructs import ConstructIRS, SPLConstructRegistry
from nl2spl.compiler.constructs.graph import ConstructEdge
from nl2spl.compiler.constructs.satisfaction import ConstructSatisfactionReport
```

2. Old imports return the same objects.
3. `constructs/*` does not import `irs`, `spl_editing`, `pipeline`, `reporting`, or `construct_plan`.
4. Phase 0 registry and catalog snapshots unchanged.
5. Focused IRS and SPL Editing tests pass.

---

## 9. Phase 5 — Update Production Imports and Boundary Tests

### 9.1 Goal

Move production imports to new paths while keeping compatibility tests for old paths.

### 9.2 Primary Rewrites

```text
nl2spl.compiler.construct_registry
  -> nl2spl.compiler.constructs

nl2spl.compiler.irs.graph
  -> nl2spl.compiler.constructs.graph

nl2spl.compiler.irs.frontier
  -> nl2spl.compiler.constructs.satisfaction

nl2spl.compiler.irs.patch_type_meta
  -> nl2spl.compiler.repair_contracts
```

### 9.3 High-Priority Files

```text
src/nl2spl/compiler/construct_plan/model.py
src/nl2spl/compiler/construct_plan/planner.py
src/nl2spl/compiler/artifacts/snapshot/serialization/serializers_plan.py
src/nl2spl/compiler/irs/instance.py
src/nl2spl/compiler/irs/result_store.py
src/nl2spl/compiler/irs/subsystem.py
src/nl2spl/compiler/irs/runner.py
src/nl2spl/compiler/irs/checker.py
src/nl2spl/compiler/irs/checkers/*.py
src/nl2spl/compiler/spl_editing/core/catalog.py
src/nl2spl/compiler/spl_editing/core/service.py
src/nl2spl/compiler/spl_editing/closure/validators.py
src/nl2spl/pipeline/orchestrator.py
src/nl2spl/pipeline/stages/stage4_flow_assembler/irs_checker.py
src/nl2spl/pipeline/stages/stage7_step_extractor/irs_checker.py
```

### 9.4 Boundary Tests

Add grep or AST-based tests for:

```text
constructs/* does not import irs/*
constructs/* does not import spl_editing/*
repair_contracts/* does not import irs/* or spl_editing/*
construct_plan/* does not import irs.graph
```

Tests should initially allow legacy shim files by explicit allowlist.

### 9.5 Acceptance

1. Production code uses new paths except legacy shim modules.
2. Compatibility tests still prove old paths work.
3. Phase 0 snapshots unchanged.
4. Boundary tests pass.

---

## 10. Phase 6 — Decouple and Move Diagnostics

### 10.1 Goal

Move diagnostic registry and consolidator to `compiler.diagnostics` without allowing `diagnostics` to import IRS.

### 10.2 Target Files

```text
src/nl2spl/compiler/diagnostics/spec.py
src/nl2spl/compiler/diagnostics/registry.py
src/nl2spl/compiler/diagnostics/defaults.py
src/nl2spl/compiler/diagnostics/kinds.py
src/nl2spl/compiler/diagnostics/consolidator.py
src/nl2spl/compiler/diagnostics/authority.py
```

Move:

```text
DiagnosticSpec
DiagnosticRegistry
DiagnosticDedupKey
DiagnosticConsolidationInput
DiagnosticConsolidationResult
DiagnosticConsolidator
```

### 10.3 IRS-Neutral Authority DTO

Before moving `DiagnosticConsolidator`, introduce:

```python
@dataclass(frozen=True)
class StageLocalDiagnosticBundle:
    stage_name: str
    diagnostics: tuple[CompileDiagnostic, ...] = ()
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class DiagnosticAuthorityBundle:
    stage_local_results: tuple[StageLocalDiagnosticBundle, ...] = ()
```

`DiagnosticConsolidationInput` should use `DiagnosticAuthorityBundle` or equivalent instead of `IRSResultStore`.

Allowed direction:

```text
diagnostics.authority defines IRS-neutral DTOs only
irs.diagnostic_authority_adapter converts IRSResultStore -> DiagnosticAuthorityBundle
diagnostics.consolidator -> diagnostics.authority only
```

Forbidden:

```text
diagnostics.authority -> irs.result_store
diagnostics.consolidator -> irs.result_store
```

The adapter that knows about `IRSResultStore` must be IRS-owned, for example:

```text
src/nl2spl/compiler/irs/diagnostic_authority_adapter.py
```

This keeps the dependency direction as:

```text
irs -> diagnostics.authority
diagnostics.consolidator -> diagnostics.authority
diagnostics -> not irs
```

### 10.4 Shims

```python
# compiler/diagnostic_registry.py
from nl2spl.compiler.diagnostics import *

# compiler/diagnostic_consolidator.py
from nl2spl.compiler.diagnostics.consolidator import *
```

### 10.5 Update Imports

Update:

```text
irs/projector.py
irs/audit.py
pipeline/orchestrator.py
spl_editing/verification/lanes.py
tests/*
```

Legacy compatibility tests may keep old imports.

### 10.6 Acceptance

1. `DiagnosticRegistry.list_kinds(enabled_only=False)` snapshot unchanged.
2. `DiagnosticRegistry.list_kinds(enabled_only=True)` snapshot unchanged.
3. Consolidation output snapshot unchanged.
4. `diagnostics/*` does not import `irs/*`.
5. `diagnostics.consolidator` does not import `IRSResultStore`.
6. Old imports still work through shims.

---

## 11. Phase 7 — Split Reporting from IRS

### 11.1 Goal

Move human-readable report rendering out of IRS.

### 11.2 Target Files

```text
src/nl2spl/compiler/reporting/report_renderer.py
src/nl2spl/compiler/reporting/construct_satisfaction_renderer.py
src/nl2spl/compiler/reporting/feedback_report_renderer.py
```

Move:

```text
compiler/report_renderer.py -> compiler/reporting/report_renderer.py
irs/feedback_projector.py -> compiler/reporting/construct_satisfaction_renderer.py
```

### 11.3 Shims

```python
# compiler/report_renderer.py
from nl2spl.compiler.reporting.report_renderer import *

# compiler/irs/feedback_projector.py
from nl2spl.compiler.reporting.construct_satisfaction_renderer import *
```

The `irs.feedback_projector` shim is temporary; new code must not import it.

### 11.4 Acceptance

1. Report output snapshot unchanged.
2. `report_renderer.py` no longer imports `irs.feedback_projector`.
3. `irs/*` contains no real human-readable report renderer logic.
4. `reporting/*` does not import `irs.feedback_projector`.
5. Old imports still work.

---

## 12. Phase 8 — Split Prompt Profiles

### 12.1 Goal

Separate pure construct checklist rendering from pipeline stage prompt policy.

### 12.2 Target Files

```text
src/nl2spl/compiler/constructs/prompt_builder.py
src/nl2spl/pipeline/prompt_profiles/irs_profiles.py
```

Move:

```text
ConstructPromptBuilder / checklist rendering -> constructs/prompt_builder.py
_STAGE_CONSTRUCT_MAP / _STAGE_NOTES -> pipeline/prompt_profiles/irs_profiles.py
```

Keep:

```text
compiler/irs_prompt_builder.py
```

as compatibility wrapper.

### 12.3 Acceptance

1. `irs_checklist_for_stage()` output snapshots unchanged.
2. `constructs/prompt_builder.py` does not import `pipeline`.
3. `pipeline/prompt_profiles/irs_profiles.py` may import construct names or construct registry APIs.
4. Stage 4, Stage 7, and Stage 3.5 prompt snapshots unchanged.

---

## 13. Phase 9 — Split Default Construct Definitions

### 13.1 Goal

Break the monolithic default registry into construct-family definition modules after Phase 1 has resolved `RESOURCE_CONTRACT_DEMAND`.

### 13.2 Target Layout

```text
src/nl2spl/compiler/constructs/definitions/
  exception_flow.py
  output.py
  command.py
  api.py
  worker.py
```

Only add:

```text
resource_contract_demand.py
```

if Phase 1 explicitly keeps it as an IRS construct.

### 13.3 Definition Module Contract

Each module should expose a narrow registration function:

```python
def register(registry: SPLConstructRegistry) -> None:
    ...
```

`constructs/defaults.py` becomes the only default assembly point:

```python
def build_default_construct_registry() -> SPLConstructRegistry:
    registry = SPLConstructRegistry()
    exception_flow.register(registry)
    output.register(registry)
    command.register(registry)
    api.register(registry)
    worker.register(registry)
    return registry
```

### 13.4 Preservation Requirements

The split must preserve:

1. construct type names;
2. slot names;
3. slot order;
4. missing diagnostics;
5. partial/complete requirements;
6. renderability flags;
7. related graph edge declarations;
8. repair affordance ids;
9. actionability decisions;
10. `RepairCatalog` entry IDs and insertion order.

### 13.5 Acceptance

1. `construct_registry_shape.json` unchanged except Phase 1-approved changes.
2. `repair_catalog_entries.json` unchanged except Phase 1-approved changes.
3. Default registry import path old and new both work.
4. IRS contract audit passes for affected constructs.

Recommended audit commands if constructs are moved but not semantically changed:

```powershell
.venv\Scripts\python.exe .agents\skills\audit-irs-contract\scripts\audit_irs_contract.py --construct EXCEPTION_FLOW --scope all --format json
.venv\Scripts\python.exe .agents\skills\audit-irs-contract\scripts\audit_irs_contract.py --construct WORKER_PROMOTION --scope all --format json
```

If `RESOURCE_CONTRACT_DEMAND` remains, audit it too.

---

## 14. Phase 10 — Tighten Import-Boundary Tests and CI Gates

### 14.1 Goal

Convert Phase 0 baseline violations into enforceable boundary tests.

### 14.2 Final Boundary Rules

These must pass without allowlist except shim files:

```text
constructs/* does not import irs/*
constructs/* does not import spl_editing/*
repair_contracts/* does not import irs/* or spl_editing/*
diagnostics/* does not import irs/*
construct_plan/* does not import irs.graph
reporting/* does not import irs.feedback_projector
irs/* does not import spl_editing/*
irs/* does not import reporting/*
```

### 14.3 Shim Allowlist

Allowed legacy shim modules:

```text
src/nl2spl/compiler/construct_registry.py
src/nl2spl/compiler/diagnostic_registry.py
src/nl2spl/compiler/diagnostic_consolidator.py
src/nl2spl/compiler/irs/graph.py
src/nl2spl/compiler/irs/frontier.py
src/nl2spl/compiler/irs/patch_type_meta.py
src/nl2spl/compiler/irs/feedback_projector.py
src/nl2spl/compiler/irs_prompt_builder.py
src/nl2spl/compiler/report_renderer.py
```

### 14.4 Acceptance

1. Boundary test fails on a deliberate forbidden import.
2. Boundary test passes with current code.
3. CI or local validation command includes boundary test.
4. Phase 0 import violations baseline is obsolete or updated to zero for final rules.

---

## 15. Phase 11 — Final Verification and Shim Exit Plan

### 15.1 Goal

Prove the refactor is behavior-preserving and document remaining compatibility shims.

### 15.2 Verification Bundle

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests\unit\compiler\irs
.venv\Scripts\python.exe -m pytest tests\unit\compiler\spl_editing
.venv\Scripts\python.exe -m pytest tests\unit\test_construct_registry.py tests\unit\test_diagnostic_registry.py tests\unit\test_diagnostic_consolidator.py tests\unit\test_report_renderer.py tests\unit\test_irs_prompt_builder.py
.venv\Scripts\python.exe -m pytest tests\integration\compiler\spl_editing
.venv\Scripts\python.exe -m ruff check src tests
git diff --check
```

If the repo has demo E2E artifacts for SPL Editing / IRS, rerun the canonical demo and compare snapshots.

### 15.3 Documentation Updates

Update:

```text
docs/handoff/irs_constructs_refactor_design.md
docs/handoff/irs_constructs_refactor_implementation_plan.md
README or package architecture docs if present
```

Add shim exit notes:

```text
Legacy path
New path
Reason for keeping
Suggested removal milestone
Compatibility tests covering it
```

### 15.4 Final Acceptance

1. All v2 design acceptance criteria are satisfied.
2. Phase 0 behavior snapshots match, except approved Phase 1 changes.
3. `RepairCatalog` entry identity is stable.
4. Diagnostics consolidation output is stable.
5. Report and prompt snapshots are stable.
6. No new code imports legacy paths except compatibility shims/tests.
7. Shim exit plan is documented.

---

## 16. Rollback Strategy

Each phase must be revertable alone:

| Phase | Rollback |
|---|---|
| 0 | Remove characterization tests/fixtures only if no later phase depends on them |
| 1 | Revert admission decision and any behavior change together |
| 2 | Remove empty packages/shims; no behavior change expected |
| 3 | Point `construct_registry.py` back to local repair metadata definitions |
| 4 | Point `construct_registry.py`, `irs/graph.py`, `irs/frontier.py` back to previous implementations |
| 5 | Restore old imports; shims should make rollback low risk |
| 6 | Restore root diagnostic files and old `IRSResultStore` consolidator input |
| 7 | Restore root report renderer and IRS feedback projector |
| 8 | Restore `irs_prompt_builder.py` as single implementation |
| 9 | Restore monolithic default registry implementation |
| 10 | Revert only boundary tests if they are too strict, not production code |
| 11 | Documentation-only rollback |

Never combine rollback of behavior changes with package movement unless the same Phase introduced both.

---

## 17. Review Checklist

Before marking implementation complete, reviewer should verify:

1. Phase 0 baseline exists and was used.
2. `RESOURCE_CONTRACT_DEMAND` decision happened before default definition split.
3. `DiagnosticConsolidator` no longer imports `IRSResultStore`.
4. `repair_contracts.audit` is local-only.
5. `FrontierStatus` / `CutlineReason` are fields only; traversal remains IRS runtime.
6. `constructs` has no IRS/SPL Editing imports.
7. `RepairCatalogBuilder.from_construct_registry()` still derives identical entries.
8. report and prompt snapshots did not drift unexpectedly.
9. legacy imports are shim-only.
10. all verification commands are recorded in the final phase notes.

---

## 18. Implementation Stop Conditions

Stop and return to design review if any of these occur:

1. `RESOURCE_CONTRACT_DEMAND` cannot be justified but removing it changes unowned diagnostics.
2. `DiagnosticConsolidator` cannot be decoupled without changing authority order.
3. `repair_contracts` needs to import SPL Editing to validate strategy linkage.
4. moving graph/frontier types requires moving traversal logic into `constructs`.
5. prompt/report snapshots drift for non-mechanical reasons.
6. `RepairCatalog` entry IDs change outside an approved Phase 1 decision.

These are architecture failures, not implementation details.
