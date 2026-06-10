# Decision Gate: Stage 2 Requiredness Contract

**状态：已确认，待 PM 批准后进入 Phase B0。**

---

## 1. 背景

Phase A 已证明 `DemandViewBuilder` 可以稳定地从 `RouteAnnotation` 结构化字段中投影
source-demanded resource contract demands。Phase B 之后会影响 Stage 3.5、Stage 6、
Post-normalize IRS 的共同输入契约。如果当前不固定 Stage 2 contract，后续字段含义反复、
metadata 偷渡语义、consumer 各自解释 requiredness 的风险很高。

本 Decision Gate 遵循实施计划第 5 节的要求，在进入 Phase B0（Schema Impact Audit）之前
锁定以下 5 项决策。

---

## 2. 决策记录

### 2.1 `direction` canonical 来源

**决策**：`semantic_role=input_contract/output_contract` 是 direction 的 canonical 来源。

在最终的 confirmed resource contract annotation contract 中：

* **`semantic_role` 必须为 `input_contract` 或 `output_contract`** — 这是 canonical direction source。
  没有 `semantic_role=input_contract/output_contract` 的 annotation 不应被视为
  confirmed resource contract annotation。
* `slot_target=input/output` 是**一致性证据** — 当同时存在时，必须与 `semantic_role` 一致。
  冲突时 DemandView builder 触发 `conflicting_direction` diagnostic，不生成 demand。
* `metadata.direction=input/output` 是**一致性证据** — 同上。该字段不独立承载 direction 语义。

下游 consumer（Stage 3.5、Stage 6、IRS）只从 DemandView demand 的 `.direction`
字段读取 direction，不应重新从 annotation 信号重新裁决。

| 信号 | 角色 |
|------|------|
| `semantic_role=input_contract` / `output_contract` | **canonical source** — **必须存在**；DemandView builder 据此决定 direction |
| `slot_target=input` / `output` | 一致性证据 — 与 semantic_role 冲突时触发 `conflicting_direction` diagnostic；**不应独立承载 direction** |
| `metadata.direction=input` / `output` | 一致性证据 — 同上；**不应独立承载 direction** |

**Phase A transitional compatibility**：当前 DemandView builder 的
`_direction_candidates()` 实现收集三个来源的全部 candidate，仅当 `len(candidates)==1`
时接受 direction。这意味着在 `semantic_role` 缺失但 `slot_target` 或
`metadata.direction` 单独存在的场景下，builder 仍会生成 demand。

这是 Phase A 为了不依赖 Stage 2 的完整 `semantic_role` 产出而保留的过渡行为。
**在 Phase B2 完成之前，这属于兼容路径，不属于最终 confirmed contract。**

Phase B0/B2 需要决定并执行收紧策略：
1. B2 完成后，Stage 2 必须输出 `semantic_role=input_contract/output_contract`。
2. B2 完成后，`slot_target` 和 `metadata.direction` 仅作为一致性校验信号，
   不再独立产生 demand。仅靠 `slot_target` 或 `metadata.direction` 承载
   direction 的 annotation 被视为 annotation contract 不完整，
   应触发 missing_direction diagnostic 且不生成 demand。
3. 收紧后，Phase A 中 `test_direction_from_slot_target` 和
   `test_direction_from_metadata` 两个测试应被标记为 transitional 或移除。
   文件内已加注释标注为 `# TRANSITIONAL (Phase A compat)`。

### 2.2 `requiredness` 存放位置

**决策**：当前阶段 `requiredness` 存放在 `RouteAnnotation.metadata["requiredness"]`，
取值为 `"required" | "optional" | "unspecified"`。

是否提升为 `RouteAnnotation` 一等字段（如 `RouteAnnotation.requiredness: str | None`）
推迟到 Phase B0 schema impact audit 中决策，不在 Phase A 临时扩大 IR schema。

Phase A 的 DemandView builder 已从 `metadata["requiredness"]` 读取，无需修改。
Phase A 的测试 fixtures 使用 `_output_contract_annotation(requiredness="required")` 模式，
已与当前存放位置一致。

**现有代码现状**：当前生产 Stage 2 尚未填充 `metadata["requiredness"]`。
Phase B2（Stage 2 Structural Annotation Contract）负责实现填充逻辑。
在 Phase B2 完成前，真实结构化 NL 路径中的 `requiredness` 将保持 `unspecified`，
这是预期行为而非 defect。

### 2.3 `requiredness=unspecified` 语义

**决策**：

| 状态 | DemandView 行为 | Consumer 约束 |
|------|----------------|---------------|
| `requiredness=required` | `required=True`，demand 正常生成 | 正常处理 |
| `requiredness=optional` | `required=False`，demand 正常生成 | 正常处理 |
| `requiredness=unspecified` | `required=None`，demand 保留，发出 `missing_requiredness` diagnostic | **禁止**静默投影为 `required=True`；**禁止**渲染为 REQUIRED |

`requiredness=unspecified` 的含义是：Stage 2 的结构化信息不足以确定该 demand 是
required 还是 optional。这是**信息不完整**，不是默认 required，也不是默认 optional。

Post-normalize IRS 对 `unspecified` output demand 应产生 warning 而非 error
（在 Phase B5 中实现）。

Renderer 对 `required=None` 不应输出 REQUIRED 关键字
（在 Phase B1/B4 中实现）。

### 2.4 `executable` contract

**决策**：resource contract annotation 必须 `executable=False`。

已在 Phase A DemandView builder 中实现（Stage 1b validation）。
违反时发出 `resource_contract_invalid_annotation_contract` diagnostic，
该 annotation 被排除，不生成 demand。

Stage 2 产出 resource contract annotation 时必须设置 `executable=False`。
这是 Stage 2 的产出契约，不是 DemandView 的猜测。

### 2.5 禁止 fallback

**决策**：Stage 2 没有给出 confirmed resource contract annotation 时，
DemandView 不生成任何 demand。

以下行为**不在**当前设计范围内：
- 根据 section title（如 "Inputs for each run" / "Required Outputs"）推断 demand
- 根据 evidence text 关键词推断 direction 或 requiredness
- 根据 packet type 推断 resource contract 语义

Phase C 的 `ResourceContractAnnotationCoverageValidator` 可以检测 annotation 缺失
并产生 coverage diagnostic，但**不生成 demand**。

旧的 `ResourceContractPlanner` 中的 header fallback 逻辑（Rule 2: section title match）
不迁移到 DemandView。这是与旧 planner 的核心设计差异。

---

## 3. Confirmed Annotation Shape

以下为 Phase B 各阶段共享的 resource contract `RouteAnnotation` shape。

```python
RouteAnnotation(
    span_id="<resolved_span_id>",          # 绑定到 resolved span
    field="resources",                     # 或 "behavior"
    semantic_role="input_contract"         # canonical direction source
        | "output_contract",
    route_family="resource_contract",      # 标识资源合约族
    construct_target="RESOURCE_CONTRACT",   # 目标 SPL construct
    slot_target="input" | "output",        # 一致性证据，必须与 semantic_role 一致
    executable=False,                      # 硬性约束，违反即 invalid
    source_section_id="<section_id>",       # adapter provenance
    source_packet_id="<packet_id>",         # adapter provenance
    source_hint_ids=[...],                  # adapter provenance
    metadata={
        "requiredness": "required"         # 三值语义
            | "optional"
            | "unspecified",
    }
)
```

**字段约束**：
- `semantic_role` **必须**为 `input_contract` 或 `output_contract`（canonical direction source；同时也是 DemandView builder 选入 contract annotations 的首要条件）
- `executable` **必须**为 `False`（DemandView builder Stage 1b 校验；违反即 `invalid_annotation_contract`）
- `slot_target` 应当与 `semantic_role` 的 direction 一致（`input_contract` ↔ `input`，`output_contract` ↔ `output`）；不一致且无 `semantic_role` 时按 Phase A transitional 兼容路径处理（见 2.1 过渡说明）
- `metadata["requiredness"]` 为可选字段；缺失时 DemandView 解释为 `unspecified` 并发出 `missing_requiredness` diagnostic

---

## 4. 对下游的影响

### Phase B0（Schema Impact Audit）

审计范围必须额外覆盖：
- `RouteAnnotation.metadata["requiredness"]` 的读写点
- Stage 6 context builder 如何将三值 requiredness 传给 LLM prompt
- Post-normalize IRS producer check 如何处理 `unspecified` output

### Phase B2（Stage 2 Structural Annotation Contract）

必须实现：
- 结构化 NL 路径在 Stage 2 后产生携带 `metadata["requiredness"]` 的 confirmed annotation
- Structural Adapter 的 hard facts（`required_input` / `required_output`）映射为 `requiredness=required`
- Explicit optional structural schema（如 adapter-confirmed optional packet）或 Stage 2
  confirmed annotation metadata 中写入 `requiredness=optional`
- 无法从 structured schema 确认 → `requiredness=unspecified` 或完全不填补 `metadata["requiredness"]`

**注意**：DemandView 不读取 section title，不对 "Optional" 标题做任何语义解析。
任何 optional section 语义必须已由 Structural Adapter / Stage 2 转成 confirmed
annotation metadata 后才能由 DemandView 消费。如果 adapter 或 Stage 2 未产出此
metadata，DemandView 将解释为 `requiredness=unspecified`。

### Phase B1/B4（Renderer + Stage 6）

- Renderer 对 `required=None` 不能输出 REQUIRED
- Stage 6 context builder 必须传递三值 requiredness，不能只传 bool
- Stage 6 不重新判断 requiredness（pass-through only）

---

## 5. Phase A Fixture 兼容性确认

Phase A 的测试 fixtures 已与上述 confirmed annotation shape 一致：

| 字段 | Fixture 值 | 符合决策 |
|------|-----------|---------|
| `semantic_role` | `"input_contract"` / `"output_contract"` | ✅ 2.1 |
| `slot_target` | `"input"` / `"output"`（与 role 一致） | ✅ 2.1 |
| `executable` | `False` | ✅ 2.4 |
| `metadata["requiredness"]` | `"required"` / `"optional"` / 缺失 | ✅ 2.2 |
| `route_family` | `"resource_contract"` | ✅ |
| `construct_target` | `"RESOURCE_CONTRACT"` | ✅ |

**Transitional 兼容测试**：以下两个测试覆盖 `semantic_role` 缺失时仅靠
`slot_target` 或 `metadata.direction` 生成 demand 的场景。这些是 Phase A
过渡行为，不是最终 confirmed contract。B2 完成后这些测试需要更新或移除。

- `test_direction_from_slot_target` — 已在源码注释中标记为 `TRANSITIONAL (Phase A compat)`
- `test_direction_from_metadata` — 同上

无需修改 Phase A 核心代码。上述两个测试的行为不由本 Decision Gate 收紧，
而是推迟到 Phase B0/B2 的收紧策略中执行（见 2.1 过渡说明）。

---

## 6. 实施计划第 5.3 节问题回应

| # | 问题 | 回答 |
|---|------|------|
| 1 | `requiredness` 存放在 `RouteAnnotation` 一等字段还是 metadata | metadata（见 2.2）。一等字段提升推迟到 B0 决策 |
| 2 | `direction` 存放在 `slot_target`、metadata，还是两者一致性校验 | `semantic_role` 是 canonical source，`slot_target` 和 `metadata.direction` 是 consistency evidence（见 2.1） |
| 3 | `requiredness=unspecified` 如何由 Stage 2 表达 | `metadata["requiredness"]="unspecified"` 或不填充该字段（见 2.3） |
| 4 | Stage 2 annotation 缺 requiredness 时是否允许生成 demand | 允许。DemandView 保留 demand，`required=None`，发出 `missing_requiredness` diagnostic（见 2.3） |
| 5 | Structural Adapter / Stage 2 是否会使用 required/optional section schema | 是。在 Phase B2 中由 Structural Adapter 或 Stage 2 normalization 映射到 annotation metadata（见第 4 节） |
| 6 | 是否需要修改 prompt/schema | 如需扩大 Stage 2 prompt/schema 以输出 `requiredness`，应在 Phase B2 提交 prompt/schema 设计确认（见 2.2） |
| 7 | DemandView Phase A fixtures 是否与最终 annotation shape 一致 | 一致（见第 5 节） |

---

## 7. 验收标准

Decision Gate 通过条件（来自实施计划第 5.4 节）：

1. ✅ requiredness 来源明确 → `RouteAnnotation.metadata["requiredness"]`
2. ✅ direction 来源明确 → `semantic_role=input_contract/output_contract`
3. ✅ annotation shape 明确 → 第 3 节完整定义
4. ✅ 不依赖 DemandView fallback → 2.5 明确禁止
5. ✅ 不引入未确认 rule-based semantic recovery → 2.5 明确禁止
6. ⏳ PM 明确批准后方可进入 Phase B0

---

## 8. 下一步

PM 批准本 Decision Gate 后 → **Phase B0: ResourceContract IR Schema Impact Audit**

Phase B0 不依赖 Stage 2 的 `requiredness` 实际填充（那属于 Phase B2），
但要求完整审计所有读取 `required: bool` 的 consumer 并制定迁移策略。
