# NL2SPL 开发计划 v2 (更新版)

## 1. 架构状态

### 已完成（Developer A）
- ✅ `pyproject.toml` - 项目配置
- ✅ `src/nl2spl/config.py` - 配置管理
- ✅ `src/nl2spl/main.py` - 入口点
- ✅ `src/nl2spl/errors/exceptions.py` - 错误处理
- ✅ `src/nl2spl/utils/logger.py` - 日志模块
- ✅ `src/nl2spl/utils/persistence.py` - 持久化模块
- ✅ `src/nl2spl/ir/*.py` - 11 个 IR 数据模型
- ✅ `src/nl2spl/llm/client.py` - LLM 客户端
- ✅ `src/nl2spl/llm/prompts.py` - Prompt 模板
- ✅ `src/nl2spl/pipeline/orchestrator.py` - 管道编排器
- ✅ `src/nl2spl/pipeline/stages/base.py` - Stage 基类
- ✅ `tests/` - 测试目录结构
- ✅ `docs/` - 文档目录

### 待完善（Developer A，可选）
- ⬜ `.env.example` - 环境变量模板
- ⬜ `tests/conftest.py` - pytest fixtures
- ⬜ `tests/fixtures/sample_inputs.py` - 测试数据

---

## 2. 团队分工（更新）

| 角色 | 代号 | 职责 | 状态 |
|------|------|------|------|
| Tech Lead | **A** | 架构（已完成）→ 代码审查 + 集成 | 架构完成 |
| Pipeline Engineer | **B** | Stage 1-3 实现 | 待开始 |
| Flow Engineer | **C** | Stage 4-5 实现 | 待开始 |
| Resource Engineer | **D** | Stage 6-7 实现 | 待开始 |
| Compiler Engineer | **E** | Stage 8-11 实现 | 待开始 |

---

## 3. 依赖关系分析

### 3.1 串行依赖（Stage 实现）

```
Week 1: A (架构完成) ──────────────────────────► B (Stage 1-3)
                                   │
Week 2:                            B ───────────► C (Stage 4-5)
                                   │
Week 3:                            C ───────────► D (Stage 6-7)
                                   │
Week 4:                            D ───────────► E (Stage 8-11)
```

**结论**：Stage 实现必须串行，不能并行开发。

### 3.2 可并行工作

| 工作类型 | 并行性 | 说明 |
|----------|--------|------|
| Stage 实现 | ❌ 串行 | C 依赖 B，D 依赖 C，E 依赖 D |
| 测试编写 | ✅ 并行 | 各开发者同时编写自己 Stage 的测试 |
| Prompt 优化 | ✅ 并行 | 各开发者同时优化自己 Stage 的 Prompt |
| 文档编写 | ✅ 并行 | 各开发者同时文档化自己的代码 |

---

## 4. 更新后的 Sprint 计划

### Sprint 1: Stage 1-3 (Week 1)

**负责人**: B  
**依赖**: A 的架构（已完成）

| 任务 | 文件 | 时间 | 验收标准 |
|------|------|------|----------|
| 理解架构 | `docs/shared_context.md` | 2h | 理解 IR 模型和 Stage 基类 |
| Stage 1: SpanSlicer | `stages/stage1_span_slicer.py` | 4h | 正确切片 |
| Stage 2: FieldRouter | `stages/stage2_field_router.py` | 4h | 正确路由 |
| Stage 3: AmbiguityResolver | `stages/stage3_ambiguity_resolver.py` | 4h | 正确消解 |
| Prompt 模板 | `prompts/stage{1,2,3}_system.txt` | 3h | 与代码一致 |
| 单元测试 | `tests/unit/test_{1,2,3}.py` | 4h | 覆盖率 > 80% |

**交付物**:
- Stage 1-3 实现
- Prompt 模板
- 单元测试

---

### Sprint 2: Stage 4-5 (Week 2)

**负责人**: C  
**依赖**: B 的 Stage 1-3

| 任务 | 文件 | 时间 | 验收标准 |
|------|------|------|----------|
| 理解 Stage 1-3 输出 | `ir/span_ir.py`, `ir/field_route_ir.py` | 2h | 理解数据格式 |
| Stage 4: FlowAssembler | `stages/stage4_flow_assembler.py` | 6h | 正确判断 Flow |
| Stage 5: BlockAssembler | `stages/stage5_block_assembler.py` | 6h | 正确组装 Block |
| Prompt 模板 | `prompts/stage{4,5}_system.txt` | 3h | 包含决策规则 |
| 单元测试 | `tests/unit/test_{4,5}.py` | 4h | 覆盖率 > 80% |

**交付物**:
- Stage 4-5 实现
- Prompt 模板
- 单元测试

---

### Sprint 3: Stage 6-7 (Week 3)

**负责人**: D  
**依赖**: B 的 Stage 1-3 + C 的 Stage 4-5

| 任务 | 文件 | 时间 | 验收标准 |
|------|------|------|----------|
| 理解 Stage 4-5 输出 | `ir/flow_structure_ir.py`, `ir/block_structure_ir.py` | 2h | 理解数据格式 |
| Stage 6: ResourceExtractor | `stages/stage6_resource_extractor.py` | 6h | 正确提取资源 |
| Stage 7: StepExtractor | `stages/stage7_step_extractor.py` | 6h | 正确提取 Step |
| Prompt 模板 | `prompts/stage{6,7}_system.txt` | 3h | 包含变量列表 |
| 单元测试 | `tests/unit/test_{6,7}.py` | 4h | 覆盖率 > 80% |

**交付物**:
- Stage 6-7 实现
- Prompt 模板
- 单元测试

---

### Sprint 4: Stage 8-11 (Week 4)

**负责人**: E  
**依赖**: D 的 Stage 6-7

| 任务 | 文件 | 时间 | 验收标准 |
|------|------|------|----------|
| 理解 Stage 6-7 输出 | `ir/resource_registry_ir.py`, `ir/step_ir.py` | 2h | 理解数据格式 |
| Stage 8: ProfileExtractor | `stages/stage8_profile_extractor.py` | 4h | 正确提取 Profile |
| Stage 9: ConstraintExtractor | `stages/stage9_constraint_extractor.py` | 4h | 正确提取 Constraint |
| Stage 9.5: IRNormalizer | `stages/stage9_5_normalizer.py` | 4h | 正确归一化 |
| Stage 10: WorkerAssembler | `stages/stage10_worker_assembler.py` | 4h | 正确组装 Worker |
| Stage 11: SPLRenderer | `stages/stage11_spl_renderer.py` | 4h | 正确渲染 SPL |
| SPL 格式化器 | `compiler/spl_formatter.py` | 3h | 格式化正确 |
| 静态校验器 | `validator/static_validator.py` | 3h | 校验正确 |
| 单元测试 | `tests/unit/test_{8,9,10,11}.py` | 6h | 覆盖率 > 80% |

**交付物**:
- Stage 8-11 实现
- SPL 格式化器
- 静态校验器
- 单元测试

---

### Sprint 5: 集成测试 + 优化 (Week 5)

**负责人**: 全员  
**依赖**: 所有 Stage 实现完成

| 任务 | 负责人 | 文件 | 时间 | 验收标准 |
|------|--------|------|------|----------|
| 端到端测试 | B | `tests/integration/test_e2e.py` | 6h | 覆盖完整流程 |
| 性能分析 | C | - | 4h | 识别瓶颈 |
| Prompt 优化 | D | `prompts/*.txt` | 6h | 提升质量 |
| 错误处理完善 | E | `errors/exceptions.py` | 4h | 覆盖所有错误 |
| 文档完善 | A | `docs/`, `README.md` | 4h | 完整清晰 |
| 最终代码审查 | A | - | 4h | 通过 mypy/ruff |

**交付物**:
- 端到端测试
- 优化后的 Prompt
- 完善的文档
- 可发布的 v0.1.0

---

## 5. 文档清单

每位开发者需要阅读的文档：

| 文档 | 路径 | 用途 |
|------|------|------|
| **共享上下文** | `docs/shared_context.md` | 项目背景、IR 详解、开发指南 |
| Sprint Plan | `docs/sprint_plan.md` | 总体开发计划 |
| 个人开发计划 | `docs/developer_{a,b,c,d,e}_plan.md` | 具体任务分解 |
| 设计文档 | `docs/spl_nl_to_spl_design_document_v4.md` | 架构设计 |
| Prompt 设计 | `docs/prompt_design_document.md` | Prompt 模板说明 |

---

## 6. 开发流程

### 6.1 每日流程

```
10:00-10:15  Standup（同步进度）
10:15-12:00  开发
14:00-17:00  开发
17:00-17:30  代码审查（A 审查 PR）
```

### 6.2 代码提交流程

1. 创建 feature 分支
2. 实现功能 + 测试
3. 提交 PR
4. A 审查通过
5. 合并到 main

### 6.3 依赖处理

当 B 完成 Stage 1-3 后：
1. B 提交 PR
2. A 审查通过
3. 合并到 main
4. C 开始 Stage 4-5

---

## 7. 风险和缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| LLM 输出不稳定 | Stage 解析失败 | 重试机制 + 容错解析 |
| Stage 接口不一致 | 集成困难 | 严格的接口约定 + 代码审查 |
| 进度延迟 | 交付延期 | 每周 Standup + 风险预警 |
| 测试覆盖不足 | Bug 逃逸 | 每个 Sprint 必须有测试 |

---

## 8. 里程碑

| 里程碑 | 日期 | 交付物 | 负责人 |
|--------|------|--------|--------|
| M1: 架构完成 | Day 0 | 项目架构 | A ✅ |
| M2: Stage 1-3 | Week 1 末 | 切片路由 | B |
| M3: Stage 4-5 | Week 2 末 | Flow/Block | C |
| M4: Stage 6-7 | Week 3 末 | 资源/步骤 | D |
| M5: Stage 8-11 | Week 4 末 | 编译完成 | E |
| M6: 发布就绪 | Week 5 末 | v0.1.0 | 全员 |
