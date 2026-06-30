"""IRS v6 APIDeclarationIRSChecker for API_DECLARATION construct.

R-API-1 implementation:
    - Extracts API_DECLARATION instances from context.resources.apis (if any)
    - Checks slot satisfaction against API_DECLARATION ConstructIRS
    - Does NOT call LLM or parse raw NL
    - Does NOT modify input IR or context
    - Does NOT create APISpecs
    - Does NOT emit final blocking CompileDiagnostics directly
"""

from __future__ import annotations

from nl2spl.compiler.construct_registry import (
    ConstructIRS,
    ConstructSatisfactionReport,
    SlotSatisfaction,
)
from nl2spl.compiler.irs.checkers.api_declaration_grammar import (
    validate_api_declaration,
)
from nl2spl.compiler.irs.context import IRSCheckContext
from nl2spl.compiler.irs.instance import ConstructInstance


class APIDeclarationIRSChecker:
    """IRS v6 checker for API_DECLARATION construct.

    Design principles:
        - Only consumes structured IR fields / registry
        - Does not infer semantics from text or call LLM
        - Does not modify context or IR
        - Does not generate new constructs or APISpecs
        - Does not directly emit final blocking CompileDiagnostics
    """

    checker_id = "api_declaration"
    supported_construct_types = ("API_DECLARATION",)
    supported_stages = ("stage6", "post_normalize")

    def extract_instances(self, context: IRSCheckContext) -> list[ConstructInstance]:
        """Extract API_DECLARATION construct instances from context.

        In R-API-1, without ConstructPlan API demands or APIMaterializationPlanIR provenance,
        this extracts materialized instances from context.resources.apis (if any).
        """
        instances: list[ConstructInstance] = []
        if context.resources is not None and hasattr(context.resources, "apis"):
            for api in context.resources.apis:
                instances.append(
                    ConstructInstance(
                        construct_id=f"api_declaration:{api.api_id or api.api_name}",
                        construct_type="API_DECLARATION",
                        materialized=True,
                        source_demanded=True,
                        ir_ref=api,
                        source_span_ids=list(getattr(api, "source_span_ids", [])),
                        construct_path=("resources", "apis", api.api_id or api.api_name),
                        metadata={"api_spec": api},
                    )
                )
        return instances

    def check_instance(
        self,
        instance: ConstructInstance,
        irs: ConstructIRS,
        context: IRSCheckContext,
    ) -> ConstructSatisfactionReport:
        """Check IRS satisfaction for an API_DECLARATION instance."""
        api = instance.metadata.get("api_spec")
        grammar = validate_api_declaration(api) if api is not None else None

        slots_sat: list[SlotSatisfaction] = []

        # 1. api_name
        has_name = bool(api and grammar and grammar.name_valid)
        slots_sat.append(
            SlotSatisfaction(
                slot_name="api_name",
                status="satisfied" if has_name else "missing",
                relation="direct" if has_name else None,
                diagnostic_kind=None if has_name else "type_or_contract_ambiguity",
                diagnostic_required_for="render",
                diagnostic_blocks_rendering=not has_name,
                explanation=(
                    "API name is grammar-safe."
                    if has_name
                    else "API name is missing or not grammar-safe."
                ),
            )
        )

        # 2. source_evidence
        source_spans = list(getattr(api, "source_span_ids", [])) if api else []
        has_source_evidence = bool(
            source_spans
            or (
                api
                and getattr(api, "origin", None)
                in ("configured_resource", "user_confirmed_repair", "adapter_hard_fact")
            )
        )
        slots_sat.append(
            SlotSatisfaction(
                slot_name="source_evidence",
                status="satisfied" if has_source_evidence else "missing",
                source_span_ids=source_spans,
                relation="direct" if has_source_evidence else None,
                explanation="Source evidence present."
                if has_source_evidence
                else "Missing source evidence.",
            )
        )

        # 3. authentication
        auth_status = (
            getattr(api, "auth_status", "compiler_default_none") if api else "compiler_default_none"
        )
        auth_valid = bool(grammar and grammar.auth_valid)
        auth_satisfied = auth_valid and auth_status != "compiler_default_none"
        slots_sat.append(
            SlotSatisfaction(
                slot_name="authentication",
                status=("satisfied" if auth_satisfied else "assumed" if auth_valid else "missing"),
                relation="direct" if auth_satisfied else "assumed" if auth_valid else None,
                diagnostic_kind=None if auth_valid else "type_or_contract_ambiguity",
                diagnostic_required_for="render",
                diagnostic_blocks_rendering=not auth_valid,
                explanation=(
                    "Authentication specified."
                    if auth_satisfied
                    else "Compiler default auth <none>."
                    if auth_valid
                    else "Authentication is unresolved or outside the grammar."
                ),
            )
        )

        # 4. openapi_schema
        schema_spec = irs.get_slot("openapi_schema")
        schema_status = (
            getattr(api, "schema_status", "unknown_placeholder") if api else "unknown_placeholder"
        )
        schema_grammar_valid = bool(grammar and grammar.schema_valid)
        schema_satisfied = schema_grammar_valid and schema_status in (
            "known_present",
            "known_empty",
        )
        schema_blocks_rendering = not schema_grammar_valid or bool(
            grammar and grammar.status == "partial_blocked"
        )
        schema_is_deferred = bool(
            grammar
            and grammar.status == "grammar_minimal_partial"
            and schema_grammar_valid
            and schema_status == "unknown_placeholder"
        )
        slots_sat.append(
            SlotSatisfaction(
                slot_name="openapi_schema",
                status="satisfied" if schema_satisfied else "missing",
                relation="direct" if schema_satisfied else None,
                diagnostic_kind=(
                    None
                    if schema_satisfied
                    else "deferred_api_contract_validation"
                    if schema_is_deferred
                    else schema_spec.missing_diagnostic
                    if schema_spec
                    else "type_or_contract_ambiguity"
                ),
                diagnostic_required_for=(
                    "downstream_api_validation" if schema_is_deferred else "render"
                ),
                diagnostic_blocks_rendering=(
                    False if schema_is_deferred else schema_blocks_rendering
                ),
                explanation=(
                    "Schema present or confirmed empty."
                    if schema_satisfied
                    else "Schema placeholder is valid; downstream API validation is pending."
                    if schema_is_deferred
                    else "Schema is invalid or an unapproved unknown placeholder."
                ),
                suggested_resolution=(
                    None
                    if schema_satisfied
                    else "Provide an OpenAPI schema or explicitly confirm the schema is empty."
                ),
            )
        )

        # 5. functions
        functions_spec = irs.get_slot("functions")
        functions_status = (
            getattr(api, "functions_status", "unknown_placeholder")
            if api
            else "unknown_placeholder"
        )
        functions_grammar_valid = bool(grammar and grammar.functions_valid)
        functions_satisfied = functions_grammar_valid and functions_status in (
            "known_present",
            "known_empty",
        )
        functions_blocks_rendering = not functions_grammar_valid or bool(
            grammar and grammar.status == "partial_blocked"
        )
        functions_are_deferred = bool(
            grammar
            and grammar.status == "grammar_minimal_partial"
            and functions_grammar_valid
            and functions_status == "unknown_placeholder"
        )
        slots_sat.append(
            SlotSatisfaction(
                slot_name="functions",
                status="satisfied" if functions_satisfied else "missing",
                relation="direct" if functions_satisfied else None,
                diagnostic_kind=(
                    None
                    if functions_satisfied
                    else "deferred_api_contract_validation"
                    if functions_are_deferred
                    else functions_spec.missing_diagnostic
                    if functions_spec
                    else "type_or_contract_ambiguity"
                ),
                diagnostic_required_for=(
                    "downstream_api_validation" if functions_are_deferred else "render"
                ),
                diagnostic_blocks_rendering=(
                    False if functions_are_deferred else functions_blocks_rendering
                ),
                explanation=(
                    "Functions present or confirmed empty."
                    if functions_satisfied
                    else "Functions placeholder is valid; downstream API validation is pending."
                    if functions_are_deferred
                    else "Functions are invalid or an unapproved unknown placeholder."
                ),
                suggested_resolution=(
                    None
                    if functions_satisfied
                    else (
                        "Provide function declarations or explicitly confirm "
                        "the API has no callable functions."
                    )
                ),
            )
        )

        # Determine renderability and completeness
        grammar_status = grammar.status if grammar else "partial_blocked"
        renderable = (
            has_name
            and has_source_evidence
            and grammar_status in {"grammar_minimal_partial", "complete"}
        )

        all_required_satisfied = (
            has_name
            and has_source_evidence
            and auth_valid
            and schema_satisfied
            and functions_satisfied
        )
        is_complete = grammar_status == "complete" and all_required_satisfied

        if not renderable:
            frontier_status = "cutline_blocked"
            cutline_reason = (
                "missing_api_identity_or_evidence"
                if not has_name or not has_source_evidence
                else "api_declaration_grammar_blocked"
            )
        elif not is_complete:
            frontier_status = "cutline_partial"
            cutline_reason = "incomplete_api_declaration_contract"
        else:
            frontier_status = "leaf"
            cutline_reason = None

        placeholder_fields = [
            field
            for field, deferred in (
                ("openapi_schema", schema_is_deferred),
                ("functions", functions_are_deferred),
            )
            if deferred
        ]
        report_metadata = {
            "api_id": getattr(api, "api_id", "") if api else "",
            "api_name": getattr(api, "api_name", "") if api else "",
            "grammar_validation_status": grammar_status,
            "grammar_valid": bool(grammar and grammar.grammar_valid),
            "grammar_validation_reasons": list(grammar.reasons) if grammar else [],
            "authority": (
                "post_normalize_irs"
                if context.stage_name == "post_normalize"
                else "stage_local_irs"
            ),
        }
        if placeholder_fields:
            api_identity = report_metadata["api_id"] or report_metadata["api_name"]
            report_metadata.update(
                {
                    "nl2spl_renderable": renderable,
                    "api_contract_validation_status": "pending",
                    "validation_authority": "downstream_spl_compiler",
                    "issue_group_id": f"api_contract_deferred:{api_identity}",
                    "repairability": "review_only",
                    "presentation_disposition": "deferred_validation",
                    "placeholder_fields": placeholder_fields,
                }
            )

        return ConstructSatisfactionReport(
            construct_id=instance.construct_id,
            construct_type=instance.construct_type,
            slots=slots_sat,
            completeness=("complete" if is_complete else "partial" if renderable else "blocked"),
            renderable=renderable,
            construct_path=instance.construct_path,
            source_span_ids=list(instance.source_span_ids),
            frontier_status=frontier_status,
            cutline_reason=cutline_reason,
            metadata=report_metadata,
        )
