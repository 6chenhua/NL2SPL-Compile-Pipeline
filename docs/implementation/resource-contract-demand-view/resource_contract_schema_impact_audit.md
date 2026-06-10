# ResourceContract IR Schema Impact Audit

**Phase B0 交付物。审计所有 `required: bool` consumer 点及其三值迁移影响。**

---

## 1. 审计范围

本审计覆盖 `required: bool` 字段从源头到 SPL 渲染的完整链路，以及
`RouteAnnotation.metadata["requiredness"]` 的读写点。

按照实施计划第 20 节清单 + 下游 worker/rendering 扩展链路。

---

## 2. IR Dataclass 审计

### 2.1 带 `required: bool` 的 IR 类型

| # | 类型 | 文件 | 行 | 当前类型 | 迁移目标 |
|---|------|------|----|---------|---------|
| 1 | `ResourceContractDemandIR` | `ir/resource_contract_ir.py` | 40 | `required: bool` | `required: bool｜None` + `requiredness: ContractRequiredness` |
| 2 | `ResourceContractFieldIR` | `ir/resource_contract_ir.py` | 125 | `required: bool` | `required: bool｜None` + `requiredness: ContractRequiredness` |
| 3 | `ContractFieldIR` | `ir/worker_plan_ir.py` | 77 | `required: bool` | `required: bool｜None` + `requiredness: ContractRequiredness` |
| 4 | `WorkerInput` | `ir/worker_ir.py` | 64 | `required: bool = True` | `required: bool｜None = True` (default 保留) |
| 5 | `WorkerOutput` | `ir/worker_ir.py` | 77 | `required: bool = True` | `required: bool｜None = True` (default 保留) |
| 6 | `InputBindingIR` | `ir/worker_plan_ir.py` | 173 | `required: bool` | **保持 `bool`**（handoff binding 不参与 source-demand 三值迁移；如未来需扩，另开设计） |
| 7 | `OutputBindingIR` | `ir/worker_plan_ir.py` | 183 | `required: bool` | **保持 `bool`**（同上） |
| 8 | `VariableSpec` | `ir/resource_registry_ir.py` | 26 | `required: bool` | `required: bool｜None` |

### 2.2 `ResourceContractBindingIR`（特殊：无 required 字段）

`ir/resource_contract_ir.py:136` 的 `ResourceContractBindingIR` **当前不携带 `required` 字段**。
Binding 是在 Stage 6 从 `ResourceContractFieldIR` 构造的，但 `required` 没有被传过去。
Resource contract 的 requiredness 改由 `ContractFieldIR.required` 承载（Stage 6 backfill），
而 `ResourceContractBindingIR` 只保留 demand_id / resource_name / resource_kind / direction / scope。

**B1 决策点**：是否在 `ResourceContractBindingIR` 增加 `requiredness` 字段？
如果 Post-normalize IRS 直接从 binding 读取 requiredness 而不需要查 ContractFieldIR，
则 binding 应新增该字段。否则只需确保 ContractFieldIR 完整传递即可。

---

## 3. Consumer 逐点审计

### 3.1 orchestrator.py

| 行 | 操作 | 当前行为 | B1 影响 |
|----|------|---------|--------|
| 183-187 | `ResourceContractPlanner().plan(...)` → `resource_contract_plan` | 产生 `ResourceContractPlanIR`，其中 `demands[].required: bool` | Phase D 移除此调用。B1 改 `ResourceContractDemandIR.required` 类型 |
| 189 | `resource_contract_plan.to_payload()` | 序列化 `required: bool` | payload 需新增 `requiredness` 字段 |
| 218 | 传递 `resource_contract_plan` 给 Stage 3.5 | — | 改为传递 DemandView |
| 341 | 传递 `resource_contract_plan` 给 Stage 6 | — | 改为传递 DemandView |
| 452-454 | `post_norm_diags` 接收 `resource_contract_plan` | — | 改为 `demand_view` |

**B1 迁移策略**：orchestrator 的 `required: bool` 消费路径由 Phase D 整体切换覆盖，B1 只需确保 payload 向后兼容。

### 3.2 stage3_5_worker_boundary_planner

| 文件 | 行 | 操作 | 当前行为 | B1 影响 |
|------|----|------|---------|--------|
| `executor.py` | 305 | `ContractFieldIR(..., f.required, ...)` | `VariableFact.required: bool` → `ContractFieldIR` | `VariableFact.required` 保持 bool（hard fact 总是确定性的） |
| `executor.py` | 309 | 同上（output） | — | 同上 |
| `executor.py` | 332 | `required=demand.required` | `ResourceContractDemandIR.required: bool` → `ContractFieldIR` | **关键路径**：demand 的 tri-state requiredness 必须在此处正确传入 ContractFieldIR |
| `materializer.py` | 505 | `InputBindingIR(f.name, f.name, f.required)` | `ContractFieldIR.required`（B1 将改为 `bool｜None`）→ 传参给 InputBindingIR | InputBindingIR.required 保持 `bool` — 如 ContractFieldIR.required 为 None，此处需显式处理再传参 |
| `materializer.py` | 509 | `OutputBindingIR(f.name, f.name, f.required, "set")` | 同上 | 同上 |
| `prompt_builder.py` | 246 | `required={demand.required}` | prompt 中显示 bool | context 改为显示三值 |

**B1 迁移策略**：
- `executor.py:332` 从 `demand.required` 改为 `demand.requiredness`，`required` 作为兼容字段保留
- `materializer.py:505,509` 改为显式处理 `required is None` 分支
- `prompt_builder.py:246` 改为 `requiredness={demand.requiredness}`

### 3.3 stage6_resource_extractor

| 文件 | 行 | 操作 | 当前行为 | B1 影响 |
|------|----|------|---------|--------|
| `context_builder.py` | 106 | `'required' if f.required else 'optional'` | ContractFieldIR `required: bool` 用于 prompt | **truthiness bug**：`None` → `'optional'`（错误） |
| `context_builder.py` | 113 | 同上 | — | 同上 |
| `context_builder.py` | 124 | 同上（VariableFact） | — | VariableFact 保持 bool |
| `context_builder.py` | 169 | `required: {demand.required}` | demand context | 改为 `requiredness: {demand.requiredness}` |
| `worker_scoped.py` | 326-340 | 构造 `ResourceContractFieldIR` | LLM 输出中 `required: bool` | LLM output schema 改为接受三值 |
| `worker_scoped.py` | 313-320 | 构造 `ResourceContractBindingIR` | 不包含 `required` | B1 决定是否增加 `requiredness` |
| `worker_scoped.py` | 534 | `field.required = materialized.required` | `ResourceContractFieldIR.required → ContractFieldIR.required` | `bool｜None` 赋值，类型一致即可 |
| `worker_scoped.py` | 570 | `required=binding.required` | — | 需要确认 `binding` 类型（实际是 `ResourceContractBindingIR`？还是 `InputBindingIR`？） |
| `legacy.py` | 248 | `existing.required = existing.required or var.required` | **truthiness bug**：`True or None = True` 正确但逻辑不清晰 | 改用 `if existing.required is None` 显式分支 |

**B1 迁移策略**：
- context_builder 的 `'required' if f.required else 'optional'` → 三值转换函数
- prompt 改为传递 `requiredness: required｜optional｜unspecified`
- LLM output schema 增加 `requiredness`，parser 做 validation
- `or var.required` 逻辑改为显式 None 处理

### 3.4 compiler/irs/checkers/post_normalize.py

| 行 | 操作 | 当前行为 | B1 影响 |
|----|------|---------|--------|
| 114 | `if not field.required:` | 跳过未 required 的 field | `None` → truthy-false → 被跳过（**语义错误**：unspecified 不应被跳过） |
| 137 | `if not (variable.required and variable.source == "output"):` | provider check | `None` → truthy-false → provider 被跳过（**语义错误**） |
| 409 | `required={demand.required}` | diagnostic message | 改为显示三值 |
| 469 | `demand.direction == "output" and demand.required` | producer check 入口 | `None` → **被跳过**，unspecified output 不触发 producer check → 符合设计（unspecified 只 warning） |

**B1 迁移策略**：
- 114：`if field.required is False:` (仅跳过明确标记为 optional 的)
- 137：改为 `variable.required is not False`
- 469：保持 `demand.required` truthiness（`None` → 不触发 producer check → 正确行为）
  - 但需要额外：当 `requiredness=unspecified` 且无 producer 时，发出 **warning** 而非 error

### 3.5 compiler/producer_index.py

| 行 | 操作 | 当前行为 | B1 影响 |
|----|------|---------|--------|
| 113 | `resource_contract_bindings: list[ResourceContractBindingIR]｜None` | 接收 bindings | 如果 B1 在 binding 上加 `requiredness`，此方法需要读取 |
| 306 | producer matching | 基于 binding 匹配 | 同上 |

**B1 迁移策略**：不阻塞。ProducerIndex 主要使用 `ResourceContractBindingIR` 的 `resource_name`/`resource_kind`/`scope` 做匹配，`requiredness` 在当前设计中由 Post-normalize IRS 检查而非 ProducerIndex。

### 3.6 stage10_worker_assembler

| 文件 | 行 | 操作 | 当前行为 | B1 影响 |
|------|----|------|---------|--------|
| `assembler.py` | 81 | `WorkerInput(name=var.name, required=var.required)` | `VariableSpec.required → WorkerInput.required` | `bool｜None` pass-through |
| `assembler.py` | 92 | `WorkerOutput(name=var.name, required=var.required)` | 同上 | 同上 |
| `assembler.py` | 168 | `WorkerInput(field.name, field.required)` | `ContractFieldIR.required → WorkerInput.required` | `bool｜None` pass-through |
| `assembler.py` | 175 | `WorkerOutput(field.name, field.required)` | 同上 | 同上 |
| `assembler.py` | 220,229 | `WorkerInput/WorkerOutput(required=v.required)` | 同上 | 同上 |
| `step_resolver.py` | 40 | `return variable.required` | 返回 `bool` | 返回类型改为 `bool｜None` |
| `child_worker_builder.py` | 90 | `WorkerInput(required=self._is_required(resources, name))` | `_is_required` 返回 `bool`（从 ResourceRegistryIR 查） | **不涉及三值** — child worker 的 required 由 registry 决定，保持 `bool` |
| `child_worker_builder.py` | 94 | `WorkerOutput(required=self._is_required(resources, name))` | 同上 | 同上 |

**B1 迁移策略**：assembler 的 required 全部是 pass-through，只需确保类型一致。
不需要在 assembler 内做语义判断。`child_worker_builder._is_required` 保持返回 `bool`。`step_resolver.py` 返回类型改为 `bool｜None`。

### 3.6b stage9_5_normalizer

#### validation.py — `InputBindingIR.required` / `OutputBindingIR.required` truthiness（11 处）

**关键前提**：`InputBindingIR.required` 和 `OutputBindingIR.required` 的语义与 source-demand
requiredness 不同 — 它们是 handoff binding 级别的约束。

| 行 | 操作 | 当前行为 | B1 影响 |
|----|------|---------|--------|
| 175 | `if binding.required and binding.parent_variable not in step.inputs:` | `None` → False（跳过） | **保留 bool** — handoff binding 不参与三值迁移 |
| 180 | `if binding.required and binding.parent_variable not in symbol_table.variables:` | 同上 | 同上 |
| 193 | `not binding.required` | `None` → True（进入） | 同上 |
| 201 | `if binding.required and binding.parent_variable not in symbol_table.variables:` | `None` → False（跳过） | 同上 |
| 206 | `if binding.required and not self._is_parent_output_used(...)` | `None` → False（跳过） | 同上 |
| 258 | `if binding.required and binding.parent_variable not in step.inputs:` | `None` → False（跳过） | 同上 |
| 264 | `binding.required` (truthiness for diagnostic decision) | `None` → False | 同上 |
| 284 | `binding.required` (truthiness for diagnostic decision) | `None` → False | 同上 |
| 293 | `not binding.required` | `None` → True（进入） | 同上 |
| 301 | `if binding.required and binding.parent_variable not in symbol_table.variables:` | `None` → False（跳过） | 同上 |
| 306 | `if binding.required and not self._is_parent_output_used(...)` | `None` → False（跳过） | 同上 |

**B1 决策**：`InputBindingIR.required` / `OutputBindingIR.required` 保持 `bool`。
Handoff binding requiredness 由 worker plan 决定，不从 source demand 三值传播。
B1 时将这些字段的类型从 `bool` 改为 `bool｜None` 是可选的；如果改为 `bool｜None`，
则上述 11 处都必须显式处理 `None` 分支。如果保持 `bool`，上述代码无需修改。

#### normalization.py — `ContractFieldIR.required` truthiness（3 处）

| 行 | 操作 | 当前行为 | B1 影响 |
|----|------|---------|--------|
| 72 | `"required": binding.required` | 序列化到 payload | 改为三值后需输出 `requiredness` |
| 179 | `any(field.required for field in removed)` | `None` → falsy | 改为 `any(field.required is not False for field in removed)` |
| 191 | `resource_var.required = any(field.required for field in removed)` | `None` 不可参与 `any` truthiness | 同上 |

**B1 策略**：行 179/191 改为 `is not False` 显式处理。

### 3.7 stage11_spl_renderer

| 行 | 操作 | 当前行为 | B1 影响 |
|----|------|---------|--------|
| 184 | `"REQUIRED" if inp.required else "OPTIONAL"` | truthiness 分支 | **严重 bug**：`None` → `"OPTIONAL"` |
| 191 | 同上（output） | 同上 | 同上 |
| 267 | 同上（child worker input） | 同上 | 同上 |
| 274 | 同上（child worker output） | 同上 | 同上 |

**B1 迁移策略**（硬性要求）：
```python
# 当前（bug）
req = "REQUIRED" if inp.required else "OPTIONAL"

# 修复后
if inp.required is True:
    req = "REQUIRED"
elif inp.required is False:
    req = "OPTIONAL"
else:
    req = ""  # or omit the REQUIRED/OPTIONAL keyword entirely
```

### 3.8 feedback report renderer

| 文件 | 操作 | B1 影响 |
|------|------|--------|
| `compiler/feedback_report_renderer.py` | 渲染 resource contract 相关 diagnostic | 需要在 report 中区分 `requiredness=required｜optional｜unspecified` |
| `compiler/report_renderer.py` | 通用 report 渲染 | 同上 |

**B1 迁移策略**：feedback report 中新增 `requiredness` 列的展示。

### 3.9 checkpoint payload serialization

| 文件 | 操作 | B1 影响 |
|------|------|--------|
| `ResourceContractDemandIR.to_payload()` | 序列化 `required: bool` | 新增 `requiredness` 字段 |
| `ResourceContractFieldIR`（无 to_payload） | 通过 dataclass asdict | 需要确定序列化方式 |
| `ContractFieldIR`（无 to_payload） | 通过 dataclass asdict | 同上 |
| `WorkerInput/WorkerOutput`（无 to_payload） | 通过 dataclass asdict | 同上 |

**B1 迁移策略**：至少 `ResourceContractDemandIR.to_payload()` 和 DemandView `DemandViewDemand.to_payload()` 必须包含 `requiredness`。其余类型的序列化方式在 B1 阶段确定。

### 3.10 test fixtures

| 文件 | 操作 | B1 影响 |
|------|------|--------|
| `tests/unit/test_resource_contract_planner.py` | 构造 `ResourceContractDemandIR(required=True/False)` | 需要更新为三值 |
| `tests/fixtures/multi_worker/scenarios.py` | 多 worker 集成测试 fixtures | 同上 |
| `tests/unit/compiler/resource_contract_demand_view/test_builder.py` | Phase A 测试，使用 `requiredness` 三值 | **Phase A 已验证兼容**，B1 时确保 payload 更新 |

---

## 4. Stage 0 / Stage 2 Producer-side `required` Audit

以下属于 `CanonicalVariableFact.required: bool` 和 `VariableSpec.required: bool` 的生产路径。
这些字段保持 `bool`，**不属于** ResourceContract 三值迁移范围。
在 B2 中通过 adapter → Stage 2 → `RouteAnnotation.metadata["requiredness"]` 映射为三值。

### 4.1 Structural Adapter（`structural_nl.py`）

| 行 | 操作 | 当前行为 | B2 影响 |
|----|------|---------|--------|
| 351 | `required = False if source == "input" else True` | header-derived input → default `required=False`，output → `required=True` | **不修改 schema**，保持 `VariableFact.required: bool` |
| 352-354 | `not clean.lower().startswith("optional ")` | 文本前缀推断 optional | **不修改 schema** — 这是 adapter 的 NL 解析行为 |
| 361 | `VariableFact(required=required)` | 写入 `VariableFact.required: bool` | 不变 |
| 385 | `existing.required = existing.required or fact.required` | merge 去重 | 保持 `bool or bool`，不涉及 `None` |

**B2 映射**：Structural Adapter 产生的 `VariableFact.required: bool` 在 Stage 2
annotation normalization 中映射为 `RouteAnnotation.metadata["requiredness"]`：
- `fact.required == True` → `"required"`
- `fact.required == False` → `"optional"`
- 无法从 adapter 确认 → 不填充 metadata（DemandView 解释为 `unspecified`）

### 4.2 Stage 2 Field Router Prompt（`stage2_field_router_prompt.py`）

| 行 | 操作 | 当前行为 | B2 影响 |
|----|------|---------|--------|
| 307 | `d["required"] = fact.required` | prompt payload 展示 bool | B2 可改为展示 `requiredness` 字符串 |

**B2 映射**：prompt payload 的展示值调整。不涉及 schema 变更。

### 4.3 Stage 6 Variable Merge（`worker_scoped.py`, `legacy.py`）

| 文件 | 行 | 操作 | `VariableSpec.required` 参与 |
|------|----|------|----------------------------|
| `worker_scoped.py` | 483, 487 | `existing.required = existing.required or var.required` | `VariableSpec.required: bool` → `bool` |
| `legacy.py` | 248, 251 | 同上 | 同上 |

**B1 策略**：`VariableSpec.required` 改为 `bool｜None` 后，merge 逻辑改为显式 None 分支。

---

## 5. `RouteAnnotation.metadata["requiredness"]` 读写审计

### 写入点

| 文件 | 行 | 当前行为 | B2 影响 |
|------|----|---------|--------|
| `tests/unit/.../test_builder.py` (helpers) | 70 | synthetic fixture 写入 `metadata["requiredness"]` | 不变 |
| 生产 Stage 2 | — | **当前未写入 requiredness** | B2 需要实现 |
| Structural Adapter | — | 产出 `VariableFact.required: bool` | B2 映射为 annotation metadata |

### 读取点

| 文件 | 行 | 当前行为 | B1 影响 |
|------|----|---------|--------|
| `DemandViewBuilder._requiredness_info()` | builder.py | 读取 `ann.metadata.get("requiredness")` | 已实现三值，不变 |

---

## 5. Truthiness 风险点汇总

以下是所有可能因 `required: bool → bool｜None` 改变行为的表达式。

### 5.1 Renderer（4 处）

| # | 行 | 表达式 | `None` 行为 | 是否正确 |
|---|----|--------|------------|---------|
| 1 | 184 | `"REQUIRED" if inp.required else "OPTIONAL"` | → `"OPTIONAL"` | **错误** |
| 2 | 191 | 同上 | → `"OPTIONAL"` | **错误** |
| 3 | 267 | 同上（child worker） | → `"OPTIONAL"` | **错误** |
| 4 | 274 | 同上（child worker） | → `"OPTIONAL"` | **错误** |

**B1 策略**：三值分支 — `required is True → REQUIRED; required is False → OPTIONAL; required is None → ""`

### 5.2 Post-normalize IRS（4 处）

| # | 行 | 表达式 | `None` 行为 | 是否正确 |
|---|----|--------|------------|---------|
| 5 | 114 | `if not field.required:` | → `True`（进入） | **错误** — unspecified 的 field 被跳过 |
| 6 | 137 | `if not (variable.required and variable.source == "output"):` | → `True`（进入） | **错误** — unspecified 的 provider 被跳过 |
| 7 | 409 | `required={demand.required}` | diagnostic message | **低风险** — 仅展示用 |
| 8 | 469 | `demand.required and ...` | → `False`（不触发） | **正确** — unspecified output 不触发 required producer check |

**B1 策略**：行 114 改为 `field.required is False`；行 137 改为 `variable.required is not False`；行 469 保持现状并额外添加 unspecified warning。

### 5.3 Context builder（5 处）

| # | 行 | 表达式 | `None` 行为 | 是否正确 |
|---|----|--------|------------|---------|
| 9 | 106 | `'required' if f.required else 'optional'` | → `'optional'` | **错误** |
| 10 | 113 | 同上 | → `'optional'` | **错误** |
| 11 | 124 | 同上 | → `'optional'` | **错误** |
| 12 | 131 | 同上 | → `'optional'` | **错误** |
| 13 | 169 | `required: {demand.required}` | → `required: None` | **低风险** — prompt display |

**B1 策略**：三值转换函数 `_requiredness_label(r) → "required"｜"optional"｜"unspecified"`

### 5.4 Validation / normalization（14 处）

| # | 文件 | 行 | 表达式 | `None` 行为 | 是否正确 |
|---|------|----|--------|------------|---------|
| 14 | `validation.py` | 175 | `if binding.required and ...` | → False（跳过） | **可能正确** — handoff binding 语义不同 |
| 15 | `validation.py` | 180 | 同上 | → False（跳过） | **可能正确** |
| 16 | `validation.py` | 193 | `not binding.required` | → True（进入） | **可能错误** |
| 17 | `validation.py` | 201 | `if binding.required and ...` | → False（跳过） | **可能正确** |
| 18 | `validation.py` | 206 | 同上 | → False（跳过） | **可能正确** |
| 19 | `validation.py` | 258 | `if binding.required and ...` | → False（跳过） | **可能正确** |
| 20 | `validation.py` | 264 | `binding.required` (truthiness) | → False | **可能错误** |
| 21 | `validation.py` | 284 | `binding.required` (truthiness) | → False | **可能错误** |
| 22 | `validation.py` | 293 | `not binding.required` | → True（进入） | **可能错误** |
| 23 | `validation.py` | 301 | `if binding.required and ...` | → False（跳过） | **可能正确** |
| 24 | `validation.py` | 306 | 同上 | → False（跳过） | **可能正确** |
| 25 | `normalization.py` | 179 | `any(field.required for field in removed)` | `None` → falsy | **潜在错误** |
| 26 | `normalization.py` | 191 | `resource_var.required = any(...)` | `None` 不可赋值 | **类型错误** |
| 27 | `normalization.py` | 72 | `"required": binding.required` | 序列化 None | **低风险** |

**B1 策略**：validation.py 中的 `InputBindingIR.required` / `OutputBindingIR.required` 语义与 source-demand requiredness 不同 — 它们是 handoff-level 的 binding 约束。B1 阶段将此字段保留为 `bool`（handoff binding 的 required 由 worker plan 决定，不从 source demand 三值传播）。normalization.py 行 179/191 改为显式 `is not False`。

### 5.5 Variable merge / adapter（6 处）

| # | 文件 | 行 | 表达式 | `None` 行为 | 是否正确 |
|---|------|----|--------|------------|---------|
| 28 | `worker_scoped.py` | 483 | `existing.required = existing.required or var.required` | `True or None = True` | **正确**但 brittle |
| 29 | `worker_scoped.py` | 487 | 同上 | 同上 | **正确**但 brittle |
| 30 | `worker_scoped.py` | 534 | `field.required = materialized.required` | pass-through | **正确** |
| 31 | `legacy.py` | 248 | `existing.required = existing.required or var.required` | 同上 | **正确**但 brittle |
| 32 | `legacy.py` | 251 | 同上 | 同上 | **正确**但 brittle |
| 33 | `structural_nl.py` | 385 | `existing.required = existing.required or fact.required` | `bool or bool` | **不涉及 None** — `VariableFact.required` 保持 `bool` |

**B1 策略**：merge 逻辑改用 `if existing.required is None: existing.required = var.required` 显式分支。`VariableFact.required` 保持 `bool`（adapter 的 hard fact requiredness 是确定性的）。

### 5.6 Worker assembly（5 处）

| # | 文件 | 行 | 表达式 | `None` 行为 | 是否正确 |
|---|------|----|--------|------------|---------|
| 34 | `assembler.py` | 81 | `WorkerInput(required=var.required)` | pass-through | **正确** |
| 35 | `assembler.py` | 92 | `WorkerOutput(required=var.required)` | pass-through | **正确** |
| 36 | `assembler.py` | 168 | `WorkerInput(field.name, field.required)` | pass-through | **正确** |
| 37 | `assembler.py` | 175 | `WorkerOutput(field.name, field.required)` | pass-through | **正确** |
| 38 | `assembler.py` | 220 | `WorkerInput(required=v.required)` | pass-through | **正确** |
| 39 | `assembler.py` | 229 | `WorkerOutput(required=v.required)` | pass-through | **正确** |
| 40 | `step_resolver.py` | 40 | `return variable.required` | 返回类型改为 `bool｜None` | **类型变化** |
| 41 | `child_worker_builder.py` | 90 | `WorkerInput(required=self._is_required(...))` | `_is_required` 返回 `bool` | **不涉及 None** — child worker 的 required 由 ResourceRegistryIR 决定 |
| 42 | `child_worker_builder.py` | 94 | `WorkerOutput(required=self._is_required(...))` | 同上 | **不涉及 None** |

**B1 策略**：assembler 全部 pass-through，只须确保类型一致。`child_worker_builder._is_required` 返回 `bool`（从 ResourceRegistryIR 查），无需改为三值。`step_resolver.py:40` 返回类型改为 `bool｜None`。

### 5.7 Stage 3.5 demand / Stage 6 contract（4 处）

| # | 文件 | 行 | 表达式 | `None` 行为 | 是否正确 |
|---|------|----|--------|------------|---------|
| 43 | `executor.py` | 332 | `required=demand.required` | pass-through | **正确** — 改为传递三值 |
| 44 | `materializer.py` | 505 | `InputBindingIR(f.name, f.name, f.required)` | pass-through | `f.required` 是 `ContractFieldIR.required`，改为三值后需处理 |
| 45 | `materializer.py` | 509 | `OutputBindingIR(f.name, f.name, f.required, "set")` | 同上 | 同上 |
| 46 | `prompt_builder.py` | 246 | `required={demand.required}` | prompt display | 改为 `requiredness={demand.requiredness}` |

### 5.8 Stage 2 / Adapter producer-side required（2 处）

**重要**：以下 `required` 字段属于 `CanonicalVariableFact.required: bool`，**不属于** ResourceContract 三值迁移范围。它们是 Stage 0 hard fact 层的确定性 `bool`，在 B2 中通过 adapter → Stage 2 → `RouteAnnotation.metadata["requiredness"]` 映射为三值。

| # | 文件 | 行 | 表达式 | B2 影响 |
|---|------|----|--------|---------|
| 47 | `structural_nl.py` | 351-361 | `VariableFact(required=required)` — adapter header/schema-derived | B2：映射到 `RouteAnnotation.metadata["requiredness"]` |
| 48 | `stage2_field_router_prompt.py` | 307 | `d["required"] = fact.required` — prompt payload | B2：prompt 中展示 `requiredness` 而非 `required` |

**B2 策略（非 B1）**：`VariableFact.required: bool` 保持 `bool`。在 Structural Adapter 或 Stage 2 annotation normalization 中，将 hard fact 的 `required` 映射为 `RouteAnnotation.metadata["requiredness"]="required"｜"optional"`。无法从 hard fact 确定时，不填充 metadata（DemandView 解释为 `unspecified`）。

---

**对 B1 实施的强制要求**：以上 48 个 points 在 B1 中必须逐个处理。不允许出现 `None` 被静默当作 `True` 或 `False` 使用的情况。B2 producer path（point 47-48）不需要在 B1 处理。

---

## 6. 迁移总结

### B1 必须修改的类型（按优先级）

```
P0 — Renderer: inp.required / out.required 的 truthiness 分支（4 处）
P0 — Post-normalize IRS: field.required 和 variable.required 的 truthiness（2 处）  
P0 — context_builder: required 转 prompt 字符串（5 处）
P1 — ContractFieldIR.required: bool → bool | None + requiredness 字段
P1 — WorkerInput/WorkerOutput.required: bool → bool | None
P1 — ResourceContractDemandIR.required: bool → bool | None + requiredness 字段
P1 — ResourceContractFieldIR.required: bool → bool | None + requiredness 字段
P2 — VariableSpec.required: bool → bool | None
P2 — Stage 3.5 executor: demand.required → demand.requiredness
P2 — Stage 3.5 materializer: f.required → 三值处理
```

### B1 明确不修改的

- `InputBindingIR.required` / `OutputBindingIR.required`：**保持 `bool`**。
  Handoff binding requiredness 语义独立，不从 source-demand 三值传播。
  如未来需扩 handoff 的 requiredness，必须另开设计方案，不在本迁移中顺手做。
- `ResourceContractBindingIR`：当前不携带 required（B1 决策是否需要新增 requiredness）
- `ProducerIndex`：不直接依赖 requiredness 判断
- Stage 6 prompt/schema：B4 独立修改，B1 仅改 schema 类型

### B1 不需要在 B1 修改的（但 B4 需要）

- Stage 6 LLM output parser 的 requiredness 校验

---

## 7. Phase B0 验收

1. ✅ 列出所有 `required: bool` consumer（本文件第 2-5 节）
2. ✅ 识别所有 truthiness 风险点（第 5 节）
3. ✅ 按优先级排序迁移任务（第 6 节）
4. ✅ 审计测试锁定 consumer 位置（test_schema_impact_audit.py）
5. ✅ 未修改任何生产代码
6. ✅ 未修改任何 schema
