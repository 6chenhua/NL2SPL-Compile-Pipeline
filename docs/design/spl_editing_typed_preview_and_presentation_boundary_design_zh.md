# Rendering Subsystem 抽离与 Typed Preview Boundary 重构设计

日期：2026-07-06  
状态：Conditional-pass revision for architecture review  
适用范围：NL2SPL Pipeline output contract、Stage 11 SPL rendering、SPL Editing preview/apply、`examples/usage.py`、`examples/output/spl_editing_demo/run_demo.py`、frontend presentation adapters

---

## 1. 设计结论

后端 canonical product 应该是 IR / typed artifact；SPL text 应降级为 presentation artifact。这个方向成立，但不能被理解为“前端或 demo 自己手写 SPL 字符串”。正确边界是：

```text
Pipeline / SPL Editing backend:
  产出 IR / typed preview artifact / diagnostics / verification metadata。

Rendering Subsystem:
  负责把 IR / typed preview artifact 渲染成 SPL text、SPL fragment、diff、UI-oriented display。

usage.py / run_demo.py / real frontend:
  负责 presentation orchestration；
  显式调用 Rendering Subsystem；
  不复制 SPL grammar；
  不把 rendered text 作为 backend authority。
```

因此，本设计的最终目标是：

```text
backend produces IR;
rendering produces SPL;
apply consumes typed artifacts only.
```

这不是一次简单的 renderer 文件搬迁，而是 pipeline output contract migration。当前 `CompileResult.spl_text` 仍是 public result surface，Stage 11 也仍被 README / demo / tests 当成 pipeline 末段；所以迁移必须兼容推进，不能先删除 Stage 11 再补 public API。

---

## 2. 问题定义

### 2.1 触发现象

Worker Delegation repair preview 曾出现：

```text
COMMAND-X [COMMAND match template USING user_request RESULT temp:text SET]
```

这类输出暴露了两个问题：

```text
1. SPL Editing backend 在生成 SPL-like preview string。
2. Rendering authority 和 materialization authority 混在一起。
```

### 2.2 更深层问题

当前项目中：

```text
NL2SPL Pipeline:
  raw input -> stages -> Stage 11 -> SPL text

SPL Editing:
  repair preview -> rendered_preview string -> user confirmation
```

这会让 SPL text / preview string 被误认为 backend canonical artifact。

更正确的模型应是：

```text
Pipeline:
  raw input -> stages 0-10 -> FinalIRPackage

SPL Editing:
  issue -> typed draft/directive -> typed preview artifact -> typed apply artifact

Rendering:
  FinalIRPackage / TypedRepairPreviewArtifact -> display output
```

### 2.3 为什么不能只改成 IR-shaped string

把 preview 从：

```text
COMMAND-X [COMMAND ...]
```

改成：

```text
StepIR(command_type=GENERAL_COMMAND, ...)
```

只是临时止血。它仍然是 backend-produced display string，不能被结构化审计，也不能支持 frontend 多视图展示。正式修复必须让 backend 返回 typed artifact。

---

## 3. 分层架构

### 3.1 Pipeline core

Pipeline owns:

```text
Stage IR artifacts
root WorkerIR / child workers / blocks / steps
ResourceRegistryIR
SymbolTable
constraints
diagnostics
traces
assumptions
provenance
verification metadata
```

Pipeline must not own:

```text
SPL text as canonical output
frontend display
repair preview display
```

### 3.2 SPL Editing backend

SPL Editing owns:

```text
EditableIssue
RepairCatalog
RepairStrategyOptionSpec
RepairInteractionView
RepairDirectiveDraft validation
NormalizedRepairDirective
ConstructClosurePlan
MaterializationPlan
TypedRepairPreviewArtifact
overlay event
verification result
```

SPL Editing must not own:

```text
SPL preview syntax
CLI layout
frontend card rendering
final SPL text rendering
```

### 3.3 Rendering Subsystem

Rendering owns:

```text
IR -> SPL text / SPL fragment / markdown / json tree / UI display
typed preview artifact -> preview display
render warnings
render diagnostics
```

Rendering must not:

```text
mutate IR
create evidence
resolve refs
create overlay
select repair strategy
change verification lane
suppress compiler diagnostics
affect compile completeness
```

### 3.4 Demo / frontend

`usage.py` and `run_demo.py` own presentation orchestration:

```text
call backend;
call Rendering Subsystem;
print / write rendered artifacts;
ask user confirmation.
```

They must not hand-write SPL grammar as a replacement for Rendering Subsystem.

---

## 4. Public API Migration

### 4.1 Current constraint

`CompileResult` is a stable public result surface and currently exposes `spl_text`. This cannot be removed in the first implementation step.

### 4.2 Target public result

```python
@dataclass(frozen=True)
class CompileResult:
    final_ir_package: FinalIRPackage
    compile_diagnostics: tuple[CompileDiagnostic, ...]
    traces: tuple[TraceRecord, ...]
    assumptions: tuple[CompileAssumption, ...]
    rendered_artifacts: tuple[RenderedDocument, ...] = ()

    # Compatibility-only.
    spl_text: str = ""
```

Rules:

```text
final_ir_package is canonical.
spl_text is compatibility/display-only.
rendered_artifacts are presentation artifacts.
No apply / verification / IRS checker may consume spl_text as authority.
```

### 4.3 Migration order

```text
R1: Add FinalIRPackage, keep spl_text.
R2: CompileResult exposes final_ir_package / rendered_artifacts.
R3: Pipeline core internally produces FinalIRPackage.
R4: usage.py explicitly calls RenderingSubsystem.render_full_spl(...).
R5: result.spl_text documented as compatibility/display-only.
R6: Stage11SPLRenderer wrapped by nl2spl.rendering.spl.stage11_compat.
R7: Pipeline architecture docs replace Stage 11 authority with FinalIRPackage.
```

---

## 5. FinalIRPackage

### 5.1 Required shape

`FinalIRPackage` must not duplicate IR authority. In particular, avoid having both `root_worker` and top-level canonical `steps` if `WorkerIR` already owns scoped steps.

Recommended model:

```python
@dataclass(frozen=True)
class FinalIRPackage:
    package_id: str
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

### 5.2 Legacy steps

If top-level unscoped `steps` must remain during migration, name it explicitly:

```python
legacy_unscoped_steps: tuple[StepIR, ...] = ()
```

Rules:

```text
legacy_unscoped_steps may be consumed only by Stage 11 compatibility wrapper.
New renderer code should consume root_worker / scoped IR as canonical input.
```

---

## 6. Rendering Subsystem

### 6.1 Package layout

```text
src/nl2spl/rendering/
  __init__.py
  model.py
  context.py

  spl/
    __init__.py
    construct_renderer.py
    full_document_renderer.py
    preview_renderer.py
    stage11_compat.py
```

### 6.2 Full SPL rendering

```python
def render_full_spl(
    package: FinalIRPackage,
    *,
    mode: RenderMode = RenderMode.FULL_DOCUMENT,
) -> RenderedDocument:
    ...
```

### 6.3 RenderedDocument

```python
@dataclass(frozen=True)
class RenderedDocument:
    renderer_id: str
    format: Literal["spl_text", "json_tree", "html", "markdown"]
    text: str
    render_diagnostics: tuple[RenderDiagnostic, ...] = ()
    source_compile_diagnostics: tuple[CompileDiagnostic, ...] = ()
```

Important boundary:

```text
RenderDiagnostic:
  display/rendering issue, such as context_required or unsupported_construct_renderer.

CompileDiagnostic:
  compiler authority diagnostic, such as missing_handler or missing_output_producer.
```

Renderer may report render diagnostics. It must not create compiler requirement diagnostics.

---

## 7. Construct-Level SPL Renderer

### 7.1 Why needed

Stage 11 currently renders a full document. Repair preview often needs local rendering:

```text
one StepIR
one BlockIR
one WorkerIR
one ExceptionFlowIR
one parent invoke step
```

Therefore rendering should support construct-level SPL rendering, and full-document rendering should become a composition over construct renderers.

### 7.2 Renderable construct enum

Do not accept arbitrary `construct_type: str`. Use a controlled enum:

```python
class RenderableSPLConstructType(str, Enum):
    AGENT = "AGENT"
    WORKER = "WORKER"
    FLOW = "FLOW"
    BLOCK = "BLOCK"
    STEP = "STEP"
    EXCEPTION_FLOW = "EXCEPTION_FLOW"
```

First phase scope:

```text
STEP
BLOCK
WORKER
EXCEPTION_FLOW
AGENT / full document
```

Explicitly non-renderable as SPL:

```text
WORKER_CANDIDATE
WORKER_PROMOTION
ConstructPlan demand
RepairResolutionMarker
IRS report
RouteAnnotation
```

These may be rendered as `json_tree` or `markdown diagnostic display`, but not `spl_text`.

### 7.3 Renderer protocol

```python
class SPLConstructRenderer(Protocol):
    construct_type: RenderableSPLConstructType

    def render(
        self,
        ir: object,
        context: SPLRenderContext,
        mode: RenderMode,
    ) -> RenderedFragment:
        ...
```

### 7.4 Render context

```python
@dataclass(frozen=True)
class SPLRenderContext:
    symbol_table: SymbolTable | None = None
    resources: ResourceRegistryIR | None = None
    profile: AgentProfileIR | None = None
    parent_worker: WorkerIR | None = None
    numbering: NumberingState | None = None
    render_scope: Literal[
        "full_document",
        "worker",
        "block",
        "step",
        "repair_preview",
    ] = "repair_preview"
```

### 7.5 Renderer behavior

Renderer may return:

```text
complete
partial
context_required
```

Renderer must not fabricate missing context.

Examples:

```text
CALL_API StepIR without API declaration context
-> context_required or render diagnostic
-> do not create API_DECLARATION
```

```text
INVOKE_WORKER without target worker
-> context_required
-> do not invent Worker_123
```

---

## 8. Stage 11 Migration

### 8.1 Current Stage 11

Current implementation:

```text
src/nl2spl/pipeline/stages/stage11_spl_renderer
```

It should be treated as existing SPL renderer implementation, not long-term pipeline authority.

### 8.2 Compatibility wrapper

Keep compatibility:

```python
class SPLRenderer:
    def render(...):
        package = FinalIRPackage(...)
        rendered = rendering.render_full_spl(package)
        return rendered.text, _errors(rendered), _warnings(rendered)
```

### 8.3 Target state

```text
Pipeline no longer owns Stage 11 as a core stage.
Pipeline returns FinalIRPackage.
usage.py calls Rendering Subsystem explicitly.
```

---

## 9. Typed Repair Preview

### 9.1 Current gap

`PreviewMaterializationResult.rendered_preview` is currently required and non-empty. This keeps preview DTO coupled to display text.

### 9.2 Target split

```python
@dataclass(frozen=True)
class TypedRepairPreviewArtifact:
    preview_id: str
    base_snapshot_id: str
    issue_id: str
    strategy_id: str
    option_id: str
    directive_hash: str
    closure_plan_hash: str
    selected_refset_id: str
    construct_nodes: tuple[PreviewConstructNode, ...]
    artifact_changes: tuple[PreviewArtifactChange, ...]
    stage_slice_results: tuple[PreviewStageSliceResult, ...]
    preview_hash: str
```

```python
@dataclass(frozen=True)
class RenderedPreview:
    preview_id: str
    renderer_id: str
    format: Literal["spl_text", "markdown", "json_tree"]
    text: str
    warnings: tuple[RenderWarning, ...] = ()
```

Rules:

```text
PreviewStore stores TypedRepairPreviewArtifact.
RenderingSubsystem.render_repair_preview_spl(...) returns RenderedPreview.
apply_preview_result validates TypedRepairPreviewArtifact hashes only.
rendered preview text is ignored by apply.
```

### 9.3 `spl_preview` migration

`RepairSuggestion.spl_preview` does not need immediate deletion because existing v2 model already describes it as display-only. It must be downgraded and migrated:

```text
Phase 1:
  Keep RepairSuggestion.spl_preview.
  Only presentation/rendering layer may populate it.

Phase 2:
  Add RepairSuggestion.preview_artifact_id.
  Mark spl_preview deprecated.

Phase 3:
  service.preview_suggestion returns TypedRepairPreviewArtifact.
  run_demo.py calls RenderingSubsystem to produce RenderedPreview.

Phase 4:
  Remove spl_preview from backend model, or keep only in presentation DTO.
```

---

## 10. SPL Editing Service Boundary

### 10.1 `get_patched_spl`

Current boundary:

```python
service.get_patched_spl(run_id) -> str
```

Target:

```python
service.get_patched_ir_package(run_id) -> FinalIRPackage
rendering.render_full_spl(package) -> RenderedDocument
```

Compatibility:

```text
get_patched_spl(...) remains display-only compatibility wrapper.
It internally calls Rendering Subsystem.
It is never used by apply / verify.
```

### 10.2 Preview apply

Correct flow:

```text
preview_id
-> load TypedRepairPreviewArtifact
-> validate typed hashes
-> apply typed materialization
-> verify
-> updated FinalIRPackage
-> Rendering Subsystem for display
```

Incorrect flow:

```text
rendered_preview text
-> apply
```

---

## 11. Renderer Must Not Consume Planning Artifacts as SPL Authority

Rendering Subsystem must not consume these as SPL authority:

```text
ConstructPlan
RouteAnnotation
RepairDirective
IRS report
WORKER_PROMOTION
WORKER_CANDIDATE
```

Reason:

```text
These are demand / planning / diagnostic artifacts.
They are not materialized SPL IR.
If renderer consumes them directly, it bypasses Stage 4/5/7 materialization, IRS, Gate, and verification.
```

Renderer consumes:

```text
FinalIRPackage
TypedRepairPreviewArtifact
materialized IR constructs
```

---

## 12. usage.py Role

Target:

```text
1. call Pipeline.compile(...)
2. receive CompileResult.final_ir_package
3. call RenderingSubsystem.render_full_spl(...)
4. write examples/output/demo/final_spl.txt
5. write feedback report with rendered SPL section
```

`final_spl.txt` remains useful for demo and review, but is not canonical compiler output.

---

## 13. run_demo.py Role

Target:

```text
1. list issues
2. choose repair option
3. collect user input
4. call backend preview_suggestion
5. receive TypedRepairPreviewArtifact
6. call RenderingSubsystem.render_repair_preview_spl
7. print preview
8. confirm preview_id
9. call backend apply_preview_result
10. get updated FinalIRPackage
11. call RenderingSubsystem.render_full_spl
12. print updated SPL
```

`run_demo.py` may show SPL-like preview only because it calls Rendering Subsystem.

---

## 14. Preview Rendering Strategy

### 14.1 Full render

Use when preview can be projected into complete render context:

```text
Typed preview artifact + base snapshot
-> in-memory projected FinalIRPackage
-> render_full_spl
```

### 14.2 Construct render

Use when preview only has local constructs:

```text
PreviewConstructNode(StepIR)
-> render_spl_construct(STEP, ...)

PreviewConstructNode(BlockIR)
-> render_spl_construct(BLOCK, ...)

PreviewConstructNode(WorkerIR)
-> render_spl_construct(WORKER, ...)
```

### 14.3 Structured fallback

Use when context is insufficient:

```text
Will create StepIR
  command_type: GENERAL_COMMAND
  text: ...
  outputs: ...
```

This is presentation output, not backend authority.

---

## 15. Static Guardrails

### 15.1 Backend-authority denylist

Audit these paths for hard-coded SPL syntax strings:

```text
src/nl2spl/compiler/spl_editing/core/**
src/nl2spl/compiler/spl_editing/materialization/**
src/nl2spl/compiler/spl_editing/handlers/**
src/nl2spl/compiler/spl_editing/patches/**
src/nl2spl/pipeline/stages/stage1_*/**
...
src/nl2spl/pipeline/stages/stage10_*/**
```

Tokens to review:

```text
COMMAND-X
[GENERAL_COMMAND]
[REQUEST_INPUT]
[INVOKE
[MAIN_FLOW]
[EXCEPTION_FLOW]
USING
RESULT ... SET
```

### 15.2 Allowlist

Allowed locations:

```text
src/nl2spl/rendering/**
src/nl2spl/pipeline/stages/stage11_spl_renderer/**  # compatibility only
examples/**
tests/**/renderer/**
docs/**
golden SPL fixtures
```

### 15.3 Behavior tests matter more than grep

Required tests:

```text
apply path never reads rendered_preview / spl_preview.
preview_hash excludes rendered text.
changing renderer formatting does not change preview applicability.
changing rendered preview text does not affect apply result.
renderer mutation test proves IR is unchanged after rendering.
```

---

## 16. Migration Plan

### R0: Inventory

```text
Inventory current Stage 11 dependencies.
Inventory all spl_text / final_spl / rendered_preview / spl_preview producers.
Inventory all consumers.
Prove apply does not require rendered text.
```

### R1: Rendering Subsystem shell

```text
Add src/nl2spl/rendering.
Wrap Stage 11 via rendering.spl.stage11_compat.
Keep old Stage 11 imports working.
Add RenderedDocument / RenderedFragment / RenderDiagnostic.
```

### R2: FinalIRPackage public API

```text
Add FinalIRPackage.
Expose CompileResult.final_ir_package.
Keep CompileResult.spl_text as compatibility/display-only.
```

### R3: usage.py rendering boundary

```text
usage.py explicitly calls RenderingSubsystem.render_full_spl.
final_spl.txt remains demo artifact.
Pipeline core can be tested without SPL rendering.
```

### R4: Construct-level renderer

```text
Implement controlled enum for renderable SPL constructs.
Implement STEP / BLOCK / WORKER / EXCEPTION_FLOW.
Add context_required behavior.
Begin refactoring full renderer to use construct renderers.
```

### R5: Typed repair preview artifact

```text
Add TypedRepairPreviewArtifact.
PreviewMaterializationResult no longer requires rendered_preview.
Preview hash binds typed artifact only.
```

### R6: run_demo.py rendering boundary

```text
run_demo.py receives typed preview.
run_demo.py calls RenderingSubsystem.render_repair_preview_spl.
apply_preview_result consumes preview_id / typed artifact only.
```

### R7: SPL Editing compatibility cleanup

```text
Deprecate RepairSuggestion.spl_preview.
Add preview_artifact_id.
Move get_patched_spl to compatibility wrapper.
Add get_patched_ir_package.
```

### R8: Static and behavioral guardrails

```text
Add backend denylist audit.
Add renderer mutation tests.
Add formatting-only change does not affect apply tests.
Add no ConstructPlan/IRS/RouteAnnotation SPL authority tests.
```

### R9: Stage 11 de-stage

```text
Docs rename Stage 11 as Rendering compatibility.
Pipeline authority chain ends at FinalIRPackage.
Stage 11 remains only as compatibility entry point until callers migrate.
```

---

## 17. PM Gate

Implementation should not be accepted until these gates pass:

```text
P0. CompileResult exposes FinalIRPackage.
P1. result.spl_text remains compatibility-only and documented as rendered artifact.
P2. Stage11 renderer is callable through nl2spl.rendering.spl.
P3. usage.py explicitly calls Rendering Subsystem.
P4. PreviewMaterializationResult no longer requires rendered_preview.
P5. TypedRepairPreviewArtifact is serializable and hashable without rendered text.
P6. run_demo.py renders preview explicitly through Rendering Subsystem.
P7. apply_preview_result validates typed hashes only.
P8. Renderer mutation test proves IR is unchanged after rendering.
P9. Formatting-only renderer change does not affect preview apply.
P10. Static audit proves backend materialization / patch / apply paths do not emit SPL syntax strings.
```

---

## 18. Final Data Flow

Pipeline:

```text
raw input
-> stages 0-10
-> FinalIRPackage
-> CompileResult(
     final_ir_package,
     compile_diagnostics,
     traces,
     assumptions,
     rendered_artifacts=compat only
   )
```

Demo / frontend:

```text
CompileResult.final_ir_package
-> RenderingSubsystem.render_full_spl(...)
-> final_spl.txt / UI display
```

SPL Editing backend:

```text
issue
-> RepairDirective
-> ConstructRepairIntent
-> dry-run materialization
-> TypedRepairPreviewArtifact
-> preview_id
```

SPL Editing presentation:

```text
TypedRepairPreviewArtifact
-> RenderingSubsystem.render_repair_preview_spl(...)
-> RenderedPreview
```

Apply:

```text
preview_id
-> validate typed preview stale state
-> apply typed materialization
-> patched artifact snapshot
-> verification
-> updated FinalIRPackage
```

Display:

```text
updated FinalIRPackage
-> RenderingSubsystem.render_full_spl(...)
```

---

## 19. Final Judgment

This design is a conditional-pass baseline:

```text
Direction: pass
Architecture boundary: pass
Implementation readiness: conditional pass
```

It becomes implementation-ready once the implementation plan explicitly covers:

```text
public API migration;
typed preview artifact split;
Stage 11 compatibility wrapper;
FinalIRPackage authority cleanup;
renderer diagnostics boundary;
static and behavioral guards.
```

