"""Serializer registry — dispatches by ``$type`` and by Python class.

The registry is the central dispatch for all artifact serialization.
It must be built via ``build_default_registry()``, which registers every
MVP serializer.  Callers MUST NOT instantiate the registry directly
without registering at least the required set of serializers.
"""

from __future__ import annotations

from typing import Any

from nl2spl.compiler.artifacts.snapshot.serialization.protocol import ArtifactSerializer

# JSON key written into every serialized artifact dict
_TYPE_KEY: str = "$type"


class SerializerRegistry:
    """Maps ``type_id`` strings and Python classes to serializers.

    Two lookup axes:
    - ``by_type_id`` — for deserialization (dict ``$type`` -> serializer).
    - ``by_class`` — for serialization (Python object type -> serializer).

    Unknown types raise ``ValueError`` — no fallback, no ``str(obj)``.
    """

    def __init__(self) -> None:
        self._by_type_id: dict[str, ArtifactSerializer] = {}
        self._by_class: dict[type, ArtifactSerializer] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, serializer: ArtifactSerializer) -> None:
        """Register *serializer* in the registry.

        Raises ``ValueError`` if the ``type_id`` is already registered
        with a different serializer.
        """
        tid = serializer.type_id
        existing = self._by_type_id.get(tid)
        if existing is not None and existing is not serializer:
            raise ValueError(
                f"type_id {tid!r} already registered by "
                f"{type(existing).__name__}"
            )
        self._by_type_id[tid] = serializer

    def register_for_class(self, cls: type, serializer: ArtifactSerializer) -> None:
        """Associate *serializer* with a Python class for serialization dispatch.

        This is separate from ``register`` because a single serializer may
        handle multiple classes (or a class may not have a direct 1:1
        mapping with a type_id).  Call ``register`` first, then call this.

        Raises ``ValueError`` if *cls* is already mapped to a different
        serializer.
        """
        existing = self._by_class.get(cls)
        if existing is not None and existing is not serializer:
            raise ValueError(
                f"Class {cls.__name__!r} already registered to "
                f"{type(existing).__name__} (type_id={existing.type_id!r})"
            )
        self._by_class[cls] = serializer

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def get_by_type_id(self, type_id: str) -> ArtifactSerializer:
        """Return the serializer for *type_id*.

        Raises ``ValueError`` if no serializer is registered for *type_id*.
        """
        if type_id not in self._by_type_id:
            raise ValueError(
                f"Unknown artifact $type: {type_id!r}. "
                f"No serializer registered."
            )
        return self._by_type_id[type_id]

    def get_by_class(self, cls: type) -> ArtifactSerializer:
        """Return the serializer for Python class *cls*.

        Raises ``ValueError`` if no serializer is registered for *cls*.
        """
        if cls not in self._by_class:
            raise ValueError(
                f"No serializer registered for Python class "
                f"{cls.__name__!r}"
            )
        return self._by_class[cls]

    # ------------------------------------------------------------------
    # Serialize / deserialize
    # ------------------------------------------------------------------

    def serialize(self, obj: Any) -> dict[str, Any]:
        """Convert *obj* to a canonical dict (includes ``"$type"``).

        Raises ``ValueError`` if no serializer is registered for
        ``type(obj)``.
        """
        serializer = self.get_by_class(type(obj))
        return serializer.to_canonical(obj)

    def deserialize(self, data: dict[str, Any]) -> Any:
        """Reconstruct a typed object from a canonical dict.

        The dict MUST contain a ``"$type"`` key.  Raises ``ValueError``
        if the key is missing or the type is unknown.
        """
        if _TYPE_KEY not in data:
            raise ValueError(
                f"Serialized artifact dict missing {_TYPE_KEY!r} key"
            )
        type_id = data[_TYPE_KEY]
        if not isinstance(type_id, str):
            raise ValueError(
                f"{_TYPE_KEY!r} must be a string, got {type(type_id).__name__}"
            )
        serializer = self.get_by_type_id(type_id)
        return serializer.from_canonical(data)

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def registered_type_ids(self) -> tuple[str, ...]:
        """Return all registered type_id strings."""
        return tuple(self._by_type_id.keys())

    def __len__(self) -> int:
        return len(self._by_type_id)


# ---------------------------------------------------------------------------
# Default registry factory
# ---------------------------------------------------------------------------


def build_default_registry() -> SerializerRegistry:
    """Build a ``SerializerRegistry`` with all MVP serializers registered.

    Each serializer family module defines a ``register_all(registry)``
    function.  This factory calls them all.
    """
    registry = SerializerRegistry()

    # Import and register each family.  Placed inline to avoid circular
    # imports — each module may import IR types lazily.

    from nl2spl.compiler.artifacts.snapshot.serialization.serializers_assembly import (
        register_all as _asm,
    )
    from nl2spl.compiler.artifacts.snapshot.serialization.serializers_compile import (
        register_all as _compile,
    )
    from nl2spl.compiler.artifacts.snapshot.serialization.serializers_diagnostics import (
        register_all as _diag,
    )
    from nl2spl.compiler.artifacts.snapshot.serialization.serializers_dto import (
        register_all as _dto,
    )
    from nl2spl.compiler.artifacts.snapshot.serialization.serializers_plan import (
        register_all as _plan,
    )
    from nl2spl.compiler.artifacts.snapshot.serialization.serializers_resource import (
        register_all as _res,
    )
    from nl2spl.compiler.artifacts.snapshot.serialization.serializers_source import (
        register_all as _src,
    )
    from nl2spl.compiler.artifacts.snapshot.serialization.serializers_symbol import (
        register_all as _symbol,
    )

    _dto(registry)
    _diag(registry)
    _compile(registry)
    _symbol(registry)
    _res(registry)
    _src(registry)
    _plan(registry)
    _asm(registry)

    return registry


# ---------------------------------------------------------------------------
# Cached singleton
# ---------------------------------------------------------------------------

_default_registry: SerializerRegistry | None = None


def get_default_registry() -> SerializerRegistry:
    """Return the cached default registry, building it on first call."""
    global _default_registry
    if _default_registry is None:
        _default_registry = build_default_registry()
    return _default_registry
