# NL2SPL 开发者文档分发指南

## 概述

本文档规定每位开发者在开始开发前需要阅读的文档清单，按优先级排序。

---

## 所有开发者共享文档

| 优先级 | 文档 | 路径 | 阅读时间 | 用途 |
|--------|------|------|----------|------|
| **P0** | 共享上下文 | `docs/shared_context.md` | 30min | 项目背景、IR 详解、开发指南 |
| **P0** | 个人开发计划 | `docs/developer_{x}_plan.md` | 20min | 具体任务分解 |
| P1 | Sprint Plan v2 | `docs/sprint_plan_v2.md` | 10min | 总体开发计划 |

---

## Developer A (Tech Lead) - 代码审查 + 集成

### 角色定位

Developer A 的架构工作已完成（90%），主要职责转为：
- 代码审查（Review PR）
- 集成调试（Integration）
- 问题解答（Support）
- 文档完善（Documentation）
- 发布管理（Release）

### 必读文档（P0）

| # | 文档 | 路径 | 重点章节 | 阅读时间 |
|---|------|------|----------|----------|
| 1 | 共享上下文 | `docs/shared_context.md` | 全文（已熟悉） | 10min |
| 2 | Sprint Plan v2 | `docs/sprint_plan_v2.md` | §3 依赖关系、§4 Sprint 计划 | 10min |
| 3 | 文档分发指南 | `docs/document_distribution_guide.md` | 全文 | 10min |

### 参考文档（P1）

| # | 文档 | 路径 | 重点章节 | 阅读时间 |
|---|------|------|----------|----------|
| 4 | 设计文档 v4 | `docs/spl_nl_to_spl_design_document_v4.md` | 全文（已熟悉） | 15min |
| 5 | Prompt 设计 | `docs/prompt_design_document.md` | 全文（已熟悉） | 15min |
| 6 | 所有开发者计划 | `docs/developer_{b,c,d,e}_plan.md` | 任务分解、验收标准 | 30min |

### 需要阅读的源代码（审查前）

| # | 文件 | 重点内容 | 阅读时间 |
|---|------|----------|----------|
| 7 | `src/nl2spl/ir/*.py` | 所有 IR 模型（已熟悉） | 10min |
| 8 | `src/nl2spl/pipeline/stages/base.py` | Stage 基类（已熟悉） | 5min |
| 9 | `src/nl2spl/llm/client.py` | LLM 客户端（已熟悉） | 5min |
| 10 | `src/nl2spl/pipeline/orchestrator.py` | Orchestrator（需要更新） | 10min |

### 每周任务

#### Week 1: 审查 Developer B

| 任务 | 时间 | 说明 |
|------|------|------|
| 审查 Stage 1 代码 | 2h | SpanSlicer 实现 |
| 审查 Stage 2 代码 | 2h | FieldRouter 实现 |
| 审查 Stage 3 代码 | 2h | AmbiguityResolver 实现 |
| 审查测试代码 | 1h | 单元测试覆盖 |
| 更新 Orchestrator | 2h | 集成 Stage 1-3 |

#### Week 2: 审查 Developer C

| 任务 | 时间 | 说明 |
|------|------|------|
| 审查 Stage 4 代码 | 2h | FlowAssembler 实现 |
| 审查 Stage 5 代码 | 2h | BlockAssembler 实现 |
| 集成测试 | 2h | Stage 1-5 集成 |

#### Week 3: 审查 Developer D

| 任务 | 时间 | 说明 |
|------|------|------|
| 审查 Stage 6 代码 | 2h | ResourceExtractor 实现 |
| 审查 Stage 7 代码 | 2h | StepExtractor 实现 |
| 集成测试 | 2h | Stage 1-7 集成 |

#### Week 4: 审查 Developer E

| 任务 | 时间 | 说明 |
|------|------|------|
| 审查 Stage 8-11 代码 | 4h | Profile/Constraint/Normalizer/Worker/SPL |
| 集成测试 | 2h | Stage 1-11 集成 |
| 端到端测试 | 2h | 完整流程测试 |

#### Week 5: 文档 + 发布

| 任务 | 时间 | 说明 |
|------|------|------|
| 文档完善 | 4h | README、API 文档 |
| 最终代码审查 | 4h | mypy/ruff 检查 |
| 发布准备 | 2h | 版本号、依赖检查 |

### 代码审查清单

审查每个 PR 时检查：

```
□ 接口一致性
  - 继承 PipelineStage[Input, Output]
  - 实现 name 属性和 execute() 方法
  - 输入输出类型正确

□ 错误处理
  - 使用 nl2spl.errors.exceptions 异常类
  - 记录详细错误信息
  - 不吞掉异常

□ 日志记录
  - 使用 get_stage_logger(self.name)
  - 记录输入输出摘要
  - 记录关键决策点

□ Checkpoint 保存
  - 调用 self.save_checkpoint(result)
  - 保存到 config.output_dir
  - JSON 格式

□ 代码质量
  - 通过 mypy 类型检查
  - 通过 ruff 代码风格检查
  - 所有公共方法有 docstring
  - 无 TODO/FIXME 注释

□ 测试覆盖
  - 单元测试覆盖率 > 80%
  - 覆盖正常/边界/错误场景
  - 测试数据充分
```

### 文档阅读顺序

```
1. docs/shared_context.md (10min) - 刷新记忆
2. docs/sprint_plan_v2.md (10min) - 理解进度
3. docs/document_distribution_guide.md (10min) - 理解分发
4. docs/developer_b_plan.md (10min) - 理解 B 的任务
5. docs/developer_c_plan.md (10min) - 理解 C 的任务
6. docs/developer_d_plan.md (10min) - 理解 D 的任务
7. docs/developer_e_plan.md (10min) - 理解 E 的任务
```

### 总阅读时间

- **必读**: 10 + 10 + 10 = **30 min**
- **参考**: 15 + 15 + 30 = **60 min**
- **总计**: **90 min (约 1.5 小时)**

### 快速参考卡

```
角色: Tech Lead
职责: 代码审查 + 集成调试 + 文档 + 发布
必读: shared_context.md + sprint_plan_v2.md + document_distribution_guide.md
每周: 审查当周完成的 Stage 代码 + 集成测试
输出: PR 审查意见、集成测试结果、文档更新
```

---

## Developer B (Pipeline Engineer) - Stage 1-3

### 必读文档（P0）

| # | 文档 | 路径 | 重点章节 | 阅读时间 |
|---|------|------|----------|----------|
| 1 | 共享上下文 | `docs/shared_context.md` | §1 项目背景、§3.1 SpanIR、§3.2 FieldRouteIR、§4 Stage 实现指南 | 30min |
| 2 | 个人开发计划 | `docs/developer_b_plan.md` | 全文 | 20min |

### 参考文档（P1）

| # | 文档 | 路径 | 重点章节 | 阅读时间 |
|---|------|------|----------|----------|
| 3 | Prompt 设计 | `docs/prompt_design_document.md` | §3 Stage 1、§4 Stage 2、§5 Stage 3 | 20min |
| 4 | 设计文档 | `docs/spl_nl_to_spl_design_document_v4.md` | §4.1 SpanIR、§4.2 FieldRouteIR、§6 Stage 1-3 | 15min |

### 需要阅读的源代码

| # | 文件 | 重点内容 | 阅读时间 |
|---|------|----------|----------|
| 5 | `src/nl2spl/ir/span_ir.py` | SpanIR、AmbiguityInfo 数据类 | 5min |
| 6 | `src/nl2spl/ir/field_route_ir.py` | FieldRouteIR 数据类 | 5min |
| 7 | `src/nl2spl/pipeline/stages/base.py` | PipelineStage 基类 | 5min |
| 8 | `src/nl2spl/llm/client.py` | LLMClient.call_json() 方法 | 5min |
| 9 | `src/nl2spl/llm/prompts.py` | STAGE1_SYSTEM、STAGE2_SYSTEM、STAGE3_SYSTEM | 10min |

### 文档阅读顺序

```
1. docs/shared_context.md (30min)
   ├── 理解项目背景
   ├── 理解 SpanIR 和 FieldRouteIR
   └── 理解 Stage 实现模式

2. docs/developer_b_plan.md (20min)
   ├── 理解具体任务
   ├── 理解接口定义
   └── 理解测试要求

3. src/nl2spl/ir/span_ir.py (5min)
4. src/nl2spl/ir/field_route_ir.py (5min)
5. src/nl2spl/pipeline/stages/base.py (5min)
6. src/nl2spl/llm/client.py (5min)
7. src/nl2spl/llm/prompts.py (10min)

8. docs/prompt_design_document.md (20min) [可选]
   └── 深入理解 Prompt 设计

9. docs/spl_nl_to_spl_design_document_v4.md (15min) [可选]
   └── 深入理解架构设计
```

### 总阅读时间

- **必读**: 30 + 20 + 5 + 5 + 5 + 5 + 10 = **80 min**
- **参考**: 20 + 15 = **35 min**
- **总计**: **115 min (约 2 小时)**

---

## Developer C (Flow Engineer) - Stage 4-5

### 必读文档（P0）

| # | 文档 | 路径 | 重点章节 | 阅读时间 |
|---|------|------|----------|----------|
| 1 | 共享上下文 | `docs/shared_context.md` | §1 项目背景、§3.3 FlowStructureIR、§3.4 BlockStructureIR、§4 Stage 实现指南 | 30min |
| 2 | 个人开发计划 | `docs/developer_c_plan.md` | 全文 | 20min |

### 参考文档（P1）

| # | 文档 | 路径 | 重点章节 | 阅读时间 |
|---|------|------|----------|----------|
| 3 | Prompt 设计 | `docs/prompt_design_document.md` | §6 Stage 4、§7 Stage 5 | 20min |
| 4 | 设计文档 | `docs/spl_nl_to_spl_design_document_v4.md` | §4.3 FlowStructureIR、§4.4 BlockStructureIR、§6 Stage 4-5 | 15min |

### 需要阅读的源代码

| # | 文件 | 重点内容 | 阅读时间 |
|---|------|----------|----------|
| 5 | `src/nl2spl/ir/span_ir.py` | SpanIR 数据类（输入） | 5min |
| 6 | `src/nl2spl/ir/field_route_ir.py` | FieldRouteIR 数据类（输入） | 5min |
| 7 | `src/nl2spl/ir/flow_structure_ir.py` | FlowStructureIR、AlternativeFlow、ExceptionFlow、DelegationCandidate | 10min |
| 8 | `src/nl2spl/ir/block_structure_ir.py` | BlockStructureIR、BlockIR | 10min |
| 9 | `src/nl2spl/pipeline/stages/base.py` | PipelineStage 基类 | 5min |
| 10 | `src/nl2spl/llm/client.py` | LLMClient.call_json() 方法 | 5min |
| 11 | `src/nl2spl/llm/prompts.py` | STAGE4_SYSTEM、STAGE5_SYSTEM | 10min |

### 文档阅读顺序

```
1. docs/shared_context.md (30min)
   ├── 理解项目背景
   ├── 理解 FlowStructureIR 和 BlockStructureIR
   └── 理解 Stage 实现模式

2. docs/developer_c_plan.md (20min)
   ├── 理解具体任务
   ├── 理解 Flow/Block 判断规则
   └── 理解测试要求

3. src/nl2spl/ir/span_ir.py (5min)
4. src/nl2spl/ir/field_route_ir.py (5min)
5. src/nl2spl/ir/flow_structure_ir.py (10min)
6. src/nl2spl/ir/block_structure_ir.py (10min)
7. src/nl2spl/pipeline/stages/base.py (5min)
8. src/nl2spl/llm/client.py (5min)
9. src/nl2spl/llm/prompts.py (10min)

10. docs/prompt_design_document.md (20min) [可选]
    └── 深入理解 Prompt 设计

11. docs/spl_nl_to_spl_design_document_v4.md (15min) [可选]
    └── 深入理解架构设计
```

### 总阅读时间

- **必读**: 30 + 20 + 5 + 5 + 10 + 10 + 5 + 5 + 10 = **100 min**
- **参考**: 20 + 15 = **35 min**
- **总计**: **135 min (约 2.5 小时)**

---

## Developer D (Resource Engineer) - Stage 6-7

### 必读文档（P0）

| # | 文档 | 路径 | 重点章节 | 阅读时间 |
|---|------|------|----------|----------|
| 1 | 共享上下文 | `docs/shared_context.md` | §1 项目背景、§3.5 SymbolTable、§3.6 StepIR、§4 Stage 实现指南 | 30min |
| 2 | 个人开发计划 | `docs/developer_d_plan.md` | 全文 | 20min |

### 参考文档（P1）

| # | 文档 | 路径 | 重点章节 | 阅读时间 |
|---|------|------|----------|----------|
| 3 | Prompt 设计 | `docs/prompt_design_document.md` | §8 Stage 6、§9 Stage 7 | 20min |
| 4 | 设计文档 | `docs/spl_nl_to_spl_design_document_v4.md` | §4.5 ResourceRegistryIR、§4.8 SymbolTable、§4.9 StepIR | 15min |

### 需要阅读的源代码

| # | 文件 | 重点内容 | 阅读时间 |
|---|------|----------|----------|
| 5 | `src/nl2spl/ir/span_ir.py` | SpanIR 数据类（输入） | 5min |
| 6 | `src/nl2spl/ir/field_route_ir.py` | FieldRouteIR 数据类（输入） | 5min |
| 7 | `src/nl2spl/ir/resource_registry_ir.py` | ResourceRegistryIR、VariableSpec、APISpec、FileSpec、TypeSpec | 10min |
| 8 | `src/nl2spl/ir/symbol_table.py` | SymbolTable、VariableSymbol、declare/reference/add_producer/add_consumer | 15min |
| 9 | `src/nl2spl/ir/step_ir.py` | StepIR、CommandType、StepKind | 10min |
| 10 | `src/nl2spl/pipeline/stages/base.py` | PipelineStage 基类 | 5min |
| 11 | `src/nl2spl/llm/client.py` | LLMClient.call_json() 方法 | 5min |
| 12 | `src/nl2spl/llm/prompts.py` | STAGE6_SYSTEM、STAGE7_SYSTEM | 10min |

### 文档阅读顺序

```
1. docs/shared_context.md (30min)
   ├── 理解项目背景
   ├── 理解 SymbolTable 和 StepIR
   └── 理解 Stage 实现模式

2. docs/developer_d_plan.md (20min)
   ├── 理解具体任务
   ├── 理解变量识别规则
   └── 理解测试要求

3. src/nl2spl/ir/span_ir.py (5min)
4. src/nl2spl/ir/field_route_ir.py (5min)
5. src/nl2spl/ir/resource_registry_ir.py (10min)
6. src/nl2spl/ir/symbol_table.py (15min)
7. src/nl2spl/ir/step_ir.py (10min)
8. src/nl2spl/pipeline/stages/base.py (5min)
9. src/nl2spl/llm/client.py (5min)
10. src/nl2spl/llm/prompts.py (10min)

11. docs/prompt_design_document.md (20min) [可选]
    └── 深入理解 Prompt 设计

12. docs/spl_nl_to_spl_design_document_v4.md (15min) [可选]
    └── 深入理解架构设计
```

### 总阅读时间

- **必读**: 30 + 20 + 5 + 5 + 10 + 15 + 10 + 5 + 5 + 10 = **115 min**
- **参考**: 20 + 15 = **35 min**
- **总计**: **150 min (约 2.5 小时)**

---

## Developer E (Compiler Engineer) - Stage 8-11

### 必读文档（P0）

| # | 文档 | 路径 | 重点章节 | 阅读时间 |
|---|------|------|----------|----------|
| 1 | 共享上下文 | `docs/shared_context.md` | §1 项目背景、§3.7 ConstraintIR、§3.8 AgentProfileIR、§3.9 WorkerIR、§4 Stage 实现指南 | 30min |
| 2 | 个人开发计划 | `docs/developer_e_plan.md` | 全文 | 30min |

### 参考文档（P1）

| # | 文档 | 路径 | 重点章节 | 阅读时间 |
|---|------|------|----------|----------|
| 3 | Prompt 设计 | `docs/prompt_design_document.md` | §10 Stage 8、§11 Stage 9、§12 Stage 9.5 | 20min |
| 4 | 设计文档 | `docs/spl_nl_to_spl_design_document_v4.md` | §4.6 ConstraintIR、§4.10 WorkerIR、§6 Stage 8-11 | 15min |

### 需要阅读的源代码

| # | 文件 | 重点内容 | 阅读时间 |
|---|------|----------|----------|
| 5 | `src/nl2spl/ir/span_ir.py` | SpanIR 数据类（输入） | 5min |
| 6 | `src/nl2spl/ir/field_route_ir.py` | FieldRouteIR 数据类（输入） | 5min |
| 7 | `src/nl2spl/ir/flow_structure_ir.py` | FlowStructureIR（输入） | 5min |
| 8 | `src/nl2spl/ir/block_structure_ir.py` | BlockStructureIR（输入） | 5min |
| 9 | `src/nl2spl/ir/resource_registry_ir.py` | ResourceRegistryIR（输入） | 5min |
| 10 | `src/nl2spl/ir/symbol_table.py` | SymbolTable（输入） | 5min |
| 11 | `src/nl2spl/ir/step_ir.py` | StepIR（输入） | 5min |
| 12 | `src/nl2spl/ir/agent_profile_ir.py` | AgentProfileIR、PersonaIR、Aspect、Concept | 10min |
| 13 | `src/nl2spl/ir/constraint_ir.py` | ConstraintIR、ConstraintKind | 10min |
| 14 | `src/nl2spl/ir/worker_ir.py` | WorkerIR、FlowRef、AlternativeFlowRef、ExceptionFlowRef | 10min |
| 15 | `src/nl2spl/pipeline/stages/base.py` | PipelineStage 基类 | 5min |
| 16 | `src/nl2spl/llm/client.py` | LLMClient.call_json() 方法 | 5min |
| 17 | `src/nl2spl/llm/prompts.py` | STAGE8_SYSTEM、STAGE9_SYSTEM | 10min |

### 文档阅读顺序

```
1. docs/shared_context.md (30min)
   ├── 理解项目背景
   ├── 理解 ConstraintIR、AgentProfileIR、WorkerIR
   └── 理解 Stage 实现模式

2. docs/developer_e_plan.md (30min)
   ├── 理解具体任务
   ├── 理解 IR 归一化逻辑
   ├── 理解 Worker 组装逻辑
   └── 理解 SPL 渲染逻辑

3. src/nl2spl/ir/span_ir.py (5min)
4. src/nl2spl/ir/field_route_ir.py (5min)
5. src/nl2spl/ir/flow_structure_ir.py (5min)
6. src/nl2spl/ir/block_structure_ir.py (5min)
7. src/nl2spl/ir/resource_registry_ir.py (5min)
8. src/nl2spl/ir/symbol_table.py (5min)
9. src/nl2spl/ir/step_ir.py (5min)
10. src/nl2spl/ir/agent_profile_ir.py (10min)
11. src/nl2spl/ir/constraint_ir.py (10min)
12. src/nl2spl/ir/worker_ir.py (10min)
13. src/nl2spl/pipeline/stages/base.py (5min)
14. src/nl2spl/llm/client.py (5min)
15. src/nl2spl/llm/prompts.py (10min)

16. docs/prompt_design_document.md (20min) [可选]
    └── 深入理解 Prompt 设计

17. docs/spl_nl_to_spl_design_document_v4.md (15min) [可选]
    └── 深入理解架构设计
```

### 总阅读时间

- **必读**: 30 + 30 + 5 + 5 + 5 + 5 + 5 + 5 + 5 + 10 + 10 + 10 + 5 + 5 + 10 = **145 min**
- **参考**: 20 + 15 = **35 min**
- **总计**: **180 min (约 3 小时)**

---

## Developer A (Tech Lead) - 代码审查 + 集成

### 必读文档（P0）

| # | 文档 | 路径 | 重点章节 | 阅读时间 |
|---|------|------|----------|----------|
| 1 | 共享上下文 | `docs/shared_context.md` | 全文 | 30min |
| 2 | Sprint Plan v2 | `docs/sprint_plan_v2.md` | 全文 | 10min |

### 参考文档（P1）

| # | 文档 | 路径 | 重点章节 | 阅读时间 |
|---|------|------|----------|----------|
| 3 | 设计文档 | `docs/spl_nl_to_spl_design_document_v4.md` | 全文 | 30min |
| 4 | Prompt 设计 | `docs/prompt_design_document.md` | 全文 | 30min |

### 总阅读时间

- **必读**: 30 + 10 = **40 min**
- **参考**: 30 + 30 = **60 min**
- **总计**: **100 min (约 1.5 小时)**

---

## 文档分发清单

### 开发启动日（Day 0）

**给所有人**：
```
docs/shared_context.md
docs/sprint_plan_v2.md
```

**给 Developer B**：
```
docs/developer_b_plan.md
src/nl2spl/ir/span_ir.py
src/nl2spl/ir/field_route_ir.py
src/nl2spl/pipeline/stages/base.py
src/nl2spl/llm/client.py
src/nl2spl/llm/prompts.py
```

**给 Developer C**（Week 2 开始前）：
```
docs/developer_c_plan.md
src/nl2spl/ir/flow_structure_ir.py
src/nl2spl/ir/block_structure_ir.py
```

**给 Developer D**（Week 3 开始前）：
```
docs/developer_d_plan.md
src/nl2spl/ir/resource_registry_ir.py
src/nl2spl/ir/symbol_table.py
src/nl2spl/ir/step_ir.py
```

**给 Developer E**（Week 4 开始前）：
```
docs/developer_e_plan.md
src/nl2spl/ir/agent_profile_ir.py
src/nl2spl/ir/constraint_ir.py
src/nl2spl/ir/worker_ir.py
```

---

## 快速参考卡

### Developer B

```
必读: shared_context.md + developer_b_plan.md
代码: span_ir.py, field_route_ir.py, base.py, client.py, prompts.py
时间: 2 小时
任务: Stage 1 (SpanSlicer) → Stage 2 (FieldRouter) → Stage 3 (AmbiguityResolver)
```

### Developer C

```
必读: shared_context.md + developer_c_plan.md
代码: span_ir.py, field_route_ir.py, flow_structure_ir.py, block_structure_ir.py, base.py, client.py, prompts.py
时间: 2.5 小时
任务: Stage 4 (FlowAssembler) → Stage 5 (BlockAssembler)
```

### Developer D

```
必读: shared_context.md + developer_d_plan.md
代码: span_ir.py, field_route_ir.py, resource_registry_ir.py, symbol_table.py, step_ir.py, base.py, client.py, prompts.py
时间: 2.5 小时
任务: Stage 6 (ResourceExtractor) → Stage 7 (StepExtractor)
```

### Developer E

```
必读: shared_context.md + developer_e_plan.md
代码: 所有 ir/*.py + base.py + client.py + prompts.py
时间: 3 小时
任务: Stage 8 (ProfileExtractor) → Stage 9 (ConstraintExtractor) → Stage 9.5 (IRNormalizer) → Stage 10 (WorkerAssembler) → Stage 11 (SPLRenderer)
```
