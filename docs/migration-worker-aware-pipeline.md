# Pipeline Worker-Aware 迁移方案

**文档版本**: v3.0  
**创建日期**: 2026-05-12  
**修订日期**: 2026-05-12  
**作者**: Sisyphus  
**状态**: 待评审

---

## 0. 关键设计决策（Frozen）

在开始开发前，以下决策已冻结，不再讨论：

| # | 决策 | 结论 | 理由 |
|---|------|------|------|
| D1 | INVOKE_WORKER 生成规则 | 从 `WorkerHandoffIR` 生成，不从 `WorkerBoundaryDecisionIR` 生成 | handoff 是真正的调用边 |
| D2 | INVOKE_WORKER source_span_ids | 优先使用 `invoke_location_hint`；缺失 location 时返回空 `source_span_ids` 并 warning，不 fallback 到全部 `from_worker.owned_span_ids` | 避免 main step 绑定过宽或引用 child-owned span |
| D3 | ChildWorkerIR 升级 | 采用方案 A，增加 `main_flow` + `steps` 字段 | 改动小，与 Stage 11 兼容 |
| D4 | SymbolTable scope | 使用复合 key `(scope_kind, scope_id, name)` | 支持同名不同 scope |
| D5 | span ownership violation | **error**，不是 warning | span ownership 是 WorkerPlanIR 核心 invariant |
| D6 | Phase 3 策略 | worker-aware path 去 adapter，但保留 legacy path | 等 legacy delegation 迁完再删除 |
| D7 | Phase 3 时机 | Phase 1.6 后即可提前部分 Phase 3 | Stage 7/9.5/10 worker-scoped 后即可不读 delegation_candidates |
| D8 | Main worker accessor | 在 `WorkerPlanIR` 增加 `main_worker` property，或统一使用 helper 取 main worker；本文推荐增加 property | 避免各阶段重复手写 lookup，降低接口误用 |
| D9 | BlockIR.spans 语义 | `BlockIR.spans` 默认保存 source span ids；fallback block 应使用 step 的 `source_span_ids`，若使用 step ids 必须同时设置 `step.block_ref` | 当前 renderer 通过 `block.spans` 匹配 `StepIR.source_span_ids` |
| D10 | Handoff step shape 校验 | Stage 9.5 必须校验 handoff step 的 command_type、worker/api target、inputs、outputs、所在 worker | 只检查 handoff_id 存在不足以保证调用正确 |

---

## 1. 背景

### 1.1 当前问题

当前 pipeline 中，Stage 4/5 已经实现 worker-aware，输出 `WorkerFlowPlanIR` 和 `WorkerBlockPlanIR`。但 Stage 6/7/9.5/10 仍然消费旧版 `FlowStructureIR` 和 `BlockStructureIR`，通过适配器转换：

```python
# orchestrator.py 中的当前流程
worker_flow_plan = stage4(...)  # Worker-aware 输出
flow_structure = worker_flow_plan_to_legacy_main_flow(worker_flow_plan, worker_plan)  # 适配器
resources, symbol_table = stage6(flow_structure, ...)  # 消费旧版
steps, symbol_table = stage7(flow_structure, ..., worker_plan)  # 消费旧版 + handoff
```

**核心问题**：
1. 适配器丢弃了 child worker 的 flow/block 信息
2. Stage 7 通过 `delegation_candidates` 推断 child worker steps，而非直接从 child flow 提取
3. SymbolTable 没有 worker scope 概念，变量可见性不明确
4. Stage 10 的 `ChildWorkerIR` 无法承载 child worker 的 flow/blocks/steps
5. Stage 11 的 `_render_child_worker()` 使用 synthetic `st_child`，无法渲染 child flow

### 1.2 迁移目标

实现全链路 worker-aware，让 Stage 6/7/9.5/10/11 直接消费 worker-scoped IR，移除适配器。

**成功标准**：
- Stage 7 按 `worker_id` 输出 steps，main worker 的 invoke step 从 `WorkerHandoffIR` 生成
- Stage 9.5 能校验 worker-scoped IR 的完整性，span ownership violation 是 error
- Stage 10 能从 worker-scoped 数据组装包含 child flow + child steps 的 WorkerIR
- Stage 11 能渲染 child worker 的完整 flow，而非 synthetic `st_child`
- 最终移除 `worker_flow_plan_to_legacy_main_flow` 等适配器函数

---

## 2. 当前架构分析

### 2.1 数据流

```
WorkerPlanIR (Stage 3.5)
  ↓
Stage 4 → WorkerFlowPlanIR (worker-aware)
  ↓
worker_flow_plan_to_legacy_main_flow() ← 适配器
  ↓
FlowStructureIR (main-worker-only view)
  ↓
Stage 5 → WorkerBlockPlanIR (worker-aware)
  ↓
worker_block_plan_to_legacy_main_blocks() ← 适配器
  ↓
BlockStructureIR (main-worker-only view)
  ↓
Stage 6/7/9.5/10 消费 legacy view + WorkerPlanIR handoffs
  ↓
WorkerIR → Stage 11 → SPL
```

### 2.2 关键数据结构

#### WorkerHandoffIR (`ir/worker_plan_ir.py`)

```python
@dataclass
class WorkerHandoffIR:
    """Parent-to-child invocation or direct API call edge."""
    handoff_id: str
    from_worker: str              # 调用方 worker_id
    to_worker: str | None         # 被调用 worker_id（invoke 模式）
    api_ref: str | None           # API 引用（api_call 模式）
    mode: Literal["invoke", "api_call"]
    condition_text: str | None
    ordering: Literal["before", "after", "conditional", "loop_body"]
    input_bindings: list[InputBindingIR]
    output_bindings: list[OutputBindingIR]
    invoke_location_hint: InvokeLocationHintIR  # ← 调用位置提示
    failure_policy: HandoffFailurePolicyIR
```

#### InvokeLocationHintIR (`ir/worker_plan_ir.py`)

```python
@dataclass
class InvokeLocationHintIR:
    """Placement hint for downstream INVOKE_WORKER generation."""
    flow_kind: Literal["main", "alternative", "exception"]
    flow_id: str | None
    after_span_id: str | None     # ← 调用点：在哪个 span 之后
    before_span_id: str | None    # ← 调用点：在哪个 span 之前
    block_hint: Literal["sequential", "if", "for", "while", "unknown"]
```

#### WorkerSpecIR (`ir/worker_plan_ir.py`)

```python
@dataclass
class WorkerSpecIR:
    """Concrete worker specification decided before flow assembly."""
    worker_id: str
    worker_name: str
    kind: Literal["main", "child", "api_adapter"]
    purpose: str
    owned_span_ids: list[str]     # ← 该 worker 拥有的 spans
    input_contract: list[ContractFieldIR]
    output_contract: list[ContractFieldIR]
    depends_on: list[str]
    # ...
```

#### ChildWorkerIR (`ir/worker_ir.py`) - **当前缺陷**

```python
@dataclass
class ChildWorkerIR:
    """Concrete child worker generated from a delegation candidate."""
    worker_name: str
    description: str
    task_text: str
    inputs: list[WorkerInput]
    outputs: list[WorkerOutput]
    # ❌ 缺失：main_flow, blocks, steps, alternative_flows, exception_flows
```

**问题**：
1. `ChildWorkerIR` 无法承载 child worker 的 flow/blocks/steps
2. Stage 11 的 `_render_child_worker()` 使用 synthetic `st_child`，无法渲染 child flow

### 2.3 Stage 11 渲染问题 (`pipeline/stages/stage11_spl_renderer.py`)

当前 `_render_child_worker()` 实现：

```python
def _render_child_worker(self, child: ChildWorkerIR, indent: int) -> list[str]:
    """Render child worker as a single command."""
    # ❌ 问题：只渲染一个 synthetic st_child，不渲染 child flow
    lines = []
    lines.append(f"{' ' * indent}command st_child")
    lines.append(f"{' ' * (indent + 2)}description \"{child.description}\"")
    # ... 只渲染 task_text，不渲染 child flow
    return lines
```

**需要修改为**：
```python
def _render_child_worker(self, child: ChildWorkerIR, indent: int) -> list[str]:
    """Render child worker with full flow support."""
    lines = []
    lines.append(f"{' ' * indent}worker {child.worker_name}")
    lines.append(f"{' ' * (indent + 2)}description \"{child.description}\"")
    
    # 渲染 child steps（使用 child.steps，不是全局 steps）
    self._render_blocks(child.main_flow.blocks, child.steps, indent + 4)
    
    # 渲染 alternative flows
    for alt_flow in child.alternative_flows:
        self._render_alternative_flow(alt_flow, child.steps, indent + 4)
    
    # 渲染 exception flows
    for exc_flow in child.exception_flows:
        self._render_exception_flow(exc_flow, child.steps, indent + 4)
    
    return lines
```

---

## 3. 迁移方案

### Phase 0: 修正文档和 IR Contract

**目标**：修正关键设计缺口，确保后续 Phase 有正确的基础。

**预估工作量**：1 天

#### 3.0.1 修正 WorkerStepPlanIR

**文件**: `src/nl2spl/ir/worker_plan_ir.py`

```python
@dataclass
class WorkerStepPlanIR:
    """Worker-scoped step extraction result.
    
    Attributes:
        main_worker_id: Main worker ID (from WorkerPlanIR)
        worker_steps: Steps keyed by worker_id
        warnings: Validation warnings from step extraction
    """
    main_worker_id: str  # ← 新增：明确 main worker ID
    worker_steps: dict[str, list[StepIR]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    
    @property
    def main_worker_steps(self) -> list[StepIR]:
        """Get steps for the main worker."""
        return self.worker_steps.get(self.main_worker_id, [])
    
    def get_all_steps(self) -> list[StepIR]:
        """Get all steps across all workers."""
        all_steps = []
        for steps in self.worker_steps.values():
            all_steps.extend(steps)
        return all_steps
```

#### 3.0.1.1 明确 WorkerPlanIR main worker accessor（D8 - Frozen）

**文件**: `src/nl2spl/ir/worker_plan_ir.py`

推荐在 `WorkerPlanIR` 上增加 property，后续 Stage 7/9.5/10 不再重复手写 main worker lookup：

```python
@dataclass
class WorkerPlanIR:
    main_worker_id: str
    workers: list[WorkerSpecIR] = field(default_factory=list)
    # ...

    @property
    def main_worker(self) -> WorkerSpecIR | None:
        """Return the main worker spec, if present."""
        return next(
            (
                worker
                for worker in self.workers
                if worker.worker_id == self.main_worker_id and worker.kind == "main"
            ),
            None,
        )
```

如果实现阶段不希望修改 `WorkerPlanIR`，则必须提供统一 helper：

```python
def main_worker_spec(worker_plan: WorkerPlanIR) -> WorkerSpecIR | None:
    return next(
        (
            worker
            for worker in worker_plan.workers
            if worker.worker_id == worker_plan.main_worker_id and worker.kind == "main"
        ),
        None,
    )
```

同一代码路径只能使用一种方式，避免 `worker_plan.main_worker` 和手写 lookup 混用。

#### 3.0.2 明确 INVOKE_WORKER 生成规则（D1 - Frozen）

**关键设计决策**：

```text
生成 INVOKE_WORKER step 的数据源是 WorkerHandoffIR，不是 WorkerBoundaryDecisionIR。

规则：
1. 遍历 worker_plan.handoffs
2. 对于 mode="invoke" 的 handoff：
   - 生成 INVOKE_WORKER step
   - source_span_ids 使用 invoke_location_hint.after_span_id / before_span_id
   - 没有 caller span 时，返回空 `source_span_ids` 并 warning；不要 fallback 到全部 `from_worker.owned_span_ids`
3. 对于 mode="api_call" 的 handoff：
   - 生成 CALL_API step
   - source_span_ids 同上
```

**错误示例（文档 v1.0）**：
```python
# ❌ 错误：从 decisions 生成
for decision in worker_plan.decisions:
    if decision.decision == "extract_child_worker":
        # ...
```

**正确示例**：
```python
# ✅ 正确：从 handoffs 生成
for handoff in worker_plan.handoffs:
    if handoff.mode == "invoke":
        invoke_step = self._build_invoke_step(handoff, worker_plan)
    elif handoff.mode == "api_call":
        api_step = self._build_api_call_step(handoff, worker_plan)
```

#### 3.0.3 明确 INVOKE_WORKER source_span_ids 规则（D2 - Frozen）

```python
def _get_invoke_source_spans(
    self,
    handoff: WorkerHandoffIR,
    worker_plan: WorkerPlanIR,
) -> list[str]:
    """Get source spans for INVOKE_WORKER step.
    
    优先使用 invoke_location_hint，fallback 到 warning。
    """
    hint = handoff.invoke_location_hint
    
    # 优先使用 caller-owned invocation span
    if hint.after_span_id:
        return [hint.after_span_id]
    if hint.before_span_id:
        return [hint.before_span_id]
    
    # Fallback：不要绑定到 from_worker 的全部 owned spans。
    # 过宽 source_span_ids 会破坏 block 排序，也可能重新引入 ownership 污染。
    self.logger.warning(
        "Handoff %s has no invoke_location_hint; using empty source_span_ids.",
        handoff.handoff_id,
    )
    
    return []
```

#### 3.0.3.1 明确 BlockIR.spans 与 StepIR.source_span_ids 的匹配规则（D9 - Frozen）

当前 Stage 11 的 `_steps_for_block()` 通过 `BlockIR.spans` 匹配 `StepIR.source_span_ids`。因此，worker-aware fallback block 必须遵守：

```text
Default rule:
  BlockIR.spans stores source span ids.

Allowed exception:
  If BlockIR.spans stores step ids, every corresponding StepIR must set
  step.block_ref = block.block_id, so renderer can select by block_ref.
```

推荐 fallback block 生成方式：

```python
def fallback_block_for_steps(block_id: str, steps: list[StepIR]) -> BlockIR:
    span_ids = []
    for step in steps:
        for span_id in step.source_span_ids:
            if span_id not in span_ids:
                span_ids.append(span_id)
    return BlockIR(
        block_id=block_id,
        block_type="SEQUENTIAL",
        condition_text=None,
        spans=span_ids,
    )
```

不推荐：

```python
# ❌ 除非同时给每个 step 设置 step.block_ref，否则 renderer 匹配不到这些 step。
BlockIR(..., spans=[step.step_id for step in steps])
```

#### 3.0.4 ChildWorkerIR 升级方案（D3 - Frozen）

**采用方案 A：升级 ChildWorkerIR 支持 child flow + steps**

```python
@dataclass
class ChildWorkerIR:
    """Concrete child worker with full flow and steps support.
    
    Attributes:
        worker_name: Child worker name
        description: Child worker description
        task_text: Command text for the delegated task
        inputs: Input specifications
        outputs: Output specifications
        main_flow: Main flow reference (新增)
        alternative_flows: Alternative flow references (新增)
        exception_flows: Exception flow references (新增)
        api_refs: Referenced API names (新增)
        steps: Child worker steps (新增) ← 关键：renderer 需要
    """
    worker_name: str
    description: str
    task_text: str
    inputs: list[WorkerInput] = field(default_factory=list)
    outputs: list[WorkerOutput] = field(default_factory=list)
    # 新增：支持 child flow
    main_flow: FlowRef = field(default_factory=FlowRef)
    alternative_flows: list[AlternativeFlowRef] = field(default_factory=list)
    exception_flows: list[ExceptionFlowRef] = field(default_factory=list)
    api_refs: list[str] = field(default_factory=list)
    # 新增：支持 child steps
    steps: list[StepIR] = field(default_factory=list)
```

**为什么需要 `steps` 字段**：
- Stage 11 渲染时需要知道每个 block 内的 steps
- 当前 `WorkerIR.main_flow.blocks` 只是 block 结构，真正渲染 step 依赖 steps 参数
- 如果 `ChildWorkerIR` 只存 blocks 不存 steps，renderer 拿不到对应 steps

---

### Phase 1: WorkerScopedStepIR + Stage 7

**目标**：让 Stage 7 按 `worker_id` 输出 steps，main worker 的 invoke step 从 `WorkerHandoffIR` 生成。

**预估工作量**：3-5 天

#### 3.1.1 修改 Stage 7 StepExtractor

**文件**: `src/nl2spl/pipeline/stages/stage7_step_extractor.py`

**新增方法**：

```python
def execute_worker_scoped(
    self,
    spans: list[SpanIR],
    routes: FieldRouteIR,
    worker_flow_plan: WorkerFlowPlanIR,
    worker_block_plan: WorkerBlockPlanIR,
    symbol_table: SymbolTable,
    worker_plan: WorkerPlanIR,
) -> tuple[WorkerStepPlanIR, SymbolTable]:
    """Execute worker-scoped step extraction.
    
    对每个 worker 独立提取 steps：
    - main worker: 从 main flow 提取普通 steps + 从 handoffs 生成 INVOKE_WORKER
    - child worker: 从 child flow 提取自己的 steps
    
    Args:
        spans: All spans
        routes: Field routes
        worker_flow_plan: Worker-scoped flow plan
        worker_block_plan: Worker-scoped block plan
        symbol_table: Symbol table
        worker_plan: Worker plan
        
    Returns:
        Tuple of (WorkerStepPlanIR, updated SymbolTable)
    """
    worker_step_plan = WorkerStepPlanIR(main_worker_id=worker_plan.main_worker_id)
    all_warnings = []
    
    # 1. 对每个 worker 提取 steps
    for worker in worker_plan.workers:
        worker_id = worker.worker_id
        flow = worker_flow_plan.worker_flows.get(worker_id)
        blocks = worker_block_plan.worker_blocks.get(worker_id)
        
        if flow is None or blocks is None:
            all_warnings.append(
                f"Worker {worker_id} missing flow/blocks, skipping step extraction"
            )
            continue
        
        # 获取该 worker 拥有的 spans
        worker_span_ids = set(worker.owned_span_ids)
        worker_spans = [s for s in spans if s.span_id in worker_span_ids]
        
        # 提取该 worker 的 steps（使用 worker-scoped prompt）
        worker_steps, symbol_table = self._extract_steps_for_worker(
            worker_spans, routes, flow, blocks, symbol_table, worker
        )
        
        worker_step_plan.worker_steps[worker_id] = worker_steps
    
    # 2. 为 main worker 从 handoffs 生成 INVOKE_WORKER / CALL_API steps
    invoke_steps = self._generate_handoff_steps(
        worker_plan, symbol_table
    )
    main_worker_id = worker_plan.main_worker_id
    worker_step_plan.worker_steps[main_worker_id].extend(invoke_steps)
    
    worker_step_plan.warnings = all_warnings
    return worker_step_plan, symbol_table


def _extract_steps_for_worker(
    self,
    spans: list[SpanIR],
    routes: FieldRouteIR,
    flow: FlowStructureIR,
    blocks: BlockStructureIR,
    symbol_table: SymbolTable,
    worker: WorkerSpecIR,
) -> tuple[list[StepIR], SymbolTable]:
    """Extract steps for a single worker.
    
    关键：prompt 中包含以下变量：
    - worker input contract
    - worker output contract
    - already-known global variables
    - current worker known variables
    - handoff-bound parent variables for main worker
    """
    # 构建 worker-scoped prompt 变量
    prompt_variables = self._build_worker_prompt_variables(
        worker, symbol_table
    )
    
    prompt = self._build_worker_scoped_prompt(
        spans, flow, blocks, prompt_variables, worker
    )
    
    # 调用 LLM 提取 steps
    steps = self._call_llm_for_steps(prompt)
    
    # 验证 steps 只引用该 worker 的 spans（D5: error，不是 warning）
    errors = self._validate_step_span_ownership(steps, worker)
    if errors:
        raise StageError(f"Step span ownership validation failed: {errors}")
    
    return steps, symbol_table


def _build_worker_prompt_variables(
    self,
    worker: WorkerSpecIR,
    symbol_table: SymbolTable,
) -> dict[str, str]:
    """Build variables for worker-scoped prompt.
    
    包含：
    - worker input contract
    - worker output contract
    - already-known global variables
    - current worker known variables
    - handoff-bound parent variables for main worker
    """
    variables = {}
    
    # 1. Worker input contract
    for field in worker.input_contract:
        variables[field.name] = f"[input] {field.data_type}: {field.description}"
    
    # 2. Worker output contract
    for field in worker.output_contract:
        variables[field.name] = f"[output] {field.data_type}: {field.description}"
    
    # 3. Global variables（Phase 1 暂用全局，Phase 2 再 scoped）
    for name, var in symbol_table.variables.items():
        if name not in variables:
            variables[name] = f"[global] {var.data_type}: {var.description}"
    
    return variables


def _generate_handoff_steps(
    self,
    worker_plan: WorkerPlanIR,
    symbol_table: SymbolTable,
) -> list[StepIR]:
    """Generate INVOKE_WORKER / CALL_API steps from handoffs.
    
    关键：只从 WorkerHandoffIR 生成，不从 decisions 生成。（D1）
    """
    handoff_steps = []
    
    for handoff in worker_plan.handoffs:
        if handoff.mode == "invoke":
            step = self._build_invoke_step(handoff, worker_plan)
        elif handoff.mode == "api_call":
            step = self._build_api_call_step(handoff, worker_plan)
        else:
            continue
        
        handoff_steps.append(step)
    
    return handoff_steps


def _build_invoke_step(
    self,
    handoff: WorkerHandoffIR,
    worker_plan: WorkerPlanIR,
) -> StepIR:
    """Build INVOKE_WORKER step from handoff."""
    # 获取被调用 worker
    to_worker = next(
        (w for w in worker_plan.workers if w.worker_id == handoff.to_worker),
        None
    )
    
    # 获取 source spans（优先使用 invoke_location_hint）（D2）
    source_spans = self._get_invoke_source_spans(handoff, worker_plan)
    
    # 从 input_bindings 提取 inputs
    inputs = [b.parent_variable for b in handoff.input_bindings]
    
    # 从 output_bindings 提取 outputs
    outputs = [b.parent_variable for b in handoff.output_bindings]
    
    return StepIR(
        step_id=f"st_invoke_{handoff.handoff_id}",
        text=f"Invoke worker: {to_worker.worker_name if to_worker else handoff.to_worker}",
        source_span_ids=source_spans,
        command_type="INVOKE_WORKER",
        inputs=inputs,
        outputs=outputs,
        kind="invoke",
        handoff_id=handoff.handoff_id,
    )


def _build_api_call_step(
    self,
    handoff: WorkerHandoffIR,
    worker_plan: WorkerPlanIR,
) -> StepIR:
    """Build CALL_API step from handoff."""
    source_spans = self._get_invoke_source_spans(handoff, worker_plan)
    inputs = [b.parent_variable for b in handoff.input_bindings]
    outputs = [b.parent_variable for b in handoff.output_bindings]
    
    return StepIR(
        step_id=f"st_api_{handoff.handoff_id}",
        text=f"Call API: {handoff.api_ref}",
        source_span_ids=source_spans,
        command_type="CALL_API",
        inputs=inputs,
        outputs=outputs,
        integration_ref=handoff.api_ref,
        kind="tool",
        handoff_id=handoff.handoff_id,
    )


def _get_invoke_source_spans(
    self,
    handoff: WorkerHandoffIR,
    worker_plan: WorkerPlanIR,
) -> list[str]:
    """Get source spans for invoke/api_call step.
    
    优先使用 invoke_location_hint，fallback 到 warning。（D2）
    """
    hint = handoff.invoke_location_hint
    
    # 优先使用 caller-owned invocation span
    if hint.after_span_id:
        return [hint.after_span_id]
    if hint.before_span_id:
        return [hint.before_span_id]
    
    # Fallback：不要绑定到 from_worker 的全部 owned spans。
    # 过宽 source_span_ids 会破坏 block 排序，也可能重新引入 ownership 污染。
    self.logger.warning(
        "Handoff %s has no invoke_location_hint; using empty source_span_ids.",
        handoff.handoff_id,
    )
    
    return []


def _validate_step_span_ownership(
    self,
    steps: list[StepIR],
    worker: WorkerSpecIR,
) -> list[str]:
    """Validate that steps only reference worker-owned spans.
    
    D5: span ownership violation 是 error，不是 warning。
    
    Rules:
    - Non-handoff step references span outside owner worker => error
    - Main ordinary step references child-owned span => error
    - Child ordinary step references parent-owned span => error
    - Handoff step source_span_ids must be caller-owned or empty-with-warning
    """
    errors = []
    owned_spans = set(worker.owned_span_ids)
    
    for step in steps:
        # INVOKE_WORKER 和 CALL_API 可以引用 caller span
        if step.command_type in ("INVOKE_WORKER", "CALL_API"):
            # Handoff step source_span_ids 必须是 caller-owned 或 empty
            for span_id in step.source_span_ids:
                if span_id and span_id not in owned_spans:
                    # 这是 warning，不是 error（因为 handoff 可能引用 caller span）
                    self.logger.warning(
                        "Handoff step %s references span %s not owned by worker %s",
                        step.step_id, span_id, worker.worker_id,
                    )
            continue
        
        # 其他 steps 只能引用 owned spans（D5: error）
        for span_id in step.source_span_ids:
            if span_id not in owned_spans:
                errors.append(
                    f"Worker {worker.worker_id} step {step.step_id} "
                    f"references span {span_id} not in owned_span_ids"
                )
    
    return errors
```

#### 3.1.2 修改 Orchestrator

**文件**: `src/nl2spl/pipeline/orchestrator.py`

**新增方法**：

```python
def _run_stage7_worker_scoped(
    self,
    spans: list[SpanIR],
    routes: FieldRouteIR,
    worker_flow_plan: WorkerFlowPlanIR,
    worker_block_plan: WorkerBlockPlanIR,
    symbol_table: SymbolTable,
    worker_plan: WorkerPlanIR,
) -> tuple[WorkerStepPlanIR, SymbolTable]:
    """Run Stage 7 with worker-scoped input."""
    extractor = StepExtractor(self.config, self.llm_client)
    return extractor.execute_worker_scoped(
        spans, routes, worker_flow_plan, worker_block_plan, symbol_table, worker_plan
    )
```

**修改 Stage 7 调用**：

```python
# Stage 7: Step Extraction
self.logger.info("Stage 7: Step Extraction")
if (
    self.config.enable_worker_boundary_planner
    and worker_flow_plan is not None
    and worker_block_plan is not None
    and worker_plan is not None
):
    # Worker-aware path
    worker_step_plan, symbol_table = self._run_stage7_worker_scoped(
        resolved_spans,
        resolved_routes,
        worker_flow_plan,
        worker_block_plan,
        symbol_table,
        worker_plan,
    )
    steps = worker_step_plan.get_all_steps()
    intermediate["stage7_worker_steps"] = worker_step_plan
    worker_stage_warnings.extend(worker_step_plan.warnings)
else:
    # Legacy path
    steps, symbol_table = self._run_stage7(
        resolved_spans,
        resolved_routes,
        flow_structure,
        block_structure,
        symbol_table,
        worker_plan,
    )
intermediate["stage7_steps"] = steps
```

#### 3.1.3 验证标准

**单元测试**：
- [ ] `WorkerStepPlanIR` 构造和访问测试（包含 main_worker_id）
- [ ] `StepExtractor.execute_worker_scoped()` 对单个 worker 提取测试
- [ ] `StepExtractor._generate_handoff_steps()` 从 handoffs 生成 invoke step 测试
- [ ] `StepExtractor._get_invoke_source_spans()` 优先使用 invoke_location_hint 测试
- [ ] `StepExtractor._get_invoke_source_spans()` 缺失 location 时返回空 `source_span_ids` 并产生 warning
- [ ] `StepExtractor._validate_step_span_ownership()` 验证 span ownership 测试（D5: error）

**集成测试**：
- [ ] 端到端测试：输入包含 child worker 的场景
- [ ] 验证 main worker steps 包含 INVOKE_WORKER step
- [ ] 验证 INVOKE_WORKER step 的 source_span_ids 来自 invoke_location_hint
- [ ] 验证缺失 invoke location 不会 fallback 到全部 parent owned spans
- [ ] 验证 child worker steps 只引用 child-owned spans
- [ ] 验证 main worker 普通 steps 不引用 child-owned spans
- [ ] 验证 span ownership violation 抛出 error

**回归测试**：
- [ ] 所有现有测试通过
- [ ] Legacy path 保持不变

---

### Phase 1.5: Worker-aware Stage 9.5

**目标**：在 Stage 10 之前进行 worker-scoped normalization，确保 IR 完整性。

**预估工作量**：2-3 天

#### 3.1.5.1 新增 normalization 方法

**文件**: `src/nl2spl/pipeline/stages/stage9_5_normalizer.py`

```python
def normalize_worker_scoped(
    self,
    worker_flow_plan: WorkerFlowPlanIR,
    worker_block_plan: WorkerBlockPlanIR,
    worker_step_plan: WorkerStepPlanIR,
    worker_plan: WorkerPlanIR,
    resources: ResourceRegistryIR,
    symbol_table: SymbolTable,
) -> tuple[
    WorkerFlowPlanIR,
    WorkerBlockPlanIR,
    WorkerStepPlanIR,
    SymbolTable,
    list[str],  # errors
    list[str],  # warnings
]:
    """Normalize and validate worker-scoped IRs.
    
    校验内容（D5: span ownership violation 是 error）：
    1. main worker steps 不引用 child-owned spans => error
    2. child worker steps 只引用自己 owned spans => error
    3. handoff step 存在且绑定完整 => error/warning
    4. child output 是否被 parent 消费或声明为 final => error
    5. worker-local producer/consumer reachability => warning
    6. CALL_API handoff 和 INVOKE_WORKER handoff 分开校验 => error
    """
    errors = []
    warnings = []
    
    # 1. 验证 span ownership（D5: error）
    span_errors = self._validate_span_ownership(worker_step_plan, worker_plan)
    errors.extend(span_errors)
    
    # 2. 验证 handoff completeness
    handoff_errors, handoff_warnings = self._validate_handoffs(
        worker_step_plan, worker_plan
    )
    errors.extend(handoff_errors)
    warnings.extend(handoff_warnings)
    
    # 3. 验证 output binding
    output_errors = self._validate_output_binding(
        worker_step_plan, worker_plan, symbol_table
    )
    errors.extend(output_errors)
    
    # 4. 验证 producer/consumer reachability
    reachability_warnings = self._validate_reachability(
        worker_step_plan, worker_plan, symbol_table
    )
    warnings.extend(reachability_warnings)
    
    # 5. 分离 invoke 和 api_call handoff 校验
    handoff_type_errors = self._validate_handoff_types(worker_plan)
    errors.extend(handoff_type_errors)
    
    return (
        worker_flow_plan,
        worker_block_plan,
        worker_step_plan,
        symbol_table,
        errors,
        warnings,
    )


def _validate_span_ownership(
    self,
    worker_step_plan: WorkerStepPlanIR,
    worker_plan: WorkerPlanIR,
) -> list[str]:
    """Validate span ownership across workers.
    
    D5: span ownership violation 是 error，不是 warning。
    
    Rules:
    - Non-handoff step references span outside owner worker => error
    - Main ordinary step references child-owned span => error
    - Child ordinary step references parent-owned span => error
    - Handoff step source_span_ids must be caller-owned or empty-with-warning
    """
    errors = []
    
    # 构建 worker -> owned spans 映射
    worker_spans: dict[str, set[str]] = {}
    for worker in worker_plan.workers:
        worker_spans[worker.worker_id] = set(worker.owned_span_ids)
    
    # 检查每个 worker 的 steps
    for worker_id, steps in worker_step_plan.worker_steps.items():
        owned = worker_spans.get(worker_id, set())
        
        for step in steps:
            # INVOKE_WORKER 和 CALL_API 可以引用 caller span
            if step.command_type in ("INVOKE_WORKER", "CALL_API"):
                continue
            
            # 其他 steps 只能引用 owned spans（D5: error）
            for span_id in step.source_span_ids:
                if span_id not in owned:
                    errors.append(
                        f"Worker {worker_id} step {step.step_id} "
                        f"references span {span_id} not in owned_span_ids"
                    )
    
    # 检查 main worker steps 不引用 child-owned spans（D5: error）
    main_worker_id = worker_step_plan.main_worker_id
    main_steps = worker_step_plan.main_worker_steps
    child_spans = set()
    for worker in worker_plan.workers:
        if worker.kind == "child":
            child_spans.update(worker.owned_span_ids)
    
    for step in main_steps:
        if step.command_type in ("INVOKE_WORKER", "CALL_API"):
            continue
        for span_id in step.source_span_ids:
            if span_id in child_spans:
                errors.append(
                    f"Main worker step {step.step_id} "
                    f"references child-owned span {span_id}"
                )
    
    return errors


def _validate_handoffs(
    self,
    worker_step_plan: WorkerStepPlanIR,
    worker_plan: WorkerPlanIR,
) -> tuple[list[str], list[str]]:
    """Validate handoff completeness."""
    errors = []
    warnings = []
    
    # 构建 handoff_id -> [(worker_id, step)] 映射。
    # D10: 不能只检查 handoff_id 是否存在，还必须检查 step shape。
    handoff_steps: dict[str, list[tuple[str, StepIR]]] = {}
    for worker_id, steps in worker_step_plan.worker_steps.items():
        for step in steps:
            if step.handoff_id:
                handoff_steps.setdefault(step.handoff_id, []).append((worker_id, step))

    worker_by_id = {worker.worker_id: worker for worker in worker_plan.workers}

    for handoff in worker_plan.handoffs:
        matching_steps = handoff_steps.get(handoff.handoff_id, [])
        if not matching_steps:
            errors.append(
                f"Handoff {handoff.handoff_id} has no corresponding step"
            )
            continue

        if len(matching_steps) > 1:
            errors.append(
                f"Handoff {handoff.handoff_id} has multiple corresponding steps"
            )
            continue

        step_worker_id, step = matching_steps[0]
        if step_worker_id != handoff.from_worker:
            errors.append(
                f"Handoff {handoff.handoff_id} step is in worker {step_worker_id}, "
                f"expected {handoff.from_worker}"
            )

        expected_inputs = [binding.parent_variable for binding in handoff.input_bindings]
        expected_outputs = [
            binding.parent_variable for binding in handoff.output_bindings
        ]
        if list(step.inputs) != expected_inputs:
            errors.append(
                f"Handoff {handoff.handoff_id} input mismatch: "
                f"{step.inputs} != {expected_inputs}"
            )
        if list(step.outputs) != expected_outputs:
            errors.append(
                f"Handoff {handoff.handoff_id} output mismatch: "
                f"{step.outputs} != {expected_outputs}"
            )

        if handoff.mode == "invoke":
            target = worker_by_id.get(handoff.to_worker or "")
            if step.command_type != "INVOKE_WORKER":
                errors.append(
                    f"Handoff {handoff.handoff_id} expected INVOKE_WORKER step, "
                    f"got {step.command_type}"
                )
            if target is not None and step.integration_ref != target.worker_name:
                errors.append(
                    f"Handoff {handoff.handoff_id} target mismatch: "
                    f"{step.integration_ref} != {target.worker_name}"
                )
        elif handoff.mode == "api_call":
            if step.command_type != "CALL_API":
                errors.append(
                    f"Handoff {handoff.handoff_id} expected CALL_API step, "
                    f"got {step.command_type}"
                )
            if step.integration_ref != handoff.api_ref:
                errors.append(
                    f"Handoff {handoff.handoff_id} api_ref mismatch: "
                    f"{step.integration_ref} != {handoff.api_ref}"
                )
        
        # 检查 input_bindings 完整性
        if not handoff.input_bindings:
            warnings.append(
                f"Handoff {handoff.handoff_id} has no input_bindings"
            )
        
        # 检查 output_bindings 完整性
        if not handoff.output_bindings:
            warnings.append(
                f"Handoff {handoff.handoff_id} has no output_bindings"
            )
    
    return errors, warnings


def _validate_output_binding(
    self,
    worker_step_plan: WorkerStepPlanIR,
    worker_plan: WorkerPlanIR,
    symbol_table: SymbolTable,
) -> list[str]:
    """Validate child output is consumed by parent or declared as final."""
    errors = []
    
    for worker in worker_plan.workers:
        if worker.kind != "child":
            continue
        
        # 获取 child worker 的 output contract
        for output_field in worker.output_contract:
            # 检查是否有 handoff 将此 output 绑定到 parent variable
            bound = False
            for handoff in worker_plan.handoffs:
                if handoff.to_worker != worker.worker_id:
                    continue
                for binding in handoff.output_bindings:
                    if binding.child_output == output_field.name:
                        bound = True
                        break
            
            if not bound:
                errors.append(
                    f"Child worker {worker.worker_id} output "
                    f"'{output_field.name}' is not bound to parent"
                )
    
    return errors


def _validate_reachability(
    self,
    worker_step_plan: WorkerStepPlanIR,
    worker_plan: WorkerPlanIR,
    symbol_table: SymbolTable,
) -> list[str]:
    """Validate worker-local producer/consumer reachability."""
    warnings = []
    
    for worker_id, steps in worker_step_plan.worker_steps.items():
        # 构建该 worker 的 producer/consumer 映射
        producers: dict[str, str] = {}  # variable -> step_id
        consumers: dict[str, list[str]] = {}  # variable -> [step_ids]
        
        for step in steps:
            for output in step.outputs:
                if output in producers:
                    warnings.append(
                        f"Worker {worker_id}: variable '{output}' "
                        f"produced by multiple steps"
                    )
                producers[output] = step.step_id
            
            for input_var in step.inputs:
                if input_var not in consumers:
                    consumers[input_var] = []
                consumers[input_var].append(step.step_id)
        
        # 检查每个 consumer 的 input 是否有 producer
        for input_var, consumer_ids in consumers.items():
            if input_var not in producers:
                # 可能是 worker input，检查 contract
                worker = next(
                    (w for w in worker_plan.workers if w.worker_id == worker_id),
                    None
                )
                if worker:
                    contract_inputs = {f.name for f in worker.input_contract}
                    if input_var not in contract_inputs:
                        warnings.append(
                            f"Worker {worker_id}: variable '{input_var}' "
                            f"consumed but not produced or declared as input"
                        )
    
    return warnings


def _validate_handoff_types(
    self,
    worker_plan: WorkerPlanIR,
) -> list[str]:
    """Validate CALL_API and INVOKE_WORKER handoffs separately."""
    errors = []
    
    for handoff in worker_plan.handoffs:
        if handoff.mode == "invoke":
            # INVOKE_WORKER 必须有 to_worker
            if not handoff.to_worker:
                errors.append(
                    f"INVOKE handoff {handoff.handoff_id} "
                    f"missing to_worker"
                )
            # 检查 to_worker 存在
            to_worker = next(
                (w for w in worker_plan.workers if w.worker_id == handoff.to_worker),
                None
            )
            if not to_worker:
                errors.append(
                    f"INVOKE handoff {handoff.handoff_id} "
                    f"references non-existent worker {handoff.to_worker}"
                )
        
        elif handoff.mode == "api_call":
            # CALL_API 必须有 api_ref
            if not handoff.api_ref:
                errors.append(
                    f"API_CALL handoff {handoff.handoff_id} "
                    f"missing api_ref"
                )
        
        else:
            errors.append(
                f"Handoff {handoff.handoff_id} "
                f"has invalid mode: {handoff.mode}"
            )
    
    return errors
```

#### 3.1.5.2 修改 Orchestrator

```python
def _run_normalization_worker_scoped(
    self,
    worker_flow_plan: WorkerFlowPlanIR,
    worker_block_plan: WorkerBlockPlanIR,
    worker_step_plan: WorkerStepPlanIR,
    worker_plan: WorkerPlanIR,
    resources: ResourceRegistryIR,
    symbol_table: SymbolTable,
) -> tuple[
    WorkerFlowPlanIR,
    WorkerBlockPlanIR,
    WorkerStepPlanIR,
    SymbolTable,
    list[str],
    list[str],
]:
    """Run worker-scoped normalization."""
    normalizer = IRNormalizer()
    return normalizer.normalize_worker_scoped(
        worker_flow_plan,
        worker_block_plan,
        worker_step_plan,
        worker_plan,
        resources,
        symbol_table,
    )
```

**修改 Stage 9.5 调用**：

```python
# Stage 9.5: IR Normalization
self.logger.info("Stage 9.5: IR Normalization")
if (
    self.config.enable_worker_boundary_planner
    and worker_flow_plan is not None
    and worker_block_plan is not None
    and worker_step_plan is not None
    and worker_plan is not None
):
    # Worker-aware path
    norm_result = self._run_normalization_worker_scoped(
        worker_flow_plan,
        worker_block_plan,
        worker_step_plan,
        worker_plan,
        resources,
        symbol_table,
    )
    (
        worker_flow_plan,
        worker_block_plan,
        worker_step_plan,
        symbol_table,
        normalization_errors,
        normalization_warnings,
    ) = norm_result
    worker_stage_warnings.extend(normalization_warnings)
    
    # D5: span ownership violation 是 error
    if normalization_errors:
        raise ValueError(
            "Worker-scoped normalization failed: "
            + "; ".join(normalization_errors)
        )
else:
    # Legacy path
    norm_result = self._run_normalization(
        flow_structure,
        block_structure,
        resources,
        symbol_table,
        steps,
        constraints,
        worker_plan,
    )
    # ...
```

#### 3.1.5.3 验证标准

**单元测试**：
- [ ] `_validate_span_ownership()` 测试（D5: error）
- [ ] `_validate_handoffs()` 测试
- [ ] `_validate_handoffs()` 校验 command_type、integration_ref、input/output binding、step 所在 worker
- [ ] `_validate_output_binding()` 测试
- [ ] `_validate_reachability()` 测试
- [ ] `_validate_handoff_types()` 测试

**集成测试**：
- [ ] 端到端测试：输入包含 child worker 的场景
- [ ] 验证 main worker steps 不引用 child-owned spans
- [ ] 验证 child worker steps 只引用自己 owned spans
- [ ] 验证每个 handoff 都有对应的 step
- [ ] 验证 `mode="invoke"` 只能对应 `INVOKE_WORKER`，`mode="api_call"` 只能对应 `CALL_API`
- [ ] 验证 handoff step 必须位于 `handoff.from_worker` 的 `worker_steps` 中
- [ ] 验证 handoff step 的 inputs/outputs 与 bindings 一致
- [ ] 验证 child output 都被正确绑定
- [ ] 验证 span ownership violation 抛出 error

**回归测试**：
- [ ] 所有现有测试通过
- [ ] Legacy path 保持不变

---

### Phase 1.6: WorkerIR/Renderer child-flow support

**目标**：升级 `ChildWorkerIR` 支持 child flow + steps，修改 Stage 10 和 Stage 11 渲染 child flow。

**预估工作量**：2-4 天

#### 3.1.6.1 升级 ChildWorkerIR（D3 - Frozen）

**文件**: `src/nl2spl/ir/worker_ir.py`

```python
@dataclass
class ChildWorkerIR:
    """Concrete child worker with full flow and steps support.
    
    Attributes:
        worker_name: Child worker name
        description: Child worker description
        task_text: Command text for the delegated task
        inputs: Input specifications
        outputs: Output specifications
        main_flow: Main flow reference
        alternative_flows: Alternative flow references
        exception_flows: Exception flow references
        api_refs: Referenced API names
        steps: Child worker steps
    """
    worker_name: str
    description: str
    task_text: str
    inputs: list[WorkerInput] = field(default_factory=list)
    outputs: list[WorkerOutput] = field(default_factory=list)
    # 新增：支持 child flow
    main_flow: FlowRef = field(default_factory=FlowRef)
    alternative_flows: list[AlternativeFlowRef] = field(default_factory=list)
    exception_flows: list[ExceptionFlowRef] = field(default_factory=list)
    api_refs: list[str] = field(default_factory=list)
    # 新增：支持 child steps
    steps: list[StepIR] = field(default_factory=list)
```

#### 3.1.6.2 修改 Stage 10 WorkerAssembler

**文件**: `src/nl2spl/pipeline/stages/stage10_worker_assembler.py`

**新增方法**：

```python
def assemble_from_worker_scoped(
    self,
    worker_step_plan: WorkerStepPlanIR,
    worker_scoped_resources: WorkerScopedResourceIR | None,
    symbol_table: SymbolTable,
    worker_plan: WorkerPlanIR,
    worker_flow_plan: WorkerFlowPlanIR | None = None,
    worker_block_plan: WorkerBlockPlanIR | None = None,
) -> WorkerIR:
    """Assemble WorkerIR from worker-scoped step plan.
    
    直接从 worker_step_plan 组装，不再依赖 delegation_candidates。
    """
    main_spec = worker_plan.main_worker
    main_worker_id = worker_plan.main_worker_id
    main_steps = worker_step_plan.worker_steps.get(main_worker_id, [])
    
    # Build child workers from worker_step_plan
    child_workers = []
    for worker in worker_plan.workers:
        if worker.kind == "main":
            continue
        
        child_steps = worker_step_plan.worker_steps.get(worker.worker_id, [])
        child_flow = worker_flow_plan.worker_flows.get(worker.worker_id) if worker_flow_plan else None
        child_blocks = worker_block_plan.worker_blocks.get(worker.worker_id) if worker_block_plan else None
        
        child_worker = self._build_child_worker(
            worker, child_steps, child_flow, child_blocks, symbol_table
        )
        child_workers.append(child_worker)
    
    # Build main flow from main_steps
    main_blocks = worker_block_plan.worker_blocks.get(main_worker_id) if worker_block_plan else None
    if main_blocks and main_blocks.main_flow_blocks:
        main_flow = FlowRef(blocks=main_blocks.main_flow_blocks)
    else:
        main_flow = FlowRef(blocks=[fallback_block_for_steps("b_main", main_steps)])
    
    # Build inputs/outputs from contract
    inputs = (
        self._inputs_from_contract(main_spec.input_contract)
        if main_spec is not None
        else []
    )
    outputs = (
        self._outputs_from_contract(main_spec.output_contract)
        if main_spec is not None
        else []
    )
    
    # Collect API refs
    api_refs = list({
        s.integration_ref
        for s in main_steps
        if s.integration_ref is not None and s.command_type == "CALL_API"
    })
    
    return WorkerIR(
        worker_name=main_spec.worker_name if main_spec else "main",
        description=main_spec.description if main_spec else "",
        inputs=inputs,
        outputs=outputs,
        main_flow=main_flow,
        child_workers=child_workers,
        api_refs=api_refs,
    )


def _build_child_worker(
    self,
    worker: WorkerSpecIR,
    steps: list[StepIR],
    flow: FlowStructureIR | None,
    blocks: BlockStructureIR | None,
    symbol_table: SymbolTable,
) -> ChildWorkerIR:
    """Build a ChildWorkerIR from worker spec, steps, flow, and blocks.
    
    Args:
        worker: Worker specification
        steps: Child worker steps
        flow: Child worker flow (if available)
        blocks: Child worker blocks (if available)
        symbol_table: Symbol table
        
    Returns:
        ChildWorkerIR with full flow and steps support
    """
    # Build main flow from blocks
    if blocks and blocks.main_flow_blocks:
        main_flow = FlowRef(blocks=blocks.main_flow_blocks)
    else:
        # Fallback: create single block from steps
        main_flow = FlowRef(
            blocks=[fallback_block_for_steps(f"b_{worker.worker_id}_main", steps)]
        )
    
    # Build alternative flows
    alternative_flows = []
    if blocks and flow:
        for alt_flow in flow.alternative_flows:
            alt_blocks = blocks.alternative_flow_blocks.get(alt_flow.flow_id, [])
            alternative_flows.append(
                AlternativeFlowRef(
                    flow_id=alt_flow.flow_id,
                    condition_text=alt_flow.condition_text,
                    blocks=alt_blocks,
                )
            )
    
    # Build exception flows
    exception_flows = []
    if blocks and flow:
        for exc_flow in flow.exception_flows:
            exc_blocks = blocks.exception_flow_blocks.get(exc_flow.flow_id, [])
            exception_flows.append(
                ExceptionFlowRef(
                    flow_id=exc_flow.flow_id,
                    condition_text=exc_flow.condition_text,
                    blocks=exc_blocks,
                )
            )
    
    # Collect API refs
    api_refs = list({
        s.integration_ref
        for s in steps
        if s.integration_ref is not None and s.command_type == "CALL_API"
    })
    
    return ChildWorkerIR(
        worker_name=worker.worker_name,
        description=worker.description,
        task_text=f"Worker: {worker.worker_name}",
        inputs=[
            WorkerInput(name=f.name, required=f.required)
            for f in worker.input_contract
        ],
        outputs=[
            WorkerOutput(name=f.name, required=f.required)
            for f in worker.output_contract
        ],
        main_flow=main_flow,
        alternative_flows=alternative_flows,
        exception_flows=exception_flows,
        api_refs=api_refs,
        steps=steps,  # ← 关键：renderer 需要
    )
```

#### 3.1.6.3 修改 Stage 11 SPLRenderer

**文件**: `src/nl2spl/pipeline/stages/stage11_spl_renderer.py`

**修改 `_render_child_worker()`**：

```python
def _render_child_worker(self, child: ChildWorkerIR, indent: int) -> list[str]:
    """Render child worker with full flow support.
    
    使用 child.main_flow.blocks 和 child.steps 渲染，
    而不是 synthetic st_child。
    """
    lines = []
    prefix = " " * indent
    
    # 渲染 worker 头
    lines.append(f"{prefix}worker {child.worker_name}")
    lines.append(f"{prefix}  description \"{child.description}\"")
    
    # 渲染 inputs
    if child.inputs:
        lines.append(f"{prefix}  inputs")
        for inp in child.inputs:
            required = "required" if inp.required else "optional"
            lines.append(f"{prefix}    {inp.name} ({required})")
    
    # 渲染 outputs
    if child.outputs:
        lines.append(f"{prefix}  outputs")
        for out in child.outputs:
            required = "required" if out.required else "optional"
            lines.append(f"{prefix}    {out.name} ({required})")
    
    # 渲染 main flow blocks（使用 child.steps）
    if child.main_flow.blocks:
        lines.append(f"{prefix}  flow main")
        for block in child.main_flow.blocks:
            lines.extend(self._render_block(block, child.steps, indent + 4))
    
    # 渲染 alternative flows
    for alt_flow in child.alternative_flows:
        lines.append(f"{prefix}  flow {alt_flow.flow_id}")
        lines.append(f"{prefix}    condition \"{alt_flow.condition_text}\"")
        for block in alt_flow.blocks:
            lines.extend(self._render_block(block, child.steps, indent + 4))
    
    # 渲染 exception flows
    for exc_flow in child.exception_flows:
        lines.append(f"{prefix}  exception {exc_flow.flow_id}")
        lines.append(f"{prefix}    condition \"{exc_flow.condition_text}\"")
        for block in exc_flow.blocks:
            lines.extend(self._render_block(block, child.steps, indent + 4))
    
    return lines


def _render_block(
    self,
    block: BlockIR,
    steps: list[StepIR],
    indent: int,
) -> list[str]:
    """Render a block with its steps."""
    lines = []
    prefix = " " * indent
    
    # 获取该 block 内的 steps
    block_steps = [s for s in steps if s.step_id in block.spans]
    
    if block.block_type == "SEQUENTIAL":
        for step in block_steps:
            lines.extend(self._render_step(step, indent))
    elif block.block_type == "IF":
        lines.append(f"{prefix}if {block.condition_text}")
        for step in block_steps:
            lines.extend(self._render_step(step, indent + 2))
        lines.append(f"{prefix}endif")
    elif block.block_type == "FOR":
        lines.append(f"{prefix}for {block.condition_text}")
        for step in block_steps:
            lines.extend(self._render_step(step, indent + 2))
        lines.append(f"{prefix}endfor")
    elif block.block_type == "WHILE":
        lines.append(f"{prefix}while {block.condition_text}")
        for step in block_steps:
            lines.extend(self._render_step(step, indent + 2))
        lines.append(f"{prefix}endwhile")
    
    return lines


def _render_step(self, step: StepIR, indent: int) -> list[str]:
    """Render a single step."""
    lines = []
    prefix = " " * indent
    
    if step.command_type == "INVOKE_WORKER":
        lines.append(f"{prefix}command {step.step_id}")
        lines.append(f"{prefix}  description \"{step.text}\"")
        lines.append(f"{prefix}  invoke_worker")
    elif step.command_type == "CALL_API":
        lines.append(f"{prefix}command {step.step_id}")
        lines.append(f"{prefix}  description \"{step.text}\"")
        lines.append(f"{prefix}  call_api {step.integration_ref}")
    else:
        lines.append(f"{prefix}command {step.step_id}")
        lines.append(f"{prefix}  description \"{step.text}\"")
    
    # 渲染 inputs/outputs
    if step.inputs:
        lines.append(f"{prefix}  inputs {', '.join(step.inputs)}")
    if step.outputs:
        lines.append(f"{prefix}  outputs {', '.join(step.outputs)}")
    
    return lines
```

#### 3.1.6.4 验证标准

**单元测试**：
- [ ] `ChildWorkerIR` 构造测试（包含 main_flow, steps, alternative_flows, exception_flows）
- [ ] `WorkerAssembler._build_child_worker()` 测试
- [ ] `SPLRenderer._render_child_worker()` 测试
- [ ] `SPLRenderer._render_block()` 测试
- [ ] `SPLRenderer._render_step()` 测试

**集成测试**：
- [ ] 端到端测试：输入包含 child worker 的场景
- [ ] 验证生成的 `ChildWorkerIR` 包含正确的 flow 和 steps
- [ ] 验证 Stage 11 能正确渲染 child worker 的 flow（不是 synthetic st_child）
- [ ] 验证渲染的 SPL 包含 child worker 的完整 flow

**回归测试**：
- [ ] 所有现有测试通过
- [ ] Legacy path 保持不变

---

### Phase 2: WorkerScopedResourceIR / Scoped SymbolTable

**目标**：让 Stage 6 支持 worker scope，明确 global/main/child/handoff 变量可见性。

**预估工作量**：4-7 天

#### 3.2.1 新增数据结构

**文件**: `src/nl2spl/ir/resource_registry_ir.py`

```python
@dataclass
class WorkerScopedResourceIR:
    """Worker-scoped resource extraction result.
    
    Attributes:
        global_resources: Resources visible to all workers
        worker_resources: Resources keyed by worker_id
        handoff_contracts: Handoff contracts between workers
    """
    global_resources: ResourceRegistryIR = field(default_factory=ResourceRegistryIR)
    worker_resources: dict[str, ResourceRegistryIR] = field(default_factory=dict)
    handoff_contracts: dict[str, HandoffContractIR] = field(default_factory=dict)
```

**文件**: `src/nl2spl/ir/worker_plan_ir.py`

```python
@dataclass
class HandoffContractIR:
    """Handoff contract between parent and child worker."""
    handoff_id: str
    parent_worker_id: str
    child_worker_id: str
    input_variables: list[ContractFieldIR] = field(default_factory=list)
    output_variables: list[ContractFieldIR] = field(default_factory=list)
```

#### 3.2.2 修改 SymbolTable 支持 scope key（D4 - Frozen）

**文件**: `src/nl2spl/ir/symbol_table.py`

```python
@dataclass
class VariableSymbol:
    """Variable symbol information."""
    name: str
    data_type: str
    source: str
    description: str
    # 新增：scope 支持
    scope_kind: Literal["global", "worker", "handoff"] = "global"
    scope_id: str | None = None  # worker_id 或 handoff_id
    # 保留原有字段兼容性
    flow_ref: str = "main"
    block_ref: str | None = None
    producer_step: str | None = None
    consumer_steps: list[str] = field(default_factory=list)
    declared: bool = True


class SymbolTable:
    """Symbol table for variable management.
    
    支持 worker-scoped variables。
    """

    def __init__(self) -> None:
        """Initialize empty symbol table."""
        # 使用复合 key：(scope_kind, scope_id, name)
        self._variables: dict[tuple[str, str | None, str], VariableSymbol] = {}
        # 兼容旧接口
        self.variables: dict[str, VariableSymbol] = {}

    def declare_scoped(
        self,
        name: str,
        data_type: str,
        source: str,
        description: str,
        scope_kind: Literal["global", "worker", "handoff"] = "global",
        scope_id: str | None = None,
    ) -> None:
        """Declare a variable with scope.
        
        Args:
            name: Variable name
            data_type: Data type
            source: Variable source
            description: Variable description
            scope_kind: Scope kind
            scope_id: Scope ID (worker_id 或 handoff_id)
        """
        key = (scope_kind, scope_id, name)
        self._variables[key] = VariableSymbol(
            name=name,
            data_type=data_type,
            source=source,
            description=description,
            scope_kind=scope_kind,
            scope_id=scope_id,
        )
        
        # 兼容旧接口：global 变量也加入 self.variables
        if scope_kind == "global":
            self.variables[name] = self._variables[key]

    def get_variables_for_worker(self, worker_id: str) -> dict[str, VariableSymbol]:
        """Get variables visible to a worker.
        
        Returns global + worker-scoped variables.
        """
        result = {}
        
        # Global variables
        for key, var in self._variables.items():
            if key[0] == "global":
                result[var.name] = var
        
        # Worker-scoped variables
        for key, var in self._variables.items():
            if key[0] == "worker" and key[1] == worker_id:
                result[var.name] = var
        
        return result

    def get_variables_for_handoff(self, handoff_id: str) -> dict[str, VariableSymbol]:
        """Get variables visible to a handoff."""
        result = {}
        
        # Global variables
        for key, var in self._variables.items():
            if key[0] == "global":
                result[var.name] = var
        
        # Handoff-scoped variables
        for key, var in self._variables.items():
            if key[0] == "handoff" and key[1] == handoff_id:
                result[var.name] = var
        
        return result

    def get_variable_list_for_worker_prompt(self, worker_id: str) -> str:
        """Generate variable list text for a specific worker's LLM prompt."""
        visible_vars = self.get_variables_for_worker(worker_id)
        if not visible_vars:
            return "No variables available."
        
        lines = []
        for var in visible_vars.values():
            scope_info = ""
            if var.scope_kind == "worker":
                scope_info = f" [worker: {var.scope_id}]"
            elif var.scope_kind == "handoff":
                scope_info = f" [handoff: {var.scope_id}]"
            lines.append(
                f"- {var.name}: {var.data_type} ({var.source}){scope_info} - {var.description}"
            )
        return "\n".join(lines)

    def get_all_declared_variables(self) -> dict[str, VariableSymbol]:
        """Get all declared variables for SPL DEFINE_VARIABLES.
        
        包含：
        - global variables
        - all contract variables (input/output)
        - all rendered step variables
        
        不包含：
        - worker-internal variables (除非被声明为 contract)
        """
        result = {}
        
        for key, var in self._variables.items():
            # global 变量 always included
            if key[0] == "global":
                result[var.name] = var
            # contract variables (input/output) always included
            elif var.source in ("input", "output"):
                result[var.name] = var
            # rendered step variables included if declared
            elif var.declared:
                result[var.name] = var
        
        return result
```

#### 3.2.3 修改 Stage 6 ResourceExtractor

**文件**: `src/nl2spl/pipeline/stages/stage6_resource_extractor.py`

```python
def execute_worker_scoped(
    self,
    spans: list[SpanIR],
    routes: FieldRouteIR,
    worker_flow_plan: WorkerFlowPlanIR,
    worker_block_plan: WorkerBlockPlanIR,
    worker_plan: WorkerPlanIR,
    canonical_input: CanonicalCompileInput,
) -> tuple[WorkerScopedResourceIR, SymbolTable]:
    """Execute worker-scoped resource extraction."""
    worker_scoped_resources = WorkerScopedResourceIR()
    symbol_table = SymbolTable()
    
    # 1. Extract global resources (from main worker)
    main_worker = worker_plan.main_worker
    if main_worker:
        main_flow = worker_flow_plan.worker_flows.get(worker_plan.main_worker_id)
        main_blocks = worker_block_plan.worker_blocks.get(worker_plan.main_worker_id)
        
        if main_flow and main_blocks:
            main_span_ids = set(main_worker.owned_span_ids)
            main_spans = [s for s in spans if s.span_id in main_span_ids]
            
            global_resources, symbol_table = self._extract_resources_for_scope(
                main_spans, routes, main_flow, main_blocks, symbol_table,
                canonical_input, scope_kind="global"
            )
            worker_scoped_resources.global_resources = global_resources
    
    # 2. Extract worker-scoped resources
    for worker in worker_plan.workers:
        if worker.kind == "main":
            continue
        
        worker_id = worker.worker_id
        flow = worker_flow_plan.worker_flows.get(worker_id)
        blocks = worker_block_plan.worker_blocks.get(worker_id)
        
        if flow is None or blocks is None:
            continue
        
        worker_span_ids = set(worker.owned_span_ids)
        worker_spans = [s for s in spans if s.span_id in worker_span_ids]
        
        worker_resources, symbol_table = self._extract_resources_for_scope(
            worker_spans, routes, flow, blocks, symbol_table,
            canonical_input, scope_kind="worker", scope_id=worker_id
        )
        worker_scoped_resources.worker_resources[worker_id] = worker_resources
    
    # 3. Extract handoff contracts
    for handoff in worker_plan.handoffs:
        handoff_contract = self._build_handoff_contract(handoff, symbol_table)
        worker_scoped_resources.handoff_contracts[handoff.handoff_id] = handoff_contract
    
    return worker_scoped_resources, symbol_table


def _extract_resources_for_scope(
    self,
    spans: list[SpanIR],
    routes: FieldRouteIR,
    flow: FlowStructureIR,
    blocks: BlockStructureIR,
    symbol_table: SymbolTable,
    canonical_input: CanonicalCompileInput,
    scope_kind: Literal["global", "worker", "handoff"] = "global",
    scope_id: str | None = None,
) -> tuple[ResourceRegistryIR, SymbolTable]:
    """Extract resources for a specific scope."""
    # 类似现有 execute() 逻辑，但使用 symbol_table.declare_scoped()
    # ...
```

#### 3.2.4 验证标准

**单元测试**：
- [ ] `VariableSymbol` 构造测试（包含 scope_kind, scope_id）
- [ ] `SymbolTable.declare_scoped()` 测试
- [ ] `SymbolTable.get_variables_for_worker()` 测试
- [ ] `SymbolTable.get_variables_for_handoff()` 测试
- [ ] `SymbolTable.get_all_declared_variables()` 测试
- [ ] 验证同名不同 scope 的变量可以共存

**集成测试**：
- [ ] 端到端测试：输入包含 child worker 的场景
- [ ] 验证 global variables 对所有 worker 可见
- [ ] 验证 worker-scoped variables 只对对应 worker 可见
- [ ] 验证 handoff contracts 正确提取
- [ ] 验证 SPL DEFINE_VARIABLES 包含正确的变量

**回归测试**：
- [ ] 所有现有测试通过
- [ ] Legacy path 保持不变

---

### Phase 3: worker-aware path 去 adapter

**目标**：让 worker-aware path 不再读取 `delegation_candidates`，legacy path 可以继续保留。

**预估工作量**：2-3 天

**时机**：Phase 1.6 后即可提前部分 Phase 3（D7）

#### 3.3.1 修改 worker-aware path

**关键设计决策**（D6 - Frozen）：

```text
worker-aware production path 不再读取 delegation_candidates
legacy path 仍可保留 delegation_candidates
等 legacy delegation 也迁完，再真正删除字段和 adapter
```

**文件**: `src/nl2spl/pipeline/orchestrator.py`

```python
# Stage 4: Flow Assembly
self.logger.info("Stage 4: Flow Assembly")
if self.config.enable_worker_boundary_planner:
    # Worker-aware path
    worker_flow_plan = self._run_stage4(resolved_spans, resolved_routes, worker_plan)
    if not isinstance(worker_flow_plan, WorkerFlowPlanIR):
        raise TypeError("Worker-aware Stage 4 must return WorkerFlowPlanIR")
    worker_stage_warnings.extend(worker_flow_plan.warnings)
    intermediate["stage4_worker_flows"] = worker_flow_plan
    
    # 不再调用 worker_flow_plan_to_legacy_main_flow()
    # 不再设置 flow_structure = ...
else:
    # Legacy path
    flow_structure = self._run_stage4(resolved_spans, resolved_routes)
    intermediate["stage4_flow"] = flow_structure
```

#### 3.3.2 保留 legacy adapter

**文件**: `src/nl2spl/pipeline/worker_plan_adapter.py`

**保留此文件**，因为：
- legacy path 仍需要 `delegation_candidates`
- 旧测试仍依赖此适配器
- 等 legacy delegation 也迁完，再删除

#### 3.3.3 验证标准

**集成测试**：
- [ ] 端到端测试：worker-aware path 不读取 `delegation_candidates`
- [ ] 端到端测试：legacy path 仍能正常使用 `delegation_candidates`

**回归测试**：
- [ ] 所有现有测试通过
- [ ] 无功能退化

---

## 4. 实施计划

### 4.1 依赖关系

```
Phase 0: 修正文档和 IR contract
├── 0.1 修正 WorkerStepPlanIR
├── 0.2 明确 INVOKE_WORKER 生成规则 (D1)
├── 0.3 明确 INVOKE_WORKER source_span_ids 规则 (D2)
├── 0.4 决定 ChildWorkerIR 升级方案 (D3)
├── 0.5 决定 SymbolTable scope 方案 (D4)
├── 0.6 决定 span ownership violation 策略 (D5)
├── 0.7 决定 Phase 3 策略 (D6, D7)
├── 0.8 决定 WorkerPlanIR main worker accessor 策略 (D8)
├── 0.9 决定 BlockIR.spans 与 StepIR.source_span_ids 匹配规则 (D9)
└── 0.10 决定 handoff step shape 校验规则 (D10)
    ↓
Phase 1: WorkerScopedStepIR + Stage 7
├── 1.1 修改 Stage 7 StepExtractor
├── 1.2 修改 Orchestrator
└── 1.3 验证
    ↓
Phase 1.5: Worker-aware Stage 9.5
├── 1.5.1 新增 normalization 方法
├── 1.5.2 修改 Orchestrator
└── 1.5.3 验证
    ↓
Phase 1.6: WorkerIR/Renderer child-flow support
├── 1.6.1 升级 ChildWorkerIR (D3)
├── 1.6.2 修改 Stage 10 WorkerAssembler
├── 1.6.3 修改 Stage 11 SPLRenderer
└── 1.6.4 验证
    ↓
Phase 3 (部分): worker-aware path 去 adapter (D7)
├── 3.1 修改 worker-aware path
├── 3.2 保留 legacy adapter (D6)
└── 3.3 验证
    ↓
Phase 2: WorkerScopedResourceIR / Scoped SymbolTable
├── 2.1 新增数据结构
├── 2.2 修改 SymbolTable (D4)
├── 2.3 修改 Stage 6 ResourceExtractor
└── 2.4 验证
    ↓
Phase 3 (剩余): 完全去 adapter
├── 3.4 删除 legacy adapter (如果 legacy delegation 已迁完)
└── 3.5 验证
```

### 4.2 时间安排

| Phase | 工作内容 | 预估时间 | 依赖 |
|-------|----------|----------|------|
| Phase 0 | 修正文档和 IR contract | 1 天 | 无 |
| Phase 1 | WorkerScopedStepIR + Stage 7 | 3-5 天 | Phase 0 |
| Phase 1.5 | Worker-aware Stage 9.5 | 2-3 天 | Phase 1 |
| Phase 1.6 | WorkerIR/Renderer child-flow support | 2-4 天 | Phase 1.5 |
| Phase 3 (部分) | worker-aware path 去 adapter | 1-2 天 | Phase 1.6 |
| Phase 2 | WorkerScopedResourceIR + Scoped SymbolTable | 4-7 天 | Phase 1.6 |
| Phase 3 (剩余) | 完全去 adapter | 1-2 天 | Phase 2 |
| **总计** | | **14-24 天（2-3 周）** | |

### 4.3 里程碑

1. **Phase 0 完成**：IR contract 明确，设计缺口已修正，10 个决策已冻结
2. **Phase 1 完成**：Stage 7 能按 worker_id 输出 steps，invoke step 从 handoffs 生成
3. **Phase 1.5 完成**：Stage 9.5 能校验 worker-scoped IR 的完整性，span ownership violation 是 error
4. **Phase 1.6 完成**：ChildWorkerIR 能承载 child flow + steps，Stage 11 能渲染 child flow
5. **Phase 3 (部分) 完成**：worker-aware path 不再读取 delegation_candidates
6. **Phase 2 完成**：SymbolTable 支持 worker scope，Stage 6 支持 worker-scoped 资源提取
7. **Phase 3 (剩余) 完成**：完全去 adapter（如果 legacy delegation 已迁完）

---

## 5. 风险控制

### 5.1 风险识别

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| Phase 1 改动 Stage 7 核心逻辑 | 高 | 保留 legacy path，通过配置开关控制 |
| ChildWorkerIR 升级影响 Stage 11 渲染 | 高 | Phase 1.6 单独验证渲染 |
| SymbolTable scope 改动影响面大 | 中 | 渐进式迁移，Phase 2 保留 legacy 接口 |
| 测试覆盖不足 | 高 | 每个 Phase 完成后运行完整测试套件 |
| 性能退化 | 低 | 每个 Phase 进行性能基准测试 |
| SPL 语法不支持 worker-local DEFINE_VARIABLES | 中 | Phase 2 需要设计 DEFINE_VARIABLES 策略 |

### 5.2 回退策略

每个 Phase 都保留 legacy 路径，通过配置开关控制：

```python
# config.py
class PipelineConfig:
    enable_worker_boundary_planner: bool = False  # 现有
    enable_worker_scoped_stages: bool = False  # 新增
```

如果出现问题，可以通过配置开关快速回退到 legacy 路径。

### 5.3 代码审查

每个 Phase 的 PR 需要：
- 至少两人审查
- 所有测试通过
- 无类型错误
- 文档更新

---

## 6. 测试策略

### 6.1 测试类型

1. **单元测试**：测试每个新增/修改的类和方法
2. **集成测试**：测试端到端流程
3. **回归测试**：确保现有功能不退化

### 6.2 测试数据

准备以下测试场景：
1. **单 worker**：只有 main worker，无 child worker
2. **多 worker**：main worker + 1-2 个 child worker
3. **复杂 handoff**：parent-child 之间有多个 handoff
4. **同名变量**：不同 worker 内部有同名变量
5. **span ownership violation**：验证 error 正确抛出

### 6.3 测试覆盖率目标

- 新增代码：100% 覆盖率
- 修改代码：90% 覆盖率
- 整体项目：80% 覆盖率

---

## 7. 附录

### 7.1 相关文件列表

**需要修改的文件**：
- `src/nl2spl/ir/worker_plan_ir.py` - 新增 WorkerStepPlanIR, HandoffContractIR
- `src/nl2spl/ir/worker_ir.py` - 升级 ChildWorkerIR
- `src/nl2spl/ir/resource_registry_ir.py` - 新增 WorkerScopedResourceIR
- `src/nl2spl/ir/symbol_table.py` - 修改 SymbolTable 支持 scope
- `src/nl2spl/pipeline/stages/stage6_resource_extractor.py` - 新增 worker-aware 方法
- `src/nl2spl/pipeline/stages/stage7_step_extractor.py` - 新增 worker-aware 方法
- `src/nl2spl/pipeline/stages/stage9_5_normalizer.py` - 新增 worker-aware 方法
- `src/nl2spl/pipeline/stages/stage10_worker_assembler.py` - 新增 worker-aware 方法
- `src/nl2spl/pipeline/stages/stage11_spl_renderer.py` - 修改 child worker 渲染
- `src/nl2spl/pipeline/orchestrator.py` - 修改 pipeline 流程

**保留的文件**（Phase 3 不删除）：
- `src/nl2spl/pipeline/worker_plan_adapter.py` - 保留给 legacy path

**需要新增的测试文件**：
- `tests/ir/test_worker_step_plan_ir.py`
- `tests/ir/test_worker_scoped_resource_ir.py`
- `tests/ir/test_symbol_table_scoped.py`
- `tests/pipeline/stages/test_stage7_worker_scoped.py`
- `tests/pipeline/stages/test_stage9_5_worker_scoped.py`
- `tests/pipeline/stages/test_stage10_worker_scoped.py`
- `tests/pipeline/stages/test_stage11_child_worker_render.py`

### 7.2 术语表

| 术语 | 定义 |
|------|------|
| Worker | SPL 工作单元，可以是 main worker 或 child worker |
| Worker-aware | 能够识别和处理多个 worker 的能力 |
| Legacy path | 旧版处理路径，使用适配器转换 |
| Worker-scoped | 按 worker 作用域隔离的 |
| Handoff | parent-child worker 之间的数据传递 |
| Delegation candidate | 旧版系统中识别的可委托任务 |
| Invoke location hint | handoff 的调用位置提示 |
| Synthetic st_child | Stage 11 当前用于渲染 child worker 的 synthetic step |

### 7.3 关键设计决策记录（Frozen）

| # | 决策 | 结论 | 理由 |
|---|------|------|------|
| D1 | INVOKE_WORKER 生成规则 | 从 `WorkerHandoffIR` 生成，不从 `WorkerBoundaryDecisionIR` 生成 | handoff 是真正的调用边 |
| D2 | INVOKE_WORKER source_span_ids | 优先使用 `invoke_location_hint`；缺失 location 时返回空 `source_span_ids` 并 warning，不 fallback 到全部 `from_worker.owned_span_ids` | 避免 main step 绑定过宽或引用 child-owned span |
| D3 | ChildWorkerIR 升级 | 采用方案 A，增加 `main_flow` + `steps` 字段 | 改动小，与 Stage 11 兼容 |
| D4 | SymbolTable scope | 使用复合 key `(scope_kind, scope_id, name)` | 支持同名不同 scope |
| D5 | span ownership violation | **error**，不是 warning | span ownership 是 WorkerPlanIR 核心 invariant |
| D6 | Phase 3 策略 | worker-aware path 去 adapter，但保留 legacy path | 等 legacy delegation 迁完再删除 |
| D7 | Phase 3 时机 | Phase 1.6 后即可提前部分 Phase 3 | Stage 7/9.5/10 worker-scoped 后即可不读 delegation_candidates |
| D8 | Main worker accessor | 在 `WorkerPlanIR` 增加 `main_worker` property，或统一使用 helper 取 main worker；本文推荐增加 property | 避免各阶段重复手写 lookup，降低接口误用 |
| D9 | BlockIR.spans 语义 | `BlockIR.spans` 默认保存 source span ids；fallback block 应使用 step 的 `source_span_ids`，若使用 step ids 必须同时设置 `step.block_ref` | 当前 renderer 通过 `block.spans` 匹配 `StepIR.source_span_ids` |
| D10 | Handoff step shape 校验 | Stage 9.5 必须校验 handoff step 的 command_type、worker/api target、inputs、outputs、所在 worker | 只检查 handoff_id 存在不足以保证调用正确 |

---

**文档结束**
