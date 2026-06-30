"""Worker-scoped methods for Stage 6 ResourceExtractor."""

from __future__ import annotations

from typing import Literal

from nl2spl.canonical import CanonicalCompileInput
from nl2spl.errors.exceptions import StageError
from nl2spl.ir.block_structure_ir import BlockStructureIR
from nl2spl.ir.field_route_ir import FieldRouteIR
from nl2spl.ir.flow_structure_ir import FlowStructureIR
from nl2spl.ir.resource_contract_ir import (
    ResourceContractBindingIR,
    ResourceContractFieldIR,
    ResourceContractPlanIR,
)
from nl2spl.ir.resource_registry_ir import (
    APISpec,
    FileSpec,
    ResourceRegistryIR,
    TypeSpec,
    VariableSpec,
    WorkerScopedResourceIR,
)
from nl2spl.ir.span_ir import SpanIR
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.ir.worker_plan_ir import (
    ContractFieldIR,
    HandoffContractIR,
    WorkerBlockPlanIR,
    WorkerFlowPlanIR,
    WorkerHandoffIR,
    WorkerPlanIR,
    WorkerSpecIR,
)
from nl2spl.llm.prompts import load_prompt
from nl2spl.pipeline.stages.stage6_resource_extractor.api_contract_extraction import (
    api_spec_from_extracted_contract,
)
from nl2spl.pipeline.stages.stage6_resource_extractor.context_builder import (
    build_resource_context,
)
from nl2spl.pipeline.stages.stage6_resource_extractor.description_cleaner import (
    clean_resource_description,
)
from nl2spl.pipeline.stages.stage6_resource_extractor.resource_name_filter import (
    is_allowed_resource_variable,
)


class WorkerScopedMixin:
    """Mixin containing worker-scoped resource extraction methods."""

    def execute_worker_scoped(
        self,
        spans: list[SpanIR],
        routes: FieldRouteIR,
        worker_flow_plan: WorkerFlowPlanIR,
        worker_block_plan: WorkerBlockPlanIR,
        worker_plan: WorkerPlanIR,
        canonical_input: CanonicalCompileInput | None = None,
        resource_contract_plan: ResourceContractPlanIR | None = None,
        demand_view: object | None = None,  # ResourceContractDemandView
    ) -> tuple[WorkerScopedResourceIR, SymbolTable]:
        """对每个 worker 独立执行 LLM 资源提取，互不干扰。

        核心思路：按 worker 裁剪 span / route 数据，每个 worker 只看到
        自己拥有的 span 子集。最后通过 SymbolTable 的 scoped 机制
        隔离同名变量。
        """
        symbol_table = SymbolTable()
        worker_scoped_resources = WorkerScopedResourceIR()
        self.resource_filter_warnings: list[str] = []
        self._contract_bindings: list[ResourceContractBindingIR] = []

        # —— 阶段 1：提取 main worker 的全局资源 ——
        # main worker 传入 canonical_input，可以消费 adapter 提取的精确变量。
        main_worker_id = worker_plan.main_worker_id
        main_flow = worker_flow_plan.worker_flows.get(main_worker_id)
        main_blocks = worker_block_plan.worker_blocks.get(main_worker_id)
        main_worker_spec = worker_plan.main_worker

        if main_flow is not None and main_blocks is not None:
            # 裁剪：只保留属于 main worker 的 span 和 route
            main_span_ids = (
                set(main_worker_spec.owned_span_ids) if main_worker_spec is not None else set()
            )
            main_spans = [s for s in spans if s.span_id in main_span_ids]
            main_routes = FieldRouteIR(
                behavior=[s for s in routes.behavior if s in main_span_ids],
                integrations=[s for s in routes.integrations if s in main_span_ids],
                annotations=[a for a in routes.annotations if a.span_id in main_span_ids],
            )
            global_resources, symbol_table = self._extract_resources_for_scope(
                spans=main_spans,
                routes=main_routes,
                flow=main_flow,
                blocks=main_blocks,
                symbol_table=symbol_table,
                canonical_input=canonical_input,
                scope_kind="global",
                demand_view=demand_view,
                scope_id=None,
                worker_spec=main_worker_spec,
                resource_contract_plan=resource_contract_plan,
            )
            worker_scoped_resources.global_resources = global_resources

        # —— 阶段 2：为每个 child worker 独立提取资源 ——
        for worker in worker_plan.workers:
            if worker.kind == "main":
                continue

            worker_id = worker.worker_id
            flow = worker_flow_plan.worker_flows.get(worker_id)
            blocks = worker_block_plan.worker_blocks.get(worker_id)

            if flow is None or blocks is None:
                self.logger.warning(
                    "Worker %s missing flow/blocks, skipping resource extraction",
                    worker_id,
                )
                continue

            # 同样裁剪 span 数据，让 LLM 只看到当前 worker 的上下文
            worker_span_ids = set(worker.owned_span_ids)
            worker_spans = [s for s in spans if s.span_id in worker_span_ids]
            worker_routes = FieldRouteIR(
                behavior=[s for s in routes.behavior if s in worker_span_ids],
                integrations=[s for s in routes.integrations if s in worker_span_ids],
                annotations=[a for a in routes.annotations if a.span_id in worker_span_ids],
            )

            # child worker 不传 canonical_input——它的变量来源是 contract，不是原始输入。
            # 也不传 demand_view——child worker 通过 worker_spec.input_contract/
            # output_contract 获取已分配的 contract fields，不需要全局 DemandView。
            worker_resources, symbol_table = self._extract_resources_for_scope(
                spans=worker_spans,
                routes=worker_routes,
                flow=flow,
                blocks=blocks,
                symbol_table=symbol_table,
                canonical_input=None,
                scope_kind="worker",
                scope_id=worker_id,
                worker_spec=worker,
                demand_view=None,
            )
            worker_scoped_resources.worker_resources[worker_id] = worker_resources

        # —— 阶段 3：构建 handoff 合约 ——
        for handoff in worker_plan.handoffs:
            contract = self._build_handoff_contract(handoff, symbol_table)
            worker_scoped_resources.handoff_contracts[handoff.handoff_id] = contract

        worker_scoped_resources.resource_contract_bindings = list(self._contract_bindings)

        self.logger.info(
            "Extracted worker-scoped resources: %d global variables, "
            "%d workers, %d handoffs, %d bindings",
            len(worker_scoped_resources.global_resources.variables),
            len(worker_scoped_resources.worker_resources),
            len(worker_scoped_resources.handoff_contracts),
            len(worker_scoped_resources.resource_contract_bindings),
        )

        return worker_scoped_resources, symbol_table

    def _extract_resources_for_scope(
        self,
        spans: list[SpanIR],
        routes: FieldRouteIR,
        flow: FlowStructureIR,
        blocks: BlockStructureIR,
        symbol_table: SymbolTable,
        canonical_input: CanonicalCompileInput | None = None,
        scope_kind: Literal["global", "worker", "handoff"] = "global",
        scope_id: str | None = None,
        worker_spec: WorkerSpecIR | None = None,
        resource_contract_plan: ResourceContractPlanIR | None = None,
        demand_view: object | None = None,
    ) -> tuple[ResourceRegistryIR, SymbolTable]:
        """对单个 scope 执行 LLM 资源提取：build prompt → LLM → 解析 JSON → 过滤 → 合并。"""
        system_prompt = load_prompt("stage6")
        user_prompt = build_resource_context(
            spans=spans,
            routes=routes,
            flow=flow,
            blocks=blocks,
            symbol_table=symbol_table,
            canonical_input=canonical_input,
            worker_spec=worker_spec,
            scope_kind=scope_kind,
            scope_id=scope_id,
            resource_contract_plan=resource_contract_plan,
            demand_view=demand_view,
        )

        try:
            result = self.client.call_json(
                stage_name=self.name,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
        except Exception as e:
            self.logger.error("LLM call failed: %s", e)
            raise StageError(
                message=f"LLM call failed in {self.name}: {e}",
                stage=self.name,
            ) from e

        variables: list[VariableSpec] = []
        filter_warnings: list[str] = []

        # —— 过滤层 1：D5——拦截从 failure condition 文本中误提取的变量 ——
        # LLM 有时会把 "API timeout" 这类 condition 文本当成变量名，
        # 这里收集当前 scope 内所有 failure_mode span 的文本做子串拦截。
        failure_texts: set[str] = set()
        if routes.annotations:
            for a in routes.annotations:
                if a.semantic_role == "failure_mode" and a.executable is False:
                    span = next((s for s in spans if s.span_id == a.span_id), None)
                    if span:
                        failure_texts.add(span.text.strip().rstrip(".").lower())
        for var_data in result.get("variables", []):
            try:
                name = var_data["name"]
                # 过滤层 2：拒绝 schema/IR 风格的变量名（如 flow_id、block_type）
                allowed, reason = is_allowed_resource_variable(name)
                if not allowed:
                    filter_warnings.append(f"Rejected schema-looking variable '{name}': {reason}")
                    continue
                # D5 过滤：变量名或描述包含 failure condition 文本则拒绝
                if failure_texts:
                    var_text = (
                        name.replace("_", " ").strip().lower()
                        + " "
                        + var_data.get("description", "").strip().lower()
                    )
                    if any(ft in var_text for ft in failure_texts):
                        filter_warnings.append(f"D5: rejected failure-derived variable '{name}'")
                        continue
                var = VariableSpec(
                    name=name,
                    data_type=var_data["data_type"],
                    required=var_data.get("required", False),
                    description=clean_resource_description(name, var_data.get("description", "")),
                    source=var_data.get("source", "step"),
                )
                variables.append(var)
            except (KeyError, ValueError, TypeError) as e:
                self.logger.warning("Skipping invalid variable: %s", e)

        files: list[FileSpec] = []
        for file_data in result.get("files", []):
            try:
                file_spec = FileSpec(
                    name=file_data["name"],
                    path=file_data.get("path", "<runtime>"),
                    data_type=file_data.get("data_type", "text"),
                    description=file_data.get("description", ""),
                )
                files.append(file_spec)
            except (KeyError, ValueError, TypeError) as e:
                self.logger.warning("Skipping invalid file: %s", e)

        apis: list[APISpec] = []
        for api_data in result.get("apis", []):
            try:
                api = api_spec_from_extracted_contract(
                    api_data,
                    valid_source_span_ids={span.span_id for span in spans},
                )
                apis.append(api)
            except (KeyError, ValueError, TypeError) as e:
                self.logger.warning("Skipping invalid API: %s", e)

        types: list[TypeSpec] = []
        for type_data in result.get("types", []):
            try:
                type_spec = TypeSpec(
                    type_name=type_data["type_name"],
                    type_kind=type_data.get("type_kind", "structured"),
                    definition=type_data.get("definition", ""),
                )
                types.append(type_spec)
            except (KeyError, ValueError, TypeError) as e:
                self.logger.warning("Skipping invalid type: %s", e)

        # —— resource_contracts：LLM 显式 materialize 的资源合约 ——
        resource_contract_fields: list[ResourceContractFieldIR] = []
        for rc_data in result.get("resource_contracts", []):
            try:
                rc_kind = rc_data.get("resource_kind", "variable")
                if rc_kind not in ("variable", "file", "api", "type"):
                    self.logger.warning("Skipping resource_contract with unknown kind: %s", rc_kind)
                    continue
                # B4: resolve authoritative requiredness BEFORE any side effects.
                # DemandView is the authority when present; LLM is fallback.
                authoritative_rq: str | None = None
                authoritative_req: bool | None = None
                if demand_view is not None:
                    dv_demands = getattr(
                        demand_view, "valid_demands", lambda: getattr(demand_view, "demands", ())
                    )()
                    found = False
                    for d in dv_demands:
                        if getattr(d, "demand_id", None) == rc_data["demand_id"]:
                            authoritative_rq = getattr(d, "requiredness", None)
                            authoritative_req = getattr(d, "required", None)
                            found = True
                            break
                    if not found:
                        self.logger.warning(
                            "Unknown demand_id %s in LLM resource_contracts "
                            "output; DemandView present but no match. Skipping.",
                            rc_data["demand_id"],
                        )
                        continue  # reject — no binding, no field, no resource
                    llm_rq = rc_data.get("requiredness")
                    if llm_rq is not None and llm_rq != authoritative_rq:
                        self.logger.warning(
                            "LLM requiredness %s disagrees with DemandView %s "
                            "for demand %s; using DemandView.",
                            llm_rq,
                            authoritative_rq,
                            rc_data["demand_id"],
                        )
                else:
                    authoritative_rq = rc_data.get("requiredness", "unspecified")
                    authoritative_req = rc_data.get("required")

                # Validate requiredness value
                if authoritative_rq not in ("required", "optional", "unspecified"):
                    self.logger.warning(
                        "Invalid requiredness '%s' for demand %s; falling back to unspecified.",
                        authoritative_rq,
                        rc_data["demand_id"],
                    )
                    authoritative_rq = "unspecified"
                    authoritative_req = None

                # Create binding
                self._contract_bindings.append(
                    ResourceContractBindingIR(
                        contract_demand_id=rc_data["demand_id"],
                        resource_name=rc_data["name"],
                        resource_kind=rc_kind,  # type: ignore[arg-type]
                        direction=rc_data.get("direction", "output"),
                        scope_kind=scope_kind,  # type: ignore[arg-type]
                        scope_id=scope_id,
                        source_span_ids=rc_data.get("source_span_ids", []),
                        source_section_id=rc_data.get("source_section_id"),
                        source_packet_id=rc_data.get("source_packet_id"),
                    )
                )

                resource_contract_fields.append(
                    ResourceContractFieldIR(
                        demand_id=rc_data["demand_id"],
                        name=rc_data["name"],
                        resource_kind=rc_kind,  # type: ignore[arg-type]
                        direction=rc_data.get("direction", "output"),
                        data_type=rc_data.get("data_type", "text"),
                        required=authoritative_req,
                        requiredness=authoritative_rq,  # type: ignore[arg-type]
                        description=rc_data.get("description", ""),
                        path=rc_data.get("path"),
                        source_span_ids=rc_data.get("source_span_ids", []),
                        source_section_id=rc_data.get("source_section_id"),
                        source_packet_id=rc_data.get("source_packet_id"),
                        evidence_text=rc_data.get("evidence_text"),
                        justification=rc_data.get("justification"),
                    )
                )

                if rc_kind == "file":
                    # Dedup: skip if a file with the same name already exists
                    existing_names = {f.name for f in files}
                    if rc_data["name"] not in existing_names:
                        files.append(
                            FileSpec(
                                name=rc_data["name"],
                                path=rc_data.get("path", "< >"),
                                data_type=rc_data.get("data_type", "text"),
                                description=rc_data.get("description", ""),
                            )
                        )
                elif rc_kind == "variable":
                    existing_var_names = {v.name for v in variables}
                    if rc_data["name"] not in existing_var_names:
                        var = VariableSpec(
                            name=rc_data["name"],
                            data_type=rc_data.get("data_type", "text"),
                            required=rc_data.get("required", False),
                            description=clean_resource_description(
                                rc_data["name"], rc_data.get("description", "")
                            ),
                            source=rc_data.get("direction", "output"),
                        )
                        variables.append(var)
                elif rc_kind == "api":
                    existing_api_names = {api.api_name for api in apis}
                    if rc_data["name"] not in existing_api_names:
                        apis.append(
                            APISpec(
                                api_name=rc_data["name"],
                                auth=rc_data.get("auth") or "none",
                                description=rc_data.get("description", ""),
                                functions=[],
                            )
                        )
                elif rc_kind == "type":
                    existing_type_names = {t.type_name for t in types}
                    if rc_data["name"] not in existing_type_names:
                        types.append(
                            TypeSpec(
                                type_name=rc_data["name"],
                                type_kind=rc_data.get("data_type", "record"),
                                definition=(
                                    rc_data.get("definition")
                                    or rc_data.get("description")
                                    or rc_data.get("data_type", "record")
                                ),
                            )
                        )
            except (KeyError, ValueError, TypeError) as e:
                self.logger.warning("Skipping invalid resource_contract entry: %s", e)

        if worker_spec is not None and resource_contract_fields:
            self._sync_resource_contract_fields_to_worker(
                worker_spec,
                resource_contract_fields,
            )

        # —— 合并层：LLM 提取的变量与精确来源合并 ——
        # 合并优先顺序：hard facts（adapter） > contract（Stage 3.5） > LLM 推断
        merge_warnings: list[str] = []
        if canonical_input is not None and canonical_input.source_schema != "generic_nl":
            variables, merge_warnings = self._merge_hard_fact_variables(
                variables,
                canonical_input,
            )
        if worker_spec is not None:
            variables, contract_warnings = self._merge_contract_variables(
                variables,
                worker_spec,
            )
            merge_warnings.extend(contract_warnings)

        resources = ResourceRegistryIR(
            variables=variables,
            files=files,
            apis=apis,
            types=types,
        )

        for var in variables:
            symbol_table.declare_scoped(
                name=var.name,
                data_type=var.data_type,
                source=var.source,
                description=var.description,
                scope_kind=scope_kind,
                scope_id=scope_id,
            )

        if not hasattr(self, "resource_filter_warnings"):
            self.resource_filter_warnings = list(filter_warnings)
        else:
            self.resource_filter_warnings.extend(filter_warnings)

        self.logger.info(
            "Extracted %d variables, %d files, %d APIs, %d types for scope %s:%s",
            len(variables),
            len(files),
            len(apis),
            len(types),
            scope_kind,
            scope_id,
        )

        return resources, symbol_table

    def _merge_contract_variables(
        self,
        variables: list[VariableSpec],
        worker_spec: WorkerSpecIR,
    ) -> tuple[list[VariableSpec], list[str]]:
        """合并 worker contract 变量，contract 声明优先于 LLM 推断。

        - contract 变量已存在的，LLM 不能覆盖其类型
        - contract 中没有的，保留 LLM 推断的变量
        - 类型冲突时以先到者为准，记录 warning
        """
        warnings: list[str] = []
        # contract 变量先入 merged，占据 key
        contract_specs = [
            self._variable_from_contract(field)
            for field in worker_spec.input_contract + worker_spec.output_contract
            if field.name and (field.resource_kind in (None, "variable"))
        ]
        merged: dict[str, VariableSpec] = {var.name: var for var in contract_specs}
        contract_names = set(merged)

        for var in variables:
            existing = merged.get(var.name)
            if existing is None:
                # contract 中没有 → 保留 LLM 推断
                merged[var.name] = var
                continue
            if var.name in contract_names:
                # contract 变量：类型不可覆盖，只补充 required 标志
                if existing.data_type != var.data_type:
                    warnings.append(
                        f"Worker contract variable {var.name} keeps type "
                        f"{existing.data_type}; LLM suggested {var.data_type}."
                    )
                existing.required = existing.required or var.required
                continue
            # 非 contract 变量：同名但来自其他 scope，类型一致则合并描述
            if existing.data_type == var.data_type:
                existing.required = existing.required or var.required
                if not existing.description and var.description:
                    existing.description = clean_resource_description(var.name, var.description)
            else:
                warnings.append(
                    f"Variable {var.name} has conflicting inferred types: "
                    f"{existing.data_type} vs {var.data_type}; keeping first."
                )

        return list(merged.values()), warnings

    @staticmethod
    def _variable_from_contract(field: ContractFieldIR) -> VariableSpec:
        return VariableSpec(
            name=field.name,
            data_type=field.data_type,
            required=field.required,
            description=clean_resource_description(field.name, field.description),
            source=field.source,
        )

    @staticmethod
    def _sync_resource_contract_fields_to_worker(
        worker_spec: WorkerSpecIR,
        fields: list[ResourceContractFieldIR],
    ) -> None:
        """Backfill worker contract fields from Stage 6 materialization.

        Stage 3.5 records source demands by ``contract_demand_id`` before
        Stage 6 knows the final resource name/kind/type.  Once Stage 6
        materializes the demand, update the matching worker contract field so
        Stage 10/11 render the resolved resource reference without adding any
        renderer-side inference.
        """
        by_demand = {field.demand_id: field for field in fields}

        def _sync(contract_fields: list[ContractFieldIR]) -> None:
            for field in contract_fields:
                if not field.contract_demand_id:
                    continue
                materialized = by_demand.get(field.contract_demand_id)
                if materialized is None:
                    continue
                field.name = materialized.name
                field.data_type = materialized.data_type
                field.required = materialized.required
                field.requiredness = materialized.requiredness
                field.description = materialized.description or field.description
                field.source_span_ids = list(materialized.source_span_ids)
                field.source_section_id = materialized.source_section_id
                field.source_packet_id = materialized.source_packet_id
                field.resource_kind = materialized.resource_kind

        _sync(worker_spec.input_contract)
        _sync(worker_spec.output_contract)

    def _build_handoff_contract(
        self,
        handoff: WorkerHandoffIR,
        symbol_table: SymbolTable,
    ) -> HandoffContractIR:
        """从 WorkerHandoffIR 构建 handoff 合约。

        input binding：查父 worker 的 scoped 变量 → 映射为 child 的 input。
        output binding：查子 worker 的 scoped 变量 → 映射为 parent 的 output。
        类型信息从 SymbolTable 继承，确保 handoff 两端类型一致。
        """
        parent_vars = symbol_table.get_variables_for_worker(handoff.from_worker)
        child_vars = symbol_table.get_variables_for_worker(handoff.to_worker or "")

        input_variables: list[ContractFieldIR] = []
        for binding in handoff.input_bindings:
            # 优先从父 worker 的 scoped 变量查找，fallback 到全局 lookup
            var = parent_vars.get(binding.parent_variable) or symbol_table.lookup(
                binding.parent_variable
            )
            input_variables.append(
                ContractFieldIR(
                    name=binding.child_input,
                    data_type=var.data_type if var else "text",
                    required=binding.required,
                    description=f"Input from {binding.parent_variable}",
                    source="input",
                )
            )

        output_variables: list[ContractFieldIR] = []
        for binding in handoff.output_bindings:
            # 优先从子 worker 的 scoped 变量查找
            var = child_vars.get(binding.child_output) or symbol_table.lookup(binding.child_output)
            output_variables.append(
                ContractFieldIR(
                    name=binding.parent_variable,
                    data_type=var.data_type if var else "text",
                    required=binding.required,
                    description=f"Output from {binding.child_output}",
                    source="output",
                )
            )

        return HandoffContractIR(
            handoff_id=handoff.handoff_id,
            parent_worker_id=handoff.from_worker,
            child_worker_id=handoff.to_worker or "",
            input_variables=input_variables,
            output_variables=output_variables,
        )
