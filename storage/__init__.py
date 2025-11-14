from __future__ import annotations

from typing import Optional

from .bootstrap import init_storage, get_storage
from .interfaces import (
    ChatConfig,
    ChatConfigInput,
    ChatConfigStore,
    ChatDailyStats,
    ChatDailyStatsInput,
    ChatStatsStore,
)

__all__ = [
    "init_storage",
    "get_storage",
    "ChatConfig",
    "ChatConfigInput",
    "ChatConfigStore",
    "ChatDailyStats",
    "ChatDailyStatsInput",
    "ChatStatsStore",
]


def ensure_storage_initialized(database_url: Optional[str] = None) -> None:
    """
    Convenience helper for modules that only need side-effects from storage startup
    (migrations). Calls init_storage() without returning the instance.
    """
    init_storage(database_url=database_url)

