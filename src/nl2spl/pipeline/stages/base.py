"""Pipeline stage base class."""

from __future__ import annotations

import abc
from typing import Any, Generic, TypeVar

from nl2spl.config import PipelineConfig
from nl2spl.llm.client import LLMClient
from nl2spl.utils.logger import get_stage_logger

Input = TypeVar("Input")
Output = TypeVar("Output")


class PipelineStage(abc.ABC, Generic[Input, Output]):
    """Abstract base class for pipeline stages.

    Each stage has a clear input/output type contract.
    """

    def __init__(self, config: PipelineConfig, client: LLMClient) -> None:
        """Initialize stage.

        Args:
            config: Pipeline configuration
            client: LLM client
        """
        self.config = config
        self.client = client
        self.logger = get_stage_logger(self.name)

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Stage name for logging and checkpointing."""
        ...

    @abc.abstractmethod
    def execute(self, input_data: Input) -> Output:
        """Execute the stage logic.

        Args:
            input_data: Stage input

        Returns:
            Stage output
        """
        ...

    def save_checkpoint(self, data: Any) -> None:
        """Save intermediate result if configured.

        Args:
            data: Data to save
        """
        if self.config.save_intermediate:
            from nl2spl.utils.persistence import save_intermediate_result

            save_intermediate_result(
                stage_name=self.name,
                result=data if isinstance(data, dict) else {"data": str(data)},
                output_dir=self.config.run_dir,
            )
