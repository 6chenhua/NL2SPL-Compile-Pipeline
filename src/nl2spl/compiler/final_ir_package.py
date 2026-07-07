from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from nl2spl.compiler.compile_result import CompileAssumption
    from nl2spl.ir.agent_profile_ir import AgentProfileIR
    from nl2spl.ir.constraint_ir import ConstraintIR
    from nl2spl.ir.diagnostics import CompileDiagnostic, TraceRecord
    from nl2spl.ir.resource_registry_ir import ResourceRegistryIR
    from nl2spl.ir.step_ir import StepIR
    from nl2spl.ir.symbol_table import SymbolTable
    from nl2spl.ir.worker_ir import WorkerIR


def _deterministic_serialize(val: Any) -> Any:
    """Helper to recursively convert objects to JSON-serializable structures."""
    if hasattr(val, "to_dict"):
        return val.to_dict()
    if isinstance(val, (set, frozenset)):
        serialized_items = [_deterministic_serialize(x) for x in val]
        try:
            return sorted(serialized_items)
        except TypeError:
            return sorted(
                serialized_items, key=lambda x: json.dumps(x, sort_keys=True, default=str)
            )
    if isinstance(val, (list, tuple)):
        return [_deterministic_serialize(x) for x in val]
    if isinstance(val, dict):
        return {str(k): _deterministic_serialize(v) for k, v in val.items()}
    if isinstance(val, Enum):
        return val.value
    if hasattr(val, "__dataclass_fields__"):
        res = {}
        for name in val.__dataclass_fields__:
            res[name] = _deterministic_serialize(getattr(val, name))
        return res
    if hasattr(val, "__dict__"):
        return {
            k: _deterministic_serialize(v) for k, v in val.__dict__.items() if not k.startswith("_")
        }
    return val


def compute_package_hash(
    root_worker: WorkerIR,
    profile: AgentProfileIR,
    resources: ResourceRegistryIR,
    symbol_table: SymbolTable,
    constraints: tuple[ConstraintIR, ...],
    diagnostics: tuple[CompileDiagnostic, ...],
    traces: tuple[TraceRecord, ...],
    assumptions: tuple[CompileAssumption, ...],
    verification_metadata: Mapping[str, Any],
) -> str:
    """Compute a deterministic hash of the package contents, excluding any rendered SPL text."""
    payload = {
        "root_worker": _deterministic_serialize(root_worker),
        "profile": _deterministic_serialize(profile),
        "resources": _deterministic_serialize(resources),
        "symbol_table": _deterministic_serialize(symbol_table),
        "constraints": _deterministic_serialize(constraints),
        "diagnostics": _deterministic_serialize(diagnostics),
        "traces": _deterministic_serialize(traces),
        "assumptions": _deterministic_serialize(assumptions),
        "verification_metadata": _deterministic_serialize(verification_metadata),
    }
    serialized = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class FinalIRPackage:
    package_id: str
    artifact_snapshot_id: str | None
    overlay_version: int | None
    package_hash: str
    root_worker: WorkerIR
    profile: AgentProfileIR
    resources: ResourceRegistryIR
    symbol_table: SymbolTable
    constraints: tuple[ConstraintIR, ...] = ()
    diagnostics: tuple[CompileDiagnostic, ...] = ()
    traces: tuple[TraceRecord, ...] = ()
    assumptions: tuple[CompileAssumption, ...] = ()
    verification_metadata: Mapping[str, Any] = field(default_factory=dict)
    legacy_unscoped_steps: tuple[StepIR, ...] = ()
