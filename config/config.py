# LifeMart_Safety/config/config.py
"""
Модуль конфигурации проекта «LifeMart Safety Bot».

▪️ Загружает переменные окружения из файла .env (в корне репозитория).
▪️ Собирает типизированный контейнер Settings, доступный как singleton `settings`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import List

from dotenv import load_dotenv

# ───────────────────────────────
#  Загрузка .env
# ───────────────────────────────
ROOT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(ROOT_DIR / ".env")           # .env должен лежать в корне проекта

# ───────────────────────────────
#  Типизированный контейнер
# ───────────────────────────────
@dataclass(frozen=True)
class Settings:
    BOT_TOKEN: str
    MODERATOR_CHAT_ID: int
    WHITELIST_USER_IDS: List[int]
    
    POLICY_MODE: str
    
    META_NOTIFY: float
    META_DELETE: float
    META_KICK: float
    
    META_DOWNWEIGHT_ANNOUNCEMENT: float
    META_DOWNWEIGHT_REPLY_TO_STAFF: float
    META_DOWNWEIGHT_WHITELIST: float
    META_DOWNWEIGHT_BRAND: float
    
    RETRAIN_THRESHOLD: int
    ANNOUNCE_BLOCKS: bool
    
    LOG_LEVEL: str = "INFO"
    DETAILED_DEBUG_INFO: bool = False


# ───────────────────────────────
#  Парс вспомогательных полей
# ───────────────────────────────
def _parse_int_list(raw: str | None) -> List[int]:
    if not raw:
        return []
    return [int(x.strip()) for x in raw.split(",") if x.strip()]


def _str_to_bool(raw: str | None, *, default: bool = True) -> bool:
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


# ───────────────────────────────
#  Сборка Settings
# ───────────────────────────────
def _build_settings() -> Settings:
    try:
        bot_token = os.environ["BOT_TOKEN"]
        mod_chat_id = int(os.environ["MODERATOR_CHAT_ID"])
    except KeyError as miss:
        raise RuntimeError(f"Переменная {miss.args[0]} не задана в .env") from None

    whitelist = _parse_int_list(os.environ.get("WHITELIST_USER_IDS"))
    
    raw_policy_mode = os.environ.get("POLICY_MODE", "semi-auto")
    policy_mode = raw_policy_mode.strip().lower().replace("_", "-")
    if policy_mode not in {"manual", "semi-auto", "auto"}:
        raise ValueError("POLICY_MODE должен быть manual | semi-auto | auto")
    
    meta_notify = float(os.environ.get("META_NOTIFY", "0.65"))
    meta_delete = float(os.environ.get("META_DELETE", "0.85"))
    meta_kick = float(os.environ.get("META_KICK", "0.95"))
    
    meta_downweight_announcement = float(os.environ.get("META_DOWNWEIGHT_ANNOUNCEMENT", "0.85"))
    meta_downweight_reply_to_staff = float(os.environ.get("META_DOWNWEIGHT_REPLY_TO_STAFF", "0.90"))
    meta_downweight_whitelist = float(os.environ.get("META_DOWNWEIGHT_WHITELIST", "0.85"))
    meta_downweight_brand = float(os.environ.get("META_DOWNWEIGHT_BRAND", "0.70"))
    
    retrain_thr = int(os.environ.get("RETRAIN_THRESHOLD", "100"))
    announce_blocks = _str_to_bool(os.environ.get("ANNOUNCE_BLOCKS"), default=False)
    log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
    detailed_debug_info = _str_to_bool(os.environ.get("DETAILED_DEBUG_INFO"), default=False)

    return Settings(
        BOT_TOKEN=bot_token,
        MODERATOR_CHAT_ID=mod_chat_id,
        WHITELIST_USER_IDS=whitelist,
        POLICY_MODE=policy_mode,
        META_NOTIFY=meta_notify,
        META_DELETE=meta_delete,
        META_KICK=meta_kick,
        META_DOWNWEIGHT_ANNOUNCEMENT=meta_downweight_announcement,
        META_DOWNWEIGHT_REPLY_TO_STAFF=meta_downweight_reply_to_staff,
        META_DOWNWEIGHT_WHITELIST=meta_downweight_whitelist,
        META_DOWNWEIGHT_BRAND=meta_downweight_brand,
        RETRAIN_THRESHOLD=retrain_thr,
        ANNOUNCE_BLOCKS=announce_blocks,
        LOG_LEVEL=log_level,
        DETAILED_DEBUG_INFO=detailed_debug_info,
    )


# singleton
settings: Settings = _build_settings()

__all__ = ["settings", "Settings"]
