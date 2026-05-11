"""Input adapters for NL2SPL."""

from nl2spl.adapters.base import InputAdapter
from nl2spl.adapters.generic_nl import GenericNLAdapter
from nl2spl.adapters.registry import InputAdapterRegistry
from nl2spl.adapters.structural_nl import StructuralNLAdapter

__all__ = [
    "GenericNLAdapter",
    "InputAdapter",
    "InputAdapterRegistry",
    "StructuralNLAdapter",
]
