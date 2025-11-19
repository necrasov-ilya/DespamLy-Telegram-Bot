"""
utils/logger.py
────────────────────────────────────────────────────────
Централизованная конфигурация logging.

• Настраивает root-логгер ровно один раз.
• Выводит логи в консоль и во вращающийся файл logs/bot.log.
• Уровень берётся из settings.LOG_LEVEL (INFO по умолчанию).
• Экспортирует функцию `get_logger(name)` для получения
  именованных логгеров в других модулях.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

from config.config import settings

# Параметры форматирования
LOG_DIR = Path(__file__).resolve().parents[1] / "logs"
LOG_DIR.mkdir(exist_ok=True)

LOG_FMT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DATE_FMT = "%Y-%m-%d %H:%M:%S"
LOG_LEVEL = getattr(logging, settings.LOG_LEVEL, logging.INFO)
_ROOT_LOGGER_INITIALIZED = False

def _init_root_logger() -> None:
    """????????? root-?????? ?????? ???? ???."""
    global _ROOT_LOGGER_INITIALIZED
    if _ROOT_LOGGER_INITIALIZED:
        return

    root = logging.getLogger()
    if not root.handlers:
        root.setLevel(LOG_LEVEL)

        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(logging.Formatter(LOG_FMT, DATE_FMT))
        root.addHandler(console)

        file_handler = RotatingFileHandler(
            LOG_DIR / "bot.log",
            maxBytes=2_000_000,       # ~2 MB
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setFormatter(logging.Formatter(LOG_FMT, DATE_FMT))
        root.addHandler(file_handler)

    _ROOT_LOGGER_INITIALIZED = True


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """
    Возвратить именованный логгер (или root, если name не указан).
    Использование:
        logger = get_logger(__name__)
        logger.info("Hello!")
    """
    _init_root_logger()
    return logging.getLogger(name or "root")


__all__ = ["get_logger"]
