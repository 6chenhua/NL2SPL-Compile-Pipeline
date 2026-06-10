"""Stage 3.2 Resource Contract Planner.

Aggregates span-level route evidence and deterministic structural evidence
into ``ResourceContractPlanIR`` without LLM calls.
"""

from nl2spl.pipeline.stages.stage3_2_resource_contract_planner.planner import (
    ResourceContractPlanner,
)

__all__ = ["ResourceContractPlanner"]
