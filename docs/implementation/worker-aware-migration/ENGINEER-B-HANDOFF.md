# 工程师 B 任务转接文档

**转接日期**: 2026-05-12  
**原工程师**: Sisyphus (Engineer B)  
**角色**: Renderer 专家  
**转接原因**: 人员调整  
**紧急程度**: 正常  

---

## 1. 任务状态概览

| 阶段 | 任务 | 状态 | 备注 |
|------|------|------|------|
| 第一阶段 | T0: IR Contract 评审 | ✅ 已完成 | 评审意见已提交，发现 ChildWorkerIR 缺失 3 字段 |
| 第一阶段 | T0: 等待修复 | ✅ 已修复 | 工程师 A 已完成 ChildWorkerIR 字段补充 |
| 第三阶段 | T1.6 准备 | ✅ 已完成 | 准备文档 ENGINEER-B-T1.6-PREP.md |
| 第三阶段 | T1.6 实现 | ✅ 已完成 | Stage 10/11/Orchestrator 代码 + 24 个测试 |
| 第四阶段 | T3: worker-aware path 去 adapter | ⬜ 待启动 | 依赖 T2 完成 |

---

## 2. 我的代码变更清单

### 2.1 修改的文件（Modified）

| 文件 | 变更内容 | 行数变化 |
|------|----------|----------|
| `src/nl2spl/pipeline/stages/stage10_worker_assembler.py` | 新增 `assemble_from_worker_scoped()` + `_build_child_worker()`；扩展 imports | +170 行 |
| `src/nl2spl/pipeline/stages/stage11_spl_renderer.py` | 新增 `__init__()`；重写 `_render_child_worker()` 使用实际 flow | +30 行 / -15 行 |
| `src/nl2spl/pipeline/orchestrator.py` | 新增 `_run_stage10_worker_scoped()`；扩展 imports | +20 行 |

### 2.2 新增的文件（New）

| 文件 | 内容 | 大小 |
|------|------|------|
| `tests/ir/test_child_worker_ir.py` | ChildWorkerIR 单元测试（8 个） | ~140 行 |
| `tests/pipeline/stages/test_stage10_worker_scoped.py` | Stage 10 worker-scoped 测试（6 个） | ~170 行 |
| `tests/pipeline/stages/test_stage11_child_worker_render.py` | Stage 11 child worker 渲染测试（10 个） | ~230 行 |
| `docs/implementation/worker-aware-migration/ENGINEER-B-T1.6-PREP.md` | T1.6 准备分析文档 | ~350 行 |

### 2.3 其他工程师的修改（非我修改，但我的代码依赖它）

| 文件 | 谁改的 | 变更内容 |
|------|--------|----------|
| `src/nl2spl/ir/worker_ir.py` | 工程师 A (T0) | ChildWorkerIR 新增 5 个字段 |
| `src/nl2spl/ir/worker_plan_ir.py` | 工程师 A (T0) | 新增 WorkerStepPlanIR |

---

## 3. 架构理解要点

### 3.1 Pipeline 流程（你的关注范围）

```
Stage 9.5: IR Normalizer（IR 校验）
    ↓
Stage 10: Worker Assembler（worker 组装）← 你的重点
    ↓
Stage 11: SPL Renderer（SPL 渲染）← 你的重点
    ↓
输出：SPL 代码
```

### 3.2 核心问题："synthetic st_child"

**问题根源**：Stage 11 的 `_render_child_worker()` 原来创建了一个假的 `StepIR(step_id="st_child")`，然后在单个 SEQUENTIAL_BLOCK 中渲染，完全忽略 child worker 的实际 flow 结构。

**我的修复**：现在优先使用 `child.main_flow.blocks` + `child.steps` 渲染，与原 main worker 渲染逻辑一致。

### 3.3 关键数据结构

```
WorkerPlanIR
├── workers: list[WorkerSpecIR]        ← worker 定义（含 main/child kind）
├── handoffs: list[WorkerHandoffIR]    ← worker 间调用边
└── main_worker_id: str

WorkerFlowPlanIR                       ← Stage 4 输出
└── worker_flows: dict[str, FlowStructureIR]

WorkerBlockPlanIR                      ← Stage 5 输出
└── worker_blocks: dict[str, BlockStructureIR]

WorkerStepPlanIR                       ← Stage 7 输出（工程师 A 新增）
├── main_worker_id: str
└── worker_steps: dict[str, list[StepIR]]

WorkerIR                               ← Stage 10 输出
├── main_flow: FlowRef
├── alternative_flows: list[AlternativeFlowRef]
├── exception_flows: list[ExceptionFlowRef]
├── api_refs: list[str]
└── child_workers: list[ChildWorkerIR]  ← 每个包含完整 flow + steps
```

### 3.4 新旧路径对比

**Legacy Path** (不受我的改动影响)：
```
Stage 4/5 → worker_plan_adapter → FlowStructureIR / BlockStructureIR
Stage 10 → assembler.assemble(flow, blocks, steps, ...)
```

**Worker-aware Path** (我新增的)：
```
Stage 4/5 → WorkerFlowPlanIR / WorkerBlockPlanIR
Stage 7   → WorkerStepPlanIR
Stage 10  → assembler.assemble_from_worker_scoped(step_plan, ..., flow_plan, block_plan)
```

---

## 4. 实现细节

### 4.1 Stage 10 新增方法

#### `assemble_from_worker_scoped()` 工作流程

```
1. 从 WorkerPlanIR 获取 main_spec
2. 从 worker-scoped blocks 构建 main_flow
3. 构建 main worker 的 alternative_flows / exception_flows
4. 从 main worker steps 收集 api_refs
5. 遍历所有非 main worker：
   a. 获取 child steps（从 WorkerStepPlanIR）
   b. 获取 child flow/blocks（从 WorkerFlowPlanIR / WorkerBlockPlanIR，可选）
   c. 调用 _build_child_worker() 构建 ChildWorkerIR
6. 组装并返回 WorkerIR
```

#### `_build_child_worker()` 工作流程

```
1. 从 blocks 构建 main_flow (FlowRef)
2. 从 flow + blocks 构建 alternative_flows
3. 从 flow + blocks 构建 exception_flows
4. 从 steps 收集 api_refs（CALL_API 类型）
5. 构建并返回 ChildWorkerIR（包含所有字段）
```

### 4.2 Stage 11 修改

#### `_render_child_worker()` 新逻辑

```
旧逻辑（synthetic st_child）：
  MAIN_FLOW → SEQUENTIAL_BLOCK → 单个 synthetic StepIR

新逻辑（实际 flow）：
  if worker.main_flow.blocks:
      MAIN_FLOW → _render_blocks(worker.main_flow.blocks, worker.steps)
  else:
      MAIN_FLOW → SEQUENTIAL_BLOCK → synthetic fallback（兼容性保留）
  
  ALTERNATIVE_FLOWs → _render_blocks(alt.blocks, worker.steps)
  EXCEPTION_FLOWs    → _render_blocks(exc.blocks, worker.steps)
```

#### `__init__()` 新增

原来 `_command_index`, `_decision_index`, `_produced_variables`, `_result_data_types` 
只在 `render()` 方法中初始化，导致私有方法无法独立调用。现在移到 `__init__` 中初始化。

### 4.3 Orchestrator 新增

#### `_run_stage10_worker_scoped()`

```python
def _run_stage10_worker_scoped(
    self,
    worker_step_plan: WorkerStepPlanIR,
    resources: ResourceRegistryIR,
    symbols: SymbolTable,
    worker_plan: WorkerPlanIR,
    worker_flow_plan: WorkerFlowPlanIR | None = None,
    worker_block_plan: WorkerBlockPlanIR | None = None,
) -> WorkerIR:
```

**注意**：orchestrator 的 `run()` 方法中 Stage 10 调用点（line ~268）尚未切换到 worker-scoped 路径。这需要在 T3 阶段做，因为需要等 Stage 7 先输出 `WorkerStepPlanIR`。

---

## 5. 测试状态

### 5.1 我新增的测试（24 个 — 全部通过）

```
tests/ir/test_child_worker_ir.py ............................. 8 passed
tests/pipeline/stages/test_stage10_worker_scoped.py ......... 6 passed
tests/pipeline/stages/test_stage11_child_worker_render.py ... 10 passed
```

### 5.2 已知预存测试失败（非我引入）

以下测试在我修改前就已失败（与工程师 A/C 的并行工作有关）：

| 测试 | 文件 | 可能原因 |
|------|------|----------|
| `test_orchestrator_feature_flag_on_runs_worker_aware_path` | `test_multi_worker_orchestrator_rollout.py` | 集成测试，依赖 Stage 7 worker-aware 路径 |
| `test_symbol_table_get_all_declared_variables` | `test_symbol_table_scope.py` | 工程师 C 的 scope 实现未完成 |
| `test_worker_aware_stage45_context_feeds_downstream_workerplan_path` | 集成测试 | 同上 |

### 5.3 运行测试命令

```bash
# 运行我的所有测试
python -m pytest tests/ir/test_child_worker_ir.py tests/pipeline/stages/test_stage10_worker_scoped.py tests/pipeline/stages/test_stage11_child_worker_render.py -v

# 运行全量测试（跳过已知失败）
python -m pytest tests/ -v -k "not (test_orchestrator_feature_flag or test_symbol_table_get_all or test_worker_aware_stage45)"
```

---

## 6. 必读文档清单（按优先级排序）

### 优先级 1：理解项目架构

| # | 文档 | 路径 | 说明 |
|---|------|------|------|
| 1 | **工程师 B 上下文** | `docs/implementation/worker-aware-migration/ENGINEER-B-CONTEXT.md` | 你的角色、架构概览、关键 IR 定义 |
| 2 | **迁移方案 v3.0** | `docs/migration-worker-aware-pipeline.md` | 全链路迁移方案，含 D1-D10 设计决策 |
| 3 | **团队任务分配** | `docs/implementation/worker-aware-migration/TEAM-ASSIGNMENT.md` | 3 人分工、时间线、里程碑 |

### 优先级 2：理解具体任务

| # | 文档 | 路径 | 说明 |
|---|------|------|------|
| 4 | **T1.6 任务规格** | `docs/implementation/worker-aware-migration/T1.6-child-worker-flow.md` | 你要做的任务详细规格 |
| 5 | **T1.6 准备文档** | `docs/implementation/worker-aware-migration/ENGINEER-B-T1.6-PREP.md` | 我对 Stage 10/11 的分析笔记 |
| 6 | **T0 IR Contract** | `docs/implementation/worker-aware-migration/T0-ir-contract.md` | IR 设计基础 |
| 7 | **T3 任务规格** | `docs/implementation/worker-aware-migration/T3-remove-legacy-adapter.md` | 你后续要做的任务 |

### 优先级 3：理解代码库

| # | 文件 | 关键内容 |
|---|------|----------|
| 8 | `src/nl2spl/ir/worker_ir.py` | ChildWorkerIR, WorkerIR 定义 |
| 9 | `src/nl2spl/ir/worker_plan_ir.py` | WorkerStepPlanIR, WorkerFlowPlanIR, WorkerBlockPlanIR |
| 10 | `src/nl2spl/pipeline/stages/stage10_worker_assembler.py` | 我修改过的文件 |
| 11 | `src/nl2spl/pipeline/stages/stage11_spl_renderer.py` | 我修改过的文件 |
| 12 | `src/nl2spl/pipeline/orchestrator.py` | 我修改过的文件 |

---

## 7. 已知问题与注意事项

### 7.1 代码层面的注意事项

1. **Orchestrator 尚未切换到 worker-scoped 路径** — 我的 `_run_stage10_worker_scoped()` 方法已经写好，但 `run()` 方法中 Stage 10 调用仍使用 legacy `_run_stage10()`。切换需要在 T3 阶段做，前提是 Stage 7 输出 `WorkerStepPlanIR`。

2. **`_render_child_worker()` 的 fallback** — 当 `child.main_flow.blocks` 为空时，仍使用 synthetic st_child 作为兼容性保留。当上游 Stage 10 正确填充 flow 信息后，fallback 就不会被触发了。

3. **SPLRenderer 的 `__init__`** — 新增了 `__init__` 方法初始化 `_command_index`、`_decision_index`、`_produced_variables`、`_result_data_types`。`render()` 方法中仍有重复赋值（`_command_index = 1` 等），这是有意保留的（确保 `render()` 每次调用时状态重置），**不要删除**。

4. **Type 注解** — 所有新增方法都有完整的 type hints，使用 `| None` 语法（Python 3.10+）。

### 7.2 集成层面的注意事项

1. **依赖工程师 A 的 T1.5** — Stage 7 输出 `WorkerStepPlanIR` 后，我的代码才能端到端工作。
2. **依赖工程师 C 的 T2** — `WorkerScopedResourceIR` 作为 `assemble_from_worker_scoped()` 的可选参数，目前传 `None`。
3. **Legacy path 兼容** — 我的改动完全不影响现有 legacy path。所有现有测试（非预存失败的）都通过。

---

## 8. 下一步工作计划

### 8.1 立即可做（不依赖他人）

- [ ] 代码审查：通读所有我修改的 3 个源文件
- [ ] 运行我新增的 24 个测试确保环境正常
- [ ] 阅读"优先级 1"的 3 个必读文档

### 8.2 等待工程师 A（T1.5 完成）

- [ ] 验证 `WorkerStepPlanIR` 能被 Stage 7 正确生成
- [ ] 端到端测试：WorkerStepPlanIR → assemble_from_worker_scoped() → SPL 输出

### 8.3 T3 任务（第 14-18 天）

根据 `TEAM-ASSIGNMENT.md`：

```
第 14-18 天：T3 部分 - worker-aware path 去 adapter
├── 修改 Orchestrator.run() 中 Stage 10 调用点
├── 确认 Stage 6/7/9.5/10 使用正确 path
├── 运行完整测试套件
└── 条件性删除 legacy adapter

第 19-20 天：T3 完成和收尾
├── 完成 T3 所有工作
├── 运行完整测试套件
└── 代码审查
```

参考 `T3-remove-legacy-adapter.md` 了解详细规格。

---

## 9. 快速上手检查清单

接替工程师请按此顺序操作：

```
□ 1. 阅读 docs/implementation/worker-aware-migration/ENGINEER-B-CONTEXT.md
□ 2. 阅读 docs/implementation/worker-aware-migration/TEAM-ASSIGNMENT.md（重点看工程师 B 的时间线）
□ 3. 阅读 docs/implementation/worker-aware-migration/ENGINEER-B-T1.6-PREP.md
□ 4. 阅读本 HANDOFF 文档
□ 5. 运行测试确认环境正常：
     python -m pytest tests/ir/test_child_worker_ir.py tests/pipeline/stages/test_stage10_worker_scoped.py tests/pipeline/stages/test_stage11_child_worker_render.py -v
□ 6. 重点阅读这 3 个源文件中的新增方法：
     - stage10_worker_assembler.py: assemble_from_worker_scoped() + _build_child_worker()
     - stage11_spl_renderer.py: _render_child_worker() + __init__()
     - orchestrator.py: _run_stage10_worker_scoped()
□ 7. 与工程师 A 确认 T1.5 进度
□ 8. 与工程师 C 确认 T2 进度
```

---

## 10. 团队联系人

| 角色 | 负责任务 | 当前阶段 |
|------|----------|----------|
| 工程师 A | T0 → T1 → T1.5 → T2 辅助 | 第三阶段（T1.5: Stage 9.5） |
| 工程师 B（你） | T1.6 → T3 | 第三阶段（T1.6 完成） |
| 工程师 C | T2 → T3 辅助 | 第三阶段（准备 T2） |

---

**文档版本**: v1.0  
**最后更新**: 2026-05-12
