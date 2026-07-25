"""Compatibility shim for IRS contract auditing.

The implementation lives in ``nl2spl.compiler.architecture_audit`` because it
intentionally checks cross-layer repair and strategy linkage.
"""

from nl2spl.compiler.architecture_audit.irs_contract_audit import (
    AuditFinding,
    AuditReport,
    AuditScope,
    AuditWaiver,
    FindingSeverity,
    _audit_registry,
    audit_irs_contract,
    load_waivers,
)

__all__ = [
    "AuditFinding",
    "AuditReport",
    "AuditScope",
    "AuditWaiver",
    "FindingSeverity",
    "_audit_registry",
    "audit_irs_contract",
    "load_waivers",
]
