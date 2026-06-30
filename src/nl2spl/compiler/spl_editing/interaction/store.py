class NormalizedDirectiveStore:
    def __init__(self) -> None:
        self._items = {}

    def put(self, directive) -> None:
        if directive.directive_id in self._items and self._items[directive.directive_id] != directive:
            raise ValueError(f"Directive identity collision: {directive.directive_id}")
        self._items[directive.directive_id] = directive

    def get(self, directive_id: str):
        return self._items[directive_id]

    def has(self, directive_id: str) -> bool:
        return directive_id in self._items
