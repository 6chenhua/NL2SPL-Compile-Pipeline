# NL2SPL 项目共享上下文文档

## 1. 项目背景

### 1.1 什么是 SPL？

SPL（Structured Prompt Language）是一种结构化的提示词语言，用于定义 AI 智能体的行为。SPL 包含以下核心块：

```spl
[DEFINE_AGENT: AgentName "描述"]
    [DEFINE_PERSONA:]
        ROLE: 角色描述
        风格: 风格描述
    [END_PERSONA]

    [DEFINE_AUDIENCE:]
        用户群体: 描述
    [END_AUDIENCE]

    [DEFINE_CONCEPTS:]
        术语: 定义
    [END_CONCEPTS]

    [DEFINE_VARIABLES:]
        "描述" 变量名: 类型
    [END_VARIABLES]

    [DEFINE_CONSTRAINTS:]
        约束类型: 约束描述
    [END_CONSTRAINTS]

    [DEFINE_WORKER: "描述" WorkerName]
        [INPUTS]
            REQUIRED <REF>变量名</REF>
        [END_INPUTS]
        [OUTPUTS]
            REQUIRED <REF>变量名</REF>
        [END_OUTPUTS]
        [MAIN_FLOW]
            [SEQUENTIAL_BLOCK]
                COMMAND-1 [COMMAND 动作描述]
            [END_SEQUENTIAL_BLOCK]
            DECISION-1 [IF 条件]
                COMMAND-2 [COMMAND 动作描述]
            [END_IF]
        [END_MAIN_FLOW]
        [ALTERNATIVE_FLOW: 条件]
            ...
        [END_ALTERNATIVE_FLOW]
        [EXCEPTION_FLOW: 条件]
            ...
        [END_EXCEPTION_FLOW]
    [END_WORKER]
[END_AGENT]
```

### 1.2 项目目标

将自然语言描述转换为 SPL 代码：

**输入**：7 段式自然语言文本
```
Task family: ...
Inputs for each run: ...
Required outputs: ...
Reusable process: ...
Policies: ...
Failure handling: ...
Delegation policy: ...
```

**输出**：符合 SPL 语法的代码

### 1.3 设计理念

**LLM 负责语义，代码负责结构**：
- LLM 理解自然语言，输出结构化 JSON（IR）
- 代码将 IR 编译为 SPL

**自顶向下分解**：
1. 先确定 Flow（MAIN / ALTERNATIVE / EXCEPTION）
2. 再确定 Block（SEQUENTIAL / IF / FOR / WHILE）
3. 最后填充 Step（具体动作）

---

## 2. 数据流图

```
输入: 7 段式自然语言文本
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ Stage 1: SpanSlicer (LLM)                                   │
│   输入: raw_text (str)                                       │
│   输出: List[SpanIR]                                         │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ Stage 2: FieldRouter (LLM)                                  │
│   输入: List[SpanIR]                                         │
│   输出: FieldRouteIR + ambiguity_updates                     │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ Stage 3: AmbiguityResolver (LLM)                            │
│   输入: List[SpanIR] + FieldRouteIR + ambiguity_updates      │
│   输出: List[SpanIR] (resolved) + FieldRouteIR (resolved)    │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ Stage 4: FlowAssembler (LLM)                                │
│   输入: List[SpanIR] + FieldRouteIR                          │
│   输出: FlowStructureIR                                      │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ Stage 5: BlockAssembler (LLM)                               │
│   输入: List[SpanIR] + FieldRouteIR + FlowStructureIR        │
│   输出: BlockStructureIR                                     │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ Stage 6: ResourceExtractor (LLM)                            │
│   输入: List[SpanIR] + FieldRouteIR                          │
│   输出: ResourceRegistryIR + SymbolTable                     │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ Stage 7: StepExtractor (LLM)                                │
│   输入: List[SpanIR] + FieldRouteIR + FlowStructureIR +      │
│         BlockStructureIR + SymbolTable                       │
│   输出: List[StepIR] + SymbolTable (updated)                 │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ Stage 8: ProfileExtractor (LLM)                             │
│   输入: List[SpanIR] + FieldRouteIR + SymbolTable            │
│   输出: AgentProfileIR                                       │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ Stage 9: ConstraintExtractor (LLM)                          │
│   输入: List[SpanIR] + FieldRouteIR + FlowStructureIR +      │
│         BlockStructureIR + SymbolTable + List[StepIR]        │
│   输出: List[ConstraintIR]                                   │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ Stage 9.5: IRNormalizer (Code)                              │
│   输入: 所有 IR                                              │
│   输出: 归一化的所有 IR + errors + warnings                   │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ Stage 10: WorkerAssembler (Code)                            │
│   输入: FlowStructureIR + BlockStructureIR + List[StepIR] +  │
│         ResourceRegistryIR + SymbolTable                     │
│   输出: WorkerIR                                             │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ Stage 11: SPLRenderer (Code)                                │
│   输入: WorkerIR + AgentProfileIR + ResourceRegistryIR +     │
│         SymbolTable                                          │
│   输出: str (SPL text)                                       │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
输出: SPL 代码
```

---

## 3. IR 模型详解

### 3.1 SpanIR（文本切片）

**用途**：保存原文切片与歧义标记

**字段**：
```python
@dataclass
class SpanIR:
    span_id: str          # 格式: s{N}
    text: str             # 原文文本（保持原样）
    ambiguity: AmbiguityInfo  # 歧义信息

@dataclass
class AmbiguityInfo:
    is_ambiguous: bool    # 是否歧义（Stage 2 回写）
    reasons: list[str]    # 歧义原因
    needs_split: bool     # 是否需要拆分
```

**示例**：
```json
{
  "span_id": "s1",
  "text": "First determine what kind of communication is requested",
  "ambiguity": {
    "is_ambiguous": false,
    "reasons": [],
    "needs_split": false
  }
}
```

---

### 3.2 FieldRouteIR（字段路由）

**用途**：将 span 路由到 6 个语义字段

**字段**：
```python
@dataclass
class FieldRouteIR:
    identity: list[str]       # span_id 列表
    audience: list[str]
    rules: list[str]
    domain: list[str]
    integrations: list[str]
    behavior: list[str]
```

**规则**：
- 一个 span 只能路由到一个字段（不允许重叠）
- 歧义 span 在 Stage 3 拆分

**示例**：
```json
{
  "identity": ["s1"],
  "audience": [],
  "rules": ["s3"],
  "domain": [],
  "integrations": ["s4"],
  "behavior": ["s2", "s5", "s6"]
}
```

---

### 3.3 FlowStructureIR（流程结构）

**用途**：判断每个 span 属于哪个 Flow

**字段**：
```python
@dataclass
class FlowStructureIR:
    main_flow_spans: list[str]           # 主流程 span
    alternative_flows: list[AlternativeFlow]  # 替代流程
    exception_flows: list[ExceptionFlow]      # 异常流程
    delegation_candidates: list[DelegationCandidate]  # 委派候选

@dataclass
class AlternativeFlow:
    flow_id: str          # 格式: alt_{N}
    condition_text: str   # 触发条件
    spans: list[str]

@dataclass
class ExceptionFlow:
    flow_id: str          # 格式: exc_{N}
    condition_text: str
    spans: list[str]

@dataclass
class DelegationCandidate:
    candidate_id: str     # 格式: dc_{N}
    spans: list[str]
    reason: str
    suggested_type: str   # "child_worker" 或 "api_call"
    input_variables: list[str]
    output_variables: list[str]
```

**Flow 判断规则（分层决策树）**：
```
第一层：判断影响范围
- 影响单个动作 → 留给 Stage 5 (IF_BLOCK)
- 影响整条路径 → 进入第二层

第二层：判断路径类型
- 用户主动触发 → ALTERNATIVE_FLOW
- 负面事件 → EXCEPTION_FLOW
- 正常条件 → 留给 Stage 5 (IF_BLOCK)
```

---

### 3.4 BlockStructureIR（块结构）

**用途**：在每个 Flow 内，将 span 组织成 Block

**字段**：
```python
@dataclass
class BlockStructureIR:
    main_flow_blocks: list[BlockIR]
    alternative_flow_blocks: dict[str, list[BlockIR]]  # flow_id → blocks
    exception_flow_blocks: dict[str, list[BlockIR]]    # flow_id → blocks

@dataclass
class BlockIR:
    block_id: str           # 格式: b{N}
    block_type: str         # "SEQUENTIAL" | "IF" | "FOR" | "WHILE"
    condition_text: str | None  # 条件文本（IF/FOR/WHILE）
    spans: list[str]
```

**Block 类型**：
- `SEQUENTIAL`：连续的、无条件的动作
- `IF`：条件执行（"if"、"when"、"unless"）
- `FOR`：遍历循环（"for each"、"for every"）
- `WHILE`：条件循环（"while"、"until"）

---

### 3.5 SymbolTable（符号表）

**用途**：管理变量的声明和引用

**字段**：
```python
class SymbolTable:
    variables: dict[str, VariableSymbol]

@dataclass
class VariableSymbol:
    name: str
    data_type: str        # "text" | "number" | "boolean" | "List[type]" | "{ }"
    source: str           # "input" | "output" | "step" | "api" | "file"
    description: str
    flow_ref: str = "main"
    block_ref: str | None = None
    producer_step: str | None = None  # 产生该变量的 step_id
    consumer_steps: list[str] = []    # 消费该变量的 step_id 列表
    declared: bool = True
```

**关键方法**：
```python
# 声明变量
symbol_table.declare("user_request", "text", "input", "用户请求")

# 生成引用标签
symbol_table.reference("user_request")  # → "<REF>user_request</REF>"

# 生成变量列表（用于 Prompt）
symbol_table.get_variable_list_for_prompt()
# → "- user_request: text (input) - 用户请求"

# 记录 producer/consumer
symbol_table.add_producer("communication_type", "st1")
symbol_table.add_consumer("user_request", "st3")
```

---

### 3.6 StepIR（步骤）

**用途**：表示 workflow 中的原子动作

**字段**：
```python
@dataclass
class StepIR:
    step_id: str              # 格式: st{N}
    text: str                 # 步骤描述
    source_span_ids: list[str]
    command_type: str         # "GENERAL_COMMAND" | "CALL_API" | "INVOKE_WORKER" | "REQUEST_INPUT" | "DISPLAY_MESSAGE"
    inputs: list[str]         # 输入变量名
    outputs: list[str]        # 输出变量名
    integration_ref: str | None  # 引用的 API（仅 CALL_API）
    flow_ref: str = "main"    # 所属 Flow
    block_ref: str = ""       # 所属 Block
    kind: str = "normal"      # "normal" | "tool" | "user_input" | "invoke" | "display"
```

---

### 3.7 ConstraintIR（约束）

**用途**：保存规则、限制、门控条件

**字段**：
```python
@dataclass
class ConstraintIR:
    constraint_id: str    # 格式: c{N}
    text: str             # 约束文本（可含 <REF> 标签）
    kind: str             # "requirement" | "prohibition" | "gate" | "evidence" | ...
    targets: list[str]    # 格式: "type:id"（step:st1, variable:var_name, global）
    source_span_ids: list[str]
```

**约束类型**：
- `requirement`：必须满足的要求
- `prohibition`：禁止的行为
- `gate`：门控条件
- `evidence`：证据要求
- `safety`：安全约束
- `audit`：审计要求

---

### 3.8 AgentProfileIR（智能体画像）

**用途**：生成 PERSONA / AUDIENCE / CONCEPTS

**字段**：
```python
@dataclass
class AgentProfileIR:
    persona: PersonaIR
    audience_aspects: list[Aspect]
    concepts: list[Concept]

@dataclass
class PersonaIR:
    role: str = "General Assistant"
    aspects: list[Aspect] = []

@dataclass
class Aspect:
    name: str   # PascalCase
    text: str

@dataclass
class Concept:
    term: str
    definition: str
```

---

### 3.9 WorkerIR（Worker 组装）

**用途**：表示最终的 SPL Worker 结构

**字段**：
```python
@dataclass
class WorkerIR:
    worker_name: str
    description: str
    inputs: list[WorkerInput]
    outputs: list[WorkerOutput]
    main_flow: FlowRef
    alternative_flows: list[AlternativeFlowRef]
    exception_flows: list[ExceptionFlowRef]
    api_refs: list[str]
    child_worker_refs: list[str]
```

---

## 4. Stage 实现指南

### 4.1 Stage 基类

所有 Stage 必须继承 `PipelineStage[Input, Output]`：

```python
from nl2spl.pipeline.stages.base import PipelineStage

class MyStage(PipelineStage[InputType, OutputType]):
    @property
    def name(self) -> str:
        return "my_stage"

    def execute(self, input_data: InputType) -> OutputType:
        # 1. 构建 prompt
        # 2. 调用 LLM (self.client.call_json)
        # 3. 解析结果
        # 4. 保存 checkpoint (self.save_checkpoint)
        # 5. 返回结果
        pass
```

### 4.2 LLM 调用

```python
# 调用 LLM 获取 JSON
result = self.client.call_json(
    stage_name=self.name,
    system_prompt=system_prompt,
    user_prompt=user_prompt,
    model="gpt-4o",  # 可选，覆盖默认模型
    max_tokens=4096,  # 可选
)
```

### 4.3 错误处理

```python
from nl2spl.errors.exceptions import StageError, LLMError

try:
    result = self.client.call_json(...)
except LLMError as e:
    raise StageError(
        message=f"LLM call failed: {e}",
        stage=self.name,
    )
```

### 4.4 日志记录

```python
# 在 __init__ 中自动获取 logger
self.logger.info("Processing %d spans", len(spans))
self.logger.warning("Overlapping spans: %s", overlaps)
self.logger.error("Failed to parse result: %s", e)
```

### 4.5 Checkpoint 保存

```python
# 在 execute 结束时保存
self.save_checkpoint({
    "result_key": result_value,
})
```

---

## 5. Prompt 模板使用指南

### 5.1 Prompt 模板位置

所有 Prompt 模板位于 `src/nl2spl/llm/prompts.py`：

```python
from nl2spl.llm.prompts import STAGE1_SYSTEM, STAGE2_SYSTEM, ...
```

### 5.2 Prompt 结构

每个 Prompt 包含：
1. **角色定义**：LLM 扮演什么角色
2. **任务边界**：LLM 需要做什么
3. **输出格式**：LLM 必须输出什么格式
4. **SPL 语法摘要**：相关的 SPL 语法

### 5.3 User Prompt 模板

```python
user_prompt = f"""请执行某个操作：

输入数据：
---
{input_json}
---

输出 JSON："""
```

---

## 6. 测试指南

### 6.1 测试文件位置

```
tests/
├── unit/
│   ├── test_span_slicer.py
│   ├── test_field_router.py
│   ├── test_flow_assembler.py
│   ├── test_block_assembler.py
│   ├── test_resource_extractor.py
│   ├── test_step_extractor.py
│   ├── test_profile_extractor.py
│   ├── test_constraint_extractor.py
│   ├── test_normalizer.py
│   ├── test_worker_assembler.py
│   └── test_spl_renderer.py
├── integration/
│   └── test_pipeline.py
└── fixtures/
    └── sample_inputs.py
```

### 6.2 测试模式

```python
import pytest
from unittest.mock import MagicMock, patch

# Mock LLM 客户端
@pytest.fixture
def mock_client():
    client = MagicMock()
    client.call_json.return_value = {
        "spans": [{"span_id": "s1", "text": "test"}]
    }
    return client

# 测试正常路径
def test_normal_case(mock_client):
    stage = MyStage(config, mock_client)
    result = stage.execute(input_data)
    assert len(result) > 0

# 测试边界情况
def test_empty_input(mock_client):
    stage = MyStage(config, mock_client)
    result = stage.execute("")
    assert result == []

# 测试错误处理
def test_llm_error(mock_client):
    mock_client.call_json.side_effect = LLMError("API error")
    stage = MyStage(config, mock_client)
    with pytest.raises(StageError):
        stage.execute(input_data)
```

### 6.3 测试数据

测试数据位于 `tests/fixtures/sample_inputs.py`：

```python
SAMPLE_INPUTS = {
    "simple": "First determine what kind of communication is requested.",
    "complex": """
Task family: Internal newsletters and announcements.
Inputs: A user request, optional topics.
...
""",
}
```

---

## 7. 开发者依赖关系

### 7.1 依赖图

```
Week 1: A (架构) ──────────────────────────────► B (Stage 1-3)
                              │
Week 2:                      B ─────────────────► C (Stage 4-5)
                              │
Week 3:                      C ─────────────────► D (Stage 6-7)
                              │
Week 4:                      D ─────────────────► E (Stage 8-11)
```

### 7.2 串行依赖

**Stage 实现必须串行**：
- C 依赖 B 的 Stage 1-3 输出（SpanIR, FieldRouteIR）
- D 依赖 B+C 的 Stage 1-5 输出
- E 依赖 D 的 Stage 6-7 输出

### 7.3 可并行工作

以下工作可以并行：
- 测试编写（各开发者同时编写自己 Stage 的测试）
- Prompt 优化（各开发者同时优化自己 Stage 的 Prompt）
- 文档编写（各开发者同时文档化自己的代码）

---

## 8. 常见问题

### 8.1 如何处理 LLM 输出不稳定？

```python
# 使用重试机制
for attempt in range(self.config.max_retries):
    try:
        result = self.client.call_json(...)
        break
    except LLMError:
        if attempt == self.config.max_retries - 1:
            raise
        time.sleep(self.config.retry_delay)
```

### 8.2 如何处理 JSON 解析失败？

```python
try:
    data = json.loads(response)
except json.JSONDecodeError as e:
    raise LLMError(f"Invalid JSON: {e}", stage=self.name)
```

### 8.3 如何处理缺失字段？

```python
# 使用默认值
spans = result.get("spans", [])
flow_id = flow_data.get("flow_id", "alt_1")
```

### 8.4 如何调试 LLM 输出？

```python
# 保存 checkpoint
self.save_checkpoint({
    "raw_response": result,
    "parsed_spans": [asdict(s) for s in spans],
})
```

---

## 10. SPL 缩进规范

SPL 采用**固定缩进规则**，每个元素的缩进级别由其在 SPL 结构中的位置决定。

**核心原则**：
- 最顶层的内容无需缩进
- 每一层被包含的内容都需要多一个缩进级别
- 每个缩进级别 = 4 个空格

**详细规范**：请参考 [SPL 缩进规范文档](../spl_indentation_spec.md)

### 快速参考

| 元素 | 缩进级别 | 空格数 |
|------|---------|--------|
| `[DEFINE_AGENT:]` / `[END_AGENT]` | 0 | 0 |
| `[DEFINE_PERSONA:]` / `[DEFINE_APIS:]` / `[DEFINE_WORKER:]` 等 | 1 | 4 |
| `ROLE:` / API 描述 / `[INPUTS]` / `[MAIN_FLOW]` 等 | 2 | 8 |
| OPENAPI_SCHEMA / API_IN_SPL / `[SEQUENTIAL]` 等 | 3 | 12 |
| `COMMAND-N [COMMAND ...]` 等命令 | 4 | 16 |

---

## 9. 代码规范

### 9.1 命名规范

- 类名: `PascalCase`
- 函数名: `snake_case`
- 变量名: `snake_case`
- 常量名: `UPPER_SNAKE_CASE`
- 文件名: `snake_case.py`

### 9.2 类型注解

```python
from __future__ import annotations
from typing import Optional

def process(spans: list[SpanIR]) -> Optional[FieldRouteIR]:
    pass
```

### 9.3 Docstring

```python
def execute(self, spans: list[SpanIR]) -> FieldRouteIR:
    """Execute field routing.

    Args:
        spans: List of spans to route

    Returns:
        FieldRouteIR with routing results

    Raises:
        StageError: If routing fails
    """
```

### 9.4 导入顺序

```python
# 1. 标准库
import json
from dataclasses import asdict

# 2. 第三方库
from openai import OpenAI

# 3. 项目内部
from nl2spl.ir.span_ir import SpanIR
from nl2spl.pipeline.stages.base import PipelineStage
```

---

## 11. 项目状态

### 11.1 开发进度

| Sprint | 负责人 | 内容 | 状态 |
|--------|--------|------|------|
| Sprint 1 | A (Tech Lead) | 架构设计、基础设施 | ✅ 完成 |
| Sprint 2 | B (Pipeline Engineer) | Stage 1-3 实现 | ✅ 完成 |
| Sprint 3 | C (Flow Engineer) | Stage 4-5 实现 | ✅ 完成 |
| Sprint 4 | D (Resource Engineer) | Stage 6-7 实现 | ✅ 完成 |
| Sprint 5 | E (Compiler Engineer) | Stage 8-11 实现 | ✅ 完成 |
| Sprint 6 | 全员 | 集成测试 + 优化 | ✅ 完成 |

### 11.2 测试覆盖

- **单元测试**: 169 tests, 全部通过
- **集成测试**: 175 passed, 4 skipped
- **代码覆盖率**: >80%

### 11.3 代码质量

- **mypy**: 通过 (有6个非关键类型警告)
- **ruff**: 通过
- **文档**: 完整

### 11.4 版本信息

- **当前版本**: v0.1.0
- **发布日期**: 2026年5月
- **Python版本**: 3.10+
- **许可证**: MIT

### 11.5 已知问题

1. **Stage 6 变量解析警告**: LLM返回格式有时不符合预期，但pipeline仍能正常运行
2. **mypy类型警告**: 6个非关键类型警告，不影响运行时功能
3. **集成测试跳过**: 4个集成测试需要API密钥才能运行

### 11.6 未来计划

- **v0.2.0**: Prompt优化、性能提升
- **v0.3.0**: 支持更多SPL语法、错误处理完善
- **v1.0.0**: 生产就绪版本
