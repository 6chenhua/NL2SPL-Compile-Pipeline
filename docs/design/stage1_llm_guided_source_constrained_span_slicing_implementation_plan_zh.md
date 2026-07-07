# Stage 1 LLM-Guided Source-Constrained Span Slicing 实施计划

本文档严格基于 `docs/design/stage1_llm_guided_source_constrained_span_slicing_design_zh.md` 制定。实施目标是为 Stage 1 引入受 source / validator 约束的 LLM semantic span slicing，并闭合 Stage 5 guarded-action consumption 与 Stage 7 guard-only residual fail-closed，修复 `internal_comms` 中 guard/action 被切断后渲染成错误 command 的问题。

适用范围：

```text
in scope:
  Stage 1 source reconstruction / LLM segmentation / deterministic validation / sidecar
  Stage 4 metadata pass-through
  Stage 5 guarded_action -> IF block consumer
  Stage 7 independent guard-only residual fail-closed
  feature-flag rollout: shadow -> selected fixtures -> production default readiness
  internal_comms E2E regression

out of scope:
  Stage 1 直接生成 FlowIR / BlockIR / StepIR
  Stage 1 判定 API_CALL / EXCEPTION_FLOW / CONSTRAINT / repair target
  Renderer / Gate / SPL Editing 修复 control-flow
  纯 rule-based semantic parser
  一次性全量替换所有 compile runs 的默认 Stage 1 行为
  production LLM default rollout without gate evidence
```

---

## 1. 总体目标

最终系统应形成以下职责链路：

```text
CanonicalCompileInput.semantic_packets
  -> SourceSectionReconstructor
  -> SectionSourceBuffer + SourceNormalizationMap

LLMSourceConstrainedSegmenter
  -> LLMSpanSegment proposal
  -> only semantic boundary proposal, no construct authority

Stage1SegmentationValidator
  -> authoritative source range / packet lineage / coverage validation
  -> rejects paraphrase, overlap, cross-section merge, fabricated packet ids

SpanSlicer
  -> SpanIR
  -> stage1_segmentation_records / span_segmentation_records sidecar

FlowAssembler
  -> pass-through segmentation metadata
  -> does not construct IF blocks

BlockAssembler
  -> consumes guarded_action
  -> creates local IF block or emits diagnostic

StepExtractor
  -> independent guard-only residual fail-closed
  -> refuses GENERAL_COMMAND for guard-only residual
```

Release strategy:

```text
R1: legacy_packet_passthrough + llm_source_constrained_shadow
    shadow payload only, no final SPL behavior change

R2: llm_source_constrained for selected regression fixtures
    Stage 1 sidecar + Stage 5 consumer + Stage 7 fail-closed closed loop

R3: llm_source_constrained production-default readiness
    only after exit criteria and PM approval
```

---

## 2. 全局硬性原则

所有阶段必须遵守：

1. LLM 只提出 semantic span boundaries，不拥有 source truth、construct authority、repair authority 或 materialization authority。
2. `segment_text_exact` 必须是 normalized source buffer 的 exact substring；不得 paraphrase、summarize、rewrite 或自动补 punctuation。
3. Validator 是 Stage 1 LLM segmentation 的 P0 correctness authority。未通过 validator 的 LLM output 不能 materialize 为 `SpanIR` 或 sidecar。
4. `SpanIR` 短期保持兼容；跨 packet provenance 必须进入 `SpanSegmentationRecord.parent_packet_ids / char_start / char_end`。
5. Stage 1 metadata 只能表达 text boundary / light syntactic relation：`atomic_text_unit`、`atomic_action_candidate`、`guarded_action`、`continuation_repaired`、`ambiguous_boundary`。
6. Stage 1 禁止输出或暗示 `construct_type`、`semantic_role`、`failure_condition`、`exception_handler`、`api_call`、`constraint`、`repairability`、`IF_BLOCK`、`COMMAND`。
7. Stage 4 只透传 segmentation metadata，不构造 IF block，不重新配对 guard/action。
8. Stage 5 对 `guarded_action` 必须创建 local IF block，或发出 visible diagnostic；禁止静默降级为 SEQUENTIAL。
9. Stage 7 guard-only residual detection 是独立 fail-closed 保险，不依赖 sidecar 中存在完整 `guarded_action`。
10. Fallback 不允许恢复旧错误；即使 LLM segmentation 失败，final SPL 也不得包含 `COMMAND When enough required information is available`。
11. `llm_source_constrained` 不得在首个实现阶段成为无条件 production default。
12. 所有 diagnostics 必须进入 checkpoint / compile diagnostics / debug report 可审计路径，不得只写 debug log。
13. 所有阶段不得新增 skip / xfail 来掩盖目标行为。

---

## 3. LLM / Rule-Based 决策约束

本计划允许新增 LLM prompt/schema，但只限 Stage 1 source-constrained segmentation。

允许的确定性逻辑仅限：

```text
- source buffer reconstruction
- whitespace / soft line break normalization
- exact substring location
- range / coverage / overlap validation
- parent_packet_ids authoritative recomputation
- retry error construction
- checkpoint payload serialization
- Stage 7 guard-only residual refusal
```

禁止新增 rule-based semantic parser：

```text
- 用动词白名单决定 guarded_action
- 用 keyword fallback 生成 IF block
- 用 Stage 7 pattern 构造 control-flow
- 用 Renderer/Gate/SPL Editing 去重或修复 Stage 1 boundary
```

Prompt/schema 改动必须满足：

```text
- output JSON only
- exact-copy fields:
    segment_text_exact
    guard_text_exact
    action_text_exact
    source_packet_ids
- guard_text_exact excludes introducer keyword
- no SPL construct labels
- ambiguous_boundary is an explicit allowed escape path
```

---

## 4. Phase A0：Characterization Baseline

### 4.1 目标

只加测试和证据，不改变生产代码。锁定当前缺陷链路：

```text
s16 tail = When enough required information is available
s17 head = produce a draft
Stage 7 can render guard-only command
```

### 4.2 可编辑范围

允许新增：

```text
tests/integration/pipeline/test_stage1_llm_segmentation_characterization.py
tests/unit/pipeline/stage1/test_stage1_current_boundary_characterization.py
artifacts/reviews/stage1_llm_segmentation/A0/
```

允许读取/引用：

```text
examples/input/internal_comms.txt
examples/output/demo/stage1_span_slicer.json
examples/output/demo/final_spl.txt
```

### 4.3 禁止改动

Phase A0 禁止修改：

```text
src/
examples/input/
examples/output/demo/
```

### 4.4 设计要求

Characterization tests 应区分：

```text
current-behavior lock:
  当前 artifacts 确实存在 guard/action 被切断或 guard-only residual 风险

target-behavior expectation helper:
  记录目标切分，但不以 test_*.py 形式进入 A0 默认 pytest
  可放入 helper module / golden json / review artifact
  不使用 skip / xfail 表达未来目标
```

### 4.5 测试计划

新增测试必须覆盖：

1. `internal_comms` 中 `When enough required information is available` 与 `produce a draft` 属于同一 source section 且 source order 连续。
2. 当前 Stage 1 checkpoint 可复现 guard/action 分离。
3. 当前 final SPL 或 Stage 7 action path 可复现 guard-only command 风险。
4. 目标 helper 表达 expected guarded-action segmentation，但不得被 pytest 自动收集为失败测试。

### 4.6 验收标准

Phase A0 通过条件：

1. 测试只锁定当前行为，不修改生产行为。
2. 无新增 skip / xfail。
3. target-behavior helper 不进入默认 pytest collection。
4. Review artifact 保存 current behavior 摘要。
5. `pytest` 定向测试通过。

### 4.7 PM 审核清单

审核时必须检查：

1. 是否只新增 characterization 和 artifact。
2. 是否没有通过修改 demo fixture 让问题消失。
3. 是否没有把 target behavior 断言放进默认失败测试。
4. 是否没有用 skip / xfail 掩盖未来目标。

---

## 5. Phase A1：Source Reconstruction and Config Substrate

### 5.1 目标

实现 Stage 1 source reconstruction 和 feature flag substrate，但默认仍为 `legacy_packet_passthrough`，不改变 final SPL。

### 5.2 可编辑范围

允许新增：

```text
src/nl2spl/pipeline/stages/stage1_segmentation/
  __init__.py
  config.py
  source_buffer.py
  segmentation_payload.py

tests/unit/pipeline/stage1/
  test_source_buffer.py
  test_stage1_segmentation_config.py
```

允许修改：

```text
src/nl2spl/pipeline/stages/stage1_span_slicer.py
src/nl2spl/pipeline/orchestrator.py
```

### 5.3 禁止改动

Phase A1 禁止修改：

```text
src/nl2spl/pipeline/stages/stage4_flow_assembler/
src/nl2spl/pipeline/stages/stage5_block_assembler/
src/nl2spl/pipeline/stages/stage7_step_extractor/
src/nl2spl/pipeline/stages/stage11_spl_renderer/
```

### 5.4 设计要求

新增 config：

```python
Stage1SegmentationConfig.mode:
  legacy_packet_passthrough
  llm_source_constrained_shadow
  llm_source_constrained
  deterministic_fallback_only
```

默认必须是：

```text
legacy_packet_passthrough
```

`SourceSectionReconstructor` 必须输出：

```text
SectionSourceBuffer.normalized_text
SourcePacketRange[]
SourceNormalizationMap
```

Normalization policy：

```text
- soft line break -> space
- packet boundary -> space or existing source punctuation
- no auto comma insertion
- no substantive text deletion
- no cross-section merge
```

模块边界：

```text
本计划不创建 `src/nl2spl/pipeline/stages/stage1_span_slicer/` 同名 package。
现有 `stage1_span_slicer.py` 继续作为 public import surface。
新增实现放入 `stage1_segmentation/` support package，由 `stage1_span_slicer.py` 组合调用。
除非单独批准模块迁移 PR，否则不得删除 `stage1_span_slicer.py`。
```

### 5.5 测试计划

新增测试必须覆盖：

1. soft line break normalized to space, not comma。
2. packet boundary does not invent punctuation。
3. blank line / bullet / numbered list boundary preserved。
4. packet range map can recover parent packet ids。
5. cross-section merge rejected。
6. default config remains `legacy_packet_passthrough`。

### 5.6 验收标准

Phase A1 通过条件：

1. 默认 compile output 不变。
2. Source buffer payload 可 deterministic serialize。
3. No LLM call introduced。
4. 定向 unit tests 通过。

### 5.7 PM 审核清单

审核时必须检查：

1. 是否没有把 `llm_source_constrained` 设成默认。
2. 是否没有在 reconstruction 中做 semantic classification。
3. 是否没有自动插入 comma / punctuation。
4. 是否没有创建 `stage1_span_slicer/` 同名 package 与 `stage1_span_slicer.py` 冲突。

---

## 6. Phase B：Prompt, Schema, Parser, and Shadow Proposal

### 6.1 目标

实现 LLM source-constrained segmentation prompt/schema/parser，并在 shadow mode 下产生 raw proposal；不改变 `SpanIR` 和 final SPL。

### 6.2 可编辑范围

允许新增：

```text
src/nl2spl/pipeline/stages/stage1_segmentation/
  llm_segment_parser.py
  llm_segmenter.py

prompts/
  stage1_source_constrained_segmentation_system.txt
  stage1_source_constrained_segmentation_user_template.txt

tests/unit/pipeline/stage1/
  test_llm_segment_parser.py
  test_stage1_segmentation_prompt_contract.py
```

允许修改：

```text
src/nl2spl/pipeline/stages/stage1_span_slicer.py
```

### 6.3 禁止改动

Phase B 禁止修改：

```text
src/nl2spl/pipeline/stages/stage4_flow_assembler/
src/nl2spl/pipeline/stages/stage5_block_assembler/
src/nl2spl/pipeline/stages/stage7_step_extractor/
```

### 6.4 设计要求

LLM raw schema：

```text
segment_text_exact
segmentation_kind
guard_text_exact
action_text_exact
source_packet_ids
source_section_id
char_start / char_end as optional hint
boundary_confidence
continuation_repaired
```

Prompt 必须包含：

```text
- exact-copy instruction
- no paraphrase / no summarization / no rewrite
- no SPL construct classification
- guard_text excludes introducer keyword
- ambiguous_boundary escape path
- same-packet multiple independent guarded_action example
```

### 6.5 测试计划

新增测试必须覆盖：

1. parser accepts valid exact-copy JSON。
2. parser rejects missing `segment_text_exact`。
3. parser rejects unknown segmentation kind。
4. prompt snapshot includes exact-copy rules。
5. prompt snapshot includes same-packet multiple guarded_action few-shot。
6. prompt snapshot forbids `IF_BLOCK / COMMAND / API_CALL` labels。

### 6.6 验收标准

Phase B 通过条件：

1. shadow mode 能产生 raw LLM proposal 或 fake-client proposal。
2. raw proposal 不进入 `SpanIR`。
3. 未实现 validator 前，不允许 production materialization。
4. No final SPL behavior change。

### 6.7 PM 审核清单

审核时必须检查：

1. 是否出现旧字段 `text / guard_text / action_text` 作为 LLM authority。
2. 是否 prompt 允许 paraphrase。
3. 是否 parser 把 invalid JSON 静默当成 legacy success。

---

## 7. Phase C：Deterministic Validator and Diagnostics

### 7.1 目标

实现 validator，确立它作为 P0 correctness authority。LLM output 只有通过 validator 后才能生成 validated records。

### 7.2 可编辑范围

允许新增：

```text
src/nl2spl/pipeline/stages/stage1_segmentation/
  segmentation_validator.py
  diagnostics.py

tests/unit/pipeline/stage1/
  test_segmentation_validator.py
  test_segmentation_validator_parent_packets.py
```

允许修改：

```text
src/nl2spl/pipeline/stages/stage1_segmentation/segmentation_payload.py
```

### 7.3 禁止改动

Phase C 禁止修改：

```text
src/nl2spl/pipeline/stages/stage4_flow_assembler/
src/nl2spl/pipeline/stages/stage5_block_assembler/
src/nl2spl/pipeline/stages/stage7_step_extractor/
```

### 7.4 设计要求

Validator 必须拒绝：

```text
paraphrase
uncovered substantive source text
overlap
out-of-order segments
cross-section merge
fabricated source_packet_ids
guarded_action missing guard_text_exact/action_text_exact
guard/action exact text not substring of segment exact text
invalid segmentation kind
ambiguous duplicate range without resolvable evidence
```

Validator 可修正：

```text
char_start / char_end hint
source_packet_ids ordering
parent_packet_ids authoritative recomputation
whitespace-equivalent offset drift
```

必须 reject：

```text
LLM packet ids completely disjoint from authoritative range
packet id mismatch beyond adjacent packet repair tolerance
```

### 7.5 测试计划

新增测试必须覆盖：

1. exact text accepted。
2. paraphrase rejected。
3. source punctuation invented by LLM rejected。
4. overlap rejected。
5. cross-section merge rejected。
6. fabricated packet ids rejected。
7. omitted adjacent packet ids repaired and marked `repaired_by_validator`。
8. disjoint packet ids rejected。
9. missing guard/action exact text rejected。
10. duplicate text ambiguous range diagnostic emitted。

### 7.6 验收标准

Phase C 通过条件：

1. Validator produces deterministic `SpanSegmentationRecord` payload。
2. Diagnostics use declared kinds。
3. Invalid LLM output never materializes。
4. Unit tests pass with no skip / xfail。

### 7.7 PM 审核清单

审核时必须检查：

1. 是否 validator 修正了 semantic boundary（禁止）。
2. 是否 validator 为了匹配 LLM packet ids 移动 range（禁止）。
3. 是否 diagnostics 只存在于 local exception message（禁止）。

---

## 8. Phase D：Shadow Sidecar Materialization and Observability

### 8.1 目标

在 `llm_source_constrained_shadow` 下保存 validated shadow payload、comparison report 和 diagnostics；不改变 final SPL。

### 8.2 可编辑范围

允许新增：

```text
src/nl2spl/pipeline/stages/stage1_segmentation/
  shadow_report.py

tests/integration/pipeline/
  test_stage1_shadow_segmentation_payload.py
```

允许修改：

```text
src/nl2spl/pipeline/stages/stage1_span_slicer.py
src/nl2spl/pipeline/orchestrator.py
```

### 8.3 禁止改动

Phase D 禁止修改：

```text
src/nl2spl/pipeline/stages/stage4_flow_assembler/
src/nl2spl/pipeline/stages/stage5_block_assembler/
src/nl2spl/pipeline/stages/stage7_step_extractor/
```

### 8.4 设计要求

Shadow checkpoint keys：

```text
stage1_shadow_segmentation_records
stage1_shadow_segmentation_payload
stage1_shadow_segmentation_report
stage1_shadow_source_buffers
```

Shadow report 必须包含：

```text
legacy_span_count
shadow_span_count
validator_failure_count
fallback_count
coverage_gap_count
cross_section_merge_error_count
internal_comms_guarded_action_match
```

R1 -> R2 exit criteria：

```text
shadow validator failure rate < 5%
shadow fallback rate < 5%
shadow segment coverage gap vs legacy < 2%
zero cross-section merge errors
internal_comms shadow output matches expected guarded_action segmentation
shadow comparison report reproducible in CI/review artifact
```

### 8.5 测试计划

新增测试必须覆盖：

1. shadow mode does not replace `stage1_spans`。
2. shadow payload is checkpointed。
3. shadow report includes exit criteria fields。
4. invalid shadow LLM output emits diagnostics but final SPL path remains legacy。

### 8.6 验收标准

Phase D 通过条件：

1. Legacy default output unchanged。
2. Shadow payload and report deterministic。
3. Review artifact includes shadow report for `internal_comms`。
4. No Stage 5 / Stage 7 behavioral dependency yet。

### 8.7 PM 审核清单

审核时必须检查：

1. 是否 shadow payload accidentally changes final SPL。
2. 是否 report metrics can be recomputed。
3. 是否 implementation claims R2 readiness without exit evidence。

---

## 9. Decision Gate R1：Shadow Exit Approval

### 9.1 目标

确认可从 shadow-only 进入 selected-fixture activation。

### 9.2 必须提供的证据

```text
artifacts/reviews/stage1_llm_segmentation/R1_shadow/
  review_report.md
  commands.log
  pytest_output.txt
  shadow_report_internal_comms.json
  shadow_segmentation_payload_internal_comms.json
  manifest.json
```

### 9.3 验收标准

R1 gate 通过条件：

1. A0-D 全部通过。
2. R1 exit criteria 全部满足，或 PM 明确批准例外。
3. No final SPL behavior change。
4. PM 明确批准后方可进入 Phase E/G。

说明：

```text
Phase F 的 Stage 7 fail-closed 不依赖 shadow exit criteria，可在 A0 之后并行实施。
但 Phase F 必须在 R2 selected fixture release 前通过。
```

---

## 10. Phase E：Stage 4 Pass-Through and Stage 5 Guarded-Action Consumer

### 10.1 目标

接入 validated sidecar 到 Stage 4/5。Stage 5 对 `guarded_action` 创建 local IF block，或显式 diagnostic；不得静默 SEQUENTIAL。

### 10.2 可编辑范围

允许新增：

```text
src/nl2spl/pipeline/stages/stage5_block_assembler/guarded_action.py

tests/unit/pipeline/stage4_stage5/
  test_guarded_action_pass_through.py
  test_stage5_guarded_action_blocks.py
```

允许修改：

```text
src/nl2spl/pipeline/orchestrator.py
src/nl2spl/pipeline/stages/stage4_flow_assembler/executor.py
src/nl2spl/pipeline/stages/stage4_flow_assembler/assembler.py
src/nl2spl/pipeline/stages/stage5_block_assembler/executor.py
src/nl2spl/pipeline/stages/stage5_block_assembler/assembler.py
```

### 10.3 禁止改动

Phase E 禁止修改：

```text
src/nl2spl/pipeline/stages/stage11_spl_renderer/
src/nl2spl/compiler/spl_editing/
```

### 10.4 设计要求

Stage 4：

```text
guarded_action stays in main_flow by default
ambiguous_boundary metadata is preserved
no alternative_flow / exception_flow promotion from segmentation metadata alone
```

Stage 5：

```text
if segmentation_kind == guarded_action:
  create IF block
  condition_text = guard_text / guard_text_exact normalized by validator
  span_ids includes span_id

if segmentation_kind == ambiguous_boundary:
  do not create IF block
  do not silently place guard-only text into executable SEQUENTIAL
  emit stage1_guard_action_boundary_ambiguous when control-leading
```

### 10.5 测试计划

新增测试必须覆盖：

1. `guarded_action` becomes IF block。
2. `guard_text_exact` excludes introducer keyword in condition text。
3. action span remains inside IF block。
4. Stage 5 cannot silently place guarded_action into SEQUENTIAL。
5. `ambiguous_boundary` control-leading span emits diagnostic and is not executable。
6. Stage 4 does not convert guarded_action into alternative/exception flow by itself。

### 10.6 验收标准

Phase E 通过条件：

1. Stage 5 local IF block appears in checkpoint for fixture sidecar。
2. Diagnostic path exists for non-control-precondition case。
3. No Renderer/Gate/SPL Editing changes。
4. Unit and integration tests pass。

### 10.7 PM 审核清单

审核时必须检查：

1. 是否 Stage 5 uses sidecar, not raw text pattern matching。
2. 是否 ambiguous_boundary 被错误渲染为 command。
3. 是否 Stage 4 越权 classification。

---

## 11. Phase F：Stage 7 Independent Guard-Only Residual Fail-Closed

### 11.1 目标

实现 Stage 7 独立 guard-only residual filter。即使 Stage 1 LLM segmentation fallback 或 sidecar 为空，也不得把 guard-only residual materialize 为 `GENERAL_COMMAND`。

### 11.2 可编辑范围

允许新增：

```text
src/nl2spl/pipeline/stages/stage7_step_extractor/guard_residual.py

tests/unit/pipeline/stage7/
  test_guard_only_residual_fail_closed.py
```

允许修改：

```text
src/nl2spl/pipeline/stages/stage7_step_extractor/action_projection.py
src/nl2spl/pipeline/stages/stage7_step_extractor/api_call_materializer.py
src/nl2spl/pipeline/stages/stage7_step_extractor/extractor.py
src/nl2spl/pipeline/stages/stage7_step_extractor/worker_scoped.py
```

### 11.3 禁止改动

Phase F 禁止修改：

```text
src/nl2spl/pipeline/stages/stage11_spl_renderer/
src/nl2spl/pipeline/stages/stage5_block_assembler/
src/nl2spl/compiler/spl_editing/
```

### 11.4 设计要求

Guard-only detection rule：

```text
residual sentence starts with:
  if / when / unless / once / as long as / provided that / in case / on condition that
AND no action body after comma / clause boundary
```

Stage 7 must only:

```text
refuse GENERAL_COMMAND
emit stage7_guard_residual_not_materialized
```

Stage 7 must not:

```text
construct IF block
invent action body
classify construct type
```

### 11.5 测试计划

新增测试必须覆盖：

1. `When enough required information is available` is not materialized。
2. Diagnostic emitted。
3. `When enough information is available, produce a draft` is not treated as guard-only residual if action body exists。
4. Sidecar absent still triggers fail-closed。
5. Non-guard residual command remains materializable。

### 11.6 验收标准

Phase F 通过条件：

1. Guard-only residual cannot become `GENERAL_COMMAND`。
2. Diagnostic visible in stage diagnostics。
3. Existing Stage 7 API residual behavior does not regress。

### 11.7 PM 审核清单

审核时必须检查：

1. 是否 Stage 7 attempted to create IF block（禁止）。
2. 是否 guard-only detection depends on sidecar guarded_action（禁止）。
3. 是否 unrelated residual commands are incorrectly suppressed。

---

## 12. Phase G：Selected Fixture Activation for internal_comms

### 12.1 目标

在 selected fixture / gated mode 下启用 `llm_source_constrained`，闭合 Stage 1 -> Stage 5 -> Stage 7 E2E。

### 12.2 可编辑范围

允许新增：

```text
tests/integration/pipeline/test_stage1_llm_internal_comms_e2e.py
artifacts/reviews/stage1_llm_segmentation/R2_internal_comms/
```

允许修改：

```text
src/nl2spl/pipeline/stages/stage1_span_slicer.py
src/nl2spl/pipeline/orchestrator.py
examples/usage.py  # only if needed for explicit gated demo run option
```

### 12.3 禁止改动

Phase G 禁止修改：

```text
examples/input/internal_comms.txt
src/nl2spl/pipeline/stages/stage11_spl_renderer/
src/nl2spl/compiler/spl_editing/
```

### 12.4 设计要求

Selected fixture activation 必须：

```text
use llm_source_constrained only under explicit config/test fixture
save stage1_segmentation_records
save stage1_source_buffers
save Stage 5 IF block checkpoint
save Stage 7 diagnostics / absence of guard-only command
```

### 12.5 测试计划

E2E 必须覆盖：

1. Stage 1 no longer emits guard-only tail span。
2. Stage 1 emits guarded_action record with:
   - `segment_text_exact` / `span_text`
   - `guard_text_exact` excludes `when`
   - `action_text_exact = produce a draft`
   - `parent_packet_ids`
   - `char_start / char_end`
   - `continuation_repaired = true`
3. Stage 5 creates IF block。
4. Final SPL does not contain `COMMAND When enough required information is available`。
5. Fallback-invalid fixture emits diagnostic and still avoids guard-only command。

### 12.6 验收标准

Phase G 通过条件：

1. `internal_comms` selected fixture E2E passes。
2. Review artifact includes before/after final SPL and checkpoints。
3. No default production mode switch。
4. No demo fixture mutation。

### 12.7 PM 审核清单

审核时必须检查：

1. 是否 selected fixture activation accidentally changes all runs。
2. 是否 final SPL correctness is due to Renderer/Gate suppression。
3. 是否 Stage 5 IF block is source-backed by sidecar。

---

## 13. Decision Gate R2：Selected Fixture Release Approval

### 13.1 目标

确认 selected fixture 模式可合入，且不影响默认 legacy path。

### 13.2 必须提供的证据

```text
artifacts/reviews/stage1_llm_segmentation/R2_internal_comms/
  review_report.md
  commands.log
  pytest_output.txt
  ruff_output.txt
  before_final_spl.txt
  after_final_spl.txt
  stage1_segmentation_payload.json
  stage5_blocks.json
  stage7_guard_diagnostics.json
  manifest.json
```

### 13.3 验收标准

R2 gate 通过条件：

1. A0-G 全部通过。
2. internal_comms E2E golden 通过。
3. Legacy default mode regression 通过。
4. No Renderer/Gate/SPL Editing workaround。
5. PM 明确批准后，才可规划 R3 production-default readiness。

---

## 14. Phase H：Production-Default Readiness Instrumentation

### 14.1 目标

准备 R3 readiness，不直接切换 production default。补齐统计、report、failure dashboard 和 regression matrix。

### 14.2 可编辑范围

允许新增：

```text
src/nl2spl/pipeline/stages/stage1_segmentation/readiness_report.py
tests/integration/pipeline/test_stage1_llm_readiness_report.py
artifacts/reviews/stage1_llm_segmentation/R3_readiness/
```

允许修改：

```text
src/nl2spl/pipeline/orchestrator.py
```

### 14.3 禁止改动

Phase H 禁止修改：

```text
default Stage1SegmentationConfig.mode
src/nl2spl/pipeline/stages/stage11_spl_renderer/
src/nl2spl/compiler/spl_editing/
```

### 14.4 设计要求

Readiness report 必须包含：

```text
validator failure rate
fallback rate
coverage gap rate
cross-section merge error count
guarded_action IF success rate
stage7 guard-only refusal count
E2E regression status
```

### 14.5 测试计划

新增测试必须覆盖：

1. report aggregates multiple compile runs。
2. failures are counted deterministically。
3. R3 readiness remains false if thresholds are not met。
4. default mode remains legacy。

### 14.6 验收标准

Phase H 通过条件：

1. Readiness report deterministic。
2. Default production mode unchanged。
3. R3 gate evidence can be generated。

### 14.7 PM 审核清单

审核时必须检查：

1. 是否偷偷切换 default。
2. 是否 readiness thresholds 可复验。
3. 是否 report excludes failed/invalid runs incorrectly。

---

## 15. Decision Gate R3：Production Default Switch

### 15.1 目标

决定是否将 `llm_source_constrained` 设为 production default。

### 15.2 必须明确的问题

R3 决策文档必须回答：

1. validator failure rate 是否低于阈值。
2. fallback rate 是否低于阈值。
3. selected regression fixtures 是否全部通过。
4. 是否存在未关闭 P0/P1 diagnostics。
5. default switch 是否需要 staged rollout percentage / environment flag。
6. rollback strategy 是什么。

### 15.3 验收标准

R3 gate 通过条件：

1. R2 已通过。
2. Phase H readiness report 通过。
3. PM 明确批准。
4. 才允许单独提交 default switch PR。

---

## 16. 端到端验收场景

最终必须具备以下 E2E 或高保真集成覆盖：

1. **internal_comms guarded-action repair**
   - 输入 `examples/input/internal_comms.txt`
   - Stage 1 emits guarded_action sidecar for `When enough... produce a draft`
   - Stage 5 emits IF block
   - final SPL 不包含 guard-only COMMAND

2. **invalid LLM output fail-closed**
   - fake LLM returns paraphrased segment
   - validator rejects
   - fallback emits diagnostic
   - final SPL 不包含 guard-only COMMAND

3. **cross-section merge rejection**
   - fake LLM merges two sections
   - validator rejects
   - diagnostic visible

4. **same-packet multiple guarded_action**
   - input `If X, do A. If Y, do B.`
   - two guarded_action records
   - no merged mega-span

5. **ambiguous_boundary handling**
   - fallback creates ambiguous control-leading span
   - Stage 5 does not create IF
   - Stage 5 emits diagnostic
   - Stage 7 does not render guard-only command

6. **legacy default regression**
   - default config remains legacy until R3
   - existing tests and demo outputs do not change unexpectedly

---

## 17. PM 总审核清单

每个阶段提交审核时，PM 必须逐项检查：

1. 是否严格对齐 `stage1_llm_guided_source_constrained_span_slicing_design_zh.md`。
2. 是否扩大到 Stage 2/3/ConstructPlan/IRS/SPL Editing。
3. 是否让 Stage 1 输出 construct authority。
4. 是否新增未确认的 rule-based semantic fallback。
5. 是否 prompt 允许 paraphrase / rewrite。
6. 是否 validator 被绕过。
7. 是否 invalid LLM output materialize 到 `SpanIR`。
8. 是否 default config 被提前切到 `llm_source_constrained`。
9. 是否 Stage 5 靠 raw text pattern matching 而不是 sidecar。
10. 是否 Stage 7 构造 IF block。
11. 是否 Renderer/Gate/SPL Editing 掩盖 Stage 1/5/7 问题。
12. 是否 diagnostics 可见并进入 artifact。
13. 是否 artifact manifest 包含关键 checkpoint。
14. 是否无新增 skip / xfail。
15. 是否 git diff 没有 fixture pollution。
16. 是否 ruff / targeted pytest / E2E 均有命令输出。

---

## 18. 阶段完成顺序

推荐顺序：

```text
Phase A0  Characterization Baseline
Phase A1  Source Reconstruction and Config Substrate
Phase B   Prompt, Schema, Parser, and Shadow Proposal
Phase C   Deterministic Validator and Diagnostics
Phase D   Shadow Sidecar Materialization and Observability
Phase F   Stage 7 Independent Guard-Only Residual Fail-Closed
Gate R1   Shadow Exit Approval
Phase E   Stage 4 Pass-Through and Stage 5 Guarded-Action Consumer
Phase G   Selected Fixture Activation for internal_comms
Gate R2   Selected Fixture Release Approval
Phase H   Production-Default Readiness Instrumentation
Gate R3   Production Default Switch
```

Dependency rules:

```text
- A0 可立即开工。
- A1 必须在 B/C 前完成，因为 prompt/validator 依赖 source buffer。
- B 和 C 可以同一 PR 实施，但 C 是 B 输出可落地的硬前置。
- D 只能 shadow，不允许行为变更。
- F 可在 A0 后并行实施；它不依赖 R1 shadow exit，但必须在 R2 前通过。
- E/G 必须在 R1 gate 后执行。
- E/F/G 共同构成 R2 selected fixture closure，不得只交付 E 或 F 就宣称完成。
- H 不得切换 default，只准备 R3 evidence。
- R3 default switch 必须是单独决策和单独改动。
```
