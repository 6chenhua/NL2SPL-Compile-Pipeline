"""Stage 9.5: worker-scoped IR structural normalization."""

from __future__ import annotations

from nl2spl.pipeline.stages.stage9_5_normalizer.helpers import HelpersMixin
from nl2spl.pipeline.stages.stage9_5_normalizer.normalization import (
    NormalizationMixin,
)
from nl2spl.pipeline.stages.stage9_5_normalizer.validation import ValidationMixin
from nl2spl.pipeline.stages.stage9_5_normalizer.worker_scoped import WorkerScopedMixin


class IRNormalizer(
    HelpersMixin,
    NormalizationMixin,
    ValidationMixin,
    WorkerScopedMixin,
):
    """Worker-scoped IR normalization and structural validation.

    The production pipeline enters Stage 9.5 with worker-scoped IR. The old
    flat ``normalize`` API is intentionally absent so compatibility paths
    cannot keep semantic repair rules alive.
    """
