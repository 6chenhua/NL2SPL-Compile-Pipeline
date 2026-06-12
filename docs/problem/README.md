# docs/problem/ — 问题记录

本目录记录代码库中发现的问题，每个文件描述一个问题及其大致解决方向。
文件不涉及具体设计或实施方案——只记录问题本身和解决思路概要。

---

## 问题列表

| 文件 | 问题概要 | 相关组件 |
|---|---|---|
| [stage2_annotation_contract_empty_main_flow.md](solved/stage2_annotation_contract_empty_main_flow.md) | Stage 2 LLM-facing annotation schema 与 canonical role contract 冲突，导致 `process_step` annotation 被拒绝并连锁造成主流程为空 | Stage 2 Field Router, Annotation Role Contract, Stage 3/4 |
| [producer_index_missing_request_input.md](producer_index_missing_request_input.md) | `ProducerIndex` 的 `ProducerKind` 缺少 `request_input` 类型，未与 SPL 语法 `COMMAND_BODY` 的五种类型对齐 | `ProducerIndex`, SPL Editing |
