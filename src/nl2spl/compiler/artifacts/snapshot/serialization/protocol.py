"""Serializer protocol — the contract every artifact serializer must fulfill.

Every serializer handles ONE artifact type and its direct nested types
(if any).  The registry dispatches by ``$type``; serializers must NOT
import from ``spl_editing`` internals.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class ArtifactSerializer(ABC):
    """Protocol for serializing a single artifact type to/from canonical JSON dicts.

    Subclasses MUST:
    - Define ``type_id`` as a class-level string property returning the
      stable artifact name (e.g. ``"SpanIR"``).
    - Implement ``to_canonical(obj)`` which converts a typed object into a
      dict of JSON-native values PLUS a ``"$type"`` key.
    - Implement ``from_canonical(data)`` which reconstructs the typed
      object from the canonical dict (``"$type"`` is ignored on input).
    """

    # ------------------------------------------------------------------
    # Class-level identity
    # ------------------------------------------------------------------

    @property
    @abstractmethod
    def type_id(self) -> str:
        """Stable artifact type string written into the ``"$type"`` key.

        Examples: ``"SpanIR"``, ``"WorkerPlanIR"``, ``"TraceRecord"``.
        """
        ...

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    @abstractmethod
    def to_canonical(self, obj: Any) -> dict[str, Any]:
        """Convert *obj* to a canonical dict of JSON-native values.

        The returned dict MUST include a ``"$type"`` key set to ``type_id``.
        Every dict value MUST be a JSON-native type (str, int, float, bool,
        None, list, dict).  No ``Path``, ``datetime``, ``Enum``, ``tuple``,
        ``set``, or arbitrary Python objects are allowed in the output.
        """
        ...

    @abstractmethod
    def from_canonical(self, data: dict[str, Any]) -> Any:
        """Reconstruct the typed object from a canonical dict.

        *data* is the dict previously produced by ``to_canonical``
        (including the ``"$type"`` key, which may be ignored during
        reconstruction).
        """
        ...
