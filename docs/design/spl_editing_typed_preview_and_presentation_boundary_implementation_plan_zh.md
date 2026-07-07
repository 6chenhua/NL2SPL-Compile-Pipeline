# Rendering Subsystem 抽离与 Typed Preview Boundary 实施计划

本文档严格基于 [`spl_editing_typed_preview_and_presentation_boundary_design_zh.md`](spl_editing_typed_preview_and_presentation_boundary_design_zh.md) 制定。实施目标是将 SPL rendering 从 NL2SPL Pipeline 与 SPL Editing backend authority 中抽离，形成独立 Rendering Subsystem；Pipeline canonical product 迁移为 `FinalIRPackage`，SPL Editing preview canonical product 迁移为 `TypedRepairPreviewArtifact`，`usage.py` / `run_demo.py` / frontend 显式调用 Rendering Subsystem 展示 SPL。

适用范围：

```text
in scope:
  - CompileResult public API additive migration
  - FinalIRPackage
  - Rendering Subsystem shell
  - Stage 11 compatibility wrapper
  - construct-level SPL renderer substrate
  - SPL Editing typed preview artifact
  - run_demo.py explicit preview rendering
  - usage.py explicit final SPL rendering
  - static and behavioral guardrails

out of scope for this plan:
  - changing SPL grammar
  - rewriting all Stage 11 internals in one step
  - changing NL2SPL stage 0-10 semantics
  - changing repair strategy semantics
  - adding LLM-based rendering
  - frontend product UI implementation
```

---

## 1. 总体目标

最终系统应形成以下职责链路：

```text
NL2SPL Pipeline core
  -> FinalIRPackage
  -> compile diagnostics / traces / assumptions / verification metadata
  -> does not own final SPL text as canonical product

SPL Editing backend
  -> TypedRepairPreviewArtifact
  -> overlay / materialization result / verification result
  -> does not own SPL preview text

Rendering Subsystem
  -> render_full_spl(FinalIRPackage)
  -> render_spl_construct(RenderableSPLConstructType, IR, context)
  -> render_repair_preview_spl(TypedRepairPreviewArtifact, context)
  -> pure, read-only, presentation-only

usage.py
  -> calls Pipeline
  -> calls Rendering Subsystem
  -> writes final_spl.txt as rendered demo artifact

run_demo.py
  -> calls SPL Editing backend
  -> calls Rendering Subsystem
  -> displays preview / updated SPL as frontend simulator
```

最终不变式：

```text
backend produces IR / typed artifacts;
rendering produces SPL / display artifacts;
apply consumes typed artifacts only.
```

---

## 2. 全局硬性原则

所有阶段必须遵守：

1. **No backend SPL authority**  
   Pipeline core、SPL Editing core/materialization/handlers/patches 不得生成 SPL-like text 作为 canonical result。

2. **Rendering is read-only**  
   Rendering Subsystem 不得 mutate IR、创建 evidence、分配 refs、写 overlay、改变 verification lane、suppress diagnostics。

3. **Rendered text is never apply authority**  
   `rendered_preview`、`spl_preview`、`spl_text`、`RenderedDocument.text` 不得参与 apply / verification / preview stale decision。

4. **Typed hashes exclude rendered output**  
   `FinalIRPackage.package_hash` 与 `TypedRepairPreviewArtifact.preview_hash` 只能基于 typed payload / metadata，不得包含 rendered text。

5. **Public API migration is additive first**  
   不得第一步删除 `CompileResult.spl_text`、Stage 11 imports、`get_patched_spl()` 或 legacy preview fields。先新增 typed API，再降级旧 API。

6. **No duplicate IR authority**  
   `FinalIRPackage` 不得同时以 canonical 形式包含 `root_worker` 与顶层 `steps` 双来源。若需要 legacy steps，只能命名为 `legacy_unscoped_steps` 并限制给 compat wrapper 使用。

7. **Compile diagnostics and render diagnostics are separate**  
   Renderer 可产生 `RenderDiagnostic`，不得产生 `CompileDiagnostic` 或改变 compile completeness。

8. **Construct renderer accepts only renderable SPL constructs**  
   `WORKER_PROMOTION`、`WORKER_CANDIDATE`、`ConstructPlan demand`、`IRS report`、`RouteAnnotation` 不得作为 SPL construct 渲染。

9. **Demo scripts are presentation orchestration only**  
   `usage.py` 与 `run_demo.py` 可以调用 rendering，不得手写替代性 SPL grammar。

10. **No new LLM or semantic fallback**  
    本计划不引入 LLM，也不新增 rule-based semantic inference。只做数据边界、renderer 抽离和 deterministic serialization/hash。

11. **Compatibility shims must have lifecycle**  
    所有 compatibility wrapper 必须注释 removal target 或 “remove after R*”。

12. **Every phase must be independently reviewable**  
    不接受 “先合入后补测试/后补 audit”。

---

## 3. LLM / Rule-Based 决策约束

本计划不允许新增 LLM prompt/schema，也不允许用关键词、标题、rendered text 反推语义。

允许的确定性逻辑仅限：

```text
- dataclass serialization / deserialization
- hash canonicalization
- immutable copy construction
- renderer dispatch by explicit enum
- compatibility wrapper delegation
- static path/token audit
- identity and stale-state equality checks
```

以下行为如实施中出现，必须暂停并重新评审：

```text
- renderer 根据文本猜 construct type
- run_demo.py 自己拼 COMMAND / USING / RESULT 语法
- SPL Editing materializer 返回 renderer text
- apply path 读取 rendered_preview
- PreviewStore 存储 rendered preview 作为 canonical preview
- FinalIRPackage 从 final_spl.txt 反向恢复 IR
```

---

## 4. Phase R0: Baseline Inventory 与 Authority Regression Locks

### 4.1 目标

锁定当前 rendering authority 泄漏点，并先建立两个最关键的行为基线：

```text
1. changing rendered_preview text does not affect apply
2. changing renderer formatting does not affect preview_hash / apply eligibility
```

本阶段不改变生产行为，只新增 inventory、characterization tests、review evidence。

### 4.2 可编辑范围

允许新增：

```text
tests/unit/rendering/
tests/integration/rendering/
tests/unit/compiler/spl_editing/preview/
artifacts/reviews/rendering_boundary/R0/
```

允许修改：

```text
docs/design/spl_editing_typed_preview_and_presentation_boundary_implementation_plan_zh.md
```

### 4.3 禁止改动

```text
src/nl2spl/pipeline/**
src/nl2spl/compiler/spl_editing/**
examples/usage.py
examples/output/spl_editing_demo/run_demo.py
```

### 4.4 设计要求

Inventory 必须列出：

```text
- CompileResult.spl_text producers and consumers
- stage11_spl_renderer imports
- final_spl.txt writers
- PreviewMaterializationResult.rendered_preview producers and consumers
- RepairSuggestion.spl_preview producers and consumers
- get_patched_spl callers
```

行为基线测试必须证明：

```text
- apply path can be made independent of rendered_preview text
- preview hash should be independent of renderer formatting
```

如果当前代码不能通过目标行为，测试应作为 pending helper 或 characterization report，不得用 skip / xfail 掩盖生产测试。

Hard gate:

```text
If current behavior cannot pass the target invariant:
  - create characterization report under artifacts/reviews/rendering_boundary/R0/
  - create helper test code only if it is not collected as a passing test
  - create an explicit TODO-linked failing target test only in the phase where production code is allowed to change
  - do not mark the invariant as satisfied in R0
```

### 4.5 测试计划

新增测试/报告：

1. `test_rendered_preview_text_is_not_apply_authority_characterization`
2. `test_renderer_formatting_is_not_preview_hash_authority_characterization`
3. `rendering_authority_inventory.md`
4. `static_scan_baseline.txt`

### 4.6 验收标准

Phase R0 通过条件：

1. Inventory 覆盖所有已知 rendering authority entry points。
2. 两个核心 baseline 行为有测试、characterization report 或未被 pytest 收集的 helper 明确记录。
3. 若当前行为尚不满足目标 invariant，R0 报告必须明确标记 `not yet satisfied`，不得假装通过。
4. 没有修改生产逻辑。
5. 无新增 skip / xfail。
6. R0 evidence bundle 包含命令输出和 inventory。

### 4.7 PM 审核清单

审核时必须检查：

1. 是否没有生产代码变更。
2. Inventory 是否包含 `CompileResult.spl_text`、`PreviewMaterializationResult.rendered_preview`、`RepairSuggestion.spl_preview`、`get_patched_spl`。
3. 是否没有把 rendered text 当作 accepted authority 的新断言。
4. 是否没有 skip / xfail。

---

## 5. Phase R1: Rendering Subsystem Shell 与 Stage 11 Compatibility Wrapper

### 5.1 目标

新增独立 `nl2spl.rendering` 包，并将现有 Stage 11 renderer 以 compatibility wrapper 方式暴露出来。此阶段不改变 pipeline output，不改变 Stage 11 行为。

### 5.2 可编辑范围

允许新增：

```text
src/nl2spl/rendering/
  __init__.py
  model.py
  context.py

src/nl2spl/rendering/spl/
  __init__.py
  stage11_compat.py
  full_document_renderer.py

tests/unit/rendering/
```

允许修改：

```text
src/nl2spl/pipeline/stages/stage11_spl_renderer/__init__.py
```

仅允许为 compat export 增加薄 wrapper，不允许重写 renderer 行为。

### 5.3 禁止改动

```text
src/nl2spl/pipeline/orchestrator.py
examples/usage.py
src/nl2spl/compiler/spl_editing/**
```

### 5.4 设计要求

新增模型：

```python
RenderedDocument
RenderedFragment
RenderDiagnostic
RenderWarning
RenderMode
```

`RenderedDocument` 必须区分：

```text
render_diagnostics
source_compile_diagnostics
```

`stage11_compat.render_full_spl_from_legacy_inputs(...)` 必须只委托现有 renderer，不改变输出。

### 5.5 测试计划

新增单元测试覆盖：

1. Rendering Subsystem importable。
2. Stage 11 compatibility wrapper 与现有 `SPLRenderer.render(...)` 输出一致。
3. `RenderedDocument` 可序列化。
4. `RenderDiagnostic` 不等同于 `CompileDiagnostic`。

### 5.6 验收标准

1. 现有 Stage 11 golden behavior 不变。
2. 新 rendering package 不依赖 SPL Editing。
3. No pipeline behavior change。
4. Ruff / targeted tests passed。

### 5.7 PM 审核清单

1. `nl2spl.rendering` 是独立包。
2. Stage 11 wrapper 是薄委托。
3. Renderer 没有新增 compiler diagnostic authority。
4. 没有修改 `usage.py` / `run_demo.py`。

---

## 6. Phase R2: FinalIRPackage 与 CompileResult Additive Migration

### 6.1 目标

新增 `FinalIRPackage`，并将其以 additive 方式暴露到 `CompileResult`。保留 `spl_text` 作为 compatibility/display-only 字段。

### 6.2 可编辑范围

允许新增：

```text
src/nl2spl/compiler/final_ir_package.py
tests/unit/compiler/test_final_ir_package.py
```

允许修改：

```text
src/nl2spl/compiler/compile_result.py
src/nl2spl/pipeline/orchestrator.py
src/nl2spl/compiler/artifacts/snapshot/**
tests/unit/compiler/
tests/integration/pipeline/
```

### 6.3 禁止改动

```text
src/nl2spl/pipeline/stages/stage0_* through stage10_*
src/nl2spl/compiler/spl_editing/**
examples/output/spl_editing_demo/run_demo.py
```

### 6.4 设计要求

`FinalIRPackage` 必须包含：

```python
package_id: str
artifact_snapshot_id: str | None
overlay_version: int | None
package_hash: str
root_worker: WorkerIR
profile: AgentProfileIR
resources: ResourceRegistryIR
symbol_table: SymbolTable
constraints: tuple[ConstraintIR, ...]
diagnostics: tuple[CompileDiagnostic, ...]
traces: tuple[TraceRecord, ...]
assumptions: tuple[CompileAssumption, ...]
verification_metadata: Mapping[str, JsonValue]
```

Rules:

```text
- package_hash excludes rendered SPL text.
- no canonical top-level steps.
- legacy_unscoped_steps allowed only if explicitly named and marked compat-only.
- spl_text remains on CompileResult but documented as display-only.
```

### 6.5 测试计划

新增/更新测试：

1. `FinalIRPackage` serialization and stable hash.
2. Hash unchanged when rendered SPL formatting changes.
3. `CompileResult.final_ir_package` exists.
4. `CompileResult.spl_text` remains backward compatible.
5. No duplicate canonical steps authority.

### 6.6 验收标准

1. Existing public API tests still pass.
2. `final_ir_package.package_hash` excludes rendered text.
3. `CompileResult.spl_text` explicitly marked compatibility/display-only in docstring.
4. Full pipeline smoke test still produces same SPL through old path.

### 6.7 PM 审核清单

1. 是否 additive migration，未删除 `spl_text`。
2. 是否未引入 canonical top-level `steps` 双 authority。
3. `package_hash` 是否 deterministic。
4. Snapshot / overlay identity 是否包含在 package。

---

## 7. Phase R3: usage.py Explicit Rendering Boundary

### 7.1 目标

让 `examples/usage.py` 显式调用 Rendering Subsystem 生成 `final_spl.txt`。Pipeline core 仍可保留 compatibility output，但 demo 路径不再把 Stage 11 视为 pipeline authority。

### 7.2 可编辑范围

允许修改：

```text
examples/usage.py
src/nl2spl/pipeline/orchestrator.py
tests/integration/pipeline/
tests/integration/examples/
```

### 7.3 禁止改动

```text
src/nl2spl/compiler/spl_editing/**
src/nl2spl/pipeline/stages/stage1_* through stage10_*
```

### 7.4 设计要求

`usage.py` target flow:

```text
result = pipeline.compile(...)
package = result.final_ir_package
rendered = rendering.render_full_spl(package)
write final_spl.txt from rendered.text
```

Compatibility:

```text
result.spl_text may still be populated.
usage.py should prefer rendered.text from Rendering Subsystem.
```

### 7.5 测试计划

1. `usage.py` still writes `examples/output/demo/final_spl.txt`.
2. Final SPL content unchanged for stable fixtures.
3. Pipeline core test can assert `final_ir_package` without reading final SPL.
4. Formatting-only render change does not affect `package_hash`.

### 7.6 验收标准

1. `usage.py` explicitly imports/calls Rendering Subsystem.
2. `final_spl.txt` remains generated.
3. No stage 0-10 behavior changes.
4. Demo output status unchanged except metadata describing SPL as rendered artifact.

### 7.7 PM 审核清单

1. `usage.py` 是否仍直接依赖 `result.spl_text` 作为主路径。
2. `final_spl.txt` 是否标注为 rendered artifact。
3. Pipeline tests 是否能不通过 SPL text 验证 core result。

---

## 8. Phase R4: Construct-Level SPL Renderer Substrate

### 8.1 目标

建立可复用的 construct-level renderer，使 repair preview 可以渲染局部 construct，而不需要伪造完整 `FinalIRPackage`。

### 8.2 可编辑范围

允许新增：

```text
src/nl2spl/rendering/spl/construct_renderer.py
src/nl2spl/rendering/spl/step_renderer.py
src/nl2spl/rendering/spl/block_renderer.py
src/nl2spl/rendering/spl/worker_renderer.py
src/nl2spl/rendering/spl/exception_flow_renderer.py
tests/unit/rendering/spl/
```

允许修改：

```text
src/nl2spl/rendering/model.py
src/nl2spl/rendering/context.py
```

### 8.3 禁止改动

```text
src/nl2spl/compiler/spl_editing/materialization/**
src/nl2spl/compiler/spl_editing/handlers/**
src/nl2spl/pipeline/stages/stage1_* through stage10_*
```

### 8.4 设计要求

新增 enum：

```python
RenderableSPLConstructType:
  AGENT
  WORKER
  FLOW
  BLOCK
  STEP
  EXCEPTION_FLOW
```

Forbidden as SPL constructs:

```text
WORKER_CANDIDATE
WORKER_PROMOTION
ConstructPlan demand
RepairResolutionMarker
IRS report
RouteAnnotation
```

Renderer must return:

```text
complete | partial | context_required
```

It must not fabricate missing context.

### 8.5 测试计划

1. Render `StepIR` command/call/request/input/invoke snippets.
2. Render `BlockIR` sequential/if snippets.
3. Render `WorkerIR` local worker snippet.
4. Return `context_required` for missing API declaration context.
5. Reject non-renderable planning constructs.
6. Renderer mutation test: input IR unchanged after render.

### 8.6 验收标准

1. Construct renderer can be used without full document context.
2. No renderer consumes `ConstructPlan` / `IRS report`.
3. No mutation of input IR.
4. No compile diagnostics created by renderer.

### 8.7 PM 审核清单

1. `construct_type` 是否为受控 enum。
2. 是否明确拒绝 `WORKER_PROMOTION` 等 analysis constructs。
3. 是否有 context_required 测试。
4. 是否有 immutability 测试。

---

## 9. Phase R5: TypedRepairPreviewArtifact 与 Preview DTO Split

### 9.1 目标

将 SPL Editing preview 的 canonical product 从 rendered string 迁移到 typed artifact。`PreviewMaterializationResult.rendered_preview` 不再是 backend canonical requirement。

### 9.2 可编辑范围

允许新增：

```text
src/nl2spl/compiler/spl_editing/preview/artifact.py
src/nl2spl/compiler/spl_editing/preview/store.py
tests/unit/compiler/spl_editing/preview/
```

允许修改：

```text
src/nl2spl/compiler/spl_editing/preview/model.py
src/nl2spl/compiler/spl_editing/preview/service.py
src/nl2spl/compiler/spl_editing/materialization/service.py
src/nl2spl/compiler/spl_editing/core/service.py
```

### 9.3 禁止改动

```text
src/nl2spl/rendering/spl/stage11_compat.py
examples/usage.py
examples/output/spl_editing_demo/run_demo.py
```

### 9.4 设计要求

新增：

```python
TypedRepairPreviewArtifact
PreviewConstructNode
PreviewArtifactChange
PreviewStageSliceResult
```

`PreviewConstructNode` payload contract:

```python
node_id: str
node_kind: Literal[
    "spl_construct",
    "artifact_change",
    "diagnostic_display",
    "structured_fallback",
]
spl_construct_type: RenderableSPLConstructType | None
role: str
ir_payload: Mapping[str, JsonValue]
source_refs: tuple[str, ...]
materialization_status: Literal[
    "planned",
    "dry_run_materialized",
    "context_required",
]
```

Hard gate:

```text
if node_kind == "spl_construct":
    spl_construct_type must not be None
    renderer may dispatch to SPL construct renderer

if node_kind != "spl_construct":
    spl_construct_type must be None
    renderer may only produce markdown / json_tree / structured fallback
    renderer must not emit spl_text through construct renderer
```

`RenderableSPLConstructType | str` is not allowed as a single dispatch field. Any arbitrary string construct name must be carried as data inside `ir_payload` or rendered through a non-SPL display node.

Rules:

```text
- ir_payload is serializable, hashable, audit-friendly.
- no live mutable IR object in preview artifact.
- preview_hash excludes rendered text.
- existing rendered_preview becomes compatibility/display-only.
- non-SPL nodes cannot enter SPL construct renderer.
```

### 9.5 测试计划

1. Preview artifact serializes/deserializes.
2. Preview hash stable across formatting changes.
3. Changing `rendered_preview` does not affect apply eligibility.
4. `PreviewMaterializationResult` can exist without backend-rendered preview.
5. Existing worker delegation / missing handler / missing output preview flows still produce confirmable preview artifact.
6. Non-SPL preview node with `spl_construct_type` set fails validation.
7. SPL preview node with missing `spl_construct_type` fails validation.

### 9.6 验收标准

1. `TypedRepairPreviewArtifact` exists and is used by preview store/service.
2. `rendered_preview` is not required for apply.
3. Preview apply stale checks use typed hashes.
4. No backend string is accepted as typed preview substitute.
5. Preview node schema enforces `node_kind` / `spl_construct_type` consistency.

### 9.7 PM 审核清单

1. Does preview artifact store live IR objects? If yes, fail.
2. Does preview hash include rendered text? If yes, fail.
3. Does apply read `rendered_preview`? If yes, fail.
4. Is `PreviewConstructNode.ir_payload` serializable? If no, fail.
5. Does any non-SPL node reach SPL construct renderer? If yes, fail.
6. Does the schema still use `RenderableSPLConstructType | str` as a single dispatch field? If yes, fail.

---

## 10. Phase R6: SPL Editing run_demo Explicit Rendering Boundary

### 10.1 目标

让 `run_demo.py` 作为 frontend simulator 显式调用 Rendering Subsystem 渲染 repair preview。SPL Editing backend 只返回 typed preview artifact / preview id。

### 10.2 可编辑范围

允许修改：

```text
examples/output/spl_editing_demo/run_demo.py
src/nl2spl/compiler/spl_editing/presentation/**
src/nl2spl/compiler/spl_editing/core/service.py
tests/integration/compiler/spl_editing/
tests/unit/compiler/spl_editing/presentation/
```

允许新增：

```text
src/nl2spl/rendering/spl/repair_preview_renderer.py
tests/unit/rendering/spl/test_repair_preview_renderer.py
```

### 10.3 禁止改动

```text
src/nl2spl/compiler/spl_editing/patches/**
src/nl2spl/compiler/spl_editing/stage_slices/**
```

除非只为 typed preview node trace 增加 read-only fields。

### 10.4 设计要求

`run_demo.py` flow:

```text
preview = service.preview_suggestion(...)
typed_artifact = preview.typed_artifact
rendered = rendering.render_repair_preview_spl(typed_artifact, context)
print(rendered.text)
confirm preview_id
apply_preview_result(preview_id)
```

No direct SPL grammar in `run_demo.py`.

`render_repair_preview_spl` must use:

```text
full render if possible
construct-level render if local
structured fallback if context_required
```

### 10.5 测试计划

1. Worker delegation define-child preview rendered by Rendering Subsystem.
2. Missing handler preview rendered by Rendering Subsystem.
3. Missing output producer preview rendered by Rendering Subsystem.
4. `run_demo.py` does not construct SPL syntax manually.
5. Applying preview works if rendered text is changed between preview and apply.

### 10.6 验收标准

1. `run_demo.py` imports rendering subsystem.
2. Backend preview response contains typed artifact.
3. `RenderedPreview.text` is display-only.
4. Existing demo E2E still readable.

### 10.7 PM 审核清单

1. Does run_demo hand-write `COMMAND` / `USING` grammar? If yes, fail.
2. Does service return typed preview artifact? If no, fail.
3. Does apply consume preview id, not rendered text? If no, fail.

---

## 11. Phase R7: SPL Editing Compatibility Cleanup

### 11.1 目标

降级旧 presentation convenience APIs，并提供 typed replacement。

### 11.2 可编辑范围

允许修改：

```text
src/nl2spl/compiler/spl_editing/core/model.py
src/nl2spl/compiler/spl_editing/core/service.py
src/nl2spl/compiler/spl_editing/presentation/**
src/nl2spl/compiler/spl_editing/demo.py
tests/unit/compiler/spl_editing/
tests/integration/compiler/spl_editing/
```

### 11.3 禁止改动

```text
src/nl2spl/compiler/spl_editing/patches/**
src/nl2spl/compiler/spl_editing/stage_slices/**
```

### 11.4 设计要求

Add:

```python
RepairSuggestion.preview_artifact_id: str | None
SPLEditingService.get_patched_ir_package(run_id) -> FinalIRPackage
```

Keep compatibility:

```python
RepairSuggestion.spl_preview
SPLEditingService.get_patched_spl(run_id)
```

Rules:

```text
spl_preview is deprecated display-only.
get_patched_spl internally calls Rendering Subsystem.
get_patched_spl is never used by apply / verify.
```

### 11.5 测试计划

1. `get_patched_ir_package` returns typed package.
2. `get_patched_spl` remains backward compatible.
3. Static test proves apply path does not call `get_patched_spl`.
4. `RepairSuggestion.spl_preview` is not populated by backend materializer.

### 11.6 验收标准

1. Compatibility APIs still work.
2. New typed APIs are present.
3. Deprecated fields documented.
4. No backend authority depends on deprecated fields.

### 11.7 PM 审核清单

1. `spl_preview` lifecycle documented.
2. `get_patched_spl` marked compatibility/display-only.
3. New typed replacements covered by tests.

---

## 12. Phase R8: Static and Behavioral Guardrails

### 12.1 目标

阻止未来重新把 rendering 放回 backend authority。

### 12.2 可编辑范围

允许新增：

```text
tests/static/test_rendering_boundary_static_audit.py
tests/integration/rendering/test_rendering_boundary_behavior.py
scripts/check_rendering_boundary.py
artifacts/reviews/rendering_boundary/R8/
```

### 12.3 禁止改动

除新增 guardrail 所需外，不改生产逻辑。

### 12.4 设计要求

Backend denylist paths:

```text
src/nl2spl/compiler/spl_editing/core/**
src/nl2spl/compiler/spl_editing/materialization/**
src/nl2spl/compiler/spl_editing/handlers/**
src/nl2spl/compiler/spl_editing/patches/**
src/nl2spl/pipeline/stages/stage1_*/**
...
src/nl2spl/pipeline/stages/stage10_*/**
```

Forbidden tokens:

```text
COMMAND-X
[GENERAL_COMMAND]
[REQUEST_INPUT]
[INVOKE
[MAIN_FLOW]
[EXCEPTION_FLOW]
[COMMAND
[CALL
[INPUT
[DISPLAY
[DEFINE_WORKER
[SEQUENTIAL_BLOCK]
[END_SEQUENTIAL_BLOCK]
USING
RESULT .* SET
RESPONSE .* SET
```

Behavioral tests:

```text
apply path never reads rendered_preview / spl_preview.
preview_hash excludes rendered text.
changing renderer formatting does not change preview applicability.
changing rendered preview text does not affect apply result.
renderer does not mutate IR.
renderer does not consume ConstructPlan / IRS report / RouteAnnotation as SPL authority.
```

### 12.5 测试计划

1. Static audit passes with allowlist.
2. Behavioral guard tests pass.
3. Mutating renderer test fails if renderer modifies input IR.
4. Formatting-only change test proves apply unaffected.
5. Static audit report contains a classification for every hit.
6. Waiver entries require owner and removal condition.

### 12.6 验收标准

1. Static audit can run locally and in CI.
2. No unwaived backend denylist hits.
3. Behavioral guardrails green.
4. CI command documented.
5. Every static audit hit is classified as one of:
   ```text
   rendering subsystem
   stage11 compatibility
   demo/frontend presentation
   renderer test
   golden SPL fixture
   documentation
   explicit waiver
   ```
6. `explicit waiver` entries include owner, reason, and removal condition.
7. Unclassified hit fails the phase.
8. Waiver without owner or removal condition fails the phase.
9. Backend denylist hit with SPL syntax token fails unless proven as a parser-context false positive.

### 12.7 PM 审核清单

1. Does static audit use path denylist + allowlist, not global grep only?
2. Are behavior tests stronger than token scans?
3. Are docs/tests/golden fixtures allowed explicitly?
4. Does every allowlist hit have a classification reason?
5. Are all waivers owned and time/removal-bound?
6. Are backend denylist hits rejected by default?

---

## 13. Phase R9: Stage 11 De-Stage Documentation and Compatibility Freeze

### 13.1 目标

将 Stage 11 从 pipeline authority 文档中降级为 Rendering Subsystem compatibility entry point，并冻结迁移边界。

### 13.2 可编辑范围

允许修改：

```text
README.md
docs/design/**
docs/problem/**
src/nl2spl/pipeline/stages/stage11_spl_renderer/**
src/nl2spl/rendering/spl/stage11_compat.py
tests/integration/pipeline/
```

### 13.3 禁止改动

```text
src/nl2spl/pipeline/stages/stage1_* through stage10_*
src/nl2spl/compiler/spl_editing/patches/**
```

### 13.4 设计要求

Docs must say:

```text
Pipeline canonical output is FinalIRPackage.
SPL text is rendered artifact.
Stage 11 compatibility remains for legacy callers.
usage.py owns explicit rendering call for demo output.
```

### 13.5 测试计划

1. Legacy Stage 11 imports still work.
2. New Rendering Subsystem imports work.
3. README examples updated but backward compatible.
4. No tests assume `spl_text` is canonical when `final_ir_package` exists.

### 13.6 验收标准

1. Documentation no longer presents Stage 11 as compiler authority.
2. Compatibility wrapper lifecycle documented.
3. Existing public callers not broken.

### 13.7 PM 审核清单

1. README/API docs align with implementation.
2. Compatibility lifecycle exists.
3. No misleading “pipeline output = SPL text” language remains except compatibility notes.

---

## 14. Phase R10: End-to-End Freeze

### 14.1 目标

完整验证 Pipeline、SPL Editing、Rendering Subsystem 三者边界闭合。

### 14.2 E2E 场景

必须覆盖：

1. **Pipeline demo rendering**
   - Run `examples/usage.py`.
   - Assert `CompileResult.final_ir_package` exists.
   - Assert `usage.py` calls Rendering Subsystem.
   - Assert `final_spl.txt` still generated.

2. **SPL Editing worker delegation preview**
   - Run `run_demo.py` worker delegation define-child preview/apply path.
   - Assert backend preview returns typed artifact.
   - Assert preview rendered through Rendering Subsystem.
   - Assert Lane B accepted.

3. **SPL Editing missing handler preview**
   - Preview/apply missing handler.
   - Assert typed preview artifact.
   - Assert rendered preview display-only.

4. **SPL Editing missing output producer preview**
   - Preview/apply missing output producer.
   - Assert typed preview artifact.
   - Assert no backend SPL preview string authority.

5. **Formatting-only renderer change**
   - Change renderer formatting in controlled test double.
   - Assert preview hash unchanged.
   - Assert apply eligibility unchanged.

6. **Renderer immutability**
   - Deep-copy IR before render.
   - Render full document and construct preview.
   - Assert IR unchanged.

7. **Static audit**
   - Run backend denylist scan.
   - Assert no unwaived hits.

### 14.3 验收标准

1. All R0-R9 phases independently passed.
2. E2E matrix passed.
3. Static audit passed.
4. No new skip / xfail.
5. Ruff passed for touched files.
6. `git diff --check` passed.
7. Evidence bundle includes command logs and manifest.

### 14.4 PM 审核清单

1. Are typed artifacts the only apply authority?
2. Does rendering remain read-only?
3. Does public API expose `FinalIRPackage`?
4. Is `spl_text` compatibility-only?
5. Are `usage.py` and `run_demo.py` explicit rendering callers?
6. Are Stage 11 compatibility boundaries documented?

---

## 15. Decision Gate: Stage 11 Compatibility Lifecycle

### 15.1 目标

决定 Stage 11 compatibility wrapper 的保留周期。

### 15.2 可选方案

```text
Option A:
  Keep Stage 11 compatibility wrapper indefinitely as public legacy API.

Option B:
  Keep for two release cycles, then remove from default docs but retain import shim.

Option C:
  Remove after all internal callers migrate.
```

推荐：Option B。

理由：

```text
public callers likely depend on SPLRenderer / spl_text;
immediate removal is too risky;
indefinite compatibility keeps architecture ambiguity alive.
```

### 15.3 必须明确的问题

1. Which public APIs are guaranteed for external users?
2. How long is `CompileResult.spl_text` supported?
3. Does Stage 11 import path stay stable?
4. What warning/deprecation message is acceptable?

### 15.4 验收标准

1. PM approves lifecycle.
2. Docs state lifecycle.
3. Tests cover compatibility behavior.

---

## 16. PM 总审核清单

每个阶段提交审核时，PM 必须检查：

1. 是否严格对齐设计文档。
2. 是否扩大 scope。
3. 是否新增 LLM / semantic fallback。
4. 是否新增 backend SPL syntax authority。
5. 是否让 rendered text 进入 apply / verification。
6. 是否让 renderer mutate IR。
7. 是否让 renderer 消费 `ConstructPlan` / `IRS report` / `RouteAnnotation` 作为 SPL authority。
8. 是否引入 `FinalIRPackage` 双 steps authority。
9. 是否保持 `CompileResult.spl_text` 兼容但 display-only。
10. 是否提供 typed replacement API。
11. 是否有 deterministic hash。
12. 是否有 serialization tests。
13. 是否有 behavior tests, not only grep.
14. 是否有 static audit。
15. 是否有 E2E artifact evidence。
16. 是否无 skip / xfail。
17. 是否更新 docs 与 compatibility lifecycle。

---

## 17. 阶段完成顺序

推荐顺序：

```text
R0  Baseline inventory and authority regression locks
R1  Rendering Subsystem shell and Stage 11 compat wrapper
R2  FinalIRPackage and CompileResult additive migration
R3  usage.py explicit rendering boundary
R4  Construct-level SPL renderer substrate
R5  TypedRepairPreviewArtifact and preview DTO split
R6  run_demo.py explicit rendering boundary
R7  SPL Editing compatibility cleanup
R8  Static and behavioral guardrails
R9  Stage 11 de-stage documentation and compatibility freeze
R10 End-to-end freeze
Gate Stage 11 compatibility lifecycle
```

Dependency notes:

```text
R0 must be first.
R1 must precede R3 and R6.
R2 must precede R3 and R7.
R4 should precede R6, otherwise repair preview lacks safe local renderer.
R5 must precede R6 and R7.
R8 should begin after R5 but must be finalized before R10.
R9 should not start before R1-R3 are stable.
R10 must be last.
```
