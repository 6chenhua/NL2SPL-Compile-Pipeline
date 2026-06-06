# Phase 0: Baseline Tests — 实施计划

## 目标

记录当前 failure handling 行为的基线，标记已知问题（condition/handler 不区分、标题敏感性、信息丢失），不改动生产代码。

## 当前状态分析

### 已有测试覆盖
- `test_input_adapters.py`：FailureModeFact 生成、空值过滤、粗体剥离
- `test_failure_mode_bridge.py`：bridge_failure_modes() 全路径（695 行）
- `test_llm_adapter_engine_e2e.py`：端到端 exception flow 物化 + missing_handler 诊断

### 缺失的基线测试（Phase 0 需要补充）

1. **标题敏感性基线**：记录 `"Error handling:"` 等变体标题走 generic path 的行为
2. **Condition/handler 信息丢失基线**：记录 `"Missing timeframe: ask user"` 被整句当作 condition 的行为
3. **failure_handling 直接绕过 behavior 路径的基线**：记录 adapter 直接产出 FailureModeFact 而非通过 SemanticPacket → FieldRoute 的行为

## 实施步骤

### Step 1: 创建 `tests/unit/test_phase0_baseline.py`

新增一个专门的基线测试文件，包含以下测试：

#### 1.1 标题敏感性基线

```python
def test_baseline_failure_handling_title_recognized():
    """BASELINE: 'Failure handling:' produces FailureModeFact."""
    canonical = StructuralNLAdapter(None).adapt(
        "Failure handling:\n- Missing timeframe\n- Conflicting instructions"
    )
    assert len(canonical.hard_facts.failure_modes) == 2

def test_baseline_error_handling_title_not_recognized_as_failure():
    """BASELINE KNOWN GAP: 'Error handling:' does NOT produce FailureModeFact.
    Falls through to generic neutral packets only. After refactor, this should
    also produce failure-related SemanticPackets via structural detection."""
    canonical = StructuralNLAdapter(None).adapt(
        "Error handling:\n- Missing timeframe\n- Conflicting instructions"
    )
    assert len(canonical.hard_facts.failure_modes) == 0  # known gap

def test_baseline_exception_cases_title_not_recognized():
    """BASELINE KNOWN GAP: 'Exception cases:' is not in the title vocabulary."""
    canonical = StructuralNLAdapter(None).adapt(
        "Exception cases:\n- Missing data\n- Invalid format"
    )
    assert len(canonical.hard_facts.failure_modes) == 0  # known gap
```

#### 1.2 Condition/handler 信息丢失基线

```python
def test_baseline_colon_separated_not_split():
    """BASELINE KNOWN GAP: 'Missing timeframe: ask user to clarify'
    is kept as one FailureModeFact. The condition and handler are not split.
    After refactor, SemanticMapper should split into failure_condition +
    exception_handler_action."""
    canonical = StructuralNLAdapter(None).adapt(
        "Failure handling:\n- Missing timeframe: ask the user to clarify."
    )
    assert len(canonical.hard_facts.failure_modes) == 1
    fact = canonical.hard_facts.failure_modes[0]
    # The whole sentence is the text — condition and handler are merged
    assert "Missing timeframe" in fact.text
    assert "ask" in fact.text.lower()
```

#### 1.3 Adapter 直接生成 FailureModeFact 的基线

```python
def test_baseline_adapter_produces_failure_mode_fact_directly():
    """BASELINE: Adapter directly generates FailureModeFact via title matching,
    not through SemanticPacket → FieldRoute path. After refactor, failure
    handling should go through RouteAnnotationPrior → FieldRoute."""
    canonical = StructuralNLAdapter(None).adapt(
        "Failure handling:\n- Missing timeframe\n- Evidence shortage"
    )
    # Hard facts are populated
    assert len(canonical.hard_facts.failure_modes) == 2
    # Neutral packets exist but do NOT carry failure semantics
    failure_packets = [
        p for p in canonical.semantic_packets
        if p.packet_type in ("failure_mode", "failure_condition")
    ]
    assert len(failure_packets) == 0  # packets are neutral only
```

#### 1.4 Bridge 作为 fallback 的基线

```python
def test_baseline_bridge_creates_exception_flow_without_handler():
    """BASELINE: bridge_failure_modes() creates ExceptionFlow skeletons
    with condition_text but no handler blocks. missing_handler diagnostic
    is expected."""
    facts = [FailureModeFact(name="missing_timeframe", text="Missing timeframe",
                             source_section_id="sec_failure",
                             evidence=[EvidenceRef(source_section_id="sec_failure")])]
    flow = bridge_failure_modes(facts, [], FlowStructureIR())
    assert len(flow.exception_flows) == 1
    assert flow.exception_flows[0].condition_text == "Missing timeframe"
    assert flow.exception_flows[0].handler_blocks == []
```

### Step 2: 运行基线测试确认全部通过

```bash
pytest tests/unit/test_phase0_baseline.py -v
```

所有测试应该通过（包括标记为 known gap 的测试 — 它们断言的是当前行为，不是期望行为）。

### Step 3: 运行现有测试确认无回归

```bash
pytest tests/unit/test_input_adapters.py tests/unit/test_failure_mode_bridge.py tests/integration/test_llm_adapter_engine_e2e.py -v
```

## 验收标准

- [ ] 基线测试文件创建且全部通过
- [ ] 标题敏感性 known gap 被记录
- [ ] condition/handler 不区分 known gap 被记录
- [ ] adapter 直接生成 FailureModeFact 的行为被记录
- [ ] 无生产代码变更
- [ ] 现有测试无回归

## 文件变更

| 操作 | 文件 |
|------|------|
| 新增 | `tests/unit/test_phase0_baseline.py` |
