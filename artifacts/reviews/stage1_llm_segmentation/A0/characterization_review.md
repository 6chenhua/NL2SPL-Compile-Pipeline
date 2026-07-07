# Phase A0: Characterization Review

- **Date**: 2026-07-05
- **Goal**: Lock current failure modes where `When enough required information is available` is split from `produce a draft` and materialized as a guard-only `GENERAL_COMMAND`.

## Locked Gaps

1. **Unit Test**: `tests/unit/pipeline/stage1/test_stage1_current_boundary_characterization.py`
   - Confirms that the current legacy span slicer splits `When enough required information is available` (tail of `s16`) from `produce a draft. If the user asks for revision` (head of `s17`).
2. **Integration Test**: `tests/integration/pipeline/test_stage1_llm_segmentation_characterization.py`
   - Confirms that the split results in `When enough required information is available.` being materialized as a `GENERAL_COMMAND` at Stage 7, instead of grouping it as a guard condition for the draft step.
