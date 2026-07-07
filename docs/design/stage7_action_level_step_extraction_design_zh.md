# Stage 7 Action-Level Step Extraction 设计文档

## 1. 背景

当前 NL2SPL Pipeline 在 demo `internal_comms` 中暴露出一个 Stage 7 架构缺口：同一个 source span 同时包含多个可执行动作，并且这些动作应该落到不同 command type 时，Stage 7 没有稳定地拆分、归属和 materialize。

典型例子来自 `examples/input/internal_comms.txt` 的 reusable process：

```text
If sources are needed and available, retrieve them using approved source
recipes. Maintain provenance for externally sourced facts.
```

该文本在当前 artifact 中对应 `s16`。语义上它至少包含两个 action：

```text
action A:
  retrieve them using approved source recipes
  expected command type: CALL_API

action B:
  Maintain provenance for externally sourced facts
  expected command type: GENERAL_COMMAND
```

当前 final SPL / updated SPL 中却出现：

```text
COMMAND [Retrieve sources using approved source recipes ... RESULT source_evidence_set SET]
CALL ApprovedSourceRecipesAPI
```

并且没有出现：

```text
COMMAND [Maintain provenance for externally sourced facts ...]
```

这说明 Stage 7 同时出现了两个问题：

1. API-covered operation 被普通 `GENERAL_COMMAND` 和 `CALL_API` 双重 materialize。
2. 同一 span 内的 residual normal action 没有被 materialize。

这不是 renderer 问题，也不是 SPL Editing repair 问题；它是 Stage 7 从 span 生成 executable step 时缺少 action-level 分解和 ownership 的问题。

## 2. 当前错误链路

### 2.1 Source span 具有混合 action

`s16` 同时表达：

```text
retrieve them using approved source recipes
Maintain provenance for externally sourced facts
```

前者应由 external capability / API lowering authority 处理；后者应由普通 command materialization 处理。

### 2.2 ConstructPlan 已经识别出 API 只覆盖部分行为

当前 `ConstructPlan` 中，`APICallDemand` 包含：

```text
action_text = retrieve them using approved source recipes
behavior_lowering_policy = api_call_augments_behavior
consumes_behavior_span_ids = ["s16"]
residual_behavior_span_ids = ["s16"]
operation_coverage:
  source_span_id = s16
  operation_surface = retrieve them using approved source recipes
```

这说明 ConstructPlan 层已经意识到 API call 不是整个 span 的全部行为。

### 2.3 Stage 7 普通 StepExtractor 先生成 span-level GENERAL_COMMAND

Stage 7 普通 step extraction 对 `s16` 生成：

```text
GENERAL_COMMAND Retrieve sources using approved source recipes
```

这个 step 覆盖了 API operation，但没有覆盖 residual provenance action。

### 2.4 API materializer 再追加 CALL_API

`stage7_step_extractor/api_call_materializer.py` 根据 `APICallDemand` 再追加：

```text
CALL_API ApprovedSourceRecipesAPI
```

因此 `retrieve using approved source recipes` 被重复 materialize。

### 2.5 Sanitizer 试图裁剪 fallback，但失败

当前 sanitizer 的思路是：

```text
API call consumes part of source span
-> 尝试从已有 GENERAL_COMMAND StepIR.text 中删除 API operation
-> 保留 residual text
```

但它依赖 source span 的 character offsets 去裁剪 `StepIR.text`。这不可靠，因为：

```text
source span text:
  retrieve them using approved source recipes. Maintain provenance...

StepIR.text:
  Retrieve sources using approved source recipes.
```

`StepIR.text` 已经经过 paraphrase，和 source span 文本不再有相同 offset。结果是：

```text
fallback GENERAL_COMMAND 没有被删除；
residual provenance action 没有被生成。
```

## 3. High-Level Root Cause

根因不是 `CALL_API` 的单点 bug，而是 Stage 7 的抽象层级不够：

```text
当前模型:
  source span -> StepIR

需要升级为:
  source span -> executable actions -> StepIR
```

当一个 span 中混杂多条 action，且 action 属于不同 command type 时，span-level extraction 会天然不稳定。

高风险组合包括：

```text
GENERAL_COMMAND + CALL_API
GENERAL_COMMAND + REQUEST_INPUT
GENERAL_COMMAND + INVOKE_WORKER
CALL_API + provenance / validation / normalization residual
REQUEST_INPUT + follow-up normal action
```

如果没有 action-level ownership，系统只能靠后置字符串裁剪修正重复或残缺。这种方式无法作为架构边界。

## 4. 设计目标

### 4.1 必须达成

Stage 7 应能稳定处理一个 source span 内的多 action、多 command type 情况：

```text
s16
  action A -> CALL_API
  action B -> GENERAL_COMMAND
```

输出应为：

```text
CALL ApprovedSourceRecipesAPI
COMMAND Maintain provenance for externally sourced facts ...
```

不得输出：

```text
COMMAND Retrieve sources using approved source recipes
CALL ApprovedSourceRecipesAPI
```

### 4.2 Authority 边界

不同 action 的 materialization authority 必须清楚：

```text
API action:
  owner = APICallStepMaterializer

normal action:
  owner = GeneralCommandStepMaterializer

worker invocation action:
  owner = WorkerInvocationMaterializer

request input action:
  owner = RequestInputStepMaterializer
```

普通 StepExtractor 不得整体消费已被 API / worker / request-input authority claim 的 span。

### 4.3 不做的事情

本设计不要求：

```text
1. 立即重写所有 Stage 7 LLM prompt。
2. 立即引入生产 LLM action segmentation。
3. 修改 SPL grammar。
4. 让 renderer 或 Gate 负责语义去重。
5. 让 SPL Editing repair verifier 修复 pipeline-level duplicate step。
```

## 5. 核心设计：ExecutableActionIR / WorkerActionPlanIR

### 5.1 新增中间层

建议在 Stage 7 前半段引入 action-level plan：

```python
@dataclass(frozen=True)
class SourceRangeIR:
    source_span_id: str
    char_start: int | None
    char_end: int | None
    relation: Literal[
        "direct",
        "normalized_whitespace",
        "derived",
        "ambiguous",
    ]


@dataclass(frozen=True)
class ExecutableActionIR:
    action_id: str
    action_kind: Literal[
        "source_slice",
        "residual_slice",
        "construct_derived",
        "handoff_derived",
    ]

    source_span_ids: tuple[str, ...]
    source_section_id: str | None
    source_packet_id: str | None
    coverage_refs: tuple[str, ...]
    covered_ranges: tuple[SourceRangeIR, ...]
    excluded_ranges: tuple[SourceRangeIR, ...] = ()

    action_text: str
    normalized_action_key: str

    command_type: Literal[
        "GENERAL_COMMAND",
        "CALL_API",
        "REQUEST_INPUT",
        "INVOKE_WORKER",
        "DISPLAY_MESSAGE",
    ]

    owning_authority: str
    source_construct_demand_id: str | None
    source_handoff_id: str | None
    capability_intent_id: str | None
    worker_promotion_id: str | None

    flow_ref: str
    block_ref: str

    input_hints: tuple[str, ...] = ()
    output_hints: tuple[str, ...] = ()
    output_policy: Literal[
        "no_output",
        "produces_output",
        "refines_existing_output",
        "validates_existing_output",
        "unknown",
    ] = "unknown"

    coverage_status: Literal[
        "exact",
        "residual",
        "derived",
        "ambiguous",
        "uncovered",
    ]
    metadata: Mapping[str, object] = field(default_factory=dict)
```

并按 worker scope 聚合：

```python
@dataclass(frozen=True)
class WorkerActionPlanIR:
    main_worker_id: str
    worker_actions: Mapping[str, tuple[ExecutableActionIR, ...]]
    coverage_reports: tuple[ActionCoverageReportIR, ...] = ()
    diagnostics: tuple[CompileDiagnostic, ...] = ()
```

同时新增只读审计对象：

```python
@dataclass(frozen=True)
class ActionCoverageReportIR:
    report_id: str
    source_span_id: str
    covered_ranges: tuple[SourceRangeIR, ...]
    uncovered_ranges: tuple[SourceRangeIR, ...]
    overlapping_ranges: tuple[SourceRangeIR, ...]
    action_ids: tuple[str, ...]
    status: Literal[
        "fully_partitioned",
        "has_uncovered_residual",
        "has_incompatible_overlap",
        "ambiguous",
    ]
    diagnostics: tuple[str, ...] = ()
```

`ActionCoverageReportIR` 必须先以 read-only intermediate 落地，再逐步切换 API / general materializers。它不是 IRS construct，不生成 repair affordance，也不直接 materialize `StepIR`；它只解释 source span 的 executable action partition 是否闭合。

### 5.2 示例

对于 `s16`，应形成：

```text
ExecutableActionIR:
  action_id = act_api_s16_...
  action_kind = source_slice
  source_span_ids = (s16,)
  action_text = retrieve them using approved source recipes
  normalized_action_key = retrieve_using_approved_source_recipes
  command_type = CALL_API
  owning_authority = stage7.api_call_materializer
  source_construct_demand_id = api_call_19e71fc8b204a57a
  source_handoff_id = None
  output_policy = no_output
  coverage_status = exact

ExecutableActionIR:
  action_id = act_general_s16_...
  action_kind = residual_slice
  source_span_ids = (s16,)
  action_text = Maintain provenance for externally sourced facts
  normalized_action_key = maintain_provenance_for_externally_sourced_facts
  command_type = GENERAL_COMMAND
  owning_authority = stage7.general_command_materializer
  source_construct_demand_id = None
  source_handoff_id = None
  output_policy = no_output
  coverage_status = residual
```

MVP 中，`Maintain provenance...` 这种 residual provenance action 的默认策略必须冻结为：

```text
output_policy = no_output
outputs = []
metadata.semantic_effect = provenance_maintenance
```

除非 source span 或 upstream resource contract 明确要求产生或更新某个 output，否则不得默认伪造：

```text
outputs = ["source_evidence_set"]
outputs = ["provenance_record"]
outputs = ["provenance_log"]
```

## 6. Stage 7 修改方案

### 6.1 Action Segmentation Builder

新增 Stage 7 action segmentation builder：

```text
inputs:
  spans
  span_by_id
  worker_flow_plan
  worker_block_plan
  construct_plan
  api_materialization_plan
  worker_plan
  route annotations

output:
  WorkerActionPlanIR
```

职责：

```text
1. 从 ConstructPlan 中读取 APICallDemand.operation_coverage。
2. 为每个 API call demand 创建 CALL_API action。
3. 从同一 source span 中计算 residual text。
4. residual text 非空时创建 GENERAL_COMMAND action。
5. 对未被任何 typed demand 消费的 executable span，创建 GENERAL_COMMAND action。
6. 对 REQUEST_INPUT / INVOKE_WORKER 等 typed demands，创建对应 action。
7. 记录 overlap / uncovered / ambiguous diagnostics。
```

`span_by_id` 是硬性输入，不是实现细节。凡是需要从 source coverage 推导 residual action 的实现，都必须消费 original source span text；不得从 paraphrased `StepIR.text` 反推 residual。

### 6.1.1 API Residual Action Projector

短期修复和长期 action plan 都需要一个确定性的 residual projector：

```python
class APIResidualActionProjector:
    def project(
        self,
        *,
        call: APICallDemand,
        span_by_id: Mapping[str, SpanIR],
        placement: APICallPlacementIR,
    ) -> APIResidualActionProjection: ...


@dataclass(frozen=True)
class APIResidualActionProjection:
    call_action: ExecutableActionIR | None
    residual_actions: tuple[ExecutableActionIR, ...]
    coverage_report: ActionCoverageReportIR
    diagnostics: tuple[CompileDiagnostic, ...]
```

规则：

```text
1. API covered operation 来自 APICallDemand.operation_coverage。
2. residual text 必须从 original source span text 删除 covered ranges 后得到。
3. projection 不读取 StepIR.text。
4. coverage ambiguous 时不得静默生成 residual action。
5. residual action 的 flow_ref/block_ref 默认复用 API placement，除非 block partition 明确给出不同 placement。
```

### 6.2 GeneralCommand Materializer

普通 command materializer 改为只消费：

```text
ExecutableActionIR.command_type == GENERAL_COMMAND
```

不再对整个 span 自由生成 command。

如果仍需要 LLM 生成 command wording，则 prompt 输入应是 action slice，而不是完整 source span：

```text
Action text:
  Maintain provenance for externally sourced facts

Allowed command type:
  GENERAL_COMMAND

Do not generate API call / worker invocation / request input.
```

### 6.3 APICall Materializer

API materializer 改为消费：

```text
ExecutableActionIR.command_type == CALL_API
```

不再在已有 `worker_step_plan` 后 append step 再 sanitize fallback。

短期兼容期可以保留 `_sanitize_general_command_fallbacks()`，但它只能作为 migration guard，不应成为主路径。

### 6.3.1 CALL_API 双来源合流规则

当前代码中 `CALL_API` 至少有两条来源：

```text
1. APICallDemand
   -> direct external capability call

2. WorkerHandoffIR(mode="api_call")
   -> handoff-shaped API call
```

Action-level 迁移必须统一这两条来源，不能让它们分别独立 append `CALL_API`。

建议唯一性 key：

```text
(
  source_span_ids,
  normalized_operation_surface,
  command_type,
  owning_authority_family
)
```

冲突规则：

```text
same operation claimed by APICallDemand and WorkerHandoffIR(mode="api_call")
-> emit duplicate_api_action_claim diagnostic
-> do not silently materialize two CALL_API steps
```

如果二者语义不同，必须通过不同 `normalized_action_key`、不同 source range 或不同 demand/handoff evidence 证明；否则按 duplicate 处理。

### 6.4 REQUEST_INPUT / INVOKE_WORKER

同样应迁移为 action-level：

```text
REQUEST_INPUT action -> RequestInputStepMaterializer
INVOKE_WORKER action -> WorkerInvocationMaterializer
```

这可以避免未来出现：

```text
Ask only highest-value clarifying questions and then record...
```

被错误压成一个 `REQUEST_INPUT` 或一个 `GENERAL_COMMAND`。

## 7. Coverage Partition Validator

Stage 7 应新增 coverage validator，按 source span 检查 action partition：

```text
for each source span:
  typed action coverage
  general residual coverage
  uncovered executable residual
  overlapping incompatible coverage
```

这个 validator 同时替代或扩展当前 Stage 7 的 span-level unmapped detection。旧语义是：

```text
span_id covered if any StepIR.source_span_ids contains span_id
```

新语义必须是：

```text
source span partition covered iff every executable action slice is owned by exactly one materialized action or explicitly diagnosed
```

因此，`CALL_API.source_span_ids = ["s16"]` 不能再让整个 `s16` 自动视为 fully covered；它只能证明 `s16` 中 API action 的 coverage 已满足。

### 7.1 必须拒绝或诊断的情况

```text
1. 同一 operation 同时被 CALL_API 和 GENERAL_COMMAND 覆盖。
2. residual_behavior_span_ids 非空，但没有 residual GENERAL_COMMAND action。
3. API-only span 被普通 GENERAL_COMMAND 完整消费。
4. action coverage overlap 且 owning_authority 不兼容。
5. ambiguous coverage 被静默 materialize。
```

### 7.2 可接受情况

```text
1. CALL_API action + GENERAL_COMMAND residual action。
2. CALL_API-only action。
3. GENERAL_COMMAND-only action。
4. REQUEST_INPUT action + GENERAL_COMMAND residual action。
5. INVOKE_WORKER action + normal residual action。
```

## 8. 短期修复路径

在完整 `ExecutableActionIR` 落地前，可以先修当前 bug。

### 8.1 修复原则

对于 `APICallDemand.behavior_lowering_policy == api_call_augments_behavior`：

```text
不要用 source span offsets 裁剪 paraphrased StepIR.text。
```

应改为：

```text
1. materialize_direct_api_calls 必须接收 spans/span_by_id，或先调用独立 APIResidualActionProjector。
2. 基于 original source span text 和 operation_coverage 计算 residual text。
3. 如果 residual text 非空：
   - 删除覆盖同一 API operation 的 GENERAL_COMMAND fallback；
   - 生成或替换为 residual GENERAL_COMMAND；
   - residual step 的 text 来自 original source span residual；
   - flow_ref/block_ref 默认复用 API placement；
   - outputs = []，除非 output_policy 显式声明。
4. 如果 residual text 为空：
   - 删除 covered fallback。
5. 如果 coverage ambiguous：
   - 不静默 materialize；
   - 生成 diagnostic。
```

短期接口必须避免“设计上依赖 original span，但函数签名拿不到 spans”的情况。推荐任一方案：

```python
materialize_direct_api_calls(
    worker_step_plan,
    construct_plan,
    api_materialization_plan,
    api_call_placements,
    resources,
    spans,
)
```

或：

```python
APIResidualActionProjector.project(
    call=call,
    span_by_id=span_by_id,
    placement=placement,
)
```

### 8.2 示例短期结果

输入：

```text
retrieve them using approved source recipes. Maintain provenance for externally sourced facts.
```

输出：

```text
CALL ApprovedSourceRecipesAPI
COMMAND Maintain provenance for externally sourced facts
```

### 8.3 短期限制

短期修复仍然是 API-specific sanitizer，不应被视为最终架构。它只能关闭当前 regression，并为 action-level Stage 7 改造争取时间。

## 9. 长期迁移路径

建议分阶段实施：

### S7A: Characterization

锁定当前错误行为：

```text
1. s16 同时生成 GENERAL_COMMAND retrieve 和 CALL_API。
2. Maintain provenance 未生成 executable step。
3. ConstructPlan policy 是 api_call_augments_behavior。
```

这些测试先作为 current-behavior lock 或 pending target assertions。

### S7B: Short-Term API Residual Fix

S7B 必须拆成可验收的小步：

```text
S7B.1 Characterize current bug
  - 构造 s16 fixture：
    source text = "retrieve them using approved source recipes. Maintain provenance..."
    LLM StepIR fallback = "Retrieve sources using approved source recipes."
    APICallDemand.policy = api_call_augments_behavior
  - 断言当前输出包含 duplicate API operation 且缺 residual provenance command。

S7B.2 Add residual projector
  - 输入：APICallDemand + span_by_id + APICallPlacementIR。
  - 输出：
    covered_api_operation_action
    residual_general_action or diagnostic
  - 不读取 StepIR.text。

S7B.3 Change api_call_materializer
  - 删除覆盖 API operation 的 GENERAL_COMMAND fallback。
  - 如果 residual action exists：
    新增 GENERAL_COMMAND residual StepIR。
    text 来自 original source span residual。
    flow_ref/block_ref 复用 API placement，除非 block partition 明确另有位置。
    outputs = [] unless output_policy is explicit。
  - 如果 coverage ambiguous：
    不 materialize residual silently。
    emit stage7_api_residual_coverage_ambiguous。

S7B.4 Update unmapped detection
  - 不再因 CALL_API 引用 s16 就认为整个 s16 covered。
  - mixed span 的 residual coverage 由 ActionCoverageReport 判定。
```

### S7C: Introduce Read-Only Action Projection

新增模型和只读 projection：

```text
WorkerActionPlanIR
ExecutableActionIR
ActionCoverageReport
```

初期只输出 debug/intermediate，不改变 StepIR。它的第一目标是解释现有 StepIR coverage，暴露 duplicate / missing residual diagnostics，而不是立刻替换 materialization。

### S7D: Route API Lowering Through Actions

让 API materializer 消费 `CALL_API` action。

验收：

```text
api_call_materializer 不再 append 后 sanitize fallback 作为主路径。
direct APICallDemand 和 WorkerHandoffIR(mode="api_call") 的重复 CALL_API claim 能被检测。
```

### S7E: Make Unmapped Detection Action-Aware

将 Stage 7 unmapped-span detection 从 span-level coverage 升级为 action partition coverage。

验收：

```text
CALL_API 覆盖 s16 的 API action，不代表 s16 的 residual action 已覆盖。
```

### S7F: Route General Commands Through Actions

普通 StepExtractor 改为消费 `GENERAL_COMMAND` action。

验收：

```text
已被 typed action claim 的 span 不再被整体生成 GENERAL_COMMAND。
```

### S7G: Coverage Validator Gate

启用 action partition validator。先以 warning/report 方式观察，再逐步升级为 fail-fast。

验收：

```text
duplicate API operation -> fail/diagnostic
missing residual action -> fail/diagnostic
ambiguous coverage -> fail/diagnostic
```

### S7H: Extend To REQUEST_INPUT / INVOKE_WORKER / API Handoff

把 request-input、worker-invocation，以及 `WorkerHandoffIR(mode="api_call")` 的 mixed span case 纳入 action-level source claims。

## 10. 验收标准

### 10.1 Demo Case

`internal_comms` 中 `s16` 应输出：

```text
CALL ApprovedSourceRecipesAPI
COMMAND Maintain provenance for externally sourced facts ...
```

不得输出：

```text
COMMAND Retrieve sources using approved source recipes
CALL ApprovedSourceRecipesAPI
```

### 10.2 Regression Matrix

必须覆盖：

```text
1. API-only span -> only CALL_API。
2. API + provenance residual -> CALL_API + residual GENERAL_COMMAND。
3. API + validation residual -> CALL_API + validation GENERAL_COMMAND。
4. API operation paraphrased by ordinary extractor -> no duplicate fallback。
5. residual coverage ambiguous -> diagnostic, not silent loss。
6. same operation covered by CALL_API and GENERAL_COMMAND -> diagnostic/fail。
7. REQUEST_INPUT + residual normal action -> two actions。
8. INVOKE_WORKER + residual normal action -> two actions。
9. CALL_API source span does not mark the full source span as fully covered。
10. API residual command has source-backed provenance pointing to the same source span and residual range。
11. residual GENERAL_COMMAND has outputs=[] unless explicit output_policy says otherwise。
12. fallback GENERAL_COMMAND removal does not remove unrelated GENERAL_COMMAND in the same block。
13. direct APICallDemand and WorkerHandoffIR(mode="api_call") cannot materialize duplicate CALL_API for the same operation。
14. action plan payload is deterministic and checkpointable。
15. ProducerIndex ignores no-output residual side-effect commands。
```

### 10.3 Authority Checks

```text
1. API action must be materialized only by API materializer.
2. General residual action must be materialized only by general command materializer.
3. Renderer must not perform semantic dedup.
4. Gate must not decide residual behavior.
5. SPL Editing repair verifier must not suppress duplicate pipeline output.
6. Stage 7 IRS sees materialized StepIR only; it does not create or repair action partition.
7. ProducerIndex remains producer authority; action coverage does not fabricate producers.
```

## 11. Open Questions

### 11.1 Action segmentation source

MVP 可以基于 `ConstructPlan.operation_coverage` 和 deterministic residual extraction。

长期是否允许 LLM 做 action segmentation，需要单独 gate：

```text
LLM may propose action segments,
but deterministic validator must verify coverage, ownership, and command type authority.
```

### 11.2 Residual output policy MVP decision

`Maintain provenance for externally sourced facts` 的 MVP output policy 不再作为 open question。默认决策是：

```text
command_type = GENERAL_COMMAND
output_policy = no_output
outputs = []
metadata.semantic_effect = provenance_maintenance
```

禁止默认行为：

```text
outputs = ["source_evidence_set"]
outputs = ["provenance_record"]
outputs = ["provenance_log"]
```

只有 source span、resource contract、ConstructPlan demand 或显式 action output policy 证明需要产生/更新某个 output 时，才允许：

```text
output_policy = refines_existing_output
or
output_policy = produces_output
```

这样可以避免把“补 residual action”误伤成伪 producer，或引入新的 `missing_output_producer` 问题。

### 11.3 Interaction with ProducerIndex

如果 residual action 没有 output，ProducerIndex 不应把它当作 producer。

如果 residual action 更新已有 output，则需要明确是：

```text
produces source_evidence_set
or refines source_evidence_set
or validates source_evidence_set
```

这应由 Stage 7 output policy 决定。

## 12. 结论

当前 bug 暴露的是 Stage 7 的架构边界问题：

```text
span-level Step Extraction 无法正确表达 mixed executable actions。
```

短期应修 `api_call_materializer` 的 residual fallback 逻辑，避免 API operation 重复和 residual action 丢失。

长期应引入：

```text
ExecutableActionIR
WorkerActionPlanIR
Coverage Partition Validator
Action-owned materializers
```

把 Stage 7 从：

```text
source span -> StepIR
```

升级为：

```text
source span -> executable actions -> StepIR
```

这样才能系统性解决 `GENERAL_COMMAND + CALL_API`、`REQUEST_INPUT + residual`、`INVOKE_WORKER + residual` 等混合 command type span 的问题。

## 13. 评审收口状态

本设计在进入实施计划前必须保留以下硬边界：

```text
1. 短期 residual fix 必须显式接收 spans/span_by_id，或调用等价 residual projector。
2. unmapped-span detection 必须从 span-level coverage 升级为 action-level coverage。
3. direct APICallDemand 与 WorkerHandoffIR(mode="api_call") 必须有统一 CALL_API action 合流/冲突规则。
4. ExecutableActionIR 必须包含 coverage_refs、ranges、action_kind、output_policy、source_handoff_id 等审计字段。
5. residual provenance action 的 MVP output policy 固定为 no_output，不伪造 producer。
6. ActionCoverageReport 必须先作为 read-only intermediate 落地，再迁移 API/general materializers。
```

若任一条件未满足，本设计只能作为方向性文档，不能作为可执行 implementation baseline。
