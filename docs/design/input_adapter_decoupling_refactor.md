# InputAdapter 解耦重构方案：以 Failure Handling 为切入点

**文档版本**: 1.0  
**创建日期**: 2026-05-30  
**作者**: Architecture Review  
**状态**: 提案 (Proposal)

---

## 执行摘要 (Executive Summary)

当前 `InputAdapter` 的设计存在**结构识别**与**语义裁决**高度耦合的问题。这在 Failure Handling 场景中尤为明显：

- Adapter 通过标题匹配识别 `failure_handling` section
- 立即将其转换为 `FailureModeFact`
- 直接指定 `compile_targets = ["flow.exception"]`
- 绕过了正常的 `behavior → flow materialization` 路径

**核心问题**：Adapter 不仅提取结构，还在**替下游做语义决策**，导致：

1. **语义前置**：过早决定内容应该变成什么 SPL 构件
2. **信息丢失**：无法区分 `condition` vs `handler action`
3. **路径绕过**：直接生成 `flow.exception`，而非通过 `FieldRoute → behavior → EXCEPTION_FLOW`
4. **扩展性差**：新的 failure handling 形态（condition + handler）无法表达

本文档提出**两阶段解耦方案**：

- **Phase 1: Structure Adapter** — 纯形态解析，不做语义判断
- **Phase 2: Semantic Mapper** — 基于证据的语义识别，输出 RouteAnnotation

---

## 1. 问题分析

### 1.1 Failure Handling 暴露的架构缺陷


#### 当前实现路径

```text
标题匹配 "failure handling"
  ↓
canonical_title = failure_handling
  ↓
_extract_failure_modes()
  ↓
FailureModeFact(text="Missing timeframe")
  ↓
SemanticPacket(
    packet_type="failure_mode",
    compile_targets=["flow.exception"]
)
  ↓
bridge_failure_modes() / Stage 4 materialize
  ↓
ExceptionFlow(condition="Missing timeframe", handler=None)
```

**问题**：

1. Adapter 决定了这是 `failure_mode`，而不是让 FieldRoute 判断
2. Adapter 决定了目标是 `flow.exception`，而不是 `behavior → EXCEPTION_FLOW`
3. 无法区分 `condition` 和 `handler action`
4. 如果用户写 `"Missing timeframe: ask user to clarify"`，整句被当作 condition

#### 更合理的路径

```text
Failure handling section
  ↓
RawSection(canonical_title="failure_handling", text="...")
  ↓
SemanticPacket(
    packet_type="failure_condition" | "exception_handler_action",
    modality="hint"  # 不是 hard_fact
)
  ↓
FieldRoute: behavior
  ↓
RouteAnnotation(
    field="behavior",
    semantic_role="failure_condition" | "exception_handler",
    construct_target="EXCEPTION_FLOW",
    slot_target="condition" | "handler",
    executable=False | True
)
  ↓
Stage 4 materialize ExceptionFlow
  ↓
Stage 5/7 materialize handler blocks/steps
```


### 1.2 根本原因：三重职责混合

当前 `StructuralNLAdapter` 同时承担三个职责：

| 职责 | 当前实现 | 应该是 |
|------|---------|--------|
| **结构识别** | 标题词汇匹配 (`"failure handling"`) | 文档形态检测（heading、list、key-value） |
| **语义识别** | if/elif 规则链 | LLM 或 semantic mapper |
| **IR 生成** | 直接生成 `FailureModeFact` | 生成 `RouteAnnotation` prior |

**结果**：

- "结构化"的定义过窄（必须匹配特定标题）
- 语义映射过度依赖规则（无法处理变体）
- 制造了 structural/generic 的虚假二分

### 1.3 具体症状

#### 症状 1：标题敏感性

```text
✓ "Failure handling: ..." → structural path
✗ "Error handling: ..." → generic path
✗ "Failure modes: ..." → generic path
✗ "Exception scenarios: ..." → generic path
```

即使形态结构完全一样，标题不匹配就退化成 generic。

#### 症状 2：语义前置

```python
# 当前代码
if canonical_title == "failure_handling":
    return _extract_failure_modes(section_text)
    # 直接决定：这些都是 failure modes
    # 直接决定：目标是 flow.exception
```

应该是：

```python
# 理想代码
if section_has_list_structure(section):
    return RawSection(title, text, list_items)
    # 不决定语义，只保留结构
```


#### 症状 3：信息丢失

当前 `_extract_failure_modes()` 把整句当作一个 failure mode：

```text
输入: "Missing timeframe: ask the user to provide it."
输出: FailureModeFact(text="Missing timeframe: ask the user to provide it.")
```

丢失了内部结构：

- `condition` = "Missing timeframe"
- `handler` = "ask the user to provide it"

#### 症状 4：语义断裂

```python
# Adapter 层
failure_mode → compile_targets = ["flow.exception"]

# Stage 2 annotation 层
failure_mode → field="behavior"
            → construct_target="EXCEPTION_FLOW"
            → slot_target="condition"
```

两层语义不一致！后者更合理，前者应该调整。

---

## 2. 设计方案：两阶段解耦

### 2.1 架构概览

```text
┌─────────────────────────────────────────────────────────────┐
│                    Raw Text Input                            │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  Phase 1: Structure Adapter (Deterministic)                  │
│  - 文档形态检测（heading、list、table、key-value）            │
│  - 提取 RawSection[]                                          │
│  - 不做语义判断                                               │
└─────────────────────────────────────────────────────────────┘
                            ↓
                    RawSection[]
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  Phase 2: Semantic Mapper (LLM-driven, evidence-bound)       │
│  - 判断 section 语义角色                                      │
│  - 区分 condition vs handler                                 │
│  - 输出 SemanticPacket + RouteAnnotation prior               │
│  - 不直接生成最终 IR                                          │
└─────────────────────────────────────────────────────────────┘
                            ↓
        SemanticPacket[] + RouteAnnotation[]
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  FieldRoute (Stage 2)                                        │
│  - 使用 RouteAnnotation prior                                │
│  - 进入 behavior / rules / resources 语义域                  │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  Stage 4: FlowAssembler                                      │
│  - behavior → FlowStructureIR                                │
│  - failure_condition → ExceptionFlow.condition               │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  Stage 5/7: Block/Step Extractor                             │
│  - exception_handler → BlockIR / StepIR                      │
└─────────────────────────────────────────────────────────────┘
```


### 2.2 Phase 1: Structure Adapter

#### 职责

**只做形态解析，不做语义判断**

- 检测文档是否有 heading、list、table、key-value 等结构
- 提取 section title、body、order、offsets
- 不关心标题是否严格等于 `"task family"` 或 `"failure handling"`
- 只要文档有结构，就保留结构信息

#### 输出

```python
@dataclass
class RawSection:
    section_id: str
    title: str  # 原始标题，不做规范化
    text: str   # section 正文
    order: int
    structure_type: Literal["heading", "list", "table", "key_value", "paragraph"]
    list_items: list[str] | None = None  # 如果是列表
    start_offset: int | None = None
    end_offset: int | None = None
```

#### 示例

输入：

```text
Failure handling:
- Missing timeframe: ask the user to clarify.
- Conflicting instructions.
- Insufficient source access: mark the draft as assumption-bearing.
```

输出：

```python
RawSection(
    section_id="sec_001",
    title="Failure handling",  # 保留原始标题
    text="Missing timeframe: ask the user to clarify.\nConflicting instructions.\n...",
    order=5,
    structure_type="list",
    list_items=[
        "Missing timeframe: ask the user to clarify.",
        "Conflicting instructions.",
        "Insufficient source access: mark the draft as assumption-bearing."
    ]
)
```

**关键**：不判断这是 `failure_mode` 还是 `policy`，只保留结构。


### 2.3 Phase 2: Semantic Mapper

#### 职责

**基于证据的语义识别**

- 判断 section 在语义上是什么
- 区分 `condition` vs `handler action`
- 输出 `SemanticPacket` + `RouteAnnotation` prior
- **不直接生成最终 SPL 构件**

#### 输入

```python
RawSection[]
```

#### 输出

```python
@dataclass
class SemanticPacket:
    packet_id: str
    source_section_id: str
    packet_type: Literal[
        "failure_condition",
        "exception_handler_action",
        "process_step",
        "policy",
        "runtime_input",
        "required_output",
        # ...
    ]
    text: str
    modality: Literal["hard_fact", "hint"]
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass
class RouteAnnotationPrior:
    """给 FieldRoute 的路由提示"""
    packet_id: str
    field: Literal["behavior", "rules", "resources", "domain"]
    semantic_role: str
    construct_target: str | None = None
    slot_target: str | None = None
    executable: bool = True
    route_family: str | None = None
```

#### 示例：Failure Handling

输入：

```python
RawSection(
    title="Failure handling",
    list_items=[
        "Missing timeframe: ask the user to clarify.",
        "Conflicting instructions.",
        "Insufficient source access: mark the draft as assumption-bearing."
    ]
)
```


输出：

```python
[
    # Case 1: condition + handler
    SemanticPacket(
        packet_id="p_fail_001_cond",
        packet_type="failure_condition",
        text="Missing timeframe",
        modality="hint"
    ),
    SemanticPacket(
        packet_id="p_fail_001_handler",
        packet_type="exception_handler_action",
        text="ask the user to clarify",
        modality="hint"
    ),
    RouteAnnotationPrior(
        packet_id="p_fail_001_cond",
        field="behavior",
        semantic_role="failure_condition",
        construct_target="EXCEPTION_FLOW",
        slot_target="condition",
        executable=False,
        route_family="flow_relevant"
    ),
    RouteAnnotationPrior(
        packet_id="p_fail_001_handler",
        field="behavior",
        semantic_role="exception_handler",
        construct_target="EXCEPTION_FLOW",
        slot_target="handler",
        executable=True,
        route_family="flow_relevant"
    ),
    
    # Case 2: condition only
    SemanticPacket(
        packet_id="p_fail_002_cond",
        packet_type="failure_condition",
        text="Conflicting instructions",
        modality="hint"
    ),
    RouteAnnotationPrior(
        packet_id="p_fail_002_cond",
        field="behavior",
        semantic_role="failure_condition",
        construct_target="EXCEPTION_FLOW",
        slot_target="condition",
        executable=False
    ),
    
    # Case 3: condition + handler
    SemanticPacket(
        packet_id="p_fail_003_cond",
        packet_type="failure_condition",
        text="Insufficient source access",
        modality="hint"
    ),
    SemanticPacket(
        packet_id="p_fail_003_handler",
        packet_type="exception_handler_action",
        text="mark the draft as assumption-bearing",
        modality="hint"
    ),
    # ... (对应的 RouteAnnotationPrior)
]
```

**关键差异**：

- 不再生成 `FailureModeFact`
- 不再指定 `compile_targets = ["flow.exception"]`
- 明确区分 `condition` 和 `handler`
- 通过 `RouteAnnotationPrior` 告诉 FieldRoute 这是 `behavior` 域


### 2.4 HardFact 边界收紧

#### 当前问题

`FailureModeFact` 被当作 hard fact，但它其实不完全是：

- `VariableFact`、`RequiredOutputFact` 是 contract-level facts（确定性高）
- `FailureModeFact` 更像 source-backed semantic observation（需要进一步解析）

#### 新设计

**保留 HardFact 仅用于高确定性的契约级事实**：

```python
@dataclass
class HardFacts:
    inputs: list[VariableFact]      # ✓ 保留
    outputs: list[VariableFact]     # ✓ 保留
    # failure_modes: list[FailureModeFact]  # ✗ 移除或降级
```

**Failure handling 改为 SemanticPacket + RouteAnnotation prior**：

- 不是 hard fact，而是 hint
- 需要 FieldRoute 和 Stage 4 进一步判断
- 保留了 condition/handler 的内部结构

#### 例外情况

如果确实需要保留 `FailureModeFact`，则：

1. 仅用于 **condition-only** 的简单观察
2. 不能作为完整 failure handling 表示
3. 必须配合 `SemanticPacket` 使用

---

## 3. 与现有设计的对比

### 3.1 当前设计 (F3 文档)

```python
# F3: failure_mode 的路由
RouteAnnotation(
    field="behavior",  # ✓ 正确
    semantic_role="failure_mode",
    construct_target="EXCEPTION_FLOW",
    slot_target="condition",
    executable=False
)

# 但同时：
"failure mode annotations may say field='behavior' because they are flow-relevant;
the old list must still keep the same span in routes.rules until Stage 4..."
```

**问题**：为了向后兼容，把 behavior 放在 rules 里，语义混乱。


### 3.2 新设计

```python
# 异常条件（触发条件）
RouteAnnotation(
    field="behavior",  # 控制流的一部分
    semantic_role="failure_condition",
    construct_target="EXCEPTION_FLOW",
    slot_target="condition",
    executable=False,  # 条件本身不可执行
    route_family="flow_relevant"
)

# 异常处理动作（handler）
RouteAnnotation(
    field="behavior",  # 同样是控制流
    semantic_role="exception_handler",
    construct_target="EXCEPTION_FLOW",
    slot_target="handler",
    executable=True,  # 处理动作是可执行的
    route_family="flow_relevant"
)
```

**关键改进**：

1. 始终在 `behavior` 域，不再放入 `rules`
2. 区分 `condition` 和 `handler`
3. 通过 `executable` 标记区分可执行性
4. 不再有"为了兼容把 behavior 放在 rules"的扭曲

### 3.3 与 `rules` 的区别

```python
# rules (约束/策略) - 非执行态的全局规则
RouteAnnotation(
    field="rules",
    semantic_role="constraint",
    executable=False
    # 例如："不得发明事实"、"必须提供证据"
)

# behavior (行为/控制流) - 包括正常流程和异常处理
RouteAnnotation(
    field="behavior",
    semantic_role="process_step",  # 正常步骤
    executable=True
)

RouteAnnotation(
    field="behavior",
    semantic_role="failure_condition",  # 异常条件
    executable=False  # 条件本身不执行
)

RouteAnnotation(
    field="behavior",
    semantic_role="exception_handler",  # 异常处理
    executable=True  # 处理动作可执行
)
```

**设计原则**：

- 不要混淆"不可执行"和"不是行为"
- 异常条件是 `executable=False`，但仍然是 `field="behavior"`
- `rules` 是全局约束，不参与控制流


---

## 4. 实施路径

### 4.1 Phase 0: 基线测试

**目标**：记录当前 failure handling 行为

**任务**：

1. 添加测试记录当前 `FailureModeFact` 生成逻辑
2. 记录当前 bridge 行为
3. 记录当前 Stage 4 exception flow 物化逻辑
4. 标记已知问题（condition/handler 不区分）

**验收**：

- 基线测试通过或标记为已知差距
- 无生产代码变更

### 4.2 Phase 1: Structure Adapter 实现

**目标**：解耦结构识别和语义判断

**任务**：

1. 创建 `StructureDetector` 类
   - 检测 heading、list、table、key-value
   - 不做标题词汇匹配
2. 修改 `StructuralNLAdapter.detect()`
   - 使用形态检测替代标题匹配
3. 输出 `RawSection[]` 保留结构信息
4. 保持 `CanonicalCompileInput` 接口兼容

**验收**：

- `"Error handling:"` 和 `"Failure handling:"` 都能识别为结构化
- 不再依赖固定标题词汇表
- 现有测试保持兼容

### 4.3 Phase 2: Semantic Mapper 实现

**目标**：基于证据的语义识别

**任务**：

1. 创建 `SemanticSectionMapper` 类
2. 实现 condition/handler 拆分逻辑
   - 规则：检测 `":"` 分隔符
   - LLM：语义拆分（可选）
3. 输出 `SemanticPacket` + `RouteAnnotationPrior`
4. 移除或降级 `FailureModeFact`

**验收**：

- `"Missing timeframe: ask user"` 拆分为 condition + handler
- `"Conflicting instructions"` 识别为 condition only
- 输出 `RouteAnnotationPrior` 指向 `behavior` 域


### 4.4 Phase 3: FieldRoute 集成

**目标**：FieldRoute 使用 RouteAnnotationPrior

**任务**：

1. 修改 Stage 2 `FieldRouter`
   - 读取 `RouteAnnotationPrior`
   - 生成 `RouteAnnotation`
   - failure_condition → `field="behavior"`
2. 移除 `routes.rules` 中的 failure mode
3. 更新 Stage 2 测试

**验收**：

- failure_condition 进入 `routes.behavior`
- annotation 标记 `executable=False`
- 不再有"为了兼容放在 rules"的逻辑

### 4.5 Phase 4: Stage 4 集成

**目标**：Stage 4 从 RouteAnnotation 物化 ExceptionFlow

**任务**：

1. 修改 `FlowAssembler`
   - 读取 `construct_target="EXCEPTION_FLOW"` 的 annotations
   - 区分 `slot_target="condition"` vs `"handler"`
   - 物化 condition-only 或 condition+handler 的 ExceptionFlow
2. 保持 bridge 作为 fallback
3. 更新 Stage 4 测试

**验收**：

- condition-only 生成 partial ExceptionFlow
- condition+handler 生成完整 ExceptionFlow（handler 在 Stage 5/7 物化）
- bridge 仅在无 annotation 时触发

### 4.6 Phase 5: Stage 5/7 集成

**目标**：物化 exception handler 为 blocks/steps

**任务**：

1. Stage 5 识别 `exception_handler` annotations
2. Stage 7 生成 handler steps
3. 更新 IRS checker

**验收**：

- handler action 生成可执行步骤
- condition-only 触发 `missing_handler` 诊断
- 完整 exception flow 渲染为 SPL


### 4.7 Phase 6: Bridge 清理

**目标**：移除或标记 deprecated bridge 逻辑

**任务**：

1. 标记 `bridge_failure_modes()` 为 deprecated
2. 仅在无 annotation 时作为 fallback
3. 添加 deprecation warning
4. 更新文档

**验收**：

- 新路径不依赖 bridge
- bridge 仅作为兼容层
- 有明确的移除计划

---

## 5. 测试策略

### 5.1 单元测试

#### Structure Adapter

```python
def test_structure_detector_recognizes_list():
    text = """
    Error handling:
    - Missing data
    - Invalid format
    """
    sections = StructureDetector().detect(text)
    assert len(sections) == 1
    assert sections[0].structure_type == "list"
    assert len(sections[0].list_items) == 2

def test_structure_detector_title_agnostic():
    """不依赖固定标题词汇"""
    text1 = "Failure handling:\n- Missing data"
    text2 = "Error scenarios:\n- Missing data"
    text3 = "Exception cases:\n- Missing data"
    
    for text in [text1, text2, text3]:
        sections = StructureDetector().detect(text)
        assert len(sections) == 1
        assert sections[0].structure_type == "list"
```

#### Semantic Mapper

```python
def test_semantic_mapper_splits_condition_handler():
    section = RawSection(
        title="Failure handling",
        list_items=["Missing timeframe: ask the user to clarify."]
    )
    packets = SemanticMapper().map(section)
    
    assert len(packets) == 2
    assert packets[0].packet_type == "failure_condition"
    assert packets[0].text == "Missing timeframe"
    assert packets[1].packet_type == "exception_handler_action"
    assert packets[1].text == "ask the user to clarify"

def test_semantic_mapper_condition_only():
    section = RawSection(
        title="Failure handling",
        list_items=["Conflicting instructions."]
    )
    packets = SemanticMapper().map(section)
    
    assert len(packets) == 1
    assert packets[0].packet_type == "failure_condition"
    assert packets[0].text == "Conflicting instructions"
```


### 5.2 集成测试

#### End-to-End: Condition Only

```python
def test_e2e_failure_condition_only():
    """纯条件，无 handler"""
    raw_text = """
    Failure handling:
    - Missing timeframe
    - Conflicting instructions
    """
    
    result = compile_pipeline.compile(raw_text)
    
    # 验证 ExceptionFlow 生成
    assert len(result.exception_flows) == 2
    assert result.exception_flows[0].condition_text == "Missing timeframe"
    assert result.exception_flows[0].handler_blocks == []
    
    # 验证诊断
    assert any(d.kind == "missing_handler" for d in result.diagnostics)
    
    # 验证 SPL 渲染为 partial skeleton
    assert "[EXCEPTION_FLOW: Missing timeframe]" in result.spl_text
    assert "[END_EXCEPTION_FLOW]" in result.spl_text
```

#### End-to-End: Condition + Handler

```python
def test_e2e_failure_condition_with_handler():
    """条件 + 处理动作"""
    raw_text = """
    Failure handling:
    - Missing timeframe: ask the user to provide it.
    """
    
    result = compile_pipeline.compile(raw_text)
    
    # 验证 ExceptionFlow 生成
    assert len(result.exception_flows) == 1
    flow = result.exception_flows[0]
    assert flow.condition_text == "Missing timeframe"
    assert len(flow.handler_blocks) > 0
    
    # 验证 handler step 生成
    handler_steps = flow.handler_blocks[0].steps
    assert any("ask" in step.action_text.lower() for step in handler_steps)
    
    # 验证无 missing_handler 诊断
    assert not any(d.kind == "missing_handler" for d in result.diagnostics)
    
    # 验证 SPL 包含 handler
    assert "[EXCEPTION_FLOW: Missing timeframe]" in result.spl_text
    assert "REQUEST_INPUT" in result.spl_text or "COMMAND" in result.spl_text
```


#### End-to-End: Mixed Cases

```python
def test_e2e_failure_mixed_cases():
    """混合：有些有 handler，有些没有"""
    raw_text = """
    Failure handling:
    - Missing timeframe: ask the user to clarify.
    - Conflicting instructions.
    - Insufficient source access: mark the draft as assumption-bearing.
    """
    
    result = compile_pipeline.compile(raw_text)
    
    assert len(result.exception_flows) == 3
    
    # Case 1: 有 handler
    flow1 = result.exception_flows[0]
    assert flow1.condition_text == "Missing timeframe"
    assert len(flow1.handler_blocks) > 0
    
    # Case 2: 无 handler
    flow2 = result.exception_flows[1]
    assert flow2.condition_text == "Conflicting instructions"
    assert flow2.handler_blocks == []
    
    # Case 3: 有 handler
    flow3 = result.exception_flows[2]
    assert flow3.condition_text == "Insufficient source access"
    assert len(flow3.handler_blocks) > 0
    
    # 验证诊断：只有 case 2 触发 missing_handler
    missing_handler_diags = [d for d in result.diagnostics if d.kind == "missing_handler"]
    assert len(missing_handler_diags) == 1
    assert "Conflicting instructions" in missing_handler_diags[0].message
```

---

## 6. 风险与缓解

### 6.1 风险：破坏现有功能

**缓解**：

- Phase 0 建立完整基线测试
- 每个 phase 保持向后兼容
- Bridge 作为 fallback 保留
- 渐进式迁移，不做大爆炸重写

### 6.2 风险：LLM 语义识别不准确

**缓解**：

- Phase 2 先用规则（检测 `:` 分隔符）
- LLM 作为可选增强
- 保留 evidence-bound 原则
- 不依赖 LLM 生成最终 IR


### 6.3 风险：性能下降

**缓解**：

- Structure detection 是确定性的，性能可控
- Semantic mapping 可缓存
- 不增加额外 LLM 调用（除非显式启用）

### 6.4 风险：与现有 F0-F4 任务冲突

**缓解**：

- 本方案与 F0-F4 方向一致
- F3/F4 已经在做 RouteAnnotation
- 本方案是 InputAdapter 侧的配套改进
- 可以并行推进，最后在 FieldRoute 层汇合

---

## 7. 成功标准

### 7.1 功能标准

- [ ] `"Error handling:"` 和 `"Failure handling:"` 都能识别
- [ ] `"Missing timeframe: ask user"` 拆分为 condition + handler
- [ ] `"Conflicting instructions"` 识别为 condition only
- [ ] condition-only 触发 `missing_handler` 诊断
- [ ] condition+handler 生成完整 ExceptionFlow
- [ ] failure handling 始终在 `behavior` 域，不在 `rules`
- [ ] 不再依赖 `FailureModeFact` 作为主路径
- [ ] Bridge 仅作为 fallback

### 7.2 架构标准

- [ ] Structure detection 与 semantic mapping 解耦
- [ ] Adapter 不直接生成最终 IR
- [ ] RouteAnnotation 是唯一的语义路由契约
- [ ] 所有 failure handling 通过 `behavior → EXCEPTION_FLOW` 路径

### 7.3 测试标准

- [ ] 所有现有测试保持通过
- [ ] 新增 condition/handler 拆分测试
- [ ] 新增 mixed cases 集成测试
- [ ] 基线测试记录当前行为

---

## 8. 后续工作

### 8.1 扩展到其他 section

本方案以 Failure Handling 为切入点，但同样适用于：

- **Delegation policy**: 区分 delegation intent vs boundary constraint
- **Reusable process**: 区分 main flow vs alternative flow vs gate
- **Policies**: 区分 prohibition vs requirement vs evidence vs gate

### 8.2 通用 Semantic Mapper

建立通用的 section → semantic packet 映射框架：

```python
class SemanticMapper:
    def map(self, section: RawSection) -> list[SemanticPacket]:
        # 根据 section 结构和内容，调用不同的 mapper
        if self._is_failure_handling(section):
            return FailureHandlingMapper().map(section)
        elif self._is_delegation(section):
            return DelegationMapper().map(section)
        # ...
```

### 8.3 LLM-driven Semantic Mapping

可选增强：使用 LLM 进行更精确的语义识别

```python
class LLMSemanticMapper:
    def map(self, section: RawSection) -> list[SemanticPacket]:
        prompt = f"""
        Analyze this section and identify:
        1. Is this a failure condition, handler action, or both?
        2. If both, split them.
        
        Section: {section.text}
        """
        # LLM call
        # Parse response
        # Return SemanticPacket[]
```

---

## 9. 结论

Failure Handling 的问题不是一个局部 bug，而是 InputAdapter 当前"结构解析 + 语义裁决 + IR 生成"三者混在一起后的**典型症状**。

**核心改进**：

1. **解耦结构识别和语义判断**
2. **Adapter 不替下游做决策**
3. **Failure handling 归类为 behavior，不是 rules**
4. **区分 condition 和 handler**
5. **通过 RouteAnnotation 统一语义路由**

这个方案与现有的 F0-F4 RouteAnnotation 重构方向完全一致，是 InputAdapter 侧的配套改进。

---

## 附录 A: 术语对照

| 术语 | 含义 |
|------|------|
| Structure Adapter | 纯形态解析器，不做语义判断 |
| Semantic Mapper | 基于证据的语义识别器 |
| RouteAnnotationPrior | Adapter 给 FieldRoute 的路由提示 |
| failure_condition | 异常触发条件（非执行态） |
| exception_handler | 异常处理动作（可执行态） |
| behavior 域 | 控制流相关的语义域，包括正常流程和异常处理 |
| rules 域 | 全局约束/策略，不参与控制流 |

---

## 附录 B: 参考文档

- `docs/Todo/route_contract_refactor_01_frontend_semantic_contract.md`
- `docs/Todo/tasks/F3_hint_aware_field_router.md`
- `docs/Todo/tasks/F4_annotation_aware_ambiguity_resolver.md`
- `docs/Todo/tasks/D2_flow_assembler_route_driven_exception_materialization.md`
- `docs/InputAdapter/nl_2_spl_input_adapter_design.md`

---

**文档结束**
