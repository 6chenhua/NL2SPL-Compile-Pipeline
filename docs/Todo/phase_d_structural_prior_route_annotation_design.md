# Phase D：StructuralPrior 与 RouteAnnotation 分离设计

状态：待实施  
日期：2026-06-05  
范围：Stage 2 route contract、LLM prompt payload、validator 上下文、下游 route 消费契约

## 1. 目标

Phase D 的目标是消除当前 neutral prior 冲突背后的架构根因：

```text
结构证据被编码成了 RouteAnnotation
```

当前 Phase A-C 可以修复 demo 中 main flow 为空的问题，但仍然依赖类似下面的 metadata 字符串判断：

```python
metadata["prior_resolution"] == "no_prior_neutral_context"
```

这说明类型边界还不够清晰。Phase D 要把两类概念显式拆开：

```text
StructuralPrior
  = deterministic 结构证据 / 上下文 / provenance
  = 供 LLM semantic mapper 和 validator 使用
  = 不能被 Stage 4/5/7 当作最终语义消费

RouteAnnotation
  = 最终语义路由决策
  = 来自确定性 hard contract 或 validated LLM output
  = Stage 4/5/7 只能消费它
```

## 2. 当前问题

当前 `_build_deterministic_priors()` 返回 `list[RouteAnnotation]`。

对于 neutral packet，它会生成：

```python
RouteAnnotation(
    span_id=span.span_id,
    field=field,
    executable=False,
    semantic_role=None,
    construct_target=None,
    slot_target=None,
    metadata={"prior_resolution": "no_prior_neutral_context"},
)
```

这个对象真实含义是：

```text
系统有结构上下文，但还没有语义判断，等待 LLM 判断。
```

但因为它是 `RouteAnnotation`，下游会把它解释成真实的 non-executable semantic annotation。

这导致了当前故障链：

```text
neutral pending prior: executable=false
LLM accepted annotation: executable=true
两者同时留在同一个 span 上
Stage 7 D6 guard 看到该 span 属于 non_exec_span_ids
主流程 step 被丢弃
final SPL 出现空 [MAIN_FLOW]
```

Phase D 要解决的是这个表示层错误，而不是继续靠补丁绕过。

## 3. 设计目标

1. `RouteAnnotation` 只表示最终语义决策。
2. neutral / pending / unknown 结构上下文不能再表示为 `RouteAnnotation`。
3. Stage 4/5/7 只能消费最终 `RouteAnnotation`。
4. LLM prompt 仍然能看到 deterministic structural evidence。
5. validator 仍然能利用 structural evidence 做 provenance 和 anti-fabrication 检查。
6. 不引入 rule-based semantic fallback。
7. LLM 调用、解析、schema 失败继续 fail-fast。
8. runtime input、required output 这类真正确定的结构 contract 仍可生成最终 `RouteAnnotation`。

## 4. 非目标

1. 本阶段不改 Stage 7 prompt 的语义任务。
2. 不在 renderer 增加 fallback command。
3. 不关闭 D6 guard。
4. 不增加基于关键词的 process-step 判定规则。
5. 不恢复 `FailureModeFact` 或 failure bridge。
6. 不恢复 legacy flat Stage 9.5 semantic repair path。

## 5. 新类型：StructuralPrior

在 `src/nl2spl/ir/field_route_ir.py` 中新增 `StructuralPrior`。

建议结构：

```python
@dataclass
class StructuralPrior:
    """用于 semantic routing 的确定性结构证据。

    StructuralPrior 不是最终语义路由决策。它可以指导 LLM 和 validator，
    但 Stage 4/5/7 不能把它当作语义消费。
    """

    span_id: str
    suggested_field: str | None = None
    source_section_id: str | None = None
    source_packet_id: str | None = None
    source_hint_ids: list[str] = field(default_factory=list)
    prior_kind: str = "neutral_context"
    confidence: str = "context"
    reason: str | None = None
    packet_type: str | None = None
    section_title: str | None = None
    structural_tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
```

字段含义：

| 字段 | 含义 |
|---|---|
| `span_id` | 该 prior 对应的 span |
| `suggested_field` | 弱 field hint，不是最终路由 |
| `source_section_id` | adapter section provenance |
| `source_packet_id` | adapter packet provenance |
| `source_hint_ids` | CompileHint provenance |
| `prior_kind` | 结构证据类型 |
| `confidence` | `exact` / `structural` / `context` / `weak` |
| `reason` | 可读解释 |
| `packet_type` | adapter packet type |
| `section_title` | 原始或 canonical section title |
| `structural_tags` | 例如 `list_item`、`colon_pair`、`section_context` |
| `metadata` | 非语义附加信息 |

建议先使用小的封闭 `prior_kind` 集合：

```text
neutral_context
weak_section_context
exact_route_prior
packet_type_context
runtime_input_contract
required_output_contract
compile_hint_context
```

注意：

- `runtime_input_contract` 和 `required_output_contract` 可以同时生成最终 `RouteAnnotation`，因为它们是确定性的 resource contract。
- `neutral_context`、`weak_section_context`、`packet_type_context` 不能单独生成最终语义。

## 6. Phase D 后的 RouteAnnotation 契约

`RouteAnnotation` 继续保留在 `field_route_ir.py`，但语义变严格：

```text
RouteAnnotation = 最终语义路由决策
```

它不能再表示：

1. unknown semantic state；
2. pending LLM interpretation；
3. weak section context；
4. generic “maybe behavior” context。

停止使用这些 metadata 作为正确性条件：

```text
prior_resolution=no_prior_neutral_context
prior_resolution=weak_section_context
```

这些概念迁移到：

```text
StructuralPrior.prior_kind
```

## 7. FieldRouteIR 结构

在 `FieldRouteIR` 中新增 `structural_priors`：

```python
@dataclass
class FieldRouteIR:
    ...
    annotations: list[RouteAnnotation] = field(default_factory=list)
    structural_priors: list[StructuralPrior] = field(default_factory=list)
```

下游规则：

```text
Stage 4/5/7 读取 annotations。
Stage 4/5/7 不读取 structural_priors。
```

Stage 2 checkpoint 应包含两者：

```json
{
  "routes": {
    "behavior": ["s13", "s14"],
    "annotations": [],
    "structural_priors": []
  }
}
```

## 8. Stage 2 数据流

当前数据流：

```text
_build_deterministic_priors()
  -> list[RouteAnnotation]

LLM refinement
  -> list[RouteAnnotation]

merge
  -> list[RouteAnnotation]
```

Phase D 后的数据流：

```text
_build_structural_route_context()
  -> structural_priors: list[StructuralPrior]
  -> deterministic_annotations: list[RouteAnnotation]

LLM refinement prompt
  <- spans
  <- canonical sections / packets / hints / hard facts
  <- structural_priors
  <- deterministic_annotations

LLM result
  -> RefinedAnnotation[]

validator
  <- LLM result
  <- spans
  <- structural_priors
  <- deterministic_annotations

merge
  -> final annotations: list[RouteAnnotation]

FieldRouteIR
  -> structural_priors
  -> annotations
```

## 9. Stage 2 API 改造

### 9.1 替换 `_build_deterministic_priors`

建议重命名为：

```python
def _build_structural_route_context(
    self,
    spans: list[SpanIR],
    canonical_input: CanonicalCompileInput,
) -> tuple[list[StructuralPrior], list[RouteAnnotation]]:
```

返回：

1. `structural_priors`：所有 deterministic structural context；
2. `deterministic_annotations`：真正确定的最终 route annotations。

### 9.2 应迁移为 StructuralPrior 的内容

这些情况必须生成 `StructuralPrior`，不能生成 `RouteAnnotation`：

1. 没有 backing packet 的 section-only context；
2. neutral packet 且没有 matching route prior；
3. 多 packet section 中只提供弱上下文的 section-level prior；
4. 不是确定性 semantic contract 的 packet type context；
5. 只作为 evidence 的 section title / section field hint。

### 9.3 可以保留为 RouteAnnotation 的内容

这些情况可以继续生成 deterministic `RouteAnnotation`：

1. runtime input contract；
2. required output contract；
3. 明确设计为 deterministic 的 exact route prior；
4. 已经过 canonical hard fact 验证的结构性 adapter fact。

不要把 failure handling 放入 deterministic set。failure condition 和 handler 语义仍由 LLM route 决定。

## 10. Prompt Builder 改造

当前：

```python
build_adapter_guided_user_prompt(spans, canonical_input, priors)
```

改为：

```python
build_adapter_guided_user_prompt(
    spans,
    canonical_input,
    structural_priors,
    deterministic_annotations,
)
```

payload 结构：

```json
{
  "spans": [],
  "structural_priors": [],
  "deterministic_annotations": [],
  "allowed_schema": {}
}
```

prompt 需要明确说明：

```text
structural_priors 是证据，不是最终答案。
deterministic_annotations 是已经接受的语义决策。
除非要添加一个不同且允许的 multi-label annotation，否则不要重复 deterministic_annotations。
对于 neutral structural prior，只有源文本证据支持时才输出 semantic annotation。
```

## 11. Validator 改造

当前：

```python
validate(llm_result, spans, canonical_input, priors)
```

改为：

```python
validate(
    llm_result,
    spans,
    canonical_input,
    structural_priors,
    deterministic_annotations,
)
```

validator 职责：

1. 检查 span 是否存在；
2. 检查 field / role / construct / slot 是否在 allowed schema 中；
3. 检查 executable contract；
4. 检查 provenance 是否能对齐 span / structural prior / packet；
5. 拒绝伪造 source id；
6. 诊断与 deterministic annotation 的真实语义冲突；
7. 对非 neutral 语义冲突发诊断，pipeline 继续运行。

冲突策略：

```text
neutral structural prior vs LLM annotation
  -> 不算冲突

deterministic annotation vs LLM same semantic key
  -> 如果 key 相同且合法，则替换

两个真实 non-neutral annotation 的 executable 状态互斥
  -> 发 route_refinement_conflict 诊断，pipeline 继续

schema 非法 / unknown span / illegal role / fabricated evidence
  -> reject；必要时 fail-fast
```

如果当前 validator 仍保留 `fallback_triggered`，需要单独决定是否继续保留。它不能静默推断 semantic replacement。

## 12. Merge 算法

输入：

```text
deterministic_annotations: list[RouteAnnotation]
validated.accepted: list[RefinedAnnotation]
structural_priors: list[StructuralPrior]
```

算法：

1. `merged = list(deterministic_annotations)`。
2. 遍历 accepted LLM annotation：
   - span 不存在则 reject；
   - schema 非法则 reject；
   - LLM 没给 provenance 时，从 matching `StructuralPrior` 补 provenance；
   - semantic key 相同则替换；
   - semantic key 不同则作为真实 multi-label annotation append。
3. 不再扫描 `metadata["prior_resolution"]`。
4. 不需要从 `merged` 删除 structural prior，因为 structural prior 不进入 `merged`。
5. 对最终 `merged` 做 conflict diagnostic。

semantic key：

```text
(span_id, field, semantic_role, construct_target, slot_target)
```

provenance lookup：

```python
prior_by_sid: dict[str, list[StructuralPrior]]
```

## 13. Legacy Route Lists 同步规则

旧六字段列表仍存在：

```text
identity, audience, rules, domain, integrations, behavior
```

Phase D 规则：

```text
legacy lists 只从最终 RouteAnnotation 同步。
structural_priors 不写入 legacy lists。
```

也就是说 `_sync_legacy_routes_from_annotations()` 应忽略 `structural_priors`。

如果某些下游仍依赖 legacy lists 做 resource extraction，应通过 deterministic resource annotations 支撑，而不是通过 neutral priors 支撑。

## 14. 下游契约

### Stage 4 Flow Assembler

消费：

```text
routes.annotations
```

不能消费：

```text
routes.structural_priors
```

### Stage 5 Block Assembler

同 Stage 4。

### Stage 7 Step Extractor

executable behavior set 只能从最终 annotations 得到：

```python
routes.get_executable_behavior_span_ids()
routes.get_non_executable_behavior_span_ids()
```

Phase D 后，这两个集合里不应再出现 neutral pending annotation。

现有 executable-wins 防御可以保留，但不应再是主要正确性机制。

### Reports / Checkpoints

报告可以展示 structural priors，但必须标注：

```text
结构证据，不是语义路由决策。
```

## 15. 迁移步骤

### Step 1：新增类型

修改 `src/nl2spl/ir/field_route_ir.py`：

1. 新增 `StructuralPrior`；
2. 新增 `FieldRouteIR.structural_priors`；
3. 更新 docstring。

### Step 2：拆分 builder 输出

修改 `stage2_field_router.py`：

1. 将 `_build_deterministic_priors` 改为 `_build_structural_route_context`；
2. 返回 `(structural_priors, deterministic_annotations)`；
3. neutral branches 改为生成 `StructuralPrior`；
4. 真实 deterministic annotations 继续生成 `RouteAnnotation`。

### Step 3：更新 prompt payload

修改 `stage2_field_router_prompt.py`：

1. 替换 `_prior_to_dict` 或新增 `_structural_prior_to_dict`；
2. payload 增加 `structural_priors`；
3. payload 增加 `deterministic_annotations`；
4. 更新测试中对 payload key 的断言。

### Step 4：更新 validator

修改 `stage2_field_router_validator.py`：

1. 接收 `structural_priors` 和 `deterministic_annotations`；
2. provenance 检查使用 structural priors；
3. conflict 检查只比较真实 annotations；
4. 不再依赖 metadata 字符串。

### Step 5：更新 merge

修改 `stage2_field_router.py`：

1. `_merge_llm_refinement` 接收 structural priors 和 deterministic annotations；
2. 删除 `_is_pending_neutral_prior`；
3. 不再根据 neutral metadata 做替换；
4. conflict diagnostics 只基于最终 annotations。

### Step 6：更新 checkpoint

Stage 2 checkpoint 应包含：

```json
{
  "routes": {
    "annotations": [],
    "structural_priors": []
  },
  "llm_refinement": {}
}
```

### Step 7：更新测试

按第 16 节补充和更新测试。

## 16. 测试计划

### 16.1 类型契约测试

添加或更新 Stage 2 测试：

1. neutral packet 生成 `StructuralPrior`，不生成 `RouteAnnotation`；
2. weak section context 生成 `StructuralPrior`，不生成 `RouteAnnotation`；
3. runtime input packet 仍生成 deterministic `RouteAnnotation`；
4. required output packet 仍生成 deterministic `RouteAnnotation`。

### 16.2 Prompt Payload 测试

更新 prompt payload 测试。

期望 keys：

```text
spans
structural_priors
deterministic_annotations
allowed_schema
```

断言 structural prior entry 包含：

```text
span_id
source_section_id
source_packet_id
suggested_field
prior_kind
confidence
```

### 16.3 Merge 测试

旧 Phase A neutral replacement 测试需要改写。

Phase D 前：

```text
neutral RouteAnnotation 被 LLM RouteAnnotation 替换
```

Phase D 后：

```text
neutral StructuralPrior 不进入 merged annotations
LLM RouteAnnotation 只出现一次
```

期望：

```text
len(routes.get_annotations("s13")) == 1
routes.get_annotations("s13")[0].executable is True
```

### 16.4 Conflict 测试

使用两个真实 annotations，而不是 structural priors：

```text
prior annotation: failure_mode executable=false
LLM annotation: process_step executable=true
```

期望：

```text
产生 route_refinement_conflict diagnostic
pipeline 继续运行
```

### 16.5 Stage 7 回归测试

构造：

```text
structural_priors 包含 s13 neutral_context
annotations 包含 s13 process_step executable=true
```

期望：

```text
get_executable_behavior_span_ids() 包含 s13
get_non_executable_behavior_span_ids() 不包含 s13
D6 guard 不丢弃该 step
```

### 16.6 Demo 回归测试

运行：

```powershell
.venv\Scripts\python.exe examples\usage.py
```

期望：

```text
examples/output/demo/final_spl.txt
  [MAIN_FLOW]
      COMMAND-...
  [END_MAIN_FLOW]
```

## 17. 验收标准

1. `RouteAnnotation` 不再承载 neutral pending state。
2. `metadata["prior_resolution"]` 不再是正确性的必要条件。
3. `FieldRouteIR.structural_priors` 存在，并出现在 Stage 2 checkpoint。
4. LLM prompt 分别接收 structural priors 和 deterministic annotations。
5. validator 使用 structural priors 做 provenance 检查，但不把它当 semantic truth。
6. Stage 4/5/7 只消费最终 annotations。
7. demo 中 LLM 将 process spans 标为 executable 时，final SPL main flow 非空。
8. failure condition spans 保持 non-executable，并继续生成 exception flows。
9. 不增加 renderer fallback。
10. 不增加 rule-based process-step keyword table。
11. 不增加 LLM failure fallback。

## 18. 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| Prompt payload 测试失败 | 预期内，因为 payload contract 改变 | 明确更新测试 |
| 下游仍依赖 legacy field lists | 可能丢 span | 用 deterministic resource annotations 支撑，审计 route list consumer |
| validator provenance 检查过严 | LLM annotation 被误拒 | structural priors 作为 provenance context |
| 真实 multi-label 被误判为冲突 | 产生误诊断 | 只对 non-neutral 且 executable 状态互斥的情况诊断 |
| checkpoint consumer 只认 annotations | 工具可能不兼容 | 保留 annotations，同时新增 structural_priors |

## 19. 推荐实施顺序

1. 新增 `StructuralPrior` 和 `FieldRouteIR.structural_priors`。
2. 拆分 `_build_deterministic_priors` 输出。
3. 更新 prompt payload 和相关测试。
4. 更新 validator 签名和 provenance 检查。
5. 更新 merge 签名，删除 neutral metadata replacement。
6. 更新 checkpoint 和 legacy route list 同步。
7. 跑 Stage 2 focused tests。
8. 跑 Stage 7 regression tests。
9. 跑 demo，检查 final SPL。
10. 跑 full tests。

## 20. 验证命令

```powershell
.venv\Scripts\python.exe -m pytest tests\unit\test_adapter_guided_fieldroute_refinement.py -q --basetemp=.pytest-tmp-phase-d-stage2
```

```powershell
.venv\Scripts\python.exe -m pytest tests\unit\test_stage7_irs_step_extraction.py tests\unit\pipeline\stages\test_worker_plan_normalizer.py -q --basetemp=.pytest-tmp-phase-d-stage7
```

```powershell
.venv\Scripts\python.exe examples\usage.py
```

```powershell
.venv\Scripts\python.exe -m pytest -q --basetemp=.pytest-tmp-phase-d-full
```
