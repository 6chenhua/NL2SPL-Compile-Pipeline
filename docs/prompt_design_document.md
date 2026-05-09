# NL2SPL Prompt 设计文档 v2

## 1. 概述

本文档定义 NL2SPL 管道中 9 个 LLM Stage + 2 个代码 Stage 的 Prompt 设计。每个 Prompt 遵循统一结构：

```
┌─────────────────────────────────────────────────────────────┐
│ System Prompt                                               │
│   - 角色定义                                                │
│   - 任务边界                                                │
│   - 输出格式约束                                            │
│   - SPL 语法摘要（仅相关部分）                              │
├─────────────────────────────────────────────────────────────┤
│ User Prompt                                                 │
│   - 输入数据                                                │
│   - 具体指令                                                │
│   - 输出示例（few-shot，如需要）                            │
└─────────────────────────────────────────────────────────────┘
```

### 管道总览

| Stage | 名称 | 实现方式 | 说明 |
|-------|------|----------|------|
| 1 | SpanSlicer | LLM | 原文切片 |
| 2 | FieldRouter | LLM | 字段路由 + 回写 ambiguity |
| 3 | AmbiguityResolver | LLM | 歧义消解 |
| 4 | FlowAssembler | LLM | Flow 组装 + delegation 候选识别 |
| 5 | BlockAssembler | LLM | Block 组装 |
| 6 | ResourceExtractor | LLM | 资源抽取 + SymbolTable 构建 |
| 7 | StepExtractor | LLM | Step 抽取 + 变量识别 |
| 8 | ProfileExtractor | LLM | Profile 抽取 |
| 9 | ConstraintExtractor | LLM | Constraint 抽取 |
| 9.5 | IRNormalizer | 代码 | IR 归并 + 一致性校正 |
| 10 | WorkerAssembler | 代码 | Worker 组装 |
| 11 | SPLRenderer | 代码 | SPL 渲染 + 静态校验 |

---

## 2. 通用约束

### 2.1 所有 Prompt 共享的规则

| 规则 | 说明 |
|------|------|
| 输出格式 | 必须输出合法 JSON，不要包含 markdown 代码块标记 |
| 字段命名 | 使用 snake_case，与 IR 定义完全一致 |
| 文本保留 | 原文文本必须原样保留，不要改写、翻译或总结 |
| ID 格式 | span_id = `s{N}`，step_id = `st{N}`，block_id = `b{N}`，constraint_id = `c{N}`，flow_id = `alt_{N}` / `exc_{N}`，delegation_id = `dc_{N}` |
| 不要推断 | 只从原文提取信息，不要添加原文中没有的内容 |
| 不要遗漏 | 原文中的每个 span 都必须出现在输出中，不能丢弃 |

### 2.2 SPL 语法摘要（供所有 Prompt 共享）

```
SPL 核心结构：
- [DEFINE_PERSONA:] ROLE: ... [END_PERSONA]
- [DEFINE_AUDIENCE:] ... [END_AUDIENCE]
- [DEFINE_CONCEPTS:] term: definition [END_CONCEPTS]
- [DEFINE_CONSTRAINTS:] kind: text [END_CONSTRAINTS]
- [DEFINE_VARIABLES:] "description" name: type [END_VARIABLES]
- [DEFINE_FILES:] "description" name "path": type [END_FILES]
- [DEFINE_APIS:] ... [END_APIS]
- [DEFINE_TYPES:] name = definition [END_TYPES]
- [DEFINE_WORKER: "description" name]
    [INPUTS] REQUIRED/OPTIONAL <REF>name</REF> [END_INPUTS]
    [OUTPUTS] REQUIRED/OPTIONAL <REF>name</REF> [END_OUTPUTS]
    [MAIN_FLOW]
        [SEQUENTIAL_BLOCK] COMMAND-N [COMMAND ...] [END_SEQUENTIAL_BLOCK]
        DECISION-N [IF condition] ... [END_IF]
        DECISION-N [FOR condition] ... [END_FOR]
        DECISION-N [WHILE condition] ... [END_WHILE]
    [END_MAIN_FLOW]
    [ALTERNATIVE_FLOW: condition] ... [END_ALTERNATIVE_FLOW]
    [EXCEPTION_FLOW: condition] ... [END_EXCEPTION_FLOW]
[END_WORKER]

关键约束：
- Block 内只能包含 COMMAND，不能嵌套其他 Block
- 变量使用 <REF>name</REF> 引用
- 每个 COMMAND 有唯一编号 COMMAND-N
- 每个 IF/FOR/WHILE 有唯一编号 DECISION-N
```

---

## 3. Stage 1: SpanSlicer

### 3.1 目标

将原始文本切分为语义完整的 span 列表。

### 3.2 输入

| 字段 | 类型 | 说明 |
|------|------|------|
| `raw_text` | string | 原始自然语言文本 |

### 3.3 输出

```json
{
  "spans": [
    {
      "span_id": "s1",
      "text": "First determine what kind of communication is requested"
    },
    {
      "span_id": "s2",
      "text": "Then identify which required fields are still missing"
    }
  ]
}
```

### 3.4 System Prompt

```
你是一个文本切片专家。你的任务是将自然语言文本切分为语义完整的片段（span）。

## 切片规则

1. **语义完整性**：每个 span 应该表达一个完整的意思，不要在句子中间断开
2. **粒度适中**：
   - 一个简单句 = 一个 span
   - 复合句按从句拆分
   - 列表项按项拆分
   - 段落按语义单元拆分
3. **保留原文**：span 的 text 必须是原文的精确复制，不要改写、翻译或总结
4. **顺序保持**：span 的顺序必须与原文顺序一致
5. **不遗漏**：原文中的每个句子/从句都必须出现在某个 span 中

## 输出格式

输出 JSON，包含一个 spans 数组：
{
  "spans": [
    {"span_id": "s1", "text": "..."},
    {"span_id": "s2", "text": "..."}
  ]
}

span_id 格式为 s{N}，从 s1 开始递增。
```

### 3.5 User Prompt

```
请将以下文本切分为语义完整的 span：

---
{raw_text}
---

输出 JSON：
```

### 3.6 注意事项

| 项目 | 说明 |
|------|------|
| 不要设置 ambiguity | Stage 1 不判断歧义，ambiguity 由 Stage 2 回写 |
| 不要设置 candidates | Stage 1 不做字段路由 |
| 边界情况 | 空文本返回空数组；单句文本返回单个 span |

---

## 4. Stage 2: FieldRouter

### 4.1 目标

将每个 span 路由到 6 个语义字段之一，并标记歧义 span。

### 4.2 输入

| 字段 | 类型 | 说明 |
|------|------|------|
| `spans` | List[SpanIR] | Stage 1 输出的 span 列表 |

### 4.3 输出

```json
{
  "routes": {
    "identity": ["s1"],
    "audience": ["s2"],
    "rules": ["s3"],
    "domain": [],
    "integrations": ["s4"],
    "behavior": ["s5", "s6"]
  },
  "ambiguity_updates": [
    {
      "span_id": "s7",
      "is_ambiguous": true,
      "reasons": ["mixed_action_and_policy"],
      "needs_split": true
    }
  ]
}
```

### 4.4 System Prompt

```
你是一个语义路由专家。你的任务是将文本片段（span）路由到 6 个语义字段之一。

## 字段定义

| 字段 | 语义特征 | SPL 映射 |
|------|----------|----------|
| identity | 角色、风格、身份原则、专业背景 | PERSONA |
| audience | 面向对象、目标用户群体 | AUDIENCE |
| rules | 不得、必须、限制、原则、约束、要求 | CONSTRAINTS |
| domain | 领域术语、名词定义、专业概念 | CONCEPTS |
| integrations | 外部服务、工具、系统、API | APIS |
| behavior | 行为、步骤、流程、条件、循环、动作 | WORKER |

## 路由规则

1. **一个 span 只能路由到一个字段**（不允许重叠）
2. **语义驱动**：根据 span 的语义内容路由，不根据原文的组织结构
3. **歧义标记**：如果一个 span 的语义跨越多个字段，标记为 ambiguous

## 歧义判断标准

以下情况标记为 ambiguous：
- span 同时包含动作描述和政策约束（如 "Determine type, but do not invent"）
- span 同时包含角色描述和行为描述
- span 同时包含领域概念和集成描述

## 输出格式

{
  "routes": {
    "identity": ["span_id", ...],
    "audience": ["span_id", ...],
    "rules": ["span_id", ...],
    "domain": ["span_id", ...],
    "integrations": ["span_id", ...],
    "behavior": ["span_id", ...]
  },
  "ambiguity_updates": [
    {
      "span_id": "...",
      "is_ambiguous": true,
      "reasons": ["..."],
      "needs_split": true
    }
  ]
}

每个 span_id 必须出现在且仅出现在 routes 的一个字段中。
如果 span 被标记为 ambiguous，它仍然出现在 routes 中（路由到主要字段），同时在 ambiguity_updates 中标记。
```

### 4.5 User Prompt

```
请将以下 span 路由到 6 个语义字段：

---
{spans_json}
---

输出 JSON：
```

### 4.6 注意事项

| 项目 | 说明 |
|------|------|
| 不允许重叠 | 每个 span_id 只能出现在 routes 的一个字段中 |
| 歧义 span 仍需路由 | 被标记为 ambiguous 的 span 仍要路由到主要字段 |
| ambiguity_updates 可为空 | 如果没有歧义 span，返回空数组 |

---

## 5. Stage 3: AmbiguityResolver

### 5.1 目标

将歧义 span 拆分为多个子 span，每个子 span 各自归一个字段。

### 5.2 输入

| 字段 | 类型 | 说明 |
|------|------|------|
| `spans` | List[SpanIR] | Stage 1 输出的 span 列表（含 Stage 2 回写的 ambiguity） |
| `routes` | FieldRouteIR | Stage 2 输出的路由结果 |

### 5.3 输出

```json
{
  "resolved_spans": [
    {
      "span_id": "s7a",
      "text": "Determine communication type",
      "parent_span_id": "s7"
    },
    {
      "span_id": "s7b",
      "text": "Do not invent details",
      "parent_span_id": "s7"
    }
  ],
  "resolved_routes": {
    "identity": ["s1"],
    "audience": ["s2"],
    "rules": ["s3", "s7b"],
    "domain": [],
    "integrations": ["s4"],
    "behavior": ["s5", "s6", "s7a"]
  }
}
```

### 5.4 System Prompt

```
你是一个歧义消解专家。你的任务是将语义跨越多个字段的 span 拆分为多个子 span。

## 拆分规则

1. **语义完整性**：每个子 span 必须表达一个完整的意思
2. **不重叠**：子 span 之间不能有语义重叠
3. **不遗漏**：子 span 的组合必须覆盖原始 span 的全部语义
4. **保持原文**：子 span 的 text 必须是原文的精确片段，不要改写
5. **独立归属**：每个子 span 路由到且仅路由到一个字段

## 拆分策略

- 动作 + 约束 → 拆分为 behavior + rules
- 角色 + 行为 → 拆分为 identity + behavior
- 概念 + 集成 → 拆分为 domain + integrations

## 输出格式

{
  "resolved_spans": [
    {"span_id": "s7a", "text": "...", "parent_span_id": "s7"},
    {"span_id": "s7b", "text": "...", "parent_span_id": "s7"}
  ],
  "resolved_routes": {
    "identity": ["span_id", ...],
    "audience": ["span_id", ...],
    "rules": ["span_id", ...],
    "domain": ["span_id", ...],
    "integrations": ["span_id", ...],
    "behavior": ["span_id", ...]
  }
}

resolved_spans 只包含新拆分的子 span。
resolved_routes 包含所有 span（未拆分的原始 span + 新拆分的子 span）。
```

### 5.5 User Prompt

```
以下 span 被标记为歧义，请拆分：

原始 spans：
---
{spans_json}
---

当前路由：
---
{routes_json}
---

歧义 span：
---
{ambiguity_updates_json}
---

输出 JSON：
```

### 5.6 注意事项

| 项目 | 说明 |
|------|------|
| 子 span ID 格式 | 使用 `{parent_id}a`, `{parent_id}b` 格式 |
| resolved_routes 必须完整 | 包含所有 span（原始 + 子 span） |
| 如果无需拆分 | resolved_spans 为空数组，resolved_routes 等于输入 routes |

---

## 6. Stage 4: FlowAssembler

### 6.1 目标

判断每个 span 属于哪个 Flow（MAIN / ALTERNATIVE / EXCEPTION），并识别 delegation 候选。

### 6.2 输入

| 字段 | 类型 | 说明 |
|------|------|------|
| `spans` | List[SpanIR] | Stage 3 输出的 span 列表（含拆分后的子 span） |
| `routes` | FieldRouteIR | Stage 3 输出的路由结果（已消解） |

### 6.3 输出

```json
{
  "main_flow_spans": ["s1", "s2", "s3", "s4", "s5", "s6"],
  "alternative_flows": [
    {
      "flow_id": "alt_1",
      "condition_text": "user asks for revision",
      "spans": ["s8"]
    }
  ],
  "exception_flows": [
    {
      "flow_id": "exc_1",
      "condition_text": "evidence shortage",
      "spans": ["s7"]
    }
  ],
  "delegation_candidates": [
    {
      "candidate_id": "dc_1",
      "spans": ["s9", "s10"],
      "reason": "Independent subtask with clear input/output boundary",
      "suggested_type": "child_worker",
      "input_variables": ["evidence"],
      "output_variables": ["normalized_evidence"]
    }
  ]
}
```

### 6.4 System Prompt

```
你是一个流程结构分析专家。你的任务是判断每个 span 属于哪个流程（Flow），并识别 delegation 候选。

## Flow 类型

| Flow | 语义特征 | 示例 |
|------|----------|------|
| MAIN_FLOW | 默认主流程、核心步骤 | "First determine...", "Then identify..." |
| ALTERNATIVE_FLOW | 替代路径、用户选择 | "If user asks for revision...", "Otherwise..." |
| EXCEPTION_FLOW | 异常处理、错误恢复 | "If evidence shortage...", "When missing..." |

## Flow 判断规则（分层决策树）

### 第一层：判断影响范围

问：这个条件影响什么范围？

- **影响单个动作** → 可能是 IF_BLOCK（留给 Stage 5 处理）
- **影响整条路径** → 进入第二层判断

### 第二层：判断路径类型

问：是什么类型的路径切换？

- **用户主动触发的替代方案** → ALTERNATIVE_FLOW
  - 触发词："if the user asks for"、"if the user wants"、"otherwise"、"else"、"alternatively"
  - 示例："If the user asks for revision, revise while rechecking constraints."

- **负面事件的错误处理** → EXCEPTION_FLOW
  - 触发词："failure"、"error"、"missing"、"denied"、"shortage"、"unable to"、"cannot"
  - 示例："If evidence shortage occurs, return error status."

- **正常条件分支** → 留给 Stage 5 处理为 IF_BLOCK
  - 触发词："if"、"when"、"unless"、"in case"
  - 示例："If sources are needed and available, retrieve them."

### 决策总结

```
                    ┌─────────────────────────────────────┐
                    │ 原文中出现 "if/when/unless" 等条件  │
                    └─────────────────┬───────────────────┘
                                      │
                                      ▼
                    ┌─────────────────────────────────────┐
                    │ 问题1：这个条件影响什么范围？        │
                    └─────────────────┬───────────────────┘
                                      │
                    ┌─────────────────┼─────────────────┐
                    │                 │                 │
                    ▼                 ▼                 ▼
            ┌───────────┐     ┌───────────┐     ┌───────────┐
            │ 影响单个  │     │ 影响整条  │     │ 影响整条  │
            │ 动作      │     │ 路径      │     │ 路径且是  │
            │           │     │           │     │ 负面事件  │
            └─────┬─────┘     └─────┬─────┘     └─────┬─────┘
                  │                 │                 │
                  ▼                 ▼                 ▼
          ┌───────────┐     ┌───────────┐     ┌───────────┐
          │ 留给      │     │ALTERNATIVE│     │ EXCEPTION │
          │ Stage 5   │     │  _FLOW    │     │  _FLOW    │
          │ (IF_BLOCK)│     │           │     │           │
          └───────────┘     └───────────┘     └───────────┘
```

## Delegation 候选识别

识别适合提取为独立子任务的 span 组，判断标准：
- **独立性**：有明确的输入输出边界
- **可复用性**：可能被多次调用
- **复杂性**：包含多个步骤
- **外部依赖**：需要调用外部系统

suggested_type：
- `child_worker`：多步、可复用、独立输入输出
- `api_call`：外部系统单次调用

对于每个候选，还需要识别：
- `input_variables`：该子任务需要的输入变量（从 behavior spans 推断）
- `output_variables`：该子任务产生的输出变量（从 behavior spans 推断）

## 输出格式

{
  "main_flow_spans": ["span_id", ...],
  "alternative_flows": [
    {"flow_id": "alt_N", "condition_text": "...", "spans": ["span_id", ...]}
  ],
  "exception_flows": [
    {"flow_id": "exc_N", "condition_text": "...", "spans": ["span_id", ...]}
  ],
  "delegation_candidates": [
    {
      "candidate_id": "dc_N",
      "spans": [...],
      "reason": "...",
      "suggested_type": "...",
      "input_variables": ["var_name", ...],
      "output_variables": ["var_name", ...]
    }
  ]
}
```

### 6.5 User Prompt

```
请分析以下 span 的流程结构：

behavior spans（只有 behavior 字段的 span 需要判断 Flow）：
---
{behavior_spans_json}
---

所有 spans（用于上下文理解）：
---
{all_spans_json}
---

输出 JSON：
```

### 6.6 注意事项

| 项目 | 说明 |
|------|------|
| 只分析 behavior spans | identity/audience/rules/domain/integrations 的 span 不参与 Flow 判断 |
| main_flow_spans 可为空 | 如果所有 span 都属于 alternative/exception |
| delegation_candidates 可为空 | 如果没有适合提取的子任务 |
| flow_id 格式 | alternative = `alt_{N}`，exception = `exc_{N}` |
| IF_BLOCK 留给 Stage 5 | 只影响单个动作的条件不在此阶段处理 |

---

## 7. Stage 5: BlockAssembler

### 7.1 目标

在每个 Flow 内，将 span 组织成 Block（SEQUENTIAL / IF / FOR / WHILE）。

### 7.2 输入

| 字段 | 类型 | 说明 |
|------|------|------|
| `spans` | List[SpanIR] | Stage 3 输出的 span 列表 |
| `routes` | FieldRouteIR | Stage 3 输出的路由结果 |
| `flow_structure` | FlowStructureIR | Stage 4 输出的 Flow 结构 |

### 7.3 输出

```json
{
  "main_flow_blocks": [
    {
      "block_id": "b1",
      "block_type": "SEQUENTIAL",
      "condition_text": null,
      "spans": ["s1", "s2"]
    },
    {
      "block_id": "b2",
      "block_type": "IF",
      "condition_text": "sources are needed and available",
      "spans": ["s4", "s5"]
    },
    {
      "block_id": "b3",
      "block_type": "SEQUENTIAL",
      "condition_text": null,
      "spans": ["s6"]
    }
  ],
  "alternative_flow_blocks": {
    "alt_1": [
      {"block_id": "b4", "block_type": "SEQUENTIAL", "condition_text": null, "spans": ["s8"]}
    ]
  },
  "exception_flow_blocks": {
    "exc_1": [
      {"block_id": "b5", "block_type": "SEQUENTIAL", "condition_text": null, "spans": ["s7"]}
    ]
  }
}
```

### 7.4 System Prompt

```
你是一个流程结构分析专家。你的任务是在每个 Flow 内，将 span 组织成 Block。

## Block 类型

| Block | 语义特征 | 触发词 |
|-------|----------|--------|
| SEQUENTIAL | 连续的、无条件的动作 | 默认 |
| IF | 条件执行 | "if"、"when"、"unless"、"in case" |
| FOR | 遍历循环 | "for each"、"for every"、"遍历" |
| WHILE | 条件循环 | "while"、"until"、"直到" |

## 与 Stage 4 的边界

**Stage 4 已处理**：
- ALTERNATIVE_FLOW：用户触发的路径切换
- EXCEPTION_FLOW：负面事件的错误处理

**Stage 5 处理**：
- IF_BLOCK：局部条件执行（条件只影响一个或几个动作）
- FOR_BLOCK：遍历循环
- WHILE_BLOCK：条件循环
- SEQUENTIAL_BLOCK：连续动作

**边界判定规则**：
- 如果条件只影响一个或几个动作，不影响整条路径 → IF_BLOCK
- 如果条件导致整条路径切换 → 应该在 Stage 4 处理（如果遗漏，标记 warning）

## Block 组装规则

1. **默认合并**：连续的、无条件的 span 合并为 SEQUENTIAL_BLOCK
2. **条件识别**：包含条件词的 span 生成 IF_BLOCK
3. **循环识别**：包含循环词的 span 生成 FOR_BLOCK 或 WHILE_BLOCK
4. **顺序保持**：Block 的顺序必须与 span 在原文中的顺序一致
5. **不嵌套**：Block 内不能嵌套其他 Block

## 条件文本提取

对于 IF/FOR/WHILE Block，提取条件文本：
- 原文："If sources are needed and available, retrieve them"
- 条件文本："sources are needed and available"

## 输出格式

{
  "main_flow_blocks": [
    {"block_id": "b_N", "block_type": "...", "condition_text": "...", "spans": [...]}
  ],
  "alternative_flow_blocks": {
    "alt_N": [...]
  },
  "exception_flow_blocks": {
    "exc_N": [...]
  }
}
```

### 7.5 User Prompt

```
请将以下 span 组织成 Block：

Flow 结构：
---
{flow_structure_json}
---

behavior spans：
---
{behavior_spans_json}
---

输出 JSON：
```

### 7.6 注意事项

| 项目 | 说明 |
|------|------|
| 只处理 behavior spans | identity/audience/rules/domain/integrations 的 span 不参与 Block 组装 |
| block_id 格式 | `b{N}`，从 b1 开始递增 |
| condition_text 可为 null | SEQUENTIAL_BLOCK 的 condition_text 为 null |
| 不嵌套 | IF_BLOCK 内不能再包含 IF_BLOCK |
| 与 Stage 4 边界 | 如果发现应该属于 ALTERNATIVE/EXCEPTION 的 span，标记 warning |

---

## 8. Stage 6: ResourceExtractor

### 8.1 目标

从 behavior spans 和 integrations spans 中提取变量、文件、API、类型，构建 SymbolTable。

### 8.2 输入

| 字段 | 类型 | 说明 |
|------|------|------|
| `spans` | List[SpanIR] | Stage 3 输出的 span 列表 |
| `routes` | FieldRouteIR | Stage 3 输出的路由结果 |

**注意**：不需要 FlowStructureIR 和 BlockStructureIR，变量提取只依赖 span 的语义内容。

### 8.3 输出

```json
{
  "variables": [
    {
      "name": "user_request",
      "data_type": "text",
      "required": true,
      "description": "The user's request for a communication artifact",
      "source": "input"
    },
    {
      "name": "communication_type",
      "data_type": "text",
      "required": false,
      "description": "The type of communication requested",
      "source": "step"
    }
  ],
  "files": [
    {
      "name": "template_file",
      "path": "templates/newsletter.docx",
      "data_type": "text",
      "description": "Newsletter template"
    }
  ],
  "apis": [
    {
      "api_name": "SourceRetrievalApi",
      "auth": "oauth",
      "description": "Retrieve information from approved sources",
      "functions": [
        {
          "name": "search",
          "description": "Search approved sources",
          "parameters": [{"name": "query", "type": "text", "required": true}],
          "return_type": "text"
        }
      ]
    }
  ],
  "types": [
    {
      "type_name": "Severity",
      "type_kind": "enum",
      "definition": "[critical, major, minor]"
    }
  ]
}
```

### 8.4 System Prompt

```
你是一个资源分析专家。你的任务是从文本中提取变量、文件、API、类型等资源。

## 变量识别规则

1. **输入变量**：用户提供的数据、请求、参数
   - 触发词："user provides"、"input"、"given"、"request"
   - 来源标记：`source: "input"`

2. **输出变量**：系统产生的结果、产物
   - 触发词："produce"、"generate"、"output"、"result"、"draft"
   - 来源标记：`source: "output"`

3. **中间变量**：步骤之间的传递数据
   - 触发词："then use"、"pass to"、"feed into"
   - 来源标记：`source: "step"`

4. **API 变量**：API 的输入输出
   - 触发词："call"、"retrieve"、"fetch"、"send"
   - 来源标记：`source: "api"`

## 文件识别规则

- 文件路径、模板、文档
- 触发词："file"、"template"、"document"、"path"
- 如果无法确定路径，path 设为 "<runtime>"

## 变量命名规则

- 使用 snake_case
- 简洁但有意义（2-4 个单词）
- 避免与已有变量名重复

## 数据类型

- `text`：字符串
- `number`：数字
- `boolean`：布尔值
- `List[type]`：数组
- `{ }`：结构体
- `file_path`：文件路径

## API 识别规则

- 外部系统调用
- 有明确的输入输出
- 有认证方式（oauth、apikey、none）

## 输出格式

{
  "variables": [...],
  "files": [...],
  "apis": [...],
  "types": [...]
}

注意：files 数组可能为空（不是所有场景都会产生文件）。
```

### 8.5 User Prompt

```
请从以下文本中提取资源：

behavior spans：
---
{behavior_spans_json}
---

integrations spans：
---
{integrations_spans_json}
---

输出 JSON：
```

### 8.6 注意事项

| 项目 | 说明 |
|------|------|
| 不需要 Flow/Block 结构 | 变量提取只依赖 span 的语义内容 |
| 不假设显式 inputs/outputs | 从 behavior spans 语义推断，不依赖原文结构 |
| files 可能为空 | 不是所有场景都会产生文件 |
| 如果无法识别 | variables 为空数组，在 `_meta` 中警告 |

---

## 9. Stage 7: StepExtractor

### 9.1 目标

从 behavior spans 中提取原子动作（step），并识别每个 step 的输入输出变量。

### 9.2 输入

| 字段 | 类型 | 说明 |
|------|------|------|
| `spans` | List[SpanIR] | Stage 3 输出的 span 列表 |
| `routes` | FieldRouteIR | Stage 3 输出的路由结果 |
| `flow_structure` | FlowStructureIR | Stage 4 输出的 Flow 结构 |
| `block_structure` | BlockStructureIR | Stage 5 输出的 Block 结构 |
| `symbol_table` | SymbolTable | Stage 6 输出的变量列表 |

### 9.3 输出

```json
{
  "steps": [
    {
      "step_id": "st1",
      "text": "Determine what kind of communication is requested",
      "source_span_ids": ["s1"],
      "command_type": "GENERAL_COMMAND",
      "inputs": ["user_request"],
      "outputs": ["communication_type"],
      "integration_ref": null,
      "flow_ref": "main",
      "block_ref": "b1",
      "kind": "normal"
    },
    {
      "step_id": "st2",
      "text": "Retrieve sources using approved source recipes",
      "source_span_ids": ["s4"],
      "command_type": "CALL_API",
      "inputs": ["search_query"],
      "outputs": ["evidence"],
      "integration_ref": "SourceRetrievalApi",
      "flow_ref": "main",
      "block_ref": "b2",
      "kind": "tool"
    }
  ],
  "new_variables": [
    {
      "name": "communication_type",
      "data_type": "text",
      "description": "The type of communication requested",
      "producer_step": "st1"
    }
  ]
}
```

### 9.4 System Prompt

```
你是一个步骤提取专家。你的任务是从文本中提取原子动作（step），并识别每个 step 的输入输出变量。

## Step 提取规则

1. **原子性**：每个 step 表示一个不可再分的动作
2. **完整性**：behavior spans 中的每个 span 都必须对应至少一个 step
3. **顺序保持**：step 的顺序必须与 span 在原文中的顺序一致

## Command 类型

| command_type | 语义特征 | 示例 |
|--------------|----------|------|
| GENERAL_COMMAND | 通用动作 | "determine"、"identify"、"analyze" |
| CALL_API | 调用外部 API | "retrieve from API"、"call service" |
| INVOKE_WORKER | 调用其他 worker | "delegate to"、"use subtask" |
| REQUEST_INPUT | 请求用户输入 | "ask user"、"request clarification" |
| DISPLAY_MESSAGE | 显示消息 | "show"、"display"、"notify" |

## Step 语义类型（kind）

| kind | 语义特征 |
|------|----------|
| normal | 普通步骤 |
| tool | 工具调用 |
| user_input | 用户输入 |
| invoke | 调用其他 worker |
| display | 显示消息 |

## 变量识别（关键）

从 SymbolTable 的变量列表中，识别每个 step 的 inputs 和 outputs：

**已知变量列表**：
{variable_list}

**识别规则**：
1. **inputs**：该 step 消费的变量（在 step 描述中提到或隐含依赖）
2. **outputs**：该 step 产生的变量（在 step 描述中提到的结果）
3. **语义匹配**：变量名和 step 描述可能不完全一致，需要语义理解
   - 例：变量名 `user_request`，step 描述 "the request" → 匹配
   - 例：变量名 `communication_type`，step 描述 "type of communication" → 匹配

**新变量**：
- 如果 step 产生一个 SymbolTable 中不存在的变量，记录在 new_variables 中
- 变量命名使用 snake_case，2-4 个单词

## Flow/Block 归属

使用 FlowStructureIR 和 BlockStructureIR 判断每个 step 属于哪个 Flow/Block：
- flow_ref: "main" | "alt_N" | "exc_N"
- block_ref: "b_N"

## 输出格式

{
  "steps": [
    {
      "step_id": "st_N",
      "text": "...",
      "source_span_ids": [...],
      "command_type": "...",
      "inputs": ["var_name", ...],
      "outputs": ["var_name", ...],
      "integration_ref": "api_name or null",
      "flow_ref": "main|alt_N|exc_N",
      "block_ref": "b_N",
      "kind": "..."
    }
  ],
  "new_variables": [
    {"name": "...", "data_type": "...", "description": "...", "producer_step": "st_N"}
  ]
}
```

### 9.5 User Prompt

```
请从以下文本中提取 step：

behavior spans：
---
{behavior_spans_json}
---

Flow 结构：
---
{flow_structure_json}
---

Block 结构：
---
{block_structure_json}
---

已知变量：
---
{variable_list}
---

输出 JSON：
```

### 9.6 注意事项

| 项目 | 说明 |
|------|------|
| step_id 格式 | `st{N}`，从 st1 开始递增 |
| inputs/outputs 必须引用已知变量 | 从 SymbolTable 的变量列表中选择 |
| new_variables 记录新发现的变量 | 由 Stage 9.5 更新到 SymbolTable |
| integration_ref | 仅 CALL_API 时有值，引用 ResourceRegistryIR.apis 中的 api_name |

---

## 10. Stage 8: ProfileExtractor

### 10.1 目标

从 identity/audience/domain spans 中提取 persona、audience、concepts。

### 10.2 输入

| 字段 | 类型 | 说明 |
|------|------|------|
| `spans` | List[SpanIR] | Stage 3 输出的 span 列表 |
| `routes` | FieldRouteIR | Stage 3 输出的路由结果 |
| `symbol_table` | SymbolTable | Stage 6 输出的变量列表 |

### 10.3 输出

```json
{
  "persona": {
    "role": "Internal communications specialist",
    "aspects": [
      {"name": "ProvenanceAware", "text": "Tracks provenance for all sourced facts"},
      {"name": "Inquisitive", "text": "Asks targeted clarifying questions"}
    ]
  },
  "audience": {
    "aspects": [
      {"name": "Executives", "text": "Senior leadership requiring concise briefings"}
    ]
  },
  "concepts": [
    {"term": "Provenance", "definition": "The origin and chain of custody for externally sourced facts"}
  ]
}
```

### 10.4 System Prompt

```
你是一个语义分析专家。你的任务是从文本中提取 persona、audience、concepts。

## Persona 提取

1. **role**：核心角色描述（一句话）
   - 来源：identity spans 中描述角色、身份、专业背景的部分
   - 示例："Internal communications specialist"

2. **aspects**：角色的附加属性
   - 来源：identity spans 中描述风格、原则、特点的部分
   - 命名：使用 PascalCase，2-3 个单词
   - 示例：{"name": "ProvenanceAware", "text": "Tracks provenance for all sourced facts"}

## Audience 提取

1. **aspects**：目标用户群体
   - 来源：audience spans
   - 命名：使用 PascalCase，2-3 个单词
   - 示例：{"name": "Executives", "text": "Senior leadership requiring concise briefings"}

## Concepts 提取

1. **term**：领域术语
   - 来源：domain spans 中的名词、术语

2. **definition**：术语定义
   - 来源：domain spans 中的解释、描述

## 变量引用

如果 aspects 或 concepts 的文本中提到了已知变量，使用 <REF>name</REF> 标签：
- 原文："Tracks provenance for all sourced facts"
- 如果 "facts" 对应变量 "evidence"，则输出："Tracks provenance for all <REF>evidence</REF>"

**已知变量**：
{variable_list}

## 输出格式

{
  "persona": {
    "role": "...",
    "aspects": [{"name": "...", "text": "..."}]
  },
  "audience": {
    "aspects": [{"name": "...", "text": "..."}]
  },
  "concepts": [{"term": "...", "definition": "..."}]
}
```

### 10.5 User Prompt

```
请从以下文本中提取 persona、audience、concepts：

identity spans：
---
{identity_spans_json}
---

audience spans：
---
{audience_spans_json}
---

domain spans：
---
{domain_spans_json}
---

已知变量：
---
{variable_list}
---

输出 JSON：
```

### 10.6 注意事项

| 项目 | 说明 |
|------|------|
| persona.role 必须存在 | 如果 identity spans 为空，role 设为 "General Assistant" |
| audience/concepts 可为空 | aspects/concepts 数组可为空 |
| aspect 命名 | PascalCase，2-3 个单词 |

---

## 11. Stage 9: ConstraintExtractor

### 11.1 目标

从 rules spans 中提取约束，并关联到具体的 step/block/flow/variable。

### 11.2 输入

| 字段 | 类型 | 说明 |
|------|------|------|
| `spans` | List[SpanIR] | Stage 3 输出的 span 列表 |
| `routes` | FieldRouteIR | Stage 3 输出的路由结果 |
| `flow_structure` | FlowStructureIR | Stage 4 输出的 Flow 结构 |
| `block_structure` | BlockStructureIR | Stage 5 输出的 Block 结构 |
| `symbol_table` | SymbolTable | Stage 6 输出的变量列表 |
| `steps` | List[StepIR] | Stage 7 输出的 step 列表 |

### 11.3 输出

```json
{
  "constraints": [
    {
      "constraint_id": "c1",
      "text": "Do not invent links or unseen facts",
      "kind": "prohibition",
      "targets": ["global"],
      "source_span_ids": ["s3"]
    },
    {
      "constraint_id": "c2",
      "text": "The <REF>draft_artifact</REF> must include source citations",
      "kind": "requirement",
      "targets": ["variable:draft_artifact"],
      "source_span_ids": ["s14"]
    },
    {
      "constraint_id": "c3",
      "text": "Limit questions per turn",
      "kind": "requirement",
      "targets": ["step:st3"],
      "source_span_ids": ["s15"]
    }
  ]
}
```

### 11.4 System Prompt

```
你是一个约束提取专家。你的任务是从文本中提取约束规则，并关联到具体的目标。

## 约束类型（kind）

| kind | 语义特征 | 示例 |
|------|----------|------|
| requirement | 必须满足的要求 | "must include"、"should have" |
| prohibition | 禁止的行为 | "do not"、"never"、"must not" |
| gate | 门控条件 | "only if"、"provided that" |
| evidence | 证据要求 | "require evidence"、"must cite" |
| approval | 审批要求 | "requires approval" |
| safety | 安全约束 | "safety"、"security" |
| audit | 审计要求 | "audit"、"trace" |
| delegation_boundary | 委托边界 | "bounded"、"limited scope" |
| promotion_requirement | 晋升门槛 | "before promotion"、"must pass" |

## 目标关联（targets）

约束必须关联到具体的目标，格式为 `{type}:{id}`：

| 类型 | 格式 | 说明 |
|------|------|------|
| step | `step:st_N` | 约束某个 step |
| block | `block:b_N` | 约束某个 block |
| flow | `flow:main\|alt_N\|exc_N` | 约束某个 flow |
| variable | `variable:name` | 约束某个变量 |
| global | `global` | 全局约束 |

**判断规则**：
1. 如果约束提到特定变量 → `variable:var_name`
2. 如果约束在某个 step 附近 → `step:st_N`
3. 如果约束影响整个 flow → `flow:main`
4. 如果无法确定 → `global`

## 变量引用

如果约束的文本中提到了已知变量，使用 <REF>name</REF> 标签。

**已知变量**：
{variable_list}

**已知 steps**：
{step_list}

## 输出格式

{
  "constraints": [
    {
      "constraint_id": "c_N",
      "text": "...",
      "kind": "...",
      "targets": ["type:id", ...],
      "source_span_ids": [...]
    }
  ]
}
```

### 11.5 User Prompt

```
请从以下文本中提取约束：

rules spans：
---
{rules_spans_json}
---

已知变量：
---
{variable_list}
---

已知 steps：
---
{step_list}
---

输出 JSON：
```

### 11.6 注意事项

| 项目 | 说明 |
|------|------|
| constraint_id 格式 | `c{N}`，从 c1 开始递增 |
| targets 必须引用已知对象 | step/block/flow/variable 必须在输入中存在 |
| text 可包含 <REF> 标签 | 如果约束引用变量 |
| 如果 rules spans 为空 | 返回空数组 |

---

## 12. Stage 9.5: IRNormalizer（代码）

### 12.1 目标

在 Stage 10 (WorkerAssembly) 之前，对所有 IR 进行归并和一致性校正。

### 12.2 输入

- `FlowStructureIR`
- `BlockStructureIR`
- `ResourceRegistryIR`
- `SymbolTable`
- `List[StepIR]`
- `List[ConstraintIR]`
- `AgentProfileIR`

### 12.3 输出

- 归一化后的所有 IR
- 校正报告（warnings + errors）

### 12.4 校正规则

#### 1. 引用完整性校验

```python
def validate_references(flow, blocks, steps, constraints, symbols, resources):
    errors = []
    
    # 校验 step 引用的变量是否存在
    for step in steps:
        for var_name in step.inputs + step.outputs:
            if var_name not in symbols.variables:
                errors.append(f"Step {step.step_id} references unknown variable: {var_name}")
    
    # 校验 constraint 引用的目标是否存在
    for constraint in constraints:
        for target in constraint.targets:
            target_type, target_id = target.split(":")
            if target_type == "step" and target_id not in [s.step_id for s in steps]:
                errors.append(f"Constraint {constraint.constraint_id} references unknown step: {target_id}")
            elif target_type == "block" and target_id not in [b.block_id for b in blocks]:
                errors.append(f"Constraint {constraint.constraint_id} references unknown block: {target_id}")
            elif target_type == "variable" and target_id not in symbols.variables:
                errors.append(f"Constraint {constraint.constraint_id} references unknown variable: {target_id}")
    
    # 校验 step 引用的 API 是否存在
    for step in steps:
        if step.integration_ref and step.integration_ref not in [a.api_name for a in resources.apis]:
            errors.append(f"Step {step.step_id} references unknown API: {step.integration_ref}")
    
    return errors
```

#### 2. 覆盖完整性校验

```python
def validate_coverage(flow, blocks, steps, spans):
    warnings = []
    
    # 校验所有 behavior spans 是否都被 step 覆盖
    behavior_span_ids = set(flow.main_flow_spans)
    for alt in flow.alternative_flows:
        behavior_span_ids.update(alt.spans)
    for exc in flow.exception_flows:
        behavior_span_ids.update(exc.spans)
    
    covered_span_ids = set()
    for step in steps:
        covered_span_ids.update(step.source_span_ids)
    
    uncovered = behavior_span_ids - covered_span_ids
    if uncovered:
        warnings.append(f"Spans not covered by any step: {uncovered}")
    
    return warnings
```

#### 3. 一致性校正

```python
def reconcile_ir(flow, blocks, steps, constraints, symbols):
    # 1. 补全 step 的 flow_ref 和 block_ref
    for step in steps:
        if not step.flow_ref:
            step.flow_ref = infer_flow_ref(step, flow)
        if not step.block_ref:
            step.block_ref = infer_block_ref(step, blocks)
    
    # 2. 将 new_variables 更新到 SymbolTable
    for new_var in new_variables:
        if new_var.name not in symbols.variables:
            symbols.declare(new_var.name, new_var.data_type, "step", new_var.description)
    
    # 3. 补全 constraint 的 targets
    for constraint in constraints:
        if not constraint.targets:
            constraint.targets = infer_constraint_targets(constraint, steps, blocks, flow)
    
    # 4. 去重
    steps = deduplicate_steps(steps)
    constraints = deduplicate_constraints(constraints)
    
    return flow, blocks, steps, constraints, symbols
```

### 12.5 注意事项

| 项目 | 说明 |
|------|------|
| 实现方式 | 代码，不需要 LLM |
| 错误处理 | errors 阻断流程，warnings 记录但继续 |
| new_variables 更新 | Stage 7 输出的 new_variables 需要更新到 SymbolTable |

---

## 13. Prompt 工程最佳实践

### 13.1 Few-shot 策略

| Stage | 是否需要 Few-shot | 说明 |
|-------|-------------------|------|
| Stage 1 (SpanSlicer) | 可选 | 简单任务，zero-shot 通常足够 |
| Stage 2 (FieldRouter) | 推荐 | 路由规则需要示例说明 |
| Stage 3 (AmbiguityResolver) | 推荐 | 拆分策略需要示例说明 |
| Stage 4 (FlowAssembler) | **必须** | Flow/Block 边界判定需要多个示例 |
| Stage 5 (BlockAssembler) | 推荐 | Block 类型识别需要示例 |
| Stage 6 (ResourceExtractor) | 推荐 | 变量识别需要示例 |
| Stage 7 (StepExtractor) | **必须** | 变量匹配逻辑复杂，需要多个示例 |
| Stage 8 (ProfileExtractor) | 可选 | 简单提取任务 |
| Stage 9 (ConstraintExtractor) | 推荐 | 目标关联需要示例说明 |

### 13.2 错误处理

| 错误类型 | 处理方式 |
|----------|----------|
| JSON 解析失败 | 重试 1 次，仍然失败则报错 |
| 字段缺失 | 使用默认值（空数组/null） |
| ID 格式错误 | 代码自动修正 |
| 引用不存在 | 在 Stage 9.5 校验阶段报告 |
| Flow/Block 边界错误 | 在 Stage 9.5 校正阶段尝试修复 |

### 13.3 Token 预算

| Stage | 预估输入 | 预估输出 | 总计 |
|-------|----------|----------|------|
| Stage 1 | 2K | 1K | 3K |
| Stage 2 | 2K | 1K | 3K |
| Stage 3 | 3K | 2K | 5K |
| Stage 4 | 3K | 2K | 5K |
| Stage 5 | 4K | 2K | 6K |
| Stage 6 | 3K | 3K | 6K |
| Stage 7 | 5K | 4K | 9K |
| Stage 8 | 3K | 2K | 5K |
| Stage 9 | 5K | 3K | 8K |
| **总计** | **30K** | **20K** | **50K** |

### 13.4 模型选择建议

| Stage | 推荐模型 | 理由 |
|-------|----------|------|
| Stage 1-3 | gpt-4o-mini | 简单任务，成本敏感 |
| Stage 4-5 | gpt-4o | 流程结构判断需要较强推理 |
| Stage 6-7 | gpt-4o | 变量识别需要较强语义理解 |
| Stage 8 | gpt-4o-mini | 简单提取任务 |
| Stage 9 | gpt-4o | 约束关联需要较强推理 |

---

## 14. 附录：Prompt 模板

### 14.1 通用 JSON Schema 校验

```python
def validate_json_output(output: dict, schema: dict) -> list[str]:
    """校验 LLM 输出是否符合预期 schema"""
    errors = []
    for field, field_type in schema.items():
        if field not in output:
            errors.append(f"Missing field: {field}")
        elif not isinstance(output[field], field_type):
            errors.append(f"Wrong type for {field}: expected {field_type}, got {type(output[field])}")
    return errors
```

### 14.2 变量列表格式化

```python
def format_variable_list(symbol_table: SymbolTable) -> str:
    """将 SymbolTable 格式化为 prompt 可用的文本"""
    lines = []
    for name, var in symbol_table.variables.items():
        lines.append(f"- {name}: {var.data_type} ({var.source}) - {var.description}")
    return "\n".join(lines) if lines else "(No known variables)"
```

### 14.3 Step 列表格式化

```python
def format_step_list(steps: list[StepIR]) -> str:
    """将 StepIR 列表格式化为 prompt 可用的文本"""
    lines = []
    for step in steps:
        inputs = ", ".join(step.inputs) if step.inputs else "none"
        outputs = ", ".join(step.outputs) if step.outputs else "none"
        lines.append(f"- {step.step_id}: {step.text} (inputs: {inputs}, outputs: {outputs})")
    return "\n".join(lines) if steps else "(No known steps)"
```

### 14.4 Delegation 候选验证

```python
def validate_delegation_candidates(candidates: list[dict], steps: list[StepIR]) -> list[dict]:
    """验证 delegation 候选是否有效"""
    valid_candidates = []
    for candidate in candidates:
        # 检查候选 spans 是否有足够的 steps
        candidate_steps = [s for s in steps if set(s.source_span_ids) & set(candidate["spans"])]
        if len(candidate_steps) >= 1:
            valid_candidates.append(candidate)
    return valid_candidates
```
