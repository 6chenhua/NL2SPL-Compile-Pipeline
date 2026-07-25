"""Compatibility shim for diagnostic registry types.

New code should import from ``nl2spl.compiler.diagnostics``.
"""

from nl2spl.compiler.diagnostics import DiagnosticRegistry, DiagnosticSpec, Severity

__all__ = ["DiagnosticRegistry", "DiagnosticSpec", "Severity"]
