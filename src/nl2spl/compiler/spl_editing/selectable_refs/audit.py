"""Audit selectable refs."""

from __future__ import annotations

from typing import Any

from nl2spl.compiler.spl_editing.selectable_refs.model import SelectableRefSet


def audit_refset_quality(refset: SelectableRefSet) -> dict[str, Any]:
    """Basic quality check on the selectable refset."""
    return {
        "total_refs": len(refset.refs),
        "kinds": {r.ref_kind for r in refset.refs},
        "roles": {r.ref_role for r in refset.refs},
    }
