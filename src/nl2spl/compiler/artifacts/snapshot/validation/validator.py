"""SnapshotValidator — orchestrates all sub-validators.

Takes a ``SnapshotDocument``, runs every sub-validator, and returns a
``SnapshotValidationResult`` with errors, effective capabilities, and
capability failures.
"""

from __future__ import annotations

from nl2spl.compiler.artifacts.snapshot.model.document import SnapshotDocument
from nl2spl.compiler.artifacts.snapshot.model.validation import (
    SnapshotValidationResult,
)
from nl2spl.compiler.artifacts.snapshot.validation.artifact_refs import (
    validate_artifact_refs,
)
from nl2spl.compiler.artifacts.snapshot.validation.capabilities import (
    derive_effective_capabilities,
)
from nl2spl.compiler.artifacts.snapshot.validation.diagnostics import (
    validate_diagnostics,
)
from nl2spl.compiler.artifacts.snapshot.validation.identity import validate_identity
from nl2spl.compiler.artifacts.snapshot.validation.integrity import (
    compute_artifact_set_hash,
    compute_payload_hash,
    validate_integrity,
)
from nl2spl.compiler.artifacts.snapshot.validation.payload_shape import (
    validate_envelope,
    validate_payload_shape,
)
from nl2spl.compiler.artifacts.snapshot.validation.schema_version import (
    validate_schema_version,
)


class SnapshotValidator:
    """Orchestrating validator for snapshot documents.

    Usage::

        validator = SnapshotValidator()
        result = validator.validate(document)
        if result.is_valid:
            ...
        else:
            for err in result.errors:
                print(err)
    """

    def validate(self, document: SnapshotDocument) -> SnapshotValidationResult:
        """Validate *document* and return a ``SnapshotValidationResult``.

        Runs all sub-validators in order.  Even if early validators find
        errors, later validators still run (no short-circuit).
        """
        errors: list[str] = []

        # Structural checks
        errors.extend(validate_envelope(document))
        errors.extend(validate_identity(document))
        errors.extend(validate_schema_version(document))
        errors.extend(validate_payload_shape(document))

        # Content checks
        errors.extend(validate_diagnostics(document))
        errors.extend(validate_artifact_refs(document))

        # Capability derivation (always runs, even if errors exist)
        effective_caps = derive_effective_capabilities(document)

        # Integrity hashes
        payload_hash = compute_payload_hash(document)
        artifact_set_hash = compute_artifact_set_hash(document)
        errors.extend(
            validate_integrity(document, payload_hash, artifact_set_hash)
        )

        return SnapshotValidationResult(
            is_valid=len(errors) == 0,
            errors=tuple(errors),
            effective_capabilities=effective_caps,
            capability_failures=effective_caps.failures,
        )
