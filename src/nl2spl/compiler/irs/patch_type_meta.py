"""Compatibility shim for repair patch-type metadata.

New code should import from ``nl2spl.compiler.repair_contracts``.
"""

from nl2spl.compiler.repair_contracts import PatchTypeMeta

__all__ = ["PatchTypeMeta"]
