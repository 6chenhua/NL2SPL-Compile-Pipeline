# Diagnostic Authority

Checkers assess slot satisfaction. They must not:

- call an LLM;
- parse raw natural language;
- mutate IR;
- synthesize missing constructs;
- create final CompileDiagnostic objects directly.

DiagnosticProjector owns conversion from satisfaction reports to compiler
diagnostics and must attach structured IRS references and authority metadata.

Every SlotSpec.missing_diagnostic must resolve in DiagnosticRegistry. Required
slot semantics, renderability, and diagnostic blocking behavior must agree.
No-demand constructs must not emit missing-slot diagnostics.