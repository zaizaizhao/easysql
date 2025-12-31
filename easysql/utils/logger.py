"""
Logging configuration for EasySql.

Uses loguru for enhanced logging with automatic formatting,
file rotation, and structured output.
"""

import sys
from pathlib import Path

from loguru import logger
from loguru import Logger


def setup_logging(
    level: str = "INFO",
    log_file: str | Path | None = None,
    rotation: str = "10 MB",
    retention: str = "7 days",
) -> None:
    """
    Configure application logging.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Path to log file (optional)
        rotation: Log file rotation size
        retention: Log file retention period
    """
    # Remove default handler
    logger.remove()

    # Console handler with color
    logger.add(
        sys.stderr,
        level=level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        ),
        colorize=True,
    )

    # File handler if specified
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        logger.add(
            log_file,
            level=level,
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
            rotation=rotation,
            retention=retention,
            encoding="utf-8",
        )


def get_logger(name: str | None = None) -> Logger:
    """
    Get a logger instance.

    Args:
        name: Logger name (module name)

    Returns:
        Logger instance
    """
    if name:
        return logger.bind(name=name)
    return logger
