# handoff — 交叉交接文档

此目录保存跨轮次、跨会话的**问题记录、重构方案与实施计划**。文档面向接手开发者，不面向运行时行为描述。

---

## 文档一览

| 文件 | 内容 |
|------|------|
| **[irs_constructplan_implementation_issues.md](irs_constructplan_implementation_issues.md)** | IRS / ConstructPlan 当前实现的**集成问题与架构风险清单**。记录了两个 P0 阻塞项（旧 config flag、Stage 4 输入 arity）和四个架构风险（ConstructPlan 过于 EXCEPTION_FLOW-specific、Stage 4 多路径物化、stage-local 与 post-normalize 权威边界、语义冲突分析器为 no-op）。含修复优先级与具体任务拆分。 |
| **[irs_constructs_refactor_design.md](irs_constructs_refactor_design.md)** | IRS / Constructs **代码组织重构设计文档**。定义了目标 package 分层架构，分析当前 `construct_registry → irs.frontier` 的反向依赖问题，给出分层原则、模块归属决策和兼容迁移策略。**不涉及行为变更**。 |
| **[irs_constructs_refactor_implementation_plan.md](irs_constructs_refactor_implementation_plan.md)** | 上述重构的**8 阶段实施计划**。从 Phase 0（基线冻结）到 Phase 8（清理验收），每阶段有明确的文件移动清单、验收标准、风险等级和回滚方式。核心约束：前六个阶段不改编译行为。 |
| **[stage2_llm_construct_target_hallucination.md](stage2_llm_construct_target_hallucination.md)** | Stage 2 LLM 输出的 `construct_target` 与 `semantic_role` **矛盾问题记录**。LLM 对 `sec_task_family` span 输出了 `semantic_role=profile_domain` + `construct_target=RESOURCE_CONTRACT` 的矛盾组合，分析混淆原因、影响范围，并给出短期/中期/长期修复方向。 |
| **[stage2_llm_output_simplification.md](stage2_llm_output_simplification.md)** | Stage 2 LLM 输出字段从 13 个精简到 2-3 个的**架构方案**。LLM 只输出 `semantic_role`，`field` / `route_family` / `construct_target` / `slot_target` / `executable` 全部由确定性映射表推导。含完整映射表、四阶段实施路径，以及如何从根本上消除 construct_target 矛盾 bug。 |
| **[resource_contract_planner_overengineering.md](resource_contract_planner_overengineering.md)** | `ResourceContractPlanner` **过度设计分析**。论证其三条规则中两条是冗余的（字段重映射）、一条是换了马甲的 hardcoding（section 标题匹配），与 `ConstructPlanner` 的跨 span 配对逻辑有本质区别。指出正确的做法是让 Stage 6 直接从 annotation 消费 contract evidence，建议删掉此 planner。 |

---

## 编写约定

- 文件名使用英文下划线命名，内容使用中文
- 每个文档开头标注状态（Draft / In Progress / Resolved）
- 问题文档必须包含"推荐修复方向"或"建议的下一步"
- 已解决的问题不要删除文件，在开头标注状态为 Resolved
