# Stage 1 LLM-Guided Source-Constrained Span Slicing 设计文档

日期：2026-07-05
状态：Draft for implementation planning
适用范围：NL2SPL Compile Pipeline Stage 1 Span Slicer；后续 Stage 4/5 guarded-action consumption；Stage 7 guard-only residual fail-closed

---

## 0. 核心结论

Stage 1 的 span slicing 不应升级为纯 rule-based sentence scanner。当前问题的本质不是普通 sentence boundary detection，而是：

```text
canonical semantic packets / raw text
-> source-backed semantic spans
-> guard-action atomicity
-> cross-packet guarded-action recovery
-> downstream IF block contract
```

因此，推荐方案是：

```text
LLM-guided semantic span slicing
+ deterministic source reconstruction
+ deterministic provenance / schema / coverage validation
+ bounded retry
+ conservative fallback
+ sidecar-first metadata contract
```

一句话：

```text
LLM 判断 semantic span boundary；代码验证它是否忠实于 source。
```

Stage 1 不应变成：

```text
rule-based semantic parser
rule-based action classifier
construct router
condition recognizer
StepIR / BlockIR materializer
```

Stage 1 只输出：

```text
SpanIR
+ span_segmentation_records sidecar
```

其中 `span_segmentation_records` 只表达文本边界和轻量句法关系，不表达 SPL construct authority。

---

## 1. 背景与问题

`internal_comms.txt` 中存在如下片段：

```text
If sources are needed and available, retrieve them using approved source
recipes. Maintain provenance for externally sourced facts. When enough required
information is available, produce a draft. If the user asks for revision, revise while re
checking constraints.
```

当前输出中出现错误 command：

```text
COMMAND [COMMAND When enough required information is available]
```

该文本不是 executable command，而是 guard / condition。它应当修饰后续动作：

```text
When enough required information is available, produce a draft.
```

期望 SPL 结构应类似：

```text
IF enough required information is available
  COMMAND Produce a draft ...
END_IF
```

而不是单独渲染：

```text
COMMAND When enough required information is available
```

当前错误链路为：

```text
Stage 1:
  s16 = retrieve... Maintain provenance... When enough required information is available
  s17 = produce a draft. If the user asks for revision

Stage 4/5:
  未恢复 When enough... 与 produce a draft 的 guard-action relation

Stage 7:
  API residual projector 扣除 retrieve...
  剩余 When enough... 被误物化为 GENERAL_COMMAND
```

根因是 Stage 1 canonical path 使用：

```text
semantic packet -> exactly one SpanIR
```

它保留 packet 边界，但没有做 packet 内语义切分，也没有修复跨 packet 的 guard/action 断裂。

---

## 2. 为什么不采用纯 rule-based sentence scanner

### 2.1 普通 sentence segmentation 不等于 semantic span slicing

Stage 1 需要产出的不是普通句子列表，而是 compiler-friendly semantic spans。

例如：

```text
When enough required information is available, produce a draft.
```

这里需要同时识别：

```text
segmentation_kind = guarded_action
guard_text = enough required information is available
action_text = produce a draft
```

这已经不是普通 `.!?` sentence boundary detection。

### 2.2 action-like phrase 很难靠规则稳定定义

目标文本可能是：

```text
produce a draft
revise while re-checking constraints
maintain provenance
ask only the highest-value clarifying questions
do not finalize if required slots remain missing
```

也可能是：

```text
the assistant should produce a draft
the next step is to produce a draft
a draft is produced once enough information is available
produce a draft once enough information is available
```

如果用规则判定 action-like phrase，需要持续追加动词白名单、句法规则、例外规则，最终 Stage 1 会退化成脆弱的 rule-based semantic parser。

### 2.3 rule-based scanner 会侵蚀 Stage 2 / ConstructPlan authority

Stage 1 的 authority 应仅限于：

```text
text boundary
source provenance
lightweight guard/action segmentation hint
```

Stage 1 不应判断：

```text
semantic_role
construct_type
failure_condition
exception_handler
api_call
constraint
repairability
```

这些属于 Stage 2 RouteAnnotation、Stage 3 ambiguity resolution、ConstructPlan、Stage 4/5/7 或 IRS 的职责。

### 2.4 规则可以保留，但只能作为验证与保底

rule-based code 应负责：

```text
source reconstruction
offset mapping
schema validation
coverage validation
parent_packet_ids derivation
no cross-section merge
bounded fallback
Stage 7 guard-only fail-closed
```

不应负责主判定：

```text
是否 guarded_action
guard/action 边界
是否跨 packet merge
action-like semantic plausibility
```

---

## 3. 设计目标

### 3.1 功能目标

1. Stage 1 不再产生 guard-only tail span，例如：

```text
When enough required information is available
```

2. Stage 1 能输出完整 guarded-action span：

```text
When enough required information is available, produce a draft.
```

3. Stage 1 sidecar 记录：

```text
segmentation_kind = guarded_action
guard_text = enough required information is available
action_text = produce a draft
parent_packet_ids = [...]
char_start / char_end
continuation_repaired = true
```

4. Stage 4/5 消费 sidecar，将 guarded_action 转换为 IF block，或显式诊断，不得静默降级为 SEQUENTIAL。

5. Stage 7 无论上游是否失败，都不得再次渲染：

```text
COMMAND When enough required information is available
```

### 3.2 架构目标

1. LLM 只做 source-constrained segmentation，不做 SPL construct routing。
2. Deterministic validator 保证 LLM 输出没有改写、重排、越界、跨 section 合并或伪造 provenance。
3. SpanIR schema 短期不强制修改；优先 sidecar-first。
4. Stage 1 output 必须可 checkpoint、可 diff、可审计。
5. 失败路径必须 fail closed，不能制造 executable command。

---

## 4. 非目标

本设计不要求：

```text
- Stage 1 生成 FlowIR / BlockIR / StepIR
- Stage 1 判定最终 command_type
- Stage 1 判定 EXCEPTION_FLOW / ALTERNATIVE_FLOW / CONSTRAINT / API_CALL
- Stage 1 变成 rule-based NL parser
- Stage 7 构造 IF block
- Renderer / Gate / SPL Editing 修复 control-flow
- 一次性重写 Stage 4/5
- 完全取消 deterministic guard
```

---

## 5. 总体架构

新版 Stage 1 canonical path：

```text
CanonicalCompileInput.semantic_packets
  -> SourceSectionReconstructor
  -> SectionSourceBuffer + packet offset map
  -> LLMSourceConstrainedSegmenter
  -> Stage1SegmentationValidator
  -> SpanIR materialization
  -> span_segmentation_records sidecar
  -> Stage 2 FieldRouter
```

Stage 4/5 消费路径：

```text
SpanIR + span_segmentation_records
  -> Stage 4 FlowAssembler
  -> WorkerFlowPlanIR
  -> Stage 5 BlockAssembler
  -> IF block for guarded_action
```

Stage 7 保底路径：

```text
StepExtractor residual projector
  -> guard-only residual detector
  -> no GENERAL_COMMAND
  -> stage7_guard_residual_not_materialized diagnostic
```

---

## 6. 核心原则

### 6.1 LLM 负责语义边界，不负责 provenance truth

LLM 可以输出：

```text
This source range is a guarded_action.
This part is guard_text.
This part is action_text.
This span crosses packet p16 and p17.
```

但最终 provenance truth 由 validator 裁决：

```text
segment text 是否来自 source buffer
char range 是否匹配
parent_packet_ids 是否可由 source range 推导
segments 是否 source-order aligned
segments 是否跨 section
```

### 6.2 text preservation is mandatory

LLM 不得 paraphrase。输出 `segment.text` 必须能在 source buffer 中定位。

允许 deterministic normalization：

```text
soft line break normalization
whitespace normalization
quote normalization if already supported by source map
```

禁止：

```text
改写文本
补充文本
删除 source-backed action
把 guard 改写成另一种表达
生成 source 中不存在的 action_text
```

### 6.3 sidecar 是 Stage 1 metadata authority

短期不修改 `SpanIR` dataclass。

`SpanIR` 仍保持最小结构：

```text
span_id
text
source_section_id
source_packet_id
```

跨 packet span 的完整 provenance 放入 sidecar：

```text
parent_packet_ids
char_start
char_end
continuation_repaired
```

`SpanIR.source_packet_id` 可保留 primary parent packet，用于兼容旧路径；完整 packet lineage 以 sidecar 为准。

### 6.4 Stage 1 metadata 不表达 construct authority

允许：

```text
atomic_text_unit
atomic_action_candidate
guarded_action
continuation_repaired
ambiguous_boundary
```

禁止：

```text
process_step
failure_condition
exception_handler
api_call
constraint
repairable
IF_BLOCK
GENERAL_COMMAND
```

---

## 7. 数据模型

### 7.1 SectionSourceBuffer

```python
@dataclass(frozen=True)
class SectionSourceBuffer:
    source_section_id: str
    normalized_text: str
    packet_ranges: tuple[SourcePacketRange, ...]
    normalization_map: SourceNormalizationMap
```

### 7.2 SourcePacketRange

```python
@dataclass(frozen=True)
class SourcePacketRange:
    packet_id: str
    source_section_id: str
    normalized_char_start: int
    normalized_char_end: int
    original_char_start: int | None = None
    original_char_end: int | None = None
```

### 7.3 LLMSpanSegment

LLM raw output schema:

```python
@dataclass(frozen=True)
class LLMSpanSegment:
    segment_text_exact: str
    segmentation_kind: Literal[
        "atomic_text_unit",
        "atomic_action_candidate",
        "guarded_action",
        "continuation_repaired",
        "ambiguous_boundary",
    ]
    guard_text_exact: str | None = None
    action_text_exact: str | None = None
    source_packet_ids: tuple[str, ...] = ()
    source_section_id: str | None = None
    char_start: int | None = None
    char_end: int | None = None
    boundary_confidence: Literal["high", "medium", "low"] = "medium"
    continuation_repaired: bool = False
```

说明：

```text
char_start / char_end 可由 LLM 提供，但只作为 hint。
validator 必须重新定位 segment_text_exact 并计算 authoritative range。
validator 通过后再规范化为内部 `SpanSegmentationRecord.span_text / guard_text / action_text / parent_packet_ids`。
```

### 7.4 SpanSegmentationRecord

Validated sidecar schema:

```python
@dataclass(frozen=True)
class SpanSegmentationRecord:
    span_id: str
    span_text: str
    segmentation_kind: Literal[
        "atomic_text_unit",
        "atomic_action_candidate",
        "guarded_action",
        "continuation_repaired",
        "ambiguous_boundary",
    ]
    guard_text: str | None
    action_text: str | None
    parent_packet_ids: tuple[str, ...]
    source_section_id: str
    char_start: int
    char_end: int
    boundary_confidence: Literal["high", "medium", "low"]
    continuation_repaired: bool
    validation_status: Literal["validated", "repaired_by_validator", "ambiguous"]
    metadata: Mapping[str, JsonValue]
```

### 7.5 Stage1SegmentationPayload

Checkpoint payload:

```python
@dataclass(frozen=True)
class Stage1SegmentationPayload:
    records: tuple[SpanSegmentationRecord, ...]
    diagnostics: tuple[CompileDiagnostic, ...]
    warnings: tuple[str, ...]
    source_buffers: tuple[SectionSourceBufferPayload, ...]
```

Intermediate keys:

```python
intermediate["stage1_segmentation_records"] = records
intermediate["span_segmentation_records"] = deterministic_payload
intermediate["stage1_source_buffers"] = source_buffers_payload
```

---

## 8. Source reconstruction

### 8.1 输入

```text
canonical_input.semantic_packets
```

每个 packet 至少包含：

```text
packet_id
source_section_id
text
source order
```

### 8.2 输出

按 `source_section_id` 分组，按 source order 重建 `SectionSourceBuffer`。

### 8.3 normalization policy

允许：

```text
- 合并 soft line break；
- 将同一 paragraph 内换行规范为空格；
- 保留 blank line / bullet / numbered list / heading boundary；
- 维护 normalized offset 到原 packet 的映射。
```

分隔符规则：

```text
- soft line break 只能规范为空格；
- packet boundary 只能规范为空格或保留已有 source punctuation；
- normalization 不得自动插入逗号、句号或其他 source 中不存在的标点；
- 如果 LLM 输出的 segment_text_exact 需要靠自动补标点才能匹配 source buffer，validator 必须视为 paraphrase / invalid output。
```

禁止：

```text
- 删除 substantive text；
- 重排 packet；
- 跨 source_section_id 合并；
- 用规则判断 semantic action；
- 在 reconstruction 阶段做 guarded_action 分类。
```

---

## 9. LLM segmentation contract

### 9.1 Prompt 目标

Prompt 不应写成：

```text
Split into sentences.
```

应写成：

```text
Split the source text into source-backed semantic spans for NL2SPL compilation.
A span is the smallest text unit that should stay atomic for downstream routing.
Do not classify SPL constructs. Do not infer commands. Do not rewrite text.
```

### 9.2 LLM 输入格式

建议输入：

```text
Section: reusable_process

Packets:
[p15] First determine what kind of communication is requested. Then identify which required fields are still missing. Ask only the highest-value clarifying questions needed to move forward. If sources are needed and available
[p16] retrieve them using approved source recipes. Maintain provenance for externally sourced facts. When enough required information is available
[p17] produce a draft. If the user asks for revision, revise while re-checking constraints.
[p18] Do not finalize if required slots remain missing unless the draft is explicitly marked as assumption-bearing and the user confirms.
[p19] At the end, record unresolved items in an assumptions log and set completion status.
```

### 9.3 Prompt rules

```text
1. Preserve source text.
   Segment text must be copied from the source packets. Do not paraphrase.

2. Preserve guard-action atomicity.
   If if/when/unless/once/as long as/provided that/in case/on condition that
   introduces a condition that governs an action, keep the condition and action
   in the same segment.
   guard_text must exclude the introducing keyword.
   Example: "When enough required information is available, produce a draft."
   guard_text = "enough required information is available"
   action_text = "produce a draft"

3. Repair packet-boundary splits.
   If one packet ends with a guard-only fragment and the next adjacent packet
   starts with the governed action, merge them into one guarded_action segment.

4. Do not classify SPL constructs.
   Do not label any segment as IF_BLOCK, EXCEPTION_FLOW, CONSTRAINT, API_CALL,
   COMMAND, REQUEST_INPUT, worker handoff, or repair target.

5. Use ambiguity explicitly.
   If the semantic boundary is unclear, output ambiguous_boundary rather than
   guessing.

6. Keep source order.
   Segments must follow original packet order and must not overlap.

7. Do not drop source-backed behavior.
   Every substantive source text unit must be covered by exactly one segment
   unless it is explicitly marked ambiguous_boundary.
```

### 9.4 Output JSON schema

```json
{
  "segments": [
    {
      "segment_text_exact": "When enough required information is available, produce a draft.",
      "segmentation_kind": "guarded_action",
      "guard_text_exact": "enough required information is available",
      "action_text_exact": "produce a draft",
      "source_packet_ids": ["p16", "p17"],
      "source_section_id": "reusable_process",
      "char_start": 456,
      "char_end": 518,
      "boundary_confidence": "high",
      "continuation_repaired": true
    }
  ]
}
```

### 9.5 Required few-shot examples

Prompt 必须包含至少以下 example classes：

```text
1. packet 内普通多句拆分
2. packet 内完整 guarded_action
3. cross-packet guarded_action repair
4. trailing guard without recoverable action -> ambiguous_boundary
5. user-choice condition，不在 Stage 1 分类为 alternative_flow
6. failure/recovery condition，不在 Stage 1 分类为 exception_flow
7. policy / constraint-like text，不在 Stage 1 分类为 constraint
8. 同一 packet 内多个独立 guarded_action：
   "If X, do A. If Y, do B." -> two separate guarded_action segments
```

---

## 10. Deterministic validation

### 10.1 Validator 输入

```text
SectionSourceBuffer
LLMSpanSegment[]
```

### 10.2 必须校验

```text
1. segment_text_exact 可以在 SectionSourceBuffer.normalized_text 中定位。
2. 定位结果与 char_start / char_end 一致；如不一致，以 deterministic locator 为准。
3. parent_packet_ids 可由 authoritative char range 反推。
4. source_section_id 与 source buffer 一致。
5. segments 按 source order 排列。
6. segments 不重叠。
7. segments 不跨 source_section_id。
8. segmentation_kind 属于允许枚举。
9. guarded_action 必须有 guard_text 和 action_text。
10. guard_text_exact / action_text_exact 必须是 segment_text_exact 的子串或 normalization-equivalent 子串。
11. guard-only fragment 不得作为 atomic_action_candidate。
12. ambiguous_boundary 不得被下游 Stage 5 当作 guarded_action。
13. LLM 不得引入 source 中不存在的 text。
```

`parent_packet_ids` 以 validator 通过 authoritative char range 和 packet range map 重新计算的结果为准。

```text
- 如果 LLM 只给出顺序不规范的同一组 packet ids，validator 可规范化顺序；
- 如果 LLM 遗漏 packet，但 authoritative range 显示 segment 跨越相邻 packets，validator 可重算并记录 repaired_by_validator；
- 如果 LLM 声明的 packet ids 与 authoritative range 完全不相交，或差异超过一个相邻 packet，validator 必须 emit stage1_segmentation_schema_invalid 并触发 retry；
- validator 不得为了匹配 LLM parent_packet_ids 而移动 segment range。
```

### 10.3 Coverage policy

默认要求覆盖 section 中所有 substantive process text。

允许以下文本作为 non-substantive：

```text
empty whitespace
pure list marker
format-only heading marker
adapter scaffold marker
```

如果存在 uncovered substantive text：

```text
validator emits stage1_segmentation_uncovered_text
retry once or twice
still invalid => conservative fallback + diagnostic
```

### 10.4 Duplicate text disambiguation

如果 `segment.text` 在 source buffer 中多次出现，validator 必须使用：

```text
parent_packet_ids hint
source order
non-overlap constraint
char_start / char_end hint
```

仍无法唯一定位时：

```text
validation_status = ambiguous
segmentation_kind = ambiguous_boundary
emit stage1_segmentation_ambiguous_range
```

---

## 11. Retry and fallback

### 11.1 Bounded retry

LLM output invalid 时，允许 bounded retry：

```text
max_retries = 2
```

Retry prompt 只包含：

```text
original source buffer
previous invalid output
structured validation errors
required correction instructions
```

不得让 retry 引入新的 task scope。

### 11.2 Conservative fallback

如果 retry 后仍失败：

```text
1. 不使用 invalid LLM segmentation。
2. 回退到 conservative packet-level spans 或 minimal deterministic splits。
3. 对疑似 guard-only fragment 标记 ambiguous_boundary。
4. emit stage1_llm_segmentation_failed。
5. Stage 7 guard-only fail-closed 继续阻止错误 command。
```

Fallback 不保证生成理想 IF block，但必须保证：

```text
不因 LLM 失败而制造 unsourced command。
```

---

## 12. SpanIR materialization

### 12.1 Span id

新 span id 可以继续使用顺序编号：

```text
s1, s2, s3, ...
```

如果为了 trace 可读性需要保留 parent 信息，可在 sidecar 中记录：

```text
parent_packet_ids
```

不要把 packet id 拼进 span id，避免下游假设 span id 格式。

### 12.2 source_packet_id 兼容策略

`SpanIR.source_packet_id` 只能容纳一个 packet 时：

```text
source_packet_id = primary parent packet id
```

推荐 primary packet 规则：

```text
- 如果单 packet span：该 packet id
- 如果跨 packet span：包含 segment.char_start 的 packet id
```

完整 provenance 以 sidecar 为准：

```text
SpanSegmentationRecord.parent_packet_ids
char_start / char_end
continuation_repaired
```

### 12.3 text policy

`SpanIR.text` 使用 validator-confirmed segment text。

不使用未经验证的 LLM paraphrase。

---

## 13. Stage 4 consumer contract

Stage 4 输入新增可选 metadata：

```python
FlowAssembler.execute(
    spans: list[SpanIR],
    routes: FieldRouteIR,
    segmentation_records_by_span_id: Mapping[str, SpanSegmentationRecord] | None = None,
    ...
)
```

Stage 4 行为：

```text
1. guarded_action span stays in main_flow by default.
2. guarded_action 不应被 Stage 4 自动转成 alternative_flow。
3. guarded_action 不应被 Stage 4 自动转成 exception_flow。
4. 如果 Stage 2 / ConstructPlan 明确将该 span 归为 failure/recovery demand，则 Stage 4 可按 construct demand 处理。
5. Stage 4 必须把 guarded_action metadata 透传给 Stage 5。
```

`ambiguous_boundary` 行为：

```text
1. Stage 4 可将 ambiguous_boundary 保留在 main_flow 中，但必须保留 metadata。
2. Stage 4 不得把 ambiguous_boundary 自动升级为 alternative_flow、exception_flow 或 guarded_action。
3. 如果 ambiguous_boundary 疑似 guard/action 断裂，Stage 4 必须透传该状态给 Stage 5，并保留 source_span_ids。
```

Stage 4 不负责：

```text
- 构造 IF block
- 生成 StepIR
- 从 unrelated spans 重新配对 guard/action
```

---

## 14. Stage 5 consumer contract

Stage 5 输入新增：

```python
BlockAssembler.execute(
    worker_flow_plan: WorkerFlowPlanIR,
    spans: list[SpanIR],
    segmentation_records_by_span_id: Mapping[str, SpanSegmentationRecord] | None = None,
    ...
)
```

强制行为：

```text
if record.segmentation_kind == "guarded_action":
    create local IF block
    condition_text = record.guard_text
    block.spans includes record.span_id
```

`ambiguous_boundary` 行为：

```text
if record.segmentation_kind == "ambiguous_boundary":
    do not create IF block
    do not silently place guard-only text into SEQUENTIAL as executable work
    emit stage1_guard_action_boundary_ambiguous when the span starts with a control introducer
    keep the span non-executable if it is guard-only
```

禁止：

```text
- 静默放入 SEQUENTIAL
- 丢弃 guard_text
- 将 action_text 单独作为 unguarded normal command
- 从 raw text 重新猜 condition/action
```

如果 Stage 5 决定不创建 IF block，必须 emit diagnostic：

```text
kind = guarded_action_classified_as_non_control_precondition
severity = warning
blocks_rendering = false
blocks_completion = true
target_ref = span_id
source_span_ids = [span_id]
metadata = {
  "guard_text": ...,
  "action_text": ...,
  "reason": ...
}
```

该 diagnostic 必须可进入 compile/debug report，不能静默吞掉。

---

## 15. Stage 7 fail-closed contract

Stage 7 不负责构造 IF block。

但 Stage 7 必须防止 guard-only residual 被物化为 command。

规则：

```text
if residual text is guard-only:
    do not create GENERAL_COMMAND
    emit stage7_guard_residual_not_materialized
```

Stage 7 的 guard-only 检测是独立 fail-closed 保险，不能依赖 sidecar 中存在完整 `guarded_action` record。即使 fallback 路径没有 sidecar，Stage 7 也必须基于 residual text 执行最小检测：

```text
guard-only residual =
  residual sentence starts with if/when/unless/once/as long as/provided that/in case/on condition that
  AND it does not contain an action body after comma / clause boundary
```

该检测只用于拒绝 `GENERAL_COMMAND` materialization，不用于构造 IF block，也不用于识别 construct type。

Diagnostic 建议：

```text
kind = stage7_guard_residual_not_materialized
severity = warning
blocks_rendering = false
blocks_completion = true
```

Stage 7 不得：

```text
- 从 guard-only residual 构造 IF
- 伪造 action body
- 把 guard-only text 作为 GENERAL_COMMAND
```

---

## 16. Diagnostics

新增或预留 diagnostic kinds：

```text
stage1_llm_segmentation_failed
stage1_segmentation_schema_invalid
stage1_segmentation_uncovered_text
stage1_segmentation_ambiguous_range
stage1_guard_action_boundary_ambiguous
guarded_action_classified_as_non_control_precondition
stage7_guard_residual_not_materialized
```

默认 severity：

| diagnostic                                              | severity | blocks_rendering | blocks_completion |
| ------------------------------------------------------- | -------: | ---------------: | ----------------: |
| `stage1_llm_segmentation_failed`                        |  warning |            false |              true |
| `stage1_segmentation_schema_invalid`                    |  warning |            false |              true |
| `stage1_segmentation_uncovered_text`                    |  warning |            false |              true |
| `stage1_segmentation_ambiguous_range`                   |  warning |            false |              true |
| `stage1_guard_action_boundary_ambiguous`                |  warning |            false |              true |
| `guarded_action_classified_as_non_control_precondition` |  warning |            false |              true |
| `stage7_guard_residual_not_materialized`                |  warning |            false |              true |

这些 diagnostics 表示 compilation quality gap，而不是 SPL rendering 必须中止。

---

## 17. Prompt 文件建议

建议新增或替换：

```text
prompts/stage1_source_constrained_segmentation_system.txt
prompts/stage1_source_constrained_segmentation_user_template.txt
```

System prompt 核心内容：

```text
You are segmenting source text for a compiler.
You must preserve source text exactly.
You must output JSON only.
You must not classify SPL constructs.
You must preserve guard-action atomicity.
You must repair adjacent packet-boundary guard/action splits when source-backed.
If unsure, mark ambiguous_boundary.
```

User prompt 包含：

```text
- section id
- ordered packets
- allowed segmentation kinds
- output schema
- examples
- validation constraints
```

---

## 18. Configuration

建议新增 Stage 1 config：

```python
@dataclass(frozen=True)
class Stage1SegmentationConfig:
    mode: Literal[
        "legacy_packet_passthrough",
        "llm_source_constrained_shadow",
        "llm_source_constrained",
        "deterministic_fallback_only",
    ] = "legacy_packet_passthrough"
    max_retries: int = 2
    require_full_coverage: bool = True
    emit_sidecar: bool = True
    require_validator_pass: bool = True
    fail_closed_on_invalid_llm_output: bool = True
```

`llm_source_constrained` 是目标生产模式，但首个实现阶段不得无条件替换 legacy Stage 1。生产 rollout 必须受 feature flag / staged rollout 控制：

```text
R1: legacy_packet_passthrough + llm_source_constrained_shadow
    - 不改变 final SPL
    - 保存 shadow segmentation payload
    - 对比 legacy spans / LLM spans / validator diagnostics

R2: llm_source_constrained for selected regression fixtures
    - internal_comms 等受控样例启用
    - Stage 1 sidecar + Stage 5 consumer + Stage 7 fail-closed 必须同一 release 闭环

R3: llm_source_constrained as production default
    - 前提是 segmentation gate 连续通过
    - validator failure rate、fallback rate、E2E regression 均低于阈值
```

不得在只有 LLM prompt、没有 validator、没有 Stage 5 consumer 的情况下把 `llm_source_constrained` 设为默认。

R1 进入 R2 的最小 exit criteria：

```text
- shadow segmentation payload 已稳定写入 checkpoint；
- shadow validator failure rate < 5%；
- shadow fallback rate < 5%；
- shadow segment coverage gap vs legacy < 2%；
- zero cross-section merge errors in shadow；
- internal_comms shadow output matches expected guarded_action segmentation；
- shadow comparison report 可由 CI 或 review artifact 复验。
```

---

## 19. 测试矩阵

### 19.1 Source reconstruction tests

覆盖：

```text
soft line break
blank line
bullet list
numbered list
same section packet ordering
cross-section no merge
normalized offset map
```

### 19.2 LLM output validator tests

构造 fake LLM output，验证：

```text
valid exact text accepted
paraphrased text rejected
cross-section segment rejected
overlap rejected
out-of-order rejected
invalid parent_packet_ids corrected or rejected
missing guard_text/action_text for guarded_action rejected
duplicate text ambiguous range handled
uncovered text diagnostic emitted
```

### 19.3 Stage 1 segmentation golden tests

输入：

```text
When enough required information is available, produce a draft.
```

预期：

```text
segmentation_kind = guarded_action
guard_text = enough required information is available
action_text = produce a draft
```

输入跨 packet：

```text
p16: When enough required information is available
p17: produce a draft.
```

预期：

```text
one guarded_action span or span group
parent_packet_ids = [p16, p17]
continuation_repaired = true
```

### 19.4 Stage 4/5 integration tests

输入 Stage 1 sidecar：

```text
record.segmentation_kind = guarded_action
guard_text = enough required information is available
action_text = produce a draft
```

预期 Stage 5：

```text
block_type = IF
condition_text = enough required information is available
spans include guarded_action span_id
```

负例：

```text
Stage 5 puts guarded_action into SEQUENTIAL silently
```

必须 fail。

### 19.5 Stage 7 regression tests

输入 residual：

```text
When enough required information is available
```

预期：

```text
no GENERAL_COMMAND
stage7_guard_residual_not_materialized diagnostic emitted
```

### 19.6 End-to-end demo regression

对 `internal_comms`：

```text
final_spl.txt 不包含:
COMMAND When enough required information is available

Stage 1 checkpoint 包含:
guarded_action record for When enough..., produce a draft

Stage 5 checkpoint 包含:
IF block with condition_text = enough required information is available

Stage 7 不产生 guard-only command
```

---

## 20. 实施阶段

### Phase A0：Characterization

只加测试，锁定当前错误：

```text
s16 tail = When enough required information is available
s17 head = produce a draft
Stage 7 renders guard-only command
```

### Phase A1：Source reconstruction and offset map

新增：

```text
src/nl2spl/pipeline/stages/stage1_span_slicer/source_buffer.py
```

实现：

```text
SectionSourceBuffer
SourcePacketRange
normalization map
```

### Phase B：LLM source-constrained segmentation prompt and parser

新增：

```text
stage1_source_constrained_segmentation_system.txt
stage1_source_constrained_segmentation_user_template.txt
llm_segment_parser.py
```

输出 `LLMSpanSegment[]`。

### Phase C：Deterministic validator

新增：

```text
segmentation_validator.py
```

负责：

```text
text location
coverage
range validation
parent_packet_ids derivation
schema enforcement
retry error production
```

### Phase D：SpanIR + sidecar materialization

新增或修改：

```text
stage1_span_slicer.py
segmentation_payload.py
```

输出：

```text
List[SpanIR]
stage1_segmentation_records
span_segmentation_records checkpoint
```

### Phase E：Stage 4/5 consumer integration

修改 Stage 4/5 execute contract，消费：

```text
segmentation_records_by_span_id
```

Stage 5 对 `guarded_action` 生成 IF block。

### Phase F：Stage 7 fail-closed

增加 guard-only residual filter。

### Phase G：End-to-end regression and audit

运行：

```text
unit tests
integration tests
demo golden output diff
git diff --check
prompt snapshot audit
```

---

## 21. 验收标准

最终通过条件：

```text
1. Stage 1 不再产生 guard-only tail span:
   "When enough required information is available"

2. Stage 1 输出 source-backed guarded_action sidecar:
   guard_text
   action_text
   parent_packet_ids
   char_start / char_end
   continuation_repaired

3. LLM segmentation output 必须通过 deterministic validation:
   no paraphrase
   no cross-section merge
   no overlap
   no out-of-order segment
   no fabricated parent_packet_ids

4. Stage 5 对 guarded_action 生成 IF block:
   condition_text = guard_text
   spans includes guarded_action span_id

5. Stage 5 不能静默 SEQUENTIAL:
   如果不生成 IF，必须 emit diagnostic。

6. Stage 7 不得渲染:
   COMMAND When enough required information is available

7. Stage 1 不输出 construct authority:
   no semantic_role
   no construct_type
   no failure_condition
   no exception_handler
   no api_call
   no repairability

8. invalid LLM output fail closed:
   retry bounded
   fallback conservative
   diagnostic visible

9. internal_comms E2E golden:
   Produce a draft 位于 IF enough required information is available block 中，
   或若产品决策不采用 IF，则必须有 guarded_action_classified_as_non_control_precondition diagnostic。
```

---

## 22. 最终判断

Stage 1 的修复不应退回纯规则化 NLP。更合适的架构是：

```text
LLM for semantic span slicing.
Code for compiler-grade verification.
Sidecar for downstream control-flow contract.
Stage 7 for residual safety.
```

该方案比纯 rule-based scanner 更适合 NL2SPL 的多阶段 LLM compiler 架构，同时保留 source-backed partial SPL 的工程底线：

```text
LLM 可以判断边界，但不能伪造来源；
validator 可以拒绝输出，但不能越权做语义 materialization；
Stage 5 可以消费 guarded_action，但必须显式构造 IF 或显式诊断；
Stage 7 可以拒绝 guard-only residual，但不能构造 control-flow。
```

---

## 23. v2.1 Implementation Gate

本节是进入 implementation plan 前的硬性收口。它不改变本文的架构方向，但把 rollout、prompt、validator、Stage 5 消费和 fallback 行为提升为 implementation gate。

### 23.1 Release / feature-flag 策略

`llm_source_constrained` 是目标生产模式，但不得在首个实现阶段无条件替换 legacy Stage 1。

配置必须至少支持：

```python
@dataclass(frozen=True)
class Stage1SegmentationConfig:
    mode: Literal[
        "legacy_packet_passthrough",
        "llm_source_constrained_shadow",
        "llm_source_constrained",
        "deterministic_fallback_only",
    ] = "legacy_packet_passthrough"

    emit_sidecar: bool = True
    require_validator_pass: bool = True
    max_retries: int = 2
    fail_closed_on_invalid_llm_output: bool = True
```

推荐 rollout：

```text
R1: legacy_packet_passthrough + shadow LLM segmentation
    - 不改变 final SPL
    - 保存 shadow segmentation payload
    - 对比 legacy spans / LLM spans / validator diagnostics

R2: llm_source_constrained for selected regression fixtures
    - internal_comms 等受控样例启用
    - Stage 1 + sidecar + Stage 5 consumer + Stage 7 fail-closed 必须同一 release 闭环

R3: llm_source_constrained as production default
    - 前提是 segmentation gate 连续通过
    - validator failure rate、fallback rate、E2E regression 均低于阈值
```

不得在只有 LLM prompt、没有 validator、没有 Stage 5 consumer 的情况下把 `llm_source_constrained` 设为默认。

### 23.2 Prompt exact-copy contract

Prompt 必须把任务定义为 source substring segmentation，而不是 summarization、rewrite 或 interpretation。

LLM 输出字段应使用 exact-copy 命名：

```json
{
  "segments": [
    {
      "segment_text_exact": "When enough required information is available, produce a draft.",
      "segmentation_kind": "guarded_action",
      "guard_text_exact": "enough required information is available",
      "action_text_exact": "produce a draft",
      "source_packet_ids": ["p16", "p17"],
      "source_section_id": "reusable_process",
      "boundary_confidence": "high",
      "continuation_repaired": true
    }
  ]
}
```

Prompt 必须明确：

```text
- Copy exact source substrings from the provided source buffer.
- Do not paraphrase.
- Do not summarize.
- Do not normalize wording.
- Do not invent missing text.
- If you cannot copy exact source text, emit ambiguous_boundary.
```

对于 soft line break / whitespace normalization，系统采用双层文本：

```text
original source packets:
  用于 provenance 与 audit

normalized source buffer:
  用于 LLM segmentation 和 validator substring matching
```

因此，`segment_text_exact` 的 exact 指 exact substring of normalized source buffer。validator 再通过 normalization map 反解到 original packet ranges。

### 23.3 Validator 是 P0 correctness authority

Validator 必须与 LLM prompt 同期实现，不能后补。LLM output 只有在 validator 通过后才能 materialize 为 `SpanIR + span_segmentation_records`。

Validator 必须拒绝：

```text
1. paraphrase：segment_text_exact 不能定位到 normalized source buffer
2. uncovered substantive source text
3. overlapping segments
4. out-of-order segments
5. cross-section merge
6. fabricated source_packet_ids
7. guarded_action missing guard_text_exact or action_text_exact
8. guard_text_exact/action_text_exact not substring of segment_text_exact
9. invalid segmentation_kind
10. ambiguous duplicate range without resolvable packet/range evidence
```

Validator 可修正：

```text
- LLM 提供的 char_start / char_end 不准确；
- source_packet_ids 顺序不规范；
- parent_packet_ids 可通过 authoritative char range -> packet range map 重新计算；
- whitespace-equivalent offset 偏差。
```

`parent_packet_ids` mismatch policy：

```text
- authoritative parent_packet_ids 总是由 validator 反推；
- LLM parent_packet_ids 只作为 hint；
- 如果 LLM parent_packet_ids 与 authoritative parent_packet_ids 为同一集合但顺序不同，validator 可修正；
- 如果 LLM 遗漏相邻 packet，但 segment_text_exact 的 authoritative range 明确覆盖它，validator 可修正并记录 repaired_by_validator；
- 如果 LLM parent_packet_ids 与 authoritative range 完全不相交，或差异超过一个相邻 packet，validator 必须 reject 并 emit stage1_segmentation_schema_invalid；
- validator 不得为了迎合 LLM parent_packet_ids 移动 segment range。
```

Validator 不得修正：

```text
- semantic segmentation_kind；
- guard/action 语义边界；
- action_text 内容；
- construct role；
- downstream block type。
```

如果无法验证：

```text
invalid LLM output
-> bounded retry
-> still invalid: conservative fallback
-> emit diagnostic
-> do not use invalid segmentation
```

### 23.4 Stage 1 sidecar + Stage 5 consumer 必须同一 release 闭环

不能只交付 Stage 1 sidecar，不交付 Stage 5 consumer。

最小 production merge gate 必须包含：

```text
1. Stage 1 source reconstruction
2. LLM source-constrained segmentation
3. deterministic validator
4. SpanIR + span_segmentation_records sidecar materialization
5. Stage 4 metadata pass-through
6. Stage 5 guarded_action -> IF block consumer
7. Stage 7 guard-only residual fail-closed
8. E2E regression
```

原因：

```text
如果只有 Stage 1 span text 变好，但 Stage 5 不消费 guarded_action metadata，
Produce a draft 仍可能进入 SEQUENTIAL block。
这会重新引入 free-text pattern matching 和 prompt drift。
```

Stage 5 强制规则：

```text
if segmentation_record.segmentation_kind == "guarded_action":
    create local IF block
    condition_text = guard_text_exact
    span_ids include segmentation_record.span_id
```

如果不生成 IF，必须发 diagnostic：

```text
guarded_action_classified_as_non_control_precondition
```

禁止静默降级为 SEQUENTIAL。

### 23.5 Fallback hard gate

Fallback 不能恢复旧错误。

即使 LLM segmentation 失败，也必须满足：

```text
final SPL must not contain:
COMMAND When enough required information is available
```

Fallback 策略：

```text
1. 不使用 invalid LLM output；
2. 回退 legacy packet passthrough 或 conservative split；
3. 对疑似 guard-only residual 标记 ambiguous_boundary；
4. Stage 7 guard-only residual filter 必须生效；
5. 输出 visible diagnostic。
```

硬验收：

```text
LLM segmentation failed
-> no guarded_action IF block is acceptable
-> visible diagnostic is required
-> guard-only COMMAND is forbidden
```

### 23.6 v2.1 readiness

```text
Architecture direction: pass
LLM segmentation concept: pass
Implementation readiness: conditional_pass
```

进入 implementation plan 的条件：

```text
1. feature-flag rollout plan 已定义；
2. prompt exact-copy contract 已定义；
3. validator schema / rejection rules / retry rules 已定义；
4. Stage 1 sidecar 与 Stage 5 consumer 作为同一 release gate；
5. fallback hard gate 阻止 guard-only command；
6. internal_comms E2E golden 测试已列为 P0。
```
