# 任务分配方案

**项目**: nl2spl Worker-Aware Pipeline Migration  
**创建日期**: 2026-05-12  
**项目经理**: Sisyphus  
**团队规模**: 3 人  
**预估总时间**: 12-15 天（2.5-3 周）

---

## 1. 团队配置

### 工程师 A（IR/Stage 专家）
**技能要求**：
- 熟悉 IR 数据结构设计
- 熟悉 Stage 7/9.5 实现
- 熟悉 LLM prompt 设计
- 熟悉校验逻辑

**负责任务**：T0 → T1 → T1.5 → T2 辅助

### 工程师 B（Renderer 专家）
**技能要求**：
- 熟悉 Stage 10/11 实现
- 熟悉 WorkerIR/ChildWorkerIR
- 熟悉 SPL 渲染逻辑
- 熆悉集成测试

**负责任务**：等待 → T1.6 → T3

### 工程师 C（Resources 专家）
**技能要求**：
- 熟悉 SymbolTable 实现
- 熟悉 ResourceRegistryIR
- 熟悉 Stage 6 实现
- 熟悉 scope 管理

**负责任务**：等待 → T2 → T3 辅助

---

## 2. 时间线

### 第一阶段：设计冻结（第 1 天）

| 工程师 | 任务 | 交付物 |
|--------|------|--------|
| A | T0: IR Contract 修正 | WorkerStepPlanIR, ChildWorkerIR 设计 |
| B | 评审 T0 设计 | 评审意见 |
| C | 评审 T0 设计 | 评审意见 |

**里程碑 M0**：IR contract 冻结

### 第二阶段：Stage 7 实现（第 2-6 天）

| 工程师 | 任务 | 交付物 |
|--------|------|--------|
| A | T1: WorkerScopedStepIR + Stage 7 | Stage 7 worker-aware 实现 |
| B | 准备 T1.6 环境 | 理解 ChildWorkerIR 需求 |
| C | 准备 T2 环境 | 理解 SymbolTable scope 需求 |

**里程碑 M1**：Stage 7 worker-aware 完成

### 第三阶段：Normalizer 实现（第 7-9 天）

| 工程师 | 任务 | 交付物 |
|--------|------|--------|
| A | T1.5: Worker-aware Stage 9.5 | Stage 9.5 worker-aware 实现 |
| B | 准备 T1.6 实现 | ChildWorkerIR 设计评审 |
| C | 准备 T2 实现 | SymbolTable scope 设计评审 |

**里程碑 M2**：Stage 9.5 worker-aware 完成

### 第四阶段：Renderer 实现（第 10-13 天）- 并行

| 工程师 | 任务 | 交付物 |
|--------|------|--------|
| A | T2 辅助：SymbolTable scope 设计 | SymbolTable 设计文档 |
| B | T1.6: WorkerIR/Renderer child-flow support | Stage 10/11 worker-aware 实现 |
| C | T2 开始：WorkerScopedResourceIR | WorkerScopedResourceIR 实现 |

**里程碑 M3**：Stage 10/11 worker-aware 完成

### 第五阶段：Resources 实现（第 14-18 天）- 并行

| 工程师 | 任务 | 交付物 |
|--------|------|--------|
| A | T2 辅助：SymbolTable 实现 | SymbolTable scoped 实现 |
| B | T3 部分：worker-aware path 去 adapter | Orchestrator 修改 |
| C | T2 完成：Stage 6 worker-aware | Stage 6 worker-aware 实现 |

**里程碑 M4**：Stage 6 worker-aware 完成

### 第六阶段：收尾（第 19-20 天）

| 工程师 | 任务 | 交付物 |
|--------|------|--------|
| A | 代码审查和测试 | 审查报告 |
| B | T3 完成：adapter 移除 | 最终代码 |
| C | T3 辅助：集成测试 | 测试报告 |

**里程碑 M5**：迁移完成

---

## 3. 详细分配

### 工程师 A 的任务流

```
第 1 天：T0 - IR Contract 修正
├── 修正 WorkerStepPlanIR
├── 升级 ChildWorkerIR（设计）
├── 设计 SymbolTable scope 方案
└── 记录设计决策 D1-D7

第 2-6 天：T1 - WorkerScopedStepIR + Stage 7
├── 实现 execute_worker_scoped()
├── 实现 _generate_handoff_steps()
├── 实现 _build_invoke_step()
├── 实现 _get_invoke_source_spans()
├── 实现 _validate_step_span_ownership()
├── 修改 Orchestrator
├── 编写测试
└── 运行回归测试

第 7-9 天：T1.5 - Worker-aware Stage 9.5
├── 实现 normalize_worker_scoped()
├── 实现 _validate_span_ownership()
├── 实现 _validate_handoffs()
├── 实现 _validate_output_binding()
├── 实现 _validate_reachability()
├── 实现 _validate_handoff_types()
├── 修改 Orchestrator
├── 编写测试
└── 运行回归测试

第 10-13 天：T2 辅助 - SymbolTable scope 设计
├── 设计 VariableSymbol scope 字段
├── 设计 SymbolTable scoped 方法
└── 评审工程师 C 的实现

第 14-18 天：T2 辅助 - SymbolTable 实现
├── 实现 declare_scoped()
├── 实现 get_variables_for_worker()
├── 实现 get_variables_for_handoff()
├── 实现 get_all_declared_variables()
└── 编写测试

第 19-20 天：代码审查和测试
├── 审查所有 PR
├── 运行完整测试套件
└── 撰写测试报告
```

### 工程师 B 的任务流

```
第 1-9 天：准备阶段
├── 评审 T0 设计
├── 理解 ChildWorkerIR 需求
├── 理解 Stage 10/11 实现
├── 准备测试环境
└── 编写测试用例

第 10-13 天：T1.6 - WorkerIR/Renderer child-flow support
├── 升级 ChildWorkerIR（实现）
├── 实现 assemble_from_worker_scoped()
├── 实现 _build_child_worker()
├── 修改 _render_child_worker()
├── 实现 _render_block()
├── 实现 _render_step()
├── 修改 Orchestrator
├── 编写测试
└── 运行回归测试

第 14-18 天：T3 部分 - worker-aware path 去 adapter
├── 修改 Stage 4 调用
├── 修改 Stage 5 调用
├── 确认 Stage 6/7/9.5/10 使用正确 path
├── 运行完整测试套件
└── 条件性删除 legacy adapter

第 19-20 天：T3 完成和收尾
├── 完成 T3 所有工作
├── 运行完整测试套件
├── 代码审查
└── 撰写交付报告
```

### 工程师 C 的任务流

```
第 1-9 天：准备阶段
├── 评审 T0 设计
├── 理解 SymbolTable scope 需求
├── 理解 ResourceRegistryIR 结构
├── 理解 Stage 6 实现
├── 准备测试环境
└── 编写测试用例

第 10-13 天：T2 开始 - WorkerScopedResourceIR
├── 实现 WorkerScopedResourceIR
├── 实现 HandoffContractIR
├── 设计 SymbolTable scope 接口
├── 编写测试
└── 评审工程师 A 的 SymbolTable 设计

第 14-18 天：T2 完成 - Stage 6 worker-aware
├── 修改 VariableSymbol（新增 scope 字段）
├── 实现 execute_worker_scoped()
├── 实现 _extract_resources_for_scope()
├── 实现 _build_handoff_contract()
├── 修改 Orchestrator
├── 编写测试
└── 运行回归测试

第 19-20 天：集成测试和收尾
├── 运行完整集成测试
├── 修复集成问题
├── 代码审查
└── 撰写测试报告
```

---

## 4. 并行执行点

### 可并行的任务

| 时间段 | 工程师 A | 工程师 B | 工程师 C |
|--------|----------|----------|----------|
| 第 10-13 天 | T2 辅助（SymbolTable 设计） | T1.6（Renderer） | T2 开始（ResourceIR） |
| 第 14-18 天 | T2 辅助（SymbolTable 实现） | T3 部分（去 adapter） | T2 完成（Stage 6） |

### 依赖关系处理

```
T0 (A) → T1 (A) → T1.5 (A) → T1.6 (B) → T3 部分 (B)
                    ↓
              T2 辅助 (A) → T2 (C) → T3 完成 (B+C)
```

---

## 5. 风险分配

| 风险 | 影响 | 责任人 | 缓解措施 |
|------|------|--------|----------|
| T1 改动 Stage 7 核心逻辑 | 高 | 工程师 A | 保留 legacy path |
| T1.6 影响 Stage 11 渲染 | 高 | 工程师 B | 单独验证渲染 |
| T2 SymbolTable 改动影响面大 | 中 | 工程师 C | 渐进式迁移 |
| 测试覆盖不足 | 高 | 所有人 | 每个任务完成后运行完整测试 |
| 接口不清晰 | 中 | 所有人 | 每日站会沟通 |

---

## 6. 沟通机制

### 每日站会
- **时间**：每天 10:00（15 分钟）
- **参与者**：工程师 A、B、C
- **内容**：
  - 昨日进展（每人 2 分钟）
  - 今日计划（每人 1 分钟）
  - 阻塞项（如有）

### 周会
- **时间**：每周五 15:00（1 小时）
- **参与者**：项目经理 + 工程师 A、B、C
- **内容**：
  - 周总结（15 分钟）
  - 下周计划（15 分钟）
  - 风险 review（15 分钟）
  - 技术讨论（15 分钟）

### 代码审查
- **常规任务**：至少两人审查
- **关键任务**（T1, T1.6, T2）：三人审查
- **审查时间**：PR 提交后 24 小时内完成

### 即时沟通
- **工具**：Slack/Teams
- **频道**：#worker-aware-migration
- **响应时间**：工作时间内 2 小时

---

## 7. 交付标准

### 代码交付标准
- 所有测试通过
- 无类型错误
- 无 lint 错误
- 测试覆盖率达标（新增代码 100%，修改代码 90%）
- 代码审查通过

### 文档交付标准
- 任务文档已更新
- 设计决策已记录
- API 文档已更新

### 测试交付标准
- 单元测试通过
- 集成测试通过
- 回归测试通过
- 性能测试通过（如有）

---

## 8. 里程碑和检查点

| 里程碑 | 日期 | 交付物 | 检查点 |
|--------|------|--------|--------|
| M0: 设计冻结 | 第 1 天 | T0 完成，IR contract 冻结 | 设计评审会 |
| M1: Stage 7 完成 | 第 6 天 | T1 完成，Stage 7 worker-aware | 代码审查 + 测试 |
| M2: Normalizer 完成 | 第 9 天 | T1.5 完成，Stage 9.5 worker-aware | 代码审查 + 测试 |
| M3: Renderer 完成 | 第 13 天 | T1.6 完成，Stage 10/11 worker-aware | 代码审查 + 测试 |
| M4: Resources 完成 | 第 18 天 | T2 完成，Stage 6 worker-aware | 代码审查 + 测试 |
| M5: 迁移完成 | 第 20 天 | T3 完成，adapter 移除 | 完整测试 + 评审 |

---

## 9. 应急计划

### 如果任务延期

| 情况 | 影响 | 应急措施 |
|------|------|----------|
| T1 延期 2 天 | M1 延期 | 工程师 B/C 协助测试 |
| T1.5 延期 1 天 | M2 延期 | 压缩 T1.6 准备时间 |
| T1.6 延期 2 天 | M3 延期 | 工程师 A 协助实现 |
| T2 延期 3 天 | M4 延期 | 增加工程师 B 协助 |
| T3 延期 2 天 | M5 延期 | 增加工程师 A/C 协助 |

### 如果人员变动

| 情况 | 影响 | 应急措施 |
|------|------|----------|
| 工程师 A 离开 | T0/T1/T1.5 延期 | 工程师 B 接管 T1.5，工程师 C 接管 T0/T1 |
| 工程师 B 离开 | T1.6/T3 延期 | 工程师 A 接管 T1.6，工程师 C 接管 T3 |
| 工程师 C 离开 | T2 延期 | 工程师 A 接管 T2，工程师 B 协助 |

---

## 10. 成功标准

### 项目成功标准
- 所有任务在 20 天内完成
- 所有测试通过
- 无回归问题
- 代码质量达标

### 团队成功标准
- 每日站会参与率 100%
- 代码审查及时完成
- 文档及时更新
- 沟通顺畅

---

## 11. 附录

### 任务文档链接
- [T0: IR Contract 修正](T0-ir-contract.md)
- [T1: WorkerScopedStepIR + Stage 7](T1-worker-scoped-step.md)
- [T1.5: Worker-aware Stage 9.5](T1.5-worker-aware-normalizer.md)
- [T1.6: WorkerIR/Renderer child-flow support](T1.6-child-worker-flow.md)
- [T2: WorkerScopedResourceIR + SymbolTable](T2-scoped-resources-symboltable.md)
- [T3: worker-aware path 去 adapter](T3-remove-legacy-adapter.md)

### 工程师上下文文档
- [工程师 A 上下文文档](ENGINEER-A-CONTEXT.md) - IR/Stage 专家
- [工程师 B 上下文文档](ENGINEER-B-CONTEXT.md) - Renderer 专家
- [工程师 C 上下文文档](ENGINEER-C-CONTEXT.md) - Resources 专家

### 相关文档
- [迁移方案 v3.0](../../migration-worker-aware-pipeline.md)
- [任务总览](README.md)
