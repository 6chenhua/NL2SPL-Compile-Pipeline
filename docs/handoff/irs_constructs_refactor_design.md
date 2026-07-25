# IRS / Constructs 分层重构设计文档 v2

**文档状态**: v2 architecture design, not yet an implementation plan
**适用仓库**: `NL2SPL-Compile-Pipeline`  
**范围**: `src/nl2spl/compiler/construct_registry.py`, `src/nl2spl/compiler/irs/`, `src/nl2spl/compiler/construct_plan/`, `src/nl2spl/compiler/diagnostic_registry.py`, `src/nl2spl/compiler/diagnostic_consolidator.py`, `src/nl2spl/compiler/irs_prompt_builder.py`, `src/nl2spl/compiler/report_renderer.py`, `src/nl2spl/compiler/spl_editing/`, `src/nl2spl/compiler/resource_contract_demand_view/`, `src/nl2spl/compiler/capability_intent/`
**目标版本**: IRS / Constructs / Repair Contracts package-architecture refactor
**核心原则**: 行为冻结、分层清晰、依赖单向、兼容迁移、repair authority 不上移、可回滚

---

## 1. 设计结论

原 v1 文档对早期 IRS package boundary 的判断仍然成立：

```text
constructs      = SPL construct domain model
diagnostics     = compiler diagnostic domain model
construct_plan  = source-demand planning
irs             = runtime checking / projection
reporting       = human-readable rendering
pipeline        = orchestration
```

但当前 IRS 已经扩展到 repair affordance、SPL Editing、worker delegation closure、API materialization、resource demand view、selected promoted diagnostics 等概念。v1 不能再作为直接实施蓝图。

v2 的核心升级是把静态 construct domain、repair metadata contract、IRS runtime、SPL Editing strategy/runtime、compiler evidence view 分开：

```text
ConstructIRS / SlotSpec
  -> 声明 construct slot satisfaction contract
  -> 可声明 repair affordance linkage metadata
  -> 不执行 repair

repair_contracts
  -> 保存 constructs 与 SPL Editing 共享的纯 metadata contract
  -> 不持有 strategy runtime / closure planner / applier / verifier

spl_editing
  -> 解释 repair_strategy_id
  -> 负责 strategy registry / closure / preview / materialization / verification

irs
  -> 执行 structured evidence 上的 slot satisfaction
  -> 投影 diagnostics
  -> 不 repair、不 render SPL、不做人类报告渲染
```

---

## 2. 当前依赖事实

当前代码仍然存在 v1 指出的包边界问题：

```text
construct_registry.py
  imports compiler.irs.frontier
  imports compiler.irs.graph
  imports compiler.irs.patch_type_meta

construct_plan/model.py
construct_plan/planner.py
  import compiler.irs.graph.ConstructEdge

report_renderer.py
  imports compiler.irs.feedback_projector

irs_prompt_builder.py
  combines construct checklist rendering, stage -> construct mapping, and stage notes
```

同时，`construct_registry.py` 已经不只是 construct static spec。它还承载：

```text
RepairAffordanceSpec
SlotActionabilityDecision
PatchTypeMeta linkage
repair_strategy_id
materialization_plan_id
selectable_ref_policy_id
intent_schema_id
stage_authority
patch_type_metadata
default actionability decisions
```

这些字段是 constructs 与 SPL Editing 的 contract metadata，不应继续放在 `irs/`，也不应被误认为 SPL Editing runtime。

---

## 3. 非目标

本次重构设计不改变以下行为：

1. 不修改 IRS slot satisfaction 语义。
2. 不新增 construct checker 规则。
3. 不改变 `PipelineResult` / `CompileResult` public schema。
4. 不移除 legacy import path，第一轮实现必须保留 shim。
5. 不重写 Stage 3.5 / Stage 4 / Stage 7 / Stage 9.5 行为。
6. 不引入新的 LLM 调用。
7. 不把 repair strategy runtime 上移到 `constructs`。
8. 不把 planner demand、source signal、diagnostic kind 机械注册成 IRS construct。

---

## 4. v2 目标 package layout

```text
src/nl2spl/compiler/

  constructs/
    __init__.py
    spec.py                  # ConstructIRS, SlotSpec, ExistencePolicy, NoDemandBehavior
    satisfaction.py          # SlotSatisfaction, ConstructSatisfactionReport, serialized frontier status fields
    graph.py                 # ConstructEdge, ConstructGraph, graph schema helpers
    registry.py              # SPLConstructRegistry
    defaults.py              # build_default_construct_registry()
    prompt_builder.py        # construct checklist rendering only
    definitions/
      __init__.py
      exception_flow.py
      output.py
      command.py
      api.py
      worker.py
      resource_contract_demand.py

  repair_contracts/
    __init__.py
    model.py                 # RepairAffordanceSpec, SlotActionabilityDecision, PatchTypeMeta
    constants.py             # shared ids and constants, if needed
    audit.py                 # local affordance/actionability shape checks only

  diagnostics/
    __init__.py
    spec.py                  # DiagnosticSpec, Severity
    registry.py              # DiagnosticRegistry
    defaults.py              # build_default_diagnostic_registry()
    kinds.py                 # diagnostic kind constants
    consolidator.py          # DiagnosticConsolidator, DiagnosticDedupKey, IRS-neutral authority inputs

  construct_plan/
    __init__.py
    model.py
    planner.py
    extractors/
      __init__.py
      exception_flow.py
      output.py
      request_input.py
      api.py
      worker.py

  irs/
    __init__.py
    config.py
    context.py
    instance.py
    checker.py
    checker_registry.py
    runner.py
    projector.py
    result_store.py
    subsystem.py
    traversal.py
    graph_snapshot.py
    checkers/
      __init__.py
      exception_flow.py
      step.py
      post_normalize.py
      worker_delegation.py
      api_declaration.py

  reporting/
    __init__.py
    report_renderer.py
    feedback_report_renderer.py
    construct_satisfaction_renderer.py

  pipeline/
    prompt_profiles/
      irs_profiles.py        # stage -> construct list and stage-specific critical rules

  resource_contract_demand_view/
    ...

  capability_intent/
    ...

  spl_editing/
    core/
    strategy/
    closure/
    materialization/
    verification/
    preview/
    drafting/
    ...
```

---

## 5. 分层职责

### 5.1 `compiler.constructs`

`constructs` 是 construct domain layer。

它负责：

1. `ConstructIRS` / `SlotSpec` 静态定义。
2. construct graph schema。
3. construct satisfaction report 数据结构。
4. construct registry shell。
5. default construct definitions。
6. construct checklist 的纯渲染。

它可以依赖：

```text
repair_contracts
```

它禁止依赖：

```text
irs
spl_editing
pipeline
reporting
construct_plan
```

`SlotSpec` 可以声明 `repair_affordances` 与 `actionability_decision`，但只能保存 contract metadata 和 linkage ids。它不能 import repair handler、patch applier、closure planner、stage slice runner、preview renderer 或 verifier。

`FrontierStatus` / `CutlineReason` 作为 serialized report fields 可以放在 `constructs.satisfaction`。frontier expansion、cutline decision、recursive traversal 等算法必须留在 `irs.traversal` 或 IRS runtime checker 内，不能上移到 `constructs`。

### 5.2 `compiler.repair_contracts`

`repair_contracts` 是 constructs 与 SPL Editing 之间的共享 contract layer。

它负责：

1. `RepairAffordanceSpec`。
2. `SlotActionabilityDecision`。
3. `PatchTypeMeta`。
4. `repair_strategy_id` linkage metadata。
5. affordance/actionability local shape validation。

它禁止负责：

1. `RepairStrategySpec` registry。
2. construct closure planning。
3. patch application。
4. stage-slice execution。
5. preview rendering。
6. repair verification lanes。
7. LLM drafting。

`repair_contracts.audit` 只能做本层 shape validation，例如字段完整性、id 格式、patch type metadata 结构一致性。跨层 linkage validation 不能放在 `repair_contracts`，因为它需要读取 SPL Editing strategy registry。

允许的跨层审计位置是：

```text
spl_editing.strategy.catalog_projection
compiler/architecture_audit/repair_linkage_audit.py
.agents/skills/audit-irs-contract
```

这些位置可以显式依赖 `repair_contracts` 与 `spl_editing.strategy`，但 `repair_contracts` 本身不能反向 import SPL Editing。

### 5.3 `compiler.spl_editing`

`spl_editing` 是 repair strategy/runtime layer。

它负责：

1. `RepairCatalogBuilder.from_construct_registry()` 从 registry 派生 repair catalog。
2. `RepairStrategySpec` 与 strategy registry。
3. closure planning。
4. directive / preview / apply。
5. materialization。
6. compiler-authority verification。
7. drafting flow。

它可以依赖：

```text
constructs
repair_contracts
diagnostics
irs public API
```

它不应被以下层反向依赖：

```text
constructs
repair_contracts
irs
diagnostics
construct_plan
```

### 5.4 `compiler.diagnostics`

`diagnostics` 是 compiler-wide diagnostic domain layer。

它负责：

1. `DiagnosticSpec`。
2. `DiagnosticRegistry`。
3. default diagnostic kinds。
4. diagnostic kind constants。
5. `DiagnosticConsolidator` / `DiagnosticDedupKey`。

`DiagnosticConsolidator` 是 compiler-wide authority merge，不应长期留在 compiler root。

迁移 `DiagnosticConsolidator` 前，必须先引入 IRS-neutral diagnostic authority input DTO/protocol。`diagnostics.consolidator` 不能直接 import `IRSResultStore`。

可选命名：

```text
DiagnosticAuthorityBundle
StageLocalDiagnosticBundle
ConstructDiagnosticAuthoritySnapshot
```

IRS runtime 可以负责把 `IRSResultStore` 转换成该 neutral input；`diagnostics` 只消费 neutral diagnostic authority snapshot。

它禁止依赖：

```text
irs
pipeline
reporting
spl_editing
```

### 5.5 `compiler.construct_plan`

`construct_plan` 是 source-demand planning layer。

它负责：

1. 从 route annotation / semantic role / evidence 识别 construct demand。
2. 记录 slot-level evidence。
3. 记录 reserved spans / dual-role spans。
4. 输出 downstream stages 与 IRS 可消费的 `ConstructPlan`。

它可以依赖：

```text
constructs
```

它不应依赖：

```text
irs.graph
irs.frontier
spl_editing
reporting
```

### 5.6 `compiler.irs`

`irs` 是 runtime checking layer。

它负责：

1. `IRSCheckContext`。
2. `ConstructInstance`。
3. `IRSChecker` protocol。
4. checker registry。
5. runner。
6. diagnostic projector。
7. result store。
8. subsystem facade。
9. runtime graph traversal / graph snapshot。
10. concrete checkers。

它禁止负责：

1. SPL construct static spec。
2. diagnostic registry。
3. human-readable report rendering。
4. SPL Editing repair execution。
5. LLM drafting。
6. stage prompt policy。

### 5.7 `compiler.reporting`

`reporting` 是 presentation layer。

它负责：

1. deterministic compile report rendering。
2. construct satisfaction feedback rendering。
3. diagnostic / assumption / trace 的人类可读文本组织。

它不负责：

1. IRS checking。
2. diagnostic projection。
3. construct slot 判断。
4. 修改 IR / SPL。

### 5.8 `resource_contract_demand_view` 与 `capability_intent`

这两个包不属于 `irs`，也不属于 `constructs`。

```text
resource_contract_demand_view = compiler evidence / demand view
capability_intent             = API/capability semantic extraction and lowering
```

它们可以为 construct extraction、API materialization、resource binding、producer analysis 提供 structured evidence，但 evidence view 本身不自动成为 IRS construct。

---

## 6. IRS construct admission ledger

新增或保留 IRS construct 前，必须证明它是 SPL grammar construct，或者是 architecture 明确批准的 compiler materialization / analysis construct。

| Candidate | IRS construct? | Owner | v2 decision |
|---|---:|---|---|
| `EXCEPTION_FLOW` | yes | SPL grammar | keep |
| `GENERAL_COMMAND` | yes | SPL grammar | keep |
| `REQUEST_INPUT` | yes | SPL grammar | keep |
| `CALL_API` | yes | SPL grammar | keep |
| `INVOKE_WORKER` | yes | SPL grammar | keep |
| `API_DECLARATION` | yes | SPL grammar | keep |
| `REQUIRED_OUTPUT` | yes | output contract construct | keep |
| `WORKER_CANDIDATE` | yes | approved compiler analysis construct | keep, document slot ownership |
| `WORKER_PROMOTION` | yes | approved compiler analysis construct | keep, document promotion boundary |
| `WORKER_HANDOFF` | yes | approved materialization / analysis construct | keep, document WorkerPlanIR lifecycle |
| `RESOURCE_CONTRACT_DEMAND` | needs explicit review | DemandView / RequiredOutput alias candidate | do not blindly keep; justify construct identity or demote to evidence / alias diagnostic |
| `delegation_intent` | no | route evidence only | never register as ConstructIRS |
| `input_contract` / `output_contract` annotation | no | route evidence only | use as evidence for worker constructs |
| diagnostic kinds | no | diagnostics only | project from real construct slots |

`RESOURCE_CONTRACT_DEMAND` is the only current registry entry that needs a dedicated admission review before implementation. If it remains an IRS construct, the implementation plan must document:

1. its stable construct identity;
2. its independent slots;
3. which stage materializes or demands it;
4. why diagnostics cannot be owned by `REQUIRED_OUTPUT`, file/variable declarations, or producer checks;
5. whether its diagnostics should be primary or alias issues.

---

## 7. Repair authority chain

Every repairable IRS slot must preserve this authority chain:

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

Allowed in `constructs` / `repair_contracts`:

```text
repair_strategy_id
affordance_id
supported_patch_types
default_patch_type
handler_id
target_resolver_id
materialization_plan_id
selectable_ref_policy_id
intent_schema_id
stage_authority
patch_type_metadata
actionability decision
```

Forbidden in `constructs` / `repair_contracts`:

```text
RepairStrategySpec registry
closure planner implementation
patch applier
stage slice runner
preview renderer
verification lane execution
LLM drafting implementation
```

`RepairStrategySpec` remains in `spl_editing.strategy`. It is not a construct static domain type and not an IRS runtime type.

---

## 8. Prompt profile split

`irs_prompt_builder.py` must be split because it currently mixes:

1. construct checklist rendering;
2. stage -> construct mapping;
3. stage-specific critical rules.

Target split:

```text
constructs/prompt_builder.py
  render ConstructIRS slot checklist only

pipeline/prompt_profiles/irs_profiles.py
  stage -> construct list
  stage-specific critical rules
  rollout / stage-local prompt policy
```

This keeps `constructs` independent from pipeline stage names.

---

## 9. Dependency rules

### 9.1 Allowed dependencies

```text
constructs      -> repair_contracts
construct_plan  -> constructs
irs             -> constructs + diagnostics
reporting       -> constructs + diagnostics + compile result models
spl_editing     -> constructs + repair_contracts + diagnostics + irs public API
pipeline        -> construct_plan + irs + reporting + constructs + spl_editing
```

### 9.2 Forbidden dependencies

```text
constructs      -> irs
constructs      -> spl_editing
constructs      -> pipeline
constructs      -> reporting
constructs      -> construct_plan

repair_contracts -> irs
repair_contracts -> spl_editing
repair_contracts -> pipeline

diagnostics     -> irs
diagnostics     -> spl_editing
diagnostics     -> pipeline
diagnostics     -> reporting

irs             -> reporting
irs             -> spl_editing
irs             -> pipeline

construct_plan  -> irs.graph
construct_plan  -> spl_editing
```

### 9.3 Compatibility shim exceptions

Migration may retain these legacy paths as shim-only modules:

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

Shim modules may re-export and emit deprecation comments, but must not host new logic.

---

## 10. Default registry split

`construct_registry.py` is now too large to remain a single implementation file. The default registry should move to grouped definitions:

```text
constructs/definitions/
  exception_flow.py
  output.py
  command.py
  api.py
  worker.py
  resource_contract_demand.py
```

`constructs/defaults.py` should assemble these definitions into `build_default_construct_registry()`.

The split must preserve:

1. construct type names;
2. slot names;
3. missing diagnostics;
4. `required_for_partial` / `required_for_complete`;
5. `renderable_without`;
6. repair affordance ids;
7. actionability decisions;
8. existing catalog entry ids.

---

## 11. Migration strategy

Implementation must be staged after this design, not mixed into the design PR.

Recommended stages:

0. Characterization and import-boundary baseline.
   - snapshot current default construct registry shape;
   - snapshot `RepairCatalog` entries;
   - snapshot `DiagnosticRegistry` enabled/reserved kinds;
   - snapshot current import violations as expected baseline;
   - add tests that document current violations and are tightened stage by stage.
1. Complete the `RESOURCE_CONTRACT_DEMAND` admission decision before splitting default definitions.
   - keep only if it has approved construct identity, independent slots, and lifecycle;
   - otherwise demote to evidence view / alias diagnostic ownership before package migration;
   - do not create `constructs/definitions/resource_contract_demand.py` until this decision is explicit.
2. Add new packages and pure re-export shims without behavioral changes.
3. Move graph/frontier/satisfaction domain types out of `irs`; keep traversal algorithms in IRS runtime.
4. Move repair metadata contract types to `repair_contracts`; keep cross-layer repair linkage audits outside `repair_contracts`.
5. Introduce an IRS-neutral diagnostic authority input DTO/protocol for `DiagnosticConsolidator`.
6. Move diagnostics registry and consolidator to `diagnostics`.
7. Split default construct definitions.
8. Split reporting and feedback rendering out of `irs`.
9. Split prompt builder into construct renderer and pipeline prompt profiles.
10. Update imports in production code.
11. Add import-boundary tests.
12. Run focused IRS / SPL Editing tests, Ruff, and demo artifact checks.

Each stage must be reversible and should keep legacy imports working until the final cleanup phase.

---

## 12. Acceptance criteria

The refactor is complete only when all criteria below are true:

1. `constructs/*` does not import `irs/*`.
2. `constructs/*` does not import `spl_editing/*`.
3. `repair_contracts/*` does not import `irs/*` or `spl_editing/*`.
4. `diagnostics/*` does not import `irs/*`.
5. `construct_plan/*` does not import `irs.graph`.
6. `reporting/*` does not import `irs.feedback_projector`.
7. `irs/*` does not contain human-readable report renderer logic.
8. `irs/*` does not execute SPL Editing repair.
9. `construct_registry.py` is shim-only.
10. `diagnostic_registry.py` is shim-only.
11. `diagnostic_consolidator.py` is shim-only.
12. `irs/graph.py`, `irs/frontier.py`, and `irs/patch_type_meta.py` are shim-only.
13. `diagnostics.consolidator` does not import `IRSResultStore` or any `irs/*` module.
14. `repair_contracts.audit` does not import SPL Editing strategy registry, catalog builder, handlers, appliers, preview, or verification modules.
15. frontier expansion and cutline decision algorithms remain in `irs.traversal` or checker runtime, not in `constructs`.
16. `RepairCatalogBuilder.from_construct_registry()` still derives identical catalog entries.
17. `RESOURCE_CONTRACT_DEMAND` has an explicit admission decision.
18. Full test behavior, diagnostic snapshots, and report snapshots have no unintended changes.

---

## 13. Final v2 position

This design keeps the v1 package-boundary insight but rejects mechanical implementation of the v1 layout.

The current architecture needs a layered refactor:

```text
constructs                static construct domain
repair_contracts          repair metadata contract
diagnostics               compiler diagnostic domain
construct_plan            source-demand planning
irs                       runtime checking / projection
reporting                 human-readable rendering
resource_contract_demand_view    compiler evidence / demand view
capability_intent         capability extraction and lowering
spl_editing               repair strategy / materialization / verification runtime
pipeline                  orchestration and prompt policy
```

The next artifact should be a new implementation plan that gates each migration step, names import-boundary checks, and performs a dedicated admission review for `RESOURCE_CONTRACT_DEMAND` before moving default definitions.
