"""Errors raised by the repair drafting substrate."""


class RepairDraftingError(ValueError):
    """Base class for repair drafting errors."""


class RepairDraftSerializationError(RepairDraftingError):
    """Raised when a draft DTO cannot be serialized or parsed."""


class RepairFieldValueScopeError(RepairDraftingError):
    """Raised when a provider consumes a value outside its ownership scope."""

