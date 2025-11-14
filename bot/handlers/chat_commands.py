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
    if update.effective_chat.type == "private":
        return
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
    status_emoji = "✅" if chat_config.is_active else "⚠️"
    status_text = "Активна" if chat_config.is_active else "Приостановлена"
    mode_info = {
        "delete_only": ("🗑️ Удаление спама", "Удаляет спам-сообщения"),
        "delete_and_ban": ("⛔ Удаление + бан", "Удаляет спам и банит при высокой уверенности"),
        "notify_only": ("🔍 Только уведомления", "Не удаляет, только уведомляет владельца"),
    }
    
    mode_name, mode_desc = mode_info.get(
        chat_config.policy_mode,
        ("❓ Неизвестно", "")
    )
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
    if update.effective_chat.type == "private":
        return
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
    if update.effective_chat.type == "private":
        return
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


async def cmd_test(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Команда /test <текст> - тестирует бота на переданном тексте.
    Доступна только администраторам. Имитирует обычное сообщение пользователя.
    """
    if not update.effective_message or not update.effective_chat:
        return
    
    if update.effective_chat.type == "private":
        await update.effective_message.reply_text(
            "❌ Эта команда работает только в группах"
        )
        return
    
    if not await _is_admin(update, context):
        await update.effective_message.reply_text(
            "❌ Эта команда доступна только администраторам"
        )
        return
    
    if not context.args:
        await update.effective_message.reply_html(
            "📝 <b>Использование:</b>\n\n"
            "<code>/test ваше тестовое сообщение</code>\n\n"
            "Бот проанализирует текст как обычное сообщение пользователя "
            "и покажет результат проверки."
        )
        return
    
    test_text = " ".join(context.args)
    
    from core.coordinator import get_coordinator
    
    coordinator = get_coordinator()
    
    try:
        result = await coordinator.analyze(test_text, message=None)
        
        scores_text = "\n".join([
            f"• Keyword: {result.keyword_result.score:.2%}",
            f"• TF-IDF: {result.tfidf_result.score:.2%}",
            f"• Pattern: {result.pattern_result.score:.2%}",
        ])
        
        avg_score = result.average_score
        max_score = result.max_score
        
        storage = get_storage()
        chat_config = storage.chat_configs.get_by_chat_id(update.effective_chat.id)
        
        verdict_emoji = "✅"
        verdict_text = "Разрешить (проходит все проверки)"
        
        if chat_config:
            if chat_config.policy_mode == "delete_and_ban" and avg_score >= chat_config.meta_kick:
                verdict_emoji = "⛔"
                verdict_text = f"Удалить + забанить (≥{chat_config.meta_kick:.0%})"
            elif avg_score >= chat_config.meta_delete:
                verdict_emoji = "🗑️"
                verdict_text = f"Удалить сообщение (≥{chat_config.meta_delete:.0%})"
            elif avg_score >= 0.65:
                verdict_emoji = "⚠️"
                verdict_text = "Уведомить владельца (≥65%)"
        
        message = (
            f"🧪 <b>Результат тестирования</b>\n\n"
            f"<b>Текст:</b>\n<code>{test_text[:200]}</code>\n\n"
            f"<b>Verdict:</b> {verdict_emoji} {verdict_text}\n"
            f"<b>Средняя оценка:</b> {avg_score:.2%}\n"
            f"<b>Максимум:</b> {max_score:.2%}\n\n"
            f"<b>Оценки фильтров:</b>\n{scores_text}\n\n"
            f"<i>Режим тестирования - действия не выполняются</i>"
        )
        
        await update.effective_message.reply_html(message)
        
        LOGGER.info(
            f"Test command used in chat {update.effective_chat.id} "
            f"by admin {update.effective_user.id}: avg={avg_score:.2f}, "
            f"max={max_score:.2f}"
        )
        
    except Exception as e:
        LOGGER.error(f"Error in test command: {e}")
        await update.effective_message.reply_text(
            f"❌ Ошибка при тестировании: {e}"
        )


async def cmd_link_moderator(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Команда /link_moderator <token> - привязать эту группу как модераторскую.
    Используется после получения токена в /mychats.
    """
    if not update.effective_message or not update.effective_chat or not update.effective_user:
        return
    
    # Проверка: только в группах
    if update.effective_chat.type == "private":
        await update.effective_message.reply_text(
            "❌ Эта команда работает только в группах.\n\n"
            "Создай группу для модерации, добавь меня туда и используй эту команду."
        )
        return
    
    # Проверка аргументов
    if not context.args or len(context.args) != 1:
        await update.effective_message.reply_text(
            "❌ Неверное использование команды.\n\n"
            "Правильно: <code>/link_moderator ТВОЙ_ТОКЕН</code>\n\n"
            "Получи токен в личных сообщениях со мной:\n"
            "/mychats → выбери чат → Настроить модераторскую группу",
            parse_mode=ParseMode.HTML
        )
        return
    
    token = context.args[0]
    user_id = update.effective_user.id
    moderator_group_id = update.effective_chat.id
    
    # Валидация токена
    import time
    tokens = context.bot_data.get("moderator_tokens", {})
    
    if token not in tokens:
        await update.effective_message.reply_text(
            "❌ <b>Токен не найден или уже использован</b>\n\n"
            "Возможные причины:\n"
            "• Токен уже был использован\n"
            "• Токен истёк (15 минут)\n"
            "• Неверный токен\n\n"
            "Получи новый токен:\n"
            "/mychats → выбери чат → Настроить модераторскую группу",
            parse_mode=ParseMode.HTML
        )
        return
    
    token_data = tokens[token]
    
    # Проверка истечения
    if time.time() > token_data["expires_at"]:
        del tokens[token]  # Удаляем истёкший
        await update.effective_message.reply_text(
            "❌ <b>Токен истёк</b>\n\n"
            "Токен действителен только 15 минут.\n"
            "Получи новый токен в /mychats",
            parse_mode=ParseMode.HTML
        )
        return
    
    # Проверка владельца
    if token_data["owner_id"] != user_id:
        await update.effective_message.reply_text(
            "❌ <b>Отказано в доступе</b>\n\n"
            "Только владелец чата может использовать этот токен.",
            parse_mode=ParseMode.HTML
        )
        return
    
    chat_id = token_data["chat_id"]
    
    # Проверка прав бота в модераторской группе
    try:
        from telegram.constants import ChatMemberStatus
        bot_member = await context.bot.get_chat_member(moderator_group_id, context.bot.id)
        
        if bot_member.status not in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER):
            await update.effective_message.reply_text(
                "❌ <b>Недостаточно прав</b>\n\n"
                "Я должен быть администратором этой группы.\n"
                "Дай мне права администратора и попробуй снова.",
                parse_mode=ParseMode.HTML
            )
            return
        
        if not bot_member.can_delete_messages:
            await update.effective_message.reply_text(
                "⚠️ <b>Рекомендация</b>\n\n"
                "Дай мне право удалять сообщения в этой группе.\n"
                "Это позволит очищать старые уведомления.",
                parse_mode=ParseMode.HTML
            )
            # Продолжаем несмотря на это
    except Exception as e:
        LOGGER.error(f"Failed to check bot permissions in group {moderator_group_id}: {e}")
        await update.effective_message.reply_text(
            "❌ Не удалось проверить мои права в группе.\n\n"
            "Убедись, что я добавлен в группу как администратор.",
            parse_mode=ParseMode.HTML
        )
        return
    
    # Сохранение привязки
    storage = get_storage()
    chat_config = storage.chat_configs.get_by_chat_id(chat_id)
    
    if not chat_config:
        await update.effective_message.reply_text(
            "❌ Конфигурация чата не найдена.\n\n"
            "Возможно, бот был удалён из основного чата.",
            parse_mode=ParseMode.HTML
        )
        del tokens[token]
        return
    
    try:
        storage.chat_configs.update(chat_id, moderator_channel_id=moderator_group_id)
        
        # Удаляем использованный токен
        del tokens[token]
        
        await update.effective_message.reply_text(
            f"✅ <b>Модераторская группа настроена!</b>\n\n"
            f"<b>Основной чат:</b> {chat_config.chat_title}\n"
            f"<b>Модераторская группа:</b> {update.effective_chat.title}\n\n"
            f"Теперь все уведомления о спаме будут приходить сюда.\n"
            f"Тебе стали доступны все режимы работы.\n\n"
            f"Управление: /mychats (в личных сообщениях)",
            parse_mode=ParseMode.HTML
        )
        
        # Уведомляем владельца в ЛС
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=(
                    f"✅ <b>Модераторская группа настроена</b>\n\n"
                    f"Чат: <b>{chat_config.chat_title}</b>\n"
                    f"Модераторская группа: <b>{update.effective_chat.title}</b>\n\n"
                    f"Все уведомления теперь будут приходить в эту группу."
                ),
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            LOGGER.warning(f"Failed to notify owner {user_id} in DM: {e}")
        
        LOGGER.info(
            f"Moderator group {moderator_group_id} linked to chat {chat_id} "
            f"by user {user_id}"
        )
        
    except Exception as e:
        LOGGER.error(f"Failed to link moderator group: {e}")
        await update.effective_message.reply_text(
            f"❌ Ошибка при сохранении настроек: {e}",
            parse_mode=ParseMode.HTML
        )
