"""Centralized logger configuration for Sentinel MAX."""
from __future__ import annotations

import logging
from typing import Optional


_LOGGER_NAME = "sentinel"


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Return a configured logger instance.

    The logger is configured with a basic formatter. Subsequent calls reuse
    the same logger hierarchy so configuration is only applied once.
    """

    logger_name = f"{_LOGGER_NAME}.{name}" if name else _LOGGER_NAME
    logger = logging.getLogger(logger_name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "[%(asctime)s] %(levelname)s %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger
