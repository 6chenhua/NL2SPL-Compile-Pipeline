# Stage 4/5/7 控制放置与输出绑定边界错位问题

## 1. 背景

在 `examples/input/internal_comms.txt` 的 reusable process 中，有一段连续业务逻辑：

```text
First determine what kind of communication is requested. Then identify which required
fields are still missing. Ask only the highest-value clarifying questions needed to move
forward. If sources are needed and available, retrieve them using approved source
recipes. Maintain provenance for externally sourced facts. When enough required
information is available, produce a draft. If the user asks for revision, revise while re
checking constraints.
```

重新运行 `examples/usage.py` 后，`examples/output/demo/final_spl.txt` 出现了与原始业务逻辑不一致的结果：

```text
COMMAND-3 [COMMAND Maintain provenance for externally sourced facts RESULT source_evidence_set: List [text] SET]

DECISION-1 [IF enough required information is available]
    COMMAND-4 [COMMAND Produce the draft communication artifact ...]
    COMMAND-5 [CALL ApprovedSourceRecipesAPI]
```

这里至少暴露出三个问题：

1. `Maintain provenance for externally sourced facts` 被放到了 API call 之前。
2. `If sources are needed and available` 条件丢失，没有生成对应的 IF block。
3. `Ask only the highest-value clarifying questions needed to move forward` 被投影成顶层 `ALTERNATIVE_FLOW: required information is missing and clarifying questions are needed`，但它更像主流程中的局部 IF block。
4. `Maintain provenance for externally sourced facts` 被错误认定为 `source_evidence_set` 的 producer。

这些问题不是 SPL renderer 的语法渲染问题，而是上游 IR 的 worker ownership、flow/block placement、step 输入输出绑定已经发生了语义漂移。

## 2. 已确认的中间产物事实

### 2.1 Stage 1 当前切分基本正确

当前 `examples/output/demo/stage1_span_slicer.json` 中，相关 span 已经被切分为：

```text
s17:
  text = Ask only the highest-value clarifying questions needed to move forward.
  segmentation_kind = atomic_action_candidate

s18:
  text = If sources are needed and available retrieve them using approved source recipes.
  segmentation_kind = guarded_action
  guard_text_exact = sources are needed and available
  action_text_exact = retrieve them using approved source recipes

s19:
  text = Maintain provenance for externally sourced facts.
  segmentation_kind = atomic_action_candidate

s20:
  text = When enough required information is available produce a draft.
  segmentation_kind = guarded_action
  guard_text_exact = enough required information is available
  action_text_exact = produce a draft
```

因此，本轮问题不是 Stage 1 把 `When enough... produce a draft` 切断造成的。Stage 1 已经能表达 `s18` 与 `s20` 的 guard-action 结构。

### 2.2 Stage 3.5 worker ownership 丢失了 API span

当前 `worker_main.owned_span_ids` 为：

```text
['s15', 's16', 's17', 's19', 's20', 's21', 's23']
```

其中缺少 `s18`。

`s18` 是 API-owned span，后续应由 API materializer 生成 `CALL_API`，因此它不应该再进入 generic `GENERAL_COMMAND` extraction。但它仍然是 executable action，仍然需要 worker/control/block placement。

当前实现把这两类排除混在一起了：

```text
正确：
  API span 不进入 GENERAL_COMMAND extraction。

错误：
  API span 同时失去 worker ownership / flow placement / block placement。
```

### 2.3 Stage 4 把 clarification step 投影为顶层 alternative flow

当前 `examples/output/demo/stage4_flow_assembler.json` 中：

```text
main_flow_spans = [s15, s16, s19, s20, s23]

alternative_flows:
  alt_2:
    condition_text = required information is missing and clarifying questions are needed
    spans = [s17]
```

这说明 `s17` 被 Stage 4 直接归入顶层 `alternative_flows`，而不是主流程中的局部 conditional block。

但原文：

```text
Ask only the highest-value clarifying questions needed to move forward.
```

配合前文：

```text
Then identify which required fields are still missing.
```

更合理的结构是：

```text
IF required information is missing:
  INPUT ask highest-value clarifying questions needed to move forward
```

也就是说，它是主流程中的局部条件区域，而不是 workflow-level alternative route。

### 2.4 Stage 5 没有为 `s18` 生成 IF block

当前 `examples/output/demo/stage5_block_assembler.json` 中：

```text
main_flow_blocks:
  b_1:
    block_type = SEQUENTIAL
    spans = [s15, s16, s19]

  b_2:
    block_type = IF
    condition_text = enough required information is available
    spans = [s20]
```

`s18` 不在任何 block 中，因此 Stage 5 没有机会把：

```text
If sources are needed and available
```

变成对应的 IF block。

### 2.5 Stage 7 API placement 使用了错误兜底

当前 `CALL_API` step 的 StepIR 形态为：

```text
step_id = st_api_8564b1b8dc
command_type = CALL_API
source_span_ids = [s18]
flow_ref = main
block_ref = b_2
outputs = []
pending_response_bindings = {"output_00": "source_evidence_set"}
```

`s18` 本身没有 block ownership，Stage 5 的 API call placement 逻辑通过 `_nearest_main_flow_block()` 选择了后续最近的 main-flow block，即 `b_2`。这导致：

```text
CALL ApprovedSourceRecipesAPI
```

被错误放进：

```text
IF enough required information is available
```

而不是：

```text
IF sources are needed and available
```

这是 silent fallback 掩盖上游 placement 缺失的典型错误。

### 2.6 Stage 7 输出绑定把 provenance action 错认成 producer

当前 `Maintain provenance...` step 的 StepIR 形态为：

```text
step_id = st_4
command_type = GENERAL_COMMAND
text = Maintain provenance for externally sourced facts.
source_span_ids = [s19]
outputs = [source_evidence_set]
flow_ref = main
block_ref = b_1
```

这不符合原文语义。

`Maintain provenance for externally sourced facts` 表达的是维护、记录或保留 provenance 关系，不是创建 `source_evidence_set`。它最多应是：

```text
no_output
records_metadata
refines_existing_output
validates_existing_output
```

不能被反向指定为 required output producer。

## 3. 用户提供并已确认的正确思路

### 3.1 Block planning 应一视同仁处理 executable actions

用户指出：

```text
难道不是所有 COMMAND 在规划 BLOCK 时都一视同仁吗？
```

该判断正确，但需要区分两个层次：

```text
control/block planning:
  所有 executable action 都应参与，包括 GENERAL_COMMAND、CALL_API、REQUEST_INPUT、INVOKE_WORKER 等。

command materialization:
  再根据 action authority 决定具体生成 GENERAL_COMMAND / CALL_API / REQUEST_INPUT / INVOKE_WORKER。
```

因此：

```text
API span 可以不生成 GENERAL_COMMAND，
但不能失去 worker/control/block placement。
```

更准确的 invariant 是：

```text
Block planning input = all executable action spans.
Generic command extraction exclusion must not affect block placement.
```

### 3.2 IF block 与 ALTERNATIVE_FLOW 的区别不是是否有 condition

用户指出 IF block 与 alternative flow 确实相似，关键在于区分何时是 IF block，何时是 ALTERNATIVE_FLOW。

修正后的定义：

```text
IF BLOCK:
  主流程中的局部条件区域。
  可以包含一个或多个连续步骤。
  条件满足后执行该局部区域，然后回到同一主流程。

ALTERNATIVE_FLOW:
  workflow-level 替代路线、修订路径、用户选择路径或外部替代分支。
  不是局部 gate，也不是执行完一个局部动作后自然回到原位置的普通条件块。
```

当前例子中：

```text
Ask only the highest-value clarifying questions needed to move forward.
```

如果系统推断其条件是：

```text
required information is missing
```

则应形成：

```text
IF required information is missing:
  INPUT ask highest-value clarifying questions needed to move forward
```

而不是：

```text
ALTERNATIVE_FLOW: required information is missing and clarifying questions are needed
```

相反：

```text
If the user asks for revision, revise while re-checking constraints.
```

更接近 workflow-level alternative flow，因为 revision 是用户触发的替代路径。

### 3.3 Step 输入输出绑定必须基于 source text 与 SymbolTable 的关系匹配

用户指出，产生不该产生的输出，本质是没有抓住 Step 输入/输出判断标准：

```text
应将原文与符号表中的已有变量做对比；
如果原文提到相应变量或明确表达对应语义关系，才认为引用/产生了变量；
不能因为系统需要某个 required output，就强制认为某 step 产生它。
```

该判断正确。更完整的标准应为：

```text
1. 原文是否提到变量名、稳定别名或可审计的语义等价表达？
2. 原文表达的是 produce / consume / refine / validate / record metadata / no-output 中哪一种关系？
3. 只有 source-backed relation 能建立 input/output binding。
4. required output 不能反向强行指定 producer。
```

例如：

```text
Produce a draft
  => produces draft_communication_artifact

Record a short assumptions log and set completion status
  => produces assumptions_log, completion_status

Maintain provenance for externally sourced facts
  => records/refines provenance metadata
  => does not produce source_evidence_set

Retrieve sources using approved source recipes
  => may produce evidence/source result only if the API/function return contract or source text supports it
  => if API return contract is unknown, keep binding deferred rather than claiming source_evidence_set is produced
```

## 4. 建议的修复方案

### 4.1 P0：锁定当前错误

先增加 characterization / regression tests，明确当前错误链路：

```text
1. s18 是 API span，但必须仍有 worker/control/block placement。
2. s18 的 guard "sources are needed and available" 必须生成 local IF block。
3. s17 clarification 不应成为顶层 ALTERNATIVE_FLOW。
4. s19 Maintain provenance 不得 produces source_evidence_set。
5. CALL_API 不得通过 nearest-block fallback 被放入无关 IF block。
```

验收应优先检查中间 IR，而不是只检查 final SPL 字符串。

### 4.2 P1：拆分 placement ownership 与 generic extraction exclusion

当前 API exclusion 不能直接用于 worker ownership / flow placement。

应显式拆成：

```text
placement_behavior_span_ids:
  所有 executable action spans，包括 API / REQUEST_INPUT / future INVOKE_WORKER candidates。

generic_step_extraction_span_ids:
  排除 API-owned / invoke-owned / repair-owned spans，只供 GENERAL_COMMAND extractor 使用。
```

`exclusion_view.api_consumed_span_ids` 只能影响：

```text
generic command extraction
child-worker candidate extraction
duplicate GENERAL_COMMAND prevention
```

不能影响：

```text
worker ownership
flow placement
block placement
local IF construction
```

### 4.3 P2：Stage 4 区分 local conditional 与 top-level alternative flow

引入 Stage 4 后处理或 validator，例如：

```text
LocalConditionalFlowReclassifier
```

职责：

```text
1. 识别被 LLM 放入 alternative_flows 但实际属于 main-flow local conditional 的 spans。
2. 将其移回 main flow。
3. 保存 local conditional metadata，供 Stage 5 构造 IF block。
```

判定口径：

```text
Local IF:
  - clarification / request input / missing-info handling
  - local precondition / local guard
  - 执行后回到主流程
  - 可包含一个或多个连续步骤

Alternative Flow:
  - revision branch
  - user-selected alternate route
  - exception-like branch
  - workflow-level alternate path
```

当前 `s17` 应由：

```text
ALTERNATIVE_FLOW alt_2
```

转为：

```text
main-flow local IF:
  condition = required information is missing
  spans = [s17]
```

### 4.4 P3：Stage 5 对 API-owned guarded_action 也生成 IF block

Stage 5 应统一处理两类 local IF：

```text
1. Stage 1 guarded_action:
   s18 -> IF sources are needed and available
   s20 -> IF enough required information is available

2. Stage 4 local conditional:
   s17 -> IF required information is missing
```

Stage 5 只负责 control/block placement，不负责 materialize command。

因此 `s18` 对应 block 里只需要保留 span placement，后续由 API materializer 生成 `CALL_API`。

### 4.5 P4：API placement 缺 block 时 fail closed

当前 `_nearest_main_flow_block()` 会静默猜测最近 block，这是把 `CALL_API` 放进错误 IF 的直接原因。

应改成：

```text
exact block found:
  status = placed

no exact block:
  status = unresolved
  diagnostic = api_call_missing_block_placement
  do not materialize CALL_API
```

不要用 Renderer、Gate 或 Stage 7 fallback 补救上游 control placement 缺失。

### 4.6 P5：Step input/output relation matching

Stage 7 需要从 “required output completion pressure” 改成 “source-backed relation matching”。

建议引入或强化 Step output policy：

```text
produces_output
consumes_input
refines_existing_output
validates_existing_output
records_metadata
no_output
unknown
```

ProducerIndex 只能接受：

```text
produces_output
```

不能把：

```text
records_metadata
refines_existing_output
validates_existing_output
no_output
```

当成 required output producer。

当前 `Maintain provenance for externally sourced facts` 应至少不再产生 `source_evidence_set`。

### 4.7 P6：E2E 验收目标

修复后，`internal_comms` 的 SPL 结构应接近：

```text
COMMAND determine what kind of communication is requested
COMMAND identify which required fields are still missing

IF required information is missing:
  INPUT ask only the highest-value clarifying questions needed to move forward

IF sources are needed and available:
  CALL ApprovedSourceRecipesAPI
  COMMAND maintain provenance for externally sourced facts

IF enough required information is available:
  COMMAND produce a draft

IF the user asks for revision:
  COMMAND revise while re-checking constraints

COMMAND record assumptions log and completion status
```

其中：

```text
source_evidence_set
```

在 API contract unknown 且没有明确 source-backed producer 时，应保持为缺口诊断或 deferred binding，而不是被 `CALL_API` 或 `Maintain provenance...` 假装生产。

## 5. 不应采用的修复方式

以下方式会掩盖问题，不应作为正式修复：

```text
1. 在 renderer 中重排 COMMAND 顺序。
2. 在 Stage 7 中根据字符串关键词硬猜 IF block。
3. 继续使用 nearest-block fallback 放置 API call。
4. 为了消除 missing_output_producer，强行把 required output 绑定到最近相关 step。
5. 把 API placeholder 的未知 return contract 渲染成已知 RESPONSE binding。
6. 把局部 clarification gate 继续展示为顶层 ALTERNATIVE_FLOW。
```

## 6. 最终问题定义

本问题不是单一 Stage 的小 bug，而是跨 Stage 3.5、Stage 4、Stage 5、Stage 7 的 authority boundary 错位：

```text
Stage 3.5:
  API exclusion 同时影响了 generic extraction 与 placement ownership。

Stage 4:
  缺少 local conditional 与 top-level alternative flow 的稳定区分。

Stage 5:
  guarded_action consumer 只处理已进入 flow/block 的 span，无法恢复被 upstream 排除的 API-owned guarded action。

Stage 7:
  API placement 使用 silent nearest-block fallback；
  output binding 受 required output pressure 影响，缺少 source-backed relation matching。
```

修复应保持以下总原则：

```text
Backend IR first.
Control/block placement treats executable actions uniformly.
Materialization authority decides command type later.
Local IF and top-level ALTERNATIVE_FLOW must be semantically distinguished.
Step input/output binding must be source-backed and relation-aware.
Renderer must only render IR and must not repair semantic placement.
```

## 7. 评审吸收修订：从局部补丁升级为 typed compiler contracts

根据后续评审，本问题文档的方向成立，但最终方案不能停留在几个 stage 内部的局部补丁。需要把以下三件事产品化为稳定 contract：

```text
1. local conditional / alternative flow 的控制区域 contract
2. API action placement 的 stage-owned placement contract
3. Step 输入输出 relation matching contract
```

也就是说，本问题的最终目标不是只修复 `internal_comms` demo，而是把 executable action planning、control placement、materialization authority、output producer authority 重新拆开。

### 7.1 更精确的 placement invariant

原文中“Block planning 应一视同仁处理 executable actions”的判断需要进一步收紧为：

```text
所有 executable action span 在 control / flow / block planning 阶段一视同仁。
```

不要说“所有 COMMAND 一视同仁”，因为在 Stage 4/5 之前，系统还不应该过早决定一个 action 最终是：

```text
GENERAL_COMMAND
CALL_API
REQUEST_INPUT
INVOKE_WORKER
```

更稳定的 compiler invariant 是：

```text
Executable action placement precedes command materialization.
Materialization authority must not remove placement authority.
```

这意味着：

```text
API / request-input / invoke / general command 的差异只影响 Stage 7 materialization；
不应影响 Stage 3.5/4/5 的 worker ownership、flow placement、block placement。
```

### 7.2 不应只做 LocalConditionalFlowReclassifier

如果只新增一个 `LocalConditionalFlowReclassifier`，很容易退化成新的启发式规则：

```text
看到 ask clarifying questions -> 强行改成 IF required information is missing
```

这不够稳。更合理的方向是新增 typed control artifact，例如：

```text
ControlRegionPlan
  local_condition_regions[]
  top_level_alternative_regions[]
  guarded_action_regions[]
  unresolved_control_regions[]
```

或等价的：

```text
LocalConditionalDemand
```

每个 control region 至少需要记录：

```text
condition_text
condition_source_span_ids
action_span_ids
relation = direct | derived | ambiguous
control_kind = local_if | alternative_flow | exception_flow | loop | unresolved
classification_source = stage1_guarded_action | route_derived | llm_classified | deterministic_evidence
```

对于当前 `s17`：

```text
Ask only the highest-value clarifying questions needed to move forward.
```

它本身没有显式 `if required information is missing`。这个 condition 是从前文：

```text
Then identify which required fields are still missing.
```

和 ask-clarification action 共同推导出来的。因此它必须记录为：

```text
relation = derived
condition_source_span_ids = [s16, s17]
action_span_ids = [s17]
control_kind = local_if
```

不能伪装成 direct source condition，也不能靠 raw NL keyword fallback 决定。

### 7.3 API call placement 应成为 Stage 5 一等输出

API call placement 不能继续依赖 Stage 7 临时补救。建议把 API placement 明确作为 Stage 5 / block planning 的一等 artifact，例如：

```text
WorkerBlockPlanIR.api_call_placements
```

或等价 intermediate。

每个 `APICallDemand` 必须有一个 placement result：

```text
call_demand_id
source_span_ids
owner_worker_id
flow_ref
block_ref
status = placed | unresolved | ambiguous
reason
```

验收 invariant：

```text
status != placed -> Stage 7 不得生成 CALL_API
```

因此 `_nearest_main_flow_block()` 这类 silent fallback 不能继续存在。缺少 exact block placement 时，应输出结构化 diagnostic，而不是猜一个最近 block。

### 7.4 Step IO relation matching 必须进入 ProducerIndex 之前

只修改 Stage 7 prompt 不够。需要显式 relation enum，例如：

```text
StepVariableRelation:
  produces
  consumes
  refines
  validates
  records_metadata
  declares
  no_relation
  unknown
```

ProducerIndex 只能接受：

```text
relation == produces
```

不能接受：

```text
records_metadata
refines
validates
unknown
no_relation
```

这比单纯修改 prompt 更可靠，可以防止 LLM 为了满足 required output，把“看起来相关”的 step 绑定为 missing output 的 producer。

### 7.5 `source_evidence_set` 应区分三种合法状态

`source_evidence_set` 不应该只有 produced / failed 两种状态。至少需要区分：

```text
produced:
  API return contract、source text 或 user-confirmed repair 明确支持该变量被生产。

deferred:
  API call 存在，且存在 pending response binding，
  但 API return contract 尚未知。
  这不能注册 ProducerIndex producer，也不能消除 missing_output_producer。

missing:
  没有 source-backed producer，也没有可确认 API return。
```

这可以避免两类错误：

```text
1. 把 API contract unknown 的 CALL_API 当作 producer。
2. 把 Maintain provenance... 这类 metadata/refinement 动作当作 producer。
```

### 7.6 负例测试必须覆盖“不消失”

P0 测试不能只证明最终 SPL 看起来更顺。还必须覆盖以下负例：

```text
1. API call 没有 placed block:
   Stage 7 不生成 CALL_API；
   输出 diagnostic = api_call_missing_block_placement 或 stage7_unresolved_api_call_materialization。

2. Maintain provenance...:
   不得出现在 ProducerIndex producers[source_evidence_set] 中。

3. API return contract unknown:
   不得通过 pending_response_bindings 假装生产 source_evidence_set。

4. local clarification condition:
   不得被静默提升为 top-level ALTERNATIVE_FLOW。

5. API-owned guarded_action:
   不得因为 excluded from GENERAL_COMMAND extraction 而失去 IF block placement。
```

### 7.7 修订后的实施顺序建议

如果后续形成 implementation plan，建议按以下顺序拆分：

```text
P0: Characterization tests
  锁定 s17/s18/s19/s20 的 worker ownership、flow、block、step、ProducerIndex 错误。

P1: ExecutableActionPlacement contract
  所有 executable action span 进入 placement plan。
  API / request-input / invoke / general command 只影响 materialization，不影响 placement。

P2: ConstructPlan / ControlRegionPlan extension
  保留现有 ConstructPlan。
  增加 LocalConditionalDemand 或 ControlRegionPlan。
  禁止 raw NL keyword fallback。

P3: Stage 3.5 ownership repair
  API-owned executable span 仍必须 owned by worker。
  generic extraction exclusion 与 placement ownership 分离。

P4: Stage 4/5 control placement
  guarded_action 与 local conditional 生成 local IF block。
  alternative flow 只用于 workflow-level branch。
  API call placement status 必须 exact placed / unresolved / ambiguous。

P5: Stage 7 fail-closed materialization
  status != placed 不生成 CALL_API。
  删除 nearest-block fallback。
  不用 required-output pressure 伪造 response binding。

P6: Relation-aware IO binding
  引入 StepVariableRelation。
  ProducerIndex 只接受 produces。
  records_metadata / refines / validates 不可作为 producer。

P7: E2E + audit
  final SPL 只作为结果检查。
  主要验收中间 IR、ProducerIndex、diagnostics、provenance。
```

### 7.8 修订后结论

本问题应以 conditional-pass 进入下一步设计或实施计划：

```text
问题诊断: pass
核心思路: pass
最终方案: conditional_pass
```

conditional 的原因不是方向错误，而是必须把 `local conditional`、`API action placement`、`Step IO relation matching` 产品化为 typed compiler contracts，避免再次变成 stage 内部的局部启发式补丁。
