# 工程师C 工作接续文档

**角色**: 工程师C（Resources 专家）  
**移交日期**: 2026-05-12  
**项目**: nl2spl Worker-Aware Pipeline Migration  
**状态**: T2 步骤1-4已完成，步骤5（Orchestrator修改）待开始

---

## 必读文档（按优先级排序）

| # | 文档路径 | 说明 |
|---|---------|------|
| 1 | `docs/implementation/worker-aware-migration/TEAM-ASSIGNMENT.md` | 团队分配 + 时间线 + 各任务详细描述 |
| 2 | `docs/implementation/worker-aware-migration/ENGINEER-C-CONTEXT.md` | 工程师C专属上下文：架构概览、IR详解、T2/T3任务规格 |
| 3 | `docs/migration-worker-aware-pipeline.md` | 迁移主方案文档：D1-D10设计决策、各Phase规格、数据流图 |
| 4 | 本文档 | 当前进度、已完成/待完成、文件修改清单 |

---

## 1. 任务分配回顾

工程师C负责任务流：**T0评审 → T2(SymbolTable+Stage6) → T3辅助(集成测试)**

| 阶段 | 任务 | 内容 | 预估时间 |
|------|------|------|----------|
| 第一阶段 | T0 | 评审工程师A的IR Contract修正 | 第1天 |
| 第四阶段 | T2 | 实现WorkerScopedResourceIR + SymbolTable scope + Stage 6 worker-aware | 第10-13天 |
| 第五阶段 | T2 | Stage 6 worker-aware 完成 | 第14-18天 |
| 第六阶段 | T3 | 集成测试辅助 | 第19-20天 |

---

## 2. 已完成任务

### 2.1 T0：IR Contract 评审 ✅

**完成内容**：
- 评审工程师A的`WorkerStepPlanIR`实现 → 通过
- 评审工程师A的`ChildWorkerIR`升级 → 发现3个缺失字段
- 评审工程师B的评审意见 → 确认缺口属实
- 工程师A已修复：`alternative_flows`、`exception_flows`、`api_refs` ✅
- M0冻结确认 ✅

**设计决策**：D1-D10已在`docs/migration-worker-aware-pipeline.md`中冻结。

---

### 2.2 T2：步骤1-3 — IR结构 + SymbolTable scope ✅

**完成日期**: 2026-05-12

#### 步骤1：VariableSymbol 添加 scope 字段
- **文件**: `src/nl2spl/ir/symbol_table.py`
- 新增 `scope_kind: Literal["global", "worker", "handoff"] = "global"`
- 新增 `scope_id: str | None = None`
- 向后兼容：使用默认值

#### 步骤2：SymbolTable 支持 scope
- **文件**: `src/nl2spl/ir/symbol_table.py`
- 新增 `_variables: dict[tuple[str, str | None, str], VariableSymbol]` — 复合key存储（D4决策）
- 保留 `variables: dict[str, VariableSymbol]` — 旧接口兼容
- 修改 `declare()` 同时更新两个接口
- 新增方法：
  - `declare_scoped()` — 声明带scope的变量
  - `get_variables_for_worker(worker_id)` — 获取worker可见变量（global + worker-scoped）
  - `get_variables_for_handoff(handoff_id)` — 获取handoff可见变量（global + handoff-scoped）
  - `get_variable_list_for_worker_prompt(worker_id)` — 生成worker的LLM prompt变量列表
  - `get_all_declared_variables()` — 获取所有声明的变量（用于SPL DEFINE_VARIABLES）

#### 步骤3：新增 IR 类
- **WorkerScopedResourceIR** (`src/nl2spl/ir/resource_registry_ir.py`)
  - `global_resources: ResourceRegistryIR` — 全局共享资源
  - `worker_resources: dict[str, ResourceRegistryIR]` — 按worker_id分组
  - `handoff_contracts: dict[str, HandoffContractIR]` — 按handoff_id分组
  - 辅助方法：`get_all_variables()`、`get_all_apis()`

- **HandoffContractIR** (`src/nl2spl/ir/worker_plan_ir.py`)
  - `handoff_id`、`parent_worker_id`、`child_worker_id`
  - `input_variables: list[ContractFieldIR]` — 输入契约
  - `output_variables: list[ContractFieldIR]` — 输出契约

- **导出更新** (`src/nl2spl/ir/__init__.py`)：已添加所有新类

---

### 2.3 T2：步骤4 — Stage 6 worker-aware 资源提取 ✅

**完成日期**: 2026-05-12

#### 新增方法（`src/nl2spl/pipeline/stages/stage6_resource_extractor.py`）

1. **`execute_worker_scoped()`** — Worker-aware 资源提取主入口
   - 参数：spans, routes, worker_flow_plan, worker_block_plan, worker_plan, canonical_input
   - 返回：`tuple[WorkerScopedResourceIR, SymbolTable]`
   - 工作流程：
     1. 提取 global 资源（从 main worker 的 flow/blocks）
     2. 遍历 child workers，为每个 child 提取资源
     3. 提取 handoff contracts
     4. 返回 WorkerScopedResourceIR

2. **`_extract_resources_for_scope()`** — 按 scope 提取资源的内部方法
   - 参数：spans, routes, flow, blocks, symbol_table, canonical_input, scope_kind, scope_id
   - 返回：`tuple[ResourceRegistryIR, SymbolTable]`
   - 工作流程：
     1. 构建 LLM prompt（stage6 prompt）
     2. 调用 LLM 获取资源
     3. 解析 variables/files/apis/types
     4. 合并 hard facts（如果 canonical_input 不为空）
     5. 使用 `symbol_table.declare_scoped()` 声明变量 🔑
     6. 返回 ResourceRegistryIR

3. **`_build_handoff_contract()`** — 从 WorkerHandoffIR 构建 HandoffContractIR
   - 从 `input_bindings` 提取输入变量
   - 从 `output_bindings` 提取输出变量
   - 从 SymbolTable 查找变量元数据

---

### 2.4 单元测试 ✅

| 测试文件 | 测试数 | 状态 |
|----------|--------|------|
| `tests/unit/ir/test_symbol_table_scope.py` | 13 | ✅ 全部通过 |
| `tests/unit/pipeline/stages/test_stage6_worker_scoped.py` | 6 | ✅ 全部通过 |
| `tests/unit/ir/test_worker_step_plan_ir.py` | 9 | ✅ 全部通过（工程师A创建，我验证）|

---

## 3. 待完成任务

### 3.1 高优先级：修改 Orchestrator（步骤5）

**文件**: `src/nl2spl/pipeline/orchestrator.py`

**需要做的事情**：在Orchestrator中添加worker-aware调用路径，根据配置选择legacy path或worker-aware path。

参考规格（`ENGINEER-C-CONTEXT.md` §3.1.7）：

```python
# Stage 6 调用逻辑
if (self.config.enable_worker_boundary_planner
    and worker_flow_plan is not None
    and worker_block_plan is not None
    and worker_plan is not None):
    # Worker-aware path
    worker_scoped_resources, symbol_table = self._run_stage6_worker_scoped(
        spans, routes, worker_flow_plan, worker_block_plan, worker_plan, canonical_input
    )
    resources = worker_scoped_resources.global_resources
else:
    # Legacy path
    resources, symbol_table = self._run_stage6(spans, routes, ...)
```

**关键点**：
- worker-aware path 的输入是 `worker_flow_plan` 和 `worker_block_plan`（不是 legacy `FlowStructureIR`/`BlockStructureIR`）
- 需要将 `worker_scoped_resources` 存入 intermediate_results（用于下游 Stage 9.5 和 Stage 10）
- 需要对 Stage 7 做类似的修改（工程师A已完成 `execute_worker_scoped()`，需要在 Orchestrator 中调用）

**依赖**：
- ⏳ 等待工程师A完成 Stage 9.5（T1.5任务）
- ⏳ 等待工程师B完成 Stage 10/11（T1.6任务）

### 3.2 中优先级：集成测试（T3辅助）

**文件**: `tests/integration/`

**需要做的事情**：
- 编写端到端测试：从 Stage 3.5 到 Stage 11 的 worker-aware 完整路径
- 验证 ServiceNow `internal-comms` 用例在 worker-aware path 下的输出
- 验证 enterprise-procedure 用例

### 3.3 低优先级：文档更新

**需要做的事情**：
- 更新 `docs/spl_nl_to_spl_design_document_v4.md` 添加 SymbolTable scope 说明
- 更新 Stage 6 的 docstring

---

## 4. 文件修改清单

### 工程师C修改的文件（与工程师A的改动区分）

| 文件 | 改动类型 | 改动量 | 关键内容 |
|------|----------|--------|----------|
| `src/nl2spl/ir/symbol_table.py` | 修改 | +166行 | VariableSymbol scope字段、SymbolTable scope方法 |
| `src/nl2spl/ir/resource_registry_ir.py` | 修改 | +46行 | WorkerScopedResourceIR类 |
| `src/nl2spl/ir/worker_plan_ir.py` | 修改 | +53行 | HandoffContractIR类 |
| `src/nl2spl/ir/__init__.py` | 修改 | +6行 | 导出新类 |
| `src/nl2spl/pipeline/stages/stage6_resource_extractor.py` | 修改 | +354行 | execute_worker_scoped等3个方法 |

### 工程师C新建的文件

| 文件 | 内容 |
|------|------|
| `tests/unit/ir/test_symbol_table_scope.py` | SymbolTable scope 13个单元测试 |
| `tests/unit/pipeline/stages/test_stage6_worker_scoped.py` | Stage 6 worker-scoped 6个单元测试 |

### 工程师A修改的文件（接续工程师需了解，但不用修改）

| 文件 | 说明 |
|------|------|
| `src/nl2spl/pipeline/stages/stage7_step_extractor/worker_scoped.py` | Stage 7 的 `execute_worker_scoped()` — Stage 6 的后续步骤 |
| `src/nl2spl/pipeline/stages/stage9_5_normalizer.py` | Stage 9.5 — 验证 worker-scoped IR 完整性 |
| `src/nl2spl/pipeline/stages/stage10_worker_assembler.py` | Stage 10 — 使用 WorkerStepPlanIR 组装 WorkerIR |
| `src/nl2spl/pipeline/stages/stage11_spl_renderer.py` | Stage 11 — 渲染 child worker 完整 flow |
| `src/nl2spl/pipeline/orchestrator.py` | Orchestrator — pipeline 编排（需要修改以添加 worker-aware path） |
| `src/nl2spl/ir/worker_ir.py` | WorkerIR/ChildWorkerIR 升级（含 alternative_flows 等） |
| `src/nl2spl/pipeline/stages/stage3_5_worker_boundary_planner.py` | Stage 3.5 — Worker Plan 生成 |

---

## 5. 测试状态

### 当前测试结果

```
总测试结果（不含集成测试）:
  395 passed, 41 deselected, 1 warning
```

### 工程师C新增测试结果

```
tests/unit/ir/test_symbol_table_scope.py ............. 13 passed
tests/unit/pipeline/stages/test_stage6_worker_scoped.py ...... 6 passed
tests/unit/ir/test_worker_step_plan_ir.py ......... 9 passed
────────────────────────────────────────────────────
                                                     28 passed
```

### LSP诊断

所有工程师C修改的文件（`symbol_table.py`、`resource_registry_ir.py`、`stage6_resource_extractor.py`）无类型错误。

---

## 6. 已实现的设计决策

| 决策 | 实现位置 | 实现方式 |
|------|----------|----------|
| D1 | Stage 7 worker_scoped.py | INVOKE_WORKER从WorkerHandoffIR生成 |
| D3 | worker_ir.py | ChildWorkerIR含alternative_flows/exception_flows/api_refs |
| **D4** | **symbol_table.py** | **复合key (scope_kind, scope_id, name)** |
| D5 | worker_plan_validator.py | span ownership violation = error |
| D6 | orchestrator.py | worker-aware path + legacy path 共存 |
| D8 | WorkerPlanIR | main_worker property |

---

## 7. 关键数据流（接续工程师必须理解）

```
WorkerPlanIR (Stage 3.5)
    ↓
Stage 4 → WorkerFlowPlanIR
    ↓
Stage 5 → WorkerBlockPlanIR
    ↓
Stage 6 → WorkerScopedResourceIR + SymbolTable ← 你的工作在这里
    ↓         ├─ global_resources (ResourceRegistryIR)
    ↓         ├─ worker_resources: dict[str, ResourceRegistryIR]
    ↓         └─ handoff_contracts: dict[str, HandoffContractIR]
Stage 7 → WorkerStepPlanIR + SymbolTable
    ↓
Stage 9.5 → 校验 worker-scoped IR
    ↓
Stage 10 → WorkerIR
    ↓
Stage 11 → SPL
```

**SymbolTable 数据流**：
```
Stage 6 调用 symbol_table.declare_scoped(scope_kind="global"/"worker", scope_id=...)
    → _variables[(scope_kind, scope_id, name)] = VariableSymbol(...)
    → 如果是 global: variables[name] = VariableSymbol(...)
Stage 7 调用 symbol_table.get_variables_for_worker(worker_id) 获取可见变量
Stage 11 调用 symbol_table.get_all_declared_variables() 获取所有声明变量
```

---

## 8. 接续工作步骤建议

### 第一步：阅读必读文档
按第0节的顺序阅读4个必读文档，理解项目全貌。

### 第二步：运行测试确认环境
```powershell
python -m pytest tests/unit/ir/test_symbol_table_scope.py -v
python -m pytest tests/unit/pipeline/stages/test_stage6_worker_scoped.py -v
python -m pytest tests/ -k "not integration" -q
```

### 第三步：实现 Orchestrator 修改
1. 阅读 `ENGINEER-C-CONTEXT.md` §3.1.7 的规格
2. 阅读 `src/nl2spl/pipeline/orchestrator.py` 当前实现
3. 参考 `ENGINEER-C-CONTEXT.md` 中的代码模板
4. 添加 worker-aware path（不删除 legacy path）
5. 确保 `worker_scoped_resources` 存入 `intermediate_results`
6. 编写 Orchestrator 测试

### 第四步：集成测试
1. 使用 `examples/output/internal-comms/` 的输入数据
2. 验证 worker-aware path 的 stage6 输出
3. 验证全链路输出与预期一致

### 第五步：清理和文档
1. 确保所有测试通过
2. 更新设计文档

---

## 9. 注意事项

1. **向后兼容**：不要删除 legacy path，worker-aware path 和 legacy path 必须共存（D6决策）
2. **类型安全**：`symbol_table.py` 使用 `Literal` 类型注解，保持类型安全
3. **双存储设计**：`_variables`（复合key）和 `variables`（旧接口）需要同步更新
4. **全局变量规则**：只有 `scope_kind="global"` 的变量同时存储在两个接口中
5. **Orchestrator**：目前是工程师A修改的版本，添加 worker-aware path 时不破坏现有逻辑
6. **SymbolTable `get_all_declared_variables()`**：用于 SPL DEFINE_VARIABLES，只返回 global + contract + declared=True 的变量

---

## 10. 联系人

| 角色 | 负责任务 | 说明 |
|------|----------|------|
| 工程师A | T0→T1→T1.5→T2辅助 | IR专家，已完成Stage 7和Stage 9.5 |
| 工程师B | T1.6→T3 | Renderer专家，负责Stage 10/11 |
| **你（接续工程师C）** | **T2→T3辅助** | Resources专家，负责SymbolTable+Stage 6 |

---

**原工程师C签字**: Sisyphus（AI Agent）  
**移交日期**: 2026-05-12

**接续工程师签字**: _________________  
**接续日期**: _________________
