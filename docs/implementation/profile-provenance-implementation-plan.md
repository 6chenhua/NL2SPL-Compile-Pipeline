# Profile Provenance 实施计划

本文档严格基于 `docs/problem/profile_provenance_design.md` 制定。实施目标是为
`PERSONA / AUDIENCE / CONCEPTS` top-level profile sections 建立 source-backed
provenance contract，使 `AgentProfileIR`、Stage 8、`ProvenanceAggregator`、
snapshot 和 `feedback_report.md` 对 persona / audience / concept 的来源保持一致。

首轮范围：

- 覆盖 `PersonaIR.role`、`PersonaIR.aspects`、`AgentProfileIR.audience_aspects`、
  `AgentProfileIR.concepts`。
- 覆盖 Stage 8 prompt/schema、profile IR、snapshot serializer、provenance
  aggregation、feedback report grouping、demo/E2E 验收。
- 不注册新的 `ConstructIRS`，不扩展 final SPL grammar，不实现 SPL Editing repair
  strategy，不扩展 `TraceRecord` schema。

---

## 1. 总体目标

最终系统应形成以下职责链路：

```text
SpanIR / RouteAnnotation / StructuralPrior
  -> Stage 8 candidate source surfaces
  -> persona / audience / concept provenance candidates

Stage 8 ProfileExtractor
  -> AgentProfileIR with source_span_ids / section / packet / relation
  -> deterministic validation and exact/substring recovery only
  -> no semantic fuzzy match, no raw fallback authority

AgentProfileIR
  -> snapshot serialization round-trip
  -> backward-compatible old payload loading

ProvenanceAggregator
  -> profile TraceRecord targets
  -> missing_provenance diagnostics for empty evidence
  -> needs_confirmation for inferred / assumed profile entries

feedback_report_renderer
  -> Profiles group
  -> source-backed materialized display only when profile source_span_ids is non-empty
  -> no provenance inference in report layer

Demo / snapshot / feedback report
  -> worker provenance unchanged
  -> profile provenance visible and auditable
```

---

## 2. 全局硬性原则

所有阶段必须遵守：

1. `PERSONA / AUDIENCE / CONCEPTS` 是 SPL grammar top-level profile sections，
   但本计划不把它们注册为 IRS-checkable `ConstructIRS`。
2. `AgentProfileIR` 是 profile provenance 的数据承载层；report renderer 不得
   从 final SPL、raw text 或显示文本反推 provenance。
3. Stage 8 只可绑定已有 `SpanIR` / `RouteAnnotation` / structural source
   evidence，不得发明 span IDs。
4. all-spans fallback 只能做 normalized exact / substring evidence recovery；
   禁止 semantic fuzzy match。
5. unrelated behavior/action span 不得被标成 profile provenance，除非没有更精确
   profile/domain candidate surface，且只能使用非 `direct` relation。
6. `source_span_ids=[]` 的 `profile:` trace 不得进入
   `Materialized Source-Backed Structure`。
7. `profile:` trace 进入 source-backed materialized section 的必要条件是：
   `source_span_ids` 非空且 relation 属于
   `{"direct", "normalized", "derived", "inferred"}`。
8. `inferred + source_span_ids 非空` 不产生 `missing_provenance`，只设置
   `needs_confirmation=True`。
9. `source_span_ids 为空 + 已进入 final SPL` 才设置
   `missing_provenance.blocks_completion=true`。
10. 旧 snapshot payload 必须继续反序列化；新产物统一使用冒号分层 target refs：
    `profile:persona`、`profile:persona.aspect:{index}`、
    `profile:audience:{index}`、`profile:concept:{index}`。
11. 不扩展 `TraceRecord` schema；section / packet provenance 继续使用现有字段。
12. 不新增 skip / xfail / 弱断言来绕过 profile provenance 覆盖。

---

## 2.1 Review Amendments / Implementation Hardening

进入编码前固定以下补强规则；后续 phase 不得放宽：

1. PP0 只允许 current characterization tests。future expectation 只能作为测试
   注释、helper 命名或 PP4 待新增测试清单记录，不得加入会失败、skip、xfail 或
   弱化断言的测试。
2. profile IR dataclass 默认 relation 必须 fail-closed。`Aspect`、`Concept`、
   `PersonaIR` 的默认 `provenance_relation` 均为 `assumed`；Stage 8 只有在成功
   绑定并校验 source evidence 后，才能显式设置 `direct`、`normalized`、
   `derived` 或 `inferred`。
3. 多 span provenance 的 section / packet 传播必须确定性处理：保留全部 span IDs
   的稳定顺序；只有所有 matched spans 共享同一个 section / packet 时才写入对应
   字段；mixed section / packet 必须写 `None`，禁止任意选择第一个。
4. PP3 必须实现 conservative rendered-profile predicate，不能把
   `blocks_completion=true` 留给不存在的后续阶段。当前 Stage 11 行为下：
   `profile:persona` 在 `AgentProfileIR` 存在时视为 rendered；
   `profile:persona.aspect:{i}` 在该 aspect 存在时视为 rendered；
   `profile:audience:{i}` 在该 audience aspect 存在时视为 rendered；
   `profile:concept:{i}` 在该 concept 存在时视为 rendered。未来 renderer 行为
   改变时，predicate 和测试必须同步更新。

---

## 3. LLM / Rule-based 决策约束

本计划允许修改 Stage 8 prompt/schema，但新增 LLM 行为仅限让 Stage 8 返回
`source_span_ids`。Stage 8 仍然是唯一 profile extraction LLM boundary。

允许的确定性逻辑：

- 校验 LLM 返回的 `source_span_ids` 是否存在于 `span_by_id`。
- 校验 source IDs 是否属于对应 profile candidate source surface。
- 对 profile value 做 Unicode / 空白 / 大小写 / 标点规范化。
- 在候选 spans 中执行 exact match 或 substring match。
- 根据匹配数量设置 `direct` / `normalized` / `derived` / `inferred` /
  `assumed`。
- 从已存在 span 复制 `source_section_id` / `source_packet_id`。
- 基于现有 profile trace 字段生成 diagnostics 和 report 分组。

禁止的行为：

1. 使用 semantic fuzzy similarity 为 profile 自动绑定 provenance。
2. 从 final SPL 或 feedback report 文本反推 source spans。
3. 在 `feedback_report_renderer` 中读取 raw NL 或 route annotations。
4. 新增 PERSONA / AUDIENCE / CONCEPTS 的 ConstructIRS。
5. 让 IRS checker、Gate、ProducerIndex 参与 profile provenance 判定。
6. 让 Stage 8 deterministic recovery 发明 profile value。
7. 让默认 `General Assistant` 在没有 source span 时表现为 source-backed。

需要 PM 重新确认才允许的行为：

1. 引入 concept term/definition 字段级 provenance。
2. 把 profile provenance diagnostic 暴露为 SPL Editing editable issue。
3. 扩展 `TraceRecord` schema。
4. 把 profile sections 纳入 IRS construct slot satisfaction。
5. 对 all-spans fallback 增加 fuzzy / semantic matching。

---

## 4. Phase PP0: Current Gap Lock

### 4.1 目标

在修改生产行为前，用 characterization tests 锁定当前缺口：worker trace 有
source-backed provenance，profile trace 没有 source spans，且 feedback report 将
空来源 profile trace 展示在 materialized source-backed section。

### 4.2 可编辑范围

允许新增或修改：

```text
tests/unit/test_provenance.py
tests/unit/test_feedback_report_renderer.py
tests/unit/test_profile_extractor.py
tests/unit/test_stage8_prompt.py
tests/unit/test_usage_stage8_prompt.py
```

### 4.3 禁止改动

Phase PP0 禁止修改：

```text
src/
prompts/
examples/output/
docs/problem/profile_provenance_design.md
```

### 4.4 设计要求

新增测试必须明确表达 current gap 与 future expectation：

```text
current:
  worker TraceRecord has source_span_ids
  profile TraceRecord has source_span_ids=[]
  profile trace may appear as normalized/inferred without source suffix

future:
  source-backed profile requires non-empty source_span_ids
```

不得把当前错误行为写成最终 contract。

### 4.5 测试计划

新增单元测试覆盖：

1. `_trace_profile()` 当前对 persona 输出 `source_span_ids=[]`。
2. `_trace_profile()` 当前对 concepts 输出 `source_span_ids=[]`。
3. worker trace 仍然带 spans / section / packet。
4. `_render_materialized()` 当前只按 `relation != "assumed"` 分组 profile。
5. future expectation 只可作为测试注释、helper 名称或 PP4 待新增测试清单记录；
   不得加入会失败、skip、xfail 或弱化断言的测试。

### 4.6 验收标准

Phase PP0 通过条件：

1. 只增加 characterization tests。
2. 测试能稳定证明当前 profile provenance 缺口。
3. 没有 production diff。
4. 没有新增 skip / xfail。

### 4.7 PM 审核清单

审核时必须检查：

1. PP0 没有改 `src/` 或 prompt。
2. 测试名称含义清楚，不把 current bug 命名为 desired behavior。
3. 测试同时覆盖 worker positive control 和 profile negative case。
4. 没有依赖当前 demo 文件的脆弱行号。

---

## 5. Phase PP1: Profile IR and Serializer Contract

### 5.1 目标

为 profile IR 增加 provenance 字段，并保证 snapshot serialization
backward-compatible round-trip。

### 5.2 可编辑范围

允许修改：

```text
src/nl2spl/ir/agent_profile_ir.py
src/nl2spl/compiler/artifacts/snapshot/serialization/serializers_compile.py
tests/unit/test_profile_extractor.py
tests/unit/test_compile_result.py
tests/unit/test_provenance.py
tests/unit/compiler/artifacts/  (如现有目录存在)
```

如没有合适 snapshot serializer 测试文件，允许新增：

```text
tests/unit/test_snapshot_serializers_compile.py
```

### 5.3 禁止改动

Phase PP1 禁止修改：

```text
src/nl2spl/pipeline/stages/stage8_profile_extractor.py
src/nl2spl/pipeline/provenance.py
src/nl2spl/compiler/feedback_report_renderer.py
prompts/stage8_system.txt
```

### 5.4 设计要求

为 dataclasses 添加字段：

```text
Aspect.source_span_ids: list[str]
Aspect.source_section_id: str | None
Aspect.source_packet_id: str | None
Aspect.provenance_relation: str

Concept.source_span_ids: list[str]
Concept.source_section_id: str | None
Concept.source_packet_id: str | None
Concept.provenance_relation: str

PersonaIR.source_span_ids: list[str]
PersonaIR.source_section_id: str | None
PersonaIR.source_packet_id: str | None
PersonaIR.provenance_relation: str
```

Defaults:

```text
Aspect.provenance_relation = "assumed"
Concept.provenance_relation = "assumed"
PersonaIR.provenance_relation = "assumed"
source_span_ids = []
source_section_id = None
source_packet_id = None
```

Stage 8 成功绑定并校验 source evidence 后，必须显式设置非 assumed relation：

```text
direct
normalized
derived
inferred
```

Invariant:

```text
relation in {"direct", "normalized", "derived", "inferred"}
requires non-empty source_span_ids
unless the payload is explicitly identified as a legacy snapshot before aggregation.
```

Serializer backward compatibility:

```text
missing source_span_ids -> []
missing source_section_id/source_packet_id -> None
missing provenance_relation:
  PersonaIR -> inferred only for explicit legacy payload with spans, otherwise assumed
  Aspect -> direct only for explicit legacy payload with spans, otherwise assumed
  Concept -> normalized only for explicit legacy payload with spans, otherwise assumed
```

### 5.5 测试计划

新增或扩展测试覆盖：

1. `Aspect` 默认 provenance 字段。
2. `Concept` 默认 provenance 字段。
3. `PersonaIR` 默认 provenance 字段。
4. serializer round-trip 保留所有 provenance 字段。
5. old payload 没有 provenance 字段时可反序列化。
6. old payload 反序列化后不会被误认为 source-backed。

### 5.6 验收标准

Phase PP1 通过条件：

1. profile IR 可表达 source spans / section / packet / relation。
2. snapshot serializer 保持 backward-compatible。
3. 没有 Stage 8 / provenance / report 行为变更。
4. focused tests 通过。

### 5.7 PM 审核清单

审核时必须检查：

1. 字段 default 没有使用 mutable shared default。
2. serializer 没有丢 `source_section_id` / `source_packet_id`。
3. old payload 兼容测试存在。
4. 没有扩展 `TraceRecord` schema。

---

## 6. Phase PP2: Stage 8 Profile Provenance Extraction

### 6.1 目标

让 Stage 8 解析、校验并恢复 profile provenance，把结果写入
`AgentProfileIR`，但暂不改变 provenance report 展示。

### 6.2 可编辑范围

允许修改：

```text
prompts/stage8_system.txt
src/nl2spl/pipeline/stages/stage8_profile_extractor.py
tests/unit/test_profile_extractor.py
tests/unit/test_stage8_prompt.py
tests/unit/test_usage_stage8_prompt.py
```

### 6.3 禁止改动

Phase PP2 禁止修改：

```text
src/nl2spl/pipeline/provenance.py
src/nl2spl/compiler/feedback_report_renderer.py
src/nl2spl/compiler/irs/
src/nl2spl/pipeline/resource_declaration_gate.py
src/nl2spl/compiler/producer_index.py
```

### 6.4 设计要求

Stage 8 prompt 必须要求每个 profile item 返回 `source_span_ids`：

```text
persona.role.source_span_ids
persona.aspects[].source_span_ids
audience.aspects[].source_span_ids
concepts[].source_span_ids
```

Stage 8 extractor 必须实现：

```text
span_by_id construction
persona/audience/concept candidate source surfaces
source ID existence validation
candidate-surface membership validation
normalized exact / substring recovery
section/packet propagation from source spans
relation assignment
assumed fallback for no evidence
```

Section / packet propagation rule:

```text
For one matched source span:
  source_section_id = matched span.source_section_id
  source_packet_id = matched span.source_packet_id

For multiple matched source spans:
  source_span_ids preserves all matched span IDs in stable order
  if all matched spans share the same source_section_id:
    source_section_id = that shared section
  else:
    source_section_id = None
  if all matched spans share the same source_packet_id:
    source_packet_id = that shared packet
  else:
    source_packet_id = None

Never pick an arbitrary first section/packet when sources are mixed.
```

`_resolve_role()` 必须改为返回 text + provenance 的结构，不再只返回字符串。

建议新增内部 DTO：

```python
@dataclass(frozen=True)
class ResolvedProfileValue:
    text: str
    source_span_ids: tuple[str, ...]
    source_section_id: str | None
    source_packet_id: str | None
    relation: str
```

候选 surface 规则：

```text
persona:
  routes.identity
  annotations semantic_role in {"identity", "persona"}

audience:
  routes.audience
  annotations semantic_role == "audience" if supported

concept:
  routes.domain
  annotations semantic_role == "profile_domain"
```

all-spans fallback:

```text
allowed:
  normalized exact match
  normalized substring match

forbidden:
  semantic fuzzy match
  embedding similarity
  behavior/action span as direct profile provenance
```

### 6.5 测试计划

新增或扩展测试覆盖：

1. LLM 返回合法 persona source ID -> `PersonaIR.source_span_ids` 非空。
2. LLM 返回合法 concept source ID -> `Concept.source_span_ids` 非空。
3. LLM 返回未知 source ID -> 丢弃 source ID，relation 降级为 `assumed`。
4. LLM 返回跨 surface source ID -> 不作为 `direct` 接受。
5. exact text recovery 成功 -> relation=`normalized`。
6. 多 span recovery -> relation=`derived`。
7. role fallback 从 source span 推断 -> relation=`inferred` 且 spans 非空。
8. 无任何 source -> default role relation=`assumed` 且 spans 空。
9. prompt tests 锁定 Stage 8 schema 包含 `source_span_ids`。

### 6.6 验收标准

Phase PP2 通过条件：

1. Stage 8 output checkpoint 中 profile entries 带 provenance 字段。
2. 未知 / 不合法 span IDs 不进入 source-backed provenance。
3. 无 fuzzy semantic fallback。
4. focused Stage 8 tests 通过。
5. provenance report 行为暂不要求改变。

### 6.7 PM 审核清单

审核时必须检查：

1. Prompt 没要求 LLM 做 source authority/admission 判定。
2. Source span validation 在代码中执行，而不是只靠 prompt。
3. `all_spans` fallback 没有 fuzzy / semantic matching。
4. `_resolve_role()` fallback 保留 source provenance。
5. Stage 8 没有写入 IRS / Gate / ProducerIndex。

---

## 7. Phase PP3: Profile Provenance Aggregation and Diagnostics

### 7.1 目标

让 `ProvenanceAggregator._trace_profile()` 消费 `AgentProfileIR` provenance，
输出 source-backed profile traces，并对缺 evidence 的 profile entry 产生
`missing_provenance` 或 provenance warning。

### 7.2 可编辑范围

允许修改：

```text
src/nl2spl/pipeline/provenance.py
tests/unit/test_provenance.py
```

如 diagnostics registry 对 kind 有显式枚举要求，允许最小修改：

```text
src/nl2spl/compiler/diagnostic_registry.py
tests/unit/test_diagnostic_consolidator.py
```

### 7.3 禁止改动

Phase PP3 禁止修改：

```text
src/nl2spl/compiler/feedback_report_renderer.py
src/nl2spl/compiler/irs/
src/nl2spl/pipeline/stages/stage11_spl_renderer/
```

### 7.4 设计要求

Trace targets 固定为：

```text
profile:persona
profile:persona.aspect:{index}
profile:audience:{index}
profile:concept:{index}
```

Trace construction:

```text
source_span_ids      <- profile item source_span_ids
source_section_id    <- profile item source_section_id
source_packet_id     <- profile item source_packet_id
relation             <- profile item provenance_relation
needs_confirmation   <- relation in {"inferred", "assumed"}
```

Diagnostics policy:

```text
source_span_ids non-empty + relation inferred:
  no missing_provenance
  needs_confirmation=true
  blocks_completion=false

source_span_ids empty + rendered_profile_item=true:
  missing_provenance
  blocks_completion=true
  blocks_rendering=false

source_span_ids empty + rendered_profile_item=false:
  missing_provenance or provenance warning
  blocks_completion=false
```

Rendered-profile detection must be deterministic and conservative. PP3 必须实现
当前 Stage 11 renderer 行为对应的 rendered-profile predicate：

```text
profile:persona:
  rendered whenever AgentProfileIR exists

profile:persona.aspect:{i}:
  rendered when profile.persona.aspects[i] exists

profile:audience:{i}:
  rendered when profile.audience_aspects[i] exists

profile:concept:{i}:
  rendered when profile.concepts[i] exists
```

If future renderer behavior changes, this predicate must be updated with tests
in the same phase that changes rendering. PP3 不得把 rendered blocking 留作
未指定的后续 integration point。

### 7.5 测试计划

新增或扩展测试覆盖：

1. persona trace includes spans / section / packet.
2. persona aspect trace target uses `profile:persona.aspect:{index}`.
3. audience aspect trace target uses `profile:audience:{index}`.
4. concept trace target uses `profile:concept:{index}`.
5. inferred with spans sets `needs_confirmation=True` and no missing provenance.
6. empty spans produces visible diagnostic or warning.
7. old `profile:concept_0` is not produced for new traces.
8. worker traces remain unchanged.
9. rendered-profile predicate marks persona / existing aspects / existing
   audience aspects / existing concepts as rendered.
10. empty-source rendered profile item produces `missing_provenance` with
    `blocks_completion=true`.

### 7.6 验收标准

Phase PP3 通过条件：

1. `ProvenanceAggregator` no longer writes empty source IDs unconditionally.
2. New profile traces use colon-layered target refs.
3. Missing evidence is visible in diagnostics or provenance warnings.
4. Rendered profile item with empty `source_span_ids` produces
   `missing_provenance` with `blocks_completion=true`.
5. Worker / flow / step provenance tests still pass.

### 7.7 PM 审核清单

审核时必须检查：

1. No new `ConstructIRS` for profile targets.
2. No `TraceRecord` schema extension.
3. No report-layer inference.
4. Empty profile spans do not silently pass as source-backed in trace metadata.
5. Completion blocking rule is explicit and tested, not derived from relation
   truthiness.

---

## 8. Phase PP4: Feedback Report Source-Backed Profile Gate

### 8.1 目标

更新 `feedback_report.md` 展示逻辑：新增 `Profiles` 分组，并确保 profile trace
只有在 `source_span_ids` 非空且 relation 合法时才进入
`Materialized Source-Backed Structure`。

### 8.2 可编辑范围

允许修改：

```text
src/nl2spl/compiler/feedback_report_renderer.py
src/nl2spl/compiler/reporting/feedback_report_renderer.py  (如当前路径仍被使用)
tests/unit/test_feedback_report_renderer.py
```

### 8.3 禁止改动

Phase PP4 禁止修改：

```text
src/nl2spl/pipeline/provenance.py
src/nl2spl/pipeline/stages/stage8_profile_extractor.py
src/nl2spl/pipeline/stages/stage11_spl_renderer/
```

### 8.4 设计要求

`_trace_group()` 增加：

```python
if target_ref.startswith("profile:"):
    return "Profiles"
```

`_render_materialized()` 必须加入 profile-specific gate：

```text
if target_ref startswith "profile:":
  include only if:
    source_span_ids is non-empty
    relation in {"direct", "normalized", "derived", "inferred"}
else:
  keep existing non-profile behavior unless separately tested
```

注意：本阶段只收紧 profile target，不改变 worker / flow / step / variable /
constraint 的既有 materialized grouping 语义。

### 8.5 测试计划

新增或扩展测试覆盖：

1. source-backed `profile:persona` appears under `Profiles`.
2. source-backed `profile:concept:{index}` shows spans / section / packet.
3. `profile:persona` with `relation=inferred` but empty spans does not appear
   in materialized section.
4. `profile:concept:{index}` with `relation=normalized` but empty spans does
   not appear in materialized section.
5. non-profile traces with existing behavior remain unchanged.
6. raw TraceRecords section can still show non-source-backed profile traces if
   that section is enabled.

### 8.6 验收标准

Phase PP4 通过条件：

1. `feedback_report.md` has `Profiles` group for source-backed profile traces.
2. No empty-span `profile:` trace appears in `Materialized Source-Backed Structure`.
3. Existing worker materialized rendering is unchanged.
4. Focused report renderer tests pass.

### 8.7 PM 审核清单

审核时必须检查：

1. `_render_materialized()` does not use only `trace.relation != "assumed"` for
   profile targets.
2. Source-backed condition explicitly checks non-empty `source_span_ids`.
3. Renderer does not import Stage 8, routes, spans, or raw source parser.
4. `Profiles` group order is stable.

---

## 9. Phase PP5: Snapshot, Demo, and E2E Verification

### 9.1 目标

重新生成 demo artifacts，并验证 `feedback_report.md`、`spl_editing_snapshot.json`
和 final diagnostics 中 profile provenance 行为符合设计。

### 9.2 可编辑范围

允许更新 generated artifacts：

```text
examples/output/demo/stage8_profile_extractor.json
examples/output/demo/spl_editing_snapshot.json
examples/output/demo/feedback_report.md
examples/output/demo/final_spl.txt  (仅因 profile provenance side effect 导致时)
```

允许新增测试：

```text
tests/integration/test_partial_spl_mvp.py
tests/integration/test_pipeline.py
tests/integration/compiler/profile_provenance/  (如需要新目录)
```

### 9.3 禁止改动

Phase PP5 禁止修改 production code，除非 PP0-PP4 验证暴露真实 blocker，并且需
回到对应 phase 修复。

### 9.4 设计要求

E2E artifacts 必须证明：

```text
Workers:
  worker:MainWorker remains direct/source-backed

Profiles:
  profile:persona has non-empty source spans when source exists
  profile:concept:{index} has non-empty source spans when source exists
  empty-span profile traces are absent from materialized source-backed section

Diagnostics:
  missing profile provenance is visible when source evidence is absent
  blocks_completion follows rendered + empty evidence policy
```

### 9.5 测试计划

执行建议：

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_profile_extractor.py -q
.venv\Scripts\python.exe -m pytest tests/unit/test_provenance.py -q
.venv\Scripts\python.exe -m pytest tests/unit/test_feedback_report_renderer.py -q
.venv\Scripts\python.exe -m pytest tests/unit/test_stage8_prompt.py tests/unit/test_usage_stage8_prompt.py -q
.venv\Scripts\python.exe -m pytest tests/integration/test_pipeline.py tests/integration/test_partial_spl_mvp.py -q
```

如 demo runner 是当前交付标准，执行现有 demo 命令并保存 artifact manifest。

### 9.6 验收标准

Phase PP5 通过条件：

1. Demo `feedback_report.md` contains `### Profiles`.
2. Profile lines in materialized section include `spans=...; section=...; packet=...`.
3. No `profile:concept_N` target appears in new generated traces.
4. No empty-span `profile:` target appears as materialized source-backed.
5. `spl_editing_snapshot.json` preserves profile provenance fields.
6. Focused tests pass.

### 9.7 PM 审核清单

审核时必须检查：

1. Artifact changes are limited to expected demo/profile provenance effects.
2. No unrelated generated demo churn is included without explanation.
3. Feedback report, snapshot, and tests agree on target ref format.
4. Final SPL display remains grammar-valid.

---

## 10. Phase PP6: Documentation and Cleanup

### 10.1 目标

更新相关说明，移除过期 profile provenance 缺口描述，确保设计、实施计划、README
或 architecture docs 对当前行为一致。

### 10.2 可编辑范围

允许修改：

```text
docs/problem/profile_provenance_design.md
docs/implementation/profile-provenance-implementation-plan.md
docs/spl_nl_to_spl_design_document_v4.md
README.md
docs/Todo/exception_flow_routing_issues.md
```

实际只修改仍然陈旧或与实现冲突的文档。

### 10.3 禁止改动

Phase PP6 禁止继续调整 production behavior。若文档同步发现行为缺口，回到对应
phase 修复。

### 10.4 设计要求

文档必须表达：

```text
profile provenance exists for source-backed persona/audience/concepts
PERSONA/AUDIENCE/CONCEPTS are grammar sections, not IRS constructs in this phase
feedback report Profiles group requires non-empty source_span_ids
old profile provenance gap is resolved or superseded
```

### 10.5 测试计划

文档阶段不新增行为测试，但必须重跑 PP5 focused tests 或引用 PP5 结果。

### 10.6 验收标准

Phase PP6 通过条件：

1. No stale statement says Stage 8 profile provenance is completely absent.
2. Design and implementation plan agree on target refs and blocking semantics.
3. No docs suggest report renderer infers provenance.
4. Focused tests remain green.

### 10.7 PM 审核清单

审核时必须检查：

1. Docs do not overstate IRS support.
2. Docs do not promise SPL Editing repair for profile provenance.
3. Docs do not preserve `profile:concept_0` as a new target format.
4. Docs include source-backed display gate.

---

## 11. Decision Gate D-PP-0: Deferred Scope Confirmation

### 11.1 目标

确认首轮后是否需要扩展到 concept 字段级 provenance 或 SPL Editing repair exposure。
该 gate 不阻塞 PP0-PP6 的首轮实施。

### 11.2 可选方案

```text
方案 A: 保持 whole-concept provenance
方案 B: 增加 term_source_span_ids / definition_source_span_ids
方案 C: 把 profile missing_provenance 暴露为 SPL Editing review-only issue
方案 D: 定义 profile provenance repair strategy 并进入 editable issue flow
```

推荐首轮采用方案 A，并把 C/D 留到 profile provenance 行为稳定之后。

### 11.3 必须明确的问题

进入 D-PP-0 后必须回答：

1. 当前 fixtures 是否存在 term 与 definition 来源不同的真实样例？
2. 用户是否需要在 SPL Editing UI 中修复 profile provenance？
3. profile repair 的 construct closure 是什么？
4. 是否需要扩展 selectable ref / target resolver 支持 profile target roles？
5. 是否需要 TraceRecord metadata，而不是继续使用现有字段？

### 11.4 验收标准

该 gate 通过条件：

1. PP0-PP6 已完成。
2. 至少一个真实 fixture 证明 whole-concept provenance 不足，才可进入 B。
3. 有确认的 repair strategy，才可进入 D。
4. PM 明确批准后方可进入后续 profile repair 计划。

---

## 12. 端到端验收场景

最终必须具备以下覆盖：

1. **Internal Comms Profile Provenance**
   - 输入包含 persona role、concept definitions、process/constraint spans。
   - Stage 8 输出 profile provenance fields。
   - feedback report 显示 `Profiles` section。
   - worker provenance 保持 direct/source-backed。

2. **Inferred Persona With Source**
   - 输入没有显式 ROLE，但有 task family / purpose span。
   - persona role fallback 使用触发 span。
   - trace relation=`inferred`，`needs_confirmation=True`。
   - 不产生 `missing_provenance`，不阻断 completion。

3. **Default Persona Without Source**
   - 输入无法支持 persona role。
   - default profile relation=`assumed`，source spans empty。
   - 不展示为 materialized source-backed。
   - 若进入 final SPL，则产生 blocking missing provenance；未进入则 review-only。

4. **Unknown LLM Span ID**
   - LLM 返回不存在的 `source_span_ids`。
   - Stage 8 丢弃非法 ID。
   - profile item 不被 source-backed 展示。
   - diagnostic / warning 可见。

5. **All-Spans Fallback Negative**
   - profile candidate surface 缺失，source 中有 behavior/action span。
   - deterministic recovery 不做 semantic fuzzy match。
   - unrelated behavior/action span 不被标为 direct profile provenance。

6. **Snapshot Backward Compatibility**
   - 旧 `AgentProfileIR` payload 没有 provenance fields。
   - 反序列化成功。
   - 旧 profile 不被误认为 source-backed。

---

## 13. PM 总审核清单

每个阶段提交审核时，PM 必须逐项检查：

1. 是否严格对齐 `docs/problem/profile_provenance_design.md`。
2. 是否扩大到 IRS construct、Gate、ProducerIndex 或 SPL Editing repair。
3. 是否新增未经确认的 LLM boundary。
4. 是否新增 semantic fuzzy fallback。
5. Stage 8 是否校验 LLM 返回的 source span IDs。
6. all-spans fallback 是否只做 exact / substring recovery。
7. profile trace 是否统一使用冒号分层 target refs。
8. `profile:concept_0` 是否只作为旧 snapshot 兼容出现。
9. `feedback_report_renderer._render_materialized()` 是否对 `profile:` target
   明确检查非空 `source_span_ids`。
10. 空 `source_span_ids` 的 profile trace 是否不会进入 source-backed materialized
    section。
11. `inferred + source_span_ids 非空` 是否只 needs confirmation，不
    blocks completion。
12. `missing_provenance.blocks_completion` 是否只对 rendered + empty evidence
    生效。
13. Snapshot serializer 是否 backward-compatible。
14. Report renderer 是否没有读取 raw NL / Stage 8 / routes。
15. Worker provenance tests 是否仍然通过。
16. 是否新增 skip / xfail / 弱断言。
17. Demo artifact diff 是否只包含预期 profile provenance 变化。
18. 文档是否仍有“Stage 8 profile provenance 完全缺失”的过期表述。

---

## 14. 阶段完成顺序

推荐顺序：

```text
PP0 Current Gap Lock
PP1 Profile IR and Serializer Contract
PP2 Stage 8 Profile Provenance Extraction
PP3 Profile Provenance Aggregation and Diagnostics
PP4 Feedback Report Source-Backed Profile Gate
PP5 Snapshot, Demo, and E2E Verification
PP6 Documentation and Cleanup
D-PP-0 Deferred Scope Confirmation
```

依赖关系：

- PP0 必须最先完成，防止后续实现误判当前缺口。
- PP1 必须早于 PP2 / PP3，因为 Stage 8 和 ProvenanceAggregator 需要消费新字段。
- PP2 必须早于 PP3，因为 provenance aggregation 不应自行恢复 Stage 8 没有写入的
  profile source fields。
- PP4 必须在 PP3 后执行，report renderer 只消费 TraceRecord。
- PP5 必须在 PP1-PP4 后执行。
- PP6 最后执行，避免文档先于代码落地。
- D-PP-0 不阻塞首轮实施，只决定后续扩展范围。
