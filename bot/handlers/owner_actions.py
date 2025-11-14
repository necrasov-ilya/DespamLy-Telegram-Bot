"""
Обработка действий владельца из уведомлений о спаме.
Callbacks: ban, ham, whitelist.
"""
from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from storage import get_storage
from storage.interfaces import ModerationActionInput
from utils.logger import get_logger

LOGGER = get_logger(__name__)


async def on_ban_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Callback: ban:<chat_id>:<message_id>:<user_id>
    Удаляет сообщение и банит пользователя.
    """
    query = update.callback_query
    if not query:
        return
    
    await query.answer()
    
    parts = query.data.split(":")
    if len(parts) != 4:
        await query.edit_message_text("❌ Неверный формат данных")
        return
    
    try:
        chat_id = int(parts[1])
        message_id = int(parts[2])
        user_id = int(parts[3])
    except ValueError:
        await query.edit_message_text("❌ Ошибка парсинга данных")
        return
    
    storage = get_storage()
    chat_config = storage.chat_configs.get_by_chat_id(chat_id)
    if not chat_config or chat_config.owner_id != query.from_user.id:
        await query.answer("❌ У тебя нет прав на это действие", show_alert=True)
        return
    try:
        await context.bot.delete_message(chat_id, message_id)
    except Exception as e:
        LOGGER.warning(f"Failed to delete message {message_id}: {e}")
    try:
        await context.bot.ban_chat_member(chat_id, user_id)
        result = "⛔ Сообщение удалено, пользователь забанен."
    except Exception as e:
        LOGGER.error(f"Failed to ban user {user_id}: {e}")
        result = f"⚠️ Ошибка при бане: {e}"
    
    # Обновляем статистику
    from datetime import datetime
    try:
        storage.chat_stats.increment(
            chat_id,
            datetime.now(),
            messages_deleted=1,
            users_banned=1
        )
    except Exception as e:
        LOGGER.warning(f"Failed to update stats: {e}")
    await query.edit_message_text(
        query.message.text_html + f"\n\n<i>{result}</i>",
        parse_mode=ParseMode.HTML
    )
    
    LOGGER.info(
        f"User {user_id} banned from chat {chat_id} by owner {query.from_user.id}"
    )


async def on_ham_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Callback: ham:<chat_id>:<message_id>:<user_id>
    Отмечает сообщение как не-спам (ложное срабатывание).
    """
    query = update.callback_query
    if not query:
        return
    
    await query.answer()
    
    parts = query.data.split(":")
    if len(parts) != 4:
        await query.edit_message_text("❌ Неверный формат данных")
        return
    
    try:
        chat_id = int(parts[1])
        message_id = int(parts[2])
        user_id = int(parts[3])
    except ValueError:
        await query.edit_message_text("❌ Ошибка парсинга данных")
        return
    
    storage = get_storage()
    chat_config = storage.chat_configs.get_by_chat_id(chat_id)
    if not chat_config or chat_config.owner_id != query.from_user.id:
        await query.answer("❌ У тебя нет прав на это действие", show_alert=True)
        return
    
    # TODO: Сохранение в dataset для переобучения
    # dataset_manager.add_sample(text, label=0)
    
    result = "✅ Отмечено как не-спам. Спасибо за обратную связь!"
    await query.edit_message_text(
        query.message.text_html + f"\n\n<i>{result}</i>",
        parse_mode=ParseMode.HTML
    )
    
    LOGGER.info(
        f"Message {message_id} marked as ham by owner {query.from_user.id}"
    )


async def on_whitelist_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Callback: whitelist_menu:<chat_id>
    Показывает меню управления whitelist.
    """
    query = update.callback_query
    if not query:
        return
    
    await query.answer()
    
    parts = query.data.split(":")
    if len(parts) != 2:
        await query.edit_message_text("❌ Неверный формат данных")
        return
    
    try:
        chat_id = int(parts[1])
    except ValueError:
        await query.edit_message_text("❌ Неверный ID чата")
        return
    
    storage = get_storage()
    chat_config = storage.chat_configs.get_by_chat_id(chat_id)
    
    if not chat_config or chat_config.owner_id != query.from_user.id:
        await query.answer("❌ У тебя нет прав на это действие", show_alert=True)
        return
    
    whitelist = chat_config.whitelist or []
    
    if whitelist:
        users_list = "\n".join([f"• @{username}" for username in whitelist])
        message = (
            f"⭐ <b>Whitelist чата</b>\n\n"
            f"<b>Доверенные пользователи ({len(whitelist)}):</b>\n"
            f"{users_list}\n\n"
            f"<i>Эти пользователи не проверяются антиспамом.</i>\n\n"
            f"Чтобы добавить пользователя в whitelist, нажми кнопку 'Whitelist' "
            f"в уведомлении о спаме."
        )
    else:
        message = (
            f"⭐ <b>Whitelist чата</b>\n\n"
            f"<i>Список доверенных пользователей пуст.</i>\n\n"
            f"Чтобы добавить пользователя в whitelist, нажми кнопку 'Whitelist' "
            f"в уведомлении о спаме."
        )
    
    keyboard = []
    
    if whitelist:
        keyboard.append([
            InlineKeyboardButton("🗑️ Очистить whitelist", callback_data=f"clear_whitelist:{chat_id}")
        ])
    
    keyboard.append([
        InlineKeyboardButton("◀️ Назад", callback_data=f"chat_menu:{chat_id}")
    ])
    
    await query.edit_message_text(
        message,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def on_clear_whitelist_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Callback: clear_whitelist:<chat_id>
    Очищает whitelist чата.
    """
    query = update.callback_query
    if not query:
        return
    
    await query.answer()
    
    chat_id = int(query.data.split(":")[1])
    storage = get_storage()
    chat_config = storage.chat_configs.get_by_chat_id(chat_id)
    
    if not chat_config or chat_config.owner_id != query.from_user.id:
        await query.answer("❌ У тебя нет прав на это действие", show_alert=True)
        return
    
    try:
        storage.chat_configs.update(chat_id, whitelist=[])
        await query.answer("✅ Whitelist очищен", show_alert=True)
        
        update.callback_query.data = f"whitelist_menu:{chat_id}"
        await on_whitelist_menu_callback(update, context)
        
        LOGGER.info(f"Whitelist cleared in chat {chat_id} by owner {query.from_user.id}")
    except Exception as e:
        LOGGER.error(f"Failed to clear whitelist: {e}")
        await query.answer("❌ Ошибка очистки whitelist", show_alert=True)


async def on_whitelist_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Callback: whitelist:<chat_id>:<user_id>
    Добавляет пользователя в whitelist чата.
    """
    query = update.callback_query
    if not query:
        return
    
    await query.answer()
    
    parts = query.data.split(":")
    if len(parts) != 3:
        await query.edit_message_text("❌ Неверный формат данных")
        return
    
    try:
        chat_id = int(parts[1])
        user_id = int(parts[2])
    except ValueError:
        await query.edit_message_text("❌ Ошибка парсинга данных")
        return
    
    storage = get_storage()
    chat_config = storage.chat_configs.get_by_chat_id(chat_id)
    if not chat_config or chat_config.owner_id != query.from_user.id:
        await query.answer("❌ У тебя нет прав на это действие", show_alert=True)
        return
    try:
        user = await context.bot.get_chat_member(chat_id, user_id)
        username = user.user.username
        
        if not username:
            await query.answer("❌ У пользователя нет username", show_alert=True)
            return
    except Exception as e:
        LOGGER.error(f"Failed to get user info: {e}")
        await query.answer("❌ Не удалось получить информацию о пользователе", show_alert=True)
        return
    current_whitelist = chat_config.whitelist or []
    if username not in current_whitelist:
        current_whitelist.append(username)
        
        try:
            storage.chat_configs.update(chat_id, whitelist=current_whitelist)
            result = f"⭐ @{username} добавлен в whitelist"
            await query.edit_message_text(
                query.message.text_html + f"\n\n<i>{result}</i>",
                parse_mode=ParseMode.HTML
            )
            
            LOGGER.info(f"User @{username} added to whitelist in chat {chat_id}")
        except Exception as e:
            LOGGER.error(f"Failed to update whitelist: {e}")
            await query.answer("❌ Ошибка обновления whitelist", show_alert=True)
    else:
        await query.answer(f"⚠️ @{username} уже в whitelist", show_alert=True)


async def on_stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Callback: stats:<chat_id>
    Показывает статистику чата за последние 7 дней.
    """
    query = update.callback_query
    if not query:
        return
    
    await query.answer()
    
    chat_id = int(query.data.split(":")[1])
    storage = get_storage()
    chat_config = storage.chat_configs.get_by_chat_id(chat_id)
    if not chat_config or chat_config.owner_id != query.from_user.id:
        await query.answer("❌ У тебя нет прав на это действие", show_alert=True)
        return
    stats = storage.chat_stats.get_stats(chat_id, days=7)
    
    if not stats:
        message = "📊 <b>Статистика чата</b>\n\nДанных пока нет"
    else:
        total_processed = sum(s.messages_processed for s in stats)
        total_spam = sum(s.spam_detected for s in stats)
        total_deleted = sum(s.messages_deleted for s in stats)
        total_banned = sum(s.users_banned for s in stats)
        
        spam_rate = (total_spam / total_processed * 100) if total_processed > 0 else 0
        
        message = (
            f"📊 <b>Статистика за 7 дней</b>\n\n"
            f"<b>Обработано сообщений:</b> {total_processed}\n"
            f"<b>Обнаружено спама:</b> {total_spam} ({spam_rate:.1f}%)\n"
            f"<b>Удалено сообщений:</b> {total_deleted}\n"
            f"<b>Забанено пользователей:</b> {total_banned}\n\n"
            f"<b>По дням:</b>\n"
        )
        
        for stat in stats[:7]:  # Последние 7 дней
            date_str = stat.date.strftime("%d.%m")
            message += (
                f"\n{date_str}: "
                f"📨{stat.messages_processed} "
                f"🚫{stat.spam_detected} "
                f"🗑️{stat.messages_deleted}"
            )
    
    keyboard = [[
        InlineKeyboardButton("◀️ Назад", callback_data=f"chat_menu:{chat_id}")
    ]]
    
    await query.edit_message_text(
        message,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def on_delete_chat_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Callback: delete_chat:<chat_id>
    Подтверждение удаления чата из списка.
    """
    query = update.callback_query
    if not query:
        return
    
    await query.answer()
    
    chat_id = int(query.data.split(":")[1])
    
    message = (
        "⚠️ <b>Удаление чата</b>\n\n"
        "Это удалит чат из списка и остановит защиту.\n"
        "Статистика будет сохранена.\n\n"
        "Ты уверен?"
    )
    
    keyboard = [
        [InlineKeyboardButton("✅ Да, удалить", callback_data=f"confirm_delete:{chat_id}")],
        [InlineKeyboardButton("❌ Отмена", callback_data=f"chat_menu:{chat_id}")],
    ]
    
    await query.edit_message_text(
        message,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def on_confirm_delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Callback: confirm_delete:<chat_id>
    Окончательное удаление чата.
    """
    query = update.callback_query
    if not query:
        return
    
    await query.answer()
    
    chat_id = int(query.data.split(":")[1])
    storage = get_storage()
    chat_config = storage.chat_configs.get_by_chat_id(chat_id)
    if not chat_config or chat_config.owner_id != query.from_user.id:
        await query.answer("❌ У тебя нет прав на это действие", show_alert=True)
        return
    
    try:
        storage.chat_configs.delete(chat_id)
        
        await query.edit_message_text(
            "✅ <b>Чат удалён</b>\n\n"
            "Защита остановлена. Статистика сохранена.\n"
            "Используй /mychats чтобы увидеть остальные чаты.",
            parse_mode=ParseMode.HTML
        )
        
        LOGGER.info(f"Chat {chat_id} deleted by owner {query.from_user.id}")
    except Exception as e:
        LOGGER.error(f"Failed to delete chat {chat_id}: {e}")
        await query.answer("❌ Ошибка удаления", show_alert=True)


async def on_setup_moderator_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Callback: setup_moderator:<chat_id>
    Инструкция по настройке модераторского канала.
    """
    query = update.callback_query
    if not query:
        return
    
    await query.answer()
    
    chat_id = int(query.data.split(":")[1])
    
    storage = get_storage()
    chat_config = storage.chat_configs.get_by_chat_id(chat_id)
    
    if not chat_config:
        await query.edit_message_text("❌ Конфигурация чата не найдена.")
        return
    
    if not context.user_data:
        context.user_data = {}
    context.user_data["awaiting_moderator_channel_for"] = chat_id
    
    message = (
        "📢 <b>Настройка модераторского канала</b>\n\n"
        "Модераторский канал — это приватный канал для уведомлений о спаме.\n\n"
        "<b>Шаги настройки:</b>\n\n"
        "1️⃣ Создай новый <b>приватный канал</b> (не группу!)\n"
        "   • Telegram → Новый канал\n"
        "   • Назови его, например: \"DespamLy: {chat_title}\"\n"
        "   • Сделай канал приватным\n\n"
        "2️⃣ Добавь этого бота (@{bot_username}) в канал как <b>администратора</b>\n"
        "   • Канал → Администраторы → Добавить администратора\n"
        "   • Выбери @{bot_username}\n"
        "   • Дай право \"Публиковать сообщения\"\n\n"
        "3️⃣ Перешли боту <b>любое сообщение</b> из этого канала\n"
        "   • Открой канал\n"
        "   • Нажми на любое сообщение → \"Переслать\"\n"
        "   • Перешли мне в личные сообщения\n\n"
        "Я автоматически определю ID канала и сохраню настройку.\n\n"
        "<i>После настройки тебе станут доступны все режимы работы.</i>"
    ).format(
        chat_title=chat_config.chat_title or "Твой чат",
        bot_username=context.bot.username
    )
    
    keyboard = [
        [InlineKeyboardButton("◀️ Назад к настройкам", callback_data=f"chat_menu:{chat_id}")],
    ]
    
    await query.edit_message_text(
        message,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def on_forwarded_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обработка пересланного сообщения для настройки модераторского канала.
    """
    message = update.effective_message
    if not message or not message.forward_origin:
        return
    
    if message.chat.type != "private":
        return
    
    user_id = update.effective_user.id
    
    if not context.user_data or "awaiting_moderator_channel_for" not in context.user_data:
        return
    
    chat_id = context.user_data.get("awaiting_moderator_channel_for")
    if not chat_id:
        return
    
    storage = get_storage()
    chat_config = storage.chat_configs.get_by_chat_id(chat_id)
    
    if not chat_config:
        await message.reply_text("❌ Конфигурация чата не найдена.")
        del context.user_data["awaiting_moderator_channel_for"]
        return
    
    if chat_config.owner_id != user_id:
        await message.reply_text("❌ Только владелец чата может настроить модераторский канал.")
        del context.user_data["awaiting_moderator_channel_for"]
        return
    
    from telegram.constants import MessageOriginType
    if message.forward_origin.type != MessageOriginType.CHANNEL:
        await message.reply_text(
            "❌ Это не сообщение из канала.\n\n"
            "Перешли сообщение именно из <b>канала</b>, а не из группы или от пользователя.",
            parse_mode=ParseMode.HTML
        )
        return
    
    channel_id = message.forward_origin.chat.id
    channel_title = message.forward_origin.chat.title
    
    try:
        bot_member = await context.bot.get_chat_member(channel_id, context.bot.id)
        if bot_member.status not in ("administrator", "creator"):
            await message.reply_text(
                "❌ Бот не является администратором этого канала.\n\n"
                "Добавь бота в канал как администратора с правом \"Публиковать сообщения\".",
                parse_mode=ParseMode.HTML
            )
            return
        
        if not bot_member.can_post_messages:
            await message.reply_text(
                "❌ У бота нет права публиковать сообщения в канале.\n\n"
                "Дай боту право \"Публиковать сообщения\" в настройках администратора.",
                parse_mode=ParseMode.HTML
            )
            return
    except Exception as e:
        LOGGER.error(f"Failed to check bot permissions in channel {channel_id}: {e}")
        await message.reply_text(
            "❌ Не удалось проверить права бота в канале.\n\n"
            "Убедись, что бот добавлен в канал как администратор.",
            parse_mode=ParseMode.HTML
        )
        return
    
    storage.chat_configs.update(chat_id, moderator_channel_id=channel_id)
    
    del context.user_data["awaiting_moderator_channel_for"]
    
    await message.reply_text(
        f"✅ <b>Модераторский канал настроен!</b>\n\n"
        f"<b>Канал:</b> {channel_title}\n"
        f"<b>ID:</b> <code>{channel_id}</code>\n\n"
        f"Теперь все уведомления о спаме будут приходить в этот канал.\n"
        f"Тебе стали доступны все режимы работы.\n\n"
        f"Используй /mychats для управления настройками.",
        parse_mode=ParseMode.HTML
    )
    
    LOGGER.info(f"Moderator channel {channel_id} set for chat {chat_id} by user {user_id}")
