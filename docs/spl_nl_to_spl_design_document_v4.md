# 结构化自然语言到 SPL 的编译式转换方案 v4

## 1. 目标

本方案用于将自然语言需求文档转换为 SPL（Structured Prompt Language）代码。

**输入**：自然语言文档（通常包含7个固定部分，但系统不依赖此结构）：
1. Task family
2. Inputs for each run
3. Required outputs
4. Reusable process
5. Policies
6. Failure handling
7. Delegation policy

**输出**：符合 SPL 语法规范的代码。

**核心理念**：系统目标不是让大模型直接生成最终 SPL，而是将其作为**语义分析器**，输出可供代码编译器消费的中间表示（IR）。最终 SPL 由代码模板、静态合并和校验生成。

---

## 2. 设计原则

### 2.1 模型负责语义，代码负责结构

大模型适合处理：
- 文本切片
- 字段路由（语义分类）
- 歧义识别与消解
- Flow/Block 结构判断
- step 拆分
- resource 语义抽取
- 变量识别

代码适合处理：
- 编号
- 去重
- 变量/文件/API 注册
- 结构拼装
- 引用校验
- 语法校验
- SPL 渲染

### 2.2 框架与输入结构无关

系统不假设输入文本的组织结构。7字段格式只是用户输入的便利格式，系统根据**语义内容**进行路由，而非根据字段名称。

### 2.3 自顶向下分解

设计过程遵循 SPL WORKER 的结构：
1. 先确定 Flow（MAIN / ALTERNATIVE / EXCEPTION）
2. 再确定每个 Flow 中的 Block（SEQUENTIAL / IF / FOR / WHILE）
3. 最后填充 Step（具体动作）

### 2.4 IR 只保留编译必需信息

不要把所有推断都固化为字段。只保留后续编译需要的信息，避免冗余。

### 2.5 Block 不嵌套 Block

根据 SPL 语法，`SEQUENTIAL_BLOCK` 内只能包含 `COMMAND`，不应再包含其他 `BLOCK`（如 `IF_BLOCK`）。编译器保证不生成嵌套结构。

### 2.6 Constraint 不设 scope

`ConstraintIR` 不需要 scope 字段。约束是否全局、局部、作用于 step 或 flow，由引用关系和编译阶段决定。

### 2.7 "if" 先做语义分流，再映射到 SPL

自然语言中的 if 可能对应：
- `IF_BLOCK`（局部条件执行）
- `ALTERNATIVE_FLOW`（替代路径）
- `EXCEPTION_FLOW`（异常/恢复路径）
- `FOR/WHILE`（循环控制）

不能直接等价映射。

### 2.8 一个 span 只能属于一个字段

FieldRouteIR 中不允许 span 重叠。歧义 span 在 Stage 3 拆分为多个子 span，每个子 span 各自归一个字段。

---

## 3. 总体架构

### 3.1 流程总览

| Stage | 名称 | 实现方式 | 输入 | 输出 |
|-------|------|----------|------|------|
| 1 | 原文切片 | **LLM** | 原始文本 | List[SpanIR] |
| 2 | 字段路由 | **LLM** | List[SpanIR] | FieldRouteIR + 回写 SpanIR.ambiguity |
| 3 | 歧义消解 | **LLM** | FieldRouteIR + ambiguous spans | FieldRouteIR（消解后） |
| 4 | Flow 组装 | **LLM** | FieldRouteIR | FlowStructureIR |
| 5 | Block 组装 | **LLM** | FieldRouteIR + FlowStructureIR | BlockStructureIR |
| 6 | Resource 抽取 | **LLM** | FieldRouteIR + FlowStructureIR + BlockStructureIR | ResourceRegistryIR + SymbolTable |
| 7 | Step 抽取 | **LLM** | FieldRouteIR + FlowStructureIR + BlockStructureIR + SymbolTable | List[StepIR] + SymbolTable（更新） |
| 8 | Profile 抽取 | **LLM** | FieldRouteIR + SymbolTable | AgentProfileIR |
| 9 | Constraint 抽取 | **LLM** | FieldRouteIR + FlowStructureIR + BlockStructureIR + SymbolTable + List[StepIR] | List[ConstraintIR] |
| 10 | Worker 组装 | **代码** | FlowStructureIR + BlockStructureIR + List[StepIR] + ResourceRegistryIR + SymbolTable | WorkerIR |
| 11 | SPL 渲染 + 校验 | **代码** | WorkerIR + AgentProfileIR + ResourceRegistryIR + SymbolTable | SPL 文本 + 校验报告 |

### 3.2 分层角色

#### 语义层（Stage 1-9）
由大模型完成，输出 JSON IR。

#### 编译层（Stage 10）
由代码完成，负责将 IR 转换成 SPL 结构。

#### 渲染 + 校验层（Stage 11）
由代码完成，输出最终 SPL 文本并进行静态校验。

### 3.3 数据流图

```
原始文本
    │
    ▼
Stage 1: List[SpanIR] (ambiguity=false)
    │
    ▼
Stage 2: FieldRouteIR + 回写 SpanIR.ambiguity
    │
    ▼
Stage 3: FieldRouteIR (消解后，歧义 span 已拆分)
    │
    ▼
Stage 4: FlowStructureIR (含 delegation_candidates)
    │
    ▼
Stage 5: BlockStructureIR
    │
    ▼
Stage 6: ResourceRegistryIR + SymbolTable
    │
    ├─────────────────────────────────────────────┐
    │                                             │
    ▼                                             ▼
Stage 7: List[StepIR] + SymbolTable      Stage 8: AgentProfileIR
    │                                             │
    ▼                                             │
Stage 9: List[ConstraintIR] ◄─────────────────────┘
    │
    ▼
Stage 10: WorkerIR (代码组装)
    │
    ▼
Stage 11: SPL 文本 + 校验报告
```

---

## 4. IR 设计

### 4.1 SpanIR

**用途**：保存原文切片与歧义标记。

**字段**：
```json
{
  "span_id": "s1",
  "text": "Ask only the highest-value clarifying questions",
  "ambiguity": {
    "is_ambiguous": false,
    "reasons": [],
    "needs_split": false
  }
}
```

**字段说明**：
- `span_id`：由代码分配，格式为 `s{N}`
- `text`：原始文本片段，保持原文措辞
- `ambiguity`：标记该 span 是否存在语义歧义
  - `is_ambiguous`：是否歧义（**Stage 1 初始化为 false，Stage 2 回写**）
  - `reasons`：歧义原因列表
  - `needs_split`：是否需要拆分

**时序说明**：
- Stage 1（SpanSlicer）：生成 span，`ambiguity.is_ambiguous = false`
- Stage 2（FieldRouter）：路由后，如果发现 span 语义跨越多个字段，回写 `ambiguity.is_ambiguous = true`
- Stage 3（AmbiguityResolver）：消费 ambiguity 标记，拆分 span

---

### 4.2 FieldRouteIR

**用途**：将 span 路由到 6 个语义字段。

**预处理字段（固定6个）**：
- `identity`：角色、风格、身份原则 → 对应 SPL 的 PERSONA
- `audience`：面向对象 → 对应 SPL 的 AUDIENCE
- `rules`：不得、必须、限制、原则 → 对应 SPL 的 CONSTRAINTS
- `domain`：领域术语、名词定义 → 对应 SPL 的 CONCEPTS
- `integrations`：外部服务、工具、系统 → 对应 SPL 的 APIS
- `behavior`：行为、步骤、流程、条件、循环 → 对应 SPL 的 WORKER

**字段结构**：
```json
{
  "identity": ["s1", "s2"],
  "audience": ["s3"],
  "rules": ["s4", "s5"],
  "domain": ["s6"],
  "integrations": ["s7"],
  "behavior": ["s8", "s9", "s10"]
}
```

**说明**：
- **一个 span 只能属于一个字段**（不允许重叠）
- 歧义 span 在 Stage 3 拆分为子 span，子 span 各自归一个字段
- 路由是语义驱动的，不是结构驱动的

**路由规则**：

| 原文语义 | 路由目标 | SPL 映射 |
|----------|----------|----------|
| 角色、风格、身份原则 | identity | PERSONA |
| 面向对象 | audience | AUDIENCE |
| 不得、必须、限制、原则 | rules | CONSTRAINTS |
| 领域术语、名词定义 | domain | CONCEPTS |
| 外部服务、工具、系统 | integrations | APIS |
| 行为、步骤、流程、条件、循环 | behavior | WORKER |

**注意**：原始7字段中的任何内容都根据语义路由，而非根据字段名称。

---

### 4.3 FlowStructureIR

**用途**：判断哪些 span 属于哪个 Flow（MAIN / ALTERNATIVE / EXCEPTION），并识别 delegation 候选。

**字段结构**：
```json
{
  "main_flow_spans": ["s1", "s2", "s3", "s4", "s5", "s6"],
  "alternative_flows": [
    {
      "flow_id": "alt_1",
      "condition_text": "missing timeframe",
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
      "spans": ["s11", "s12"],
      "reason": "Independent subtask with clear input/output boundary",
      "suggested_type": "child_worker"
    }
  ]
}
```

**字段说明**：
- `main_flow_spans`：属于主流程的 span 列表
- `alternative_flows`：替代流程列表
  - `flow_id`：唯一标识，格式为 `alt_{N}`
  - `condition_text`：触发条件
  - `spans`：属于该流程的 span 列表
- `exception_flows`：异常流程列表
  - `flow_id`：唯一标识，格式为 `exc_{N}`
  - `condition_text`：触发条件
  - `spans`：属于该流程的 span 列表
- `delegation_candidates`：delegation 候选列表（由 Stage 4 的 LLM 识别）
  - `candidate_id`：唯一标识，格式为 `dc_{N}`
  - `spans`：相关的 span 列表
  - `reason`：为什么适合提取为子任务
  - `suggested_type`：建议类型（`child_worker` 或 `api_call`）

**判定规则**：
- 默认所有 span 属于 main_flow
- 如果 span 描述了"如果失败"、"如果缺少"、"当...发生时"等异常场景，归入 exception_flow
- 如果 span 描述了"否则"、"另一种方式"、"如果用户要求修改"等替代场景，归入 alternative_flow
- 如果 spans 描述了独立的子任务（有明确的输入输出边界），标记为 delegation_candidates

---

### 4.4 BlockStructureIR

**用途**：在每个 Flow 内，判断哪些 span 形成 Block（SEQUENTIAL / IF / FOR / WHILE）。

**字段结构**：
```json
{
  "main_flow_blocks": [
    {
      "block_id": "b1",
      "block_type": "SEQUENTIAL",
      "condition_text": null,
      "spans": ["s1", "s2", "s3"]
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
      {
        "block_id": "b4",
        "block_type": "SEQUENTIAL",
        "condition_text": null,
        "spans": ["s8"]
      }
    ]
  },
  "exception_flow_blocks": {
    "exc_1": [
      {
        "block_id": "b5",
        "block_type": "SEQUENTIAL",
        "condition_text": null,
        "spans": ["s7"]
      }
    ]
  }
}
```

**字段说明**：
- `main_flow_blocks`：主流程的 Block 列表
- `alternative_flow_blocks`：替代流程的 Block 列表（按 flow_id 索引）
- `exception_flow_blocks`：异常流程的 Block 列表（按 flow_id 索引）
- 每个 Block 包含：
  - `block_id`：唯一标识，格式为 `b{N}`
  - `block_type`：SEQUENTIAL / IF / FOR / WHILE
  - `condition_text`：条件描述（仅 IF/FOR/WHILE 时有值）
  - `spans`：属于该 Block 的 span 列表

**判定规则**：
- 连续的、无条件的 span 合并为 SEQUENTIAL_BLOCK
- 包含 "if"、"when"、"unless" 等条件词的 span 生成 IF_BLOCK
- 包含 "for each"、"while" 等循环词的 span 生成 FOR_BLOCK 或 WHILE_BLOCK

**编译器保证**：
- Block 不嵌套其他 Block
- 如果遇到嵌套情况（如 IF 内有 IF），将其扁平化或提取为独立 Block

---

### 4.5 AgentProfileIR

**用途**：生成 SPL 的 PERSONA / AUDIENCE / CONCEPTS 前置语义结构。

**字段结构**：
```json
{
  "persona": {
    "role": "资深软件工程师",
    "aspects": [
      {"name": "ProvenanceAware", "text": "Tracks origin of sourced facts"},
      {"name": "Inquisitive", "text": "Asks targeted clarifying questions"}
    ]
  },
  "audience": {
    "aspects": [
      {"name": "Executives", "text": "Senior leadership requiring concise briefings"},
      {"name": "InternalUsers", "text": "Employees requesting internal communications"}
    ]
  },
  "concepts": [
    {"term": "Provenance", "definition": "The origin and chain of custody for externally sourced facts"},
    {"term": "EvidenceCarrier", "definition": "Normalized format for delegated evidence"}
  ]
}
```

**字段说明**：
- `persona.role`：核心角色描述（一句话）
- `persona.aspects`：角色的附加属性（风格、原则等）
- `audience.aspects`：目标用户群体
- `concepts`：领域术语定义列表

**变量引用**：
- 如果 aspects 或 concepts 引用变量，使用 `<REF>name</REF>` 标签

**输出到 SPL**：
```spl
[DEFINE_PERSONA:]
    ROLE: 资深软件工程师
    ProvenanceAware: Tracks origin of sourced facts
    Inquisitive: Asks targeted clarifying questions
[END_PERSONA]

[DEFINE_AUDIENCE:]
    Executives: Senior leadership requiring concise briefings
    InternalUsers: Employees requesting internal communications
[END_AUDIENCE]

[DEFINE_CONCEPTS:]
    Provenance: The origin and chain of custody for externally sourced facts
    EvidenceCarrier: Normalized format for delegated evidence
[END_CONCEPTS]
```

---

### 4.6 ConstraintIR

**用途**：保存规则、限制、门控条件、审核要求。

**字段**：
```json
{
  "constraint_id": "c1",
  "text": "The <REF>draft_artifact</REF> must include source citations",
  "kind": "requirement",
  "targets": ["step:st5"],
  "source_span_ids": ["s14"]
}
```

**字段说明**：
- `constraint_id`：唯一标识，格式为 `c{N}`
- `text`：约束的自然语言描述（可包含 `<REF>` 标签）
- `kind`：约束类型
  - `requirement`：必须满足的要求
  - `prohibition`：禁止的行为
  - `gate`：门控条件（必须满足才能继续）
  - `evidence`：证据要求
  - `approval`：审批要求
  - `safety`：安全约束
  - `audit`：审计要求
  - `delegation_boundary`：委托边界
  - `promotion_requirement`：晋升门槛
- `targets`：约束的目标引用，格式为 `{type}:{id}`
  - `step:st1`：约束某个 step
  - `block:b1`：约束某个 block
  - `flow:main`：约束某个 flow
  - `worker:w1`：约束某个 worker
  - `variable:var_name`：约束某个变量
  - `global`：全局约束
- `source_span_ids`：来源 span 列表

**不建议字段**：
- scope（由 targets 决定）
- confidence（不需要）

**输出到 SPL**：
```spl
[DEFINE_CONSTRAINTS:]
    Evidence: Require evidence for sourced claims
    Safety: Do not invent links or unseen facts
[END_CONSTRAINTS]
```

---

### 4.7 ResourceRegistryIR

**用途**：统一管理变量、文件、API、类型。

**字段结构**：
```json
{
  "variables": [
    {
      "name": "user_request",
      "data_type": "text",
      "required": true,
      "description": "The user's request for a communication artifact",
      "source": "input",
      "flow_ref": "main",
      "block_ref": null,
      "producer": null,
      "consumers": ["st3", "st5"]
    }
  ],
  "files": [
    {
      "name": "template_file",
      "path": "templates/newsletter.docx",
      "data_type": "text",
      "description": "Newsletter template",
      "used_by": ["st8"]
    }
  ],
  "apis": [
    {
      "api_name": "SourceRetrievalApi",
      "auth": "oauth",
      "functions": [
        {
          "name": "search",
          "description": "Search approved sources",
          "parameters": [
            {"name": "query", "type": "text", "required": true}
          ],
          "return_type": "text"
        }
      ],
      "used_by_worker": "parent_worker"
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

**字段说明**：
- `variables`：变量列表
  - `source`：来源（input / output / step / api / file）
  - `flow_ref`：所属 Flow（main / alt_{N} / exc_{N}）
  - `block_ref`：所属 Block（可为 null）
  - `producer`：产生该变量的 step_id（可为 null）
  - `consumers`：消费该变量的 step_id 列表
- `files`：文件列表
- `apis`：API 列表
- `types`：自定义类型列表

**输出到 SPL**：
```spl
[DEFINE_VARIABLES:]
    "The user's request" user_request: text
    "Draft communication artifact" draft_artifact: text
[END_VARIABLES]

[DEFINE_FILES:]
    "Newsletter template" template_file "templates/newsletter.docx": text
[END_FILES]

[DEFINE_APIS:]
    "Search approved sources" SourceRetrievalApi<oauth> RETRY 2 {
        functions: [{
            name: "search",
            description: "Search approved sources",
            parameters: [{name: "query", type: "text", required: true}],
            return: {type: "text", controlled-output: false}
        }]
    }
[END_APIS]

[DEFINE_TYPES:]
    Severity = [critical, major, minor]
[END_TYPES]
```

---

### 4.8 SymbolTable

**用途**：管理变量的声明和引用关系，生成 `<REF>` 标签。

**字段结构**：
```json
{
  "variables": {
    "user_request": {
      "name": "user_request",
      "data_type": "text",
      "source": "input",
      "description": "The user's request",
      "flow_ref": "main",
      "block_ref": null,
      "producer_step": null,
      "consumer_steps": ["st3", "st5"],
      "declared": true
    }
  }
}
```

**接口**：
```python
class SymbolTable:
    variables: dict[str, VariableSymbol]
    
    def declare(self, name: str, data_type: str, source: str, description: str, 
                flow_ref: str = "main", block_ref: str | None = None) -> None:
        """声明变量（用于 DEFINE_VARIABLES 块）"""
        
    def reference(self, name: str) -> str:
        """生成 <REF>name</REF> 引用"""
        return f"<REF>{name}</REF>"
        
    def value_reference(self, name: str) -> str:
        """生成 <REF>*name</REF> 按值引用"""
        return f"<REF>*{name}</REF>"
        
    def get_variable_list_for_prompt(self) -> str:
        """生成变量列表文本，用于传入 LLM prompt"""
        return "\n".join([f"- {v.name}: {v.data_type} ({v.source})" for v in self.variables.values()])
        
    def validate_references(self) -> list[str]:
        """校验所有引用是否都有对应的声明"""
        errors = []
        for name, var in self.variables.items():
            if var.producer_step and var.producer_step not in [...]:
                errors.append(f"Variable {name} references unknown step {var.producer_step}")
        return errors
```

**职责**：
- 管理变量的声明和引用关系
- 生成 `<REF>name</REF>` 引用标签
- 校验"先声明后引用"
- 跟踪变量的 producer、consumer、flow_ref、block_ref
- **提供 `get_variable_list_for_prompt()` 方法，将变量列表传入 LLM prompt**

---

### 4.9 StepIR

**用途**：表示 behavior 中的原子动作。

**字段**：
```json
{
  "step_id": "st1",
  "text": "Determine what kind of communication is requested",
  "source_span_ids": ["s8"],
  "command_type": "GENERAL_COMMAND",
  "inputs": ["user_request"],
  "outputs": ["communication_type"],
  "integration_ref": null,
  "flow_ref": "main",
  "block_ref": "b1",
  "kind": "normal"
}
```

**字段说明**：
- `step_id`：唯一标识，格式为 `st{N}`（与 SpanIR 的 `s{N}` 区分）
- `text`：步骤的自然语言描述
- `source_span_ids`：来源 span 列表
- `command_type`：命令类型
  - `GENERAL_COMMAND`：通用命令
  - `CALL_API`：调用 API
  - `INVOKE_WORKER`：调用其他 worker
  - `REQUEST_INPUT`：请求用户输入
  - `DISPLAY_MESSAGE`：显示消息
- `inputs`：输入变量名列表（引用 SymbolTable）
- `outputs`：输出变量名列表（引用 SymbolTable）
- `integration_ref`：引用的 API 名称（仅 CALL_API 时有值）
- `flow_ref`：所属 Flow（main / alt_{N} / exc_{N}）
- `block_ref`：所属 Block
- `kind`：语义类型
  - `normal`：普通步骤
  - `tool`：工具调用
  - `user_input`：用户输入
  - `invoke`：调用其他 worker
  - `display`：显示消息

**不建议字段**：
- branch（由 BlockIR 表示）
- loop（由 BlockIR 表示）
- policy_gate（由 ConstraintIR 表示）
- confidence（不需要）

**输出到 SPL**：
```spl
COMMAND-1 [COMMAND Determine communication type RESULT communication_type: text]
COMMAND-2 [CALL SourceRetrievalApi WITH query: <REF>search_query</REF> RESPONSE evidence: text SET]
```

---

### 4.10 WorkerIR

**用途**：表示一个可编译的 SPL worker。

**字段**：
```json
{
  "worker_name": "InternalCommsWorker",
  "description": "Generate internal communication artifacts",
  "inputs": [
    {"name": "user_request", "required": true},
    {"name": "available_connectors", "required": false}
  ],
  "outputs": [
    {"name": "draft_artifact", "required": true},
    {"name": "completion_status", "required": true}
  ],
  "main_flow": {
    "blocks": ["b1", "b2", "b3"]
  },
  "alternative_flows": [
    {
      "flow_id": "alt_1",
      "condition_text": "missing timeframe",
      "blocks": ["b4"]
    }
  ],
  "exception_flows": [
    {
      "flow_id": "exc_1",
      "condition_text": "evidence shortage",
      "blocks": ["b5"]
    }
  ],
  "api_refs": ["SourceRetrievalApi"],
  "child_worker_refs": ["SourceGatheringWorker"]
}
```

**字段说明**：
- `worker_name`：Worker 名称
- `description`：Worker 描述
- `inputs`：输入变量列表（带 required 标记）
- `outputs`：输出变量列表（带 required 标记）
- `main_flow`：主流程（包含 blocks 列表）
- `alternative_flows`：替代流程列表
- `exception_flows`：异常流程列表
- `api_refs`：引用的 API 列表
- `child_worker_refs`：引用的子 Worker 列表（来自 FlowStructureIR.delegation_candidates）

**不建议字段**：
- contains_loop（由 flow 推导）
- contains_condition（由 flow 推导）

**输出到 SPL**：
```spl
[DEFINE_WORKER: "Generate internal communication artifacts" InternalCommsWorker]
    [INPUTS]
        REQUIRED <REF>user_request</REF>
        OPTIONAL <REF>available_connectors</REF>
    [END_INPUTS]
    [OUTPUTS]
        REQUIRED <REF>draft_artifact</REF>
        REQUIRED <REF>completion_status</REF>
    [END_OUTPUTS]
    [MAIN_FLOW]
        [SEQUENTIAL_BLOCK]
            COMMAND-1 [COMMAND Determine communication type]
            COMMAND-2 [COMMAND Identify missing fields]
        [END_SEQUENTIAL_BLOCK]
        DECISION-1 [IF sources are needed and available]
            COMMAND-3 [CALL SourceRetrievalApi]
            COMMAND-4 [COMMAND Maintain provenance]
        [END_IF]
        [SEQUENTIAL_BLOCK]
            COMMAND-5 [COMMAND Produce draft]
        [END_SEQUENTIAL_BLOCK]
    [END_MAIN_FLOW]
    [ALTERNATIVE_FLOW: missing timeframe]
        [SEQUENTIAL_BLOCK]
            COMMAND-6 [INPUT Ask user to clarify]
        [END_SEQUENTIAL_BLOCK]
    [END_ALTERNATIVE_FLOW]
    [EXCEPTION_FLOW: evidence shortage]
        [SEQUENTIAL_BLOCK]
            COMMAND-7 [DISPLAY "Unable to retrieve sufficient evidence"]
            COMMAND-8 [COMMAND Return error status]
        [END_SEQUENTIAL_BLOCK]
    [END_EXCEPTION_FLOW]
[END_WORKER]
```

---

## 5. 关键转换规则

### 5.1 字段路由规则

| 原文语义 | 路由目标 | SPL 映射 |
|----------|----------|----------|
| 角色、风格、身份原则 | identity | PERSONA |
| 面向对象 | audience | AUDIENCE |
| 不得、必须、限制、原则 | rules | CONSTRAINTS |
| 领域术语、名词定义 | domain | CONCEPTS |
| 外部服务、工具、系统 | integrations | APIS |
| 行为、步骤、流程、条件、循环 | behavior | WORKER |

**关键点**：
- 路由是语义驱动的，不是结构驱动的
- **一个 span 只能属于一个字段**（不允许重叠）
- 歧义 span 在 Stage 3 拆分为子 span，子 span 各自归一个字段

---

### 5.2 歧义处理规则

当一个 span 的语义跨越多个字段时：
1. Stage 2（FieldRouter）标记 `ambiguity.is_ambiguous = true`
2. Stage 3（AmbiguityResolver）将 span 拆分为多个子 span
3. 每个子 span 各自归一个字段

**示例**：
```
原始 span:
  s3: "Determine communication type, but do not invent details"
  ambiguity: {is_ambiguous: true, reasons: ["mixed_action_and_policy"], needs_split: true}

Stage 3 拆分后:
  s3a: "Determine communication type" → behavior
  s3b: "Do not invent details" → rules
```

---

### 5.3 Flow 判断规则

| 语义特征 | Flow 类型 |
|----------|-----------|
| 默认、主流程 | MAIN_FLOW |
| "如果失败"、"如果缺少"、"当...发生时" | EXCEPTION_FLOW |
| "否则"、"另一种方式"、"如果用户要求修改" | ALTERNATIVE_FLOW |

---

### 5.4 Block 判断规则

| 语义特征 | Block 类型 |
|----------|-----------|
| 连续的、无条件的动作 | SEQUENTIAL |
| "if"、"when"、"unless" | IF |
| "for each"、"遍历" | FOR |
| "while"、"直到" | WHILE |

---

### 5.5 Delegation 处理规则

Delegation 内容不单独处理，而是路由到标准字段：

| delegation 语义 | 路由目标 | SPL 映射 |
|-----------------|----------|----------|
| 外部系统单次调用 | integrations | CALL_API |
| 多步、可复用、独立输入输出 | behavior | INVOKE_WORKER (child worker) |
| 多步且依赖外部系统 | integrations + behavior | INVOKE_WORKER + 内部 CALL_API |
| 委托约束、边界 | rules | CONSTRAINTS |
| 晋升门槛 | rules | CONSTRAINTS (promotion_requirement) |

**Delegation 候选识别**：
- Stage 4（FlowAssembler）的 LLM 在判断 Flow 结构时，同时识别 delegation_candidates
- delegation_candidates 存储在 FlowStructureIR 中
- Stage 10（WorkerAssembler）根据 delegation_candidates 生成 child_worker_refs

---

## 6. 编译流程设计

### Stage 1：原文切片

**实现方式**：LLM

**输入**：原始文本

**输出**：`List[SpanIR]`

**职责**：
- 按语义边界切片（句子、短语、从句）
- 分配 span_id（格式：`s{N}`）
- 初始化 `ambiguity.is_ambiguous = false`

**注意**：Stage 1 不判断歧义，歧义由 Stage 2 回写。

---

### Stage 2：字段路由

**实现方式**：LLM

**输入**：`List[SpanIR]`

**输出**：`FieldRouteIR` + 回写 `SpanIR.ambiguity`

**职责**：
- 将每个 span 路由到 6 个语义字段
- 如果发现 span 语义跨越多个字段，回写 `ambiguity.is_ambiguous = true` 和 `needs_split = true`

**注意**：路由结果中不允许 span 重叠。歧义 span 标记后由 Stage 3 处理。

---

### Stage 3：歧义消解

**实现方式**：LLM

**输入**：`FieldRouteIR` + 标记为 ambiguous 的 spans

**输出**：`FieldRouteIR`（消解后）

**职责**：
- 消费 ambiguity 标记
- 将歧义 span 拆分为多个子 span
- 每个子 span 各自归一个字段
- 更新 FieldRouteIR

---

### Stage 4：Flow 组装

**实现方式**：LLM

**输入**：`FieldRouteIR`（消解后）

**输出**：`FlowStructureIR`

**职责**：
- 判断哪些 span 属于 MAIN_FLOW
- 判断哪些 span 属于 ALTERNATIVE_FLOW
- 判断哪些 span 属于 EXCEPTION_FLOW
- 记录每个 Flow 的触发条件
- **识别 delegation_candidates**

---

### Stage 5：Block 组装

**实现方式**：LLM

**输入**：
- `FieldRouteIR`（消解后）
- `FlowStructureIR`

**输出**：`BlockStructureIR`

**职责**：
- 在每个 Flow 内部，将 span 组织成 Block
- 识别条件语句（if/when/unless），生成 IF_BLOCK
- 识别循环语句（for/while/each），生成 FOR_BLOCK 或 WHILE_BLOCK
- 其余 span 生成 SEQUENTIAL_BLOCK

---

### Stage 6：Resource 抽取 + SymbolTable 构建

**实现方式**：LLM

**输入**：
- `FieldRouteIR`（behavior spans）
- `FlowStructureIR`
- `BlockStructureIR`

**输出**：
- `ResourceRegistryIR`
- `SymbolTable`

**职责**：
- 从 behavior spans 中识别输入变量、输出变量、中间变量
- 从 integrations spans 中提取 APIs
- 从 behavior spans 中提取文件引用
- 使用 FlowStructureIR 和 BlockStructureIR 上下文，将变量关联到 Flow/Block
- 构建 SymbolTable

**注意**：
- 不假设输入文本有显式的 "Inputs for each run" 和 "Required outputs" 字段
- 如果无法识别 inputs/outputs，在 `_meta` 中警告

---

### Stage 7：Step 抽取

**实现方式**：LLM

**输入**：
- `FieldRouteIR`（behavior spans）
- `FlowStructureIR`
- `BlockStructureIR`
- `SymbolTable`

**输出**：
- `List[StepIR]`
- `SymbolTable`（更新后）

**职责**：
- 从 behavior spans 中提取原子动作
- **使用 LLM 识别每个 step 的 inputs/outputs**（从 SymbolTable 的变量列表中选择）
- 使用 FlowStructureIR 和 BlockStructureIR 判断每个 step 属于哪个 Flow/Block
- 如果 step 产生新变量，更新 SymbolTable
- 如果 step 引用 API，记录 integration_ref

**SymbolTable 使用方式**：
```
Prompt 中传入变量列表：
"Known variables:
- user_request: text (input)
- communication_type: text (step)
- missing_fields: List[text] (step)
...

For each step, identify which variables it consumes (inputs) and produces (outputs)."
```

---

### Stage 8：Profile 抽取

**实现方式**：LLM

**输入**：
- `FieldRouteIR`（identity, audience, domain spans）
- `SymbolTable`

**输出**：
- `AgentProfileIR`

**职责**：
- 从 identity spans 中提取 persona.role 和 persona.aspects
- 从 audience spans 中提取 audience.aspects
- 从 domain spans 中提取 concepts
- 如果 aspects 或 concepts 引用变量，使用 SymbolTable 生成 `<REF>` 标签

---

### Stage 9：Constraint 抽取

**实现方式**：LLM

**输入**：
- `FieldRouteIR`（rules spans）
- `FlowStructureIR`
- `BlockStructureIR`
- `SymbolTable`
- **`List[StepIR]`**（用于 targets 引用）

**输出**：
- `List[ConstraintIR]`

**职责**：
- 从 rules spans 中提取约束
- 使用 SymbolTable 识别约束引用的变量
- 使用 FlowStructureIR 和 BlockStructureIR 判断约束的目标 Flow/Block
- **使用 List[StepIR] 判断约束的目标 Step**
- 为每个约束分配 constraint_id
- 确定约束的 kind 和 targets

---

### Stage 10：Worker 组装

**实现方式**：代码

**输入**：
- `FlowStructureIR`
- `BlockStructureIR`
- `List[StepIR]`
- `ResourceRegistryIR`
- `SymbolTable`

**输出**：
- `WorkerIR`

**职责**：
- 组装 parent worker
- 绑定 inputs/outputs（从 ResourceRegistryIR.variables 中提取）
- 绑定 apis（从 ResourceRegistryIR.apis 中提取）
- **根据 FlowStructureIR.delegation_candidates 生成 child_worker_refs**（代码逻辑，不需要 LLM）
- 将 BlockStructureIR 转换为 BlockIR 列表
- 将 FlowStructureIR 转换为 FlowIR

---

### Stage 11：SPL 渲染 + 静态校验

**实现方式**：代码

**输入**：
- `WorkerIR`
- `AgentProfileIR`
- `ResourceRegistryIR`
- `SymbolTable`

**输出**：
- SPL 文本
- 校验报告

**职责**：
- 渲染 SPL 代码（4空格缩进）
- 校验变量引用（先声明后引用）
- 校验 API 声明（先声明后调用）
- 校验 required outputs 可达性

**校验规则**：
1. 变量先声明后引用
2. API 先声明后调用
3. Worker 输入输出闭合
4. Block 不嵌套其他 Block
5. Required outputs 可达

---

## 7. 模块划分

### 7.1 代码模块

```python
# Stage 1 (LLM)
class SpanSlicer:
    """原文切片，生成 SpanIR 列表"""
    def slice(self, raw_text: str) -> list[SpanIR]

# Stage 2 (LLM)
class FieldRouter:
    """字段路由，将 span 路由到 6 个语义字段，回写 ambiguity"""
    def route(self, spans: list[SpanIR]) -> tuple[FieldRouteIR, list[SpanIR]]

# Stage 3 (LLM)
class AmbiguityResolver:
    """歧义消解，拆分 ambiguous span"""
    def resolve(self, routes: FieldRouteIR, spans: list[SpanIR]) -> tuple[FieldRouteIR, list[SpanIR]]

# Stage 4 (LLM)
class FlowAssembler:
    """Flow 组装，判断哪些 span 属于哪个 Flow，识别 delegation_candidates"""
    def assemble(self, routes: FieldRouteIR) -> FlowStructureIR

# Stage 5 (LLM)
class BlockAssembler:
    """Block 组装，在每个 Flow 内判断哪些 span 形成 Block"""
    def assemble(self, routes: FieldRouteIR, flow: FlowStructureIR) -> BlockStructureIR

# Stage 6 (LLM)
class ResourceExtractor:
    """Resource 抽取 + SymbolTable 构建"""
    def extract(self, routes: FieldRouteIR, flow: FlowStructureIR, blocks: BlockStructureIR) -> tuple[ResourceRegistryIR, SymbolTable]

# Stage 7 (LLM)
class StepExtractor:
    """Step 抽取，使用 LLM 识别变量引用"""
    def extract(self, routes: FieldRouteIR, flow: FlowStructureIR, blocks: BlockStructureIR, 
                symbols: SymbolTable) -> tuple[list[StepIR], SymbolTable]

# Stage 8 (LLM)
class ProfileExtractor:
    """Profile 抽取"""
    def extract(self, routes: FieldRouteIR, symbols: SymbolTable) -> AgentProfileIR

# Stage 9 (LLM)
class ConstraintExtractor:
    """Constraint 抽取"""
    def extract(self, routes: FieldRouteIR, flow: FlowStructureIR, blocks: BlockStructureIR, 
                symbols: SymbolTable, steps: list[StepIR]) -> list[ConstraintIR]

# Stage 10 (Code)
class WorkerAssembler:
    """Worker 组装（代码逻辑）"""
    def assemble(self, flow: FlowStructureIR, blocks: BlockStructureIR, steps: list[StepIR], 
                 resources: ResourceRegistryIR, symbols: SymbolTable) -> WorkerIR

# Stage 11 (Code)
class SPLRenderer:
    """SPL 渲染 + 静态校验（代码逻辑）"""
    def render(self, worker: WorkerIR, profile: AgentProfileIR, resources: ResourceRegistryIR, 
               symbols: SymbolTable) -> tuple[str, list[str]]
```

---

## 8. Prompt 设计原则

### 8.1 模型只输出 JSON IR
不要直接让模型输出 SPL。

### 8.2 每个 prompt 只做一件事
建议 prompt 颗粒度如下：
- Span Slicer（Stage 1）
- Field Router（Stage 2）
- Ambiguity Resolver（Stage 3）
- Flow Assembler（Stage 4）
- Block Assembler（Stage 5）
- Resource Extractor（Stage 6）
- Step Extractor（Stage 7）
- Profile Extractor（Stage 8）
- Constraint Extractor（Stage 9）

### 8.3 Prompt 中必须明确语法边界
每个 prompt 都要给出与当前任务相关的 SPL 语法摘要，避免模型越界。

### 8.4 Prompt 输出必须可被代码消费
字段名稳定、类型稳定、可去重、可引用。

### 8.5 SymbolTable 作为上下文传入
Stage 7（Step Extractor）的 prompt 中，必须传入 SymbolTable 的变量列表，让 LLM 识别每个 step 的 inputs/outputs。

---

## 9. 失败处理

### 9.1 缺少字段
如果输入文档中缺少关键内容，系统应：
- 标记缺失
- 尽量继续
- 在 assumptions 中说明

### 9.2 if 语义不明确
进入 BlockStructureIR 的 `uncertain` 类型，由后续编译器依据上下文决定。

### 9.3 required outputs 不可达
输出失败状态或 assumption-bearing draft，而不是静默完成。

### 9.4 歧义无法消解
Stage 3 尝试拆分，如果无法拆分，保留原始 span 并标记 warning。

### 9.5 inputs/outputs 无法识别
Stage 6 如果无法从 behavior spans 中识别 inputs/outputs，在 `_meta` 中警告，继续执行。

---

## 10. 实现优先级

### 第一阶段：最小可用版本（MVP）

必须包含的 Stage：
- Stage 1: Span 切片
- Stage 2: 字段路由
- Stage 3: 歧义消解（简化版：不拆分，只标记）
- Stage 4: Flow 组装（仅支持 MAIN_FLOW）
- Stage 5: Block 组装（仅支持 SEQUENTIAL_BLOCK）
- Stage 6: Resource 抽取
- Stage 7: Step 抽取
- Stage 8: Profile 抽取（简化版）
- Stage 9: Constraint 抽取（简化版）
- **Stage 10: Worker 组装**（必须包含，否则 Stage 11 无法运行）
- Stage 11: SPL 渲染 + 校验

**MVP 限制**：
- 仅支持 MAIN_FLOW + SEQUENTIAL_BLOCK
- 不支持 ALTERNATIVE_FLOW、EXCEPTION_FLOW
- 不支持 IF_BLOCK、FOR_BLOCK、WHILE_BLOCK
- 不支持 delegation_candidates

### 第二阶段：增强能力

新增：
- Stage 3 完整版（支持 span 拆分）
- Stage 4 支持 ALTERNATIVE_FLOW、EXCEPTION_FLOW、delegation_candidates
- Stage 5 支持 IF_BLOCK、FOR_BLOCK、WHILE_BLOCK
- Stage 10 支持 child_worker 生成

### 第三阶段：优化

- 自动修正
- Prompt 集成优化
- Validator 回写修复
- 设计文档自动生成

---

## 11. 与现有实现的对比

| 维度 | 本设计 | 当前 StructuralNL2SPL | skill_to_cnlp |
|------|--------|----------------------|---------------|
| **输入** | 自然语言（不依赖结构） | 7字段 Structural NL | SKILL.md + scripts |
| **设计思路** | 自顶向下（Flow → Block → Step） | 自底向上（Step → Block → Flow） | 自底向上 |
| **Section提取** | 6个语义字段 | 6阶段LLM提取 | 8个Section |
| **中间表示** | 10种IR | 6种IR | 5种IR |
| **Span追踪** | 有（SpanIR） | 无 | 无 |
| **歧义处理** | 有（Ambiguity Resolver） | 无 | 无 |
| **Flow/Block 结构** | 提前判断（Stage 4-5） | 后续组装（Stage 8） | 后续组装（Step 4） |
| **SymbolTable** | 有 | 无 | 无 |
| **变量识别** | LLM（传入 SymbolTable 上下文） | 代码 | 代码 |
| **Delegation** | 路由到标准字段 + delegation_candidates | 独立模块 | 无 |
| **LLM/Code 分工** | 明确标注 | 未明确 | 未明确 |

---

## 12. 结论

这套方案的核心是：

- 用大模型做语义理解
- 用 IR 做稳定的中间表示
- 用代码做 SPL 编译和校验
- 用最少的字段覆盖 SPL 的全部语法能力
- **自顶向下分解**：先确定 Flow，再确定 Block，最后填充 Step
- **明确 LLM/Code 分工**：Stage 1-9 由 LLM 完成，Stage 10-11 由代码完成

最关键的稳定边界是：
- Flow 确定高层结构（MAIN / ALTERNATIVE / EXCEPTION）
- Block 确定中层结构（SEQUENTIAL / IF / FOR / WHILE）
- Step 表示原子动作
- Constraint 表示规则
- Resource 管理变量 / 文件 / API / 类型
- Worker 组织 flow
- SymbolTable 管理变量声明和引用

这套结构可以直接指导编码实现。
