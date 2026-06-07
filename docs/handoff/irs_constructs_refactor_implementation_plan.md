# IRS / Constructs 代码组织重构实施文档

**文档状态**: Draft for staged execution  
**目标**: 多阶段、可验收、低风险地重构 IRS / Constructs 代码组织  
**核心约束**: 前六个阶段原则上不改变编译行为；所有 import-path 变更必须有 shim；每阶段可单独回滚。

---

## 1. 实施总览

本实施计划将重构拆为 8 个阶段：

| Phase | 名称 | 行为变化 | 风险等级 |
|---|---|---:|---:|
| Phase 0 | Baseline freeze and import smoke tests | 否 | 低 |
| Phase 1 | 建立 `constructs/` 并移动 construct domain types | 否 | 中 |
| Phase 2 | 更新跨层 imports，消除 `constructs -> irs` | 否 | 中-高 |
| Phase 3 | 建立 `diagnostics/` | 否 | 中 |
| Phase 4 | 拆分 `irs_prompt_builder.py` | 否 | 中 |
| Phase 5 | 建立 `reporting/` 并移动 feedback renderer | 否 | 中 |
| Phase 6 | 收缩 `irs/__init__.py` 与 legacy re-export | 否 | 中-高 |
| Phase 7 | 拆分大型 IRS checkers | 否，除非发现 bug | 高 |
| Phase 8 | 清理、文档、验收与后续移除 shim 计划 | 否 | 低 |

执行原则：

1. 每个 Phase 单独提交。
2. 每个 Phase 结束后跑测试与 import smoke tests。
3. 任何行为变化必须单独记录，不得混入结构性重构提交。
4. shim 优先保留，减少一次性破坏。
5. 大文件拆分时先做 mechanical extraction，再做逻辑优化。

---

## 2. Phase 0 — Baseline freeze and import smoke tests

### 2.1 目标

在开始文件移动前建立行为基线，避免后续重构无法判断是否引入行为变化。

### 2.2 任务

1. 跑当前全量测试：

```bash
pytest
```

2. 跑 IRS / construct 相关测试：

```bash
pytest tests -k "irs or construct or diagnostic or report"
```

3. 新增 import smoke tests：

```python
# tests/test_irs_constructs_import_smoke.py

def test_import_legacy_construct_registry():
    import nl2spl.compiler.construct_registry as m
    assert hasattr(m, "ConstructIRS")
    assert hasattr(m, "SPLConstructRegistry")


def test_import_legacy_irs_graph_frontier():
    from nl2spl.compiler.irs.graph import ConstructEdge, ConstructGraph
    from nl2spl.compiler.irs.frontier import FrontierStatus, CutlineReason
    assert ConstructEdge is not None
    assert ConstructGraph is not None
    assert FrontierStatus is not None
    assert CutlineReason is not None


def test_import_irs_public_api():
    import nl2spl.compiler.irs as irs
    assert irs is not None


def test_import_construct_plan_model():
    import nl2spl.compiler.construct_plan.model as model
    assert hasattr(model, "ConstructPlan")


def test_import_report_renderer():
    import nl2spl.compiler.report_renderer as renderer
    assert hasattr(renderer, "render_report")
```

4. 如果仓库已有 CLI / golden report 测试，保存当前输出快照。

### 2.3 验收标准

- 全量测试通过。
- 新增 import smoke tests 通过。
- 当前 report / diagnostic snapshot 被记录。

### 2.4 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| 当前 main 本身已有失败测试 | 无法判断重构影响 | 记录 baseline failure，后续只比较新增失败 |
| 没有稳定 golden snapshot | 行为漂移难发现 | 至少保存核心场景输出文本 |

---

## 3. Phase 1 — 建立 `constructs/` 并移动 construct domain types

### 3.1 目标

创建 `compiler.constructs` 包，将 construct static spec、satisfaction report、graph schema、registry 和 defaults 从旧位置拆出。

### 3.2 文件变更

新增：

```text
src/nl2spl/compiler/constructs/__init__.py
src/nl2spl/compiler/constructs/spec.py
src/nl2spl/compiler/constructs/satisfaction.py
src/nl2spl/compiler/constructs/graph.py
src/nl2spl/compiler/constructs/registry.py
src/nl2spl/compiler/constructs/defaults.py
src/nl2spl/compiler/constructs/definitions/__init__.py
```

移动/拆分：

```text
compiler/construct_registry.py
  → constructs/spec.py
  → constructs/satisfaction.py
  → constructs/registry.py
  → constructs/defaults.py

compiler/irs/graph.py
  → constructs/graph.py

compiler/irs/frontier.py
  → constructs/satisfaction.py 或 constructs/frontier.py
```

建议 `frontier` 类型放入 `constructs/satisfaction.py`：

```python
FrontierStatus
CutlineReason
```

因为它们是 `ConstructSatisfactionReport` 的字段。

### 3.3 `constructs/__init__.py` 建议导出

```python
from .spec import ConstructIRS, SlotSpec
from .satisfaction import (
    SlotSatisfaction,
    ConstructSatisfactionReport,
    ConstructCompleteness,
    FrontierStatus,
    CutlineReason,
)
from .graph import ConstructEdge, ConstructGraph, ConstructEdgeType
from .registry import SPLConstructRegistry
from .defaults import build_default_construct_registry

__all__ = [
    "ConstructIRS",
    "SlotSpec",
    "SlotSatisfaction",
    "ConstructSatisfactionReport",
    "ConstructCompleteness",
    "FrontierStatus",
    "CutlineReason",
    "ConstructEdge",
    "ConstructGraph",
    "ConstructEdgeType",
    "SPLConstructRegistry",
    "build_default_construct_registry",
]
```

### 3.4 Compatibility shims

保留：

```python
# src/nl2spl/compiler/construct_registry.py
from nl2spl.compiler.constructs import *
```

```python
# src/nl2spl/compiler/irs/graph.py
from nl2spl.compiler.constructs.graph import *
```

```python
# src/nl2spl/compiler/irs/frontier.py
from nl2spl.compiler.constructs.satisfaction import CutlineReason, FrontierStatus

__all__ = ["CutlineReason", "FrontierStatus"]
```

### 3.5 验收标准

- 原有旧 import path 仍可用。
- 新 import path 可用。
- `constructs/*` 不 import `irs/*`。
- `pytest tests/test_irs_constructs_import_smoke.py` 通过。
- 全量测试通过，或仅有 baseline 已知失败。

### 3.6 验收命令

```bash
python - <<'PY'
from nl2spl.compiler.constructs import ConstructIRS, SPLConstructRegistry
from nl2spl.compiler.constructs.graph import ConstructEdge, ConstructGraph
from nl2spl.compiler.constructs.satisfaction import ConstructSatisfactionReport
from nl2spl.compiler.construct_registry import ConstructIRS as LegacyConstructIRS
from nl2spl.compiler.irs.graph import ConstructEdge as LegacyEdge
print("ok")
PY

# constructs 不得依赖 irs
grep -R "nl2spl.compiler.irs" src/nl2spl/compiler/constructs || true
```

预期：第二条 grep 结果为空。

### 3.7 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| dataclass type identity 因 shim 变成两个不同类 | isinstance / equality 出错 | shim 必须 re-export 同一对象，不复制定义 |
| circular import 新增 | import 失败 | Phase 0 smoke tests 必须覆盖 |
| default registry 拆分后遗漏 construct | IRS checker 找不到 construct | `SPLConstructRegistry.default().list_constructs()` snapshot 测试 |

---

## 4. Phase 2 — 更新跨层 imports，消除 `constructs -> irs`

### 4.1 目标

把源代码中的旧路径改为新路径，同时保留 shim 供测试与外部兼容。

### 4.2 需要更新的路径

```text
nl2spl.compiler.construct_registry
  → nl2spl.compiler.constructs

nl2spl.compiler.irs.graph
  → nl2spl.compiler.constructs.graph

nl2spl.compiler.irs.frontier
  → nl2spl.compiler.constructs.satisfaction
```

### 4.3 重点文件

必须覆盖：

```text
construct_plan/model.py
construct_plan/planner.py
irs/checker.py
irs/runner.py
irs/subsystem.py
irs/factory.py
irs/projector.py
irs/result_store.py
irs/checkers/exception_flow.py
irs/checkers/step.py
irs/checkers/worker_delegation.py
irs/checkers/post_normalize.py
pipeline/stages/stage4_flow_assembler/irs_checker.py
pipeline/stages/stage7_step_extractor/irs_checker.py
compiler/report_renderer.py
compiler/irs_prompt_builder.py
tests/*
```

### 4.4 任务

1. 批量替换 imports。
2. 保留旧 shim 文件。
3. 调整 lint / type check。
4. 补一个防回归测试：

```python
def test_constructs_package_does_not_import_irs():
    import pkgutil
    import nl2spl.compiler.constructs as constructs
    # 这里可做静态 grep，也可用 import graph 工具后续增强
```

更直接的方式是 CI grep：

```bash
! grep -R "nl2spl.compiler.irs" src/nl2spl/compiler/constructs
```

### 4.5 验收标准

```bash
grep -R "nl2spl.compiler.irs.graph" src tests
```

除 `src/nl2spl/compiler/irs/graph.py` shim 外无结果。

```bash
grep -R "nl2spl.compiler.irs.frontier" src tests
```

除 `src/nl2spl/compiler/irs/frontier.py` shim 外无结果。

```bash
grep -R "nl2spl.compiler.construct_registry" src tests
```

除 shim 与明确的 backward compatibility 测试外无结果。

### 4.6 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| 批量替换误改注释或字符串 snapshot | Snapshot 测试失败 | 分代码与 docs 两步替换 |
| pipeline stage checker import 漏掉 | 局部运行失败 | import smoke + targeted pytest |
| tests 仍依赖旧路径 | 不一定是错误 | 允许 legacy import 测试保留，但新测试应使用新路径 |

---

## 5. Phase 3 — 建立 `diagnostics/`

### 5.1 目标

将 `diagnostic_registry.py` 从 compiler 顶层移动到 `compiler.diagnostics`，但不放入 `constructs`。

### 5.2 文件变更

新增：

```text
src/nl2spl/compiler/diagnostics/__init__.py
src/nl2spl/compiler/diagnostics/spec.py
src/nl2spl/compiler/diagnostics/registry.py
src/nl2spl/compiler/diagnostics/defaults.py
src/nl2spl/compiler/diagnostics/kinds.py
```

保留 shim：

```python
# src/nl2spl/compiler/diagnostic_registry.py
from nl2spl.compiler.diagnostics import *
```

### 5.3 更新 imports

```text
irs/projector.py
compiler/__init__.py
tests/*
```

从：

```python
from nl2spl.compiler.diagnostic_registry import DiagnosticRegistry
```

改为：

```python
from nl2spl.compiler.diagnostics import DiagnosticRegistry
```

### 5.4 验收标准

- 新旧 import path 均可用。
- `diagnostics/*` 不 import `irs/*`。
- `diagnostics/*` 不 import `constructs/*`，除非未来确有必要。
- `irs/projector.py` 使用新路径。
- diagnostic list snapshot 不变。

### 5.5 验收命令

```bash
python - <<'PY'
from nl2spl.compiler.diagnostics import DiagnosticRegistry
from nl2spl.compiler.diagnostic_registry import DiagnosticRegistry as Legacy
r = DiagnosticRegistry.default()
print(r.list_kinds())
assert DiagnosticRegistry is Legacy
PY

! grep -R "nl2spl.compiler.irs" src/nl2spl/compiler/diagnostics
```

### 5.6 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| DiagnosticRegistry.default 拆分遗漏 enabled/reserved kind | diagnostics 投影异常 | 增加 list_kinds snapshot 测试 |
| projector 找不到 registry | IRS diagnostics 缺失 | targeted test `irs/projector.py` |
| 误放入 constructs 导致 domain 污染 | 后续扩展困难 | 明确建立 diagnostics sibling package |

---

## 6. Phase 4 — 拆分 `irs_prompt_builder.py`

### 6.1 目标

把 construct checklist renderer 与 stage-specific prompt policy 分离。

### 6.2 文件变更

新增：

```text
src/nl2spl/compiler/constructs/prompt_builder.py
src/nl2spl/pipeline/stage_prompt_profiles.py
```

保留 shim：

```text
src/nl2spl/compiler/irs_prompt_builder.py
```

### 6.3 拆分规则

`constructs/prompt_builder.py` 只保留：

```python
class ConstructPromptBuilder:
    def render_construct_checklist(self, irs: ConstructIRS) -> str: ...
```

不要包含：

```text
_STAGE_CONSTRUCT_MAP
_STAGE_NOTES
stage3_5 / stage4 / stage7 specific rules
```

这些进入：

```python
# pipeline/stage_prompt_profiles.py
STAGE_CONSTRUCT_MAP = {...}
STAGE_NOTES = {...}
```

兼容 wrapper：

```python
# compiler/irs_prompt_builder.py
from nl2spl.compiler.constructs import SPLConstructRegistry
from nl2spl.compiler.constructs.prompt_builder import ConstructPromptBuilder
from nl2spl.pipeline.stage_prompt_profiles import STAGE_CONSTRUCT_MAP, STAGE_NOTES

class IRSDrivenPromptBuilder:
    ...  # wrapper around ConstructPromptBuilder + stage profiles
```

### 6.4 验收标准

- `irs_checklist_for_stage("stage4")` 输出与重构前一致。
- `irs_checklist_for_stage("stage7")` 输出与重构前一致。
- `constructs/prompt_builder.py` 不 import `pipeline`。
- pipeline stage profile 可以 import constructs。

### 6.5 测试建议

新增 snapshot test：

```python
def test_stage4_irs_prompt_snapshot():
    from nl2spl.compiler.irs_prompt_builder import irs_checklist_for_stage
    text = irs_checklist_for_stage("stage4")
    assert "EXCEPTION_FLOW" in text
    assert "No failure signal" in text
```

以及新 API test：

```python
def test_construct_prompt_builder_has_no_stage_policy():
    from nl2spl.compiler.constructs.prompt_builder import ConstructPromptBuilder
    assert ConstructPromptBuilder is not None
```

### 6.6 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| prompt 文本变化导致 LLM 输出变化 | E2E 行为漂移 | snapshot 对比，机械拆分不改文本 |
| constructs 反向依赖 pipeline | 再次形成分层污染 | grep 检查 |
| stage notes 漏迁移 | Stage prompt 缺关键规则 | stage4/stage7 snapshot test |

---

## 7. Phase 5 — 建立 `reporting/` 并移动 feedback renderer

### 7.1 目标

把 human-readable rendering 从 `irs/` 移出，建立 reporting layer。

### 7.2 文件变更

新增：

```text
src/nl2spl/compiler/reporting/__init__.py
src/nl2spl/compiler/reporting/report_renderer.py
src/nl2spl/compiler/reporting/construct_satisfaction_renderer.py
```

移动：

```text
irs/feedback_projector.py
  → reporting/construct_satisfaction_renderer.py

report_renderer.py
  → reporting/report_renderer.py
```

保留 shim：

```python
# compiler/report_renderer.py
from nl2spl.compiler.reporting.report_renderer import *
```

可选保留：

```python
# compiler/irs/feedback_projector.py
from nl2spl.compiler.reporting.construct_satisfaction_renderer import *
```

该 shim 只为兼容旧测试，不应被新代码使用。

### 7.3 更新 imports

```text
compiler/report_renderer.py
pipeline / CLI 调用 render_report 的位置
tests/*
```

### 7.4 验收标准

- `render_report(...)` 输出与迁移前一致。
- `reporting/*` 可以依赖 constructs / diagnostics。
- `irs/*` 不再包含真实 human-readable renderer。
- `report_renderer.py` 不再 import `irs.feedback_projector`。

### 7.5 测试建议

```python
def test_legacy_report_renderer_import():
    from nl2spl.compiler.report_renderer import render_report
    assert render_report is not None


def test_new_report_renderer_import():
    from nl2spl.compiler.reporting.report_renderer import render_report
    assert render_report is not None


def test_report_renderer_output_stable(snapshot):
    # 使用一个最小 SPL + diagnostic + construct_satisfaction fixture
    ...
```

### 7.6 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| report snapshot 变化 | 用户可见输出变化 | 保持代码原样移动，不重排文本 |
| CLI 仍 import 旧 path | 可通过 shim 工作，但不彻底 | Phase 5 后 grep 新代码旧 import |
| IRS package 仍 re-export feedback projector | 分层不干净 | 新代码禁止 import `irs.feedback_projector` |

---

## 8. Phase 6 — 收缩 `irs/__init__.py`

### 8.1 目标

在 construct / diagnostics / reporting 分层稳定后，减少 `irs/__init__.py` 的 lazy import hack。

### 8.2 任务

1. 检查 `irs/__init__.py` 当前 re-export 项。
2. 保留必要 public API。
3. 移除因 `construct_registry -> irs` 循环而存在的 lazy workaround。
4. 如果保留 `__getattr__`，必须明确其用途是 public API convenience，而不是 circular import workaround。

### 8.3 验收标准

- `import nl2spl.compiler.irs` 成功。
- `from nl2spl.compiler.irs import IRSSubsystem` 成功，如果这是既有 public API。
- `constructs/*` 仍不 import `irs/*`。
- 删除或减少 lazy import 后不引入 circular import。

### 8.4 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| 外部代码依赖 `irs.__init__` re-export | import break | 保留 public API 或 shim |
| 删除 lazy import 后暴露隐藏循环 | import 失败 | Phase 0 smoke tests 扩展覆盖 |
| 一次性修改过多 public API | 难回滚 | 只调整内部明显无用 re-export |

---

## 9. Phase 7 — 拆分大型 IRS checkers

### 9.1 目标

收缩大型 checker 文件，优先拆分 `PostNormalizeIRSCheckerV6`，其次拆分 `Stage7StepIRSChecker`。

### 9.2 原则

1. 第一轮只做 mechanical split。
2. 不改变 slot 判断逻辑。
3. 不改变 diagnostic id 生成逻辑。
4. 不改变 `ConstructSatisfactionReport` 字段。
5. 不改变 `supported_construct_types` 的语义。

### 9.3 Phase 7A — 拆 `post_normalize.py`

目标结构：

```text
irs/checkers/post_normalize/
  __init__.py
  checker.py
  extract_instances.py
  exception_flow.py
  required_output.py
  general_command.py
  request_input.py
  call_api.py
  invoke_worker.py
```

职责划分：

| 文件 | 职责 |
|---|---|
| `checker.py` | class `PostNormalizeIRSCheckerV6`; dispatch only |
| `extract_instances.py` | 从 `WorkerIR` / `WorkerPlanIR` 抽取 `ConstructInstance` |
| `exception_flow.py` | `_check_exception_flow` 逻辑 |
| `required_output.py` | `_check_required_output` + ProducerIndex 接入 |
| `general_command.py` | general command source evidence 检查 |
| `request_input.py` | request input prompt/value slot 检查 |
| `call_api.py` | API call integration/call evidence 检查 |
| `invoke_worker.py` | worker invocation/handoff 检查 |

保留 shim：

```python
# irs/checkers/post_normalize.py
from nl2spl.compiler.irs.checkers.post_normalize.checker import PostNormalizeIRSCheckerV6
```

### 9.4 Phase 7B — 拆 `step.py`

目标结构：

```text
irs/checkers/steps/
  __init__.py
  checker.py
  general_command.py
  request_input.py
  call_api.py
  invoke_worker.py
```

保留 shim：

```python
# irs/checkers/step.py
from nl2spl.compiler.irs.checkers.steps.checker import Stage7StepIRSChecker
```

### 9.5 验收标准

- checker public class name 不变。
- `IRSCheckerRegistry` 注册行为不变。
- 每个 construct type 的 satisfaction report snapshot 不变。
- `PostNormalizeIRSCheckerV6.supported_construct_types` 不变。
- `Stage7StepIRSChecker.supported_construct_types` 不变。

### 9.6 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| 拆分时共享 helper 漏迁移 | 局部 checker 失败 | 先抽 helper module，再拆 checker |
| diagnostic id 因 source span 顺序变化而变 | snapshot 失败 | 保持原排序与输入顺序 |
| ProducerIndex scope 传参错误 | required output 判断变化 | required-output golden test |
| Handoff / API 检查上下文丢失 | INVOKE/CALL 误判 | targeted tests for delegation/API |

---

## 10. Phase 8 — 清理、文档、后续 shim 退出计划

### 10.1 目标

完成文档更新、architecture decision record、dependency validation，并制定 shim removal plan。

### 10.2 任务

1. 更新架构文档。
2. 更新 import examples。
3. 增加 dependency boundary tests。
4. 增加 README / design docs 中的新 package layout。
5. 标记 legacy shim deprecated。
6. 新增 issue：后续删除 shim。

### 10.3 验收标准

- 文档描述与代码 layout 一致。
- 新代码没有使用 legacy import path。
- legacy import path 只有 shim 和 compatibility tests 使用。
- CI 增加 boundary grep 检查。

---

## 11. 全局风险评估

| 风险 | 概率 | 影响 | 等级 | 缓解 |
|---|---:|---:|---:|---|
| 循环 import 暴露 | 中 | 高 | 高 | Phase 0 import smoke + 分阶段移动 + shim |
| type identity duplication | 中 | 高 | 高 | shim re-export，不复制定义 |
| prompt 文本漂移 | 中 | 高 | 高 | Phase 4 snapshot，机械拆分不改文本 |
| report 文本漂移 | 中 | 中 | 中 | Phase 5 report snapshot |
| diagnostic kind registry 漏项 | 低-中 | 高 | 中-高 | registry list snapshot |
| checker 拆分导致语义变化 | 中 | 高 | 高 | Phase 7 targeted golden tests |
| 测试仍依赖旧路径 | 高 | 低 | 中 | shim 保留；逐步迁移 tests |
| CI 缺少边界检查 | 中 | 中 | 中 | grep-based boundary tests |
| 过早删除 `__getattr__` | 中 | 高 | 高 | Phase 6 才处理，且保留 public API |

---

## 12. 回滚策略

每个 Phase 独立提交，回滚粒度如下：

| Phase | 回滚方式 |
|---|---|
| Phase 1 | 恢复旧文件，删除 constructs package，或保持 shim 指回旧实现 |
| Phase 2 | 恢复 import path；shim 保留不影响行为 |
| Phase 3 | 恢复 `diagnostic_registry.py` 实现；diagnostics package 可暂留 |
| Phase 4 | `irs_prompt_builder.py` 恢复原实现；保留新 builder 不接入 |
| Phase 5 | `report_renderer.py` 恢复原实现；reporting package 暂不使用 |
| Phase 6 | 恢复 `irs/__init__.py` lazy import |
| Phase 7 | shim 指回原 checker 文件，或 revert checker split commit |

---

## 13. 最小测试矩阵

### 13.1 Import matrix

```text
nl2spl.compiler.constructs
nl2spl.compiler.construct_registry
nl2spl.compiler.constructs.graph
nl2spl.compiler.irs.graph
nl2spl.compiler.constructs.satisfaction
nl2spl.compiler.irs.frontier
nl2spl.compiler.diagnostics
nl2spl.compiler.diagnostic_registry
nl2spl.compiler.reporting.report_renderer
nl2spl.compiler.report_renderer
nl2spl.compiler.irs
nl2spl.compiler.construct_plan.model
```

### 13.2 Behavior matrix

至少覆盖：

1. Failure condition only → partial exception flow + missing_handler。
2. Complete failure handling → handler rendered / complete。
3. Required output without producer → missing_output_producer。
4. REQUEST_INPUT without source ask signal → not renderable / assumed_command_not_renderable。
5. CALL_API mention without executable call action → not rendered / ambiguity。
6. Complete source-backed delegation → valid INVOKE_WORKER。
7. Incomplete delegation → no executable invoke + type_or_contract_ambiguity。
8. ReportRenderer includes construct satisfaction section。
9. DiagnosticProjector maps slot diagnostic_kind through DiagnosticRegistry。
10. ConstructPlan reserved spans still exclude handler-only spans from main step extraction。

### 13.3 Boundary matrix

```bash
# No constructs -> irs
! grep -R "nl2spl.compiler.irs" src/nl2spl/compiler/constructs

# No diagnostics -> irs
! grep -R "nl2spl.compiler.irs" src/nl2spl/compiler/diagnostics

# No construct_plan -> irs.graph
! grep -R "nl2spl.compiler.irs.graph" src/nl2spl/compiler/construct_plan

# No report renderer depending on irs feedback projector
! grep -R "irs.feedback_projector" src/nl2spl/compiler/reporting src/nl2spl/compiler/report_renderer.py
```

---

## 14. 执行顺序建议

推荐严格按以下顺序执行：

```text
Phase 0  → 建 baseline
Phase 1  → 移 construct domain types + shims
Phase 2  → 更新 imports + 消除反向依赖
Phase 3  → 移 diagnostic registry
Phase 4  → 拆 prompt builder
Phase 5  → 移 reporting renderer
Phase 6  → 清理 irs/__init__.py
Phase 7A → 拆 post-normalize checker
Phase 7B → 拆 step checker
Phase 8  → 文档、CI boundary、shim removal plan
```

不要把 Phase 1、Phase 3、Phase 5 合并为一个大提交。它们都涉及 public import path，一旦合并，定位 import break 会困难。

---

## 15. 完成定义

本重构完成的判定标准：

1. 新目录结构存在并承担实际逻辑。
2. `constructs` 与 `diagnostics` 均不依赖 `irs`。
3. `construct_plan` 不再依赖 `irs.graph`。
4. `irs` 不再承载 construct static spec、diagnostic registry、human-readable reporting。
5. `reporting` 承载 report / satisfaction feedback renderer。
6. 旧 import path 通过 shim 继续可用。
7. 全量测试与核心 golden tests 通过。
8. prompt output 与 report output 无非预期变化。
9. checker 拆分后 satisfaction reports 与 diagnostics 保持稳定。
10. 文档与代码 layout 一致。

---

## 16. 后续演进建议

完成本轮结构性重构后，下一步可以再考虑：

1. 为 `construct_plan` 增加 extractor registry。
2. 将 default construct definitions 按 construct family 拆得更细。
3. 将 `DiagnosticKind` 改为更 typed 的 literal/enum，但不让 `constructs` 依赖 diagnostics。
4. 引入 import-linter 或 grimp 做依赖边界 CI。
5. 在 Phase 7 后进一步拆 `IRSCheckContext` 的 typed context。
6. 在 recursive IRS 真正落地时，把 traversal algorithm 放入 `irs/traversal.py`，不要污染 `constructs/graph.py`。
