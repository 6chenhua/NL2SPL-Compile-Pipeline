# NL2SPL 设计文档 v4

**更新时间**: 2026-05-16  
**代码状态**: 已完成 Partial SPL MVP、MVP+ Structural Provenance、LLM Adapter Engine 接入与 live E2E 验收  
**核心定位**: NL2SPL 是从不完备自然语言需求到 SPL 高层设计草案的渐进式编译器。

---

## 1. 核心理念

NL2SPL 不以“一次性生成完整可执行 SPL”为目标。它的目标是最大努力把已有需求结构化为 partial/complete SPL draft，并把缺失、不明确、冲突和 AI 推断显式暴露出来。

当前实现遵循以下原则：

1. **Source-backed first**: 只有源文本、adapter hard fact、合法 handoff 或确定性 compiler scaffold 支持的内容才能进入可执行 SPL。
2. **No silent fabrication**: 不静默发明 exception handler、required output producer、worker/API contract 或 generic fallback command。
3. **Partial SPL is valid output**: 缺信息时保留可确定结构，例如空 exception flow skeleton、required output contract、delegation intent trace。
4. **Diagnostics over guessing**: 缺失或不完整信息进入 `CompileDiagnostic`，而不是被 LLM 或 normalizer 补全。
5. **Provenance is first-class**: 主要 SPL 元素通过 `TraceRecord` 关联到 source span、section、packet。
6. **Report is deterministic**: readable report 由代码生成，不再通过另一个 LLM pass 总结。
7. **No demand, no structure**: 用户没有表达某类 SPL 结构时，不生成该结构，也不输出该结构缺失诊断。

---

## 2. 当前系统边界

### 2.1 已实现

- Structural NL adapter 和 Generic NL adapter。
- 可选 LLM Adapter Engine，用于从 adapter context 中提取 evidence-bound hard facts。
- Canonical input contract:
  - `RawSection`
  - `SemanticPacket`
  - `EvidenceRef`
  - `VariableFact`
  - `FailureModeFact`
  - `DelegationIntentFact`
  - `CompileHint`
- 11 个主 pipeline stage，加 Stage 3.5/3.6 worker boundary planner/validator。
- Failure mode bridge:
  - `FailureModeFact -> ExceptionFlow` skeleton。
- Delegation intent bridge:
  - incomplete delegation -> `type_or_contract_ambiguity` diagnostic。
- Stage 9.5 requirement-fidelity normalizer。
- `ProducerIndex`。
- `ExecutableElementGate`。
- `ProvenanceAggregator`。
- `AssumptionBuilder`。
- `Completeness` calculator。
- deterministic `ReportRenderer`。
- deterministic `FeedbackReportRenderer`。
- CLI 输出:
  - `final_spl.txt`
  - `compile_report.txt`
  - `feedback_report.md`
  - stderr status summary。

### 2.2 暂未实现或刻意延期

- 多轮澄清 UI。
- 完整 TraceRef 字段下沉到所有 IR 类型。
- 完整 semantic duplicate detection。
- 完整 policy conflict detection。
- 深层嵌套 flow 修复。
- 完整 multi-worker graph。
- candidate-to-handoff 强链接。
- Full structural NL pipeline with LLM stages 的稳定 golden baseline。
- resource extractor 对 schema-looking variable 的彻底过滤。

---

## 3. 输入适配层

### 3.1 Adapter Registry

入口是 `InputAdapterRegistry`。当前默认顺序：

1. `StructuralNLAdapter`
2. `GenericNLAdapter`

配置项:

```python
PipelineConfig.adapter_llm_engine: "off" | "generic_only" | "structural_enrich" | "all"
```

环境变量:

```powershell
NL2SPL_ADAPTER_LLM_ENGINE=off|generic_only|structural_enrich|all
```

默认值为 `off`，保证向后兼容。非法值直接 `ValueError`，不静默 fallback。

### 3.2 Structural NL

Structural NL 识别 7 个稳定 section：

1. Task family
2. Inputs for each run
3. Required outputs
4. Reusable process
5. Policies
6. Failure handling
7. Delegation policy

Structural adapter 输出：

- `raw_sections`
- `semantic_packets`
- `hard_facts`
  - inputs
  - outputs
  - failure_modes
  - delegation_intents
- `compile_hints`
- `adapter_warnings`

关键规则：

- `Inputs for each run` 和 `Required outputs` 产生 hard facts。
- `Failure handling` 产生 `FailureModeFact`，但不产生 handler step。
- `Delegation policy` 产生 `DelegationIntentFact`，但不代表可执行 handoff。
- 所有 adapter hard facts 必须带 `EvidenceRef`。

### 3.3 Generic NL

Generic adapter 是 freeform fallback。默认无 LLM 时保持 legacy passthrough。

当启用 LLM adapter engine 时，它会先构造 synthetic provenance context：

- `RawSection.section_id = "sec_freeform_input"`
- `SemanticPacket.packet_id = "p_freeform_000"` 等

然后调用 LLM fact extraction，并通过 parser/verifier 过滤：

- uncited fact 不进入 hard facts。
- unknown section/packet 的 fact 不进入 hard facts。
- reserved compiler/schema variable 不进入 hard facts。
- LLM warning 保留为 adapter warning。

### 3.4 LLM Adapter Engine

LLM Adapter Engine 的职责不是生成 SPL，也不是生成 step。它只提取 evidence-bound facts：

```json
{
  "inputs": [],
  "outputs": [],
  "failure_modes": [],
  "delegation_intents": [],
  "warnings": []
}
```

反伪造规则：

- 不生成 handler action。
- 不生成 producer step。
- 不补 worker/API contract。
- 没有 source section/packet evidence 的 fact 被拒绝。
- 内部字段名如 `span_id`、`source_section_id`、`main_flow_spans`、`exception_flows` 等被拒绝。

---

## 4. Canonical Compile Input

Pipeline 统一消费 `CanonicalCompileInput`：

```python
@dataclass
class CanonicalCompileInput:
    source_schema: str
    schema_version: str
    raw_text: str
    raw_sections: list[RawSection]
    semantic_packets: list[SemanticPacket]
    hard_facts: HardFacts
    compile_hints: CompileHints
    warnings: list[AdapterWarning]
    detection: AdapterDetectionResult | None
```

`CanonicalCompileInputValidator` 检查：

- schema/raw text 非空。
- section id 唯一。
- packet id 唯一。
- packet 引用的 section 存在。
- hard fact name 不重复。
- evidence section/packet 存在，且 packet 属于对应 section。
- 不允许出现 `confidence` 字段。

---

## 5. Pipeline 总览

当前 orchestrator 主流程：

```text
Input text
  -> InputAdapterRegistry
  -> CanonicalCompileInputValidator
  -> Stage 1 Span Slicing
  -> Stage 2 Field Routing
  -> Stage 3 Ambiguity Resolution
  -> optional Stage 3.5 Worker Boundary Planning
  -> optional Stage 3.6 Worker Plan Validation
  -> Stage 4 Flow Assembly
  -> Fact Bridge: FailureModeFact -> ExceptionFlow skeleton
  -> Stage 5 Block Assembly
  -> Stage 6 Resource Extraction
  -> Stage 7 Step Extraction
  -> Stage 8 Profile Extraction
  -> Stage 9 Constraint Extraction
  -> Stage 9.5 IR Normalization
  -> Stage 10 Worker Assembly
  -> Executable Element Gate
  -> Stage 11 SPL Rendering
  -> Provenance Aggregation
  -> Delegation Intent Diagnostics
  -> Completeness
  -> Assumptions
  -> Readable Report
```

### 5.1 Stage 表

| Stage | 名称 | 类型 | 输入 | 输出 |
|---|---|---|---|---|
| Adapter | Input Adapter | Code + optional LLM | raw text | `CanonicalCompileInput` |
| 1 | Span Slicing | LLM or adapter-aware code | canonical input | `list[SpanIR]` |
| 2 | Field Routing | LLM or adapter-aware code | spans + canonical input | `FieldRouteIR` |
| 3 | Ambiguity Resolution | LLM | spans + routes | resolved spans/routes |
| 3.5 | Worker Boundary Planning | LLM | spans + routes + canonical input | `WorkerPlanIR` |
| 3.6 | Worker Plan Validation | Code | `WorkerPlanIR` | validation result |
| 4 | Flow Assembly | LLM | spans + routes | `FlowStructureIR` or `WorkerFlowPlanIR` |
| Bridge | Failure Mode Bridge | Code | `FailureModeFact` + spans + flow | partial `ExceptionFlow` |
| 5 | Block Assembly | LLM | spans + routes + flow | `BlockStructureIR` or `WorkerBlockPlanIR` |
| 6 | Resource Extraction | LLM | spans/routes/flow/blocks/canonical | `ResourceRegistryIR`, `SymbolTable` |
| 7 | Step Extraction | LLM | spans/routes/flow/blocks/symbols | steps + diagnostics |
| 8 | Profile Extraction | LLM | spans/routes/symbols | `AgentProfileIR` |
| 9 | Constraint Extraction | LLM | spans/routes/flow/blocks/symbols/steps/canonical | constraints |
| 9.5 | IR Normalization | Code | IR bundle | normalized IR + diagnostics |
| 10 | Worker Assembly | Code | normalized IR | `WorkerIR` |
| Gate | Executable Element Gate | Code | `WorkerIR` + worker plan | filtered worker + diagnostics |
| 11 | SPL Rendering | Code | filtered worker + profile/resources | SPL text + validation |
| Post | Provenance/Report | Code | final IR + diagnostics | traces, assumptions, completeness, report |

---

## 6. Partial SPL 与 diagnostics

### 6.1 Diagnostic kinds

当前 public diagnostic kinds：

| Kind | 来源 | 含义 | Completion impact |
|---|---|---|---|
| `missing_handler` | Stage 9.5 + Gate | exception flow 没有 handler step 或 gate 后没有 renderable handler | partial |
| `missing_output_producer` | Stage 9.5 | required output 没有合法 producer | partial |
| `type_or_contract_ambiguity` | Stage 9.5 + delegation bridge | API/worker/request input/hand-off contract 不明确 | partial |
| `assumed_command_not_renderable` | Stage 9.5 + Gate | command 缺少 source evidence 或合法 handoff，被阻止渲染 | partial |
| `unmapped_behavior_span` | Stage 7 | 行为 span 没被映射为 executable step | partial |
| `missing_provenance` | ProvenanceAggregator | 元素缺少可靠 provenance | 默认不阻塞 completion，除非调用方调整 |

### 6.2 Validation 与 compile diagnostics 的区别

| 类型 | 含义 | 示例 | 对 completeness 的影响 |
|---|---|---|---|
| `validation_errors` | SPL/IR 硬性结构错误 | unknown variable, unknown step, unknown API | `blocked` |
| `validation_warnings` | 结构或数据流警告 | unused variable, uncovered spans | 不直接决定 |
| `adapter_warnings` | 输入适配告警 | empty section, duplicate section, LLM warning | 不直接决定 |
| `compile_diagnostics` | 需求不完备、歧义、假设、溯源缺口 | missing handler, missing producer | `blocks_completion=True` 时为 `partial` |

### 6.3 Completeness

当前计算规则：

```text
validation_errors 非空 -> blocked
任一 diagnostic.blocks_completion=True -> partial
否则 -> complete
```

Adapter warnings 不参与 completeness 计算。

---

## 7. 反伪造机制

### 7.1 ProducerIndex

`ProducerIndex` 用于判断 required output 是否有合法 producer。

合法 producer 包括：

- source-backed step output。
- valid invoke handoff 的 output binding。
- valid API handoff / CALL_API output。
- `metadata.origin == "compiler_unpack"` 的 compiler scaffold。

不合法 producer：

- Worker OUTPUTS declaration 本身。
- `VariableSpec.source` 本身。
- source_span_ids 为空且无合法 handoff 的 step。
- fake handoff_id。
- handoff step 上与 binding 不匹配的 `step.outputs`。

### 7.2 Executable Element Gate

Gate 位于 Stage 10 和 Stage 11 之间。它保证 renderer 只收到可渲染 step。

Step origin 分类：

| Origin | 条件 | 默认 renderable |
|---|---|---|
| `source_backed` | `source_span_ids` 非空，无 handoff_id | 是，但有 command-type guard |
| `handoff_generated` | `handoff_id` 非空 | 只有 handoff contract 合法时是 |
| `compiler_synthetic` | `metadata.origin == "compiler_unpack"` | 是 |
| `assumed` | 无 source、无 handoff、无合法 scaffold | 否 |

Command guard：

- `INVOKE_WORKER` 必须来自合法 handoff。
- `CALL_API` 必须有 concrete `integration_ref`，handoff 模式下必须匹配 handoff `api_ref`。
- `REQUEST_INPUT` 必须有 source span。
- source-backed `GENERAL_COMMAND` 可渲染。

被 gate 阻止的 step：

- 不进入 SPL。
- 进入 `StepRenderInfo`。
- 产生 `assumed_command_not_renderable` diagnostic。
- 若阻止的是 exception handler，gate 后再次产生 `missing_handler`。

### 7.3 Failure Mode Bridge

`bridge_failure_modes()` 把 adapter `FailureModeFact` 转为 partial `ExceptionFlow` skeleton。

规则：

- 只生成 exception flow 结构。
- 不生成 handler block 里的 command。
- 根据 `EvidenceRef` 或 section span 解析 source spans。
- 如果已有 exception flow 与 evidence span 或 condition text 重合，则跳过，避免重复。

### 7.4 Delegation Intent Bridge

`bridge_delegation_intents()` 处理 adapter `DelegationIntentFact`。

规则：

- Delegation intent 是 traceable fact，不是 executable handoff。
- 如果没有合法 handoff contract，发出 `type_or_contract_ambiguity`。
- 没有合法 handoff 时不渲染 `[INVOKE ...]`。
- Provenance report 仍展示 `delegation_intent:<name>` 和 `section=sec_delegation_policy`。

---

## 8. Provenance

### 8.1 TraceRecord

```python
@dataclass
class TraceRecord:
    target_ref: str
    source_span_ids: list[str]
    source_section_id: str | None
    source_packet_id: str | None
    relation: "direct" | "normalized" | "inferred" | "assumed"
    explanation: str
    needs_confirmation: bool
```

### 8.2 当前 trace 覆盖

`ProvenanceAggregator` 当前覆盖：

- worker
- child worker
- main/alternative/exception flow
- step
- constraint
- handoff
- delegation intent
- variable
- profile/persona/concepts

### 8.3 section/packet provenance

MVP+ 已实现 section/packet provenance 传播：

- flow trace 从 block spans 解析 section/packet。
- worker trace 从 `WorkerSpecIR.owned_span_ids` 解析 section/packet。
- handoff trace 从 invoke location hint 和 failure policy spans 解析 section/packet。
- variable trace 使用 producer step span、handoff binding、adapter `VariableFact`。
- delegation intent trace 使用 `EvidenceRef`。
- report 展示 `section=...` 和 `packet=...`。

### 8.4 Variable provenance 优先级

变量 provenance 不把 `VariableSpec.source` 当证据。优先级：

1. producer step 的 source spans。
2. valid handoff output binding。
3. adapter hard fact section/packet。
4. worker/output/input contract declaration。
5. 否则 relation=`assumed`，并可能产生 `missing_provenance`。

---

## 9. Public Result Interface

### 9.1 PipelineResult

当前 `PipelineResult` 字段：

```python
@dataclass
class PipelineResult:
    spl_text: str
    validation_errors: list[str]
    validation_warnings: list[str]
    compile_diagnostics: list[Any]
    traces: list[Any]
    adapter_warnings: list[str]
    completeness: Completeness
    assumptions: list[CompileAssumption]
    readable_report: str
    intermediate_results: dict[str, Any]
    final_spl_path: Path | None

    @property
    def diagnostics(self) -> list[Any]:
        return self.compile_diagnostics
```

### 9.2 CompileResult

`CompileResult` 是更稳定的 public result schema，用于未来逐步替代 pipeline-internal result：

```python
@dataclass
class CompileResult:
    spl_text: str
    completeness: Completeness
    diagnostics: list[CompileDiagnostic]
    traces: list[TraceRecord]
    assumptions: list[CompileAssumption]
    adapter_warnings: list[str]
    validation_errors: list[str]
    validation_warnings: list[str]
    readable_report: str
```

### 9.3 CompileAssumption

Assumption 是 report-only，不进入 SPL：

```python
@dataclass
class CompileAssumption:
    assumption_id: str
    target_ref: str
    source_span_ids: list[str]
    text: str
    reason: str
    suggested_resolution: str | None
    related_missing_slot: str | None
    related_diagnostic_id: str | None
```

`AssumptionBuilder` 从 diagnostics 生成 assumptions，并通过 `related_diagnostic_id` 避免 report 重复表达同一问题。

---

## 10. Readable Report

`ReportRenderer` 生成 deterministic plain-text report，不调用 LLM。

固定顺序：

1. Summary
2. Adapter
3. Diagnostics
4. Assumptions
5. Provenance Traces
6. Validation
7. SPL

Report 展示：

- completeness status。
- diagnostic count。
- adapter warning count。
- trace count。
- diagnostics 按 severity/kind/id 排序。
- assumptions 链接相关 diagnostic。
- missing slot 信息。
- trace `needs_confirmation` 标记。
- section/packet provenance。

CLI 会写入两个 report artifact：

```text
<run_dir>/compile_report.txt
<run_dir>/feedback_report.md
```

其中 `compile_report.txt` 是紧凑的编译摘要；`feedback_report.md` 是面向用户和评审的 Markdown 反馈报告，解释哪些 SPL 结构已经 materialize、哪些需求被保留为 partial、哪些命令被 anti-fabrication gate 阻止、diagnostics/assumptions/provenance 如何对应到源文本。

---

## 11. Worker 与 delegation

### 11.1 两条路径

当前 pipeline 支持两种路径：

1. Legacy path:
   - `FlowStructureIR`
   - `BlockStructureIR`
   - flat `StepIR`
   - optional delegation candidates

2. Worker-aware path:
   - Stage 3.5 `WorkerPlanIR`
   - Stage 3.6 validation
   - `WorkerFlowPlanIR`
   - `WorkerBlockPlanIR`
   - `WorkerStepPlanIR`
   - worker-scoped resource extraction
   - worker-scoped normalization

`enable_worker_boundary_planner` 控制是否启用 worker-aware path。

### 11.2 Handoff renderability

`INVOKE_WORKER` 可渲染条件：

- step 有 `handoff_id`。
- handoff 存在于 `WorkerPlanIR.handoffs`。
- `handoff.mode == "invoke"`。
- `handoff.to_worker` 非空且指向声明的 child worker。
- step `integration_ref` 精确匹配目标 worker name。
- input/output bindings 非空且与 step inputs/outputs 精确匹配。

不满足条件时：

- 不渲染 invoke。
- diagnostic 中暴露 ambiguity。
- delegation provenance 仍保留。

---

## 12. 测试与验收状态

### 12.1 MVP 验收场景

已覆盖 6 个核心场景：

1. Failure condition only -> partial exception flow + `missing_handler`。
2. Required output without producer -> no synthetic producer + `missing_output_producer`。
3. Complete failure handling -> handler rendered + complete。
4. Vague policy -> no demand, no structure。
5. Complete single-level delegation -> child worker + executable invoke。
6. Incomplete delegation -> no executable invoke + diagnostic + partial。

### 12.2 MVP+ Structural Provenance

已覆盖：

- required output section provenance。
- failure handling section provenance。
- delegation policy section provenance。
- report 中展示 `section=...` / `packet=...`。

### 12.3 Live E2E

最新 live E2E 报告：

```text
docs/implementation/mvp_live_e2e_check_report.md
```

已通过场景：

- required-output-v2
- failure-handler-v2
- structural-provenance-v2
- freeform-adapter-v2

最新全量测试基线：

```text
835 passed, 4 skipped
```

---

## 13. 当前主要已知风险

### 13.1 Stage 6 schema-looking variable noise

LLM resource extraction 仍可能从 stage context 中抽出类似 schema/internal 的变量名，例如：

- `span_id`
- `source_section_id`
- `main_flow_spans`
- `exception_flows`

Adapter verifier 已经防止这些字段通过 adapter hard facts 进入 canonical contract，但 Stage 6 LLM 输出仍可能产生噪声。当前 normalizer 会剪掉部分 orphan step variables，但后续仍建议做 Stage 6 prompt/schema hardening。

### 13.2 Worker graph 仍是保守 MVP

当前支持 single-level delegation happy path 和 incomplete delegation negative path。复杂 worker graph、candidate-to-handoff linkage、嵌套 child worker 仍未完成。

### 13.3 Report 是文本形态

当前 report 是 deterministic plain-text。未来可增加 HTML/JSON report，但不能替代结构化 diagnostics/traces。

---

## 14. 后续演进建议

建议按以下顺序推进：

1. **Resource extractor hardening**
   - 禁止 schema/internal field 成为 `VariableSpec`。
   - 对 Stage 6 LLM 输出增加 reserved-name filter。

2. **TraceRef schema 下沉**
   - 在主要 IR 上增加 `trace_refs` 或 `origin` 字段。
   - 保持 `TraceRecord` public schema 不变。

3. **Candidate-to-handoff linkage**
   - 在 `WorkerHandoffIR` 中保存 candidate/evidence link。
   - 让 delegation provenance 更精确。

4. **Semantic conflict diagnostics**
   - policy conflict。
   - duplicate behavior。
   - incompatible IO contract。

5. **Interactive clarification**
   - 基于 `MissingSlot` / `CompileAssumption` 生成澄清问题。
   - 不改变 compiler core，只增加交互层。

---

## 15. 结论

当前项目已经从“尽量生成完整 SPL”的传统生成式 pipeline，演进为“需求忠实的渐进式编译 pipeline”：

- 能输出 partial SPL。
- 能明确区分 validation、adapter warning、compile diagnostic。
- 能防止关键 silent fabrication。
- 能追踪主要 SPL 元素 provenance。
- 能通过 readable report 向人解释缺失、歧义、假设和来源。
- 能在 live LLM E2E 中验证 failure/output/delegation/freeform adapter 的核心闭环。

因此 v4 设计文档的当前基线应以 Partial SPL MVP + MVP+ Structural Provenance + LLM Adapter Engine 为准，而不是早期“LLM 生成完整 SPL”的设计假设。
