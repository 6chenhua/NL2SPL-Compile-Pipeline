# R3 DiagnosticProjector 实施计划

## 1. 阶段定位

R3 是 IRS v6 的 diagnostic projection 阶段。

R1 已经完成 report schema foundation，R2 已经完成 framework skeleton。R3 的目标是在 R2 `DiagnosticProjector` skeleton 上实现统一的 `ConstructSatisfactionReport` / `SlotSatisfaction` 到 `CompileDiagnostic` 的投影机制。

```text
R3 = report/slot diagnostic projection
R3 != checker semantic migration
R3 != Worker/Delegation checker
R3 != orchestrator integration
R3 != recursive IRS evaluator
R3 != old Stage 4/7 checker rewrite
```

R3 的核心价值是把 diagnostic 的 message / severity / blocking / target / dedup 规则集中到 projector，避免后续每个 checker 自己拼装 `CompileDiagnostic`。

```text
IRSChecker:
    负责 slot satisfaction 与 diagnostic_kind 标注

DiagnosticProjector:
    负责把 diagnostic_kind + report/slot evidence 投影成 CompileDiagnostic
```

## 2. 阶段目标

R3 需要完成：

```text
1. 扩展 DiagnosticProjector，使其从 report.slots 中读取 diagnostic_kind。
2. 使用 DiagnosticRegistry 获取 severity / blocks_completion / allowed_targets。
3. 生成 CompileDiagnostic。
4. 保留 slot/report 的 source_span_ids / source_section_id / source_packet_id。
5. 生成 deterministic diagnostic_id。
6. 生成 deterministic dedup key，并在 projector 内去重。
7. 对 unknown / disabled diagnostic kind 产生 warning 并跳过，不生成伪 diagnostic。
8. 保持 R2 runner 行为兼容。
9. 不迁移旧 checker。
10. 不接 orchestrator。
```

R3 只投影 checker 已经明确给出的 `diagnostic_kind`。R3 不负责判断某个 slot 是否应该产生 diagnostic。

## 3. 允许修改范围

R3 允许修改：

```text
src/nl2spl/compiler/irs/projector.py
src/nl2spl/compiler/irs/runner.py
tests/unit/compiler/irs/
docs/implementation/irs-v6/
```

如果测试需要补充 shared fake checker，可继续放在：

```text
tests/unit/compiler/irs/test_r3_diagnostic_projector.py
```

或追加到：

```text
tests/unit/compiler/irs/test_r2_framework_skeleton.py
```

推荐新增独立文件：

```text
tests/unit/compiler/irs/test_r3_diagnostic_projector.py
```

R3 可以读取但不应修改：

```text
src/nl2spl/compiler/construct_registry.py
src/nl2spl/compiler/diagnostic_registry.py
src/nl2spl/ir/diagnostics.py
```

如果发现 `DiagnosticRegistry` 缺少 R3 必需字段，必须先暂停并说明；不要在 R3 中扩展 registry schema，除非该扩展已被明确批准。

## 4. 禁止修改范围

R3 不允许修改：

```text
src/nl2spl/pipeline/orchestrator.py
src/nl2spl/pipeline/stages/stage4_flow_assembler/irs_checker.py
src/nl2spl/pipeline/stages/stage7_step_extractor/irs_checker.py
src/nl2spl/pipeline/stages/stage9_5_normalizer/final_irs_checker.py
src/nl2spl/pipeline/executable_gate.py
src/nl2spl/config.py
prompts/
examples/
output/
```

R3 不新增 feature flag。`DiagnosticProjector` 是 `IRSRunner` 内部组件；由于 R3 仍不接入 orchestrator，不需要 pipeline 开关。

## 5. LLM / Rule-based 决策约束

R3 不需要语义理解。

禁止事项：

```text
1. 不新增 LLM 调用。
2. 不新增自然语言语义分类规则。
3. 不根据 span text 推断 diagnostic_kind。
4. 不根据 construct_type 自动判断缺什么 slot。
5. 不根据 report.completeness 自动制造 diagnostic。
6. 不新增 Worker/Delegation promotion 判断。
7. 不补全 source evidence。
```

R3 只接受 checker 已经写入的 `slot.diagnostic_kind`。如果没有 `diagnostic_kind`，projector 不生成 diagnostic。

如果实施时认为需要“根据文本内容判断 diagnostic kind”，必须暂停并确认实现方式；该逻辑通常应属于 checker，而不是 projector。

## 6. 目标行为设计

### 6.1 DiagnosticProjector 初始化

建议接口：

```python
class DiagnosticProjector:
    def __init__(
        self,
        diagnostic_registry: DiagnosticRegistry | None = None,
    ) -> None:
        self._diagnostic_registry = diagnostic_registry or DiagnosticRegistry.default()
```

要求：

```text
1. 默认使用 DiagnosticRegistry.default()。
2. 测试可以注入自定义 DiagnosticRegistry。
3. Projector 仍保持 stateless，不在实例上累计 projected diagnostics。
```

### 6.2 Project 输入输出

保持 R2 接口：

```python
def project(
    self,
    reports: list[ConstructSatisfactionReport],
    context: IRSCheckContext,
) -> DiagnosticProjectionResult:
```

输出：

```python
@dataclass
class DiagnosticProjectionResult:
    diagnostics: list[CompileDiagnostic] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
```

### 6.3 投影触发规则

Projector 只处理：

```text
for report in reports:
    for slot in report.slots:
        if slot.diagnostic_kind:
            project slot diagnostic
```

不处理：

```text
1. status=missing 但 diagnostic_kind=None 的 slot。
2. report.completeness=partial 但没有 diagnostic_kind 的 report。
3. report.renderable=False 但没有 diagnostic_kind 的 report。
4. report.diagnostics 中的 legacy diagnostic 对象。
```

第 4 点的原因：R3 目标是让新 v6 checker 使用 projector，不迁移旧 checker 的 legacy `report.diagnostics` 语义。旧路径迁移属于 R6/R7。

### 6.4 DiagnosticRegistry 使用规则

对每个 `slot.diagnostic_kind`：

```text
1. 如果 DiagnosticRegistry.has(kind)=False:
       warning + skip
2. 如果 DiagnosticSpec.enabled=False:
       warning + skip
3. 否则生成 CompileDiagnostic
```

生成字段：

```python
CompileDiagnostic(
    diagnostic_id=...,
    kind=kind,
    severity=spec.default_severity,
    message=...,
    target_ref=...,
    source_span_ids=...,
    suggested_resolution=...,
    blocks_rendering=...,
    blocks_completion=spec.blocks_completion,
)
```

### 6.5 target_ref 规则

R3 不根据 construct_type 做语义映射。为了避免 projector 解释 construct 类型，target_ref 使用：

```text
target_ref = report.construct_id
```

要求：

```text
1. 如果 report.construct_id 已经是 "step:st_1"，保持原样。
2. 如果 report.construct_id 是 "worker_candidate_1"，也保持原样。
3. Projector 不自动添加 "step:" / "worker:" / "exception_flow:" 前缀。
```

这保证 target_ref 是 checker/report 的责任，而不是 projector 的语义判断。

### 6.6 source evidence 合并规则

source_span_ids：

```text
slot.source_span_ids 优先。
如果 slot.source_span_ids 为空，则使用 report.source_span_ids。
如果二者都为空，则 []。
```

source_section_id / source_packet_id：

```text
slot.source_section_id 优先，否则 report.source_section_id。
slot.source_packet_id 优先，否则 report.source_packet_id。
```

由于 `CompileDiagnostic` 目前没有 `source_section_id` / `source_packet_id` 字段，R3 不修改 `CompileDiagnostic` schema。建议将这两个值写入 `suggested_resolution` 或 message 会污染用户文案，因此 R3 更稳的选择是：

```text
1. source_span_ids 写入 CompileDiagnostic.source_span_ids。
2. source_section_id / source_packet_id 暂不写入 CompileDiagnostic。
3. 在 DiagnosticProjectionResult.warnings 中不要因为 section/packet 缺失而报 warning。
```

如果后续需要结构化 section/packet provenance，应在单独阶段扩展 `CompileDiagnostic` 或 diagnostic metadata 字段，不在 R3 临时塞入字符串。

### 6.7 message 规则

消息生成顺序：

```text
1. 如果 slot.explanation 非空，优先使用 slot.explanation。
2. 否则使用 DiagnosticSpec.description。
3. message 应包含 construct_id 和 slot_name 的简短上下文。
```

建议格式：

```text
{spec.description} [construct={report.construct_id}, slot={slot.slot_name}]
```

如果使用 slot.explanation：

```text
{slot.explanation} [construct={report.construct_id}, slot={slot.slot_name}]
```

禁止：

```text
1. 根据 source span text 生成解释。
2. 根据 construct_type 写特殊模板。
3. 在 R3 中引入大段 report renderer 文案。
```

### 6.8 blocks_rendering 规则

R3 使用 report 的 generic renderability 状态：

```text
blocks_rendering = not report.renderable
```

理由：

```text
1. DiagnosticRegistry 只有 blocks_completion，没有 blocks_rendering。
2. report.renderable 是 checker 已裁决的 construct-level renderability。
3. Projector 不重新解释 slot 是否阻塞渲染。
```

例子：

```text
EXCEPTION_FLOW condition-only:
    report.renderable=True
    missing_handler -> blocks_rendering=False, blocks_completion=True

GENERAL_COMMAND no source evidence:
    report.renderable=False
    assumed_command_not_renderable -> blocks_rendering=True, blocks_completion=True
```

### 6.9 deterministic diagnostic_id

R3 必须避免递增全局状态。

建议使用稳定 digest：

```python
key = (
    kind,
    report.construct_id,
    slot.slot_name,
    tuple(sorted(source_span_ids)),
)
diagnostic_id = "irs_" + sha1(json.dumps(key, sort_keys=True).encode()).hexdigest()[:12]
```

要求：

```text
1. 同一输入多次 project 生成相同 diagnostic_id。
2. source_span_ids 顺序不同但集合相同时 diagnostic_id 相同。
3. kind / target / slot 不同则 diagnostic_id 不同。
4. 不使用 Python 内置 hash()。
```

### 6.10 dedup 规则

Projector 内部 dedup key：

```python
dedup_key = (
    kind,
    report.construct_id,
    slot.slot_name,
    tuple(sorted(source_span_ids)),
)
```

行为：

```text
1. 同一 report/slot/kind/source 只生成一个 diagnostic。
2. 不同 source_span_ids 应保留为不同 diagnostic。
3. 不同 slot_name 应保留为不同 diagnostic。
4. 不同 construct_id 应保留为不同 diagnostic。
```

R3 只做 projector 内部去重，不替代 orchestrator 级 diagnostic consolidation。

## 7. Runner 对接要求

R2 runner 已调用 projector。R3 只需要确保：

```text
1. runner 使用的默认 projector 具备 R3 投影能力。
2. runner 仍允许测试注入自定义 projector。
3. projector warnings 仍合并到 IRSRunResult.warnings。
4. runner 不理解 diagnostic spec，不拼装 CompileDiagnostic。
```

如果 R2 runner 当前 `projector=None` 时不投影，R3 可以保持该行为。是否让 runner 默认创建 `DiagnosticProjector()` 由实施者判断，但必须满足：

```text
IRSRunner(registry, construct_registry, projector=DiagnosticProjector())
```

可以产生 diagnostics。

R3 不要求 runner 在未显式传 projector 时自动投影，因为 R5 接入 orchestrator 时可以明确传入默认 projector。

## 8. 测试计划

建议新增：

```text
tests/unit/compiler/irs/test_r3_diagnostic_projector.py
```

### 8.1 Basic projection tests

建议测试：

```text
test_projector_projects_slot_diagnostic_kind
test_projector_uses_diagnostic_registry_defaults
test_projector_uses_slot_explanation_before_spec_description
test_projector_uses_report_construct_id_as_target_ref
```

验收点：

```text
1. slot.diagnostic_kind="missing_handler" 生成 CompileDiagnostic。
2. severity 来自 DiagnosticRegistry。
3. blocks_completion 来自 DiagnosticRegistry。
4. target_ref == report.construct_id。
5. message 包含 construct_id 与 slot_name。
```

### 8.2 Source evidence tests

建议测试：

```text
test_projector_uses_slot_source_spans_before_report_source_spans
test_projector_falls_back_to_report_source_spans
test_projector_allows_empty_source_spans
```

验收点：

```text
1. slot.source_span_ids 非空时优先。
2. slot.source_span_ids 为空时使用 report.source_span_ids。
3. 二者都为空时 diagnostic.source_span_ids == []。
```

### 8.3 Unknown / disabled kind tests

建议测试：

```text
test_projector_warns_and_skips_unknown_diagnostic_kind
test_projector_warns_and_skips_disabled_diagnostic_kind
```

验收点：

```text
1. unknown kind 不生成 CompileDiagnostic。
2. disabled kind 不生成 CompileDiagnostic。
3. warnings 包含 kind 与 reason。
```

### 8.4 Determinism / dedup tests

建议测试：

```text
test_projector_diagnostic_id_is_deterministic
test_projector_diagnostic_id_ignores_source_span_order
test_projector_deduplicates_same_kind_target_slot_source
test_projector_keeps_different_slots_separate
test_projector_keeps_different_sources_separate
```

验收点：

```text
1. 同一输入两次 project，diagnostic_id 相同。
2. ["s1", "s2"] 与 ["s2", "s1"] 生成同一 id。
3. 完全相同 key 去重。
4. 不同 slot/source 不被误删。
```

### 8.5 Blocks rendering tests

建议测试：

```text
test_projector_blocks_rendering_when_report_not_renderable
test_projector_does_not_block_rendering_when_report_renderable
```

验收点：

```text
1. report.renderable=False -> diagnostic.blocks_rendering=True。
2. report.renderable=True -> diagnostic.blocks_rendering=False。
3. diagnostic.blocks_completion 仍来自 DiagnosticRegistry。
```

### 8.6 Runner integration tests

建议测试：

```text
test_runner_with_projector_returns_projected_diagnostics
test_runner_projector_warning_is_preserved
test_runner_without_projector_preserves_r2_no_diagnostic_behavior
```

验收点：

```text
1. fake checker 返回含 diagnostic_kind 的 report。
2. runner + DiagnosticProjector 产生 CompileDiagnostic。
3. runner 不自己拼 diagnostic。
4. projector warning 合并到 IRSRunResult.warnings。
5. 不传 projector 时仍保持 R2 行为。
```

### 8.7 No semantic logic tests

建议测试：

```text
test_projector_does_not_create_diagnostic_without_diagnostic_kind
test_projector_does_not_infer_from_missing_slot_status
test_projector_does_not_infer_from_report_completeness
```

验收点：

```text
1. status="missing" 但 diagnostic_kind=None -> no diagnostic。
2. report.completeness="partial" 但 no diagnostic_kind -> no diagnostic。
3. report.renderable=False 但 no diagnostic_kind -> no diagnostic。
```

## 9. 测试命令

R3 提交审核时至少提供：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/compiler/irs/test_r3_diagnostic_projector.py -q
.\.venv\Scripts\python.exe -m pytest tests/unit/test_irs_v6_r0_baseline.py tests/unit/test_irs_v6_r1_report_schema.py tests/unit/compiler/irs/test_r2_framework_skeleton.py tests/unit/compiler/irs/test_r3_diagnostic_projector.py -q
.\.venv\Scripts\python.exe -m pytest tests/unit/ -q --basetemp=.pytest-tmp-r3
```

如果 R3 tests 被追加到 R2 文件，请相应替换测试路径。

## 10. 审核清单

审核时我会逐条核验：

```text
1. 是否只修改 R3 允许范围内文件。
2. 是否没有修改 orchestrator。
3. 是否没有修改 Stage 4 / Stage 7 / Post-normalize checker。
4. 是否没有修改 config / prompts / examples / output。
5. 是否没有新增 LLM 调用。
6. 是否没有新增 rule-based NL 语义判断。
7. Projector 是否只处理 slot.diagnostic_kind。
8. Projector 是否不根据 missing status / completeness / renderable 自动制造 diagnostic。
9. severity / blocks_completion 是否来自 DiagnosticRegistry。
10. blocks_rendering 是否来自 report.renderable。
11. target_ref 是否保持 report.construct_id。
12. source_span_ids 是否按 slot -> report fallback。
13. unknown / disabled diagnostic kind 是否 warning + skip。
14. diagnostic_id 是否 deterministic。
15. dedup 是否只在 projector 内部生效。
16. runner 是否仍只做调度，不理解 diagnostic spec。
17. R0/R1/R2/R3 阶段测试是否通过。
18. 全量单元测试是否通过。
```

## 11. 提交审核时需要填写的信息

实施者提交 R3 审核时，请提供：

```text
1. 修改文件列表。
2. DiagnosticProjector 行为说明。
3. DiagnosticRegistry 使用方式。
4. diagnostic_id 生成规则。
5. dedup key 规则。
6. source evidence fallback 规则。
7. unknown / disabled kind 处理方式。
8. runner 对接说明。
9. 测试命令与结果。
10. 是否修改 orchestrator：必须为否。
11. 是否修改 Stage 4 / Stage 7 / Post-normalize checker：必须为否。
12. 是否新增 LLM/rule-based 语义逻辑：必须为否。
13. 已知风险。
14. 后续 R4/R5 依赖事项。
```

## 12. R3 完成标准

R3 完成必须满足：

```text
1. DiagnosticProjector 能从 slot.diagnostic_kind 生成 CompileDiagnostic。
2. DiagnosticProjector 使用 DiagnosticRegistry.default() 或注入 registry。
3. severity / blocks_completion 来自 DiagnosticRegistry。
4. blocks_rendering 来自 report.renderable。
5. target_ref == report.construct_id。
6. source_span_ids 使用 slot 优先、report fallback。
7. unknown diagnostic kind warning + skip。
8. disabled diagnostic kind warning + skip。
9. diagnostic_id deterministic。
10. duplicate projection 被去重。
11. 不根据 missing status / completeness / renderable 自动制造 diagnostic。
12. Runner + DiagnosticProjector 能返回 projected diagnostics。
13. Runner 不传 projector 时保持 R2 行为。
14. 没有 orchestrator 接入。
15. 没有旧 checker 迁移。
16. 没有 Worker/Delegation checker。
17. 没有新增 LLM 或 rule-based 语义判断。
18. R0/R1/R2/R3 测试通过。
19. 全量单元测试通过。
20. 进度跟踪 HTML 的 R3 区块已填写。
```

## 13. 后续阶段衔接

R3 为 R4/R5 提供 diagnostic 投影能力：

```text
R4 Worker/Delegation Checker:
    checker 只需要在 SlotSatisfaction 上写 diagnostic_kind。
    projector 统一生成 CompileDiagnostic。

R5 Runner Orchestrator Integration:
    orchestrator 只接收 IRSRunResult.diagnostics。
    不需要知道 diagnostic spec 细节。
```

R3 仍不解决 internal-comms-3 Issue 3。Issue 3 的实际 Worker/Delegation explanation 应由 R4 checker 产生 reports，再由 R3 projector 投影 diagnostics，最终由 R5 接入 pipeline。

