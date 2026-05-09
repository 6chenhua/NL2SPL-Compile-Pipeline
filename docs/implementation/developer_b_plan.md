# Developer B (Pipeline Engineer) - 详细开发计划

## 角色定位

**代号**: B  
**角色**: Pipeline Engineer  
**职责**: Stage 1-3 实现（SpanSlicer, FieldRouter, AmbiguityResolver）

---

## Week 1: Stage 1-3 实现

### Day 1-2: 理解架构 + Stage 1

| 任务 | 文件 | 输出 | 验收标准 |
|------|------|------|----------|
| T1.5.1 理解 IR 模型 | `src/nl2spl/ir/*.py` | 理解 SpanIR, FieldRouteIR | 能正确使用 IR |
| T1.5.2 理解 Stage 基类 | `src/nl2spl/pipeline/stages/base.py` | 理解 PipelineStage | 能正确继承 |
| T1.5.3 实现 Stage 1 | `src/nl2spl/pipeline/stages/stage1_span_slicer.py` | SpanSlicer | 切片正确 |

**Stage 1 实现要点**:
```python
class SpanSlicer(PipelineStage[str, list[SpanIR]]):
    @property
    def name(self) -> str:
        return "stage1_span_slicer"

    def execute(self, raw_text: str) -> list[SpanIR]:
        # 1. 构建 prompt
        system_prompt = STAGE1_SYSTEM
        user_prompt = f"请将以下文本切分为语义完整的 span：\n\n---\n{raw_text}\n---"

        # 2. 调用 LLM
        result = self.client.call_json(
            stage_name=self.name,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )

        # 3. 解析结果
        spans = []
        for item in result.get("spans", []):
            span = SpanIR(
                span_id=item["span_id"],
                text=item["text"],
            )
            spans.append(span)

        # 4. 保存 checkpoint
        self.save_checkpoint({"spans": [asdict(s) for s in spans]})

        return spans
```

**测试用例**:
```python
# tests/unit/test_span_slicer.py
def test_simple_sentence():
    """测试简单句切片"""
    raw_text = "First determine what kind of communication is requested."
    spans = slicer.execute(raw_text)
    assert len(spans) == 1
    assert spans[0].text == raw_text

def test_multiple_sentences():
    """测试多句切片"""
    raw_text = "First determine type. Then identify fields."
    spans = slicer.execute(raw_text)
    assert len(spans) == 2

def test_compound_sentence():
    """测试复合句切片"""
    raw_text = "Determine type, but do not invent details."
    spans = slicer.execute(raw_text)
    assert len(spans) >= 1
```

### Day 2-3: Stage 2 实现

| 任务 | 文件 | 输出 | 验收标准 |
|------|------|------|----------|
| T1.6.1 实现 Stage 2 | `src/nl2spl/pipeline/stages/stage2_field_router.py` | FieldRouter | 路由正确 |
| T1.6.2 创建 Prompt | `prompts/stage2_system.txt` | System Prompt | 包含路由规则 |

**Stage 2 实现要点**:
```python
class FieldRouter(PipelineStage[list[SpanIR], tuple[FieldRouteIR, list[dict]]]):
    @property
    def name(self) -> str:
        return "stage2_field_router"

    def execute(self, spans: list[SpanIR]) -> tuple[FieldRouteIR, list[dict]]:
        # 1. 构建 prompt
        spans_json = json.dumps([asdict(s) for s in spans], ensure_ascii=False)
        system_prompt = STAGE2_SYSTEM
        user_prompt = f"请将以下 span 路由到 6 个语义字段：\n\n---\n{spans_json}\n---"

        # 2. 调用 LLM
        result = self.client.call_json(
            stage_name=self.name,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )

        # 3. 解析结果
        routes = FieldRouteIR(**result.get("routes", {}))
        ambiguity_updates = result.get("ambiguity_updates", [])

        # 4. 回写 ambiguity 到 spans
        for update in ambiguity_updates:
            span_id = update["span_id"]
            for span in spans:
                if span.span_id == span_id:
                    span.ambiguity.is_ambiguous = update.get("is_ambiguous", False)
                    span.ambiguity.reasons = update.get("reasons", [])
                    span.ambiguity.needs_split = update.get("needs_split", False)

        # 5. 校验无重叠
        overlaps = routes.validate_no_overlap()
        if overlaps:
            self.logger.warning("Overlapping spans detected: %s", overlaps)

        # 6. 保存 checkpoint
        self.save_checkpoint({
            "routes": asdict(routes),
            "ambiguity_updates": ambiguity_updates,
        })

        return routes, ambiguity_updates
```

**测试用例**:
```python
# tests/unit/test_field_router.py
def test_identity_routing():
    """测试 identity 字段路由"""
    spans = [SpanIR("s1", "Internal communications specialist")]
    routes, _ = router.execute(spans)
    assert "s1" in routes.identity

def test_behavior_routing():
    """测试 behavior 字段路由"""
    spans = [SpanIR("s1", "Determine communication type")]
    routes, _ = router.execute(spans)
    assert "s1" in routes.behavior

def test_rules_routing():
    """测试 rules 字段路由"""
    spans = [SpanIR("s1", "Do not invent facts")]
    routes, _ = router.execute(spans)
    assert "s1" in routes.rules

def test_no_overlap():
    """测试无重叠"""
    spans = [
        SpanIR("s1", "Specialist role"),
        SpanIR("s2", "Determine type"),
    ]
    routes, _ = router.execute(spans)
    assert len(routes.validate_no_overlap()) == 0
```

### Day 3-4: Stage 3 实现

| 任务 | 文件 | 输出 | 验收标准 |
|------|------|------|----------|
| T1.7.1 实现 Stage 3 | `src/nl2spl/pipeline/stages/stage3_ambiguity_resolver.py` | AmbiguityResolver | 消解正确 |
| T1.7.2 创建 Prompt | `prompts/stage3_system.txt` | System Prompt | 包含拆分策略 |

**Stage 3 实现要点**:
```python
class AmbiguityResolver(PipelineStage[
    tuple[list[SpanIR], FieldRouteIR, list[dict]],
    tuple[list[SpanIR], FieldRouteIR]
]):
    @property
    def name(self) -> str:
        return "stage3_ambiguity_resolver"

    def execute(
        self, input_data: tuple[list[SpanIR], FieldRouteIR, list[dict]]
    ) -> tuple[list[SpanIR], FieldRouteIR]:
        spans, routes, ambiguity_updates = input_data

        # 如果没有歧义，直接返回
        if not ambiguity_updates:
            return spans, routes

        # 1. 构建 prompt
        spans_json = json.dumps([asdict(s) for s in spans], ensure_ascii=False)
        routes_json = json.dumps(asdict(routes), ensure_ascii=False)
        ambiguity_json = json.dumps(ambiguity_updates, ensure_ascii=False)

        system_prompt = STAGE3_SYSTEM
        user_prompt = f"""以下 span 被标记为歧义，请拆分：

原始 spans：
---
{spans_json}
---

当前路由：
---
{routes_json}
---

歧义 span：
---
{ambiguity_json}
---

输出 JSON："""

        # 2. 调用 LLM
        result = self.client.call_json(
            stage_name=self.name,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )

        # 3. 解析结果
        resolved_spans_data = result.get("resolved_spans", [])
        resolved_routes_data = result.get("resolved_routes", {})

        # 4. 创建新的 spans
        new_spans = []
        for span_data in resolved_spans_data:
            span = SpanIR(
                span_id=span_data["span_id"],
                text=span_data["text"],
            )
            new_spans.append(span)

        # 5. 合并 spans（移除原始歧义 span，添加新 span）
        resolved_spans = []
        ambiguous_ids = {u["span_id"] for u in ambiguity_updates}
        for span in spans:
            if span.span_id not in ambiguous_ids:
                resolved_spans.append(span)
        resolved_spans.extend(new_spans)

        # 6. 创建新的 routes
        resolved_routes = FieldRouteIR(**resolved_routes_data)

        # 7. 保存 checkpoint
        self.save_checkpoint({
            "resolved_spans": [asdict(s) for s in resolved_spans],
            "resolved_routes": asdict(resolved_routes),
        })

        return resolved_spans, resolved_routes
```

**测试用例**:
```python
# tests/unit/test_ambiguity_resolver.py
def test_no_ambiguity():
    """测试无歧义情况"""
    spans = [SpanIR("s1", "Determine type")]
    routes = FieldRouteIR(behavior=["s1"])
    result_spans, result_routes = resolver.execute((spans, routes, []))
    assert len(result_spans) == 1

def test_split_ambiguous_span():
    """测试拆分歧义 span"""
    spans = [SpanIR("s1", "Determine type, but do not invent")]
    routes = FieldRouteIR(behavior=["s1"])
    ambiguity_updates = [{
        "span_id": "s1",
        "is_ambiguous": True,
        "reasons": ["mixed_action_and_policy"],
        "needs_split": True,
    }]
    result_spans, result_routes = resolver.execute((spans, routes, ambiguity_updates))
    assert len(result_spans) == 2
```

### Day 4-5: 测试 + Prompt 优化

| 任务 | 文件 | 输出 | 验收标准 |
|------|------|------|----------|
| T1.8.1 创建 Prompt 文件 | `prompts/stage{1,2,3}_system.txt` | Prompt 文件 | 与代码一致 |
| T1.9.1 单元测试 | `tests/unit/test_span_slicer.py` | 测试文件 | 覆盖正常/边界/错误 |
| T1.9.2 单元测试 | `tests/unit/test_field_router.py` | 测试文件 | 覆盖正常/边界/错误 |
| T1.9.3 单元测试 | `tests/unit/test_ambiguity_resolver.py` | 测试文件 | 覆盖正常/边界/错误 |

---

## Week 2: 集成测试

### Day 1-2: 集成测试

| 任务 | 文件 | 输出 | 验收标准 |
|------|------|------|----------|
| T2.5.1 集成测试 | `tests/integration/test_pipeline.py` | 测试文件 | Stage 1-5 集成 |
| T3.5.1 测试数据 | `tests/fixtures/sample_inputs.py` | 测试数据 | 包含多种场景 |

**测试数据示例**:
```python
# tests/fixtures/sample_inputs.py
SAMPLE_INPUTS = {
    "simple": "First determine what kind of communication is requested.",
    "complex": """
Task family: Internal newsletters and announcements.
Inputs: A user request, optional topics.
Required outputs: A draft communication.
Reusable process: First determine type. Then identify fields. Ask clarifying questions.
Policies: Do not invent facts. Require evidence.
Failure handling: Missing timeframe, evidence shortage.
Delegation policy: Optional source gathering if bounded.
""",
    "with_ambiguity": "Determine communication type, but do not invent details.",
}
```

### Day 3-5: Prompt 优化

| 任务 | 文件 | 输出 | 验收标准 |
|------|------|------|----------|
| T3.5.2 Prompt 优化 | `prompts/stage{1,2,3}_system.txt` | 优化后 Prompt | Few-shot 示例 |

---

## 文件编辑权限

### 可编辑文件
```
src/nl2spl/pipeline/stages/stage1_span_slicer.py
src/nl2spl/pipeline/stages/stage2_field_router.py
src/nl2spl/pipeline/stages/stage3_ambiguity_resolver.py
prompts/stage1_system.txt
prompts/stage2_system.txt
prompts/stage3_system.txt
tests/unit/test_span_slicer.py
tests/unit/test_field_router.py
tests/unit/test_ambiguity_resolver.py
tests/integration/test_pipeline.py
tests/fixtures/sample_inputs.py
examples/usage.py
```

### 不可编辑文件
```
src/nl2spl/ir/*.py          # 由 A 定义
src/nl2spl/llm/client.py    # 由 A 定义
src/nl2spl/pipeline/stages/base.py  # 由 A 定义
src/nl2spl/config.py        # 由 A 管理
pyproject.toml              # 由 A 管理
```

---

## 交付物清单

| 交付物 | 文件 | 完成时间 |
|--------|------|----------|
| Stage 1 实现 | `stage1_span_slicer.py` | Day 2 |
| Stage 2 实现 | `stage2_field_router.py` | Day 3 |
| Stage 3 实现 | `stage3_ambiguity_resolver.py` | Day 4 |
| Prompt 文件 | `prompts/stage{1,2,3}_system.txt` | Day 4 |
| 单元测试 | `tests/unit/test_*.py` | Day 5 |
| 集成测试 | `tests/integration/test_pipeline.py` | Week 2 |
| 测试数据 | `tests/fixtures/sample_inputs.py` | Week 2 |

---

## 验收标准

### 功能验收
- [ ] Stage 1 正确切片（简单句、复合句、列表）
- [ ] Stage 2 正确路由（6 个字段，无重叠）
- [ ] Stage 3 正确消解（拆分歧义 span）
- [ ] ambiguity 正确回写到 SpanIR

### 代码质量
- [ ] 通过 mypy 类型检查
- [ ] 通过 ruff 代码风格检查
- [ ] 所有公共方法有 docstring
- [ ] 使用 logger 记录关键信息

### 测试覆盖
- [ ] 单元测试覆盖率 > 80%
- [ ] 集成测试覆盖 Stage 1-5
- [ ] 测试数据包含多种场景
