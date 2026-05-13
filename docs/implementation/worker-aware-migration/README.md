# Worker-Aware Pipeline 迁移 - 开发任务分解

**项目**: nl2spl Worker-Aware Pipeline Migration  
**创建日期**: 2026-05-12  
**项目经理**: Sisyphus  
**状态**: 待启动

---

## 项目概述

将 nl2spl pipeline 从 legacy adapter 模式迁移到全链路 worker-aware 模式。详见 [迁移方案 v3.0](../migration-worker-aware-pipeline.md)。

## 任务总览

| 任务 ID | 任务名称 | 负责人 | 预估时间 | 前置依赖 | 状态 | 任务文档 |
|---------|----------|--------|----------|----------|------|----------|
| T0 | IR Contract 修正 | 工程师 A | 1 天 | 无 | 待启动 | [T0-ir-contract.md](T0-ir-contract.md) |
| T1 | WorkerScopedStepIR + Stage 7 | 工程师 A | 3-5 天 | T0 | 待启动 | [T1-worker-scoped-step.md](T1-worker-scoped-step.md) |
| T1.5 | Worker-aware Stage 9.5 | 工程师 A | 2-3 天 | T1 | 待启动 | [T1.5-worker-aware-normalizer.md](T1.5-worker-aware-normalizer.md) |
| T1.6 | WorkerIR/Renderer child-flow support | 工程师 B | 2-4 天 | T1.5 | 待启动 | [T1.6-child-worker-flow.md](T1.6-child-worker-flow.md) |
| T2 | WorkerScopedResourceIR + SymbolTable | 工程师 C | 4-7 天 | T1.6 | 待启动 | [T2-scoped-resources-symboltable.md](T2-scoped-resources-symboltable.md) |
| T3 | worker-aware path 去 adapter | 工程师 B/C | 2-3 天 | T1.6 (部分), T2 (完全) | 待启动 | [T3-remove-legacy-adapter.md](T3-remove-legacy-adapter.md) |

**总预估时间**: 12-15 天（2.5-3 周）  
**详细分配**: [TEAM-ASSIGNMENT.md](TEAM-ASSIGNMENT.md)

---

## 依赖关系图

```
T0 (IR Contract)
  ↓
T1 (Stage 7)
  ↓
T1.5 (Stage 9.5)
  ↓
T1.6 (ChildWorkerIR + Renderer)
  ↓
┌─────────────────┬─────────────────┐
↓                 ↓                 ↓
T3 (部分)        T2 (Resources)    (可选)
  ↓                 ↓
  └────────┬────────┘
           ↓
        T3 (完全)
```

---

## 关键设计决策（Frozen）

在开始开发前，以下决策已冻结：

| # | 决策 | 结论 |
|---|------|------|
| D1 | INVOKE_WORKER 生成规则 | 从 `WorkerHandoffIR` 生成 |
| D2 | INVOKE_WORKER source_span_ids | 优先使用 `invoke_location_hint` |
| D3 | ChildWorkerIR 升级 | 增加 `main_flow` + `steps` 字段 |
| D4 | SymbolTable scope | 使用复合 key `(scope_kind, scope_id, name)` |
| D5 | span ownership violation | **error**，不是 warning |
| D6 | Phase 3 策略 | 保留 legacy adapter |
| D7 | Phase 3 时机 | T1.6 后可提前部分 T3 |

---

## 开发规范

### 代码规范
- 遵循项目现有代码风格
- 所有新增代码必须有类型注解
- 禁止使用 `as any` 或 `@ts-ignore`
- 每个 PR 必须通过 CI 检查

### 测试规范
- 新增代码必须有单元测试
- 关键路径必须有集成测试
- 测试覆盖率目标：新增代码 100%，修改代码 90%

### 提交规范
- 每个任务独立分支：`feature/worker-aware-{task_id}`
- PR 标题格式：`[T{task_id}] {描述}`
- 每个 PR 关联对应的 issue

### 代码审查
- 每个 PR 需要至少两人审查
- 必须通过所有测试
- 必须无类型错误

---

## 沟通机制

### 每日站会
- 时间：每天 10:00
- 内容：昨日进展、今日计划、阻塞项

### 周会
- 时间：每周五 15:00
- 内容：周总结、下周计划、风险 review

### 文档更新
- 每个任务完成后更新本文档状态
- 关键决策必须记录在案

---

## 风险管理

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| T1 改动 Stage 7 核心逻辑 | 高 | 保留 legacy path |
| T1.6 影响 Stage 11 渲染 | 高 | 单独验证渲染 |
| T2 SymbolTable 改动影响面大 | 中 | 渐进式迁移 |
| 测试覆盖不足 | 高 | 每个任务完成后运行完整测试 |

---

## 附录

### 目录结构

```
docs/implementation/
└── worker-aware-migration/             # 本目录
    ├── README.md                       # 本文档（任务总览）
    ├── TEAM-ASSIGNMENT.md              # 团队分配方案和时间线
    ├── TASK-ASSIGNMENT.md              # 任务分配矩阵
    ├── ENGINEER-A-CONTEXT.md           # 工程师 A 上下文文档
    ├── ENGINEER-B-CONTEXT.md           # 工程师 B 上下文文档
    ├── ENGINEER-C-CONTEXT.md           # 工程师 C 上下文文档
    ├── T0-ir-contract.md               # T0: IR Contract 修正
    ├── T1-worker-scoped-step.md        # T1: WorkerScopedStepIR + Stage 7
    ├── T1.5-worker-aware-normalizer.md # T1.5: Worker-aware Stage 9.5
    ├── T1.6-child-worker-flow.md       # T1.6: WorkerIR/Renderer child-flow support
    ├── T2-scoped-resources-symboltable.md  # T2: WorkerScopedResourceIR + SymbolTable
    └── T3-remove-legacy-adapter.md     # T3: worker-aware path 去 adapter
```

### 相关文档
- [迁移方案 v3.0](../../migration-worker-aware-pipeline.md)
- [项目 README](../../../README.md)

### 联系方式
- 项目经理：Sisyphus
- 技术负责人：待指定
- 测试负责人：待指定
