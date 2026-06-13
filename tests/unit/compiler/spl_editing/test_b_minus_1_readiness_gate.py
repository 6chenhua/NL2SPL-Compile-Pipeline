"""B-1 Readiness Verification Gate.

Aggregated gate tests that prove all R0-R7 readiness prerequisites are
in place BEFORE any SPL Editing backend implementation code is written.

This file MUST pass in its entirety before B0 starts.  If any test
fails, stop and restore readiness — do not proceed to backend code.

Tests are intentionally self-contained: each test imports only what it
needs and asserts exactly one readiness fact.  This keeps failures
localized and unambiguous.
"""

from __future__ import annotations


# ===========================================================================
# G1: SlotSpec.repair_affordances exists + MVP slots declare affordances
# ===========================================================================


def test_g1_slotspec_has_repair_affordances_field() -> None:
    """G1: SlotSpec defaults to empty repair_affordances tuple."""
    from nl2spl.compiler.construct_registry import SlotSpec

    slot = SlotSpec(slot_name="test")
    assert hasattr(slot, "repair_affordances"), (
        "G1 FAIL: SlotSpec must have repair_affordances field"
    )
    assert slot.repair_affordances == ()


def test_g1_mvp_slots_declare_affordances() -> None:
    """G1: Every MVP slot in default registry has at least one affordance."""
    from nl2spl.compiler.construct_registry import SPLConstructRegistry

    registry = SPLConstructRegistry.default()
    mvp_slots = [
        ("EXCEPTION_FLOW", "handler_action"),
        ("REQUIRED_OUTPUT", "producer"),
        ("REQUEST_INPUT", "value_target"),
        ("CALL_API", "integration_evidence"),
        ("INVOKE_WORKER", "handoff_id"),
        ("INVOKE_WORKER", "target_worker"),
        ("WORKER_PROMOTION", "promotion_input_contract"),
        ("WORKER_PROMOTION", "promotion_output_contract"),
        ("WORKER_PROMOTION", "promotion_invocation_point"),
        ("WORKER_PROMOTION", "promotion_result_handoff"),
        ("WORKER_HANDOFF", "target"),
        ("WORKER_HANDOFF", "input_bindings"),
        ("WORKER_HANDOFF", "output_bindings"),
        ("WORKER_HANDOFF", "invocation_site"),
    ]
    for ct, sn in mvp_slots:
        irs = registry.get(ct)
        slot = irs.get_slot(sn)
        assert slot is not None, f"G1 FAIL: {ct}.{sn} slot not found"
        assert len(slot.repair_affordances) >= 1, (
            f"G1 FAIL: {ct}.{sn} has no repair affordances"
        )


def test_g1_affordance_ids_are_globally_unique() -> None:
    """G1: No affordance_id appears in more than one construct type."""
    from nl2spl.compiler.construct_registry import SPLConstructRegistry

    registry = SPLConstructRegistry.default()
    id_to_constructs: dict[str, set[str]] = {}
    for ct in registry.list_constructs():
        irs = registry.get(ct)
        for slot in irs.slots:
            for aff in slot.repair_affordances:
                id_to_constructs.setdefault(aff.affordance_id, set()).add(ct)

    violations = {k: v for k, v in id_to_constructs.items() if len(v) > 1}
    assert len(violations) == 0, (
        f"G1 FAIL: affordance_ids shared across construct types: {violations}"
    )


# ===========================================================================
# G2: RepairCatalogBuilder derives catalog entries
# ===========================================================================


def test_g2_catalog_derived_from_registry() -> None:
    """G2: RepairCatalogBuilder.from_construct_registry() produces entries."""
    from nl2spl.compiler.construct_registry import SPLConstructRegistry
    from nl2spl.compiler.spl_editing.core.catalog import RepairCatalogBuilder

    catalog = RepairCatalogBuilder.from_construct_registry(
        SPLConstructRegistry.default()
    )
    assert len(catalog) > 0, "G2 FAIL: catalog must be non-empty"
    assert len(catalog.entries) > 0


def test_g2_catalog_entry_count_matches_affordance_count() -> None:
    """G2: Catalog size equals sum of all (slot × affordance) pairs."""
    from nl2spl.compiler.construct_registry import SPLConstructRegistry
    from nl2spl.compiler.spl_editing.core.catalog import RepairCatalogBuilder

    registry = SPLConstructRegistry.default()
    expected = sum(
        len(slot.repair_affordances)
        for ct in registry.list_constructs()
        for slot in registry.get(ct).slots
    )
    catalog = RepairCatalogBuilder.from_construct_registry(registry)
    assert len(catalog) == expected, (
        f"G2 FAIL: catalog has {len(catalog)} entries, expected {expected}"
    )


def test_g2_catalog_lookup_by_irs_ref_and_kind() -> None:
    """G2: Looking up by construct_type + slot_name + diagnostic_kind works."""
    from nl2spl.compiler.construct_registry import SPLConstructRegistry
    from nl2spl.compiler.spl_editing.core.catalog import RepairCatalogBuilder

    catalog = RepairCatalogBuilder.from_construct_registry(
        SPLConstructRegistry.default()
    )
    entries = catalog.find_by_construct_slot_kind(
        "EXCEPTION_FLOW", "handler_action", "missing_handler",
    )
    assert len(entries) == 1, "G2 FAIL: missing_handler must map to 1 entry"
    assert entries[0].affordance_id == "exception_flow.add_handler_step"


# ===========================================================================
# G3: ProducerIssueGrouper groups required output / resource contract demand
# ===========================================================================


def test_g3_producer_grouper_exists_and_groups() -> None:
    """G3: ProducerIssueGrouper assigns primary/alias roles."""
    from nl2spl.compiler.compile_result import MissingSlot
    from nl2spl.compiler.spl_editing.issues.grouper import ProducerIssueGrouper
    from nl2spl.ir.diagnostics import (
        METADATA_KEY_ISSUE_GROUP_ID,
        METADATA_KEY_ISSUE_ROLE,
        METADATA_KEY_REPAIRABILITY,
        CompileDiagnostic,
    )

    # Build two diagnostics for the same output 'draft'
    req_diag = CompileDiagnostic(
        diagnostic_id="diag_req",
        kind="missing_output_producer",
        severity="warning",
        message="Required output 'draft' has no source-backed producer step.",
        target_ref="worker:w_main.output:draft",
        blocks_completion=True,
        metadata={
            "irs_ref": {
                "construct_type": "REQUIRED_OUTPUT",
                "construct_id": "worker:w_main.output:draft",
                "slot_name": "producer",
                "source_authority": "post_normalize_irs",
            },
        },
    )
    rcd_diag = CompileDiagnostic(
        diagnostic_id="diag_rcd",
        kind="missing_output_producer",
        severity="warning",
        message="Resource contract output 'rcd_draft' has materialized resource(s) draft but no renderable producer.",
        target_ref="resource_contract_demand:rcd_draft",
        blocks_completion=True,
        metadata={
            "irs_ref": {
                "construct_type": "RESOURCE_CONTRACT_DEMAND",
                "construct_id": "resource_contract_demand:rcd_draft",
                "slot_name": "producer",
                "source_authority": "post_normalize_irs",
            },
        },
    )

    ProducerIssueGrouper().annotate([req_diag, rcd_diag])

    # Same group
    assert req_diag.metadata[METADATA_KEY_ISSUE_GROUP_ID] is not None
    assert req_diag.metadata[METADATA_KEY_ISSUE_GROUP_ID] == rcd_diag.metadata[METADATA_KEY_ISSUE_GROUP_ID]
    # Primary is REQUIRED_OUTPUT
    assert req_diag.metadata[METADATA_KEY_ISSUE_ROLE] == "primary"
    # Alias is RESOURCE_CONTRACT_DEMAND
    assert rcd_diag.metadata[METADATA_KEY_ISSUE_ROLE] == "alias"
    # Both editable
    assert req_diag.metadata[METADATA_KEY_REPAIRABILITY] == "editable"
    assert rcd_diag.metadata[METADATA_KEY_REPAIRABILITY] == "editable"


# ===========================================================================
# G4: WorkerDelegationPromoter emits selected_promoted_stage_local_irs
# ===========================================================================


def test_g4_promoter_exists_and_emits_selected_promoted_authority() -> None:
    """G4: WorkerDelegationPromoter sets authority to
    selected_promoted_stage_local_irs.
    """
    from nl2spl.compiler.compile_result import MissingSlot
    from nl2spl.compiler.spl_editing.issues.promoter import (
        PROMOTED_AUTHORITY,
        WorkerDelegationPromoter,
    )
    from nl2spl.ir.diagnostics import (
        METADATA_KEY_AUTHORITY,
        METADATA_KEY_ISSUE_ROLE,
        METADATA_KEY_REPAIRABILITY,
        CompileDiagnostic,
    )

    diag = CompileDiagnostic(
        diagnostic_id="diag_promo",
        kind="type_or_contract_ambiguity",
        severity="warning",
        message="Missing input contract [construct=worker_promotion:cand_1, slot=promotion_input_contract]",
        target_ref="worker_promotion:cand_1",
        source_span_ids=["s1"],
        missing_slot=MissingSlot(
            slot_name="promotion_input_contract",
            required_for="complete",
            reason="missing promotion_input_contract",
            source_span_ids=["s1"],
        ),
        blocks_rendering=False,
        blocks_completion=True,
        metadata={
            "irs_ref": {
                "construct_type": "WORKER_PROMOTION",
                "construct_id": "worker_promotion:cand_1",
                "slot_name": "promotion_input_contract",
                "construct_path": ["worker_plan", "promotion", "cand_1"],
                "source_authority": "stage_local_irs",
            },
            "authority": "stage_local_irs",
            "original_semantic_role": "delegation_intent",
            "promotion_candidate_id": "cand_1",
        },
    )

    WorkerDelegationPromoter().annotate([diag])

    assert diag.metadata[METADATA_KEY_AUTHORITY] == PROMOTED_AUTHORITY, (
        f"G4 FAIL: authority must be '{PROMOTED_AUTHORITY}', "
        f"got '{diag.metadata.get(METADATA_KEY_AUTHORITY)}'"
    )
    assert diag.metadata[METADATA_KEY_ISSUE_ROLE] == "primary"
    assert diag.metadata[METADATA_KEY_REPAIRABILITY] == "editable"


# ===========================================================================
# G5: CompileDiagnostic.metadata["irs_ref"] is emitted and preserved
# ===========================================================================


def test_g5_diagnostic_projector_emits_irs_ref() -> None:
    """G5: DiagnosticProjector writes irs_ref into every projected diagnostic."""
    from nl2spl.compiler.construct_registry import (
        ConstructSatisfactionReport,
        SlotSatisfaction,
        SPLConstructRegistry,
    )
    from nl2spl.compiler.irs.context import IRSCheckContext
    from nl2spl.compiler.irs.projector import DiagnosticProjector

    report = ConstructSatisfactionReport(
        construct_id="worker:w_main.exception_flow:exc_1",
        construct_type="EXCEPTION_FLOW",
        slots=[
            SlotSatisfaction(
                slot_name="handler_action",
                status="missing",
                diagnostic_kind="missing_handler",
                explanation="No handler step.",
            ),
        ],
        completeness="partial",
        renderable=True,
        construct_path=("worker", "w_main", "exception_flows", "exc_1"),
    )
    context = IRSCheckContext(stage_name="post_normalize")
    result = DiagnosticProjector().project([report], context)

    assert len(result.diagnostics) == 1
    diag = result.diagnostics[0]
    irs_ref = diag.metadata.get("irs_ref")
    assert irs_ref is not None, "G5 FAIL: irs_ref must be in metadata"
    assert irs_ref["construct_type"] == "EXCEPTION_FLOW"
    assert irs_ref["slot_name"] == "handler_action"
    assert irs_ref["source_authority"] == "post_normalize_irs"


def test_g5_consolidator_preserves_irs_ref() -> None:
    """G5: DiagnosticConsolidator does not strip irs_ref during dedup."""
    from nl2spl.compiler.diagnostic_consolidator import (
        DiagnosticConsolidationInput,
        DiagnosticConsolidator,
    )
    from nl2spl.ir.diagnostics import CompileDiagnostic

    diag = CompileDiagnostic(
        diagnostic_id="diag_g5",
        kind="missing_handler",
        severity="warning",
        message="Test",
        target_ref="x",
        blocks_completion=True,
        metadata={
            "irs_ref": {
                "construct_type": "EXCEPTION_FLOW",
                "construct_id": "exc_1",
                "slot_name": "handler_action",
                "construct_path": [],
                "source_authority": "post_normalize_irs",
            },
            "authority": "post_normalize_irs",
        },
    )
    result = DiagnosticConsolidator().consolidate(
        DiagnosticConsolidationInput(post_normalize_diagnostics=[diag])
    )
    assert len(result.final_diagnostics) == 1
    final = result.final_diagnostics[0]
    assert final.metadata.get("irs_ref") is not None, (
        "G5 FAIL: consolidator must preserve irs_ref"
    )


# ===========================================================================
# G6: Gate accepts origin="user_confirmed_repair"
# ===========================================================================


def test_g6_gate_classifies_user_confirmed_repair() -> None:
    """G6: Gate.classify_origin returns 'user_confirmed_repair'."""
    from nl2spl.ir.step_ir import StepIR
    from nl2spl.pipeline.executable_gate import ExecutableElementGate

    gate = ExecutableElementGate()
    step = StepIR(
        "st_repair", "User-confirmed handler", [],
        "GENERAL_COMMAND",
        metadata={"origin": "user_confirmed_repair"},
    )
    assert gate.classify_origin(step) == "user_confirmed_repair", (
        "G6 FAIL: Gate must classify user_confirmed_repair"
    )


def test_g6_gate_renders_user_confirmed_repair() -> None:
    """G6: Gate.is_renderable accepts user_confirmed_repair origin."""
    from nl2spl.ir.step_ir import StepIR
    from nl2spl.pipeline.executable_gate import ExecutableElementGate

    gate = ExecutableElementGate()
    step = StepIR(
        "st_repair", "User-confirmed handler", [],
        "GENERAL_COMMAND",
        metadata={"origin": "user_confirmed_repair"},
    )
    ok, reason = gate.is_renderable(
        step, "user_confirmed_repair", {}, set(), {},
    )
    assert ok is True, f"G6 FAIL: Gate must render user_confirmed_repair: {reason}"


# ===========================================================================
# G7: ProducerIndex accepts origin="user_confirmed_repair"
# ===========================================================================


def test_g7_producer_index_recognizes_user_confirmed_repair() -> None:
    """G7: _step_is_renderable returns True for user_confirmed_repair."""
    from nl2spl.compiler.producer_index import _step_is_renderable, ProducerIndex
    from nl2spl.ir.step_ir import StepIR

    step = StepIR(
        "st_repair", "User-confirmed producer", [],
        "GENERAL_COMMAND",
        outputs=["result"],
        metadata={"origin": "user_confirmed_repair"},
    )
    assert _step_is_renderable(step) is True, (
        "G7 FAIL: ProducerIndex must recognize user_confirmed_repair"
    )
    index = ProducerIndex(steps=[step])
    assert index.is_produced("result"), (
        "G7 FAIL: output of user_confirmed_repair step must be produced"
    )


# ===========================================================================
# G8: Post-normalize IRS source evidence accepts origin="user_confirmed_repair"
# ===========================================================================


def test_g8_post_normalize_accepts_user_confirmed_repair() -> None:
    """G8: _source_evidence_slot returns satisfied for user_confirmed_repair."""
    from nl2spl.compiler.construct_registry import SPLConstructRegistry
    from nl2spl.compiler.irs.checkers.post_normalize import PostNormalizeIRSCheckerV6
    from nl2spl.ir.step_ir import StepIR

    checker = PostNormalizeIRSCheckerV6()
    irs = SPLConstructRegistry.default().get("GENERAL_COMMAND")
    step = StepIR(
        "st_repair", "User-confirmed repair step", [],
        "GENERAL_COMMAND",
        metadata={"origin": "user_confirmed_repair"},
    )
    slot = checker._source_evidence_slot(step, irs, set())
    assert slot.status == "satisfied", (
        f"G8 FAIL: Post-normalize IRS must accept user_confirmed_repair, "
        f"got status='{slot.status}'"
    )
    assert slot.diagnostic_kind is None, (
        "G8 FAIL: user_confirmed_repair must not produce a missing-evidence diagnostic"
    )


# ===========================================================================
# G9: DELEGATION_INTENT is not an active construct target or repair target
# ===========================================================================


def test_g9_delegation_intent_not_in_registry() -> None:
    """G9: DELEGATION_INTENT is NOT in SPLConstructRegistry."""
    from nl2spl.compiler.construct_registry import SPLConstructRegistry

    registry = SPLConstructRegistry.default()
    assert not registry.has("DELEGATION_INTENT"), (
        "G9 FAIL: DELEGATION_INTENT must not be a registered construct"
    )
    assert "DELEGATION_INTENT" not in registry.list_constructs()


def test_g9_delegation_intent_not_in_catalog() -> None:
    """G9: DELEGATION_INTENT does not appear as construct_type in the catalog."""
    from nl2spl.compiler.construct_registry import SPLConstructRegistry
    from nl2spl.compiler.spl_editing.core.catalog import RepairCatalogBuilder

    catalog = RepairCatalogBuilder.from_construct_registry(
        SPLConstructRegistry.default()
    )
    for entry in catalog.entries:
        assert entry.construct_type != "DELEGATION_INTENT", (
            f"G9 FAIL: catalog entry {entry.entry_id} has DELEGATION_INTENT "
            f"construct_type"
        )


def test_g9_delegation_intent_only_as_metadata() -> None:
    """G9: delegation_intent appears only as original_semantic_role metadata."""
    from nl2spl.compiler.construct_registry import SPLConstructRegistry
    from nl2spl.compiler.irs.checkers.worker_delegation import WorkerDelegationIRSChecker
    from nl2spl.compiler.irs.context import IRSCheckContext
    from nl2spl.ir.field_route_ir import FieldRouteIR, RouteAnnotation

    routes = FieldRouteIR(
        behavior=["s_del"],
        annotations=[
            RouteAnnotation(
                span_id="s_del",
                field="behavior",
                semantic_role="delegation_intent",
                route_family="delegation_boundary",
                executable=False,
            )
        ],
    )
    checker = WorkerDelegationIRSChecker()
    instances = checker.extract_instances(
        IRSCheckContext(stage_name="stage3_5", routes=routes)
    )

    for instance in instances:
        # Never DELEGATION_INTENT construct type
        assert instance.construct_type != "DELEGATION_INTENT", (
            f"G9 FAIL: instance {instance.construct_id} has DELEGATION_INTENT type"
        )
        # Always carries original_semantic_role in metadata
        assert instance.metadata.get("original_semantic_role") == "delegation_intent", (
            f"G9 FAIL: instance {instance.construct_id} missing "
            f"original_semantic_role=delegation_intent"
        )
