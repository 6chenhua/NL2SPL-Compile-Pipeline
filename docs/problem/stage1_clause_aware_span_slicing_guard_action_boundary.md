# Stage 1 Clause-Aware Span Slicing and Guard-Action Boundary Problem

## 1. 背景

`examples/input/internal_comms.txt` 中的 reusable process 包含如下片段：

```text
If sources are needed and available, retrieve them using approved source
recipes. Maintain provenance for externally sourced facts. When enough required
information is available, produce a draft. If the user asks for revision, revise while re
checking constraints.
```

当前 `examples/output/demo/final_spl.txt` 中出现了错误输出：

```text
COMMAND [COMMAND When enough required information is available]
```

这条内容明显不是 executable command，而是 guard / condition。它应当修饰后续动作：

```text
When enough required information is available, produce a draft.
```

最终期望结构应类似：

```text
IF enough required information is available
  COMMAND Produce a draft ...
END_IF
```

而不是把 `When enough required information is available` 单独渲染为 `GENERAL_COMMAND`。

## 2. 当前错误链路

### 2.1 Stage 1 切分结果

当前 `stage1_span_slicer.json` 中相关 spans 为：

```text
s16:
  retrieve them using approved source recipes.
  Maintain provenance for externally sourced facts.
  When enough required information is available

s17:
  produce a draft.
  If the user asks for revision
```

也就是说，一个完整的 guard-action 句：

```text
When enough required information is available, produce a draft.
```

被跨 span 切断了。

### 2.2 Stage 4 / Stage 5 后续结构

`stage4_flow_assembler.json` 中：

```text
main_flow_spans = [s15, s16, s17, s19]
alternative_flows:
  alt_1 condition = "the user asks for revision", spans = [s18]
```

Stage 4 识别了 `If the user asks for revision`，但没有恢复 `When enough required information is available` 与 `produce a draft` 的 guard-action 关系。

`stage5_block_assembler.json` 中：

```text
b_2:
  block_type = IF
  condition_text = "sources are needed and available"
  spans = [s16]

b_3:
  block_type = SEQUENTIAL
  spans = [s17, s19]
```

因此 `produce a draft` 落入普通 sequential block，而 `When enough...` 留在 `s16`。

### 2.3 Stage 7 暴露错误

Stage 7 的 API residual projector 从 `s16` 中扣除 API-covered action：

```text
retrieve them using approved source recipes
```

剩余内容包含：

```text
Maintain provenance for externally sourced facts.
When enough required information is available.
```

当前 projector 对“完整未覆盖句子”的策略是 materialize 为 residual `GENERAL_COMMAND`。因此它生成了两条 residual commands：

```text
COMMAND Maintain provenance for externally sourced facts
COMMAND When enough required information is available
```

第一条是正确 residual command；第二条是 guard fragment 被误物化。

## 3. 根因判断

本问题的首要根因不是 Stage 7，而是 Stage 1 的切分策略破坏了 guard-action 原子性。

当前 canonical path 的 Stage 1 实现位于：

```text
src/nl2spl/pipeline/stages/stage1_span_slicer.py
```

其中 `_execute_canonical()` 的核心策略是：

```python
for packet in canonical_input.semantic_packets:
    spans.append(
        SpanIR(
            span_id=f"s{next_id}",
            text=packet.text,
            source_section_id=packet.source_section_id,
            source_packet_id=packet.packet_id,
        )
    )
```

也就是说：

```text
semantic packet -> exactly one SpanIR
```

它没有在 packet 内做 clause-aware segmentation，也没有检测：

```text
When <condition>, <action>
If <condition>, <action>
Unless <condition>, <action>
As long as <condition>, <action>
```

这类 control-leading sentence 的原子性。

因此，当 input adapter / canonical packet 本身已经把多个句子打包在同一个 packet 中时，Stage 1 不能提供更细的 action/guard 边界；当上游 packet text 或 LLM residual slicing 又把 guard 和 action 切到相邻 spans 时，后续 Stage 4/5 很难可靠恢复。

## 4. 现有切分策略的问题

### 4.1 Canonical path 粒度过粗

当前 canonical path 保留 adapter packet 边界，但不做 packet 内 segmentation。

优点：

```text
- source_section_id / source_packet_id 保真；
- 不跨 adapter packet 合并；
- 简单、稳定、可追溯。
```

缺点：

```text
- 一个 packet 内可能包含多个 executable actions；
- 一个 packet 内可能混合 command / condition / API call / residual action；
- 下游 Stage 4/5/7 被迫在过粗 span 上重新解释局部语义；
- Stage 7 residual projector 容易把 guard fragment 当 command。
```

### 4.2 Generic raw-text path 依赖 LLM residual slicing

非 canonical path 使用 deterministic pre-slicing + LLM residual slicing。该路径要求 LLM 输出 “semantically complete spans”，但没有强制 control-clause atomicity contract。

风险：

```text
- LLM 可能把 condition 和 action 分开；
- 切分结果缺少 guard/action relation metadata；
- Stage 3 split recommendations 只能补救 ambiguity，不能稳定承担所有 control pairing。
```

### 4.3 Stage 2/3 split recommendation 不是根治点

Stage 2 adapter-guided refinement 已存在 `split_recommendations`，Stage 3 ambiguity resolver 也能拆分 ambiguous spans。

但这条路径更适合处理“一个 span 内混合多种 route/semantic role”的场景，不适合作为 Stage 1 基础切分缺陷的唯一修复。

原因：

```text
- Stage 2/3 已经在 Stage 1 之后，span boundary damage 已发生；
- 如果 guard/action 已跨 span 分离，split 机制本身不能表达跨 span guard_applies_to relation；
- 依赖 LLM split recommendations 会让 control-flow 基础边界不稳定。
```

## 5. 目标切分策略

建议将 Stage 1 的 adapter-aware slicing 从：

```text
semantic packet -> SpanIR
```

升级为：

```text
semantic packet
-> sentence / clause-aware segmentation
-> control-clause atomicity repair
-> SpanIR + segmentation metadata
```

### 5.1 第一层：adapter packet provenance boundary + controlled cross-packet repair

Stage 1 应把 adapter packet 视为 source provenance boundary，而不是不可跨越的 segmentation boundary。

规则：

```text
- 默认不做任意跨 source_packet_id 合并；
- 如果 packet 内拆分出 child spans，child spans 必须保留 parent source_packet_id；
- 如果相邻 packets 属于同一 source_section_id、source order 连续，且形成 guard-only + action-like continuation，可以做受控 cross-packet repair；
- 受控 repair 必须满足第 11 节定义的 same-section、source order、guard-only、action-like、control-leading sentence、provenance metadata 六个准入条件；
- repair 结果必须记录 parent_packet_ids、source ranges、continuation_repaired=true；
- 长期应推动 InputAdapter 不再切断 control-leading sentence，但 Stage 1 MVP 不能依赖 adapter 已经完美。
```

### 5.2 第二层：packet 内 sentence segmentation

对 packet text 做基础 sentence segmentation，得到候选句子。

对于 demo，理想候选应是：

```text
If sources are needed and available, retrieve them using approved source recipes.
Maintain provenance for externally sourced facts.
When enough required information is available, produce a draft.
If the user asks for revision, revise while re-checking constraints.
```

### 5.3 第三层：control-leading sentence 保持原子

如果句子以 control introducer 开头：

```text
if
when
unless
once
as long as
provided that
in case
on condition that
```

并且句中存在逗号后的 action，则整个 sentence 必须作为一个 guarded-action span，不能拆成：

```text
guard-only span
action-only span
```

MVP 可以先保持一个 span：

```text
When enough required information is available, produce a draft.
```

后续 Stage 4/5 再提取：

```text
condition_text = enough required information is available
guarded_action = produce a draft
```

长期可以输出更结构化的 metadata：

```text
segmentation_kind = guarded_action
guard_text = enough required information is available
action_text = produce a draft
```

### 5.4 第四层：trailing guard lookahead repair

如果一个 candidate segment 末尾是 guard-only fragment：

```text
When enough required information is available
```

且下一个 segment 以 action-like verb phrase 开始：

```text
produce a draft
```

Stage 1 应将二者合并为：

```text
When enough required information is available, produce a draft.
```

该 repair 必须保留 provenance：

```text
parent source_packet_id(s)
source_section_id
segmentation metadata: continuation_repaired
```

### 5.5 第五层：可审计 segmentation metadata

Stage 1 metadata 只表达文本边界和轻量句法关系，不承担 construct routing、repairability、diagnostic 或 materialization authority。

允许的 segmentation kind 仅限：

```text
segmentation_kind:
  atomic_text_unit
  atomic_action_candidate
  guarded_action
  continuation_repaired
  ambiguous_boundary
```

允许记录的 metadata：

```text
guard_text: optional
action_text: optional
parent_packet_ids
source_section_id
char_start
char_end
boundary_confidence
continuation_repaired
```

禁止 Stage 1 输出或暗示：

```text
construct routing authority
semantic role authority
diagnostic authority
repairability authority
materialization authority
```

短期如果不修改 `SpanIR` schema，应先在 Stage 1 checkpoint 中保存 sidecar：

```text
span_segmentation_records
```

避免 Stage 4/5/7 重新从 raw text 猜测，同时避免 Stage 1 越权成为 semantic routing authority。

## 6. 对 internal_comms 的目标切分

当前错误切分：

```text
s16:
  retrieve them using approved source recipes.
  Maintain provenance for externally sourced facts.
  When enough required information is available

s17:
  produce a draft.
  If the user asks for revision
```

建议目标切分：

```text
s15a:
  First determine what kind of communication is requested.

s15b:
  Then identify which required fields are still missing.

s15c:
  Ask only the highest-value clarifying questions needed to move forward.

s16a:
  If sources are needed and available, retrieve them using approved source recipes.

s16b:
  Maintain provenance for externally sourced facts.

s17a:
  When enough required information is available, produce a draft.

s18a:
  If the user asks for revision, revise while re-checking constraints.

s18b:
  Do not finalize if required slots remain missing unless the draft is explicitly marked as assumption-bearing and the user confirms.

s19a:
  At the end, record unresolved items in an assumptions log and set completion status.
```

MVP 不一定要使用 `s15a` 这种命名；可以继续顺序编号。但语义粒度应接近上述结构。

## 7. Stage 职责边界

### Stage 1

负责：

```text
- 保持 source packet provenance；
- packet 内 clause-aware segmentation；
- 不切断 guard-action unit；
- 输出足够的 segmentation metadata。
```

不负责：

```text
- 生成 FlowIR / BlockIR；
- 判断最终 command_type；
- materialize StepIR。
```

### Stage 4

负责：

```text
- 使用 Stage 1 segmentation metadata 和 span text 识别 flow-level condition；
- 生成 alternative_flows / main_flow relation；
- 对 guard-action span 建立 source-backed control relation。
```

不负责：

```text
- 修复任意错误切分；
- 从 rendered SPL 或 StepIR 反推 condition。
```

### Stage 5

负责：

```text
- 将 Stage 4 flow relation 转换为 IF / WHILE / FOR blocks；
- 保证 guarded action 位于对应 block 中。
```

不负责：

```text
- 从 unrelated spans 自行猜 guard-action pairing。
```

### Stage 7

负责：

```text
- 将 action/block-owned content materialize 为 StepIR；
- 对明显 guard-only residual fail closed。
```

不负责：

```text
- 完整识别 condition；
- 构造 IF block；
- 修复 Stage 1/4/5 的 control-flow 结构错误。
```

Stage 7 的防御规则应很窄：

```text
如果 residual sentence 以 if/when/unless/as long as/provided that 等开头，
且没有明确 action body，
不得 materialize 为 GENERAL_COMMAND；
emit diagnostic，例如 stage7_guard_residual_not_materialized。
```

## 8. 迁移建议（已由第 12 节取代）

本节早期版本的 Phase A-E 已被第 12 节取代，不再作为正式实施计划输入。正式 implementation planning 必须以第 12 节为准：

```text
A0: Adapter / Stage 1 boundary characterization
B: Stage 1 deterministic segmentation + controlled cross-packet repair
C: Stage 1 sidecar first
D: Stage 4 / Stage 5 guarded-action contract
E: Stage 7 residual guard fail-closed
```

最终验收条件必须锁定：

```text
1. Stage 1 不再产生 guard-only tail span: "When enough required information is available"。
2. Stage 1 输出 guarded_action sidecar，包含 guard_text/action_text/parent_packet_ids/char ranges。
3. Stage 5 对 guarded_action 生成 IF block，或发出 diagnostic；不能静默降级为 SEQUENTIAL。
4. Stage 7 无论如何不得再渲染 COMMAND When enough required information is available。
```

## 9. 非目标

本设计不要求：

```text
- Stage 7 成为 condition recognizer；
- Renderer/Gate/SPL Editing 修复 control-flow；
- 用 LLM 做任意 semantic segmentation；
- 在 Stage 1 中生成 BlockIR / StepIR；
- 全量重写 Stage 4/5。
```

## 10. 结论

当前 `COMMAND When enough required information is available` 的根因是 Stage 1 span slicing 破坏了 guard-action 原子性。Stage 7 只是最后把这个结构错误暴露为用户可见 command。

正确修复方向应是：

```text
Stage 1: clause-aware segmentation + guard-action atomicity
Stage 4/5: consume source-backed guard relation and build control blocks
Stage 7: fail-closed, never materialize guard-only residual as command
```

这能保持 pipeline 分层清晰：Stage 1 负责可追溯语义边界，Stage 4/5 负责 control-flow，Stage 7 负责 command materialization。

## 11. 评审修订：从 conditional pass 到可实施边界

后续评审指出：本文档的问题判断和总体方向成立，但原方案中仍有三个会影响落地的关键缺口。修订后的判断是：

```text
Problem diagnosis: pass
Original repair design: conditional pass
Implementation readiness: blocked until the amendments below are included
```

### 11.1 必须支持受控 cross-packet repair

原文档中写到：

```text
默认不跨 source_packet_id 合并；
只有 adapter 明确标记 continuation 时才允许跨 packet repair。
```

这个原则对 provenance 很谨慎，但无法修复当前 demo 的真实错误。当前错误不是单纯 “packet 内多句未拆”，而是 canonical semantic packets 已经把完整句子从中间撕开：

```text
s15 tail: If sources are needed and available
s16 head: retrieve them using approved source recipes

s16 tail: When enough required information is available
s17 head: produce a draft
```

因此，仅做 packet-internal segmentation 最多能得到：

```text
retrieve them using approved source recipes.
Maintain provenance for externally sourced facts.
When enough required information is available
```

它仍然无法把 `When enough...` 和下一个 packet 的 `produce a draft` 重新组成 guarded action。

修订后的 Stage 1 MVP 规则应为：

```text
默认不做任意跨 packet 合并；
但允许受控 cross-packet repair。
```

允许条件必须全部满足：

```text
1. 相邻 fragments 属于同一个 source_section_id；
2. 在原始 source order 中连续；
3. 前一个 fragment 是 guard-only fragment；
4. 后一个 fragment 以 action-like phrase 开始；
5. 合并后形成 control-leading sentence：
   if/when/unless/once/as long as/provided that/in case + condition + action；
6. repair 结果记录 parent_packet_ids、source ranges、continuation_repaired=true。
```

长期更理想的修复是 Stage 0 / InputAdapter cleanup：adapter 生成 canonical packets 时不要切断 control-leading sentence，并写入 `continuation_group_id` 与 source char ranges。但当前 MVP 不能等待 adapter 全量重构，Stage 1 需要具备上述受控 repair 能力。

### 11.2 Stage 5 必须显式消费 guarded-action contract

即使 Stage 1 正确输出：

```text
When enough required information is available, produce a draft.
```

也不自动保证最终 SPL 会生成：

```text
IF enough required information is available
  COMMAND Produce a draft
END_IF
```

当前 Stage 5 prompt / policy 可能把 “when enough information is ready, proceed” 视为 normal sequential precondition，而不是 IF block。这会与本文目标结构冲突。

因此 Phase D 必须从“Stage 4/5 consume metadata”收紧为明确 contract：

```text
If Stage 1 segmentation metadata marks a span as guarded_action,
Stage 5 must create a local IF block,
unless Stage 4/5 explicitly classifies the guard as non-control precondition
and emits an auditable diagnostic.
```

最低验收：

```text
Input span:
  When enough required information is available, produce a draft.

Stage 5 output:
  block_type = IF
  condition_text = "enough required information is available"
  spans include the guarded action span
```

如果实现选择“不生成 IF，而视为 normal precondition”，必须输出结构化 diagnostic，例如：

```text
guarded_action_classified_as_non_control_precondition
blocks_rendering=false
blocks_completion=true
```

禁止静默降级为 SEQUENTIAL。

### 11.3 Stage 1 metadata 只能表达边界和轻量句法关系

原文档建议的 `segmentation_kind` 包含：

```text
atomic_action
guarded_action
declaration
constraint
failure_condition
continuation_repaired
ambiguous
```

这需要收窄。Stage 1 不应成为 semantic router，也不应提前决定 `declaration / constraint / failure_condition` 等语义角色。这些属于 Stage 2 RouteAnnotation、ConstructPlan 或后续 IRS 的 authority。

修订后的 Stage 1 metadata 范围：

```text
segmentation_kind:
  atomic_text_unit
  atomic_action_candidate
  guarded_action
  continuation_repaired
  ambiguous_boundary
```

允许记录：

```text
guard_text
action_text
parent_packet_ids
source_section_id
source ranges
char_start / char_end
continuation_repaired
boundary_confidence
```

禁止记录或作为 authority 使用：

```text
construct_type
semantic_role
failure_condition
exception_handler
api_call
constraint
repairability
```

Stage 1 只负责文本边界与轻量句法关系；Stage 2/3/ConstructPlan 再决定语义角色。

### 11.4 Stage 7 fail-closed 仍是必要保底，但不是主修复

Stage 7 仍应增加窄防线：

```text
if residual starts with if/when/unless/once/as long as/provided that
and no action body is present:
    do not create GENERAL_COMMAND
    emit stage7_guard_residual_not_materialized
```

建议 diagnostic：

```text
kind = stage7_guard_residual_not_materialized
severity = warning
blocks_rendering = false
blocks_completion = true
```

该 diagnostic 表示上游 control boundary 仍有缺口。它不能替代 Stage 1 cross-packet repair 或 Stage 5 guarded-action block construction。

## 12. 修订后的落地阶段

### Phase A0：Adapter / Stage 1 boundary characterization

锁定当前真实错误形态：

```text
s15 ends with "If sources are needed and available"
s16 starts with "retrieve them..."
s16 ends with "When enough required information is available"
s17 starts with "produce a draft."
```

目标断言：

```text
Stage 1 final spans no longer contain guard-only tail fragments.
```

### Phase B：Stage 1 deterministic segmentation + controlled cross-packet repair

实现：

```text
1. 在 raw section 内按 source order 重建可切分文本；
2. sentence segmentation；
3. control-leading sentence atomicity；
4. same-section adjacent source order 下的 guard-only + action-like cross-packet repair；
5. 输出 child SpanIR 或 span group；
6. 输出 parent_packet_ids / char ranges / continuation_repaired sidecar。
```

关键验收：

```text
When enough required information is available, produce a draft.
```

必须成为一个 span，或成为一个 span group，且带有：

```json
{
  "segmentation_kind": "guarded_action",
  "guard_text": "enough required information is available",
  "action_text": "produce a draft",
  "parent_packet_ids": ["...", "..."],
  "continuation_repaired": true
}
```

### Phase C：Stage 1 sidecar first

短期不强制修改 `SpanIR` dataclass。优先输出：

```text
stage1_segmentation_records
span_segmentation_records
```

避免一次性修改所有 serializer、prompt consumer 和 snapshot model。

### Phase D：Stage 4 / Stage 5 guarded-action contract

Stage 4：

```text
guarded_action span stays in main_flow;
does not become alternative_flow unless guard is a user-choice path;
does not become exception_flow unless Stage 2/ConstructPlan classifies it as failure/recovery condition.
```

Stage 5：

```text
guarded_action metadata => local IF block
condition_text = guard_text
spans = [guarded_action_span_id]
```

同时必须修改或覆盖现有 prompt/policy 中把 “when enough information is ready, proceed” 默认视为 SEQUENTIAL 的规则。

### Phase E：Stage 7 residual guard fail-closed

即使 Stage 1/4/5 回归，也不得再次渲染：

```text
COMMAND When enough required information is available
```

Stage 7 只能拒绝 guard-only residual 并发 diagnostic，不得自行构造 IF block。
