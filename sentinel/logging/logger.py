"""Centralized logger configuration for Sentinel MAX."""
from __future__ import annotations

import logging
from pathlib import Path
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
        formatter = logging.Formatter(
            "[%(asctime)s] %(levelname)s %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)

        log_path = Path("sentinel.log")
        try:
            file_handler = logging.FileHandler(log_path, encoding="utf-8")
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except Exception:
            # Fall back to stdout-only logging if file handler fails to initialize.
            pass

        logger.setLevel(logging.INFO)
    return logger
