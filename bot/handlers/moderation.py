"""
Модуль обработки входящих сообщений и детекта спама.
Интегрируется с FilterCoordinator, PolicyEngine, RateLimiter и Notifications.
"""
from __future__ import annotations

import json
from datetime import datetime
from hashlib import sha256

from telegram import Message, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from core.coordinator import FilterCoordinator
from core.types import Action, AnalysisResult
from filters.keyword import KeywordFilter
from filters.tfidf import TfidfFilter
from filters.pattern import PatternClassifier
from storage import get_storage, ChatConfig
from storage.interfaces import ModerationEventInput
from bot.services import get_rate_limiter, send_individual_notification
from utils.logger import get_logger

LOGGER = get_logger(__name__)

# Глобальные компоненты (инициализируются один раз)
_coordinator: FilterCoordinator | None = None
_INITIALIZED = False


def _ensure_initialized() -> None:
    """Инициализация фильтров и координатора (один раз при старте)."""
    global _coordinator, _INITIALIZED
    
    if _INITIALIZED:
        return
    
    keyword_filter = KeywordFilter()
    tfidf_filter = TfidfFilter()
    pattern_filter = PatternClassifier()
    
    _coordinator = FilterCoordinator(
        keyword_filter=keyword_filter,
        tfidf_filter=tfidf_filter,
        pattern_filter=pattern_filter,
    )
    
    _INITIALIZED = True
    LOGGER.info("Moderation filters initialized")


def _hash_text(value: str) -> str:
    """Хеширование текста для записи в БД."""
    return sha256(value.encode("utf-8")).hexdigest()


def _extract_confidence(analysis: AnalysisResult) -> float:
    """Извлекает confidence score из результата анализа."""
    if analysis.pattern_result is not None:
        return float(analysis.pattern_result.score)
    return float(analysis.average_score)


async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Основной handler входящих сообщений.
    
    Алгоритм:
    1. Проверка базовых условий (текст, не ЛС)
    2. Получение chat_config из БД
    3. Проверка is_active и whitelist
    4. Rate limiting check
    5. Анализ через FilterCoordinator
    6. Принятие решения через PolicyEngine
    7. Выполнение действия (delete/ban/notify)
    8. Запись в БД и отправка уведомления
    9. Инкремент статистики
    """
    _ensure_initialized()
    
    msg: Message = update.effective_message
    if not msg or not msg.from_user or not msg.text:
        return
    
    # Игнорируем личные сообщения
    if msg.chat.type == "private":
        return
    
    storage = get_storage()
    
    # Шаг 1: Получаем конфигурацию чата
    chat_config = storage.chat_configs.get_by_chat_id(msg.chat_id)
    
    if not chat_config:
        LOGGER.debug(f"Chat {msg.chat_id} not registered, ignoring message")
        return
    
    if not chat_config.is_active:
        LOGGER.debug(f"Chat {msg.chat_id} not active, ignoring message")
        return
    
    # Шаг 2: Проверка whitelist
    if chat_config.whitelist and msg.from_user.username:
        if msg.from_user.username in chat_config.whitelist:
            LOGGER.debug(f"User @{msg.from_user.username} in whitelist, skipping")
            return
    
    # Шаг 3: Rate limiting check
    rate_limiter = get_rate_limiter()
    if rate_limiter.is_flood(msg.chat_id, msg.from_user.id):
        LOGGER.warning(
            f"Flood detected: chat_id={msg.chat_id}, user_id={msg.from_user.id}"
        )
        # При флуде сразу удаляем сообщение без анализа
        try:
            await msg.delete()
        except Exception as e:
            LOGGER.error(f"Failed to delete flood message: {e}")
        return
    
    # Шаг 4: Upsert пользователя в БД
    try:
        storage.users.upsert(
            msg.from_user.id,
            username=msg.from_user.username,
        )
    except Exception as e:
        LOGGER.warning(f"Failed to upsert user: {e}")
    
    text = msg.text.strip()
    
    # Шаг 5: Анализ через FilterCoordinator
    analysis = await _coordinator.analyze(text, message=msg)
    
    # Шаг 6: Принятие решения через PolicyEngine (адаптированный)
    action = _decide_action(analysis, chat_config)
    
    LOGGER.info(
        f"Message from {msg.from_user.full_name} in chat {chat_config.chat_title}: "
        f"score={_extract_confidence(analysis):.2f}, "
        f"action={action.value}, mode={chat_config.policy_mode}"
    )
    
    # Инкремент статистики: messages_processed
    try:
        storage.chat_stats.increment(
            chat_config.chat_id,
            datetime.now(),
            messages_processed=1
        )
    except Exception as e:
        LOGGER.warning(f"Failed to increment stats: {e}")
    
    # Если APPROVE - ничего не делаем
    if action == Action.APPROVE:
        return
    
    # Шаг 7: Запись события в БД
    event_id = None
    try:
        event_id = storage.events.record_event(
            ModerationEventInput(
                chat_id=msg.chat_id,
                message_id=msg.message_id,
                user_id=msg.from_user.id,
                username=msg.from_user.username,
                text_hash=_hash_text(text),
                text_length=len(text),
                action=action.value,
                action_confidence=_extract_confidence(analysis),
                filter_keyword_score=analysis.keyword_result.score if analysis.keyword_result else None,
                filter_tfidf_score=analysis.tfidf_result.score if analysis.tfidf_result else None,
                filter_pattern_score=analysis.pattern_result.score if analysis.pattern_result else None,
                meta_debug=json.dumps(
                    analysis.pattern_result.details,
                    ensure_ascii=False,
                    default=str
                ) if analysis.pattern_result and analysis.pattern_result.details else None,
                source='bot',
            )
        )
    except Exception as e:
        LOGGER.error(f"Failed to record event: {e}")
    
    # Шаг 8: Выполнение действия
    spam_detected = 0
    messages_deleted = 0
    users_banned = 0
    
    if action == Action.DELETE:
        try:
            await msg.delete()
            messages_deleted = 1
            spam_detected = 1
            LOGGER.info(f"Deleted message {msg.message_id} from chat {msg.chat_id}")
        except Exception as e:
            LOGGER.error(f"Failed to delete message: {e}")
    
    elif action == Action.KICK:
        try:
            await msg.delete()
            messages_deleted = 1
            spam_detected = 1
            
            # Softban (kick)
            await context.bot.ban_chat_member(msg.chat_id, msg.from_user.id)
            await context.bot.unban_chat_member(msg.chat_id, msg.from_user.id)
            users_banned = 1
            
            LOGGER.info(
                f"Deleted and softbanned user {msg.from_user.id} "
                f"from chat {msg.chat_id}"
            )
        except Exception as e:
            LOGGER.error(f"Failed to delete/ban: {e}")
    
    elif action == Action.NOTIFY:
        spam_detected = 1
        LOGGER.info(f"Spam detected (notify only): {msg.message_id}")
    
    # Обновление статистики
    if spam_detected or messages_deleted or users_banned:
        try:
            storage.chat_stats.increment(
                chat_config.chat_id,
                datetime.now(),
                spam_detected=spam_detected,
                messages_deleted=messages_deleted,
                users_banned=users_banned
            )
        except Exception as e:
            LOGGER.warning(f"Failed to update stats: {e}")
    
    # Шаг 9: Отправка уведомления владельцу
    if action in (Action.DELETE, Action.KICK, Action.NOTIFY):
        action_str = {
            Action.DELETE: "deleted",
            Action.KICK: "deleted_and_banned",
            Action.NOTIFY: "detected_only",
        }.get(action, "unknown")
        
        try:
            await send_individual_notification(
                context=context,
                owner_id=chat_config.owner_id,
                chat_id=chat_config.chat_id,
                chat_title=chat_config.chat_title or f"Chat {chat_config.chat_id}",
                user_id=msg.from_user.id,
                username=msg.from_user.username or "Unknown",
                text=text,
                meta_score=_extract_confidence(analysis),
                action=action_str,
                message_id=msg.message_id,
            )
        except Exception as e:
            LOGGER.error(f"Failed to send notification: {e}")


def _decide_action(analysis: AnalysisResult, chat_config: ChatConfig) -> Action:
    """
    Упрощённая версия PolicyEngine для per-chat конфигураций.
    
    Режимы:
    - notify_only: только уведомления, никаких действий
    - delete_only: удаление при meta_score >= meta_delete
    - delete_and_ban: удаление + softban при meta_score >= meta_kick
    """
    meta_score = _extract_confidence(analysis)
    
    if chat_config.policy_mode == "notify_only":
        if meta_score >= chat_config.meta_delete:
            return Action.NOTIFY
        return Action.APPROVE
    
    elif chat_config.policy_mode == "delete_and_ban":
        if meta_score >= chat_config.meta_kick:
            return Action.KICK
        elif meta_score >= chat_config.meta_delete:
            return Action.DELETE
        return Action.APPROVE
    
    else:  # delete_only (default)
        if meta_score >= chat_config.meta_delete:
            return Action.DELETE
        return Action.APPROVE
