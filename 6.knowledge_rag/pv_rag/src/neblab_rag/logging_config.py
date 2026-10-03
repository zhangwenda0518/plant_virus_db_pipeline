"""Structured logging via structlog, routed through stdlib `logging`.

Routing through stdlib `logging` (rather than ``PrintLoggerFactory``) means:
- Test fixtures like pytest's ``caplog`` see structured log output
- In production, all logs flow through one handler chain (file, syslog, JSON
  to stdout for container collectors, etc.)
- Log levels are controlled in one place
"""

import logging
import sys

import structlog


def configure_logging(level: str = "INFO") -> None:
    """Configure structlog to emit through stdlib logging at ``level``."""
    log_level = getattr(logging, level.upper())
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=log_level)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Get a structlog logger bound to ``name``, routed through stdlib logging."""
    return structlog.get_logger(name)
