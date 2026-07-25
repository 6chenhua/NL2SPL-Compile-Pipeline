"""ARC5: DemandView and Downstream Boundary Hardening.

Behavioral tests: verify that resource contract demand is ONLY authorized
by semantic_role, not by single fields.  Static audit tests: scan production
code for illegal single-field inference patterns.
"""

from __future__ import annotations

# ===========================================================================
# Behavioral tests: DemandView boundary hardening
# ===========================================================================


class TestDemandExclusivelyFromSemanticRole:
    """Resource contract demand existence is ONLY authorized by
    semantic_role in {input_contract, output_contract}."""

    def test_construct_target_alone_creates_no_demand(self):
        """construct_target=RESOURCE_CONTRACT without input_contract/output_contract
        semantic_role must NOT produce a demand."""
        from nl2spl.compiler.resource_contract_demand_view.builder import (
            DemandViewBuilder,
        )
        from nl2spl.ir.field_route_ir import FieldRouteIR, RouteAnnotation
        from nl2spl.ir.span_ir import SpanIR

        ann = RouteAnnotation(
            span_id="sp_pd",
            field="domain",
            semantic_role="profile_domain",  # NOT a resource contract role
            route_family="profile",
            construct_target="RESOURCE_CONTRACT",
            slot_target="input",
            executable=False,
        )
        routes = FieldRouteIR(annotations=[ann])
        span = SpanIR(span_id="sp_pd", text="task description")
        builder = DemandViewBuilder()
        view = builder.build([span], routes)

        assert len(view.demands) == 0, (
            f"profile_domain + RESOURCE_CONTRACT/input must not create demand. "
            f"Got: {[d.demand_id for d in view.demands]}"
        )

    def test_profile_domain_resource_contract_yields_no_demand(self):
        """profile_domain + construct_target=RESOURCE_CONTRACT + slot_target=input
        is a known contradiction — yield no demand."""
        from nl2spl.compiler.resource_contract_demand_view.builder import (
            DemandViewBuilder,
        )
        from nl2spl.ir.field_route_ir import FieldRouteIR, RouteAnnotation
        from nl2spl.ir.span_ir import SpanIR

        ann = RouteAnnotation(
            span_id="sp_gap",
            field="domain",
            semantic_role="profile_domain",
            construct_target="RESOURCE_CONTRACT",
            slot_target="input",
            executable=False,
        )
        routes = FieldRouteIR(annotations=[ann])
        span = SpanIR(span_id="sp_gap", text="profile description")
        builder = DemandViewBuilder()
        view = builder.build([span], routes)

        assert len(view.demands) == 0

    def test_route_family_alone_creates_no_demand(self):
        """route_family=resource_contract without input_contract/output_contract
        semantic_role must NOT produce a demand."""
        from nl2spl.compiler.resource_contract_demand_view.builder import (
            DemandViewBuilder,
        )
        from nl2spl.ir.field_route_ir import FieldRouteIR, RouteAnnotation
        from nl2spl.ir.span_ir import SpanIR

        ann = RouteAnnotation(
            span_id="sp_rf",
            field="behavior",
            semantic_role="failure_mode",
            route_family="resource_contract",
            executable=False,
        )
        routes = FieldRouteIR(annotations=[ann])
        span = SpanIR(span_id="sp_rf", text="failure text")
        builder = DemandViewBuilder()
        view = builder.build([span], routes)

        assert len(view.demands) == 0

    def test_input_contract_with_wrong_slot_creates_diagnostic_no_silent_demand(self):
        """input_contract with slot_target=output: intra-annotation direction
        conflict produces diagnostic and NO silent demand (safe failure)."""
        from nl2spl.compiler.resource_contract_demand_view.builder import (
            DemandViewBuilder,
        )
        from nl2spl.ir.field_route_ir import FieldRouteIR, RouteAnnotation
        from nl2spl.ir.span_ir import SpanIR

        ann = RouteAnnotation(
            span_id="sp_ic",
            field="resources",
            semantic_role="input_contract",
            route_family="resource_contract",
            construct_target="RESOURCE_CONTRACT",
            slot_target="output",  # inconsistent with input_contract
            executable=False,
            source_section_id="sec_inputs",
            source_packet_id="pkt_1",
        )
        routes = FieldRouteIR(annotations=[ann])
        span = SpanIR(span_id="sp_ic", text="customer name")
        builder = DemandViewBuilder()
        view = builder.build([span], routes)

        # Intra-annotation direction conflict: NO demand, diagnostic visible
        assert len(view.demands) == 0, (
            "Conflicting direction signals must produce diagnostic, not silent demand"
        )
        assert len(view.view_diagnostics) >= 1, (
            "Intra-annotation direction conflict diagnostic required"
        )

    def test_input_contract_consistent_creates_demand(self):
        """input_contract with slot_target=input: all fields consistent → demand."""
        from nl2spl.compiler.resource_contract_demand_view.builder import (
            DemandViewBuilder,
        )
        from nl2spl.ir.field_route_ir import FieldRouteIR, RouteAnnotation
        from nl2spl.ir.span_ir import SpanIR

        ann = RouteAnnotation(
            span_id="sp_ok",
            field="resources",
            semantic_role="input_contract",
            route_family="resource_contract",
            construct_target="RESOURCE_CONTRACT",
            slot_target="input",
            executable=False,
            source_section_id="sec_inputs",
            source_packet_id="pkt_1",
        )
        routes = FieldRouteIR(annotations=[ann])
        span = SpanIR(span_id="sp_ok", text="customer name")
        builder = DemandViewBuilder()
        view = builder.build([span], routes)

        assert len(view.demands) == 1
        assert view.demands[0].direction == "input"

    def test_demandview_selection_only_uses_semantic_role(self):
        """Verify _select_contract_annotations() filters exclusively by
        semantic_role in _CONTRACT_ROLES, not by construct_target or route_family."""
        import inspect

        from nl2spl.compiler.resource_contract_demand_view.builder import (
            DemandViewBuilder,
        )

        source = inspect.getsource(DemandViewBuilder._select_contract_annotations)
        # Must check semantic_role
        assert "semantic_role" in source
        assert "_CONTRACT_ROLES" in source
        # Must NOT check construct_target as existence condition
        assert 'construct_target == "RESOURCE_CONTRACT"' not in source, (
            "DemandView must not create demand from construct_target alone"
        )
        assert 'route_family == "resource_contract"' not in source, (
            "DemandView must not create demand from route_family alone"
        )


# ===========================================================================
# Static audit: scan production code for illegal single-field inference
# ===========================================================================


class TestStaticAuditNoSingleFieldInference:
    """Scan production source files for illegal demand-creation patterns.

    Uses function-level source inspection (``inspect.getsource``) to
    catch multi-line conditions that single-line scanning would miss.
    """

    @staticmethod
    def _function_source(module_path: str, func_name: str) -> str | None:
        """Return the source of *func_name* in *module_path*, or ``None``."""
        import importlib
        import inspect
        import os
        if not os.path.exists(module_path):
            return None
        # Derive module name from path
        mod_name = (
            module_path.replace("/", ".").replace("\\", ".").removesuffix(".py")
        )
        if mod_name.startswith("src."):
            mod_name = mod_name[4:]
        try:
            mod = importlib.import_module(mod_name)
            obj = getattr(mod, func_name, None)
            if obj is None:
                # Try nested classes
                for part in func_name.split("."):
                    obj = getattr(obj or mod, part, None)
                    if obj is None:
                        break
            if obj is not None:
                return inspect.getsource(obj)
        except Exception:
            pass
        return None

    def test_planner_contract_annotations_no_single_field_inference(self):
        """The legacy planner's _contract_annotations() must NOT use
        route_family or construct_target as single-field demand gates."""
        import inspect

        from nl2spl.pipeline.stages.stage3_2_resource_contract_planner.planner import (
            ResourceContractPlanner,
        )

        source = inspect.getsource(ResourceContractPlanner._contract_annotations)
        # Must filter by semantic_role and _CONTRACT_ROLES
        assert "semantic_role" in source, (
            "Planner must check semantic_role for contract annotations"
        )
        # Must NOT use single-field inference
        assert 'route_family == "resource_contract"' not in source, (
            "Planner must not use route_family as demand existence condition"
        )
        assert 'construct_target == "RESOURCE_CONTRACT"' not in source, (
            "Planner must not use construct_target as demand existence condition"
        )

    def test_builder_select_contract_annotations_no_single_field_inference(self):
        """The DemandView builder's _select_contract_annotations() must NOT
        use route_family or construct_target as single-field demand gates."""
        import inspect

        from nl2spl.compiler.resource_contract_demand_view.builder import (
            DemandViewBuilder,
        )

        source = inspect.getsource(DemandViewBuilder._select_contract_annotations)
        assert "semantic_role" in source
        assert 'route_family == "resource_contract"' not in source
        assert 'construct_target == "RESOURCE_CONTRACT"' not in source

    def test_no_slot_target_as_sole_direction_in_planner(self):
        """Planner must not use slot_target alone as direction authority."""
        import inspect

        from nl2spl.pipeline.stages.stage3_2_resource_contract_planner.planner import (
            ResourceContractPlanner,
        )

        source = inspect.getsource(ResourceContractPlanner._contract_annotations)
        # slot_target checks without semantic_role checks are forbidden
        # in the demand-creation path
        has_slot = "slot_target" in source
        has_sem = "semantic_role" in source
        if has_slot and not has_sem:
            raise AssertionError("slot_target used without semantic_role in planner")


# ===========================================================================
# Behavioral test: legacy planner rejects profile_domain + RESOURCE_CONTRACT
# ===========================================================================


class TestLegacyPlannerRejectsNonContractAnnotations:
    """The legacy Stage3.2 planner must reject annotations with
    construct_target=RESOURCE_CONTRACT but non-resource semantic_role."""

    def test_planner_rejects_profile_domain_resource_contract(self):
        """profile_domain + RESOURCE_CONTRACT/input must NOT be selected
        by the legacy planner's _contract_annotations()."""
        from nl2spl.ir.field_route_ir import FieldRouteIR, RouteAnnotation
        from nl2spl.pipeline.stages.stage3_2_resource_contract_planner.planner import (
            ResourceContractPlanner,
        )

        ann = RouteAnnotation(
            span_id="sp_pd",
            field="domain",
            semantic_role="profile_domain",
            construct_target="RESOURCE_CONTRACT",
            slot_target="input",
            executable=False,
        )
        routes = FieldRouteIR(annotations=[ann])
        selected = ResourceContractPlanner._contract_annotations(routes)
        assert len(selected) == 0, (
            "Legacy planner must not select profile_domain + RESOURCE_CONTRACT"
        )

    def test_planner_selects_input_contract_correctly(self):
        """input_contract annotations are correctly selected."""
        from nl2spl.ir.field_route_ir import FieldRouteIR, RouteAnnotation
        from nl2spl.pipeline.stages.stage3_2_resource_contract_planner.planner import (
            ResourceContractPlanner,
        )

        ann = RouteAnnotation(
            span_id="sp_ic",
            field="resources",
            semantic_role="input_contract",
            executable=False,
        )
        routes = FieldRouteIR(annotations=[ann])
        selected = ResourceContractPlanner._contract_annotations(routes)
        assert len(selected) == 1


# ===========================================================================
# DemandView builder invariant: _CONTRACT_ROLES is the gate
# ===========================================================================


class TestContractRolesGate:
    """_CONTRACT_ROLES = {input_contract, output_contract} is the sole gate
    for resource contract demand projection."""

    def test_contract_roles_is_exactly_input_output(self):
        from nl2spl.compiler.resource_contract_demand_view.builder import (
            _CONTRACT_ROLES,
        )
        assert _CONTRACT_ROLES == frozenset({"input_contract", "output_contract"})
