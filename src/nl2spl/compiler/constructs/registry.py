"""Registry shell for ConstructIRS definitions."""

from __future__ import annotations

from nl2spl.compiler.constructs.spec import ConstructIRS


class SPLConstructRegistry:
    """Registry of ConstructIRS definitions keyed by construct type."""

    def __init__(self) -> None:
        self._constructs: dict[str, ConstructIRS] = {}

    # -- mutation -----------------------------------------------------------

    def register(self, irs: ConstructIRS) -> None:
        self._constructs[irs.construct_type] = irs

    # -- query --------------------------------------------------------------

    def get(self, construct_type: str) -> ConstructIRS:
        if construct_type not in self._constructs:
            raise KeyError(f"Unknown construct type: {construct_type}")
        return self._constructs[construct_type]

    def has(self, construct_type: str) -> bool:
        return construct_type in self._constructs

    def list_constructs(self) -> list[str]:
        return sorted(self._constructs)

    # -- factory ------------------------------------------------------------

    @staticmethod
    def default() -> SPLConstructRegistry:
        from nl2spl.compiler.constructs.defaults import build_default_construct_registry

        return build_default_construct_registry()
