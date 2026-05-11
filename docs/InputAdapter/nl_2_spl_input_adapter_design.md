# NL2SPL InputAdapter 详细设计文档

## 1. 背景

当前 NL2SPL 项目的目标是将自然语言描述转换为符合 SPL（Structured Prompt Language）语法的结构化提示词。现有 compile pipeline 的核心设计是：不假设输入文本具有固定结构，而是通过语义分析将自然语言逐步转换为 IR，再由代码完成 SPL 组装和校验。

但在实际输入中，很多自然语言并非完全自由文本，而是具有稳定结构。例如：

```text
Task family:
Inputs for each run:
Required outputs:
Reusable process:
Policies:
Failure handling:
Delegation policy:
```

这类输入中的 section 标题本身携带明确语义。如果仍然完全按无结构自然语言处理，会浪费输入结构信息，并且容易在早期 FieldRoute 阶段出现错误路由，例如将 `Required outputs` 当成普通行为描述，将 `Failure handling` 当成 persona 片段，或者将 `Delegation policy` 简化为普通约束文本。

因此需要引入一个独立的 `InputAdapter` 层，用于在不推翻现有 compile pipeline 的前提下，充分利用已知输入结构，将不同格式的输入统一转换为一个标准的 `CanonicalCompileInput`。

---

## 2. 设计目标

### 2.1 核心目标

InputAdapter 的目标是：

> 面向不同输入结构的独立归一化层；它检测 structural_nl 等已知输入格式，并将其转换为统一的 CanonicalCompileInput，其中包含 raw sections、semantic packets、hard facts 和 compile hints；compile pipeline 只消费 CanonicalCompileInput，不感知具体输入结构。

### 2.2 具体目标

1. **保持现有 compile pipeline 不被推翻**  
   Adapter 是 pipeline 前置层，不替代 Stage 1-11，也不改变原有 IR 设计。

2. **统一所有 adapter 的输出格式**  
   不同输入结构可以有不同 adapter，但所有 adapter 必须输出同一种 `CanonicalCompileInput`。

3. **充分利用已知输入结构语义**  
   对 `Inputs for each run`、`Required outputs`、`Failure handling` 等结构明确的 section，应提前抽取 hard facts，而不是让后续 LLM 从自由文本中猜。

4. **区分 hard facts 和 compile hints**  
   Adapter 能确定的事实应作为 hard facts；需要后续语义判断的内容只能作为 compile hints。

5. **保留来源追踪**  
   Adapter 输出的每个 section、packet、hard fact、hint 都应保留来源 section 信息，便于后续调试、覆盖率校验和错误定位。

6. **不使用伪置信度**  
   `detect()` 不返回 `confidence`。结构匹配应由 matched sections、missing sections、duplicate sections、unexpected sections 和 parse errors 表达。

---

## 3. 非目标

InputAdapter 不负责以下事情：

1. **不直接生成 SPL**  
   SPL 仍然由原有 compiler 和 renderer 生成。

2. **不直接生成最终 WorkerIR / StepIR / ConstraintIR**  
   Adapter 可以提供 seeds 和 hints，但最终 IR 仍由现有 pipeline 生成。

3. **不替代 FieldRouter / FlowAssembler / StepExtractor**  
   Adapter 只提供更高质量的输入，不承担最终语义裁决。

4. **不做完整 semantic coverage validation**  
   覆盖率验证属于独立 validator 层。Adapter 只提供可验证的 provenance 和 hard facts。

5. **不绑定具体业务领域**  
   `structural_nl` 是输入结构类型，不是 internal communications 业务类型。业务语义应放入 section 内容、semantic packets 或 compile hints。

---

## 4. 总体架构

### 4.1 新增位置

```text
Raw NL
  ↓
InputAdapterRegistry
  ↓
Selected InputAdapter
  ↓
CanonicalCompileInput
  ↓
Existing Compile Pipeline
  ↓
SPL Output
```

### 4.2 与现有 pipeline 的关系

InputAdapter 独立于现有 pipeline，原有 Stage 仍保持职责稳定：

```text
Stage 1  SpanSlicer
Stage 2  FieldRouter
Stage 3  AmbiguityResolver
Stage 4  FlowAssembler
Stage 5  BlockAssembler
Stage 6  ResourceExtractor
Stage 7  StepExtractor
Stage 8  ProfileExtractor
Stage 9  ConstraintExtractor
Stage 10 WorkerAssembler
Stage 11 SPLRenderer
```

Adapter 不改写这些 Stage，而是通过 `CanonicalCompileInput` 给它们提供：

- 原始 section 信息；
- 语义 packet；
- 输入、输出、failure mode 等 hard facts；
- flow、block、step、constraint、delegation 等 compile hints。

### 4.3 编译入口

编译器入口不应暴露具体 adapter 类型。

推荐：

```python
canonical_input = adapter_registry.adapt(raw_text)
compile_result = compile_pipeline.compile(canonical_input)
```

不推荐：

```python
compile_pipeline.compile_structural_nl(raw_text)
compile_pipeline.compile_skill_doc(raw_text)
compile_pipeline.compile_freeform_nl(raw_text)
```

原因是后者会让 compile pipeline 感知输入结构，导致 adapter 和 compiler 耦合。

---

## 5. 核心概念

## 5.1 InputAdapter

InputAdapter 是所有输入适配器的统一接口。

```python
class InputAdapter:
    name: str

    def detect(self, raw_text: str) -> AdapterDetectionResult:
        ...

    def adapt(self, raw_text: str) -> CanonicalCompileInput:
        ...
```

职责：

- 判断 raw text 是否符合某种已知输入结构；
- 解析结构；
- 标准化 section；
- 生成 semantic packets；
- 抽取 hard facts；
- 生成 compile hints；
- 输出 CanonicalCompileInput。

---

## 5.2 AdapterDetectionResult

`detect()` 的返回值，用于描述结构匹配结果。

不包含 `confidence`。

```json
{
  "matched": true,
  "schema_name": "structural_nl",
  "schema_version": "1.0",
  "matched_sections": [
    "task_family",
    "inputs_for_each_run",
    "required_outputs",
    "reusable_process",
    "policies",
    "failure_handling",
    "delegation_policy"
  ],
  "missing_sections": [],
  "unexpected_sections": [],
  "duplicate_sections": [],
  "empty_sections": [],
  "parse_errors": []
}
```

字段说明：

| 字段 | 类型 | 说明 |
|---|---|---|
| `matched` | boolean | 是否匹配该 adapter |
| `schema_name` | string | 输入结构名称，例如 `structural_nl` |
| `schema_version` | string | schema 版本 |
| `matched_sections` | string[] | 命中的标准 section 名称 |
| `missing_sections` | string[] | 期望但缺失的 section |
| `unexpected_sections` | string[] | 无法识别的 section |
| `duplicate_sections` | string[] | 重复出现的 section |
| `empty_sections` | string[] | 标题存在但正文为空的 section |
| `parse_errors` | object[] | 解析错误 |

### matched 判断规则

对于 `structural_nl`，建议使用确定性规则：

```text
matched = 至少命中 3 个 structural_nl 标准 section
```

或者更严格：

```text
matched = 在 task_family、inputs_for_each_run、required_outputs 中至少命中 2 个
```

最终阈值可根据测试集调整，但不使用置信度小数。

---

## 5.3 CanonicalCompileInput

所有 adapter 的统一输出。

```json
{
  "source_schema": "structural_nl",
  "schema_version": "1.0",
  "raw_text": "...",
  "raw_sections": [],
  "semantic_packets": [],
  "hard_facts": {},
  "compile_hints": {},
  "warnings": []
}
```

字段说明：

| 字段 | 类型 | 说明 |
|---|---|---|
| `source_schema` | string | 输入结构名称 |
| `schema_version` | string | schema 版本 |
| `raw_text` | string | 原始输入文本 |
| `raw_sections` | RawSection[] | 标准化后的 section 列表 |
| `semantic_packets` | SemanticPacket[] | 从 section 中拆出的语义单元 |
| `hard_facts` | HardFacts | adapter 可确定的编译事实 |
| `compile_hints` | CompileHints | 给后续 pipeline 的软提示 |
| `warnings` | AdapterWarning[] | 适配过程中的警告 |

---

## 5.4 RawSection

保留输入结构和来源信息。

```json
{
  "section_id": "sec_inputs",
  "canonical_title": "inputs_for_each_run",
  "original_title": "Inputs for each run",
  "text": "A user request, optional known topics, optional timeframe...",
  "order": 2,
  "start_offset": 124,
  "end_offset": 268
}
```

字段说明：

| 字段 | 类型 | 说明 |
|---|---|---|
| `section_id` | string | section 唯一 ID |
| `canonical_title` | string | 标准化 section 名称 |
| `original_title` | string | 原始标题 |
| `text` | string | section 正文 |
| `order` | number | section 在原文中的顺序 |
| `start_offset` | number | 原文起始位置，可选 |
| `end_offset` | number | 原文结束位置，可选 |

---

## 5.5 SemanticPacket

SemanticPacket 是 adapter 输出给 pipeline 的基本语义单元。它比普通 span 更强，因为它保留了 section provenance 和结构语义。

```json
{
  "packet_id": "p_input_user_request",
  "source_section_id": "sec_inputs",
  "packet_type": "runtime_input",
  "text": "A user request",
  "modality": "hard_fact",
  "compile_targets": ["resource.variable", "worker.input"],
  "suggested_name": "user_request",
  "required": true
}
```

字段说明：

| 字段 | 类型 | 说明 |
|---|---|---|
| `packet_id` | string | packet 唯一 ID |
| `source_section_id` | string | 来源 section |
| `packet_type` | string | 语义类型 |
| `text` | string | 原始语义文本 |
| `modality` | `hard_fact` / `hint` | 是硬事实还是软提示 |
| `compile_targets` | string[] | 建议影响的编译目标 |
| `suggested_name` | string | 建议变量名、worker 名、constraint 名等 |
| `required` | boolean | 是否必需，可选 |
| `metadata` | object | 其他补充信息 |

### packet_type 枚举建议

```text
runtime_input
required_output
task_family
process_step
policy
failure_mode
delegation_rule
domain_term
audience_hint
format_hint
integration_hint
```

### compile_targets 枚举建议

```text
profile.persona
profile.audience
profile.concepts
resource.variable
resource.api
worker.input
worker.output
flow.main
flow.alternative
flow.exception
block.sequential
block.if
block.for
block.while
step.command
step.input
step.call_api
step.invoke_worker
constraint.requirement
constraint.prohibition
constraint.evidence
constraint.gate
constraint.delegation_boundary
validator.required_output_reachability
```

注意：`compile_targets` 是提示，不是最终 IR。

---

## 5.6 HardFacts

HardFacts 表示 adapter 可以从结构中确定的事实。后续 pipeline 原则上不应推翻，只能补充、规范化或报告冲突。

```json
{
  "inputs": [],
  "outputs": [],
  "failure_modes": [],
  "required_sections": [],
  "source_constraints": []
}
```

### 5.6.1 InputFact

```json
{
  "name": "user_request",
  "description": "A user request",
  "data_type": "text",
  "required": true,
  "source_section_id": "sec_inputs"
}
```

### 5.6.2 OutputFact

```json
{
  "name": "draft_communication_artifact",
  "description": "A draft communication artifact",
  "data_type": "text",
  "required": true,
  "source_section_id": "sec_required_outputs"
}
```

### 5.6.3 FailureModeFact

```json
{
  "name": "evidence_shortage",
  "text": "Evidence shortage",
  "source_section_id": "sec_failure_handling"
}
```

---

## 5.7 CompileHints

CompileHints 是给后续 pipeline 的软提示。它不替代 LLM/代码的最终判断。

```json
{
  "profile_hints": [],
  "process_hints": [],
  "constraint_hints": [],
  "flow_hints": [],
  "resource_hints": [],
  "delegation_hints": []
}
```

### 5.7.1 ProfileHint

```json
{
  "source_section_id": "sec_task_family",
  "target": "persona.role",
  "text": "Internal communications specialist"
}
```

### 5.7.2 ProcessHint

```json
{
  "source_section_id": "sec_reusable_process",
  "text": "If sources are needed and available, retrieve them using approved source recipes.",
  "suggested_flow": "main",
  "suggested_block_type": "IF",
  "suggested_step_type": "INVOKE_WORKER_OR_CALL_API"
}
```

### 5.7.3 ConstraintHint

```json
{
  "source_section_id": "sec_policies",
  "text": "Do not invent links or unseen facts.",
  "suggested_kind": "prohibition"
}
```

### 5.7.4 DelegationHint

```json
{
  "source_section_id": "sec_delegation_policy",
  "text": "Source gathering may be delegated if bounded.",
  "suggested_type": "child_worker",
  "suggested_worker_name": "SourceGatheringWorker"
}
```

---

## 6. structural_nl Adapter 设计

## 6.1 schema 命名

机器字段：

```json
{
  "schema_name": "structural_nl",
  "schema_version": "1.0"
}
```

展示名称：

```text
Structural NL
```

`structural_nl` 表示“具有稳定标题分段结构的自然语言规范”，不表示某个具体业务领域。

---

## 6.2 标准 section

第一版支持以下 section：

| 原始标题 | canonical_title | 语义 |
|---|---|---|
| Task family | `task_family` | 任务族、agent/worker 描述、可能的 persona/domain hint |
| Inputs for each run | `inputs_for_each_run` | 运行时输入 |
| Required outputs | `required_outputs` | 必须输出 |
| Reusable process | `reusable_process` | 可复用处理流程 |
| Policies | `policies` | 规则、限制、门控、证据要求 |
| Failure handling | `failure_handling` | 异常和失败场景 |
| Delegation policy | `delegation_policy` | 委托规则、边界、候选子任务 |

---

## 6.3 heading normalize 规则

```python
def normalize_heading(line: str) -> str:
    line = line.strip()
    line = line.rstrip(":：")
    line = line.lower()
    line = " ".join(line.split())
    return line
```

映射表：

```python
STRUCTURAL_NL_SECTIONS = {
    "task family": "task_family",
    "inputs for each run": "inputs_for_each_run",
    "required outputs": "required_outputs",
    "reusable process": "reusable_process",
    "policies": "policies",
    "failure handling": "failure_handling",
    "delegation policy": "delegation_policy",
}
```

---

## 6.4 section 解析规则

1. 按行扫描输入文本；
2. 对每一行执行 heading normalize；
3. 如果 normalize 后命中 section 映射表，则认为该行是 section heading；
4. 当前 heading 到下一个 heading 之间的内容作为该 section 正文；
5. 保留 section 的原始标题、标准标题、正文、顺序和 offset；
6. 检查重复 section、空 section、未知 section。

---

## 6.5 semantic packet 生成规则

### 6.5.1 Task family

输入：

```text
Internal newsletters, announcements, update digests, executive briefs, and related internal-comms artifacts.
```

生成：

```json
[
  {
    "packet_type": "task_family",
    "modality": "hint",
    "compile_targets": ["profile.persona", "worker.description", "profile.concepts"],
    "text": "Internal newsletters, announcements, update digests, executive briefs, and related internal-comms artifacts."
  }
]
```

说明：

- 不直接硬编码 persona；
- 只给 ProfileExtractor 和 WorkerAssembler 提供提示；
- 可作为 worker description 的强候选。

---

### 6.5.2 Inputs for each run

输入：

```text
A user request, optional known topics, optional timeframe, available connectors or source repositories, and optional format preferences.
```

生成 hard facts：

```json
{
  "inputs": [
    {
      "name": "user_request",
      "description": "A user request",
      "data_type": "text",
      "required": true,
      "source_section_id": "sec_inputs"
    },
    {
      "name": "known_topics",
      "description": "Optional known topics",
      "data_type": "List [text]",
      "required": false,
      "source_section_id": "sec_inputs"
    },
    {
      "name": "timeframe",
      "description": "Optional timeframe",
      "data_type": "text",
      "required": false,
      "source_section_id": "sec_inputs"
    },
    {
      "name": "connectors_or_source_repositories",
      "description": "Available connectors or source repositories",
      "data_type": "List [text]",
      "required": false,
      "source_section_id": "sec_inputs"
    },
    {
      "name": "format_preferences",
      "description": "Optional format preferences",
      "data_type": "text",
      "required": false,
      "source_section_id": "sec_inputs"
    }
  ]
}
```

生成 semantic packets：

```json
[
  {
    "packet_type": "runtime_input",
    "modality": "hard_fact",
    "compile_targets": ["resource.variable", "worker.input"],
    "suggested_name": "user_request",
    "required": true,
    "text": "A user request"
  }
]
```

说明：

- 该 section 的核心产物是 `hard_facts.inputs`；
- 后续 ResourceExtractor 应直接 seed 这些变量；
- FieldRouter 不应再把它们当成普通 behavior span 处理。

---

### 6.5.3 Required outputs

输入：

```text
A draft communication artifact, a source/evidence set, a short assumptions log for any unresolved items, and a completion status.
```

生成 hard facts：

```json
{
  "outputs": [
    {
      "name": "draft_communication_artifact",
      "description": "A draft communication artifact",
      "data_type": "text",
      "required": true,
      "source_section_id": "sec_required_outputs"
    },
    {
      "name": "source_evidence_set",
      "description": "A source/evidence set",
      "data_type": "text",
      "required": true,
      "source_section_id": "sec_required_outputs"
    },
    {
      "name": "assumptions_log",
      "description": "A short assumptions log for unresolved items",
      "data_type": "text",
      "required": true,
      "source_section_id": "sec_required_outputs"
    },
    {
      "name": "completion_status",
      "description": "A completion status",
      "data_type": "text",
      "required": true,
      "source_section_id": "sec_required_outputs"
    }
  ]
}
```

说明：

- 这些 output facts 必须 seed 到 ResourceRegistryIR；
- WorkerAssembler 必须将它们绑定到 Worker outputs；
- Validator 应检查 required outputs 是否有 producer step。

---

### 6.5.4 Reusable process

输入示例：

```text
First determine what kind of communication is requested. Then identify which required fields are still missing. Ask only the highest-value clarifying questions needed to move forward. If sources are needed and available, retrieve them using approved source recipes. Maintain provenance for externally sourced facts. When enough required information is available, produce a draft. If the user asks for revision, revise while rechecking constraints. Do not finalize if required slots remain missing unless the draft is explicitly marked as assumption-bearing and the user confirms.
```

生成 compile hints：

```json
{
  "process_hints": [
    {
      "text": "First determine what kind of communication is requested.",
      "suggested_flow": "main",
      "suggested_block_type": "SEQUENTIAL",
      "suggested_step_type": "GENERAL_COMMAND"
    },
    {
      "text": "If sources are needed and available, retrieve them using approved source recipes.",
      "suggested_flow": "main",
      "suggested_block_type": "IF",
      "suggested_step_type": "INVOKE_WORKER_OR_CALL_API"
    },
    {
      "text": "If the user asks for revision, revise while rechecking constraints.",
      "suggested_flow": "alternative",
      "suggested_condition": "the user asks for revision"
    },
    {
      "text": "Do not finalize if required slots remain missing unless the draft is explicitly marked as assumption-bearing and the user confirms.",
      "suggested_flow": "main",
      "suggested_block_type": "IF",
      "suggested_constraint_kind": "gate"
    }
  ]
}
```

说明：

- Reusable process 不生成 hard facts，除非其中出现明确输入/输出声明；
- 它主要提供 flow/block/step/constraint hints；
- 最终是否映射为 IF_BLOCK、ALTERNATIVE_FLOW、EXCEPTION_FLOW 仍由后续 pipeline 决定。

---

### 6.5.5 Policies

输入：

```text
Do not invent links or unseen facts. Require evidence for sourced claims. Limit questions per turn. Prefer tool evidence over unnecessary user questioning. Deny finalization if critical slots are missing or provenance fails.
```

生成 compile hints：

```json
{
  "constraint_hints": [
    {
      "text": "Do not invent links or unseen facts.",
      "suggested_kind": "prohibition"
    },
    {
      "text": "Require evidence for sourced claims.",
      "suggested_kind": "evidence"
    },
    {
      "text": "Limit questions per turn.",
      "suggested_kind": "requirement"
    },
    {
      "text": "Prefer tool evidence over unnecessary user questioning.",
      "suggested_kind": "requirement"
    },
    {
      "text": "Deny finalization if critical slots are missing or provenance fails.",
      "suggested_kind": "gate"
    }
  ]
}
```

说明：

- Policies 主要进入 ConstraintExtractor；
- gate 类 policy 需要同时提示 FlowAssembler/BlockAssembler，因为它可能需要流程级控制；
- Adapter 不直接决定 targets。

---

### 6.5.6 Failure handling

输入：

```text
Missing timeframe, conflicting instructions, insufficient source access, evidence shortage, user refusal to answer, and provenance failure.
```

生成 hard facts：

```json
{
  "failure_modes": [
    {
      "name": "missing_timeframe",
      "text": "Missing timeframe",
      "source_section_id": "sec_failure_handling"
    },
    {
      "name": "conflicting_instructions",
      "text": "Conflicting instructions",
      "source_section_id": "sec_failure_handling"
    },
    {
      "name": "insufficient_source_access",
      "text": "Insufficient source access",
      "source_section_id": "sec_failure_handling"
    },
    {
      "name": "evidence_shortage",
      "text": "Evidence shortage",
      "source_section_id": "sec_failure_handling"
    },
    {
      "name": "user_refusal_to_answer",
      "text": "User refusal to answer",
      "source_section_id": "sec_failure_handling"
    },
    {
      "name": "provenance_failure",
      "text": "Provenance failure",
      "source_section_id": "sec_failure_handling"
    }
  ]
}
```

生成 flow hints：

```json
{
  "flow_hints": [
    {
      "text": "Missing timeframe",
      "suggested_flow": "exception",
      "suggested_condition": "missing timeframe"
    }
  ]
}
```

说明：

- failure modes 是 hard facts；
- 但每个 failure mode 是否生成独立 EXCEPTION_FLOW，还是在一个 exception flow 中分支，由后续 FlowAssembler 决定；
- Validator 可检查每个 failure mode 是否被 exception flow 或 equivalent handling 覆盖。

---

### 6.5.7 Delegation policy

输入：

```text
Optional delegated subtasks such as source gathering or template matching may be used if bounded and the returned evidence is normalized into approved evidence carriers.
```

生成 delegation hints：

```json
{
  "delegation_hints": [
    {
      "text": "Source gathering may be delegated if bounded.",
      "suggested_type": "child_worker",
      "suggested_worker_name": "SourceGatheringWorker"
    },
    {
      "text": "Template matching may be delegated if bounded.",
      "suggested_type": "child_worker",
      "suggested_worker_name": "TemplateMatchingWorker"
    }
  ],
  "constraint_hints": [
    {
      "text": "Delegated subtasks must be bounded.",
      "suggested_kind": "delegation_boundary"
    },
    {
      "text": "Returned evidence must be normalized into approved evidence carriers.",
      "suggested_kind": "delegation_boundary"
    }
  ]
}
```

说明：

- 委托候选是 hint，不是 hard fact；
- 委托边界可以作为强约束 hint；
- 是否生成 child worker 由 FlowAssembler / WorkerAssembler 决定。

---

## 7. 与现有 pipeline 的接入设计

## 7.1 CompilePipeline 输入改造

当前 compile pipeline 若直接接收 raw text，可改为接收 `CanonicalCompileInput`：

```python
class CompilePipeline:
    def compile(self, canonical_input: CanonicalCompileInput) -> CompileResult:
        ...
```

为了兼容旧接口，可以提供 façade：

```python
class NL2SPLCompiler:
    def compile_raw(self, raw_text: str) -> CompileResult:
        canonical_input = self.adapter_registry.adapt(raw_text)
        return self.pipeline.compile(canonical_input)
```

---

## 7.2 Stage 1：SpanSlicer 的适配方式

原职责：从 raw text 生成 `List[SpanIR]`。

新增输入：`canonical_input.raw_sections` 和 `semantic_packets`。

建议行为：

1. 对于 `semantic_packets`，优先生成 packet-aware spans；
2. 每个 span 保留 `source_section_id` 和 `packet_id`；
3. 对于没有被 adapter 结构化的文本，仍按原逻辑切片；
4. 不直接使用 section 标题作为语义内容，除非标题本身提供必要语义。

扩展 SpanIR：

```json
{
  "span_id": "s1",
  "text": "A user request",
  "source_section_id": "sec_inputs",
  "source_packet_id": "p_input_user_request",
  "ambiguity": {
    "is_ambiguous": false,
    "reasons": [],
    "needs_split": false
  }
}
```

---

## 7.3 Stage 2：FieldRouter 的适配方式

原职责：将 span 路由到 6 个语义字段。

新增上下文：`semantic_packets.compile_targets` 和 `compile_hints`。

建议行为：

1. 对 hard fact packet，不再强行路由到 6 个字段；
2. runtime input / required output 优先进入 ResourceExtractor seed；
3. policy packet 可提示 rules；
4. process packet 可提示 behavior；
5. delegation packet 可同时提示 behavior、rules、integrations 的 derived extraction；
6. integrations 不再作为纯互斥路由字段，而是允许由后续 ResourceExtractor 从 process/delegation hints 中派生。

---

## 7.4 Stage 4：FlowAssembler 的适配方式

新增上下文：

- `compile_hints.flow_hints`
- `hard_facts.failure_modes`
- `compile_hints.process_hints`
- `compile_hints.delegation_hints`

建议行为：

1. 对 `suggested_flow = main` 的 process hint，优先放入 main flow；
2. 对 `suggested_flow = alternative` 的 hint，优先生成 alternative flow candidate；
3. 对 failure modes，优先生成 exception flow candidate；
4. 对 delegation hints，生成 delegation_candidates；
5. 最终 flow 结构仍由 FlowAssembler 判断，不由 Adapter 直接决定。

---

## 7.5 Stage 6：ResourceExtractor 的适配方式

新增输入：`hard_facts.inputs`、`hard_facts.outputs`、`compile_hints.resource_hints`。

建议行为：

1. 将 `hard_facts.inputs` 直接 seed 为 input variables；
2. 将 `hard_facts.outputs` 直接 seed 为 output variables；
3. 使用 suggested names 作为变量名，但需要做命名规范化和冲突处理；
4. 对 connectors/source repositories 可生成 integration/resource hint；
5. 初始化 SymbolTable 时直接声明 hard fact variables；
6. 后续 StepExtractor 只能引用或补充这些变量，不应重复创建。

---

## 7.6 Stage 9：ConstraintExtractor 的适配方式

新增输入：`compile_hints.constraint_hints`。

建议行为：

1. constraint hint 的 `suggested_kind` 作为默认 kind；
2. targets 仍由 ConstraintExtractor 根据 flow/block/step/symbol table 判断；
3. gate 类 constraint 必须尝试绑定到 flow/block/step 或 variable；
4. delegation boundary 类 constraint 可绑定到 child worker、delegation candidate 或 global。

---

## 7.7 Validator 的适配方式

Adapter 不实现完整 validator，但为 validator 提供基础数据：

1. `hard_facts.outputs` → required output reachability check；
2. `hard_facts.failure_modes` → failure coverage check；
3. `constraint_hints` → policy coverage check；
4. `semantic_packets` → packet-level coverage check，可后续增强。

---

## 8. 数据模型建议

以下为 Python dataclass / Pydantic 风格定义。

```python
from dataclasses import dataclass, field
from typing import Any, Literal

@dataclass
class AdapterDetectionResult:
    matched: bool
    schema_name: str
    schema_version: str
    matched_sections: list[str] = field(default_factory=list)
    missing_sections: list[str] = field(default_factory=list)
    unexpected_sections: list[str] = field(default_factory=list)
    duplicate_sections: list[str] = field(default_factory=list)
    empty_sections: list[str] = field(default_factory=list)
    parse_errors: list[dict[str, Any]] = field(default_factory=list)

@dataclass
class RawSection:
    section_id: str
    canonical_title: str
    original_title: str
    text: str
    order: int
    start_offset: int | None = None
    end_offset: int | None = None

@dataclass
class SemanticPacket:
    packet_id: str
    source_section_id: str
    packet_type: str
    text: str
    modality: Literal["hard_fact", "hint"]
    compile_targets: list[str] = field(default_factory=list)
    suggested_name: str | None = None
    required: bool | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass
class VariableFact:
    name: str
    description: str
    data_type: str
    required: bool
    source_section_id: str

@dataclass
class FailureModeFact:
    name: str
    text: str
    source_section_id: str

@dataclass
class HardFacts:
    inputs: list[VariableFact] = field(default_factory=list)
    outputs: list[VariableFact] = field(default_factory=list)
    failure_modes: list[FailureModeFact] = field(default_factory=list)

@dataclass
class CompileHint:
    source_section_id: str
    text: str
    target: str | None = None
    suggested_kind: str | None = None
    suggested_flow: str | None = None
    suggested_block_type: str | None = None
    suggested_step_type: str | None = None
    suggested_condition: str | None = None
    suggested_type: str | None = None
    suggested_worker_name: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass
class CompileHints:
    profile_hints: list[CompileHint] = field(default_factory=list)
    process_hints: list[CompileHint] = field(default_factory=list)
    constraint_hints: list[CompileHint] = field(default_factory=list)
    flow_hints: list[CompileHint] = field(default_factory=list)
    resource_hints: list[CompileHint] = field(default_factory=list)
    delegation_hints: list[CompileHint] = field(default_factory=list)

@dataclass
class AdapterWarning:
    code: str
    message: str
    source_section_id: str | None = None
    severity: Literal["info", "warning", "error"] = "warning"

@dataclass
class CanonicalCompileInput:
    source_schema: str
    schema_version: str
    raw_text: str
    raw_sections: list[RawSection] = field(default_factory=list)
    semantic_packets: list[SemanticPacket] = field(default_factory=list)
    hard_facts: HardFacts = field(default_factory=HardFacts)
    compile_hints: CompileHints = field(default_factory=CompileHints)
    warnings: list[AdapterWarning] = field(default_factory=list)
```

---

## 9. AdapterRegistry 设计

用于管理多个 adapter。

```python
class InputAdapterRegistry:
    def __init__(self, adapters: list[InputAdapter]):
        self.adapters = adapters

    def detect_all(self, raw_text: str) -> list[AdapterDetectionResult]:
        return [adapter.detect(raw_text) for adapter in self.adapters]

    def select_adapter(self, raw_text: str) -> InputAdapter:
        results = []
        for adapter in self.adapters:
            result = adapter.detect(raw_text)
            if result.matched:
                results.append((adapter, result))

        if not results:
            return GenericNLAdapter()

        return self._select_by_priority(results)

    def adapt(self, raw_text: str) -> CanonicalCompileInput:
        adapter = self.select_adapter(raw_text)
        return adapter.adapt(raw_text)
```

### 9.1 adapter 优先级

建议优先级：

```text
1. 显式 schema 标记的 adapter
2. 高特异性结构 adapter
3. structural_nl adapter
4. generic_nl adapter
```

例如：

```text
skill_md_adapter > structural_nl_adapter > generic_nl_adapter
```

---

## 10. structural_nl 端到端示例

## 10.1 输入

```text
Task family:
Internal newsletters, announcements, update digests, executive briefs, and related internal-comms artifacts.

Inputs for each run:
A user request, optional known topics, optional timeframe, available connectors or source repositories, and optional format preferences.

Required outputs:
A draft communication artifact, a source/evidence set, a short assumptions log for any unresolved items, and a completion status.

Reusable process:
First determine what kind of communication is requested. Then identify which required fields are still missing. Ask only the highest-value clarifying questions needed to move forward. If sources are needed and available, retrieve them using approved source recipes. Maintain provenance for externally sourced facts. When enough required information is available, produce a draft. If the user asks for revision, revise while rechecking constraints. Do not finalize if required slots remain missing unless the draft is explicitly marked as assumption-bearing and the user confirms.

Policies:
Do not invent links or unseen facts. Require evidence for sourced claims. Limit questions per turn. Prefer tool evidence over unnecessary user questioning. Deny finalization if critical slots are missing or provenance fails.

Failure handling:
Missing timeframe, conflicting instructions, insufficient source access, evidence shortage, user refusal to answer, and provenance failure.

Delegation policy:
Optional delegated subtasks such as source gathering or template matching may be used if bounded and the returned evidence is normalized into approved evidence carriers.
```

## 10.2 detect 输出

```json
{
  "matched": true,
  "schema_name": "structural_nl",
  "schema_version": "1.0",
  "matched_sections": [
    "task_family",
    "inputs_for_each_run",
    "required_outputs",
    "reusable_process",
    "policies",
    "failure_handling",
    "delegation_policy"
  ],
  "missing_sections": [],
  "unexpected_sections": [],
  "duplicate_sections": [],
  "empty_sections": [],
  "parse_errors": []
}
```

## 10.3 adapt 输出摘要

```json
{
  "source_schema": "structural_nl",
  "schema_version": "1.0",
  "hard_facts": {
    "inputs": [
      {"name": "user_request", "data_type": "text", "required": true},
      {"name": "known_topics", "data_type": "List [text]", "required": false},
      {"name": "timeframe", "data_type": "text", "required": false},
      {"name": "connectors_or_source_repositories", "data_type": "List [text]", "required": false},
      {"name": "format_preferences", "data_type": "text", "required": false}
    ],
    "outputs": [
      {"name": "draft_communication_artifact", "data_type": "text", "required": true},
      {"name": "source_evidence_set", "data_type": "text", "required": true},
      {"name": "assumptions_log", "data_type": "text", "required": true},
      {"name": "completion_status", "data_type": "text", "required": true}
    ],
    "failure_modes": [
      {"name": "missing_timeframe", "text": "Missing timeframe"},
      {"name": "conflicting_instructions", "text": "Conflicting instructions"},
      {"name": "insufficient_source_access", "text": "Insufficient source access"},
      {"name": "evidence_shortage", "text": "Evidence shortage"},
      {"name": "user_refusal_to_answer", "text": "User refusal to answer"},
      {"name": "provenance_failure", "text": "Provenance failure"}
    ]
  },
  "compile_hints": {
    "profile_hints": [],
    "process_hints": [],
    "constraint_hints": [],
    "flow_hints": [],
    "delegation_hints": []
  }
}
```

---

## 11. 命名规范

## 11.1 section_id

格式：

```text
sec_{canonical_title}
```

示例：

```text
sec_task_family
sec_inputs
sec_required_outputs
sec_reusable_process
sec_policies
sec_failure_handling
sec_delegation_policy
```

对于重复 section：

```text
sec_policies_1
sec_policies_2
```

---

## 11.2 packet_id

格式：

```text
p_{packet_type}_{short_name}
```

示例：

```text
p_input_user_request
p_output_draft_communication_artifact
p_policy_do_not_invent_facts
p_failure_evidence_shortage
```

---

## 11.3 变量名生成

规则：

1. 英文转小写；
2. 非字母数字替换为下划线；
3. 去掉冠词和弱词，例如 `a`, `the`, `for each run`；
4. 规范化常见短语；
5. 冲突时追加后缀。

短语映射示例：

```python
VARIABLE_NAME_ALIASES = {
    "a user request": "user_request",
    "optional known topics": "known_topics",
    "optional timeframe": "timeframe",
    "available connectors or source repositories": "connectors_or_source_repositories",
    "optional format preferences": "format_preferences",
    "a draft communication artifact": "draft_communication_artifact",
    "a source/evidence set": "source_evidence_set",
    "a short assumptions log for any unresolved items": "assumptions_log",
    "a completion status": "completion_status",
}
```

---

## 11.4 数据类型推断规则

第一版使用简单规则即可：

| 文本模式 | data_type |
|---|---|
| `topics`, `connectors`, `repositories`, `items`, `sources` | `List [text]` |
| `status`, 且不是明显 boolean | `text` |
| `whether ...` | `boolean` |
| 默认 | `text` |

注意：Required outputs 中的 `completion status` 建议使用 `text`，而不是 `boolean`，因为状态可能是 `completed`、`blocked`、`assumption-bearing completed` 等多值状态。

---

## 12. 错误与警告设计

## 12.1 缺失 section

```json
{
  "code": "MISSING_SECTION",
  "message": "Expected structural_nl section 'required_outputs' is missing.",
  "severity": "warning"
}
```

处理策略：

- 不阻塞 adapter；
- 在 `missing_sections` 中记录；
- 交给后续 pipeline 尽量继续；
- Validator 可根据缺失类型决定是否失败。

---

## 12.2 空 section

```json
{
  "code": "EMPTY_SECTION",
  "message": "Section 'Policies' is present but empty.",
  "source_section_id": "sec_policies",
  "severity": "warning"
}
```

---

## 12.3 重复 section

```json
{
  "code": "DUPLICATE_SECTION",
  "message": "Section 'Policies' appears multiple times.",
  "severity": "warning"
}
```

处理策略：

- 保留所有重复 section；
- section_id 加序号；
- canonical_title 相同；
- 后续 semantic packet 保留来源。

---

## 12.4 无法解析列表项

```json
{
  "code": "UNPARSEABLE_LIST_ITEM",
  "message": "Could not confidently split the inputs section into variable candidates.",
  "source_section_id": "sec_inputs",
  "severity": "warning"
}
```

注意：这里仍不返回 confidence，只说明解析失败或部分失败。

---

## 13. 测试策略

## 13.1 单元测试

### detect 测试

覆盖：

1. 完整 structural_nl 输入；
2. 缺少部分 section；
3. section 顺序打乱；
4. section 标题大小写变化；
5. 冒号为中文冒号；
6. 重复 section；
7. 空 section；
8. 非 structural_nl 文本。

### parse section 测试

验证：

1. section 数量正确；
2. order 正确；
3. original_title 保留；
4. canonical_title 正确；
5. text 不包含 heading；
6. offset 正确或为空。

### hard facts 测试

验证：

1. inputs 数量正确；
2. outputs 数量正确；
3. required 标记正确；
4. variable name 正确；
5. data_type 合理；
6. source_section_id 正确。

### compile hints 测试

验证：

1. policies 生成 constraint hints；
2. failure handling 生成 failure modes 和 flow hints；
3. delegation policy 生成 delegation hints 和 constraint hints；
4. reusable process 生成 process hints。

---

## 13.2 集成测试

输入：structural_nl 文本。  
期望：

1. adapter 输出 CanonicalCompileInput；
2. ResourceExtractor seed inputs/outputs；
3. WorkerIR 包含 required inputs/outputs；
4. Failure modes 被 FlowAssembler 看见；
5. Delegation hints 被 FlowAssembler 看见；
6. SPLRenderer 输出语法合法 SPL；
7. Validator 不再出现 required output 完全不可见的问题。

---

## 13.3 回归测试

使用当前失败样例作为固定回归用例。

最低验收标准：

1. `user_request` 必须进入 Worker inputs；
2. `draft_communication_artifact`、`source_evidence_set`、`assumptions_log`、`completion_status` 必须进入 Worker outputs；
3. `missing_timeframe`、`evidence_shortage`、`provenance_failure` 等 failure modes 必须进入 hard facts；
4. `Do not invent links or unseen facts` 必须进入 constraint hints；
5. `source gathering` 和 `template matching` 必须进入 delegation hints；
6. Adapter 不直接生成 SPL。

---

## 14. 实现优先级

## Phase 1：最小可用版本

目标：解决当前 structural_nl 输入无法充分利用结构的问题。

必须实现：

1. `InputAdapter` 接口；
2. `AdapterDetectionResult`；
3. `CanonicalCompileInput` 数据模型；
4. `StructuralNLAdapter.detect()`；
5. `StructuralNLAdapter.adapt()`；
6. section parser；
7. inputs hard facts；
8. outputs hard facts；
9. failure modes hard facts；
10. basic constraint hints；
11. basic process hints；
12. basic delegation hints。

暂不实现：

1. LLM 辅助适配；
2. 复杂 bullet/list parser；
3. span-level coverage；
4. 多 schema 自动冲突处理。

---

## Phase 2：与 pipeline 深度集成

目标：让现有 pipeline 真正消费 adapter 结果。

实现：

1. SpanSlicer 支持 `semantic_packets`；
2. ResourceExtractor 支持 `hard_facts.inputs/outputs` seed；
3. FlowAssembler 支持 `failure_modes` 和 `flow_hints`；
4. ConstraintExtractor 支持 `constraint_hints`；
5. WorkerAssembler 使用 seeded inputs/outputs；
6. Validator 支持 adapter-derived required output reachability。

---

## Phase 3：扩展更多 adapter

目标：支持更多结构化输入。

候选 adapter：

1. `skill_md`；
2. `api_task_spec`；
3. `workflow_spec`；
4. `policy_doc`；
5. `generic_nl` fallback。

所有 adapter 必须输出同一个 `CanonicalCompileInput`。

---

## 15. 关键设计决策总结

| 决策 | 结论 |
|---|---|
| Adapter 是否属于 compile pipeline 内部？ | 否。它是独立前置归一化层。 |
| Adapter 是否直接输出 SPL？ | 否。 |
| Adapter 是否直接输出最终 IR？ | 否。只输出 hard facts 和 compile hints。 |
| 所有 adapter 是否统一输出格式？ | 是。统一输出 `CanonicalCompileInput`。 |
| detect 是否返回 confidence？ | 否。使用结构证据字段。 |
| schema_name 如何命名？ | `structural_nl`。 |
| structural_nl 是否等于 internal comms？ | 否。structural_nl 是输入结构，不是业务领域。 |
| Inputs / Required outputs 是否 hard facts？ | 是。 |
| Reusable process 是否 hard fact？ | 通常不是，主要是 process hints。 |
| Policies 是否 hard fact？ | 文本存在是事实，但 constraint kind/target 通常是 hint。 |
| Failure handling 是否 hard fact？ | failure mode 列表是 hard fact，具体处理结构是 hint。 |
| Delegation policy 是否 hard fact？ | 委托边界较强，委托候选通常是 hint。 |

---

## 16. 推荐目录结构

```text
nl2spl/
  adapters/
    __init__.py
    base.py
    registry.py
    structural_nl.py
    generic_nl.py
  canonical/
    __init__.py
    compile_input.py
    detection.py
    packets.py
    facts.py
    hints.py
  compiler/
    pipeline.py
    stages/
      span_slicer.py
      field_router.py
      resource_extractor.py
      flow_assembler.py
      constraint_extractor.py
  validators/
    semantic_coverage_validator.py
```

---

## 17. 伪代码实现

```python
class StructuralNLAdapter(InputAdapter):
    name = "structural_nl"
    schema_version = "1.0"

    def detect(self, raw_text: str) -> AdapterDetectionResult:
        sections = self._parse_sections(raw_text)
        matched = [s.canonical_title for s in sections if s.canonical_title in STRUCTURAL_NL_CANONICAL_TITLES]
        missing = self._find_missing_sections(matched)
        duplicate = self._find_duplicate_sections(matched)
        empty = [s.canonical_title for s in sections if not s.text.strip()]

        is_matched = self._is_matched(matched)

        return AdapterDetectionResult(
            matched=is_matched,
            schema_name="structural_nl",
            schema_version="1.0",
            matched_sections=matched,
            missing_sections=missing,
            duplicate_sections=duplicate,
            empty_sections=empty,
            unexpected_sections=self._find_unexpected_sections(sections),
            parse_errors=[],
        )

    def adapt(self, raw_text: str) -> CanonicalCompileInput:
        sections = self._parse_sections(raw_text)

        semantic_packets = []
        hard_facts = HardFacts()
        compile_hints = CompileHints()
        warnings = []

        for section in sections:
            if section.canonical_title == "inputs_for_each_run":
                inputs = self._extract_inputs(section)
                hard_facts.inputs.extend(inputs)
                semantic_packets.extend(self._inputs_to_packets(inputs, section))

            elif section.canonical_title == "required_outputs":
                outputs = self._extract_outputs(section)
                hard_facts.outputs.extend(outputs)
                semantic_packets.extend(self._outputs_to_packets(outputs, section))

            elif section.canonical_title == "failure_handling":
                modes = self._extract_failure_modes(section)
                hard_facts.failure_modes.extend(modes)
                compile_hints.flow_hints.extend(self._failure_modes_to_flow_hints(modes, section))

            elif section.canonical_title == "policies":
                compile_hints.constraint_hints.extend(self._extract_constraint_hints(section))

            elif section.canonical_title == "reusable_process":
                compile_hints.process_hints.extend(self._extract_process_hints(section))

            elif section.canonical_title == "delegation_policy":
                compile_hints.delegation_hints.extend(self._extract_delegation_hints(section))
                compile_hints.constraint_hints.extend(self._extract_delegation_constraint_hints(section))

            elif section.canonical_title == "task_family":
                compile_hints.profile_hints.extend(self._extract_profile_hints(section))

        return CanonicalCompileInput(
            source_schema="structural_nl",
            schema_version="1.0",
            raw_text=raw_text,
            raw_sections=sections,
            semantic_packets=semantic_packets,
            hard_facts=hard_facts,
            compile_hints=compile_hints,
            warnings=warnings,
        )
```

---

## 18. 最终结论

InputAdapter 的价值不在于替代 compiler，而在于将输入结构中已经明确的语义提前显式化、标准化、可追踪化。

它解决的是现有 compile pipeline 的前置输入质量问题：

```text
原始 structural NL
  → 容易被错误切片、错误路由、遗漏 outputs/failure/delegation

CanonicalCompileInput
  → hard facts 明确，compile hints 可用，provenance 可追踪，pipeline 仍保持通用
```

因此，InputAdapter 应作为独立模块存在，输出统一的 `CanonicalCompileInput`，并通过 hard facts 与 compile hints 以低耦合方式服务现有 pipeline。

