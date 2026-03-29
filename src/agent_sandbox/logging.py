"""Minimal logging helpers shared by library and operator surfaces."""

from __future__ import annotations

import logging
from typing import Any

_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def get_logger(name: str) -> logging.Logger:
    """Return a library logger that stays silent until the host configures logging."""

    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.addHandler(logging.NullHandler())
    return logger


def configure_basic_logging(level: int | str = logging.INFO, **kwargs: Any) -> None:
    """Best-effort logging setup for the CLI and optional HTTP service."""

    logging.basicConfig(level=level, format=_LOG_FORMAT, **kwargs)
