"""Deterministic admission for new child-worker outputs."""

from __future__ import annotations

import hashlib
import re

from nl2spl.compiler.spl_editing.admission.errors import NewFactAdmissionError
from nl2spl.compiler.spl_editing.admission.model import (
    AdmittedOutputDeclaration,
    NewOutputDeclarationDraft,
)

_RESERVED = {"worker", "flow", "block", "command", "input", "output", "mainworker"}
_ALLOWED_TYPES = {"text", "number", "boolean", "object", "list[text]"}


class NewFactAdmissionService:
    def admit_child_outputs(
        self,
        *,
        declarations: tuple[NewOutputDeclarationDraft, ...],
        snapshot,
        directive_id: str,
    ) -> tuple[AdmittedOutputDeclaration, ...]:
        existing = _existing_names(snapshot)
        admitted: list[AdmittedOutputDeclaration] = []
        seen_local: set[str] = set()
        for declaration in declarations:
            if not declaration.local_id.strip() or declaration.local_id in seen_local:
                raise NewFactAdmissionError("Output local_id must be non-empty and unique")
            seen_local.add(declaration.local_id)
            canonical = _canonical_name(declaration.display_name)
            if not canonical or canonical in _RESERVED:
                raise NewFactAdmissionError(f"Reserved or invalid output name '{canonical}'")
            if canonical in existing or any(item.canonical_name == canonical for item in admitted):
                raise NewFactAdmissionError(f"Output name conflict: '{canonical}'")
            data_type = (declaration.data_type_hint or "text").strip().lower()
            if data_type not in _ALLOWED_TYPES:
                raise NewFactAdmissionError(f"Unsupported output type '{data_type}'")
            stable = hashlib.sha256(
                f"{snapshot.snapshot_id}|{directive_id}|child_output|{declaration.local_id}".encode()
            ).hexdigest()[:16]
            admitted.append(
                AdmittedOutputDeclaration(
                    output_id=f"child_output_{stable}",
                    canonical_name=canonical,
                    display_name=declaration.display_name.strip(),
                    semantic_description=declaration.semantic_description.strip(),
                    data_type=data_type,
                    evidence_ref=f"provisional_repair_fact:{directive_id}:{declaration.local_id}",
                )
            )
        return tuple(admitted)


def _canonical_name(value: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip()).strip("_").lower()
    if text and text[0].isdigit():
        text = f"result_{text}"
    return text


def _existing_names(snapshot) -> set[str]:
    result: set[str] = set()
    table = snapshot.symbol_table
    if table is not None:
        for key in getattr(table, "_variables", {}):
            result.add(key[-1])
        result.update(getattr(table, "variables", {}).keys())
    plan = snapshot.worker_plan
    if plan is not None:
        for worker in plan.workers:
            result.update(field.name for field in worker.input_contract)
            result.update(field.name for field in worker.output_contract)
    return result
