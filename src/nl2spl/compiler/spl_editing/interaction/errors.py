class RepairInteractionError(ValueError):
    """Invalid or unavailable repair interaction contract."""


class RepairInteractionNotFoundError(RepairInteractionError):
    pass
