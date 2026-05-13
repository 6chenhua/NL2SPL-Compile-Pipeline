# 项目状态文档：Worker-Aware Pipeline 迁移

**文档类型**: 项目状态与接任指南  
**创建日期**: 2026-05-12  
**当前 PM**: Sisyphus（准备转接）  
**接任工程师**: 待指定  
**项目总预估**: 2.5-3 周  
**已完成时间**: 约 1 周  
**剩余时间**: 约 1.5-2 周

---

## 1. 项目概述

### 1.1 一句话描述

将 nl2spl pipeline 从「只处理 main worker 的 legacy adapter 模式」迁移到「全链路 worker-aware 模式」，让所有 Stage 都能正确处理多个 worker（main + child）。

### 1.2 为什么要做这个迁移

当前系统支持"worker"概念（类似于微服务或子任务），但只完成了一半：
- Stage 4/5 已经能识别多个 worker
- Stage 6/7/9.5/10 仍然通过适配器只看 main worker
- child worker 的流程被丢弃，无法正确渲染

### 1.3 项目目录

```
docs/implementation/worker-aware-migration/    # 所有项目文档
docs/migration-worker-aware-pipeline.md         # 主迁移方案（必读）
src/nl2spl/ir/                                  # IR 定义（数据模型）
src/nl2spl/pipeline/stages/                     # Pipeline Stage 实现
src/nl2spl/pipeline/orchestrator.py             # Pipeline 编排器
tests/unit/                                     # 单元测试
```

---

## 2. 当前状态总览

### 2.1 测试状态

```
============================= 371 passed in 4.59s ==============================
```

**全部测试通过，无回归问题。**

| 状态 | 数量 |
|------|------|
| ✅ 通过 | 371 |
| ❌ 失败 | 0 |
| 🔧 跳过 | 0 |

### 2.2 任务完成状态

| 任务 ID | 任务名称 | 负责人 | 状态 | 完成日期 |
|---------|----------|--------|------|----------|
| T0 | IR Contract 修正 | 工程师 A | ✅ 完成 | 第 1 天 |
| T1 | WorkerScopedStepIR + Stage 7 | 工程师 A | ✅ 完成 | 第 5 天 |
| T1.0.5 | Worker-aware prompt 整合 | 工程师 A | ✅ 完成 | 第 5 天 |
| T1.5 | Worker-aware Stage 9.5 | 工程师 A | ✅ 完成 | 第 9 天 |
| T1.6 | WorkerIR/Renderer child-flow support | 工程师 B | ⏳ 准备中 | - |
| T2 | WorkerScopedResourceIR + SymbolTable | 工程师 C | ⏳ 进行中 | - |
| T3 | worker-aware path 去 adapter | (待 T2 完成) | 🔲 待启动 | - |

---

## 3. 必读文档清单（按阅读顺序）

### 3.1 核心文档（必须全部阅读）

| 序号 | 文档 | 路径 | 说明 | 阅读时间 |
|------|------|------|------|----------|
| 1 | **项目 README** | `docs/implementation/worker-aware-migration/README.md` | 任务总览、开发规范、沟通机制 | 5 分钟 |
| 2 | **迁移方案 v3.0** | `docs/migration-worker-aware-pipeline.md` | 完整迁移方案、数据流、设计决策 D1-D10 | 30 分钟 |
| 3 | **团队分配方案** | `docs/implementation/worker-aware-migration/TEAM-ASSIGNMENT.md` | 3 人团队分配、时间线、依赖关系 | 10 分钟 |
| 4 | **任务分配矩阵** | `docs/implementation/worker-aware-migration/TASK-ASSIGNMENT.md` | 每个任务的范围、验收标准、交付物 | 15 分钟 |

### 3.2 上下文文档（理解团队分工）

| 序号 | 文档 | 路径 | 说明 |
|------|------|------|------|
| 5 | **工程师 A 上下文** | `docs/implementation/worker-aware-migration/ENGINEER-A-CONTEXT.md` | IR/Stage 专家（T0, T1, T1.5, T2 辅助） |
| 6 | **工程师 B 上下文** | `docs/implementation/worker-aware-migration/ENGINEER-B-CONTEXT.md` | Renderer 专家（T1.6, T3） |
| 7 | **工程师 C 上下文** | `docs/implementation/worker-aware-migration/ENGINEER-C-CONTEXT.md` | Resources 专家（T2, T3 辅助） |
| 8 | **工程师 B T1.6 准备** | `docs/implementation/worker-aware-migration/ENGINEER-B-T1.6-PREP.md` | T1.6 预备文档 |
| 9 | **工程师 C 交接** | `docs/implementation/worker-aware-migration/ENGINEER-C-HANDOFF.md` | T2 交接文档 |

### 3.3 任务文档（详细实现规格）

| 序号 | 文档 | 路径 | 说明 |
|------|------|------|------|
| 10 | **T0 任务文档** | `docs/implementation/worker-aware-migration/T0-ir-contract.md` | IR Contract 修正规格 |
| 11 | **T1 任务文档** | `docs/implementation/worker-aware-migration/T1-worker-scoped-step.md` | Stage 7 实现规格 |
| 12 | **T1.5 任务文档** | `docs/implementation/worker-aware-migration/T1.5-worker-aware-normalizer.md` | Stage 9.5 实现规格 |
| 13 | **T1.6 任务文档** | `docs/implementation/worker-aware-migration/T1.6-child-worker-flow.md` | Stage 10/11 实现规格 |
| 14 | **T2 任务文档** | `docs/implementation/worker-aware-migration/T2-scoped-resources-symboltable.md` | SymbolTable 实现规格 |
| 15 | **T3 任务文档** | `docs/implementation/worker-aware-migration/T3-remove-legacy-adapter.md` | Adapter 移除规格 |

**阅读建议**: 先读 1-4（核心文档），再根据需要读 5-7（上下文文档）。任务文档（10-15）在分配具体任务时才读。

---

## 4. 关键设计决策（D1-D10 Frozen）

以下决策已冻结，**不可修改**，所有开发必须遵守：

| # | 决策 | 结论 |
|---|------|------|
| D1 | INVOKE_WORKER 生成规则 | 从 `WorkerHandoffIR` 生成，不从 `WorkerBoundaryDecisionIR` 生成 |
| D2 | INVOKE_WORKER source_span_ids | 优先使用 `invoke_location_hint`；缺失时返回空并 warning，不 fallback |
| D3 | ChildWorkerIR 升级 | 增加 `main_flow` + `steps` + `alternative_flows` + `exception_flows` + `api_refs` |
| D4 | SymbolTable scope | 使用复合 key `(scope_kind, scope_id, name)` |
| D5 | span ownership violation | **error**，不是 warning |
| D6 | Phase 3 策略 | 保留 legacy adapter |
| D7 | Phase 3 时机 | T1.6 后可提前部分 T3 |
| D8 | Main worker accessor | `WorkerPlanIR` 增加 `main_worker` property |
| D9 | BlockIR.spans 语义 | 默认保存 source span ids；fallback 使用 `source_span_ids` |
| D10 | Handoff step shape 校验 | Stage 9.5 必须校验 handoff step 的完整形状 |

**如果开发者质疑这些决策**：请参考迁移方案文档中每个决策的"理由"列。

---

## 5. 代码结构

### 5.1 已修改文件（T0, T1, T1.5 完成）

| 文件 | 修改内容 | 任务 |
|------|----------|------|
| `src/nl2spl/ir/worker_plan_ir.py` | 新增 `WorkerStepPlanIR` | T0 |
| `src/nl2spl/ir/worker_ir.py` | 升级 `ChildWorkerIR`（新增 main_flow, steps 等） | T0 |
| `src/nl2spl/pipeline/stages/stage7_step_extractor/worker_scoped.py` | 新增 worker-scoped 方法 | T1 |
| `src/nl2spl/pipeline/stages/stage7_step_extractor/extractor.py` | 整合 mixin | T1 |
| `src/nl2spl/pipeline/stages/stage7_step_extractor/legacy.py` | legacy 逻辑（保留） | T1 |
| `src/nl2spl/pipeline/stages/stage9_5_normalizer/worker_scoped.py` | 新增 worker-scoped 校验 | T1.5 |
| `src/nl2spl/pipeline/orchestrator.py` | 新增 worker-aware 调用路径 | T1, T1.5 |

### 5.2 正在修改的文件（T2 进行中）

| 文件 | 修改内容 | 任务 |
|------|----------|------|
| `src/nl2spl/ir/symbol_table.py` | 支持 worker scope（D4） | T2 |
| `src/nl2spl/ir/resource_registry_ir.py` | 新增 `WorkerScopedResourceIR` | T2 |
| `src/nl2spl/pipeline/stages/stage6_resource_extractor/` | 新增 worker-scoped 方法 | T2 |

### 5.3 待修改文件

| 文件 | 修改内容 | 任务 |
|------|----------|------|
| `src/nl2spl/pipeline/stages/stage10_worker_assembler.py` | 新增 worker-aware 方法 | T1.6 |
| `src/nl2spl/pipeline/stages/stage11_spl_renderer.py` | 修改 child worker 渲染 | T1.6 |

### 5.4 Mixin 模式说明

Stage 7 和 Stage 9.5 都采用了 **mixin 模式**：

```
stage7_step_extractor/
├── __init__.py        # 只导出 StepExtractor
├── extractor.py       # 主类（继承 mixin）
├── legacy.py          # LegacyMethodsMixin（旧版逻辑）
└── worker_scoped.py   # WorkerScopedMethodsMixin（新增逻辑）
```

**优点**：
- 新增逻辑和旧版逻辑完全隔离
- 不影响 legacy path
- 通过配置开关 `enable_worker_boundary_planner` 选择路径

---

## 6. 测试状态

### 6.1 测试文件总览

| 测试文件 | 测试数量 | 说明 |
|----------|----------|------|
| `tests/unit/ir/test_worker_step_plan_ir.py` | 9 | WorkerStepPlanIR 测试 |
| `tests/unit/pipeline/stages/test_worker_handoff_step_extraction.py` | 4 | Stage 7 handoff 测试 |
| `tests/unit/pipeline/stages/test_stage6_worker_scoped.py` | 多个 | Stage 6 测试（T2 进行中） |
| `tests/unit/pipeline/stages/test_worker_plan_normalizer.py` | 多个 | Stage 9.5 测试 |
| 其他现有测试 | ~350 | 保持向后兼容 |

### 6.2 运行测试命令

```bash
# 运行所有测试
python -m pytest tests/unit/ -v --tb=short

# 运行特定测试
python -m pytest tests/unit/ir/test_worker_step_plan_ir.py -v
python -m pytest tests/unit/pipeline/stages/test_worker_handoff_step_extraction.py -v
```

### 6.3 测试覆盖要求

- 新增代码：100% 覆盖率
- 修改代码：90% 覆盖率
- 每个 PR 必须运行完整测试套件并全部通过

---

## 7. 当前实现详情

### 7.1 T0: IR Contract 修正（✅ 完成）

**新增类**:
- `WorkerStepPlanIR` - worker-scoped 步骤提取结果
- `ChildWorkerIR` 升级 - 新增 main_flow/steps 等字段

**测试**: 9 个，全部通过

### 7.2 T1: WorkerScopedStepIR + Stage 7（✅ 完成）

**新增方法**（在 `WorkerScopedMethodsMixin` 中）:
- `execute_worker_scoped()` - 按 worker 独立提取步骤
- `_extract_steps_for_worker()` - 为单个 worker 提取步骤
- `_generate_handoff_steps()` - 从 handoffs 生成步骤（D1）
- `_build_invoke_step()` - 构建 INVOKE_WORKER 步骤
- `_build_api_call_step()` - 构建 CALL_API 步骤
- `_get_invoke_source_spans()` - 获取 source spans（D2）
- `_validate_step_span_ownership()` - 验证 span ownership（D5）

**Orchestrator 修改**: 新增 worker-aware 调用路径，保留 legacy path

**测试**: 4 个，全部通过

### 7.3 T1.5: Worker-aware Stage 9.5（✅ 完成）

**新增方法**（在 worker_scoped 中）:
- `normalize_worker_scoped()` - worker-scoped IR 校验
- `_validate_span_ownership()` - 验证 span ownership（D5）
- `_validate_handoffs()` - 验证 handoff completeness
- `_validate_output_binding()` - 验证 child output binding
- `_validate_reachability()` - 验证 producer/consumer reachability
- `_validate_handoff_types()` - 验证 handoff 类型

**Orchestrator 修改**: 新增 worker-aware 调用路径

**关键行为**:
- span ownership violation 抛出 error（D5）
- 其他校验问题记录为 error/warning

### 7.4 T2: WorkerScopedResourceIR + SymbolTable（⏳ 进行中 - 工程师 C）

**当前进度**: 测试文件已存在（`test_stage6_worker_scoped.py`），部分实现已开始

**关键点**: 工程师 C 负责 SymbolTable scope 实现，工程师 A 辅助设计

### 7.5 T1.6: WorkerIR/Renderer child-flow support（⏳ 准备中 - 工程师 B）

**当前进度**: 工程师 B 正在准备，前置任务 T1.5 已完成

---

## 8. 下一步计划

### 8.1 执行顺序

```
T2（进行中，工程师 C）
  ↓
T3 部分（可提前，工程师 B）
  ↓
T1.6（工程师 B 可开始）
  ↓
T3 完全（工程师 B + 工程师 C）
```

### 8.2 当前可以立即启动的任务

1. **T1.6**: 工程师 B 可以开始，因为 T1.5 已完成
2. **T3 部分**: 工程师 B 可以在 T1.6 后开始

### 8.3 当前阻塞的任务

- **T3 完全**: 依赖 T2 完成

### 8.4 推荐下周计划

| 日期 | 工程师 A | 工程师 B | 工程师 C |
|------|----------|----------|----------|
| 第 10-13 天 | T2 辅助（SymbolTable 设计） | T1.6 开始（Renderer） | T2 继续（ResourceIR） |
| 第 14-18 天 | T2 辅助（SymbolTable 实现） | T3 部分（去 adapter） | T2 完成（Stage 6） |
| 第 19-20 天 | 代码审查 | T3 完成 | 集成测试 |

---

## 9. 风险与缓解

| 风险 | 影响 | 责任人 | 缓解措施 |
|------|------|--------|----------|
| T2 SymbolTable 改动影响面大 | 高 | 工程师 C | 保留旧接口兼容性 |
| T1.6 影响 Stage 11 渲染 | 高 | 工程师 B | 单独验证渲染 |
| 测试覆盖不足 | 高 | 所有人 | 每个任务完成后运行完整测试 |
| 工程师 A 转接 | 中 | 新 PM | 本文档作为交接指南 |

---

## 10. 开发规范速查

### 10.1 代码规范
- 遵循项目现有代码风格
- 使用 mixin 模式分离新旧逻辑
- 所有新增代码必须有类型注解
- 禁止使用 `as any` 或 `@ts-ignore`

### 10.2 提交规范
- 分支命名：`feature/worker-aware-{task_id}`
- PR 标题格式：`[T{task_id}] {描述}`

### 10.3 配置开关
```python
# config.py
enable_worker_boundary_planner: bool = False  # 控制是否使用 worker-aware 路径
```

### 10.4 沟通机制
- **每日站会**：每天 10:00（15 分钟）
- **即时沟通**：Slack/Teams 频道 `#worker-aware-migration`

---

## 11. 常见问题（接任工程师须知）

### Q1: 如果测试失败怎么办？
1. 确认是否只运行了新测试还是全部测试
2. 检查是否修改了 legacy path 的代码
3. 运行 `python -m pytest tests/unit/ -v --tb=long` 查看详细错误
4. 如果 legacy test 失败，可能是 backward compatibility 问题

### Q2: 如何判断使用 worker-aware path 还是 legacy path？
```python
if (self.config.enable_worker_boundary_planner
    and worker_flow_plan is not None
    and worker_block_plan is not None
    and worker_plan is not None):
    # Worker-aware path
else:
    # Legacy path
```

### Q3: Span ownership violation 是 error 还是 warning？
**error**（D5 决策）。非 handoff 步骤引用非 owned span 会抛出 `StageError`。

### Q4: INVOKE_WORKER step 的 source_span_ids 从哪里来？
优先从 `invoke_location_hint`，没有 hint 时返回空列表（D2 决策）。

### Q5: 如何找到某个变量是哪个 worker 的？
在 Phase 2（T2）完成后，使用 `symbol_table.get_variables_for_worker(worker_id)`。

---

## 12. 附录

### 12.1 所有文档完整路径

```
docs/implementation/worker-aware-migration/
├── README.md                           # 任务总览
├── TEAM-ASSIGNMENT.md                  # 团队分配方案
├── TASK-ASSIGNMENT.md                  # 任务分配矩阵
├── ENGINEER-A-CONTEXT.md               # 工程师 A 上下文文档
├── ENGINEER-B-CONTEXT.md               # 工程师 B 上下文文档
├── ENGINEER-B-T1.6-PREP.md             # 工程师 B T1.6 准备文档
├── ENGINEER-C-CONTEXT.md               # 工程师 C 上下文文档
├── ENGINEER-C-HANDOFF.md               # 工程师 C 交接文档
├── T0-ir-contract.md                   # T0 任务文档
├── T1-worker-scoped-step.md            # T1 任务文档
├── T1.5-worker-aware-normalizer.md     # T1.5 任务文档
├── T1.6-child-worker-flow.md           # T1.6 任务文档
├── T2-scoped-resources-symboltable.md  # T2 任务文档
└── T3-remove-legacy-adapter.md         # T3 任务文档

docs/migration-worker-aware-pipeline.md  # 主迁移方案
```

### 12.2 所有代码文件完整路径

```
src/nl2spl/ir/
├── worker_plan_ir.py            # WorkerPlanIR, WorkerStepPlanIR, WorkerHandoffIR
├── worker_ir.py                 # WorkerIR, ChildWorkerIR
├── symbol_table.py              # SymbolTable, VariableSymbol
├── resource_registry_ir.py      # ResourceRegistryIR, WorkerScopedResourceIR
├── flow_structure_ir.py         # FlowStructureIR, DelegationCandidate
├── block_structure_ir.py        # BlockStructureIR, BlockIR
└── step_ir.py                   # StepIR

src/nl2spl/pipeline/
├── orchestrator.py              # Pipeline 编排器
├── worker_plan_adapter.py       # Legacy adapter（保留）
└── stages/
    ├── stage7_step_extractor/   # Stage 7（已迁移）
    │   ├── __init__.py
    │   ├── extractor.py         # 主类
    │   ├── legacy.py            # 旧版逻辑
    │   └── worker_scoped.py     # 新版逻辑
    ├── stage9_5_normalizer/     # Stage 9.5（已迁移）
    │   ├── __init__.py
    │   ├── normalizer.py        # 主类
    │   └── worker_scoped.py     # 新版逻辑
    ├── stage6_resource_extractor/ # Stage 6（进行中）
    ├── stage10_worker_assembler.py   # Stage 10（待迁移）
    └── stage11_spl_renderer.py       # Stage 11（待迁移）
```

### 12.3 联系方式

- **原 PM（Sisyphus）**: 本文档创建者
- **工程师 A**: IR/Stage 专家 - T0, T1, T1.5, T2 辅助
- **工程师 B**: Renderer 专家 - T1.6, T3
- **工程师 C**: Resources 专家 - T2, T3 辅助

---

**文档结束**

*建议接任工程师从阅读「必读文档清单」中的文档 1-4 开始，然后根据分配的任务阅读对应的上下文文档和任务文档。*
