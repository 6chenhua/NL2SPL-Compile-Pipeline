# IRS Test Contract

Required coverage scales with the slot behavior.

For every ConstructIRS:

- registry shape and actionability scope;
- checker instance extraction and slot satisfaction;
- diagnostic projection and authority metadata;
- no-demand negative behavior.

For every editable slot:

- RepairCatalog derivation;
- exact strategy linkage;
- runtime registration;
- target and structured context resolution;
- selectable-reference rejection of unknown refs;
- preview, confirmation, apply, and verification;
- negative test proving incomplete closure is not exposed as fixable.

CI must run the deterministic audit with scope all. P0 and unwaived P1 findings
fail. Waivers must include exact finding ID, construct, reason, owner, issue
reference, creation date, and expiry. Malformed, duplicate, and expired waivers
must fail the gate. CI must also run scripts/check_skill_mirrors.py.