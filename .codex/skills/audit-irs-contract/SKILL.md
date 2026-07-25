---
name: audit-irs-contract
description: >
  Audit an existing NL2SPL ConstructIRS implementation for admission,
  SlotSpec completeness, typed actionability decisions, diagnostics,
  runtime repair closure, and test coverage. Use after creating or modifying
  IRS registry entries, checkers, diagnostics, or SPL Editing affordances.
---

# Audit IRS Contract

Audit an already-created IRS implementation. Do not create new IRS behavior
unless reporting a missing contract. IRS creation belongs to irs-knowledge.

Prefer deterministic findings from the audit script over narrative judgment.
Then perform the semantic checks that cannot be proven mechanically.

## Required Workflow

1. Identify the construct or registry scope being reviewed.
2. Run:

~~~bash
python .agents/skills/audit-irs-contract/scripts/audit_irs_contract.py \
  --construct CONSTRUCT_TYPE \
  --scope all \
  --format json
~~~

Omit --construct for a registry-wide audit.

3. Resolve or explicitly report every unwaived P0 and P1.
4. Read the references selected below and perform the semantic review.
5. Report the verdict and contract matrix. Do not hide waived findings.

## Repository Integration Contract

This is a repository-integrated skill, not a standalone audit implementation.

- CLI wrapper:
  .agents/skills/audit-irs-contract/scripts/audit_irs_contract.py
- Deterministic backend:
  src/nl2spl/compiler/architecture_audit/irs_contract_audit.py
- CI guardrail:
  tests/unit/compiler/irs/test_irs_contract_audit_guardrail.py
- Mirror verifier:
  scripts/check_skill_mirrors.py

The legacy module `src/nl2spl/compiler/irs/audit.py` is a compatibility shim.
The CLI must import the architecture-audit backend directly and fail clearly
when the NL2SPL package or deterministic backend is not available. Do not copy
the backend into the skill package; that would create a second registry
interpretation.

## CI Gate

Run the registry-wide gate with:

~~~bash
python .agents/skills/audit-irs-contract/scripts/audit_irs_contract.py \
  --scope all \
  --format json
~~~

Failure policy:

- unwaived P0: fail;
- unwaived P1: fail;
- P2: warn;
- expired waiver: fail;
- malformed or duplicate waiver: fail.

See references/ci-gate.md for the complete repository contract.

## Canonical Skill And Mirror

Canonical source:

    .agents/skills/audit-irs-contract

Generated mirror:

    .codex/skills/audit-irs-contract

Do not manually maintain divergent copies. Synchronize or verify with:

~~~bash
python scripts/check_skill_mirrors.py \
  --skill audit-irs-contract
~~~

## Reference Routing

- Admission or construct identity questions:
  read references/admission-rules.md.
- Slot requiredness, actionability, or affordance questions:
  read references/slot-actionability-decision.md.
- Handler, strategy, materialization, preview, apply, or verification questions:
  read references/repair-runtime-closure.md.
- Checker, diagnostic, projector, or authority questions:
  read references/diagnostic-authority.md.
- Test and CI completeness questions:
  read references/test-contract.md and references/ci-gate.md.
- Full review or uncertain scope:
  read references/audit-matrix.md.

## Responsibility Boundary

This skill:

- audits registry, runtime, diagnostic, and test coherence;
- classifies findings as P0, P1, or P2;
- identifies missing contracts and runtime closure;
- checks explicit waivers and their expiry.

This skill does not:

- invent repair strategies;
- add affordances because a slot has a diagnostic;
- call an LLM to decide machine-checkable invariants;
- mutate IR or implement a repair;
- replace irs-knowledge.

## Actionability Rule

A slot requires an explicit SlotActionabilityDecision when any condition holds:

- required_for_partial is true;
- required_for_complete is true;
- missing_diagnostic is not null;
- repair_affordances is not empty.

The invariants are:

- editable requires one or more affordances and complete runtime closure;
- non_editable forbids affordances and requires a disposition;
- optional_enrichment must not block rendering or completion and must not
  become a mandatory editable issue.

## Output Contract

Use this structure:

    Verdict: pass | conditional_pass | fail

    P0 findings:
    - ...

    P1 findings:
    - ...

Contract matrix:

| construct | slot | required_for | diagnostic | actionability | affordance | runtime closure |
| --- | --- | --- | --- | --- | --- | --- |

    Admission decision:
    - accepted / rejected
    - reason

    Repairability decision:
    - editable
    - review_only
    - deferred_validation
    - developer_only
    - non_repairable

    Runtime closure:
    - strategy
    - handler
    - context builder
    - target resolver
    - patch adapter
    - materialization plan
    - preview/apply
    - verifier

    Missing tests:
    - ...

    Waivers:
    - finding ID, owner, issue reference, reason, creation date, expiry

    Residual risks:
    - ...

P0 is reserved for broken product semantics or authority boundaries. P1 is a
required closure or production-readiness gap. P2 is non-blocking hardening.
