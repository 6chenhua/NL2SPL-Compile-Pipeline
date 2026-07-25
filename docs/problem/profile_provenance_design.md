# Profile Provenance 溯源机制设计

## 1. 背景

当前编译器已经把 provenance 作为反馈报告的重要部分处理。`feedback_report.md`
能够展示 worker、flow、step、variable、constraint、handoff、source signal、
API 等结构对应的 span / section / packet 来源。

但 profile 层仍然是缺口。Stage 8 `ProfileExtractor` 会生成
`AgentProfileIR`，其中包含：

- persona；
- audience aspects；
- concepts。

这些对象目前没有保存来源信息。随后
`ProvenanceAggregator._trace_profile()` 只能生成空来源 trace：

```text
profile:persona       relation=inferred   source_span_ids=[]
profile:audience_N    relation=inferred   source_span_ids=[]
profile:concept_N     relation=normalized source_span_ids=[]
```

因此 feedback report 中可以看到：

```text
worker:MainWorker (direct) -- spans=...; section=...; packet=...
```

但 profile 只显示为：

```text
profile:concept_0 (normalized)
profile:persona (inferred)
```

没有 span、section、packet。这不是 final SPL 展示问题，也不是 feedback report
渲染丢失信息，而是 profile IR 和 provenance 聚合层没有建立 source-backed
contract。

## 2. 当前事实

当前代码事实：

1. `AgentProfileIR`、`PersonaIR`、`Aspect`、`Concept` 没有 provenance 字段。
2. Stage 8 prompt 虽然传入了 source spans JSON，但解析结果只读取 `role`、
   `aspects`、`concepts`；即使 LLM 输出 span IDs，当前 dataclass 构造也不会接收。
3. `ProvenanceAggregator._trace_profile()` 明确写入 `source_span_ids=[]`。
4. `feedback_report_renderer` 只渲染已有 `TraceRecord`，不会、也不应该在 report
   层补推 provenance。
5. Worker provenance 已经是 source-backed；profile provenance 缺失不应通过改
   Worker 逻辑解决。

## 3. 目标

为以下 profile 内容增加可追踪 provenance：

- persona role；
- persona aspects；
- audience aspects；
- concepts，包括 term 和 definition。

目标 feedback report 形态：

```text
### Profiles
- `profile:persona` (direct) -- spans=s0; section=sec_persona; packet=p_role
- `profile:persona.aspect:0` (direct) -- spans=s1; section=sec_persona; packet=p_aspect_evidence_driven
- `profile:audience:0` (direct) -- spans=s8; section=sec_audience; packet=p_audience_execs
- `profile:concept:5` (normalized) -- spans=s12; section=sec_concepts; packet=p_concept_provenance
```

如果某个 profile 项没有可验证 source evidence，不得把它展示为 source-backed。
应保留 trace，但标记为 `assumed` 或 `inferred`，并产生 provenance diagnostic。

## 4. 非目标

本设计不做以下事情：

- 不把 PERSONA / AUDIENCE / CONCEPTS 注册为新的 `ConstructIRS`。
- 不把 profile route label 当作 diagnostic host construct。
- 不扩展 final SPL grammar。
- 不在 feedback report renderer 中推断 provenance。
- 不把 raw keyword heuristic 当作 provenance authority。
- 第一阶段不扩展 `TraceRecord` schema。

PERSONA / AUDIENCE / CONCEPTS 是 SPL grammar 中的 top-level profile sections。
它们不是 executable construct；本阶段也不把它们注册为 IRS-checkable
`ConstructIRS`，不把它们纳入 construct slot satisfaction authority。IRS 仍然保持
construct-centered；profile provenance 由 Stage 8 和 ProvenanceAggregator 负责。

## 4.1 Review Amendments

进入实施前固定以下边界，避免后续实现重新出现“看起来有 provenance、实际不
source-backed”的问题：

1. grammar construct 和 IRS construct 必须区分。PERSONA / AUDIENCE / CONCEPTS
   属于 SPL grammar top-level profile sections，但本阶段不是 IRS construct。
2. profile trace 只有在 `source_span_ids` 非空时，才能进入
   `Materialized Source-Backed Structure`。
3. `missing_provenance.blocks_completion` 必须按“是否进入 final SPL 且 evidence
   为空”精细化，不能因为 source-backed inferred fallback 就阻断 completion。

## 5. Authority Chain

目标 authority chain：

```text
SpanIR / RouteAnnotation / StructuralPrior
-> Stage 8 ProfileExtractor
-> AgentProfileIR with source provenance fields
-> ProvenanceAggregator._trace_profile()
-> TraceRecord
-> feedback_report.md / snapshot provenance
```

职责边界：

| Concern | Authority |
|---|---|
| profile value 提取 | Stage 8 ProfileExtractor |
| source span 合法性校验 | Stage 8，对结构化 span IDs 校验 |
| profile trace 构造 | ProvenanceAggregator |
| missing provenance diagnostic | ProvenanceAggregator |
| 用户可见展示 | feedback report renderer |
| construct slot satisfaction | IRS，不由 profile provenance 承担 |

feedback report 只能展示已有 trace 和 diagnostics，不允许重新执行 provenance
推断。

## 6. IR 数据模型

### 6.1 为 profile IR 增加 provenance 字段

建议在 profile 子对象上增加 provenance 字段：

```python
@dataclass
class Aspect:
    name: str
    text: str
    source_span_ids: list[str] = field(default_factory=list)
    source_section_id: str | None = None
    source_packet_id: str | None = None
    provenance_relation: str = "direct"

@dataclass
class Concept:
    term: str
    definition: str
    source_span_ids: list[str] = field(default_factory=list)
    source_section_id: str | None = None
    source_packet_id: str | None = None
    provenance_relation: str = "normalized"

@dataclass
class PersonaIR:
    role: str = "General Assistant"
    aspects: list[Aspect] = field(default_factory=list)
    source_span_ids: list[str] = field(default_factory=list)
    source_section_id: str | None = None
    source_packet_id: str | None = None
    provenance_relation: str = "inferred"
```

`AgentProfileIR` 暂不需要顶层 provenance 字段。实际可追踪对象是 persona
role、persona aspect、audience aspect、concept。

### 6.2 relation 语义

沿用现有 `TraceRecord.relation` 字符串，不在第一阶段改 schema：

| relation | profile 语义 |
|---|---|
| `direct` | 源文本直接声明该 profile 内容。 |
| `normalized` | 内容来自源文本，但经过大小写、空格、术语格式等规范化。 |
| `derived` | 内容由多个 source-backed span 共同推导。 |
| `inferred` | 从 source-backed 上下文确定性推断，需要确认。 |
| `assumed` | 没有 source evidence，不得视为 source-backed。 |

`needs_confirmation` 规则：

- `direct`、`normalized`、`derived`: `False`
- `inferred`、`assumed`: `True`

### 6.3 Concept 字段级 provenance

MVP 可以先用一个 provenance 集合覆盖整个 `Concept`。如果后续发现 term 和
definition 经常来自不同 span，再扩展：

```python
term_source_span_ids: list[str] = field(default_factory=list)
definition_source_span_ids: list[str] = field(default_factory=list)
```

第一阶段不建议直接加字段级 concept provenance，避免 snapshot 和 serializer
变更面过大。

## 7. Stage 8 提取设计

### 7.1 Prompt 输出 contract

Stage 8 prompt 应要求每个 profile 元素返回 `source_span_ids`：

```json
{
  "persona": {
    "role": "Internal communications specialist",
    "source_span_ids": ["s0"],
    "aspects": [
      {
        "name": "EvidenceDriven",
        "text": "Maintains provenance for externally sourced facts.",
        "source_span_ids": ["s1"]
      }
    ]
  },
  "audience": {
    "aspects": [
      {
        "name": "Executives",
        "text": "Executive recipients of concise briefs.",
        "source_span_ids": ["s8"]
      }
    ]
  },
  "concepts": [
    {
      "term": "Provenance",
      "definition": "The traceable origin of a fact or claim.",
      "source_span_ids": ["s12"]
    }
  ]
}
```

所有返回的 `source_span_ids` 必须存在于输入 `SpanIR` 集合中。未知 span ID
必须被丢弃，不能进入 source-backed trace。

### 7.2 候选 source surface

Stage 8 应建立结构化候选集合：

```text
persona candidates:
  routes.identity
  annotations where semantic_role in {"identity", "persona"}

audience candidates:
  routes.audience
  annotations where semantic_role == "audience" if present

concept candidates:
  routes.domain
  annotations where semantic_role == "profile_domain"
```

如果 route 缺失，但 annotation 提供了明确 profile 语义，可用 annotation 作为
candidate source surface。若二者都缺失，允许 fallback 到 all spans 做文本匹配，
但 relation 不得标为 `direct`。

all-spans fallback 只能做 normalized exact / substring evidence recovery。不得做
semantic fuzzy match，不得把 unrelated behavior/action span 标成 profile
provenance。

### 7.3 Deterministic provenance recovery

不要只依赖 LLM 输出 span IDs。Stage 8 需要 deterministic recovery：

1. 构造 `span_by_id`。
2. 校验 LLM 返回的 source IDs 是否存在且属于对应候选集合。
3. 若 source IDs 不合法，使用 normalize 后的 value 文本在候选 spans 中匹配。
4. 精确匹配一个 span：采用该 span，relation=`normalized`。
5. 匹配多个 spans：采用全部匹配，relation=`derived`。
6. 无匹配：保留 profile value，但 `source_span_ids=[]`，relation=`assumed`。

该步骤只负责绑定已有结构化 evidence，不负责发明 profile value。

### 7.4 Role fallback 也必须携带 provenance

当前 `_resolve_role()` 只返回字符串。应改成返回值与 provenance：

```python
@dataclass(frozen=True)
class ResolvedProfileValue:
    text: str
    source_span_ids: tuple[str, ...]
    source_section_id: str | None
    source_packet_id: str | None
    relation: str
```

示例：

| 场景 | relation | source_span_ids |
|---|---|---|
| 显式 role span | `direct` | 对应 identity span |
| 从 `Task family:` 推断角色 | `inferred` | 触发推断的 span |
| 完全无 source | `assumed` | 空 |

这样即使 role 是 deterministic fallback，也能在 report 中说明来源。

## 8. ProvenanceAggregator 设计

当前 `_trace_profile()` 写死空来源：

```python
TraceRecord(
    target_ref="profile:persona",
    source_span_ids=[],
    relation="inferred",
)
```

目标改为读取 `AgentProfileIR` 内的 provenance：

```python
TraceRecord(
    target_ref="profile:persona",
    source_span_ids=list(profile.persona.source_span_ids),
    source_section_id=profile.persona.source_section_id,
    source_packet_id=profile.persona.source_packet_id,
    relation=profile.persona.provenance_relation,
    needs_confirmation=_profile_needs_confirmation(profile.persona),
    explanation=f"Persona: {profile.persona.role}",
)
```

建议 target ref 规范：

| Profile item | target_ref |
|---|---|
| Persona role | `profile:persona` |
| Persona aspect | `profile:persona.aspect:{index}` |
| Audience aspect | `profile:audience:{index}` |
| Concept | `profile:concept:{index}` |

本次 profile provenance schema 变更直接采用冒号分层形式，不继续保留
`profile:concept_0` 作为新 trace target。旧 snapshot 反序列化可兼容旧 target
字符串，但新产物、diagnostics、feedback report 和后续 SPL Editing target
resolver 都应使用冒号分层形式。

## 9. Diagnostics 设计

第一阶段复用现有 `missing_provenance`，不新增 profile 专用 diagnostic kind。

规则：

| profile relation | source spans | final SPL rendered | diagnostic / completion |
|---|---|---|---|
| `direct` | 非空 | 任意 | 无 |
| `normalized` | 非空 | 任意 | 无 |
| `derived` | 非空 | 任意 | 无 |
| `inferred` | 非空 | 任意 | 无 `missing_provenance`；`needs_confirmation=True`；`blocks_completion=false` 或 review-only |
| 任意 relation | 空 | 是 | `missing_provenance`; `blocks_completion=true`; `blocks_rendering=false` |
| 任意 relation | 空 | 否 | `missing_provenance` 或 provenance warning; `blocks_completion=false` |

诊断示例：

```text
kind=missing_provenance
target_ref=profile:concept:5
message=Profile concept 'Provenance' has no source-backed span evidence.
severity=warning
blocks_completion=true
blocks_rendering=false
metadata.rendered_profile_item=true
```

理由：

- profile 会影响 agent 行为；如果某个缺 provenance 的 profile item 已进入 final
  SPL，应影响 completion status。
- source-backed inferred fallback 有触发 source span 时，不是 missing provenance；
  它应通过 `needs_confirmation=True` 表达确认需求，而不是阻断 completion。
- 未进入 final SPL 的默认或遗留 profile item 不应造成全局 completion regression。
- profile 不是 executable behavior，因此默认不阻止 final SPL rendering。
- 如果后续要让 SPL Editing 修复该问题，需要单独定义 repair strategy；本阶段先
  作为 review-only provenance diagnostic。

## 10. Feedback Report 设计

### 10.1 新增 Profiles 分组

`feedback_report_renderer._trace_group()` 增加：

```python
if target_ref.startswith("profile:"):
    return "Profiles"
```

`_render_materialized()` 分组顺序建议：

```text
Workers
Profiles
Flows
Steps
Variables
Constraints
Handoffs
Source Signals
Other
```

### 10.2 source-backed profile 展示

有 source spans 的 profile trace 应展示为：

```text
### Profiles
- `profile:persona` (direct) -- spans=s0; section=sec_persona; packet=p_role
- `profile:concept:5` (normalized) -- spans=s12; section=sec_concepts; packet=p_concept_provenance
```

profile trace 进入 `Materialized Source-Backed Structure` 的必要条件：

```text
source_span_ids 非空
and relation in {"direct", "normalized", "derived", "inferred"}
```

任意 profile trace 只要 `source_span_ids` 为空，不论 relation 是 `inferred`、
`normalized` 还是 `assumed`，都不得展示为 source-backed materialized structure。
它可以出现在完整 TraceRecords 区域，并通过 `missing_provenance` diagnostic 或
provenance warning 展示。

## 11. Snapshot 和序列化

需要更新 `serializers_compile.py`：

- `AspectSerializer` 写入并读取：
  - `source_span_ids`
  - `source_section_id`
  - `source_packet_id`
  - `provenance_relation`
- `ConceptSerializer` 同上。
- `PersonaIRSerializer` 为 persona role 写入并读取同样字段。

兼容规则：

| 字段缺失 | 默认 |
|---|---|
| `source_span_ids` | `[]` |
| `source_section_id` | `None` |
| `source_packet_id` | `None` |
| `PersonaIR.provenance_relation` | `inferred` |
| `Aspect.provenance_relation` | 有 spans 时 `direct`，无 spans 时 `assumed` |
| `Concept.provenance_relation` | 有 spans 时 `normalized`，无 spans 时 `assumed` |

本阶段不扩展 `TraceRecord`，避免 snapshot schema 连锁变更。

## 12. 校验规则

Stage 8 provenance 校验必须满足：

1. 未知 span ID 不得进入 source-backed trace。
2. 空 source ID 不得被默认为 source-backed。
3. concept 不得从无关 behavior/action span 声称 provenance，除非没有更精确的
   domain/profile candidate surface。
4. persona fallback 推断必须保留触发推断的 source span。
5. provenance 不得从 final SPL 文本反推。
6. report renderer 不得补救缺失 provenance。

允许的 soft recovery：

- route 缺失但 annotation 有 `profile_domain` / `identity` / `persona` /
  `audience` 时，可使用 annotation 的 span。
- route 和 annotation 都缺失时，可用 all spans 进行 deterministic text match，
  但 relation 应为 `derived` 或 `inferred`，不得标成 `direct`。

## 13. 测试设计

### 13.1 单元测试

建议新增或扩展：

- `tests/unit/test_agent_profile_ir.py`
  - dataclass 默认值保持兼容；
  - persona/aspect/concept 可携带 provenance fields。
- `tests/unit/test_snapshot_serializers_compile.py`
  - profile provenance serialization round-trip；
  - 旧 snapshot payload 无 provenance 字段也能反序列化。
- `tests/unit/test_stage8_profile_extractor.py`
  - LLM 返回合法 span IDs 时绑定到 persona/concepts；
  - 未知 span IDs 被拒绝并降级为 assumed；
  - deterministic role fallback 保留 source span。
- `tests/unit/test_provenance.py`
  - `_trace_profile()` 生成带 spans/section/packet 的 profile traces；
  - 缺 profile evidence 产生 `missing_provenance`；
  - source-backed inferred persona 设置 `needs_confirmation=True`。
- `tests/unit/test_feedback_report_renderer.py`
  - `profile:` trace 渲染到 `Profiles` 分组；
  - source-backed profile 展示 spans/section/packet；
  - assumed profile 不展示为 materialized source-backed。

### 13.2 Demo / E2E 验收

使用 `examples/input/internal_comms.txt` 或等价 fixture。

期望 `feedback_report.md` 同时包含：

```text
### Workers
- `worker:MainWorker` (direct) -- spans=...

### Profiles
- `profile:persona` (...) -- spans=...
- `profile:concept:0` (...) -- spans=...
```

不应再出现无来源的 profile materialized 记录：

```text
profile:concept_N (normalized)
profile:persona (inferred)
```

除非同时存在对应 `missing_provenance` diagnostic，并且该 trace 没有被展示为
source-backed materialized structure。

## 14. 实施顺序

### P0 - Characterization

- 增加测试锁定当前缺口：worker 有 provenance，profile 无 provenance。
- 用 feedback report fixture 证明 profile 只有 normalized/inferred，无 source
  suffix。

### P1 - IR 和 serializer

- 给 `Aspect`、`Concept`、`PersonaIR` 增加 provenance 字段。
- 更新 snapshot serializers。
- 增加 backward-compatible round-trip 测试。

### P2 - Stage 8 provenance extraction

- 更新 Stage 8 prompt contract。
- 解析并校验 `source_span_ids`。
- 增加 deterministic provenance recovery。
- 改造 `_resolve_role()`，让 fallback role 携带 provenance。

### P3 - ProvenanceAggregator

- 改造 `_trace_profile()`，读取 `AgentProfileIR` provenance。
- 对缺 evidence 的 profile entry 产生 `missing_provenance`。
- 设置 inferred/assumed 的 `needs_confirmation`。

### P4 - Feedback report

- 新增 `Profiles` 分组。
- 确保 source-backed profile 显示 spans/section/packet。
- 确保 assumed profile 不进入 materialized source-backed section。

### P5 - E2E 验证

- 重新生成 demo artifacts。
- 检查 `feedback_report.md`、`spl_editing_snapshot.json`。
- 跑 focused unit tests、Ruff、必要的 demo E2E。

## 15. 验收标准

完成标准：

1. `AgentProfileIR` 能保存 persona、audience、concept 的 source provenance。
2. Stage 8 只接受经过校验的 source span IDs。
3. `ProvenanceAggregator` 对 source-backed profile 输出非空 span evidence。
4. 缺 profile provenance 时产生可见 `missing_provenance` diagnostic 或 provenance
   warning，且 completion blocking 按 rendered + empty evidence 精细化。
5. `feedback_report.md` 有 `Profiles` 分组并展示 span/section/packet。
6. `Materialized Source-Backed Structure` 中不存在空 `source_span_ids` 的
   profile trace。
7. Worker provenance 行为保持不变。
8. 不引入 PERSONA / AUDIENCE / CONCEPTS 的新 IRS construct。
9. 老 snapshot 无 profile provenance 字段时仍可反序列化。

## 16. 风险和缓解

| 风险 | 缓解 |
|---|---|
| snapshot churn | 使用默认字段并保持反序列化兼容。 |
| LLM 编造 source span IDs | Stage 8 校验 span ID 和 candidate source surface。 |
| profile 被误展示为 source-backed | 无 spans 时 relation=`assumed` 并产生 diagnostic。 |
| IRS 边界被扩大 | profile provenance 保持在 Stage 8 + ProvenanceAggregator，不注册 ConstructIRS。 |
| report 层承担推断 | renderer 只分组和展示已有 trace。 |

## 17. 开放问题

1. concept 是否现在就需要 term/definition 字段级 provenance？
2. profile provenance diagnostic 是否应进入 SPL Editing 可编辑项，还是在确认
   repair strategy 前保持 review-only？
