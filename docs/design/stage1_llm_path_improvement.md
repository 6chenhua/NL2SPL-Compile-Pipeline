# Stage 1 SpanSlicer LLM 路径质量改进设计

> **版本**: v2.0  
> **修订记录**: v1.0 初始版本；v2.0 整合批判性分析修订（缺陷根因修正、Stage 2/3 语言统一、Stage 3 字段继承、预处理多行支持、性能基线、错误路径规范、兼容性矩阵）

---

## 1. 问题背景

### 1.1 当前架构现状

Stage 1（SpanSlicer）与 Stage 2（FieldRouter）构成 NL → SPL 管线的前置两层，负责将原始文本切分为语义完整的 span（Stage 1）并将其路由到 6 个语义字段（Stage 2）。这两层均存在双执行路径：

- **LLM 路径**（`generic_nl` schema）：纯 LLM 调用，Stage 1 产 span，Stage 2 产 route。
- **Canonical 路径**（`structural_nl` schema）：确定性适配器预处理，产出带语义标记的 `SemanticPacket` 后由 Stage 1/2 复用。

### 1.2 实际质量差距

对同一份 "Internal Communications Drafting" 结构化 Markdown 输入，两路径输出差异显著：

| 指标 | LLM 路径（generic_nl） | Canonical 路径（structural_nl） |
|---|---|---|
| **Span 数量** | 18 | 30+ |
| **段标签剥离** | ❌ 保留（如 `"Task family: ..."`）| ✅ 剥离（仅保留内容）|
| **列表拆分** | ❌ 合并（如 `"A user request, optional topics..."`）| ✅ 逐项拆分 |
| **Provenance** | ❌ 无 `source_section_id` / `source_packet_id` | ✅ 完整 |
| **输出验证** | ❌ 解析 JSON 即结束 | ✅ Validator 校验 schema/角色/覆盖 |

### 1.3 当前 Prompt 规则体系的 6 个结构性缺陷

通过分析 `stage1_system.txt` 的 6 条规则及下游 Stage 2/3 实现，识别出以下根因：

#### 缺陷 1（High）：Rule 3 覆盖范围不足——只识别 `Label: content` 模式

现有规则只说 `"Label: content" (e.g. "Task family: newsletters...")`，但实际 Markdown 输入包含多种结构标记：

| 模式 | 示例 | 当前规则 | 理想处理 |
|---|---|---|---|
| `# Title` | `# Internal Communications Drafting` | ❌ 未覆盖 | 剥离 `#`，判断元标签 |
| `## Section` | `## Task Family` | ❌ 未覆盖 | 剥离整行（组织性） |
| `**Label:**` | `**Name:** Internal Communications Drafting` | ⚠️ 半覆盖 | 剥离 `**Label:**` 及后续内联 markdown |
| `- item` | `- Newsletters` | ❌ 未覆盖 | 剥离 `-` |
| `N. item` | `1. Receive request` | ❌ 未覆盖 | 剥离 `N.` |
| `Title – MetaLabel` | `Title – Structural Requirement Description` | ❌ 未覆盖 | 剥离 `– MetaLabel` |

#### 缺陷 2（Low）：Rule 6 与 Rule 3 措辞不精确导致 LLM 判断边界不稳定

Rule 6 原文要求 *"Every **sentence and clause** must appear in exactly one span"*，而非 "every line"。严格语义下，组织性标题 `## Task Family` 本身不含完整 sentence 或 clause，不应被 No Omission 规则覆盖。

**真正的根因**：规则未明确 "sentence/clause" 与 "structural label" 的判断边界。LLM 对边界的理解因调用而异——同一标题在不同运行中可能被判定为语义内容（生成 span）或组织结构（不生成 span），导致输出不一致。这不是规则之间的逻辑冲突，而是**规则措辞的精确性不足**。

#### 缺陷 3（Low）：Rule 4（Verbatim）与 Rule 1（Semantic Completeness）的切片粒度策略缺失

`"Optional: None"` 剥离标签后剩下 `"None"`——verbatim 但语义不完整。更根本的原因是**切片粒度策略缺失**：`"None"` 应被视为 `"Optional"` 字段的**占位值**而非独立语义单元，这要求 Stage 1 具备字段感知能力，而目前完全不具备。

Canonical 路径通过 `source_packet_id` 上下文解决此问题，但 LLM 路径无 provenance，Stage 2 无法仅凭 `"None"` 判断属于 `input_contract` 还是 `constraint`。**第三层 §2.3 新增 `section_context` 字段，配合 `is_placeholder` 标记策略**（见 §2.3.6）系统性解决。

#### 缺陷 4（Medium）：缺少反例（Negative Examples）

从 `stage1_system.txt` 全 42 行看，无任何 BAD/GOOD 对比。LLM 对 "不要做什么" 的学习信号远比正面规则有效。

#### 缺陷 5（High）：切片与路由互依赖，但切片在无路由上下文下执行

某些复合内容（如 `"If sources unavailable, flag the issue and ask for clarification"`）需要同时判断：
- 应拆为 2 个 span（condition + handler）
- 每个 span 应路由到不同字段（`failure_mode` vs `exception_handler_action`）

Stage 1 切片时完全不知道路由语义，只能整体输出，错误推到 Stage 3 补救。

#### 缺陷 6（Medium）：Stage 2/3 LLM 路径 user_prompt 同样存在中英文混杂

| 阶段 | 文件 / 行号 | 中文 prompt 片段 |
|---|---|---|
| **Stage 1** | `stage1_span_slicer.py` L47-53 | `"请将以下文本切分为语义完整的 span："` |
| **Stage 2** | `stage2_field_router.py` L108-114 | `"请将以下 span 路由到 6 个语义字段："` |
| **Stage 3** | `stage3_ambiguity_resolver.py` L117-134 | `"以下 span 被标记为歧义，请拆分："` |

**影响**：三个阶段的 LLM 交互呈现混合语言状态。若本次只修复 Stage 1，下游 Stage 2/3 仍保持中英混杂，翻译漂移风险在后续阶段持续存在。

**本次方案定位**：第一层统一修复 Stage 1/2/3 的 user_prompt 语言；第一层 prompt 规则（§2.1.1–2.1.3）仅针对 Stage 1 的 system prompt。Stage 2/3 system prompt 规则统一留给后续专项迭代。

### 1.4 问题本质

LLM 路径的核心问题不是 "Stage 1 与 Stage 2 分离"，而是 **Stage 1 的切片质量太差**：规则覆盖不足、无确定性预处理、无后验验证、无字段感知能力、下游 Stage 语言不统一。即使合并两阶段，若 prompt 不变，合并后仍会产出低质量切片。

### 1.5 严重性与影响面总表

| 缺陷 | 严重性 | 影响面 |
|---|---|---|
| 缺陷 1（Rule 3 不足）| **High** | 所有结构化输入 |
| 缺陷 5（切片路由互依赖）| **High** | 复合句处理 |
| 缺陷 6（多阶段语言不一致）| **Medium** | 下游 Stage 2/3 |
| 缺陷 4（无反例）| **Medium** | LLM 学习信号 |
| 缺陷 2（措辞不精确）| **Low** | 仅影响边缘 case |
| 缺陷 3（None 语义丢失）| **Low** | 仅影响占位符 span |

---

## 2. 详细设计方案

采用 **三层递进改进**：先修 Prompt（立即），再加确定性预处理（中期），最后补全 Provenance 与下游继承（配合 Stage 2/3）。

### 2.1 第一层：Prompt 规则修补（最高优先级）

**目标**：通过 prompt 工程直接提升 LLM 输出质量，并统一 Stage 1/2/3 的 prompt 语言。

**文件**：
- `prompts/stage1_system.txt`
- `src/nl2spl/pipeline/stages/stage1_span_slicer.py`
- `src/nl2spl/pipeline/stages/stage2_field_router.py`
- `src/nl2spl/pipeline/stages/stage3_ambiguity_resolver.py`

#### 2.1.1 扩展 Rule 3：完整的结构标记剥离清单

**设计思路**：现有 Rule 3 仅覆盖 `Label: content` 格式。Markdown 文档中存在多种结构标记（`#`/`##`/`**Label:**`/`-`/`N.`），需明确剥离每种标记。

```
3. **Strip All Structural Markers**: Remove these patterns from span text:

   Markdown headers:
   - `#`, `##`, `###` → remove the marker.
   - If the header text (in lowercase) matches one of these known
     organizational titles — "task family", "inputs for each run",
     "required outputs", "reusable process", "policies", "failure
     handling", "delegation policy" — strip the entire header;
     do NOT produce a span for it.
   - Otherwise, keep the text as a span (it names a concept, e.g.
     "## API Reference").

   Bold labels:
   - `**Label:**` at the start of a line → strip both the `**`, the
     `Label:`, and any immediately following inline markdown
     (e.g. `_emphasis_`, `*italic*`); keep only the plain text content.

   Bullet markers:
   - `-`, `*`, `+` at the start of a list item → strip the marker;
     keep only the item text.

   Number markers:
   - `1.`, `2.`, `3.` (etc.) at the start of an ordered list item →
     strip the marker; keep only the step text.

   En-dash meta-labels:
   - `Title – MetaLabel` where MetaLabel contains any of the keywords:
     "Description", "Document", "Specification", "Guide" → strip the
     `– MetaLabel` portion and keep only the Title.
   - DO NOT strip en-dash phrases that contain version information,
     scope qualifiers, or proper nouns (e.g. "API Design – v2.0",
     "Data Processing – With External Sources").
```

**关键修订**：
- **组织性标题白名单**：明确枚举 7 个已知组织性标题，取代模糊的启发式判断
- **En-dash 规则**：改为关键词匹配启发式（含 "Description"/"Document" 等才剥离），而非精确字符串匹配，并显式标注不剥离的反例（`v2.0` 类版本号）
- **Bold labels**：明确覆盖紧随的 inline markdown 符号（`_emphasis_` 等）

> **⚠️ 双白名单同步约束**：§2.1.1（Prompt 中的组织性标题枚举）与 §2.2.1（代码中的 `_ORGANIZATIONAL_TITLES` 集合）是**同一白名单的两份物理副本**。任何对其中一份的修改必须同步到另一份，否则将导致 Prompt 期望的切片行为与代码实际行为不一致。建议在代码仓库中建立 lint 规则或 CI 检查，确保两处列表始终保持同步。

#### 2.1.2 澄清 Rule 6：组织性标题排除

**设计思路**：针对缺陷 2 根因（"sentence/clause" 边界模糊），明确将组织性标题排除出 No Omission 覆盖范围。

```
6. **No Omission of Semantic Content**: Every semantic clause and sentence
   must appear in exactly one span. However, organizational headers
   (those whose lowercase text matches the whitelist in Rule 3) serve
   only to label subsequent content; they are NOT semantic content
   (they do not express a complete thought or clause) and should be
   stripped, NOT included as spans.
```

#### 2.1.3 添加反例（Common Errors）

**设计思路**：LLM 对反例比对正面规则更敏感。明确列举最常见的错误模式并提供正确输出。反例覆盖**多领域**输入，避免过度特化。

```
## Common Errors (DO NOT PRODUCE THESE)

❌ BAD:  {"text": "Task family: Internal newsletters, announcements..."}
   REASON: Label "Task family:" must be stripped.
   ✅ GOOD: {"text": "Internal newsletters, announcements..."}

❌ BAD:  {"text": "A user request, optional known topics, optional timeframe..."}
   REASON: List items must each be a separate span.
   ✅ GOOD: {"text": "A user request"}, {"text": "optional known topics"}, ...

❌ BAD:  {"text": "1. Receive request"}
   REASON: Number marker must be stripped.
   ✅ GOOD: {"text": "Receive request"}

❌ BAD:  {"text": "## Inputs for Each Run"}
   REASON: Organizational headers must NOT appear as spans.
   ✅ GOOD: Do not produce this span; include its subsection content instead.

❌ BAD:  {"text": "Internal Communications Drafting – Structural Requirement Description"}
   REASON: "– Structural Requirement Description" is a meta-label;
           strip it (contains keyword "Description").
   ✅ GOOD: {"text": "Internal Communications Drafting"}

❌ BAD (from a different domain — API spec input):
       {"text": "Endpoint: POST /api/v1/users"}
   REASON: Label "Endpoint:" must be stripped.
   ✅ GOOD: {"text": "POST /api/v1/users"}

❌ BAD (from a different domain — policy document input):
       {"text": "## Rules and Regulations"}
   REASON: Keep this — "Rules and Regulations" names a concept,
           not an organizational header.
   ✅ GOOD: {"text": "Rules and Regulations"}
```

**关键修订**：新增 2 个来自**不同领域**（API 规格、Policy 文档）的反例，避免 LLM 过度特化 "Internal Communications" 类输入。

#### 2.1.4 修订 Rule 4：结构性标记剥离的例外条款

**设计思路**：原始 Rule 4 说 "the span text must be an exact verbatim copy of the original. Do not rewrite, paraphrase, translate, or summarize." 但扩展后的 Rule 3 要求剥离 `#`/`##`/`**Label:**`/`-`/`N.` 等多种标记。这两条规则存在**潜在认知冲突**：LLM 可能将 "剥离 `1.`" 视为违反 verbatim 要求。需要在 Rule 4 中明确添加例外语句，消除歧义。

```
4. **Preserve Original Text**: Apart from the structural-marker stripping
   defined in Rule 3, the span text must be an exact verbatim copy of
   the original. Do not rewrite, paraphrase, translate, or summarize.

   Exception: structural markers listed in Rule 3 (markdown headers,
   bold labels, bullet markers, number markers, en-dash meta-labels)
   are excluded from the verbatim requirement — removing them is not
   "rewriting", it is structural cleanup.
```

**关键修订**：将 Rule 4 的 "Apart from the label-stripping rule above" 扩展为 "Apart from the structural-marker stripping defined in Rule 3"，并显式列出例外场景，消除 Rule 3（剥离标记）与 Rule 4（verbatim 保留）之间的认知冲突。

#### 2.1.5 统一 Prompt 语言（覆盖 Stage 1/2/3）

**设计思路**：System prompt 英文 + User prompt 中文 + 输入文本英文 = 三种语言混杂，增加 LLM 认知负担，可能导致翻译 span 内容（违反 Rule 4）。统一为英文。

**Stage 1 代码改动**（`stage1_span_slicer.py` L47-53）：

```python
# 修改前
user_prompt = f"""请将以下文本切分为语义完整的 span：

---
{raw_text}
---

输出 JSON："""

# 修改后
user_prompt = f"""Split the following text into semantically complete spans.

---
{raw_text}
---

Output valid JSON:"""
```

**Stage 2 代码改动**（`stage2_field_router.py` L108-114）：

```python
# 修改前
user_prompt = f"""请将以下 span 路由到 6 个语义字段：

---
{spans_json}
---

输出 JSON："""

# 修改后
user_prompt = f"""Route each span below to one of 6 semantic fields.

---
{spans_json}
---

Output valid JSON:"""
```

**Stage 3 代码改动**（`stage3_ambiguity_resolver.py` L117-134）：

```python
# 修改前
user_prompt = f"""以下 span 被标记为歧义，请拆分：

原始 spans：
...

# 修改后
user_prompt = f"""The spans below are marked ambiguous. Split each into
unambiguous sub-spans.

Original spans:
...
Output valid JSON:"""
```

**本次范围边界**：user_prompt 英文化覆盖全部三阶段；system prompt（`stage2_system.txt`、`stage3_system.txt`）规则改进留给后续专项迭代。

### 2.2 第二层：确定性预处理（中期）

**目标**：将可由正则可靠识别的结构切片从 LLM 责任中移除，由代码确定性地切片并附 provenance；LLM 只处理残留的语义模糊内容。

**设计思路**：Canonical 路径已证明 "确定性预处理 + 可选 LLM refinement" 是稳健范式。LLM 路径应复用此模式：先由代码识别 Markdown 结构标记并切片，再将剩余模糊文本交给 LLM。

**文件**：`src/nl2spl/pipeline/stages/stage1_span_slicer.py`

#### 2.2.1 新增 `_pre_slice_structural()` 方法

**职责**：接收原始文本，识别确定性结构模式，产出 `list[SpanIR]` 和 `residual_blocks`（带 section 上下文注释的块级残留）。

**处理策略：块级（而非逐行）处理**

设计采用**语义块级处理**而非逐行处理，以支持跨多行的结构单元。以空行为块分隔符，每个块内再识别结构标记：

```
Block 1: "**Description:** This agent handles all internal
          communications including newsletters and announcements."
          → 单条 **Label:** 跨 2 行
          → 合并为 1 个 span: "This agent handles all internal
             communications including newsletters and announcements."

Block 2: "- Newsletters"
         → 单行 bullet item
         → 1 个 span: "Newsletters"
```

**识别模式与处理逻辑**：

| 模式（正则） | 处理 | 输出 span |
|---|---|---|
| `^#{1,6}\s+(.+)` | 剥离 `#` 标记；标题小写后匹配组织性标题表或关键词模式 | 若匹配：记录为当前 `section_context`，无 span；若否：生成 span |
| `^\*\*(.+?):\*\*\s*(.+)` | 剥离 `**Label:**`，提取 content；若 content 跨多行则累积直到下个块 | `{text: "content"}` |
| `^[-*+]\s+(.+)` | 剥离 marker，每项独立 span | `{text: "item"}` |
| `^\d+\.\s+(.+)` | 剥离 `N.`，每步独立 span | `{text: "step"}` |
| `(.+?)\s+–\s+(.+?)(Description|Document|Specification|Guide).*$` | 剥离 `– MetaLabel` | `{text: "Title"}` |

**组织性标题判定**（两级 fallback）：

```python
# Level 1: 精确匹配（适用于已知领域）
_ORGANIZATIONAL_TITLES: frozenset[str] = frozenset({
    "task family",
    "inputs for each run",
    "required outputs",
    "reusable process",
    "policies",
    "failure handling",
    "delegation policy",
})

# Level 2: 关键词模式匹配（适用于新领域扩展）
_ORGANIZATIONAL_KEYWORDS: re.Pattern = re.compile(
    r'^(inputs?|outputs?|polic(?:y|ies)|process|procedure|'
    r'requirements?|failures?|delegation|prerequisites?|'
    r'steps?|actions?|constraints?)\b',
    re.IGNORECASE,
)

def _is_organizational(title: str) -> bool:
    """Determine if a section title is organizational (structural)
    rather than semantic (content-bearing)."""
    normalized = title.strip().lower()
    if normalized in _ORGANIZATIONAL_TITLES:
        return True
    return bool(_ORGANIZATIONAL_KEYWORDS.match(normalized))
```

**关键修订**：
- **块级处理**：检测 `**Label:**` 后累积后续非空行直到下一个结构标记或空行，解决多行内容语义断裂
- **两级 fallback 判定**：精确匹配 + 关键词模式匹配组合，兼顾已知领域的准确性和新领域的扩展性
- **section_context 跟踪**：每识别一个组织性标题，更新 `section_context`，后续每个 span 附带此字段

> **⚠️ 双白名单同步约束**：本处 `_ORGANIZATIONAL_TITLES` 集合必须与 §2.1.1 中 Prompt 内联的组织性标题枚举保持完全一致。任何修改必须双向同步，建议通过 lint 规则或单元测试断言两处列表一致。详见 §8 #5。

#### 2.2.2 主 `execute()` 流程改造

```python
def execute(self, input_data: str | CanonicalCompileInput) -> list[SpanIR]:
    if isinstance(input_data, CanonicalCompileInput):
        # ... 现有 canonical 逻辑不变 ...

    raw_text = input_data
    self.logger.info("Starting span slicing for text of length %d", len(raw_text))

    # --- NEW: 确定性预处理（块级处理） ---
    try:
        pre_slices, residual_blocks = self._pre_slice_structural(raw_text)
    except Exception as exc:
        # 降级策略：预处理异常时 fallback 到第一层全量 LLM 路径
        self.logger.warning(
            "Pre-slicing failed (%s); falling back to full LLM path.", exc
        )
        pre_slices, residual_blocks = [], [raw_text]

    # --- NEW: 仅残留块调用 LLM（逐块分别调用，消除跨 section fallback 歧义） ---
    llm_spans: list[SpanIR] = []
    if any(block.strip() for block in residual_blocks):
        try:
            llm_spans = self._call_llm_for_residual(residual_blocks)
        except Exception as exc:
            # 降级策略：残留块 LLM 调用全部失败时，跳过残留切分
            self.logger.warning(
                "Residual LLM call failed (%s); skipping residual spans.", exc,
            )
            llm_spans = []

    # --- NEW: 合并并统一重编号（代码层面，不依赖 LLM start_id 约定） ---
    all_spans = pre_slices + llm_spans
    for i, span in enumerate(all_spans):
        span.span_id = f"s{i + 1}"

    # --- NEW: 后验验证 ---
    coverage_diags = self._validate_coverage(raw_text, all_spans)

    # ... checkpoint / 返回 ...
    return all_spans
```

**关键修订**：
- **LLM span_id 忽略**：代码层面统一重编号（`s{i+1}`），完全消除对 LLM 数字计数能力的依赖
- **降级策略**：预处理异常时 fallback 到第一层全量 LLM 路径（等同第一层行为），避免阻断编译

#### 2.2.3 `_call_llm_for_residual()` 方法

**设计思路**：残留块（`residual_blocks`）中可能仍有需要语义拆分的复合句。为保留位置上下文，**每个残留块独立调用 LLM**，彻底消除跨 section fallback 歧义。

完整实现（含逐块调用逻辑、错误隔离、`section_context` 赋值）详见 **§2.3.3**。

**残留文本块（`residual_blocks`）格式**：

预处理阶段在残留块前插入 section 注释头，保留位置线索：

```
[Section: Reusable Process]
If sources are unavailable, flag the issue and ask for clarification.
Ensure you document all steps before proceeding.

[Section: Policies]
Sensitive topics require approval from legal counsel before publication.
```

#### 2.2.4 `_validate_coverage()` 方法

**设计思路**：验证切片是否覆盖了原始文本的所有语义内容。

**明确算法定义**：

采用**词集合 Jaccard 相似度（单向）**：

```
raw_tokens = set(raw_text_lower.split())                    # 原文词集合
span_tokens = set(" ".join(s.text for s in all_spans).lower().split())

# 剥离标签豁免：仅豁免 Markdown 标点符号，不豁免组织性标题词。
# 原因：组织性标题（如 "inputs for each run"）展开为单词后，
# "for"/"each"/"run"/"inputs" 等常见词在文档其他位置也会出现，
# 豁免这些词会导致覆盖率虚高（错误地认为 span 覆盖了原文）。
structural_tokens = {"##", "#", ":", "**", "-", "*", "+"}

coverage_numerator = len(raw_tokens & span_tokens) - len(raw_tokens & span_tokens & structural_tokens)
coverage_denominator = len(raw_tokens) - len(raw_tokens & structural_tokens)

raw_to_span_coverage = coverage_numerator / max(coverage_denominator, 1)
```

**行为规则**：
- 覆盖率 ≥ 0.90：通过，无诊断
- 覆盖率 ∈ [0.80, 0.90)：生成 `warning` 级 `CompileDiagnostic`，不阻断编译
- 覆盖率 < 0.80：生成 `error` 级 `CompileDiagnostic`，不阻断编译但记录到 checkpoint

诊断输出格式（追加到 checkpoint 的 `diagnostics` 字段）：

```python
{
    "diagnostics": [{
        "kind": "coverage_warning",
        "severity": "warning",
        "coverage": 0.87,
        "missing_tokens_sample": ["word1", "word2", ...],
        "message": "Span coverage is 87% (threshold: 90%).",
    }]
}
```

#### 2.2.5 错误处理与降级策略汇总

| 阶段 | 错误类型 | 行为 |
|---|---|---|
| `_pre_slice_structural()` 异常 | 正则匹配失败 / 内部错误 | **降级**：fallback 到全量 LLM 路径（第一层行为），生成 warning 诊断 |
| `_call_llm_for_residual()` 单块 LLM 异常 | 单块调用失败 / JSON 解析失败 | **错误隔离**：仅跳过该块，继续处理其他块，生成 warning 诊断（不影响其他块） |
| `_call_llm_for_residual()` 全部块失败 | 所有残留块 LLM 调用均失败 | **降级**：返回空列表，仅使用预处理结果 |
| `_validate_coverage()` 覆盖率 < 0.80 | 内容可能大面积遗漏 | **不阻断**编译，生成 error 级 `CompileDiagnostic` |

### 2.3 第三层：Provenance 补全与下游继承（配合 Stage 2/3）

**目标**：为 LLM 路径产出的 span 增加 `section_context`，解决 `"None"` 等脱离上下文后语义不完整的 span，并确保 Stage 3 拆分后子 span 正确继承。

**文件**：
- `src/nl2spl/ir/span_ir.py`
- `prompts/stage1_system.txt`
- `src/nl2spl/pipeline/stages/stage1_span_slicer.py`
- `src/nl2spl/pipeline/stages/stage2_field_router.py`
- **`src/nl2spl/pipeline/stages/stage3_ambiguity_resolver.py`（新增修改点）**

#### 2.3.1 SpanIR 扩展

**设计思路**：新增 `section_context` 字段，记录 span 所属最近的组织性标题。字段可选，不影响 canonical 路径现有语义。

```python
@dataclass
class SpanIR:
    span_id: str
    text: str
    ambiguity: AmbiguityInfo = field(default_factory=AmbiguityInfo)
    source_section_id: str | None = None
    source_packet_id: str | None = None
    section_context: str | None = None
    """Natural-language section title for LLM-path spans.
    
    This field carries the nearest organizational header text (e.g.
    "Policies", "Inputs for Each Run"). Mutually exclusive in practice
    with source_section_id:
    
    - source_section_id: structured ID from canonical adapter
                         (e.g. "sec_task_family")
    - section_context: natural-language title from LLM path
                       (e.g. "Task Family")
    
    Both may be None for top-level document content.
    """

    def to_dict(self) -> dict[str, object]:
        data: dict[str, object] = {
            "span_id": self.span_id,
            "text": self.text,
            "ambiguity": {
                "is_ambiguous": self.ambiguity.is_ambiguous,
                "reasons": self.ambiguity.reasons,
                "needs_split": self.ambiguity.needs_split,
            },
        }
        if self.source_section_id is not None:
            data["source_section_id"] = self.source_section_id
        if self.source_packet_id is not None:
            data["source_packet_id"] = self.source_packet_id
        if self.section_context is not None:
            data["section_context"] = self.section_context
        return data
```

**文档注释明确互斥语义**：`source_section_id`（canonical 路径结构化 ID）与 `section_context`（LLM 路径自然语言标题）通常互斥填充，二者并存时 canonical ID 优先。

#### 2.3.2 确定性预处理补 section_context

**设计思路**：在 `_pre_slice_structural()` 中，维护当前 `section_context`，生成的每个 span 都带上此字段。

```python
def _pre_slice_structural(self, raw_text: str) -> tuple[list[SpanIR], list[str]]:
    section_context: str | None = None
    pre_slices: list[SpanIR] = []
    residual_blocks: list[str] = []
    current_block_lines: list[str] = []
    current_block_context: str | None = None

    def _flush_block():
        nonlocal current_block_lines, current_block_context
        if current_block_lines:
            block_text = "\n".join(current_block_lines)
            if current_block_context:
                residual_blocks.append(
                    f"[Section: {current_block_context}]\n{block_text}"
                )
            else:
                residual_blocks.append(block_text)
        current_block_lines = []
        current_block_context = None

    for line in raw_text.splitlines():
        stripped = line.strip()
        if not stripped:
            _flush_block()
            continue

        # 匹配 ## 标题
        if section_match := re.match(r'^#{1,6}\s+(.+)$', stripped):
            _flush_block()
            title = section_match.group(1).strip()
            if _is_organizational(title):
                section_context = title  # 记录但不生成 span
            else:
                pre_slices.append(SpanIR(
                    span_id="",  # 后续由 execute() 统一重编号
                    text=title,
                    section_context=section_context,
                ))
            continue

        # 匹配 **Label:** （块级累积）
        if label_match := re.match(r'^\*\*(.+?):\*\*\s*(.*)$', stripped):
            _flush_block()
            label_text = label_match.group(2).strip()
            if label_text:
                pre_slices.append(SpanIR(
                    span_id="",
                    text=label_text,
                    section_context=section_context,
                ))
            continue

        # 匹配 bullet item
        if bullet_match := re.match(r'^[-*+]\s+(.+)$', stripped):
            _flush_block()
            pre_slices.append(SpanIR(
                span_id="",
                text=bullet_match.group(1).strip(),
                section_context=section_context,
            ))
            continue

        # 匹配 ordered item
        if num_match := re.match(r'^\d+\.\s+(.+)$', stripped):
            _flush_block()
            pre_slices.append(SpanIR(
                span_id="",
                text=num_match.group(1).strip(),
                section_context=section_context,
            ))
            continue

        # 未匹配：累积到残留块
        if not current_block_lines:
            current_block_context = section_context
        current_block_lines.append(stripped)

    _flush_block()
    return pre_slices, residual_blocks
```

**关键设计点**：
- `span_id` 留空，由 `execute()` 统一分配（见 §2.2.2）
- 未匹配行按空行分块，每块插入 `[Section: ...]` 注释头保留位置线索
- 匹配 `**Label:**` 后开始新的 block（多行 content 作为残留处理，交给 LLM）

#### 2.3.3 LLM 输出扩展 section_context

**Prompt 改动**：在 `stage1_system.txt` 的输出格式中增加 `section_context` 字段：

```
## Output Format

Output valid JSON only, no markdown fences:
{
  "spans": [
    {
      "span_id": "s1",
      "text": "...",
      "section_context": "the nearest section header this span falls under,
                           or null if at document top-level"
    }
  ]
}

Note: span_id values will be reassigned by the pipeline. Use any valid
format (e.g. s1, s2) — the pipeline will renumber them.
```

**解析逻辑**：`_call_llm_for_residual()` **逐块分别调用 LLM**，每个残留块独立拥有确定的 `section_context`，彻底消除跨 section fallback 歧义：

```python
_SECTION_PREFIX_RE = re.compile(r'^\[Section:\s*(.+?)\]\s*\n(.*)$', re.DOTALL)

def _call_llm_for_residual(
    self, residual_blocks: list[str],
) -> list[SpanIR]:
    """Process each residual block with a separate LLM call.
    
    Per-block calls ensure each span's section_context comes from
    exactly one source (its own block's [Section: X] prefix),
    eliminating the cross-section fallback ambiguity that occurred
    when all blocks were concatenated into a single prompt.
    """
    all_spans: list[SpanIR] = []

    for block in residual_blocks:
        if not block.strip():
            continue

        # Extract section context and text from the block prefix
        m = _SECTION_PREFIX_RE.match(block.strip())
        if m:
            block_context = m.group(1)
            block_text = m.group(2).strip()
        else:
            block_context = None
            block_text = block.strip()

        if not block_text:
            continue

        system_prompt = load_prompt("stage1")
        user_prompt = f"""Split the following text into semantically
complete spans.

---
{block_text}
---

Output valid JSON:"""

        try:
            result = self.client.call_json(
                stage_name=self.name,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
        except Exception as exc:
            self.logger.warning(
                "LLM call for residual block failed (%s); "
                "skipping block.", exc,
            )
            continue

        for item in result.get("spans", []):
            all_spans.append(SpanIR(
                span_id="",  # 后续由 execute() 统一重编号
                text=item["text"],
                # LLM 输出优先；null 时回退到本块的 section prefix
                section_context=item.get("section_context") or block_context,
            ))

    return all_spans
```

**设计优势**：
1. **确定性归属**：每个 span 的 `section_context` 仅来自其所属块的 `[Section: X]` 前缀，不存在跨块歧义
2. **LLM 输出优先**：若 LLM 返回了非 null 的 `section_context`，直接采用
3. **块内 fallback**：若 LLM 返回 null，回退到**本块的** `[Section: X]` 前缀（而非任意块的前缀）
4. **错误隔离**：单个块的 LLM 调用失败不影响其他块，仅跳过失败块

**代价与权衡**：
- 调用次数从 1 次增至 N 次（N = 残留块数）
- 但每次调用的 token 量更小，总 token 数基本不变
- 延迟线性增加，但残留块数通常较少（结构化输入大部分由确定性预处理覆盖），实际影响可控

#### 2.3.4 Stage 2 适配：精确映射表替代关键词启发式

**设计思路**：原启发式路由（`if "policies" in ctx_lower`）对 `"Delegation Policy"` 会误判路由到 `rules`（正确应为 `behavior`）。改为精确映射表 + 关键词 fallback + 默认值的三级优先级。

```python
# 精确映射表（与 _ORGANIZATIONAL_TITLES 对齐）
_SECTION_CONTEXT_TO_FIELD: dict[str, str] = {
    "task family": "domain",
    "inputs for each run": "resources",
    "required outputs": "resources",
    "reusable process": "behavior",
    "policies": "rules",
    "failure handling": "behavior",
    "delegation policy": "behavior",
}

def _section_field(self, span: SpanIR, canonical_input: CanonicalCompileInput) -> str:
    # Priority 1: canonical source_section_id (structured, highest confidence)
    if span.source_section_id:
        sections = {s.section_id: s for s in canonical_input.raw_sections}
        section = sections.get(span.source_section_id)
        if section is not None:
            if section.canonical_title == "task_family":
                return "domain"
            if section.canonical_title in {"policies", "failure_handling"}:
                return "rules"
            return "behavior"

    # Priority 2: section_context exact match (LLM path, medium confidence)
    if span.section_context:
        ctx_lower = span.section_context.strip().lower()
        if ctx_lower in _SECTION_CONTEXT_TO_FIELD:
            return _SECTION_CONTEXT_TO_FIELD[ctx_lower]
        # Fallback: keyword-based routing (low confidence)
        if "input" in ctx_lower or "output" in ctx_lower:
            return "resources"
        if "policy" in ctx_lower or "rule" in ctx_lower or "constraint" in ctx_lower:
            return "rules"
        if "process" in ctx_lower or "step" in ctx_lower or "delegation" in ctx_lower:
            return "behavior"
        if "task" in ctx_lower or "family" in ctx_lower:
            return "domain"

    # Priority 3: default (lowest confidence)
    return "behavior"
```

**三级优先级设计意图**：
1. **精确匹配优先**（`ctx_lower in _SECTION_CONTEXT_TO_FIELD`）：彻底解决 `"Delegation Policy"` 误判——精确映射为 `behavior`，而非被 "policy" 关键词匹配到 `rules`
2. **关键词匹配作为 fallback**：覆盖未在映射表中的新领域输入
3. **默认 `behavior`**：兜底，与当前行为保持一致

#### 2.3.5 Stage 3 AmbiguityResolver section_context 继承（**关键新增**）

**问题分析**：`stage3_ambiguity_resolver.py` L160-167 创建拆分后的子 span 时，仅传递 `source_section_id` 和 `source_packet_id`，**未传递 `section_context`**。新增该字段后，若不做此修改，Stage 3 拆分后的子 span 将丢失 `section_context`，导致 Stage 2 路由时无法利用 section 上下文——这正是设计要解决的核心问题。

**修改**（`stage3_ambiguity_resolver.py` L160-167）：

```python
# 修改前
span = SpanIR(
    span_id=span_data["span_id"],
    text=span_data["text"],
    source_section_id=span_data.get("source_section_id")
        or (parent.source_section_id if parent else None),
    source_packet_id=span_data.get("source_packet_id")
        or (parent.source_packet_id if parent else None),
)

# 修改后
# 子 span ID 采用后缀策略：父 "s5" → 子 "s5a", "s5b", ...
# 而非使用 LLM 返回的 span_id（可能与 Stage 1 重编号后的 ID 冲突）
child_idx = sum(1 for s in new_spans if parent and s.span_id.startswith(parent.span_id))
child_id = f"{parent.span_id}{chr(ord('a') + child_idx)}" if parent else span_data["span_id"]

span = SpanIR(
    span_id=child_id,
    text=span_data["text"],
    source_section_id=span_data.get("source_section_id")
        or (parent.source_section_id if parent else None),
    source_packet_id=span_data.get("source_packet_id")
        or (parent.source_packet_id if parent else None),
    section_context=span_data.get("section_context")
        or (parent.section_context if parent else None),  # NEW: inherit from parent
    is_placeholder=parent.is_placeholder if parent else False,  # NEW: inherit from parent
)
```

**子 span ID 管理（后缀策略）**：

Stage 1 的 `execute()` 已对全局 span 列表做代码层重编号（`s1`, `s2`, ...）。Stage 3 若直接使用 LLM 返回的 `span_id`，极易与 Stage 1 的现有 ID 冲突。后缀策略解决此问题：

- 父 span `s5` 拆分为 2 个子 span → `s5a`, `s5b`
- 父 span `s12` 拆分为 3 个子 span → `s12a`, `s12b`, `s12c`
- 后缀使用小写字母 `a`–`z` 递增（单父 span 拆分不超过 26 个子 span，满足业务需求）
- 后缀保留了**可追溯性**：从 `s5a` 可直接追溯到原父 span `s5`

**继承规则**：
- 子 span `section_context` 默认继承父 span；若 LLM 显式指定则覆盖
- 子 span `is_placeholder` 默认继承父 span（占位符拆分后仍标记为占位符）
- 与 `source_section_id` / `source_packet_id` 的继承模式完全一致
- **子 span ID 不使用 LLM 返回值**，由代码层后缀分配保证全局唯一

#### 2.3.6 `"None"` 占位符 span 的特殊处理（**关键新增**）

**问题分析**：`"Optional: None"` 剥离标签后剩下 `"None"`。Stage 2 即使有 `section_context`，仍无法确定 `"None"` 对应哪个具体字段的空值。`"None"` 是**占位符**，语义本质是"该字段无内容"，不应被视为独立的语义单元。

**策略**：在确定性预处理阶段识别 `"None"` 型占位符 span，附加 `is_placeholder` 标记（SpanIR 新增布尔字段，默认 `False`）。Stage 2 路由时可将占位符 span 直接归入所属字段的 `resource_contract`，而非让 LLM 判断。

**SpanIR 扩展**：

```python
@dataclass
class SpanIR:
    span_id: str
    text: str
    ambiguity: AmbiguityInfo = field(default_factory=AmbiguityInfo)
    source_section_id: str | None = None
    source_packet_id: str | None = None
    section_context: str | None = None
    is_placeholder: bool = False
    """True when this span represents an empty/absent placeholder value.
    
    E.g. after stripping the label from "Optional: None", the remaining
    "None" is a placeholder indicating "no optional inputs exist", not
    a semantic statement to be routed on its own.
    """
```

**预处理识别**（`_pre_slice_structural()` 中）：

```python
_PLACEHOLDER_VALUES: frozenset[str] = frozenset({
    "none", "n/a", "na", "not applicable",
})

# 在生成 span 后检测：
if item_text.strip().lower() in _PLACEHOLDER_VALUES:
    span.is_placeholder = True
```

**下游路由辅助**（`FieldRouter._section_field()` 中）：

```python
if span.is_placeholder and span.section_context:
    # 占位符的归属由其 section_context 决定，不参与字段独立判断
    ctx_lower = span.section_context.strip().lower()
    if ctx_lower in _SECTION_CONTEXT_TO_FIELD:
        return _SECTION_CONTEXT_TO_FIELD[ctx_lower]
```

---

## 3. 严格验收标准

### 3.1 第一层验收（Prompt 修补）

#### 3.1.1 功能标准

| ID | 标准 | 验证方法 |
|-----|------|---------|
| **L1-F1** | `"Task family: ..."` 等 `Label: content` 格式的标签被剥离，span 文本仅含内容 | 单元测试：对包含 `Task family:` 的输入，输出中不含 `"Task family:"` 文本 |
| **L1-F2** | Markdown 列表项（`-`/`*`/`+` 开头的项）每项独立成 span | 单元测试：4 项列表产出 4 个 span，每个 span 文本为单一项 |
| **L1-F3** | 有序列表（`1.`/`2.` 等）每项独立成 span，编号被剥离 | 单元测试：7 步流程产出 7 个 span，文本如 `"Receive request"` 而非 `"1. Receive request"` |
| **L1-F4** | 组织性段标题（如 `## Task Family`）不产出独立 span | 单元测试：仅含 `## Task Family` 的输入产出 0 个含 "Task Family" 文本的 span |
| **L1-F5** | `Title – MetaLabel` 格式中，MetaLabel 含 Description/Document/Specification/Guide 关键词时剥离后半部分 | 单元测试：输入 `"X – Structural Requirement Description"` 输出 `"X"`；输入 `"Y – v2.0"` 保留原文 |
| **L1-F6** | Prompt 语言统一：Stage 1/2/3 的 `user_prompt` 均为纯英文 | 代码审查：三个 stage 文件中 user_prompt 字符串无中文 |

#### 3.1.2 质量指标

| ID | 指标 | 目标 | 验证方法 |
|-----|------|------|---------|
| **L1-Q1** | 标签剥离率（无残留 `Label:` 格式的 span） | 100% | 30 次 LLM 调用（`temperature=0`），检查所有 span 文本 |
| **L1-Q2** | 列表项拆分率（每个 `-` 项独立成 span） | ≥95% | 30 次 LLM 调用，检查列表项与 span 数 |
| **L1-Q3** | Prompt 语言一致性 | 100% 英文 | 代码审查 + 人工确认 |

#### 3.1.3 回归标准

| ID | 标准 | 验证方法 |
|-----|------|---------|
| **L1-R1** | Stage 1 的 `_execute_canonical()` 方法行为不变 | 单元测试：canonical 路径输出对比 golden fixture |
| **L1-R2** | Stage 2/3 的 canonical 路径行为不变 | 单元测试：canonical 路径输出对比 golden fixture |
| **L1-R3** | 所有现有测试通过 | `pytest tests/unit/`、`pytest tests/integration/` 全量通过 |

---

### 3.2 第二层验收（确定性预处理）

#### 3.2.1 功能标准

| ID | 标准 | 验证方法 |
|-----|------|---------|
| **L2-F1** | `_pre_slice_structural()` 对已知结构化标记（标题/bold label/bullet/ordered item/en-dash）100% 正确切片 | 单元测试：针对每种模式至少 3 个测试用例，覆盖正常、边界、异常输入 |
| **L2-F2** | 无法被规则匹配的文本正确收集到 `residual_blocks`，且每个块保留 section 注释头 | 单元测试：混合输入，残留块包含 `[Section: ...]` 前缀 |
| **L2-F3** | 跨行 `**Label:**` 内容的处理路径正确：同行 `label_text`（如 `**Name:** X`）由确定性预处理直接产出 span；**跨行 Label 内容**（如 `**Description:**\nThis agent handles...`）进入 `residual_blocks`，由 LLM 残留路径正确切分为语义完整 span（无截断半句） | 单元测试：构造跨行 Label 输入，验证其进入 `residual_blocks` 而非被截断为不完整 span |
| **L2-F4** | `pre_slice` 和 `llm_span` 合并后 span_id 由代码统一重编号，连续递增 | 单元测试：预处理 5 条 + LLM 3 条 → ID 为 s1–s8，忽略 LLM 输出的原始 ID |
| **L2-F5** | `_validate_coverage()` 在 Jaccard 覆盖率 < 0.90 时产出诊断警告 | 单元测试：mock LLM 返回缺失 span，验证诊断输出包含 `coverage_warning` |
| **L2-F6** | `_validate_coverage()` 剥离标签词 + 组织性标题词不计入覆盖率分母 | 单元测试：构造含已知标签的输入，覆盖率计算正确 |
| **L2-F7** | `_pre_slice_structural()` 异常时降级为全量 LLM 路径 | 单元测试：mock 预处理抛出 `ValueError`，验证 fallback 到 LLM 调用 |
| **L2-F8** | 组织性标题判定使用两级 fallback（精确匹配 + 关键词模式） | 单元测试：`_is_organizational()` 在白名单内和模式匹配上均返回 True |
| **L2-F9** | `_call_llm_for_residual()` LLM 调用失败时，跳过残留切分，仅使用预处理结果，不中断编译 | 单元测试：mock LLM 抛出异常，验证返回结果仅含 `pre_slices`，且日志含 `residual_skipped` 警告 |
| **L2-F10** | `_validate_coverage()` 在覆盖率 < 0.80 时生成 error 级 `CompileDiagnostic`，不阻断编译 | 单元测试：mock LLM 返回大量缺失 span 的结果，验证诊断 severity 为 `error` 且编译继续执行 |

#### 3.2.2 质量指标

| ID | 指标 | 目标 | 验证方法 |
|-----|------|------|---------|
| **L2-Q1** | 结构化标记识别准确率（无遗漏、无误判） | 100% | 20 个结构化 Markdown 样本，所有模式均被正确处理 |
| **L2-Q2** | LLM 调用 token 节省比（相对第一层） | ≥40% | 对比预处理前后 LLM 输入 token 数 |
| **L2-Q3** | 预处理延迟（`_pre_slice_structural()` 执行时间）| p95 ≤ 50ms | 基准测试：100 个样本，测量预处理阶段 p95 延迟 |
| **L2-Q4** | Stage 1 端到端延迟（预处理 + LLM 残留调用）| 相对基线增量 ≤ 200ms | 基准测试：相同输入，对比改动前后 Stage 1 总执行时间 p95 |

#### 3.2.3 回归标准

| ID | 标准 | 验证方法 |
|-----|------|---------|
| **L2-R1** | 第一层所有验收标准继续满足 | 全量运行第一层测试 |
| **L2-R2** | `_execute_canonical()` 方法行为不变（不经过 `_pre_slice_structural`） | 单元测试：canonical 路径走原 `_execute_canonical` 分支 |
| **L2-R3** | 纯自然语言输入（无可识别结构化标记）完全走 LLM 路径，行为等同第一层 | 单元测试：纯自然语言输入产出与第一层一致的输出结构 |

---

### 3.3 第三层验收（Provenance 补全与下游继承）

#### 3.3.1 功能标准

| ID | 标准 | 验证方法 |
|-----|------|---------|
| **L3-F1** | `SpanIR` 新增 `section_context: str \| None` 和 `is_placeholder: bool` 字段，默认 `None` / `False` | 单元测试：`SpanIR(span_id="s1", text="...")` 可正常实例化，新字段为默认值 |
| **L3-F2** | `_pre_slice_structural()` 产出的每个 span 的 `section_context` 为最近组织性标题文本 | 单元测试：跨 3 个 section 的输入，每个 span 的 `section_context` 逐一对应正确标题 |
| **L3-F3** | LLM 输出的 span 的 `section_context` 准确率 ≥80%（允许 20% null fallback） | 集成测试：10 次 LLM 调用，非 null 的 `section_context` 准确率 ≥80% |
| **L3-F4** | LLM 返回 null `section_context` 时，降级使用预处理阶段产出的值（fallback 机制） | 单元测试：mock LLM 返回 null `section_context`，验证 fallback 到预处理的值 |
| **L3-F5** | `to_dict()` 在 `section_context` 为 None 时不输出该字段；`is_placeholder` 为 False 时不输出 | 单元测试：`SpanIR(span_id="s1", text="t", section_context=None).to_dict()` 不含这两个键 |
| **L3-F6** | `FieldRouter._section_field()` 在无 `source_section_id` 时使用精确映射表，精确匹配优先于关键词匹配 | 单元测试：`section_context="Delegation Policy"` 路由到 `behavior`（非 `rules`） |
| **L3-F7** | **Stage 3 AmbiguityResolver 拆分后的子 span 保持父 span 的 `section_context`** | 单元测试：构造父 span 有 `section_context="Policies"`，拆分后每个子 span `section_context` 均为 `"Policies"` |
| **L3-F8** | `is_placeholder=True` 的 span 在 `_section_field()` 中按 `section_context` 映射路由（不走独立判断） | 单元测试：`text="None"`, `section_context="Inputs for Each Run"`, `is_placeholder=True` → 路由到 `resources` |
| **L3-F9** | LLM 拆分输出中显式指定 `section_context` 时，以 LLM 值覆盖父 span 值 | 单元测试：mock LLM 输出 `section_context="new section"`，子 span 使用 LLM 值 |

#### 3.3.2 质量指标

| ID | 指标 | 目标 | 验证方法 |
|-----|------|------|---------|
| **L3-Q1** | 确定性 span 的 `section_context` 准确率 | 100% | 20 个测试用例，`section_context` 与人工标注一致 |
| **L3-Q2** | LLM span 的 `section_context` 准确率 | ≥80% | 10 次 LLM 调用（`temperature=0`），非 null 值与人工标注一致率 |
| **L3-Q3** | `"None"` 等占位符 span 的 Stage 2 路由正确率提升 | 相对基线提升 ≥20 个百分点 | A/B 对比：有 `is_placeholder` + `section_context` vs 无，同一批短 span 路由到预期字段的比例 |

#### 3.3.3 回归标准

| ID | 标准 | 验证方法 |
|-----|------|---------|
| **L3-R1** | 第一、二层所有验收标准继续满足 | 全量运行第一、二层测试 |
| **L3-R2** | Canonical 路径的 `SpanIR` 输出不变（`section_context` 保持为 `None`，`is_placeholder` 保持为 `False`） | 单元测试：canonical 路径产出的 span 无新字段输出（`to_dict()` 不含这两个键） |
| **L3-R3** | Stage 2 接收无 `section_context` 的 span 时行为不变（等价于第一/二层） | 单元测试：构造旧格式 span，路由结果与改动前一致 |
| **L3-R4** | Stage 3 接收无 `section_context` 的 span 拆分时，子 span `section_context` 为 `None` | 单元测试：构造无 `section_context` 父 span，子 span `section_context` 为 `None` |
| **L3-R5** | 所有现有集成测试通过 | `pytest tests/integration/` 全量通过 |

---

## 4. 实施顺序与依赖关系

```
第一层 Prompt 修补（S1 Prompt + S1/S2/S3 语言统一）
        │
        ├──▶ 第三层 3b：LLM section_context（仅依赖第一层 Prompt 改动）
        │         ↑ 可与第二层并行实施
        │
        ▼
第二层 确定性预处理
        │
        ├──▶ 第三层 3a：预处理产出 section_context（依赖第二层）
        │
        └──▶ 第三层 3c：Stage 3 字段继承 + Stage 2 精确映射表
                   （依赖 3a 和 3b 均完成）
```

**关键依赖说明**：
- 3a 和 3b 是**第三层内部的两个并行子任务**，可独立实施
- 3c 是整合验证步骤，需要 3a/3b 均完成后方可实施
- 第一层验收标准（L1-F1 至 L1-F5）在第二层实现后**部分由代码保证**：第二层实现文档应明确标注"由代码保证"vs"仍由 LLM 保证"的条目

---

## 5. 理想输出示例

以 "Internal Communications Drafting" Markdown 为输入，三层改进后的预期输出（共 40 个 span）。

**关于 s1/s2 文本重复的设计说明**：s1 来自文档标题（H1 `# Internal Communications Drafting`），s2 来自 Name 字段（`**Name:** Internal Communications Drafting`）。虽然文本相同，但**语义角色不同**：s1 是文档主题标识，s2 是任务族名称定义。Stage 2 路由时二者都归 `domain`，但下游 Stage 8（ProfileExtractor）可区分利用（标题作为 profile_domain，Name 作为 task family identity）。这是规则严格执行的自然结果，保留比丢弃更安全。

```json
{
  "spans": [
    {"span_id": "s1",  "text": "Internal Communications Drafting", "section_context": null},
    {"span_id": "s2",  "text": "Internal Communications Drafting", "section_context": "Task Family"},
    {"span_id": "s3",  "text": "Include newsletters, announcements, update digests, and executive briefs.", "section_context": "Task Family"},
    {"span_id": "s4",  "text": "Exclude technical documentation and external communications.", "section_context": "Task Family"},
    {"span_id": "s5",  "text": "Newsletters", "section_context": "Task Family"},
    {"span_id": "s6",  "text": "Announcements", "section_context": "Task Family"},
    {"span_id": "s7",  "text": "Update digests", "section_context": "Task Family"},
    {"span_id": "s8",  "text": "Executive briefs", "section_context": "Task Family"},
    {"span_id": "s9",  "text": "Topic", "section_context": "Inputs for Each Run"},
    {"span_id": "s10", "text": "Audience", "section_context": "Inputs for Each Run"},
    {"span_id": "s11", "text": "Tone", "section_context": "Inputs for Each Run"},
    {"span_id": "s12", "text": "Key facts", "section_context": "Inputs for Each Run"},
    {"span_id": "s13", "text": "None", "section_context": "Inputs for Each Run", "is_placeholder": true},
    {"span_id": "s14", "text": "Draft message", "section_context": "Required Outputs"},
    {"span_id": "s15", "text": "Assumptions log", "section_context": "Required Outputs"},
    {"span_id": "s16", "text": "Evidence trail", "section_context": "Required Outputs"},
    {"span_id": "s17", "text": "Readiness status", "section_context": "Required Outputs"},
    {"span_id": "s18", "text": "Receive request", "section_context": "Reusable Process"},
    {"span_id": "s19", "text": "Validate inputs", "section_context": "Reusable Process"},
    {"span_id": "s20", "text": "Gather evidence", "section_context": "Reusable Process"},
    {"span_id": "s21", "text": "Draft", "section_context": "Reusable Process"},
    {"span_id": "s22", "text": "Review policies", "section_context": "Reusable Process"},
    {"span_id": "s23", "text": "Finalize with artifacts", "section_context": "Reusable Process"},
    {"span_id": "s24", "text": "Hand off", "section_context": "Reusable Process"},
    {"span_id": "s25", "text": "No external data", "section_context": "Policies"},
    {"span_id": "s26", "text": "Cite all sources", "section_context": "Policies"},
    {"span_id": "s27", "text": "Avoid legal/financial language", "section_context": "Policies"},
    {"span_id": "s28", "text": "Preserve brand tone and confidentiality", "section_context": "Policies"},
    {"span_id": "s29", "text": "Require approvals for sensitive topics", "section_context": "Policies"},
    {"span_id": "s30", "text": "None", "section_context": "Policies", "is_placeholder": true},
    {"span_id": "s31", "text": "Missing inputs", "section_context": "Failure Handling"},
    {"span_id": "s32", "text": "Tone mismatches", "section_context": "Failure Handling"},
    {"span_id": "s33", "text": "Unverified facts", "section_context": "Failure Handling"},
    {"span_id": "s34", "text": "Audience blind spots", "section_context": "Failure Handling"},
    {"span_id": "s35", "text": "Policy violations", "section_context": "Failure Handling"},
    {"span_id": "s36", "text": "None", "section_context": "Failure Handling", "is_placeholder": true},
    {"span_id": "s37", "text": "Drafting", "section_context": "Delegation Policy"},
    {"span_id": "s38", "text": "Fact-checking", "section_context": "Delegation Policy"},
    {"span_id": "s39", "text": "Formatting", "section_context": "Delegation Policy"},
    {"span_id": "s40", "text": "Revision history generation", "section_context": "Delegation Policy"}
  ]
}
```

**变化说明**：
- 相对理想输出 v1（41 spans），v2 移除了末尾 `"Non-delegable: None"` 产生的 `"None"` span（v1 为 s41），合并到 s36 后输出更精炼——实际输出仍为 40 spans
- `is_placeholder: true` 显式标记 `"None"` 型占位符 span（s13, s30, s36），下游路由不对其进行独立语义判断
- 所有 span 均附 `section_context`，Stage 2/3 可直接利用

---

## 6. 兼容性矩阵与序列化规范

### 6.1 SpanIR 新字段影响面

| 消费方 | 文件 | 使用字段 | 新增字段影响 |
|---|---|---|---|
| Stage 1（SpanSlicer）| `stage1_span_slicer.py` | 创建 SpanIR | ✅ 新增字段写入点 |
| Stage 2（FieldRouter） | `stage2_field_router.py` | 读取 / 传递 SpanIR | ⚠️ 新增 §2.3.4 映射表 |
| **Stage 3（AmbiguityResolver）** | `stage3_ambiguity_resolver.py` | **重新创建** SpanIR | ❌ **必须新增字段继承（§2.3.5）** |
| Stage 3.5（WorkerBoundaryPlanner） | `stage3_5_worker_boundary_planner/` | 读取 SpanIR.span_id / text | ✅ 新字段无影响（仅读取） |
| Stage 4-11 | 各 stage 模块 | 读取 SpanIR.span_id / text | ✅ 新字段无影响 |
| Checkpoint 文件 | `stage1_span_slicer.json` 等 | `to_dict()` 序列化 | ⚠️ 输出格式变更（新增字段） |
| 单元测试 fixtures | `tests/fixtures/` 下各文件 | 硬编码 SpanIR 字段 | ⚠️ fixture 需补充新字段预期 |

### 6.2 序列化格式规范

`SpanIR.to_dict()` 新增字段输出规则：

```python
# 输出规则（与 source_section_id 现有模式一致）：
# section_context: 仅在非 None 时输出
# is_placeholder: 仅在 True 时输出（False 时不输出，保持兼容）

{
    "span_id": "s1",
    "text": "None",
    "ambiguity": {...},
    "section_context": "Inputs for Each Run",  # 仅在非 None 时
    "is_placeholder": true                      # 仅在 True 时
}

# 以下示例不含新字段（向后兼容）：
{
    "span_id": "s5",
    "text": "Topic",
    "ambiguity": {...}
}
```

### 6.3 跨版本兼容性保证

- **前向兼容**：新版本代码读取旧 checkpoint 文件（无 `section_context` / `is_placeholder` 字段）时，字段取默认值（`None` / `False`），行为等同改动前
- **后向兼容**：旧版本代码读取新 checkpoint 文件时，`to_dict()` 不输出的字段（`section_context=None` 且 `is_placeholder=False` 时）不影响旧代码；输出的新字段（`section_context` 非 None 时或 `is_placeholder` 为 `true` 时）被旧代码忽略（`json.loads` 容错，未识别的键不会导致异常）

---

## 7. 风险矩阵

| 风险 | 严重性 | 概率 | 缓解措施 |
|---|---|---|---|
| LLM 无法可靠遵守 `start_id` 编号约定 | **High** | High | **已修复**：§2.2.2 代码层统一重编号 |
| Stage 3 拆分 span 后 `section_context` 丢失 | **High** | Deterministic | **已修复**：§2.3.5 显式规范继承逻辑 |
| `_section_field()` 关键词启发式误判 `"Delegation Policy"` | **High** | Medium | **已修复**：§2.3.4 精确映射表优先 |
| `_pre_slice_structural()` 无法处理多行 `**Label:**` 内容 | **Medium** | High | **已修复**：§2.2.1 改为块级处理 |
| Stage 2/3 中文 prompt 不同步修复 | **Medium** | Deterministic | **已修复**：§2.1.4 覆盖 Stage 1/2/3 |
| `_validate_coverage()` token 定义不清导致误报 | **Low** | Medium | **已修复**：§2.2.4 明确 Jaccard 公式 + 结构性标签豁免 |
| 预处理增加 Stage 1 延迟 | **Low** | Low | **已覆盖**：L2-Q3 延迟增量 ≤200ms 基准 |
| `"None"` 占位符 span 路由歧义 | **Low** | Medium | **已修复**：§2.3.6 `is_placeholder` 标记 + §2.3.4 占位符路由逻辑 |
| SpanIR 新字段引入下游意外行为 | **Low** | Low | 可选字段 + 严格回归测试（L3-R1 至 L3-R5） |

---

## 8. 已知限制与后续迭代方向

以下是本次设计**未覆盖**但已识别为后续需求的条目：

1. **Stage 2/3 system prompt 规则改进**：本次仅英文化 Stage 2/3 的 `user_prompt`（§2.1.4），其 `system_prompt`（`stage2_system.txt`、`stage3_system.txt`）的结构性规则改进留给后续专项迭代。

2. **`_ORGANIZATIONAL_TITLES` 数据驱动化**：当前硬编码在代码中。若后续发现标题措辞多样化（如 "Input Parameters" vs "Inputs for Each Run"），应迁移至配置文件或 prompt 内联白名单。

3. **切片与路由联合优化**：缺陷 5（切片路由互依赖）在三层方案中未根本解决——本次改进提升了切片质量，但切片仍在无路由上下文下执行。彻底解决需要"切片即路由"的联合 LLM 调用，作为第四层候选方案。

4. **`"None"` 占位符的语义完整表达**：当前方案标记占位符后由 Stage 2 路由。更根本的方案是让 Stage 1 输出 `"No optional inputs defined"` 替代 `"None"`（违反 Rule 4 verbatim 但语义更完整）——这需要重新权衡 Rule 4 的严格性，建议后续评估。

5. **双白名单同步自动化**：§2.1.1（Prompt）与 §2.2.1（代码 `_ORGANIZATIONAL_TITLES`）是同一白名单的两份物理副本，当前依赖人工确保同步。后续应建立自动化机制：方案 A）从单一源（如 YAML 配置文件）生成两份副本；方案 B）建立 CI lint 规则，在代码审查时检查两处列表是否一致。建议采用方案 A（单一源生成）作为最终目标。
