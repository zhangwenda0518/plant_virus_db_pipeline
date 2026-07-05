"""Utility functions and logging configurations for PrimerForge."""

import logging
import sys


def setup_logger(
    name: str = "primerforge", level: int = logging.INFO
) -> logging.Logger:
    """Sets up a standardized console logger for the PrimerForge application.

    Args:
        name: Name of the logger.
        level: Logging level (e.g. logging.INFO, logging.DEBUG).

    Returns:
        logging.Logger: A configured logger instance.
    """
    logger = logging.getLogger(name)

    # If the logger already has handlers, do not add more (prevents duplicate log entries)
    if logger.handlers:
        return logger

    logger.setLevel(level)

    # Use a clean, informative formatter suitable for bioinformatics CLIs
    formatter = logging.Formatter(
        "[%(asctime)s] %(levelname)s [%(name)s.%(funcName)s:%(lineno)d] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger
