"""
Меню управления чатами в личных сообщениях владельца.
Команда /mychats показывает список чатов и меню настройки.
"""
from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from storage import get_storage
from utils.logger import get_logger

LOGGER = get_logger(__name__)


async def cmd_mychats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Команда /mychats - показывает список чатов владельца.
    Работает только в личных сообщениях.
    """
    if not update.effective_user or not update.effective_message:
        return
    
    # Проверка что команда в ЛС
    if update.effective_message.chat.type != "private":
        await update.effective_message.reply_text(
            "❌ Эта команда работает только в личных сообщениях.\n"
            "Напиши мне в ЛС: @YourBotUsername"
        )
        return
    
    owner_id = update.effective_user.id
    storage = get_storage()
    
    # Получаем все чаты владельца
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
    
    # Формируем список с кнопками
    message = f"🏠 <b>Твои чаты ({len(chats)})</b>\n\n"
    
    keyboard = []
    for chat in chats:
        # Статус чата
        status_emoji = "✅" if chat.is_active else "⚠️"
        mode_emoji = {
            "delete_only": "🗑️",
            "delete_and_ban": "⛔",
            "notify_only": "🔍",
        }.get(chat.policy_mode, "❓")
        
        # Название кнопки
        chat_title = chat.chat_title or f"Chat {chat.chat_id}"
        button_text = f"{status_emoji} {chat_title} {mode_emoji}"
        
        keyboard.append([
            InlineKeyboardButton(
                button_text,
                callback_data=f"chat_menu:{chat.chat_id}"
            )
        ])
    
    # Кнопка справки
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
    
    # Извлекаем chat_id
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
    
    # Проверка владельца
    if chat_config.owner_id != query.from_user.id:
        await query.answer("❌ Ты не владелец этого чата", show_alert=True)
        return
    
    # Формируем меню чата
    status = "✅ Активен" if chat_config.is_active else "⚠️ Не активен"
    mode_name = {
        "delete_only": "🗑️ Удаление спама",
        "delete_and_ban": "⛔ Удаление + бан",
        "notify_only": "🔍 Только уведомления",
    }.get(chat_config.policy_mode, "❓ Неизвестно")
    
    message = (
        f"⚙️ <b>Настройки чата</b>\n"
        f"<b>Название:</b> {chat_config.chat_title or 'Неизвестно'}\n"
        f"<b>Статус:</b> {status}\n"
        f"<b>Режим:</b> {mode_name}\n\n"
        f"<b>Пороги:</b>\n"
        f" • Удаление: {chat_config.meta_delete:.2f}\n"
        f" • Бан: {chat_config.meta_kick:.2f}\n\n"
        f"<b>Whitelist:</b> {len(chat_config.whitelist) if chat_config.whitelist else 0} пользователей"
    )
    
    # Кнопки действий
    keyboard = []
    
    # Кнопка активации/деактивации
    if chat_config.is_active:
        keyboard.append([
            InlineKeyboardButton("⏸️ Приостановить защиту", callback_data=f"pause:{chat_id}")
        ])
    else:
        keyboard.append([
            InlineKeyboardButton("▶️ Активировать защиту", callback_data=f"activate:{chat_id}")
        ])
    
    # Кнопка изменения режима
    keyboard.append([
        InlineKeyboardButton("🔄 Изменить режим", callback_data=f"change_mode:{chat_id}")
    ])
    
    # Кнопка whitelist
    keyboard.append([
        InlineKeyboardButton("⭐ Управление whitelist", callback_data=f"whitelist:{chat_id}")
    ])
    
    # Кнопка статистики
    keyboard.append([
        InlineKeyboardButton("📊 Статистика (7 дней)", callback_data=f"stats:{chat_id}")
    ])
    
    # Кнопка удаления
    keyboard.append([
        InlineKeyboardButton("🗑️ Удалить чат", callback_data=f"delete_chat:{chat_id}")
    ])
    
    # Кнопка назад
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
        
        # Обновляем меню
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
        
        # Обновляем меню
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
    
    message = (
        "🔄 <b>Выбери режим защиты:</b>\n\n"
        "<b>🗑️ Удаление спама</b> (рекомендуется)\n"
        "Удаляет спам-сообщения, не банит пользователей\n\n"
        "<b>⛔ Удаление + бан</b> (агрессивный)\n"
        "Удаляет спам и банит при высокой уверенности\n\n"
        "<b>🔍 Только уведомления</b> (тестовый)\n"
        "Не удаляет, только отправляет уведомления"
    )
    
    keyboard = [
        [InlineKeyboardButton("🗑️ Удаление спама", callback_data=f"set_mode:{chat_id}:delete_only")],
        [InlineKeyboardButton("⛔ Удаление + бан", callback_data=f"set_mode:{chat_id}:delete_and_ban")],
        [InlineKeyboardButton("🔍 Только уведомления", callback_data=f"set_mode:{chat_id}:notify_only")],
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
    
    await query.answer()
    
    parts = query.data.split(":")
    chat_id = int(parts[1])
    new_mode = parts[2]
    
    storage = get_storage()
    
    try:
        storage.chat_configs.update(chat_id, policy_mode=new_mode)
        
        mode_names = {
            "delete_only": "🗑️ Удаление спама",
            "delete_and_ban": "⛔ Удаление + бан",
            "notify_only": "🔍 Только уведомления",
        }
        
        await query.answer(f"✅ Режим изменён: {mode_names.get(new_mode)}", show_alert=True)
        
        # Возвращаемся в меню чата
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
    
    # Эмулируем команду /mychats
    await cmd_mychats(update, context)
