# NL2SPL Worker Contract Partial Rendering 修复计划

日期：2026-06-14  
状态：Implementation Plan  
适用范围：NL2SPL-Compile-Pipeline；Stage 3.5 worker risk filtering / materialization、Stage 3.6 WorkerPlanValidator、Stage 7 handoff step generation、IRS worker/delegation checker、Stage 9.5 handoff validation / normalization、Stage 10 worker assembly、Stage 11 renderer regression、plan artifact parser / serializer

---

## 1. 问题摘要

当前项目存在一个架构级错误：SPL 语法允许 `WORKER_INSTRUCTION` 的 `[INPUTS]` 和 `[OUTPUTS]` 缺省或为空，但当前 pipeline 在 Stage 3.5 worker materialization / delegation promotion 阶段把缺少 input/output contract 过早解释为“child worker 不可 materialize”。结果是：本应作为 source-backed partial worker skeleton 渲染的 worker，在到达 Stage 11 renderer 前已被 rejected、降级回 main worker，或只能以 diagnostic 形式残留。

该错误不是 Stage 11 renderer 的主要问题。Renderer 已经能渲染空 `[INPUTS]` / `[OUTPUTS]` section 和空 `[MAIN_FLOW]`。真正的修复点在更早的 compiler authority 边界：

```text
Stage 3.5 worker risk filtering / WorkerPlanMaterializer
+ WorkerPlanIR contract state model
+ Stage 3.6 WorkerPlanValidator
+ Stage 7 handoff step generation
+ ConstructIRS / WorkerDelegationIRSChecker
+ Stage 9.5 handoff validation / normalization
+ Stage 10 child worker assembly
+ plan parser / snapshot serializer
+ regression tests
```

核心修复原则：

```text
缺 input/output contract
  => 阻断 promotion / handoff / invocation completeness
  => 产生 type_or_contract_ambiguity / contract diagnostic
  => 不应阻断 worker definition skeleton 的 partial rendering
```

---

## 2. 目标语义

修复后，系统必须明确区分以下概念：

```text
worker definition syntax renderability
≠ worker promotion readiness
≠ handoff contract completeness
≠ INVOKE_WORKER executable materialization readiness
```

目标行为：

| 场景 | Worker definition | Handoff | INVOKE_WORKER | Diagnostic |
| --- | --- | --- | --- | --- |
| source-backed responsibility + known input/output contract | 渲染完整 child worker | 完整 | 可生成 | 无 contract gap |
| source-backed responsibility + unknown input/output contract | 渲染 partial child worker skeleton | partial / incomplete | 不生成或被 Gate 阻断 | contract ambiguity |
| source-backed responsibility + confirmed empty input/output contract | 渲染空 INPUTS/OUTPUTS child worker | confirmed-empty handoff 可成立 | 可生成无 WITH/RESPONSE invocation | 无 contract gap |
| invented input/output contract | 拒绝 invented fields | 不使用 invented binding | 不生成 | invented contract / provenance diagnostic |
| no source-backed responsibility | 不生成 child worker | 不生成 | 不生成 | 视 source demand 决定 |

---

## 3. 非目标

本修复不做以下事情：

```text
1. 不让 LLM 编造 input/output contract。
2. 不生成 dummy ContractFieldIR。
3. 不用空字符串、placeholder variable 或 synthetic variable 表示 unknown contract。
4. 不修改 renderer 让它承担 IRS 判断。
5. 不因为 partial worker skeleton 存在就强行生成 INVOKE_WORKER。
6. 不绕过 Post-normalize IRS、Gate、ProducerIndex。
7. 不把 delegation_intent 恢复为独立 IRS construct。
```

---

## 4. 当前根因

### 4.1 Stage 3.5 risk auto-reject 过早过滤 contract-missing candidate

当前 `WorkerBoundaryPlanner._BLOCKING_RISKS` 等同于 `_REJECTION_REASONS`，其中包含：

```text
no_clear_input_contract
no_clear_output_contract
unclear_result_handoff
```

这意味着 Stage 3.5a candidate 一旦带有缺 contract 风险，会在 Stage 3.5b / materializer 之前被 `_split_by_blocking_risks()` 自动降级为 `keep_in_main_worker` 或其他 rejected decision。

问题：

```text
contract incompleteness 在 materializer 之前就被解释成 worker candidate 不可继续。
```

正确解释应是：

```text
no_clear_input_contract / no_clear_output_contract / unclear_result_handoff
  => promotion / handoff / invocation 不完整
  => 不应作为 worker responsibility candidate 的 blocking risk
```

因此必须先拆分 risk taxonomy：

```text
candidate-blocking risks:
  insufficient_semantic_boundary
  over_fragmentation
  ordinary_sequential_step
  simple_control_flow
  policy_or_constraint
  exception_flow / alternative_flow / single_api_call 等非 worker-definition 路径

promotion-blocking risks:
  no_clear_input_contract
  no_clear_output_contract
  no_parent_invocation_point
  unclear_result_handoff
```

### 4.2 Stage 3.5 materializer 将 contract 缺失作为 reject 条件

当前 `WorkerPlanMaterializer` 的保证语义是：每个 accepted decision 必须 materialize 为一个带 valid handoff 的 non-main worker，否则 reject。该语义过强。

当前 `_candidate_to_worker()` 近似逻辑：

```python
inputs = candidate.possible_inputs or matched_hard_inputs
outputs = candidate.possible_outputs or matched_hard_outputs

if not inputs or not outputs:
    return None
```

然后 `_materialize_accepted()` 会把 `worker is None` 解释为 `no_clear_input_contract` / `no_clear_output_contract`，并将原 `extract_child_worker` decision 改写为 `keep_in_main_worker`。

问题：

```text
缺 contract 被解释成 worker 不存在。
```

正确解释应是：

```text
worker responsibility exists，但 promotion / handoff contract incomplete。
```

### 4.3 空 list 不能表达 confirmed-empty 与 unknown

当前 IR 中：

```python
CandidateTaskUnitIR.possible_inputs: list[ContractFieldIR]
CandidateTaskUnitIR.possible_outputs: list[ContractFieldIR]
WorkerSpecIR.input_contract: list[ContractFieldIR]
WorkerSpecIR.output_contract: list[ContractFieldIR]
WorkerHandoffIR.input_bindings: list[InputBindingIR]
WorkerHandoffIR.output_bindings: list[OutputBindingIR]
```

空 list 可能表示：

```text
1. 确认没有 input/output。
2. 暂时不知道 input/output。
3. LLM 没给。
4. adapter hard facts 没匹配到。
```

这四种语义目前被压缩成同一个状态，导致 checker 与 materializer 无法正确区分。

### 4.4 ConstructIRS 把 CHILD_WORKER contract 当成 required-for-partial

当前 `CHILD_WORKER.input_contract` / `output_contract` 被设计为 `required_for_partial=True` 且 `renderable_without=False`。这与 SPL 语法和 partial-first 输出原则冲突。Worker definition skeleton 可以 partial render；缺 contract 应影响 complete / invocation，不应影响 definition skeleton 的 renderability。

### 4.5 Stage 3.6 WorkerPlanValidator 将 partial worker 当作 invalid graph

当前 `WorkerPlanValidator` 仍以“每个 non-main worker 必须完整可调用”为结构不变量，典型规则包括：

```text
non-main worker 必须至少有一个 invoke handoff
child worker 必须声明非空 input_contract / output_contract
accepted child handoff 必须有非空 input_bindings / output_bindings
```

这与 partial worker skeleton 目标冲突。修复后 validator 应区分：

```text
worker definition graph validity
≠ invocation / handoff completeness
```

`WorkerPlanValidator` 仍应拒绝 dangling target、重复 ID、非法 enum、span ownership 冲突、invented binding 指向不存在字段等结构错误；但 unknown contract / unknown binding 应转为 status-aware warning 或 IRS diagnostic，不应阻断 Stage 4 之前的 pipeline。

### 4.6 Stage 7 才是 INVOKE_WORKER step 的主要 materialization 点

当前 `INVOKE_WORKER` / `CALL_API` step 主要由 Stage 7 worker-scoped step extractor 根据 `worker_plan.handoffs` 生成，而不是 Stage 9.5 生成。Stage 9.5 主要做 handoff step validation / normalization。

因此“unknown binding 不生成 INVOKE_WORKER”的主修复点应在：

```text
src/nl2spl/pipeline/stages/stage7_step_extractor/worker_scoped.py
```

Stage 9.5 的职责是：

```text
complete / confirmed-empty handoff 必须有 matching step 并通过 binding validation
partial_contract_unknown handoff 不要求 matching INVOKE_WORKER step
```

### 4.7 Stage 10 通过 handoff 反推 child worker definition

当前 `_child_workers_from_plan()` 从 `worker_plan.handoffs` 中收集 `invoked_worker_ids`，再构建 `ChildWorkerIR`。这意味着：

```text
如果没有完整 handoff，child worker definition 也会丢失。
```

这进一步把 “invocation readiness” 与 “worker definition existence” 绑定在一起。

---

## 5. 总体修复策略

总体策略是拆分两个生命周期：

```text
A. Worker definition lifecycle
   source-backed worker responsibility
   -> partial WorkerSpecIR
   -> ChildWorkerIR
   -> rendered DEFINE_WORKER skeleton

B. Invocation lifecycle
   source-backed handoff contract
   -> WorkerHandoffIR complete or confirmed-empty
   -> Stage 7 INVOKE_WORKER materialization
   -> Stage 9.5 handoff validation / normalization
   -> Gate / IRS verification
```

缺 input/output contract 只影响 B，不应删除 A。

同时需要拆分 validator / gate 的判断边界：

```text
WorkerPlanValidator:
  保证 worker graph 结构可遍历、ID/target/span ownership 合法。
  不把 unknown contract 当作 graph invalid。

Stage 7:
  只为 complete 或 confirmed-empty handoff 生成 INVOKE_WORKER / CALL_API step。
  不为 partial_contract_unknown handoff 生成 executable step。

Stage 9.5:
  验证 materialized handoff step 与 complete handoff 一致。
  partial_contract_unknown handoff 缺少 step 不是 error。

IRS:
  报告 CHILD_WORKER partial renderability 与 WORKER_PROMOTION / WORKER_HANDOFF incompleteness。
```

---

## 6. 数据模型修复

### 6.1 新增 ContractSideStatus

在 `src/nl2spl/ir/worker_plan_ir.py` 新增：

```python
ContractSideStatus = Literal[
    "unknown",
    "known_present",
    "known_empty",
]

BindingSideStatus = Literal[
    "unknown",
    "known_present",
    "known_empty",
]
```

语义：

| 状态 | 含义 | 是否满足 contract slot | 是否允许 render empty section |
| --- | --- | --- | --- |
| `known_present` | 有 source-backed contract fields | 是 | 是 |
| `known_empty` | 明确确认该侧没有 contract | 是 | 是 |
| `unknown` | 无足够证据 | 否 | 是，但 partial |

### 6.2 扩展 CandidateTaskUnitIR

```python
@dataclass
class CandidateTaskUnitIR:
    ...
    possible_inputs: list[ContractFieldIR] = field(default_factory=list)
    possible_outputs: list[ContractFieldIR] = field(default_factory=list)
    input_contract_status: ContractSideStatus = "unknown"
    output_contract_status: ContractSideStatus = "unknown"
```

兼容规则：

```text
旧 fixture 未提供 status：默认 unknown。
possible_inputs 非空：运行时可视为 known_present。
possible_outputs 非空：运行时可视为 known_present。
```

### 6.3 扩展 WorkerSpecIR

```python
@dataclass
class WorkerSpecIR:
    ...
    input_contract: list[ContractFieldIR] = field(default_factory=list)
    output_contract: list[ContractFieldIR] = field(default_factory=list)
    input_contract_status: ContractSideStatus = "unknown"
    output_contract_status: ContractSideStatus = "unknown"
    partial_reason: str | None = None
```

`partial_reason` 可选，用于 report / feedback：

```text
missing_input_contract
missing_output_contract
missing_input_and_output_contract
unknown_handoff_contract
```

### 6.4 扩展 WorkerHandoffIR

```python
@dataclass
class WorkerHandoffIR:
    ...
    input_bindings: list[InputBindingIR] = field(default_factory=list)
    output_bindings: list[OutputBindingIR] = field(default_factory=list)
    input_binding_status: BindingSideStatus = "unknown"
    output_binding_status: BindingSideStatus = "unknown"
    materialization_status: Literal[
        "complete",
        "partial_contract_unknown",
        "confirmed_empty_contract",
        "blocked",
    ] = "partial_contract_unknown"
```

### 6.5 状态派生 helper

新增 helper，避免各 stage 手写判断：

```python
def contract_side_status(fields: list[ContractFieldIR], explicit_empty: bool = False) -> ContractSideStatus:
    if fields:
        return "known_present"
    if explicit_empty:
        return "known_empty"
    return "unknown"


def contract_side_satisfied(fields: list[ContractFieldIR], status: ContractSideStatus) -> bool:
    return bool(fields) or status == "known_empty"


def binding_side_satisfied(bindings: list[InputBindingIR | OutputBindingIR], status: BindingSideStatus) -> bool:
    return bool(bindings) or status == "known_empty"
```

建议位置：

```text
src/nl2spl/ir/worker_contract_status.py
```

或者短期放在 `worker_plan_ir.py`，后续再拆。

### 6.6 known_empty 来源必须可审计

`known_empty` 不得由空 list 自动推断。需要在 IR 或 metadata 中保留来源，至少满足以下任一来源：

```text
1. 明确结构化 source evidence 表示该侧无 input/output。
2. adapter hard fact 明确给出 empty contract side。
3. user_confirmed_repair 明确确认该侧为空。
4. 显式 LLM schema field 标记 confirmed empty，且有 source_span_ids / evidence trace。
```

建议字段：

```python
input_contract_status_source: str | None = None
output_contract_status_source: str | None = None
input_binding_status_source: str | None = None
output_binding_status_source: str | None = None
```

短期也可放入 `metadata` / checkpoint payload，但必须能被 diagnostic / feedback 展示和测试断言。

### 6.7 Parser / serializer / persisted artifact 兼容

新增 status 字段后，以下路径必须同步：

```text
src/nl2spl/pipeline/stages/stage3_5_worker_boundary_planner/plan_parser.py
src/nl2spl/compiler/artifacts/snapshot/serialization/serializers_plan.py
SPL Editing CreateWorkerHandoffContract patch payload / applier / verifier
fixture builders and persisted snapshot tests
```

兼容规则：

```text
旧 payload 无 status：默认 unknown。
非空 contract / binding list：helper 可视为 known_present，但 serializer 仍应写出 status。
known_empty 必须显式写出 status 与来源。
roundtrip 后 status 不得丢失。
```

---

## 7. Stage 3.5 materializer 修复

目标文件：

```text
src/nl2spl/pipeline/stages/stage3_5_worker_boundary_planner/planner.py
src/nl2spl/pipeline/stages/stage3_5_worker_boundary_planner/executor.py
src/nl2spl/pipeline/stages/stage3_5_worker_boundary_planner/decision_validator.py
src/nl2spl/pipeline/stages/stage3_5_worker_boundary_planner/materializer.py
```

### 7.1 拆分 blocking risk 与 promotion risk

当前 `_BLOCKING_RISKS = _REJECTION_REASONS` 过宽。修复后应拆成：

```python
_CANDIDATE_BLOCKING_RISKS = {
    "insufficient_semantic_boundary",
    "ordinary_sequential_step",
    "simple_control_flow",
    "policy_or_constraint",
    "alternative_flow",
    "exception_flow",
    "failure_recovery_protocol",
    "single_api_call",
    "over_fragmentation",
}

_PROMOTION_INCOMPLETENESS_RISKS = {
    "no_clear_input_contract",
    "no_clear_output_contract",
    "no_parent_invocation_point",
    "unclear_result_handoff",
}
```

`_split_by_blocking_risks()` 只 auto-reject candidate-blocking risks。Contract / invocation / result handoff 风险保留在 candidate 上，让 Stage 3.5b / materializer / IRS 报告 promotion incompleteness。

验收：

```text
candidate.risks 仅包含 no_clear_input_contract / no_clear_output_contract 时，不被 auto-reject。
decision_validator 不因 accepted candidate 带 promotion incompleteness risk 而拒绝。
WORKER_PROMOTION report 仍能看到这些 risk 并产出 type_or_contract_ambiguity。
```

### 7.2 修改 `_candidate_to_worker()`

当前行为：缺 inputs 或 outputs 返回 `None`。

目标行为：只要有 source-backed worker responsibility / boundary evidence，就生成 `WorkerSpecIR`；缺 contract 用 status 表达。

建议伪代码：

```python
def _candidate_to_worker(...):
    inputs = list(candidate.possible_inputs)
    outputs = list(candidate.possible_outputs)

    if not inputs:
        inputs = self._match_hard_fact_contracts(candidate, hard_inputs)
    if not outputs:
        outputs = self._match_hard_fact_contracts(candidate, hard_outputs)

    input_status = self._derive_contract_status(
        fields=inputs,
        candidate_status=getattr(candidate, "input_contract_status", "unknown"),
    )
    output_status = self._derive_contract_status(
        fields=outputs,
        candidate_status=getattr(candidate, "output_contract_status", "unknown"),
    )

    if not self._has_worker_responsibility(candidate):
        return None

    partial_reason = self._partial_contract_reason(input_status, output_status)

    return WorkerSpecIR(
        worker_id=self._worker_id_from_candidate(candidate.candidate_id),
        worker_name=self._worker_name_from_candidate(candidate),
        kind="child",
        purpose=candidate.purpose or candidate.task_text,
        owned_span_ids=list(candidate.source_span_ids),
        input_contract=inputs,
        output_contract=outputs,
        input_contract_status=input_status,
        output_contract_status=output_status,
        partial_reason=partial_reason,
        boundary_kind=candidate.candidate_kind,
        decision_evidence=list(decision.evidence),
        reason=decision.reason,
    )
```

`_has_worker_responsibility()` 不应做 raw text 语义推断，只消费已有 structured fields：

```python
def _has_worker_responsibility(candidate: CandidateTaskUnitIR) -> bool:
    return bool(
        candidate.source_span_ids
        and (candidate.task_text or candidate.purpose)
        and candidate.candidate_kind in WORKER_LIKE_BOUNDARY_KINDS
    )
```

### 7.3 修改 `_contract_fields_backed()`

当前 `_contract_fields_backed()` 对双空 contract 返回 False。修复后应区分：

```text
unknown empty side：不是 invented field，但 contract incomplete。
known_empty side：satisfied。
invented non-empty field：仍然 reject field 或 reject worker，取决于 provenance。
```

建议逻辑：

```python
def _contract_fields_backed(worker, candidate, hard_inputs, hard_outputs):
    if worker.input_contract and hard_inputs:
        if not all(f.name in {h.name for h in hard_inputs} for f in worker.input_contract):
            return False
    if worker.output_contract and hard_outputs:
        if not all(f.name in {h.name for h in hard_outputs} for f in worker.output_contract):
            return False

    # Empty contract is not automatically invented.
    # Completeness is handled by IRS via *_contract_status.
    return True
```

### 7.4 修改 `_materialize_accepted()`

当前行为：`worker is None` 或缺 contract 会 reject decision。

目标行为：

```text
worker is None only means no valid worker responsibility / invalid candidate reference。
contract unknown 不再 reject；保留 accepted decision，并生成 partial worker。
```

建议：

```python
worker = self._candidate_to_worker(...)

if worker is None:
    reject insufficient_semantic_boundary
    continue

if not self._contract_fields_backed(...):
    reject invented_contract_fields
    continue

workers.append(worker)
materialized_decisions.append(decision)
handoff = self._build_handoff(worker, candidate, ...)
handoffs.append(handoff)
```

### 7.5 修改 D1 non-executable guard

当前 D1 guard 会拒绝 owned spans 全部 non-executable 的 child worker，并把 `delegation_intent without contract` 混进 rejection reason。

目标：

```text
non-executable span 不能生成 executable command，
但可以作为 worker definition / responsibility evidence。
```

建议改为：

```text
若 boundary_kind 是 failure_mode / exception flow 类：不生成 child worker，走 ExceptionFlow。
若 boundary_kind 是 explicit_delegation / bounded_subtask / template_or_format_protocol：允许 partial worker skeleton。
若无 task responsibility，仅有裸 delegation_intent 且无 candidate structure：保留 candidate-only IRS report，不 materialize worker。
```

具体实现：

```python
if owned and owned.issubset(non_exec_span_ids):
    if child.boundary_kind in {"explicit_delegation", "bounded_subtask", "template_or_format_protocol", "integration_wrapper"}:
        warnings.append(
            f"D1 guard: preserving partial child worker '{child.worker_id}' "
            "from non-executable boundary evidence; executable invocation remains gated."
        )
        kept_workers.append(child)
        kept_handoffs.append(handoffs[i])
        continue

    # failure_mode / exception-only still rejected from worker path
    reject_decision(...)
```

---

## 8. Handoff 修复

### 8.1 `_build_handoff()` 需要写入 binding status

当前 `_build_handoff()` 从 worker contract 直接生成 bindings。若 contract 为空，则 bindings 为空，但没有 status。

目标：

```python
input_binding_status = (
    "known_present" if input_bindings
    else "known_empty" if worker.input_contract_status == "known_empty"
    else "unknown"
)

output_binding_status = (
    "known_present" if output_bindings
    else "known_empty" if worker.output_contract_status == "known_empty"
    else "unknown"
)
```

`materialization_status`：

```python
if input_binding_status in {"known_present", "known_empty"} and output_binding_status in {"known_present", "known_empty"}:
    status = "complete" if input_bindings or output_bindings else "confirmed_empty_contract"
else:
    status = "partial_contract_unknown"
```

### 8.2 Stage 7 INVOKE_WORKER / CALL_API generation 策略

目标文件：

```text
src/nl2spl/pipeline/stages/stage7_step_extractor/worker_scoped.py
src/nl2spl/pipeline/stages/stage7_step_extractor/legacy.py  # 若仍被测试覆盖
```

规则：

```text
只有 handoff input/output binding side 均 satisfied 时，才生成 INVOKE_WORKER / CALL_API step。
```

伪代码：

```python
if handoff.materialization_status == "partial_contract_unknown":
    warnings.append(
        f"Handoff {handoff.handoff_id} is partial; no executable invocation generated."
    )
    continue

if not binding_side_satisfied(handoff.input_bindings, handoff.input_binding_status):
    # IRS owns the diagnostic; Stage 7 only avoids executable step generation.
    continue

if not binding_side_satisfied(handoff.output_bindings, handoff.output_binding_status):
    # IRS owns the diagnostic; Stage 7 only avoids executable step generation.
    continue

generate_invoke_or_api_step(handoff)
```

注意：

```text
known_empty + empty bindings 可以生成无 WITH / RESPONSE 的 INVOKE_WORKER。
unknown + empty bindings 不生成 INVOKE_WORKER。
```

### 8.3 Stage 9.5 handoff validation / normalization 策略

目标文件：

```text
src/nl2spl/pipeline/stages/stage9_5_normalizer/worker_scoped.py
src/nl2spl/pipeline/stages/stage9_5_normalizer/validation.py
```

Stage 9.5 不应承担 handoff step 生成。修复后：

```text
complete handoff:
  必须有 matching INVOKE_WORKER / CALL_API step。
  step inputs / outputs 必须与 bindings 一致。

confirmed_empty_contract handoff:
  可以有 matching INVOKE_WORKER / CALL_API step。
  step inputs / outputs 可以为空。

partial_contract_unknown handoff:
  不要求 matching step。
  不对 missing step 报 error。
  保留 IRS / feedback diagnostic，用于说明 invocation blocked。
```

伪代码：

```python
if handoff.materialization_status == "partial_contract_unknown":
    warnings.append(
        f"Handoff {handoff.handoff_id} remains partial; invocation validation skipped."
    )
    continue

target_steps = self._steps_for_worker_plan_handoff(...)
if not target_steps:
    errors.append(...)
```

---

## 9. Stage 3.6 WorkerPlanValidator 修复

目标文件：

```text
src/nl2spl/pipeline/worker_plan_validator.py
src/nl2spl/pipeline/orchestrator.py  # 只在错误处理 / intermediate 需要同步时修改
src/nl2spl/pipeline/stages/stage3_5_worker_boundary_planner/executor.py
```

### 9.1 Validator 边界调整

`WorkerPlanValidator` 的职责应是 graph structure validation，而不是 promotion / invocation completeness authority。

保留 error：

```text
重复 worker_id / handoff_id
非法 enum 值
main worker 缺失或重复
handoff target 不存在
invoke handoff 指向 main worker
api_call handoff 缺 api_ref
span ownership 冲突
binding 指向不存在的 concrete contract field（当 binding 本身存在时）
rejected candidate 被 materialized 为 concrete worker
```

降级为 warning / IRS diagnostic：

```text
non-main worker 没有 complete handoff
child worker input_contract / output_contract 为空且 status=unknown
accepted child handoff input_bindings / output_bindings 为空且 status=unknown
partial_contract_unknown handoff 没有 generated invocation step
```

### 9.2 Validator 必须 status-aware

建议新增 helper：

```python
def _worker_contract_side_valid_for_plan(worker, side: str) -> bool:
    fields = worker.input_contract if side == "input" else worker.output_contract
    status = worker.input_contract_status if side == "input" else worker.output_contract_status
    return bool(fields) or status in {"known_empty", "unknown"}


def _handoff_binding_side_complete(handoff, side: str) -> bool:
    bindings = handoff.input_bindings if side == "input" else handoff.output_bindings
    status = handoff.input_binding_status if side == "input" else handoff.output_binding_status
    return bool(bindings) or status == "known_empty"
```

注意：

```text
unknown 对 WorkerPlan graph validity 是可接受的。
unknown 对 WORKER_HANDOFF / INVOKE_WORKER completeness 仍不满足。
```

### 9.3 Orchestrator / executor 验收

修复后，Stage 3.5 executor 和 orchestrator 中的 pre-repair / Stage 3.6 validation 不应因为 partial worker skeleton 抛 `StageError` / `ValueError`。

验收：

```text
WorkerSpecIR(kind=child, input_contract=[], output_contract=[], *_status="unknown")
  可以通过 WorkerPlanValidator。

WorkerHandoffIR(materialization_status="partial_contract_unknown", input_bindings=[], output_bindings=[])
  可以通过 WorkerPlanValidator，但产生 warning / IRS report。

真实结构错误仍然失败。
```

---

## 10. ConstructIRS 修复

目标文件：

```text
src/nl2spl/compiler/construct_registry.py
```

### 10.1 CHILD_WORKER registry 调整

将 CHILD_WORKER 从“必须完整 contract 才 partial render”改为“responsibility 足够 partial render，contract 影响 complete”。

建议配置：

```python
ConstructIRS(
    construct_type="CHILD_WORKER",
    existence_policy="source_signal_required",
    source_signals=["delegation", "subtask", "bounded_task", "worker_boundary"],
    partial_rendering_allowed=True,
    description="A source-backed sub-worker definition that may be partial when contract or invocation details are missing.",
    slots=[
        SlotSpec(
            slot_name="responsibility",
            required_for_partial=True,
            required_for_complete=True,
            evidence_kinds=["subtask_purpose", "delegated_responsibility"],
        ),
        SlotSpec(
            slot_name="input_contract",
            required_for_partial=False,
            required_for_complete=True,
            renderable_without=True,
            evidence_kinds=["input_contract", "parent_binding", "confirmed_empty_input_contract"],
            missing_diagnostic="type_or_contract_ambiguity",
        ),
        SlotSpec(
            slot_name="output_contract",
            required_for_partial=False,
            required_for_complete=True,
            renderable_without=True,
            evidence_kinds=["output_contract", "returned_result", "confirmed_empty_output_contract"],
            missing_diagnostic="type_or_contract_ambiguity",
        ),
        SlotSpec(
            slot_name="invocation_point",
            required_for_partial=False,
            required_for_complete=True,
            renderable_without=True,
            evidence_kinds=["condition", "handoff_point"],
            missing_diagnostic="type_or_contract_ambiguity",
        ),
        SlotSpec(
            slot_name="result_handoff",
            required_for_partial=False,
            required_for_complete=True,
            renderable_without=True,
            evidence_kinds=["output_binding", "result_binding"],
            missing_diagnostic="type_or_contract_ambiguity",
        ),
    ],
)
```

### 10.2 WORKER_PROMOTION / WORKER_HANDOFF 保持严格

不要把所有 construct 都改宽。应保留：

```text
WORKER_PROMOTION.promotion_input_contract required_for_complete
WORKER_PROMOTION.promotion_output_contract required_for_complete
WORKER_HANDOFF.input_bindings required_for_complete
WORKER_HANDOFF.output_bindings required_for_complete
INVOKE_WORKER.input_bindings/output_bindings 按现有 complete semantics
```

关键是让 CHILD_WORKER definition partial，而不是让 invocation 无 contract 也完整。

---

## 11. WorkerDelegationIRSChecker 修复

目标文件：

```text
src/nl2spl/compiler/irs/checkers/worker_delegation.py
```

### 11.1 Slot satisfaction 改为 status-aware

当前 checker 主要通过 `bool(list)` 判断 slot 是否满足。应改为：

```python
def _contract_satisfied(fields, status):
    return bool(fields) or status == "known_empty"


def _binding_satisfied(bindings, status):
    return bool(bindings) or status == "known_empty"
```

### 11.2 CHILD_WORKER report

规则：

```text
responsibility satisfied:
  bool(worker.purpose or worker.reason or worker.owned_span_ids)

input_contract satisfied:
  contract_satisfied(worker.input_contract, worker.input_contract_status)

output_contract satisfied:
  contract_satisfied(worker.output_contract, worker.output_contract_status)

renderable:
  responsibility satisfied

completeness:
  complete only if responsibility + input_contract + output_contract + invocation_point + result_handoff satisfied
  partial if responsibility satisfied but one or more complete slots missing
  blocked if responsibility missing
```

### 11.3 WORKER_PROMOTION report

规则：

```text
candidate itself can be valid as candidate-only report
promotion readiness requires input/output contract unless known_empty
```

Pseudo slots：

```python
promotion_input_contract = contract_satisfied(
    candidate.possible_inputs,
    candidate.input_contract_status,
)

promotion_output_contract = contract_satisfied(
    candidate.possible_outputs,
    candidate.output_contract_status,
)
```

`unknown` 仍产生 `type_or_contract_ambiguity`，但 report 应说明：

```text
promotion blocked; child worker definition may still be partial-renderable if materialized.
```

### 11.4 WORKER_HANDOFF report

规则：

```python
input_bindings_satisfied = binding_satisfied(
    handoff.input_bindings,
    handoff.input_binding_status,
)
output_bindings_satisfied = binding_satisfied(
    handoff.output_bindings,
    handoff.output_binding_status,
)
```

`known_empty` 表示该侧确认无 binding requirement，不应报 missing。

---

## 12. Stage 10 child worker assembly 修复

目标文件：

```text
src/nl2spl/pipeline/stages/stage10_worker_assembler/child_worker_builder.py
```

### 12.1 不再仅通过 handoff 推导 child worker definitions

当前逻辑：

```python
invoked_worker_ids = [handoff.to_worker for handoff in worker_plan.handoffs if handoff.mode == "invoke"]
for worker_id in invoked_worker_ids:
    build ChildWorkerIR
```

目标逻辑：

```python
child_specs = [
    worker for worker in worker_plan.workers
    if worker.kind in {"child", "api_adapter"}
]

for spec in child_specs:
    build ChildWorkerIR
```

`child_worker_refs` 策略：

```text
所有 rendered child workers 都应进入 child_worker_refs，供 renderer 在 agent level 输出 DEFINE_WORKER。
是否有 INVOKE_WORKER step 是另一件事，由 Stage 7 / Stage 9.5 / Gate 控制。
```

建议伪代码：

```python
def _child_workers_from_plan(self, worker_plan: WorkerPlanIR, steps: list[StepIR]):
    child_worker_refs = []
    child_workers = []

    for spec in worker_plan.workers:
        if spec.kind == "main":
            continue

        invoke_step = self._find_invoke_step_by_worker_name(steps, spec.worker_name)

        child_worker_refs.append(spec.worker_name)
        child_workers.append(
            ChildWorkerIR(
                worker_name=spec.worker_name,
                description=spec.purpose or spec.reason,
                task_text=invoke_step.text if invoke_step else spec.purpose or spec.reason,
                inputs=self._inputs_from_contract(spec.input_contract),
                outputs=self._outputs_from_contract(spec.output_contract),
                # Optional metadata if ChildWorkerIR supports it:
                # metadata={
                #   "input_contract_status": spec.input_contract_status,
                #   "output_contract_status": spec.output_contract_status,
                #   "partial_reason": spec.partial_reason,
                # }
            )
        )

    return child_worker_refs, child_workers
```

### 12.2 Guard against empty-shell noise

避免把完全无责任、无来源的 worker 也渲染：

```python
if not spec.purpose and not spec.reason and not spec.owned_span_ids:
    continue
```

---

## 13. Renderer 策略

目标文件：

```text
src/nl2spl/pipeline/stages/stage11_spl_renderer/renderer.py
```

短期不改 renderer 行为。当前 renderer 输出：

```spl
[INPUTS]
[END_INPUTS]
[OUTPUTS]
[END_OUTPUTS]
[MAIN_FLOW]
[END_MAIN_FLOW]
```

这是稳定且与当前 validator 更兼容的方式。

不建议短期省略空 `[INPUTS]` / `[OUTPUTS]` section，因为 static validator 可能仍要求 section 存在。若未来决定省略，需要同步修改 validator。

本阶段只补 regression tests，确保：

```text
1. empty inputs/outputs 不报 renderer error。
2. empty main flow 不合成 fallback command。
3. child worker with no invocation still renders as DEFINE_WORKER skeleton。
```

---

## 14. Diagnostics 与 feedback 修复

### 14.1 Diagnostic authority

诊断分层：

```text
CHILD_WORKER:
  partial renderable worker definition

WORKER_PROMOTION:
  promotion readiness blocked by missing input/output contract

WORKER_HANDOFF:
  handoff contract missing or partial

INVOKE_WORKER:
  only materialized when handoff binding is satisfied

Gate:
  blocks executable invocation/step if unsourced or incomplete
```

### 14.2 用户可见表达

不应再写：

```text
Worker rejected because no clear input/output contract.
```

应改为：

```text
Child worker retained as partial SPL.
Input/output contract is missing, so invocation is not materialized until the contract is specified.
```

Feedback section 推荐：

```text
Worker delegation
- Worker_extract_sources: partial worker definition rendered.
  - Missing input contract: blocks promotion/invocation, not worker definition rendering.
  - Missing output contract: blocks promotion/invocation, not worker definition rendering.
  - No INVOKE_WORKER generated because handoff bindings are unknown.
```

---

## 15. 测试计划

### 15.1 P0 baseline failing tests

先新增失败测试，确认当前 bug：

```text
test_materializer_preserves_child_worker_with_unknown_input_contract
test_materializer_preserves_child_worker_with_unknown_output_contract
test_materializer_does_not_reject_for_missing_contract_only
test_stage3_5_risk_filter_does_not_auto_reject_contract_missing_candidate
test_worker_plan_validator_allows_partial_child_worker_with_unknown_contract
test_stage7_does_not_generate_invoke_for_unknown_handoff
test_stage10_builds_child_worker_from_worker_spec_without_handoff
test_renderer_renders_child_worker_with_empty_inputs_outputs
test_unknown_handoff_does_not_materialize_invoke_worker
```

### 15.2 WorkerPlanIR model tests

```text
test_contract_status_defaults_to_unknown
test_non_empty_contract_implies_known_present_in_helpers
test_known_empty_contract_satisfies_contract_side
test_unknown_empty_contract_does_not_satisfy_contract_side
test_binding_status_known_empty_satisfies_binding_side
test_binding_status_unknown_does_not_satisfy_binding_side
test_worker_plan_status_roundtrip_preserves_unknown
test_worker_plan_status_roundtrip_preserves_known_empty
test_known_empty_requires_explicit_status_source
```

### 15.3 Stage 3.5 risk filter / materializer tests

```text
test_contract_missing_risks_are_not_candidate_blocking
test_insufficient_semantic_boundary_still_candidate_blocking
test_decision_validator_allows_promotion_incompleteness_risks_on_accepted_candidate
test_candidate_to_worker_allows_empty_inputs_with_unknown_status
test_candidate_to_worker_allows_empty_outputs_with_unknown_status
test_candidate_to_worker_sets_partial_reason_for_unknown_input
test_candidate_to_worker_sets_partial_reason_for_unknown_output
test_invented_contract_fields_still_rejected
test_d1_guard_preserves_explicit_delegation_partial_worker
test_d1_guard_still_rejects_failure_mode_as_child_worker
```

### 15.4 WorkerPlanValidator tests

```text
test_validator_allows_non_main_worker_without_complete_handoff_when_partial
test_validator_allows_unknown_empty_child_contract_side
test_validator_allows_unknown_empty_handoff_binding_side
test_validator_still_rejects_duplicate_worker_id
test_validator_still_rejects_unknown_handoff_target
test_validator_still_rejects_binding_to_unknown_existing_contract_field
test_validator_reports_partial_worker_warning_not_error
```

### 15.5 Parser / serializer / SPL Editing patch tests

```text
test_plan_parser_reads_candidate_contract_status
test_plan_parser_reads_worker_contract_status
test_plan_parser_reads_handoff_binding_status
test_worker_plan_serializer_roundtrips_contract_status
test_worker_plan_serializer_roundtrips_binding_status
test_create_worker_handoff_contract_sets_known_present_status
test_confirmed_empty_repair_sets_known_empty_status_and_source
```

### 15.6 IRS checker tests

```text
test_child_worker_partial_renderable_with_responsibility_only
test_child_worker_unknown_input_contract_reports_type_or_contract_ambiguity
test_child_worker_known_empty_input_contract_no_missing_input_diagnostic
test_worker_promotion_unknown_contract_blocked
test_worker_promotion_known_empty_contract_satisfied
test_worker_handoff_unknown_bindings_incomplete
test_worker_handoff_known_empty_bindings_satisfied
```

### 15.7 Stage 7 / Stage 9.5 / INVOKE_WORKER tests

```text
test_stage7_unknown_empty_bindings_do_not_generate_invoke_worker
test_stage7_known_empty_bindings_generate_invoke_without_with_response
test_stage7_known_present_bindings_generate_invoke_with_bindings
test_stage9_5_partial_unknown_handoff_without_step_is_not_error
test_stage9_5_complete_handoff_without_step_is_error
test_stage9_5_confirmed_empty_handoff_validates_empty_step
test_partial_handoff_diagnostic_preserved_by_irs
```

### 15.8 Stage 10 assembly tests

```text
test_child_worker_definition_from_worker_plan_workers_even_without_handoff
test_child_worker_refs_include_partial_child_worker
test_child_worker_empty_contract_maps_to_empty_worker_inputs_outputs
test_no_empty_shell_worker_without_responsibility
```

### 15.9 Integration tests

```text
test_pipeline_partial_child_worker_rendered_when_contract_missing
test_pipeline_missing_contract_blocks_invocation_not_definition
test_pipeline_confirmed_empty_contract_allows_invocation_without_bindings
test_pipeline_no_dummy_contract_fields_created
test_pipeline_no_assumed_commands_created_for_partial_worker
test_pipeline_stage3_6_does_not_abort_on_partial_worker
test_pipeline_roundtrip_snapshot_preserves_partial_worker_status
```

---

## 16. 实施阶段

### Phase 0: Baseline tests

目标：先锁定当前错误，防止后续局部 patch 掩盖问题。

改动：

```text
tests/unit/pipeline/stage3_5/test_worker_materializer_partial_contract.py
tests/unit/pipeline/stage10/test_child_worker_partial_definition.py
tests/unit/pipeline/stage11/test_renderer_empty_worker_contract.py
```

验收：新增测试在当前 main 分支上失败，失败原因指向 contract 缺失导致 worker reject 或 child worker 未进入 renderer。

### Phase 1: IR status model + parser / serializer compatibility

目标：引入 `ContractSideStatus` / `BindingSideStatus`，并保证 payload / checkpoint / snapshot roundtrip 不丢状态。

改动：

```text
src/nl2spl/ir/worker_plan_ir.py
src/nl2spl/ir/worker_contract_status.py  # optional
src/nl2spl/pipeline/stages/stage3_5_worker_boundary_planner/plan_parser.py
src/nl2spl/compiler/artifacts/snapshot/serialization/serializers_plan.py
SPL Editing CreateWorkerHandoffContract patch payload / applier / verifier
```

验收：

```text
旧 fixture 不需要全量修改。
所有新增字段有默认值。
unknown / known_present / known_empty roundtrip 后不丢失。
known_empty 必须带可审计 source / metadata。
旧 payload 无 status 时默认 unknown。
```

### Phase 2: Stage 3.5 risk taxonomy

目标：contract 缺失不再作为 candidate auto-reject 条件。

改动：

```text
stage3_5_worker_boundary_planner.planner._BLOCKING_RISKS
stage3_5_worker_boundary_planner.executor._split_by_blocking_risks
stage3_5_worker_boundary_planner.decision_validator
```

验收：

```text
candidate.risks 只有 no_clear_input_contract / no_clear_output_contract 时不被 auto-reject。
insufficient_semantic_boundary / over_fragmentation 等仍会 auto-reject。
accepted candidate 可保留 promotion incompleteness risks 给 IRS 报告。
```

### Phase 3: Materializer partial worker preservation

目标：缺 contract 不再 reject accepted child worker candidate。

改动：

```text
materializer._candidate_to_worker
materializer._contract_fields_backed
materializer._materialize_accepted
materializer D1 guard
materializer._build_handoff status propagation
```

验收：

```text
unknown contract => partial WorkerSpecIR exists。
missing contract warning 不再改写 decision 为 keep_in_main_worker。
partial_contract_unknown handoff exists only as planning edge, not executable step demand。
invented non-source-backed contract 仍被拒绝。
```

### Phase 4: WorkerPlanValidator status-aware graph validation

目标：Stage 3.6 不因 partial worker / partial handoff abort pipeline。

改动：

```text
src/nl2spl/pipeline/worker_plan_validator.py
src/nl2spl/pipeline/stages/stage3_5_worker_boundary_planner/executor.py
src/nl2spl/pipeline/orchestrator.py  # 如需同步 validation reporting
```

验收：

```text
partial worker skeleton 通过 graph validation。
partial_contract_unknown handoff 不因 empty bindings 失败。
真实 graph 错误仍然失败。
validator warnings 与 IRS diagnostics 不互相伪造。
```

### Phase 5: Stage 7 executable handoff generation gating

目标：unknown binding 不生成 INVOKE_WORKER / CALL_API；known_empty binding 可生成 empty invocation。

改动：

```text
src/nl2spl/pipeline/stages/stage7_step_extractor/worker_scoped.py
src/nl2spl/pipeline/stages/stage7_step_extractor/legacy.py  # 若 legacy tests 仍覆盖
```

验收：

```text
partial_contract_unknown handoff 不生成 StepIR(command_type="INVOKE_WORKER")。
known_empty + empty bindings 可生成 inputs=[] / outputs=[] 的 INVOKE_WORKER。
known_present bindings 生成完整 inputs / outputs。
symbol_table 不为 skipped handoff 生成 dummy producer / consumer。
```

### Phase 6: Stage 9.5 handoff validation / normalization

目标：Stage 9.5 验证 generated steps，不负责生成 incomplete invocation。

改动：

```text
src/nl2spl/pipeline/stages/stage9_5_normalizer/worker_scoped.py
src/nl2spl/pipeline/stages/stage9_5_normalizer/validation.py
src/nl2spl/pipeline/stages/stage9_5_normalizer/normalization.py  # 若 structured response metadata 受影响
```

验收：

```text
partial_contract_unknown handoff 没有 corresponding step 不报 error。
complete handoff 没有 corresponding step 仍报 error。
confirmed_empty_contract handoff 可验证 empty step。
handoff output structured unpack 既有 regression 不回退。
```

### Phase 7: IRS registry and checker

目标：CHILD_WORKER partial renderable；promotion/handoff strict；checker status-aware。

改动：

```text
compiler/construct_registry.py
compiler/irs/checkers/worker_delegation.py
```

验收：

```text
CHILD_WORKER responsibility-only => partial, renderable=True。
WORKER_PROMOTION unknown contract => blocked report。
WORKER_HANDOFF unknown binding => incomplete report。
known_empty 不报 missing。
```

### Phase 8: Stage 10 child worker assembly

目标：child worker definition 从 `worker_plan.workers` 生成，不依赖 `handoffs`。

改动：

```text
pipeline/stages/stage10_worker_assembler/child_worker_builder.py
```

验收：

```text
WorkerSpecIR(kind=child) 即使没有 complete handoff，也会成为 ChildWorkerIR。
空 contract 映射为空 inputs/outputs。
没有责任 evidence 的 empty shell 不渲染。
```

### Phase 9: Renderer regression

目标：确认 renderer 不需要承担 IRS 判断，但能稳定输出 partial child worker skeleton。

改动：

```text
src/nl2spl/pipeline/stages/stage11_spl_renderer/renderer.py  # 仅必要时改
tests/unit/pipeline/stage11/test_renderer_empty_worker_contract.py
```

验收：

```text
empty INPUTS / OUTPUTS / MAIN_FLOW 正常渲染。
没有 steps 时不合成 fallback command。
无 invocation 的 child worker 仍输出 DEFINE_WORKER skeleton。
```

### Phase 10: Feedback/report wording

目标：用户报告区分 partial worker definition 与 blocked invocation。

改动：

```text
compiler/feedback_report_renderer.py
compiler/report_renderer.py
相关 diagnostic projector / analyzer if needed
```

验收：

```text
报告不再说 worker rejected。
报告说 partial worker retained, invocation blocked by missing contract。
diagnostic authority 仍来自 IRS / DiagnosticProjector。
```

### Phase 11: Full regression audit

目标：确保没有引入 dummy contract、dummy invocation、dummy command。

运行：

```bash
pytest tests/unit/compiler/irs -q
pytest tests/unit/pipeline/stage3_5 -q
pytest tests/unit/pipeline/stage7 -q
pytest tests/unit/pipeline/stage9_5 -q
pytest tests/unit/pipeline/stage10 -q
pytest tests/unit/pipeline/stage11 -q
pytest tests/integration -q
pytest tests/integration/compiler/spl_editing -q
ruff check src tests
mypy src
```

---

## 17. 风险与控制

### 风险 1：partial worker skeleton 过多，输出噪声增加

控制：

```text
只允许 source-backed responsibility / structured worker boundary evidence 生成 WorkerSpecIR。
裸 delegation_intent 不自动 materialize worker，只进入 candidate/promotion report。
无 purpose、无 reason、无 owned spans 的 worker 不进入 Stage 10。
```

### 风险 2：known_empty 被滥用，绕过 contract requirement

控制：

```text
known_empty 只能来自明确结构化 evidence、user_confirmed_repair、adapter hard fact 或显式 LLM schema field。
不能由空 list 自动推断。
```

### 风险 3：unknown binding 误生成 INVOKE_WORKER

控制：

```text
Stage 7 必须使用 binding_side_satisfied() 决定是否生成 invocation step。
Stage 9.5 必须识别 partial_contract_unknown handoff 并跳过 matching-step 强校验。
unknown + empty list => false。
known_empty + empty list => true。
```

### 风险 4：IRS diagnostic 重复

控制：

```text
CHILD_WORKER missing contract diagnostic 表达 definition partial。
WORKER_PROMOTION / WORKER_HANDOFF 表达 promotion/invocation blocked。
DiagnosticConsolidator 应按 construct_type + slot + target_ref 去重或分组展示。
```

### 风险 5：旧 fixture / serialization 破坏

控制：

```text
新增字段全部有默认值。
禁止修改必填构造参数顺序。
必要时 payload serializer 使用 getattr 默认值。
```

---

## 18. 验收标准

修复完成后必须满足：

```text
1. SPL grammar 允许的 empty INPUTS / OUTPUTS 不再被 compiler 当成 worker 不可渲染。
2. accepted child worker candidate 不因 missing input/output contract 被降级为 keep_in_main_worker。
3. WorkerSpecIR 可以表达 unknown / known_present / known_empty contract side。
4. WorkerHandoffIR 可以表达 unknown / known_present / known_empty binding side。
5. CHILD_WORKER responsibility-only 可以 partial render。
6. WORKER_PROMOTION unknown contract 仍然 blocked。
7. WORKER_HANDOFF unknown binding 仍然 incomplete。
8. Stage 3.5 risk filter 不因 no_clear_input_contract / no_clear_output_contract 自动 reject candidate。
9. WorkerPlanValidator 不因 partial worker / partial_contract_unknown handoff abort pipeline。
10. Stage 7 不为 unknown binding handoff 生成 INVOKE_WORKER。
11. Stage 9.5 不要求 partial_contract_unknown handoff 存在 matching INVOKE_WORKER step。
12. Stage 10 从 worker_plan.workers 生成 child worker definition，不只依赖 handoffs。
13. Stage 11 能渲染空 INPUTS / OUTPUTS / MAIN_FLOW child worker。
14. confirmed-empty contract 不产生 missing contract diagnostic。
15. unknown contract 产生可见 diagnostic，但不阻断 worker definition rendering。
16. plan parser / serializer / snapshot roundtrip 保留 contract / binding status。
17. 不生成 dummy contract、dummy producer、dummy command。
18. feedback report 明确展示 partial worker definition 与 invocation blocked 的区别。
19. 全量 unit / integration / lint / type check 通过。
```

---

## 19. 建议代码修改清单

```text
src/nl2spl/ir/worker_plan_ir.py
  - 新增 ContractSideStatus / BindingSideStatus
  - CandidateTaskUnitIR 增加 input_contract_status / output_contract_status
  - WorkerSpecIR 增加 input_contract_status / output_contract_status / partial_reason
  - WorkerHandoffIR 增加 input_binding_status / output_binding_status / materialization_status

src/nl2spl/ir/worker_contract_status.py
  - 新增 status helper：contract_side_satisfied / binding_side_satisfied

src/nl2spl/pipeline/stages/stage3_5_worker_boundary_planner/planner.py
src/nl2spl/pipeline/stages/stage3_5_worker_boundary_planner/executor.py
src/nl2spl/pipeline/stages/stage3_5_worker_boundary_planner/decision_validator.py
  - 拆分 candidate-blocking risks 与 promotion-incompleteness risks
  - no_clear_input_contract / no_clear_output_contract 不再 auto-reject candidate

src/nl2spl/pipeline/stages/stage3_5_worker_boundary_planner/plan_parser.py
src/nl2spl/compiler/artifacts/snapshot/serialization/serializers_plan.py
  - 解析 / 序列化 CandidateTaskUnitIR / WorkerSpecIR / WorkerHandoffIR status 字段
  - roundtrip 保留 known_empty source / metadata

src/nl2spl/pipeline/stages/stage3_5_worker_boundary_planner/materializer.py
  - _candidate_to_worker 不因 empty contract 返回 None
  - _contract_fields_backed 不把 empty unknown 视为 invented
  - _materialize_accepted 不因 missing contract reject
  - D1 guard 区分 delegation worker evidence 与 exception/failure evidence
  - _build_handoff 写入 binding status

src/nl2spl/pipeline/worker_plan_validator.py
  - partial worker / partial_contract_unknown handoff 通过 graph validation
  - 真正 graph 错误仍为 error
  - contract / binding incompleteness 改为 warning 或交由 IRS diagnostic

src/nl2spl/pipeline/stages/stage7_step_extractor/worker_scoped.py
src/nl2spl/pipeline/stages/stage7_step_extractor/legacy.py
  - unknown binding 不生成 INVOKE_WORKER / CALL_API step
  - known_empty binding 可生成 empty invocation

src/nl2spl/pipeline/stages/stage9_5_normalizer/worker_scoped.py
src/nl2spl/pipeline/stages/stage9_5_normalizer/validation.py
  - partial_contract_unknown handoff 不要求 matching step
  - complete / confirmed-empty handoff 继续严格校验 generated step

src/nl2spl/compiler/construct_registry.py
  - CHILD_WORKER partial_rendering_allowed=True
  - CHILD_WORKER input/output contract 从 required_for_partial 降为 required_for_complete
  - renderable_without=True

src/nl2spl/compiler/irs/checkers/worker_delegation.py
  - contract/binding satisfaction status-aware
  - CHILD_WORKER report 支持 partial renderability
  - WORKER_PROMOTION / WORKER_HANDOFF 保持 strict complete requirement

src/nl2spl/pipeline/stages/stage10_worker_assembler/child_worker_builder.py
  - child worker definitions 从 worker_plan.workers 生成
  - 不再只依赖 invoked_worker_ids from handoffs

src/nl2spl/pipeline/stages/stage11_spl_renderer/renderer.py
  - 不需要主逻辑修改
  - 补 empty child worker regression tests

src/nl2spl/compiler/feedback_report_renderer.py
  - 调整 wording，区分 partial worker 与 blocked invocation
```

---

## 20. 最终判断

本问题不是简单的 renderer bug，而是 compiler pipeline 中 construct lifecycle 与 invocation lifecycle 混合导致的架构错误。正确修复不是让 renderer 接受更多异常，也不是降低 handoff / invocation 的 IRS 要求，而是：

```text
保留 source-backed partial worker definition，
用 IRS diagnostic 表达 contract incompleteness，
用 Stage 7 / Stage 9.5 / Gate 阻止 incomplete invocation，
用 Stage 10 保证 child worker definition 不依赖 handoff 是否完整。
```

一句话原则：

```text
缺 contract 应阻断 worker 的“调用完整性”，不应阻断 worker 的“定义可渲染性”。
```
