"""
Команды для использования в групповом чате.
/status - текущий статус защиты
/pause - приостановить защиту
/resume - возобновить защиту
"""
from __future__ import annotations

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from storage import get_storage
from utils.logger import get_logger

LOGGER = get_logger(__name__)


async def _is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Проверяет, является ли пользователь администратором чата."""
    if not update.effective_user or not update.effective_chat:
        return False
    
    try:
        member = await context.bot.get_chat_member(
            update.effective_chat.id,
            update.effective_user.id
        )
        return member.status in ("creator", "administrator")
    except Exception as e:
        LOGGER.error(f"Failed to check admin status: {e}")
        return False


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Команда /status - показывает текущий статус защиты чата.
    Доступна только администраторам.
    """
    if not update.effective_message or not update.effective_chat:
        return
    
    # Только в группах
    if update.effective_chat.type == "private":
        return
    
    # Проверка прав админа
    if not await _is_admin(update, context):
        await update.effective_message.reply_text(
            "❌ Эта команда доступна только администраторам"
        )
        return
    
    storage = get_storage()
    chat_config = storage.chat_configs.get_by_chat_id(update.effective_chat.id)
    
    if not chat_config:
        await update.effective_message.reply_html(
            "⚠️ <b>Чат не зарегистрирован</b>\n\n"
            "Владелец должен настроить защиту через /mychats в личке с ботом"
        )
        return
    
    # Статус
    status_emoji = "✅" if chat_config.is_active else "⚠️"
    status_text = "Активна" if chat_config.is_active else "Приостановлена"
    
    # Режим
    mode_info = {
        "delete_only": ("🗑️ Удаление спама", "Удаляет спам-сообщения"),
        "delete_and_ban": ("⛔ Удаление + бан", "Удаляет спам и банит при высокой уверенности"),
        "notify_only": ("🔍 Только уведомления", "Не удаляет, только уведомляет владельца"),
    }
    
    mode_name, mode_desc = mode_info.get(
        chat_config.policy_mode,
        ("❓ Неизвестно", "")
    )
    
    # Получаем статистику за сегодня
    from datetime import datetime
    today_stats = storage.chat_stats.get_stats(chat_config.chat_id, days=1)
    
    if today_stats:
        stat = today_stats[0]
        today_text = (
            f"\n\n<b>📊 Сегодня:</b>\n"
            f"Обработано: {stat.messages_processed}\n"
            f"Спам: {stat.spam_detected}\n"
            f"Удалено: {stat.messages_deleted}\n"
            f"Забанено: {stat.users_banned}"
        )
    else:
        today_text = "\n\n<i>Статистики за сегодня пока нет</i>"
    
    message = (
        f"{status_emoji} <b>Статус защиты</b>\n\n"
        f"<b>Состояние:</b> {status_text}\n"
        f"<b>Режим:</b> {mode_name}\n"
        f"<i>{mode_desc}</i>\n"
        f"\n<b>Пороги:</b>\n"
        f" • Удаление: {chat_config.meta_delete:.0%}\n"
        f" • Бан: {chat_config.meta_kick:.0%}\n"
        f"\n<b>Whitelist:</b> {len(chat_config.whitelist) if chat_config.whitelist else 0} пользователей"
        f"{today_text}"
    )
    
    await update.effective_message.reply_html(message)


async def cmd_pause(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Команда /pause - приостанавливает защиту чата.
    Доступна только администраторам.
    """
    if not update.effective_message or not update.effective_chat:
        return
    
    # Только в группах
    if update.effective_chat.type == "private":
        return
    
    # Проверка прав админа
    if not await _is_admin(update, context):
        await update.effective_message.reply_text(
            "❌ Эта команда доступна только администраторам"
        )
        return
    
    storage = get_storage()
    chat_config = storage.chat_configs.get_by_chat_id(update.effective_chat.id)
    
    if not chat_config:
        await update.effective_message.reply_text(
            "⚠️ Чат не зарегистрирован"
        )
        return
    
    if not chat_config.is_active:
        await update.effective_message.reply_text(
            "ℹ️ Защита уже приостановлена"
        )
        return
    
    try:
        storage.chat_configs.update(chat_config.chat_id, is_active=False)
        
        await update.effective_message.reply_html(
            "⏸️ <b>Защита приостановлена</b>\n\n"
            "Бот больше не будет проверять сообщения.\n"
            "Для возобновления используй /resume"
        )
        
        LOGGER.info(
            f"Chat {chat_config.chat_id} paused by admin {update.effective_user.id}"
        )
    except Exception as e:
        LOGGER.error(f"Failed to pause chat {chat_config.chat_id}: {e}")
        await update.effective_message.reply_text(
            "❌ Ошибка при приостановке защиты"
        )


async def cmd_resume(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Команда /resume - возобновляет защиту чата.
    Доступна только администраторам.
    """
    if not update.effective_message or not update.effective_chat:
        return
    
    # Только в группах
    if update.effective_chat.type == "private":
        return
    
    # Проверка прав админа
    if not await _is_admin(update, context):
        await update.effective_message.reply_text(
            "❌ Эта команда доступна только администраторам"
        )
        return
    
    storage = get_storage()
    chat_config = storage.chat_configs.get_by_chat_id(update.effective_chat.id)
    
    if not chat_config:
        await update.effective_message.reply_text(
            "⚠️ Чат не зарегистрирован"
        )
        return
    
    if chat_config.is_active:
        await update.effective_message.reply_text(
            "ℹ️ Защита уже активна"
        )
        return
    
    try:
        storage.chat_configs.update(chat_config.chat_id, is_active=True)
        
        await update.effective_message.reply_html(
            "▶️ <b>Защита возобновлена</b>\n\n"
            "Бот снова проверяет сообщения.\n"
            f"Режим: {chat_config.policy_mode}"
        )
        
        LOGGER.info(
            f"Chat {chat_config.chat_id} resumed by admin {update.effective_user.id}"
        )
    except Exception as e:
        LOGGER.error(f"Failed to resume chat {chat_config.chat_id}: {e}")
        await update.effective_message.reply_text(
            "❌ Ошибка при возобновлении защиты"
        )
