"""IRS Runtime Configuration — product-level policy for IRS subsystem.

IRSRuntimeConfig controls which IRS capabilities are active and how
results are surfaced.  It is a frozen dataclass to prevent accidental
mutation after construction.

This config is intentionally decoupled from PipelineConfig (R11 wires
them together).  R10 uses it standalone.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IRSRuntimeConfig:
    """Product-level configuration for the IRS subsystem.

    Attributes:
        enabled: Master switch.  ``False`` disables the entire IRS
            subsystem — ``run_stage_local`` and ``run_post_normalize``
            both return empty results.
        stage_local_enabled: Enable stage-local construct satisfaction
            checks (Stage 3.5 / 4 / 7).
        worker_delegation_enabled: Register WorkerDelegationIRSChecker.
        exception_flow_enabled: Register Stage4ExceptionFlowIRSChecker.
        step_enabled: Register Stage7StepIRSChecker.
        post_normalize_enabled: Enable post-normalize IRS (final
            construct-level authority).
        include_stage_local_diagnostics_in_compile: When ``True``,
            stage-local IRS diagnostics are merged into final
            ``compile_diagnostics``.  Default ``False`` to avoid
            premature diagnostic noise.
        include_construct_satisfaction_in_feedback: When ``True``,
            construct satisfaction reports are included in feedback
            output.
        collect_graph_snapshot: When ``True``, graph snapshots are
            collected per stage for provenance / future recursion.
    """

    enabled: bool = True
    stage_local_enabled: bool = True
    worker_delegation_enabled: bool = True
    exception_flow_enabled: bool = True
    step_enabled: bool = True
    post_normalize_enabled: bool = True
    include_stage_local_diagnostics_in_compile: bool = False
    include_construct_satisfaction_in_feedback: bool = True
    collect_graph_snapshot: bool = True
