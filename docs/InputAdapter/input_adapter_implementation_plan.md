# InputAdapter Implementation Plan

Date: 2026-05-10

## Scope

Implement Phase 1 plus MVP integration:

- canonical input contract
- structural and generic adapters
- orchestrator adaptation step
- Stage 1/2/6/9 MVP consumption
- unit and integration regression tests

## Execution Checklist

1. Implement canonical models and validator.
2. Implement adapter base, registry, generic fallback, and structural parser.
3. Integrate `CanonicalCompileInput` into Stage 1.
4. Integrate adapter-aware routing into Stage 2.
5. Seed hard fact variables in Stage 6.
6. Add constraint hint context to Stage 9.
7. Record adapter diagnostics in orchestrator results.
8. Add tests from `docs/input_adapter_test_matrix.md`.

## Non-Goals

- No LLM-assisted adapter.
- No complete semantic coverage validator.
- No direct generation of SPL or compiler IR.
- No conversion of delegation hints into worker candidates.

