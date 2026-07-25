"""Default diagnostic registry factory."""

from nl2spl.compiler.diagnostics.registry import DiagnosticRegistry


def build_default_diagnostic_registry() -> DiagnosticRegistry:
    return DiagnosticRegistry.default()


__all__ = ["build_default_diagnostic_registry"]
