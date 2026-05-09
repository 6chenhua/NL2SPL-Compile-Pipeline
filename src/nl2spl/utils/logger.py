"""Logging utilities for NL2SPL pipeline."""

from __future__ import annotations

import logging
import sys
from pathlib import Path


def setup_logger(
    name: str = "nl2spl",
    level: str = "INFO",
    log_file: Path | None = None,
) -> logging.Logger:
    """Set up logger with console and optional file handler.

    Args:
        name: Logger name
        level: Log level
        log_file: Optional log file path

    Returns:
        Configured logger
    """
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper()))

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)
    console_format = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_handler.setFormatter(console_format)
    logger.addHandler(console_handler)

    # File handler
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_format = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s:%(funcName)s:%(lineno)d: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        file_handler.setFormatter(file_format)
        logger.addHandler(file_handler)

    return logger


def get_stage_logger(stage_name: str) -> logging.Logger:
    """Get logger for specific pipeline stage.

    Args:
        stage_name: Name of the pipeline stage

    Returns:
        Logger instance for the stage
    """
    return logging.getLogger(f"nl2spl.{stage_name}")
