"""Configuration management for NL2SPL pipeline."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


ADAPTER_LLM_ENGINE_MODES = {"off", "generic_only", "structural_enrich", "all"}


@dataclass
class LLMConfig:
    """LLM configuration."""

    model: str = "gpt-4o"
    max_tokens: int = 4096
    temperature: float = 0.0
    api_key: str | None = None
    base_url: str | None = None

    def __post_init__(self) -> None:
        """Load from environment if not set."""
        if self.api_key is None:
            self.api_key = os.getenv("OPENAI_API_KEY")
        if self.base_url is None:
            self.base_url = os.getenv("OPENAI_BASE_URL")


@dataclass
class PipelineConfig:
    """Pipeline configuration."""

    # LLM settings
    llm: LLMConfig = field(default_factory=LLMConfig)

    # Output settings
    output_dir: Path = Path("output")
    run_name: str | None = None
    final_spl_filename: str = "final_spl.txt"
    run_dir: Path = field(init=False)
    save_intermediate: bool = True
    trace_dir: Path | None = None

    # Logging settings
    log_level: str = "INFO"
    log_file: Path | None = None

    # Validation settings
    validate_spl: bool = True
    strict_mode: bool = False

    # Migration feature flags
    enable_worker_boundary_planner: bool = False
    enable_worker_boundary_planner_split: bool = True
    enable_worker_boundary_single_call_fallback: bool = False

    # IRS-driven prompt builder (Phase 2+):
    # When enabled, Stage 4/7 prompts include IRS-generated checklists.
    enable_irs_prompt_builder: bool = False

    # IRS-driven Stage 4 exception flow check (Phase 3+):
    # When enabled, Stage 4 post-hoc IRS check produces
    # ConstructSatisfactionReport for every exception flow.
    enable_irs_stage4_exception_flow_check: bool = False

    # IRS-driven Stage 7 step check (Phase 4+):
    # When enabled, Stage 7 post-hoc IRS check produces
    # ConstructSatisfactionReport for every executable step.
    enable_irs_stage7_step_check: bool = False

    # IRS diagnostic consolidation (Phase 5+):
    # When enabled, stage-local diagnostics from
    # intermediate_results are merged into compile_diagnostics.
    # Superseded by enable_irs_post_normalize_check — when that flag is
    # True, consolidation is skipped to avoid duplicating diagnostics.
    enable_irs_diagnostic_consolidation: bool = False

    # Post-normalize IRS check (Phase 8+):
    # Final authority for construct-level diagnostics.  Runs after Stage 10
    # assembly, before the executable-element gate.  Produces authoritative
    # missing_handler, missing_output_producer, type_or_contract_ambiguity,
    # and assumed_command_not_renderable diagnostics from normalized IR.
    # Default True — replaces Stage 9.5 diagnostic emission entirely.
    enable_irs_post_normalize_check: bool = True

    # IRS v6 runner (Phase R5+):
    # When enabled, runs the IRS v6 runner framework to produce
    # construct satisfaction reports and diagnostics.
    # Default False: no behavior change until explicitly enabled.
    enable_irs_v6_runner: bool = False

    # IRS v6 Worker/Delegation checker (Phase R5+):
    # When enabled, registers WorkerDelegationIRSChecker to analyze
    # worker promotion readiness and handoff satisfaction.
    # Requires enable_irs_v6_runner=True to take effect.
    # Default False: no behavior change until explicitly enabled.
    enable_irs_worker_delegation_check: bool = False

    # LLM semantic conflict analyzer (Phase 6+):
    # When enabled, runs an LLM-backed conflict analysis pass.
    # Default NoOp -- zero behaviour change.
    enable_llm_conflict_analyzer: bool = False

    # Resource name filter (Phase 7+):
    # When enabled, Stage 6 rejects schema/IR-looking variable names.
    enable_resource_name_filter: bool = False

    # Stage 6 resource context V2 (Phase 8+):
    # When enabled, Stage 6 prompts use semi-structured resource extraction
    # views instead of raw IR JSON dumps.  Reduces schema noise and
    # mis-extracted variables.  Applies to both legacy and worker-scoped paths.
    enable_stage6_resource_context_v2: bool = False

    # Adapter-guided LLM FieldRoute refinement:
    # When enabled, the structural NL FieldRouter calls an LLM with adapter
    # evidence to refine deterministic priors.  Default on — the Step 4
    # validator acts as the safety boundary for LLM output.
    enable_adapter_guided_fieldroute_llm: bool = True

    # Compatibility/debug fallback for adapter-guided FieldRoute refinement.
    # Default False: if Stage 2 cannot call/parse the adapter-guided LLM,
    # fail fast instead of silently compiling from weak deterministic priors.
    allow_adapter_guided_fieldroute_fallback: bool = False

    # Adapter LLM engine: off | generic_only | structural_enrich | all
    adapter_llm_engine: str = "off"

    # Retry settings
    max_retries: int = 3
    retry_delay: float = 1.0

    def __post_init__(self) -> None:
        """Ensure directories exist."""
        if self.adapter_llm_engine not in ADAPTER_LLM_ENGINE_MODES:
            raise ValueError(
                "adapter_llm_engine must be one of: "
                + ", ".join(sorted(ADAPTER_LLM_ENGINE_MODES))
            )

        self.output_dir.mkdir(parents=True, exist_ok=True)

        if self.run_name is None:
            base_run_name = f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            self.run_name = base_run_name
            suffix = 2
            while (self.output_dir / self.run_name).exists():
                self.run_name = f"{base_run_name}_{suffix}"
                suffix += 1

        run_name_path = Path(self.run_name)
        if run_name_path.is_absolute() or ".." in run_name_path.parts:
            raise ValueError("run_name must be a relative directory name inside output_dir")

        self.run_dir = self.output_dir / run_name_path
        self.run_dir.mkdir(parents=True, exist_ok=True)
        if self.trace_dir:
            self.trace_dir.mkdir(parents=True, exist_ok=True)


def load_config(
    env_file: Path | None = None,
    **kwargs: Any,
) -> PipelineConfig:
    """Load configuration from environment and overrides.

    Args:
        env_file: Path to .env file
        **kwargs: Override values for PipelineConfig fields

    Returns:
        PipelineConfig instance
    """
    if env_file and env_file.exists():
        load_dotenv(env_file)

    kwargs.setdefault(
        "adapter_llm_engine",
        os.getenv("NL2SPL_ADAPTER_LLM_ENGINE", "off"),
    )

    return PipelineConfig(**kwargs)
