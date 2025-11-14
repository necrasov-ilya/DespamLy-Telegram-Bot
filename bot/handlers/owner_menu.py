"""Owner chat management menu via /mychats command."""
from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from storage import get_storage
from utils.logger import get_logger

LOGGER = get_logger(__name__)


async def cmd_mychats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show list of owner's chats (works both in DM and groups)."""
    if not update.effective_user or not update.effective_message:
        return
    
    owner_id = update.effective_user.id
    storage = get_storage()
    chats = storage.chat_configs.get_by_owner_id(owner_id)
    
    if not chats:
        await update.effective_message.reply_html(
            "📭 <b>У тебя пока нет чатов</b>\n\n"
            "Чтобы добавить бота в чат:\n"
            "1. Открой групповой чат\n"
            "2. Нажми на название чата\n"
            "3. Добавь участников → найди меня\n"
            "4. Сделай меня администратором\n\n"
            "После добавления я появлюсь здесь!"
        )
        return
    
    message = f"🏠 <b>Твои чаты ({len(chats)})</b>\n\n"
    
    keyboard = []
    for chat in chats:
        status_emoji = "✅" if chat.is_active else "⚠️"
        mode_emoji = {
            "delete_only": "🗑️",
            "delete_and_ban": "⛔",
            "notify_only": "🔍",
        }.get(chat.policy_mode, "❓")
        
        chat_title = chat.chat_title or f"Chat {chat.chat_id}"
        button_text = f"{status_emoji} {chat_title} {mode_emoji}"
        
        keyboard.append([
            InlineKeyboardButton(
                button_text,
                callback_data=f"chat_menu:{chat.chat_id}"
            )
        ])
    
    keyboard.append([
        InlineKeyboardButton("❓ Справка", callback_data="help_mychats")
    ])
    
    await update.effective_message.reply_html(
        message + 
        "<i>Выбери чат для настройки:</i>\n\n"
        "Легенда:\n"
        "✅ - активен  ⚠️ - не настроен\n"
        "🗑️ - удаление  ⛔ - бан  🔍 - мониторинг",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def on_chat_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обработка callback для меню конкретного чата.
    Format: chat_menu:<chat_id>
    """
    query = update.callback_query
    if not query:
        return
    
    await query.answer()
    
    parts = query.data.split(":")
    if len(parts) != 2:
        await query.edit_message_text("❌ Ошибка формата данных")
        return
    
    try:
        chat_id = int(parts[1])
    except ValueError:
        await query.edit_message_text("❌ Неверный ID чата")
        return
    
    storage = get_storage()
    chat_config = storage.chat_configs.get_by_chat_id(chat_id)
    
    if not chat_config:
        await query.edit_message_text("❌ Чат не найден")
        return
    
    if chat_config.owner_id != query.from_user.id:
        await query.answer("❌ Ты не владелец этого чата", show_alert=True)
        return
    
    status = "✅ Активен" if chat_config.is_active else "⚠️ Не активен"
    mode_name = {
        "delete_only": "🗑️ Удаление спама",
        "delete_and_ban": "⛔ Удаление + бан",
        "notify_only": "🔍 Только уведомления",
    }.get(chat_config.policy_mode, "❓ Неизвестно")
    
    mod_channel = "✅ Настроен" if chat_config.moderator_channel_id else "❌ Не настроен"
    
    message = (
        f"⚙️ <b>Настройки чата</b>\n"
        f"<b>Название:</b> {chat_config.chat_title or 'Неизвестно'}\n"
        f"<b>Статус:</b> {status}\n"
        f"<b>Режим:</b> {mode_name}\n"
        f"<b>Модераторский канал:</b> {mod_channel}\n\n"
        f"<b>Пороги:</b>\n"
        f" • Удаление: {chat_config.meta_delete:.0%}\n"
        f" • Бан: {chat_config.meta_kick:.0%}\n\n"
        f"<b>Whitelist:</b> {len(chat_config.whitelist) if chat_config.whitelist else 0} пользователей"
    )
    
    keyboard = []
    
    if chat_config.is_active:
        keyboard.append([
            InlineKeyboardButton("⏸️ Приостановить защиту", callback_data=f"pause:{chat_id}")
        ])
    else:
        keyboard.append([
            InlineKeyboardButton("▶️ Активировать защиту", callback_data=f"activate:{chat_id}")
        ])
    
    keyboard.append([
        InlineKeyboardButton("🔄 Изменить режим", callback_data=f"change_mode:{chat_id}")
    ])
    
    if not chat_config.moderator_channel_id:
        keyboard.append([
            InlineKeyboardButton("📢 Настроить модераторский канал", callback_data=f"setup_moderator:{chat_id}")
        ])
    else:
        keyboard.append([
            InlineKeyboardButton("📢 Изменить модераторский канал", callback_data=f"setup_moderator:{chat_id}")
        ])
    
    keyboard.append([
        InlineKeyboardButton("⭐ Управление whitelist", callback_data=f"whitelist_menu:{chat_id}")
    ])
    keyboard.append([
        InlineKeyboardButton("📊 Статистика (7 дней)", callback_data=f"stats:{chat_id}")
    ])
    keyboard.append([
        InlineKeyboardButton("🗑️ Удалить чат", callback_data=f"delete_chat:{chat_id}")
    ])
    keyboard.append([
        InlineKeyboardButton("◀️ Назад к списку", callback_data="back_to_mychats")
    ])
    
    await query.edit_message_text(
        message,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def on_activate_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Активация защиты для чата."""
    query = update.callback_query
    if not query:
        return
    
    await query.answer()
    
    chat_id = int(query.data.split(":")[1])
    storage = get_storage()
    
    try:
        storage.chat_configs.update(chat_id, is_active=True)
        await query.answer("✅ Защита активирована!", show_alert=True)
        await on_chat_menu_callback(update, context)
        
        LOGGER.info(f"Chat {chat_id} activated by user {query.from_user.id}")
    except Exception as e:
        LOGGER.error(f"Failed to activate chat {chat_id}: {e}")
        await query.answer("❌ Ошибка активации", show_alert=True)


async def on_pause_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Приостановка защиты для чата."""
    query = update.callback_query
    if not query:
        return
    
    await query.answer()
    
    chat_id = int(query.data.split(":")[1])
    storage = get_storage()
    
    try:
        storage.chat_configs.update(chat_id, is_active=False)
        await query.answer("⏸️ Защита приостановлена", show_alert=True)
        await on_chat_menu_callback(update, context)
        
        LOGGER.info(f"Chat {chat_id} paused by user {query.from_user.id}")
    except Exception as e:
        LOGGER.error(f"Failed to pause chat {chat_id}: {e}")
        await query.answer("❌ Ошибка", show_alert=True)


async def on_change_mode_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Меню выбора режима работы."""
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
    
    has_channel = chat_config.moderator_channel_id is not None
    
    message = (
        "🔄 <b>Выбери режим защиты:</b>\n\n"
        "<b>🗑️ Удаление спама</b> (рекомендуется)\n"
        "Удаляет спам-сообщения, не банит пользователей\n\n"
        "<b>⛔ Удаление + бан</b> (агрессивный)\n"
        "Удаляет спам и банит при высокой уверенности\n\n"
        "<b>🔍 Только уведомления</b> (тестовый)\n"
        "Не удаляет, только отправляет уведомления"
    )
    
    if not has_channel:
        message += "\n\n⚠️ <i>Режимы с баном и уведомлениями требуют настройки модераторского канала</i>"
    
    keyboard = [
        [InlineKeyboardButton("🗑️ Удаление спама", callback_data=f"set_mode:{chat_id}:delete_only")],
        [InlineKeyboardButton(
            "🔒 Удаление + бан" if not has_channel else "⛔ Удаление + бан",
            callback_data=f"set_mode:{chat_id}:delete_and_ban"
        )],
        [InlineKeyboardButton(
            "🔒 Только уведомления" if not has_channel else "🔍 Только уведомления",
            callback_data=f"set_mode:{chat_id}:notify_only"
        )],
        [InlineKeyboardButton("◀️ Назад", callback_data=f"chat_menu:{chat_id}")],
    ]
    
    await query.edit_message_text(
        message,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def on_set_mode_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Установка режима работы."""
    query = update.callback_query
    if not query:
        return
    
    parts = query.data.split(":")
    chat_id = int(parts[1])
    new_mode = parts[2]
    
    storage = get_storage()
    
    chat_config = storage.chat_configs.get_by_chat_id(chat_id)
    if not chat_config:
        await query.answer("❌ Конфигурация чата не найдена", show_alert=True)
        return
    
    if new_mode in ("delete_and_ban", "notify_only") and not chat_config.moderator_channel_id:
        await query.answer(
            "⚠️ Этот режим требует настройки модераторского канала.\n\n"
            "Вернитесь в меню чата и нажмите '📢 Настроить модераторский канал'",
            show_alert=True
        )
        return
    
    try:
        storage.chat_configs.update(chat_id, policy_mode=new_mode)
        
        mode_names = {
            "delete_only": "🗑️ Удаление спама",
            "delete_and_ban": "⛔ Удаление + бан",
            "notify_only": "🔍 Только уведомления",
        }
        
        await query.answer(f"✅ Режим изменён: {mode_names.get(new_mode)}", show_alert=True)
        update.callback_query.data = f"chat_menu:{chat_id}"
        await on_chat_menu_callback(update, context)
        
        LOGGER.info(f"Chat {chat_id} mode changed to {new_mode} by user {query.from_user.id}")
    except Exception as e:
        LOGGER.error(f"Failed to set mode for chat {chat_id}: {e}")
        await query.answer("❌ Ошибка изменения режима", show_alert=True)


async def on_back_to_mychats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Возврат к списку чатов."""
    query = update.callback_query
    if not query:
        return
    
    await query.answer()
    await cmd_mychats(update, context)


async def on_help_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает справку по управлению чатами."""
    query = update.callback_query
    if not query:
        return
    
    await query.answer()
    
    message = (
        "📖 <b>Справка по управлению</b>\n\n"
        "<b>Легенда статусов:</b>\n"
        "✅ - Защита активна\n"
        "⚠️ - Защита приостановлена\n\n"
        "<b>Режимы работы:</b>\n"
        "🗑️ - Удаление спама (рекомендуется)\n"
        "⛔ - Удаление + бан (агрессивный)\n"
        "🔍 - Только уведомления (тестовый)\n\n"
        "<b>Команды в группе:</b>\n"
        "/status - Статус защиты\n"
        "/pause - Приостановить\n"
        "/resume - Возобновить\n"
        "/test {текст} - Тестировать бота\n\n"
        "<b>Управление:</b>\n"
        "• Настройка порогов срабатывания\n"
        "• Whitelist для доверенных пользователей\n"
        "• Статистика за последние 7 дней\n"
        "• Удаление чата из списка"
    )
    
    keyboard = [[
        InlineKeyboardButton("◀️ Назад к списку", callback_data="back_to_mychats")
    ]]
    
    await query.edit_message_text(
        message,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
