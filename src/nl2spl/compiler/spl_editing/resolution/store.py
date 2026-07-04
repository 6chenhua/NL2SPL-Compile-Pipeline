from nl2spl.compiler.spl_editing.resolution.model import (
    validate_promotion_resolution_marker,
)


class PromotionResolutionStore:
    def __init__(self) -> None:
        self._items = {}

    def put(self, marker) -> None:
        if marker.marker_id in self._items and self._items[marker.marker_id] != marker:
            raise ValueError(f"Resolution marker collision: {marker.marker_id}")
        self._items[marker.marker_id] = marker

    def find_target(self, target_ref: str):
        return tuple(
            marker
            for marker in self._items.values()
            if marker.target_worker_promotion_id == target_ref
        )

    def find_valid_target(self, target_ref: str):
        return tuple(
            marker
            for marker in self.find_target(target_ref)
            if validate_promotion_resolution_marker(marker, target_ref).valid
        )
