"""Legacy (global) methods for Stage 6 ResourceExtractor."""

from __future__ import annotations

import json
from dataclasses import asdict

from nl2spl.canonical import CanonicalCompileInput, VariableFact
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
)
from nl2spl.ir.span_ir import SpanIR
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.llm.prompts import load_prompt
from nl2spl.pipeline.stages.stage6_resource_extractor.context_builder import (
    build_resource_context,
)
from nl2spl.pipeline.stages.stage6_resource_extractor.resource_name_filter import (
    is_allowed_resource_variable,
)


class LegacyMethodsMixin:
    """Mixin containing legacy (global) resource extraction methods."""

    def execute(
        self,
        input_data: tuple[list[SpanIR], FieldRouteIR]
        | tuple[list[SpanIR], FieldRouteIR, FlowStructureIR, BlockStructureIR]
        | tuple[
            list[SpanIR],
            FieldRouteIR,
            FlowStructureIR,
            BlockStructureIR,
            CanonicalCompileInput,
        ],
    ) -> tuple[ResourceRegistryIR, SymbolTable]:
        """Execute resource extraction (legacy global path)."""
        canonical_input: CanonicalCompileInput | None = None
        if len(input_data) == 2:
            spans, routes = input_data
            flow_structure = None
            block_structure = None
        elif len(input_data) == 4:
            spans, routes, flow_structure, block_structure = input_data
        else:
            spans, routes, flow_structure, block_structure, canonical_input = input_data
        self.logger.info(
            "Starting resource extraction with %d spans (%d behavior, %d integrations)",
            len(spans),
            len(routes.behavior),
            len(routes.integrations),
        )

        system_prompt = load_prompt("stage6")
        if self.config.enable_stage6_resource_context_v2:
            user_prompt = build_resource_context(
                spans=spans,
                routes=routes,
                flow=flow_structure,
                blocks=block_structure,
                canonical_input=canonical_input,
                scope_kind="global",
            )
        else:
            behavior_spans = [s for s in spans if s.span_id in routes.behavior]
            integrations_spans = [s for s in spans if s.span_id in routes.integrations]

            behavior_json = json.dumps(
                [s.to_dict() for s in behavior_spans], ensure_ascii=False
            )
            integrations_json = json.dumps(
                [s.to_dict() for s in integrations_spans], ensure_ascii=False
            )
            structure_context = ""
            if flow_structure is not None and block_structure is not None:
                flow_json = json.dumps(asdict(flow_structure), ensure_ascii=False)
                blocks_json = json.dumps(asdict(block_structure), ensure_ascii=False)
                structure_context = f"""

flow structure:
---
{flow_json}
---

block structure:
---
{blocks_json}
---"""

            user_prompt = f"""请从以下文本中提取资源：

behavior spans：
---
{behavior_json}
---

integrations spans：
---
{integrations_json}
---
{structure_context}

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

        self.resource_filter_warnings = list(filter_warnings)

        resources = ResourceRegistryIR(
            variables=variables,
            files=files,
            apis=apis,
            types=types,
        )

        symbol_table = SymbolTable()
        for var in variables:
            symbol_table.declare(
                name=var.name,
                data_type=var.data_type,
                source=var.source,
                description=var.description,
            )

        self.logger.info(
            "Extracted %d variables, %d files, %d APIs, %d types",
            len(variables), len(files), len(apis), len(types),
        )

        self.save_checkpoint({
            "resources": asdict(resources),
            "symbol_table": {
                name: asdict(var) for name, var in symbol_table.variables.items()
            },
            "adapter_merge_warnings": merge_warnings,
        })

        return resources, symbol_table

    def _merge_hard_fact_variables(
        self,
        variables: list[VariableSpec],
        canonical_input: CanonicalCompileInput,
    ) -> tuple[list[VariableSpec], list[str]]:
        """Merge hard fact variables with LLM variables, preferring hard facts."""
        warnings: list[str] = []
        hard_fact_specs = [
            self._variable_from_fact(fact, "input")
            for fact in canonical_input.hard_facts.inputs
        ] + [
            self._variable_from_fact(fact, "output")
            for fact in canonical_input.hard_facts.outputs
        ]

        merged: dict[str, VariableSpec] = {var.name: var for var in hard_fact_specs}
        hard_fact_names = set(merged)

        for var in variables:
            existing = merged.get(var.name)
            if existing is None:
                merged[var.name] = var
                continue
            if var.name in hard_fact_names:
                if existing.data_type != var.data_type:
                    warnings.append(
                        f"Hard fact variable {var.name} keeps type {existing.data_type}; "
                        f"LLM suggested {var.data_type}."
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
    def _variable_from_fact(fact: VariableFact, source: str) -> VariableSpec:
        return VariableSpec(
            name=fact.name,
            data_type=fact.data_type,
            required=fact.required,
            description=fact.description,
            source=source,
        )
