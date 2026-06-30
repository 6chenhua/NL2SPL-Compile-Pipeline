# API Deferred Validation Downstream Handoff Contract

This contract defines how NL2SPL hands off API declarations when the user has
expressed API intent but NL2SPL does not have an authoritative OpenAPI or
API_IN_SPL contract.

## Authority boundary

- NL2SPL is authoritative for structural renderability only.
- The downstream SPL compiler or API validation layer is authoritative for real
  API contract validation.
- NL2SPL must not probe endpoints, credentials, provider availability, or
  network reachability.
- NL2SPL must not describe placeholder contracts as externally validated.

## Text-only handoff

Rendered SPL is the normative handoff for consumers that only read SPL text.
When an API declaration is structurally renderable but contract validation is
deferred, the renderer emits grammar-safe placeholders:

- OpenAPI placeholder: `{}`
- Functions placeholder: `{"functions":[]}`
- The matching `CALL` remains renderable when declaration identity and binding
  evidence are valid.

## Structured handoff

Structured consumers should read the pipeline result or snapshot fields:

- `APISpec.declaration_status == "grammar_minimal_partial"`
- `APISpec.schema_status == "unknown_placeholder"`
- `APISpec.functions_status == "unknown_placeholder"`
- `deferred_api_contract_validation` diagnostics:
  - `severity == "info"`
  - `blocks_rendering == false`
  - `blocks_completion == false`
  - `metadata.presentation_disposition == "deferred_validation"`
  - `metadata.validation_authority == "downstream_spl_compiler"`
  - `metadata.api_contract_validation_status == "pending"`

Malformed API declaration shapes are not deferred. They remain structural
fail-closed diagnostics and must not render as valid API declarations.
