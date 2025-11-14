"""Configuration module for DespamLy antispam bot."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(ROOT_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    """Application settings loaded from environment variables."""
    
    BOT_TOKEN: str
    
    META_NOTIFY: float = 0.65
    META_DELETE: float = 0.85
    META_KICK: float = 0.95
    
    META_DOWNWEIGHT_ADMIN: float = 0.90
    META_DOWNWEIGHT_REPLY_TO_STAFF: float = 0.90
    META_DOWNWEIGHT_WHITELIST: float = 0.85
    META_DOWNWEIGHT_BRAND: float = 0.70
    META_DOWNWEIGHT_ANNOUNCEMENT: float = 0.85
    
    LOG_LEVEL: str = "INFO"
    DETAILED_DEBUG_INFO: bool = False


def _str_to_bool(raw: str | None, *, default: bool = False) -> bool:
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _build_settings() -> Settings:
    bot_token = os.environ.get("BOT_TOKEN")
    if not bot_token:
        raise RuntimeError("BOT_TOKEN is required in .env")
    
    return Settings(
        BOT_TOKEN=bot_token,
        META_NOTIFY=float(os.environ.get("META_NOTIFY", "0.65")),
        META_DELETE=float(os.environ.get("META_DELETE", "0.85")),
        META_KICK=float(os.environ.get("META_KICK", "0.95")),
        META_DOWNWEIGHT_ADMIN=float(os.environ.get("META_DOWNWEIGHT_ADMIN", "0.90")),
        META_DOWNWEIGHT_REPLY_TO_STAFF=float(os.environ.get("META_DOWNWEIGHT_REPLY_TO_STAFF", "0.90")),
        META_DOWNWEIGHT_WHITELIST=float(os.environ.get("META_DOWNWEIGHT_WHITELIST", "0.85")),
        META_DOWNWEIGHT_BRAND=float(os.environ.get("META_DOWNWEIGHT_BRAND", "0.70")),
        META_DOWNWEIGHT_ANNOUNCEMENT=float(os.environ.get("META_DOWNWEIGHT_ANNOUNCEMENT", "0.85")),
        LOG_LEVEL=os.environ.get("LOG_LEVEL", "INFO").upper(),
        DETAILED_DEBUG_INFO=_str_to_bool(os.environ.get("DETAILED_DEBUG_INFO"), default=False),
    )


settings: Settings = _build_settings()

__all__ = ["settings", "Settings"]
