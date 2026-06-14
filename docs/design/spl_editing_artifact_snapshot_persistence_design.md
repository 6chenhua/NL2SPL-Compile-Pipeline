# SPL Editing Artifact Snapshot 持久化设计

状态：设计方案

相关文档：

- `docs/design/spl_editing_architecture_design_v2.md`
- `docs/implementation/spl-editing-backend-implementation-plan.md`
- `docs/implementation/spl-editing-readiness-implementation-plan.md`

## 1. 目的

AI-assisted SPL Editing 需要在 NL2SPL 编译完成后加载一份结构化的
compiler-state artifact。Editing 后端不能从 rendered SPL、compile report、
feedback report 或 stage debug JSON 中反推可编辑状态。

本设计定义 NL2SPL 在编译结束时应产出的 canonical JSON snapshot 文档。

本地开发与 CLI 场景中的产物为：

```text
output/<run_name>/spl_editing_snapshot.json
```

这个 JSON 文件是未来后端数据库记录的本地模拟。相同 JSON document 应可
直接存入 DB JSON / JSONB / document column，而不改变 SPL Editing 的核心
读取与编辑流程。

## 2. 核心判断

MVP 不应使用 `pkl` 作为持久化格式。MVP 应直接定义 canonical JSON
snapshot document。

理由：

- JSON 可以直接进入数据库 JSON / JSONB / document column。
- JSON 可以显式表达 schema version、capabilities、identity、integrity。
- JSON 可检查、可 diff、可迁移、可测试、可索引。
- JSON 更适合 CLI、service、UI、backend 之间的边界。
- JSON 避免 pickle loader 的可信代码执行风险。

但这不意味着可以直接 dump 当前 `intermediate_results` 或 `stage*.json`。
正确方案必须是：

```text
Pipeline typed artifacts
  -> explicit Snapshot DTO / serializer
  -> canonical spl_editing_snapshot.json
  -> SnapshotRepository
  -> SnapshotLoader
  -> ArtifactSnapshot accessors
  -> SPL Editing service
```

## 3. 权威输入边界

`spl_editing_snapshot.json` 是 SPL Editing 的唯一权威结构化输入。

以下文件不是 SPL Editing 的权威输入：

- `final_spl.txt`
- `compile_report.txt`
- `feedback_report.md`
- stage-level `stage*.json`

这些文件可以继续用于人工查看和调试，但不能用于：

- issue discovery；
- IR 重建；
- repair strategy 推断；
- patch verification；
- fallback 读取。

## 4. 当前缺口

当前 run directory 中存在 final SPL、报告和 stage debug JSON，但缺少一个单一、
冻结、结构化、可校验的 compiler-state contract。

这个缺口导致当前 SPL Editing demo 仍需要 fixture snapshot。SPL Editing
backend 已经具备消费 snapshot 的能力，但 NL2SPL 还没有在真实 compile run 中
产出 canonical snapshot document。

## 5. 模块归属与依赖方向

Snapshot 是 NL2SPL compiler output contract，不是 SPL Editing 内部模型。

正确依赖方向：

```text
pipeline/orchestrator -> compiler artifact snapshot writer
spl_editing           -> compiler artifact snapshot repository/loader/model
```

禁止依赖方向：

```text
pipeline/orchestrator -> spl_editing patch/handler/applier modules
pipeline/orchestrator -> spl_editing storage internals
```

Snapshot contract 应放在 compiler artifact 的中立模块中，而不是放在
`spl_editing` 的实现内部。SPL Editing 消费 snapshot，但不拥有 compiler
output contract。

这个边界保护以下原则：

- IRS 只声明 repair affordance，不执行 repair；
- NL2SPL 只产出 compiler state；
- SPL Editing 消费 compiler state 并执行 typed repair；
- 普通 compile path 不依赖 SPL Editing patch/handler/applier。

## 6. JSON Snapshot 不等于 Stage Debug JSON

必须明确：

```text
canonical JSON snapshot != 当前 stage*.json debug artifacts
```

错误模型：

```text
intermediate_results -> json dump -> SPL Editing loader
```

正确模型：

```text
typed compiler artifacts
  -> Snapshot DTO
  -> serializer registry
  -> canonical JSON snapshot
  -> validated loader
  -> typed accessors
```

Stage JSON 是 stage-local debug artifact。它不是稳定、完整、typed、可重放的
最终 compiler-state contract。

## 7. Run Directory 契约

配置为支持 SPL Editing 的 run directory 应包含：

```text
output/<run_name>/
  final_spl.txt
  spl_editing_snapshot.json
  stage*.json
  compile_report.txt             optional
  feedback_report.md             optional
```

只有 `spl_editing_snapshot.json` 是 SPL Editing authority input。

## 8. 顶层 JSON Contract

顶层 JSON document 应包含：

```text
artifact_kind
schema_version
identity
capabilities
payload
integrity
```

概念结构：

```json
{
  "artifact_kind": "spl_editing_artifact_snapshot",
  "schema_version": "1.0.0",
  "identity": {},
  "capabilities": {},
  "payload": {},
  "integrity": {}
}
```

该文档应按未来 DB record payload 设计。本地文件只是同一 payload 的
file-backed 表示。

## 9. 数据库形态

未来后端可以把同一 JSON document 存入数据库表或 document collection。

推荐逻辑字段：

```text
snapshot_id
compile_run_id
base_snapshot_id
parent_snapshot_id
overlay_version
schema_version
artifact_kind
capabilities
payload
artifact_set_hash
created_at
```

MVP 本地文件 `spl_editing_snapshot.json` 应被视为这条 DB record 的本地模拟。

SPL Editing 应依赖 snapshot repository 边界，而不是直接依赖文件路径。
本地 repository 读取 JSON 文件；未来后端 repository 从数据库读取同一 JSON
document。

## 10. Identity Layer

Identity 字段：

```text
compile_run_id
snapshot_id
base_snapshot_id
parent_snapshot_id
overlay_version
created_at
producer
producer_version
```

NL2SPL base snapshot：

```text
overlay_version = 0
base_snapshot_id = snapshot_id
parent_snapshot_id = null
```

SPL Editing overlay snapshot：

```text
overlay_version > 0
base_snapshot_id = original base snapshot id
parent_snapshot_id = previous snapshot id
```

Stale patch detection 仍基于：

```text
(compile_run_id, snapshot_id, overlay_version)
```

Lineage 字段用于审计 overlay history，不替代 stale revision check。

## 11. Capability Model

Snapshot 应暴露 capability，而不是简单地全有或全无。

推荐 capability：

```text
issue_extraction
suggestion_generation
lane_a_replay
lane_b_replay
final_spl_display
```

不同能力需要不同 artifact：

- `issue_extraction` 需要 final diagnostics、`irs_ref` 和 catalog metadata；
- `suggestion_generation` 需要 target context、source spans、traces 和相关
  stage artifacts；
- `lane_a_replay` 需要 Stage 10 input artifacts；
- `lane_b_replay` 需要 Stage 9.5 normalizer input artifacts；
- `final_spl_display` 需要 rendered SPL 或 replay-generated SPL。

Production SPL Editing flow 通常应要求：

```text
issue_extraction = true
suggestion_generation = true
lane_a_replay = true
lane_b_replay = true
final_spl_display = true
```

Capability validation 应输出 capability-specific error。比如 snapshot 可以
支持 issue extraction，但因为缺 normalizer input artifacts 而不支持 Lane B。

### 11.1 Capability 推导规则

`capabilities` 不能由 writer 随意手写为 `true` 后直接被 SPL Editing 信任。

设计规则：

```text
SnapshotWriter may declare intended capabilities.
SnapshotValidator derives effective capabilities.
SPL Editing may only trust effective capabilities after validation.
```

也就是说，JSON 中的 `capabilities` 是 declared capabilities；真正可用于
editing flow 的是 validator 根据 artifact presence、schema validity、
diagnostic metadata、replay bundle 完整性推导出的 effective capabilities。

如果 declared capability 与 validator 推导结果不一致，validator 结果是唯一
权威。比如：

```text
declared lane_b_replay = true
but normalizer_input missing
=> effective lane_b_replay = false
=> validation error: missing_normalizer_input_bundle
```

## 12. Payload 分层

`payload` 不应是一个 arbitrary big object。建议分为：

```text
payload.source
payload.stage_artifacts
payload.replay_artifacts
payload.diagnostics
payload.provenance
payload.editing
```

每个 IR artifact 都应是 typed JSON DTO payload。JSON 是 persistence format，
不是业务层随意读写的 dict model。

## 13. Source Layer

`payload.source` 保存 source-side context：

```text
canonical_input
spans
routes
construct_plan
```

`ConstructPlan` 如果存在，应作为 source-demand context 进入 snapshot。它仍是
IRS 上游的 planning/evidence state，不因进入 snapshot 而成为 IRS construct。

## 14. Editable Stage Artifact Layer

`payload.stage_artifacts` 保存 typed patch 可能编辑的 stage-level artifacts：

```text
worker_plan
worker_flow_plan
worker_block_plan
worker_step_plan
resources
worker_scoped_resources
symbol_table
constraints
agent_profile
```

这些 JSON payload 必须带 typed DTO 语义，而不是任意 dict。

每个 artifact 至少需要表达：

```text
artifact type
artifact schema
artifact payload
```

字段命名可在实施阶段确定，但设计要求必须保留 artifact type identity 和
schema identity。

## 15. Normalization / Replay Layer

Snapshot 必须显式区分：

```text
normalizer input
normalizer output
Stage 10 input
```

Lane A / Lane B 的语义不同：

```text
Lane A:
  patched Stage 10 input artifacts
  -> Stage 10 WorkerAssembler
  -> Gate
  -> Post-normalize IRS
  -> Renderer

Lane B:
  patched normalizer input artifacts
  -> Stage 9.5 IRNormalizer
  -> Stage 10 WorkerAssembler
  -> Gate
  -> Post-normalize IRS
  -> Renderer
```

因此 `payload.replay_artifacts` 应明确表达：

```text
normalizer_input
normalizer_output
stage10_input
assembled_worker_pre_gate
gated_worker
final_spl
```

MVP 可以选择复制 artifact，也可以用 ref 减少重复。关键不是存储是否重复，
而是 replay role 必须清楚：loader/verifier 必须知道哪个 artifact set 是
editable source、哪个是 normalizer input、哪个是 Stage 10 input。

### 15.1 Artifact Ownership / Ref 规则

为避免同一 artifact 在 `stage_artifacts` 与 `replay_artifacts` 中出现不一致
副本，必须定义 ownership 规则。

设计规则：

```text
payload.stage_artifacts owns editable artifacts.
payload.replay_artifacts either references stage_artifacts or stores derived copies.
Copied replay artifacts must record source_ref / derived_from / artifact_hash.
Validator must verify copied artifacts unless they are explicit normalized derivatives.
```

含义：

- `stage_artifacts` 是 patch apply 的 canonical editable owner。
- `replay_artifacts` 可以引用 `stage_artifacts`。
- 如果 `replay_artifacts` 复制 artifact，必须记录来源与 hash。
- 如果 replay artifact 是 normalizer output，必须标记为 derived artifact，而不是
  与 editable source 混淆。

概念形态：

```json
{
  "artifact_ref": "payload.stage_artifacts.worker_step_plan",
  "artifact_hash": "sha256:..."
}
```

或：

```json
{
  "derived_from": "payload.stage_artifacts.worker_step_plan",
  "derivation": "stage9_5_normalized",
  "artifact_hash": "sha256:..."
}
```

## 16. Worker Authority Layer

Snapshot 必须区分 pre-gate 与 post-gate worker：

```text
assembled_worker_pre_gate
gated_worker
gate_diagnostics
post_normalize_diagnostics
render_diagnostics
final_spl
compile_diagnostics
traces
```

`final_worker` 作为持久化字段名过于模糊。SPL Editing verification 需要知道
worker 是 pre-gate 还是 post-gate，因为 Gate 是过滤不可渲染 step 的权威。

Post-gate worker 和 rendered SPL 必须代表用户实际看到的 compiler surface。

## 17. Diagnostic Contract

Snapshot 中的 `compile_diagnostics` 必须是 final consolidated diagnostics，
不是 raw stage-local debug list。

`payload.diagnostics` 建议包含：

```text
compile_diagnostics
post_normalize_diagnostics
gate_diagnostics
render_diagnostics
diagnostic_groups
```

每个 editable IRS-derived diagnostic 必须保留：

```text
diagnostic_id
kind
severity
message
target_ref
blocks_completion
source_span_ids
metadata["irs_ref"]
metadata["authority"]
metadata["repairability"]
metadata["issue_role"]
metadata["issue_group_id"]
```

`metadata["irs_ref"]` 是 deterministic repair discovery 的必要字段。没有它，
SPL Editing 无法从 diagnostic 反查：

```text
ConstructIRS / SlotSpec / repair_affordances
```

缺少 `irs_ref` 的 editable diagnostic 应被拒绝或标记为 non-editable。禁止
退回到 diagnostic-kind-only 的修复策略。

## 18. Provenance Layer

`payload.provenance` 应保存：

```text
traces
assumptions
```

这支持 source-span lookup、issue explanation、repair context building，以及
未来 UI diagnostics modal 的细节展示。

## 19. Editing Layer

Base snapshot 应包含空的 editing history：

```text
overlay_events = []
accepted_patches = []
verification_history = []
```

Overlay snapshot 可以填充这些历史。这与 SPL Editing 架构一致：

```text
frozen editable artifact snapshot
  -> repair overlay event log
  -> patched artifact snapshot
  -> verification result
```

### 19.1 Overlay 持久化规则

MVP 应明确采用 full JSON overlay snapshot，而不是只保存 compact patch delta。

设计规则：

```text
Base snapshot: full JSON document, overlay_version = 0.
Overlay snapshot: full JSON document, overlay_version > 0.
overlay_events are retained for audit.
Compact JSON patch is a future optimization.
```

这样 apply 后的 snapshot 可以直接用于 CLI、UI、DB 读取和 Lane A/B replay，
不需要每次验证时先重放一串 patch delta。`parent_snapshot_id` 指向上一份 full
snapshot，`base_snapshot_id` 指向原始 base snapshot。

## 20. JSON 不等于放弃 Typed Model

JSON 是持久化格式，不是业务对象模型。

正确边界：

```text
JSON document
  -> SnapshotLoader
  -> ArtifactSnapshot DTO / accessors
  -> PatchApplier / VerificationRunner
```

Patch applier 和 verifier 应通过 typed accessors 与 derived snapshot 操作工作。
它们不应直接修改嵌套 JSON dict。

Loader 可以恢复 IR dataclass，也可以提供 DTO-backed typed accessors。只要
业务逻辑保持 typed、schema-validated，这两种方式都可以。

## 21. Serializer Registry 要求

NL2SPL IR 对象可能包含 enum、tuple、nested dataclass、datetime、Path 以及其他
非 JSON-native 值，因此 snapshot writer 不能是 raw `json.dumps(asdict(...))`。

设计要求引入显式 serializer/deserializer registry。

每类 artifact 需要定义：

```text
type identity
schema identity
to-json semantics
from-json semantics
validation semantics
```

这样才能支持 schema migration、局部校验和精确错误报告，而不是让 SPL Editing
依赖临时 dict shape。

### 21.1 MVP Serializer Coverage

MVP serializer 不应覆盖所有 debug artifact。第一批覆盖范围应限制在三类 MVP
issue 和 Lane A/B replay 必需 artifact。

MVP 覆盖对象：

```text
CanonicalCompileInput
SpanIR
FieldRouteIR
ConstructPlan
WorkerPlanIR
WorkerFlowPlanIR
WorkerBlockPlanIR
WorkerStepPlanIR
ResourceRegistryIR
WorkerScopedResourceIR
SymbolTable
ConstraintIR
AgentProfileIR
WorkerIR
CompileDiagnostic
TraceRecord
RepairOverlayEvent
VerificationResult
```

其他 stage debug payload 不进入 canonical snapshot，除非某个 capability 明确
要求它，并且为它定义 typed serializer / validator。

## 22. Producer Timing

NL2SPL 应在以下步骤完成后生成 base snapshot：

1. worker-scoped IR normalization 完成；
2. Stage 10 worker assembly 完成；
3. post-normalize IRS 完成；
4. executable gate 完成；
5. Stage 11 rendering 产出 final SPL；
6. diagnostic consolidation 产出 final `compile_diagnostics`；
7. provenance aggregation 产出 final traces。

Snapshot 必须代表与最终 `PipelineResult` 相同的 compiler authority surface。

一致性约束：

```text
snapshot.final_spl == final_spl.txt content
snapshot.compile_diagnostics == PipelineResult.compile_diagnostics payload
snapshot.traces == PipelineResult.traces payload
snapshot.compile_run_id == current run identity
```

建议保留 `artifact_set_hash` 绑定 artifact set 完整性；`snapshot_id` 继续作为
revision identity。

### 22.1 Hash Policy

Snapshot 需要区分存储完整性 hash 与 compiler-state 语义完整性 hash。

设计规则：

```text
snapshot_id = revision identity
payload_hash = complete canonical JSON payload hash
artifact_set_hash = semantic compiler artifact hash
```

`payload_hash` 用于检测文件 / DB payload 是否被篡改或损坏。它覆盖完整
canonical JSON payload。

`artifact_set_hash` 用于绑定影响 issue extraction / replay / verification 的
核心 compiler artifacts。它应排除 volatile fields，例如 `created_at`、
validation status、validation errors，以及不改变 compiler-state 语义的运行时
展示字段。

`snapshot_id` 不应被 hash 替代。它继续作为 revision identity，与
`compile_run_id`、`overlay_version` 共同参与 stale revision check。

## 23. Consumer Boundary

SPL Editing 应通过 repository 加载 snapshot，然后使用已有 service API：

```text
register_compile_result(snapshot)
list_editable_issues(run_id)
create_session(run_id, issue)
generate_suggestions(session_id)
apply_suggestion(session_id, suggestion_id)
verify_session(session_id)
```

Editing backend 不得在 snapshot validation 失败后 fallback 到 report parsing。

没有有效 snapshot 的历史 run 默认不可编辑。如果未来需要迁移历史 run，应设计
显式 migration 工具，而不是隐式解析报告或 stage debug JSON。

## 24. Configuration Surface

Snapshot persistence 应由专门配置对象控制，而不是多个散落 bool。

设计概念：

```text
enabled
mode: disabled | best_effort | required
filename
include_traces
include_pre_gate_worker
include_stage_debug_payloads
serialization_format = json
required_capabilities
```

推荐行为：

- 普通 compile run 可以使用 `disabled` 或 `best_effort`；
- UI / CLI SPL Editing flow 应使用 `required`；
- production editing flow 不应 silent fallback 到 non-editable output。

## 25. Failure Semantics

Failure semantics 取决于 mode 与 required capabilities。

`required` mode：

```text
invalid snapshot -> compile run fails or returns a blocking artifact error
no fallback to report parsing
```

`best_effort` mode：

```text
invalid snapshot -> compile run can still succeed
snapshot status = failed
snapshot error is exposed
SPL Editing is unavailable for that run
```

Validation 应产生 capability-specific errors，例如：

```text
missing_normalizer_input_bundle -> lane_b_replay unavailable
missing_compile_diagnostics -> issue_extraction unavailable
missing_traces -> suggestion_generation degraded or unavailable
```

Invalid snapshot 示例：

- 缺少 worker plan；
- 缺少 worker step plan；
- replay lane 所需的 worker flow/block plan 缺失；
- 缺少 resources；
- 缺少 symbol table；
- 缺少 final compile diagnostics；
- editable diagnostics 缺少 `irs_ref`；
- base snapshot 的 `overlay_version` 非 0；
- schema version 不兼容；
- snapshot identity 与 compile run 不一致；
- integrity hash 不匹配；
- required capability 不满足。

## 26. PipelineResult Surface

`PipelineResult` 应暴露 snapshot availability，但不必直接嵌入大型 payload。

设计级字段：

```text
spl_editing_snapshot_path
spl_editing_snapshot_status
spl_editing_snapshot_error
```

UI 和 CLI 需要这些字段判断某个 run 是否可编辑。完整 snapshot document 可以
继续作为持久化 artifact 或 DB record 存在，而不是每次都返回到内存结果对象。

`spl_editing_snapshot_status` 应是枚举值：

```text
not_requested
available
failed_best_effort
failed_required
```

这样普通 compile run 与 UI-triggered editing run 可以区分失败语义：

- `failed_best_effort`：compile 可以成功，但该 run 不可编辑；
- `failed_required`：snapshot 是 required artifact，失败应阻断 editing flow。

## 27. Security and Integrity

安全与完整性约束：

- 拒绝 invalid JSON schema；
- 拒绝未知 `artifact_kind`；
- 拒绝不兼容 `schema_version`；
- 拒绝缺少 required capabilities 的 snapshot；
- 拒绝 identity 与 compile run / snapshot / overlay 预期不一致的 snapshot；
- 拒绝 integrity hash 不匹配的 snapshot；
- snapshot validation 失败后禁止 fallback 到 report parsing。

如果未来 UI 支持上传 snapshot document，loader 仍必须在允许任何 editing
operation 前完成 schema、identity、capability 和 integrity 校验。

## 28. Relationship to Stage JSON

Stage JSON 仍是 debug artifacts。

它们不应成为 SPL Editing primary loader，因为：

- 可能不包含 replay 所需的全部 typed object；
- 可能把 dataclass 序列化成 lossy dictionary；
- 可能丢失 runtime-only metadata；
- 它们是 stage-local，而不是单一最终 compiler-state contract；
- 从它们重建 typed IR 会复制一套 shadow compiler assembly logic。

如果需要 JSON export，必须是本设计定义的 first-class canonical snapshot
document，而不是基于当前 debug persistence 的 inference layer。

## 29. UI Flow

Snapshot 存在后，CLI / UI 可直接操作真实 compile output：

```text
NL2SPL compile run
  -> spl_editing_snapshot.json
  -> SnapshotRepository loads JSON document
  -> SnapshotLoader exposes ArtifactSnapshot accessors
  -> list user-facing editable issues
  -> user selects issue
  -> backend generates allowed repair suggestions
  -> user applies one suggestion
  -> overlay snapshot produced
  -> Lane A/B replay verifies result
  -> patched SPL shown to user
```

这就是 compiler diagnostics 到 AI-assisted SPL editing 的结构化桥接。

## 30. Acceptance Criteria

Snapshot persistence readiness 达成条件：

- 每个配置为支持 SPL Editing 的成功 NL2SPL run 都产出
  `spl_editing_snapshot.json`；
- 该 JSON document 可被 SPL Editing 加载，不需要手工 fixture construction；
- 同一 JSON document shape 可存入 DB JSON / JSONB / document column；
- `list_editable_issues()` 使用 loaded diagnostics，不解析 reports；
- 三类 MVP issue family 可从真实 run snapshot 走通：
  - `missing_handler`；
  - `missing_output_producer`；
  - worker promotion / handoff repair 的 `type_or_contract_ambiguity`；
- apply suggestion 后生成 overlay snapshot，并递增 `overlay_version`；
- verification 从 loaded snapshot 执行 Lane A 或 Lane B replay；
- stale revision check 拒绝 run、snapshot 或 overlay mismatch；
- snapshot loading 在 required artifacts 或 required capabilities 缺失时
  fail fast；
- snapshot final SPL 与 `final_spl.txt` 一致；
- snapshot diagnostics 与 `PipelineResult.compile_diagnostics` 一致；
- 缺少 `irs_ref` 的 editable diagnostic 被拒绝或标记为 non-editable；
- base snapshot 包含 `overlay_version = 0` 和空 editing history；
- loader 拒绝不兼容 schema version；
- loader 拒绝 integrity hash mismatch；
- 从 persisted snapshot 执行 unchanged Lane A replay 与 baseline replay 一致；
- 从 persisted snapshot 执行 unchanged Lane B replay 与 baseline replay 一致；
- stage JSON alone 不能产生 editable issue extraction；
- 普通 pipeline snapshot emission 不 import SPL Editing patch、handler、
  applier modules。
- effective capabilities 必须由 SnapshotValidator 推导，不能直接信任 writer
  声明值；
- replay artifact 副本必须带 `source_ref` / `derived_from` / `artifact_hash`，
  并通过 validator 一致性校验；
- overlay snapshot 在 MVP 中必须是 full JSON document，且保留
  `overlay_events` 用于审计；
- `payload_hash` 与 `artifact_set_hash` 必须分别覆盖存储完整性与 compiler-state
  语义完整性；
- `PipelineResult.spl_editing_snapshot_status` 必须使用定义好的 status enum；
- serializer MVP coverage 不得隐式扩展到任意 stage debug payload。

## 31. Open Decisions

实施前仍需明确：

- compiler-owned snapshot contract 的中立模块路径；
- schema version 字符串与 compatibility policy；
- `artifact_set_hash` 的具体 canonical artifact 输入集合；
- 普通 CLI run 默认使用 `disabled` 还是 `best_effort`；
- UI-triggered compile run 是否总是使用 `required`；
- file-backed local snapshot 与 DB-backed production snapshot 的 repository
  边界；
- compact JSON patch 是否作为 full overlay snapshot 之外的未来优化；
- 历史 run directory 是否需要显式 migration tool，还是默认作为 non-editable
  historical run。

## 32. 实施准备结论

当前设计已经可以进入 implementation planning，但不建议直接开始编码。

在进入编码前，应先把以下 contract 固化为实施计划：

```text
1. SnapshotValidator 推导 effective capabilities。
2. stage_artifacts / replay_artifacts 的 ownership 与 ref 规则。
3. MVP overlay snapshot = full JSON document。
4. payload_hash / artifact_set_hash 的 canonical 计算范围。
5. PipelineResult snapshot status enum。
6. MVP serializer coverage。
```

这些收敛后，`spl_editing_snapshot.json` 才能成为稳定、可校验、可迁移的
NL2SPL 与 SPL Editing handoff contract。
