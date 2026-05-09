# NL2SPL 开发计划 (Sprint Plan)

## 1. 项目架构总览

```
nl2spl/
├── src/nl2spl/                    # 源代码
│   ├── __init__.py
│   ├── main.py                    # 入口点
│   ├── config.py                  # 配置管理
│   ├── errors/                    # 错误处理
│   │   ├── __init__.py
│   │   └── exceptions.py
│   ├── ir/                        # IR 数据模型
│   │   ├── __init__.py
│   │   ├── span_ir.py
│   │   ├── field_route_ir.py
│   │   ├── flow_structure_ir.py
│   │   ├── block_structure_ir.py
│   │   ├── agent_profile_ir.py
│   │   ├── constraint_ir.py
│   │   ├── resource_registry_ir.py
│   │   ├── symbol_table.py
│   │   ├── step_ir.py
│   │   └── worker_ir.py
│   ├── llm/                       # LLM 客户端
│   │   ├── __init__.py
│   │   ├── client.py
│   │   └── prompts.py
│   ├── pipeline/                  # 管道编排
│   │   ├── __init__.py
│   │   ├── orchestrator.py
│   │   └── stages/
│   │       ├── __init__.py
│   │       ├── base.py
│   │       ├── stage1_span_slicer.py      # 待实现
│   │       ├── stage2_field_router.py     # 待实现
│   │       ├── stage3_ambiguity_resolver.py # 待实现
│   │       ├── stage4_flow_assembler.py   # 待实现
│   │       ├── stage5_block_assembler.py  # 待实现
│   │       ├── stage6_resource_extractor.py # 待实现
│   │       ├── stage7_step_extractor.py   # 待实现
│   │       ├── stage8_profile_extractor.py # 待实现
│   │       ├── stage9_constraint_extractor.py # 待实现
│   │       ├── stage9_5_normalizer.py     # 待实现
│   │       ├── stage10_worker_assembler.py # 待实现
│   │       └── stage11_spl_renderer.py    # 待实现
│   ├── compiler/                  # 编译器
│   │   ├── __init__.py
│   │   └── spl_formatter.py       # 待实现
│   ├── validator/                 # 校验器
│   │   ├── __init__.py
│   │   └── static_validator.py    # 待实现
│   └── utils/                     # 工具模块
│       ├── __init__.py
│       ├── logger.py
│       └── persistence.py
├── prompts/                       # Prompt 模板
│   ├── stage1_system.txt          # 待创建
│   ├── stage2_system.txt          # 待创建
│   ├── stage3_system.txt          # 待创建
│   ├── stage4_system.txt          # 待创建
│   ├── stage5_system.txt          # 待创建
│   ├── stage6_system.txt          # 待创建
│   ├── stage7_system.txt          # 待创建
│   ├── stage8_system.txt          # 待创建
│   └── stage9_system.txt          # 待创建
├── tests/                         # 测试
│   ├── __init__.py
│   ├── unit/                      # 单元测试
│   │   ├── __init__.py
│   │   ├── test_span_slicer.py
│   │   ├── test_field_router.py
│   │   ├── test_flow_assembler.py
│   │   ├── test_block_assembler.py
│   │   ├── test_resource_extractor.py
│   │   ├── test_step_extractor.py
│   │   ├── test_profile_extractor.py
│   │   ├── test_constraint_extractor.py
│   │   ├── test_normalizer.py
│   │   ├── test_worker_assembler.py
│   │   └── test_spl_renderer.py
│   ├── integration/               # 集成测试
│   │   ├── __init__.py
│   │   └── test_pipeline.py
│   └── fixtures/                  # 测试数据
│       ├── __init__.py
│       └── sample_inputs.py
├── examples/                      # 示例
│   └── usage.py
├── output/                        # 中间结果
├── docs/                          # 文档
│   ├── nl2spl_design_document_v4.md
│   ├── prompt_design_document.md
│   └── sprint_plan.md
├── pyproject.toml
└── README.md
```

---

## 2. 团队分工

| 角色 | 代号 | 职责 | 文件编辑范围 |
|------|------|------|-------------|
| Tech Lead | **A** | 架构搭建、代码审查、集成 | 所有文件 |
| Pipeline Engineer | **B** | Stage 1-3 实现 | `stages/stage{1,2,3}_*.py`, `tests/unit/test_{span_slicer,field_router}.py` |
| Flow Engineer | **C** | Stage 4-5 实现 | `stages/stage{4,5}_*.py`, `tests/unit/test_{flow_assembler,block_assembler}.py` |
| Resource Engineer | **D** | Stage 6-7 实现 | `stages/stage{6,7}_*.py`, `tests/unit/test_{resource_extractor,step_extractor}.py` |
| Compiler Engineer | **E** | Stage 8-11 实现 | `stages/stage{8,9,9_5,10,11}_*.py`, `compiler/`, `validator/`, `tests/unit/test_{profile_extractor,constraint_extractor,normalizer,worker_assembler,spl_renderer}.py` |

---

## 3. Sprint 计划

### Sprint 1: 基础设施 + 切片路由 (Week 1)

**目标**: 完成基础架构和 Stage 1-3

| 任务 | 负责人 | 文件 | 依赖 | 预估时间 |
|------|--------|------|------|----------|
| T1.1 项目架构搭建 | A | `pyproject.toml`, `config.py`, `errors/`, `utils/` | 无 | 4h |
| T1.2 IR 数据模型定义 | A | `ir/*.py` | T1.1 | 6h |
| T1.3 LLM 客户端封装 | A | `llm/client.py` | T1.1 | 3h |
| T1.4 Stage 基类定义 | A | `pipeline/stages/base.py` | T1.2 | 2h |
| T1.5 Stage 1: SpanSlicer | B | `stages/stage1_span_slicer.py` | T1.4 | 4h |
| T1.6 Stage 2: FieldRouter | B | `stages/stage2_field_router.py` | T1.5 | 4h |
| T1.7 Stage 3: AmbiguityResolver | B | `stages/stage3_ambiguity_resolver.py` | T1.6 | 4h |
| T1.8 Prompt 模板创建 | B | `prompts/stage{1,2,3}_system.txt` | T1.5-1.7 | 3h |
| T1.9 单元测试 (Stage 1-3) | B | `tests/unit/test_{span_slicer,field_router}.py` | T1.5-1.7 | 4h |
| T1.10 代码审查 | A | - | T1.5-1.9 | 2h |

**Sprint 1 交付物**:
- 完整的项目架构
- IR 数据模型
- Stage 1-3 实现 + 测试
- 可运行的切片路由管道

---

### Sprint 2: 流程结构 (Week 2)

**目标**: 完成 Stage 4-5 (Flow/Block 组装)

| 任务 | 负责人 | 文件 | 依赖 | 预估时间 |
|------|--------|------|------|----------|
| T2.1 Stage 4: FlowAssembler | C | `stages/stage4_flow_assembler.py` | Sprint 1 | 6h |
| T2.2 Stage 5: BlockAssembler | C | `stages/stage5_block_assembler.py` | T2.1 | 6h |
| T2.3 Prompt 模板 (Stage 4-5) | C | `prompts/stage{4,5}_system.txt` | T2.1-2.2 | 3h |
| T2.4 单元测试 (Stage 4-5) | C | `tests/unit/test_{flow_assembler,block_assembler}.py` | T2.1-2.2 | 4h |
| T2.5 集成测试 (Stage 1-5) | B | `tests/integration/test_pipeline.py` | Sprint 1 + T2.1-2.2 | 4h |
| T2.6 代码审查 | A | - | T2.1-2.5 | 2h |

**Sprint 2 交付物**:
- Stage 4-5 实现 + 测试
- Flow/Block 结构组装
- 集成测试 (Stage 1-5)

---

### Sprint 3: 资源提取 (Week 3)

**目标**: 完成 Stage 6-7 (资源/步骤提取)

| 任务 | 负责人 | 文件 | 依赖 | 预估时间 |
|------|--------|------|------|----------|
| T3.1 Stage 6: ResourceExtractor | D | `stages/stage6_resource_extractor.py` | Sprint 2 | 6h |
| T3.2 Stage 7: StepExtractor | D | `stages/stage7_step_extractor.py` | T3.1 | 6h |
| T3.3 Prompt 模板 (Stage 6-7) | D | `prompts/stage{6,7}_system.txt` | T3.1-3.2 | 3h |
| T3.4 单元测试 (Stage 6-7) | D | `tests/unit/test_{resource_extractor,step_extractor}.py` | T3.1-3.2 | 4h |
| T3.5 测试数据准备 | B | `tests/fixtures/sample_inputs.py` | Sprint 1 | 3h |
| T3.6 集成测试更新 | B | `tests/integration/test_pipeline.py` | T3.1-3.2 | 3h |
| T3.7 代码审查 | A | - | T3.1-3.6 | 2h |

**Sprint 3 交付物**:
- Stage 6-7 实现 + 测试
- SymbolTable 构建
- 变量识别逻辑

---

### Sprint 4: 约束提取 + 编译 (Week 4)

**目标**: 完成 Stage 8-11 (Profile/Constraint/Normalizer/Worker/SPL)

| 任务 | 负责人 | 文件 | 依赖 | 预估时间 |
|------|--------|------|------|----------|
| T4.1 Stage 8: ProfileExtractor | E | `stages/stage8_profile_extractor.py` | Sprint 3 | 4h |
| T4.2 Stage 9: ConstraintExtractor | E | `stages/stage9_constraint_extractor.py` | T4.1 | 4h |
| T4.3 Stage 9.5: IRNormalizer | E | `stages/stage9_5_normalizer.py` | T4.2 | 4h |
| T4.4 Stage 10: WorkerAssembler | E | `stages/stage10_worker_assembler.py` | T4.3 | 4h |
| T4.5 Stage 11: SPLRenderer | E | `stages/stage11_spl_renderer.py` | T4.4 | 4h |
| T4.6 SPL 格式化器 | E | `compiler/spl_formatter.py` | T4.5 | 3h |
| T4.7 静态校验器 | E | `validator/static_validator.py` | T4.5 | 3h |
| T4.8 Prompt 模板 (Stage 8-9) | E | `prompts/stage{8,9}_system.txt` | T4.1-4.2 | 2h |
| T4.9 单元测试 (Stage 8-11) | E | `tests/unit/test_*.py` | T4.1-4.7 | 6h |
| T4.10 代码审查 | A | - | T4.1-4.9 | 3h |

**Sprint 4 交付物**:
- Stage 8-11 实现 + 测试
- SPL 渲染器
- 静态校验器

---

### Sprint 5: 集成测试 + 优化 (Week 5)

**目标**: 端到端测试、性能优化、文档完善

| 任务 | 负责人 | 文件 | 依赖 | 预估时间 |
|------|--------|------|------|----------|
| T5.1 端到端测试 | B | `tests/integration/test_e2e.py` | Sprint 4 | 6h |
| T5.2 性能分析 | C | - | T5.1 | 4h |
| T5.3 Prompt 优化 | D | `prompts/*.txt` | T5.1-5.2 | 6h |
| T5.4 错误处理完善 | E | `errors/exceptions.py` | T5.1 | 4h |
| T5.5 文档完善 | A | `docs/`, `README.md` | All | 4h |
| T5.6 示例代码 | B | `examples/usage.py` | T5.1 | 3h |
| T5.7 最终代码审查 | A | - | All | 4h |
| T5.8 发布准备 | A | `pyproject.toml`, `README.md` | T5.7 | 2h |

**Sprint 5 交付物**:
- 完整的端到端测试
- 优化后的 Prompt
- 完善的文档
- 可发布的 v0.1.0

---

## 4. 文件编辑权限矩阵

### 4.1 Tech Lead (A)

**可编辑**: 所有文件

**主要职责**:
- 架构设计和搭建
- 代码审查
- 集成调试
- 发布管理

**专属文件**:
- `pyproject.toml`
- `src/nl2spl/config.py`
- `src/nl2spl/main.py`
- `src/nl2spl/pipeline/orchestrator.py`

---

### 4.2 Pipeline Engineer (B)

**可编辑**:
```
src/nl2spl/pipeline/stages/stage1_span_slicer.py
src/nl2spl/pipeline/stages/stage2_field_router.py
src/nl2spl/pipeline/stages/stage3_ambiguity_resolver.py
prompts/stage1_system.txt
prompts/stage2_system.txt
prompts/stage3_system.txt
tests/unit/test_span_slicer.py
tests/unit/test_field_router.py
tests/integration/test_pipeline.py
tests/fixtures/sample_inputs.py
examples/usage.py
```

**不可编辑**:
```
src/nl2spl/ir/*.py          # IR 模型由 A 定义
src/nl2spl/llm/client.py    # LLM 客户端由 A 定义
src/nl2spl/pipeline/stages/base.py  # 基类由 A 定义
src/nl2spl/config.py        # 配置由 A 管理
pyproject.toml              # 项目配置由 A 管理
```

---

### 4.3 Flow Engineer (C)

**可编辑**:
```
src/nl2spl/pipeline/stages/stage4_flow_assembler.py
src/nl2spl/pipeline/stages/stage5_block_assembler.py
prompts/stage4_system.txt
prompts/stage5_system.txt
tests/unit/test_flow_assembler.py
tests/unit/test_block_assembler.py
```

**不可编辑**:
```
src/nl2spl/ir/*.py
src/nl2spl/llm/client.py
src/nl2spl/pipeline/stages/base.py
src/nl2spl/pipeline/stages/stage{1,2,3}_*.py  # B 的文件
src/nl2spl/pipeline/stages/stage{6,7,8,9,10,11}_*.py  # 其他人的文件
```

---

### 4.4 Resource Engineer (D)

**可编辑**:
```
src/nl2spl/pipeline/stages/stage6_resource_extractor.py
src/nl2spl/pipeline/stages/stage7_step_extractor.py
prompts/stage6_system.txt
prompts/stage7_system.txt
tests/unit/test_resource_extractor.py
tests/unit/test_step_extractor.py
```

**不可编辑**:
```
src/nl2spl/ir/*.py
src/nl2spl/llm/client.py
src/nl2spl/pipeline/stages/base.py
src/nl2spl/pipeline/stages/stage{1,2,3,4,5}_*.py
src/nl2spl/pipeline/stages/stage{8,9,10,11}_*.py
```

---

### 4.5 Compiler Engineer (E)

**可编辑**:
```
src/nl2spl/pipeline/stages/stage8_profile_extractor.py
src/nl2spl/pipeline/stages/stage9_constraint_extractor.py
src/nl2spl/pipeline/stages/stage9_5_normalizer.py
src/nl2spl/pipeline/stages/stage10_worker_assembler.py
src/nl2spl/pipeline/stages/stage11_spl_renderer.py
src/nl2spl/compiler/spl_formatter.py
src/nl2spl/validator/static_validator.py
prompts/stage8_system.txt
prompts/stage9_system.txt
tests/unit/test_profile_extractor.py
tests/unit/test_constraint_extractor.py
tests/unit/test_normalizer.py
tests/unit/test_worker_assembler.py
tests/unit/test_spl_renderer.py
```

**不可编辑**:
```
src/nl2spl/ir/*.py
src/nl2spl/llm/client.py
src/nl2spl/pipeline/stages/base.py
src/nl2spl/pipeline/stages/stage{1,2,3,4,5,6,7}_*.py
```

---

## 5. 接口约定

### 5.1 Stage 输入输出接口

每个 Stage 必须实现以下接口:

```python
class StageXxx(PipelineStage[InputType, OutputType]):
    @property
    def name(self) -> str:
        return "stage_xxx"

    def execute(self, input_data: InputType) -> OutputType:
        # 实现逻辑
        pass
```

### 5.2 IR 数据传递

Stage 之间通过 IR 数据类传递数据:

```
Stage 1 → List[SpanIR]
Stage 2 → FieldRouteIR + List[SpanIR] (ambiguity updates)
Stage 3 → List[SpanIR] + FieldRouteIR (resolved)
Stage 4 → FlowStructureIR
Stage 5 → BlockStructureIR
Stage 6 → ResourceRegistryIR + SymbolTable
Stage 7 → List[StepIR] + SymbolTable (updated)
Stage 8 → AgentProfileIR
Stage 9 → List[ConstraintIR]
Stage 9.5 → Normalized IRs
Stage 10 → WorkerIR
Stage 11 → str (SPL text)
```

### 5.3 错误处理

所有 Stage 必须:
1. 使用 `nl2spl.errors.exceptions` 中的异常类
2. 记录详细的错误信息
3. 在 checkpoint 中保存错误状态

### 5.4 日志记录

所有 Stage 必须:
1. 使用 `get_stage_logger(self.name)` 获取 logger
2. 记录输入输出摘要
3. 记录关键决策点

### 5.5 中间结果保存

所有 Stage 必须:
1. 在 `execute()` 结束时调用 `self.save_checkpoint(result)`
2. 保存到 `config.output_dir`
3. 使用 JSON 格式

---

## 6. 代码规范

### 6.1 命名规范

- 类名: PascalCase
- 函数名: snake_case
- 变量名: snake_case
- 常量名: UPPER_SNAKE_CASE
- 文件名: snake_case.py

### 6.2 类型注解

- 所有公共函数必须有类型注解
- 使用 `from __future__ import annotations`
- 使用 `Optional[X]` 而非 `X | None`

### 6.3 文档字符串

- 所有公共类和函数必须有 docstring
- 使用 Google 风格 docstring
- 包含 Args、Returns、Raises 部分

### 6.4 测试覆盖

- 每个 Stage 至少 5 个单元测试
- 测试正常路径、边界情况、错误情况
- 使用 pytest fixtures 复用测试数据

---

## 7. 风险和缓解措施

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| LLM 输出不稳定 | Stage 解析失败 | 重试机制 + 容错解析 |
| Stage 接口不一致 | 集成困难 | 严格的接口约定 + 代码审查 |
| Prompt 效果不佳 | 输出质量差 | Sprint 5 专门优化 |
| 测试覆盖不足 | Bug 逃逸 | 每个 Sprint 必须有测试 |
| 进度延迟 | 交付延期 | 每周 Standup + 风险预警 |

---

## 8. 交付标准

### 8.1 代码质量

- [ ] 通过 mypy 类型检查
- [ ] 通过 ruff 代码风格检查
- [ ] 单元测试覆盖率 > 80%
- [ ] 无 TODO/FIXME 注释

### 8.2 功能完整性

- [ ] 所有 11 个 Stage 实现
- [ ] 端到端测试通过
- [ ] 示例可运行

### 8.3 文档完整性

- [ ] README 包含安装和使用说明
- [ ] 所有公共 API 有 docstring
- [ ] 设计文档更新

---

## 9. 沟通机制

### 9.1 每日 Standup

- 时间: 每天 10:00
- 时长: 15 分钟
- 内容: 昨天完成、今天计划、阻塞问题

### 9.2 Sprint Review

- 时间: 每个 Sprint 结束
- 时长: 1 小时
- 内容: Demo、反馈、调整

### 9.3 代码审查

- 每个 PR 必须有至少 1 人审查
- Tech Lead 审查所有 PR
- 审查重点: 接口一致性、错误处理、测试覆盖

---

## 10. 里程碑

| 里程碑 | 日期 | 交付物 |
|--------|------|--------|
| M1: 基础架构 | Week 1 末 | 项目架构 + Stage 1-3 |
| M2: 流程结构 | Week 2 末 | Stage 4-5 + 集成测试 |
| M3: 资源提取 | Week 3 末 | Stage 6-7 + SymbolTable |
| M4: 编译完成 | Week 4 末 | Stage 8-11 + SPL 渲染 |
| M5: 发布就绪 | Week 5 末 | v0.1.0 发布 |
