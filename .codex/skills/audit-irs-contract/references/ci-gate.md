# CI Gate

## Required Repository Components

The skill CLI is intentionally thin. CI requires all of these repository files:

- src/nl2spl/compiler/irs/audit.py
- .agents/skills/audit-irs-contract/scripts/audit_irs_contract.py
- .agents/skills/audit-irs-contract/waivers.json
- scripts/check_skill_mirrors.py
- tests/unit/compiler/irs/test_irs_contract_audit_guardrail.py

The skill package must not contain a second audit backend.

## Commands

Registry-wide audit:

~~~bash
python .agents/skills/audit-irs-contract/scripts/audit_irs_contract.py \
  --scope all \
  --format json
~~~

Skill mirror check:

~~~bash
python scripts/check_skill_mirrors.py \
  --skill irs-knowledge \
  --skill audit-irs-contract
~~~

Focused CI tests:

~~~bash
python -m pytest \
  tests/unit/compiler/irs/test_irs_contract_audit_guardrail.py \
  -q
~~~

## Exit Policy

- unwaived P0 finding: exit non-zero;
- unwaived P1 finding: exit non-zero;
- P2 finding: report without blocking;
- expired waiver: exit non-zero;
- malformed waiver: exit non-zero;
- duplicate finding and construct waiver identity: exit non-zero;
- skill mirror mismatch: exit non-zero.

## Waiver Schema

Every waiver requires:

- finding_id
- construct
- reason
- owner
- issue_ref
- created_at
- expires

created_at and expires use ISO 8601 dates. created_at must not be after expires.
Waivers are exact finding identities, not wildcard suppression.