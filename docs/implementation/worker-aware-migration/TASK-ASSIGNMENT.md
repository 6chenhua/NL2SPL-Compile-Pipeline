# 任务分配矩阵

**项目**: nl2spl Worker-Aware Pipeline Migration  
**创建日期**: 2026-05-12  
**项目经理**: Sisyphus

---

## 1. 按技能分配

### 后端开发工程师（熟悉 IR/Stage）

| 任务 ID | 任务名称 | 预估时间 | 技能要求 |
|---------|----------|----------|----------|
| T0 | IR Contract 修正 | 1 天 | IR 设计、数据结构 |
| T1 | WorkerScopedStepIR + Stage 7 | 3-5 天 | Stage 开发、LLM prompt |
| T1.5 | Worker-aware Stage 9.5 | 2-3 天 | 校验逻辑、错误处理 |
| T2 | WorkerScopedResourceIR + SymbolTable | 4-7 天 | SymbolTable、资源管理 |

### 全栈开发工程师（熟悉 Stage 10/11）

| 任务 ID | 任务名称 | 预估时间 | 技能要求 |
|---------|----------|----------|----------|
| T1.6 | WorkerIR/Renderer child-flow support | 2-4 天 | WorkerIR、SPL 渲染 |
| T3 | worker-aware path 去 adapter | 2-3 天 | Orchestrator、集成测试 |

---

## 2. 按并行度分配

### 第一阶段（可并行）

| 任务 ID | 任务名称 | 负责人 | 前置依赖 |
|---------|----------|--------|----------|
| T0 | IR Contract 修正 | 工程师 A | 无 |

### 第二阶段（T0 完成后）

| 任务 ID | 任务名称 | 负责人 | 前置依赖 |
|---------|----------|--------|----------|
| T1 | WorkerScopedStepIR + Stage 7 | 工程师 A | T0 |

### 第三阶段（T1 完成后）

| 任务 ID | 任务名称 | 负责人 | 前置依赖 |
|---------|----------|--------|----------|
| T1.5 | Worker-aware Stage 9.5 | 工程师 A | T1 |

### 第四阶段（T1.5 完成后，可并行）

| 任务 ID | 任务名称 | 负责人 | 前置依赖 |
|---------|----------|--------|----------|
| T1.6 | WorkerIR/Renderer child-flow support | 工程师 B | T1.5 |

### 第五阶段（T1.6 完成后，可并行）

| 任务 ID | 任务名称 | 负责人 | 前置依赖 |
|---------|----------|--------|----------|
| T2 | WorkerScopedResourceIR + SymbolTable | 工程师 A | T1.6 |
| T3 (部分) | worker-aware path 去 adapter | 工程师 B | T1.6 |

### 第六阶段（T2 完成后）

| 任务 ID | 任务名称 | 负责人 | 前置依赖 |
|---------|----------|--------|----------|
| T3 (完全) | worker-aware path 去 adapter | 工程师 B | T2 |

---

## 3. 推荐分配方案

### 方案 A：2 人团队（推荐）

| 角色 | 任务 | 时间线 |
|------|------|--------|
| 工程师 A | T0 → T1 → T1.5 → T2 | 第 1-15 天 |
| 工程师 B | (等待) → T1.6 → T3 | 第 6-15 天 |

**总时间**: 15 天（3 周）

### 方案 B：3 人团队（加速）

| 角色 | 任务 | 时间线 |
|------|------|--------|
| 工程师 A | T0 → T1 → T1.5 | 第 1-8 天 |
| 工程师 B | (等待) → T1.6 | 第 6-10 天 |
| 工程师 C | (等待) → T2 | 第 6-15 天 |
| 工程师 B | T3 | 第 11-15 天 |

**总时间**: 15 天（3 周）

### 方案 C：1 人团队（最慢）

| 角色 | 任务 | 时间线 |
|------|------|--------|
| 工程师 A | T0 → T1 → T1.5 → T1.6 → T2 → T3 | 第 1-24 天 |

**总时间**: 24 天（约 5 周）

---

## 4. 关键路径

```
T0 (1天) → T1 (3-5天) → T1.5 (2-3天) → T1.6 (2-4天) → T2 (4-7天) → T3 (2-3天)
```

**关键路径总时间**: 14-24 天

**并行机会**:
- T2 和 T3 (部分) 可以并行
- T1.6 完成后，工程师 B 可以开始 T3 (部分)

---

## 5. 风险分配

| 风险 | 影响 | 责任人 | 缓解措施 |
|------|------|--------|----------|
| T1 改动 Stage 7 核心逻辑 | 高 | 工程师 A | 保留 legacy path |
| T1.6 影响 Stage 11 渲染 | 高 | 工程师 B | 单独验证渲染 |
| T2 SymbolTable 改动影响面大 | 中 | 工程师 A | 渐进式迁移 |
| 测试覆盖不足 | 高 | 所有人 | 每个任务完成后运行完整测试 |

---

## 6. 沟通机制

### 每日站会
- 时间：每天 10:00
- 参与者：所有工程师
- 内容：昨日进展、今日计划、阻塞项

### 周会
- 时间：每周五 15:00
- 参与者：项目经理 + 所有工程师
- 内容：周总结、下周计划、风险 review

### 代码审查
- 每个 PR 需要至少两人审查
- 关键任务（T1, T1.6, T2）需要三人审查

---

## 7. 交付时间线

| 里程碑 | 日期 | 交付物 |
|--------|------|--------|
| M0: 设计冻结 | 第 1 天 | T0 完成，IR contract 冻结 |
| M1: Stage 7 完成 | 第 6 天 | T1 完成，Stage 7 worker-aware |
| M2: Normalizer 完成 | 第 9 天 | T1.5 完成，Stage 9.5 worker-aware |
| M3: Renderer 完成 | 第 13 天 | T1.6 完成，Stage 10/11 worker-aware |
| M4: Resources 完成 | 第 20 天 | T2 完成，Stage 6 worker-aware |
| M5: 迁移完成 | 第 24 天 | T3 完成，adapter 移除 |

---

## 8. 附录：任务文档链接

- [T0: IR Contract 修正](T0-ir-contract.md)
- [T1: WorkerScopedStepIR + Stage 7](T1-worker-scoped-step.md)
- [T1.5: Worker-aware Stage 9.5](T1.5-worker-aware-normalizer.md)
- [T1.6: WorkerIR/Renderer child-flow support](T1.6-child-worker-flow.md)
- [T2: WorkerScopedResourceIR + SymbolTable](T2-scoped-resources-symboltable.md)
- [T3: worker-aware path 去 adapter](T3-remove-legacy-adapter.md)
