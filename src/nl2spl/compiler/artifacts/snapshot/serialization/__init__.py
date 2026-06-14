"""Canonical JSON serialization for snapshot artifacts.

Provides:
- ``ArtifactSerializer`` — ABC for typed serializer implementations.
- ``SerializerRegistry`` — type-dispatch registry (fail-fast on unknown).
- ``build_default_registry()`` — factory with all MVP serializers.
- ``get_default_registry()`` — cached singleton.

Leaf-level conversion helpers live in ``_canonical.py`` (private).
"""

from __future__ import annotations

from nl2spl.compiler.artifacts.snapshot.serialization.protocol import ArtifactSerializer
from nl2spl.compiler.artifacts.snapshot.serialization.registry import (
    SerializerRegistry,
    build_default_registry,
    get_default_registry,
)

__all__ = [
    "ArtifactSerializer",
    "SerializerRegistry",
    "build_default_registry",
    "get_default_registry",
]
