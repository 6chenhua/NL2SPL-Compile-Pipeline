# IRS 核心概念详解

> IRS = **Information Requirements Specification**（信息需求规格层）。
> IRS checker / runner = 在规格之上执行的 satisfaction analysis。

## ConstructIRS — 规格定义

`ConstructIRS` 是 SPL construct 的信息需求规格。每种 construct 类型注册一个。

```python
@dataclass
class ConstructIRS:
    construct_type: str                          # 如 "EXCEPTION_FLOW"
    existence_policy: ExistencePolicy            # 何时应存在
    source_signals: list[str]                    # 触发存在的信号
    slots: list[SlotSpec]                        # 信息槽位列表
    no_demand_behavior: NoDemandBehavior         # 无需求时行为
    partial_rendering_allowed: bool              # 是否允许部分渲染
    description: str | None = None
```

`ExistencePolicy` 取值：`source_signal_required` / `compiler_default_allowed` / `grammar_required_if_parent_exists`

`NoDemandBehavior` 取值：`do_not_generate` / `generate_default` / `report_ambiguity`

---

## SlotSpec — 信息槽位

```python
@dataclass
class SlotSpec:
    slot_name: str
    syntax_required: bool = False
    required_for_partial: bool = False      # 缺则 blocked
    required_for_complete: bool = False     # 缺则 partial（若允许）
    renderable_without: bool = False        # 缺失时是否仍可渲染
    evidence_kinds: list[str] = field(default_factory=list)
    missing_diagnostic: str | None = None   # 缺失时的 diagnostic kind
    can_be_inferred: bool = False
    can_be_suggested: bool = True
```

关键语义：
- 缺 `required_for_partial` → **blocked**，停止下钻
- 缺 `required_for_complete` 但 `partial_rendering_allowed=True` → **partial**，形成 cutline
- `renderable_without=False` 的槽位缺失 → 不可渲染

---

## ConstructInstance — 实例标准化

把具体 IR 中的 construct 标准化为可检查实例：

```python
@dataclass
class ConstructInstance:
    construct_id: str
    construct_type: str
    ir_ref: object | None
    materialized: bool          # 是否已被 materialize
    source_demanded: bool       # 源文本是否有需求信号
    candidate_only: bool        # 是否仅为候选（不可渲染）
    primary_parent_id: str | None
    construct_path: tuple[str, ...]
    source_span_ids: list[str]
    metadata: dict[str, Any]
```

### 状态语义表

| materialized | source_demanded | candidate_only | 行为 |
|---|---|---|---|
| True | True | False | 检查 materialized construct 的 IRS |
| False | True | True | report-only satisfaction，**不渲染 SPL construct** |
| False | False | — | **不创建 instance**，不产生 diagnostic |
| — | — | True | **不得被 renderer 或 gate 当成可执行 construct** |

### 典型映射

```text
WorkerPlanIR.candidates[]     → WORKER_CANDIDATE  (materialized=F, source_demanded=T, candidate_only=T)
WorkerPlanIR.candidates[]     → WORKER_PROMOTION  (materialized=F, source_demanded=T, candidate_only=T)
WorkerPlanIR.workers[kind!=main] → CHILD_WORKER   (materialized=T, source_demanded=T, candidate_only=F)
WorkerHandoffIR               → WORKER_HANDOFF    (materialized=T, source_demanded=T, candidate_only=F)
```

---

## ConstructSatisfactionReport — 满足度报告

```python
@dataclass
class ConstructSatisfactionReport:
    # 核心字段
    construct_id: str
    construct_type: str
    slots: list[SlotSatisfaction]
    completeness: ConstructCompleteness  # "complete" | "partial" | "blocked"
    renderable: bool

    # v6 扩展字段（均有默认值，兼容旧 checker）
    primary_parent_id: str | None = None
    child_construct_ids: list[str] = field(default_factory=list)
    related_edges: list[ConstructEdge] = field(default_factory=list)
    construct_path: tuple[str, ...] = ()
    source_span_ids: list[str] = field(default_factory=list)
    source_section_id: str | None = None
    source_packet_id: str | None = None
    cutline_reason: CutlineReason | None = None
    frontier_status: FrontierStatus = "leaf"
    metadata: dict[str, Any] = field(default_factory=dict)
```

### SlotSatisfaction

```python
@dataclass
class SlotSatisfaction:
    slot_name: str
    status: SlotStatus  # "satisfied" | "missing" | "inferred" | "assumed" | "not_applicable"
    source_span_ids: list[str] = field(default_factory=list)
    source_section_id: str | None = None
    source_packet_id: str | None = None
    relation: Literal["direct", "normalized", "inferred", "assumed"] | None = None
    diagnostic_kind: str | None = None
    explanation: str | None = None
```

---

## Frontier / Cutline — 部分求值边界

控制递归检查何时停止：

```text
缺 required_for_partial → blocked → 停止下钻
缺 required_for_complete 但允许 partial → partial → cutline → 不为缺失 child 造 report
有 source-backed child evidence → 才继续检查 child
无 source-backed child evidence → 不生成 child report
```

### FrontierStatus

| 值 | 含义 |
|---|---|
| `continue` | 可以继续检查 child |
| `leaf` | 叶子节点，无 child |
| `cutline_partial` | 缺 required_for_complete，允许 partial，停止 |
| `cutline_blocked` | 缺 required_for_partial，停止 |

### CutlineReason

| 值 | 含义 |
|---|---|
| `missing_required_for_complete` | 缺完整渲染所需 slot |
| `no_source_demand` | 无源文本需求信号 |
| `promotion_blocked` | Worker 晋升条件不满足 |
| `non_renderable_candidate` | 候选不可渲染 |
| `blocked_by_gate` | 被 Gate 裁决阻止 |

---

## ConstructEdge — DAG 关系

construct 之间的关系不是严格树，而是 DAG。非树关系通过 `ConstructEdge` 表达：

```python
@dataclass
class ConstructEdge:
    from_id: str
    to_id: str
    edge_type: ConstructEdgeType
    source_span_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
```

### Edge Types（10 种）

| Edge Type | 含义 | 示例 |
|---|---|---|
| `contains` | 包含 | WORKER contains FLOW |
| `produces` | 产出 | STEP produces VARIABLE |
| `consumes` | 消费 | STEP consumes VARIABLE |
| `invokes` | 调用 | INVOKE_WORKER invokes CHILD_WORKER |
| `handoff_to` | 交接 | WORKER_HANDOFF handoff_to CHILD_WORKER |
| `handles` | 处理 | EXCEPTION_FLOW handles CONDITION |
| `applies_to` | 应用于 | POLICY applies_to STEP |
| `derived_from` | 派生自 | BLOCK derived_from SPAN |
| `promotes_to` | 晋升为 | WORKER_CANDIDATE promotes_to WORKER_PROMOTION |
| `blocked_by` | 被阻塞 | WORKER_PROMOTION blocked_by missing_slot |

**`primary_parent_id` 只表达主包含关系。多重关系必须用 `ConstructEdge`。**

---

## IRSCheckContext — 只读上下文

```python
@dataclass(frozen=True)
class IRSCheckContext:
    stage_name: str | None = None
    spans: list[SpanIR] = field(default_factory=list)
    routes: FieldRouteIR | None = None
    flow: FlowStructureIR | None = None
    block_plan: BlockStructureIR | None = None
    resources: ResourceRegistryIR | None = None
    steps: list[StepIR] = field(default_factory=list)
    worker_plan: WorkerPlanIR | None = None
    symbol_table: SymbolTable | None = None
    # ... 更多字段见 context.py
```

Checker 不应通过 context 修改 IR。Context 允许部分字段为空。
