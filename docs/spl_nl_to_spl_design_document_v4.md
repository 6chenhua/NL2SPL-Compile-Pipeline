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
1. 先判断是否需要多个 Worker，以及 Worker 之间的数据协作边界
2. 再确定每个 Worker 内部的 Flow（MAIN / ALTERNATIVE / EXCEPTION）
3. 再确定每个 Flow 中的 Block（SEQUENTIAL / IF / FOR / WHILE）
4. 最后填充 Step（具体动作）

当前实现中，delegation 仍通过 `FlowStructureIR.delegation_candidates` 作为兼容载体进入后续阶段；Stage 9.5 会把 child-worker 候选物化为具体 `INVOKE_WORKER` step，Stage 10 会生成具体 child worker。目标设计是将 Worker 边界规划拆成独立 `DelegationPlanIR` / `WorkerPlanIR`，并放在 FlowStructureIR 之前。

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
| 1 | 原文切片 | **LLM** | 原始文本（或 CanonicalCompileInput） | List[SpanIR] |
| 2 | 字段路由 | **LLM** | List[SpanIR]（+ CanonicalCompileInput） | FieldRouteIR + 回写 SpanIR.ambiguity |
| 3 | 歧义消解 | **LLM** | FieldRouteIR + ambiguous spans | FieldRouteIR（消解后） |
| **3.5** | **Worker 边界规划** | **LLM** | List[SpanIR] + FieldRouteIR（+ CanonicalCompileInput） | **WorkerPlanIR** |
| **3.6** | **Worker 计划校验** | **代码** | WorkerPlanIR + known span IDs | **WorkerPlanValidationResult** |
| 4 | Flow 组装 | **LLM** | List[SpanIR] + FieldRouteIR（+ WorkerPlanIR） | FlowStructureIR 或 WorkerFlowPlanIR |
| 5 | Block 组装 | **LLM** | List[SpanIR] + FieldRouteIR + FlowStructureIR（或 WorkerFlowPlanIR） | BlockStructureIR 或 WorkerBlockPlanIR |
| 6 | Resource 抽取 | **LLM** | FieldRouteIR + FlowStructureIR + BlockStructureIR（+ CanonicalCompileInput） | ResourceRegistryIR + SymbolTable |
| 7 | Step 抽取 | **LLM** | FieldRouteIR + FlowStructureIR + BlockStructureIR + SymbolTable（+ WorkerPlanIR） | List[StepIR] + SymbolTable（更新） |
| 8 | Profile 抽取 | **LLM** | FieldRouteIR + SymbolTable | AgentProfileIR |
| 9 | Constraint 抽取 | **LLM** | FieldRouteIR + FlowStructureIR + BlockStructureIR + SymbolTable + List[StepIR]（+ CanonicalCompileInput） | List[ConstraintIR] |
| 9.5 | IR 归一化 | **代码** | FlowStructureIR + BlockStructureIR + ResourceRegistryIR + SymbolTable + List[StepIR] + List[ConstraintIR]（+ WorkerPlanIR） | 归一化后的 IR + errors/warnings |
| 10 | Worker 组装 | **代码** | FlowStructureIR + BlockStructureIR + List[StepIR] + ResourceRegistryIR + SymbolTable（+ WorkerPlanIR） | WorkerIR（含 child_workers） |
| 11 | SPL 渲染 + 校验 | **代码** | WorkerIR + AgentProfileIR + ResourceRegistryIR + SymbolTable + List[StepIR] + List[ConstraintIR] | SPL 文本 + 校验报告 |

### 3.2 分层角色

#### 语义层（Stage 1-9）
由大模型完成，输出 JSON IR。Stage 3.5（Worker 边界规划）也由 LLM 完成，输出 WorkerPlanIR。

#### 校验层（Stage 3.6）
由代码完成，校验 WorkerPlanIR 的图结构、所有权、handoff 和 candidate 一致性。

#### 编译层（Stage 10）
由代码完成，负责将 IR 转换成 SPL 结构。

#### 渲染 + 校验层（Stage 11）
由代码完成，输出最终 SPL 文本并进行静态校验。

### 3.3 数据流图

```
原始文本 / CanonicalCompileInput
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
    ├─────────────────────────────────────────────────────┐
    │  (可选，enable_worker_boundary_planner=true)        │
    ▼                                                     │
Stage 3.5: WorkerPlanIR (worker 边界规划)                 │
    │                                                     │
    ▼                                                     │
Stage 3.6: WorkerPlanValidationResult (校验)              │
    │                                                     │
    ├─────────────────────────────────────────────────────┘
    │
    ▼
Stage 4: FlowStructureIR 或 WorkerFlowPlanIR
    │       (WorkerPlanIR → WorkerFlowPlanIR per worker)
    │       (无 WorkerPlanIR → 单一 FlowStructureIR + delegation_candidates)
    │
    ▼
Stage 5: BlockStructureIR 或 WorkerBlockPlanIR
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
Stage 9.5: Normalized IRs + errors/warnings
    │       (含 WorkerPlanIR handoffs 物化、
    │        delegation_candidates 物化、
    │        多输出聚合、required output 补全)
    │
    ▼
Stage 10: WorkerIR (代码组装，含 child_workers)
    │       (WorkerPlanIR 优先；delegation_candidates 兼容)
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
  },
  "source_section_id": null,
  "source_packet_id": null
}
```

**字段说明**：
- `span_id`：由代码分配，格式为 `s{N}`
- `text`：原始文本片段，保持原文措辞
- `ambiguity`：标记该 span 是否存在语义歧义
  - `is_ambiguous`：是否歧义（**Stage 1 初始化为 false，Stage 2 回写**）
  - `reasons`：歧义原因列表
  - `needs_split`：是否需要拆分
- `source_section_id`：来源 section ID（由输入适配器设置，用于溯源）
- `source_packet_id`：来源 packet ID（由输入适配器设置，用于溯源）

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

**用途**：判断哪些 behavior span 属于哪个 Flow（MAIN / ALTERNATIVE / EXCEPTION）。在无 WorkerPlanIR 的 legacy 路径下，同时保留 delegation 候选作为兼容字段。当 WorkerPlanIR 启用时，每个 worker 有独立的 FlowStructureIR（通过 WorkerFlowPlanIR 包装），delegation_candidates 字段为空。

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
      "suggested_type": "child_worker",
      "input_variables": ["available_connectors"],
      "output_variables": ["retrieved_sources", "provenance_log"]
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
- `delegation_candidates`：delegation 候选列表（legacy 兼容字段，由 Stage 4 的 LLM 识别；WorkerPlanIR 启用时由 adapter 自动生成）
  - `candidate_id`：唯一标识，格式为 `dc_{N}`
  - `spans`：相关的 span 列表
  - `reason`：为什么适合提取为子任务
  - `suggested_type`：建议类型（`child_worker` 或 `api_call`）
  - `input_variables`：候选子任务需要读取的变量名列表
  - `output_variables`：候选子任务产生的变量名列表

**判定规则**：
- 默认所有 span 属于 main_flow
- 如果 span 描述失败、拒绝、证据不足、系统不可用、前置条件无法满足等负面事件，归入 exception_flow
- 如果 span 描述用户主动选择的另一条完整路径，归入 alternative_flow
- 如果条件只影响主流程中的一个动作，保留在 main_flow，交给 Stage 5 生成 IF/FOR/WHILE block
- 如果条件描述“只要/直到某条件成立就反复处理”，保留在 main_flow，交给 Stage 5 生成 WHILE block
- 如果 spans 描述了独立的子任务（有明确的输入输出边界），标记为 delegation_candidates

**Stage 4 prompt 输入形态**：
- `behavior_spans` 以纯文本传入，格式为 `span_id: span text`
- 全量上下文也以纯文本 span 列表传入，用于理解周边语义
- 不再把 `SpanIR` 的完整 JSON 传给 Stage 4，因此 prompt 中不包含 `ambiguity`
- 输出中的 span 列表必须继续使用 `span_id`，不能复制 span text
- **Worker-aware 模式**：当传入 WorkerPlanIR 时，prompt 额外包含 WorkerPlanIR context（当前 worker 的 spec、相关 handoffs），且不输出 delegation_candidates

#### 4.3.1 目标设计：DelegationPlanIR / WorkerPlanIR

当前 `delegation_candidates` 放在 `FlowStructureIR` 内，是为了兼容现有 Stage 7、Stage 9.5、Stage 10。更合理的长期设计是在 FlowStructureIR 之前增加 Worker 边界规划 IR：

**已实现**：Stage 3.5（WorkerBoundaryPlanner）生成 `WorkerPlanIR`，Stage 3.6（WorkerPlanValidator）校验。通过 `enable_worker_boundary_planner` 配置开关控制。

```json
{
  "main_worker_id": "worker_main",
  "workers": [
    {
      "worker_id": "worker_main",
      "worker_name": "MainWorker",
      "kind": "main",
      "purpose": "Coordinate the full user request",
      "owned_span_ids": ["s4", "s5", "s6", "s9"],
      "input_contract": [{"name": "user_request", "required": true, "data_type": "text"}],
      "output_contract": [{"name": "draft_artifact", "required": true, "data_type": "text"}],
      "depends_on": ["worker_source_retrieval"],
      "constraints": ["c1", "c2"]
    },
    {
      "worker_id": "worker_source_retrieval",
      "worker_name": "child_dc_1",
      "kind": "child",
      "purpose": "Retrieve sources and maintain provenance",
      "owned_span_ids": ["s7", "s8"],
      "input_contract": [{"name": "available_connectors", "required": true, "data_type": "List [text]"}],
      "output_contract": [{"name": "child_dc_1_result", "required": true, "data_type": "ChildDc1Result"}],
      "depends_on": [],
      "constraints": ["c3"]
    }
  ],
  "handoffs": [
    {
      "from_worker": "worker_main",
      "to_worker": "worker_source_retrieval",
      "mode": "invoke",
      "condition_text": "sources are needed and available",
      "input_bindings": {"available_connectors": "available_connectors"},
      "output_bindings": {"child_dc_1_result": "child_dc_1_result"},
      "failure_policy": "return provenance failure or ask user for source access"
    }
  ],
  "unassigned_span_ids": [],
  "warnings": []
}
```

这个 IR 应明确 Worker 所有权、输入输出契约、调用条件、失败策略和 handoff 数据绑定。它的价值是让后续阶段不再猜测"为什么没有定义 worker"，而是在 Flow/Block/Step 生成前就建立可校验的 worker 协作图。

**已实现的完整 WorkerPlanIR 结构**（对应 `worker_plan_ir.py`）：

```python
BoundaryKind = Literal[
    "explicit_delegation", "bounded_subtask", "integration_wrapper",
    "complex_control_extraction", "loop_body_worker", "failure_recovery_protocol",
    "template_or_format_protocol", "main_worker", "not_a_worker",
]

Signal = Literal[
    "explicit_delegation", "bounded_io", "multi_step_process",
    "independent_failure_policy", "external_integration", "provenance_or_audit",
    "evidence_normalization", "reuse_potential", "testability", "complex_control",
]

Risk = Literal[
    "no_clear_input_contract", "no_clear_output_contract", "no_parent_invocation_point",
    "single_api_call", "simple_control_flow", "ordinary_sequential_step",
    "policy_or_constraint", "alternative_flow", "exception_flow",
    "over_fragmentation", "unclear_result_handoff", "insufficient_semantic_boundary",
]

@dataclass
class ContractFieldIR:
    """Worker input or output contract field."""
    name: str
    data_type: str
    required: bool
    description: str
    source: Literal["input", "output", "state", "derived"]

@dataclass
class CandidateTaskUnitIR:
    """Potential worker boundary before a final decision is made."""
    candidate_id: str
    source_span_ids: list[str]
    task_text: str
    purpose: str
    candidate_kind: BoundaryKind
    possible_inputs: list[ContractFieldIR] = field(default_factory=list)
    possible_outputs: list[ContractFieldIR] = field(default_factory=list)
    signals: list[Signal] = field(default_factory=list)
    risks: list[Risk] = field(default_factory=list)

@dataclass
class ControlComplexityRegionIR:
    """Predicted or confirmed region with difficult control structure."""
    region_id: str
    source_span_ids: list[str]
    outer_control: Literal["SEQUENTIAL", "IF", "FOR", "WHILE", "unknown"]
    inner_control: Literal["IF", "FOR", "WHILE", "multiple", "unknown"]
    description: str
    discovery_phase: Literal["predicted", "confirmed"]
    severity: Literal["info", "warning", "error"]
    can_flatten: bool
    can_merge_condition: bool
    can_lift_guard: bool
    suggested_repairs: list[str]

@dataclass
class WorkerSpecIR:
    """Concrete worker specification."""
    worker_id: str
    worker_name: str
    kind: Literal["main", "child", "api_adapter"]
    purpose: str
    reason: str
    owned_span_ids: list[str]
    input_contract: list[ContractFieldIR] = field(default_factory=list)
    output_contract: list[ContractFieldIR] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    boundary_strength: Literal["strong", "moderate", "weak"] = "moderate"

@dataclass
class InputBindingIR:
    """Parent-to-child input binding."""
    child_input: str
    parent_variable: str
    required: bool = True
    default_value: str | None = None

@dataclass
class OutputBindingIR:
    """Child-to-parent output binding."""
    child_output: str
    parent_variable: str
    required: bool = True
    merge_strategy: Literal["set", "append", "merge_struct", "ignore_if_empty"] = "set"

@dataclass
class InvokeLocationHintIR:
    """Preferred flow/block location for the handoff step."""
    flow_kind: Literal["main", "alternative", "exception"] = "main"
    flow_id: str | None = None
    after_span_id: str | None = None
    before_span_id: str | None = None
    block_hint: Literal["sequential", "if", "for", "while", "unknown"] = "unknown"

@dataclass
class HandoffFailurePolicyIR:
    """Failure policy for a handoff."""
    policy_kind: Literal["propagate_exception", "ask_user", "continue_with_assumption",
                         "block_finalization", "return_empty_result", "custom"] = "propagate_exception"
    description: str = "Propagate handoff failure to the parent worker."
    custom_policy: str | None = None

@dataclass
class WorkerHandoffIR:
    """Handoff between two workers."""
    handoff_id: str
    from_worker: str | None
    to_worker: str | None
    mode: Literal["invoke", "api_call"]
    api_ref: str | None
    condition_text: str
    ordering: Literal["before", "after", "conditional", "loop_body"]
    input_bindings: list[InputBindingIR] = field(default_factory=list)
    output_bindings: list[OutputBindingIR] = field(default_factory=list)
    invoke_location_hint: InvokeLocationHintIR = field(default_factory=InvokeLocationHintIR)
    failure_policy: HandoffFailurePolicyIR = field(default_factory=HandoffFailurePolicyIR)

@dataclass
class WorkerBoundaryDecisionIR:
    """Decision about a candidate task unit."""
    candidate_id: str
    decision: Literal["extract_child_worker", "keep_in_main_worker",
                      "compile_as_call_api", "compile_as_constraint",
                      "compile_as_exception_flow", "compile_as_alternative_flow",
                      "needs_repair_or_warning"]
    reason: str
    confidence: float = 0.0

@dataclass
class WorkerPlanIR:
    """Global worker boundary plan for the SPL program."""
    main_worker_id: str
    workers: list[WorkerSpecIR] = field(default_factory=list)
    handoffs: list[WorkerHandoffIR] = field(default_factory=list)
    candidates: list[CandidateTaskUnitIR] = field(default_factory=list)
    decisions: list[WorkerBoundaryDecisionIR] = field(default_factory=list)
    rejected_candidates: list[WorkerBoundaryDecisionIR] = field(default_factory=list)
    control_complexity_regions: list[ControlComplexityRegionIR] = field(default_factory=list)
    unassigned_span_ids: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

@dataclass
class WorkerFlowPlanIR:
    """Envelope for worker-scoped flow checkpoints."""
    worker_flows: dict[str, FlowStructureIR] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

@dataclass
class WorkerBlockPlanIR:
    """Envelope for worker-scoped block checkpoints."""
    worker_blocks: dict[str, BlockStructureIR] = field(default_factory=dict)
    control_complexity_regions: list[ControlComplexityRegionIR] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
```

**关键设计决策**：
- `WorkerPlanIR` 包含 `workers`（WorkerSpecIR 列表）、`handoffs`（WorkerHandoffIR 列表）、`candidates`（候选任务单元）、`decisions`（边界决策）和 `rejected_candidates`（被拒绝的候选）
- 每个 `WorkerSpecIR` 有明确的 `owned_span_ids`（所有权）、`input_contract`/`output_contract`（IO 契约）、`boundary_strength`（边界强度）
- `WorkerHandoffIR` 描述 worker 间的调用关系，包含 `input_bindings`/`output_bindings`（数据绑定）、`invoke_location_hint`（调用位置提示）、`failure_policy`（失败策略）
- `ControlComplexityRegionIR` 记录嵌套控制结构的发现和修复建议
- `WorkerFlowPlanIR` 和 `WorkerBlockPlanIR` 是 worker 作用域的 flow/block 检查点包装

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
  "kind": "normal",
  "handoff_id": null
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
- `integration_ref`：引用的 API 名称（仅 CALL_API 时有值）或 child worker 名称（仅 INVOKE_WORKER 时有值）
- `flow_ref`：所属 Flow（main / alt_{N} / exc_{N}）
- `block_ref`：所属 Block
- `kind`：语义类型
  - `normal`：普通步骤
  - `tool`：工具调用
  - `user_input`：用户输入
  - `invoke`：调用其他 worker
  - `display`：显示消息
- `handoff_id`：关联的 WorkerPlanIR handoff ID（当 step 由 WorkerPlanIR handoff 物化时设置）

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
  "child_worker_refs": ["child_dc_1"],
  "child_workers": [
    {
      "worker_name": "child_dc_1",
      "description": "Retrieve sources and maintain provenance",
      "task_text": "Retrieve sources and maintain provenance",
      "inputs": [{"name": "available_connectors", "required": true}],
      "outputs": [{"name": "child_dc_1_result", "required": true}]
    }
  ]
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
- `child_worker_refs`：引用的子 Worker 名称列表（当前来自 FlowStructureIR.delegation_candidates）
- `child_workers`：具体子 Worker 定义列表，由 Stage 10 从 child-worker delegation candidates 和对应 `INVOKE_WORKER` step 组装

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

**当前 Delegation 编译链路**：
- Stage 4（FlowAssembler）在判断 Flow 结构时识别 `delegation_candidates`，当前暂存在 `FlowStructureIR` 中。
- Stage 7 可能从行为文本中抽取 `INVOKE_WORKER` step，但该 step 必须能在后续阶段解析到具体 child worker。
- Stage 9.5（IRNormalizer）根据 child-worker candidates 物化或修正具体 `INVOKE_WORKER` step，并把 `integration_ref` 解析为 `child_dc_N` 形式的真实 worker 名称。
- Stage 9.5 不允许把 unresolved `INVOKE_WORKER` 降级成普通 COMMAND；如果无法解析到具体 worker，应报告错误。
- Stage 10（WorkerAssembler）根据 delegation candidates 和具体 invocation 生成 `child_worker_refs` 与 `child_workers`。
- Stage 11（SPLRenderer）只渲染 concrete worker invocation；渲染前校验 unresolved worker target。

**目标 Delegation 编译链路**：
- 在 Stage 4 之前增加独立 `DelegationPlanIR` / `WorkerPlanIR`，先确定是否需要多个 SPL Worker。
- FlowStructureIR 只描述单个 worker 内部的执行路径，不再负责 worker 边界判断。
- Worker 间协作通过 handoff edge 表示，包含 trigger condition、input/output binding、failure policy 和调用顺序。

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

**输入**：
- `List[SpanIR]`（Stage 3 输出的消解后 spans）
- `FieldRouteIR`（Stage 3 输出的消解后 routes）
- `WorkerPlanIR`（可选，当 `enable_worker_boundary_planner=true` 时传入）

**Prompt 形态**：
- behavior spans：只包含路由到 behavior 的 span，格式化为纯文本 `span_id: span text`
- full source context：全量 span 的纯文本上下文，格式同上
- 不传完整 `SpanIR` JSON，也不传 `ambiguity` 字段
- **Worker-aware 模式**：额外传入 WorkerPlanIR context（当前 worker 的 spec、相关 handoffs、unassigned_span_ids）

**输出**：
- 无 WorkerPlanIR 时：`FlowStructureIR`（含 delegation_candidates）
- 有 WorkerPlanIR 时：`WorkerFlowPlanIR`（每个 worker 一个 FlowStructureIR，delegation_candidates 为空）

**职责**：
- 判断哪些 span 属于 MAIN_FLOW
- 判断哪些 span 属于 ALTERNATIVE_FLOW
- 判断哪些 span 属于 EXCEPTION_FLOW
- 记录每个 Flow 的触发条件
- **Legacy 模式**：兼容地识别 delegation_candidates
- **Worker-aware 模式**：不判断 worker 边界（由 Stage 3.5 已确定），只处理 worker 内部的 flow 结构
- 将普通主流程条件留在 main_flow，交给 Stage 5 生成 IF/FOR/WHILE

---

### Stage 5：Block 组装

**实现方式**：LLM

**输入**：
- `List[SpanIR]`（用于把 span_id 映射回具体文本）
- `FieldRouteIR`（消解后）
- `FlowStructureIR` 或 `WorkerFlowPlanIR`

**Prompt 形态**：
- 只传一个 `flow_json`
- `flow_json` 中每个 span 引用都展开为 `{ "span_id": "...", "text": "..." }`
- 不再额外传 `behavior_json`
- 输出中的 `spans` 仍必须只写 span_id 列表

**输出**：
- 无 WorkerPlanIR 时：`BlockStructureIR`
- 有 WorkerPlanIR 时：`WorkerBlockPlanIR`（每个 worker 一个 BlockStructureIR，含 control_complexity_regions）

**职责**：
- 在每个 Flow 内部，将 span 组织成 Block
- 识别条件语句（if/when/unless），生成 IF_BLOCK
- 识别循环语句（for/while/each），生成 FOR_BLOCK 或 WHILE_BLOCK
- 其余 span 生成 SEQUENTIAL_BLOCK
- **Worker-aware 模式**：额外检测并记录 `ControlComplexityRegionIR`（嵌套控制结构）

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

### Stage 9.5：IR 归一化

**实现方式**：代码

**输入**：
- `FlowStructureIR`
- `BlockStructureIR`
- `ResourceRegistryIR`
- `SymbolTable`
- `List[StepIR]`
- `List[ConstraintIR]`

**输出**：
- 归一化后的 `FlowStructureIR`
- 归一化后的 `BlockStructureIR`
- 归一化后的 `List[StepIR]`
- 归一化后的 `List[ConstraintIR]`
- 归一化后的 `SymbolTable`
- `errors`
- `warnings`

**职责**：
- 修正普通条件误入 alternative/exception flow 的情况，将其移回 main flow
- 将 loop-like exception flow（例如 required slots remain missing）移回 main flow 并生成 WHILE block
- 从 child-worker delegation candidates 物化具体 `INVOKE_WORKER` step
- 解析 placeholder worker invocation，要求 `integration_ref` 指向具体 child worker
- 聚合多输出 child worker 结果，必要时生成结构化 `TypeSpec`
- 为 required outputs 补充正常路径 producer
- 校验变量引用、producer/consumer 顺序、coverage、required output reachability

**约束**：
- 不允许把 unresolved `INVOKE_WORKER` 降级为普通 COMMAND
- 不允许渲染 placeholder `Worker` / `child_worker` target
- warnings 可以继续编译，errors 应阻断最终渲染或至少进入 validation_errors

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
- **根据 FlowStructureIR.delegation_candidates 和已解析的 INVOKE_WORKER step 生成 child_worker_refs 与 child_workers**（代码逻辑，不需要 LLM）
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
- `List[StepIR]`
- `List[ConstraintIR]`

**输出**：
- SPL 文本
- 校验报告

**职责**：
- 渲染 SPL 代码（4空格缩进）
- 渲染 concrete child workers，再渲染 main worker
- 渲染 `ResourceRegistryIR.types` 到 `[DEFINE_TYPES:]`
- 校验变量引用（先声明后引用）
- 校验 API 声明（先声明后调用）
- 校验 worker invocation 指向具体 worker
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
    def execute(self, raw_text: str | CanonicalCompileInput) -> list[SpanIR]

# Stage 2 (LLM)
class FieldRouter:
    """字段路由，将 span 路由到 6 个语义字段，回写 ambiguity"""
    def execute(self, input_data: list[SpanIR] | tuple[list[SpanIR], CanonicalCompileInput]) -> tuple[FieldRouteIR, list[dict[str, Any]]]

# Stage 3 (LLM)
class AmbiguityResolver:
    """歧义消解，拆分 ambiguous span"""
    def execute(self, input_data: tuple[list[SpanIR], FieldRouteIR, list[dict[str, Any]]]) -> tuple[list[SpanIR], FieldRouteIR]

# Stage 3.5 (LLM)
class WorkerBoundaryPlanner:
    """Worker 边界规划，生成 WorkerPlanIR"""
    def execute(self, input_data: tuple[list[SpanIR], FieldRouteIR] | tuple[list[SpanIR], FieldRouteIR, CanonicalCompileInput | None]) -> WorkerPlanIR

# Stage 3.6 (Code)
class WorkerPlanValidator:
    """Worker 计划校验"""
    def validate(self, plan: WorkerPlanIR, known_span_ids: Iterable[str] | None = None) -> WorkerPlanValidationResult

# Stage 4 (LLM)
class FlowAssembler:
    """Flow 组装，判断哪些 span 属于哪个 Flow"""
    def execute(self, input_data: tuple[list[SpanIR], FieldRouteIR] | tuple[list[SpanIR], FieldRouteIR, WorkerPlanIR]) -> FlowStructureIR | WorkerFlowPlanIR

# Stage 5 (LLM)
class BlockAssembler:
    """Block 组装，在每个 Flow 内判断哪些 span 形成 Block"""
    def execute(self, input_data: tuple[list[SpanIR], FieldRouteIR, FlowStructureIR] | tuple[list[SpanIR], FieldRouteIR, WorkerFlowPlanIR]) -> BlockStructureIR | WorkerBlockPlanIR

# Stage 6 (LLM)
class ResourceExtractor:
    """Resource 抽取 + SymbolTable 构建"""
    def execute(self, input_data: tuple[list[SpanIR], FieldRouteIR, FlowStructureIR, BlockStructureIR] | tuple[list[SpanIR], FieldRouteIR, FlowStructureIR, BlockStructureIR, CanonicalCompileInput]) -> tuple[ResourceRegistryIR, SymbolTable]

# Stage 7 (LLM)
class StepExtractor:
    """Step 抽取，使用 LLM 识别变量引用"""
    def execute(self, input_data: tuple[list[SpanIR], FieldRouteIR, FlowStructureIR, BlockStructureIR, SymbolTable] | tuple[list[SpanIR], FieldRouteIR, FlowStructureIR, BlockStructureIR, SymbolTable, WorkerPlanIR]) -> tuple[list[StepIR], SymbolTable]

# Stage 8 (LLM)
class ProfileExtractor:
    """Profile 抽取"""
    def execute(self, input_data: tuple[list[SpanIR], FieldRouteIR, SymbolTable]) -> AgentProfileIR

# Stage 9 (LLM)
class ConstraintExtractor:
    """Constraint 抽取"""
    def execute(self, input_data: tuple[list[SpanIR], FieldRouteIR, FlowStructureIR, BlockStructureIR, SymbolTable, list[StepIR]] | tuple[list[SpanIR], FieldRouteIR, FlowStructureIR, BlockStructureIR, SymbolTable, list[StepIR], CanonicalCompileInput]) -> list[ConstraintIR]

# Stage 9.5 (Code)
class IRNormalizer:
    """IR 归一化与一致性校正（代码逻辑）"""
    def normalize(
        self,
        flow: FlowStructureIR,
        blocks: BlockStructureIR,
        resources: ResourceRegistryIR,
        symbols: SymbolTable,
        steps: list[StepIR],
        constraints: list[ConstraintIR],
        worker_plan: WorkerPlanIR | None = None,
    ) -> tuple[
        FlowStructureIR,
        BlockStructureIR,
        list[StepIR],
        list[ConstraintIR],
        SymbolTable,
        list[str],
        list[str],
    ]

# Stage 10 (Code)
class WorkerAssembler:
    """Worker 组装（代码逻辑）"""
    def assemble(self, flow: FlowStructureIR, blocks: BlockStructureIR, steps: list[StepIR], 
                 resources: ResourceRegistryIR, symbols: SymbolTable,
                 worker_plan: WorkerPlanIR | None = None) -> WorkerIR

# Stage 11 (Code)
class SPLRenderer:
    """SPL 渲染 + 静态校验（代码逻辑）"""
    def render(self, worker: WorkerIR, profile: AgentProfileIR, resources: ResourceRegistryIR, 
               symbols: SymbolTable, steps: list[StepIR],
               constraints: list[ConstraintIR]) -> tuple[str, list[str], list[str]]
```

### 7.2 辅助模块

```python
# Worker 计划适配器（兼容层）
class WorkerPlanAdapter:
    """将 WorkerPlanIR 转换为 legacy DelegationCandidate"""
    def to_delegation_candidates(self, plan: WorkerPlanIR) -> list[DelegationCandidate]

def worker_flow_plan_to_legacy_main_flow(
    worker_flow_plan: WorkerFlowPlanIR,
    worker_plan: WorkerPlanIR,
) -> FlowStructureIR:
    """将 WorkerFlowPlanIR 转换为 legacy FlowStructureIR（仅 main worker 视图）"""

def worker_block_plan_to_legacy_main_blocks(
    worker_block_plan: WorkerBlockPlanIR,
    worker_plan: WorkerPlanIR,
) -> BlockStructureIR:
    """将 WorkerBlockPlanIR 转换为 legacy BlockStructureIR（仅 main worker 视图）"""

# 输入适配器
class InputAdapter(ABC):
    """输入适配器基类"""
    def detect(self, raw_text: str) -> AdapterDetectionResult
    def adapt(self, raw_text: str) -> CanonicalCompileInput

class InputAdapterRegistry:
    """输入适配器注册表"""
    def select_adapter(self, raw_text: str) -> InputAdapter
    def adapt(self, raw_text: str) -> CanonicalCompileInput

# 配置
@dataclass
class PipelineConfig:
    """流水线配置"""
    llm: LLMConfig
    enable_worker_boundary_planner: bool = False  # Worker 边界规划开关
    # ... 其他配置
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
Stage 4 先判断它是否是路径切换；若只是局部动作条件，则保留在 main flow。Stage 5 只能输出 `SEQUENTIAL` / `IF` / `FOR` / `WHILE`，不引入 `uncertain` block 类型；无法确定时应保守使用 `SEQUENTIAL` 并由 Stage 9.5 记录 warning。

### 9.3 required outputs 不可达
输出失败状态或 assumption-bearing draft，而不是静默完成。

### 9.4 歧义无法消解
Stage 3 尝试拆分，如果无法拆分，保留原始 span 并标记 warning。

### 9.5 inputs/outputs 无法识别
Stage 6 如果无法从 behavior spans 中识别 inputs/outputs，在 `_meta` 中警告，继续执行。

---

## 10. 当前实现状态与后续优先级

### 10.1 当前已实现能力

- Stage 1-9 LLM 语义分析链路
- **Stage 3.5 Worker 边界规划（WorkerBoundaryPlanner）**，生成 WorkerPlanIR
- **Stage 3.6 Worker 计划校验（WorkerPlanValidator）**，校验图结构、所有权、handoff 一致性
- Stage 4/5 **Worker-aware 模式**，支持 WorkerFlowPlanIR / WorkerBlockPlanIR
- Stage 9.5 代码归一化与一致性校正，**含 WorkerPlanIR handoff 物化**
- Stage 10 Worker 组装，包含 concrete `child_workers`，**WorkerPlanIR 优先路径**
- Stage 11 SPL 渲染与静态校验
- MAIN / ALTERNATIVE / EXCEPTION flow
- SEQUENTIAL / IF / FOR / WHILE block
- **`delegation_candidates` 到 concrete child worker invocation 的兼容编译链路**（通过 WorkerPlanAdapter）
- 多输出 child worker 结果聚合为结构化 result variable 和 TypeSpec
- Required output producer 补全与 worker invocation 校验
- **CanonicalCompileInput 输入适配器框架**（StructuralNLAdapter、GenericNLAdapter）
- **ControlComplexityRegionIR 嵌套控制结构检测与修复**
- **输入适配器（InputAdapterRegistry）**，支持结构化 NL 和通用 NL 两种输入格式

### 10.2 当前设计债

- ~~Delegation/worker 边界仍暂存在 `FlowStructureIR.delegation_candidates`~~ **已通过 Stage 3.5 WorkerPlanIR 解决**，delegation_candidates 现为 legacy 兼容字段。
- Stage 7 仍可能先抽取出没有 concrete target 的 `INVOKE_WORKER`，需要 Stage 9.5 后置修正。**WorkerPlanIR 启用时，Stage 9.5 会从 WorkerPlanIR handoffs 物化步骤，减少此问题。**
- Stage 6/7 的部分 prompt 仍使用完整 `SpanIR` JSON，可继续按 Stage 4/5 的方式平整化，减少无关字段噪声。
- **Worker-aware 路径仍需通过 `worker_plan_adapter.py` 桥接到 legacy Flow/Block 结构**，后续可逐步移除 legacy 路径。

### 10.3 下一阶段优先级

1. ~~增加独立 `DelegationPlanIR` / `WorkerPlanIR` stage，放在 FlowAssembler 之前。~~ **已完成（Stage 3.5）**
2. ~~将 `FlowStructureIR.delegation_candidates` 标记为兼容字段，并逐步迁移 Stage 7、Stage 9.5、Stage 10 到 WorkerPlanIR。~~ **已完成（WorkerPlanAdapter + enable_worker_boundary_planner 开关）**
3. ~~用 handoff edge 显式描述 worker 协作、输入输出绑定、触发条件和失败策略。~~ **已完成（WorkerHandoffIR）**
4. 继续收敛 prompt 输入，只传当前阶段需要的文本和结构，不传无关 metadata。
5. 扩展端到端 golden tests，覆盖 internal-comms、multi-worker、multi-output TypeSpec、loop normalization 等场景。
6. **将 `enable_worker_boundary_planner` 默认开启**，逐步移除 legacy delegation_candidates 路径。
7. **Stage 6/7 prompt 平整化**，按 Stage 4/5 方式只传纯文本 span 上下文。
8. **Worker-aware Stage 6/7 直接消费 WorkerPlanIR**，不再通过 legacy adapter 桥接。

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
