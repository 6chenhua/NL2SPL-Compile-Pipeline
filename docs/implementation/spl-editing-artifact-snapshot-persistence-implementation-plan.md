# SPL Editing Artifact Snapshot 持久化实施计划

状态：实施计划修订版  
来源设计：[spl_editing_artifact_snapshot_persistence_design.md](../design/spl_editing_artifact_snapshot_persistence_design.md)  
目标产物：`output/<run_name>/spl_editing_snapshot.json`

## 0. 目标

本计划描述如何在 NL2SPL 侧实现 canonical JSON artifact snapshot 持久化，使真实 NL2SPL compile run 可以直接进入 SPL Editing 后端，而不再依赖手工构造的 fixture snapshot。

目标链路：

```text
NL2SPL compile run
  -> spl_editing_snapshot.json
  -> SnapshotRepository
  -> SnapshotLoader
  -> ArtifactSnapshot accessors
  -> SPL Editing service
  -> issue / suggestion / apply / verify / patched SPL
```

MVP 必须做到：

- 产出 canonical JSON snapshot，不使用 `pkl`；
- 本地 JSON 文件模拟未来 DB JSON / JSONB record；
- 不解析 `final_spl.txt`、`compile_report.txt`、`feedback_report.md` 或 `stage*.json`；
- 保留 typed artifact contract，不让业务层直接操作任意 JSON dict；
- 支持三类 SPL Editing MVP issue 的真实 run snapshot 闭环；
- 支持 Lane A / Lane B 从 persisted snapshot replay；
- 保持 pipeline 不依赖 SPL Editing patch / handler / applier。

## 1. 非目标

本阶段不做：

- 真实数据库实现；
- 历史 run directory 自动迁移；
- compact JSON patch 优化；
- 完整 JSON schema ecosystem / migration framework；
- 覆盖所有 stage debug payload 的 serializer；
- UI Diagnostics Console；
- 修改 IRS checker 执行 repair；
- 让 LLM 参与 snapshot 持久化。

## 2. 总体实施策略

先固化 contract，再接入 pipeline。

推荐顺序：

```text
S-1 Contract Freeze
S0 Neutral Snapshot Foundation
S1 Serializer MVP Coverage
S2 Snapshot Validation / Capabilities / Hashes
S3 File-backed Repository
S3.5 SnapshotBuilder / BuildInput Contract
S4 Pipeline Integration
S5 SPL Editing Loader Compatibility
S6 Overlay Full JSON Snapshot Persistence
S7 Real Run CLI Flow
S8 End-to-End Regression
S9 Documentation / Final Audit
```

不建议从 orchestrator 直接写 JSON 开始。那会导致 writer、validator、serializer、capability 语义散落，最终产物很容易变成“能写 JSON 的 artifact dump”，而不是可校验、可迁移、可被 SPL Editing 信任的 canonical snapshot。

## 3. 目标模块结构

Snapshot contract 应位于 compiler-owned 中立模块。

建议目录采用 facade + submodules，不要把所有逻辑塞进同名大文件：

```text
src/nl2spl/compiler/artifacts/snapshot/
  __init__.py
  constants.py
  capabilities.py
  schema.py
  hash_policy.py
  status.py
  errors.py

  model/
    __init__.py
    document.py
    identity.py
    payload.py
    artifact_ref.py
    integrity.py
    validation.py
    editing_history.py

  serialization/
    __init__.py
    base.py
    registry.py
    primitives.py
    canonical_input.py
    spans.py
    routes.py
    construct_plan.py
    worker_plan.py
    worker_flow_block_step.py
    resources.py
    diagnostics.py
    provenance.py
    editing_history.py

  validation/
    __init__.py
    validator.py
    identity.py
    schema_version.py
    capabilities.py
    diagnostics.py
    artifact_refs.py
    integrity.py
    payload_shape.py

  build/
    __init__.py
    input.py
    builder.py
    collectors.py
    capture_keys.py
    errors.py

  persistence/
    __init__.py
    repository.py
    file_repository.py
    index.py
    writer.py
    loader.py

  hashes.py
```

允许保留兼容 facade 文件，例如 `serializers.py`、`validator.py`、`repository.py`、`builder.py`，但它们只能 re-export 或编排子模块，不承载全部具体实现。

允许依赖：

```text
pipeline/orchestrator -> compiler.artifacts.snapshot.builder/writer
spl_editing           -> compiler.artifacts.snapshot.repository/loader/model
snapshot serializers  -> nl2spl.ir / compiler DTOs
```

禁止依赖：

```text
compiler.artifacts.snapshot -> spl_editing patch/handler/applier
compiler.artifacts.snapshot -> spl_editing storage/runtime internals
pipeline/orchestrator       -> spl_editing patch/handler/applier/storage internals
IRS checker                 -> snapshot writer / SPL Editing repair implementation
```

特别注意：snapshot module 可以被 SPL Editing 消费，但 snapshot module 不能反向依赖 SPL Editing 的运行时模型。

## 4. 全局验收规则

所有阶段必须持续满足：

- `spl_editing_snapshot.json` 是唯一 SPL Editing authority input；
- stage debug JSON 不能产生 editable issue；
- snapshot validator 推导 effective capabilities；
- writer 声明的 capability 不能被直接信任；
- `stage_artifacts` 是 editable artifact owner；
- `replay_artifacts` 必须通过 ref 或 derived copy 表达来源；
- MVP overlay snapshot 是 full JSON document；
- `PipelineResult` 暴露 snapshot path/status/error；
- 普通 pipeline 不 import SPL Editing patch/handler/applier；
- 缺少 `irs_ref` 的 editable diagnostic 不进入 repair flow；
- SnapshotLoader 在 validation failed 时不得返回可用于 SPL Editing 的 `ArtifactSnapshot`，除非调用显式 debug API。

## 5. S-1：Contract Freeze

目的：在编码前把设计开放点收敛成可 import、可测试的 contract，而不是只形成文档 checklist。

必须产出：

```text
src/nl2spl/compiler/artifacts/snapshot/constants.py
src/nl2spl/compiler/artifacts/snapshot/capabilities.py
src/nl2spl/compiler/artifacts/snapshot/schema.py
src/nl2spl/compiler/artifacts/snapshot/hash_policy.py
```

最低 contract：

```python
SNAPSHOT_ARTIFACT_KIND = "spl_editing_artifact_snapshot"
SNAPSHOT_SCHEMA_VERSION = "1.0.0"
```

```python
class SnapshotStatus(str, Enum):
    NOT_REQUESTED = "not_requested"
    AVAILABLE = "available"
    FAILED_BEST_EFFORT = "failed_best_effort"
    FAILED_REQUIRED = "failed_required"
```

```python
class SnapshotCapability(str, Enum):
    ISSUE_EXTRACTION = "issue_extraction"
    SUGGESTION_GENERATION = "suggestion_generation"
    LANE_A_REPLAY = "lane_a_replay"
    LANE_B_REPLAY = "lane_b_replay"
    FINAL_SPL_DISPLAY = "final_spl_display"
```

固定 top-level JSON section：

```text
artifact_kind
schema_version
identity
capabilities
payload
integrity
```

固定 capability derivation matrix：

| Capability | 必需字段 / 条件 |
| --- | --- |
| `issue_extraction` | `payload.diagnostics.compile_diagnostics`；editable diagnostics 具备 `metadata.irs_ref`、authority、repairability / grouping metadata |
| `suggestion_generation` | `issue_extraction` + source spans / provenance traces + target resolver 所需 stage artifacts |
| `lane_a_replay` | `payload.replay_artifacts.stage10_input` + Stage 10 dependencies + gate / IRS / renderer inputs |
| `lane_b_replay` | `payload.replay_artifacts.normalizer_input` + normalizer dependencies + Lane A replay 所需 artifacts |
| `final_spl_display` | baseline final SPL 可用；patched SPL display 仍必须经 Lane A/B replay |

固定 hash policy：

```text
payload_hash = complete canonical JSON payload hash
artifact_set_hash = semantic compiler artifact hash
snapshot_id = revision identity, not hash
```

固定 overlay MVP 策略：

```text
base snapshot = full JSON document, overlay_version = 0
overlay snapshot = full JSON document, overlay_version > 0
compact JSON patch = future optimization
```

验收：

- 后续 tests 必须 import 上述 constants/enums/matrices；
- 禁止后续阶段重新定义同名字符串常量；
- S-1 不是 checklist-only 阶段，必须产生代码级 contract。

## 6. S0：Neutral Snapshot Foundation

目的：建立 compiler-owned snapshot 基础模型，不依赖 SPL Editing 实现。

建议模型：

```text
SnapshotDocument
SnapshotIdentity
SnapshotIntegrity
SnapshotPayload
SnapshotDeclaredCapabilities
SnapshotEffectiveCapabilities
SnapshotValidationResult
SnapshotCapabilityError
SnapshotOverlayEventDTO
SnapshotAcceptedPatchDTO
SnapshotVerificationRecordDTO
```

功能点：

- 定义 snapshot identity model；
- 定义 declared capabilities 与 effective capabilities 的区别；
- 定义 validation result / capability error model；
- 定义 JSON document envelope / payload typed DTO；
- 定义中立 editing history DTO；
- 定义通用 snapshot errors。

边界要求：

- 该模块可以被 pipeline 和 SPL Editing 共同 import；
- 该模块不得 import SPL Editing patches / handlers / appliers；
- 该模块不得 import SPL Editing storage/runtime internals；
- 该模块不得调用 LLM；
- 该模块不得执行 repair。

测试：

- base snapshot 必须 `overlay_version = 0`；
- overlay identity 必须保留 `base_snapshot_id` / `parent_snapshot_id`；
- status / capability enum 只允许 S-1 定义值；
- import boundary test：snapshot foundation 不 import `spl_editing.patches`、`spl_editing.handlers`、`spl_editing.storage`。

## 7. S1：Serializer MVP Coverage

目的：建立 canonical JSON serializer/deserializer registry，覆盖 SPL Editing MVP 必需 artifact。

MVP serializer 覆盖：

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
SnapshotOverlayEventDTO
SnapshotAcceptedPatchDTO
SnapshotVerificationRecordDTO
```

注意：这里不得直接序列化 SPL Editing runtime model，例如 `RepairOverlayEvent` 或 `VerificationResult`。如果 SPL Editing 需要持久化这些信息，必须先转换成 compiler-owned neutral DTO：

```text
RepairOverlayEvent      -> SnapshotOverlayEventDTO
VerificationResult      -> SnapshotVerificationRecordDTO
Applied repair metadata -> SnapshotAcceptedPatchDTO
```

功能点：

- 每类 artifact 有 type identity；
- 每类 artifact 有 schema identity；
- 每类 artifact 支持 to-json / from-json；
- 每类 artifact 支持 schema validation；
- registry 对未知 `$type` fail-fast。

明确禁止：

- `json.dumps(asdict(...))` 直接覆盖未知对象；
- serializer fallback 到 `str(obj)`；
- silently dropping metadata；
- silently converting tuple/list 造成语义漂移；
- 任意 stage debug payload 自动进入 snapshot；
- snapshot serializer 反向 import SPL Editing runtime model。

测试：

- 每类 MVP artifact round-trip；
- `CompileDiagnostic.metadata["irs_ref"]` round-trip 不丢失；
- `origin="user_confirmed_repair"` metadata round-trip 不丢失；
- unknown `$type` 被拒绝；
- serializer output 不包含 Python object repr；
- neutral editing DTO 可从 SPL Editing runtime object 显式转换，但 serializer 本身不 import SPL Editing。

## 8. S2：Validator / Capabilities / Hashes

目的：让 snapshot 从“JSON 文件”变成“可校验 contract”。

功能点：

- 校验 top-level section 完整性；
- 校验 artifact kind；
- 校验 schema version compatibility；
- 校验 identity：
  - `compile_run_id`
  - `snapshot_id`
  - `base_snapshot_id`
  - `parent_snapshot_id`
  - `overlay_version`
- 校验 base snapshot editing history 为空；
- 校验 required artifact presence；
- 校验 editable diagnostics 必须有 `irs_ref`；
- 校验 `stage_artifacts` / `replay_artifacts` ownership/ref；
- 推导 effective capabilities；
- 计算并校验 `payload_hash`；
- 计算并校验 `artifact_set_hash`。

Capability 规则：

```text
declared capabilities = writer 声明值
effective capabilities = validator 推导值
SPL Editing 只信任 effective capabilities
```

Canonical JSON hashing 规则：

```python
json.dumps(
    value,
    sort_keys=True,
    separators=(",", ":"),
    ensure_ascii=False,
)
```

Hash normalization 规则：

- serializer 输出必须已经把 Path/datetime/Enum/tuple 转成 canonical JSON value；
- hash 层不做任意对象转换；
- missing field 与 explicit null 不等价，除非 schema 明确允许；
- `payload_hash` 基于完整 normalized payload；
- `artifact_set_hash` 基于 validation-normalized semantic artifact set，排除 `created_at`、validation errors、status 等 volatile fields；
- overlay editing history 变化不得破坏 base artifact semantic hash，除非 stage artifacts 本身发生变化。

测试：

- declared `lane_b_replay=true` 但缺 normalizer input 时，effective `lane_b_replay=false`；
- 缺 `compile_diagnostics` 时，`issue_extraction=false`；
- editable diagnostic 缺 `irs_ref` 时被拒绝或 non-editable；
- copied replay artifact hash mismatch 被拒绝；
- normalized derivative 不要求与 editable source hash 相同，但必须声明 `derived_from` / `derivation`；
- payload hash mismatch 被拒绝；
- volatile fields 不改变 `artifact_set_hash`；
- SnapshotLoader never returns `ArtifactSnapshot` if validation failed，除非显式 debug API。

## 9. S3：File-backed Snapshot Repository

目的：用本地 JSON 文件模拟未来 DB repository。

Repository interface 必须同时支持 run-dir 和 snapshot-id 语义：

```text
load_base_for_run(run_dir)
load_snapshot(snapshot_id)
save_snapshot(snapshot)
save_overlay_snapshot(snapshot)
```

功能点：

- 读取 `output/<run_name>/spl_editing_snapshot.json` 作为 base snapshot；
- 保存 base snapshot JSON；
- 保存 overlay full snapshot JSON；
- loader 必须先 validate，再暴露 typed accessors；
- repository API 不泄露文件系统细节给 SPL Editing service；
- repository 不解析 reports；
- repository 不把 stage debug JSON 当 snapshot。

未来 DB 对齐：

```text
JsonFileSnapshotRepository
  -> local spl_editing_snapshot.json / overlay JSON documents

DatabaseSnapshotRepository
  -> same JSON document from DB JSON / JSONB
```

测试：

- load valid snapshot 成功；
- missing file 返回明确错误，不 fallback 到 reports；
- invalid JSON schema 被拒绝；
- stage debug JSON 不能被 loader 当作 snapshot；
- repository 保存后再加载，identity/hash/capabilities 一致；
- `load_snapshot(snapshot_id)` 不依赖 run-dir path 语义。

## 10. S3.5：SnapshotBuilder / BuildInput Contract

目的：把“从 pipeline state 收集 artifact 并构造 SnapshotDocument”的职责从 writer/orchestrator 中剥离出来。

建议模型：

```python
@dataclass(frozen=True)
class SnapshotBuildInput:
    compile_run_id: str
    output_dir: Path
    result: PipelineResult
    intermediate: Mapping[str, Any]
    final_spl_text: str
    final_spl_path: Path | None
    config: SPLEditingSnapshotConfig
```

职责划分：

```text
SnapshotBuilder:
  SnapshotBuildInput -> SnapshotDocumentDTO

SerializerRegistry:
  typed object -> canonical JSON DTO

SnapshotWriter:
  SnapshotDocumentDTO -> canonical JSON file

SnapshotValidator:
  JSON document -> validation result + effective capabilities

SnapshotRepository/Loader:
  validated JSON -> ArtifactSnapshot accessors
```

验收：

- orchestrator 只组装 `SnapshotBuildInput`；
- writer 不直接读取 `intermediate` dict；
- builder 不落盘；
- builder 不 import SPL Editing patch/handler/applier；
- builder 对缺失 artifact 产生 capability-specific errors，而不是 silent fallback。

## 11. S4：Pipeline Integration

目的：让真实 NL2SPL compile run 产出 snapshot JSON。

功能点：

- 新增专门配置对象：
  - `enabled`
  - `mode: disabled | best_effort | required`
  - `filename`
  - `serialization_format = json`
  - `required_capabilities`
  - `include_traces`
  - `include_pre_gate_worker`
  - `include_stage_debug_payloads`
- `PipelineResult` 暴露：
  - `spl_editing_snapshot_path`
  - `spl_editing_snapshot_status`
  - `spl_editing_snapshot_error`
- Orchestrator 在最终 `PipelineResult` surface 已具备时构造 `SnapshotBuildInput`，再调用 builder/writer。

Artifact capture matrix：

| Snapshot field | Capture point | 用途 |
| --- | --- | --- |
| `normalizer_input` | Stage 9.5 调用前 | Lane B replay |
| `normalizer_output` | Stage 9.5 返回后 | debug / equivalence |
| `stage10_input` | Stage 10 调用前 | Lane A replay |
| `assembled_worker_pre_gate` | Stage 10 返回后、Gate 前 | Gate diff / replay baseline |
| `gated_worker` | Gate 后 | 用户实际 render surface |
| `post_normalize_diagnostics` | IRS 后 | diagnostic diff baseline |
| `gate_diagnostics` | Gate 后 | renderability authority baseline |
| `render_diagnostics` | Stage 11 后 | render baseline |
| `compile_diagnostics` | consolidation 后 | issue extraction authority |

Mode semantics：

- `disabled`：不写 snapshot，status = `not_requested`；
- `best_effort`：写失败不阻断 compile，status = `failed_best_effort`；
- `required`：写失败阻断 editing flow，status = `failed_required`；
- 成功写入：status = `available`。

测试：

- disabled 不写文件；
- best_effort 写失败时 compile 可成功，status 为 `failed_best_effort`；
- required 写失败时返回 blocking artifact error 或失败状态；
- 成功 run 产出 `spl_editing_snapshot.json`；
- snapshot final SPL 与 `final_spl.txt` 一致；
- snapshot diagnostics 与 `PipelineResult.compile_diagnostics` 一致；
- orchestrator 不 import SPL Editing patch/handler/applier；
- matrix 中每个 artifact 的 capture point 有单元或集成证明。

## 12. S5：SPL Editing Loader Compatibility

目的：让 SPL Editing 使用 persisted JSON snapshot，而不是 fixture snapshot。

功能点：

- SPL Editing CLI / service 通过 repository 加载 snapshot；
- Loader 暴露当前 SPL Editing 需要的 artifact accessors；
- 新增更明确的 service API：

```python
register_artifact_snapshot(snapshot: ArtifactSnapshot) -> str
```

- 保留兼容 API：

```python
register_compile_result(result: PipelineResult) -> str
```

- `register_compile_result` 仅服务内存 pipeline result，不得强行把 persisted snapshot 伪装成 `PipelineResult`；
- 不解析 report；
- 不直接读取 stage debug JSON。

关键设计：

```text
JSON document
  -> SnapshotLoader
  -> ArtifactSnapshot accessors
  -> SPLEditingService.register_artifact_snapshot(...)
```

测试：

- 从真实 `spl_editing_snapshot.json` list editable issues；
- `missing_handler` issue 可提取；
- `missing_output_producer` issue 可提取；
- `WORKER_PROMOTION type_or_contract_ambiguity` issue 可提取；
- 缺 required capability 时 service 拒绝对应操作；
- loader 不接受 `feedback_report.md` / `compile_report.txt`。

## 13. S6：Overlay Full JSON Snapshot Persistence

目的：apply 后产出可直接加载和验证的 overlay snapshot。

MVP 规则：

```text
base snapshot = full JSON document, overlay_version = 0
overlay snapshot = full JSON document, overlay_version > 0
compact JSON patch = future optimization
```

路径规则：

```text
output/<run_name>/
  spl_editing_snapshot.json              # base snapshot, overlay_version=0
  spl_editing_overlays/
    <overlay_snapshot_id>.json           # full overlay snapshots
```

Session 语义：

```text
session.base_snapshot_id
session.current_snapshot_id
```

规则：

- 初始 session 的 `current_snapshot_id = base_snapshot_id`；
- apply 成功后生成 overlay snapshot；
- apply 成功后 `current_snapshot_id` 指向 overlay snapshot；
- verify 使用 `current_snapshot_id` 加载 snapshot，不重新加载 base `spl_editing_snapshot.json`；
- base snapshot 不被修改。

overlay identity 更新：

- same `compile_run_id`；
- same `base_snapshot_id`；
- new `snapshot_id`；
- `parent_snapshot_id = previous snapshot_id`；
- `overlay_version = previous + 1`。

功能点：

- overlay snapshot 保存 `overlay_events`；
- overlay snapshot 保存 accepted patch metadata；
- overlay snapshot 保存 verification history DTO；
- overlay snapshot 可被 repository 重新加载；
- overlay snapshot 可直接用于 Lane A/B replay。

测试：

- apply 后 overlay version 递增；
- parent/base lineage 正确；
- base snapshot 不被修改；
- overlay full snapshot reload 后 verification 仍 accepted；
- stale revision check 拒绝旧 overlay；
- overlay event history 可审计；
- verify 使用 session `current_snapshot_id`，不是 base snapshot。

## 14. S7：CLI Real Snapshot Flow

目的：让 demo CLI 对真实 NL2SPL 输出运行，而不是内置 fixture。

功能点：

- `spl-edit demo --run <run_dir>` 读取 base `spl_editing_snapshot.json`；
- 创建 editing session，并记录 `current_snapshot_id`；
- 列出 user-facing editable issues；
- 选择 issue；
- 生成 suggestions；
- apply suggestion；
- 保存 overlay snapshot；
- 更新 session `current_snapshot_id`；
- verify 当前 snapshot；
- 打印 patched SPL。

必须区分：

```text
--run <run_dir> = base run directory
editing session state = current_snapshot_id / overlay lineage
```

验收场景：

```text
nl2spl compile <input> --emit-spl-editing-snapshot
spl-edit demo --run output/<run_name>
```

测试：

- CLI 不读取 `feedback_report.md`；
- CLI 不读取 `compile_report.txt`；
- CLI 在 snapshot 缺失时明确报错；
- CLI 在 required capability 缺失时明确报错；
- CLI happy path 可完成 issue -> suggestion -> apply -> verify；
- apply 后 verify 使用 overlay snapshot。

## 15. S8：三类 MVP Issue 真实 Run 回归

目的：证明 persisted JSON snapshot 不是测试 fixture，而是可支持真实编辑闭环。

必须覆盖：

```text
missing_handler
missing_output_producer
type_or_contract_ambiguity (WORKER_PROMOTION -> handoff)
```

每类都要证明：

- snapshot 由 NL2SPL pipeline 写出；
- loader 读取 snapshot；
- issue extraction 不解析 reports；
- suggestion 生成受 affordance 限制；
- apply 修改 typed artifact；
- overlay snapshot 保存成功；
- Lane A 或 Lane B replay accepted；
- patched SPL 可展示。

测试：

- integration test：`missing_handler` full persisted snapshot flow；
- integration test：`missing_output_producer` full persisted snapshot flow；
- integration test：`WORKER_PROMOTION handoff` full persisted snapshot flow；
- negative test：删除 `irs_ref` 后 issue 不可编辑；
- negative test：破坏 artifact hash 后 loader 拒绝；
- negative test：stage JSON alone 不能进入 editing flow。

## 16. S9：Final Audit / Documentation

目的：冻结交付路径与边界。

文档更新：

- snapshot persistence design 状态更新；
- SPL Editing backend implementation plan 补充 persisted snapshot handoff；
- CLI 使用说明更新；
- run directory contract 更新；
- future DB repository 边界记录。

Final audit checklist：

- 不使用 pkl；
- 不解析 reports；
- 不 dump arbitrary intermediate；
- 不让 business logic 直接写 nested JSON dict；
- 不让 pipeline import SPL Editing patch/handler/applier；
- 不信任 writer-declared capabilities；
- 不允许 diagnostic-kind-only repair fallback；
- Lane A/B 从 persisted snapshot replay；
- overlay full snapshot 可 reload；
- SnapshotLoader validation failed 时不返回可用 `ArtifactSnapshot`。

## 17. 推荐测试分布

建议新增测试目录：

```text
tests/unit/compiler/artifacts/snapshot/
  test_s_minus_1_contract_constants.py
  test_s0_model_boundaries.py
  test_s1_serializers.py
  test_s2_validator_capabilities_hashes.py
  test_s3_repository.py
  test_s3_5_snapshot_builder.py

tests/unit/pipeline/
  test_s4_snapshot_pipeline_integration.py

tests/unit/compiler/spl_editing/
  test_s5_snapshot_loader_compatibility.py
  test_s6_overlay_snapshot_persistence.py
  test_s7_real_snapshot_cli.py

tests/integration/compiler/spl_editing/
  test_s8_persisted_snapshot_full_flows.py
```

测试原则：

- 每个阶段必须有 negative tests；
- 不允许 fallback-as-success；
- 不允许 silent skip；
- typed metadata 必须 round-trip；
- hash/capability/identity 错误必须 fail-fast；
- tests 复用 S-1 contract constants/enums，不硬编码重复字符串。

## 18. Code Maintainability Guardrails

本节是编码阶段的硬约束。违反这些规则的实现，即使测试暂时通过，也不应通过审核。

### 18.1 Serializer 拆分规则

`serializers.py` 不得包含所有 artifact serializer 的具体实现。具体 serializer 必须按 artifact family 拆分到 `serialization/` 子模块。

允许：

```text
serialization/registry.py
serialization/worker_plan.py
serialization/diagnostics.py
serialization/editing_history.py
```

禁止：

```python
def to_json(obj):
    if isinstance(obj, CanonicalCompileInput):
        ...
    elif isinstance(obj, SpanIR):
        ...
    elif isinstance(obj, WorkerPlanIR):
        ...
    # hundreds of lines
```

Serializer registry 不得存在 fallback serializer。unknown type 必须 fail-fast。

### 18.2 Validator 拆分规则

`validation/validator.py` 只做 orchestration，不承载所有 validation rule。

推荐结构：

```text
validation/identity.py
validation/schema_version.py
validation/capabilities.py
validation/diagnostics.py
validation/artifact_refs.py
validation/integrity.py
validation/payload_shape.py
```

`SnapshotValidator` 的职责应类似：

```python
class SnapshotValidator:
    def validate(self, document: SnapshotDocument) -> SnapshotValidationResult:
        results = (
            validate_envelope(document),
            validate_identity(document),
            validate_artifact_refs(document),
            derive_capabilities(document),
            validate_integrity(document),
        )
        return merge_validation_results(results)
```

禁止一个 800 行 validator 同时处理 schema、hash、diagnostics、capabilities、artifact refs。

### 18.3 Model 拆分规则

`model/` 只定义结构，不写业务逻辑。Snapshot model 不得把大面积 `dict[str, Any]` 暴露给业务层。

允许 dict 的位置：

- JSON DTO 边界；
- serializer input/output；
- validation error raw context。

禁止 dict 的位置：

- SPL Editing patch applier；
- SPL Editing verifier；
- context builder；
- issue extractor；
- service apply / verify 主流程。

业务层必须通过 typed accessors 使用 snapshot：

```python
snapshot.require_worker_step_plan()
snapshot.require_stage10_input()
snapshot.require_compile_diagnostics()
snapshot.derive_with_stage_artifacts(...)
```

### 18.4 Builder 拆分规则

`SnapshotBuilder` 不得散落读取 `intermediate` magic key。所有 pipeline capture key 必须集中在 `build/capture_keys.py` 或 collector 中。

推荐：

```text
build/input.py
build/builder.py
build/collectors.py
build/capture_keys.py
build/errors.py
```

Collector 职责：

```python
class SnapshotArtifactCollector:
    def collect_normalizer_input(self, build_input: SnapshotBuildInput) -> ArtifactBundle: ...
    def collect_stage10_input(self, build_input: SnapshotBuildInput) -> ArtifactBundle: ...
    def collect_authority_outputs(self, build_input: SnapshotBuildInput) -> AuthorityBundle: ...
```

禁止：

```python
worker_plan = build_input.intermediate.get("worker_plan") or ...
# many fallback keys
# report parsing fallback
# stage debug JSON fallback
```

### 18.5 Repository 拆分规则

Repository protocol 与 file implementation 必须分离。

推荐：

```text
persistence/repository.py       # Protocol / interface
persistence/file_repository.py  # JsonFileSnapshotRepository
persistence/index.py            # snapshot_id -> path lookup
persistence/writer.py
persistence/loader.py
```

`JsonFileSnapshotRepository` 可以维护本地 index，例如 `snapshot_id -> path`。SPL Editing service 不得依赖 overlay 文件路径规则。

### 18.6 Loader / Debug API 规则

SnapshotLoader validation failed 不得返回 `ArtifactSnapshot`。

如果确实需要检查损坏 snapshot，必须使用显式 debug API，例如：

```python
load_invalid_for_debug(...)
```

该 API 不得被 SPL Editing normal flow 调用。

### 18.7 SPL Editing 消费规则

SPL Editing patch applier / verifier 不得 import snapshot JSON DTO，不得直接操作 nested JSON dict。

允许：

```text
SPL Editing -> ArtifactSnapshot accessors
SPL Editing -> SnapshotRepository interface
```

禁止：

```text
SPL Editing patch applier -> SnapshotDocument.payload["stage_artifacts"][...]
SPL Editing verifier      -> raw JSON DTO
patch applier             -> writes overlay JSON files directly
```

Overlay snapshot 保存必须通过 Repository。

### 18.8 Hash 层规则

Hash 计算只接受 normalized JSON DTO。Hash 层不得再处理 Python object，不得隐式转换 Path、datetime、Enum、tuple。

如果 serializer 未完成 canonical normalization，hash 必须 fail-fast。

## 19. 阶段完成定义

每个阶段完成必须满足：

- phase-local tests 通过；
- 现有 SPL Editing unit/integration tests 通过；
- 相关 IRS regression subset 通过；
- 无新增 pipeline -> spl_editing implementation dependency；
- 无 report parsing；
- 无 arbitrary dict mutation 进入 patch applier / verifier；
- failure mode 清晰可见。

## 20. 实施顺序建议

严格按顺序执行：

```text
S-1 -> S0 -> S1 -> S2 -> S3 -> S3.5 -> S4 -> S5 -> S6 -> S7 -> S8 -> S9
```

不要提前做：

- DB backend；
- compact JSON patch；
- historical migration；
- all-stage serializer；
- UI integration。

这些属于后续增强，不应阻塞 JSON snapshot MVP。

## 21. PM 审核重点

审核每阶段代码时重点看：

- 是否为了跑通而增加 fallback；
- 是否偷偷解析 report / debug JSON；
- 是否把 capability 当 writer 填的 bool；
- 是否让 pipeline import SPL Editing implementation；
- 是否用 `diagnostic.kind` 单字段决定修复；
- 是否用 `json.dumps(asdict(...))` 覆盖未知对象；
- 是否让 applier/verifier 操作 raw JSON dict；
- 是否把 overlay 只存 patch delta；
- 是否破坏 Gate / IRS / ProducerIndex / Renderer authority；
- 是否让 snapshot module 反向 import SPL Editing runtime model；
- 是否让 failed validation snapshot 继续进入 SPL Editing。
- 是否让 `serializers.py`、`validator.py`、`builder.py`、`model.py` 演化成巨型文件；
- 是否让 `SnapshotBuilder` 散落读取 `intermediate` magic key；
- 是否让 repository file path 规则泄漏到 SPL Editing service；
- 是否让 patch applier 自己写 overlay JSON 文件。

任何出现以上情况的实现都不应通过审核。
