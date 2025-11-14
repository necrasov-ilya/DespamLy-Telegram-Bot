"""Automatic chat registration when bot is added."""
from __future__ import annotations

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatMemberStatus, ParseMode
from telegram.ext import ContextTypes

from storage import get_storage, ChatConfigInput
from utils.logger import get_logger

LOGGER = get_logger(__name__)


async def on_my_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle bot being added to or removed from a chat."""
    if not update.my_chat_member:
        return
    
    chat_member = update.my_chat_member
    chat = update.effective_chat
    new_status = chat_member.new_chat_member.status
    old_status = chat_member.old_chat_member.status
    
    if not chat or not chat_member.from_user:
        return
    
    storage = get_storage()
    owner_id = chat_member.from_user.id
    
    # СЦЕНАРИЙ: Бот добавлен в чат
    if new_status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.MEMBER) and \
       old_status in (ChatMemberStatus.LEFT, ChatMemberStatus.BANNED):
        
        LOGGER.info(f"Bot added to chat {chat.id} ({chat.title}) by user {owner_id}")
        
        # Проверяем: есть ли уже конфигурация? (повторное добавление)
        existing_config = storage.chat_configs.get_by_chat_id(chat.id)
        
        if existing_config:
            # СЦЕНАРИЙ: Повторное добавление — восстанавливаем настройки
            LOGGER.info(f"Bot re-added to chat {chat.id}, showing restore options")
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    "✅ Восстановить защиту",
                    callback_data=f"restore_config:{chat.id}"
                )],
                [InlineKeyboardButton(
                    "🔄 Начать заново",
                    callback_data=f"reset_config:{chat.id}"
                )]
            ])
            
            has_moderator = "✅" if existing_config.moderator_channel_id else "❌"
            mode_emoji = {"delete_only": "🗑️", "delete_and_ban": "⛔", "notify_only": "🔍"}
            mode_name = mode_emoji.get(existing_config.policy_mode, "❓")
            
            await context.bot.send_message(
                chat_id=chat.id,
                text=(
                    "👋 <b>С возвращением!</b>\n\n"
                    f"Я помню этот чат. У тебя были настройки:\n\n"
                    f"• Режим: {mode_name} {existing_config.policy_mode}\n"
                    f"• Модераторская группа: {has_moderator}\n"
                    f"• Whitelist: {len(existing_config.whitelist or [])} пользователей\n\n"
                    f"Хочешь восстановить защиту или начать заново?"
                ),
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard
            )
            return
        
        # СЦЕНАРИЙ: Первое добавление — создаём конфигурацию
        config = ChatConfigInput(
            chat_id=chat.id,
            chat_title=chat.title,
            chat_type=chat.type,
            owner_id=owner_id,
            policy_mode="delete_only",
            is_active=False
        )
        
        try:
            storage.chat_configs.upsert(config)
            LOGGER.info(f"Chat config created for chat {chat.id}")
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Включить защиту", callback_data=f"activate_initial:{chat.id}")]
            ])
            
            await context.bot.send_message(
                chat_id=chat.id,
                text=(
                    "👋 <b>Привет! Я DespamLy</b> — бот для защиты от спама.\n\n"
                    "Я автоматически обнаруживаю и удаляю спам с помощью ML-моделей.\n\n"
                    "Нажми кнопку ниже, чтобы включить защиту.\n"
                    "Для расширенных настроек используй команду /mychats в личных сообщениях со мной.\n\n"
                    "📖 Подробная инструкция: /primer"
                ),
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard
            )
            
            try:
                await context.bot.send_message(
                    chat_id=owner_id,
                    text=(
                        f"✅ Я добавлен в чат <b>{chat.title}</b>\n\n"
                        f"Напиши мне /mychats чтобы настроить защиту от спама."
                    ),
                    parse_mode=ParseMode.HTML
                )
            except Exception as e:
                LOGGER.warning(f"Failed to send DM to owner {owner_id}: {e}")
                
        except Exception as e:
            LOGGER.error(f"Failed to create chat config for {chat.id}: {e}")
    
    # СЦЕНАРИЙ: Бот удалён из чата
    elif new_status in (ChatMemberStatus.LEFT, ChatMemberStatus.BANNED) and \
         old_status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.MEMBER):
        
        LOGGER.info(f"Bot removed from chat {chat.id} ({chat.title})")
        
        # Проверяем: это основной чат или модераторская группа?
        main_chat = storage.chat_configs.get_by_chat_id(chat.id)
        
        if main_chat:
            # СЦЕНАРИЙ: Удалён из основного чата
            LOGGER.info(f"Bot removed from main chat {chat.id}")
            
            try:
                storage.chat_configs.update(chat.id, is_active=False)
                LOGGER.info(f"Chat {chat.id} deactivated")
                
                # Уведомляем владельца
                try:
                    await context.bot.send_message(
                        chat_id=main_chat.owner_id,
                        text=(
                            f"⚠️ <b>Бот удалён из чата</b>\n\n"
                            f"Я был удалён из чата <b>{chat.title}</b>.\n\n"
                            f"<b>Что сохранилось:</b>\n"
                            f"• Все настройки\n"
                            f"• Модераторская группа\n"
                            f"• Whitelist\n"
                            f"• Статистика\n\n"
                            f"Если добавишь меня обратно, защита восстановится автоматически."
                        ),
                        parse_mode=ParseMode.HTML
                    )
                except Exception as e:
                    LOGGER.warning(f"Failed to notify owner {main_chat.owner_id}: {e}")
                    
            except Exception as e:
                LOGGER.error(f"Failed to deactivate chat {chat.id}: {e}")
            return
        
        # СЦЕНАРИЙ: Может это модераторская группа?
        affected_chats = storage.chat_configs.get_by_moderator_channel_id(chat.id)
        
        if affected_chats:
            LOGGER.info(f"Bot removed from moderator group {chat.id}, affecting {len(affected_chats)} chats")
            
            for affected_chat in affected_chats:
                old_mode = affected_chat.policy_mode
                
                try:
                    # Сбрасываем модераторскую группу и режим
                    storage.chat_configs.update(
                        affected_chat.chat_id,
                        moderator_channel_id=None,
                        policy_mode="delete_only"
                    )
                    
                    mode_changed = old_mode != "delete_only"
                    
                    # Уведомляем владельца
                    try:
                        message = (
                            f"⚠️ <b>Модераторская группа отключена</b>\n\n"
                            f"Я был удалён из модераторской группы для чата <b>{affected_chat.chat_title}</b>.\n\n"
                            f"<b>Что изменилось:</b>\n"
                        )
                        
                        if mode_changed:
                            message += f"• Режим переключен на 'Удаление спама'\n"
                        
                        message += (
                            f"• Модераторская группа отключена\n"
                            f"• Режимы с баном и уведомлениями недоступны\n\n"
                            f"<b>Защита продолжает работать</b> в режиме удаления спама.\n\n"
                            f"Чтобы настроить новую модераторскую группу:\n"
                            f"/mychats → выбери чат → Настроить модераторскую группу"
                        )
                        
                        await context.bot.send_message(
                            chat_id=affected_chat.owner_id,
                            text=message,
                            parse_mode=ParseMode.HTML
                        )
                        LOGGER.info(f"Notified owner {affected_chat.owner_id} about moderator group removal")
                    except Exception as e:
                        LOGGER.error(f"Failed to notify owner {affected_chat.owner_id}: {e}")
                        
                except Exception as e:
                    LOGGER.error(f"Failed to reset moderator group for chat {affected_chat.chat_id}: {e}")


async def on_activate_initial_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Callback: activate_initial:<chat_id>
    Активация защиты при первоначальной настройке с проверкой прав админа.
    """
    query = update.callback_query
    if not query:
        return
    
    await query.answer()
    
    chat_id = int(query.data.split(":")[1])
    user_id = query.from_user.id
    
    try:
        chat_member = await context.bot.get_chat_member(chat_id, user_id)
        
        if chat_member.status not in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER):
            await query.answer(
                "❌ Только администраторы могут включать защиту от спама",
                show_alert=True
            )
            return
        
        bot_member = await context.bot.get_chat_member(chat_id, context.bot.id)
        
        if bot_member.status != ChatMemberStatus.ADMINISTRATOR:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Попробовать снова", callback_data=f"activate_initial:{chat_id}")]
            ])
            await query.edit_message_text(
                "❌ <b>Недостаточно прав</b>\n\n"
                "Чтобы удалять спам, мне нужны права администратора с разрешением:\n"
                "• Удаление сообщений\n\n"
                "Дай мне эти права и нажми кнопку ниже.",
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard
            )
            return
        
        if not bot_member.can_delete_messages:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Попробовать снова", callback_data=f"activate_initial:{chat_id}")]
            ])
            await query.edit_message_text(
                "❌ <b>Недостаточно прав</b>\n\n"
                "У меня есть права администратора, но нет права <b>удалять сообщения</b>.\n\n"
                "Добавь это право в настройках администратора и нажми кнопку ниже.",
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard
            )
            return
    
    except Exception as e:
        LOGGER.error(f"Failed to check permissions for chat {chat_id}: {e}")
        await query.edit_message_text(
            "❌ <b>Ошибка проверки прав</b>\n\n"
            "Не удалось проверить права доступа.\n"
            "Попробуй позже или обратись в поддержку.\n\n"
            f"<code>{str(e)}</code>",
            parse_mode=ParseMode.HTML
        )
        return
    
    storage = get_storage()
    
    try:
        storage.chat_configs.update(chat_id, is_active=True)
        
        await query.edit_message_text(
            "✅ <b>Защита включена!</b>\n\n"
            "Я начал мониторить сообщения в этом чате.\n"
            "Спам-сообщения будут автоматически удаляться.\n\n"
            "Для расширенных настроек используй /mychats в личных сообщениях со мной.",
            parse_mode=ParseMode.HTML
        )
        
        LOGGER.info(f"Chat {chat_id} activated by user {user_id} via initial setup")
        
    except Exception as e:
        LOGGER.error(f"Failed to activate chat {chat_id}: {e}")
        await query.edit_message_text(
            "❌ <b>Ошибка активации</b>\n\n"
            "Не удалось активировать защиту.\n"
            "Попробуй позже или обратись в поддержку.\n\n"
            f"<code>{str(e)}</code>",
            parse_mode=ParseMode.HTML
        )


async def on_restore_config_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Callback: restore_config:<chat_id>
    Восстановить прежнюю конфигурацию при повторном добавлении бота.
    """
    query = update.callback_query
    if not query:
        return
    
    await query.answer()
    
    chat_id = int(query.data.split(":")[1])
    user_id = query.from_user.id
    
    # Проверка прав
    try:
        chat_member = await context.bot.get_chat_member(chat_id, user_id)
        if chat_member.status not in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER):
            await query.answer(
                "❌ Только администраторы могут восстанавливать защиту",
                show_alert=True
            )
            return
    except Exception as e:
        LOGGER.error(f"Failed to check admin status: {e}")
        await query.answer("❌ Ошибка проверки прав", show_alert=True)
        return
    
    storage = get_storage()
    
    try:
        # Просто активируем с прежними настройками
        storage.chat_configs.update(chat_id, is_active=True)
        
        await query.edit_message_text(
            "✅ <b>Защита восстановлена!</b>\n\n"
            "Все прежние настройки активированы.\n"
            "Я продолжу работу с сохранёнными параметрами.\n\n"
            "Для изменений используй /mychats в личных сообщениях.",
            parse_mode=ParseMode.HTML
        )
        
        LOGGER.info(f"Chat {chat_id} restored by user {user_id}")
        
    except Exception as e:
        LOGGER.error(f"Failed to restore chat {chat_id}: {e}")
        await query.answer("❌ Ошибка восстановления", show_alert=True)


async def on_reset_config_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Callback: reset_config:<chat_id>
    Сбросить конфигурацию и начать заново.
    """
    query = update.callback_query
    if not query:
        return
    
    await query.answer()
    
    chat_id = int(query.data.split(":")[1])
    user_id = query.from_user.id
    chat = update.effective_chat
    
    # Проверка прав
    try:
        chat_member = await context.bot.get_chat_member(chat_id, user_id)
        if chat_member.status not in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER):
            await query.answer(
                "❌ Только администраторы могут сбрасывать настройки",
                show_alert=True
            )
            return
    except Exception as e:
        LOGGER.error(f"Failed to check admin status: {e}")
        await query.answer("❌ Ошибка проверки прав", show_alert=True)
        return
    
    storage = get_storage()
    
    try:
        # Создаём новую конфигурацию (сбрасываем старую)
        config = ChatConfigInput(
            chat_id=chat_id,
            chat_title=chat.title if chat else None,
            chat_type=chat.type if chat else "group",
            owner_id=user_id,
            policy_mode="delete_only",
            is_active=False
        )
        
        storage.chat_configs.upsert(config)
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Включить защиту", callback_data=f"activate_initial:{chat_id}")]
        ])
        
        await query.edit_message_text(
            "🔄 <b>Настройки сброшены</b>\n\n"
            "Начинаем с чистого листа.\n"
            "Нажми кнопку ниже, чтобы включить защиту.",
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard
        )
        
        LOGGER.info(f"Chat {chat_id} config reset by user {user_id}")
        
    except Exception as e:
        LOGGER.error(f"Failed to reset chat {chat_id}: {e}")
        await query.answer("❌ Ошибка сброса настроек", show_alert=True)
