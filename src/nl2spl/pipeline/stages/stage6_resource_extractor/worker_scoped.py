"""Worker-scoped methods for Stage 6 ResourceExtractor."""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Literal

from nl2spl.canonical import CanonicalCompileInput
from nl2spl.errors.exceptions import StageError
from nl2spl.ir.block_structure_ir import BlockStructureIR
from nl2spl.ir.field_route_ir import FieldRouteIR
from nl2spl.ir.flow_structure_ir import FlowStructureIR
from nl2spl.ir.resource_registry_ir import (
    APIFunction,
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
from nl2spl.pipeline.stages.stage6_resource_extractor.context_builder import (
    build_resource_context,
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
    ) -> tuple[WorkerScopedResourceIR, SymbolTable]:
        """Execute worker-scoped resource extraction.

        Workflow:
        1. Extract global resources (from main worker)
        2. For each child worker, extract child resources with declare_scoped()
        3. Extract handoff contracts
        4. Return WorkerScopedResourceIR
        """
        symbol_table = SymbolTable()
        worker_scoped_resources = WorkerScopedResourceIR()
        self.resource_filter_warnings: list[str] = []

        # 1. Extract global resources (from main worker)
        main_worker_id = worker_plan.main_worker_id
        main_flow = worker_flow_plan.worker_flows.get(main_worker_id)
        main_blocks = worker_block_plan.worker_blocks.get(main_worker_id)
        main_worker_spec = worker_plan.main_worker

        if main_flow is not None and main_blocks is not None:
            main_span_ids = (
                set(main_worker_spec.owned_span_ids)
                if main_worker_spec is not None
                else set()
            )
            main_spans = [s for s in spans if s.span_id in main_span_ids]
            main_routes = FieldRouteIR(
                behavior=[s for s in routes.behavior if s in main_span_ids],
                integrations=[s for s in routes.integrations if s in main_span_ids],
                annotations=[a for a in routes.annotations
                             if a.span_id in main_span_ids],
            )
            global_resources, symbol_table = self._extract_resources_for_scope(
                spans=main_spans,
                routes=main_routes,
                flow=main_flow,
                blocks=main_blocks,
                symbol_table=symbol_table,
                canonical_input=canonical_input,
                scope_kind="global",
                scope_id=None,
                worker_spec=main_worker_spec,
            )
            worker_scoped_resources.global_resources = global_resources

        # 2. Extract resources for each child worker
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

            worker_span_ids = set(worker.owned_span_ids)
            worker_spans = [s for s in spans if s.span_id in worker_span_ids]
            worker_routes = FieldRouteIR(
                behavior=[s for s in routes.behavior if s in worker_span_ids],
                integrations=[s for s in routes.integrations if s in worker_span_ids],
                annotations=[a for a in routes.annotations
                             if a.span_id in worker_span_ids],
            )

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
            )
            worker_scoped_resources.worker_resources[worker_id] = worker_resources

        # 3. Extract handoff contracts
        for handoff in worker_plan.handoffs:
            contract = self._build_handoff_contract(handoff, symbol_table)
            worker_scoped_resources.handoff_contracts[handoff.handoff_id] = contract

        self.logger.info(
            "Extracted worker-scoped resources: %d global variables, %d workers, %d handoffs",
            len(worker_scoped_resources.global_resources.variables),
            len(worker_scoped_resources.worker_resources),
            len(worker_scoped_resources.handoff_contracts),
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
    ) -> tuple[ResourceRegistryIR, SymbolTable]:
        """Extract resources for a specific scope (LLM call + parsing)."""
        system_prompt = load_prompt("stage6")
        if self.config.enable_stage6_resource_context_v2:
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
            )
        else:
            behavior_json = json.dumps(
                [s.to_dict() for s in spans if s.span_id in routes.behavior],
                ensure_ascii=False,
            )
            integrations_json = json.dumps(
                [s.to_dict() for s in spans if s.span_id in routes.integrations],
                ensure_ascii=False,
            )
            structure_context = ""
            if flow is not None and blocks is not None:
                flow_json = json.dumps(asdict(flow), ensure_ascii=False)
                blocks_json = json.dumps(asdict(blocks), ensure_ascii=False)
                structure_context = f"""

flow structure:
---
{flow_json}
---

block structure:
---
{blocks_json}
---"""

            worker_context = ""
            if worker_spec is not None:
                lines: list[str] = [
                    f"  name: {worker_spec.worker_name}",
                    f"  kind: {worker_spec.kind}",
                    f"  purpose: {worker_spec.purpose}",
                ]
                if worker_spec.input_contract:
                    lines.append("  inputs:")
                    for field in worker_spec.input_contract:
                        lines.append(
                            f"    - {field.name}: {field.data_type} "
                            f"(required={field.required}) - {field.description}"
                        )
                if worker_spec.output_contract:
                    lines.append("  outputs:")
                    for field in worker_spec.output_contract:
                        lines.append(
                            f"    - {field.name}: {field.data_type} "
                            f"(required={field.required}) - {field.description}"
                        )
                worker_context = f"""

worker context:
{chr(10).join(lines)}
"""

            known_vars = symbol_table.get_variable_list_for_worker_prompt(
                scope_id or "main"
            )
            known_vars_context = ""
            if known_vars != "No variables available.":
                known_vars_context = f"""

known variables:
{known_vars}
"""

            user_prompt = f"""请从以下文本中提取资源：

behavior spans：
---
{behavior_json}
---

integrations spans：
---
{integrations_json}
---
{structure_context}{worker_context}{known_vars_context}

输出 JSON："""

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
        # D5: identify failure mode span texts for variable filtering
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
                if self.config.enable_resource_name_filter:
                    allowed, reason = is_allowed_resource_variable(name)
                    if not allowed:
                        filter_warnings.append(
                            f"Rejected schema-looking variable '{name}': {reason}"
                        )
                        continue
                # D5: reject variables derived from failure condition text
                if failure_texts:
                    var_text = (
                        name.replace("_", " ").strip().lower()
                        + " " + var_data.get("description", "").strip().lower()
                    )
                    if any(ft in var_text for ft in failure_texts):
                        filter_warnings.append(
                            f"D5: rejected failure-derived variable '{name}'"
                        )
                        continue
                var = VariableSpec(
                    name=name,
                    data_type=var_data["data_type"],
                    required=var_data.get("required", False),
                    description=var_data.get("description", ""),
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
                functions: list[APIFunction] = []
                for func_data in api_data.get("functions", []):
                    func = APIFunction(
                        name=func_data["name"],
                        description=func_data.get("description", ""),
                        parameters=func_data.get("parameters", []),
                        return_type=func_data.get("return_type", "text"),
                    )
                    functions.append(func)
                api = APISpec(
                    api_name=api_data["api_name"],
                    auth=api_data.get("auth", "none"),
                    description=api_data.get("description", ""),
                    functions=functions,
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
            len(variables), len(files), len(apis), len(types),
            scope_kind, scope_id,
        )

        return resources, symbol_table

    def _merge_contract_variables(
        self,
        variables: list[VariableSpec],
        worker_spec: WorkerSpecIR,
    ) -> tuple[list[VariableSpec], list[str]]:
        """Merge worker contract variables, preferring explicit contract facts."""
        warnings: list[str] = []
        contract_specs = [
            self._variable_from_contract(field)
            for field in worker_spec.input_contract + worker_spec.output_contract
        ]
        merged: dict[str, VariableSpec] = {var.name: var for var in contract_specs}
        contract_names = set(merged)

        for var in variables:
            existing = merged.get(var.name)
            if existing is None:
                merged[var.name] = var
                continue
            if var.name in contract_names:
                if existing.data_type != var.data_type:
                    warnings.append(
                        f"Worker contract variable {var.name} keeps type "
                        f"{existing.data_type}; LLM suggested {var.data_type}."
                    )
                if existing.description != var.description and var.description:
                    existing.description = (
                        f"{existing.description} (LLM note: {var.description})"
                    )
                existing.required = existing.required or var.required
                continue
            if existing.data_type == var.data_type:
                existing.required = existing.required or var.required
                if not existing.description and var.description:
                    existing.description = var.description
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
            description=field.description,
            source=field.source,
        )

    def _build_handoff_contract(
        self,
        handoff: WorkerHandoffIR,
        symbol_table: SymbolTable,
    ) -> HandoffContractIR:
        """Build handoff contract from WorkerHandoffIR.

        Looks up variables using scoped access: parent-worker variables for
        input bindings, child-worker variables for output bindings.
        """
        parent_vars = symbol_table.get_variables_for_worker(handoff.from_worker)
        child_vars = symbol_table.get_variables_for_worker(
            handoff.to_worker or ""
        )

        input_variables: list[ContractFieldIR] = []
        for binding in handoff.input_bindings:
            var = parent_vars.get(
                binding.parent_variable
            ) or symbol_table.lookup(binding.parent_variable)
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
            var = child_vars.get(
                binding.child_output
            ) or symbol_table.lookup(binding.child_output)
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
