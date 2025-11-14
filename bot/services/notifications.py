"""
Система уведомлений владельцев чатов о детектах спама.
Включает группировку уведомлений для предотвращения флуда.
"""
from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from utils.logger import get_logger

LOGGER = get_logger(__name__)


@dataclass(slots=True)
class PendingNotification:
    """Ожидающее уведомление о спаме."""
    chat_id: int
    message_id: int
    user_id: int
    username: str
    text: str
    meta_score: float
    action: str
    created_at: float


class NotificationBuffer:
    """
    Буфер для группировки уведомлений.
    
    Стратегия:
    - Индивидуальное уведомление если прошло >5 минут с последнего
    - Batch уведомление если накопилось >10 pending уведомлений
    """
    
    def __init__(self, batch_threshold: int = 10, window_seconds: int = 300):
        self.batch_threshold = batch_threshold
        self.window_seconds = window_seconds
        
        # Key: owner_id, Value: список pending уведомлений
        self._buffer: Dict[int, List[PendingNotification]] = defaultdict(list)
        
        # Key: owner_id, Value: timestamp последнего отправленного уведомления
        self._last_sent: Dict[int, float] = {}
    
    def add(
        self,
        owner_id: int,
        chat_id: int,
        message_id: int,
        user_id: int,
        username: str,
        text: str,
        meta_score: float,
        action: str,
    ) -> None:
        """
        Добавляет уведомление в буфер.
        """
        notification = PendingNotification(
            chat_id=chat_id,
            message_id=message_id,
            user_id=user_id,
            username=username,
            text=text,
            meta_score=meta_score,
            action=action,
            created_at=time.time(),
        )
        
        self._buffer[owner_id].append(notification)
        
        LOGGER.debug(
            f"Added notification to buffer for owner {owner_id}, "
            f"total pending: {len(self._buffer[owner_id])}"
        )
    
    def should_send_batch(self, owner_id: int) -> bool:
        """
        Проверяет, нужно ли отправить batch уведомление.
        """
        pending_count = len(self._buffer.get(owner_id, []))
        return pending_count >= self.batch_threshold
    
    def should_send_individual(self, owner_id: int) -> bool:
        """
        Проверяет, нужно ли отправить индивидуальное уведомление.
        """
        last_sent = self._last_sent.get(owner_id, 0)
        time_passed = time.time() - last_sent
        
        return time_passed >= self.window_seconds
    
    def get_pending(self, owner_id: int) -> List[PendingNotification]:
        """
        Возвращает и очищает pending уведомления для владельца.
        """
        notifications = self._buffer.get(owner_id, [])
        self._buffer[owner_id] = []
        return notifications
    
    def mark_sent(self, owner_id: int) -> None:
        """
        Отмечает время последней отправки уведомления.
        """
        self._last_sent[owner_id] = time.time()


# Глобальный буфер
_notification_buffer: NotificationBuffer | None = None


def get_notification_buffer() -> NotificationBuffer:
    """Возвращает глобальный экземпляр NotificationBuffer."""
    global _notification_buffer
    if _notification_buffer is None:
        _notification_buffer = NotificationBuffer()
    return _notification_buffer


async def send_individual_notification(
    context: ContextTypes.DEFAULT_TYPE,
    owner_id: int,
    chat_id: int,
    chat_title: str,
    user_id: int,
    username: str,
    text: str,
    meta_score: float,
    action: str,
    message_id: int,
) -> None:
    """
    Отправляет индивидуальное уведомление с кнопками действий.
    """
    # Формируем текст
    action_emoji = {
        "deleted": "🗑️",
        "deleted_and_banned": "⛔",
        "detected_only": "🔍",
    }.get(action, "❓")
    
    text_preview = text[:200] + ("..." if len(text) > 200 else "")
    
    message = (
        f"{action_emoji} <b>Спам в чате \"{chat_title}\"</b>\n\n"
        f"👤 @{username} (ID: {user_id})\n"
        f"📊 Уверенность: {meta_score*100:.1f}%\n"
        f"✅ Действие: {action}\n\n"
        f"<i>{text_preview}</i>"
    )
    
    # Кнопки действий
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "❌ Удалить и забанить",
                callback_data=f"ban:{chat_id}:{message_id}:{user_id}"
            )
        ],
        [
            InlineKeyboardButton(
                "✅ Ham (ошибка)",
                callback_data=f"ham:{chat_id}:{message_id}:{user_id}"
            )
        ],
        [
            InlineKeyboardButton(
                "⭐ В Whitelist",
                callback_data=f"whitelist:{chat_id}:{user_id}"
            )
        ]
    ])
    
    try:
        await context.bot.send_message(
            chat_id=owner_id,
            text=message,
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard,
        )
        
        LOGGER.info(f"Sent individual notification to owner {owner_id}")
    except Exception as e:
        LOGGER.error(f"Failed to send notification to {owner_id}: {e}")


async def send_grouped_notification(
    context: ContextTypes.DEFAULT_TYPE,
    owner_id: int,
    notifications: List[PendingNotification],
) -> None:
    """
    Отправляет batch уведомление о нескольких детектах.
    """
    if not notifications:
        return
    
    # Группируем по чатам
    by_chat: Dict[int, List[PendingNotification]] = defaultdict(list)
    for notif in notifications:
        by_chat[notif.chat_id].append(notif)
    
    # Статистика по действиям
    actions_count = defaultdict(int)
    for notif in notifications:
        actions_count[notif.action] += 1
    
    # Формируем текст
    message = (
        f"🚨 <b>{len(notifications)} спам-сообщений</b> за последние 5 минут\n\n"
    )
    
    for chat_id, chat_notifs in by_chat.items():
        # Берём title из первого уведомления (все из одного чата)
        message += f"📂 Чат ID {chat_id}: {len(chat_notifs)} сообщений\n"
    
    message += "\n<b>Действия:</b>\n"
    for action, count in actions_count.items():
        message += f" • {action}: {count}\n"
    
    # Кнопки
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Подробнее", callback_data="batch_details")]
    ])
    
    try:
        await context.bot.send_message(
            chat_id=owner_id,
            text=message,
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard,
        )
        
        LOGGER.info(f"Sent batch notification to owner {owner_id} ({len(notifications)} items)")
    except Exception as e:
        LOGGER.error(f"Failed to send batch notification to {owner_id}: {e}")
