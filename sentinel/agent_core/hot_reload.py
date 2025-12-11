"""Hot reloader for Sentinel modules."""
from __future__ import annotations

import importlib
from types import ModuleType
from typing import Dict

from sentinel.logging.logger import get_logger

logger = get_logger(__name__)


class HotReloader:
    def __init__(self) -> None:
        self._modules: Dict[str, ModuleType] = {}

    def track(self, module: ModuleType) -> None:
        self._modules[module.__name__] = module
        logger.info("Tracking module %s for hot reload", module.__name__)

    def reload_all(self) -> None:
        for name, module in list(self._modules.items()):
            try:
                importlib.reload(module)
                logger.info("Reloaded module %s", name)
            except Exception as exc:  # pragma: no cover
                logger.error("Failed to reload %s: %s", name, exc)
