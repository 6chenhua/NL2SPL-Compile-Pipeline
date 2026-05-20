# NL2SPL Compiler 架构设计方案：IRS 驱动的需求到 SPL 渐进式编译器

## 0. 文档目的

本文档定义 NL2SPL 的下一阶段架构：在当前 v4 已实现的 Partial SPL MVP、Structural Provenance、LLM Adapter Engine、Requirement-Fidelity Normalizer、ProducerIndex、ExecutableElementGate、ProvenanceAggregator、AssumptionBuilder、Completeness Calculator 和 ReportRenderer 基础上，将系统进一步演进为 **IRS-driven requirement-to-SPL compiler**。

本文档同时给出：

1. 全量目标架构；
2. MVP / v5 增量架构；
3. IRS 与 LLM Prompt 联动方案；
4. Semantic Conflict、DataFlow 等后续分析模块的接口预留；
5. 不引入 rule-based 实现的 MVP 收缩原则。

核心原则：

> MVP 阶段优先用 LLM prompt 做笼统实现，不引入复杂 rule-based conflict detector 或 dataflow analyzer；但所有可能未来 rule-based 化的模块，都必须保留清晰接口，避免后续 prompt 逻辑代码化困难。

---

# 1. 总体定位

## 1.1 NL2SPL 是渐进式编译器，不是格式转换器

NL2SPL 的输入是自然语言需求或结构化自然语言需求。它通常不完备、不一致、重复、模糊，不能假设输入已经是完整 specification。

NL2SPL 的输出也不应只是 SPL 文本，而应是：

```text
partial / complete SPL draft
+ diagnostics
+ provenance traces
+ assumptions / suggestions
+ readable report
```

完整 SPL 可理解为：

```text
完善后的需求 + 高层系统设计
```

因此，NL2SPL 的过程是：

```text
用户需求
→ 规范化输入
→ 构件识别
→ slot 填充
→ partial / complete SPL draft
→ 缺口、假设、矛盾、溯源报告
→ 用户或后续系统继续完善
```

---

## 1.2 v4 当前定位

当前 v4 已经实现了一个可运行的 **reactive requirement-fidelity compiler**。

它的主要机制是：

```text
先生成 IR
再通过 Stage 9.5、ProducerIndex、ExecutableElementGate、ProvenanceAggregator、AssumptionBuilder 等发现缺口、阻止伪造、输出报告
```

v4 已经具备：

- Partial SPL 输出；
- FailureModeFact 到 partial ExceptionFlow skeleton；
- Required output producer 检查；
- Incomplete delegation diagnostic；
- Assumed command 不渲染；
- Source / section / packet provenance；
- Deterministic readable report；
- Validation / adapter warning / compile diagnostic 分层；
- LLM Adapter Engine 的 evidence-bound hard fact extraction。

v4 的不足不是方向错误，而是：

```text
构件生成规则仍分散在 Bridge、Stage 9.5、ProducerIndex、Gate 和 prompts 中。
```

下一阶段应把这些隐式规则显式化、中心化，并逐步前移到构件生成阶段。

---

# 2. 核心架构思想：IRS-driven Compiler

## 2.1 IRS 的定义

IRS 是 **Information Requirements Spec**，即 SPL 构件的信息需求规范。

IRS 不是 SPL grammar 的简单派生物。更准确地说：

```text
SPL Grammar + Requirement Semantics + Compiler Policy → IRS
```

三者职责不同：

| 层次                    | 负责什么  | 示例                                                                   |
| --------------------- | ----- | -------------------------------------------------------------------- |
| SPL Grammar           | 语法合法性 | EXCEPTION\_FLOW 如果出现，必须有 CONDITION；body 可以是 0 个或多个 BLOCK             |
| Requirement Semantics | 需求完整性 | 一个完整 exception flow 需要 handler\_action                               |
| Compiler Policy       | 编译策略  | 有 condition 无 handler 时可渲染 partial ExceptionFlow，并报 missing\_handler |

不能把 grammar-required slot、semantic-required slot、renderability slot 混为一谈。

---

## 2.2 IRS 的目标

IRS 的目标不是增加一套复杂 validator，而是统一驱动：

```text
1. Stage prompt
2. LLM 输出 schema
3. Stage-local slot checking
4. Stage-local diagnostics
5. Stage 9.5 global consolidation
6. ExecutableElementGate
7. ReportRenderer
8. 测试用例
```

理想状态下，diagnostic 不是由大量散落的 if/else 硬编码出来，而是由 construct slot satisfaction 自然产生。

---

## 2.3 IRS 不替代 Stage 9.5

IRS 负责 local construct-level checking。

Stage 9.5 仍然保留，职责从“主要发现者”逐步转为：

```text
1. 汇总 stage-local diagnostics；
2. 去重；
3. 运行跨构件一致性检查；
4. 处理 required output producer；
5. 处理 worker handoff consistency；
6. 处理 gate 后二次诊断；
7. 计算 completeness 所需输入。
```

原因：很多问题不是单个 construct 内部能发现的，例如：

- required output 是否有 producer；
- variable 是否 use-before-def；
- worker handoff binding 是否匹配；
- constraint 和 step 是否冲突；
- child worker 是否被调用；
- invoke target 是否存在；
- 多 worker graph 是否一致。

因此最终架构是：

```text
IRS-driven local checking
+
Stage 9.5 global consistency checking
```

---

# 3. IRS 数据模型

## 3.1 SlotSpec

```python
@dataclass
class SlotSpec:
    slot_name: str

    # 如果 construct 已经被 materialized，语法上是否必须有
    syntax_required: bool = False

    # 生成 partial construct 至少需要什么
    required_for_partial: bool = False

    # 生成 semantically complete construct 需要什么
    required_for_complete: bool = False

    # 缺失该 slot 时是否仍允许渲染 partial SPL
    renderable_without: bool = False

    # 哪类证据可以满足该 slot
    evidence_kinds: list[str] = field(default_factory=list)

    # 缺失时触发的 diagnostic kind
    missing_diagnostic: str | None = None

    # 是否允许从其他 slot 推断
    can_be_inferred: bool = False

    # 是否允许 LLM 在 prompt 中提出 assumption，但不渲染进 SPL
    can_be_suggested: bool = True

    # 备注，用于 prompt 生成
    notes: str | None = None
```

---

## 3.2 ConstructIRS

```python
@dataclass
class ConstructIRS:
    construct_type: str

    # construct 自身是否可默认生成
    existence_policy: Literal[
        "source_signal_required",
        "compiler_default_allowed",
        "grammar_required_if_parent_exists"
    ]

    # 哪些 source signals 允许 materialize 该 construct
    source_signals: list[str]

    # slot 定义
    slots: list[SlotSpec]

    # 如果没有 source signal 应如何处理
    no_demand_behavior: Literal[
        "do_not_generate",
        "generate_default",
        "report_ambiguity"
    ] = "do_not_generate"

    # 是否允许 partial rendering
    partial_rendering_allowed: bool = False

    # 构件级说明，用于 prompt
    description: str | None = None
```

---

## 3.3 SlotSatisfaction

```python
@dataclass
class SlotSatisfaction:
    slot_name: str
    status: Literal["satisfied", "missing", "inferred", "assumed", "not_applicable"]
    source_span_ids: list[str] = field(default_factory=list)
    source_section_id: str | None = None
    source_packet_id: str | None = None
    relation: Literal["direct", "normalized", "inferred", "assumed"] | None = None
    diagnostic_kind: str | None = None
    explanation: str | None = None
```

---

## 3.4 ConstructSatisfactionReport

```python
@dataclass
class ConstructSatisfactionReport:
    construct_id: str
    construct_type: str
    slots: list[SlotSatisfaction]
    completeness: Literal["complete", "partial", "blocked"]
    renderable: bool
    diagnostics: list[CompileDiagnostic]
```

每个 Stage 在生成一个关键 construct 时，应同步产出或可推导出该 report。

---

# 4. 关键 SPL 构件 IRS

## 4.1 EXCEPTION\_FLOW IRS

语法事实：

- `EXCEPTION_FLOW` 在 worker 中是 `{EXCEPTION_FLOW}`，即 0 个或多个。
- 如果 materialized，则必须有 `CONDITION`。
- body 是 `{BLOCK}`，可以为空。

需求语义：

- 有 condition 但无 handler\_action，是 partial exception flow。
- handler\_action 不应由系统猜测。

```python
EXCEPTION_FLOW_IRS = ConstructIRS(
    construct_type="EXCEPTION_FLOW",
    existence_policy="source_signal_required",
    source_signals=[
        "failure_mode",
        "exception_condition",
        "error_condition",
        "missing_state",
        "invalid_state",
        "refusal",
        "unavailable_resource",
        "provenance_failure",
    ],
    partial_rendering_allowed=True,
    slots=[
        SlotSpec(
            slot_name="condition",
            syntax_required=True,
            required_for_partial=True,
            required_for_complete=True,
            evidence_kinds=["failure_mode", "exception_condition"],
        ),
        SlotSpec(
            slot_name="handler_action",
            syntax_required=False,
            required_for_complete=True,
            renderable_without=True,
            evidence_kinds=["handler_action", "recovery_step"],
            missing_diagnostic="missing_handler",
            can_be_suggested=True,
            notes="Do not invent handler actions. If missing, keep partial exception flow and emit missing_handler."
        ),
        SlotSpec(
            slot_name="trigger_step",
            syntax_required=False,
            required_for_complete=False,
            renderable_without=True,
            evidence_kinds=["trigger_step"],
            missing_diagnostic=None,
            notes="Post-MVP. Trigger association may be handled by global analysis."
        )
    ]
)
```

Rules:

```text
No failure signal → do not generate EXCEPTION_FLOW.
Concrete failure condition → generate partial EXCEPTION_FLOW.
Condition + handler action → generate complete EXCEPTION_FLOW.
Condition only → missing_handler.
Vague 'handle errors properly' → do not generate concrete EXCEPTION_FLOW; emit type_or_contract_ambiguity.
```

---

## 4.2 MAIN\_WORKER IRS

语法事实：

- Worker instruction requires `WORKER_NAME` and `MAIN_FLOW`.
- Static description / purpose is optional.
- Inputs and outputs are optional.

需求语义：

- 不应仅因为模板需要 worker 就生成空可执行 worker。
- 必须有明确 task behavior / process / action 才能生成可执行 MainWorker。

```python
MAIN_WORKER_IRS = ConstructIRS(
    construct_type="MAIN_WORKER",
    existence_policy="source_signal_required",
    source_signals=["task_behavior", "process", "action", "user_request_to_perform_task"],
    partial_rendering_allowed=True,
    slots=[
        SlotSpec(
            slot_name="worker_name",
            syntax_required=True,
            required_for_partial=True,
            required_for_complete=True,
            can_be_inferred=True,
            notes="Compiler may normalize a worker name from task family."
        ),
        SlotSpec(
            slot_name="main_flow",
            syntax_required=True,
            required_for_partial=True,
            required_for_complete=True,
            evidence_kinds=["process", "behavior", "action"],
            missing_diagnostic="type_or_contract_ambiguity",
        ),
        SlotSpec(
            slot_name="purpose",
            syntax_required=False,
            required_for_complete=False,
            evidence_kinds=["task_family", "task_description"],
            can_be_inferred=True,
            notes="Purpose is design-level metadata, not grammar-required."
        ),
    ]
)
```

---

## 4.3 CHILD\_WORKER IRS

Child worker 不是语法自动需要的结构。它必须有足够 delegation / worker-boundary evidence。

```python
CHILD_WORKER_IRS = ConstructIRS(
    construct_type="CHILD_WORKER",
    existence_policy="source_signal_required",
    source_signals=["delegation", "subtask", "bounded_task", "worker_boundary"],
    partial_rendering_allowed=False,
    slots=[
        SlotSpec(
            slot_name="responsibility",
            required_for_partial=True,
            required_for_complete=True,
            evidence_kinds=["subtask_purpose", "delegated_responsibility"],
        ),
        SlotSpec(
            slot_name="input_contract",
            required_for_complete=True,
            renderable_without=False,
            evidence_kinds=["input_contract", "parent_binding"],
            missing_diagnostic="type_or_contract_ambiguity",
        ),
        SlotSpec(
            slot_name="output_contract",
            required_for_complete=True,
            renderable_without=False,
            evidence_kinds=["output_contract", "returned_result"],
            missing_diagnostic="type_or_contract_ambiguity",
        ),
        SlotSpec(
            slot_name="invocation_point",
            required_for_complete=True,
            renderable_without=False,
            evidence_kinds=["condition", "handoff_point"],
            missing_diagnostic="type_or_contract_ambiguity",
        ),
        SlotSpec(
            slot_name="result_handoff",
            required_for_complete=True,
            renderable_without=False,
            evidence_kinds=["output_binding", "result_binding"],
            missing_diagnostic="type_or_contract_ambiguity",
        ),
    ]
)
```

Rules:

```text
Optional subtask mention only → candidate/report, no child worker SPL.
Responsibility + IO + invocation + handoff → child worker + INVOKE_WORKER allowed.
Missing contract → type_or_contract_ambiguity.
```

---

## 4.4 GENERAL\_COMMAND IRS

```python
GENERAL_COMMAND_IRS = ConstructIRS(
    construct_type="GENERAL_COMMAND",
    existence_policy="source_signal_required",
    source_signals=["action", "operation", "process_step"],
    partial_rendering_allowed=False,
    slots=[
        SlotSpec(
            slot_name="action_text",
            syntax_required=True,
            required_for_complete=True,
            evidence_kinds=["action", "operation"],
            missing_diagnostic="assumed_command_not_renderable",
        ),
        SlotSpec(
            slot_name="source_evidence",
            required_for_complete=True,
            renderable_without=False,
            evidence_kinds=["source_span", "semantic_packet", "hard_fact"],
            missing_diagnostic="assumed_command_not_renderable",
        ),
        SlotSpec(
            slot_name="result_variable",
            syntax_required=False,
            required_for_complete=False,
            evidence_kinds=["result", "output", "derived_variable"],
        ),
    ]
)
```

Rules:

```text
Executable behavior must be source-backed.
Assumed behavior is report-only, not SPL command.
```

---

## 4.5 REQUEST\_INPUT IRS

```python
REQUEST_INPUT_IRS = ConstructIRS(
    construct_type="REQUEST_INPUT",
    existence_policy="source_signal_required",
    source_signals=["ask_user", "request_clarification", "prompt_user", "user_confirms", "obtain_user_input"],
    partial_rendering_allowed=False,
    slots=[
        SlotSpec(
            slot_name="prompt_text",
            syntax_required=True,
            required_for_complete=True,
            evidence_kinds=["ask_user", "clarification_request", "confirmation_request"],
            missing_diagnostic="assumed_command_not_renderable",
        ),
        SlotSpec(
            slot_name="value_target",
            syntax_required=True,
            required_for_complete=True,
            evidence_kinds=["input_variable", "confirmation_variable"],
            missing_diagnostic="type_or_contract_ambiguity",
        ),
    ]
)
```

Rules:

```text
Compiler cannot generate REQUEST_INPUT merely because information is missing.
The source must explicitly express asking, requesting clarification, prompting, or user confirmation.
```

---

## 4.6 CALL\_API IRS

```python
CALL_API_IRS = ConstructIRS(
    construct_type="CALL_API",
    existence_policy="source_signal_required",
    source_signals=["api", "tool", "connector", "source_repository", "external_system"],
    partial_rendering_allowed=False,
    slots=[
        SlotSpec(
            slot_name="api_name",
            syntax_required=True,
            required_for_complete=True,
            evidence_kinds=["api_ref", "integration_ref"],
            missing_diagnostic="type_or_contract_ambiguity",
        ),
        SlotSpec(
            slot_name="integration_evidence",
            required_for_complete=True,
            evidence_kinds=["connector", "repository", "tool"],
            missing_diagnostic="type_or_contract_ambiguity",
        ),
        SlotSpec(
            slot_name="response_binding",
            required_for_complete=False,
            evidence_kinds=["response", "output_variable"],
        ),
    ]
)
```

---

## 4.7 INVOKE\_WORKER IRS

```python
INVOKE_WORKER_IRS = ConstructIRS(
    construct_type="INVOKE_WORKER",
    existence_policy="source_signal_required",
    source_signals=["accepted_handoff", "delegated_subtask", "invoke_worker"],
    partial_rendering_allowed=False,
    slots=[
        SlotSpec(
            slot_name="target_worker",
            syntax_required=True,
            required_for_complete=True,
            evidence_kinds=["worker_spec", "accepted_worker_boundary"],
            missing_diagnostic="type_or_contract_ambiguity",
        ),
        SlotSpec(
            slot_name="handoff_id",
            required_for_complete=True,
            evidence_kinds=["worker_handoff"],
            missing_diagnostic="type_or_contract_ambiguity",
        ),
        SlotSpec(
            slot_name="input_bindings",
            required_for_complete=True,
            evidence_kinds=["input_binding"],
            missing_diagnostic="type_or_contract_ambiguity",
        ),
        SlotSpec(
            slot_name="output_bindings",
            required_for_complete=True,
            evidence_kinds=["output_binding"],
            missing_diagnostic="type_or_contract_ambiguity",
        ),
    ]
)
```

---

## 4.8 REQUIRED\_OUTPUT IRS

```python
REQUIRED_OUTPUT_IRS = ConstructIRS(
    construct_type="REQUIRED_OUTPUT",
    existence_policy="source_signal_required",
    source_signals=["required_output", "output_contract"],
    partial_rendering_allowed=True,
    slots=[
        SlotSpec(
            slot_name="output_name",
            syntax_required=True,
            required_for_partial=True,
            required_for_complete=True,
            evidence_kinds=["output_name", "output_contract"],
        ),
        SlotSpec(
            slot_name="output_type",
            syntax_required=True,
            required_for_partial=True,
            required_for_complete=True,
            evidence_kinds=["output_type", "output_description"],
            can_be_inferred=True,
        ),
        SlotSpec(
            slot_name="producer",
            syntax_required=False,
            required_for_complete=True,
            renderable_without=True,
            evidence_kinds=["producer_step", "handoff_output", "api_response"],
            missing_diagnostic="missing_output_producer",
        ),
    ]
)
```

Rules:

```text
Declared required output can be rendered.
Missing producer is a completion diagnostic, not a reason to invent producer step.
```

---

# 5. IRS 与 LLM Prompt 联动

## 5.1 为什么必须联动

如果 IRS 只在 Stage 9.5 或 validator 中使用，它只是另一个后置检查器。

真正的价值在于：

```text
IRS → Stage Prompt → LLM 输出时就按 slot 填充 → Stage-local diagnostics
```

这样才能从 reactive compiler 逐步演进为 proactive compiler。

---

## 5.2 IRSDrivenPromptBuilder

```python
class IRSDrivenPromptBuilder:
    def __init__(self, registry: SPLConstructRegistry):
        self.registry = registry

    def build_stage_prompt(
        self,
        stage_name: str,
        construct_types: list[str],
        base_task: str,
    ) -> str:
        checklists = [
            self.render_construct_checklist(self.registry.get(c))
            for c in construct_types
        ]
        return base_task + "\n\n" + "\n\n".join(checklists)

    def render_construct_checklist(self, irs: ConstructIRS) -> str:
        ...
```

---

## 5.3 Stage 4 Prompt 示例

Stage 4 FlowAssembler 需要 IRS：

```text
MAIN_FLOW
ALTERNATIVE_FLOW
EXCEPTION_FLOW
```

Prompt 插入内容示例：

```text
When generating EXCEPTION_FLOW:
- Generate it only if the source contains concrete failure/exception evidence.
- Slot condition:
  - syntax_required: true
  - required_for_partial: true
  - must be grounded in source evidence.
- Slot handler_action:
  - required_for_complete: true
  - do not invent if missing.
  - if missing, keep partial EXCEPTION_FLOW and emit missing_handler.
- If no concrete failure condition exists, do not generate EXCEPTION_FLOW.
- Do not generate REQUEST_INPUT or COMMAND as handler unless source explicitly states the handler behavior.
```

---

## 5.4 Stage 7 Prompt 示例

Stage 7 StepExtractor 需要 IRS：

```text
GENERAL_COMMAND
REQUEST_INPUT
CALL_API
INVOKE_WORKER
```

Prompt 插入内容示例：

```text
When generating REQUEST_INPUT:
- Only generate if the source explicitly says ask the user, request clarification, prompt the user, obtain user input, or user confirms.
- Do not generate REQUEST_INPUT merely because some information is missing.
- If asking the user is only your suggested fix, output an assumption/suggestion, not a StepIR.

When generating INVOKE_WORKER:
- Only generate if there is an accepted handoff with target worker and input/output bindings.
- Optional delegated subtask mention is not enough.
- If handoff is incomplete, emit type_or_contract_ambiguity and do not generate executable invoke step.
```

---

## 5.5 Stage 输出 schema 联动

每个 IRS-enabled Stage 应输出：

```json
{
  "construct_type": "EXCEPTION_FLOW",
  "construct_id": "exception_flow:missing_timeframe",
  "slots": {
    "condition": {
      "status": "satisfied",
      "source_span_ids": ["s12"],
      "relation": "direct"
    },
    "handler_action": {
      "status": "missing",
      "diagnostic_kind": "missing_handler"
    }
  },
  "completeness": "partial",
  "renderable": true
}
```

MVP 阶段可以不修改所有 Stage 输出 schema，但 Stage 4 和 Stage 7 应率先接入。

---

# 6. 全量架构

## 6.1 分层架构

```text
Layer 0: Source
    Raw NL / Structural NL / Skill-like NL

Layer 1: Input Normalization
    InputAdapterRegistry
    StructuralNLAdapter
    GenericNLAdapter
    LLM Adapter Engine
    CanonicalCompileInputValidator

Layer 2: Semantic Front-End
    Stage 1 SpanSlicer
    Stage 2 FieldRouter
    Stage 3 AmbiguityResolver

Layer 3: Construct Planning
    Stage 3.5 WorkerBoundaryPlanner
    Stage 3.6 WorkerPlanValidator
    SPLConstructRegistry / IRS

Layer 4: IRS-driven Construct Assembly
    Stage 4 FlowAssembler
    Stage 5 BlockAssembler
    Stage 6 ResourceExtractor
    Stage 7 StepExtractor
    Stage 8 ProfileExtractor
    Stage 9 ConstraintExtractor

Layer 5: Global Analysis and Consolidation
    Stage 9.5 IRNormalizer
    DiagnosticConsolidator
    ProducerIndex
    LLMConflictAnalyzer
    Future UseDefAnalyzer
    Future WorkerGraphValidator

Layer 6: Renderability and Code Generation
    Stage 10 WorkerAssembler
    ExecutableElementGate
    Stage 11 SPLRenderer

Layer 7: Output and Feedback
    ProvenanceAggregator
    AssumptionBuilder
    CompletenessCalculator
    ReportRenderer
    Future InteractiveClarificationLayer
```

---

## 6.2 Stage 9.5 的最终职责

Stage 9.5 是 global analysis pass，不应消失。

职责：

```text
1. 收集 stage-local diagnostics；
2. 合并重复 diagnostics；
3. ProducerIndex required-output check；
4. LLMConflictAnalyzer 结果接入；
5. Worker/Handoff consistency check；
6. Gate 后二次 missing_handler；
7. completeness 输入准备；
8. 将不同来源 diagnostics 统一为 CompileDiagnostic。
```

---

# 7. Conflict / DataFlow 等分析模块的 MVP 策略

## 7.1 总原则

MVP 不优先引入复杂 rule-based 分析器。

原因：

```text
1. rule-based detector 会增加工程复杂度；
2. 当前最重要的是验证 partial SPL + diagnostics + provenance + report 的闭环；
3. 过早代码化会导致规则难以调整；
4. 但接口必须保留，避免后续从 prompt 迁移到 code 困难。
```

因此 MVP 采用：

```text
LLM-prompt-first implementation
+
rule-based-ready interface
```

---

## 7.2 Semantic Conflict Analyzer

### MVP 实现

MVP 使用 LLM prompt 做笼统 conflict 判断。

```python
class SemanticConflictAnalyzer(Protocol):
    def analyze(
        self,
        constraints: list[ConstraintIR],
        steps: list[StepIR],
        flows: FlowStructureIR | WorkerFlowPlanIR,
        symbols: SymbolTable,
        context: ConflictAnalysisContext,
    ) -> list[CompileDiagnostic]: ...
```

MVP 实现类：

```python
class LLMSemanticConflictAnalyzer:
    def analyze(...):
        # call LLM with structured summary
        # return non-blocking CompileDiagnostic list
```

MVP prompt 要求：

```text
- Identify only clear or likely semantic conflicts.
- Do not rewrite SPL.
- Do not invent missing steps.
- Return diagnostics only.
- Mark uncertain conflicts as warning/info, not validation error.
```

### 未来 rule-based 实现

保留接口：

```python
class RuleBasedSemanticConflictAnalyzer:
    def analyze(...): ...
```

未来可以处理确定性冲突，例如：

```text
prohibition: never ask user
+
REQUEST_INPUT step
→ policy_step_conflict
```

但 MVP 不实现该 rule-based 类。

---

## 7.3 DataFlow Analyzer

### MVP 实现

MVP 不实现完整 DataFlowAnalyzer。

保留当前：

```text
ProducerIndex
```

用于 required output producer 检查。

### 接口预留

```python
class DataFlowAnalyzer(Protocol):
    def analyze(
        self,
        steps: list[StepIR],
        symbols: SymbolTable,
        worker_plan: WorkerPlanIR | None,
        context: DataFlowAnalysisContext,
    ) -> list[CompileDiagnostic]: ...
```

MVP 实现：

```python
class NoOpDataFlowAnalyzer:
    def analyze(...):
        return []
```

未来实现：

```text
RuleBasedDataFlowAnalyzer
LLMAssistedDataFlowReviewer
```

ProducerIndex 不被 DataFlowAnalyzer 替代。二者并行输出 diagnostics，由 Stage 9.5 汇总。

---

## 7.4 Duplicate / Redundancy Analyzer

### MVP 实现

MVP 不实现复杂 duplicate detection。

如果需要演示，可用 LLM prompt 输出非阻断 warning：

```python
class LLMDuplicateRequirementAnalyzer:
    def analyze(...): ...
```

MVP 默认可关闭。

### 未来实现

保留接口：

```python
class RequirementRedundancyAnalyzer(Protocol):
    def analyze(
        self,
        spans: list[SpanIR],
        constraints: list[ConstraintIR],
        steps: list[StepIR],
        context: RedundancyAnalysisContext,
    ) -> list[CompileDiagnostic]: ...
```

未来可逐步加入：

```text
exact text duplicate
normalized text duplicate
embedding similarity
LLM semantic duplicate review
```

---

## 7.5 WorkerGraphValidator

### MVP 实现

MVP 保持现有 worker plan validation 和 ExecutableElementGate。

复杂 worker graph 不纳入 MVP。

### 接口预留

```python
class WorkerGraphValidator(Protocol):
    def validate(
        self,
        worker_plan: WorkerPlanIR,
        worker_ir: WorkerIR,
        context: WorkerGraphValidationContext,
    ) -> list[CompileDiagnostic]: ...
```

MVP 实现：

```python
class MinimalWorkerGraphValidator:
    def validate(...):
        # only validate single-level accepted handoff if present
```

未来扩展：

```text
cycle detection
orphan child worker
unused child worker
handoff IO type mismatch
cross-worker dataflow
nested child workers
```

---

# 8. MVP / v5 增量设计

## 8.1 v5 目标

v5 不是重写 v4，而是：

```text
将 v4 中散落的隐式 construct rules 显式化为 SPLConstructRegistry / IRS，
并让 Stage 4、Stage 7 率先 IRS-driven。
```

v5 目标：

```text
1. 建立 SPLConstructRegistry 最小版本；
2. 将 EXCEPTION_FLOW、REQUIRED_OUTPUT、GENERAL_COMMAND、REQUEST_INPUT、CALL_API、INVOKE_WORKER 的规则显式化；
3. IRS 驱动 Stage 4 / Stage 7 prompt；
4. Stage 4 / Stage 7 输出 slot satisfaction 信息；
5. Stage 9.5 汇总 stage-local diagnostics；
6. Semantic conflict 暂用 LLM analyzer，不实现 rule-based；
7. DataFlow 保持 ProducerIndex，不实现完整 UseDefAnalyzer；
8. 保持 v4 public result interface 不变。
```

---

## 8.2 v5 不做

```text
1. 不重写所有 Stage；
2. 不要求所有 IR 都下沉 TraceRef；
3. 不实现 rule-based semantic conflict detector；
4. 不实现完整 DataFlowAnalyzer；
5. 不实现完整 WorkerGraphValidator；
6. 不实现 semantic duplicate detection；
7. 不实现交互 UI；
8. 不改变 CompileResult / PipelineResult public schema。
```

---

## 8.3 v5 实施阶段

### Phase 1: SPLConstructRegistry 最小实现

交付：

```text
src/nl2spl/compiler/construct_registry.py
```

包含：

```text
SlotSpec
ConstructIRS
SlotSatisfaction
ConstructSatisfactionReport
SPLConstructRegistry
```

首批 constructs：

```text
EXCEPTION_FLOW
REQUIRED_OUTPUT
GENERAL_COMMAND
REQUEST_INPUT
CALL_API
INVOKE_WORKER
CHILD_WORKER
```

---

### Phase 2: IRSDrivenPromptBuilder

交付：

```text
src/nl2spl/compiler/irs_prompt_builder.py
```

职责：

```text
1. 根据 Stage 名称选择 construct IRS；
2. 渲染 slot checklist；
3. 注入到 Stage 4 / Stage 7 prompt；
4. 保持 prompt 文本可测试、可 snapshot。
```

---

### Phase 3: Stage 4 接入 IRS

目标：

```text
FlowAssembler 使用 EXCEPTION_FLOW IRS。
```

行为：

```text
Failure condition only → partial ExceptionFlow + missing_handler。
No failure signal → no ExceptionFlow。
Vague handle errors properly → type_or_contract_ambiguity，不生成 concrete flow。
```

输出：

```text
FlowStructureIR + construct satisfaction metadata / diagnostics。
```

---

### Phase 4: Stage 7 接入 IRS

目标：

```text
StepExtractor 使用 GENERAL_COMMAND / REQUEST_INPUT / CALL_API / INVOKE_WORKER IRS。
```

行为：

```text
Assumed behavior → no renderable step。
Missing source evidence → assumed_command_not_renderable。
REQUEST_INPUT only if source explicitly asks/prompt/confirms。
CALL_API only if source has API/tool/connector evidence。
INVOKE_WORKER only if accepted handoff exists。
```

---

### Phase 5: Stage 9.5 汇总改造

目标：

```text
Stage 9.5 收集 stage-local diagnostics，而不是重复发现同一问题。
```

职责：

```text
1. Merge diagnostics；
2. Deduplicate missing_handler；
3. ProducerIndex required-output check；
4. Gate after-check；
5. LLMConflictAnalyzer optional diagnostics；
6. Completeness input preparation。
```

---

### Phase 6: LLMConflictAnalyzer MVP

目标：

```text
暂用 LLM prompt 做 conflict 判断，不实现 rule-based。
```

实现：

```text
LLMSemanticConflictAnalyzer
```

要求：

```text
1. 输出 CompileDiagnostic；
2. 不直接修改 IR；
3. 不阻断 rendering，除非配置开启；
4. 默认 severity=warning/info；
5. 保留 RuleBasedSemanticConflictAnalyzer 接口位。
```

---

### Phase 7: Resource Extractor Hardening

目标：

```text
减少 Stage 6 schema-looking variable noise。
```

实现：

```text
reserved name filter
looks_like_ir_field()
resource output verifier
prompt hardening
```

禁止变量：

```text
span_id
source_section_id
source_packet_id
main_flow_spans
exception_flows
block_id
flow_id
step_id
```

---

### Phase 8: Regression and E2E

测试：

```text
1. v4 existing tests must pass。
2. Failure condition only。
3. Required output without producer。
4. Vague failure policy。
5. REQUEST_INPUT without ask signal。
6. Incomplete delegation。
7. Complete source-backed delegation。
8. LLM conflict analyzer smoke test。
9. IRS prompt snapshot test。
10. Stage 4/7 slot satisfaction unit tests。
```

---

# 9. 接口预留原则

## 9.1 Prompt-first, Code-ready

所有 MVP 中由 LLM prompt 完成的分析模块，都必须遵循：

```text
1. 有明确 Protocol / interface；
2. LLM 实现类与未来 rule-based 实现类共用同一接口；
3. 输出统一为 CompileDiagnostic / TraceRecord / CompileAssumption；
4. 不让 prompt 结果散落到 pipeline 其他位置；
5. Stage 9.5 只消费接口输出，不关心背后是 LLM 还是 rule-based。
```

---

## 9.2 禁止 prompt 逻辑不可迁移

不允许：

```text
1. 在 prompt 中定义一套无法被结构化表示的隐式规则；
2. 让 Stage 依赖自然语言字符串判断 conflict 类型；
3. 让 LLM 直接修改 SPL / IR；
4. 让 LLM 输出非结构化 warning 文本；
5. 让 LLM 生成未注册 diagnostic kind。
```

必须：

```text
1. prompt 输入结构化；
2. prompt 输出结构化；
3. diagnostic kind 使用注册表；
4. 每条 diagnostic 有 target_ref、source_span_ids、message、suggested_resolution；
5. 可被未来 code implementation 替代。
```

---

# 10. Diagnostic Registry

为了支持 IRS 与 LLM analyzers，建议定义 Diagnostic Registry。

```python
@dataclass
class DiagnosticSpec:
    kind: str
    default_severity: Literal["info", "warning", "error"]
    blocks_completion: bool
    description: str
    allowed_targets: list[str]
```

首批 kind：

```text
missing_handler
missing_output_producer
type_or_contract_ambiguity
assumed_command_not_renderable
unmapped_behavior_span
missing_provenance
semantic_conflict
redundant_requirement
```

MVP 默认启用：

```text
missing_handler
missing_output_producer
type_or_contract_ambiguity
assumed_command_not_renderable
unmapped_behavior_span
missing_provenance
semantic_conflict  # only if LLMConflictAnalyzer enabled
```

Post-MVP：

```text
redundant_requirement
policy_step_conflict
use_before_def
worker_graph_inconsistency
```

---

# 11. 与当前 v4 的关系

## 11.1 v4 保持为稳定基线

v5 不推翻 v4。

保持：

```text
InputAdapterRegistry
CanonicalCompileInput
Stage 1-11 pipeline
FailureModeBridge
DelegationIntentBridge
ProducerIndex
ExecutableElementGate
ProvenanceAggregator
AssumptionBuilder
CompletenessCalculator
ReportRenderer
PipelineResult / CompileResult
```

新增：

```text
SPLConstructRegistry
IRSDrivenPromptBuilder
Stage 4 IRS integration
Stage 7 IRS integration
LLMConflictAnalyzer interface + MVP implementation
ResourceExtractor hardening
DiagnosticRegistry
```

---

## 11.2 v4 → v5 的核心变化

| 方面          | v4                                      | v5                                    |
| ----------- | --------------------------------------- | ------------------------------------- |
| 规则位置        | 分散在 bridge / normalizer / gate / prompt | 集中到 SPLConstructRegistry              |
| 缺口发现        | 主要 reactive                             | Stage 4/7 开始 proactive                |
| Prompt      | 手写规则                                    | IRS 自动生成 checklist                    |
| Diagnostics | Stage 9.5 + Gate 生成                     | Stage-local + Stage 9.5 consolidation |
| Conflict    | 暂未实现 / 延期                               | LLMConflictAnalyzer MVP               |
| DataFlow    | ProducerIndex                           | ProducerIndex 保持；DataFlow 接口预留        |
| Rule-based  | 局部已有 code guard                         | 不新增复杂 rule-based，预留接口                 |

---

# 12. 验收标准

## 12.1 架构验收

```text
1. SPLConstructRegistry 存在且可被 Stage 4/7 调用。
2. Stage 4 prompt 中包含 EXCEPTION_FLOW IRS checklist。
3. Stage 7 prompt 中包含 COMMAND / REQUEST_INPUT / CALL_API / INVOKE_WORKER IRS checklist。
4. Stage-local diagnostics 能进入 Stage 9.5 汇总。
5. Stage 9.5 不重复生成相同 missing_handler。
6. LLMConflictAnalyzer 使用统一接口，输出 CompileDiagnostic。
7. ReportRenderer 展示 IRS-driven diagnostics 与 conflict diagnostics。
8. 关闭 LLMConflictAnalyzer 时，pipeline 行为与 v4 兼容。
```

---

## 12.2 行为验收

```text
1. 用户没有 failure signal → 不生成 EXCEPTION_FLOW。
2. 用户有 failure condition 但无 handler → partial EXCEPTION_FLOW + missing_handler。
3. 用户只说 handle failures properly → 不生成 concrete EXCEPTION_FLOW，输出 type_or_contract_ambiguity。
4. REQUEST_INPUT 只有在 source 明确 ask/request/prompt/confirm 时生成。
5. CALL_API 没有 connector/API/tool evidence 时不生成。
6. INVOKE_WORKER 没有 accepted handoff 时不生成。
7. Required output 无 producer 时不合成 producer command。
8. Assumed command 不渲染。
9. LLMConflictAnalyzer 不修改 IR，只输出 diagnostics。
10. 所有新增 diagnostics 都进入 readable report。
```

---

# 13. 后续路线

## v5: IRS-explicit compiler

```text
显式化 construct rules。
Stage 4/7 率先 IRS-driven。
LLMConflictAnalyzer MVP。
ResourceExtractor hardening。
```

## v6: Proactive compiler

```text
更多 Stage 接入 IRS。
TraceRef 下沉到核心 IR。
Stage 9.5 主要做 global consistency。
UseDefAnalyzer / WorkerGraphValidator 接口实现。
```

## v7: Interactive compiler

```text
基于 MissingSlot / CompileAssumption / TraceRecord 生成澄清问题。
用户补充后注入 CanonicalCompileInput。
重新 compile。
```

---

# 14. 最终结论

NL2SPL 的最终架构应被定义为：

> 一个 IRS-driven requirement-to-SPL compiler。它以 SPL grammar 保证语法合法性，以 IRS 保证构件级信息需求，以 Stage 9.5 保证全局一致性，以 ExecutableElementGate 阻止未授权行为渲染，以 provenance/report 解释每个 SPL 元素来源、缺失、假设和建议。

当前 v4 已经是一个可运行的 reactive requirement-fidelity compiler。下一步 v5 不应重写系统，而应把 v4 中散落的隐式规则显式化为 SPLConstructRegistry / IRS，并优先接入 Stage 4 与 Stage 7。

对于 Semantic Conflict、Duplicate Detection、DataFlow Analysis 等复杂能力，MVP 先用 LLM prompt 做笼统实现或暂不启用；但必须通过 Protocol / Analyzer 接口保留 future rule-based implementation 的位置，避免后续 prompt 逻辑沉淀成不可迁移的隐性规则。

---

你的评估成立。当前文档已经能作为 **v5 架构提案**，但还缺少工程实施所需的几个硬边界：slot 判定规则、stage-local 数据落点、最终裁决权、diagnostic 去重、LLM analyzer 的 evidence-bound 约束等。

我刚才尝试把这些内容追加到画布文档中，但更新失败，原因是画布工具对正则锚点的兼容问题。下面给出可直接追加到文档末尾的修订内容，建议作为新的 **第 15 节：v5 工程实施补充规则**。

---

# 15. v5 工程实施补充规则

本节用于补齐前文作为架构提案时尚未完全 self-contained 的工程边界。实施 v5 时，本节规则优先级高于前文中存在歧义的表述。

---

## 15.1 SlotSpec 判定表

`syntax_required`、`required_for_partial`、`required_for_complete`、`renderable_without` 必须按以下优先级解释。

| 情况                                                           | 判定               | 编译行为                                                                               |
| ------------------------------------------------------------ | ---------------- | ---------------------------------------------------------------------------------- |
| missing `syntax_required`                                    | 构件语法不合法          | 不渲染该构件；产生 validation error 或 blocked diagnostic                                    |
| missing `required_for_partial`                               | partial 构件最低信息不足 | 不 materialize 该 construct；若存在 vague source signal，可输出 `type_or_contract_ambiguity` |
| missing `required_for_complete` 且 `renderable_without=True`  | 构件可 partial 渲染   | 渲染 partial SPL；产生对应 diagnostic；整体 completeness 通常为 partial                         |
| missing `required_for_complete` 且 `renderable_without=False` | 构件不可安全渲染         | 不渲染该构件或相关 executable element；产生 diagnostic                                         |
| slot satisfied by source evidence                            | source-backed    | 可进入后续 IR；是否最终渲染仍由 Gate / ProducerIndex 等最终裁决                                       |
| slot satisfied by assumption only                            | assumed          | 进入 assumption/report；默认不进入 executable SPL                                          |

补充说明：

```text
1. required_for_partial 只在 partial_rendering_allowed=True 的 construct 上有主要意义。
2. 对 partial_rendering_allowed=False 的 construct，required_for_partial 仅用于 candidate/report 表达，不代表可以渲染 partial SPL。
3. syntax_required 只表示语法要求，不表示需求完整性。
4. required_for_complete 表示需求/设计完整性要求，不等于 grammar requirement。
```

这也和 SPL grammar 的事实一致：例如 `EXCEPTION_FLOW` 本身在 worker 中是 `{EXCEPTION_FLOW}`，即可以不存在；但一旦 materialize 出 `EXCEPTION_FLOW`，语法上就需要 `CONDITION`，而 body `{BLOCK}` 可以为空。

---

## 15.2 Stage-local diagnostics 与 satisfaction report 的数据落点

v5 不改变现有 Stage return contract。Stage 4 / Stage 7 的 `ConstructSatisfactionReport` 通过 orchestrator side-channel 写入 `intermediate_results`。

推荐结构：

```python
intermediate_results["construct_satisfaction"] = {
    "stage4": list[ConstructSatisfactionReport],
    "stage7": list[ConstructSatisfactionReport],
}

intermediate_results["stage_local_diagnostics"] = {
    "stage4": list[CompileDiagnostic],
    "stage7": list[CompileDiagnostic],
}
```

规则：

```text
1. Stage 4/7 原有 return value 保持不变。
2. IRS metadata 通过 orchestrator 写入 intermediate_results。
3. Stage 9.5 从 intermediate_results 读取 stage-local diagnostics 和 satisfaction reports。
4. 未来如果 Stage return contract 重构，再把 satisfaction reports 提升为显式返回值。
```

这样不会破坏 v4 已有接口。当前 v4 已经有 `PipelineResult.intermediate_results`，并且已有 `compile_diagnostics`、`traces`、`adapter_warnings`、`completeness`、`assumptions`、`readable_report` 等 public result 字段。

---

## 15.3 IRS、Stage 9.5、Gate、ProducerIndex 的最终裁决边界

v5 必须避免多个组件同时裁决同一件事。

| 组件                         | 负责什么                                                     | 不负责什么                                                                      |
| -------------------------- | -------------------------------------------------------- | -------------------------------------------------------------------------- |
| IRS / Stage-local checking | prompt/schema 约束、slot satisfaction、局部 diagnostic 预判      | 不做最终 renderability 裁决；不做 required output producer 最终裁决                     |
| Stage 9.5                  | 汇总、去重、全局一致性检查、completeness 输入准备                          | 不直接渲染 SPL；不替代 Gate                                                         |
| ExecutableElementGate      | Step/Command/INPUT/CALL_API/INVOKE_WORKER 是否进入 SPL 的最终裁决 | 不判断 required output 是否有 producer                                           |
| ProducerIndex              | required output 是否有合法 producer 的最终裁决                     | 不决定 step 是否可渲染；只消费 post-gate renderable producers 和 valid handoff bindings |
| SPLRenderer                | 只渲染已通过裁决的结构                                              | 不修补缺失 handler、producer、worker/API contract                                 |

核心规则：

```text
IRS may suggest non-renderability.
ExecutableElementGate decides final renderability.
ProducerIndex decides final output producer status.
Stage 9.5 consolidates all decisions into CompileDiagnostic.
```

这和 v4 当前职责一致：`ProducerIndex` 已负责 required output producer 判断，`ExecutableElementGate` 已负责渲染前过滤 assumed / invalid command。

---

## 15.4 Diagnostic 去重规则

Stage-local diagnostics、Gate diagnostics、ProducerIndex diagnostics 和 LLM analyzer diagnostics 需要统一去重。

建议 dedup key：

```python
dedup_key = (
    diagnostic.kind,
    diagnostic.target_ref,
    tuple(sorted(normalize_span_ids(diagnostic.source_span_ids))),
    diagnostic.missing_slot.slot_name if diagnostic.missing_slot else diagnostic.metadata.get("missing_slot"),
)
```

特殊规则：

```text
1. missing_handler 必须支持 gate 后重算。
2. 如果 Stage 4 认为 handler 存在，但 Gate 后 handler step 被过滤，则必须补发或保留 missing_handler。
3. Gate 后 missing_handler 优先级高于 Stage 4 的 pre-gate 判断。
4. 同一 target_ref 的 missing_handler 只显示一次，但 report 可说明它来自 gate 后重算。
```

---

## 15.5 REQUIRED_OUTPUT IRS 修正

Required output declaration 不应因为 exact type 不清楚而被阻断。

修正规则：

```text
output_name:
    required_for_partial=True
    required_for_complete=True

output_type:
    syntax_required=False at IRS level
    required_for_partial=False
    required_for_complete=False 或 weak required_for_complete
    renderable_without=True
    can_be_inferred=True
    ambiguity 可进入 type_or_contract_ambiguity

producer:
    required_for_complete=True
    renderable_without=True
    missing_diagnostic=missing_output_producer
```

说明：

```text
1. SPL variable declaration 最终需要 DATA_TYPE，但 compiler 可以使用保守类型推断，例如 text。
2. 类型不确定不应阻止 required output declaration。
3. 缺 producer 是 completion diagnostic，不是合成 producer command 的理由。
4. ProducerIndex 是 producer status 的最终裁决者。
```

---

## 15.6 CALL_API IRS 修正

CALL_API 必须区分 `integration mention` 与 `executable API call`。

```text
integration mention:
    用户提到 connector、repository、external system、tool。
    这只能生成 resource/API candidate 或 compile hint。

executable API call:
    用户明确要求调用某个 API/tool/connector 执行动作，并且有 call action evidence。
    只有这种情况才能生成 CALL_API。
```

修正后的 source signal：

```text
api_call_action
tool_call_action
connector_action
```

必要 slot：

```text
api_name / integration_ref
integration_evidence
call_action
```

规则：

```text
source_repository as input/context → resource candidate, not CALL_API.
named API/tool + executable action → CALL_API candidate.
missing api_name / integration_evidence / call_action → no CALL_API rendering, type_or_contract_ambiguity.
```

---

## 15.7 CHILD_WORKER 与 WORKER_CANDIDATE 修正

`CHILD_WORKER` 不应由 optional subtask mention 直接 materialize。

应区分：

```text
DELEGATION_INTENT / WORKER_CANDIDATE:
    用户提到 optional subtask、source gathering、template matching 等。
    只进入 candidate/report/provenance。

CHILD_WORKER:
    已有 accepted worker boundary，且具备 responsibility、input contract、output contract、invocation point、result handoff。
    才能渲染为 child worker SPL。
```

建议新增：

```python
WORKER_CANDIDATE_IRS = ConstructIRS(
    construct_type="WORKER_CANDIDATE",
    existence_policy="source_signal_required",
    source_signals=["delegation", "subtask", "optional_subtask", "template_matching", "source_gathering"],
    partial_rendering_allowed=False,
    slots=[
        SlotSpec(
            slot_name="candidate_responsibility",
            required_for_partial=True,
            required_for_complete=True,
            evidence_kinds=["subtask_name", "delegation_intent"],
        ),
        SlotSpec(
            slot_name="promotion_requirements",
            required_for_complete=False,
            evidence_kinds=["input_contract", "output_contract", "invocation_point", "handoff"],
            missing_diagnostic="type_or_contract_ambiguity",
            renderable_without=False,
            notes="If promotion requirements are missing, keep as candidate/report only."
        ),
    ]
)
```

---

## 15.8 LLMConflictAnalyzer evidence-bound 约束

LLMConflictAnalyzer 不能成为新的 hallucination 入口。

每条 `semantic_conflict` diagnostic 必须满足：

```text
1. 至少引用一个 source_span_id，或引用可解析的 section/packet evidence。
2. target_ref 必须指向已有 ConstraintIR、StepIR、FlowIR、WorkerIR 或 variable。
3. 不得发明新的 policy、step、worker、变量。
4. 不得修改 IR 或 SPL。
5. uncited conflict 默认丢弃；如果需要保留，只能降级为 non-blocking analysis warning，且不进入 compile_diagnostics。
6. 默认 severity=warning/info。
7. 默认 blocks_completion=False，除非配置显式开启。
```

建议增加 verifier：

```python
class LLMConflictDiagnosticVerifier:
    def verify(self, diagnostic: CompileDiagnostic, context: ConflictAnalysisContext) -> bool:
        ...
```

Verifier 检查：

```text
known diagnostic kind
known target_ref
known source_span_ids or known section/packet evidence
no invented construct references
```

---

## 15.9 v5 数据流图

```text
Stage 4 / Stage 7
    ↓
IR output remains unchanged
    ↓
construct_satisfaction side-channel
    intermediate_results["construct_satisfaction"]
    intermediate_results["stage_local_diagnostics"]
    ↓
Stage 9.5
    - read stage-local diagnostics
    - run ProducerIndex
    - run optional LLMConflictAnalyzer
    - deduplicate diagnostics
    - prepare completeness inputs
    ↓
Stage 10 WorkerAssembler
    ↓
ExecutableElementGate
    - final renderability authority
    - may emit assumed_command_not_renderable
    - may cause gate-after missing_handler
    ↓
Stage 11 SPLRenderer
    ↓
Post-processing
    ProvenanceAggregator
    AssumptionBuilder
    CompletenessCalculator
    ReportRenderer / FeedbackReportRenderer
```

---

## 15.10 新增文件与现有文件关系

建议新增文件：

| 文件                                                   | 作用                                                                                                     |
| ---------------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| `src/nl2spl/compiler/construct_registry.py`          | SlotSpec、ConstructIRS、SPLConstructRegistry、SlotSatisfaction、ConstructSatisfactionReport                |
| `src/nl2spl/compiler/irs_prompt_builder.py`          | 根据 IRS 生成 Stage prompt checklist                                                                       |
| `src/nl2spl/compiler/diagnostic_registry.py`         | DiagnosticSpec 与 diagnostic kind 注册表                                                                   |
| `src/nl2spl/compiler/analyzers/semantic_conflict.py` | SemanticConflictAnalyzer Protocol、LLMSemanticConflictAnalyzer、future RuleBasedSemanticConflictAnalyzer |
| `src/nl2spl/compiler/analyzers/dataflow.py`          | DataFlowAnalyzer Protocol、NoOpDataFlowAnalyzer、future implementations                                  |
| `src/nl2spl/compiler/analyzers/redundancy.py`        | RequirementRedundancyAnalyzer Protocol、future duplicate detection                                      |

现有组件处理：

| 现有组件                            | v5 处理                                            |
| ------------------------------- | ------------------------------------------------ |
| InputAdapterRegistry / adapters | 保持不变                                             |
| CanonicalCompileInputValidator  | 保持不变                                             |
| Stage 4 FlowAssembler           | prompt 接入 IRS；return contract 不变                 |
| Stage 7 StepExtractor           | prompt 接入 IRS；return contract 不变                 |
| Stage 9.5 IRNormalizer          | 增加 stage-local diagnostics 汇总逻辑                  |
| ProducerIndex                   | 保持最终 producer authority                          |
| ExecutableElementGate           | 保持最终 renderability authority                     |
| ReportRenderer                  | 展示新增 diagnostics                                 |
| FeedbackReportRenderer          | 同步展示新增 diagnostics / assumptions / traces        |
| PipelineResult / CompileResult  | 字段不变；如 DiagnosticKind 是 Literal/Enum，需要扩展 kind 值 |

---

## 15.11 Public schema 变化原则

v5 不改变 `PipelineResult` / `CompileResult` 的字段结构。

如果 `DiagnosticKind` 在代码中是 `Literal[...]` 或 enum，则需要扩展允许值：

```text
semantic_conflict
redundant_requirement  # reserved / disabled by default
```

规则：

```text
1. 新 diagnostic kind 是 schema-compatible change，但可能需要更新 type annotation。
2. LLMConflictAnalyzer 默认可关闭。
3. 关闭时 v4 行为应保持兼容。
```

---

## 15.12 追加验收标准

```text
1. Stage-local diagnostics / ConstructSatisfactionReport 通过 intermediate_results 承载，不破坏原 Stage return contract。
2. Stage 9.5 按 dedup key 去重，不重复生成相同 missing_handler。
3. Gate 后 missing_handler 能覆盖 pre-gate 误判。
4. ProducerIndex 仍是 required output producer 的最终裁决者。
5. ExecutableElementGate 仍是 step/command renderability 的最终裁决者。
6. LLMConflictAnalyzer 输出必须 evidence-bound。
7. ReportRenderer 和 FeedbackReportRenderer 都展示新增 diagnostics。
8. REQUIRED_OUTPUT 类型不确定不阻断 output declaration。
9. CALL_API 不因 source_repository/context mention 自动生成。
10. optional subtask mention 只生成 WORKER_CANDIDATE / DELEGATION_INTENT，不生成 CHILD_WORKER。
```

---
