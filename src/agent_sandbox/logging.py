from __future__ import annotations

import logging

LOGGER_NAME = "agent_sandbox"


def get_logger(name: str = LOGGER_NAME) -> logging.Logger:
    """Return a package logger with a NullHandler by default."""

    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.addHandler(logging.NullHandler())
    return logger
