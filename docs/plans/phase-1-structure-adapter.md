# Phase 1: Structure Adapter — 实施计划

## 目标

让 `RawSection` 携带结构信息（`structure_type` + `list_items`），使下游无需重新解析即可获取 section 的形态。

## 当前状态

- ✅ `StructuralShapeDetector` 已实现（morphology.py）
- ✅ `detect()` 已使用形态检测
- ❌ `RawSection` 缺少 `structure_type` 和 `list_items` 字段
- ❌ `_parse_sections()` 不分析 list 结构

## 实施步骤

### Step 1: 给 RawSection 添加字段

文件：`src/nl2spl/canonical/compile_input.py`

```python
@dataclass
class RawSection:
    section_id: str
    canonical_title: str
    original_title: str
    text: str
    order: int
    start_offset: int | None = None
    end_offset: int | None = None
    structure_type: str = "paragraph"       # NEW
    list_items: list[str] | None = None     # NEW
```

用 `str` 而非 `Literal`，保持简单。默认值确保向后兼容。

### Step 2: 在 _parse_sections() 中填充新字段

文件：`src/nl2spl/adapters/structural_nl.py`

在 `_parse_sections()` 创建 `RawSection` 后，调用已有的 `_has_list_shape()` 和 `_split_list_items()` 填充字段。

### Step 3: 简化 adapt() 中的重复计算

`adapt()` 第 146-147 行当前重新计算 list 结构。改为从 `section.structure_type` 和 `section.list_items` 读取。

### Step 4: 添加 Phase 1 测试

在 `tests/unit/test_phase0_baseline.py` 或新文件中添加设计文档要求的测试：

```python
def test_structure_detector_recognizes_list():
    sections = StructuralNLAdapter(None)._parse_sections(
        "Error handling:\n- Missing data\n- Invalid format"
    )
    assert len(sections) == 1
    assert sections[0].structure_type == "list"
    assert len(sections[0].list_items) == 2

def test_structure_detector_title_agnostic():
    """不依赖固定标题词汇"""
    for title in ["Failure handling", "Error scenarios", "Exception cases"]:
        sections = StructuralNLAdapter(None)._parse_sections(
            f"{title}:\n- Missing data"
        )
        assert len(sections) == 1
        assert sections[0].structure_type == "list"
```

### Step 5: 运行全量测试

```bash
pytest tests/unit/test_phase0_baseline.py tests/unit/test_input_adapters.py tests/unit/test_failure_mode_bridge.py tests/integration/test_llm_adapter_engine_e2e.py -v
```

## 验收标准

- [ ] `"Error handling:"` 和 `"Failure handling:"` 都能识别为结构化
- [ ] 不再依赖固定标题词汇表（detect 层面已满足，adapt 层面保持向后兼容）
- [ ] 现有测试保持兼容
- [ ] `RawSection.structure_type` 和 `list_items` 正确填充

## 文件变更

| 操作 | 文件 |
|------|------|
| 修改 | `src/nl2spl/canonical/compile_input.py` — RawSection 添加字段 |
| 修改 | `src/nl2spl/adapters/structural_nl.py` — _parse_sections 填充字段 + adapt 简化 |
| 新增 | `tests/unit/test_phase1_structure_adapter.py` — Phase 1 测试 |
