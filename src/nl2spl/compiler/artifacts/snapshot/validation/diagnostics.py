"""Diagnostic validation — irs_ref presence, repairability metadata."""

from __future__ import annotations

from nl2spl.compiler.artifacts.snapshot.model.document import SnapshotDocument
from nl2spl.ir.diagnostics import CompileDiagnostic, DiagnosticIRSRef

_EDITABLE_KINDS = frozenset({
    "missing_handler",
    "missing_output_producer",
    "type_or_contract_ambiguity",
})


def validate_diagnostics(document: SnapshotDocument) -> list[str]:
    """Validate that editable diagnostics carry required metadata.

    Checks that every ``CompileDiagnostic`` with an editable kind has:
    - ``metadata["irs_ref"]`` present and a valid ``DiagnosticIRSRef``.
    - ``metadata["authority"]`` present.
    - ``metadata["repairability"]`` present.
    - ``metadata["issue_group_id"]`` present.

    Returns a list of error messages (empty = valid).
    """
    errors: list[str] = []
    diags = document.payload.diagnostics.compile_diagnostics

    for diag in diags:
        if not isinstance(diag, CompileDiagnostic):
            continue
        if diag.kind not in _EDITABLE_KINDS:
            continue

        meta = diag.metadata if diag.metadata else {}
        d_id = diag.diagnostic_id

        # irs_ref is the critical field
        irs_ref = meta.get("irs_ref")
        if irs_ref is None:
            errors.append(
                f"Diagnostic {d_id} (kind={diag.kind}) is editable but "
                f"missing metadata['irs_ref']"
            )
        elif not isinstance(irs_ref, (DiagnosticIRSRef, dict)):
            errors.append(
                f"Diagnostic {d_id} metadata['irs_ref'] is not a "
                f"DiagnosticIRSRef: got {type(irs_ref).__name__}"
            )
        else:
            # Extract values for validation (works for both dict and DiagnosticIRSRef)
            _check_irs_ref_values(irs_ref, d_id, errors)

        # authority — must be a non-empty string
        auth = meta.get("authority")
        if not auth or not isinstance(auth, str) or not auth.strip():
            errors.append(
                f"Diagnostic {d_id} is editable but metadata['authority'] "
                f"is missing or not a non-empty string"
            )

        # repairability — must be a non-empty string
        rep = meta.get("repairability")
        if not rep or not isinstance(rep, str) or not rep.strip():
            errors.append(
                f"Diagnostic {d_id} is editable but metadata['repairability'] "
                f"is missing or not a non-empty string"
            )

        # issue_group_id — must be a non-empty string
        gid = meta.get("issue_group_id")
        if not gid or not isinstance(gid, str) or not gid.strip():
            errors.append(
                f"Diagnostic {d_id} is editable but metadata['issue_group_id'] "
                f"is missing or not a non-empty string"
            )

    return errors


def _check_irs_ref_values(
    irs_ref: object, diag_id: str, errors: list[str],
) -> None:
    """Validate that irs_ref has non-empty required string fields."""
    if isinstance(irs_ref, DiagnosticIRSRef):
        vals = {
            "construct_type": irs_ref.construct_type,
            "construct_id": irs_ref.construct_id,
            "slot_name": irs_ref.slot_name,
        }
    else:
        vals = {
            k: irs_ref.get(k, "")  # type: ignore[union-attr]
            for k in ("construct_type", "construct_id", "slot_name")
        }
    for key, val in vals.items():
        if not val or not isinstance(val, str) or not val.strip():
            errors.append(
                f"Diagnostic {diag_id} metadata['irs_ref'].{key} "
                f"must be a non-empty string, got {val!r}"
            )
