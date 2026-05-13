# 项目进度追踪：Worker-Aware Pipeline 迁移

**文档类型**: 实时进度追踪  
**创建日期**: 2026-05-13  
**当前 PM**: 6chenhua（接替 Sisyphus）  
**最后更新**: 2026-05-13

---

## 1. 整体进度仪表盘

| 里程碑 | 目标日期 | 状态 | 完成日期 |
|--------|----------|------|----------|
| M0: 设计冻结 | 第 1 天 | ✅ 完成 | 第 1 天 |
| M1: Stage 7 完成 | 第 6 天 | ✅ 完成 | 第 5 天 |
| M2: Normalizer 完成 | 第 9 天 | ✅ 完成 | 第 9 天 |
| M3: Renderer 完成 | 第 13 天 | 🔄 进行中（提前启动） | - |
| M4: Resources 完成 | 第 18 天 | 🔄 进行中 | - |
| M5: 迁移完成 | 第 20 天 | 🔲 待启动 | - |

**整体进度**: 约 50%（3/6 里程碑完成，2 个进行中）

---

## 2. 任务级进度

### T0: IR Contract 修正 ✅

| 项 | 内容 |
|----|------|
| **状态** | ✅ 完成 |
| **负责人** | 工程师 A |
| **完成日期** | 第 1 天 |
| **交付物** | WorkerStepPlanIR、ChildWorkerIR 升级（新增 main_flow/steps/alternative_flows/exception_flows/api_refs）、WorkerPlanIR.main_worker property |
| **测试** | 9 个，全部通过 |
| **代码文件** | `src/nl2spl/ir/worker_plan_ir.py` (+53行), `src/nl2spl/ir/worker_ir.py` (+13行), `src/nl2spl/ir/__init__.py` (+6行) |

### T1: WorkerScopedStepIR + Stage 7 ✅

| 项 | 内容 |
|----|------|
| **状态** | ✅ 完成 |
| **负责人** | 工程师 A |
| **完成日期** | 第 5 天 |
| **交付物** | Mixin 模式 Stage 7（extractor/legacy/worker_scoped），worker-aware step extraction 完整流程 |
| **测试** | 4 个 handoff 测试 + 238 行测试代码，全部通过 |
| **代码文件** | `stage7_step_extractor/` 目录（4 文件），`orchestrator.py`（新增 worker-aware 调用路径） |

核心方法（已实现）：
- `execute_worker_scoped()` — 按 worker 独立提取步骤
- `_extract_steps_for_worker()` — 为单个 worker 提取步骤
- `_generate_handoff_steps()` — 从 handoffs 生成步骤（D1）
- `_build_invoke_step()` — 构建 INVOKE_WORKER 步骤
- `_build_api_call_step()` — 构建 CALL_API 步骤
- `_get_invoke_source_spans()` — 获取 source spans（D2）
- `_validate_step_span_ownership()` — 验证 span ownership（D5）

### T1.0.5: Worker-aware Prompt 整合 ✅

| 项 | 内容 |
|----|------|
| **状态** | ✅ 完成 |
| **负责人** | 工程师 A |
| **完成日期** | 第 5 天 |
| **交付物** | Worker-aware prompts 整合到 Stage 7/9.5 |
| **代码文件** | `prompts/stage3_5_system.txt`（修改） |

### T1.5: Worker-aware Stage 9.5 ✅

| 项 | 内容 |
|----|------|
| **状态** | ✅ 完成 |
| **负责人** | 工程师 A |
| **完成日期** | 第 9 天 |
| **交付物** | Mixin 模式 Stage 9.5（normalizer/worker_scoped + helpers），完整 worker-scoped 校验 |
| **测试** | 全部通过 |
| **代码文件** | `stage9_5_normalizer/` 目录（8 文件），`orchestrator.py`（新增 worker-aware 调用路径） |

核心方法（已实现）：
- `normalize_worker_scoped()` — worker-scoped IR 校验
- `_validate_span_ownership()` — 验证 span ownership（D5: error）
- `_validate_handoffs()` — 验证 handoff completeness
- `_validate_output_binding()` — 验证 child output binding
- `_validate_reachability()` — 验证 producer/consumer reachability
- `_validate_handoff_types()` — 验证 handoff 类型

---

### T1.6: WorkerIR/Renderer child-flow support 🔄

| 项 | 内容 |
|----|------|
| **状态** | 🔄 进行中 |
| **负责人** | 工程师 B |
| **开始日期** | 约第 10 天 |
| **预估剩余** | 2-3 天 |

#### 已完成部分

| 子任务 | 状态 | 说明 |
|--------|------|------|
| Stage 10 `assemble_from_worker_scoped()` | ✅ 已实现 | 完整实现，约 190 行新代码 |
| Stage 10 `_build_child_worker()` | ✅ 已实现 | 构建带完整 flow/steps 的 ChildWorkerIR |
| Stage 11 `_render_child_worker()` 升级 | ✅ 已实现 | 支持 main_flow.blocks、alternative_flows、exception_flows |
| Stage 11 `__init__()` 状态初始化 | ✅ 已实现 | 新增 command_index、decision_index 等状态 |
| Orchestrator `_run_stage10_worker_scoped()` | ✅ 已实现 | Worker-aware 路径集成 |
| Orchestrator `_run_stage11` worker-aware 参数 | 🔲 未实现 | Stage 11 仍然走统一路径（待确认是否需要独立 worker-aware 路径） |

#### 待完成部分

| 子任务 | 优先级 | 说明 |
|--------|--------|------|
| 编写 T1.6 单元测试 | 🔴 高 | 测试 assemble_from_worker_scoped 和 _build_child_worker |
| WorkerIR 升级验证 | 🔴 高 | 确认 ChildWorkerIR 新字段（main_flow/steps/alternative_flows/exception_flows/api_refs）完全可用 |
| 端到端验证：child worker 渲染 | 🔴 高 | 使用 enterprise-procedure 用例验证 child worker 正确渲染 |
| 回归测试 | 🟡 中 | 确保 Stage 10/11 legacy path 不受影响 |
| Orchestrator Stage 11 worker-aware path（如需） | 🟢 低 | Stage 11 可能不需要独立 worker-aware 路径，因为 WorkerIR 已经包含 child workers |

---

### T2: WorkerScopedResourceIR + SymbolTable 🔄

| 项 | 内容 |
|----|------|
| **状态** | 🔄 进行中 |
| **负责人** | 工程师 C |
| **开始日期** | 约第 10 天 |
| **预估剩余** | 3-5 天 |

#### 已完成部分

| 子任务 | 状态 | 说明 |
|--------|------|------|
| VariableSymbol scope 字段 | ✅ 已实现 | scope_kind (global/worker/handoff) + scope_id |
| SymbolTable 复合 key 存储 | ✅ 已实现 | `_variables: dict[tuple[str, str|None, str], VariableSymbol]` |
| `declare_scoped()` | ✅ 已实现 | 带 scope 参数的变量声明 |
| `get_variables_for_worker()` | ✅ 已实现 | 返回 global + worker-scoped 变量 |
| `get_variables_for_handoff()` | ✅ 已实现 | 返回 global + handoff-scoped 变量 |
| `get_variable_list_for_worker_prompt()` | ✅ 已实现 | 生成 worker LLM prompt 的变量列表 |
| WorkerScopedResourceIR | ✅ 已实现 | 全局/worker/handoff 三级资源存储 |
| Stage 6 `execute_worker_scoped()` | ✅ 已实现 | 约 350 行新代码，完整 worker-scoped 提取流程 |
| Stage 6 `_extract_resources_for_scope()` | ✅ 已实现 | 单个 scope 的资源提取 |
| Stage 6 `_build_handoff_contract()` | 🔲 待验证 | diff 中未完全展示，需确认完整性 |
| Orchestrator `_run_stage6_worker_scoped()` | ✅ 已实现 | Worker-aware 路径集成 |

#### 待完成部分

| 子任务 | 优先级 | 说明 |
|--------|--------|------|
| `_build_handoff_contract()` 完成 | 🔴 高 | 需确认实现完整性 |
| 补充 Stage 6 测试用例 | 🔴 高 | `test_stage6_worker_scoped.py` 已创建（342行），需确认测试覆盖 |
| SymbolTable 测试完善 | 🔴 高 | `test_symbol_table_scope.py` 已创建（351行），需确认覆盖所有新方法 |
| `get_all_declared_variables()` | 🟡 中 | 工程师 A 任务列表中提到的方法，需确认是否已实现 |
| Worker-scoped LLM prompt 验证 | 🟡 中 | 确认 Stage 6 worker-scoped prompt 输出正确 |
| 回归测试 | 🟡 中 | 确保 legacy path 不受影响 |

---

### T3: worker-aware path 去 adapter 🔲

| 项 | 内容 |
|----|------|
| **状态** | 🔲 待启动 |
| **负责人** | 工程师 B + 工程师 C |
| **前置依赖** | T1.6 完成（部分），T2 完成（完全） |
| **预估时间** | 2-3 天 |

#### 可提前启动的子任务（T1.6 完成后）

| 子任务 | 负责人 | 说明 |
|--------|--------|------|
| 确认所有 Stage 使用正确 path | 工程师 B | 审计 orchestrator 中所有 6 个 stage 的路径选择 |
| 验证 legacy adapter 可移除 | 工程师 B | 确认 worker-aware path 完全覆盖 legacy 功能 |
| 运行完整回归测试 | 工程师 C | 确保切换后全部测试通过 |

#### 依赖 T2 完成的子任务

| 子任务 | 负责人 | 说明 |
|--------|--------|------|
| Stage 6 worker-aware 切换 | 工程师 C | 移除 Stage 6 legacy path |
| 条件性删除 legacy adapter | 工程师 B | 保留代码但不调用（D6: 保留 legacy adapter） |
| 端到端集成测试 | 工程师 B+C | 多 worker 完整场景验证 |

---

## 3. 代码变更统计（未提交工作区）

| 文件 | 变更行数 | 关联任务 | 说明 |
|------|----------|----------|------|
| `worker_plan_ir.py` | +53 | T0 | WorkerStepPlanIR |
| `worker_ir.py` | +13 | T0 | ChildWorkerIR 升级 |
| `symbol_table.py` | +166/-0 | T2 | Scoped 存储和方法 |
| `resource_registry_ir.py` | +46 | T2 | WorkerScopedResourceIR |
| `stage6_resource_extractor.py` | +354 | T2 | Worker-scoped 提取 |
| `stage7_step_extractor/` | 目录重构 | T1 | Mixin 模式 |
| `stage9_5_normalizer/` | 目录重构 | T1.5 | Mixin 模式 |
| `stage10_worker_assembler.py` | +193 | T1.6 | assemble_from_worker_scoped |
| `stage11_spl_renderer.py` | +71 | T1.6 | Child worker full-flow 渲染 |
| `orchestrator.py` | +178/-0 | T1/T1.5/T1.6/T2 | Worker-aware 调用路径 |
| `worker_plan_validator.py` | +84 | T1.5 | 增强校验 |

**总计**: 29 文件，+2191/-2370 行

---

## 4. 测试状态

```
371 passed in 4.38s — 全部通过，无回归
```

| 测试文件 | 行数 | 关联任务 | 状态 |
|----------|------|----------|------|
| `test_worker_step_plan_ir.py` | 134 | T0 | ✅ 9 个测试通过 |
| `test_worker_handoff_step_extraction.py` | 238 | T1 | ✅ 4 个测试通过 |
| `test_symbol_table_scope.py` | 351 | T2 | ⏳ 已创建，待运行 |
| `test_stage6_worker_scoped.py` | 342 | T2 | ⏳ 已创建，待运行 |
| 其他现有测试 | ~350 | 回归 | ✅ 全部通过 |

---

## 5. 工程师任务分配（下一步）

### 工程师 A（IR/Stage 专家）

**已完成**: T0 ✅, T1 ✅, T1.0.5 ✅, T1.5 ✅

**接下来（优先级排序）**：

| 优先级 | 任务 | 预估时间 | 说明 |
|--------|------|----------|------|
| 🔴 P0 | T2 辅助：审查 SymbolTable 实现 | 0.5 天 | 审查 `declare_scoped()`、`get_variables_for_worker()` 等方法的正确性，确认 D4 复合 key 完全实现 |
| 🔴 P0 | 确认 `get_all_declared_variables()` 实现 | 0.5 天 | 如果尚未实现则立即实现 |
| 🟡 P1 | T1.6 辅助：审查 `_build_child_worker()` | 0.5 天 | 确认 ChildWorkerIR 构建逻辑正确 |
| 🟡 P1 | 代码审查：Stage 10/11 改动 | 0.5 天 | 审查 Stage 10 worker-scoped 和 Stage 11 渲染改动 |
| 🟢 P2 | T3 准备：审计全链路 worker-aware path | 1 天 | 确认所有 Stage 的 worker-aware 路径正确连接 |

### 工程师 B（Renderer 专家）

**已完成**: T0 设计评审

**接下来（优先级排序）**：

| 优先级 | 任务 | 预估时间 | 说明 |
|--------|------|----------|------|
| 🔴 P0 | 完成 `_build_child_worker()` 并编写测试 | 1 天 | diff 中方法实现被截断，需确认完整性并补测试 |
| 🔴 P0 | T1.6 测试：WorkerIR child-flow 渲染验证 | 1 天 | 使用 enterprise-procedure 用例验证 child worker 正确渲染 main_flow/alternative_flows/exception_flows |
| 🔴 P0 | 确认 ChildWorkerIR 新字段完全可用 | 0.5 天 | 验证 main_flow/steps/alternative_flows/exception_flows/api_refs |
| 🟡 P1 | 回归测试：Stage 10/11 legacy path | 0.5 天 | 确保 legacy path 不受影响 |
| 🟢 P2 | T3 (部分)：审计 orchestrator 路径选择 | 1 天 | 确认所有 stage 走正确的 worker-aware/legacy 路径 |

### 工程师 C（Resources 专家）

**已完成**: Stage 6 部分实现、SymbolTable 部分实现

**接下来（优先级排序）**：

| 优先级 | 任务 | 预估时间 | 说明 |
|--------|------|----------|------|
| 🔴 P0 | 完成 `_build_handoff_contract()` 实现 | 0.5 天 | 如果 diff 中未完全实现则完成 |
| 🔴 P0 | 完善 Stage 6 测试 | 1 天 | `test_stage6_worker_scoped.py` 已创建，补充关键测试用例 |
| 🔴 P0 | 完善 SymbolTable 测试 | 0.5 天 | `test_symbol_table_scope.py` 已创建，补充所有新方法测试 |
| 🟡 P1 | Stage 6 LLM prompt 验证 | 1 天 | 验证 worker-scoped prompt 正确提取每个 worker 的资源 |
| 🟡 P1 | HandoffContractIR 集成验证 | 0.5 天 | 验证 handoff contract 正确传递变量 |
| 🟢 P2 | 回归测试：Stage 6 legacy path | 0.5 天 | 确保 legacy ResourceExtractor 不受影响 |

---

## 6. 本周（第 13-18 天）推荐计划

| 日期 | 工程师 A | 工程师 B | 工程师 C |
|------|----------|----------|----------|
| 第 13 天 | 审查 SymbolTable 实现 | 完成 `_build_child_worker()` + 测试 | 完成 `_build_handoff_contract()` |
| 第 14 天 | 确认 `get_all_declared_variables()` | T1.6 测试：child worker 渲染 | 完善 Stage 6 测试 |
| 第 15 天 | T1.6 代码审查 | 回归测试 Stage 10/11 | 完善 SymbolTable 测试 |
| 第 16 天 | T3 准备：路径审计 | T3 (部分)：路径审计 | LLM prompt 验证 |
| 第 17 天 | 集成测试辅助 | T3 (部分)：adapter 移除准备 | 回归测试 Stage 6 |
| 第 18 天 | 代码审查收尾 | T3 继续 | 集成测试 |

---

## 7. 风险更新

| 风险 | 原级别 | 当前级别 | 说明 |
|------|--------|----------|------|
| T2 SymbolTable 改动影响面大 | 高 | 🟡 中 | 已实现向后兼容（self.variables 保留），legacy path 不受影响 |
| T1.6 影响 Stage 11 渲染 | 高 | 🟡 中 | 已实现但缺测试验证 |
| 测试覆盖不足 | 高 | 🔴 高 | T1.6 和 T2 的测试文件已创建但需确认覆盖充分 |
| 未提交代码量过大 | 新风险 | 🔴 高 | 29 文件未提交，建议本周内分批提交 |

---

## 8. 关键阻塞项

| 阻塞项 | 影响 | 解决方案 |
|--------|------|----------|
| T1.6 测试未完成 | 无法确认 Stage 10/11 正确性 | 工程师 B 本周完成测试 |
| T2 测试未完成 | 无法确认 SymbolTable scope 正确性 | 工程师 C 本周完成测试 |
| `_build_handoff_contract()` 未确认 | T2 可能不完整 | 工程师 C 本周确认并完成 |

---

*下次更新：每个任务完成后或每周五周会后*
