# Exception Flow 路由问题记录

Date: 2026-06-05

Status: 待讨论

## 背景

Exception flow 的路由通过 annotation 间接完成，而非直接进入 stage 4 LLM。本文档记录在审查过程中发现的设计漏洞和潜在问题。

---

## 问题 1: Exception Handler Span 进入 Stage 4 LLM 但缺乏语义标记

**严重程度**: 中

**现象**:

Exception flow 有两个组件：
- **condition** (failure_mode / failure_condition): `executable=False` → 不进入 stage 4 LLM
- **handler** (exception_handler): `executable=True` → 进入 stage 4 LLM

Handler span 作为 executable behavior span 进入 stage 4，但 stage 4 的 LLM **不知道它是 exception handler**。LLM 可能：
1. 把它放进 `main_flow` → 错误
2. 把它放进 `exception_flows` → 碰巧正确
3. 放进 `alternative_flows` → 错误

**当前缓解措施**:

- `_filter_non_condition_exception_flows()` 清理 LLM 产出的不可靠 exception flows，但**只检查 condition，不检查 handler**
- `materialize_handler_blocks()` 在 stage 5 从 handler annotation 确定性地创建 handler blocks

**残留风险**:

如果 LLM 把 handler span 放进了 `main_flow`，stage 4 不会纠正它。Stage 5 的 `materialize_handler_blocks()` 会创建正确的 handler block，但 main_flow 里可能残留一个不应该出现的 span。

**相关代码**:
- `src/nl2spl/pipeline/stages/stage4_flow_assembler/executor.py:34-38` — behavior span 筛选
- `src/nl2spl/pipeline/route_exception_materializer.py:100-186` — handler block materialization
- `src/nl2spl/pipeline/stages/stage4_flow_assembler/executor.py:304-391` — condition-only filter

---

## 问题 2: Worker-Aware 路径下 Condition 和 Handler 可能被拆到不同 Worker

**严重程度**: 高

**现象**:

Stage 3.5 (WorkerBoundaryPlanner) 做 worker 分割时，基于语义边界决定 `owned_span_ids`。但它**不知道 exception flow 的语义** — 一个 failure condition span 和对应的 handler span 可能被分到不同 worker。

`_materialize_worker_exceptions()` 按 `owned_span_ids` 把 condition 分配到 worker，`materialize_handler_blocks()` 按 annotation 把 handler 分配到 worker。如果 condition 在 worker A、handler 在 worker B：
- worker A 的 flow 里有一个没有 handler 的 exception flow
- worker B 的 block 里有一个没有对应 exception flow 的 handler block

**当前行为**:

`_materialize_worker_exceptions()` 对 unowned 或 multi-owned condition span 会 fallback 到 main worker 并记录 warning。但这不解决 condition 和 handler 被拆分的问题。

**相关代码**:
- `src/nl2spl/pipeline/stages/stage4_flow_assembler/executor.py:222-301` — `_materialize_worker_exceptions`
- `src/nl2spl/pipeline/stages/stage3_5_worker_boundary_planner/executor.py` — ownership 决策

---

## 问题 3: `_filter_non_condition_exception_flows` 不验证 Handler 位置

**严重程度**: 低-中

**现象**:

`_filter_non_condition_exception_flows()` 只关注 condition span 的合法性，不检查：
- LLM 是否把 handler span 放进了 `main_flow`
- LLM 是否把 handler span 错误地标记为 condition

如果 annotation 说 span X 是 handler（`slot_target="handler"`），但 LLM 把它当 condition 放进了 exception flow，这个函数不会纠正。

**相关代码**:
- `src/nl2spl/pipeline/stages/stage4_flow_assembler/executor.py:304-391`

---

## 边界情况与 E2E 测试用例

### TC-1: Handler 被 LLM 放进 main_flow（问题 1）

**输入**:
```
spans:
  s1: "接收用户提交的数据"          → process_step, executable=True
  s2: "如果数据格式无效"            → failure_mode, executable=False
  s3: "返回错误提示并记录日志"       → exception_handler, executable=True

annotations:
  s2 → EXCEPTION_FLOW.condition, semantic_role=failure_mode
  s3 → EXCEPTION_FLOW.handler, semantic_role=exception_handler
```

**Stage 4 LLM 可能产出** (错误):
```json
{
  "main_flow_spans": ["s1", "s3"],
  "exception_flows": []
}
```

**期望行为**:
- `main_flow_spans` 应只包含 `["s1"]`
- `s3` 不应出现在 main_flow 中
- stage 4 之后应有验证：annotation 标记为 handler 的 span 不得出现在 main_flow

**断言**:
```python
assert "s3" not in flow.main_flow_spans
# 或更严格：main_flow 中不应包含任何 EXCEPTION_FLOW.handler annotation 的 span
```

---

### TC-2: Handler 被 LLM 错误标记为 condition（问题 3）

**输入**:
```
spans:
  s1: "调用第三方支付接口"           → process_step, executable=True
  s2: "如果支付超时"                → failure_mode, executable=False
  s3: "重试支付请求"                → exception_handler, executable=True

annotations:
  s2 → EXCEPTION_FLOW.condition, semantic_role=failure_mode
  s3 → EXCEPTION_FLOW.handler, semantic_role=exception_handler
```

**Stage 4 LLM 可能产出** (错误):
```json
{
  "main_flow_spans": ["s1"],
  "exception_flows": [
    {"flow_id": "exc_00", "condition_text": "重试支付请求", "spans": ["s3"]}
  ]
}
```

**期望行为**:
- `_filter_non_condition_exception_flows` 应识别 `s3` 不是 condition（它的 annotation 是 handler）
- LLM 产出的 exception flow 应被过滤掉
- route-derived materializer 应从 `s2` 创建正确的 exception flow

**断言**:
```python
assert len(flow.exception_flows) == 1
assert flow.exception_flows[0].condition_text == "如果支付超时"
assert "s3" not in flow.exception_flows[0].spans
```

---

### TC-3: Condition 和 Handler 被拆到不同 Worker（问题 2）

**输入**:
```
spans:
  s1: "解析订单数据"                → process_step, executable=True
  s2: "如果库存不足"                → failure_mode, executable=False
  s3: "通知仓库补货并标记订单为待处理" → exception_handler, executable=True

worker_plan:
  worker_main: owned=[s1, s2]
  worker_notify: owned=[s3]

annotations:
  s2 → EXCEPTION_FLOW.condition
  s3 → EXCEPTION_FLOW.handler
```

**期望行为**:
- condition `s2` 在 worker_main → worker_main 应有 exception flow
- handler `s3` 在 worker_notify → 但 handler 应跟随 condition 所在的 worker
- 或者：系统应检测到 condition/handler 跨 worker 并发出 warning

**当前实际行为**:
- worker_main 有 exception flow (condition only, 无 handler)
- worker_notify 有 handler block (无对应 exception flow)
- 无 warning 提示跨 worker 拆分

**断言**:
```python
# 理想行为：handler 应跟随 condition
assert "s3" in worker_main_flow.exception_flows[0].spans
# 或至少：系统应报告跨 worker 拆分
assert any("cross-worker" in w.lower() for w in warnings)
```

---

### TC-4: 多个 Condition 共享一个 Handler（边界）

**输入**:
```
spans:
  s1: "提交订单"                    → process_step, executable=True
  s2: "如果库存不足"                → failure_mode, executable=False
  s3: "如果支付失败"                → failure_mode, executable=False
  s4: "回滚事务并通知管理员"         → exception_handler, executable=True

annotations:
  s2 → EXCEPTION_FLOW.condition (failure_mode)
  s3 → EXCEPTION_FLOW.condition (failure_mode)
  s4 → EXCEPTION_FLOW.handler (exception_handler)
```

**问题**:
- `materialize_handler_blocks()` 用 `failure_item_index` 或 section 级别配对
- 如果 `s2` 和 `s3` 在同一个 section，handler `s4` 只会配对到其中一个 exception flow
- 另一个 exception flow 没有 handler

**期望行为**:
- `s4` 应同时关联到 `s2` 和 `s3` 的 exception flows
- 或者：系统应明确声明一个 handler 只能服务一个 condition，要求用户拆分

**断言**:
```python
exc_flows = flow.exception_flows
assert len(exc_flows) == 2
# handler 至少应关联到一个 condition
handler_in_flow = [f for f in exc_flows if "s4" in f.spans]
assert len(handler_in_flow) >= 1
# 另一个 flow 应有 missing_handler 诊断
```

---

### TC-5: Condition 文本为空标记但 Handler 存在（边界）

**输入**:
```
spans:
  s1: "执行数据迁移"                → process_step, executable=True
  s2: "None"                        → failure_mode, executable=False  (空标记)
  s3: "记录错误日志并回滚"           → exception_handler, executable=True

annotations:
  s2 → EXCEPTION_FLOW.condition (failure_mode)
  s3 → EXCEPTION_FLOW.handler (exception_handler)
```

**期望行为**:
- `_is_empty_condition("None")` 返回 True → condition 被跳过
- 但 handler `s3` 仍然是 executable behavior → 进入 stage 4 LLM
- LLM 可能把 `s3` 放进 main_flow

**断言**:
```python
assert len(flow.exception_flows) == 0  # condition 为空，不生成 exception flow
# 但 s3 作为 behavior 仍然存在，需要决定它的归宿
assert "s3" in flow.main_flow_spans  # 或有专门的 unpaired-handler 诊断
```

---

### TC-6: Handler 同时也是 Process Step（双重角色）

**输入**:
```
spans:
  s1: "调用订单创建 API"            → process_step, executable=True
  s2: "如果订单创建失败"            → failure_mode, executable=False
  s3: "重试订单创建并记录失败原因"   → 同时是 process_step 和 exception_handler

annotations:
  s2 → EXCEPTION_FLOW.condition
  s3 → EXCEPTION_FLOW.handler, executable=True
  s3 → process_step, executable=True  (双重 annotation)
```

**问题**:
- `s3` 既是 main flow 的一部分（process_step），又是 exception handler
- 当前 annotation 支持 multi-label，但 stage 4 LLM 只看到一次 `s3`

**期望行为**:
- `s3` 应同时出现在 main_flow（作为 process_step）和 exception handler block（作为 handler）
- 或者：系统应要求用户明确是重试流程还是异常处理，不接受双重角色

**断言**:
```python
assert "s3" in flow.main_flow_spans  # 作为 process_step
# 同时 handler block 也应包含 s3
handler_blocks = blocks.exception_flow_blocks.get(exc_flow.flow_id, [])
assert any("s3" in b.spans for b in handler_blocks)
```

---

## 待讨论

1. Stage 4 LLM 是否应该接收 exception handler spans 的语义信息（例如通过 prompt 或 annotation 传递）？
2. Stage 3.5 做 worker 分割时，是否应该考虑 exception flow 的 condition-handler 配对约束？
3. 是否需要一个 post-stage-4 的验证步骤，确保 handler span 没有被错误地放进 main_flow？
4. 一个 handler 是否应该允许服务多个 condition？还是强制一对一？
5. 双重角色 span（process_step + exception_handler）应该如何处理？

---

## 待探讨: Worker 边界规划与变量提取的顺序问题

Date: 2026-06-05

Status: 待探讨

### 问题描述

当前 pipeline 顺序：

```
Stage 3.5 (WorkerBoundaryPlanner) → Stage 6 (ResourceExtractor)
```

Stage 3.5 在 Stage 6 **之前**执行，但 child worker 的 input/output contract 可能依赖于 Stage 6 提取的变量信息。原文中可能**没有显式声明**子 worker 需要的变量。

### 当前 contract 填充逻辑

`materializer.py:_candidate_to_worker()` 中，child worker contract 来源：

1. **Stage 3.5a LLM 猜测** `possible_inputs` / `possible_outputs` — 从原文推断
2. **hard facts token 匹配** — 用变量名 snake_case token 匹配 candidate text

如果两者都无法填充 → `return None` → 拒绝该 worker。

### 隐式变量依赖场景

**输入**:
```
s1: "处理订单请求"
s2: "检查库存是否充足"
s3: "如果库存不足，通知仓库补货"
s4: "更新订单状态"
```

Stage 3.5a 可能把 s3 拆为 child worker，猜测 contract：
```json
{
  "possible_inputs": ["库存数量", "商品ID"],
  "possible_outputs": ["补货结果"]
}
```

但实际运行时，"通知仓库补货" worker 需要的变量可能是：
- `order_id` — 来自 s1 的输出（隐式传递）
- `sku_id` — 来自 s2 的中间变量
- `shortage_quantity` — 隐式计算得出

这些变量**不是原文显式声明的 input/output**，而是从流程上下文推导的。Stage 3.5 阶段没有这些信息。

### 鸡生蛋问题

| 方案 | 优点 | 缺点 |
|------|------|------|
| 当前顺序（3.5 → 6） | 无循环依赖 | Stage 3.5 不知道隐式变量，可能定错 worker 边界 |
| 提前（6 → 3.5） | Stage 3.5 有完整变量信息 | Stage 6 的 worker-scoped 提取需要 worker 边界 → 循环依赖 |
| 两阶段（3.5a → 6 → 3.5c） | 兼顾两者 | 增加 pipeline 复杂度，Stage 3.5 需要拆成更多子阶段 |

### 可能的解法方向

**方案 A: 两阶段 contract resolution**
```
Stage 3.5a: 提取 candidate（不含 contract）
Stage 3.5b: 边界决策
Stage 6: 提取变量
Stage 3.5c: 根据提取的变量回填 worker contract
```

**方案 B: Stage 3.5 只做 candidate 提取，contract 推迟到 Stage 6+**
```
Stage 3.5: 只产出 candidate task units + 边界决策，不填 contract
Stage 6: 提取变量，同时推导每个 worker 的 input/output 依赖
Stage 6.5: 确定性 materializer 填充 worker contract
```

**方案 C: 保持当前顺序，增加隐式变量推导**
```
Stage 3.5a: LLM 除了猜 possible_inputs/outputs，还标注"隐式依赖"
Stage 3.5c: materializer 用 flow 上下文推导隐式变量
```

### 待讨论

1. 当前 `_match_hard_fact_contracts` 的 token 匹配是否足够覆盖常见场景？
2. 隐式变量依赖在实际输入中出现的频率有多高？
3. 方案 A 的两阶段拆分是否与现有 Stage 3.5a/3.5b/3.5c 子阶段架构兼容？
4. 是否需要先做一个 survey：统计现有测试用例中有多少 child worker 的 contract 依赖隐式变量？

---

## 问题 4: Stage 8 ProfileExtractor 缺少溯源机制

Date: 2026-06-05

Status: 待讨论

**严重程度**: 中

### 现象

Stage 8 (ProfileExtractor) 提取的 `AgentProfileIR` 完全没有 provenance 信息。LLM 产出的 persona、audience aspects、concepts 直接解析为 IR，不追溯来源 span。

### IR 结构对比

**当前（无溯源）**:
```python
@dataclass
class Aspect:
    name: str       # 无 source_span_id
    text: str       # 无 source_span_id

@dataclass
class Concept:
    term: str        # 无 source_span_id
    definition: str  # 无 source_span_id

@dataclass
class AgentProfileIR:
    persona: PersonaIR              # 无来源
    audience_aspects: list[Aspect]  # 无来源
    concepts: list[Concept]         # 无来源
```

**其他 stage 的溯源机制**:

| Stage | 溯源字段 |
|-------|---------|
| Stage 6 ResourceExtractor | `source_span_ids`, `EvidenceRef`, `source_packet_id` |
| Stage 7 StepExtractor | `source_span_ids`, `source_resource_ids` |
| Stage 2 FieldRouter | `RouteAnnotation.source_section_id`, `source_packet_id` |
| Stage 9 ConstraintExtractor | `source_span_ids` |
| **Stage 8 ProfileExtractor** | **无** |

### 影响

1. **调试困难** — persona role 或 concept 提取错误时，无法追溯是哪个 span 导致的
2. **编译报告不完整** — `CompileResult` 的 provenance trace 里 profile 部分是空的
3. **下游验证缺失** — 无法验证 profile 是否忠实于原文，因为没有 span 对应关系
4. **LLM 幻觉不可检测** — 如果 LLM 凭空生成了一个 concept，没有 span 可以对照验证

### 修复方向

给 `Aspect` 和 `Concept` 增加 `source_span_ids` 字段，Stage 8 的 LLM prompt 要求输出中包含来源 span_id：

```python
@dataclass
class Aspect:
    name: str
    text: str
    source_span_ids: list[str] = field(default_factory=list)

@dataclass
class Concept:
    term: str
    definition: str
    source_span_ids: list[str] = field(default_factory=list)
```

### 边界测试用例

#### TC-7: Profile 概念无溯源

**输入**:
```
spans:
  s1: "这是一个面向企业客户的智能客服系统"
  s2: "需要支持多轮对话和意图识别"
```

**Stage 8 LLM 可能产出**:
```json
{
  "persona": {"role": "智能客服助手", "aspects": []},
  "concepts": [
    {"term": "多轮对话", "definition": "支持上下文连续的对话"},
    {"term": "意图识别", "definition": "理解用户输入的目的"},
    {"term": "情感分析", "definition": "检测用户情绪"}  ← 幻觉，原文无此概念
  ]
}
```

**当前行为**: 三个 concept 都被接受，无法区分哪个是忠实提取、哪个是幻觉。

**期望行为**:
```python
concepts[0].source_span_ids == ["s2"]   # 有据可查
concepts[1].source_span_ids == ["s2"]   # 有据可查
concepts[2].source_span_ids == []       # 无来源 → 可被诊断为幻觉
```
