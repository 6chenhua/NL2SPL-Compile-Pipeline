"""Stateful ID allocator context."""

from __future__ import annotations

import re
from typing import Any, Literal

NamespaceType = Literal["step", "block", "handoff"]


class IdAllocator:
    """Statefully scans existing artifact IDs and generates new unique ones."""

    def __init__(
        self,
        existing_step_ids: set[str],
        existing_block_ids: set[str],
        existing_handoff_ids: set[str],
        supported_namespaces: tuple[NamespaceType, ...],
    ) -> None:
        valid_ns = {"step", "block", "handoff"}
        for ns in supported_namespaces:
            if ns not in valid_ns:
                raise ValueError(f"Unknown namespace: {ns}")

        self._used_step_ids = set(existing_step_ids)
        self._used_block_ids = set(existing_block_ids)
        self._used_handoff_ids = set(existing_handoff_ids)
        self._supported_namespaces = set(supported_namespaces)

    @classmethod
    def from_snapshot(cls, snapshot: Any, supported_namespaces: tuple[str, ...]) -> IdAllocator:
        """Create an allocator statefully scanning the snapshot's existing IDs."""
        valid_ns = {"step", "block", "handoff"}
        for ns in supported_namespaces:
            if ns not in valid_ns:
                raise ValueError(f"Unknown namespace: {ns}")

        step_ids: set[str] = set()
        block_ids: set[str] = set()
        handoff_ids: set[str] = set()
        actual_supported: list[NamespaceType] = []

        # 1. Step IDs
        if "step" in supported_namespaces:
            art = getattr(snapshot, "worker_step_plan", None)
            if art is not None:
                try:
                    for step in art.get_all_steps():
                        step_ids.add(step.step_id)
                    actual_supported.append("step")
                except Exception:
                    pass

        # 2. Block IDs
        if "block" in supported_namespaces:
            art = getattr(snapshot, "worker_block_plan", None)
            if art is not None:
                try:
                    for block_structure in art.worker_blocks.values():
                        for block in block_structure.get_all_blocks():
                            block_ids.add(block.block_id)
                    actual_supported.append("block")
                except Exception:
                    pass

        # 3. Handoff IDs.  The namespace includes both materialized
        # WorkerHandoffIR records and existing INVOKE_WORKER step references;
        # persisted snapshots may contain a pending invoke step whose handoff
        # contract is the missing artifact being repaired.
        if "handoff" in supported_namespaces:
            handoff_source_found = False
            art = getattr(snapshot, "worker_plan", None)
            if art is not None:
                handoff_source_found = True
                try:
                    for handoff in art.handoffs:
                        handoff_ids.add(handoff.handoff_id)
                except Exception:
                    pass
            step_art = getattr(snapshot, "worker_step_plan", None)
            if step_art is not None:
                handoff_source_found = True
                try:
                    for step in step_art.get_all_steps():
                        handoff_id = getattr(step, "handoff_id", None)
                        if handoff_id:
                            handoff_ids.add(str(handoff_id))
                except Exception:
                    pass
            if handoff_source_found:
                actual_supported.append("handoff")

        return cls(
            existing_step_ids=step_ids,
            existing_block_ids=block_ids,
            existing_handoff_ids=handoff_ids,
            supported_namespaces=tuple(actual_supported),
        )

    def is_namespace_available(self, namespace: str) -> bool:
        """Check if the given namespace is supported/available in this allocator."""
        return namespace in self._supported_namespaces

    def allocate_step_id(self) -> str:
        """Allocate a unique step ID matching 'st{N}' format."""
        if not self.is_namespace_available("step"):
            raise ValueError("Namespace 'step' is not available in this allocator context.")

        max_val = 0
        for sid in self._used_step_ids:
            matches = re.findall(r"\d+", sid)
            if matches:
                for val_str in matches:
                    max_val = max(max_val, int(val_str))

        next_val = max_val + 1
        next_id = f"st{next_val}"
        self._used_step_ids.add(next_id)
        return next_id

    def allocate_block_id(self, worker_id: str = "") -> str:
        """Allocate a unique block ID matching 'b_repair_{N}' format."""
        if not self.is_namespace_available("block"):
            raise ValueError("Namespace 'block' is not available in this allocator context.")

        max_val = 0
        for bid in self._used_block_ids:
            matches = re.findall(r"\d+", bid)
            if matches:
                for val_str in matches:
                    max_val = max(max_val, int(val_str))

        next_val = max_val + 1
        next_id = f"b_repair_{next_val}"
        self._used_block_ids.add(next_id)
        return next_id

    def allocate_handoff_id(self) -> str:
        """Allocate a unique handoff ID matching 'handoff_repair_{N}' format."""
        if not self.is_namespace_available("handoff"):
            raise ValueError("Namespace 'handoff' is not available in this allocator context.")

        max_val = 0
        for hid in self._used_handoff_ids:
            matches = re.findall(r"\d+", hid)
            if matches:
                for val_str in matches:
                    max_val = max(max_val, int(val_str))

        next_val = max_val + 1
        next_id = f"handoff_repair_{next_val}"
        self._used_handoff_ids.add(next_id)
        return next_id
