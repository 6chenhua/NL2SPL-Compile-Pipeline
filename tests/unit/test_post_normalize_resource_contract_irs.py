"""Phase 4 IRS tests: resource contract demand materialization checks.

Verifies that the post-normalize checker:
1. Reports ``missing_resource_contract`` when a demand has no binding.
2. Reports ``resource_kind_mismatch`` when a document-artifact demand
   is materialized as a variable instead of a file.
3. Reports satisfied when everything matches correctly.
"""

from __future__ import annotations

from nl2spl.compiler.construct_registry import SPLConstructRegistry
from nl2spl.compiler.irs.checkers.post_normalize import PostNormalizeIRSCheckerV6
from nl2spl.compiler.irs.context import IRSCheckContext
from nl2spl.ir.resource_contract_ir import (
    ResourceContractBindingIR,
    ResourceContractDemandIR,
    ResourceContractPlanIR,
)
from nl2spl.ir.resource_registry_ir import (
    FileSpec,
    ResourceRegistryIR,
    VariableSpec,
    WorkerScopedResourceIR,
)
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.worker_ir import WorkerIR
from nl2spl.ir.worker_plan_ir import WorkerPlanIR, WorkerSpecIR

# =============================================================================
# Helpers
# =============================================================================


def _worker_plan_with_output(name: str, description: str = "") -> WorkerPlanIR:
    spec = WorkerSpecIR(
        worker_id="worker_main",
        worker_name="MainWorker",
        kind="main",
        purpose="test",
        boundary_kind="main_worker",
        output_contract=[],
    )
    return WorkerPlanIR(main_worker_id="worker_main", workers=[spec])


def _document_demand(demand_id: str = "rcd_output_s11") -> ResourceContractDemandIR:
    return ResourceContractDemandIR(
        demand_id=demand_id,
        direction="output",
        required=True,
        evidence_text="Finished draft (Word or Google Doc, 200-500 words)",
        source_span_ids=["s11"],
        source_section_id="sec_required_outputs",
        evidence_sources=["section_title", "list_item_packet"],
    )


def _variable_binding(
    demand_id: str = "rcd_output_s11",
    resource_name: str = "finished_draft_var",
) -> ResourceContractBindingIR:
    return ResourceContractBindingIR(
        contract_demand_id=demand_id,
        resource_name=resource_name,
        resource_kind="variable",
        direction="output",
        scope_kind="global",
        scope_id=None,
        source_span_ids=["s11"],
    )


def _file_binding(
    demand_id: str = "rcd_output_s11",
    resource_name: str = "finished_draft",
) -> ResourceContractBindingIR:
    return ResourceContractBindingIR(
        contract_demand_id=demand_id,
        resource_name=resource_name,
        resource_kind="file",
        direction="output",
        scope_kind="global",
        scope_id=None,
        source_span_ids=["s11"],
    )


def _worker_ir() -> WorkerIR:
    return WorkerIR(worker_name="MainWorker", description="Test worker")


def _worker_ir_with_step(output_name: str) -> WorkerIR:
    return WorkerIR(
        worker_name="MainWorker",
        description="Test worker",
        steps=[
            StepIR(
                step_id="st_produce_output",
                text=f"Produce {output_name}",
                source_span_ids=["s14"],
                command_type="GENERAL_COMMAND",
                outputs=[output_name],
            ),
        ],
    )


# =============================================================================
# Tests
# =============================================================================


class TestResourceContractIRS:
    """IRS post-normalize checks for RESOURCE_CONTRACT_DEMAND."""

    def test_demand_with_file_binding_is_satisfied(self) -> None:
        """Document demand + file binding + FileSpec in registry = satisfied."""
        registry = SPLConstructRegistry.default()
        irs = registry.get("RESOURCE_CONTRACT_DEMAND")
        assert irs is not None

        checker = PostNormalizeIRSCheckerV6()
        plan = ResourceContractPlanIR(demands=[_document_demand()])
        ws_resources = WorkerScopedResourceIR(
            global_resources=ResourceRegistryIR(
                files=[FileSpec("finished_draft", "< >", "text", "Draft")],
            ),
            resource_contract_bindings=[_file_binding()],
        )
        context = IRSCheckContext(
            stage_name="post_normalize",
            normalized_ir=_worker_ir_with_step("finished_draft"),
            worker_plan=_worker_plan_with_output("finished_draft"),
            resources=ws_resources.global_resources,
            metadata={
                "resource_contract_plan": plan,
                "worker_scoped_resources": ws_resources,
            },
        )

        instances = checker.extract_instances(context)
        rcd_instances = [
            i for i in instances
            if i.construct_type == "RESOURCE_CONTRACT_DEMAND"
        ]
        assert len(rcd_instances) == 1

        report = checker.check_instance(rcd_instances[0], irs, context)
        assert report.completeness == "complete"

    def test_demand_without_binding_reports_missing(self) -> None:
        """Demand with no binding → missing_resource_contract diagnostic."""
        registry = SPLConstructRegistry.default()
        irs = registry.get("RESOURCE_CONTRACT_DEMAND")

        checker = PostNormalizeIRSCheckerV6()
        plan = ResourceContractPlanIR(demands=[_document_demand()])
        ws_resources = WorkerScopedResourceIR(
            global_resources=ResourceRegistryIR(),
            resource_contract_bindings=[],  # no binding
        )
        context = IRSCheckContext(
            stage_name="post_normalize",
            normalized_ir=_worker_ir(),
            worker_plan=_worker_plan_with_output("finished_draft"),
            resources=ws_resources.global_resources,
            metadata={
                "resource_contract_plan": plan,
                "worker_scoped_resources": ws_resources,
            },
        )

        instances = checker.extract_instances(context)
        rcd_instances = [
            i for i in instances
            if i.construct_type == "RESOURCE_CONTRACT_DEMAND"
        ]
        assert len(rcd_instances) == 1

        report = checker.check_instance(rcd_instances[0], irs, context)
        assert report.completeness == "partial"

        mat_slot = next(s for s in report.slots if s.slot_name == "materialization")
        assert mat_slot.status == "missing"
        assert mat_slot.diagnostic_kind == "missing_resource_contract"

    def test_file_binding_without_producer_reports_missing_output_producer(self) -> None:
        """FileSpec + binding alone is not complete without a producer."""
        registry = SPLConstructRegistry.default()
        irs = registry.get("RESOURCE_CONTRACT_DEMAND")

        checker = PostNormalizeIRSCheckerV6()
        plan = ResourceContractPlanIR(demands=[_document_demand()])
        ws_resources = WorkerScopedResourceIR(
            global_resources=ResourceRegistryIR(
                files=[FileSpec("finished_draft", "< >", "text", "Draft")],
            ),
            resource_contract_bindings=[_file_binding()],
        )
        context = IRSCheckContext(
            stage_name="post_normalize",
            normalized_ir=_worker_ir(),
            worker_plan=_worker_plan_with_output("finished_draft"),
            resources=ws_resources.global_resources,
            metadata={
                "resource_contract_plan": plan,
                "worker_scoped_resources": ws_resources,
            },
        )

        instances = checker.extract_instances(context)
        rcd_instance = next(
            i for i in instances
            if i.construct_type == "RESOURCE_CONTRACT_DEMAND"
        )

        report = checker.check_instance(rcd_instance, irs, context)
        assert report.completeness == "partial"
        producer_slot = next(s for s in report.slots if s.slot_name == "producer")
        assert producer_slot.status == "missing"
        assert producer_slot.diagnostic_kind == "missing_output_producer"

    def test_binding_kind_without_matching_registry_reports_kind_mismatch(self) -> None:
        """Binding kind/name must match the materialized registry collection."""
        registry = SPLConstructRegistry.default()
        irs = registry.get("RESOURCE_CONTRACT_DEMAND")

        checker = PostNormalizeIRSCheckerV6()
        plan = ResourceContractPlanIR(demands=[_document_demand()])
        ws_resources = WorkerScopedResourceIR(
            global_resources=ResourceRegistryIR(
                variables=[
                    VariableSpec(
                        "finished_draft", "text", True,
                        "Finished draft", "output",
                    ),
                ],
            ),
            resource_contract_bindings=[_file_binding()],
        )
        context = IRSCheckContext(
            stage_name="post_normalize",
            normalized_ir=_worker_ir_with_step("finished_draft"),
            worker_plan=_worker_plan_with_output("finished_draft"),
            resources=ws_resources.global_resources,
            metadata={
                "resource_contract_plan": plan,
                "worker_scoped_resources": ws_resources,
            },
        )

        instances = checker.extract_instances(context)
        rcd_instances = [
            i for i in instances
            if i.construct_type == "RESOURCE_CONTRACT_DEMAND"
        ]
        assert len(rcd_instances) == 1

        report = checker.check_instance(rcd_instances[0], irs, context)
        assert report.completeness == "partial"

        kind_slot = next(s for s in report.slots if s.slot_name == "resource_registry")
        assert kind_slot.status == "missing"
        assert kind_slot.diagnostic_kind == "resource_kind_mismatch"

    def test_plain_text_demand_with_variable_is_satisfied(self) -> None:
        """Non-document demand (plain text) with variable binding = satisfied."""
        registry = SPLConstructRegistry.default()
        irs = registry.get("RESOURCE_CONTRACT_DEMAND")

        checker = PostNormalizeIRSCheckerV6()
        demand = ResourceContractDemandIR(
            demand_id="rcd_output_s12",
            direction="output",
            required=True,
            evidence_text="Status flag (values: drafting, ready for review, approved)",
            source_span_ids=["s12"],
            evidence_sources=["list_item_packet"],
        )
        plan = ResourceContractPlanIR(demands=[demand])
        binding = ResourceContractBindingIR(
            contract_demand_id="rcd_output_s12",
            resource_name="status_flag",
            resource_kind="variable",
            direction="output",
            scope_kind="global",
            scope_id=None,
        )
        ws_resources = WorkerScopedResourceIR(
            global_resources=ResourceRegistryIR(
                variables=[
                    VariableSpec(
                        "status_flag", "text", True,
                        "Status flag", "output",
                    ),
                ],
            ),
            resource_contract_bindings=[binding],
        )
        context = IRSCheckContext(
            stage_name="post_normalize",
            normalized_ir=_worker_ir_with_step("status_flag"),
            worker_plan=_worker_plan_with_output("status_flag"),
            resources=ws_resources.global_resources,
            metadata={
                "resource_contract_plan": plan,
                "worker_scoped_resources": ws_resources,
            },
        )

        instances = checker.extract_instances(context)
        rcd_instances = [
            i for i in instances
            if i.construct_type == "RESOURCE_CONTRACT_DEMAND"
        ]
        assert len(rcd_instances) == 1

        report = checker.check_instance(rcd_instances[0], irs, context)
        assert report.completeness == "complete"

    def test_missing_plan_skips_check(self) -> None:
        """When no ResourceContractPlanIR is in context, no instances are created."""
        checker = PostNormalizeIRSCheckerV6()
        context = IRSCheckContext(
            stage_name="post_normalize",
            normalized_ir=_worker_ir(),
            worker_plan=_worker_plan_with_output(""),
            resources=ResourceRegistryIR(),
            metadata={},
        )

        instances = checker.extract_instances(context)
        rcd_instances = [
            i for i in instances
            if i.construct_type == "RESOURCE_CONTRACT_DEMAND"
        ]
        assert len(rcd_instances) == 0
