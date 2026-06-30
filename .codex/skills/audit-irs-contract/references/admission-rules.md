# IRS Admission Rules

Accept a ConstructIRS only when it represents:

- an SPL grammar construct; or
- an architecture-approved compiler analysis or materialization construct with
  stable instances and ownership.

Reject source labels, route annotations, planner records, diagnostic kinds, and
presentation categories as ConstructIRS types.

For every accepted construct verify:

- stable construct identity;
- explicit existence policy;
- authoritative source signals;
- no-demand behavior;
- instance extraction ownership;
- checker and runner ownership;
- diagnostic projection boundary.

Delegation intent is source evidence. Repair targets must be real worker,
handoff, promotion, or invocation constructs.