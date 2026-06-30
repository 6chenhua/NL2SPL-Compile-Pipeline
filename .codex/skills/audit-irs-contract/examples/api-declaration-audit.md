# API Declaration Audit Example

Expected decisions:

- API_DECLARATION.openapi_schema: non_editable, deferred_validation
- API_DECLARATION.functions: non_editable, deferred_validation
- neither slot declares a repair affordance

CALL_API.integration_evidence is a separate compatibility slot. If it declares
an affordance without strategy, materialization, and runtime registration, the
audit reports a runtime_closure_incomplete P1. It must not be presented as a
complete API declaration repair.