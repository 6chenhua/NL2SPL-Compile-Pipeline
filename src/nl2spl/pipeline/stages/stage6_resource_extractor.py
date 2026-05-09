"""Stage 6: ResourceExtractor - Extract variables, files, APIs, types."""

from __future__ import annotations

import json
from dataclasses import asdict

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
from nl2spl.pipeline.stages.base import PipelineStage


class ResourceExtractor(
    PipelineStage[
        tuple[list[SpanIR], FieldRouteIR]
        | tuple[list[SpanIR], FieldRouteIR, FlowStructureIR, BlockStructureIR],
        tuple[ResourceRegistryIR, SymbolTable],
    ]
):
    """Extract resources (variables, files, APIs, types) from spans.

    This stage takes behavior and integrations spans, extracts resources,
    and builds a SymbolTable for variable management.
    """

    @property
    def name(self) -> str:
        """Stage name for logging and checkpointing."""
        return "stage6_resource_extractor"

    def execute(
        self,
        input_data: tuple[list[SpanIR], FieldRouteIR]
        | tuple[list[SpanIR], FieldRouteIR, FlowStructureIR, BlockStructureIR],
    ) -> tuple[ResourceRegistryIR, SymbolTable]:
        """Execute resource extraction.

        Args:
            input_data: Tuple of (spans, field routes) or
                (spans, field routes, flow structure, block structure)

        Returns:
            Tuple of (ResourceRegistryIR, SymbolTable)

        Raises:
            StageError: If resource extraction fails
        """
        if len(input_data) == 2:
            spans, routes = input_data
            flow_structure = None
            block_structure = None
        else:
            spans, routes, flow_structure, block_structure = input_data
        self.logger.info(
            "Starting resource extraction with %d spans (%d behavior, %d integrations)",
            len(spans),
            len(routes.behavior),
            len(routes.integrations),
        )

        # 1. Filter behavior and integrations spans
        behavior_spans = [s for s in spans if s.span_id in routes.behavior]
        integrations_spans = [s for s in spans if s.span_id in routes.integrations]

        # 2. Build prompts
        behavior_json = json.dumps(
            [asdict(s) for s in behavior_spans], ensure_ascii=False
        )
        integrations_json = json.dumps(
            [asdict(s) for s in integrations_spans], ensure_ascii=False
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

        system_prompt = load_prompt("stage6")
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

        # 3. Call LLM
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

        # 4. Parse variables
        variables: list[VariableSpec] = []
        for var_data in result.get("variables", []):
            try:
                var = VariableSpec(
                    name=var_data["name"],
                    data_type=var_data["data_type"],
                    required=var_data.get("required", False),
                    description=var_data.get("description", ""),
                    source=var_data.get("source", "step"),
                )
                variables.append(var)
            except (KeyError, ValueError, TypeError) as e:
                self.logger.warning("Skipping invalid variable: %s", e)
                continue

        # 5. Parse files
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
                continue

        # 6. Parse apis
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
                continue

        # 7. Parse types
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
                continue

        # 8. Build ResourceRegistryIR
        resources = ResourceRegistryIR(
            variables=variables,
            files=files,
            apis=apis,
            types=types,
        )

        # 9. Build SymbolTable
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
            len(variables),
            len(files),
            len(apis),
            len(types),
        )

        # 10. Save checkpoint
        self.save_checkpoint({
            "resources": asdict(resources),
            "symbol_table": {
                name: asdict(var) for name, var in symbol_table.variables.items()
            },
        })

        return resources, symbol_table
