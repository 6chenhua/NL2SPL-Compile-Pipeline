"""Deterministic hashing helpers for SPL Editing preview stale detection."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, is_dataclass
from typing import Any

from nl2spl.compiler.spl_editing.closure.model import ConstructClosurePlan
from nl2spl.compiler.spl_editing.intent.model import ConstructRepairIntent
from nl2spl.compiler.spl_editing.strategy.model import RepairDirective


def _make_json_safe(val: Any) -> Any:
    if isinstance(val, (tuple, list)):
        return [_make_json_safe(v) for v in val]
    if isinstance(val, dict):
        return {str(k): _make_json_safe(v) for k, v in sorted(val.items())}
    if is_dataclass(val):
        return _make_json_safe(asdict(val))
    return val


def compute_sha256(obj: Any) -> str:
    """Compute a stable, deterministic SHA-256 hash for any dataclass or serializable object."""
    safe_obj = _make_json_safe(obj)
    serialized = json.dumps(safe_obj, sort_keys=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def compute_intent_hash(intent: ConstructRepairIntent) -> str:
    """Compute deterministic hash of ConstructRepairIntent."""
    return compute_sha256(intent)


def compute_directive_hash(directive: RepairDirective) -> str:
    """Compute deterministic hash of RepairDirective."""
    return compute_sha256(directive)


def compute_closure_plan_hash(plan: ConstructClosurePlan) -> str:
    """Compute deterministic hash of ConstructClosurePlan."""
    return compute_sha256(plan)


def compute_selected_refset_hash(refset: Any) -> str:
    """Compute deterministic hash of SelectableRefSet or equivalent sequence of references."""
    if type(refset).__name__ == "SelectableRefSet":
        d = asdict(refset)
        if "refs" in d and isinstance(d["refs"], (list, tuple)):
            d["refs"] = sorted(d["refs"], key=lambda r: r.get("ref_id", ""))
        return compute_sha256(d)
    if isinstance(refset, (list, tuple)):
        sorted_refs = sorted(
            refset,
            key=lambda x: getattr(x, "ref_id", "") if hasattr(x, "ref_id") else str(x)
        )
        return compute_sha256(sorted_refs)
    return compute_sha256(refset)


def compute_slice_typed_plan_hashes_hash(
    refs: tuple[StageSliceTypedPlanRef, ...] | list[StageSliceTypedPlanRef] | dict[str, str]
) -> str:
    """Compute deterministic hash for slice typed plan hashes."""
    if isinstance(refs, (list, tuple)):
        sorted_refs = sorted(refs, key=lambda x: getattr(x, "slice_id", ""))
        return compute_sha256(sorted_refs)
    return compute_sha256(refs)


def compute_preview_construct_hashes_hash(hashes: tuple[str, ...] | list[str]) -> str:
    """Compute deterministic hash for preview construct hashes."""
    return compute_sha256(sorted(hashes))


def compute_llm_generation_config_hash(config: Any) -> str:
    """Compute deterministic hash of LLM generation config."""
    return compute_sha256(config)
