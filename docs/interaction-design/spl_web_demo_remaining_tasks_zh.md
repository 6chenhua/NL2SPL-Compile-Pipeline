# SPL Web Demo 剩余任务跟踪文档

版本：v0.1
状态日期：2026-07-10

依据文档：

- `docs/interaction-design/spl_web_demo_functional_requirements_zh.md` v0.3
- `docs/interaction-design/spl_web_demo_detailed_design_zh.md` v0.2
- `docs/interaction-design/spl_web_demo_implementation_plan_zh.md` v0.1
- `apps/spl-web-demo/.probe-output/20260709T185204Z/`

## 1. 文档目的

本文档记录 SPL Web Demo 在 snapshot 驱动的 API MVP-A/B 和 HTTP route 接入完成后，仍需完成的 9 个任务。本文档用于：

- 明确完成最初 Web Demo 目标所需的剩余范围。
- 区分 MVP 必做任务和延期增强任务。
- 记录每个任务的当前状态、依赖、交付物和验收条件。
- 防止前端开发先于 API read-model 稳定，造成重复调整 DTO 和 UI。

本文档是任务跟踪文档，不替代功能需求、详细设计或实现计划。

## 2. 状态定义

| 状态 | 英文标识 | 含义 |
|---|---|---|
| 已完成 | `completed` | 交付物和验收条件均已满足，验证 gate 已通过 |
| 部分完成 | `partial` | 已有部分基础能力，但任务定义中的必要交付物尚未全部完成 |
| 待开始 | `pending` | 尚未进入实现，或当前能力不足以满足该任务的验收条件 |
| 阻塞 | `blocked` | 无法继续，需要新的 service contract、外部输入或明确决策 |
| 延期 | `deferred` | 不阻塞第一版 MVP，明确安排在必做任务之后 |

状态更新规则：

- 只有实际运行测试或浏览器验证后，任务才能标记为 `completed`。
- 仅创建文件、DTO 或路由，但核心用户流程不可运行时，不得标记为 `completed`。
- Contract Probe 发现 public service contract 不足时，应标记为 `blocked` 或 `deferred`，不得通过 private service fields 绕过。
- 每次状态更新应同时记录验证命令或输出位置。

## 3. 当前已完成基线

以下内容已完成，不计入后续 9 个任务：

- Contract Probe 已验证 snapshot registration、issue presentation、repair interaction、directive、preview、apply 和 verification 链路。
- Framework-agnostic `SplWebDemoApi` 已实现 run、initial SPL、Construct list/provenance、Span detail、issue、interaction、directive、preview 和 apply handler。
- FastAPI 薄 route 已接入统一 `/api/demo/v1` 前缀。
- `from-snapshot` 已明确为 local/debug-only endpoint。
- Directive 和 preview 已绑定 API run ownership。
- 非 object JSON body 已统一返回 `400 invalid_request`。
- Apply 后 `overlay_version > 0` 且 patched projection 不可用时，返回 HTTP 200 `projection_unavailable`，不返回 stale SPL。
- T1 原始验收已通过 typed snapshot 投影 27 张平铺 cards；该数量属于历史基线，后续层级 UI 修订已扩展为 `WORKER → FLOW → BLOCK → COMMAND`，需要生成新的 canonical 摘要。
- T2 已从结构化 `TraceRecord` 和 `SpanIR` 投影 Construct provenance 与完整 source span text。
- T3 已完成单 issue explanation trigger、error cache 收敛和 Preview Cancel 客户端丢弃语义。
- Handler、projector、explanation lifecycle 与 HTTP route focused tests 共 35 个，当前验证为通过。
- Web Demo backend 未发现 `_get_snapshot`、`_snapshots`、`feedback_report.md`、`final_spl.txt` 或 diagnostic message 解析路径。
- T4 已完成 snapshot 驱动的只读前端工作台，并通过真实浏览器响应式验证。
- Frontend TypeScript、8 个 Vitest 测试、production build 和 dependency audit 均已通过。
- T5 已完成 worker delegation `keep_in_main_flow` 的前端 repair 闭环和真实浏览器 Cancel/Apply E2E。
- Frontend repair suite 共 14 个 Vitest 测试，typecheck、production build 和 dependency audit 均已通过。
- T6 已完成真实 LLM Contract Probe、同步 `POST /runs`、compiler facade 和前端自然语言编译入口。
- T7 已完成 snapshot、repair、live compile 三条浏览器 E2E 和统一启动文档。

当前未完成的关键事实：

- Initial `GET /runs/{run_id}/spl` 已返回真实 cards，Construct Provenance 和 Span detail API 已可用。
- Explanation scheduling API 已可用，真实 LLM scheduler 通过依赖注入启用。
- 前端已支持已验证的 repair interaction、preview、apply、cancel 和 verification 展示。
- Live `POST /runs` 已可用；真实 smoke 与浏览器 HTTP E2E 均已通过。
- Apply 后 patched SPL/cards public read-model 仍不可用。

## 4. 任务状态总览

| ID | 任务 | 分类 | 当前状态 | 前置依赖 | MVP 必需 |
|---|---|---|---|---|---|
| T1 | SPL Construct Card 投影 | Backend read-model | 已完成 `completed` | 当前 snapshot bootstrap | 是 |
| T2 | Construct Provenance 与 Span API | Backend read-model | 已完成 `completed` | T1 的稳定 construct identity | 是 |
| T3 | Explanation Trigger 与 Preview Cancel 收口 | Backend lifecycle | 已完成 `completed` | 现有 issue/preview API | 是 |
| T4 | 最小前端只读工作台 | Frontend MVP-A | 已完成 `completed` | T1、T2；T3 可并行收口 | 是 |
| T5 | 前端 Repair 闭环 | Frontend MVP-B | 已完成 `completed` | T4、现有 repair HTTP API | 是 |
| T6 | Live Compile 接入 | Backend compile path | 已完成 `completed` | live compile smoke probe | 是 |
| T7 | 浏览器 E2E 与交付收口 | Integration | 已完成 `completed` | T1-T6 | 是 |
| T8 | Apply 后 patched SPL/cards read-model | Backend enhancement | 延期 `deferred` | 新 public read-model contract + probe | 否 |
| T9 | MVP-C 其他 Repair 类型 | Repair expansion | 延期 `deferred` | 各 repair flow Contract Probe | 否 |

## 5. 必做任务

### T1. SPL Construct Card 投影

状态：**已完成 `completed`**

优先级：P1

建议下一任务：否，后续进入 T2。

完成内容：

- 新增结构化 `CardProjector` 与 `SplConstructCard` DTO。
- 当前 presentation contract 覆盖 `WORKER`、`FLOW`、`EXCEPTION_FLOW`、`BLOCK`、`COMMAND`、`REQUIRED_OUTPUT`、`PROFILE`、`CONSTRAINT`。
- `StepIR` 仅作为 compiler internal IR，由 Web Demo 映射为用户可见 `COMMAND`。
- 每张 card 提供 typed `parent_ref` 和 `construct_path`，用于组装 `Worker → Flow → Block → Command`。
- 无法验证 Flow/Block 归属的 Command 以 `review_only + unplaced` fail closed，不生成虚假 Block。
- Initial `GET /spl` 已返回真实 `spl_cards`。
- 已增加 `GET /runs/{run_id}/constructs`。
- Overlay 后 patched projection 不可用时继续返回空 cards 和 `projection_unavailable`。
- 已增加 projector、handler 和 HTTP 测试；层级 contract 对应的后端 focused gate 尚需在仓库 `.venv` 中重新执行。

历史完成证据（平铺 card v1）：

- Focused pytest：`19 passed`。
- Ruff check：通过。
- Ruff format check：`12 files already formatted`。
- 正式 backend forbidden-boundary search：无匹配。
- 历史 canonical 摘要：`apps/spl-web-demo/.probe-output/20260710T071204Z/canonical_construct_cards.summary.json`。
- 该历史 artifact 返回 27 张 cards：`WORKER=1`、`STEP=9`、`EXCEPTION_FLOW=6`、`REQUIRED_OUTPUT=3`、`PROFILE=1`、`CONSTRAINT=7`。
- 上述数量和 `STEP` 类型已被层级 presentation contract 取代，不得作为当前 cardinality 或类型断言。

层级 UI 修订验证：

- Frontend TypeScript：通过。
- Frontend Vitest：`18 passed`。
- Frontend production build：通过。
- Frontend forbidden-boundary 与 source line-length scan：无异常。
- Backend focused pytest、Ruff 和新 canonical hierarchy artifact：待本地 `.venv` gate 后补录。

目标：

从结构化 snapshot、IR 或 stage artifact 投影前端可消费的 SPL Construct Cards，不解析 `final_spl.txt`、`feedback_report.md` 或诊断文本。

范围：

- 维护轻量 `CardProjector`，不解析 rendered SPL。
- 当前覆盖 `WORKER`、`FLOW`、`EXCEPTION_FLOW`、`BLOCK`、`COMMAND`、`REQUIRED_OUTPUT`、`PROFILE`、`CONSTRAINT`。
- 显式投影 `SEQUENTIAL`、`IF`、`WHILE`、`FOR` Block subtype。
- 为每个 card 提供稳定的 `construct_ref`、`parent_ref`、`construct_path`、标题、摘要和 provenance summary。
- 将 initial `GET /runs/{run_id}/spl` 中的 `spl_cards` 作为 typed hierarchy read-model 返回。
- 通过 `GET /api/demo/v1/runs/{run_id}/constructs` 提供同一 projection。

交付物：

- Card DTO 和 projector。
- Framework-agnostic handler 与 FastAPI route。
- Projector 单元测试和 HTTP 测试。
- 基于 canonical demo snapshot 的真实输出样例。

验收条件：

- `overlay_version == 0` 时至少返回一种以上真实 Construct Card。
- 卡片 identity 可用于后续 provenance 查询。
- 不从 rendered SPL 文本反向解析 construct。
- `overlay_version > 0` 且 patched projection 不可用时继续返回空 cards 和 `projection_unavailable`。

### T2. Construct Provenance 与 Span API

状态：**已完成 `completed`**

优先级：P1

依赖：T1

完成内容：

- 新增 `ProvenanceProjector`、Construct provenance DTO、Trace DTO 和 Span DTO。
- Card 内部已冻结不对前端暴露的 trace-target candidates，用于解析 worker、step、flow、scoped variable、profile 和 constraint trace。
- 已增加 Construct provenance 与 Span detail handler/routes。
- 已结构化保留 `user_confirmed_repair` 的 patch、diagnostic 和 user text 字段。
- Construct provenance 在 patched read-model 不可用时 fail closed；原始 source span 仍可独立读取。
- 已补充 projector、handler 与 HTTP 测试并在仓库 `.venv` 中完成验证。

完成证据：

- Focused pytest：`27 passed`。
- Ruff check：通过。
- Ruff format check：`14 files already formatted`。
- 正式 backend forbidden-boundary search：无匹配。
- Canonical provenance 响应摘要：`apps/spl-web-demo/.probe-output/20260710T074921Z/canonical_construct_provenance.summary.json`。
- Canonical snapshot 的 27 个 Construct 全部匹配 Trace：`available=27`。
- Provenance kind：`direct=25`、`assumed=1`、`mixed=1`。
- 解析出 26 个唯一 Span；`s21a`、`s37a`、`s37b` 在 snapshot span index 中缺失，已按 contract 显式列为 unresolved，没有伪造文本。

目标：

支持用户从 Construct Card 查看该 Construct 来源于哪些 span，以及每个 span 的原文内容。

范围：

- 新增轻量 `ProvenanceProjector`。
- 从 snapshot 的 `TraceRecord` 和 `SpanIR` 投影 provenance DTO。
- 增加以下 API：

```text
GET /api/demo/v1/runs/{run_id}/constructs
GET /api/demo/v1/runs/{run_id}/constructs/{construct_ref}/provenance
GET /api/demo/v1/runs/{run_id}/spans/{span_id}
```

- 对无 source span 的 Construct 显式返回 `inferred` 或 `assumed`，不得伪造 span。
- 保留 `user_confirmed_repair` 等 provenance 类型的结构化表达。

交付物：

- Provenance DTO、projector、handler 和 routes。
- Construct-to-trace、trace-to-span 和 span-not-found 测试。
- 至少一个有 source span 和一个无 source span 的固定测试样例。

验收条件：

- 有来源的 Construct 可以返回 span id 和完整 span text。
- 无来源的 Construct 返回明确 provenance kind。
- API 不访问 private editing fields，不解析 diagnostic message。
- `construct_not_found` 和 `span_not_found` 使用稳定错误码。

### T3. Explanation Trigger 与 Preview Cancel 收口

状态：**已完成 `completed`**

优先级：P1

完成内容：

- Issue detail 已读取 cached explanation，envelope 支持 `ready`、`pending`、`missing`、`error`。
- 已增加单 issue explanation trigger handler 与 HTTP route：

```text
POST /api/demo/v1/runs/{run_id}/issues/{issue_id}/explanation
```

- Route 只调用注入的 `ExplanationScheduler`，不持有或直接调用 LLM。
- 底层继续使用 snapshot-level scheduling，但 API 只返回目标 issue 的 envelope。
- 已补齐 `ready` 幂等、`missing -> pending -> ready/error`、重复 pending 不重复调度和 scheduler unavailable 测试。
- Batch generation 基础设施异常现在会写入稳定的 `error` cache，不再永久停留在 `pending`。
- 外层 batch executor `submit()` 启动失败时也会将已写入的 pending cache 收敛为 error，再向 handler 返回 503。
- Preview Cancel 已冻结为客户端丢弃 `preview_id` 且不调用 apply；当前不增加后端 cancel endpoint。
- 已增加零副作用测试：Cancel 不产生 overlay、不执行 verification、不修改 issue state。

完成证据：

- Focused pytest：`35 passed`。
- Ruff check：通过。
- Ruff format check：`17 files already formatted`。
- 正式 backend forbidden-boundary search：无匹配。
- Canonical lifecycle 摘要：`apps/spl-web-demo/.probe-output/20260710T082156Z/canonical_explanation_lifecycle.summary.json`。
- 已验证 ready 幂等、missing/pending/ready/error、pending 去重、scheduler unavailable/start failure 和 Preview Cancel 零副作用。

交付物：

- Explanation trigger handler、route 和状态测试。
- Preview cancel 行为说明及前端/API 责任边界。
- `missing -> pending -> ready/error` 可验证样例，允许使用 fake scheduler 隔离 LLM。

验收条件：

- Missing explanation 可以触发 scheduling，而 route 不直接调用 LLM 生成解释。
- API 状态与 snapshot cache 一致。
- Cancel 不产生 overlay、不执行 verification、不修改 issue state。

### T4. 最小前端只读工作台

状态：**已完成 `completed`**

优先级：P1

依赖：T1、T2；T3 可并行收口

完成内容：

- 已创建独立的 `apps/spl-web-demo/frontend/`，采用 `Vite + React + TypeScript`。
- 已实现 snapshot path bootstrap、run/projection status、Construct Cards、Provenance、Span detail、Issue Console、Issue Detail 和 explanation lifecycle 展示。
- 已通过 Vite dev proxy 将同源 `/api` 转发至 FastAPI，不新增后端 CORS 配置。
- 前端只消费 public HTTP DTO；rendered SPL 只原样展示，不参与状态推断或 Construct 解析。
- 已显式处理 loading、empty、error、pending 和 `unsupported_in_mvp`。
- 已冻结 T4 为 inspection-only；repair interaction、preview、apply 和 cancel 控件不进入本阶段。
- 已增加组件测试，覆盖 canonical read flow、独立 Span API、missing explanation trigger、projection unavailable 和 bootstrap error。
- 前端依赖已安装并锁定，Vite、Vitest 和 React plugin 已更新到当前兼容版本。
- 已完成 typecheck、Vitest、production build、dependency audit 和真实浏览器四档响应式检查。

完成证据：

- TypeScript typecheck：通过。
- Vitest：`8 passed`。
- Production build：通过。
- `npm audit`：`0 vulnerabilities`。
- 浏览器已验证 snapshot、Construct、Provenance、Span、Issue 和 cached explanation 读取流程。
- `1440x900`、`1024x900`、`768x900`、`390x844` 均无横向溢出、元素越界或文本溢出。
- 浏览器控制台 warning/error：`0/0`。
- 验证摘要：`apps/spl-web-demo/.probe-output/20260710T090151Z/frontend_t4_browser.summary.json`。

目标：

提供一个单页、低复杂度的 API-first 工作台，先完成 snapshot 驱动的读取和检查流程。

建议技术边界：

- `Vite + React + TypeScript`。
- 不引入前端路由库、全局状态库、复杂组件库或设计系统。
- 仅保留 API client、页面组件、局部状态和少量 CSS。

范围：

- Snapshot path 输入与 run bootstrap。
- Run 状态和 projection status 展示。
- SPL Construct Cards。
- Provenance drawer 或下方面板。
- Issue Console、Issue Detail 和 cached explanation。
- Loading、empty、error 和 `unsupported_in_mvp` 状态。

交付物：

- `apps/spl-web-demo/frontend/` 独立目录。
- 可运行的开发命令和 README。
- 最小 API client、独立生成页与结构化 SPL 工作台。

验收条件：

- 用户可从页面加载 canonical snapshot run。
- 用户可查看 Construct Card、span 原文、Issue Detail 和 explanation。
- 前端不理解 internal IR，不解析 SPL 或 diagnostic message。
- 页面在常见桌面宽度和移动窄屏下无内容重叠。

页面与完整文档投影回填（2026-07-10）：

- `/` 已作为独立 Generate SPL 页面，支持自然语言编译和 local/debug snapshot bootstrap。
- `/runs/{run_id}` 已作为独立 SPL Workbench 页面，刷新、后退和前进均可恢复正确页面。
- 新增 `GET /api/demo/v1/runs/{run_id}/spl-document`，返回扁平、稳定 identity 的结构化文档节点。
- 工作台按层级展示 `PERSONA`、`AUDIENCE`、`CONCEPTS`、`CONSTRAINTS`、`RESOURCES`、`TYPES`、`VARIABLES`、`FILES`、`APIS`、`WORKERS`、`INPUTS` 和 `OUTPUTS`。
- 有 `construct_ref` 的节点继续复用公共 provenance/span API；section 节点保持 `construct_ref=null`。
- Apply 后 patched document read-model 不可用时，`spl-document` 返回 HTTP 200、`projection_unavailable` 和空 `nodes`，不回退 initial document。
- Problems Dock、Issue Detail、explanation、repair interaction、preview、apply 和 verification 均保留在新工作台中。
- Backend focused suite：`49 passed`；Frontend Vitest：`20 passed`；TypeScript、Ruff 和 production build 均通过。
- 浏览器已验证 `1440x900`、`1024x900`、`768x900`、`390x844`，页面无横向溢出；干净页面控制台 warning/error 为 `0/0`。
- 验收摘要：`apps/spl-web-demo/.probe-output/20260710T154227Z/frontend_document_workbench.summary.json`。

### T5. 前端 Repair 闭环

状态：**已完成 `completed`**

优先级：P1

依赖：T4、现有 repair HTTP API

完成内容：

- 已为前端 API client 增加 interaction、directive、preview 和 apply DTO 与路由调用。
- 已只接入经过验证的 worker delegation `keep_in_main_flow` option；其他 repair option 保持 display-only。
- 已按真实 contract 渲染必填 `task_selection` single choice 和可选 `additional_instruction` long text。
- `task_selection` 提交 option 的业务 `value`，不提交 `option_id`；`additional_instruction` 映射到 directive 顶层字段。
- 未选择必填 task 时禁止生成 preview。
- 已展示 directive/session/suggestion/preview identity、typed artifact summary、preview cards 状态和 rendered preview。
- Cancel 仅清理前端 interaction/directive/preview state，不调用 apply 或其他后端 cancel endpoint。
- Apply 显式提交 `user_confirmation=true`，随后刷新 public run/SPL/Construct/Issue read-model。
- Apply response 到达后会先清除 initial cards；即使 refresh 失败也不恢复 stale SPL/cards。
- 已增加 Verification panel，展示 accepted、lane、failure reasons、diagnostic counts、overlay、revision 和 projection status。
- 未知 interaction field 或未验证 field contract 会 fail closed 为 `unsupported_in_mvp`，不会伪造空值。
- TypeScript、14 个 Vitest 测试、production build、dependency audit 和真实浏览器 repair E2E 均已通过。

完成证据：

- Cancel flow：preview 请求 1 次、apply 请求 0 次，overlay/revision 不变，无 verification，preview 已清除。
- Apply flow：verification `accepted=true`、lane `B`、resolved diagnostics `4`、new blocking diagnostics `0`。
- Apply 后 overlay 从 `0` 增加到 `1`，revision 更新为 `demo:snap_b61a1efdd39c:1`，issue count 刷新为 `8`。
- Apply 后 `GET /spl` 返回 `rendered_spl=null`、空 cards 和 `projection_unavailable`，页面可见 Construct Cards 为 `0`。
- `1440x900`、`1024x900`、`768x900`、`390x844` 均无横向溢出、元素越界或文本溢出。
- 浏览器控制台 warning/error：`0/0`。
- TypeScript typecheck：通过；Vitest：`14 passed`；production build：通过；`npm audit`：`0 vulnerabilities`。
- 验证摘要：`apps/spl-web-demo/.probe-output/20260710T094240Z/frontend_t5_repair.summary.json`。

目标：

在最小工作台中接入已验证的 worker delegation `keep_in_main_flow` repair flow。

范围：

- 从 Issue Detail 选择 repair option。
- 根据 interaction schema 渲染：
  - `task_selection`：`single_choice`，必填。
  - `additional_instruction`：`long_text`，可选。
- 提交 directive draft。
- 展示 preview、suggestion/session identity 和 preview cards 状态。
- 支持 Apply 和 Cancel。
- Apply 后刷新 run、issues 和 SPL projection status。
- 当 `projection_status="projection_unavailable"` 时，显示明确提示，不保留旧 SPL 作为当前状态。

交付物：

- Repair form、Preview panel 和 Verification panel。
- 前端 API error mapping。
- Repair happy path 和关键错误状态的组件或浏览器测试。

验收条件：

- 用户可完成 interaction -> directive -> preview -> apply 全链路。
- 未填写必填字段时不能提交。
- Cancel 不 apply。
- Apply 后显示 verification accepted/lane/failure reasons 和 updated issue summary。
- 前端不会为 unsupported interaction field 伪造空值。

### T6. Live Compile 接入

状态：**已完成 `completed`**

优先级：P1

依赖：live compile smoke probe

完成内容：

- 已新增独立 Contract Probe case entrypoint：`contract_probe/live_compile_probe.py`。
- 已提供固定的 `live_compile_smoke` 自然语言输入，不把完整输入复制进摘要，只记录来源、长度与 SHA-256。
- probe 支持 `--compile-attempts`，记录成功次数、成功率与每次真实编译耗时。
- probe 记录 runtime `PipelineResult` 字段清单、SPL/diagnostic/trace/assumption 数量、completeness、final IR 与 snapshot 状态。
- snapshot 配置明确使用 `precompute_issue_explanations=false`。
- snapshot available 后，通过现有 Web Demo handler 完成注册，并验证 run、SPL、Construct 和 Issue read APIs。
- snapshot unavailable、文件缺失、注册失败或 read-model 不可用均 fail closed，不进入 repair flow。
- probe 根据最大编译耗时和可配置 HTTP budget 输出 `synchronous_candidate` 或 `async_job_recommended`，不预设任务队列架构。
- 已增加 5 个 probe 单元测试，覆盖成功率、空 initial projection、snapshot unavailable、配置边界和 CLI 参数。
- 真实 LLM smoke 已通过：`1/1` attempt，耗时 `56.19s`，在 `120s` budget 下为 `synchronous_candidate`。
- Probe 产出 available snapshot、1636 字符 SPL、8 张 cards，run/SPL/Construct/Issue API 均返回 200。
- 首次 smoke 暴露并修复 `editing_available` 语义冲突：该字段表示 snapshot Editing 服务可用，不再等同于“存在 can_fix issue”。
- 已新增 `PipelineCompilerFacade`，集中创建 pipeline config；probe 与 HTTP path 复用同一 config builder。
- 已实现同步 `POST /api/demo/v1/runs`、payload validation、LLM/compile/timeout/internal error mapping 和 snapshot 半成功响应。
- Snapshot status 声称 available 但缺少 path 时 fail closed 为 `422 compile_failed`。
- 前端已增加自然语言需求输入、同步 compiling 状态和 live run hydration；debug snapshot bootstrap 保持为次要入口。

完成证据：

- Contract Probe：`apps/spl-web-demo/.probe-output/20260710T100142Z/live_compile_smoke.summary.json`。
- Probe 结论：`pass + synchronous_candidate`，`success_rate=1.0`，最大耗时 `56.1902771s`。
- Browser HTTP E2E：真实 `POST /runs` 返回 200，随后 run/SPL/Construct/Issue/Provenance 均返回 200。
- Browser live run：6 张 cards、1544 字符 SPL、projection available，loading 状态可见。
- T6/T7 汇总：`apps/spl-web-demo/.probe-output/20260710T101412Z/live_compile_http_e2e.summary.json`。
- Backend Web Demo suite：`47 passed`；Ruff lint/format：通过。
- Frontend：TypeScript 通过、Vitest `16 passed`、production build 通过、audit `0 vulnerabilities`。

目标：

完成最初需求中的“用户输入初始自然语言需求，生成 SPL IR 并进入 Web Demo 工作流”。

实施顺序：

1. 增加 Contract Probe case：`live_compile_smoke`。
2. 记录真实 LLM compile 耗时、成功率、`PipelineResult` 字段和 snapshot 状态。
3. 验证 `spl_editing_snapshot_path` 可由 `register_snapshot_file(path)` 注册。
4. 实现：

```text
POST /api/demo/v1/runs
```

5. 将成功结果映射到现有 `DemoRunStore` 和 read APIs。

行为约束：

- 默认 `precompute_issue_explanations=false`。
- API route 不编排 pipeline stage，不解析 compiler report。
- 同步请求是否保留，由 smoke probe 的耗时决定。
- 如果常规输入超出可接受 HTTP 时间，再切换异步 job + polling；不得预先增加不必要的任务队列架构。

交付物：

- Live compile probe 输出。
- Compiler facade/adapter、handler、route 和测试。
- 前端需求输入和 compile 状态展示。

验收条件：

- 用户输入自然语言后可获得 run id、initial SPL、cards 和 issues。
- Snapshot 生成失败的半成功状态可见，editing 被正确禁用。
- LLM key 和后端配置不进入前端代码。

### T7. 浏览器 E2E 与交付收口

状态：**已完成 `completed`**

优先级：P1

依赖：T1-T6

完成内容：

- 已启动真实 FastAPI server 和 Vite dev server，并通过 `/api` 同源代理联调。
- T4 浏览器 E2E 已验证 snapshot、Construct、Provenance、Span、Issue 和 explanation。
- T5 浏览器 E2E 已分别验证 Cancel 零副作用与 Apply/verification/refresh。
- T6 浏览器 E2E 已验证 live compile loading、run、SPL、cards、provenance 和 issue console。
- `1440x900`、`1024x900`、`768x900`、`390x844` 三轮检查均无横向溢出、元素越界或文本溢出。
- 三轮浏览器 gate 的控制台 warning/error 均为 `0/0`。
- 已新增 `apps/spl-web-demo/README.md`，统一记录安装、启动、验证命令和已知限制。
- 已记录 patched projection unavailable、MVP-C deferred 和 TestClient dependency warning。

完成证据：

- T4：`apps/spl-web-demo/.probe-output/20260710T090151Z/frontend_t4_browser.summary.json`。
- T5：`apps/spl-web-demo/.probe-output/20260710T094240Z/frontend_t5_repair.summary.json`。
- T6：`apps/spl-web-demo/.probe-output/20260710T101412Z/live_compile_http_e2e.summary.json`。

交付物：

- 浏览器 E2E 测试或可复现验证脚本。
- 最终 README 和运行命令。
- 最终 focused pytest、Ruff、format 和 browser verification 记录。

验收条件：

- 新环境按 README 可以启动前后端。
- 浏览器可以完整执行 MVP-A/B 核心流程。
- Apply 后页面状态与 API 一致，无 stale SPL。
- 无明显布局重叠、不可点击控件或未处理的错误状态。

## 6. 延期任务

### T8. Apply 后 patched SPL/cards read-model

状态：**延期 `deferred`**

优先级：P2

是否阻塞第一版 MVP：否

延期原因：

Contract Probe 已确认 apply 成功后 `overlay_version=1`，但 patched snapshot 的 `final_spl_available=false`。当前 public presentation/read-model 不足以稳定返回 patched SPL/cards。

进入条件：

- SPL Editing service 或 presentation facade 提供 public patched snapshot/read-model getter；或
- overlay replay 能稳定生成 patched final SPL 和 typed card source；且
- 新 Contract Probe case 验证该路径，不依赖 `_get_snapshot`、`_snapshots` 等 private fields。

候选范围：

- 新增 patched snapshot public read API。
- 从 patched typed artifacts 投影 SPL cards 和 provenance。
- Apply 后将 `projection_status` 从 `projection_unavailable` 更新为 `available`。

验收条件：

- Apply 后可以返回真实 patched SPL/cards。
- 不使用 preview text 冒充 applied SPL。
- 不回退初始 `PipelineResult.spl_text`。

### T9. MVP-C 其他 Repair 类型

状态：**延期 `deferred`**

优先级：P2

是否阻塞第一版 MVP：否

目标：

在 worker delegation 首个闭环稳定后，逐个评估并接入 `missing_handler`、`missing_output_producer` 等其他 repair option。

进入条件：

- 每个 repair 类型必须先有独立 Contract Probe。
- Probe 必须证明其可以通过 public presentation facade 完成 interaction、directive、preview、apply 和 verification。
- Interaction field 类型必须被 MVP 前端支持；否则保留 `unsupported_in_mvp`。

交付物：

- 每种 repair flow 的 probe report。
- 对应 interaction/projector/API/frontend 增量。
- 每种 flow 的 focused tests 和 verification 证据。

验收条件：

- 不在 route 或前端复制 repair 规则。
- 不为展示完整性伪造 directive contract。
- 每种新增 flow 都有独立 apply 和 verification 测试。

## 7. 推荐执行顺序

```text
T1 Construct Cards
-> T2 Provenance / Span APIs
-> T3 Explanation Trigger / Cancel
-> T4 Frontend Read Workbench
-> T5 Frontend Repair Flow
-> T6 Live Compile
-> T7 Browser E2E / Delivery Freeze

T8 Patched Projection: deferred
T9 MVP-C Repairs: deferred
```

并行建议：

- T3 可与 T1/T2 并行，但不要阻塞 read-model 主线。
- T6 的 smoke probe 可提前运行，但 live compile route 不应阻塞 snapshot 驱动的前端开发。
- T8/T9 只有在 T7 完成并冻结第一版 MVP 后再启动。

## 8. 里程碑

### M1. Backend Read Closure

包含：T1、T2、T3。

完成标志：前端所需的 cards、provenance、span、issue explanation 和 cancel 语义稳定。

### M2. Frontend MVP Closure

包含：T4、T5。

完成标志：snapshot 驱动的单页工作台可以完成读取和 worker delegation repair 闭环。

### M3. Original User Flow Closure

包含：T6。

完成标志：用户可以从自然语言需求开始，而不是只能加载已有 snapshot。

### M4. Demo Freeze

包含：T7。

完成标志：真实浏览器 E2E、启动文档和最终 gate 全部通过。

### M5. Post-MVP Enhancements

包含：T8、T9。

完成标志：只有在 public contract 和对应 probe 通过后逐项启动，不影响第一版 MVP 判定。

## 9. 当前结论

截至 2026-07-10：

- Snapshot 驱动的 repair API/HTTP contract：**已完成**。
- 9 个后续任务中：
  - `pending`：0 个。
  - `partial`：0 个。
  - `deferred`：2 个（T8、T9）。
  - `completed`：7 个（T1、T2、T3、T4、T5、T6、T7）。
- 第一版 Web Demo：**已完成并通过 snapshot、repair 和 live compile 浏览器验证**。
- 后续只进入明确延期项 T8/T9，且必须先补 public contract 与对应 Contract Probe。
