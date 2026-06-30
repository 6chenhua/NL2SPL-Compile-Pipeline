# External Capability Intent 与 API Lowering 重构实施计划

本文档严格基于 `docs/design/external_capability_intent_extraction_and_api_lowering_design_zh.md` 制定。实施目标是建立稳定的 external capability extraction/lowering 架构：把混杂在普通 step 中的 invocation 转换为 source-backed intent 和 construct demands，并在合同与 Gate 允许时安全渲染 `API_DECLARATION/CALL_API`；本计划不承诺所有混合 step 都生成完整 `[DEFINE_APIS:] + [CALL ...]`。

状态：Architecture direction approved；implementation conditionally approved after R0。  
与旧计划关系：本计划不替代 `api-definition-full-materialization-implementation-plan.md` 的 explicit-name 基础能力；它复用现有 API IRS/Gate/DTO，并完成前置 capability lifecycle、unnamed lowering、operation coverage 和 authority switch。  
首轮范围：混合 step 中的 named/described capability、declaration-only、direct call、partial binding、shadow migration。暂不覆盖 handoff-backed API 扩展、完整 OpenAPI 自动生成、runtime discovery、SPL Editing repair strategy。

---

## 1. 总体目标

```text
Adapter / Stage 1 / Stage 2
  -> EarlyCapabilityEvidenceView              deterministic, non-authoritative

Resolved spans after Stage 3
  -> ExternalCapabilitySemanticExtractor      one versioned LLM structured call
  -> ExternalCapabilityIntentCandidateIR      source-anchored candidate only

DemandView + candidates + adapter evidence
  -> ExternalCapabilityIntentResolver         deterministic
  -> ExternalCapabilityIntentPlanIR           sole capability authority

Stage 3.25 ConstructPlanner
  -> APIDeclarationDemand / APICallDemand      no raw-NL re-read

Stage 3.5
  -> worker ownership only                    no API semantics

Stage 4/5/6/7
  -> placement / declaration binding / argument binding / StepIR

post-normalize IRS + Gate
  -> renderable declaration/call views

Stage 11
  -> grammar rendering only
```

只有 Phase B Semantic Extractor 是新增的不确定性注入点。其余新增组件必须确定性、可 roundtrip、可离线回放。

---

## 2. 全局硬性原则

1. 不新增 `Stage 3.20` 编号；组件按职责命名并在 resolved spans 与 ConstructPlan 之间编排。
2. `routes.integrations` 只是兼容索引，不是 coverage、admission、demand 或 render authority。
3. Early evidence 不得直接进入 ConstructPlan。
4. Semantic candidate 不得被 Stage 6/7、Gate、Renderer 消费。
5. Resolver final plan 是 capability authority；ConstructPlan 是 SPL construct demand authority。
6. Stage 3.5 不创建/升级 capability intent，不产生 API demand，不回写 ConstructPlan。
7. Phase A/C、name resolver、placement、binding、Gate 均不得调用 LLM。
8. Phase B LLM 只做闭合 claim 分类和 extractive surface selection，不输出 admission、ID、binding、API name 或 construct。
9. `operation_surface/capability_surface/explicit ref/evidence` 必须经程序化 source-anchor validation。
10. Authentication 完全无 evidence 时默认 `<none>`，记录 `defaulted_none`；存在“需要认证”但方式不明时不得默认。
11. 不发明 schema、function、URL、parameter、return 或变量引用。
12. Candidate 与 partial binding 必须可见，不得静默退化为 GENERAL_COMMAND。
13. 同一 operation 由 CALL_API 消费后不得重复生成同义 GENERAL_COMMAND；残余 behavior 必须保留。
14. Stage-local diagnostics 必须 checkpoint；只有经 consolidator 选择后进入 final diagnostics。
15. 不新增 skip/xfail/弱断言掩盖迁移失败。
16. 每个 migration shim 标记 remove-after phase；默认生产 authority 只能切换一次。

---

## 3. LLM / Rule-based 决策约束

允许的确定性逻辑：结构化字段投影、Unicode/空白/大小写/标点规范化、source anchor 校验、stable hash、exact canonical ref merge、DemandView lookup、boolean admission、operation coverage、placement/status check、serializer、diagnostic consolidation。

唯一新增 LLM：`ExternalCapabilitySemanticExtractor`。必须具有独立 stage name、prompt version、schema version、model/config fingerprint 和 checkpoint payload。

禁止：关键词确认 external boundary；fuzzy similarity 自动 merge；Resolver 重读 raw NL；LLM 生成 inferred name；Stage 3.5 fallback；renderer fallback。

需要 PM 重新确认才允许：新增第二次 capability LLM call、扩大到 handoff-backed API、自动 OpenAPI contract generation、改变 SPL grammar、暴露 repair strategy。

---

## 4. Phase R0：Contract tightening

### 4.1 目标

在改变生产行为前冻结所有 DTO、grammar/renderability、DemandView projection 和 duplicate-prevention contract。

### 4.2 可编辑范围

```text
docs/design/external_capability_intent_extraction_and_api_lowering_design_zh.md
src/nl2spl/compiler/construct_plan/model.py
src/nl2spl/pipeline/stages/stage6_resource_extractor/api_materialization.py
src/nl2spl/compiler/resource_contract_demand_view/model.py
src/nl2spl/ir/resource_registry_ir.py
src/nl2spl/ir/structured_text_ir.py
tests/unit/compiler/capability_intent/
tests/unit/api_materialization/
tests/unit/pipeline/test_resource_declaration_gate.py
```

### 4.3 禁止改动

不得接入 orchestrator、修改 prompt、改变 final SPL、删除 legacy fields。

### 4.4 设计要求与实现思路

- Final intent字段名冻结为 `capability_admission_status` 与 `invocation_admission_status`；R0 model、R4 resolver、serializer、snapshot 禁止使用旧单一 `admission_status`。
- 为 final intent定义 `binding_status/unresolved_binding_claims/source_candidate_ids`。
- `ExternalCapabilityIntentPlanIR` 定义 `candidate_resolution_map` 完整性约束。
- 现有 `DemandViewDemand` 增加可选 source-backed `resource_ref`，或明确首轮恒为 `None`；不得从 evidence text slugify。
- 保留现有 `APICallPlacementIR` 字段与 type tag；status 统一 `placed/unresolved/ambiguous`。
- 现有 `APICallBindingIR` 记录为 declaration→APISpec binding；规划兼容更名 `APIDeclarationBindingIR`，本阶段不破坏旧 tag。
- 新增 `APICallArgumentBindingIR`。
- `APIMaterializationPlanIR` 增加 demand-level materialization/renderability record。
- `APICallDemand` 增加 `operation_coverage/consumes_behavior_span_ids/residual_behavior_span_ids/behavior_lowering_policy`。
- `operation_coverage` 使用 `OperationCoverageIR(coverage_id, source_span_id, operation_surface, char_start, char_end, relation)`；offset 可空但 surface anchor 不可空。同 span residual 场景必须有有效 offsets 或 Stage 3 split 后独立 span，禁止只靠 span subset。
- grammar characterization 验证 `{ }`、empty functions；认证缺省 `<none>`。

### 4.5 R0 PR 拆分

R0 保持一个阻塞阶段，但必须拆为三个独立可审查 PR：

```text
R0a DTO/schema/serializer
  capability intent/plan、argument binding、operation coverage、materialization record
R0b grammar/renderability characterization
  placeholders、defaulted_none/unresolved auth、name-only blocked
R0c DemandView/diagnostic contract
  resource_ref、no-slugify、diagnostic suppression
```

R0a/b/c 均不得接 runtime；D-CAP-0 只有在三者 contract tests 全部通过后批准。

### 4.6 测试计划

覆盖 DTO roundtrip、旧 snapshot default、candidate map 双向一致性、defaulted_none/ambiguous auth、DemandView 无 resource_ref、placement enum、operation coverage serializer、placeholder grammar characterization。

### 4.7 验收标准

所有 contract 测试通过；默认 pipeline/SPL 不变；无第二套同名 DTO；全量测试无新增失败、skip、xfail。

### 4.8 PM 审核清单

检查 actual DTO 路径；检查 `APICallBindingIR` 未被误改为参数绑定；检查 name-only 不可渲染；检查 `<none>` 仅在完全无 auth evidence 时默认；检查 R0 没有 runtime wiring。

---

## 5. Phase R1：Baseline characterization

### 5.1 目标

锁定当前漏标、Stage 3.5 越权、duplicate/fallback、partial Gate 行为，只加测试。

### 5.2 可编辑范围

```text
tests/characterization/capability_intent/
tests/integration/capability_intent/test_current_gaps.py
examples/output/（仅固定 fixture，禁止覆盖无关 demo）
```

### 5.3 禁止改动

所有 `src/`、prompt、grammar 禁止修改。

### 5.4 设计要求

Fixture 至少包含：混合 named capability、described unnamed、普通 retrieve、policy-only、同 span residual provenance、Stage 2 integrations 为空但 Stage 3.5 external signal、extractor failure placeholder。

### 5.5 测试计划

显式标注 current gap 与 future expectation；不得把旧行为当批准 contract。

### 5.6 验收标准

测试稳定复现缺口；无 production diff；全量测试基线记录。Fixture manifest 必须经 PM 审批，并覆盖设计 §16.4 的七类：explicit named、described unnamed、internal action、data object/no boundary、policy-only、multi-capability ambiguity、declaration-only vs executable；另含 routes漏标和Stage3.5越权 characterization；其中必须有“`routes.integrations`为空但resolved span包含明确 capability surface”的硬性fixture。

### 5.7 PM 审核清单

确认没有只测 demo phrase；确认跨领域 negative fixtures；确认断言验证 artifact 而非只搜字符串。

---

## 6. Phase R2：Early evidence shadow

### 6.1 目标

实现 deterministic early evidence collection，只写 intermediate/checkpoint，不影响 ConstructPlan。

### 6.2 可编辑范围

```text
src/nl2spl/compiler/capability_intent/model.py
src/nl2spl/compiler/capability_intent/evidence_collector.py
src/nl2spl/compiler/capability_intent/serialization.py
src/nl2spl/pipeline/orchestrator.py
tests/unit/compiler/capability_intent/test_evidence_collector.py
```

### 6.3 禁止改动

Stage 3.5/6/7、ConstructPlanner、renderer、API Gate、prompt 禁止修改。

### 6.4 设计要求与实现思路

Collector 只映射 adapter hints、Stage 1 provenance、Stage 2 annotations。MVP 可使用 immutable view 而非完整 dataclass，但 payload 必须保存 origin/span/hint/surface。不得关键词扫描、确认 boundary、生成名称。Checkpoint key：`capability_evidence_candidates_payload`。

### 6.5 测试计划

Adapter explicit、route clue、无 clue、重复 clue deterministic merge、缺 provenance rejection、Stage 2 漏标不阻塞后续全量 coverage契约。

### 6.6 验收标准

Shadow payload deterministic；final result不变；collector 无 LLM/client import。

### 6.7 PM 审核清单

grep 关键词 heuristic；检查 evidence 没有 admission；检查未接 ConstructPlan。

---

## 7. Phase R3：Semantic extractor shadow

### 7.1 目标

新增唯一 LLM semantic boundary，扫描全部 resolved spans，输出严格 candidate schema。

### 7.2 可编辑范围

```text
src/nl2spl/pipeline/capability_semantic_extractor.py
src/nl2spl/compiler/capability_intent/model.py
src/nl2spl/compiler/capability_intent/candidate_validator.py
prompts/capability_semantic_extractor_system.txt
src/nl2spl/pipeline/orchestrator.py
tests/unit/pipeline/capability_semantic_extractor/
tests/evaluation/capability_semantic_extractor/
```

### 7.3 禁止改动

ConstructPlanner、Stage 3.5/6/7、Gate/Renderer 不得消费 candidates；禁止 rule fallback。

### 7.4 设计要求与实现思路

- 在 Stage 3 resolved spans 后调用，可与 DemandView 并行但首版可串行编排。
- Prompt 输入所有 resolved spans、section/packet、early context；routes 不是过滤器。
- 输出闭合 boundary/identity/invocation claims、extractive surfaces、evidence span IDs。
- `operation_text` 由 deterministic normalizer从 `operation_surface` 生成。
- Post-validator执行 existence、anchor、claim evidence、unknown field、duplicate candidate validation。
- Anchor失败降级 unresolved或reject并诊断，禁止自动修文。
- Payload记录 prompt/schema/model fingerprint；disposition可先写 structured suppressed metadata。
- Extractor failure输出显式 unavailable result，不返回空 candidates冒充成功；交给R4按early evidence三分支解析。

### 7.5 测试计划

Golden named/unnamed/mention/policy/internal；幻觉 surface；不存在 span；多 capability；复合 clause；跨领域 metamorphic；LLM failure；schema unknown field；全 span coverage。

指标只允许在 PM 批准的人工 gold labels 上计算，禁止LLM自评。Evaluation manifest必须记录来源、slice样本数、label guideline版本、是否允许multi-label、双人标注disagreement及adjudicator结论。Schema validity不能替代semantic metrics。

### 7.6 验收标准

只新增一次 LLM call；shadow不改变SPL；失败不返回“无 intent”。冻结评估集上必须同时满足：boundary precision≥0.90、recall≥0.85；executable invocation precision≥0.90、recall≥0.85；explicit identity precision≥0.95、recall≥0.90；described-unnamed precision≥0.85、recall≥0.80；internal-action false-positive≤0.05；policy-only call false-positive≤0.05；进入Resolver的surface anchor有效率=1.00。任何单项未达标不得进入R4/R5 switch。

### 7.7 PM 审核清单

检查 prompt 没要求 API name/schema；检查 source anchor 在代码而非 prompt；检查完整 fingerprint；检查 routes 未作为 coverage gate。

---

## 8. Phase R4：Resolver shadow

### 8.1 目标

实现完全确定性的 merge、admission、DemandView binding、canonical ID 和 candidate map，仍不驱动 ConstructPlan。

### 8.2 可编辑范围

```text
src/nl2spl/compiler/capability_intent/resolver.py
src/nl2spl/compiler/capability_intent/admission.py
src/nl2spl/compiler/capability_intent/demand_binding_view.py
src/nl2spl/compiler/capability_intent/diagnostics.py
src/nl2spl/compiler/capability_intent/serialization.py
src/nl2spl/pipeline/orchestrator.py
tests/unit/compiler/capability_intent/test_resolver.py
```

### 8.3 禁止改动

Resolver 禁止 LLM/raw NL/Stage 3.5；ConstructPlanner/Stage6/7输出不变。

### 8.4 设计要求与实现思路

Exact canonical ref merge；unnamed仅 normalized surface相等+operation relation+scope compatible时merge；fuzzy只产生 ambiguity。分别计算 capability/invocation admission。DemandView 缺 resource_ref时保留 unbound。生成 stable ID和 total `candidate_resolution_map`；final intent反向 IDs一致。Candidate产生用户可投影 diagnostic context。Extractor unavailable时实现三分支：explicit adapter evidence可形成declaration-only final intent；存在Stage2 early clue则产生 unavailable diagnostic且不建call；无early evidence只写suppressed/checkpoint，不制造capability blocker。

### 8.5 测试计划

Merge/no-merge/conflict、顺序不变性、snapshot roundtrip、declaration-only、candidate soft failure、partial binding、DemandView unavailable、candidate map totality、无 LLM import。

### 8.6 验收标准

同输入 byte-stable payload；使用canonical dict key、tuple/list和diagnostic排序；DemandView/extraction到达顺序不影响结果；final SPL不变。

### 8.7 PM 审核清单

检查 fuzzy不自动merge；检查 candidate不生成 demand；检查 Resolver不slugify变量；检查所有candidate有映射。

---

## 9. Phase R5：ConstructPlan authority switch

### 9.1 目标

Stage 3.25 只从 confirmed final intents 创建 API declaration/call demands，并脱权 routes/Stage3.5 hints。

### 9.2 可编辑范围

```text
src/nl2spl/compiler/construct_plan/model.py
src/nl2spl/compiler/construct_plan/planner.py
src/nl2spl/pipeline/orchestrator.py
src/nl2spl/pipeline/stages/stage3_5_worker_boundary_planner/
tests/unit/compiler/construct_plan/test_capability_lowering.py
tests/unit/pipeline/stage3_5/test_capability_deauthority.py
```

### 9.3 禁止改动

Stage6/7/Gate/Renderer 不在本阶段切换；Stage3.5不得创建intent/demand。

### 9.4 设计要求与实现思路

Confirmed capability→declaration；加confirmed invocation→call。`APICallDemand.operation_coverage` 必须携带 clause-level source anchor；consumed/residual spans与lowering policy必须完整，Stage7不得自行从文本重推。Declaration agent-global；`APICallDemand`不携带worker_id，call owner暂空。`owner_worker_id`只由R6a `APICallPlacementIR`依据WorkerPlan和source-span ownership确定，禁止默认MainWorker。Legacy compile hint只compare并诊断。Migration flag只用于shadow comparison，remove after R8。

R5前置门禁：R4 shadow必须覆盖全部R1 fixture manifest；candidate map、admission、binding、coverage与预期一致；所有diff均被标为approved change或有解释，`unexplained_diff_count=0`。门禁报告与PM批准进入checkpoint/PR附件。

### 9.5 测试计划

Declaration-only、call、candidate、policy-only、unnamed、coverage replaces/augments/residual/ambiguous、legacy conflict、routes empty仍可lower、serializer。

### 9.6 验收标准

API demand唯一来源是final plan；同operation不重复demand；Stage3.5无API semantic writes；除已批准consistency diagnostic外，R5不得改变rendered SPL或StepIR materialization；R4-vs-R1 shadow comparison `unexplained_diff_count=0`并获PM批准。

### 9.7 PM 审核清单

grep routes.integrations/compile_as_call_api demand creation；检查coverage字段完整；检查ambiguous不选第一个。

---

## 10. Phase R6a：Name resolver、placement 与 Stage 6 materialization

### 10.1 目标

先稳定 deterministic name、Stage4/5 placement、declaration binding和APISpec materialization，不生成新的 CALL_API StepIR。

### 10.2 可编辑范围

```text
src/nl2spl/compiler/capability_intent/name_resolver.py
src/nl2spl/pipeline/stages/stage5_block_assembler/api_call_placement.py
src/nl2spl/pipeline/stages/stage6_resource_extractor/api_materialization.py
相关 serializer/tests
```

### 10.3 禁止改动

Stage7、Gate/Renderer不切换；不自动生成OpenAPI；不使用Stage3.5 hint。

### 10.4 设计要求与实现思路

Placement只消费call demand+ownership。`CapabilityNameResolverV1`独立版本化，基于final intent结构字段生成stable name/collision suffix。Stage6扩展现有APIMaterializationPlanIR，生成APISpec、declaration binding和materialization record；auth absent→defaulted none；不得创建argument binding或StepIR。

### 10.5 测试计划

Named/unnamed稳定性、collision、auth三态、placement unresolved/ambiguous、materialization status、旧APICallBinding兼容、snapshot roundtrip。

### 10.6 验收标准

APISpec/placement/declaration binding可追到intent/demand；inferred name只进入materialization plan/APISpec，不反写final intent capability_ref；partial APISpec在R7a前不得进入renderable view；placement不得默认MainWorker；R6a可独立合入；final SPL仍由旧路径控制；全量测试通过。

### 10.7 PM 审核清单

检查name resolver不读raw NL；检查未复制DTO；检查Stage6未创建StepIR；检查Stage7无R6a依赖泄漏。

---

## 11. Phase R6b：Argument binding、operation coverage 与 Stage 7 CALL_API

### 11.1 目标

在R6a artifacts稳定后，实现source-backed argument binding和duplicate-safe CALL_API，精确保留same-span residual behavior。

### 11.2 可编辑范围

```text
src/nl2spl/pipeline/stages/stage7_step_extractor/api_call_materializer.py
src/nl2spl/pipeline/stages/stage7_step_extractor/worker_scoped.py
src/nl2spl/compiler/construct_plan/model.py
相关 serializer/tests
```

### 11.3 禁止改动

不重新解析raw NL；不更改Stage6 APISpec；不按span subset删除GENERAL_COMMAND；不fallback。

### 11.4 设计要求与实现思路

新增APICallArgumentBindingIR，只绑定DemandView/source-backed refs。Stage7要求placed、declaration binding和APISpec。消费`OperationCoverageIR`：exact coverage替换API operation；`residual_behavior_span_ids`或同span非覆盖char ranges继续进入普通step；ambiguous coverage不生成重复命令并诊断。Coverage接口为R5产物，Stage7只校验不重算。

### 11.5 测试计划

Fully/partial/unbound/not-required；same-span retrieve+provenance；offset invalid；split-span residual；replaces/augments/residual/ambiguous；多call；no fallback；sanitation demand identity；coverage missing/ambiguous时no CALL且no同义GENERAL_COMMAND；declared API blocked时no renderable CALL且no fallback；same-span residual无offset且未split时不得删除GENERAL_COMMAND并产生coverage ambiguity diagnostic；R6a artifacts存在但APICallArgumentBindingIR/argument binder未接入时，Stage7 graceful no-CALL_API并产生可审计diagnostic，不crash、不回退GENERAL_COMMAND。

### 11.6 验收标准

CALL与GENERAL_COMMAND无重复执行；residual零丢失；无span-subset sanitation；缺argument-binding组件时graceful no-CALL_API；R6b可独立回滚且全量测试通过。

### 11.7 PM 审核清单

检查coverage来源是APICallDemand；检查argument refs有provenance；检查Stage7没有文本语义规则；检查R6a/R6b可独立回滚。


---

## 12. Phase R7a：IRS / Gate / ProducerIndex

### 12.1 目标

建立post-normalize API declaration/call final authority和Gate views，不接Renderer。

### 12.2 可编辑范围

```text
src/nl2spl/compiler/irs/checkers/api_declaration.py
src/nl2spl/compiler/irs/checkers/post_normalize.py
src/nl2spl/pipeline/resource_declaration_gate.py
src/nl2spl/pipeline/executable_gate.py
src/nl2spl/compiler/producer_index.py
相关tests
```

### 12.3 禁止改动

Renderer不修改；Stage6 local report不是authority；Gate不补语义。

### 12.4 设计要求与实现思路

Characterize placeholders；状态complete/grammar_minimal_partial/blocked；CALL ref必须指向Gate-approved declaration；ProducerIndex只消费gate pass；blocked partial必须产生可投影stage-local diagnostic。

### 12.5 测试计划

Grammar valid/invalid、defaulted none、ambiguous auth、partial block、undeclared call、ProducerIndex bypass negative、silent-block negative。

### 12.6 验收标准

Post-normalize report唯一render authority；无Gate bypass；blocked partial有diagnostic；不改变renderer输入路径。

### 12.7 PM 审核清单

检查Stage6 report未越权；placeholder未complete；ProducerIndex不自判；R7a可独立回滚。

---

## 13. Phase R7b：Renderer integration

### 13.1 目标

将Stage11切换为只消费R7a gate-approved views，保证CALL/DEFINE一致性。

### 13.2 可编辑范围

```text
src/nl2spl/pipeline/stages/stage11_spl_renderer/
src/nl2spl/pipeline/orchestrator.py
tests/integration/capability_intent/test_gate_rendering.py
```

### 13.3 禁止改动

Renderer不读capability intent/raw NL，不补name/auth/schema/functions，不重做IRS/Gate。

### 13.4 设计要求与实现思路

只渲染RenderableResourceRegistryView和gate-approved executable view；DEFINE与CALL成对一致；blocked declaration对应CALL不渲染；无fallback。

### 13.5 测试计划

Complete/partial/blocked、CALL/DEFINE consistency、missing view fail-closed、renderer fallback negative、R7a有但R7b未切换的兼容状态。

### 13.6 验收标准

无悬挂CALL；renderer纯消费；R7b可独立回滚；全量测试通过。

### 13.7 PM 审核清单

检查renderer无semantic import；检查gate view是唯一资源输入；检查blocked无silent output。


---

## 14. Phase R8：Feedback / provenance / migration cleanup

### 14.1 目标

完成candidate soft failure、trace、snapshot、diagnostic去重和legacy脱权清理。

### 14.2 可编辑范围

```text
src/nl2spl/pipeline/provenance.py
src/nl2spl/compiler/feedback_report_renderer.py
src/nl2spl/compiler/report_renderer.py
src/nl2spl/compiler/diagnostic_consolidator.py
src/nl2spl/compiler/artifacts/snapshot/
src/nl2spl/pipeline/orchestrator.py
相关 E2E tests/docs/examples
```

### 14.3 禁止改动

不新增repair strategy；不删serializer兼容字段，除非migration test证明；不让feedback解析raw NL。

### 14.4 设计要求与实现思路

Capability section显示excerpt、缺失claim、未lower原因、建议补充；trace覆盖source→candidate→intent→demand→IR→SPL。Final diagnostics只保留explicit evidence extractor failure、无construct覆盖的confirmed lowering问题、影响completion的legacy conflict。移除Stage3.5 API authority与migration flag；routes保留derived index。

### 14.5 测试计划

Candidate feedback、diagnostic suppression、trace completeness、snapshot replay、legacy removal grep、cross-domain E2E、full suite。

### 14.6 验收标准

用户可区分candidate/partial/blocked；feedback同时显示capability semantic issue、API contract issue及related/suppressed关系；无重复diagnostic；snapshot结果稳定；无legacy production import/call。

### 14.7 PM 审核清单

检查feedback不发明解释；检查stage-local不直入final；检查shim生命周期结束；检查demo不是唯一E2E。

---

## 15. Decision Gate D-CAP-0：R0 grammar 与 DemandView

### 15.1 目标

在 shadow components 开工前冻结 admission字段名、Phase B评估阈值、operation coverage、grammar-minimal partial、resource binding、DTO schema migration与diagnostic authority，防止 R2-R7 各自发明不兼容 contract。

### 15.2 可选方案

```text
Placeholder：validator接受 -> grammar_minimal_partial；不接受 -> partial_blocked
DemandView：扩展source-backed resource_ref；或首轮保持None/unbound
Binding DTO：兼容更名旧APICallBinding；参数绑定使用新type
Name resolver：独立CapabilityNameResolverV1
```

推荐保守方案：validator失败则blocked；resource_ref缺失则unbound；禁止evidence text推断。

### 15.3 必须明确的问题

1. `{ }` 与 empty functions 的实际 grammar validator结果。
2. `defaulted_none` authentication的serializer/trace表达。
3. DemandView resource_ref是否进入首轮。
4. APICallBinding type-tag兼容周期。
5. CapabilityNameResolverV1 collision contract。
6. capability/construct diagnostics suppression golden。
7. Final intent字段固定为`capability_admission_status`和`invocation_admission_status`，禁止旧`admission_status`。
8. Phase B per-claim阈值、最小fixture样本量和评估集版本冻结。
9. `OperationCoverageIR`字段、offset/anchor规则及R5→R6b传播测试冻结。

D-CAP-0 审批记录必须填写以下字段，禁止仅写“阈值已确认”：

```text
evaluation_set_id
evaluation_set_version
total_fixture_count
per_slice_fixture_counts
cross_domain_slice_manifest
frozen_metric_thresholds
approver
approval_date
```

样本量数字由 R1 语料盘点后在 D-CAP-0 冻结；计划阶段不预设缺乏项目数据支撑的数字，但字段不得为空。

### 15.4 验收标准

R0 contract tests通过；默认SPL不变；schema migration可roundtrip；PM书面批准后方可进入R2，R1 characterization可提前进行。

---

## 16. 端到端验收场景

1. **混合 named capability**：validate + retrieve via named service + normalize/provenance；只retrieval变CALL，residual保留。
2. **描述性 unnamed capability**：direct surface+invocation→inferred name、unknown mechanism、partial contract。
3. **普通 retrieve**：无external surface→无capability demand。
4. **Declaration only**：confirmed capability + no invocation→仅declaration demand。
5. **Candidate soft failure**：模糊boundary→feedback，不渲染API。
6. **Partial binding**：semantic confirmed、DemandView缺ref→不降admission，诊断binding。
7. **Stage2漏标**：全resolved coverage仍提取。
8. **Same-span residual**：API operation被消费，provenance/transform不丢。
9. **Extractor unavailable**：按early evidence三分支处理，无Stage3.5 fallback。
10. **Snapshot replay**：candidate map、intent ID、name、Gate、SPL不漂移。
11. **Cross-domain metamorphic**：替换领域名词不依赖固定phrase。
12. **Grammar blocking**：不可渲染declaration与CALL同时blocked。

---

## 17. PM 总审核清单

1. 是否严格对齐最终设计与R0收紧。
2. 是否新增第二个LLM语义边界。
3. Phase A/C是否导入LLM client。
4. routes.integrations是否被当coverage/authority。
5. Stage3.5是否创建或升级API语义。
6. candidate是否越过Resolver进入下游。
7. anchor validation是否程序化执行。
8. fuzzy similarity是否自动merge。
9. candidate_resolution_map是否total且双向一致。
10. capability/invocation admission是否仍被混成一个状态。
11. binding缺失是否错误降低semantic admission。
12. DemandView缺resource_ref时是否发明变量。
13. `<none>`默认是否错误覆盖“需要认证但方式不明”。
14. partial placeholder是否被标complete。
15. CALL是否引用非Gate-approved declaration。
16. Stage7是否按span subset误删residual behavior。
17. 是否存在同operation CALL+GENERAL_COMMAND重复执行。
18. Stage6 local report是否越权render。
19. renderer是否读capability intent或fallback。
20. stage-local diagnostics是否绕过consolidator。
21. snapshot是否保存prompt/schema/model fingerprint。
22. migration shim是否有remove-after phase。
23. 是否新增skip/xfail/弱断言。
24. 是否只用当前demo证明通用性。
25. full suite是否通过。

---

## 18. 阶段完成顺序

```text
R0 Contract tightening
D-CAP-0 approval
R1 Baseline characterization
R2 Early evidence shadow
R3 Semantic extractor shadow
R4 Resolver shadow
R5 ConstructPlan authority switch
R6a Name/placement/Stage6 materialization
R6b Stage7 binding/coverage
R7a IRS/Gate/ProducerIndex
R7b Renderer integration
R8 Feedback/migration cleanup
```

R1可与R0测试并行但不得先改变production。R2-R4全部shadow，不改变SPL。R5是唯一demand authority切换点。R6a必须等R5。R6b必须等R6a artifacts稳定。R7a必须等R6b。R7b必须等R7a。R8最后移除shim。建议每阶段独立PR，禁止合并R2-R5为单次大改；R6a/R6b必须独立PR；R7a/R7b必须独立PR。

---

## 19. 首轮交付边界

首轮完成时必须支持：从普通混合step识别named/described capability，生成final intent、declaration/call demands、operation coverage、deterministic name、partial/complete APISpec、direct CALL_API，以及可审计diagnostics/provenance/snapshot。

明确不包含：handoff-backed扩展、自动完整OpenAPI、runtime API discovery、SPL Editing repair、删除routes.integrations schema、任意tool ontology。
