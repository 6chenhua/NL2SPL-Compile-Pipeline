"""R0: Baseline inventory and authority regression locks."""

from nl2spl.compiler.spl_editing.preview.model import (
    PreviewMaterializationResult,
    StageSliceTypedPlanRef,
)
from nl2spl.compiler.spl_editing.preview.store import PreviewStore
from nl2spl.compiler.spl_editing.preview.validators import (
    PreviewApplyExpectedState,
    validate_preview_not_stale,
)


def test_rendered_preview_text_is_not_apply_authority_invariant() -> None:
    """R0 Invariant: Changing the rendered preview text does not affect stale validator."""
    store = PreviewStore()

    # 1. Construct a valid preview result and save it to the store
    preview_id = "prev_test_invariant"
    r1 = PreviewMaterializationResult(
        preview_id=preview_id,
        base_snapshot_id="snap_base",
        intent_hash="intent_h",
        directive_hash="dir_h",
        closure_plan_hash="closure_h",
        selected_refset_id="refset_1",
        slice_typed_plan_hashes=(StageSliceTypedPlanRef("slice_1", "hash_1"),),
        preview_construct_hashes=("const_hash_1",),
        llm_generation_config_hash="llm_h",
        rendered_preview="StepIR(command_type=GENERAL_COMMAND, text='original formatted display')",
        strategy_id="strat_1",
        option_id="opt_1",
        interaction_contract_hash="contract_h",
        normalized_directive_hash="norm_dir_h",
        admitted_fact_hashes=("fact_h",),
    )

    store.put("sess_1", "issue_1", "snap_base", r1, ttl_seconds=60)

    # 2. Construct the expected state from candidates (matching r1)
    expected = PreviewApplyExpectedState(
        session_id="sess_1",
        issue_id="issue_1",
        base_snapshot_id="snap_base",
        intent_hash="intent_h",
        directive_hash="dir_h",
        closure_plan_hash="closure_h",
        selected_refset_id="refset_1",
        slice_typed_plan_hashes=(StageSliceTypedPlanRef("slice_1", "hash_1"),),
        preview_construct_hashes=("const_hash_1",),
        llm_generation_config_hash="llm_h",
        strategy_id="strat_1",
        option_id="opt_1",
        interaction_contract_hash="contract_h",
        normalized_directive_hash="norm_dir_h",
        admitted_fact_hashes=("fact_h",),
    )

    # Validation should pass successfully
    validated_1 = validate_preview_not_stale(store, preview_id, expected)
    assert (
        validated_1.rendered_preview
        == "StepIR(command_type=GENERAL_COMMAND, text='original formatted display')"
    )

    # 3. Save a modified preview result with a completely different rendered preview text,
    # but identical structural hashes.
    r2 = PreviewMaterializationResult(
        preview_id=preview_id,
        base_snapshot_id="snap_base",
        intent_hash="intent_h",
        directive_hash="dir_h",
        closure_plan_hash="closure_h",
        selected_refset_id="refset_1",
        slice_typed_plan_hashes=(StageSliceTypedPlanRef("slice_1", "hash_1"),),
        preview_construct_hashes=("const_hash_1",),
        llm_generation_config_hash="llm_h",
        rendered_preview=(
            "StepIR(command_type=GENERAL_COMMAND, "
            "text='MUTATED DISPLAY FORMAT - IGNORED BY VALIDATOR')"
        ),
        strategy_id="strat_1",
        option_id="opt_1",
        interaction_contract_hash="contract_h",
        normalized_directive_hash="norm_dir_h",
        admitted_fact_hashes=("fact_h",),
    )

    store.put("sess_1", "issue_1", "snap_base", r2, ttl_seconds=60)

    # 4. Re-run validation - it must STILL pass successfully without error, proving independence!
    validated_2 = validate_preview_not_stale(store, preview_id, expected)
    assert validated_2.rendered_preview == (
        "StepIR(command_type=GENERAL_COMMAND, text='MUTATED DISPLAY FORMAT - IGNORED BY VALIDATOR')"
    )
