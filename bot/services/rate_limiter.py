"""
In-memory rate limiter для защиты от флуда.
Проверяет количество сообщений от пользователя в чате за короткие интервалы.
"""
from __future__ import annotations

import time
from collections import defaultdict
from typing import Dict, List, Tuple

from utils.logger import get_logger

LOGGER = get_logger(__name__)


class RateLimiter:
    """
    In-memory rate limiter для детекта флуда.
    
    Лимиты:
    - 3 сообщения в секунду
    - 10 сообщений в минуту
    
    Key: (chat_id, user_id)
    Value: список timestamp'ов
    """
    
    def __init__(self):
        self._windows: Dict[Tuple[int, int], List[float]] = defaultdict(list)
        self._last_cleanup = time.time()
    
    def is_flood(self, chat_id: int, user_id: int) -> bool:
        """
        Проверяет, является ли текущее сообщение флудом.
        
        Returns:
            True если превышен лимит, False в противном случае
        """
        now = time.time()
        key = (chat_id, user_id)
        
        # Периодическая очистка старых записей (каждую минуту)
        if now - self._last_cleanup > 60:
            self._cleanup_old_entries(now)
            self._last_cleanup = now
        
        # Получаем или создаём список timestamps для этого пользователя
        timestamps = self._windows[key]
        
        # Удаляем timestamps старше 1 минуты
        timestamps[:] = [ts for ts in timestamps if now - ts < 60]
        
        # Проверяем лимиты
        recent_1s = sum(1 for ts in timestamps if now - ts < 1)
        recent_1m = len(timestamps)
        
        if recent_1s >= 3:
            LOGGER.warning(
                f"Rate limit exceeded (1s): chat_id={chat_id}, user_id={user_id}, "
                f"count={recent_1s}"
            )
            return True
        
        if recent_1m >= 10:
            LOGGER.warning(
                f"Rate limit exceeded (1m): chat_id={chat_id}, user_id={user_id}, "
                f"count={recent_1m}"
            )
            return True
        
        # Добавляем текущий timestamp
        timestamps.append(now)
        
        return False
    
    def _cleanup_old_entries(self, now: float) -> None:
        """
        Удаляет записи старше 1 минуты для экономии памяти.
        """
        keys_to_remove = []
        
        for key, timestamps in self._windows.items():
            # Удаляем старые timestamps
            timestamps[:] = [ts for ts in timestamps if now - ts < 60]
            
            # Если больше нет активных timestamps, помечаем ключ на удаление
            if not timestamps:
                keys_to_remove.append(key)
        
        # Удаляем пустые ключи
        for key in keys_to_remove:
            del self._windows[key]
        
        if keys_to_remove:
            LOGGER.debug(f"Cleaned up {len(keys_to_remove)} inactive rate limit entries")
    
    def get_stats(self) -> dict:
        """
        Возвращает статистику rate limiter'а.
        """
        now = time.time()
        active_users = sum(
            1 for timestamps in self._windows.values()
            if any(now - ts < 60 for ts in timestamps)
        )
        
        return {
            "total_keys": len(self._windows),
            "active_users_1m": active_users,
        }


# Глобальный экземпляр
_rate_limiter: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    """
    Возвращает глобальный экземпляр RateLimiter (singleton).
    """
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
    return _rate_limiter
